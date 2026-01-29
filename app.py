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
st.set_page_config(page_title="Pro Portfolio Master", page_icon="💎", layout="wide")

st.markdown("""
<style>
    div[data-testid="stMetric"] { background-color: #f9f9f9; border: 1px solid #e0e0e0; padding: 15px; border-radius: 10px; }
    button[data-baseweb="tab"] { font-weight: bold; }
    .stSelectbox label { font-size: 1.0rem; font-weight: bold; color: #4e4e4e; }
    .stRadio label { font-size: 1.0rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. JSONBin.io 및 데이터 유틸리티
# -----------------------------------------------------------------------------
API_KEY = st.secrets["jsonbin"]["api_key"] if "jsonbin" in st.secrets else None
BIN_ID = st.secrets["jsonbin"]["bin_id"] if "jsonbin" in st.secrets else None

def load_data_from_cloud():
    """클라우드에서 데이터 불러오기"""
    if not API_KEY or not BIN_ID: return {}
    try:
        url = f"https://api.jsonbin.io/v3/b/{BIN_ID}/latest"
        res = requests.get(url, headers={"X-Master-Key": API_KEY})
        if res.status_code == 200:
            data = res.json().get("record", {})
            # 데이터 구조 호환성 처리
            if "portfolio" in data and isinstance(data["portfolio"], list):
                return {"profiles": {"Default": data["portfolio"]}}
            if "profiles" in data: return data
            return {"profiles": {"Default": []}}
        return {"profiles": {"Default": []}}
    except: return {"profiles": {"Default": []}}

def save_data_to_cloud(full_data):
    """클라우드에 데이터 저장하기"""
    if not API_KEY or not BIN_ID: return False
    try:
        url = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
        headers = {"Content-Type": "application/json", "X-Master-Key": API_KEY}
        res = requests.put(url, json=full_data, headers=headers)
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

def fetch_stock_data(ticker):
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

@st.cache_data(ttl=60) 
def get_stock_info_cached(ticker):
    return fetch_stock_data(ticker)

# -----------------------------------------------------------------------------
# 3. 세션 및 로직 (핵심: 자동 저장 적용)
# -----------------------------------------------------------------------------
if 'full_data' not in st.session_state:
    st.session_state.full_data = {"profiles": {"Default": []}}

# 앱 최초 실행 시 클라우드 로드
if 'init_load' not in st.session_state:
    cloud_data = load_data_from_cloud()
    if cloud_data: st.session_state.full_data = cloud_data
    st.session_state.init_load = True

if 'current_profile' not in st.session_state:
    st.session_state.current_profile = "Default"

def get_current_portfolio():
    return st.session_state.full_data["profiles"].get(st.session_state.current_profile, [])

def update_portfolio_and_save(new_list):
    """
    [핵심 변경] 포트폴리오를 업데이트하고 즉시 클라우드에 저장합니다.
    """
    # 1. 세션 업데이트 (화면 반영)
    st.session_state.full_data["profiles"][st.session_state.current_profile] = new_list
    
    # 2. 클라우드 자동 저장 (백그라운드)
    if save_data_to_cloud(st.session_state.full_data):
        st.toast("☁️ 변경사항이 클라우드에 자동 저장되었습니다!", icon="✅")
    else:
        st.toast("⚠️ 저장 실패! API 설정을 확인하세요.", icon="❌")

def add_stock(ticker, avg_price, qty):
    info = get_stock_info_cached(ticker.strip().upper())
    if info['valid']:
        current_list = get_current_portfolio()
        current_list.append({
            'Ticker': ticker.strip().upper(),
            'Avg Price': float(avg_price),
            'Quantity': float(qty),
            'Current Price': info['current_price'],
            'Sector': info['sector'],
            'Market Cap Class': info['market_cap_class']
        })
        # 추가 즉시 저장
        update_portfolio_and_save(current_list)
        return True
    return False

def refresh_prices():
    current_list = get_current_portfolio()
    updated_list = []
    progress_bar = st.progress(0)
    for i, item in enumerate(current_list):
        new_info = fetch_stock_data(item['Ticker'])
        if new_info['valid']:
            item['Current Price'] = new_info['current_price']
            item['Sector'] = new_info['sector']
            item['Market Cap Class'] = new_info['market_cap_class']
        updated_list.append(item)
        progress_bar.progress((i + 1) / len(current_list))
    progress_bar.empty()
    # 가격 갱신 후 자동 저장
    update_portfolio_and_save(updated_list)
    st.toast("시세 업데이트 완료 및 저장됨!", icon="🔄")

def process_csv(txt):
    try:
        df = pd.read_csv(io.StringIO(txt), header=None, names=['Ticker', 'Price', 'Qty'])
        cnt = sum(add_stock(str(r['Ticker']), r['Price'], r['Qty']) for _, r in df.iterrows())
        if cnt > 0: st.sidebar.success(f"{cnt}개 추가 완료!")
    except Exception as e: st.sidebar.error(f"오류: {e}")

# -----------------------------------------------------------------------------
# 4. 사이드바
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("👥 프로필 & 설정")
    
    # API 키 상태 점검
    if not API_KEY or not BIN_ID:
        st.error("🚨 Secrets(API Key)가 설정되지 않았습니다! 저장이 불가능합니다.")
    
    prof_keys = list(st.session_state.full_data["profiles"].keys())
    sel_prof = st.selectbox("프로필 선택", prof_keys, index=prof_keys.index(st.session_state.current_profile) if st.session_state.current_profile in prof_keys else 0)
    
    if sel_prof != st.session_state.current_profile:
        st.session_state.current_profile = sel_prof
        st.rerun()

    with st.expander("➕ 프로필 관리"):
        new_p = st.text_input("새 프로필 이름")
        if st.button("생성"):
            if new_p and new_p not in st.session_state.full_data["profiles"]:
                st.session_state.full_data["profiles"][new_p] = []
                st.session_state.current_profile = new_p
                # 프로필 생성 시 자동 저장
                save_data_to_cloud(st.session_state.full_data)
                st.rerun()
        
        if len(prof_keys) > 1 and st.button("현재 프로필 삭제", type="primary"):
            del st.session_state.full_data["profiles"][st.session_state.current_profile]
            st.session_state.current_profile = list(st.session_state.full_data["profiles"].keys())[0]
            save_data_to_cloud(st.session_state.full_data)
            st.rerun()

    st.divider()
    
    # 수동 저장 버튼 (혹시 몰라 유지하되, 자동 저장이 기본임)
    if st.button("강제 클라우드 저장 (Manual Save)", use_container_width=True): 
        if save_data_to_cloud(st.session_state.full_data): st.toast("저장 완료!", icon="💾")
        else: st.error("저장 실패")

    st.divider()
    currency_mode = st.radio("통화", ["USD ($)", "KRW (₩)"], horizontal=True)
    ex_rate = get_exchange_rate()
    if currency_mode == "KRW (₩)": st.caption(f"환율: {ex_rate:,.2f} 원")
    
    t1, t2 = st.tabs(["CSV", "개별"])
    with t1:
        if st.button("CSV 추가"): process_csv(st.text_area("티커,가격,수량"))
    with t2:
        t, p, q = st.text_input("티커"), st.number_input("매수가($)"), st.number_input("수량")
        if st.button("추가"): add_stock(t, p, q)
    
    st.markdown("---")
    if st.button("🔄 시세 새로고침", use_container_width=True): refresh_prices(); st.rerun()

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title(f"📊 {st.session_state.current_profile}'s Portfolio")

portfolio_data = get_current_portfolio()

if portfolio_data:
    df = pd.DataFrame(portfolio_data)
    
    # 계산 로직
    df['Invested_USD'] = df['Avg Price'] * df['Quantity']
    df['Value_USD'] = df['Current Price'] * df['Quantity']
    df['PnL_USD'] = df['Value_USD'] - df['Invested_USD']
    df['Return (%)'] = (df['PnL_USD'] / df['Invested_USD']) * 100
    
    is_krw = currency_mode == "KRW (₩)"
    rate = ex_rate if is_krw else 1.0
    sym, fmt = ("₩", '{:,.0f}') if is_krw else ("$", '{:,.2f}')

    df['Invested_Disp'] = df['Invested_USD'] * rate
    df['Value_Disp'] = df['Value_USD'] * rate
    df['PnL_Disp'] = df['PnL_USD'] * rate

    # 상단 메트릭
    tot_inv = df['Invested_Disp'].sum()
    tot_val = df['Value_Disp'].sum()
    tot_pnl = df['PnL_Disp'].sum()
    tot_ret = (df['PnL_USD'].sum() / df['Invested_USD'].sum() * 100) if df['Invested_USD'].sum() else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 매수", f"{sym}{tot_inv:,.0f}" if is_krw else f"${tot_inv:,.2f}")
    c2.metric("총 평가", f"{sym}{tot_val:,.0f}" if is_krw else f"${tot_val:,.2f}")
    c3.metric("총 손익", f"{sym}{tot_pnl:,.0f}" if is_krw else f"${tot_pnl:,.2f}", delta=f"{tot_pnl:,.0f}" if is_krw else f"{tot_pnl:,.2f}")
    c4.metric("수익률", f"{tot_ret:.2f}%", delta=f"{tot_ret:.2f}%")

    st.divider()

    # --- 차트 ---
    st.subheader("📈 포트폴리오 시각화")
    tab1, tab2 = st.tabs(["🧩 종합 분석", "💹 수익률 분석"])
    
    with tab1:
        st.markdown("##### 🗺️ 자산 지도")
        fig_tree = px.treemap(df, path=[px.Constant("Total"), 'Sector', 'Ticker'], values='Value_Disp',
                              color='Return (%)', color_continuous_scale=['#0059b3', '#f0f0f0', '#ff2e2e'], color_continuous_midpoint=0)
        fig_tree.update_traces(textinfo="label+value+percent entry")
        st.plotly_chart(fig_tree, use_container_width=True)

        c_chart1, c_chart2 = st.columns(2)
        with c_chart1:
            st.markdown("##### 🍰 섹터 비중")
            fig_sec = px.pie(df, values='Value_Disp', names='Sector', hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
            fig_sec.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_sec, use_container_width=True)
        with c_chart2:
            st.markdown("##### 🏗️ 시총 규모")
            cap_order = ["Mega Cap (초대형주)", "Large Cap (대형주)", "Mid Cap (중형주)", "Small Cap (소형주)", "Micro Cap (초소형주)", "Unknown"]
            df_cap = df.groupby('Market Cap Class')['Value_Disp'].sum().reset_index()
            fig_cap = px.bar(df_cap, x='Market Cap Class', y='Value_Disp', color='Market Cap Class', category_orders={"Market Cap Class": cap_order}, text_auto='.2s')
            fig_cap.update_layout(showlegend=False)
            st.plotly_chart(fig_cap, use_container_width=True)

    with tab2:
        c_r1, c_r2 = st.columns(2)
        with c_r1:
            st.markdown("##### 🏭 섹터별 수익률")
            df_sec_ret = df.groupby('Sector')['Return (%)'].mean().reset_index().sort_values('Return (%)', ascending=False)
            colors_sec = ['#ff2e2e' if x >= 0 else '#0059b3' for x in df_sec_ret['Return (%)']]
            fig_sec_ret = go.Figure(go.Bar(x=df_sec_ret['Sector'], y=df_sec_ret['Return (%)'], marker_color=colors_sec))
            st.plotly_chart(fig_sec_ret, use_container_width=True)
        with c_r2:
            st.markdown("##### 🏆 종목 랭킹")
            df_rank = df.sort_values('Return (%)', ascending=True)
            colors_rank = ['#ff2e2e' if x >= 0 else '#0059b3' for x in df_rank['Return (%)']]
            fig_rank = go.Figure(go.Bar(x=df_rank['Return (%)'], y=df_rank['Ticker'], orientation='h', marker_color=colors_rank))
            st.plotly_chart(fig_rank, use_container_width=True)

    st.divider()

    # --- 정렬 및 편집 ---
    st.subheader("📝 상세 데이터 관리 (자동 저장됨)")
    
    # 정렬 UI
    c_s1, c_s2 = st.columns([1, 2])
    with c_s1:
        sort_opt = st.selectbox("정렬 기준", ["평가금액", "수익률", "티커", "섹터", "보유수량"])
    with c_s2:
        sort_ord = st.radio("정렬 순서", ["내림차순 (▼)", "오름차순 (▲)"], horizontal=True)

    # 정렬 로직
    sort_map = {"평가금액": "Value_Disp", "수익률": "Return (%)", "티커": "Ticker", "섹터": "Sector", "보유수량": "Quantity"}
    asc = False if "내림차순" in sort_ord else True
    df_sorted = df.sort_values(by=sort_map[sort_opt], ascending=asc).reset_index(drop=True)

    edit_df = df_sorted[['Ticker', 'Sector', 'Market Cap Class', 'Avg Price', 'Quantity', 'Current Price', 'Return (%)', 'Value_Disp']].copy()
    edit_df.columns = ['Ticker', 'Sector', 'Market Cap', 'Avg Price ($)', 'Quantity', 'Current Price ($)', 'Return (%)', f'Valuation ({sym})']

    edited_df = st.data_editor(
        edit_df,
        column_config={
            "Ticker": st.column_config.TextColumn(disabled=True),
            "Sector": st.column_config.TextColumn(disabled=True),
            "Market Cap": st.column_config.TextColumn(disabled=True),
            "Avg Price ($)": st.column_config.NumberColumn(min_value=0, format="%.2f", required=True),
            "Quantity": st.column_config.NumberColumn(min_value=0, format="%.4f", required=True),
            "Current Price ($)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "Return (%)": st.column_config.NumberColumn(disabled=True, format="%.2f%"),
            f"Valuation ({sym})": st.column_config.NumberColumn(disabled=True, format="%.0f" if is_krw else "%.2f"),
        },
        use_container_width=True,
        num_rows="dynamic",
        key="editor"
    )

    # 변경 감지 및 자동 저장
    if not edit_df.equals(edited_df):
        new_portfolio = []
        for index, row in edited_df.iterrows():
            ticker = row['Ticker']
            try:
                # 메타데이터 보존
                original_row = df[df['Ticker'] == ticker].iloc[0]
                sector = original_row['Sector']
                mkt_cap = original_row['Market Cap Class']
                curr_price = original_row['Current Price']
            except:
                sector, mkt_cap, curr_price = "Unknown", "Unknown", 0.0

            new_portfolio.append({
                'Ticker': ticker,
                'Avg Price': float(row['Avg Price ($)']),
                'Quantity': float(row['Quantity']),
                'Current Price': float(curr_price),
                'Sector': sector,
                'Market Cap Class': mkt_cap
            })
        
        # [자동 저장 트리거]
        update_portfolio_and_save(new_portfolio)
        st.rerun()

else:
    st.info("👈 데이터를 입력해주세요.")
