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
st.set_page_config(page_title="Pro Multi-Profile Portfolio", page_icon="👥", layout="wide")

st.markdown("""
<style>
    div[data-testid="stMetric"] { background-color: #f9f9f9; border: 1px solid #e0e0e0; padding: 15px; border-radius: 10px; }
    button[data-baseweb="tab"] { font-weight: bold; }
    .stSelectbox label { font-size: 1.2rem; font-weight: bold; color: #4e4e4e; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. JSONBin.io 통신 및 데이터 관리
# -----------------------------------------------------------------------------
API_KEY = st.secrets["jsonbin"]["api_key"] if "jsonbin" in st.secrets else None
BIN_ID = st.secrets["jsonbin"]["bin_id"] if "jsonbin" in st.secrets else None

def load_data_from_cloud():
    """클라우드에서 전체 프로필 데이터를 가져옴"""
    if not API_KEY or not BIN_ID: return {}
    try:
        url = f"https://api.jsonbin.io/v3/b/{BIN_ID}/latest"
        res = requests.get(url, headers={"X-Master-Key": API_KEY})
        if res.status_code == 200:
            data = res.json().get("record", {})
            
            # [호환성 처리] 예전 버전(리스트 형태) 데이터가 있다면 'Default' 프로필로 감싸줌
            if "portfolio" in data and isinstance(data["portfolio"], list):
                return {"profiles": {"Default": data["portfolio"]}}
            if "profiles" in data:
                return data
            return {"profiles": {"Default": []}}
        return {"profiles": {"Default": []}}
    except:
        return {"profiles": {"Default": []}}

def save_data_to_cloud(full_data):
    """전체 프로필 데이터를 클라우드에 저장"""
    if not API_KEY or not BIN_ID: return False
    try:
        url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
        headers = {"Content-Type": "application/json", "X-Master-Key": API_KEY}
        res = requests.put(url, json=full_data, headers=headers)
        return res.status_code == 200
    except: return False

# -----------------------------------------------------------------------------
# 3. 주식 정보 및 환율 (캐싱 적용)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_exchange_rate():
    try:
        # 환율 가져오기 (실패 시 1400원 고정)
        return yf.Ticker("KRW=X").fast_info.get('last_price', 1400.0)
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
# 4. 세션 초기화 및 로직
# -----------------------------------------------------------------------------
# 전체 데이터 구조: {'profiles': {'Default': [...], 'Kids': [...]}}
if 'full_data' not in st.session_state:
    st.session_state.full_data = {"profiles": {"Default": []}}

# 초기 로드 (앱 실행 시 1회)
if 'init_load' not in st.session_state:
    cloud_data = load_data_from_cloud()
    if cloud_data: st.session_state.full_data = cloud_data
    st.session_state.init_load = True

# 현재 선택된 프로필
if 'current_profile' not in st.session_state:
    st.session_state.current_profile = "Default"

def get_current_portfolio():
    return st.session_state.full_data["profiles"].get(st.session_state.current_profile, [])

def update_current_portfolio(new_list):
    st.session_state.full_data["profiles"][st.session_state.current_profile] = new_list

def add_stock(ticker, avg_price, qty):
    info = get_stock_info(ticker.strip().upper())
    if info['valid']:
        current_list = get_current_portfolio()
        current_list.append({
            'Ticker': ticker.strip().upper(),
            'Avg Price': float(avg_price), # USD 기준 저장
            'Quantity': float(qty),
            'Current Price': info['current_price'], # USD 기준 저장
            'Sector': info['sector'],
            'Market Cap Class': info['market_cap_class']
        })
        update_current_portfolio(current_list)
        return True
    return False

def process_csv(txt):
    try:
        df = pd.read_csv(io.StringIO(txt), header=None, names=['Ticker', 'Price', 'Qty'])
        cnt = sum(add_stock(str(r['Ticker']), r['Price'], r['Qty']) for _, r in df.iterrows())
        if cnt > 0: st.sidebar.success(f"{cnt}개 추가 완료!")
    except Exception as e: st.sidebar.error(f"오류: {e}")

# -----------------------------------------------------------------------------
# 5. 사이드바 UI (프로필 관리 및 입력)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("👥 프로필 관리")
    
    # 1. 프로필 선택
    profile_list = list(st.session_state.full_data["profiles"].keys())
    selected_profile = st.selectbox("현재 프로필", profile_list, index=profile_list.index(st.session_state.current_profile) if st.session_state.current_profile in profile_list else 0)
    
    if selected_profile != st.session_state.current_profile:
        st.session_state.current_profile = selected_profile
        st.rerun()

    # 2. 프로필 추가/삭제
    with st.expander("프로필 추가 / 삭제"):
        new_prof = st.text_input("새 프로필 이름")
        if st.button("새 프로필 생성"):
            if new_prof and new_prof not in st.session_state.full_data["profiles"]:
                st.session_state.full_data["profiles"][new_prof] = []
                st.session_state.current_profile = new_prof
                st.rerun()
            elif new_prof in st.session_state.full_data["profiles"]:
                st.error("이미 존재하는 이름입니다.")
        
        if len(profile_list) > 1:
            if st.button(f"🗑️ '{selected_profile}' 삭제", type="primary"):
                del st.session_state.full_data["profiles"][selected_profile]
                st.session_state.current_profile = list(st.session_state.full_data["profiles"].keys())[0]
                st.rerun()

    st.markdown("---")
    
    # 3. 클라우드 동기화
    st.subheader("☁️ 클라우드 동기화")
    c1, c2 = st.columns(2)
    if c1.button("📤 전체 저장", type="primary", use_container_width=True): 
        if save_data_to_cloud(st.session_state.full_data): st.toast("모든 프로필 저장 완료!", icon="💾")
    if c2.button("📥 불러오기", use_container_width=True):
        d = load_data_from_cloud()
        if d: 
            st.session_state.full_data = d
            st.rerun()

    st.markdown("---")
    
    # 4. 환율 및 입력
    currency_mode = st.radio("통화 선택", ["USD ($)", "KRW (₩)"], horizontal=True)
    ex_rate = get_exchange_rate()
    if currency_mode == "KRW (₩)": st.caption(f"ℹ️ 적용 환율: 1 USD = {ex_rate:,.2f} KRW")
    
    t1, t2 = st.tabs(["CSV 입력", "개별 입력"])
    with t1:
        if st.button("CSV 추가"): process_csv(st.text_area("티커,가격,수량"))
    with t2:
        t, p, q = st.text_input("티커"), st.number_input("매수가($)"), st.number_input("수량")
        if st.button("추가"): add_stock(t, p, q)
    
    if st.button("현재 프로필 초기화"): 
        st.session_state.full_data["profiles"][st.session_state.current_profile] = []
        st.rerun()

# -----------------------------------------------------------------------------
# 6. 메인 대시보드
# -----------------------------------------------------------------------------
st.title(f"📊 {st.session_state.current_profile}'s Portfolio")

portfolio_data = get_current_portfolio()

if portfolio_data:
    df = pd.DataFrame(portfolio_data)
    
    # --- [검증된 계산 로직] ---
    # 1. 먼저 USD 기준으로 모든 값을 계산합니다. (데이터 무결성)
    df['Invested_USD'] = df['Avg Price'] * df['Quantity']
    df['Value_USD'] = df['Current Price'] * df['Quantity']
    df['PnL_USD'] = df['Value_USD'] - df['Invested_USD']
    df['Return (%)'] = (df['PnL_USD'] / df['Invested_USD']) * 100
    
    # 2. 화면 표시용 변수를 만듭니다. (환율 적용은 여기서만!)
    is_krw = currency_mode == "KRW (₩)"
    
    if is_krw:
        sym, fmt = "₩", '{:,.0f}'
        # USD 컬럼에 환율을 곱해 새로운 Display 컬럼 생성
        df['Avg Price_Disp'] = df['Avg Price'] * ex_rate
        df['Current Price_Disp'] = df['Current Price'] * ex_rate
        df['Invested_Disp'] = df['Invested_USD'] * ex_rate
        df['Value_Disp'] = df['Value_USD'] * ex_rate
        df['PnL_Disp'] = df['PnL_USD'] * ex_rate
    else:
        sym, fmt = "$", '{:,.2f}'
        df['Avg Price_Disp'] = df['Avg Price']
        df['Current Price_Disp'] = df['Current Price']
        df['Invested_Disp'] = df['Invested_USD']
        df['Value_Disp'] = df['Value_USD']
        df['PnL_Disp'] = df['PnL_USD']

    # --- 상단 메트릭 ---
    tot_inv = df['Invested_Disp'].sum()
    tot_val = df['Value_Disp'].sum()
    tot_pnl = df['PnL_Disp'].sum()
    tot_ret = (df['PnL_USD'].sum() / df['Invested_USD'].sum() * 100) if df['Invested_USD'].sum() else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 매수 금액", f"{sym}{tot_inv:,.0f}" if is_krw else f"${tot_inv:,.2f}")
    c2.metric("총 평가 금액", f"{sym}{tot_val:,.0f}" if is_krw else f"${tot_val:,.2f}")
    c3.metric("총 손익", f"{sym}{tot_pnl:,.0f}" if is_krw else f"${tot_pnl:,.2f}", 
                   delta=f"{tot_pnl:,.0f}" if is_krw else f"{tot_pnl:,.2f}")
    c4.metric("총 수익률", f"{tot_ret:.2f}%", delta=f"{tot_ret:.2f}%")

    st.divider()

    # --- 차트 섹션 ---
    # 차트는 Value_Disp (환율 적용된 평가금액)을 기준으로 그립니다.
    st.subheader("📈 포트폴리오 분석")
    
    # 1. 트리맵
    fig_tree = px.treemap(df, path=[px.Constant("Total"), 'Sector', 'Ticker'], values='Value_Disp',
                          color='Return (%)', color_continuous_scale=['#0059b3', '#f0f0f0', '#ff2e2e'], color_continuous_midpoint=0)
    fig_tree.update_traces(textinfo="label+value+percent entry")
    st.plotly_chart(fig_tree, use_container_width=True)
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🥧 섹터 비중")
        fig_sec = px.pie(df, values='Value_Disp', names='Sector', hole=0.4)
        st.plotly_chart(fig_sec, use_container_width=True)
    with c2:
        st.markdown("#### 🏗️ 시총 규모")
        cap_order = ["Mega Cap (초대형주)", "Large Cap (대형주)", "Mid Cap (중형주)", "Small Cap (소형주)", "Micro Cap (초소형주)", "Unknown"]
        df_cap = df.groupby('Market Cap Class')['Value_Disp'].sum().reset_index()
        fig_cap = px.bar(df_cap, x='Market Cap Class', y='Value_Disp', color='Market Cap Class', category_orders={"Market Cap Class": cap_order})
        st.plotly_chart(fig_cap, use_container_width=True)

    # --- 데이터 테이블 ---
    st.markdown("#### 📋 상세 데이터")
    
    # 테이블 표시는 Display용 컬럼을 사용하되 이름은 깔끔하게 변경
    table_df = df[['Ticker', 'Sector', 'Quantity', 'Avg Price_Disp', 'Current Price_Disp', 'Return (%)', 'PnL_Disp', 'Value_Disp']].copy()
    table_df.columns = ['Ticker', 'Sector', 'Qty', 'Avg Price', 'Current Price', 'Return (%)', 'PnL', 'Value']

    st.dataframe(table_df.style.format({
        'Avg Price': f'{sym}{fmt}', 'Current Price': f'{sym}{fmt}', 'Qty': '{:,.2f}',
        'Return (%)': '{:.2f}%', 'PnL': f'{sym}{fmt}', 'Value': f'{sym}{fmt}'
    }).map(lambda x: f'color: {"#ff2e2e" if x>0 else "#0059b3" if x<0 else "black"}; font-weight: bold;', subset=['Return (%)', 'PnL']), 
    use_container_width=True, hide_index=True)

else:
    st.info(f"👈 '{st.session_state.current_profile}' 프로필이 비어있습니다. 데이터를 추가해주세요.")
