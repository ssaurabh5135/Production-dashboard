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

# Convert Google value to float safely
def clean_num(value):
    if value is None:
        return 0
    v = str(value).replace(",", "").replace("%", "").strip()
    if v == "":
        return 0
    try:
        return float(v)
    except:
        return 0

# ------------------ GOOGLE AUTH ------------------
creds_info = st.secrets["gcp_service_account"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
client = gspread.authorize(creds)

# ------------------ READ GOOGLE SHEET ------------------
sh = client.open_by_key(SPREADSHEET_ID)
ws = sh.worksheet(DASHBOARD_SHEET)

rows = ws.get_values("A1:H")
header = rows[0]
data_rows = rows[1:]
data = [dict(zip(header, r)) for r in data_rows]

df = pd.DataFrame(data)
df.columns = df.columns.str.strip().str.lower()

# convert date
df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce')
df = df.dropna(subset=[df.columns[0]])
df = df.sort_values(df.columns[0])

latest = df.iloc[-1]
cols = df.columns.tolist()

date_col, today_col, oee_col, plan_col, rej_day_col, rej_pct_col, rej_cum_col, total_cum_col = cols[:8]

# ------------------ APPLY SAME VS CODE LOGIC ------------------

today_sale = clean_num(latest[today_col])

oee_raw = clean_num(latest[oee_col])
oee = oee_raw * 100 if oee_raw < 5 else oee_raw

plan_raw = clean_num(latest[plan_col])
plan_vs_actual = plan_raw * 100 if plan_raw < 5 else plan_raw

rej_day = clean_num(latest[rej_day_col])

rej_pct_raw = clean_num(latest[rej_pct_col])
rej_pct = rej_pct_raw * 100 if rej_pct_raw < 5 else rej_pct_raw

rej_cum = clean_num(latest[rej_cum_col])

cum_series = pd.to_numeric(df[total_cum_col].apply(clean_num), errors='coerce').dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

achieved_pct_val = round((total_cum / TARGET_SALE * 100) if TARGET_SALE else 0, 2)

# ------------------ COLORS ------------------
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ------------------ GAUGE ------------------
gauge = go.Figure(go.Indicator(
    mode="gauge",
    value=achieved_pct_val,
    number={'suffix': "%", 'font': {"size": 44, "color": GREEN}},
    gauge={
        "shape": "angular",
        "axis": {"range": [0, 100]},
        "bar": {"color": GREEN}
    }
))
gauge.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=170,
    width=300
)
gauge_html = gauge.to_html(include_plotlyjs='cdn', full_html=False)

# ------------------ LOAD SALES REPORT (same logic) ------------------
try:
    sr_ws = sh.worksheet(SALES_REPORT_SHEET)
    sr = pd.DataFrame(sr_ws.get_all_records())
    sr.columns = sr.columns.str.strip().str.lower()
    sale_df = sr
    rej_df = sr
except:
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

# cleanup
sale_df['date'] = pd.to_datetime(sale_df['date'], errors='coerce')
sale_df['sale amount'] = pd.to_numeric(sale_df['sale amount'], errors='coerce').fillna(0)
sale_df = sale_df.dropna().sort_values('date')

rej_df['date'] = pd.to_datetime(rej_df['date'], errors='coerce')
rej_df['rej amt'] = pd.to_numeric(rej_df[rej_df.columns[-1]], errors='coerce')
rej_df = rej_df.dropna().sort_values('date')

# ------------------ PLOTS ------------------
fig_sale = go.Figure(go.Bar(x=sale_df['date'], y=sale_df['sale amount'], marker_color=BLUE))
fig_sale.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135
)
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

fig_rej = go.Figure(go.Scatter(
    x=rej_df['date'], y=rej_df['rej amt'], mode="lines+markers",
    marker=dict(size=8, color=BUTTERFLY_ORANGE)
))
fig_rej.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135
)
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ------------------ BACKGROUND IMAGE ------------------
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}"

# ------------------ HTML (UNCHANGED UI) ------------------
# SAME UI AS YOUR VS CODE
html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
{open('style.css').read() if False else ""}
</style>
</head>
<body style="background:url('{bg_url}') center/cover no-repeat fixed;">

<!-- Top Row -->
<div>Date: {latest[date_col].strftime('%d-%b-%Y')}</div>
<div>Today's Sale: ₹ {format_inr(today_sale)}</div>
<div>OEE %: {round(oee,1)}%</div>

<!-- Middle -->
<div>Rejection %: {round(rej_pct,1)}%</div>
<div>{gauge_html}</div>

<!-- Bottom -->
<div>Rejection (Day Before): ₹ {format_inr(rej_day)}</div>
<div>Rejection (Cumulative): ₹ {format_inr(rej_cum)}</div>
<div>{sale_html}</div>
<div>{rej_html}</div>

</body>
</html>
"""

st.components.v1.html(html_template, height=770, scrolling=True)
