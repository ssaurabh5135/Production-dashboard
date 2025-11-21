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
IMAGE_PATH = "winter.jpg"  # image stored in the repo next to this file
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

# ------------------ GOOGLE SHEETS AUTH ------------------
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

# ------------------ OPEN SPREADSHEET ------------------
try:
    sh = client.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Cannot open spreadsheet: {e}")
    st.stop()

# ================== LOAD DASHBOARD SHEET (A1:H) ==================
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

# Parse date
date_col = df.columns[0]
df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

# Make numeric
for c in df.columns[1:]:
    df[c] = pd.to_numeric(
        df[c].astype(str).str.replace(",", ""), errors="coerce"
    )

df = df.dropna(subset=[date_col]).sort_values(date_col)
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

# KPIs
today_sale = latest[today_col]
oee = ensure_pct(latest[oee_col])
plan_vs_actual = ensure_pct(latest[plan_col])
rej_day = latest[rej_day_col]
rej_pct = ensure_pct(latest[rej_pct_col])
rej_cum = latest[rej_cum_col]

cum_series = df[total_cum_col].dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0
achieved_pct = round(total_cum / TARGET_SALE * 100, 2)

# COLORS
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# KPI GAUGE
gauge = go.Figure(
    go.Indicator(
        mode="gauge",
        value=achieved_pct,
        number={
            "suffix": "%",
            "font": {"size": 44, "color": GREEN, "family": "Poppins"},
        },
        domain={"x": [0, 1], "y": [0, 1]},
        gauge={
            "shape": "angular",
            "axis": {"range": [0, 100]},
            "bar": {"color": GREEN, "thickness": 0.38},
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

# LOAD SALES REPORT
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
            if rej_date_str and rej_amt not in ("", None):
                rej_records.append({"date": rej_date_str, "rej amt": rej_amt})

    if sale_records:
        sale_df = pd.DataFrame(sale_records)

    if rej_records:
        rej_df = pd.DataFrame(rej_records)

if sale_df is None or sale_df.empty:
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})

if rej_df is None or rej_df.empty:
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

# Clean trend data
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

# PLOT — sale
fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(
    x=sale_df["date"], y=sale_df["sale amount"], marker_color=BLUE
))
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

# PLOT — rejection
fig_rej = go.Figure()
fig_rej.add_trace(go.Scatter(
    x=rej_df["date"], y=rej_df["rej amt"],
    mode="lines+markers",
    marker=dict(size=8, color=BUTTERFLY_ORANGE),
    line=dict(width=3, color=BUTTERFLY_ORANGE),
))
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# Background
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# HTML template
center_html = f"""
<div class="center-content" style='width:100%;height:100%;'>
  <div class="value-green">{achieved_pct}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee,1)}%"
left_rej_pct = f"{rej_pct: .1f}%"
left_rej_day = format_inr(rej_day)
bottom_rej_cum = format_inr(rej_cum)

html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">

<!-- AUTO REFRESH ADDED SAFELY -->
<meta http-equiv="refresh" content="60">

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
.value-orange {{
    color: {BUTTERFLY_ORANGE};
    font-size: 34px;
    font-weight: 800;
}}
.value-blue {{
    color: {BLUE};
    font-size: 34px;
    font-weight: 800;
}}
.value-green {{
    color: {GREEN};
    font-size: 46px;
    font-weight: 800;
}}
.title-black {{
    color: #000;
    font-size: 15px;
    font-weight: 700;
}}
.title-green {{
    color: {GREEN};
    font-size: 26px;
    font-weight: 700;
}}
.chart-container {{
    width: 100%;
    height: 110px;
    overflow: hidden;
}}
.chart-title-black {{
    font-size: 15px;
    color: #000;
    font-weight: 700;
    text-align:left;
    padding-left: 6px;
}}
</style>
</head>
<body>
<div class="container">

    <!-- Top Row -->
    <div class="card">
        <div class="center-content">
            <div class="value-orange">{top_date}</div>
            <div class="title-black">Date</div>
        </div>
    </div>

    <div class="card">
        <div class="center-content">
            <div class="value-blue">₹ {top_today_sale}</div>
            <div class="title-black">Today's Sale</div>
        </div>
    </div>

    <div class="card">
        <div class="center-content">
            <div class="value-orange">{top_oee}</div>
            <div class="title-black">OEE %</div>
        </div>
    </div>

    <!-- Middle -->
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

    <!-- Bottom -->
    <div class="card">
        <div class="center-content">
            <div class="value-orange">₹ {bottom_rej_cum}</div>
            <div class="title-black">Rejection (Cumulative)</div>
        </div>
    </div>

    <div class="card">
        <div class="chart-title-black">Sale Trend</div>
        <div class="chart-container">{sale_html}</div>
    </div>

    <div class="card">
        <div class="chart-title-black">Rejection Trend</div>
        <div class="chart-container">{rej_html}</div>
    </div>

</div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</body>
</html>
"""

st.components.v1.html(html_template, height=770, scrolling=True)
