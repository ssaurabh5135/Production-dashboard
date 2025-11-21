import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

IMAGE_PATH = "winter.jpg"
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
DASHBOARD_SHEET = "Dashboard"
SALES_REPORT_SHEET = "Sales Report"
TARGET_SALE = 19_92_00_000

# ----- Helpers -----
def load_image_base64(path):
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except:
        return ""

def format_inr(n):
    try: x = str(int(float(n)))
    except: return str(n)
    if len(x) <= 3: return x
    last3 = x[-3:]
    rest = x[:-3]
    rest = "".join([rest[::-1][i:i+2][::-1] + "," for i in range(0,len(rest),2)][::-1])
    return rest + last3

# ----- Auth -----
creds_info = st.secrets["gcp_service_account"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
client = gspread.authorize(creds)

# ----- Load Dashboard Sheet -----
sheet = client.open_by_key(SPREADSHEET_ID)
ws = sheet.worksheet(DASHBOARD_SHEET)
rows = ws.get_values("A1:H")

header = rows[0]
data_rows = rows[1:]
df = pd.DataFrame([dict(zip(header,r)) for r in data_rows])

# Normalize header
df.columns = [str(c).strip().lower() for c in df.columns]

df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors="coerce")
df = df.dropna(subset=[df.columns[0]])
df = df.sort_values(df.columns[0])

latest = df.iloc[-1]
cols = df.columns.tolist()

date_col = cols[0]
today_col = cols[1]
oee_col = cols[2]
plan_col = cols[3]
rej_day_col = cols[4]                   # <-- REJECTION AMOUNT (DAYBEFORE)
rej_pct_col = cols[5]
rej_cum_col = cols[6]
total_cum_col = cols[7]

# ----- Extract values -----
def val(row, col):
    try: return row[col]
    except: return 0

today_sale = val(latest, today_col)
oee = val(latest, oee_col)
plan_vs_actual = val(latest, plan_col)
rej_day = val(latest, rej_day_col)
rej_pct = val(latest, rej_pct_col)
rej_cum = val(latest, rej_cum_col)

cum_series = pd.to_numeric(df[total_cum_col], errors="coerce").dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

# Percentage fixes
def pct(x):
    try:
        x = float(x)
        return x*100 if x <= 1 else x
    except:
        return 0

oee = pct(oee)
plan_vs_actual = pct(plan_vs_actual)
rej_pct = pct(rej_pct)

achieved_pct_val = round((total_cum / TARGET_SALE * 100), 2)

# ----- Colors -----
ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ----- Gauge -----
gauge = go.Figure(go.Indicator(
    mode="gauge",
    value=achieved_pct_val,
    number={'suffix': "%", 'font': {"size": 44, "color": GREEN}},
    gauge={
        "shape":"angular",
        "axis":{"range":[0,100]},
        "bar":{"color":GREEN,"thickness":0.38},
        "bgcolor":"rgba(0,0,0,0)",
    }
))
gauge.update_layout(height=170,width=300,paper_bgcolor="rgba(0,0,0,0)")
gauge_html = gauge.to_html(include_plotlyjs='cdn', full_html=False)

# ----- Fallback chart data -----
sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

sale_df['date'] = pd.to_datetime(sale_df['date'])
sale_df['sale amount'] = pd.to_numeric(sale_df['sale amount'], errors="coerce").fillna(0)

rej_df['date'] = pd.to_datetime(rej_df['date'])
rej_df['rej amt'] = pd.to_numeric(rej_df['rej amt'], errors="coerce").fillna(0)

# ----- Sale Trend -----
fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(x=sale_df['date'], y=sale_df['sale amount'], marker_color=BLUE))
fig_sale.update_layout(height=135, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

# ----- Rejection Trend -----
fig_rej = go.Figure()
fig_rej.add_trace(go.Scatter(
    x=rej_df['date'], y=rej_df['rej amt'],
    mode="lines+markers", marker=dict(size=8,color=ORANGE)
))
fig_rej.update_layout(height=135, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ----- BG Image -----
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}"

# ----- Values -----
top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee,1)}%"
left_rej_pct = f"{round(rej_pct,1)}%"
left_rej_day = format_inr(rej_day)
bottom_rej_cum = format_inr(rej_cum)

center_html = f"""
<div class='center-content'>
  <div class='value-green'>{achieved_pct_val}%</div>
  <div class='title-green'>Achieved %</div>
</div>
"""

# ----- HTML -----
html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
:root {{
    --orange:{ORANGE};
    --green:{GREEN};
    --blue:{BLUE};
}}
body {{
    margin:0;
    padding:18px;
    background:url("{bg_url}") center/cover no-repeat fixed;
    font-family:'Poppins';
}}
.container {{
    display:grid;
    grid-template-columns:1fr 1fr 1fr;
    grid-template-rows:130px 220px 140px;
    gap:18px;
}}
.card {{
    background:rgba(255,255,255,0.15);
    border-radius:14px;
    backdrop-filter:blur(6px);
    display:flex;
    justify-content:center;
    align-items:center;
    flex-direction:column;
}}
.value-orange {{color:var(--orange);font-size:34px;font-weight:800}}
.value-blue {{color:var(--blue);font-size:34px;font-weight:800}}
.value-green {{color:var(--green);font-size:46px;font-weight:800}}
.title-black {{font-size:15px;font-weight:700;color:#000}}
.title-green {{color:var(--green);font-size:26px;font-weight:700}}
.chart-container {{height:110px;width:100%;overflow:hidden}}
</style>
</head>
<body>

<div class="container">

    <!-- Top Row -->
    <div class="card"><div class="value-orange">{top_date}</div><div class="title-black">Date</div></div>
    <div class="card"><div class="value-blue">₹ {top_today_sale}</div><div class="title-black">Today's Sale</div></div>
    <div class="card"><div class="value-orange">{top_oee}</div><div class="title-black">OEE %</div></div>

    <!-- Middle -->
    <div class="card"><div class="value-orange">{left_rej_pct}</div><div class="title-black">Rejection %</div></div>
    <div class="card">{center_html}</div>
    <div class="card">{gauge_html}</div>

    <!-- Bottom Row -->
    <div class="card"><div class="value-orange">₹ {bottom_rej_cum}</div><div class="title-black">Rejection (Cumulative)</div></div>
    <div class="card"><div class="title-black">Sale Trend</div><div class="chart-container">{sale_html}</div></div>
    <div class="card"><div class="title-black">Rejection Trend</div><div class="chart-container">{rej_html}</div></div>

</div>

<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</body>
</html>
"""

st.components.v1.html(html_template, height=770, scrolling=True)
