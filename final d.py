import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# ------------------ CONFIG ------------------
SPREADSHEET_ID = "1YXWksPNgOeamvZuCzeG1uFyc5xp9xZbZ"
SHEET_NAME = "Dashboard Sheet"

st.subheader("Google Sheets Diagnostics")

# ------------------ SERVICE ACCOUNT AUTH ------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

try:
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    st.success("[OK] GSpread client authorized with service account.")
except Exception as e:
    st.error(f"[ERROR] Service Account auth failed: {e}")
    st.stop()

# ------------------ VERIFY SPREADSHEET ACCESS ------------------
try:
    sheet = client.open_by_key(SPREADSHEET_ID)
    st.success(f"[OK] Spreadsheet accessed: {sheet.title}")

    # List available worksheets
    worksheets = sheet.worksheets()
    st.write("Available worksheets:", [w.title for w in worksheets])

    # Try opening the target worksheet
    try:
        worksheet = sheet.worksheet(SHEET_NAME)
        st.success(f"[OK] Worksheet found: {worksheet.title}")
    except gspread.WorksheetNotFound:
        st.warning(f"[WARNING] Worksheet '{SHEET_NAME}' not found. Creating it...")
        worksheet = sheet.add_worksheet(title=SHEET_NAME, rows="100", cols="20")
        st.success(f"[OK] Worksheet '{SHEET_NAME}' created.")

except gspread.SpreadsheetNotFound:
    st.error("[ERROR] Spreadsheet not found. Double-check ID or sharing with service account.")
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
    st.warning("[WARNING] No data found in the sheet yet.")
