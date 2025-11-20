import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64
from pathlib import Path
import gspread
import json
from google.oauth2.service_account import Credentials

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

IMAGE_PATH = "winter.JPG"

# Use the exact new spreadsheet ID
SPREADSHEET_ID = "1YXWksPNgOeamvZuCzeG1uFyc5xp9xZbZ"
SHEET_NAME = "Dashboard Sheet"
TARGET_SALE = 1992000000

# ------------------ HELPER FUNCTIONS ------------------
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

# ------------------ GOOGLE SHEETS AUTH USING SERVICE ACCOUNT ------------------
st.subheader("Google Sheets Diagnostics")

try:
    # Load JSON from Streamlit secrets
    creds_dict = st.secrets["gcp_service_account"]
    st.success("[OK] Secrets loaded from Streamlit TOML.")
except Exception as e:
    st.error(f"[ERROR] Could NOT load gcp_service_account from secrets: {e}")
    st.stop()

try:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    st.success("[OK] Service Account credentials loaded with proper scopes.")
except Exception as e:
    st.error(f"[ERROR] Service Account auth failed: {e}")
    st.stop()

try:
    client = gspread.authorize(creds)
    st.success("[OK] GSpread client authorized.")
except Exception as e:
    st.error(f"[ERROR] GSpread authorization failed: {e}")
    st.stop()

# ------------------ VERIFY SPREADSHEET ACCESS ------------------
try:
    sheet = client.open_by_key(SPREADSHEET_ID)
    try:
        worksheet = sheet.worksheet(SHEET_NAME)
        st.success(f"[OK] Spreadsheet and worksheet access verified: {worksheet.title}")
    except gspread.WorksheetNotFound:
        st.warning(f"[WARNING] Worksheet '{SHEET_NAME}' not found. Creating it...")
        worksheet = sheet.add_worksheet(title=SHEET_NAME, rows="100", cols="20")
        st.success(f"[OK] Worksheet '{SHEET_NAME}' created.")
except gspread.SpreadsheetNotFound:
    st.error("[ERROR] Spreadsheet not found. Check ID or sharing with Service Account.")
    st.stop()
except Exception as e:
    st.error(f"[ERROR] Cannot access spreadsheet or worksheet: {e}")
    st.stop()

# ------------------ LOAD DATA ------------------
try:
    data = worksheet.get_all_records()
    st.success(f"[OK] Data loaded ({len(data)} rows).")
except Exception as e:
    st.error(f"[ERROR] Getting records failed: {e}")
    st.stop()

df = pd.DataFrame(data)
if df.empty:
    st.error("[ERROR] No data found.")
    st.stop()

# ------------------ DATA CLEANUP ------------------
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
        "axis": {"range": [0, 100], "tickvals": [0, 25, 50, 75, 100],
                 "ticktext": ["0%", "25%", "50%", "75%", "100%"]},
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

# ------------------ BACKGROUND IMAGE ------------------
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# ------------------ HTML TEMPLATE ------------------
top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee if not pd.isna(oee) else 0, 1)}%"
left_rej_pct = f"{round(rej_pct if not pd.isna(rej_pct) else 0,1)}%"
left_rej_day = format_inr(rej_day)
bottom_rej_cum = format_inr(rej_cum)
center_html = f"""
<div class="center-content" style='width:100%;height:100%;'>
  <div class="value-green">{achieved_pct_val}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

html_template = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
</head>
<body>
<div>{center_html}</div>
</body>
</html>
"""

st.components.v1.html(html_template, height=770, scrolling=True)
