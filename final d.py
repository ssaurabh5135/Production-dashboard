import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# ------------------ PAGE CONFIG ------------------
st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

# ------------------ CONFIG ------------------
IMAGE_PATH = "winter.jpg"
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
DASHBOARD_SHEET = "Dashboard"
SALES_REPORT_SHEET = "Sales Report"
TARGET_SALE = 19_92_00_000

# ------------------ HELPERS ------------------
def load_image_base64(path: str) -> str:
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except Exception:
        # If image not found, just no background – no extra messages
        return ""

def format_inr(n):
    """Format number in Indian style, handle strings with commas/decimals."""
    try:
        s = str(n).replace(",", "").strip()
        x_int = int(float(s))
        x = str(x_int)
    except Exception:
        return str(n)

    if len(x) <= 3:
        return x
    last3 = x[-3:]
    rest = x[:-3]
    rest = ''.join([
        rest[::-1][i:i+2][::-1] + ','
        for i in range(0, len(rest), 2)
    ][::-1])
    return rest + last3

def ensure_pct(x):
    """Convert values like 0.88, 88, '88%', '1.6%' → 88.0, 88.0, 88.0, 1.6 etc."""
    try:
        if isinstance(x, str):
            x = x.replace('%', '').replace(',', '').strip()
        val = float(x)
        # If value is <= 1, treat as decimal fraction (0.88 → 88%)
        return val * 100 if val <= 1 else val
    except Exception:
        return 0.0

def to_numeric_series(s: pd.Series) -> pd.Series:
    """Convert series with commas etc to numeric."""
    return pd.to_numeric(
        s.astype(str).str.replace(",", "").str.strip(),
        errors="coerce"
    )

# ------------------ GOOGLE AUTH (NO DEBUG TEXT) ------------------
try:
    creds_info = st.secrets["gcp_service_account"]
except KeyError:
    st.error("Missing gcp_service_account in Streamlit secrets.")
    st.stop()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
client = gspread.authorize(creds)

# ------------------ OPEN SHEET ------------------
try:
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.worksheet(DASHBOARD_SHEET)
except Exception as e:
    st.error(f"Cannot open spreadsheet or worksheet: {e}")
    st.stop()

# ------------------ LOAD A1:H STRICT ------------------
rows = worksheet.get_values("A1:H")
if not rows or len(rows) < 2:
    st.error("Dashboard sheet has no usable data in A1:H.")
    st.stop()

header = rows[0]       # A1:H1
data_rows = rows[1:]   # From row 2 down
data = [dict(zip(header, r)) for r in data_rows]

df = pd.DataFrame(data)
df.columns = [str(c) for c in df.columns]

if df.empty:
    st.error("Dashboard sheet empty.")
    st.stop()

# ------------------ CLEAN DATA ------------------
df.columns = df.columns.str.strip().str.lower()
df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors="coerce")
df = df.dropna(subset=[df.columns[0]]).sort_values(df.columns[0])
latest = df.iloc[-1]
cols = df.columns.tolist()

# Expected headers (in order) – based on what you told me
expected = [
    "date",
    "today's sale",
    "oee %",
    "plan vs actual %",
    "rejection amount (daybefore)",
    "rejection %",
    "rejection amount (cumulative)",
    "total sales (cumulative)",
]

if len(cols) < 8 or [c.strip().lower() for c in cols[:8]] != [e.lower() for e in expected]:
    st.error(f"Dashboard headers mismatch.\nFound: {cols}\nExpected (first 8): {expected}")
    st.stop()

(
    date_col,
    today_col,
    oee_col,
    plan_col,
    rej_day_col,
    rej_pct_col,
    rej_cum_col,
    total_cum_col,
) = cols[:8]

def get_val(row, col):
    try:
        return row[col]
    except Exception:
        return 0

# ------------------ KPI VALUES ------------------
today_sale_raw = get_val(latest, today_col)
oee_raw = get_val(latest, oee_col)
plan_vs_actual_raw = get_val(latest, plan_col)
rej_day_raw = get_val(latest, rej_day_col)
rej_pct_raw = get_val(latest, rej_pct_col)
rej_cum_raw = get_val(latest, rej_cum_col)

# Convert numeric columns properly (handle commas)
cum_series = to_numeric_series(df[total_cum_col]).dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0.0

# Percent conversions
oee = ensure_pct(oee_raw)
plan_vs_actual = ensure_pct(plan_vs_actual_raw)
rej_pct = ensure_pct(rej_pct_raw)

# Rejection amounts & today sale numeric (for charts)
today_sale_num = to_numeric_series(pd.Series([today_sale_raw])).iloc[0]
rej_day_num = to_numeric_series(pd.Series([rej_day_raw])).iloc[0]
rej_cum_num = to_numeric_series(pd.Series([rej_cum_raw])).iloc[0]

achieved_pct_val = round((total_cum / TARGET_SALE * 100) if TARGET_SALE else 0, 2)

# ------------------ COLORS ------------------
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ------------------ KPI GAUGE ------------------
gauge = go.Figure(
    go.Indicator(
        mode="gauge",
        value=achieved_pct_val,
        number={"suffix": "%", "font": {"size": 44, "color": GREEN}},
        domain={"x": [0, 1], "y": [0, 1]},
        gauge={
            "shape": "angular",
            "axis": {
                "range": [0, 100],
                "tickvals": [0, 25, 50, 75, 100],
                "ticktext": ["0%", "25%", "50%", "75%", "100%"],
            },
            "bar": {"color": GREEN, "thickness": 0.38},
            "bgcolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [0, 60], "color": "#c4eed1"},
                {"range": [60, 85], "color": "#7ee2b7"},
                {"range": [85, 100], "color": GREEN},
            ],
            "threshold": {"line": {"color": "#111", "width": 5}, "value": achieved_pct_val},
        },
    )
)
gauge.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=10, b=30, l=10, r=10),
    height=170,
    width=300,
)
gauge_html = gauge.to_html(include_plotlyjs="cdn", full_html=False)

# ------------------ SALES REPORT (OPTIONAL) ------------------
try:
    sr_ws = sh.worksheet(SALES_REPORT_SHEET)
    sr_data = sr_ws.get_all_records()
    sr = pd.DataFrame(sr_data)
    sr.columns = sr.columns.str.strip().str.lower()
    if "table_name" in sr.columns:
        sale_df = sr[sr["table_name"].str.lower() == "sale_summery"]
        rej_df = sr[sr["table_name"].str.lower() == "rejection_summery"]
        if sale_df.empty:
            sale_df = sr
        if rej_df.empty:
            rej_df = sr
    else:
        sale_df = sr
        rej_df = sr
except Exception:
    # Fallback – use Dashboard data
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

# ------------------ CLEANUP FOR CHARTS ------------------
sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
sale_df["sale amount"] = to_numeric_series(sale_df["sale amount"]).fillna(0)
sale_df = sale_df.dropna(subset=["date"]).sort_values("date")

rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
# auto-pick a rejection column if needed
rej_cols = [c for c in rej_df.columns if "rej" in c.lower()]
if rej_cols:
    rej_src_col = rej_cols[0]
else:
    rej_src_col = rej_df.columns[-1]
rej_df["rej amt"] = to_numeric_series(rej_df[rej_src_col]).fillna(0)
rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# ------------------ PLOTLY FIGURES ------------------
fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(x=sale_df["date"], y=sale_df["sale amount"], marker_color=BLUE))
fig_sale.update_layout(
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    autosize=True,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45),
    yaxis=dict(showgrid=False, tickfont=dict(size=12)),
)
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

fig_rej = go.Figure()
fig_rej.add_trace(
    go.Scatter(
        x=rej_df["date"],
        y=rej_df["rej amt"],
        mode="lines+markers",
        marker=dict(size=8, color=BUTTERFLY_ORANGE),
        line=dict(width=3, color=BUTTERFLY_ORANGE),
    )
)
fig_rej.update_layout(
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    autosize=True,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45),
    yaxis=dict(showgrid=False, tickfont=dict(size=12)),
)
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ------------------ BACKGROUND IMAGE ------------------
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# ------------------ HTML TEMPLATE (SAME UI AS YOUR ORIGINAL) ------------------
center_html = f"""
<div class="center-content" style='width:100%;height:100%;'>
  <div class="value-green">{achieved_pct_val}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale_num)
top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}%"
left_rej_pct = f"{round(rej_pct if pd.notna(rej_pct) else 0, 1)}%"
left_rej_day = format_inr(rej_day_num)
bottom_rej_cum = format_inr(rej_cum_num)

html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
:root {{
    --card-radius: 14px;
    --accent: {BUTTERFLY_ORANGE};
    --orange: {BUTTERFLY_ORANGE};
    --green: {GREEN};
    --blue: {BLUE};
}}
html,body,#root{{height:100%;}}
body {{
    margin:0;
    padding:18px;
    font-family: 'Poppins', sans-serif;
    background: url("{bg_url}") center/cover no-repeat fixed;
    color:#071024;
}}
.center-content {{
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    height: 100%;
    text-align: center;
}}
.container {{
    width: 100%;
    min-height: 98vh;
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    grid-template-rows: 130px 220px 140px;
    gap: 18px;
    row-gap: 30px;
}}
.card {{
    background: linear-gradient(180deg, rgba(255,255,255,0.13), rgba(255,255,255,0.06));
    border-radius: var(--card-radius);
    padding:0px;
    box-shadow: 0 6px 18px rgba(4, 8, 15, 0.22);
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(6px) saturate(120%);
    -webkit-backdrop-filter: blur(6px);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}}
.card .center-content {{
    width: 100%;
    align-items: center;
    justify-content: center;
}}
.top-card {{
    height: 100%;
    width: 100%;
    padding: 20px 0 0 0;
}}
.bottom-card {{
    height: 100%;
    width: 100%;
    padding: 10px 0 0 0;
}}
.chart-container {{
    width: 100%;
    height: 110px;
    max-width: 100%;
    overflow: hidden;
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    display: block;
}}
.value-orange {{
    color: {BUTTERFLY_ORANGE} !important;
    font-size: 34px !important;
    font-weight: 800 !important;
    width: 100%;
    text-align: center !important;
    margin-bottom: 2px !important;
}}
.value-blue {{
    color: {BLUE} !important;
    font-size: 34px !important;
    font-weight: 800 !important;
    width: 100%;
    text-align: center !important;
    margin-bottom: 2px !important;
}}
.value-green {{
    color: {GREEN} !important;
    font-size: 46px !important;
    font-weight: 800 !important;
    width: 100%;
    text-align: center !important;
    margin-bottom: 2px !important;
}}
.title-green {{
    color: {GREEN} !important;
    font-size: 26px !important;
    font-weight: 700 !important;
    margin-top: 4px !important;
}}
.title-black {{
    color: #000 !important;
    font-size: 15px !important;
    font-weight: 700 !important;
    margin-top: 6px !important;
    width: 100%;
    text-align: center !important;
}}
.chart-title-black {{
    color: #000 !important;
    font-size: 15px !important;
    font-weight: 700 !important;
    margin-bottom: 2px !important;
    width: 100%;
    text-align: left !important;
    padding-left: 6px;
}}
@media (max-width: 1100px) {{
    .container {{ grid-template-columns: 1fr; grid-template-rows: auto; }}
}}
</style>
</head>
<body>
<div class="container">

    <!-- Top Row -->
    <div class="card top-card">
        <div class="center-content">
            <div class="value-orange">{top_date}</div>
            <div class="title-black">Date</div>
        </div>
    </div>
    <div class="card top-card">
        <div class="center-content">
            <div class="value-blue">₹ {top_today_sale}</div>
            <div class="title-black">Today's Sale</div>
        </div>
    </div>
    <div class="card top-card">
        <div class="center-content">
            <div class="value-orange">{top_oee}</div>
            <div class="title-black">OEE %</div>
        </div>
    </div>

    <!-- Center/Middle Row -->
    <div class="card">
        <div class="center-content">
            <div class="value-orange">{left_rej_pct}</div>
            <div class="title-black">Rejection %</div>
        </div>
    </div>
    <div class="card">
        {center_html}
    </div>
    <div class="card">
        {gauge_html}
    </div>

    <!-- Bottom Row -->
    <div class="card bottom-card">
        <div class="center-content">
            <div class="value-orange">₹ {bottom_rej_cum}</div>
            <div class="title-black">Rejection (Cumulative)</div>
        </div>
    </div>
    <div class="card bottom-card">
        <div class="chart-title-black">Sale Trend</div>
        <div id="sale_chart_container" class="chart-container">{sale_html}</div>
    </div>
    <div class="card bottom-card">
        <div class="chart-title-black">Rejection Trend</div>
        <div id="rej_chart_container" class="chart-container">{rej_html}</div>
    </div>

</div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</body>
</html>
"""

st.components.v1.html(html_template, height=770, scrolling=True)
