import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import io
import requests # JSONBin 통신용

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
# 2. JSONBin.io 연동 함수 (핵심 기능)
# -----------------------------------------------------------------------------
# secrets에서 키 가져오기 (없으면 에러 방지 위해 None 처리)
API_KEY = st.secrets["jsonbin"]["api_key"] if "jsonbin" in st.secrets else None
BIN_ID = st.secrets["jsonbin"]["bin_id"] if "jsonbin" in st.secrets else None

def load_data_from_cloud():
    """JSONBin에서 데이터 불러오기"""
    if not API_KEY or not BIN_ID:
        st.error("⚠️ Secrets 설정이 필요합니다.")
        return []
    
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}/latest"
    headers = {"X-Master-Key": API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json().get("record", {})
            return data.get("portfolio", []) # 'portfolio' 키로 저장된 리스트 반환
        else:
            st.error(f"클라우드 로드 실패: {response.status_code}")
            return []
    except Exception as e:
        st.error(f"통신 오류: {e}")
        return []

def save_data_to_cloud(portfolio_data):
    """JSONBin에 데이터 저장하기 (덮어쓰기)"""
    if not API_KEY or not BIN_ID:
        st.error("⚠️ Secrets 설정이 필요합니다.")
        return False
        
    url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    headers = {
        "Content-Type": "application/json",
        "X-Master-Key": API_KEY
    }
    # 포트폴리오 리스트를 JSON 객체로 감싸서 저장
    payload = {"portfolio": portfolio_data}
    
    try:
        response = requests.put(url, json=payload, headers=headers)
        if response.status_code == 200:
            return True
        else:
            st.error(f"저장 실패: {response.text}")
            return False
    except Exception as e:
        st.error(f"통신 오류: {e}")
        return False

# -----------------------------------------------------------------------------
# 3. 주식 데이터 처리 유틸리티
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_exchange_rate():
    try:
        return yf.Ticker("KRW=X").fast_info.get('last_price', 1400.0)
    except:
        return 1400.0

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
            if not hist.empty: price = hist['Close'].iloc[-1]
            else: price = stock.info.get('currentPrice', 0)
        
        info = stock.info
        return {
            'current_price': price,
            'sector': info.get('sector', 'Others'),
            'market_cap_class': classify_market_cap(info.get('marketCap', 0)),
            'valid': True
        }
    except:
        return {'valid': False}

# -----------------------------------------------------------------------------
# 4. 세션 및 데이터 로직
# -----------------------------------------------------------------------------
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

# 앱 시작 시 클라우드에서 자동 로드 시도 (최초 1회만)
if 'init_load' not in st.session_state:
    cloud_data = load_data_from_cloud()
    if cloud_data:
        st.session_state.portfolio = cloud_data
        st.toast("☁️ 클라우드에서 데이터를 불러왔습니다!", icon="✅")
    st.session_state.init_load = True

def add_stock_data(ticker, avg_price, qty):
    ticker = ticker.strip().upper()
    info = get_stock_info(ticker)
    if info['valid']:
        # 기존에 같은 티커가 있으면 제거하고 업데이트 (선택사항)
        # st.session_state.portfolio = [x for x in st.session_state.portfolio if x['Ticker'] != ticker]
        
        st.session_state.portfolio.append({
            'Ticker': ticker,
            'Avg Price': float(avg_price),
            'Quantity': float(qty),
            'Current Price': info['current_price'],
            'Sector': info['sector'],
            'Market Cap Class': info['market_cap_class'],
        })
        return True
    return False

def process_csv_input(csv_text):
    try:
        df_input = pd.read_csv(io.StringIO(csv_text), header=None, names=['Ticker', 'Price', 'Qty'])
        success = 0
        bar = st.sidebar.progress(0)
        for i, row in df_input.iterrows():
            if add_stock_data(str(row['Ticker']), row['Price'], row['Qty']): success += 1
            bar.progress((i + 1) / len(df_input))
        bar.empty()
        if success > 0: 
            st.sidebar.success(f"{success}개 추가 완료! 저장을 눌러주세요.")
    except Exception as e:
        st.sidebar.error(f"오류: {e}")

# -----------------------------------------------------------------------------
# 5. 사이드바 (Cloud Save/Load)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("☁️ 클라우드 동기화")
    
    # 저장 / 불러오기 버튼
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("📤 클라우드 저장", use_container_width=True, type="primary"):
            if save_data_to_cloud(st.session_state.portfolio):
                st.toast("저장 완료!", icon="💾")
                st.success("저장되었습니다.")
    with col_s2:
        if st.button("📥 불러오기", use_container_width=True):
            data = load_data_from_cloud()
            if data:
                st.session_state.portfolio = data
                st.rerun()
    
    st.markdown("---")
    
    st.subheader("⚙️ 보기 설정")
    currency_mode = st.radio("통화", ["USD ($)", "KRW (₩)"], horizontal=True)
    exchange_rate = get_exchange_rate()
    if currency_mode == "KRW (₩)": st.caption(f"환율: {exchange_rate:,.2f} 원")

    st.markdown("---")
    
    # 입력 탭
    tab1, tab2 = st.tabs(["CSV 입력", "개별 입력"])
    with tab1:
        csv_input = st.text_area("티커, 매수가, 수량", height=100)
        if st.button("목록 추가"):
            if csv_input: process_csv_input(csv_input)
    with tab2:
        t = st.text_input("티커").strip()
        p = st.number_input("매수가($)", 0.0)
        q = st.number_input("수량", 0.0)
        if st.button("추가"):
            add_stock_data(t, p, q)

    if st.button("⚠️ 초기화"):
        st.session_state.portfolio = []
        st.rerun()

# -----------------------------------------------------------------------------
# 6. 메인 대시보드 (기존 유지)
# -----------------------------------------------------------------------------
st.title("📊 My Cloud Portfolio")

if not API_KEY:
    st.warning("⚠️ Streamlit Secrets에 JSONBin API Key 설정이 필요합니다. (가이드 참조)")

if st.session_state.portfolio:
    df = pd.DataFrame(st.session_state.portfolio)
    
    # 최신 주가 업데이트 (불러온 데이터가 구버전일 수 있으므로)
    # 성능을 위해 전체 루프보다는 필요한 경우만 갱신하거나, 여기서는 간단히 표시 로직만 수행
    # (실제로는 불러온 뒤 주가 갱신 로직을 한 번 돌리는 것이 좋습니다. 여기서는 편의상 생략 또는 개별 추가시 갱신됨)
    
    # USD 계산
    df['Invested_USD'] = df['Avg Price'] * df['Quantity']
    df['Value_USD'] = df['Current Price'] * df['Quantity']
    df['PnL_USD'] = df['Value_USD'] - df['Invested_USD']
    df['Return (%)'] = (df['PnL_USD'] / df['Invested_USD']) * 100
    
    # 통화 변환
    if currency_mode == "KRW (₩)":
        sym, fmt = "₩", '{:,.0f}'
        df['Avg Price'] *= exchange_rate
        df['Current Price'] *= exchange_rate
        df['Invested'] = df['Invested_USD'] * exchange_rate
        df['Value'] = df['Value_USD'] * exchange_rate
        df['PnL'] = df['PnL_USD'] * exchange_rate
    else:
        sym, fmt = "$", '{:,.2f}'
        df['Invested'] = df['Invested_USD']
        df['Value'] = df['Value_USD']
        df['PnL'] = df['PnL_USD']

    # 메트릭
    tot_inv, tot_val, tot_pnl = df['Invested'].sum(), df['Value'].sum(), df['PnL'].sum()
    tot_ret = (tot_pnl / tot_inv * 100) if tot_inv else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 매수", f"{sym}{tot_inv:,.0f}" if sym=="₩" else f"${tot_inv:,.2f}")
    c2.metric("총 평가", f"{sym}{tot_val:,.0f}" if sym=="₩" else f"${tot_val:,.2f}")
    c3.metric("총 손익", f"{sym}{tot_pnl:,.0f}" if sym=="₩" else f"${tot_pnl:,.2f}", delta=f"{tot_pnl:,.0f}" if sym=="₩" else f"{tot_pnl:,.2f}")
    c4.metric("수익률", f"{tot_ret:.2f}%", delta=f"{tot_ret:.2f}%")

    st.divider()

    # 차트
    c_left, c_right = st.columns([2, 1])
    with c_left:
        fig_tree = px.treemap(df, path=[px.Constant("Portfolio"), 'Sector', 'Ticker'], values='Value',
            color='Return (%)', color_continuous_scale=['#0059b3', '#f0f0f0', '#ff2e2e'], color_continuous_midpoint=0)
        fig_tree.update_traces(textinfo="label+value+percent entry")
        st.plotly_chart(fig_tree, use_container_width=True)
    with c_right:
        df_sorted = df.sort_values('Return (%)')
        colors = ['#ff2e2e' if x >= 0 else '#0059b3' for x in df_sorted['Return (%)']]
        fig_bar = go.Figure(go.Bar(x=df_sorted['Return (%)'], y=df_sorted['Ticker'], orientation='h', marker_color=colors))
        st.plotly_chart(fig_bar, use_container_width=True)

    # 테이블
    st.dataframe(
        df[['Ticker', 'Sector', 'Quantity', 'Avg Price', 'Current Price', 'Return (%)', 'PnL', 'Value']].style.format({
            'Avg Price': f'{sym}{fmt}', 'Current Price': f'{sym}{fmt}', 'Quantity': '{:,.2f}',
            'Return (%)': '{:,.2f}%', 'PnL': f'{sym}{fmt}', 'Value': f'{sym}{fmt}'
        }).map(lambda x: f'color: {"#ff2e2e" if x>0 else "#0059b3" if x<0 else "black"}; font-weight: bold;', subset=['Return (%)', 'PnL']),
        use_container_width=True, hide_index=True
    )
else:
    st.info("👈 사이드바에서 [불러오기]를 하거나 데이터를 입력하세요.")
