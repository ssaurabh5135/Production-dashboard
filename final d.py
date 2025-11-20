import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Factory Dashboard", layout="wide")

IMAGE_PATH = "winter.JPG"

# 🔥 USE YOUR NEW GOOGLE SHEET ID
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
SHEET_NAME = "Dashboard"
TARGET_SALE = 1992000000

# ------------------ IMAGE HANDLER ------------------
def load_image_base64(path):
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except:
        return ""

# ------------------ INR FORMAT ------------------
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

# ------------------ GOOGLE AUTH ------------------
st.subheader("Google Sheets Diagnostics")

try:
    creds_dict = st.secrets["gcp_service_account"]
    st.success("[OK] Secrets loaded from Streamlit TOML.")
except Exception as e:
    st.error(f"[ERROR] Could NOT load secrets: {e}")
    st.stop()

try:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    st.success("[OK] Service Account credentials loaded.")
except Exception as e:
    st.error(f"[ERROR] Service Account auth failed: {e}")
    st.stop()

try:
    client = gspread.authorize(creds)
    st.success("[OK] GSpread client authorized.")
except Exception as e:
    st.error(f"[ERROR] gspread authorization failed: {e}")
    st.stop()

# ------------------ ACCESS SHEET ------------------
try:
    sheet = client.open_by_key(SPREADSHEET_ID)
    st.success("[OK] Spreadsheet opened.")

    try:
        worksheet = sheet.worksheet(SHEET_NAME)
        st.success(f"[OK] Worksheet found: {worksheet.title}")
    except gspread.WorksheetNotFound:
        st.error(f"Worksheet '{SHEET_NAME}' not found.")
        st.stop()

except Exception as e:
    st.error(f"[ERROR] Cannot access spreadsheet or worksheet: {e}")
    st.stop()

# ------------------ LOAD DATA ------------------
try:
    data = worksheet.get_all_records()
    st.success(f"[OK] Loaded {len(data)} rows.")
except Exception as e:
    st.error(f"[ERROR] Could NOT load data: {e}")
    st.stop()

df = pd.DataFrame(data)
if df.empty:
    st.error("No data in sheet.")
    st.stop()

# ------------------ CLEANUP ------------------
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
total_cum = df[total_cum_col].dropna().iloc[-1]

achieved_pct = (total_cum / TARGET_SALE * 100)
achieved_pct_val = round(achieved_pct, 2)

# ------------------ SIMPLE HTML ------------------
html_template = f"""
<h1 style='color:green;'>Achieved: {achieved_pct_val}%</h1>
"""

st.components.v1.html(html_template, height=200)

