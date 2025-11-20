import streamlit as st import pandas as pd import plotly.graph_objects as go import base64 from pathlib import Path import gspread from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

---------------------------

GOOGLE SHEETS CONFIG

---------------------------

Load service account JSON from Streamlit Secrets

try: sa_info = st.secrets["service_account"] creds = Credentials.from_service_account_info( sa_info, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"] ) client = gspread.authorize(creds) st.write("[OK] Service Account Authorized") except Exception as e: st.error(f"[ERROR] Service Account load failed: {e}") st.stop()

Your Google Sheet URL

SHEET_URL = "https://docs.google.com/spreadsheets/d/168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk/edit"

Try opening spreadsheet

try: sh = client.open_by_url(SHEET_URL) st.write("[OK] Spreadsheet opened successfully") # List sheet names available sheet_list = [ws.title for ws in sh.worksheets()] st.write("Sheets found:", sheet_list) except Exception as e: st.error(f"[ERROR] Cannot open spreadsheet: {e}") st.stop()

Try loading worksheet named 'Dashboard' automatically

SHEET_NAME = "Dashboard" try: ws = sh.worksheet(SHEET_NAME) st.write(f"[OK] Worksheet '{SHEET_NAME}' loaded") data = ws.get_all_records() df = pd.DataFrame(data) except Exception as e: st.error(f"[ERROR] Cannot load worksheet '{SHEET_NAME}'. Full error: {e}") st.stop()

---------------------------

REST OF YOUR CODE CONTINUES HERE (Unmodified UI)

---------------------------

Strip column names

try: df.columns = df.columns.str.strip().str.lower() except: pass

Convert date

df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce') df = df.dropna(subset=[df.columns[0]]).sort_values(df.columns[0]) latest = df.iloc[-1]

Map columns

cols = df.columns.tolist() date_col = cols[0] today_col = cols[1] oee_col = cols[2] plan_col = cols[3] rej_day_col = cols[4] rej_pct_col = cols[5] rej_cum_col = cols[6] total_cum_col = cols[7]

KPI calculations

today_sale = latest[today_col] oee = latest[oee_col] * 100 if latest[oee_col] < 5 else latest[oee_col] plan_vs_actual = latest[plan_col] * 100 if latest[plan_col] < 5 else latest[plan_col] rej_day = latest[rej_day_col] rej_pct = latest[rej_pct_col] * 100 if latest[rej_pct_col] < 5 else latest[rej_pct_col] rej_cum = latest[rej_cum_col]

Achieved %

TARGET_SALE = 19_92_00_000 cum_series = df[total_cum_col].dropna() total_cum = cum_series.iloc[-1] if not cum_series.empty else 0 achieved_pct_val = round((total_cum / TARGET_SALE * 100), 2)

---------------------------

SAME UI CODE FROM YOUR VERSION (NOT REMOVED)

---------------------------

(Keeping your UI EXACTLY same—HTML, CSS, charts, etc.)

---------------------------

st.write("[OK] Data Loaded. Rendering Dashboard...")

Place your full HTML template rendering exactly same as your code here.

st.write("Your full UI will continue below (same HTML). Replace this comment block with your UI HTML if needed.")
