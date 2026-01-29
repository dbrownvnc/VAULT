import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import io

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 스타일 (한국형 테마 적용)
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Pro 24h Portfolio", page_icon="📈", layout="wide")

st.markdown("""
<style>
    /* 메트릭 카드 스타일 */
    div[data-testid="stMetric"] {
        background-color: #f9f9f9;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 10px;
    }
    /* 탭 폰트 굵게 */
    button[data-baseweb="tab"] {
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 데이터 수집 및 유틸리티 함수
# -----------------------------------------------------------------------------

@st.cache_data(ttl=300) # 환율은 5분마다 갱신
def get_exchange_rate():
    """실시간 원/달러 환율 정보를 가져옵니다."""
    try:
        # yfinance에서 KRW=X는 달러/원 환율 티커입니다.
        fx = yf.Ticker("KRW=X")
        return fx.fast_info.get('last_price', 1400.0) # 실패시 기본값 1400
    except:
        return 1400.0

def classify_market_cap(market_cap):
    if market_cap is None: return "Unknown"
    billions = market_cap / 1_000_000_000
    if billions >= 200: return "Mega Cap (초대형주)"
    elif billions >= 10: return "Large Cap (대형주)"
    elif billions >= 2: return "Mid Cap (중형주)"
    elif billions >= 0.3: return "Small Cap (소형주)"
    else: return "Micro Cap (초소형주)"

@st.cache_data(ttl=10) # 주가는 10초마다 갱신 (실시간성 강화)
def get_stock_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        
        # fast_info는 최근 체결가를 가져오며, 장중/장외(After-market) 최신가를 포함하는 경우가 많음
        price = stock.fast_info.get('last_price', None)
        
        # 데이터가 없을 경우 history로 최근 1분 데이터 조회 (Pre/Post market 포함)
        if price is None:
            hist = stock.history(period="1d", interval="1m", prepost=True)
            if not hist.empty:
                price = hist['Close'].iloc[-1]
            else:
                price = stock.info.get('currentPrice', 0)
        
        info = stock.info
        return {
            'current_price': price,
            'sector': info.get('sector', 'Others'),
            'market_cap_class': classify_market_cap(info.get('marketCap', 0)),
            'currency': info.get('currency', 'USD'),
            'valid': True
        }
    except Exception as e:
        return {'valid': False}

# -----------------------------------------------------------------------------
# 3. 세션 및 로직 관리
# -----------------------------------------------------------------------------
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

def add_stock_data(ticker, avg_price, qty):
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
        })
        return True
    return False

def process_csv_input(csv_text):
    try:
        df_input = pd.read_csv(io.StringIO(csv_text), header=None, names=['Ticker', 'Price', 'Qty'])
        success_count = 0
        bar = st.sidebar.progress(0)
        for i, row in df_input.iterrows():
            if add_stock_data(str(row['Ticker']), row['Price'], row['Qty']):
                success_count += 1
            bar.progress((i + 1) / len(df_input))
        bar.empty()
        if success_count > 0: st.sidebar.success(f"{success_count}개 종목 업데이트 완료!")
    except Exception as e:
        st.sidebar.error(f"데이터 형식 오류: {e}")

# -----------------------------------------------------------------------------
# 4. 사이드바 UI
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ 설정 및 입력")
    
    # 환율 모드 선택
    currency_mode = st.radio("표시 통화 선택", ["USD ($)", "KRW (₩)"], horizontal=True)
    exchange_rate = get_exchange_rate()
    
    if currency_mode == "KRW (₩)":
        st.caption(f"💱 현재 적용 환율: 1 USD = {exchange_rate:,.2f} KRW")
    
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["CSV 일괄", "개별 추가"])
    with tab1:
        st.info("티커, 매수가($), 수량")
        csv_input = st.text_area("데이터 붙여넣기", height=100, help="Gemini가 만들어준 데이터를 여기에 붙여넣으세요.")
        if st.button("데이터 불러오기", type="primary", use_container_width=True):
            if csv_input: process_csv_input(csv_input)
            
    with tab2:
        t = st.text_input("티커").strip()
        p = st.number_input("매수가 ($)", 0.0)
        q = st.number_input("수량", 0.0)
        if st.button("추가하기"):
            add_stock_data(t, p, q)

    if st.button("⚠️ 초기화"):
        st.session_state.portfolio = []
        st.rerun()

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title("📊 Real-time Stock Dashboard (24h)")

if st.session_state.portfolio:
    # 데이터프레임 생성
    df = pd.DataFrame(st.session_state.portfolio)
    
    # 1. 기초 계산 (USD 기준)
    df['Invested_USD'] = df['Avg Price'] * df['Quantity']
    df['Value_USD'] = df['Current Price'] * df['Quantity']
    df['PnL_USD'] = df['Value_USD'] - df['Invested_USD']
    df['Return (%)'] = (df['PnL_USD'] / df['Invested_USD']) * 100
    
    # 2. 통화 변환 로직
    if currency_mode == "KRW (₩)":
        currency_symbol = "₩"
        df['Avg Price'] = df['Avg Price'] * exchange_rate
        df['Current Price'] = df['Current Price'] * exchange_rate
        df['Invested'] = df['Invested_USD'] * exchange_rate
        df['Value'] = df['Value_USD'] * exchange_rate
        df['PnL'] = df['PnL_USD'] * exchange_rate
        fmt_str = '{:,.0f}' # 원화는 소수점 제거
    else:
        currency_symbol = "$"
        df['Invested'] = df['Invested_USD']
        df['Value'] = df['Value_USD']
        df['PnL'] = df['PnL_USD']
        fmt_str = '{:,.2f}'

    # ------------------
    # Top Metrics
    # ------------------
    total_invested = df['Invested'].sum()
    total_value = df['Value'].sum()
    total_pnl = df['PnL'].sum()
    total_return = (total_pnl / total_invested * 100) if total_invested else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총 매수 금액", f"{currency_symbol}{total_invested:,.0f}" if currency_mode == "KRW (₩)" else f"${total_invested:,.2f}")
    col2.metric("총 평가 금액", f"{currency_symbol}{total_value:,.0f}" if currency_mode == "KRW (₩)" else f"${total_value:,.2f}")
    
    # 한국식 색상 적용 (상승=빨강, 하락=파랑)
    color_pnl = "normal" # metric 함수가 자동 처리하지만 명시적 색상은 dataframe에서 처리
    col3.metric("총 손익", f"{currency_symbol}{total_pnl:,.0f}" if currency_mode == "KRW (₩)" else f"${total_pnl:,.2f}", 
                delta=f"{total_pnl:,.0f}" if currency_mode == "KRW (₩)" else f"{total_pnl:,.2f}")
    col4.metric("총 수익률", f"{total_return:.2f}%", delta=f"{total_return:.2f}%")

    st.divider()

    # ------------------
    # Advanced Charts
    # ------------------
    
    # 1. 트리맵 (Map of the Market)
    st.subheader("🗺️ 포트폴리오 지도 (Treemap)")
    # 수익률에 따른 색상 (한국식: 빨강=상승, 파랑=하락)
    # Plotly 색상 스케일 커스텀 (Blue -> Gray -> Red)
    fig_tree = px.treemap(
        df, 
        path=[px.Constant("내 포트폴리오"), 'Sector', 'Ticker'], 
        values='Value',
        color='Return (%)',
        color_continuous_scale=['#0059b3', '#f0f0f0', '#ff2e2e'], # 파랑-회색-빨강
        color_continuous_midpoint=0,
        hover_data=['Return (%)', 'Current Price']
    )
    fig_tree.update_traces(textinfo="label+value+percent entry")
    st.plotly_chart(fig_tree, use_container_width=True)

    c1, c2 = st.columns(2)
    
    # 2. 수익률 랭킹 (Horizontal Bar)
    with c1:
        st.subheader("🏆 종목별 수익률 랭킹")
        df_sorted = df.sort_values('Return (%)', ascending=True)
        # 색상 배열 생성
        colors = ['#ff2e2e' if x >= 0 else '#0059b3' for x in df_sorted['Return (%)']]
        
        fig_bar = go.Figure(go.Bar(
            x=df_sorted['Return (%)'],
            y=df_sorted['Ticker'],
            orientation='h',
            marker_color=colors,
            text=df_sorted['Return (%)'].apply(lambda x: f"{x:.1f}%"),
            textposition='auto'
        ))
        fig_bar.update_layout(xaxis_title="수익률 (%)", margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig_bar, use_container_width=True)

    # 3. 자산 구성 (Donut Chart)
    with c2:
        st.subheader("🍩 자산 구성 (비중)")
        fig_donut = px.pie(df, values='Value', names='Ticker', hole=0.4)
        fig_donut.update_traces(textposition='inside', textinfo='percent+label')
        fig_donut.update_layout(margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig_donut, use_container_width=True)

    # ------------------
    # Data Table
    # ------------------
    st.subheader("📋 상세 데이터")
    
    display_df = df[['Ticker', 'Sector', 'Quantity', 'Avg Price', 'Current Price', 'Return (%)', 'PnL', 'Value']]
    
    # 테이블 스타일링 (한국식 색상)
    def color_korean_style(val):
        if val > 0: color = '#ff2e2e' # 빨강
        elif val < 0: color = '#0059b3' # 파랑
        else: color = 'black'
        return f'color: {color}; font-weight: bold;'

    st.dataframe(
        display_df.style.format({
            'Avg Price': f'{currency_symbol}{fmt_str}',
            'Current Price': f'{currency_symbol}{fmt_str}',
            'Quantity': '{:,.2f}',
            'Return (%)': '{:,.2f}%',
            'PnL': f'{currency_symbol}{fmt_str}',
            'Value': f'{currency_symbol}{fmt_str}'
        }).map(color_korean_style, subset=['Return (%)', 'PnL']),
        use_container_width=True,
        hide_index=True
    )

else:
    st.info("왼쪽 사이드바에 데이터를 입력해주세요. (CSV 붙여넣기 추천)")
