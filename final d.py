import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import base64
import gspread
from google.oauth2.service_account import Credentials

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")
IMAGE_PATH = "winter.JPG"
SPREADSHEET_ID = "1YXWksPNgOeamvZuCzeG1uFyc5xp9xZbZ"  # Your sheet ID
SHEET_NAME = "Dashboard Sheet"
TARGET_SALE = 1992000000

# ------------------ HELPERS ------------------
def load_image_base64(path):
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except Exception as e:
        st.warning(f"Background image not found: {e}")
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
    rest = ','.join([rest[::-1][i:i+2][::-1] for i in range(0, len(rest), 2)][::-1])
    return rest + last3

# ------------------ SERVICE ACCOUNT AUTH ------------------
st.subheader("Google Sheets Diagnostics")

try:
    creds_dict = st.secrets["gcp_service_account"]
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    st.success("✅ Service Account authorized")
except Exception as e:
    st.error(f"❌ Authorization failed: {e}")
    st.stop()

# ------------------ DEBUG: LIST ALL SPREADSHEETS ------------------
try:
    sheets = client.openall()
    st.write("🟢 Spreadsheets accessible to this Service Account:")
    for s in sheets:
        st.write(f"- {s.title} (ID: {s.id})")
except Exception as e:
    st.error(f"❌ Cannot list spreadsheets: {e}")

# ------------------ VERIFY SPREADSHEET & WORKSHEET ------------------
try:
    sheet = client.open_by_key(SPREADSHEET_ID)
    worksheets = sheet.worksheets()
    st.write("✅ Worksheets in this spreadsheet:")
    for ws in worksheets:
        st.write(f"- {ws.title}")
    try:
        worksheet = sheet.worksheet(SHEET_NAME)
        st.success(f"✅ Access to worksheet '{SHEET_NAME}' verified")
    except gspread.WorksheetNotFound:
        st.warning(f"⚠️ Worksheet '{SHEET_NAME}' not found. Creating it...")
        worksheet = sheet.add_worksheet(title=SHEET_NAME, rows="100", cols="20")
        st.success(f"✅ Worksheet '{SHEET_NAME}' created")
except Exception as e:
    st.error(f"❌ Cannot access spreadsheet or worksheet: {e}")
    st.stop()

# ------------------ LOAD DATA ------------------
try:
    data = worksheet.get_all_records()
    st.success(f"✅ Data loaded ({len(data)} rows)")
except Exception as e:
    st.error(f"❌ Failed to get records: {e}")
    st.stop()

df = pd.DataFrame(data)
if df.empty:
    st.error("❌ No data found")
    st.stop()

# ------------------ CLEAN & PREPARE DATA ------------------
df.columns = df.columns.str.strip().str.lower()
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

today_sale = latest[today_col]
oee = latest[oee_col] * 100 if latest[oee_col] < 5 else latest[oee_col]
plan_vs_actual = latest[plan_col] * 100 if latest[plan_col] < 5 else latest[plan_col]
rej_day = latest[rej_day_col]
rej_pct = latest[rej_pct_col] * 100 if latest[rej_pct_col] < 5 else latest[rej_pct_col]
rej_cum = latest[rej_cum_col]
cum_series = df[total_cum_col].dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

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
        "axis": {"range": [0, 100]},
        "bar": {"color": GREEN, "thickness": 0.38},
        "steps": [
            {"range": [0, 60], "color": "#c4eed1"},
            {"range": [60, 85], "color": "#7ee2b7"},
            {"range": [85, 100], "color": GREEN}
        ]
    }
))
gauge.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=10, b=30, l=10, r=10), height=170, width=300)

# ------------------ DASHBOARD HTML ------------------
center_html = f"""
<div class="center-content" style='width:100%;height:100%;'>
  <div class="value-green">{achieved_pct_val}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

st.components.v1.html(center_html, height=300, scrolling=True)
