import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.title("Service Account Debug (Secrets)")

# ------------------ Load Service Account from Streamlit secrets ------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

try:
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    st.success("✅ Service Account authorized via Secrets")
except Exception as e:
    st.error(f"❌ Authorization failed: {e}")
    st.stop()

# ------------------ List accessible spreadsheets ------------------
st.subheader("Accessible Spreadsheets")
try:
    sheets = client.openall()
    if sheets:
        for s in sheets:
            st.write(f"📄 {s.title} | ID: {s.id}")
    else:
        st.warning("No spreadsheets found! Service Account may not have access.")
except Exception as e:
    st.error(f"❌ Could not list spreadsheets: {e}")

# ------------------ Test opening your spreadsheet ------------------
SPREADSHEET_ID = "1YXWksPNgOeamvZuCzeG1uFyc5xp9xZbZ"
SHEET_NAME = "Dashboard Sheet"

st.subheader("Test Spreadsheet Access")
try:
    sheet = client.open_by_key(SPREADSHEET_ID)
    st.success(f"✅ Spreadsheet opened: {sheet.title}")
    try:
        worksheet = sheet.worksheet(SHEET_NAME)
        st.success(f"✅ Worksheet opened: {worksheet.title}")
    except gspread.WorksheetNotFound:
        st.error(f"❌ Worksheet '{SHEET_NAME}' not found. Check spelling/case.")
except gspread.SpreadsheetNotFound:
    st.error(f"❌ Spreadsheet with ID {SPREADSHEET_ID} not found. Check sharing.")
except Exception as e:
    st.error(f"❌ Cannot access spreadsheet or worksheet: {e}")
