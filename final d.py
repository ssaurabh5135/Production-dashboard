import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# ========== PAGE CONFIG ==========
st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

# ========== CONFIG ==========
IMAGE_PATH = "winter.jpg"  # image stored in repo
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
DASHBOARD_SHEET = "Dashboard"
SALES_REPORT_SHEET = "Sales Report"
TARGET_SALE = 19_92_00_000

# ========== HELPERS ==========
def load_image_base64(path: str) -> str:
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except Exception:
        # silently ignore, just no background
        return ""

def format_inr(n):
    try:
        x = str(int(float(n)))
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

def to_number(v):
    """
    Convert Google Sheets cell value to float:
    - handles "9630590", "1,23,456", "88%", "1.6%", " ₹ 123 "
    - returns 0 on failure
    """
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        # remove currency symbol
        s = s.replace("₹", "").replace(",", "").strip()
        # percentage like "88%" or "1.6%"
        if s.endswith("%"):
            s2 = s[:-1].strip()
            try:
                return float(s2)
            except Exception:
                return 0.0
        try:
            return float(s)
        except Exception:
            return 0.0
    return 0.0

# ========== GOOGLE SERVICE ACCOUNT AUTH ==========
try:
    creds_info = st.secrets["gcp_service_account"]
except Exception:
    st.error("Service account JSON not found in st.secrets['gcp_service_account'].")
    st.stop()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
try:
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    client = gspread.authorize(creds)
except Exception as e:
    st.error(f"Could not authorize Google service account: {e}")
    st.stop()

# ========== OPEN SPREADSHEET ==========
try:
    sh = client.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Could not open spreadsheet: {e}")
    st.stop()

# ========== LOAD DASHBOARD SHEET (A1:H) ==========
try:
    ws_dash = sh.worksheet(DASHBOARD_SHEET)
    rows = ws_dash.get_values("A1:H")
except Exception as e:
    st.error(f"Could not read Dashboard sheet: {e}")
    st.stop()

if not rows or len(rows) < 2:
    st.error("Dashboard sheet has no usable data in A1:H.")
    st.stop()

header = rows[0]
data_rows = rows[1:]
data = [dict(zip(header, r)) for r in data_rows]
df = pd.DataFrame(data)

# normalize headers like VS Code (lowercase, stripped)
df.columns = df.columns.str.strip().str.lower()

# parse date column (first column)
date_col = df.columns[0]
df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

# numeric conversion for remaining columns
for col in df.columns[1:]:
    df[col] = df[col].apply(to_number)

# drop rows with no date, sort by date, pick latest row
df = df.dropna(subset=[date_col])
if df.empty:
    st.error("Dashboard sheet has no valid dated rows.")
    st.stop()

df = df.sort_values(date_col)
latest = df.iloc[-1]
cols = df.columns.tolist()

if len(cols) < 8:
    st.error(f"Expected at least 8 columns in dashboard sheet, found {len(cols)}: {cols}")
    st.stop()

# column positions EXACTLY like VS Code
date_col      = cols[0]  # date
today_col     = cols[1]  # today's sale
oee_col       = cols[2]  # oee %
plan_col      = cols[3]  # plan vs actual %
rej_day_col   = cols[4]  # rejection amount (daybefore)
rej_pct_col   = cols[5]  # rejection %
rej_cum_col   = cols[6]  # rejection amount (cumulative)
total_cum_col = cols[7]  # total sales (cumulative)

# ========== KPIs (FOLLOWING VS CODE LOGIC) ==========
today_sale = to_number(latest[today_col])

# VS logic: if <5 treat as decimal, else already in %
oee_raw = to_number(latest[oee_col])
oee = oee_raw * 100 if oee_raw < 5 else oee_raw

plan_raw = to_number(latest[plan_col])
plan_vs_actual = plan_raw * 100 if plan_raw < 5 else plan_raw

rej_day = to_number(latest[rej_day_col])

rej_pct_raw = to_number(latest[rej_pct_col])
rej_pct = rej_pct_raw * 100 if rej_pct_raw < 5 else rej_pct_raw

rej_cum = to_number(latest[rej_cum_col])

cum_series = pd.to_numeric(df[total_cum_col], errors="coerce").dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0.0

achieved_pct = (total_cum / TARGET_SALE * 100) if TARGET_SALE else 0
achieved_pct_val = round(achieved_pct, 2)

# ========== COLORS ==========
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ========== GAUGE (SAME AS VS CODE) ==========
gauge = go.Figure(
    go.Indicator(
        mode="gauge",
        value=achieved_pct_val,
        number={
            "suffix": "%",
            "font": {"size": 44, "color": GREEN, "family": "Poppins", "weight": "bold"},
        },
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

# ========== SALES REPORT (FOR GRAPHS) ==========
try:
    sr_ws = sh.worksheet(SALES_REPORT_SHEET)
    sr_records = sr_ws.get_all_records()
    sr = pd.DataFrame(sr_records)
    sr.columns = sr.columns.str.strip().str.lower()

    if "table_name" in sr.columns:
        # SAME logic as VS code
        sale_df = sr[sr["table_name"].str.lower() == "sale_summery"].copy()
        rej_df = sr[sr["table_name"].str.lower() == "rejection_summery"].copy()
        if sale_df.empty:
            sale_df = sr.copy()
        if rej_df.empty:
            rej_df = sr.copy()
    else:
        sale_df = sr.copy()
        rej_df = sr.copy()
except Exception:
    # fallback: use dashboard data (only last rows)
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

# clean sale_df
if "date" in sale_df.columns:
    sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
else:
    # if date column name different, fallback to dashboard
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
    sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")

if "sale amount" in sale_df.columns:
    sale_df["sale amount"] = sale_df["sale amount"].apply(to_number)
else:
    # try generic numeric conversion on 2nd column
    if len(sale_df.columns) > 1:
        sale_col = sale_df.columns[1]
        sale_df.rename(columns={sale_col: "sale amount"}, inplace=True)
        sale_df["sale amount"] = sale_df["sale amount"].apply(to_number)
    else:
        sale_df["sale amount"] = 0

sale_df = sale_df.dropna(subset=["date"]).sort_values("date")

# clean rej_df
if "date" in rej_df.columns:
    rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
else:
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})
    rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")

# find rejection amount column
rej_cols = [c for c in rej_df.columns if "rej" in c]
if rej_cols:
    rej_src = rej_cols[0]
else:
    rej_src = rej_df.columns[1] if len(rej_df.columns) > 1 else rej_df.columns[0]

rej_df["rej amt"] = rej_df[rej_src].apply(to_number)
rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# ========== PLOTLY FIGURES (SAME STYLE AS VS CODE) ==========
fig_sale = go.Figure()
fig_sale.add_trace(
    go.Bar(
        x=sale_df["date"],
        y=sale_df["sale amount"],
        marker_color=BLUE,
    )
)
fig_sale.update_layout(
    title="",
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    width=None,
    autosize=True,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
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
    title="",
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    width=None,
    autosize=True,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
)
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ========== BACKGROUND IMAGE ==========
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# ========== HTML TEMPLATE (EXACT VS CODE UI) ==========
center_html = f"""
<div class="center-content" style='width:100%;height:100%;'>
  <div class="value-green">{achieved_pct_val}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}%"
left_rej_pct = f"{round(rej_pct if pd.notna(rej_pct) else 0, 1)}%"
left_rej_day = format_inr(rej_day)
bottom_rej_cum = format_inr(rej_cum)

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
