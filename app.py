import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import io # 문자열을 파일처럼 처리하기 위해 추가

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 디자인
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Pro Portfolio Tracker", page_icon="📈", layout="wide")
st.markdown("""
<style>
    .metric-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #ff4b4b; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 유틸리티 함수
# -----------------------------------------------------------------------------
def classify_market_cap(market_cap):
    if market_cap is None: return "Unknown"
    billions = market_cap / 1_000_000_000
    if billions >= 200: return "Mega Cap (초대형주)"
    elif billions >= 10: return "Large Cap (대형주)"
    elif billions >= 2: return "Mid Cap (중형주)"
    elif billions >= 0.3: return "Small Cap (소형주)"
    else: return "Micro Cap (초소형주)"

@st.cache_data(ttl=60)
def get_stock_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        price = stock.fast_info.get('last_price', None)
        info = stock.info
        if price is None: price = info.get('currentPrice', 0)
        
        return {
            'current_price': price,
            'sector': info.get('sector', 'Others'),
            'market_cap_class': classify_market_cap(info.get('marketCap', 0)),
            'market_cap_raw': info.get('marketCap', 0),
            'currency': info.get('currency', 'USD'),
            'valid': True
        }
    except Exception as e:
        return {'valid': False}

# -----------------------------------------------------------------------------
# 3. 세션 및 데이터 관리
# -----------------------------------------------------------------------------
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

def add_stock_data(ticker, avg_price, qty):
    """단일 종목 추가 로직 (재사용을 위해 함수 분리)"""
    ticker = ticker.strip().upper()
    info = get_stock_info(ticker)
    
    if info['valid']:
        st.session_state.portfolio.append({
            'Ticker': ticker,
            'Avg Price': float(avg_price),
            'Quantity': float(qty),
            'Current Price': info['current_price'],
            'Sector': info['sector'],
            'Market Cap Class': info['market_cap_class'],
            'Currency': info['currency']
        })
        return True
    return False

def process_csv_input(csv_text):
    """CSV 텍스트를 읽어서 일괄 등록"""
    try:
        # 헤더가 없는 경우를 가정하여 읽기
        df_input = pd.read_csv(io.StringIO(csv_text), header=None, names=['Ticker', 'Price', 'Qty'])
        
        success_count = 0
        progress_bar = st.sidebar.progress(0)
        
        for idx, row in df_input.iterrows():
            if add_stock_data(str(row['Ticker']), row['Price'], row['Qty']):
                success_count += 1
            progress_bar.progress((idx + 1) / len(df_input))
            
        progress_bar.empty()
        
        if success_count > 0:
            st.sidebar.success(f"✅ {success_count}개 종목 일괄 등록 성공!")
        else:
            st.sidebar.warning("등록된 종목이 없습니다. 티커를 확인하세요.")
            
    except Exception as e:
        st.sidebar.error(f"형식 오류: {e}")

# -----------------------------------------------------------------------------
# 4. 사이드바 (입력 패널 - 기능 확장)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("📝 포트폴리오 입력")
    
    # 탭을 사용하여 개별 입력과 일괄 입력을 분리
    tab1, tab2 = st.tabs(["개별 추가", "⚡ 일괄 추가(CSV)"])
    
    with tab1:
        input_ticker = st.text_input("티커", placeholder="AAPL").strip()
        c1, c2 = st.columns(2)
        p = c1.number_input("매수가", 0.0, format="%.2f")
        q = c2.number_input("수량", 0.0, format="%.2f")
        if st.button("추가", use_container_width=True):
            if add_stock_data(input_ticker, p, q):
                st.success(f"{input_ticker} 추가됨")
            else:
                st.error("티커 오류")

    with tab2:
        st.markdown("**형식:** `티커, 매수가, 수량`")
        st.markdown("_예시: NVDA, 120.5, 10_")
        csv_input = st.text_area("데이터 붙여넣기", height=150)
        
        if st.button("일괄 등록 실행", type="primary", use_container_width=True):
            if csv_input:
                process_csv_input(csv_input)

    st.markdown("---")
    if st.button("전체 초기화"):
        st.session_state.portfolio = []
        st.rerun()

# -----------------------------------------------------------------------------
# 5. 메인 대시보드 (기존과 동일하되 간단히 정리)
# -----------------------------------------------------------------------------
st.title("📊 My Smart Portfolio")

if st.session_state.portfolio:
    df = pd.DataFrame(st.session_state.portfolio)
    df['Invested'] = df['Avg Price'] * df['Quantity']
    df['Value'] = df['Current Price'] * df['Quantity']
    df['P&L'] = df['Value'] - df['Invested']
    df['Return (%)'] = (df['P&L'] / df['Invested']) * 100
    
    # 상단 지표
    c1, c2, c3 = st.columns(3)
    c1.metric("총 평가 금액", f"${df['Value'].sum():,.0f}")
    c2.metric("총 수익금", f"${df['P&L'].sum():,.0f}", delta_color="normal")
    tot_ret = (df['P&L'].sum() / df['Invested'].sum() * 100)
    c3.metric("총 수익률", f"{tot_ret:.2f}%", delta=f"{tot_ret:.2f}%")
    
    st.divider()
    
    # 차트 (좌: 섹터, 우: 시총)
    col1, col2 = st.columns(2)
    with col1:
        fig1 = px.pie(df, values='Value', names='Sector', title='섹터별 비중')
        st.plotly_chart(fig1, use_container_width=True)
    with col2:
        cap_order = ["Mega Cap (초대형주)", "Large Cap (대형주)", "Mid Cap (중형주)", "Small Cap (소형주)", "Micro Cap (초소형주)", "Unknown"]
        fig2 = px.bar(df, x='Market Cap Class', y='Value', color='Ticker', title='시가총액 규모별', category_orders={"Market Cap Class": cap_order})
        st.plotly_chart(fig2, use_container_width=True)
        
    # 테이블 출력
    st.dataframe(df.style.format({'Avg Price': '${:.2f}', 'Current Price': '${:.2f}', 'Return (%)': '{:.2f}%'}), use_container_width=True)

else:
    st.info("👈 사이드바의 '일괄 추가' 탭에 데이터를 붙여넣으세요.")
