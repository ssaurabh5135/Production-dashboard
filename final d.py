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
IMAGE_PATH = "winter.jpg"   # image kept in the repo, same folder as this file
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
DASHBOARD_SHEET = "Dashboard"
SALES_REPORT_SHEET = "Sales Report"
TARGET_SALE = 19_92_00_000

# ------------------ HELPERS ------------------
def load_image_base64(path: str) -> str:
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except Exception as e:
        # Only show if there is really a problem
        st.warning(f"Background image not found at {path}. Using plain background. ({e})")
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
        rest[::-1][i:i + 2][::-1] + ','
        for i in range(0, len(rest), 2)
    ][::-1])
    return rest + last3

def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

# ------------------ GOOGLE SERVICE ACCOUNT AUTH ------------------
try:
    creds_info = st.secrets["gcp_service_account"]
except KeyError:
    st.error("Missing 'gcp_service_account' in Streamlit secrets.")
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

# ------------------ OPEN SPREADSHEET & WORKSHEET ------------------
try:
    sh = client.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Cannot open spreadsheet by ID ({SPREADSHEET_ID}): {e}")
    st.stop()

try:
    ws_dashboard = sh.worksheet(DASHBOARD_SHEET)
except Exception as e:
    st.error(f"Cannot open worksheet '{DASHBOARD_SHEET}': {e}")
    st.stop()

# ------------------ LOAD DASHBOARD DATA (STRICT A1:H) ------------------
try:
    # UNFORMATTED_VALUE → gives decimals like Excel (0.88, 0.016) instead of "88%"
    rows = ws_dashboard.get('A1:H', value_render_option='UNFORMATTED_VALUE')
except Exception as e:
    st.error(f"Failed reading Dashboard range A1:H: {e}")
    st.stop()

if not rows or len(rows) < 2:
    st.error("Dashboard sheet has no usable data in A1:H.")
    st.stop()

header = rows[0]
data_rows = [r for r in rows[1:] if any(str(c).strip() for c in r)]
data = [dict(zip(header, r)) for r in data_rows]

df = pd.DataFrame(data)
if df.empty:
    st.error("No rows found in Dashboard sheet after header.")
    st.stop()

# ------------------ DATA CLEANUP & KPIs (SAME LOGIC AS VS CODE) ------------------
df.columns = df.columns.str.strip().str.lower()

# Expecting exactly these 8 logical columns in order
expected_cols = [
    "date",
    "today's sale",
    "oee %",
    "plan vs actual %",
    "rejection amount (daybefore)",
    "rejection %",
    "rejection amount (cumulative)",
    "total sales (cumulative)",
]

# If headers are exactly as above, reorder them in that sequence
col_map = {c.lower(): c for c in df.columns}
ordered_cols = []
for c in expected_cols:
    cl = c.lower()
    if cl in col_map:
        ordered_cols.append(col_map[cl])
    else:
        # fallback: use whatever df currently has
        ordered_cols = list(df.columns)
        break
df = df[ordered_cols]
df.columns = df.columns.str.lower()

df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce')
df = df.dropna(axis=0, subset=[df.columns[0]])
df = df.sort_values(df.columns[0])

if df.empty:
    st.error("No valid dates found in Dashboard sheet.")
    st.stop()

latest = df.iloc[-1]
cols = df.columns.tolist()

date_col = cols[0]
today_col = cols[1]
oee_col = cols[2]
plan_col = cols[3]
rej_day_col = cols[4]
rej_pct_col = cols[5]
rej_cum_col = cols[6]
total_cum_col = cols[7]

# --- SAME NUMERIC LOGIC AS ORIGINAL EXCEL VERSION ---
today_sale = safe_float(latest[today_col])

oee_raw = safe_float(latest[oee_col])
oee = oee_raw * 100 if oee_raw < 5 else oee_raw

plan_raw = safe_float(latest[plan_col])
plan_vs_actual = plan_raw * 100 if plan_raw < 5 else plan_raw

rej_day = safe_float(latest[rej_day_col])

rej_pct_raw = safe_float(latest[rej_pct_col])
rej_pct = rej_pct_raw * 100 if rej_pct_raw < 5 else rej_pct_raw

rej_cum = safe_float(latest[rej_cum_col])

cum_series = pd.to_numeric(df[total_cum_col], errors='coerce').dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0.0

achieved_pct = (total_cum / TARGET_SALE * 100) if TARGET_SALE else 0
achieved_pct_val = round(achieved_pct, 2)

# ------------------ COLORS ------------------
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ------------------ KPI GAUGE (SAME STYLE AS VS CODE) ------------------
gauge = go.Figure(go.Indicator(
    mode="gauge",
    value=achieved_pct_val,
    number={
        'suffix': "%",
        'font': {"size": 44, "color": GREEN, "family": "Poppins", "weight": "bold"}
    },
    domain={'x': [0, 1], 'y': [0, 1]},
    gauge={
        "shape": "angular",
        "axis": {
            "range": [0, 100],
            "tickvals": [0, 25, 50, 75, 100],
            "ticktext": ["0%", "25%", "50%", "75%", "100%"]
        },
        "bar": {"color": GREEN, "thickness": 0.38},
        "bgcolor": "rgba(0,0,0,0)",
        "steps": [
            {"range": [0, 60], "color": "#c4eed1"},
            {"range": [60, 85], "color": "#7ee2b7"},
            {"range": [85, 100], "color": GREEN}
        ],
        "threshold": {"line": {"color": "#111", "width": 5}, "value": achieved_pct_val}
    }
))
gauge.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=10, b=30, l=10, r=10),
    height=170,
    width=300
)
gauge_html = gauge.to_html(include_plotlyjs='cdn', full_html=False)

# ------------------ LOAD SALES REPORT SHEET ------------------
try:
    ws_sr = sh.worksheet(SALES_REPORT_SHEET)
    sr_records = ws_sr.get_all_records()
    sr = pd.DataFrame(sr_records)
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
    # Fallback: same as VS code
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

# ------------------ CLEANUP FOR CHARTS (SAME AS VS CODE) ------------------
sale_df['date'] = pd.to_datetime(sale_df['date'], errors='coerce')
sale_df['sale amount'] = pd.to_numeric(sale_df['sale amount'], errors='coerce').fillna(0)
sale_df = sale_df.dropna(subset=['date']).sort_values('date')

rej_df['date'] = pd.to_datetime(rej_df['date'], errors='coerce')
rej_df_col = rej_df.columns[rej_df.columns.str.contains('rej')].tolist()
rej_amt_col = rej_df_col[0] if rej_df_col else (rej_df.columns[1] if len(rej_df.columns) > 1 else rej_df.columns[0])
rej_df['rej amt'] = pd.to_numeric(rej_df[rej_amt_col], errors='coerce').fillna(0)
rej_df = rej_df.dropna(subset=['date']).sort_values('date')

# ------------------ PLOTLY FIGURES (SAME STYLE AS VS CODE) ------------------
fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(
    x=sale_df['date'],
    y=sale_df['sale amount'],
    marker_color=BLUE
))
fig_sale.update_layout(
    title="",
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    width=None,
    autosize=True,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True)
)
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

fig_rej = go.Figure()
fig_rej.add_trace(go.Scatter(
    x=rej_df['date'],
    y=rej_df['rej amt'],
    mode='lines+markers',
    marker=dict(size=8, color=BUTTERFLY_ORANGE),
    line=dict(width=3, color=BUTTERFLY_ORANGE),
))
fig_rej.update_layout(
    title="",
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    width=None,
    autosize=True,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True)
)
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ------------------ BACKGROUND IMAGE ------------------
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# ------------------ HTML TEMPLATE (EXACT SAME UI AS VS CODE) ------------------
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
left_rej_day = format_inr(rej_day)  # (not shown in current cards, kept for future use)
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
