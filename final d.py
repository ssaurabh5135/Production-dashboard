

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
    rest = ''.join(
        [rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1]
    )
    return rest + last3

def ensure_pct(x):
    try:
        v = float(str(x).replace("%", "").replace(",", ""))
    except Exception:
        return 0.0
    return v * 100 if v <= 5 else v

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

try:
    sh = client.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Cannot open spreadsheet: {e}")
    st.stop()

try:
    dash_ws = sh.worksheet(DASHBOARD_SHEET)
    rows = dash_ws.get_values("A1:H")
except Exception as e:
    st.error(f"Cannot read Dashboard sheet: {e}")
    st.stop()

if not rows or len(rows) < 2:
    st.error("Dashboard sheet has no data (A1:H).")
    st.stop()

header = rows[0]
data_rows = [r for r in rows[1:] if any(r)]
dash_data = [dict(zip(header, r)) for r in data_rows]
df = pd.DataFrame(dash_data)
df.columns = df.columns.str.strip().str.lower()

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

if list(df.columns[:8]) != expected_cols:
    pass

date_col = df.columns[0]
df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

for c in df.columns[1:]:
    df[c] = pd.to_numeric(df[c].astype(str).replace(",", ""), errors="coerce")

df = df.dropna(subset=[date_col])

if df.empty:
    st.error("No valid dates in Dashboard sheet.")
    st.stop()

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

today_sale = latest[today_col]
raw_oee = latest[oee_col]
oee = ensure_pct(raw_oee)
raw_plan = latest[plan_col]
plan_vs_actual = ensure_pct(raw_plan)
rej_day = latest[rej_day_col]
raw_rej_pct = latest[rej_pct_col]
rej_pct = ensure_pct(raw_rej_pct)
rej_cum = latest[rej_cum_col]

cum_series = df[total_cum_col].dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

achieved_pct_val = round(total_cum / TARGET_SALE * 100, 2) if TARGET_SALE else 0

# ----- INDENT CALCULATION -----
from datetime import datetime, timedelta
DAILY_TARGET = 6670000
today_d = datetime.today().date()
yesterday_d = today_d - timedelta(days=1)
start_month = today_d.replace(day=1)
working_days = sum(
    1 for i in range((yesterday_d - start_month).days + 1)
    if (start_month + timedelta(days=i)).weekday() != 6
)
indent_value = working_days * DAILY_TARGET



# COLORS
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ---- GAUGE FIGURE ----
gauge = go.Figure(
    go.Indicator(
        mode="gauge",
        value=achieved_pct_val,
        number={
            "suffix": "%",
            "font": {
                "size": 44,
                "color": GREEN,
                "family": "Poppins",
                "weight": "bold",
            },
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
            "threshold": {
                "line": {"color": "#111", "width": 5},
                "value": achieved_pct_val,
            },
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

# ------------------- SALES REPORT -----------------
try:
    sr_ws = sh.worksheet(SALES_REPORT_SHEET)
    sr_rows = sr_ws.get_values()
except Exception:
    sr_rows = []

sale_df = None
rej_df = None
if sr_rows and len(sr_rows) > 1:
    sale_records = []
    rej_records = []
    for r in sr_rows[1:]:
        if len(r) >= 3:
            date_str = (r[0] or "").strip()
            sales_type = (r[1] or "").strip().upper()
            sale_amt = r[2]
            if date_str and sales_type == "OEE":
                sale_records.append({"date": date_str, "sale amount": sale_amt})

        if len(r) >= 12:
            rej_date_str = (r[10] or "").strip()
            rej_amt = r[11]
            if rej_date_str and rej_amt not in (None, ""):
                rej_records.append({"date": rej_date_str, "rej amt": rej_amt})

    if sale_records:
        sale_df = pd.DataFrame(sale_records)
    if rej_records:
        rej_df = pd.DataFrame(rej_records)

if sale_df is None or sale_df.empty:
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
if rej_df is None or rej_df.empty:
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
sale_df["sale amount"] = pd.to_numeric(
    sale_df["sale amount"].astype(str).str.replace(",", ""), errors="coerce"
).fillna(0)
sale_df = sale_df.dropna(subset=["date"]).sort_values("date")

rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
rej_df["rej amt"] = pd.to_numeric(
    rej_df["rej amt"].astype(str).str.replace(",", ""), errors="coerce"
).fillna(0)
rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# ------------ SALE TREND CHART -------------
bar_gradients = pc.n_colors('rgb(34,139,230)', 'rgb(79,223,253)', len(sale_df), colortype='rgb')
fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(
    x=sale_df["date"],
    y=sale_df["sale amount"],
    marker_color=bar_gradients,
    marker_line_width=0,
    opacity=0.97
))
fig_sale.update_layout(
    margin=dict(t=24, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
)

# ------------ REJECTION TREND CHART -------------
fig_rej = go.Figure()
fig_rej.add_trace(go.Scatter(
    x=rej_df["date"], y=rej_df["rej amt"],
    mode="lines+markers",
    marker=dict(size=10, color=BUTTERFLY_ORANGE, line=dict(width=1.5, color="#fff")),
    line=dict(width=7, color=BUTTERFLY_ORANGE, shape="spline"),
    hoverinfo="x+y",
    opacity=1,
    name=""
))
fig_rej.add_trace(go.Scatter(
    x=rej_df["date"], y=rej_df["rej amt"],
    mode="lines",
    line=dict(width=17, color="rgba(252,125,27,0.13)", shape="spline"),
    hoverinfo="skip",
    opacity=1,
    name=""
))
fig_rej.update_layout(
    margin=dict(t=24, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    showlegend=False,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
)

sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

bg_b64 = load_image_base64(IMAGE_PATH)



st.markdown(
    f"""
    <style>
    body, .stApp {{
        background: url("data:image/jpeg;base64,{bg_b64}") no-repeat center center fixed !important;
        background-size: cover !important;
        background-position: center center !important;
        min-height: 100vh !important;
        min-width: 100vw !important;
        width: 100vw !important;
        height: 100vh !important;
        overflow: hidden !important;
        margin: 0 !important;
        padding: 0 !important;
    }}
    .block-container {{
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
        padding-left: 0rem !important;
        padding-right: 0rem !important;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}%"
left_rej_pct = f"{rej_pct: .1f}%"
bottom_rej_cum = format_inr(rej_cum)

html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
:root {{
    --card-radius: 17px;
    --orange: {BUTTERFLY_ORANGE};
    --blue: {BLUE};
    --green: {GREEN};
}}
body {{
    margin:0;
    padding:0;
    font-family:'Poppins',sans-serif;
    background: none !important;
    color:#091128;
}}
.container {{
    box-sizing: border-box;
    width: 100vw;
    height: 100vh;
    padding: 5vw;
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    grid-template-rows: 130px 220px 140px;
    gap: 18px;
    row-gap: 30px;
    max-width: 1700px;
    max-height: 900px;
    margin: auto;
}}

.card {{
    background: linear-gradient(184deg,rgba(255,255,255,0.13) 12%,rgba(255,255,255,0.04) 83%);
    border-radius: 16px;
    box-shadow: 0 6px 18px rgba(4, 8, 15, 0.13);
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(6px) saturate(120%);
    -webkit-backdrop-filter: blur(6px);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
}}

.value-orange, .value-blue {{
    font-size:54px!important;
    font-family:'Poppins','Segoe UI',Arial,sans-serif;
    font-weight:900!important;
    letter-spacing:0.03em;
    text-align:center;
    position:relative;
    z-index:2;
    background-clip:text!important;
    -webkit-background-clip:text!important;
    -webkit-text-fill-color:transparent;
    color:transparent!important;
    padding:4px 11px;
    margin:0 auto;
    white-space:nowrap;
    width:100%;
}}
.value-orange {{
    background-image:linear-gradient(90deg,#ffd98a 0%,#fc7d1b 58%,#ffc473 100%);
    text-shadow:0 2px 0 #fff, 0 6px 16px #fc7d1b,
                 0 1px 8px #fffbe8, 0 12px 38px #fc7d1b;
    -webkit-text-stroke:1.2px #b96000;
    filter:drop-shadow(0 4px 18px #fc7d1b);
    border-radius:10px;
    background-size:200% 100%;
}}
.value-blue {{
    background-image:linear-gradient(89deg,#b9e6ff 0%,#228be6 75%,#79cafc 100%);
    text-shadow:0 2px 0 #fff, 0 0.5px 9px #79cafc,
                 0 6px 18px #228be6, 0 12px 38px #79cafc;
    -webkit-text-stroke:1.2px #1661a2;
    filter:drop-shadow(0 4px 18px #228be6);
    border-radius:10px;
    background-size:200% 100%;
}}
.value-green {{
    font-size:56px!important;
    font-weight:900!important;
    font-family:'Poppins','Segoe UI',Arial,sans-serif;
    background:linear-gradient(90deg,#aef9e2 0%,#00df6c 60%,#50e2ad 100%);
    -webkit-background-clip:text!important;
    background-clip:text!important;
    -webkit-text-fill-color:transparent;
    color:transparent!important;
    text-shadow:0 3px 8px #fffbe8,
                 0 5px 16px #00df6c,
                 0 10px 30px #aef9e2;
    -webkit-text-stroke:1.2px #1a8d56;
    filter:drop-shadow(0 4px 16px #00df6c);
    border-radius:10px;
    background-size:200% 100%;
    text-align:center;
    margin-bottom:4px;
}}

.title-green {{
    color:{GREEN}!important;
    font-size:26px!important;
    font-weight:750!important;
    margin-top:4px!important;
}}
.title-black {{
    color:#f7f5fa!important;
    font-size:17px!important;
    font-weight:800!important;
    margin-top:7px!important;
    width:100%;text-align:center!important;
}}
.chart-title-black {{
    color: #003!important;
    font-size:16px!important;
    font-weight:700!important;
    margin-bottom:3px!important;
    width:100%; text-align:left!important;
    padding-left:7px;
}}

.chart-container {{
    width:100%; height:110px;
    overflow:hidden;
    box-sizing:border-box;
    margin:0; padding:0;
    display:block;
}}

.center-content {{
    width:100%;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    padding:0;
    margin:0;
}}

</style>
</head>
<body>
<div class="container">



    <!-- ===================== TOP ROW ===================== -->

    <div class="card top-card">
        <div class="center-content">
            <div class="value-blue" id="salevalue">₹ {top_today_sale}</div>
            <div class="title-black">Yesterday's Sale</div>
        </div>
    </div>

    <div class="card">
        <div class="center-content">
            <div class="value-orange" id="rejval">{left_rej_pct}</div>
            <div class="title-black">Rejection %</div>
        </div>
    </div>

    <div class="card top-card">
        <div class="center-content">
            <div class="value-blue" id="oeevalue">{top_oee}</div>
            <div class="title-black">OEE %</div>
        </div>
    </div>


    <!-- ===================== MIDDLE ROW ===================== -->

    <div class="card">
        {gauge_html}
    </div>

    <div class="card">
        <div class="center-content">
            <div class="value-green" id="achval">{achieved_pct_val}%</div>
            <div class="title-green">Achieved %</div>
        </div>
    </div>

    <div class="card top-card">
        <div class="center-content">
            <div class="value-blue" style="font-size:40px!important;">COPQ Updating...</div>
        </div>
    </div>


    <!-- ===================== BOTTOM ROW ===================== -->

    <div class="card bottom-card">
        <div class="chart-title-black">Sale Trend</div>
        <div id="sale_chart_container" class="chart-container">{sale_html}</div>
    </div>

    <div class="card bottom-card">
        <div class="chart-title-black">Rejection Trend</div>
        <div id="rej_chart_container" class="chart-container">{rej_html}</div>
    </div>

    <!-- ⭐⭐⭐ NEW INDENT VS ACTUAL CARD (REPLACED GAP CARD) ⭐⭐⭐ -->

    <div class="card bottom-card">

        <div class="chart-title-black">Indent vs Actual</div>

        <!-- BAR CHART -->
        <div class="chart-container">
            {compare_html}
        </div>

        <div style="display:flex; width:100%; justify-content:space-around; margin-top:6px;">

            <div style="text-align:center;">
                <div class="title-black" style="font-size:15px;">Indent</div>
                <div class="value-blue" style="font-size:32px;">₹ {format_inr(indent_value)}</div>
            </div>

            <div style="text-align:center;">
                <div class="title-black" style="font-size:15px;">Actual</div>
                <div class="value-orange" style="font-size:32px;">₹ {format_inr(total_cum)}</div>
            </div>

        </div>

    </div>

</div> <!-- END CONTAINER -->


<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>


"""

st.components.v1.html(html_template, height=770, scrolling=True)







