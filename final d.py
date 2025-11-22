import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.colors as pc
import base64
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

IMAGE_PATH = "nature.jpg"
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
DASHBOARD_SHEET = "Dashboard"
SALES_REPORT_SHEET = "Sales Report"
TARGET_SALE = 19_92_00_000

def load_image_base64(path: str) -> str:
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except Exception:
        return ""

def format_inr(n):
    try:
        x = str(int(float(str(n).replace(",", ""))))
    except Exception:
        return str(n)
    if len(x) <= 3:
        return x
    last3 = x[-3:]
    rest = x[:-3]
    rest = ''.join([rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1])
    return rest + last3

def ensure_pct(x):
    try:
        v = float(str(x).replace("%", "").replace(",", ""))
    except Exception:
        return 0.0
    return v * 100 if v <= 5 else v

# GOOGLE AUTH
try:
    creds_info = st.secrets["gcp_service_account"]
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    client = gspread.authorize(creds)
except Exception as e:
    st.error(f"Google auth failed: {e}")
    st.stop()

# OPEN SPREADSHEET
try:
    sh = client.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Cannot open spreadsheet: {e}")
    st.stop()

# READ DASHBOARD SHEET
try:
    dash_ws = sh.worksheet(DASHBOARD_SHEET)
    rows = dash_ws.get_values("A1:H")
except Exception as e:
    st.error(f"Cannot read Dashboard sheet: {e}")
    st.stop()

if not rows or len(rows) < 2:
    st.error("Dashboard sheet has no data.")
    st.stop()

header = rows[0]
data_rows = [r for r in rows[1:] if any(r)]
dash_data = [dict(zip(header, r)) for r in data_rows]

df = pd.DataFrame(dash_data)
df.columns = df.columns.str.strip().str.lower()

date_col = df.columns[0]
df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

for c in df.columns[1:]:
    df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")

df = df.dropna(subset=[date_col])
df = df.sort_values(date_col)

latest = df.iloc[-1]

cols = df.columns.tolist()
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

# VALUES
today_sale = latest[today_col]
oee = ensure_pct(latest[oee_col])
plan_vs_actual = ensure_pct(latest[plan_col])
rej_day = latest[rej_day_col]
rej_pct = ensure_pct(latest[rej_pct_col])
rej_cum = latest[rej_cum_col]
total_cum = df[total_cum_col].dropna().iloc[-1]

achieved_pct_val = round(total_cum / TARGET_SALE * 100, 2)

BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"


# GAUGE CHART (UNCHANGED)
gauge = go.Figure(
    go.Indicator(
        mode="gauge",
        value=achieved_pct_val,
        number={"suffix": "%", "font": {"size": 44, "color": GREEN, "family": "Poppins"}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": GREEN},
            "steps": [
                {"range": [0, 60], "color": "#c4eed1"},
                {"range": [60, 85], "color": "#7ee2b7"},
                {"range": [85, 100], "color": GREEN},
            ],
        },
    )
)
gauge.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=170)
gauge_html = gauge.to_html(include_plotlyjs="cdn", full_html=False)


# TREND CHARTS (UNCHANGED)
sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
sale_df = sale_df.dropna().sort_values("date")

rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})
rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
rej_df = rej_df.dropna().sort_values("date")

bar_gradients = pc.n_colors("rgb(34,139,230)", "rgb(79,223,253)", len(sale_df), colortype="rgb")

fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(x=sale_df["date"], y=sale_df["sale amount"], marker_color=bar_gradients))
fig_sale.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=135)
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

fig_rej = go.Figure()
fig_rej.add_trace(go.Scatter(
    x=rej_df["date"], y=rej_df["rej amt"],
    mode="lines+markers",
    line=dict(color=BUTTERFLY_ORANGE, width=7),
    marker=dict(size=10, color=BUTTERFLY_ORANGE, line=dict(width=1.5, color="#fff"))
))
fig_rej.add_trace(go.Scatter(
    x=rej_df["date"], y=rej_df["rej amt"],
    mode="lines",
    line=dict(color="rgba(252,125,27,0.13)", width=17),
    hoverinfo="skip"
))
fig_rej.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=135, showlegend=False)
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)


# BACKGROUND
bg_b64 = load_image_base64(IMAGE_PATH)

st.markdown(
    f"""
<style>
body, .stApp {{
    background: url("data:image/jpeg;base64,{bg_b64}") no-repeat center center fixed !important;
    background-size: cover !important;
}}
.block-container {{
    padding: 0 !important;
}}
</style>
""",
    unsafe_allow_html=True,
)


# TOP VALUES
top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee,1)}%"          # already includes %  ← fix applied later
left_rej_pct = f"{rej_pct:.1f}%"
bottom_rej_cum = format_inr(rej_cum)


# ===========================
#  HTML TEMPLATE (FIXED)
# ===========================

html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">

<style>

:root {{
    --card-radius: 16px;
    --orange: #fc7d1b;
    --blue: #228be6;
    --green: #009e4f;
}}

body {{
    margin:0;
    padding:0;
    background:none;
    font-family:'Poppins',sans-serif;
}}

.container {{
    width:100vw;
    height:100vh;
    padding:6vw;
    display:grid;
    grid-template-columns:1fr 1fr 1fr;
    grid-template-rows:130px 220px 140px;
    gap:18px;
    row-gap:30px;
    max-width:1700px;
    max-height:900px;
    margin:auto;
}}

/* EXACT VS CODE CARD */
.card {{
    background: linear-gradient(184deg,rgba(255,255,255,0.13) 12%,rgba(255,255,255,0.04) 83%);
    border-radius: var(--card-radius);
    box-shadow: 0 6px 18px rgba(4, 8, 15, 0.13);
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(6px) saturate(120%);
    -webkit-backdrop-filter: blur(6px) saturate(120%);
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    position:relative;
    overflow:hidden;
}}

/* REMOVE INNER BOX EFFECT */
.center-content {{
    width:100%;
    height:100%;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    background:none !important;
    padding:0 !important;
    margin:0 !important;
    border:none !important;
    box-shadow:none !important;
}}

.snow-bg {{
    position:absolute;
    width:100%;
    height:100%;
    left:0; top:0;
    opacity:0.42;
    pointer-events:none;
}}

.value-orange {{
    font-size:54px;
    font-weight:900;
    background-image:linear-gradient(90deg,#ffd98a,#fc7d1b,#ffc473);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    z-index:2;
}}

.value-blue {{
    font-size:54px;
    font-weight:900;
    background-image:linear-gradient(90deg,#b9e6ff,#228be6,#79cafc);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    z-index:2;
}}

.value-green {{
    font-size:56px;
    font-weight:900;
    background-image:linear-gradient(90deg,#aef9e2,#00df6c,#50e2ad);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    z-index:2;
}}

.title-black {{
    color:#191921;
    font-size:17px;
    font-weight:800;
    margin-top:4px;
}}

.title-green {{
    color:#009e4f;
    font-size:26px;
    font-weight:700;
    margin-top:4px;
}}

.chart-title-black {{
    color:#003;
    font-size:16px;
    font-weight:700;
    padding-left:7px;
    width:100%;
    text-align:left;
}}

.chart-container {{
    width:100%;
    height:110px;
}}
</style>
</head>

<body>
<div class="container">

    <div class="card">
      <canvas class="snow-bg" id="snowdate"></canvas>
      <div class="center-content">
        <div class="value-orange">{top_date}</div>
        <div class="title-black">Date</div>
      </div>
    </div>

    <div class="card">
      <canvas class="snow-bg" id="snowsale"></canvas>
      <div class="center-content">
        <div class="value-blue">₹ {top_today_sale}</div>
        <div class="title-black">Today's Sale</div>
      </div>
    </div>

    <!-- FIX APPLIED: removed extra % -->
    <div class="card">
      <canvas class="snow-bg" id="snowoee"></canvas>
      <div class="center-content">
        <div class="value-orange">{top_oee}</div>
        <div class="title-black">OEE %</div>
      </div>
    </div>

    <div class="card">
      <canvas class="snow-bg" id="snowrej"></canvas>
      <div class="center-content">
        <div class="value-orange">{left_rej_pct}</div>
        <div class="title-black">Rejection %</div>
      </div>
    </div>

    <div class="card">
      <canvas class="snow-bg" id="snowach"></canvas>
      <div class="center-content">
        <div class="value-green">{achieved_pct_val}%</div>
        <div class="title-green">Achieved %</div>
      </div>
    </div>

    <div class="card">
      <canvas class="snow-bg" id="snowspeed"></canvas>
      {gauge_html}
    </div>

    <div class="card">
      <canvas class="snow-bg" id="snowrejcum"></canvas>
      <div class="center-content">
        <div class="value-orange">{bottom_rej_cum}</div>
        <div class="title-black">Rejection (Cumulative)</div>
      </div>
    </div>

    <div class="card">
      <canvas class="snow-bg" id="snowsalechart"></canvas>
      <div class="chart-title-black">Sale Trend</div>
      <div class="chart-container">{sale_html}</div>
    </div>

    <div class="card">
      <canvas class="snow-bg" id="snowrejchart"></canvas>
      <div class="chart-title-black">Rejection Trend</div>
      <div class="chart-container">{rej_html}</div>
    </div>

</div>
</body>
</html>
"""

st.components.v1.html(html_template, height=950, scrolling=False)
