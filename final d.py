import streamlit as st 
import pandas as pd
import plotly.graph_objects as go 
import base64 from pathlib
import Path 
import gspread from google.oauth2.service_account
import Credentials

------------------ PAGE CONFIG ------------------

st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

------------------ CONFIG ------------------

IMAGE_PATH = "winter.jpg" SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk" DASHBOARD_SHEET = "Dashboard" SALES_REPORT_SHEET = "Sales Report" TARGET_SALE = 19_92_00_000

------------------ HELPERS ------------------

def load_image_base64(path): try: data = Path(path).read_bytes() return base64.b64encode(data).decode() except: return ""

def format_inr(n): try: x = str(int(n)) except: return str(n) if len(x) <= 3: return x last3 = x[-3:] rest = x[:-3] rest = ''.join([rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1]) return rest + last3

------------------ AUTH ------------------

creds_info = st.secrets["gcp_service_account"] SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"] creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES) client = gspread.authorize(creds)

------------------ OPEN SHEET ------------------

sh = client.open_by_key(SPREADSHEET_ID) worksheet = sh.worksheet(DASHBOARD_SHEET)

------------------ LOAD A1:H STRICT ------------------

rows = worksheet.get_values('A1:H') header = rows[0] data_rows = rows[1:] data = [dict(zip(header, r)) for r in data_rows] df = pd.DataFrame(data) df.columns = [str(c) for c in df.columns]

if df.empty: st.error("Dashboard sheet empty.") st.stop()

------------------ CLEAN DATA ------------------

df.columns = df.columns.str.strip().str.lower() df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce') df = df.dropna(subset=[df.columns[0]]).sort_values(df.columns[0]) latest = df.iloc[-1] cols = df.columns.tolist()

HEADER MAPPING

exact header order enforced

expected = [ "date", "today's sale", "oee %", "plan vs actual %", "rejection amount (daybefore)", "rejection %", "rejection amount (cumulative)", "total sales (cumulative)" ]

normalize comparison

if [c.strip().lower() for c in cols[:8]] != [e.lower() for e in expected]: st.error(f"Dashboard headers mismatch. Found: {cols}") st.stop()

(date_col, today_col, oee_col, plan_col, rej_day_col, rej_pct_col, rej_cum_col, total_cum_col) = cols[:8]

def get_val(r, c): try: return r[c] except: return 0

VALUES

today_sale = get_val(latest, today_col) oee = get_val(latest, oee_col) plan_vs_actual = get_val(latest, plan_col) rej_day = get_val(latest, rej_day_col) rej_pct = get_val(latest, rej_pct_col) rej_cum = get_val(latest, rej_cum_col) cum_series = pd.to_numeric(df[total_cum_col], errors='coerce').dropna() total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

def ensure_pct(x): try: x = float(x) return x * 100 if x <= 1 else x except: return 0

oee = ensure_pct(oee) plan_vs_actual = ensure_pct(plan_vs_actual) rej_pct = ensure_pct(rej_pct) achieved_pct_val = round((total_cum / TARGET_SALE * 100) if TARGET_SALE else 0, 2)

------------------ COLORS ------------------

BUTTERFLY_ORANGE = "#fc7d1b" BLUE = "#228be6" GREEN = "#009e4f"

------------------ KPI GAUGE ------------------

gauge = go.Figure(go.Indicator( mode="gauge", value=achieved_pct_val, number={'suffix': "%", 'font': {"size": 44, "color": GREEN}}, domain={'x': [0, 1], 'y': [0, 1]}, gauge={ "shape": "angular", "axis": {"range": [0, 100]}, "bar": {"color": GREEN} } )) gauge.update_layout(height=170, width=300, paper_bgcolor="rgba(0,0,0,0)") gauge_html = gauge.to_html(include_plotlyjs='cdn', full_html=False)

SALES REPORT (fallback)

sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]}) rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

sale_df['date'] = pd.to_datetime(sale_df['date'], errors='coerce') sale_df['sale amount'] = pd.to_numeric(sale_df['sale amount'], errors='coerce').fillna(0) sale_df = sale_df.dropna(subset=['date']).sort_values('date')

rej_df['date'] = pd.to_datetime(rej_df['date'], errors='coerce') rej_df['rej amt'] = pd.to_numeric(rej_df['rej amt'], errors='coerce').fillna(0) rej_df = rej_df.dropna(subset=['date']).sort_values('date')

------------------ CHARTS ------------------

fig_sale = go.Figure() fig_sale.add_trace(go.Bar(x=sale_df['date'], y=sale_df['sale amount'], marker_color=BLUE)) sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

fig_rej = go.Figure() fig_rej.add_trace(go.Scatter(x=rej_df['date'], y=rej_df['rej amt'], mode='lines+markers', marker=dict(color=BUTTERFLY_ORANGE))) rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

------------------ BACKGROUND ------------------

bg_b64 = load_image_base64(IMAGE_PATH) bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

------------------ HTML TEMPLATE ------------------

center_html = f"""

<div class='center-content'>
  <div class='value-green'>{achieved_pct_val}%</div>
  <div class='title-green'>Achieved %</div>
</div>
"""top_date = latest[date_col].strftime("%d-%b-%Y") top_today_sale = format_inr(today_sale) top_oee = f"{round(oee,1)}%" left_rej_pct = f"{round(rej_pct,1)}%" bottom_rej_cum = format_inr(rej_cum)

html_template = f""" <!doctype html>

<html><body><h3 style='display:none'></h3></body></html>
"""st.components.v1.html(html_template, height=200) import streamlit as st import pandas as pd import plotly.graph_objects as go import base64 from pathlib import Path import gspread from google.oauth2.service_account import Credentials

------------------ PAGE CONFIG ------------------

st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

------------------ CONFIG ------------------

IMAGE_PATH = "winter.jpg" SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk" DASHBOARD_SHEET = "Dashboard" SALES_REPORT_SHEET = "Sales Report" TARGET_SALE = 19_92_00_000

------------------ HELPERS ------------------

def load_image_base64(path): try: data = Path(path).read_bytes() return base64.b64encode(data).decode() except: return ""

def format_inr(n): try: x = str(int(n)) except: return str(n) if len(x) <= 3: return x last3 = x[-3:] rest = x[:-3] rest = ''.join([rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1]) return rest + last3

------------------ AUTH ------------------

creds_info = st.secrets["gcp_service_account"] SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"] creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES) client = gspread.authorize(creds)

------------------ OPEN SHEET ------------------

sh = client.open_by_key(SPREADSHEET_ID) worksheet = sh.worksheet(DASHBOARD_SHEET)

------------------ LOAD A1:H STRICT ------------------

rows = worksheet.get_values('A1:H') header = rows[0] data_rows = rows[1:] data = [dict(zip(header, r)) for r in data_rows] df = pd.DataFrame(data) df.columns = [str(c) for c in df.columns]

if df.empty: st.error("Dashboard sheet empty.") st.stop()

------------------ CLEAN DATA ------------------

df.columns = df.columns.str.strip().str.lower() df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce') df = df.dropna(subset=[df.columns[0]]).sort_values(df.columns[0]) latest = df.iloc[-1] cols = df.columns.tolist()

HEADER MAPPING

exact header order enforced

expected = [ "date", "today's sale", "oee %", "plan vs actual %", "rejection amount (daybefore)", "rejection %", "rejection amount (cumulative)", "total sales (cumulative)" ]

normalize comparison

if [c.strip().lower() for c in cols[:8]] != [e.lower() for e in expected]: st.error(f"Dashboard headers mismatch. Found: {cols}") st.stop()

(date_col, today_col, oee_col, plan_col, rej_day_col, rej_pct_col, rej_cum_col, total_cum_col) = cols[:8]

def get_val(r, c): try: return r[c] except: return 0

VALUES

today_sale = get_val(latest, today_col) oee = get_val(latest, oee_col) plan_vs_actual = get_val(latest, plan_col) rej_day = get_val(latest, rej_day_col) rej_pct = get_val(latest, rej_pct_col) rej_cum = get_val(latest, rej_cum_col) cum_series = pd.to_numeric(df[total_cum_col], errors='coerce').dropna() total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

def ensure_pct(x): try: x = float(x) return x * 100 if x <= 1 else x except: return 0

oee = ensure_pct(oee) plan_vs_actual = ensure_pct(plan_vs_actual) rej_pct = ensure_pct(rej_pct) achieved_pct_val = round((total_cum / TARGET_SALE * 100) if TARGET_SALE else 0, 2)

------------------ COLORS ------------------

BUTTERFLY_ORANGE = "#fc7d1b" BLUE = "#228be6" GREEN = "#009e4f"

------------------ KPI GAUGE ------------------

gauge = go.Figure(go.Indicator( mode="gauge", value=achieved_pct_val, number={'suffix': "%", 'font': {"size": 44, "color": GREEN}}, domain={'x': [0, 1], 'y': [0, 1]}, gauge={ "shape": "angular", "axis": {"range": [0, 100]}, "bar": {"color": GREEN} } )) gauge.update_layout(height=170, width=300, paper_bgcolor="rgba(0,0,0,0)") gauge_html = gauge.to_html(include_plotlyjs='cdn', full_html=False)

SALES REPORT (fallback)

sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]}) rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

sale_df['date'] = pd.to_datetime(sale_df['date'], errors='coerce') sale_df['sale amount'] = pd.to_numeric(sale_df['sale amount'], errors='coerce').fillna(0) sale_df = sale_df.dropna(subset=['date']).sort_values('date')

rej_df['date'] = pd.to_datetime(rej_df['date'], errors='coerce') rej_df['rej amt'] = pd.to_numeric(rej_df['rej amt'], errors='coerce').fillna(0) rej_df = rej_df.dropna(subset=['date']).sort_values('date')

------------------ CHARTS ------------------

fig_sale = go.Figure() fig_sale.add_trace(go.Bar(x=sale_df['date'], y=sale_df['sale amount'], marker_color=BLUE)) sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

fig_rej = go.Figure() fig_rej.add_trace(go.Scatter(x=rej_df['date'], y=rej_df['rej amt'], mode='lines+markers', marker=dict(color=BUTTERFLY_ORANGE))) rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

------------------ BACKGROUND ------------------

bg_b64 = load_image_base64(IMAGE_PATH) bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

------------------ HTML TEMPLATE ------------------

center_html = f"""

<div class='center-content'>
  <div class='value-green'>{achieved_pct_val}%</div>
  <div class='title-green'>Achieved %</div>
</div>
"""top_date = latest[date_col].strftime("%d-%b-%Y") top_today_sale = format_inr(today_sale) top_oee = f"{round(oee,1)}%" left_rej_pct = f"{round(rej_pct,1)}%" bottom_rej_cum = format_inr(rej_cum)

html_template = f""" <!doctype html>

<html><body><h3 style='display:none'></h3></body></html>
"""st.components.v1.html(html_template, height=200)
