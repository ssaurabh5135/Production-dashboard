import streamlit as st, pandas as pd, plotly.graph_objects as go, base64, time
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Factory Dashboard (Exact Layout)", layout="wide")
IMAGE_PATH="winter.jpg"
SPREADSHEET_ID="168UoOWdTfOBxBvy_4QGymfiIRimSO2OoJdnzBDRPLvk"
DASHBOARD_SHEET="Dashboard"
SALES_REPORT_SHEET="Sales Report"
TARGET_SALE=19_92_00_000

def load_image_base64(p):
    try: return base64.b64encode(Path(p).read_bytes()).decode()
    except: return ""

def format_inr(n):
    try: x=str(int(float(str(n).replace(",",""))))
    except: return str(n)
    if len(x)<=3: return x
    last3=x[-3:];rest=x[:-3]
    rest=''.join([rest[::-1][i:i+2][::-1]+',' for i in range(0,len(rest),2)][::-1])
    return rest+last3

def ensure_pct(x):
    try: v=float(str(x).replace("%","").replace(",",""))
    except: return 0.0
    return v*100 if v<=5 else v

# GOOGLE AUTH
creds=Credentials.from_service_account_info(st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"])
client=gspread.authorize(creds)
sh=client.open_by_key(SPREADSHEET_ID)

# DASHBOARD DATA
rows=sh.worksheet(DASHBOARD_SHEET).get_values("A1:H")
header=rows[0]
data=[dict(zip(header,r)) for r in rows[1:] if any(r)]
df=pd.DataFrame(data)
df.columns=df.columns.str.strip().str.lower()
date_col=df.columns[0]
df[date_col]=pd.to_datetime(df[date_col],errors="coerce")
for c in df.columns[1:]:
    df[c]=pd.to_numeric(df[c].astype(str).replace(",","",regex=True),errors="coerce")
df=df.dropna(subset=[date_col]).sort_values(date_col)
latest=df.iloc[-1]
(date_col,today_col,oee_col,plan_col,rej_day_col,rej_pct_col,rej_cum_col,total_cum_col)=df.columns[:8]

today_sale=latest[today_col]
oee=ensure_pct(latest[oee_col])
plan_vs_actual=ensure_pct(latest[plan_col])
rej_day=latest[rej_day_col]
rej_pct=ensure_pct(latest[rej_pct_col])
rej_cum=latest[rej_cum_col]

total_cum=df[total_cum_col].dropna().iloc[-1]
achieved_pct_val=round((total_cum/TARGET_SALE*100),2)

# COLORS
ORANGE="#fc7d1b";BLUE="#228be6";GREEN="#009e4f"

# GAUGE
g=go.Figure(go.Indicator(mode="gauge",value=achieved_pct_val,
    number={"suffix":"%","font":{"size":44,"color":GREEN}},domain={"x":[0,1],"y":[0,1]},
    gauge={"axis":{"range":[0,100]},"bar":{"color":GREEN}}))
g.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",height=170)
gauge_html=g.to_html(include_plotlyjs="cdn",full_html=False)

bg_b64=load_image_base64(IMAGE_PATH)
bg=f"data:image/png;base64,{bg_b64}"

ach_html=f"<div class='center-content'><div class='value-green'>{achieved_pct_val}%</div><div class='title-green'>Achieved %</div></div>"
top_date=latest[date_col].strftime("%d-%b-%Y")
top_today_sale=format_inr(today_sale)
top_oee=f'{round(oee,1)}%'
left_rej_pct=f'{rej_pct:.1f}%'
bottom_rej_cum=format_inr(rej_cum)

html=f"""
<!doctype html><html><head><meta charset='utf-8'>
<style>
body{{margin:0;padding:18px;font-family:Poppins;background:url('{bg}') center/cover no-repeat fixed;}}
.container{{width:100%;min-height:98vh;display:grid;grid-template-columns:1fr 1fr 1fr;
grid-template-rows:130px 220px 140px;gap:18px;row-gap:30px;}}
.card{{background:rgba(255,255,255,0.1);border-radius:14px;padding:0;box-shadow:0 6px 18px rgba(0,0,0,.3);
backdrop-filter:blur(6px);display:flex;flex-direction:column;align-items:center;justify-content:center;}}
.value-orange{{color:{ORANGE};font-size:34px;font-weight:800;text-align:center;}}
.value-blue{{color:{BLUE};font-size:34px;font-weight:800;text-align:center;}}
.value-green{{color:{GREEN};font-size:46px;font-weight:800;text-align:center;}}
.title-black{{color:#000;font-size:15px;font-weight:700;text-align:center;}}
.title-green{{color:{GREEN};font-size:26px;font-weight:700;text-align:center;}}
.chart-container{{height:110px;overflow:hidden;}}
</style></head>
<body>
<div class='container'>
<div class='card'><div class='value-orange'>{top_date}</div><div class='title-black'>Date</div></div>
<div class='card'><div class='value-blue'>₹ {top_today_sale}</div><div class='title-black'>Today's Sale</div></div>
<div class='card'><div class='value-orange'>{top_oee}</div><div class='title-black'>OEE %</div></div>
<div class='card'><div class='value-orange'>{left_rej_pct}</div><div class='title-black'>Rejection %</div></div>
<div class='card'>{ach_html}</div>
<div class='card'>{gauge_html}</div>
<div class='card'><div class='value-orange'>₹ {bottom_rej_cum}</div><div class='title-black'>Rejection (Cumulative)</div></div>
<div class='card'><div class='chart-container'>SALE TREND</div></div>
<div class='card'><div class='chart-container'>REJECTION TREND</div></div>
</div>
</body></html>
"""

# AUTO REFRESH (30 SEC)
key=int(time.time()//30)

st.components.v1.html(html,height=770,scrolling=True,key=f"frame_{key}")
