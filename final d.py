import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# ----------------------------------
# PAGE CONFIG
# ----------------------------------
st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

# ----------------------------------
# CONFIG
# ----------------------------------
IMAGE_PATH = "winter.jpg"
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
DASHBOARD_SHEET = "Dashboard"
SALES_REPORT_SHEET = "Sales Report"
TARGET_SALE = 19_92_00_000

# ----------------------------------
# HELPERS
# ----------------------------------
def load_image_base64(path):
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except:
        return ""

def format_inr(n):
    try:
        x = str(int(float(n)))
    except:
        return str(n)
    if len(x) <= 3:
        return x
    last3 = x[-3:]
    rest = x[:-3]
    rest = ",".join([rest[max(i-2,0):i] for i in range(len(rest), 0, -2)][::-1])
    return rest + last3

# ----------------------------------
# LOAD GOOGLE SHEET (REPLACES EXCEL)
# ----------------------------------
creds_info = st.secrets["gcp_service_account"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
client = gspread.authorize(creds)

worksheet = client.open_by_key(SPREADSHEET_ID).worksheet(DASHBOARD_SHEET)

rows = worksheet.get_all_values()

header = [h.strip().lower() for h in rows[0]]
data = rows[1:]

df = pd.DataFrame(data, columns=header)

# ----------------------------------
# SAME VS CODE LOGIC — DO NOT CHANGE
# ----------------------------------
df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce')
df = df.dropna(subset=[df.columns[0]])
df = df.sort_values(df.columns[0])

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

# SAME KPI LOGIC AS VS CODE
today_sale = float(latest[today_col])
oee = float(latest[oee_col]) * 100 if float(latest[oee_col]) < 5 else float(latest[oee_col])
plan_vs_actual = float(latest[plan_col]) * 100 if float(latest[plan_col]) < 5 else float(latest[plan_col])
rej_day = float(latest[rej_day_col])
rej_pct = float(latest[rej_pct_col]) * 100 if float(latest[rej_pct_col]) < 5 else float(latest[rej_pct_col])
rej_cum = float(latest[rej_cum_col])
total_cum = float(df[total_cum_col].dropna().iloc[-1])

achieved_pct_val = round((total_cum / TARGET_SALE * 100), 2)

# ----------------------------------
# COLORS
# ----------------------------------
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ----------------------------------
# GAUGE (UNCHANGED)
# ----------------------------------
gauge = go.Figure(go.Indicator(
    mode="gauge",
    value=achieved_pct_val,
    number={'suffix': "%", 'font': {"size": 44, "color": GREEN}},
    domain={'x': [0, 1], 'y': [0, 1]},
    gauge={
        "shape": "angular",
        "axis": {"range": [0, 100]},
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
gauge.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=170, width=300)
gauge_html = gauge.to_html(include_plotlyjs=False, full_html=False)

# ----------------------------------
# SALES REPORT (UNCHANGED)
# ----------------------------------
try:
    sr = client.open_by_key(SPREADSHEET_ID).worksheet(SALES_REPORT_SHEET).get_all_records()
    sr = pd.DataFrame(sr)
    sr.columns = sr.columns.str.lower()
    sale_df = sr
    rej_df = sr
except:
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

sale_df['date'] = pd.to_datetime(sale_df['date'], errors='coerce')
sale_df['sale amount'] = pd.to_numeric(sale_df['sale amount'], errors='coerce').fillna(0)
sale_df = sale_df.dropna(subset=['date'])

rej_df['date'] = pd.to_datetime(rej_df['date'], errors='coerce')
rej_df['rej amt'] = pd.to_numeric(rej_df[rej_df.columns[-1]], errors='coerce').fillna(0)
rej_df = rej_df.dropna(subset=['date'])

# ----------------------------------
# PLOTS (UNCHANGED)
# ----------------------------------
fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(x=sale_df['date'], y=sale_df['sale amount'], marker_color=BLUE))
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

fig_rej = go.Figure()
fig_rej.add_trace(go.Scatter(x=rej_df['date'], y=rej_df['rej amt'],
                             mode='lines+markers',
                             marker=dict(size=8, color=BUTTERFLY_ORANGE),
                             line=dict(width=3, color=BUTTERFLY_ORANGE)))
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ----------------------------------
# UI EXACT SAME AS VS CODE
# ----------------------------------
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}"

center_html = f"""
<div class="center-content">
  <div class="value-green">{achieved_pct_val}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

top_date = pd.to_datetime(latest[date_col]).strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee,1)}%"
left_rej_pct = f"{round(rej_pct,1)}%"
left_rej_day = format_inr(rej_day)
bottom_rej_cum = format_inr(rej_cum)

html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
... SAME CSS AS YOUR VS CODE ...
</style>
</head>
<body>
<div class="container">

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

    <div class="card">
        <div class="center-content">
            <div class="value-orange">{left_rej_pct}</div>
            <div class="title-black">Rejection %</div>
        </div>
    </div>

    <div class="card">{center_html}</div>

    <div class="card">{gauge_html}</div>

    <div class="card bottom-card">
        <div class="center-content">
            <div class="value-orange">₹ {bottom_rej_cum}</div>
            <div class="title-black">Rejection (Cumulative)</div>
        </div>
    </div>

    <div class="card bottom-card">
        <div class="chart-title-black">Sale Trend</div>
        <div class="chart-container">{sale_html}</div>
    </div>

    <div class="card bottom-card">
        <div class="chart-title-black">Rejection Trend</div>
        <div class="chart-container">{rej_html}</div>
    </div>

</div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</body>
</html>
"""

st.components.v1.html(html_template, height=770, scrolling=True)
