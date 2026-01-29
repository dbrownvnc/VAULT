import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 디자인
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Pro Portfolio Tracker",
    page_icon="📈",
    layout="wide"
)

# 커스텀 CSS (가독성 향상)
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 유틸리티 함수 (데이터 수집 및 로직)
# -----------------------------------------------------------------------------

# 시가총액 규모 분류 기준 (USD 기준, 일반적인 월가 기준 적용)
def classify_market_cap(market_cap):
    if market_cap is None:
        return "Unknown"
    
    billions = market_cap / 1_000_000_000
    if billions >= 200:
        return "Mega Cap (초대형주)"
    elif billions >= 10:
        return "Large Cap (대형주)"
    elif billions >= 2:
        return "Mid Cap (중형주)"
    elif billions >= 0.3:
        return "Small Cap (소형주)"
    else:
        return "Micro Cap (초소형주)"

@st.cache_data(ttl=60) # 1분마다 캐시 초기화 (실시간성 유지)
def get_stock_info(ticker):
    """
    yfinance를 통해 주식의 최신 정보를 가져옵니다.
    """
    try:
        stock = yf.Ticker(ticker)
        # fast_info가 응답 속도가 더 빠름
        price = stock.fast_info.get('last_price', None)
        
        # 상세 정보는 info 딕셔너리에서 추출
        info = stock.info
        sector = info.get('sector', 'Others')
        industry = info.get('industry', 'Others')
        mkt_cap = info.get('marketCap', 0)
        currency = info.get('currency', 'USD')
        
        if price is None:
            # fast_info 실패 시 일반 info에서 재시도
            price = info.get('currentPrice', 0)

        return {
            'current_price': price,
            'sector': sector,
            'industry': industry,
            'market_cap_raw': mkt_cap,
            'market_cap_class': classify_market_cap(mkt_cap),
            'currency': currency,
            'valid': True
        }
    except Exception as e:
        return {'valid': False, 'error': str(e)}

# -----------------------------------------------------------------------------
# 3. 세션 상태 관리 (데이터 저장소)
# -----------------------------------------------------------------------------
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

def add_stock(ticker, avg_price, qty):
    """포트폴리오에 종목을 추가하고 즉시 데이터를 업데이트합니다."""
    with st.spinner(f"'{ticker}' 데이터 불러오는 중..."):
        info = get_stock_info(ticker)
        
    if info['valid']:
        st.session_state.portfolio.append({
            'Ticker': ticker.upper(),
            'Avg Price': avg_price,
            'Quantity': qty,
            'Current Price': info['current_price'],
            'Sector': info['sector'],
            'Market Cap Class': info['market_cap_class'],
            'Market Cap Raw': info['market_cap_raw'],
            'Currency': info['currency']
        })
        st.success(f"✅ {ticker.upper()} 추가 완료!")
    else:
        st.error(f"❌ '{ticker}' 정보를 찾을 수 없습니다. 티커를 확인해주세요.")

def clear_portfolio():
    st.session_state.portfolio = []
    st.rerun()

# -----------------------------------------------------------------------------
# 4. 사이드바 (입력 패널)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("📝 포트폴리오 입력")
    
    input_ticker = st.text_input("티커 (Ticker)", placeholder="예: AAPL, TSLA, 005930.KS").strip()
    col1, col2 = st.columns(2)
    with col1:
        input_price = st.number_input("평균 매수단가", min_value=0.0, format="%.2f")
    with col2:
        input_qty = st.number_input("보유 수량", min_value=0.0, format="%.2f")
        
    if st.button("주식 추가", use_container_width=True):
        if input_ticker and input_qty > 0:
            add_stock(input_ticker, input_price, input_qty)
        else:
            st.warning("티커와 수량을 올바르게 입력해주세요.")

    st.markdown("---")
    if st.button("포트폴리오 초기화", type="primary"):
        clear_portfolio()
    
    st.info("💡 **Tip:** 한국 주식은 티커 뒤에 `.KS`(코스피) 또는 `.KQ`(코스닥)를 붙이세요. (예: 005930.KS)")

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📊 Pro Stock Portfolio Dashboard")

if len(st.session_state.portfolio) > 0:
    # 데이터프레임 변환 및 계산
    df = pd.DataFrame(st.session_state.portfolio)
    
    # 핵심 계산 로직
    df['Invested Amount'] = df['Avg Price'] * df['Quantity'] # 총 매수 금액
    df['Current Value'] = df['Current Price'] * df['Quantity'] # 현재 평가 금액
    df['Profit/Loss'] = df['Current Value'] - df['Invested Amount'] # 손익금
    df['Return (%)'] = (df['Profit/Loss'] / df['Invested Amount']) * 100 # 수익률
    
    # --- Top Metrics 섹션 ---
    total_invested = df['Invested Amount'].sum()
    total_value = df['Current Value'].sum()
    total_pnl = df['Profit/Loss'].sum()
    total_return = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 매수 금액", f"${total_invested:,.2f}")
    m2.metric("현재 평가 금액", f"${total_value:,.2f}")
    m3.metric("총 손익 (P&L)", f"${total_pnl:,.2f}", delta_color="normal")
    m4.metric("총 수익률", f"{total_return:,.2f}%", delta=f"{total_return:,.2f}%")
    
    st.markdown("---")

    # --- 차트 섹션 (섹터 & 시총) ---
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🍰 섹터별 비중 (Sector Allocation)")
        fig_sector = px.pie(df, values='Current Value', names='Sector', hole=0.4,
                            color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_sector.update_traces(textinfo='percent+label')
        st.plotly_chart(fig_sector, use_container_width=True)
        
    with c2:
        st.subheader("🏛️ 시가총액 규모별 분포 (Market Cap)")
        # 시총 순서 정렬을 위한 로직
        cap_order = ["Mega Cap (초대형주)", "Large Cap (대형주)", "Mid Cap (중형주)", "Small Cap (소형주)", "Micro Cap (초소형주)", "Unknown"]
        fig_cap = px.bar(df, x='Market Cap Class', y='Current Value', color='Ticker',
                         category_orders={"Market Cap Class": cap_order},
                         labels={'Current Value': '평가 금액 ($)'})
        st.plotly_chart(fig_cap, use_container_width=True)

    # --- 상세 데이터 테이블 ---
    st.subheader("📋 보유 종목 상세 (Detailed View)")
    
    # 보여줄 컬럼 선택 및 포맷팅
    display_df = df[['Ticker', 'Sector', 'Market Cap Class', 'Avg Price', 'Current Price', 'Quantity', 'Return (%)', 'Profit/Loss', 'Current Value']]
    
    # 스타일링 (수익률 색상 적용)
    def color_return(val):
        color = '#ff4b4b' if val < 0 else '#2ecc71'
        return f'color: {color}'

    st.dataframe(
        display_df.style.format({
            'Avg Price': '${:,.2f}',
            'Current Price': '${:,.2f}',
            'Quantity': '{:,.2f}',
            'Return (%)': '{:,.2f}%',
            'Profit/Loss': '${:,.2f}',
            'Current Value': '${:,.2f}'
        }).map(color_return, subset=['Return (%)', 'Profit/Loss']),
        use_container_width=True,
        hide_index=True
    )

else:
    # 데이터가 없을 때 보여줄 화면
    st.info("👈 왼쪽 사이드바에서 주식 티커와 매수 정보를 입력하여 포트폴리오를 구성해보세요.")
    st.markdown("""
    **사용 가이드:**
    1. **미국 주식:** AAPL, NVDA, TSLA 등 티커 입력
    2. **한국 주식:** 005930.KS (삼성전자), 035420.KS (네이버) 등 `.KS` 입력
    3. **자동 분류:** 입력 즉시 섹터와 시가총액 규모가 자동으로 분류됩니다.
    """)