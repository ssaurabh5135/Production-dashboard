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
IMAGE_PATH = "winter.jpg"  # image stored in the repo next to this file
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
DASHBOARD_SHEET = "Dashboard"
SALES_REPORT_SHEET = "Sales Report"
TARGET_SALE = 19_92_00_000

# ------------------ HELPERS ------------------
def load_image_base64(path: str) -> str:
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except Exception:
        # Silent fallback: no warning text on UI
        return ""

def format_inr(n):
    try:
        x = str(int(float(str(n).replace(",", ""))))
    except Exception:
        return str(n)
    if len(x) <= 3:
        return x
    last3 = x[-3:]
    rest = x[:-3]
    rest = ''.join(
        [rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1]
    )
    return rest + last3

def ensure_pct(x):
    """
    Behave like your original logic:
    - If value is <= 5, treat as decimal (0.88 -> 88)
    - Else assume already percentage (88 -> 88)
    """
    try:
        v = float(str(x).replace("%", "").replace(",", ""))
    except Exception:
        return 0.0
    return v * 100 if v <= 5 else v

# ------------------ GOOGLE SHEETS AUTH ------------------
try:
    creds_info = st.secrets["gcp_service_account"]
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    client = gspread.authorize(creds)
except Exception as e:
    st.error(f"Google auth failed: {e}")
    st.stop()

# ------------------ OPEN SPREADSHEET ------------------
try:
    sh = client.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Cannot open spreadsheet: {e}")
    st.stop()

# ================== LOAD DASHBOARD SHEET (A1:H) ==================
try:
    dash_ws = sh.worksheet(DASHBOARD_SHEET)
    rows = dash_ws.get_values("A1:H")
except Exception as e:
    st.error(f"Cannot read Dashboard sheet: {e}")
    st.stop()

if not rows or len(rows) < 2:
    st.error("Dashboard sheet has no data (A1:H).")
    st.stop()

header = rows[0]
data_rows = [r for r in rows[1:] if any(r)]  # drop completely empty rows

dash_data = [dict(zip(header, r)) for r in data_rows]
df = pd.DataFrame(dash_data)

# Normalise header names
df.columns = df.columns.str.strip().str.lower()

# We expect exactly 8 columns in same order as Excel
expected_cols = [
    "date",
    "today's sale",
    "oee %",
    "plan vs actual %",
    "rejection amount (daybefore)",
    "rejection %",
    "rejection amount (cumulative)",
    "total sales (cumulative)",
]
if list(df.columns[:8]) != expected_cols:
    # If order different, still continue but warn
    pass

# Parse date column
date_col = df.columns[0]
df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

# Make numeric for remaining columns
for c in df.columns[1:]:
    df[c] = pd.to_numeric(
        df[c].astype(str).str.replace(",", ""), errors="coerce"
    )

df = df.dropna(subset=[date_col])
if df.empty:
    st.error("No valid dates in Dashboard sheet.")
    st.stop()

df = df.sort_values(date_col)
latest = df.iloc[-1]
cols = df.columns.tolist()

(
    date_col,
    today_col,
    oee_col,
    plan_col,
    rej_day_col,
    rej_pct_col,
    rej_cum_col,
    total_cum_col,
) = cols[:8]

# ------------------ KPIs (same logic as VS Code) ------------------
today_sale = latest[today_col]

raw_oee = latest[oee_col]
oee = ensure_pct(raw_oee)

raw_plan = latest[plan_col]
plan_vs_actual = ensure_pct(raw_plan)

rej_day = latest[rej_day_col]
raw_rej_pct = latest[rej_pct_col]

raw_rej_pct = latest[rej_pct_col]
rej_pct = ensure_pct(raw_rej_pct)

rej_cum = latest[rej_cum_col]

cum_series = df[total_cum_col].dropna()
total_cum = cum_series.iloc[-1] if not cum_series.empty else 0

achieved_pct = (total_cum / TARGET_SALE * 100) if TARGET_SALE else 0
achieved_pct_val = round(achieved_pct, 2)

# ------------------ COLORS ------------------
BUTTERFLY_ORANGE = "#fc7d1b"
BLUE = "#228be6"
GREEN = "#009e4f"

# ================== KPI GAUGE (same as VS logic) ==================
gauge = go.Figure(
    go.Indicator(
        mode="gauge",
        value=achieved_pct_val,
        number={
            "suffix": "%",
            "font": {
                "size": 44,
                "color": GREEN,
                "family": "Poppins",
                "weight": "bold",
            },
        },
        domain={"x": [0, 1], "y": [0, 1]},
        gauge={
            "shape": "angular",
            "axis": {
                "range": [0, 100],
                "tickvals": [0, 25, 50, 75, 100],
                "ticktext": ["0%", "25%", "50%", "75%", "100%"],
            },
            "bar": {"color": GREEN, "thickness": 0.38},
            "bgcolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [0, 60], "color": "#c4eed1"},
                {"range": [60, 85], "color": "#7ee2b7"},
                {"range": [85, 100], "color": GREEN},
            ],
            "threshold": {
                "line": {"color": "#111", "width": 5},
                "value": achieved_pct_val,
            },
        },
    )
)
gauge.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=10, b=30, l=10, r=10),
    height=170,
    width=300,
)
gauge_html = gauge.to_html(include_plotlyjs="cdn", full_html=False)

# ================== SALES REPORT → TRENDS ==================
# We ignore complex headers and manually select columns like your Excel logic.
try:
    sr_ws = sh.worksheet(SALES_REPORT_SHEET)
    sr_rows = sr_ws.get_values()  # full sheet
except Exception:
    sr_rows = []

sale_df = None
rej_df = None

if sr_rows and len(sr_rows) > 1:
    sale_records = []
    rej_records = []

    # Row 0 is header row in Google Sheet
    for r in sr_rows[1:]:
        # Make sure row has enough columns
        # ---- Left block: Date (A), Sales Type (B), Sale Amount (C)
        if len(r) >= 3:
            date_str = (r[0] or "").strip()
            sales_type = (r[1] or "").strip().upper()
            sale_amt = r[2]
            if date_str and sales_type == "OEE":
                sale_records.append(
                    {"date": date_str, "sale amount": sale_amt}
                )

        # ---- Right block for Rejection Trend: Date (K), Rej Amt (L)
        if len(r) >= 12:
            rej_date_str = (r[10] or "").strip()
            rej_amt = r[11]
            if rej_date_str and rej_amt not in (None, ""):
                rej_records.append(
                    {"date": rej_date_str, "rej amt": rej_amt}
                )

    if sale_records:
        sale_df = pd.DataFrame(sale_records)
    if rej_records:
        rej_df = pd.DataFrame(rej_records)

# Fallbacks if Sales Report parsing fails
if sale_df is None or sale_df.empty:
    sale_df = pd.DataFrame(
        {"date": df[date_col], "sale amount": df[today_col]}
    )

if rej_df is None or rej_df.empty:
    rej_df = pd.DataFrame(
        {"date": df[date_col], "rej amt": df[rej_day_col]}
    )

# ---- Clean/convert for charts ----
sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
sale_df["sale amount"] = pd.to_numeric(
    sale_df["sale amount"].astype(str).str.replace(",", ""), errors="coerce"
).fillna(0)
sale_df = sale_df.dropna(subset=["date"]).sort_values("date")

rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
rej_df["rej amt"] = pd.to_numeric(
    rej_df["rej amt"].astype(str).str.replace(",", ""), errors="coerce"
).fillna(0)
rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# ================== PLOTLY FIGURES (same style as VS code) ==================
fig_sale = go.Figure()
fig_sale.add_trace(
    go.Bar(x=sale_df["date"], y=sale_df["sale amount"], marker_color=BLUE)
)
fig_sale.update_layout(
    title="",
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    width=None,
    autosize=True,
    xaxis=dict(
        showgrid=False,
        tickfont=dict(size=12),
        tickangle=-45,
        automargin=True,
    ),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
)
sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

fig_rej = go.Figure()
fig_rej.add_trace(
    go.Scatter(
        x=rej_df["date"],
        y=rej_df["rej amt"],
        mode="lines+markers",
        marker=dict(size=8, color=BUTTERFLY_ORANGE),
        line=dict(width=3, color=BUTTERFLY_ORANGE),
    )
)
fig_rej.update_layout(
    title="",
    margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=135,
    width=None,
    autosize=True,
    xaxis=dict(
        showgrid=False,
        tickfont=dict(size=12),
        tickangle=-45,
        automargin=True,
    ),
    yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
)
rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# ================== BACKGROUND IMAGE ==================
bg_b64 = load_image_base64(IMAGE_PATH)
bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# ================== HTML TEMPLATE (EXACT VS-CODE UI) ==================
center_html = f"""
<div class="center-content" style='width:100%;height:100%;'>
  <div class="value-green">{achieved_pct_val}%</div>
  <div class="title-green">Achieved %</div>
</div>
"""

top_date = latest[date_col].strftime("%d-%b-%Y")
top_today_sale = format_inr(today_sale)
top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}%"
left_rej_pct = f"{rej_pct: .1f}%"
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

# import streamlit as st
# import pandas as pd
# import plotly.graph_objects as go
# import base64
# from pathlib import Path
# import gspread
# from google.oauth2.service_account import Credentials

# st.set_page_config(page_title="Factory Dashboard (Word Art Glass)", layout="wide")

# IMAGE_PATH = "winter.jpg"
# SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
# DASHBOARD_SHEET = "Dashboard"
# SALES_REPORT_SHEET = "Sales Report"
# TARGET_SALE = 19_92_00_000

# def load_image_base64(path: str) -> str:
#     try:
#         data = Path(path).read_bytes()
#         return base64.b64encode(data).decode()
#     except Exception:
#         return ""

# def format_inr(n):
#     try:
#         x = str(int(float(str(n).replace(",", ""))))
#     except Exception:
#         return str(n)
#     if len(x) <= 3:
#         return x
#     last3 = x[-3:]
#     rest = x[:-3]
#     rest = ''.join([rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1])
#     return rest + last3

# def ensure_pct(x):
#     try:
#         v = float(str(x).replace("%", "").replace(",", ""))
#     except Exception:
#         return 0.0
#     return v * 100 if v <= 5 else v

# try:
#     creds_info = st.secrets["gcp_service_account"]
#     SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
#     creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
#     client = gspread.authorize(creds)
# except Exception as e:
#     st.error(f"Google auth failed: {e}")
#     st.stop()
# try:
#     sh = client.open_by_key(SPREADSHEET_ID)
# except Exception as e:
#     st.error(f"Cannot open spreadsheet: {e}")
#     st.stop()

# try:
#     dash_ws = sh.worksheet(DASHBOARD_SHEET)
#     rows = dash_ws.get_values("A1:H")
# except Exception as e:
#     st.error(f"Cannot read Dashboard sheet: {e}")
#     st.stop()

# if not rows or len(rows) < 2:
#     st.error("Dashboard sheet has no data (A1:H).")
#     st.stop()

# header = rows[0]
# data_rows = [r for r in rows[1:] if any(r)]
# dash_data = [dict(zip(header, r)) for r in data_rows]
# df = pd.DataFrame(dash_data)
# df.columns = df.columns.str.strip().str.lower()
# expected_cols = [
#     "date",
#     "today's sale",
#     "oee %",
#     "plan vs actual %",
#     "rejection amount (daybefore)",
#     "rejection %",
#     "rejection amount (cumulative)",
#     "total sales (cumulative)",
# ]
# if list(df.columns[:8]) != expected_cols:
#     pass

# date_col = df.columns[0]
# df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
# for c in df.columns[1:]:
#     df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
# df = df.dropna(subset=[date_col])
# if df.empty:
#     st.error("No valid dates in Dashboard sheet.")
#     st.stop()
# df = df.sort_values(date_col)
# latest = df.iloc[-1]
# cols = df.columns.tolist()
# (
#     date_col,
#     today_col,
#     oee_col,
#     plan_col,
#     rej_day_col,
#     rej_pct_col,
#     rej_cum_col,
#     total_cum_col,
# ) = cols[:8]

# today_sale = latest[today_col]
# raw_oee = latest[oee_col]
# oee = ensure_pct(raw_oee)
# raw_plan = latest[plan_col]
# plan_vs_actual = ensure_pct(raw_plan)
# rej_day = latest[rej_day_col]
# raw_rej_pct = latest[rej_pct_col]
# rej_pct = ensure_pct(raw_rej_pct)
# rej_cum = latest[rej_cum_col]
# cum_series = df[total_cum_col].dropna()
# total_cum = cum_series.iloc[-1] if not cum_series.empty else 0
# achieved_pct_val = round(total_cum / TARGET_SALE * 100, 2) if TARGET_SALE else 0

# BUTTERFLY_ORANGE = "#fc7d1b"
# BLUE = "#228be6"
# GREEN = "#009e4f"

# gauge = go.Figure(go.Indicator(
#     mode="gauge",
#     value=achieved_pct_val,
#     number={
#         "suffix": "%",
#         "font": {
#             "size": 44,
#             "color": GREEN,
#             "family": "Poppins",
#             "weight": "bold",
#         },
#     },
#     domain={"x": [0, 1], "y": [0, 1]},
#     gauge={
#         "shape": "angular",
#         "axis": {
#             "range": [0, 100],
#             "tickvals": [0, 25, 50, 75, 100],
#             "ticktext": ["0%", "25%", "50%", "75%", "100%"],
#         },
#         "bar": {"color": GREEN, "thickness": 0.38},
#         "bgcolor": "rgba(0,0,0,0)",
#         "steps": [
#             {"range": [0, 60], "color": "#c4eed1"},
#             {"range": [60, 85], "color": "#7ee2b7"},
#             {"range": [85, 100], "color": GREEN},
#         ],
#         "threshold": {
#             "line": {"color": "#222", "width": 5},
#             "value": achieved_pct_val,
#         },
#     },
# ))
# gauge.update_layout(
#     paper_bgcolor="rgba(0,0,0,0)",
#     plot_bgcolor="rgba(0,0,0,0)",
#     margin=dict(t=10, b=30, l=10, r=10),
#     height=170,
#     width=300,
# )
# gauge_html = gauge.to_html(include_plotlyjs="cdn", full_html=False)

# try:
#     sr_ws = sh.worksheet(SALES_REPORT_SHEET)
#     sr_rows = sr_ws.get_values()
# except Exception:
#     sr_rows = []

# sale_df = None
# rej_df = None
# if sr_rows and len(sr_rows) > 1:
#     sale_records = []
#     rej_records = []
#     for r in sr_rows[1:]:
#         if len(r) >= 3:
#             date_str = (r[0] or "").strip()
#             sales_type = (r[1] or "").strip().upper()
#             sale_amt = r[2]
#             if date_str and sales_type == "OEE":
#                 sale_records.append({"date": date_str, "sale amount": sale_amt})
#         if len(r) >= 12:
#             rej_date_str = (r[10] or "").strip()
#             rej_amt = r[11]
#             if rej_date_str and rej_amt not in (None, ""):
#                 rej_records.append({"date": rej_date_str, "rej amt": rej_amt})
#     if sale_records:
#         sale_df = pd.DataFrame(sale_records)
#     if rej_records:
#         rej_df = pd.DataFrame(rej_records)

# if sale_df is None or sale_df.empty:
#     sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
# if rej_df is None or rej_df.empty:
#     rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

# sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
# sale_df["sale amount"] = pd.to_numeric(sale_df["sale amount"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
# sale_df = sale_df.dropna(subset=["date"]).sort_values("date")
# rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
# rej_df["rej amt"] = pd.to_numeric(rej_df["rej amt"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
# rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# fig_sale = go.Figure()
# fig_sale.add_trace(go.Bar(x=sale_df["date"], y=sale_df["sale amount"], marker_color=BLUE))
# fig_sale.update_layout(
#     title="",
#     margin=dict(t=20, b=40, l=10, r=10),
#     paper_bgcolor="rgba(0,0,0,0)",
#     plot_bgcolor="rgba(0,0,0,0)",
#     height=135,
#     xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
#     yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
# )
# sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

# fig_rej = go.Figure()
# fig_rej.add_trace(
#     go.Scatter(
#         x=rej_df["date"], y=rej_df["rej amt"],
#         mode="lines+markers",
#         marker=dict(size=8, color=BUTTERFLY_ORANGE),
#         line=dict(width=3, color=BUTTERFLY_ORANGE),
#     )
# )
# fig_rej.update_layout(
#     title="",
#     margin=dict(t=20, b=40, l=10, r=10),
#     paper_bgcolor="rgba(0,0,0,0)",
#     plot_bgcolor="rgba(0,0,0,0)",
#     height=135,
#     xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
#     yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
# )
# rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# bg_b64 = load_image_base64(IMAGE_PATH)
# bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# center_html = f"""
# <div class="center-content" style='width:100%;height:100%;'>
#   <span class="wordart value-green" id="achieved" data-value="{achieved_pct_val}">0%</span>
#   <div class="title-green">Achieved %</div>
# </div>
# """

# top_date = latest[date_col].strftime("%d-%b-%Y")
# top_today_sale = format_inr(today_sale)
# top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}"
# left_rej_pct = f"{rej_pct: .1f}"
# left_rej_day = format_inr(rej_day)
# bottom_rej_cum = format_inr(rej_cum)

# html_template = f"""
# <!doctype html>
# <html>
# <head>
# <meta charset="utf-8">
# <style>
# body {{
#     margin:0;
#     padding:18px;
#     font-family: 'Poppins', sans-serif;
#     background: url("{bg_url}") center/cover no-repeat fixed;
#     color:#091128;
# }}
# .container {{
#     width:100%; min-height:99vh;
#     display: grid;
#     grid-template-columns: 1fr 1fr 1fr;
#     grid-template-rows: 130px 220px 140px;
#     gap: 18px; row-gap: 30px;
#     box-shadow: 0 6px 60px 0 rgba(40,90,140,0.09);
# }}
# .card {{
#     background: linear-gradient(150deg,rgba(255,255,255,0.65) 20%,rgba(255,255,255,0.16) 85%);
#     border-radius: 21px;
#     border: 3px solid rgba(255,255,255,0.27);
#     box-shadow: 0 12px 50px 0 rgba(50,80,120,0.20), 0 2.8px 9px rgba(0,0,0,0.09);
#     backdrop-filter: blur(16px) saturate(142%);
#     -webkit-backdrop-filter: blur(16px) saturate(142%);
#     display: flex; flex-direction:column; align-items:center; justify-content:center;
#     transition: box-shadow 0.25s;
# }}

# .wordart {{
#     font-family: 'Poppins', 'Segoe UI', Arial, sans-serif;
#     font-weight: 900;
#     font-size: 58px !important;
#     letter-spacing: 0.04em;
#     line-height: 1.1;
#     background: linear-gradient(90deg,
#       #fffbe8 0%, #fad784 22%, #ffa940 49%, #fc7d1b 73%, #fcad9b 88%, #fffbe8 100%);
#     color: #fffbe8;
#     background-clip: text !important;
#     -webkit-background-clip: text !important;
#     -webkit-text-fill-color: transparent;
#     filter: drop-shadow(0 4px 18px rgba(252,125,27,0.25));
#     display: inline-block;
#     /* Presentation 3D-style stroke and neon outline */
#     text-shadow:
#       0 1px 0 #ffd,
#       0 2px 1px #d9ae7b,
#       0 4px 12px #ffa940,
#       0 0.5px 18px #fc7d1b,
#       0 2px 24px #fff6d9,
#       0 10px 54px #fc7d1b,
#       -0.5px -0.5px 0 #fffbe8;
#     border-radius: 11px;
#     padding: 4px 17px;
#     /* inner-glass/shine effect */
#     position: relative;
#     z-index: 2;
#     overflow: visible;
#     animation: wordpop 1.7s cubic-bezier(.5,.4,.3,1.2) both,
#                shimmer 3.6s linear infinite;
# }}
# .value-blue {{
#     font-size:52px!important;
#     background: linear-gradient(100deg, #dbf1ff 5%, #54ade6 44%, #228be6 86%, #95f7ff 100%);
#     color: #dbf1ff;
#     background-clip:text !important;
#     -webkit-background-clip:text !important;
#     -webkit-text-fill-color: transparent;
#     filter: drop-shadow(0 3.5px 14px #228be6);
#     text-shadow:
#       0 1px 0 #fffbe8,
#       0 2px 1px #444,
#       0 8px 24px #228be6,
#       0 0.5px 18px #66f,
#       0 2px 24px #d6f4ff,
#       0 10px 34px #4ddbf7;
#     border-radius: 8px;
#     padding: 4px 13px;
#     z-index:2;
#     animation: wordpop 1.4s cubic-bezier(.44,.59,.52,1.19) both, shimmer 3.4s linear infinite;
# }}
# .value-orange {{
#     font-size:52px!important;
#     background: linear-gradient(98deg, #fffbe8 9%, #fad784 37%, #ffa940 63%, #fc7d1b 85%, #ffe4b9 100%);
#     color: #fc7d1b;
#     background-clip: text !important;
#     -webkit-background-clip:text !important;
#     -webkit-text-fill-color:transparent;
#     filter: drop-shadow(0 4px 18px #fc7d1b);
#     text-shadow:
#       0 1px 0 #ffd,
#       0 2px 1px #d9ae7b,
#       0 8px 24px #ffa940,
#       0 0.5px 24px #ffa940,
#       0 2px 14px #fff6d9,
#       0 14px 42px #fcb147,
#       -0.75px -0.75px 0 #fffbe8;
#     border-radius:8px;
#     padding: 4px 13px;
#     z-index:2;
#     animation: wordpop 1.1s cubic-bezier(.44,.59,.52,1.19) both, shimmer 3.15s linear infinite;
# }}
# .value-green {{
#     font-size:54px!important;
#     background: linear-gradient(93deg, #e8fff2 8%, #51efbe 52%, #009e4f 89%, #3fffa1 99%);
#     color:#3fffa1;
#     background-clip:text !important;
#     -webkit-background-clip:text !important;
#     -webkit-text-fill-color: transparent;
#     filter: drop-shadow(0 3px 10px #45fa87);
#     text-shadow: 0 2.5px 44px #009e4f, 0 0.7px 2.5px #fff, 0 2px 15px #50efbe, 0 0.5px 6px #a0ffd2;
#     border-radius:7px;
#     padding:3px 12px;
#     z-index:2;
#     animation: wordpop 1.4s cubic-bezier(.44,.59,.52,1.19) both, shimmer 3.4s linear infinite;
# }}

# @keyframes wordpop {{
#   0%{{opacity:0;transform:translateY(14px) scale(.93);}}
#   55%{{opacity:1;transform:translateY(-3px)scale(1.17);}}
#   85%{{transform:translateY(1px)scale(1.04);}}
#   100%{{opacity:1;transform:translateY(0)scale(1);}}
# }}
# @keyframes shimmer {{
#     0%{{background-position:-200% center;}}
#     100%{{background-position:200% center;}}
# }}
# .title-green {{
#     color:{GREEN}!important;
#     font-size:28px!important;
#     font-weight:700!important;
#     margin-top:4px!important;
#     text-shadow:0 2px 8px #50f9a3;
# }}
# .title-black {{
#     color:#191921!important;
#     font-size:17px!important;
#     font-weight:800!important;
#     margin-top:7px!important;
#     width:100%;text-align:center!important;
# }}
# .chart-title-black {{
#     color: #003!important;
#     font-size:16px!important;
#     font-weight:700!important;
#     margin-bottom:3px!important;
#     width:100%; text-align:left!important; padding-left:7px;}
# @media (max-width:1100px){.container{{grid-template-columns:1fr;grid-template-rows:auto;}}}
# </style>
# </head>
# <body>
# <div class="container">
#     <div class="card top-card">
#         <div class="center-content">
#             <span class="wordart value-orange" id="dt" data-value="0">{top_date}</span>
#             <div class="title-black">Date</div>
#         </div>
#     </div>
#     <div class="card top-card">
#         <div class="center-content">
#             <span class="wordart value-blue" id="todaysale" data-value="{top_today_sale.replace(',','')}">0</span>
#             <div class="title-black">Today's Sale</div>
#         </div>
#     </div>
#     <div class="card top-card">
#         <div class="center-content">
#             <span class="wordart value-orange" id="oee" data-value="{top_oee}">0%</span>
#             <div class="title-black">OEE %</div>
#         </div>
#     </div>
#     <div class="card">
#         <div class="center-content">
#             <span class="wordart value-orange" id="rejpct" data-value="{left_rej_pct.replace('%','').strip()}">0%</span>
#             <div class="title-black">Rejection %</div>
#         </div>
#     </div>
#     <div class="card">
#         {center_html}
#     </div>
#     <div class="card">
#         {gauge_html}
#     </div>
#     <div class="card bottom-card">
#         <div class="center-content">
#             <span class="wordart value-orange" id="rejcum" data-value="{bottom_rej_cum.replace(',','')}">0</span>
#             <div class="title-black">Rejection (Cumulative)</div>
#         </div>
#     </div>
#     <div class="card bottom-card">
#         <div class="chart-title-black">Sale Trend</div>
#         <div id="sale_chart_container" class="chart-container">{sale_html}</div>
#     </div>
#     <div class="card bottom-card">
#         <div class="chart-title-black">Rejection Trend</div>
#         <div id="rej_chart_container" class="chart-container">{rej_html}</div>
#     </div>
# </div>
# <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
# <script>
# // Animated word art count-up for all metrics
# function animateValue(element, start, end, duration, suffix="", prefix="") {
#     if(isNaN(Number(end))) element.textContent = prefix + end + suffix;
#     else {
#     const range = end - start;
#     let startTime = null;
#     function step(now) {
#         if (!startTime) startTime = now;
#         let progress = Math.min((now - startTime) / duration, 1);
#         let value = Math.floor(start + range * progress);
#         if (element.id=="oee" || element.id=="rejpct" || element.id=="achieved")
#             element.textContent = prefix + value.toLocaleString('en-IN') + suffix;
#         else if(element.id=="todaysale" || element.id=="rejcum")
#             element.textContent = prefix + value.toLocaleString('en-IN');
#         if (progress < 1) requestAnimationFrame(step);
#         else {
#           if (element.id=="oee" || element.id=="rejpct" || element.id=="achieved")
#             element.textContent = prefix + Number(end).toLocaleString('en-IN',{minimumFractionDigits:2, maximumFractionDigits:2}) + suffix;
#           else
#             element.textContent = prefix + Number(end).toLocaleString('en-IN');
#         }
#     }
#     requestAnimationFrame(step);
#     }
# }
# window.addEventListener("DOMContentLoaded", function() {
#     let ts = document.getElementById('todaysale');
#     if (ts) animateValue(ts, 0, parseInt(ts.dataset.value.replace(/,/g,"")), 1100, "", "₹ ");
#     let oee = document.getElementById('oee');
#     if (oee) animateValue(oee, 0, parseFloat(oee.dataset.value), 1100, "%");
#     let rej = document.getElementById('rejpct');
#     if (rej) animateValue(rej, 0, parseFloat(rej.dataset.value), 1100, "%");
#     let rcum = document.getElementById('rejcum');
#     if (rcum) animateValue(rcum, 0, parseInt(rcum.dataset.value.replace(/,/g,"")), 1100, "", "₹ ");
#     let ach = document.getElementById('achieved');
#     if (ach) animateValue(ach, 0, parseFloat(ach.dataset.value), 1100, "%");
# });
# </script>
# </body>
# </html>
# """

# st.components.v1.html(html_template, height=770, scrolling=True)

# # On Fri, 21 Nov, 2025, 5:19 pm Saurabh Shinde, <ssaurabh5135@gmail.com> wrote:
# # import streamlit as st
# # import pandas as pd
# # import plotly.graph_objects as go
# # import base64
# # from pathlib import Path
# # import gspread
# # from google.oauth2.service_account import Credentials

# # st.set_page_config(page_title="Factory Dashboard (Word Art Glass)", layout="wide")

# # IMAGE_PATH = "winter.jpg"
# # SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
# # DASHBOARD_SHEET = "Dashboard"
# # SALES_REPORT_SHEET = "Sales Report"
# # TARGET_SALE = 19_92_00_000

# # def load_image_base64(path: str) -> str:
# #     try:
# #         data = Path(path).read_bytes()
# #         return base64.b64encode(data).decode()
# #     except Exception:
# #         return ""

# # def format_inr(n):
# #     try:
# #         x = str(int(float(str(n).replace(",", ""))))
# #     except Exception:
# #         return str(n)
# #     if len(x) <= 3:
# #         return x
# #     last3 = x[-3:]
# #     rest = x[:-3]
# #     rest = ''.join([rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1])
# #     return rest + last3

# # def ensure_pct(x):
# #     try:
# #         v = float(str(x).replace("%", "").replace(",", ""))
# #     except Exception:
# #         return 0.0
# #     return v * 100 if v <= 5 else v

# # try:
# #     creds_info = st.secrets["gcp_service_account"]
# #     SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
# #     creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
# #     client = gspread.authorize(creds)
# # except Exception as e:
# #     st.error(f"Google auth failed: {e}")
# #     st.stop()
# # try:
# #     sh = client.open_by_key(SPREADSHEET_ID)
# # except Exception as e:
# #     st.error(f"Cannot open spreadsheet: {e}")
# #     st.stop()

# # try:
# #     dash_ws = sh.worksheet(DASHBOARD_SHEET)
# #     rows = dash_ws.get_values("A1:H")
# # except Exception as e:
# #     st.error(f"Cannot read Dashboard sheet: {e}")
# #     st.stop()

# # if not rows or len(rows) < 2:
# #     st.error("Dashboard sheet has no data (A1:H).")
# #     st.stop()

# # header = rows[0]
# # data_rows = [r for r in rows[1:] if any(r)]
# # dash_data = [dict(zip(header, r)) for r in data_rows]
# # df = pd.DataFrame(dash_data)
# # df.columns = df.columns.str.strip().str.lower()
# # expected_cols = [
# #     "date",
# #     "today's sale",
# #     "oee %",
# #     "plan vs actual %",
# #     "rejection amount (daybefore)",
# #     "rejection %",
# #     "rejection amount (cumulative)",
# #     "total sales (cumulative)",
# # ]
# # if list(df.columns[:8]) != expected_cols:
# #     pass

# # date_col = df.columns[0]
# # df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
# # for c in df.columns[1:]:
# #     df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
# # df = df.dropna(subset=[date_col])
# # if df.empty:
# #     st.error("No valid dates in Dashboard sheet.")
# #     st.stop()
# # df = df.sort_values(date_col)
# # latest = df.iloc[-1]
# # cols = df.columns.tolist()
# # (
# #     date_col,
# #     today_col,
# #     oee_col,
# #     plan_col,
# #     rej_day_col,
# #     rej_pct_col,
# #     rej_cum_col,
# #     total_cum_col,
# # ) = cols[:8]

# # today_sale = latest[today_col]
# # raw_oee = latest[oee_col]
# # oee = ensure_pct(raw_oee)
# # raw_plan = latest[plan_col]
# # plan_vs_actual = ensure_pct(raw_plan)
# # rej_day = latest[rej_day_col]
# # raw_rej_pct = latest[rej_pct_col]
# # rej_pct = ensure_pct(raw_rej_pct)
# # rej_cum = latest[rej_cum_col]
# # cum_series = df[total_cum_col].dropna()
# # total_cum = cum_series.iloc[-1] if not cum_series.empty else 0
# # achieved_pct_val = round(total_cum / TARGET_SALE * 100, 2) if TARGET_SALE else 0

# # BUTTERFLY_ORANGE = "#fc7d1b"
# # BLUE = "#228be6"
# # GREEN = "#009e4f"

# # gauge = go.Figure(go.Indicator(
# #     mode="gauge",
# #     value=achieved_pct_val,
# #     number={
# #         "suffix": "%",
# #         "font": {
# #             "size": 44,
# #             "color": GREEN,
# #             "family": "Poppins",
# #             "weight": "bold",
# #         },
# #     },
# #     domain={"x": [0, 1], "y": [0, 1]},
# #     gauge={
# #         "shape": "angular",
# #         "axis": {
# #             "range": [0, 100],
# #             "tickvals": [0, 25, 50, 75, 100],
# #             "ticktext": ["0%", "25%", "50%", "75%", "100%"],
# #         },
# #         "bar": {"color": GREEN, "thickness": 0.38},
# #         "bgcolor": "rgba(0,0,0,0)",
# #         "steps": [
# #             {"range": [0, 60], "color": "#c4eed1"},
# #             {"range": [60, 85], "color": "#7ee2b7"},
# #             {"range": [85, 100], "color": GREEN},
# #         ],
# #         "threshold": {
# #             "line": {"color": "#222", "width": 5},
# #             "value": achieved_pct_val,
# #         },
# #     },
# # ))
# # gauge.update_layout(
# #     paper_bgcolor="rgba(0,0,0,0)",
# #     plot_bgcolor="rgba(0,0,0,0)",
# #     margin=dict(t=10, b=30, l=10, r=10),
# #     height=170,
# #     width=300,
# # )
# # gauge_html = gauge.to_html(include_plotlyjs="cdn", full_html=False)

# # try:
# #     sr_ws = sh.worksheet(SALES_REPORT_SHEET)
# #     sr_rows = sr_ws.get_values()
# # except Exception:
# #     sr_rows = []

# # sale_df = None
# # rej_df = None
# # if sr_rows and len(sr_rows) > 1:
# #     sale_records = []
# #     rej_records = []
# #     for r in sr_rows[1:]:
# #         if len(r) >= 3:
# #             date_str = (r[0] or "").strip()
# #             sales_type = (r[1] or "").strip().upper()
# #             sale_amt = r[2]
# #             if date_str and sales_type == "OEE":
# #                 sale_records.append({"date": date_str, "sale amount": sale_amt})
# #         if len(r) >= 12:
# #             rej_date_str = (r[10] or "").strip()
# #             rej_amt = r[11]
# #             if rej_date_str and rej_amt not in (None, ""):
# #                 rej_records.append({"date": rej_date_str, "rej amt": rej_amt})
# #     if sale_records:
# #         sale_df = pd.DataFrame(sale_records)
# #     if rej_records:
# #         rej_df = pd.DataFrame(rej_records)

# # if sale_df is None or sale_df.empty:
# #     sale_df = pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
# # if rej_df is None or rej_df.empty:
# #     rej_df = pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

# # sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
# # sale_df["sale amount"] = pd.to_numeric(sale_df["sale amount"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
# # sale_df = sale_df.dropna(subset=["date"]).sort_values("date")
# # rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
# # rej_df["rej amt"] = pd.to_numeric(rej_df["rej amt"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
# # rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# # fig_sale = go.Figure()
# # fig_sale.add_trace(go.Bar(x=sale_df["date"], y=sale_df["sale amount"], marker_color=BLUE))
# # fig_sale.update_layout(
# #     title="",
# #     margin=dict(t=20, b=40, l=10, r=10),
# #     paper_bgcolor="rgba(0,0,0,0)",
# #     plot_bgcolor="rgba(0,0,0,0)",
# #     height=135,
# #     xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
# #     yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
# # )
# # sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

# # fig_rej = go.Figure()
# # fig_rej.add_trace(
# #     go.Scatter(
# #         x=rej_df["date"], y=rej_df["rej amt"],
# #         mode="lines+markers",
# #         marker=dict(size=8, color=BUTTERFLY_ORANGE),
# #         line=dict(width=3, color=BUTTERFLY_ORANGE),
# #     )
# # )
# # fig_rej.update_layout(
# #     title="",
# #     margin=dict(t=20, b=40, l=10, r=10),
# #     paper_bgcolor="rgba(0,0,0,0)",
# #     plot_bgcolor="rgba(0,0,0,0)",
# #     height=135,
# #     xaxis=dict(showgrid=False, tickfont=dict(size=12), tickangle=-45, automargin=True),
# #     yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
# # )
# # rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# # bg_b64 = load_image_base64(IMAGE_PATH)
# # bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# # center_html = f"""
# # <div class="center-content" style='width:100%;height:100%;'>
# #   <span class="wordart value-green" id="achieved" data-value="{achieved_pct_val}">0%</span>
# #   <div class="title-green">Achieved %</div>
# # </div>
# # """

# # top_date = latest[date_col].strftime("%d-%b-%Y")
# # top_today_sale = format_inr(today_sale)
# # top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}"
# # left_rej_pct = f"{rej_pct: .1f}"
# # left_rej_day = format_inr(rej_day)
# # bottom_rej_cum = format_inr(rej_cum)

# # html_template = f"""
# # <!doctype html>
# # <html>
# # <head>
# # <meta charset="utf-8">
# # <style>
# # body {{
# #     margin:0;
# #     padding:18px;
# #     font-family: 'Poppins', sans-serif;
# #     background: url("{bg_url}") center/cover no-repeat fixed;
# #     color:#091128;
# # }}
# # .container {{
# #     width:100%; min-height:99vh;
# #     display: grid;
# #     grid-template-columns: 1fr 1fr 1fr;
# #     grid-template-rows: 130px 220px 140px;
# #     gap: 18px; row-gap: 30px;
# #     box-shadow: 0 6px 60px 0 rgba(40,90,140,0.09);
# # }}
# # .card {{
# #     background: linear-gradient(150deg,rgba(255,255,255,0.65) 20%,rgba(255,255,255,0.16) 85%);
# #     border-radius: 21px;
# #     border: 3px solid rgba(255,255,255,0.27);
# #     box-shadow: 0 12px 50px 0 rgba(50,80,120,0.20), 0 2.8px 9px rgba(0,0,0,0.09);
# #     backdrop-filter: blur(16px) saturate(142%);
# #     -webkit-backdrop-filter: blur(16px) saturate(142%);
# #     display: flex; flex-direction:column; align-items:center; justify-content:center;
# #     transition: box-shadow 0.25s;
# # }}

# # .wordart {{
# #     font-family: 'Poppins', 'Segoe UI', Arial, sans-serif;
# #     font-weight: 900;
# #     font-size: 58px !important;
# #     letter-spacing: 0.04em;
# #     line-height: 1.1;
# #     background: linear-gradient(90deg,
# #       #fffbe8 0%, #fad784 22%, #ffa940 49%, #fc7d1b 73%, #fcad9b 88%, #fffbe8 100%);
# #     color: #fffbe8;
# #     background-clip: text !important;
# #     -webkit-background-clip: text !important;
# #     -webkit-text-fill-color: transparent;
# #     filter: drop-shadow(0 4px 18px rgba(252,125,27,0.25));
# #     display: inline-block;
# #     /* Presentation 3D-style stroke and neon outline */
# #     text-shadow:
# #       0 1px 0 #ffd,
# #       0 2px 1px #d9ae7b,
# #       0 4px 12px #ffa940,
# #       0 0.5px 18px #fc7d1b,
# #       0 2px 24px #fff6d9,
# #       0 10px 54px #fc7d1b,
# #       -0.5px -0.5px 0 #fffbe8;
# #     border-radius: 11px;
# #     padding: 4px 17px;
# #     /* inner-glass/shine effect */
# #     position: relative;
# #     z-index: 2;
# #     overflow: visible;
# #     animation: wordpop 1.7s cubic-bezier(.5,.4,.3,1.2) both,
# #                shimmer 3.6s linear infinite;
# # }}
# # .value-blue {{
# #     font-size:52px!important;
# #     background: linear-gradient(100deg, #dbf1ff 5%, #54ade6 44%, #228be6 86%, #95f7ff 100%);
# #     color: #dbf1ff;
# #     background-clip:text !important;
# #     -webkit-background-clip:text !important;
# #     -webkit-text-fill-color: transparent;
# #     filter: drop-shadow(0 3.5px 14px #228be6);
# #     text-shadow:
# #       0 1px 0 #fffbe8,
# #       0 2px 1px #444,
# #       0 8px 24px #228be6,
# #       0 0.5px 18px #66f,
# #       0 2px 24px #d6f4ff,
# #       0 10px 34px #4ddbf7;
# #     border-radius: 8px;
# #     padding: 4px 13px;
# #     z-index:2;
# #     animation: wordpop 1.4s cubic-bezier(.44,.59,.52,1.19) both, shimmer 3.4s linear infinite;
# # }}
# # .value-orange {{
# #     font-size:52px!important;
# #     background: linear-gradient(98deg, #fffbe8 9%, #fad784 37%, #ffa940 63%, #fc7d1b 85%, #ffe4b9 100%);
# #     color: #fc7d1b;
# #     background-clip: text !important;
# #     -webkit-background-clip:text !important;
# #     -webkit-text-fill-color:transparent;
# #     filter: drop-shadow(0 4px 18px #fc7d1b);
# #     text-shadow:
# #       0 1px 0 #ffd,
# #       0 2px 1px #d9ae7b,
# #       0 8px 24px #ffa940,
# #       0 0.5px 24px #ffa940,
# #       0 2px 14px #fff6d9,
# #       0 14px 42px #fcb147,
# #       -0.75px -0.75px 0 #fffbe8;
# #     border-radius:8px;
# #     padding: 4px 13px;
# #     z-index:2;
# #     animation: wordpop 1.1s cubic-bezier(.44,.59,.52,1.19) both, shimmer 3.15s linear infinite;
# # }}
# # .value-green {{
# #     font-size:54px!important;
# #     background: linear-gradient(93deg, #e8fff2 8%, #51efbe 52%, #009e4f 89%, #3fffa1 99%);
# #     color:#3fffa1;
# #     background-clip:text !important;
# #     -webkit-background-clip:text !important;
# #     -webkit-text-fill-color: transparent;
# #     filter: drop-shadow(0 3px 10px #45fa87);
# #     text-shadow: 0 2.5px 44px #009e4f, 0 0.7px 2.5px #fff, 0 2px 15px #50efbe, 0 0.5px 6px #a0ffd2;
# #     border-radius:7px;
# #     padding:3px 12px;
# #     z-index:2;
# #     animation: wordpop 1.4s cubic-bezier(.44,.59,.52,1.19) both, shimmer 3.4s linear infinite;
# # }}

# # @keyframes wordpop {{
# #   0%{{opacity:0;transform:translateY(14px) scale(.93);}}
# #   55%{{opacity:1;transform:translateY(-3px)scale(1.17);}}
# #   85%{{transform:translateY(1px)scale(1.04);}}
# #   100%{{opacity:1;transform:translateY(0)scale(1);}}
# # }}
# # @keyframes shimmer {{
# #     0%{{background-position:-200% center;}}
# #     100%{{background-position:200% center;}}
# # }}
# # .title-green {{
# #     color:{GREEN}!important;
# #     font-size:28px!important;
# #     font-weight:700!important;
# #     margin-top:4px!important;
# #     text-shadow:0 2px 8px #50f9a3;
# # }}
# # .title-black {{
# #     color:#191921!important;
# #     font-size:17px!important;
# #     font-weight:800!important;
# #     margin-top:7px!important;
# #     width:100%;text-align:center!important;
# # }}
# # .chart-title-black {{
# #     color: #003!important;
# #     font-size:16px!important;
# #     font-weight:700!important;
# #     margin-bottom:3px!important;
# #     width:100%; text-align:left!important; padding-left:7px;}
# # @media (max-width:1100px){.container{{grid-template-columns:1fr;grid-template-rows:auto;}}}
# # </style>
# # </head>
# # <body>
# # <div class="container">
# #     <div class="card top-card">
# #         <div class="center-content">
# #             <span class="wordart value-orange" id="dt" data-value="0">{top_date}</span>
# #             <div class="title-black">Date</div>
# #         </div>
# #     </div>
# #     <div class="card top-card">
# #         <div class="center-content">
# #             <span class="wordart value-blue" id="todaysale" data-value="{top_today_sale.replace(',','')}">0</span>
# #             <div class="title-black">Today's Sale</div>
# #         </div>
# #     </div>
# #     <div class="card top-card">
# #         <div class="center-content">
# #             <span class="wordart value-orange" id="oee" data-value="{top_oee}">0%</span>
# #             <div class="title-black">OEE %</div>
# #         </div>
# #     </div>
# #     <div class="card">
# #         <div class="center-content">
# #             <span class="wordart value-orange" id="rejpct" data-value="{left_rej_pct.replace('%','').strip()}">0%</span>
# #             <div class="title-black">Rejection %</div>
# #         </div>
# #     </div>
# #     <div class="card">
# #         {center_html}
# #     </div>
# #     <div class="card">
# #         {gauge_html}
# #     </div>
# #     <div class="card bottom-card">
# #         <div class="center-content">
# #             <span class="wordart value-orange" id="rejcum" data-value="{bottom_rej_cum.replace(',','')}">0</span>
# #             <div class="title-black">Rejection (Cumulative)</div>
# #         </div>
# #     </div>
# #     <div class="card bottom-card">
# #         <div class="chart-title-black">Sale Trend</div>
# #         <div id="sale_chart_container" class="chart-container">{sale_html}</div>
# #     </div>
# #     <div class="card bottom-card">
# #         <div class="chart-title-black">Rejection Trend</div>
# #         <div id="rej_chart_container" class="chart-container">{rej_html}</div>
# #     </div>
# # </div>
# # <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
# # <script>
# # // Animated word art count-up for all metrics
# # function animateValue(element, start, end, duration, suffix="", prefix="") {
# #     if(isNaN(Number(end))) element.textContent = prefix + end + suffix;
# #     else {
# #     const range = end - start;
# #     let startTime = null;
# #     function step(now) {
# #         if (!startTime) startTime = now;
# #         let progress = Math.min((now - startTime) / duration, 1);
# #         let value = Math.floor(start + range * progress);
# #         if (element.id=="oee" || element.id=="rejpct" || element.id=="achieved")
# #             element.textContent = prefix + value.toLocaleString('en-IN') + suffix;
# #         else if(element.id=="todaysale" || element.id=="rejcum")
# #             element.textContent = prefix + value.toLocaleString('en-IN');
# #         if (progress < 1) requestAnimationFrame(step);
# #         else {
# #           if (element.id=="oee" || element.id=="rejpct" || element.id=="achieved")
# #             element.textContent = prefix + Number(end).toLocaleString('en-IN',{minimumFractionDigits:2, maximumFractionDigits:2}) + suffix;
# #           else
# #             element.textContent = prefix + Number(end).toLocaleString('en-IN');
# #         }
# #     }
# #     requestAnimationFrame(step);
# #     }
# # }
# # window.addEventListener("DOMContentLoaded", function() {
# #     let ts = document.getElementById('todaysale');
# #     if (ts) animateValue(ts, 0, parseInt(ts.dataset.value.replace(/,/g,"")), 1100, "", "₹ ");
# #     let oee = document.getElementById('oee');
# #     if (oee) animateValue(oee, 0, parseFloat(oee.dataset.value), 1100, "%");
# #     let rej = document.getElementById('rejpct');
# #     if (rej) animateValue(rej, 0, parseFloat(rej.dataset.value), 1100, "%");
# #     let rcum = document.getElementById('rejcum');
# #     if (rcum) animateValue(rcum, 0, parseInt(rcum.dataset.value.replace(/,/g,"")), 1100, "", "₹ ");
# #     let ach = document.getElementById('achieved');
# #     if (ach) animateValue(ach, 0, parseFloat(ach.dataset.value), 1100, "%");
# # });
# # </script>
# # </body>
# # </html>
# # """

# # st.components.v1.html(html_template, height=770, scrolling=True)
# # # import streamlit as st
# # # import pandas as pd
# # # import plotly.graph_objects as go
# # # import base64
# # # from pathlib import Path
# # # import gspread
# # # from google.oauth2.service_account import Credentials

# # # # ------------------ PAGE CONFIG ------------------
# # # st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

# # # # ------------------ CONFIG ------------------
# # # IMAGE_PATH = "winter.jpg" # image stored in the repo next to this file
# # # SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
# # # DASHBOARD_SHEET = "Dashboard"
# # # SALES_REPORT_SHEET = "Sales Report"
# # # TARGET_SALE = 19_92_00_000

# # # # ------------------ HELPERS ------------------
# # # def load_image_base64(path: str) -> str:
# # #     try:
# # #         data = Path(path).read_bytes()
# # #         return base64.b64encode(data).decode()
# # #     except Exception:
# # #         return ""

# # # def format_inr(n):
# # #     try:
# # #         x = str(int(float(str(n).replace(",", ""))))
# # #     except Exception:
# # #         return str(n)
# # #     if len(x) <= 3:
# # #         return x
# # #     last3 = x[-3:]
# # #     rest = x[:-3]
# # #     rest = ''.join(
# # #         [rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1]
# # #     )
# # #     return rest + last3

# # # def ensure_pct(x):
# # #     try:
# # #         v = float(str(x).replace("%", "").replace(",", ""))
# # #     except Exception:
# # #         return 0.0
# # #     return v * 100 if v <= 5 else v

# # # # ------------------ GOOGLE SHEETS AUTH ------------------
# # # try:
# # #     creds_info = st.secrets["gcp_service_account"]
# # #     SCOPES = [
# # #         "https://www.googleapis.com/auth/spreadsheets",
# # #         "https://www.googleapis.com/auth/drive",
# # #     ]
# # #     creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
# # #     client = gspread.authorize(creds)
# # # except Exception as e:
# # #     st.error(f"Google auth failed: {e}")
# # #     st.stop()

# # # # ------------------ OPEN SPREADSHEET ------------------
# # # try:
# # #     sh = client.open_by_key(SPREADSHEET_ID)
# # # except Exception as e:
# # #     st.error(f"Cannot open spreadsheet: {e}")
# # #     st.stop()

# # # # ================== LOAD DASHBOARD SHEET (A1:H) ==================
# # # try:
# # #     dash_ws = sh.worksheet(DASHBOARD_SHEET)
# # #     rows = dash_ws.get_values("A1:H")
# # # except Exception as e:
# # #     st.error(f"Cannot read Dashboard sheet: {e}")
# # #     st.stop()

# # # if not rows or len(rows) < 2:
# # #     st.error("Dashboard sheet has no data (A1:H).")
# # #     st.stop()

# # # header = rows[0]
# # # data_rows = [r for r in rows[1:] if any(r)]
# # # dash_data = [dict(zip(header, r)) for r in data_rows]
# # # df = pd.DataFrame(dash_data)
# # # df.columns = df.columns.str.strip().str.lower()
# # # expected_cols = [
# # #     "date",
# # #     "today's sale",
# # #     "oee %",
# # #     "plan vs actual %",
# # #     "rejection amount (daybefore)",
# # #     "rejection %",
# # #     "rejection amount (cumulative)",
# # #     "total sales (cumulative)",
# # # ]
# # # if list(df.columns[:8]) != expected_cols:
# # #     pass

# # # date_col = df.columns[0]
# # # df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
# # # for c in df.columns[1:]:
# # #     df[c] = pd.to_numeric(
# # #         df[c].astype(str).str.replace(",", ""), errors="coerce"
# # #     )

# # # df = df.dropna(subset=[date_col])
# # # if df.empty:
# # #     st.error("No valid dates in Dashboard sheet.")
# # #     st.stop()

# # # df = df.sort_values(date_col)
# # # latest = df.iloc[-1]
# # # cols = df.columns.tolist()
# # # (
# # #     date_col,
# # #     today_col,
# # #     oee_col,
# # #     plan_col,
# # #     rej_day_col,
# # #     rej_pct_col,
# # #     rej_cum_col,
# # #     total_cum_col,
# # # ) = cols[:8]

# # # today_sale = latest[today_col]
# # # raw_oee = latest[oee_col]
# # # oee = ensure_pct(raw_oee)
# # # raw_plan = latest[plan_col]
# # # plan_vs_actual = ensure_pct(raw_plan)
# # # rej_day = latest[rej_day_col]
# # # raw_rej_pct = latest[rej_pct_col]
# # # rej_pct = ensure_pct(raw_rej_pct)
# # # rej_cum = latest[rej_cum_col]
# # # cum_series = df[total_cum_col].dropna()
# # # total_cum = cum_series.iloc[-1] if not cum_series.empty else 0
# # # achieved_pct = (total_cum / TARGET_SALE * 100) if TARGET_SALE else 0
# # # achieved_pct_val = round(achieved_pct, 2)

# # # # ------------------ COLORS ------------------
# # # BUTTERFLY_ORANGE = "#fc7d1b"
# # # BLUE = "#228be6"
# # # GREEN = "#009e4f"

# # # # ================== KPI GAUGE ==================
# # # gauge = go.Figure(
# # #     go.Indicator(
# # #         mode="gauge",
# # #         value=achieved_pct_val,
# # #         number={
# # #             "suffix": "%",
# # #             "font": {
# # #                 "size": 44,
# # #                 "color": GREEN,
# # #                 "family": "Poppins",
# # #                 "weight": "bold",
# # #             },
# # #         },
# # #         domain={"x": [0, 1], "y": [0, 1]},
# # #         gauge={
# # #             "shape": "angular",
# # #             "axis": {
# # #                 "range": [0, 100],
# # #                 "tickvals": [0, 25, 50, 75, 100],
# # #                 "ticktext": ["0%", "25%", "50%", "75%", "100%"],
# # #             },
# # #             "bar": {"color": GREEN, "thickness": 0.38},
# # #             "bgcolor": "rgba(0,0,0,0)",
# # #             "steps": [
# # #                 {"range": [0, 60], "color": "#c4eed1"},
# # #                 {"range": [60, 85], "color": "#7ee2b7"},
# # #                 {"range": [85, 100], "color": GREEN},
# # #             ],
# # #             "threshold": {
# # #                 "line": {"color": "#111", "width": 5},
# # #                 "value": achieved_pct_val,
# # #             },
# # #         },
# # #     )
# # # )
# # # gauge.update_layout(
# # #     paper_bgcolor="rgba(0,0,0,0)",
# # #     plot_bgcolor="rgba(0,0,0,0)",
# # #     margin=dict(t=10, b=30, l=10, r=10),
# # #     height=170,
# # #     width=300,
# # # )
# # # gauge_html = gauge.to_html(include_plotlyjs="cdn", full_html=False)

# # # # ================== SALES REPORT → TRENDS ==================
# # # try:
# # #     sr_ws = sh.worksheet(SALES_REPORT_SHEET)
# # #     sr_rows = sr_ws.get_values()
# # # except Exception:
# # #     sr_rows = []

# # # sale_df = None
# # # rej_df = None

# # # if sr_rows and len(sr_rows) > 1:
# # #     sale_records = []
# # #     rej_records = []
# # #     for r in sr_rows[1:]:
# # #         if len(r) >= 3:
# # #             date_str = (r[0] or "").strip()
# # #             sales_type = (r[1] or "").strip().upper()
# # #             sale_amt = r[2]
# # #             if date_str and sales_type == "OEE":
# # #                 sale_records.append(
# # #                     {"date": date_str, "sale amount": sale_amt}
# # #                 )
# # #         if len(r) >= 12:
# # #             rej_date_str = (r[10] or "").strip()
# # #             rej_amt = r[11]
# # #             if rej_date_str and rej_amt not in (None, ""):
# # #                 rej_records.append(
# # #                     {"date": rej_date_str, "rej amt": rej_amt}
# # #                 )
# # #     if sale_records:
# # #         sale_df = pd.DataFrame(sale_records)
# # #     if rej_records:
# # #         rej_df = pd.DataFrame(rej_records)

# # # if sale_df is None or sale_df.empty:
# # #     sale_df = pd.DataFrame(
# # #         {"date": df[date_col], "sale amount": df[today_col]}
# # #     )
# # # if rej_df is None or rej_df.empty:
# # #     rej_df = pd.DataFrame(
# # #         {"date": df[date_col], "rej amt": df[rej_day_col]}
# # #     )
# # # sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
# # # sale_df["sale amount"] = pd.to_numeric(
# # #     sale_df["sale amount"].astype(str).str.replace(",", ""), errors="coerce"
# # # ).fillna(0)
# # # sale_df = sale_df.dropna(subset=["date"]).sort_values("date")
# # # rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
# # # rej_df["rej amt"] = pd.to_numeric(
# # #     rej_df["rej amt"].astype(str).str.replace(",", ""), errors="coerce"
# # # ).fillna(0)
# # # rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# # # fig_sale = go.Figure()
# # # fig_sale.add_trace(
# # #     go.Bar(x=sale_df["date"], y=sale_df["sale amount"], marker_color=BLUE)
# # # )
# # # fig_sale.update_layout(
# # #     title="",
# # #     margin=dict(t=20, b=40, l=10, r=10),
# # #     paper_bgcolor="rgba(0,0,0,0)",
# # #     plot_bgcolor="rgba(0,0,0,0)",
# # #     height=135,
# # #     width=None,
# # #     autosize=True,
# # #     xaxis=dict(
# # #         showgrid=False,
# # #         tickfont=dict(size=12),
# # #         tickangle=-45,
# # #         automargin=True,
# # #     ),
# # #     yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
# # # )
# # # sale_html = fig_sale.to_html(include_plotlyjs=False, full_html=False)

# # # fig_rej = go.Figure()
# # # fig_rej.add_trace(
# # #     go.Scatter(
# # #         x=rej_df["date"],
# # #         y=rej_df["rej amt"],
# # #         mode="lines+markers",
# # #         marker=dict(size=8, color=BUTTERFLY_ORANGE),
# # #         line=dict(width=3, color=BUTTERFLY_ORANGE),
# # #     )
# # # )
# # # fig_rej.update_layout(
# # #     title="",
# # #     margin=dict(t=20, b=40, l=10, r=10),
# # #     paper_bgcolor="rgba(0,0,0,0)",
# # #     plot_bgcolor="rgba(0,0,0,0)",
# # #     height=135,
# # #     width=None,
# # #     autosize=True,
# # #     xaxis=dict(
# # #         showgrid=False,
# # #         tickfont=dict(size=12),
# # #         tickangle=-45,
# # #         automargin=True,
# # #     ),
# # #     yaxis=dict(showgrid=False, tickfont=dict(size=12), automargin=True),
# # # )
# # # rej_html = fig_rej.to_html(include_plotlyjs=False, full_html=False)

# # # bg_b64 = load_image_base64(IMAGE_PATH)
# # # bg_url = f"data:image/png;base64,{bg_b64}" if bg_b64 else ""

# # # # ================== HTML TEMPLATE (GLASS+ANIMATION) ==================
# # # center_html = f"""
# # # <div class="center-content" style='width:100%;height:100%;'>
# # #   <div class="value-green" id="achieved" data-value="{achieved_pct_val}">0%</div>
# # #   <div class="title-green">Achieved %</div>
# # # </div>
# # # """

# # # top_date = latest[date_col].strftime("%d-%b-%Y")
# # # top_today_sale = format_inr(today_sale)
# # # top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}"
# # # left_rej_pct = f"{rej_pct: .1f}"
# # # left_rej_day = format_inr(rej_day)
# # # bottom_rej_cum = format_inr(rej_cum)

# # # html_template = f"""
# # # <!doctype html>
# # # <html>
# # # <head>
# # # <meta charset="utf-8">
# # # <style>
# # :root {{
# #     --card-radius: 19px;
# #     --accent: {BUTTERFLY_ORANGE};
# #     --orange: {BUTTERFLY_ORANGE};
# #     --green: {GREEN};
# #     --blue: {BLUE};
# # }}
# # html,body,#root{{height:100%;}}
# # body {{
# #     margin:0;
# #     padding:18px;
# #     font-family: 'Poppins', sans-serif;
# #     background: url("{bg_url}") center/cover no-repeat fixed;
# #     color:#071024;
# # }}
# # .center-content {{
# #     display: flex;
# #     flex-direction: column;
# #     justify-content: center;
# #     align-items: center;
# #     height: 100%;
# #     text-align: center;
# # }}
# # .container {{
# #     width: 100%;
# #     min-height: 98vh;
# #     display: grid;
# #     grid-template-columns: 1fr 1fr 1fr;
# #     grid-template-rows: 130px 220px 140px;
# #     gap: 18px;
# #     row-gap: 30px;
# #     box-shadow: 0 3px 48px 0 rgba(90,110,140,0.09);
# # }}
# # .card {{
# #     background: linear-gradient(151deg,rgba(255,255,255,0.42) 5%,rgba(255,255,255,0.09) 78%);
# #     border-radius: var(--card-radius);
# #     border: 1.5px solid rgba(255,255,255,0.17);
# #     box-shadow: 0 8px 34px 0 rgba(55,65,81,0.13), 0 1.5px 4px rgba(0,0,0,0.05);
# #     backdrop-filter: blur(11px) saturate(125%);
# #     -webkit-backdrop-filter: blur(11px) saturate(125%);
# #     display: flex;
# #     flex-direction: column;
# #     align-items: center;
# #     justify-content: center;
# #     transition: box-shadow 0.4s;
# # }}
# # .card .center-content {{
# #     width: 100%;
# #     align-items: center;
# #     justify-content: center;
# # }}
# # .top-card {{
# #     height: 100%;
# #     width: 100%;
# #     padding: 20px 0 0 0;
# # }}
# # .bottom-card {{
# #     height: 100%;
# #     width: 100%;
# #     padding: 10px 0 0 0;
# # }}
# # .chart-container {{
# #     width: 100%;
# #     height: 110px;
# #     max-width: 100%;
# #     overflow: hidden;
# #     box-sizing: border-box;
# #     margin: 0;
# #     padding: 0;
# #     display: block;
# # }}
# # .value-orange,
# # .value-blue,
# # .value-green {{
# #     font-size: 46px !important;
# #     font-weight: 900 !important;
# #     letter-spacing: 0.04em;
# #     background-clip: text !important;
# #     -webkit-background-clip: text !important;
# #     color: transparent !important;
# #     -webkit-text-fill-color: transparent;
# #     text-shadow:
# #       0 1px 16px rgba(255,255,255,0.3),
# #       0 0px 2px rgba(0,0,0,0.09),
# #       0 4px 24px rgba(0,0,0,0.16);
# #     transition: all 0.5s cubic-bezier(0.32, 0.72, 0.36, 0.96) !important;
# #     animation: value-pop 1.2s cubic-bezier(0.17, 0.85, 0.45, 1.04) both;
# #     filter: drop-shadow(0 2px 9px rgba(0,0,0,0.06));
# #     mix-blend-mode: lighten;  
# # }}
# # .value-orange {{
# #     background-image: linear-gradient(95deg,#ffecb8 0%,#fca471 47%,#fc7d1b 78%,#fcb147 100%);
# # }}
# # .value-blue {{
# #     background-image: linear-gradient(87deg,#b9e6ff 0%,#6dcefa 40%,#228be6 82%,#d3f7ff 100%);
# # }}
# # .value-green {{
# #     background-image: linear-gradient(93deg,#c5ffdf 4%,#51efbe 51%,#009e4f 86%);
# #     font-size: 56px !important;
# # }}
# # @keyframes value-pop {{
# #   0% {{ opacity:0; transform: translateY(16px) scale(0.98);}}
# #   68% {{ opacity:1; transform: translateY(-3px) scale(1.06);}}
# #   80% {{ opacity:1; transform: translateY(2px) scale(1.01);}}
# #   100% {{ opacity:1; transform: translateY(0px) scale(1);}}
# # }}
# # @keyframes shimmer {{
# #     0% {{ background-position: -300% center; }}
# #     100% {{ background-position: 300% center; }}
# # }}
# # .value-orange, .value-blue, .value-green {{
# #     background-size: 200% 100%;
# #     animation:
# #       value-pop 1.18s cubic-bezier(0.14, 0.78, 0.29, 1.02) both,
# #       shimmer 3.9s linear infinite;
# # }}
# # .title-green {{
# #     color: {GREEN} !important;
# #     font-size: 26px !important;
# #     font-weight: 700 !important;
# #     margin-top: 4px !important;
# # }}
# # .title-black {{
# #     color: #000 !important;
# #     font-size: 15px !important;
# #     font-weight: 700 !important;
# #     margin-top: 6px !important;
# #     width: 100%;
# #     text-align: center !important;
# # }}
# # .chart-title-black {{
# #     color: #000 !important;
# #     font-size: 15px !important;
# #     font-weight: 700 !important;
# #     margin-bottom: 2px !important;
# #     width: 100%;
# #     text-align: left !important;
# #     padding-left: 6px;
# # }}
# # @media (max-width: 1100px) {{
# #     .container {{ grid-template-columns: 1fr; grid-template-rows: auto; }}
# # }}
# # </style>
# # </head>
# # <body>
# # <div class="container">

# #     <!-- Top Row -->
# #     <div class="card top-card">
# #         <div class="center-content">
# #             <div class="value-orange" id="dt" data-value="0">{top_date}</div>
# #             <div class="title-black">Date</div>
# #         </div>
# #     </div>
# #     <div class="card top-card">
# #         <div class="center-content">
# #             <div class="value-blue" id="todaysale" data-value="{top_today_sale.replace(',','')}">0</div>
# #             <div class="title-black">Today's Sale</div>
# #         </div>
# #     </div>
# #     <div class="card top-card">
# #         <div class="center-content">
# #             <div class="value-orange" id="oee" data-value="{top_oee}">0%</div>
# #             <div class="title-black">OEE %</div>
# #         </div>
# #     </div>

# #     <!-- Center/Middle Row -->
# #     <div class="card">
# #         <div class="center-content">
# #             <div class="value-orange" id="rejpct" data-value="{left_rej_pct.replace('%','').strip()}">0%</div>
# #             <div class="title-black">Rejection %</div>
# #         </div>
# #     </div>
# #     <div class="card">
# #         {center_html}
# #     </div>
# #     <div class="card">
# #         {gauge_html}
# #     </div>

# #     <!-- Bottom Row -->
# #     <div class="card bottom-card">
# #         <div class="center-content">
# #             <div class="value-orange" id="rejcum" data-value="{bottom_rej_cum.replace(',','')}">0</div>
# #             <div class="title-black">Rejection (Cumulative)</div>
# #         </div>
# #     </div>
# #     <div class="card bottom-card">
# #         <div class="chart-title-black">Sale Trend</div>
# #         <div id="sale_chart_container" class="chart-container">{sale_html}</div>
# #     </div>
# #     <div class="card bottom-card">
# #         <div class="chart-title-black">Rejection Trend</div>
# #         <div id="rej_chart_container" class="chart-container">{rej_html}</div>
# #     </div>

# # </div>
# # <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
# # <script>
# # function animateValue(element, start, end, duration, suffix="", prefix="") {{
# #     if(isNaN(Number(end))) element.textContent = prefix + end + suffix;
# #     else {{
# #     const range = end - start;
# #     let startTime = null;
# #     function step(now) {{
# #         if (!startTime) startTime = now;
# #         let progress = Math.min((now - startTime) / duration, 1);
# #         let value = Math.floor(start + range * progress);
# #         if (element.id==="oee" || element.id==="rejpct" || element.id==="achieved")
# #             element.textContent = prefix + value.toLocaleString('en-IN') + suffix;
# #         else if(element.id==="todaysale" || element.id==="rejcum")
# #             element.textContent = prefix + value.toLocaleString('en-IN');
# #         if (progress < 1) requestAnimationFrame(step);
# #         else {{
# #           if (element.id==="oee" || element.id==="rejpct" || element.id==="achieved")
# #             element.textContent = prefix + Number(end).toLocaleString('en-IN',{{minimumFractionDigits:2, maximumFractionDigits:2}}) + suffix;
# #           else
# #             element.textContent = prefix + Number(end).toLocaleString('en-IN');
# #         }}
# #     }}
# #     requestAnimationFrame(step);
# #     }}
# # }}
# # window.addEventListener("DOMContentLoaded", function() {{
# #     // Today's Sale
# #     let ts = document.getElementById('todaysale');
# #     if (ts) animateValue(ts, 0, parseInt(ts.dataset.value.replace(/,/g,"")), 1100, "", "₹ ");
# #     // OEE %
# #     let oee = document.getElementById('oee');
# #     if (oee) animateValue(oee, 0, parseFloat(oee.dataset.value), 1100, "%");
# #     // Rejection %
# #     let rej = document.getElementById('rejpct');
# #     if (rej) animateValue(rej, 0, parseFloat(rej.dataset.value), 1100, "%");
# #     // Cumulative Rejection
# #     let rcum = document.getElementById('rejcum');
# #     if (rcum) animateValue(rcum, 0, parseInt(rcum.dataset.value.replace(/,/g,"")), 1100, "", "₹ ");
# #     // Achieved %
# #     let ach = document.getElementById('achieved');
# #     if (ach) animateValue(ach, 0, parseFloat(ach.dataset.value), 1100, "%");
# # }});
# # </script>
# # </body>
# # </html>
# # """

# # st.components.v1.html(html_template, height=770, scrolling=True)












