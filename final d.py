import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.colors as pc
import base64
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

IMAGE_PATH = "black.jpg"
SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
DASHBOARD_SHEET = "Dashboard"
SALES_REPORT_SHEET = "Sales Report"

def load_image_base64(path: str) -> str:
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except Exception:
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
    try:
        v = float(str(x).replace("%", "").replace(",", ""))
    except Exception:
        return 0.0
    return v * 100 if v <= 5 else v

def find_col(df, target):
    norm_target = (
        target.lower()
        .replace(" ", "")
        .replace("%", "")
        .replace("(", "")
        .replace(")", "")
    )
    for c in df.columns:
        norm_c = (
            str(c).lower()
            .replace(" ", "")
            .replace("%", "")
            .replace("(", "")
            .replace(")", "")
        )
        if norm_c == norm_target:
            return c
    return None

# Google Sheets Auth
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

try:
    sh = client.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Cannot open spreadsheet: {e}")
    st.stop()

try:
    dash_ws = sh.worksheet(DASHBOARD_SHEET)
    rows = dash_ws.get_values()
except Exception as e:
    st.error(f"Cannot read Dashboard sheet: {e}")
    st.stop()

if not rows or len(rows) < 2:
    st.error("Dashboard sheet has no data.")
    st.stop()

header = rows[0]
data_rows = [r for r in rows[1:] if any(r)]
dash_data = [dict(zip(header, r)) for r in data_rows]
df = pd.DataFrame(dash_data)
df.columns = df.columns.astype(str)

date_col = find_col(df, "date")
today_col = find_col(df, "today's sale") or find_col(df, "todays sale")
oee_col = find_col(df, "oee %") or find_col(df, "oee")
plan_col = find_col(df, "plan vs actual %")
rej_day_col = find_col(df, "rejection amount (daybefore)") or find_col(df, "rejection amount daybefore")
rej_pct_col = find_col(df, "rejection %") or find_col(df, "rejection")
rej_cum_col = find_col(df, "rejection amount (cumulative)") or find_col(df, "rejection amount cumulative")
total_cum_col = find_col(df, "total sales (cumulative)") or find_col(df, "total sales cumulative")

if not all([date_col, today_col, oee_col, plan_col, rej_day_col, rej_pct_col, rej_cum_col, total_cum_col]):
    st.error("One or more required dashboard columns are missing in Google Sheet.")
    st.stop()

copq_col = find_col(df, "copq")
copq_cum_col = find_col(df, "copq cumulative") or find_col(df, "copqcumulative")

df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
for c in df.columns:
    if c != date_col:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
df = df.dropna(subset=[date_col]).sort_values(date_col)

try:
    sr_ws = sh.worksheet(SALES_REPORT_SHEET)
    sr_rows = sr_ws.get_values()
except Exception:
    sr_rows = []

sale_records = []
rej_records = []

if sr_rows and len(sr_rows) > 1:
    for r in sr_rows[1:]:
        if len(r) >= 3:
            date_str = (r[0] or "").strip()
            sales_type = (r[1] or "").strip().upper()
            sale_amt = r[2]
            if date_str and sales_type == "OEE":
                sale_records.append({"date": date_str, "sale amount": sale_amt})
        if len(r) >= 12:
            rej_date_str = (r[10] or "").strip()
            rej_amt = r[11]
            if rej_date_str and rej_amt not in (None, ""):
                rej_records.append({"date": rej_date_str, "rej amt": rej_amt})

sale_df = pd.DataFrame(sale_records) if sale_records else pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
rej_df = pd.DataFrame(rej_records) if rej_records else pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
sale_df["sale amount"] = pd.to_numeric(sale_df["sale amount"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
sale_df = sale_df.dropna(subset=["date"]).sort_values("date")

rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
rej_df["rej amt"] = pd.to_numeric(rej_df["rej amt"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# Load monthly TARGET_SALE from Dashboard sheet A10:B13 (extended for Jan)
month_targets_vals = dash_ws.get_values('A10:B13')
month_targets = {
    row[0].strip(): float(row[1].replace(",", "")) if len(row) > 1 and row[1].strip() else 1
    for row in month_targets_vals[1:] if len(row) >= 2
}

month_options = sorted(month_targets.keys(), key=lambda m: pd.to_datetime(m, format='%b').month)

# Main dashboard rendering
def render_dashboard(selected_month):
    selected_month_num = pd.to_datetime(selected_month, format='%b').month

    df_filtered = df[df[date_col].dt.month == selected_month_num]
    sale_filtered = sale_df[sale_df["date"].dt.month == selected_month_num]
    rej_filtered = rej_df[rej_df["date"].dt.month == selected_month_num]

    if not df_filtered.empty:
        latest = df_filtered.iloc[-1]
        today_sale = latest[today_col]
        oee = ensure_pct(latest[oee_col])
        rej_day_amount = latest[rej_day_col]
        rej_pct = ensure_pct(latest[rej_pct_col])
        rej_cum_series = df_filtered[rej_cum_col].dropna()
        rej_cum_val = rej_cum_series.iloc[-1] if not rej_cum_series.empty else 0
        total_cum_series = df_filtered[total_cum_col].dropna()
        total_cum_val = total_cum_series.iloc[-1] if not total_cum_series.empty else 0
        copq_display = format_inr(latest[copq_col]) if copq_col and pd.notna(latest[copq_col]) else "..."
        copq_cum_display = format_inr(latest[copq_cum_col]) if copq_cum_col and pd.notna(latest[copq_cum_col]) else "..."
    else:
        today_sale = 0
        oee = 0
        rej_day_amount = 0
        rej_pct = 0
        rej_cum_val = 0
        total_cum_val = 0
        copq_display = "..."
        copq_cum_display = "..."

    total_sales_filtered = sale_filtered["sale amount"].sum() if not sale_filtered.empty else 0
    target_sale = month_targets.get(selected_month, 1)
    if target_sale <= 0:
        target_sale = 1
    achieved_pct_val = round(total_sales_filtered / target_sale * 100, 2)

    # Sale Trend Graph Color handling - avoid ZeroDivisionError by min color count 2
    num_colors = max(len(sale_filtered), 2)
    bar_gradients = pc.n_colors(
        "rgb(34,139,230)",
        "rgb(79,223,253)",
        num_colors,
        colortype="rgb",
    )
    fig_sale = go.Figure()
    fig_sale.add_trace(
        go.Bar(
            x=sale_filtered["date"],
            y=sale_filtered["sale amount"] / 100000.0,
            marker_color=bar_gradients,
            marker_line_width=0,
            opacity=0.97,
            hovertemplate="Date: %{x|%d-%b}<br>Sale: %{y:.2f} Lakh<extra></extra>",
        )
    )
    fig_sale.update_layout(
        margin=dict(t=5, b=30, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=105,
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=10),
            tickangle=-45,
            automargin=True,
            tickformat="%d",
            dtick="D1",
        ),
        yaxis=dict(
            showgrid=False,
            tickfont=dict(size=10),
            automargin=True,
            title="Lakh",
        ),
    )

    rej_lakh = rej_filtered["rej amt"] / 1000.0
    fig_rej = go.Figure()
    fig_rej.add_trace(
        go.Scatter(
            x=rej_filtered["date"],
            y=rej_lakh,
            mode="lines+markers",
            marker=dict(size=8, color="#fc7d1b", line=dict(width=1.5, color="#fff")),
            line=dict(width=5, color="#fc7d1b", shape="spline"),
            hoverinfo="x+y",
            opacity=1,
            hovertemplate="Date: %{x|%d-%b}<br>Rejection: %{y:.2f} K<extra></extra>",
        )
    )
    fig_rej.add_trace(
        go.Scatter(
            x=rej_filtered["date"],
            y=rej_lakh,
            mode="lines",
            line=dict(width=15, color="rgba(252,125,27,0.13)", shape="spline"),
            hoverinfo="skip",
            opacity=1,
        )
    )
    fig_rej.update_layout(
        margin=dict(t=5, b=30, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=105,
        showlegend=False,
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=10),
            tickangle=-45,
            automargin=True,
            tickformat="%d",
            dtick="D1",
        ),
        yaxis=dict(
            showgrid=False,
            tickfont=dict(size=10),
            automargin=True,
            title="K",
        ),
    )

    sale_html = fig_sale.to_html(include_plotlyjs="cdn", full_html=False)
    rej_html = fig_rej.to_html(include_plotlyjs="cdn", full_html=False)

    BUTTERFLY_ORANGE = "#fc7d1b"
    GREEN = "#009e4f"

    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=achieved_pct_val,
            number={
                "suffix": "%",
                "font": {
                    "size": 36,
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
                "bar": {"color": GREEN, "thickness": 0.35},
                "bgcolor": "rgba(0,0,0,0)",
                "steps": [
                    {"range": [0, 60], "color": "#c4eed1"},
                    {"range": [60, 85], "color": "#7ee2b7"},
                    {"range": [85, 100], "color": GREEN},
                ],
                "threshold": {
                    "line": {"color": "#111", "width": 4},
                    "value": achieved_pct_val,
                },
            },
        )
    )
    gauge.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=5, b=5, l=5, r=5),
        height=130,
    )
    gauge_html = gauge.to_html(include_plotlyjs="cdn", full_html=False)

    bg_b64 = load_image_base64(IMAGE_PATH)
    top_today_sale = format_inr(today_sale)
    top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}%"
    left_rej_amt = format_inr(rej_day_amount)
    left_rej_pct = f"{rej_pct:.1f}%"
    bottom_rej_cum = format_inr(rej_cum_val)
    total_cum_disp = format_inr(total_cum_val)
    inventory_val = dash_ws.acell("K2").value
    inventory_disp = format_inr(inventory_val) if inventory_val else "0"

    # Render dashboard html
    st.markdown(
        f"""
    <style>
    body, .stApp {{
        /* background: url("data:image/jpeg;base64,{bg_b64}") no-repeat center center fixed !important; */
        background-size: cover !important;
        background-position: center center !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
    }}
    .block-container {{
        padding: 0 !important;
        margin: 0 !important;
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )

    html_template = f"""
    <!doctype html>
    <html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@400;600;700;900&display=swap" rel="stylesheet"><style>
    :root {{
        --blue1: #8ad1ff;
        --blue2: #4ca0ff;
        --blue3: #0d6efd;
        --orange1: #ffd699;
        --orange2: #ff9334;
        --orange3: #ff6a00;
        --green1: #a6ffd9;
        --green2: #00d97e;
    }}
    body {{
        margin: 0;
        padding: 0;
        font-family: "Fredoka", sans-serif;
        background: none !important;
    }}
    .container {{
        box-sizing: border-box;
        width: 100%;
        height: 100vh;
        padding: 60px 60px 0 60px !important;
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        grid-template-rows: 130px 130px 140px 140px;
        gap: 24px;
        max-width: 1700px;
        max-height: 900px;
        margin: auto;
    }}
    .card {{
        position: relative;
        border-radius: 20px;
        padding: 0;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        backdrop-filter: blur(12px) saturate(180%);
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.15);
        box-shadow: 0 0 15px rgba(255,255,255,0.28), 0 10px 30px rgba(0,0,0,0.5), inset 0 0 20px rgba(255,255,255,0.12);
        overflow: hidden;
    }}
    .value-blue {{
        font-size: 42px !important;
        font-weight: 900;
        background: linear-gradient(180deg, var(--blue1), var(--blue2), var(--blue3));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .value-orange {{
        font-size: 42px !important;
        font-weight: 900;
        background: linear-gradient(180deg, var(--orange1), var(--orange2), var(--orange3));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .value-green {{
        font-size: 42px !important;
        font-weight: 900;
        background: linear-gradient(180deg, var(--green1), var(--green2));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .title-black {{
        color: #5c5c63 !important;
        font-size: 17px;
        font-weight: 800;
        margin-top: 6px;
        text-align: center;
    }}
    .chart-title-black {{
        position: absolute;
        top: 8px;
        left: 12px;
        color: #fff !important;
        font-size: 15px;
        font-weight: 700;
        z-index: 10;
    }}
    .chart-container {{
        width: 100%;
        height: 100%;
        display: block;
        padding:25px 5px 5px 5px;
        box-sizing: border-box;
    }}
    .snow-bg {{
        position: absolute;
        left: 0;
        top: 0;
        width: 100%;
        height: 100%;
        opacity: 0.5;
        pointer-events: none;
    }}
    .center-content {{
        display: flex;
        flex-direction: column;
        align-items: center;
        width: 100%;
        z-index: 5;
    }}
    .gauge-wrapper {{
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
    }}
    </style></head><body><div class="container"><!-- Row 1 -->
    <div class="card">
        <canvas class="snow-bg" id="snowsale"></canvas>
        <div class="center-content">
            <div class="value-blue">₹ {top_today_sale}</div>
            <div class="title-black">Yesterday's Sale</div>
        </div>
    </div>
    <div class="card">
        <canvas class="snow-bg" id="snowrej"></canvas>
        <div class="center-content">
            <div class="value-orange">₹ {left_rej_amt}</div>
            <div class="title-black">Rejection Amount</div>
        </div>
    </div>
    <div class="card">
        <canvas class="snow-bg" id="snowoee"></canvas>
        <div class="center-content">
            <div class="value-blue">{top_oee}</div>
            <div class="title-black">OEE %</div>
        </div>
    </div>
    <!-- Row 2 -->
    <div class="card">
        <canvas class="snow-bg" id="snowcumsale"></canvas>
        <div class="center-content">
            <div class="value-blue">₹ {total_cum_disp}</div>
            <div class="title-black">Sale Cumulative</div>
        </div>
    </div>
    <div class="card">
        <canvas class="snow-bg" id="snowach"></canvas>
        <div class="center-content">
            <div class="value-orange">{left_rej_pct}</div>
            <div class="title-black">Rejection %</div>
        </div>
    </div>
    <div class="card">
        <canvas class="snow-bg" id="snowcopq"></canvas>
        <div class="center-content">
            <div class="value-blue">₹ {copq_display}</div>
            <div class="title-black">COPQ Last Day</div>
        </div>
    </div>
    <!-- Row 3 -->
    <div class="card">
        <canvas class="snow-bg" id="snowsalechart"></canvas>
        <div class="chart-title-black">Sale Trend</div>
        <div class="chart-container">{sale_html}</div>
    </div>
    <div class="card">
        <canvas class="snow-bg" id="snowrejchart"></canvas>
        <div class="chart-title-black">Rejection Trend</div>
        <div class="chart-container">{rej_html}</div>
    </div>
    <div class="card">
        <canvas class="snow-bg" id="snowcopqcum"></canvas>
        <div class="center-content">
            <div class="value-blue">₹ {copq_cum_display}</div>
            <div class="title-black">COPQ Cumulative</div>
        </div>
    </div>
    <!-- Row 4 -->
    <div class="card">
        <canvas class="snow-bg" id="snowspeed"></canvas>
        <div class="gauge-wrapper">{gauge_html}</div>
    </div>
    <div class="card">
        <canvas class="snow-bg" id="snowrejcum"></canvas>
        <div class="center-content">
            <div class="value-orange">₹ {bottom_rej_cum}</div>
            <div class="title-black">Rejection Cumulative</div>
        </div>
    </div>
    <div class="card">
        <canvas class="snow-bg" id="snowinventory"></canvas>
        <div class="center-content">
            <div class="value-blue">₹ {inventory_disp}</div>
            <div class="title-black">Inventory Value</div>
        </div>
    </div></body></html>
    """
    st.components.v1.html(html_template, height=900, scrolling=True)

# Bottom month selector only:
selected_month = st.selectbox("Select Month to View Data for", month_options, index=len(month_options)-1)

render_dashboard(selected_month)



#################################the below code is working till dec end 

# import streamlit as st
# import pandas as pd
# import plotly.graph_objects as go
# import plotly.colors as pc
# import base64
# from pathlib import Path
# import gspread
# from google.oauth2.service_account import Credentials

# st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

# IMAGE_PATH = "black.jpg"
# SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
# DASHBOARD_SHEET = "Dashboard"
# SALES_REPORT_SHEET = "Sales Report"

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
#     rest = ''.join(
#         [rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1]
#     )
#     return rest + last3

# def ensure_pct(x):
#     try:
#         v = float(str(x).replace("%", "").replace(",", ""))
#     except Exception:
#         return 0.0
#     return v * 100 if v <= 5 else v

# def find_col(df, target):
#     norm_target = (
#         target.lower()
#         .replace(" ", "")
#         .replace("%", "")
#         .replace("(", "")
#         .replace(")", "")
#     )
#     for c in df.columns:
#         norm_c = (
#             str(c).lower()
#             .replace(" ", "")
#             .replace("%", "")
#             .replace("(", "")
#             .replace(")", "")
#         )
#         if norm_c == norm_target:
#             return c
#     return None

# # Google Sheets Auth
# try:
#     creds_info = st.secrets["gcp_service_account"]
#     SCOPES = [
#         "https://www.googleapis.com/auth/spreadsheets",
#         "https://www.googleapis.com/auth/drive",
#     ]
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
#     rows = dash_ws.get_values()
# except Exception as e:
#     st.error(f"Cannot read Dashboard sheet: {e}")
#     st.stop()

# if not rows or len(rows) < 2:
#     st.error("Dashboard sheet has no data.")
#     st.stop()

# header = rows[0]
# data_rows = [r for r in rows[1:] if any(r)]
# dash_data = [dict(zip(header, r)) for r in data_rows]
# df = pd.DataFrame(dash_data)
# df.columns = df.columns.astype(str)

# date_col = find_col(df, "date")
# today_col = find_col(df, "today's sale") or find_col(df, "todays sale")
# oee_col = find_col(df, "oee %") or find_col(df, "oee")
# plan_col = find_col(df, "plan vs actual %")
# rej_day_col = find_col(df, "rejection amount (daybefore)") or find_col(df, "rejection amount daybefore")
# rej_pct_col = find_col(df, "rejection %") or find_col(df, "rejection")
# rej_cum_col = find_col(df, "rejection amount (cumulative)") or find_col(df, "rejection amount cumulative")
# total_cum_col = find_col(df, "total sales (cumulative)") or find_col(df, "total sales cumulative")

# if not all([date_col, today_col, oee_col, plan_col, rej_day_col, rej_pct_col, rej_cum_col, total_cum_col]):
#     st.error("One or more required dashboard columns are missing in Google Sheet.")
#     st.stop()

# copq_col = find_col(df, "copq")
# copq_cum_col = find_col(df, "copq cumulative") or find_col(df, "copqcumulative")

# df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
# for c in df.columns:
#     if c != date_col:
#         df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
# df = df.dropna(subset=[date_col]).sort_values(date_col)

# try:
#     sr_ws = sh.worksheet(SALES_REPORT_SHEET)
#     sr_rows = sr_ws.get_values()
# except Exception:
#     sr_rows = []

# sale_records = []
# rej_records = []

# if sr_rows and len(sr_rows) > 1:
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

# sale_df = pd.DataFrame(sale_records) if sale_records else pd.DataFrame({"date": df[date_col], "sale amount": df[today_col]})
# rej_df = pd.DataFrame(rej_records) if rej_records else pd.DataFrame({"date": df[date_col], "rej amt": df[rej_day_col]})

# sale_df["date"] = pd.to_datetime(sale_df["date"], errors="coerce")
# sale_df["sale amount"] = pd.to_numeric(sale_df["sale amount"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
# sale_df = sale_df.dropna(subset=["date"]).sort_values("date")

# rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
# rej_df["rej amt"] = pd.to_numeric(rej_df["rej amt"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
# rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# # Load monthly TARGET_SALE from Dashboard sheet A10:B12
# month_targets_vals = dash_ws.get_values('A10:B12')
# month_targets = {
#     row[0].strip(): float(row[1].replace(",", "")) if len(row) > 1 and row[1].strip() else 1
#     for row in month_targets_vals[1:] if len(row) >= 2
# }

# month_options = sorted(month_targets.keys(), key=lambda m: pd.to_datetime(m, format='%b').month)

# # Main dashboard rendering
# def render_dashboard(selected_month):
#     selected_month_num = pd.to_datetime(selected_month, format='%b').month

#     df_filtered = df[df[date_col].dt.month == selected_month_num]
#     sale_filtered = sale_df[sale_df["date"].dt.month == selected_month_num]
#     rej_filtered = rej_df[rej_df["date"].dt.month == selected_month_num]

#     if not df_filtered.empty:
#         latest = df_filtered.iloc[-1]
#         today_sale = latest[today_col]
#         oee = ensure_pct(latest[oee_col])
#         rej_day_amount = latest[rej_day_col]
#         rej_pct = ensure_pct(latest[rej_pct_col])
#         rej_cum_series = df_filtered[rej_cum_col].dropna()
#         rej_cum_val = rej_cum_series.iloc[-1] if not rej_cum_series.empty else 0
#         total_cum_series = df_filtered[total_cum_col].dropna()
#         total_cum_val = total_cum_series.iloc[-1] if not total_cum_series.empty else 0
#         copq_display = format_inr(latest[copq_col]) if copq_col and pd.notna(latest[copq_col]) else "..."
#         copq_cum_display = format_inr(latest[copq_cum_col]) if copq_cum_col and pd.notna(latest[copq_cum_col]) else "..."
#     else:
#         today_sale = 0
#         oee = 0
#         rej_day_amount = 0
#         rej_pct = 0
#         rej_cum_val = 0
#         total_cum_val = 0
#         copq_display = "..."
#         copq_cum_display = "..."

#     total_sales_filtered = sale_filtered["sale amount"].sum() if not sale_filtered.empty else 0
#     target_sale = month_targets.get(selected_month, 1)
#     if target_sale <= 0:
#         target_sale = 1
#     achieved_pct_val = round(total_sales_filtered / target_sale * 100, 2)

#     # Sale Trend Graph Color handling - avoid ZeroDivisionError by min color count 2
#     num_colors = max(len(sale_filtered), 2)
#     bar_gradients = pc.n_colors(
#         "rgb(34,139,230)",
#         "rgb(79,223,253)",
#         num_colors,
#         colortype="rgb",
#     )
#     fig_sale = go.Figure()
#     fig_sale.add_trace(
#         go.Bar(
#             x=sale_filtered["date"],
#             y=sale_filtered["sale amount"] / 100000.0,
#             marker_color=bar_gradients,
#             marker_line_width=0,
#             opacity=0.97,
#             hovertemplate="Date: %{x|%d-%b}<br>Sale: %{y:.2f} Lakh<extra></extra>",
#         )
#     )
#     fig_sale.update_layout(
#         margin=dict(t=5, b=30, l=10, r=10),
#         paper_bgcolor="rgba(0,0,0,0)",
#         plot_bgcolor="rgba(0,0,0,0)",
#         height=105,
#         xaxis=dict(
#             showgrid=False,
#             tickfont=dict(size=10),
#             tickangle=-45,
#             automargin=True,
#             tickformat="%d",
#             dtick="D1",
#         ),
#         yaxis=dict(
#             showgrid=False,
#             tickfont=dict(size=10),
#             automargin=True,
#             title="Lakh",
#         ),
#     )

#     rej_lakh = rej_filtered["rej amt"] / 1000.0
#     fig_rej = go.Figure()
#     fig_rej.add_trace(
#         go.Scatter(
#             x=rej_filtered["date"],
#             y=rej_lakh,
#             mode="lines+markers",
#             marker=dict(size=8, color="#fc7d1b", line=dict(width=1.5, color="#fff")),
#             line=dict(width=5, color="#fc7d1b", shape="spline"),
#             hoverinfo="x+y",
#             opacity=1,
#             hovertemplate="Date: %{x|%d-%b}<br>Rejection: %{y:.2f} K<extra></extra>",
#         )
#     )
#     fig_rej.add_trace(
#         go.Scatter(
#             x=rej_filtered["date"],
#             y=rej_lakh,
#             mode="lines",
#             line=dict(width=15, color="rgba(252,125,27,0.13)", shape="spline"),
#             hoverinfo="skip",
#             opacity=1,
#         )
#     )
#     fig_rej.update_layout(
#         margin=dict(t=5, b=30, l=10, r=10),
#         paper_bgcolor="rgba(0,0,0,0)",
#         plot_bgcolor="rgba(0,0,0,0)",
#         height=105,
#         showlegend=False,
#         xaxis=dict(
#             showgrid=False,
#             tickfont=dict(size=10),
#             tickangle=-45,
#             automargin=True,
#             tickformat="%d",
#             dtick="D1",
#         ),
#         yaxis=dict(
#             showgrid=False,
#             tickfont=dict(size=10),
#             automargin=True,
#             title="K",
#         ),
#     )

#     sale_html = fig_sale.to_html(include_plotlyjs="cdn", full_html=False)
#     rej_html = fig_rej.to_html(include_plotlyjs="cdn", full_html=False)

#     BUTTERFLY_ORANGE = "#fc7d1b"
#     GREEN = "#009e4f"

#     gauge = go.Figure(
#         go.Indicator(
#             mode="gauge+number",
#             value=achieved_pct_val,
#             number={
#                 "suffix": "%",
#                 "font": {
#                     "size": 36,
#                     "color": GREEN,
#                     "family": "Poppins",
#                     "weight": "bold",
#                 },
#             },
#             domain={"x": [0, 1], "y": [0, 1]},
#             gauge={
#                 "shape": "angular",
#                 "axis": {
#                     "range": [0, 100],
#                     "tickvals": [0, 25, 50, 75, 100],
#                     "ticktext": ["0%", "25%", "50%", "75%", "100%"],
#                 },
#                 "bar": {"color": GREEN, "thickness": 0.35},
#                 "bgcolor": "rgba(0,0,0,0)",
#                 "steps": [
#                     {"range": [0, 60], "color": "#c4eed1"},
#                     {"range": [60, 85], "color": "#7ee2b7"},
#                     {"range": [85, 100], "color": GREEN},
#                 ],
#                 "threshold": {
#                     "line": {"color": "#111", "width": 4},
#                     "value": achieved_pct_val,
#                 },
#             },
#         )
#     )
#     gauge.update_layout(
#         paper_bgcolor="rgba(0,0,0,0)",
#         plot_bgcolor="rgba(0,0,0,0)",
#         margin=dict(t=5, b=5, l=5, r=5),
#         height=130,
#     )
#     gauge_html = gauge.to_html(include_plotlyjs="cdn", full_html=False)

#     bg_b64 = load_image_base64(IMAGE_PATH)
#     top_today_sale = format_inr(today_sale)
#     top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}%"
#     left_rej_amt = format_inr(rej_day_amount)
#     left_rej_pct = f"{rej_pct:.1f}%"
#     bottom_rej_cum = format_inr(rej_cum_val)
#     total_cum_disp = format_inr(total_cum_val)
#     inventory_val = dash_ws.acell("K2").value
#     inventory_disp = format_inr(inventory_val) if inventory_val else "0"

#     # Render dashboard html
#     st.markdown(
#         f"""
#     <style>
#     body, .stApp {{
#         /* background: url("data:image/jpeg;base64,{bg_b64}") no-repeat center center fixed !important; */
#         background-size: cover !important;
#         background-position: center center !important;
#         margin: 0 !important;
#         padding: 0 !important;
#         overflow: hidden !important;
#     }}
#     .block-container {{
#         padding: 0 !important;
#         margin: 0 !important;
#     }}
#     </style>
#     """,
#         unsafe_allow_html=True,
#     )

#     html_template = f"""
#     <!doctype html>
#     <html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@400;600;700;900&display=swap" rel="stylesheet"><style>
#     :root {{
#         --blue1: #8ad1ff;
#         --blue2: #4ca0ff;
#         --blue3: #0d6efd;
#         --orange1: #ffd699;
#         --orange2: #ff9334;
#         --orange3: #ff6a00;
#         --green1: #a6ffd9;
#         --green2: #00d97e;
#     }}
#     body {{
#         margin: 0;
#         padding: 0;
#         font-family: "Fredoka", sans-serif;
#         background: none !important;
#     }}
#     .container {{
#         box-sizing: border-box;
#         width: 100%;
#         height: 100vh;
#         padding: 60px 60px 0 60px !important;
#         display: grid;
#         grid-template-columns: 1fr 1fr 1fr;
#         grid-template-rows: 130px 130px 140px 140px;
#         gap: 24px;
#         max-width: 1700px;
#         max-height: 900px;
#         margin: auto;
#     }}
#     .card {{
#         position: relative;
#         border-radius: 20px;
#         padding: 0;
#         display: flex;
#         flex-direction: column;
#         justify-content: center;
#         align-items: center;
#         backdrop-filter: blur(12px) saturate(180%);
#         background: rgba(255,255,255,0.08);
#         border: 1px solid rgba(255,255,255,0.15);
#         box-shadow: 0 0 15px rgba(255,255,255,0.28), 0 10px 30px rgba(0,0,0,0.5), inset 0 0 20px rgba(255,255,255,0.12);
#         overflow: hidden;
#     }}
#     .value-blue {{
#         font-size: 42px !important;
#         font-weight: 900;
#         background: linear-gradient(180deg, var(--blue1), var(--blue2), var(--blue3));
#         -webkit-background-clip: text;
#         -webkit-text-fill-color: transparent;
#     }}
#     .value-orange {{
#         font-size: 42px !important;
#         font-weight: 900;
#         background: linear-gradient(180deg, var(--orange1), var(--orange2), var(--orange3));
#         -webkit-background-clip: text;
#         -webkit-text-fill-color: transparent;
#     }}
#     .value-green {{
#         font-size: 42px !important;
#         font-weight: 900;
#         background: linear-gradient(180deg, var(--green1), var(--green2));
#         -webkit-background-clip: text;
#         -webkit-text-fill-color: transparent;
#     }}
#     .title-black {{
#         color: #5c5c63 !important;
#         font-size: 17px;
#         font-weight: 800;
#         margin-top: 6px;
#         text-align: center;
#     }}
#     .chart-title-black {{
#         position: absolute;
#         top: 8px;
#         left: 12px;
#         color: #fff !important;
#         font-size: 15px;
#         font-weight: 700;
#         z-index: 10;
#     }}
#     .chart-container {{
#         width: 100%;
#         height: 100%;
#         display: block;
#         padding:25px 5px 5px 5px;
#         box-sizing: border-box;
#     }}
#     .snow-bg {{
#         position: absolute;
#         left: 0;
#         top: 0;
#         width: 100%;
#         height: 100%;
#         opacity: 0.5;
#         pointer-events: none;
#     }}
#     .center-content {{
#         display: flex;
#         flex-direction: column;
#         align-items: center;
#         width: 100%;
#         z-index: 5;
#     }}
#     .gauge-wrapper {{
#         width: 100%;
#         height: 100%;
#         display: flex;
#         align-items: center;
#         justify-content: center;
#         overflow: hidden;
#     }}
#     </style></head><body><div class="container"><!-- Row 1 -->
#     <div class="card">
#         <canvas class="snow-bg" id="snowsale"></canvas>
#         <div class="center-content">
#             <div class="value-blue">₹ {top_today_sale}</div>
#             <div class="title-black">Yesterday's Sale</div>
#         </div>
#     </div>
#     <div class="card">
#         <canvas class="snow-bg" id="snowrej"></canvas>
#         <div class="center-content">
#             <div class="value-orange">₹ {left_rej_amt}</div>
#             <div class="title-black">Rejection Amount</div>
#         </div>
#     </div>
#     <div class="card">
#         <canvas class="snow-bg" id="snowoee"></canvas>
#         <div class="center-content">
#             <div class="value-blue">{top_oee}</div>
#             <div class="title-black">OEE %</div>
#         </div>
#     </div>
#     <!-- Row 2 -->
#     <div class="card">
#         <canvas class="snow-bg" id="snowcumsale"></canvas>
#         <div class="center-content">
#             <div class="value-blue">₹ {total_cum_disp}</div>
#             <div class="title-black">Sale Cumulative</div>
#         </div>
#     </div>
#     <div class="card">
#         <canvas class="snow-bg" id="snowach"></canvas>
#         <div class="center-content">
#             <div class="value-orange">{left_rej_pct}</div>
#             <div class="title-black">Rejection %</div>
#         </div>
#     </div>
#     <div class="card">
#         <canvas class="snow-bg" id="snowcopq"></canvas>
#         <div class="center-content">
#             <div class="value-blue">₹ {copq_display}</div>
#             <div class="title-black">COPQ Last Day</div>
#         </div>
#     </div>
#     <!-- Row 3 -->
#     <div class="card">
#         <canvas class="snow-bg" id="snowsalechart"></canvas>
#         <div class="chart-title-black">Sale Trend</div>
#         <div class="chart-container">{sale_html}</div>
#     </div>
#     <div class="card">
#         <canvas class="snow-bg" id="snowrejchart"></canvas>
#         <div class="chart-title-black">Rejection Trend</div>
#         <div class="chart-container">{rej_html}</div>
#     </div>
#     <div class="card">
#         <canvas class="snow-bg" id="snowcopqcum"></canvas>
#         <div class="center-content">
#             <div class="value-blue">₹ {copq_cum_display}</div>
#             <div class="title-black">COPQ Cumulative</div>
#         </div>
#     </div>
#     <!-- Row 4 -->
#     <div class="card">
#         <canvas class="snow-bg" id="snowspeed"></canvas>
#         <div class="gauge-wrapper">{gauge_html}</div>
#     </div>
#     <div class="card">
#         <canvas class="snow-bg" id="snowrejcum"></canvas>
#         <div class="center-content">
#             <div class="value-orange">₹ {bottom_rej_cum}</div>
#             <div class="title-black">Rejection Cumulative</div>
#         </div>
#     </div>
#     <div class="card">
#         <canvas class="snow-bg" id="snowinventory"></canvas>
#         <div class="center-content">
#             <div class="value-blue">₹ {inventory_disp}</div>
#             <div class="title-black">Inventory Value</div>
#         </div>
#     </div></body></html>
#     """
#     st.components.v1.html(html_template, height=900, scrolling=True)

# # Bottom month selector only:
# selected_month = st.selectbox("Select Month to View Data for", month_options, index=len(month_options)-1)

# render_dashboard(selected_month)

# #######################################

# import streamlit as st
# import pandas as pd
# import plotly.graph_objects as go
# import plotly.colors as pc
# import base64
# from pathlib import Path
# import gspread
# from google.oauth2.service_account import Credentials

# st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")

# IMAGE_PATH = "black.jpg"
# SPREADSHEET_ID = "168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
# DASHBOARD_SHEET = "Dashboard"
# SALES_REPORT_SHEET = "Sales Report"
# TARGET_SALE = 16_68_00_000 # yearly target in ₹

# # ---------- Helpers ----------

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
#     rest = ''.join(
#         [rest[::-1][i:i+2][::-1] + ',' for i in range(0, len(rest), 2)][::-1]
#     )
#     return rest + last3

# def ensure_pct(x):
#     try:
#         v = float(str(x).replace("%", "").replace(",", ""))
#     except Exception:
#         return 0.0
#     return v * 100 if v <= 5 else v

# def find_col(df, target):
#     """Find column ignoring case, spaces, %, brackets."""
#     norm_target = (
#         target.lower()
#         .replace(" ", "")
#         .replace("%", "")
#         .replace("(", "")
#         .replace(")", "")
#     )
#     for c in df.columns:
#         norm_c = (
#             str(c).lower()
#             .replace(" ", "")
#             .replace("%", "")
#             .replace("(", "")
#             .replace(")", "")
#         )
#         if norm_c == norm_target:
#             return c
#     return None

# # ---------- Auth & Dashboard ----------

# try:
#     creds_info = st.secrets["gcp_service_account"]
#     SCOPES = [
#         "https://www.googleapis.com/auth/spreadsheets",
#         "https://www.googleapis.com/auth/drive",
#     ]
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
#     rows = dash_ws.get_values()
# except Exception as e:
#     st.error(f"Cannot read Dashboard sheet: {e}")
#     st.stop()

# if not rows or len(rows) < 2:
#     st.error("Dashboard sheet has no data.")
#     st.stop()

# header = rows[0]
# data_rows = [r for r in rows[1:] if any(r)]
# dash_data = [dict(zip(header, r)) for r in data_rows]
# df = pd.DataFrame(dash_data)
# df.columns = df.columns.astype(str)

# date_col = find_col(df, "date")
# today_col = find_col(df, "today's sale") or find_col(df, "todays sale")
# oee_col = find_col(df, "oee %") or find_col(df, "oee")
# plan_col = find_col(df, "plan vs actual %")
# rej_day_col = find_col(df, "rejection amount (daybefore)") or find_col(df, "rejection amount daybefore")
# rej_pct_col = find_col(df, "rejection %") or find_col(df, "rejection")
# rej_cum_col = find_col(df, "rejection amount (cumulative)") or find_col(df, "rejection amount cumulative")
# total_cum_col = find_col(df, "total sales (cumulative)") or find_col(df, "total sales cumulative")

# if not all([date_col, today_col, oee_col, plan_col, rej_day_col, rej_pct_col, rej_cum_col, total_cum_col]):
#     st.error("One or more required dashboard columns are missing in Google Sheet.")
#     st.stop()

# copq_col = find_col(df, "copq")
# copq_cum_col = find_col(df, "copq cumulative") or find_col(df, "copqcumulative")

# df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
# for c in df.columns:
#     if c != date_col:
#         df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")

# df = df.dropna(subset=[date_col]).sort_values(date_col)
# latest = df.iloc[-1]

# today_sale = latest[today_col]
# raw_oee = latest[oee_col]
# oee = ensure_pct(raw_oee)
# raw_plan = latest[plan_col]
# plan_vs_actual = ensure_pct(raw_plan)

# rej_day_amount = latest[rej_day_col]
# raw_rej_pct = latest[rej_pct_col]
# rej_pct = ensure_pct(raw_rej_pct)
# rej_cum = latest[rej_cum_col]

# cum_series = df[total_cum_col].dropna()
# total_cum = cum_series.iloc[-1] if not cum_series.empty else 0
# achieved_pct_val = round(total_cum / TARGET_SALE * 100, 2) if TARGET_SALE else 0

# if copq_col and pd.notna(latest[copq_col]):
#     copq_display = format_inr(latest[copq_col])
# else:
#     copq_display = "..."

# if copq_cum_col and pd.notna(latest[copq_cum_col]):
#     copq_cum_display = format_inr(latest[copq_cum_col])
# else:
#     copq_cum_display = "..."

# BUTTERFLY_ORANGE = "#fc7d1b"
# BLUE = "#228be6"
# GREEN = "#009e4f"

# # ---------- Gauge ----------

# gauge = go.Figure(
#     go.Indicator(
#         mode="gauge+number",
#         value=achieved_pct_val,
#         number={
#             "suffix": "%",
#             "font": {
#                 "size": 36,
#                 "color": GREEN,
#                 "family": "Poppins",
#                 "weight": "bold",
#             },
#         },
#         domain={"x": [0, 1], "y": [0, 1]},
#         gauge={
#             "shape": "angular",
#             "axis": {
#                 "range": [0, 100],
#                 "tickvals": [0, 25, 50, 75, 100],
#                 "ticktext": ["0%", "25%", "50%", "75%", "100%"],
#             },
#             "bar": {"color": GREEN, "thickness": 0.35},
#             "bgcolor": "rgba(0,0,0,0)",
#             "steps": [
#                 {"range": [0, 60], "color": "#c4eed1"},
#                 {"range": [60, 85], "color": "#7ee2b7"},
#                 {"range": [85, 100], "color": GREEN},
#             ],
#             "threshold": {
#                 "line": {"color": "#111", "width": 4},
#                 "value": achieved_pct_val,
#             },
#         },
#     )
# )

# gauge.update_layout(
#     paper_bgcolor="rgba(0,0,0,0)",
#     plot_bgcolor="rgba(0,0,0,0)",
#     margin=dict(t=5, b=5, l=5, r=5),
#     height=130,
# )

# gauge_html = gauge.to_html(include_plotlyjs="cdn", full_html=False)

# # ---------- Sales Report for Trends ----------

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
# sale_df["sale amount"] = pd.to_numeric(
#     sale_df["sale amount"].astype(str).str.replace(",", ""), errors="coerce"
# ).fillna(0)
# sale_df = sale_df.dropna(subset=["date"]).sort_values("date")

# rej_df["date"] = pd.to_datetime(rej_df["date"], errors="coerce")
# rej_df["rej amt"] = pd.to_numeric(
#     rej_df["rej amt"].astype(str).str.replace(",", ""), errors="coerce"
# ).fillna(0)
# rej_df = rej_df.dropna(subset=["date"]).sort_values("date")

# # ---------- SALE TREND GRAPH (Lakhs, all days) ----------

# sale_df["sale_lakh"] = sale_df["sale amount"] / 100000.0

# bar_gradients = pc.n_colors(
#     "rgb(34,139,230)",
#     "rgb(79,223,253)",
#     len(sale_df),
#     colortype="rgb",
# )

# fig_sale = go.Figure()
# fig_sale.add_trace(
#     go.Bar(
#         x=sale_df["date"],
#         y=sale_df["sale_lakh"],
#         marker_color=bar_gradients,
#         marker_line_width=0,
#         opacity=0.97,
#         hovertemplate="Date: %{x|%d-%b}<br>Sale: %{y:.2f} Lakh<extra></extra>",
#     )
# )

# fig_sale.update_layout(
#     margin=dict(t=5, b=30, l=10, r=10),
#     paper_bgcolor="rgba(0,0,0,0)",
#     plot_bgcolor="rgba(0,0,0,0)",
#     height=105,
#     xaxis=dict(
#         showgrid=False,
#         tickfont=dict(size=10),
#         tickangle=-45,
#         automargin=True,
#         tickformat="%d", # show only day number
#         dtick="D1", # every day visible
#     ),
#     yaxis=dict(
#         showgrid=False,
#         tickfont=dict(size=10),
#         automargin=True,
#         title="Lakh",
#     ),
# )

# # ---------- REJECTION TREND GRAPH (Lakhs, all days) ----------

# rej_df["rej_lakh"] = rej_df["rej amt"] / 1000.0

# fig_rej = go.Figure()

# fig_rej.add_trace(
#     go.Scatter(
#         x=rej_df["date"],
#         y=rej_df["rej_lakh"],
#         mode="lines+markers",
#         marker=dict(
#             size=8,
#             color=BUTTERFLY_ORANGE,
#             line=dict(width=1.5, color="#fff"),
#         ),
#         line=dict(width=5, color=BUTTERFLY_ORANGE, shape="spline"),
#         hoverinfo="x+y",
#         opacity=1,
#         hovertemplate="Date: %{x|%d-%b}<br>Rejection: %{y:.2f} K<extra></extra>",
#     )
# )

# fig_rej.add_trace(
#     go.Scatter(
#         x=rej_df["date"],
#         y=rej_df["rej_lakh"],
#         mode="lines",
#         line=dict(
#             width=15,
#             color="rgba(252,125,27,0.13)",
#             shape="spline",
#         ),
#         hoverinfo="skip",
#         opacity=1,
#     )
# )

# fig_rej.update_layout(
#     margin=dict(t=5, b=30, l=10, r=10),
#     paper_bgcolor="rgba(0,0,0,0)",
#     plot_bgcolor="rgba(0,0,0,0)",
#     height=105,
#     showlegend=False,
#     xaxis=dict(
#         showgrid=False,
#         tickfont=dict(size=10),
#         tickangle=-45,
#         automargin=True,
#         tickformat="%d",
#         dtick="D1",
#     ),
#     yaxis=dict(
#         showgrid=False,
#         tickfont=dict(size=10),
#         automargin=True,
#         title="K",
#     ),
# )

# sale_html = fig_sale.to_html(include_plotlyjs="cdn", full_html=False)
# rej_html = fig_rej.to_html(include_plotlyjs="cdn", full_html=False)

# bg_b64 = load_image_base64(IMAGE_PATH)

# top_today_sale = format_inr(today_sale)
# top_oee = f"{round(oee if pd.notna(oee) else 0, 1)}%"
# left_rej_amt = format_inr(rej_day_amount)
# left_rej_pct = f"{rej_pct:.1f}%"
# bottom_rej_cum = format_inr(rej_cum)
# total_cum_disp = format_inr(total_cum)

# # ---------- Streamlit + HTML ----------

# st.markdown(
#     f"""
#     <style>
#     body, .stApp {{
#         # background: url("data:image/jpeg;base64,{bg_b64}") no-repeat center center fixed !important;
#         background-size: cover !important;
#         background-position: center center !important;
#         margin: 0 !important;
#         padding: 0 !important;
#         overflow: hidden !important;
#     }}
#     .block-container {{
#         padding: 0 !important;
#         margin: 0 !important;
#     }}
#     </style>
#     """,
#     unsafe_allow_html=True,
# )

# html_template = f"""
# <!doctype html>
# <html>
# <head>
# <meta charset="utf-8">
# <link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@400;600;700;900&display=swap" rel="stylesheet">
# <style>

# :root {{
#     --blue1: #8ad1ff;
#     --blue2: #4ca0ff;
#     --blue3: #0d6efd;
#     --orange1: #ffd699;
#     --orange2: #ff9334;
#     --orange3: #ff6a00;
#     --green1: #a6ffd9;
#     --green2: #00d97e;
# }}

# body {{
#     margin: 0;
#     padding: 0;
#     font-family: "Fredoka", sans-serif;
#     background: none !important;
# }}

# .container {{
#     box-sizing: border-box;
#     width: 100%;
#     height: 100vh;
#     padding: 60px 60px 0 60px !important;
#     display: grid;
#     grid-template-columns: 1fr 1fr 1fr;
#     grid-template-rows: 130px 130px 140px 140px;
#     gap: 24px;
#     max-width: 1700px;
#     max-height: 900px;
#     margin: auto;
# }}

# .card {{
#     position: relative;
#     border-radius: 20px;
#     padding: 0;
#     display: flex;
#     flex-direction: column;
#     justify-content: center;
#     align-items: center;
#     backdrop-filter: blur(12px) saturate(180%);
#     background: rgba(255,255,255,0.08);
#     border: 1px solid rgba(255,255,255,0.15);
#     box-shadow: 0 0 15px rgba(255,255,255,0.28), 0 10px 30px rgba(0,0,0,0.5), inset 0 0 20px rgba(255,255,255,0.12);
#     overflow: hidden;
# }}

# .value-blue {{
#     font-size: 42px !important;
#     font-weight: 900;
#     background: linear-gradient(180deg, var(--blue1), var(--blue2), var(--blue3));
#     -webkit-background-clip: text;
#     -webkit-text-fill-color: transparent;
#     # text-shadow: 0px 4px 6px rgba(0,153,255,0.6), 0px 12px 22px rgba(0,78,255,0.55), 0px 18px 40px rgba(0,40,140,0.9);
# }}

# .value-orange {{
#     font-size: 42px !important;
#     font-weight: 900;
#     background: linear-gradient(180deg, var(--orange1), var(--orange2), var(--orange3));
#     -webkit-background-clip: text;
#     -webkit-text-fill-color: transparent;
#     # text-shadow: 0px 4px 6px rgba(255,165,0,0.6), 0px 12px 22px rgba(255,90,0,0.55), 0px 18px 40px rgba(255,50,0,0.9);
# }}

# .value-green {{
#     font-size: 42px !important;
#     font-weight: 900;
#     background: linear-gradient(180deg, var(--green1), var(--green2));
#     -webkit-background-clip: text;
#     -webkit-text-fill-color: transparent;
#     # text-shadow: 0px 4px 6px rgba(0,255,180,0.6), 0px 12px 22px rgba(0,160,100,0.55), 0px 18px 40px rgba(0,120,80,0.9);
# }}

# .title-black {{
#     color: #5c5c63 !important;
#     font-size: 17px;
#     font-weight: 800;
#     margin-top: 6px;
#     text-align: center;
# }}

# .chart-title-black {{
#     position: absolute;
#     top: 8px;
#     left: 12px;
#     color: #fff !important;
#     font-size: 15px;
#     font-weight: 700;
#     z-index: 10;
# }}

# .chart-container {{
#     width: 100%;
#     height: 100%;
#     display: block;
#     padding:25px 5px 5px 5px;
#     box-sizing: border-box;
# }}

# .snow-bg {{
#     position: absolute;
#     left: 0;
#     top: 0;
#     width: 100%;
#     height: 100%;
#     opacity: 0.5;
#     pointer-events: none;
# }}

# .center-content {{
#     display: flex;
#     flex-direction: column;
#     align-items: center;
#     width: 100%;
#     z-index: 5;
# }}

# .gauge-wrapper {{
#     width: 100%;
#     height: 100%;
#     display: flex;
#     align-items: center;
#     justify-content: center;
#     overflow: hidden;
# }}

# </style>
# </head>

# <body>

# <div class="container">

#     <!-- Row 1 -->
#     <div class="card">
#         <canvas class="snow-bg" id="snowsale"></canvas>
#         <div class="center-content">
#             <div class="value-blue">₹ {top_today_sale}</div>
#             <div class="title-black">Yesterday's Sale</div>
#         </div>
#     </div>

#     <div class="card">
#         <canvas class="snow-bg" id="snowrej"></canvas>
#         <div class="center-content">
#             <div class="value-orange">₹ {left_rej_amt}</div>
#             <div class="title-black">Rejection Amount</div>
#         </div>
#     </div>

#     <div class="card">
#         <canvas class="snow-bg" id="snowoee"></canvas>
#         <div class="center-content">
#             <div class="value-blue">{top_oee}</div>
#             <div class="title-black">OEE %</div>
#         </div>
#     </div>

#     <!-- Row 2 -->
#     <div class="card">
#         <canvas class="snow-bg" id="snowcumsale"></canvas>
#         <div class="center-content">
#             <div class="value-blue">₹ {total_cum_disp}</div>
#             <div class="title-black">Sale Cumulative</div>
#         </div>
#     </div>

#     <div class="card">
#         <canvas class="snow-bg" id="snowach"></canvas>
#         <div class="center-content">
#             <div class="value-orange">{left_rej_pct}</div>
#             <div class="title-black">Rejection %</div>
#         </div>
#     </div>

#     <div class="card">
#         <canvas class="snow-bg" id="snowcopq"></canvas>
#         <div class="center-content">
#             <div class="value-blue">₹ {copq_display}</div>
#             <div class="title-black">COPQ Last Day</div>
#         </div>
#     </div>

#     <!-- Row 3: Sale Trend, Rejection Trend, COPQ Cumulative -->
#     <div class="card">
#         <canvas class="snow-bg" id="snowsalechart"></canvas>
#         <div class="chart-title-black">Sale Trend</div>
#         <div class="chart-container">{sale_html}</div>
#     </div>

#     <div class="card">
#         <canvas class="snow-bg" id="snowrejchart"></canvas>
#         <div class="chart-title-black">Rejection Trend</div>
#         <div class="chart-container">{rej_html}</div>
#     </div>

#     <div class="card">
#         <canvas class="snow-bg" id="snowcopqcum"></canvas>
#         <div class="center-content">
#             <div class="value-blue">₹ {copq_cum_display}</div>
#             <div class="title-black">COPQ Cumulative</div>
#         </div>
#     </div>

#     <!-- Row 4: Gauge below Sale Trend -->
#     <div class="card">
#         <canvas class="snow-bg" id="snowspeed"></canvas>
#         <div class="gauge-wrapper">{gauge_html}</div>
#     </div>

#     <div class="card">
#         <canvas class="snow-bg" id="snowrejcum"></canvas>
#         <div class="center-content">
#             <div class="value-orange">{bottom_rej_cum}</div>
#             <div class="title-black">Rejection Cumulative</div>
#         </div>
#     </div>

#     <div class="card">
#         <canvas class="snow-bg" id="snowempty"></canvas>
#         <div class="center-content">
#             <div class="value-blue">&nbsp;</div>
#         </div>
#     </div>

# </div>

# </body>
# </html>
# """

# st.components.v1.html(html_template, height=900, scrolling=True)









































