import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64
from pathlib import Path
import json
from google.oauth2.service_account import Credentials
import gspread

# ----------- CONFIG ----------
st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

IMAGE_PATH = "winter.JPG"  # Your image file path
SPREADSHEET_ID = "1xUsy3nWWuHqOVZi_Q57jatIV78w77wTu"
SHEET_NAME = "Dashboard Sheet"
TARGET_SALE = 1992000000

BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ----------- HELPER FUNCTIONS ----------
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
    rest = ''.join([rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1])
    return rest + last3

# ----------- STEP 1: LOAD SERVICE ACCOUNT ----------
st.subheader("Google Sheets Diagnostics")
try:
    json_str = st.secrets["gcp_service_account"]["json"]
    creds_dict = json.loads(json_str)
    st.success("[OK] Secrets loaded and JSON parsed.")
except Exception as e:
    st.error(f"[ERROR] Could not load service account secrets: {e}")
    st.stop()

# ----------- STEP 2: CREATE CREDENTIALS WITH SCOPES ----------
try:
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    st.success("[OK] Service Account credentials created with proper scopes.")
except Exception as e:
    st.error(f"[ERROR] Could not create credentials: {e}")
    st.stop()

# ----------- STEP 3: AUTHORIZE GSPREAD CLIENT ----------
try:
    client = gspread.authorize(creds)
    st.success("[OK] GSpread client authorized.")
except Exception as e:
    st.error(f"[ERROR] GSpread authorization failed: {e}")
    st.stop()

# ----------- STEP 4: OPEN SPREADSHEET ----------
try:
    sheet = client.open_by_key(SPREADSHEET_ID)
    st.success(f"[OK] Spreadsheet accessed by ID: {SPREADSHEET_ID}")
except Exception as e:
    st.error(f"[ERROR] Cannot access spreadsheet: {e}")
    st.stop()

# ----------- STEP 5: OPEN WORKSHEET ----------
try:
    worksheet = sheet.worksheet(SHEET_NAME)
    st.success(f"[OK] Worksheet accessed: {SHEET_NAME}")
except Exception as e:
    st.error(f"[ERROR] Cannot access worksheet '{SHEET_NAME}': {e}")
    st.stop()

# ----------- STEP 6: LOAD DATA ----------
try:
    data = worksheet.get_all_records()
    if not data:
        st.error("[ERROR] Worksheet is empty.")
        st.stop()
    st.success(f"[OK] Data loaded ({len(data)} rows).")
except Exception as e:
    st.error(f"[ERROR] Getting records failed: {e}")
    st.stop()

df = pd.DataFrame(data)
df.columns = df.columns.str.strip().str.lower()
df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce')
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

today_sale = latest[today_col]
oee = latest[oee_col] * 100 if latest[oee_col] < 5 else latest[oee_col]
plan_vs_actual = latest[plan_col] * 100 if latest[plan_col] < 5 else latest[plan_col]
rej_day = latest[rej_day_col]
rej_pct = latest[rej_pct_col] * 100 if latest[rej_pct_col] < 5 else latest[rej_pct_col]
rej_cum = latest[rej_cum_col]
cum_series = df[total_cum_col].dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0
achieved_pct = (total_cum / TARGET_SALE * 100) if TARGET_SALE else 0
achieved_pct_val = round(achieved_pct, 2)

# ----------- STEP 7: GAUGE PLOT -----------
gauge = go.Figure(go.Indicator(
    mode="gauge",
    value=achieved_pct_val,
    number={'suffix': "%", 'font': {"size": 44, "color": GREEN, "family": "Poppins", "weight": "bold"}},
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
gauge.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=10, b=30, l=10, r=10),
    height=170,
    width=300
)

# ----------- STEP 8: LOAD BACKGROUND IMAGE ----------
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# ----------- STEP 9: OPTIONAL SALES REPORT ----------
try:
    sales_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Sales Report")
    sr_data = sales_sheet.get_all_records()
    sr = pd.DataFrame(sr_data)
    sr.columns = sr.columns.str.strip().str.lower()
    sale_df = sr[sr['table_name'].str.lower() == 'sale_summery'] if 'table_name' in sr.columns else sr
    rej_df = sr[sr['table_name'].str.lower() == 'rejection_summery'] if 'table_name' in sr.columns else sr
    st.success("[OK] Sales Report data loaded.")
except Exception as e:
    st.warning(f"[Warning] Loading Sales Report failed ({e}), fallback from Dashboard Sheet.")
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

# ----------- STEP 10: PLOT SALES AND REJECTION ----------
fig_sale = go.Figure(go.Bar(x=sale_df['date'], y=sale_df['sale amount'], marker_color=BLUE))
fig_sale.update_layout(
    title="",
    margin=dict(t=20,b=40,l=10,r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True)
)

fig_rej = go.Figure(go.Scatter(
    x=rej_df['date'], y=rej_df['rej amt'],
    mode='lines+markers',
    marker=dict(size=8, color=BUTTERFLY_ORANGE),
    line=dict(width=3, color=BUTTERFLY_ORANGE)
))
fig_rej.update_layout(
    title="",
    margin=dict(t=20,b=40,l=10,r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True)
)

# ----------- STEP 11: DASHBOARD HTML ----------
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
left_rej_day = format_inr(rej_day)
bottom_rej_cum = format_inr(rej_cum)

html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
</head>
<body>
<div>
{center_html}
<p>Date: {top_date}</p>
<p>Today's Sale: {top_today_sale}</p>
<p>OEE: {top_oee}</p>
<p>Rejection %: {left_rej_pct}</p>
<p>Rejection Day: {left_rej_day}</p>
<p>Cumulative Rejection: {bottom_rej_cum}</p>
</div>
</body>
</html>
"""

# ----------- STEP 12: RENDER -----------
st.components.v1.html(html_template, height=770, scrolling=True)
st.plotly_chart(gauge)
st.plotly_chart(fig_sale)
st.plotly_chart(fig_rej)
