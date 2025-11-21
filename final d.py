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
    rest = ''.join([rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1])
    return rest + last3

# ------------------ AUTH ------------------
creds_info = st.secrets["gcp_service_account"]
creds = Credentials.from_service_account_info(
    creds_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
)
client = gspread.authorize(creds)

# ------------------ LOAD GOOGLE SHEET ------------------
ws = client.open_by_key(SPREADSHEET_ID).worksheet(DASHBOARD_SHEET)
rows = ws.get_values("A1:H")

header = rows[0]
data_rows = rows[1:]
df = pd.DataFrame([dict(zip(header, r)) for r in data_rows])

# ------------------ SAME LOGIC AS VS CODE ------------------
df.columns = df.columns.str.strip().str.lower()
df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors="coerce")

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

# ---- VALUE EXTRACTION ----
today_sale = float(latest[today_col]) if latest[today_col] != "" else 0

# SAME VS CODE PERCENT LOGIC
def pct_fix(v):
    try:
        v = float(v)
        return v * 100 if v < 5 else v
    except:
        return 0

oee = pct_fix(latest[oee_col])
plan_vs_actual = pct_fix(latest[plan_col])
rej_pct = pct_fix(latest[rej_pct_col])

rej_day = float(latest[rej_day_col]) if latest[rej_day_col] else 0
rej_cum = float(latest[rej_cum_col]) if latest[rej_cum_col] else 0

cum_series = pd.to_numeric(df[total_cum_col], errors="coerce").dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

achieved_pct_val = round((total_cum / TARGET_SALE * 100) if TARGET_SALE else 0, 2)

# ------------------ COLORS ------------------
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ------------------ GAUGE (EXACT AS VS CODE) ------------------
gauge = go.Figure(go.Indicator(
    mode="gauge",
    value=achieved_pct_val,
    number={'suffix': "%", 'font': {"size": 44, "color": GREEN, "family": "Poppins"}},
    domain={'x':[0,1],'y':[0,1]},
    gauge={
        "shape": "angular",
        "axis": {"range":[0,100], "tickvals":[0,25,50,75,100]},
        "bar": {"color": GREEN, "thickness": 0.38},
        "bgcolor": "rgba(0,0,0,0)",
        "steps": [
            {"range":[0,60], "color":"#c4eed1"},
            {"range":[60,85], "color":"#7ee2b7"},
            {"range":[85,100], "color":GREEN},
        ],
        "threshold":{"line":{"color":"#111","width":5}, "value":achieved_pct_val},
    }
))
gauge.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(t=10,b=30,l=10,r=10), height=170, width=300)

gauge_html = gauge.to_html(include_plotlyjs=False, full_html=False)

# ------------------ SALES REPORT SHEET ------------------
try:
    sr_ws = client.open_by_key(SPREADSHEET_ID).worksheet(SALES_REPORT_SHEET)
    sr = pd.DataFrame(sr_ws.get_all_records())
    sr.columns = sr.columns.str.lower()
    sale_df = sr
    rej_df = sr
except:
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
sale_df["sale amount"] = pd.to_numeric(sale_df["sale amount"], errors="coerce").fillna(0)
sale_df = sale_df.dropna(subset=["date"]).sort_values("date")

rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
rej_df["rej amt"] = pd.to_numeric(rej_df[rej_df.columns[-1]], errors="coerce").fillna(0)
rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# ---- SALE TREND ----
fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(x=sale_df["date"], y=sale_df["sale amount"], marker_color=BLUE))
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

# ---- REJECTION TREND ----
fig_rej = go.Figure()
fig_rej.add_trace(go.Scatter(
    x=rej_df["date"], y=rej_df["rej amt"],
    mode="lines+markers",
    marker=dict(size=8, color=BUTTERFLY_ORANGE),
    line=dict(width=3, color=BUTTERFLY_ORANGE),
))
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ------------------ UI VARIABLES ------------------
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}"

center_html = f"""
<div class="center-content" style='width:100%;height:100%;'>
  <div class="value-green">{achieved_pct_val}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee,1)}%"
left_rej_pct = f"{round(rej_pct,1)}%"
left_rej_day = format_inr(rej_day)
bottom_rej_cum = format_inr(rej_cum)

# ------------------ HTML TEMPLATE (EXACT SAME UI AS VS CODE) ------------------
html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
/* SAME CSS FROM VS CODE */
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

    <div class="card">
        {center_html}
    </div>

    <div class="card">
        {gauge_html}
    </div>

    <div class="card bottom-card">
        <div class="center-content">
            <div class="value-orange">₹ {left_rej_day}</div>
            <div class="title-black">Rejection (Day Before)</div>
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
</body>
</html>
"""

st.components.v1.html(html_template, height=770, scrolling=True)
