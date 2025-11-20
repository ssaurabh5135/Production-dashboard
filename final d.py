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
IMAGE_PATH = "winter.JPG"
# Google Sheets: use the converted Google Sheets ID you provided
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
# worksheet names
DASHBOARD_SHEET = "Dashboard"            # main data (was Dashboard Sheet in excel)
SALES_REPORT_SHEET = "Sales Report"      # optional
TARGET_SALE = 19_92_00_000

# ------------------ HELPERS ------------------
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

# ------------------ GOOGLE SERVICE ACCOUNT AUTH ------------------
st.subheader("Google Sheets Diagnostics")
try:
    creds_info = st.secrets["gcp_service_account"]
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    st.success("[OK] Service Account credentials loaded.")
except Exception as e:
    st.error(f"[ERROR] Service Account auth failed: {e}")
    st.stop()

# Show spreadsheets visible (debug)
try:
    sheets_visible = client.openall()
    if sheets_visible:
        st.write("Spreadsheets visible to service account (first 50):")
        for s in sheets_visible[:50]:
            st.write(f"- {s.title}  |  ID: {s.id}")
    else:
        st.warning("No spreadsheets visible to the service account (this can indicate missing sharing).")
except Exception as e:
    st.warning(f"Could not list spreadsheets: {e}")

# ------------------ OPEN SPREADSHEET & WORKSHEET ------------------
try:
    sh = client.open_by_key(SPREADSHEET_ID)
    st.success(f"[OK] Opened spreadsheet: {sh.title}")
    # list worksheets for debugging
    worksheets = [w.title for w in sh.worksheets()]
    st.write("Worksheets in spreadsheet:", worksheets)
except Exception as e:
    st.error(f"[ERROR] Cannot open spreadsheet by ID ({SPREADSHEET_ID}): {e}")
    st.stop()

# Try to load Dashboard worksheet
try:
    worksheet = sh.worksheet(DASHBOARD_SHEET)
    st.success(f"[OK] Opened worksheet: {DASHBOARD_SHEET}")
except gspread.WorksheetNotFound:
    st.error(f"[ERROR] Worksheet '{DASHBOARD_SHEET}' not found. Available sheets: {worksheets}")
    st.stop()
except Exception as e:
    st.error(f"[ERROR] Cannot access worksheet '{DASHBOARD_SHEET}': {e}")
    st.stop()

# ------------------ LOAD DATA FROM SHEET (READ ONLY A1:H) ------------------
try:
    # Read EXACT fixed range → ignores helper columns in G3/S3
    rows = worksheet.get_values('A1:H')

    if not rows or len(rows) < 2:
        st.error("[ERROR] Dashboard sheet has no usable data in A1:H.")
        st.stop()

    header = rows[0]                  # A1 to H1
    data_rows = rows[1:]              # Data from row 2 downward
    data = [dict(zip(header, r)) for r in data_rows]

    st.success(f"[OK] Data loaded from '{DASHBOARD_SHEET}' (strict A1:H mode, {len(data)} rows).")

except Exception as e:
    st.error(f"[ERROR] Failed reading A1:H from Dashboard: {e}")
    st.stop()
# ------------------ DATA CLEANUP & KPIS ------------------
# normalize columns and parse date
df.columns = df.columns.str.strip().str.lower()
df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce')
df = df.dropna(axis=0, subset=[df.columns[0]])
df = df.sort_values(df.columns[0])
latest = df.iloc[-1]
cols = df.columns.tolist()

# Basic defensive check for expected number of columns
if len(cols) < 8:
    st.error(f"[ERROR] Expected at least 8 columns in dashboard sheet. Found {len(cols)} columns: {cols}")
    st.stop()

date_col = cols[0]
today_col = cols[1]
oee_col = cols[2]
plan_col = cols[3]
rej_day_col = cols[4]
rej_pct_col = cols[5]
rej_cum_col = cols[6]
total_cum_col = cols[7]

# extract values (robust handling)
def get_val(row, col):
    try:
        return row[col]
    except Exception:
        return 0

today_sale = get_val(latest, today_col)
oee = get_val(latest, oee_col)
plan_vs_actual = get_val(latest, plan_col)
rej_day = get_val(latest, rej_day_col)
rej_pct = get_val(latest, rej_pct_col)
rej_cum = get_val(latest, rej_cum_col)
cum_series = pd.to_numeric(df[total_cum_col], errors='coerce').dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

# convert percentages if they are in decimals
def ensure_pct(x):
    try:
        x = float(x)
        return x * 100 if x <= 1 else x
    except:
        return 0

oee = ensure_pct(oee)
plan_vs_actual = ensure_pct(plan_vs_actual)
rej_pct = ensure_pct(rej_pct)

achieved_pct_val = round((total_cum / TARGET_SALE * 100) if TARGET_SALE else 0, 2)

# ------------------ COLORS ------------------
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ------------------ KPI GAUGE ------------------
gauge = go.Figure(go.Indicator(
    mode="gauge",
    value=achieved_pct_val,
    number={'suffix': "%", 'font': {"size": 44, "color": GREEN}},
    domain={'x': [0, 1], 'y': [0, 1]},
    gauge={
        "shape": "angular",
        "axis": {"range": [0, 100], "tickvals": [0, 25, 50, 75, 100]},
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

# ------------------ LOAD SALES REPORT SHEET (OPTIONAL) ------------------
try:
    sr_ws = sh.worksheet(SALES_REPORT_SHEET)
    sr_data = sr_ws.get_all_records()
    sr = pd.DataFrame(sr_data)
    sr.columns = sr.columns.str.strip().str.lower()
    sale_df = sr[sr['table_name'].str.lower() == 'sale_summery'] if 'table_name' in sr.columns else sr
    rej_df = sr[sr['table_name'].str.lower() == 'rejection_summery'] if 'table_name' in sr.columns else sr
    st.success(f"[OK] Sales Report loaded ({len(sr)} rows).")
except Exception:
    st.warning(f"[WARN] 'Sales Report' sheet unavailable or read failed — using fallback from Dashboard data.")
    sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
    rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

# ------------------ CLEANUP FOR CHARTS ------------------
sale_df['date'] = pd.to_datetime(sale_df['date'], errors='coerce')
sale_df['sale amount'] = pd.to_numeric(sale_df['sale amount'], errors='coerce').fillna(0)
sale_df = sale_df.dropna(subset=['date']).sort_values('date')

rej_df['date'] = pd.to_datetime(rej_df['date'], errors='coerce')
rej_df_col = rej_df.columns[rej_df.columns.str.contains('rej')].tolist()
rej_amt_col = rej_df_col[0] if rej_df_col else (rej_df.columns[1] if len(rej_df.columns) > 1 else rej_df.columns[0])
rej_df['rej amt'] = pd.to_numeric(rej_df[rej_amt_col], errors='coerce').fillna(0)
rej_df = rej_df.dropna(subset=['date']).sort_values('date')

# ------------------ PLOTLY FIGURES ------------------
fig_sale = go.Figure()
fig_sale.add_trace(go.Bar(x=sale_df['date'], y=sale_df['sale amount'], marker_color=BLUE))
fig_sale.update_layout(
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    autosize=True,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45),
    yaxis=dict(showgrid=False, tickfont=dict(size=12))
)
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

fig_rej = go.Figure()
fig_rej.add_trace(go.Scatter(
    x=rej_df['date'], y=rej_df['rej amt'],
    mode='lines+markers',
    marker=dict(size=8, color=BUTTERFLY_ORANGE),
    line=dict(width=3, color=BUTTERFLY_ORANGE),
))
fig_rej.update_layout(
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    autosize=True,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45),
    yaxis=dict(showgrid=False, tickfont=dict(size=12))
)
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ------------------ BACKGROUND IMAGE ------------------
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# ------------------ HTML TEMPLATE (keeps your UI same) ------------------
center_html = f"""
<div class="center-content" style='width:100%;height:100%;'>
  <div class="value-green">{achieved_pct_val}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}%"
left_rej_pct = f"{round(rej_pct if pd.notna(rej_pct) else 0,1)}%"
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

