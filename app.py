import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import io
import requests

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 스타일
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Pro 24h Portfolio (Cloud)", page_icon="☁️", layout="wide")

st.markdown("""
<style>
    div[data-testid="stMetric"] { background-color: #f9f9f9; border: 1px solid #e0e0e0; padding: 15px; border-radius: 10px; }
    button[data-baseweb="tab"] { font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. JSONBin.io 및 데이터 유틸리티
# -----------------------------------------------------------------------------
API_KEY = st.secrets["jsonbin"]["api_key"] if "jsonbin" in st.secrets else None
BIN_ID = st.secrets["jsonbin"]["bin_id"] if "jsonbin" in st.secrets else None

def load_data_from_cloud():
    if not API_KEY or not BIN_ID: return []
    try:
        res = requests.get(f"https://api.jsonbin.io/v3/b/{BIN_ID}/latest", headers={"X-Master-Key": API_KEY})
        return res.json().get("record", {}).get("portfolio", []) if res.status_code == 200 else []
    except: return []

def save_data_to_cloud(data):
    if not API_KEY or not BIN_ID: return False
    try:
        res = requests.put(f"https://api.jsonbin.io/v3/b/{BIN_ID}", json={"portfolio": data}, 
                           headers={"Content-Type": "application/json", "X-Master-Key": API_KEY})
        return res.status_code == 200
    except: return False

@st.cache_data(ttl=300)
def get_exchange_rate():
    try: return yf.Ticker("KRW=X").fast_info.get('last_price', 1400.0)
    except: return 1400.0

def classify_market_cap(market_cap):
    if not market_cap: return "Unknown"
    billions = market_cap / 1_000_000_000
    if billions >= 200: return "Mega Cap (초대형주)"
    elif billions >= 10: return "Large Cap (대형주)"
    elif billions >= 2: return "Mid Cap (중형주)"
    elif billions >= 0.3: return "Small Cap (소형주)"
    else: return "Micro Cap (초소형주)"

@st.cache_data(ttl=10) 
def get_stock_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        price = stock.fast_info.get('last_price', None)
        if price is None:
            hist = stock.history(period="1d", interval="1m", prepost=True)
            price = hist['Close'].iloc[-1] if not hist.empty else stock.info.get('currentPrice', 0)
        
        info = stock.info
        return {
            'current_price': price,
            'sector': info.get('sector', 'Others'),
            'market_cap_class': classify_market_cap(info.get('marketCap', 0)),
            'valid': True
        }
    except: return {'valid': False}

# -----------------------------------------------------------------------------
# 3. 앱 로직
# -----------------------------------------------------------------------------
if 'portfolio' not in st.session_state: st.session_state.portfolio = []
if 'init_load' not in st.session_state:
    cloud_data = load_data_from_cloud()
    if cloud_data: st.session_state.portfolio = cloud_data
    st.session_state.init_load = True

def add_stock_data(ticker, avg_price, qty):
    info = get_stock_info(ticker.strip().upper())
    if info['valid']:
        st.session_state.portfolio.append({
            'Ticker': ticker.strip().upper(), 'Avg Price': float(avg_price), 'Quantity': float(qty),
            'Current Price': info['current_price'], 'Sector': info['sector'], 'Market Cap Class': info['market_cap_class']
        })
        return True
    return False

def process_csv(txt):
    try:
        df = pd.read_csv(io.StringIO(txt), header=None, names=['Ticker', 'Price', 'Qty'])
        cnt = sum(add_stock_data(str(r['Ticker']), r['Price'], r['Qty']) for _, r in df.iterrows())
        if cnt > 0: st.sidebar.success(f"{cnt}개 추가! 저장을 눌러주세요.")
    except Exception as e: st.sidebar.error(f"오류: {e}")

# -----------------------------------------------------------------------------
# 4. 화면 구성
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("☁️ 클라우드 관리")
    c1, c2 = st.columns(2)
    if c1.button("📤 저장", type="primary"): 
        if save_data_to_cloud(st.session_state.portfolio): st.toast("저장 완료!", icon="💾")
    if c2.button("📥 불러오기"):
        d = load_data_from_cloud()
        if d: 
            st.session_state.portfolio = d
            st.rerun()
    
    st.divider()
    currency_mode = st.radio("통화", ["USD ($)", "KRW (₩)"], horizontal=True)
    ex_rate = get_exchange_rate()
    if currency_mode == "KRW (₩)": st.caption(f"환율: {ex_rate:,.2f} 원")
    
    st.divider()
    t1, t2 = st.tabs(["CSV", "개별"])
    with t1:
        if st.button("CSV 추가"): process_csv(st.text_area("티커,가격,수량"))
    with t2:
        t, p, q = st.text_input("티커"), st.number_input("가"), st.number_input("양")
        if st.button("추가"): add_stock_data(t, p, q)
    
    if st.button("초기화"): st.session_state.portfolio = []; st.rerun()

st.title("📊 My Pro Dashboard")

if st.session_state.portfolio:
    df = pd.DataFrame(st.session_state.portfolio)
    
    # 계산 및 환율 적용
    is_krw = currency_mode == "KRW (₩)"
    rate = ex_rate if is_krw else 1.0
    sym, fmt = ("₩", '{:,.0f}') if is_krw else ("$", '{:,.2f}')
    
    df['Invested'] = df['Avg Price'] * df['Quantity'] * rate
    df['Value'] = df['Current Price'] * df['Quantity'] * rate
    df['PnL'] = df['Value'] - df['Invested']
    df['Return (%)'] = (df['PnL'] / df['Invested']) * 100
    
    # 상단 지표
    cols = st.columns(4)
    cols[0].metric("총 매수", f"{sym}{df['Invested'].sum():,.0f}" if is_krw else f"${df['Invested'].sum():,.2f}")
    cols[1].metric("총 평가", f"{sym}{df['Value'].sum():,.0f}" if is_krw else f"${df['Value'].sum():,.2f}")
    cols[2].metric("총 손익", f"{sym}{df['PnL'].sum():,.0f}" if is_krw else f"${df['PnL'].sum():,.2f}", 
                   delta=f"{df['PnL'].sum():,.0f}" if is_krw else f"{df['PnL'].sum():,.2f}")
    cols[3].metric("수익률", f"{df['Return (%)'].mean():.2f}%" if not df.empty else "0%", 
                   delta=f"{(df['PnL'].sum()/df['Invested'].sum()*100):.2f}%")

    st.divider()

    # --- 차트 섹션 (업그레이드) ---
    st.subheader("📈 포트폴리오 심층 분석")
    
    # 1. 트리맵 (전체 맵)
    fig_tree = px.treemap(df, path=[px.Constant("Portfolio"), 'Sector', 'Ticker'], values='Value',
                          color='Return (%)', color_continuous_scale=['#0059b3', '#f0f0f0', '#ff2e2e'], color_continuous_midpoint=0)
    fig_tree.update_traces(textinfo="label+value+percent entry")
    st.plotly_chart(fig_tree, use_container_width=True)
    
    # 2. 섹터 & 시총 분석 (새로 추가된 부분)
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("#### 🥧 섹터별 비중 (Sector)")
        fig_sec = px.pie(df, values='Value', names='Sector', hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
        fig_sec.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_sec, use_container_width=True)
        
    with c2:
        st.markdown("#### 🏗️ 시총 규모별 비중 (Size)")
        cap_order = ["Mega Cap (초대형주)", "Large Cap (대형주)", "Mid Cap (중형주)", "Small Cap (소형주)", "Micro Cap (초소형주)", "Unknown"]
        # 시총 규모별로 그룹화하여 금액 합계 계산
        df_cap = df.groupby('Market Cap Class')['Value'].sum().reset_index()
        fig_cap = px.bar(df_cap, x='Market Cap Class', y='Value', color='Market Cap Class', 
                         category_orders={"Market Cap Class": cap_order}, 
                         text_auto='.2s', color_discrete_sequence=px.colors.sequential.Viridis)
        st.plotly_chart(fig_cap, use_container_width=True)

    # 3. 수익률 랭킹
    st.markdown("#### 🏆 수익률 랭킹")
    df_sorted = df.sort_values('Return (%)')
    colors = ['#ff2e2e' if x >= 0 else '#0059b3' for x in df_sorted['Return (%)']]
    fig_bar = go.Figure(go.Bar(x=df_sorted['Return (%)'], y=df_sorted['Ticker'], orientation='h', marker_color=colors,
                               text=df_sorted['Return (%)'].apply(lambda x: f"{x:.1f}%"), textposition='auto'))
    fig_bar.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=400)
    st.plotly_chart(fig_bar, use_container_width=True)

    # 데이터 테이블
    st.dataframe(df[['Ticker', 'Sector', 'Market Cap Class', 'Avg Price', 'Current Price', 'Return (%)', 'PnL', 'Value']].style.format({
        'Avg Price': f'{sym}{fmt}', 'Current Price': f'{sym}{fmt}', 'Return (%)': '{:.2f}%', 
        'PnL': f'{sym}{fmt}', 'Value': f'{sym}{fmt}'
    }).map(lambda x: f'color: {"#ff2e2e" if x>0 else "#0059b3" if x<0 else "black"}; font-weight: bold;', subset=['Return (%)', 'PnL']), 
    use_container_width=True, hide_index=True)

else:
    st.info("👈 사이드바에서 [불러오기]를 눌러 데이터를 로드하세요.")
