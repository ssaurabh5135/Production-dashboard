import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64
from pathlib import Path

st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

IMAGE_PATH = r"C:\Users\lcatpune.production\Desktop\Model number and cycle time\winter.JPG"
EXCEL_PATH = r'\\Lcatnas\production\00 ASHA\ALL REPOTS OF-2025\11) November\production sheet.xlsx'
SHEET_NAME = "Dashboard Sheet"
TARGET_SALE = 19_92_00_000

def load_image_base64(path):
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except Exception as e:
        st.warning(f"Background image not found at {path}. Using plain background. ({e})")
        return ""

def format_inr(n):
    try:
        x = str(int(n))
    except:
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

@st.cache_data(ttl=30)
def load_master():
    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME, engine="openpyxl")
    df.columns = df.columns.str.strip().str.lower()
    df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce')
    return df

try:
    df = load_master()
except Exception as e:
    st.error(f"Could not load Excel dashboard sheet: {e}")
    st.stop()

df = df.dropna(axis=0, subset=[df.columns[0]])
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

# ✅ FIX 1 — CLEANING OEE, PLAN %, REJ % TO MAKE THEM NUMERIC
df[oee_col] = pd.to_numeric(df[oee_col], errors='coerce')
df[plan_col] = pd.to_numeric(df[plan_col], errors='coerce')
df[rej_pct_col] = pd.to_numeric(df[rej_pct_col], errors='coerce')

# ===========================
# VALUES
# ===========================

today_sale = latest[today_col]

# ✅ FIXED OEE %
raw_oee = latest[oee_col]
oee = raw_oee * 100 if raw_oee < 5 else raw_oee

# FIXED PLAN %
raw_plan = latest[plan_col]
plan_vs_actual = raw_plan * 100 if raw_plan < 5 else raw_plan

# FIXED REJECTION %
raw_rej_pct = latest[rej_pct_col]
rej_pct = raw_rej_pct * 100 if raw_rej_pct < 5 else raw_rej_pct

rej_day = latest[rej_day_col]
rej_cum = latest[rej_cum_col]

cum_series = df[total_cum_col].dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

achieved_pct = (total_cum / TARGET_SALE * 100) if TARGET_SALE else 0
achieved_pct_val = round(achieved_pct, 2)

# Custom colors
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# Gauge
gauge = go.Figure(go.Indicator(
    mode="gauge",
    value=achieved_pct_val,
    number={'suffix': "%", 'font': {"size": 44, "color": GREEN, "family": "Poppins", "weight": "bold"}},
    domain={'x': [0, 1], 'y': [0, 1]},
    gauge={
        "shape": "angular",
        "axis": {"range": [0, 100], "tickvals": [0, 25, 50, 75, 100], "ticktext": ["0%", "25%", "50%", "75%", "100%"]},
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

# =======================================
# TREND GRAPHS
# =======================================

try:
    sr = pd.read_excel(EXCEL_PATH, sheet_name="Sales Report", engine="openpyxl")
    sr.columns = sr.columns.str.strip().str.lower()
    sale_df = sr[sr['table_name'].str.lower() == 'sale_summery'] if 'table_name' in sr.columns else sr
    rej_df = sr[sr['table_name'].str.lower() == 'rejection_summery'] if 'table_name' in sr.columns else sr
except Exception:
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

sale_df['date'] = pd.to_datetime(sale_df['date'], errors='coerce')
sale_df['sale amount'] = pd.to_numeric(sale_df['sale amount'], errors='coerce').fillna(0)
sale_df = sale_df.dropna(subset=['date']).sort_values('date')

rej_df['date'] = pd.to_datetime(rej_df['date'], errors='coerce')
rej_df_col = rej_df.columns[rej_df.columns.str.contains('rej')].tolist()
rej_amt_col = rej_df_col[0] if rej_df_col else rej_df.columns[1] if len(rej_df.columns) > 1 else rej_df.columns[0]
rej_df['rej amt'] = pd.to_numeric(rej_df[rej_amt_col], errors='coerce').fillna(0)
rej_df = rej_df.dropna(subset=['date']).sort_values('date')

# SALE TREND
fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(x=sale_df['date'], y=sale_df['sale amount'], marker_color=BLUE))
fig_sale.update_layout(
    title="",
    margin=dict(t=20,b=40,l=10,r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    autosize=True,
)
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

# REJECTION TREND
fig_rej = go.Figure()
fig_rej.add_trace(go.Scatter(
    x=rej_df['date'], y=rej_df['rej amt'],
    mode='lines+markers',
    marker=dict(size=8, color=BUTTERFLY_ORANGE),
    line=dict(width=3, color=BUTTERFLY_ORANGE),
))
fig_rej.update_layout(
    title="",
    margin=dict(t=20,b=40,l=10,r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    autosize=True,
)
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ===========================
# HTML TEMPLATE
# ===========================

bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

center_html = f"""
<div class="center-content" style='width:100%;height:100%;'>
  <div class="value-green">{achieved_pct_val}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee if not pd.isna(oee) else 0, 1)}%"
left_rej_pct = f"{round(rej_pct if not pd.isna(rej_pct) else 0,1)}%"
bottom_rej_cum = format_inr(rej_cum)

# FULL HTML (unchanged)
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
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}}
.top-card {{
    padding: 20px 0 0 0;
}}
.bottom-card {{
    padding: 10px 0 0 0;
}}
.chart-container {{
    width: 100%;
    height: 110px;
    overflow: hidden;
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
.title-green {{
    color: {GREEN};
    font-size: 26px;
    font-weight: 700;
}}
.title-black {{
    color: #000;
    font-size: 15px;
    font-weight: 700;
    margin-top: 6px;
}}
.chart-title-black {{
    color: #000;
    font-size: 15px;
    font-weight: 700;
    text-align: left;
    padding-left: 6px;
}}
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
