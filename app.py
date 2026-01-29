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
    .stSelectbox label { font-size: 1.2rem; font-weight: bold; color: #4e4e4e; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. JSONBin.io 및 데이터 유틸리티
# -----------------------------------------------------------------------------
API_KEY = st.secrets["jsonbin"]["api_key"] if "jsonbin" in st.secrets else None
BIN_ID = st.secrets["jsonbin"]["bin_id"] if "jsonbin" in st.secrets else None

def load_data_from_cloud():
    if not API_KEY or not BIN_ID: return {}
    try:
        url = f"https://api.jsonbin.io/v3/b/{BIN_ID}/latest"
        res = requests.get(url, headers={"X-Master-Key": API_KEY})
        if res.status_code == 200:
            data = res.json().get("record", {})
            if "portfolio" in data and isinstance(data["portfolio"], list):
                return {"profiles": {"Default": data["portfolio"]}}
            if "profiles" in data: return data
            return {"profiles": {"Default": []}}
        return {"profiles": {"Default": []}}
    except: return {"profiles": {"Default": []}}

def save_data_to_cloud(full_data):
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

# 캐시를 사용하되, 강제 새로고침을 위해 함수 분리
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
# 3. 세션 및 로직
# -----------------------------------------------------------------------------
if 'full_data' not in st.session_state:
    st.session_state.full_data = {"profiles": {"Default": []}}
if 'init_load' not in st.session_state:
    cloud_data = load_data_from_cloud()
    if cloud_data: st.session_state.full_data = cloud_data
    st.session_state.init_load = True
if 'current_profile' not in st.session_state:
    st.session_state.current_profile = "Default"

def get_current_portfolio():
    return st.session_state.full_data["profiles"].get(st.session_state.current_profile, [])

def update_current_portfolio(new_list):
    st.session_state.full_data["profiles"][st.session_state.current_profile] = new_list

def add_stock(ticker, avg_price, qty):
    info = get_stock_info_cached(ticker.strip().upper())
    if info['valid']:
        current_list = get_current_portfolio()
        # 중복 티커가 있으면 합치는 대신, 리스트에 추가 (개별 관리)
        current_list.append({
            'Ticker': ticker.strip().upper(),
            'Avg Price': float(avg_price),
            'Quantity': float(qty),
            'Current Price': info['current_price'],
            'Sector': info['sector'],
            'Market Cap Class': info['market_cap_class']
        })
        update_current_portfolio(current_list)
        return True
    return False

def refresh_prices():
    """모든 종목의 현재가를 최신으로 업데이트"""
    current_list = get_current_portfolio()
    updated_list = []
    progress_bar = st.progress(0)
    for i, item in enumerate(current_list):
        # 캐시 없이 직접 호출
        new_info = fetch_stock_data(item['Ticker'])
        if new_info['valid']:
            item['Current Price'] = new_info['current_price']
            item['Sector'] = new_info['sector'] # 섹터 정보도 갱신
            item['Market Cap Class'] = new_info['market_cap_class']
        updated_list.append(item)
        progress_bar.progress((i + 1) / len(current_list))
    progress_bar.empty()
    update_current_portfolio(updated_list)
    st.toast("모든 시세가 업데이트되었습니다!", icon="🔄")

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
    
    # 프로필 관리
    prof_keys = list(st.session_state.full_data["profiles"].keys())
    sel_prof = st.selectbox("프로필", prof_keys, index=prof_keys.index(st.session_state.current_profile) if st.session_state.current_profile in prof_keys else 0)
    if sel_prof != st.session_state.current_profile:
        st.session_state.current_profile = sel_prof
        st.rerun()

    with st.expander("➕ 새 프로필 / 삭제"):
        new_p = st.text_input("이름")
        if st.button("생성"):
            if new_p and new_p not in st.session_state.full_data["profiles"]:
                st.session_state.full_data["profiles"][new_p] = []
                st.session_state.current_profile = new_p
                st.rerun()
        if len(prof_keys) > 1 and st.button("현재 프로필 삭제", type="primary"):
            del st.session_state.full_data["profiles"][st.session_state.current_profile]
            st.session_state.current_profile = list(st.session_state.full_data["profiles"].keys())[0]
            st.rerun()

    st.divider()
    
    # 클라우드
    c1, c2 = st.columns(2)
    if c1.button("📤 저장", type="primary", use_container_width=True): 
        if save_data_to_cloud(st.session_state.full_data): st.toast("저장 완료!", icon="💾")
    if c2.button("📥 로드", use_container_width=True):
        d = load_data_from_cloud()
        if d: st.session_state.full_data = d; st.rerun()

    st.divider()
    
    # 설정 및 입력
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
    if st.button("🔄 현재가 새로고침", use_container_width=True):
        refresh_prices()
        st.rerun()

# -----------------------------------------------------------------------------
# 5. 메인 대시보드
# -----------------------------------------------------------------------------
st.title(f"📊 {st.session_state.current_profile}'s Portfolio")

portfolio_data = get_current_portfolio()

if portfolio_data:
    df = pd.DataFrame(portfolio_data)
    
    # 1. USD 기초 계산
    df['Invested_USD'] = df['Avg Price'] * df['Quantity']
    df['Value_USD'] = df['Current Price'] * df['Quantity']
    df['PnL_USD'] = df['Value_USD'] - df['Invested_USD']
    df['Return (%)'] = (df['PnL_USD'] / df['Invested_USD']) * 100
    
    # 2. 환율 적용 (Display용)
    is_krw = currency_mode == "KRW (₩)"
    rate = ex_rate if is_krw else 1.0
    sym, fmt = ("₩", '{:,.0f}') if is_krw else ("$", '{:,.2f}')

    # 계산 컬럼
    df['Invested_Disp'] = df['Invested_USD'] * rate
    df['Value_Disp'] = df['Value_USD'] * rate
    df['PnL_Disp'] = df['PnL_USD'] * rate

    # --- Metrics ---
    tot_inv = df['Invested_Disp'].sum()
    tot_val = df['Value_Disp'].sum()
    tot_pnl = df['PnL_Disp'].sum()
    tot_ret = (df['PnL_USD'].sum() / df['Invested_USD'].sum() * 100) if df['Invested_USD'].sum() else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 매수", f"{sym}{tot_inv:,.0f}" if is_krw else f"${tot_inv:,.2f}")
    c2.metric("총 평가", f"{sym}{tot_val:,.0f}" if is_krw else f"${tot_val:,.2f}")
    c3.metric("총 손익", f"{sym}{tot_pnl:,.0f}" if is_krw else f"${tot_pnl:,.2f}", 
              delta=f"{tot_pnl:,.0f}" if is_krw else f"{tot_pnl:,.2f}")
    c4.metric("수익률", f"{tot_ret:.2f}%", delta=f"{tot_ret:.2f}%")

    st.divider()

    # --- [NEW] 고급 분석 차트 ---
    st.subheader("📈 심층 분석 (Advanced Analytics)")
    
    tab_graph1, tab_graph2 = st.tabs(["포트폴리오 구성", "수익률 분석"])
    
    with tab_graph1:
        # 기존 트리맵 + 시총 + [NEW] 집중도 분석
        c_g1, c_g2 = st.columns([2, 1])
        with c_g1:
            fig_tree = px.treemap(df, path=[px.Constant("Total"), 'Sector', 'Ticker'], values='Value_Disp',
                                  color='Return (%)', color_continuous_scale=['#0059b3', '#f0f0f0', '#ff2e2e'], color_continuous_midpoint=0)
            fig_tree.update_traces(textinfo="label+value+percent entry")
            st.plotly_chart(fig_tree, use_container_width=True)
            
        with c_g2:
            st.markdown("#### 🎯 집중도 (Top 5)")
            # 상위 5개와 나머지 계산
            df_sorted_val = df.sort_values('Value_Disp', ascending=False)
            if len(df) > 5:
                top5 = df_sorted_val.head(5)
                others_val = df_sorted_val.iloc[5:]['Value_Disp'].sum()
                others_df = pd.DataFrame([{'Ticker': 'Others', 'Value_Disp': others_val}])
                df_concentration = pd.concat([top5[['Ticker', 'Value_Disp']], others_df])
            else:
                df_concentration = df_sorted_val[['Ticker', 'Value_Disp']]
                
            fig_conc = px.pie(df_concentration, values='Value_Disp', names='Ticker', hole=0.5)
            st.plotly_chart(fig_conc, use_container_width=True)

            st.markdown("#### 🏗️ 시총 규모")
            cap_order = ["Mega Cap (초대형주)", "Large Cap (대형주)", "Mid Cap (중형주)", "Small Cap (소형주)", "Micro Cap (초소형주)", "Unknown"]
            df_cap = df.groupby('Market Cap Class')['Value_Disp'].sum().reset_index()
            fig_cap = px.bar(df_cap, x='Market Cap Class', y='Value_Disp', color='Market Cap Class', category_orders={"Market Cap Class": cap_order})
            fig_cap.update_layout(showlegend=False)
            st.plotly_chart(fig_cap, use_container_width=True)

    with tab_graph2:
        # [NEW] 섹터별 수익률 비교 & 랭킹
        c_r1, c_r2 = st.columns(2)
        with c_r1:
            st.markdown("#### 🏭 섹터별 평균 수익률")
            # 섹터별 수익률 가중평균 or 단순평균 (여기선 단순평균 사용)
            df_sec_ret = df.groupby('Sector')['Return (%)'].mean().reset_index().sort_values('Return (%)', ascending=False)
            colors_sec = ['#ff2e2e' if x >= 0 else '#0059b3' for x in df_sec_ret['Return (%)']]
            fig_sec_ret = go.Figure(go.Bar(x=df_sec_ret['Sector'], y=df_sec_ret['Return (%)'], marker_color=colors_sec))
            fig_sec_ret.update_layout(yaxis_title="수익률 (%)")
            st.plotly_chart(fig_sec_ret, use_container_width=True)
            
        with c_r2:
            st.markdown("#### 🏆 종목별 수익률 랭킹")
            df_rank = df.sort_values('Return (%)', ascending=True)
            colors_rank = ['#ff2e2e' if x >= 0 else '#0059b3' for x in df_rank['Return (%)']]
            fig_rank = go.Figure(go.Bar(x=df_rank['Return (%)'], y=df_rank['Ticker'], orientation='h', marker_color=colors_rank))
            st.plotly_chart(fig_rank, use_container_width=True)

    st.divider()

    # --- [EDITABLE] 상세 데이터 테이블 ---
    st.subheader("📝 상세 데이터 수정")
    st.info("💡 팁: '매수단가($)'와 '수량'을 클릭하여 직접 수정할 수 있습니다. 행을 삭제하려면 왼쪽 체크박스를 선택하고 델리트 키를 누르세요.")

    # 편집용 데이터프레임 준비 (보여줄 컬럼만)
    # Streamlit Editor는 원본 Dataframe 구조를 유지해야 하므로, 편집 가능한 컬럼과 보여줄 컬럼을 정리
    # 편집은 USD 기준으로 하는 것이 정확하므로 USD 컬럼을 노출
    
    edit_df = df[['Ticker', 'Avg Price', 'Quantity', 'Current Price', 'Return (%)', 'Value_Disp']].copy()
    edit_df.columns = ['Ticker', 'Avg Price ($)', 'Quantity', 'Current Price ($)', 'Return (%)', f'Valuation ({sym})']

    # data_editor 설정
    edited_df = st.data_editor(
        edit_df,
        column_config={
            "Avg Price ($)": st.column_config.NumberColumn(min_value=0, format="%.2f", required=True),
            "Quantity": st.column_config.NumberColumn(min_value=0, format="%.4f", required=True),
            "Ticker": st.column_config.TextColumn(disabled=True), # 티커 수정은 금지 (API 연동 문제)
            "Current Price ($)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "Return (%)": st.column_config.NumberColumn(disabled=True, format="%.2f%"),
            f"Valuation ({sym})": st.column_config.NumberColumn(disabled=True, format="%.0f" if is_krw else "%.2f"),
        },
        use_container_width=True,
        num_rows="dynamic", # 행 삭제 가능
        key="editor"
    )

    # --- 수정 사항 반영 로직 ---
    # 편집된 데이터프레임(edited_df)과 원본(edit_df)이 다르면 세션 업데이트
    # 주의: 여기서 num_rows="dynamic"으로 행이 삭제되었는지 확인해야 함
    
    if not edit_df.equals(edited_df):
        # 1. 수정된 데이터프레임을 리스트(Dict) 형태로 변환
        new_portfolio = []
        
        # 원래 데이터(df)에서 섹터와 시총 정보 등을 가져오기 위해 병합
        # Ticker를 키로 사용하여 메타데이터 보존
        # (주의: 사용자가 행을 삭제했을 수 있으므로 edited_df 기준으로 순회)
        
        for index, row in edited_df.iterrows():
            ticker = row['Ticker']
            # 원본 데이터에서 해당 티커의 메타데이터(섹터 등) 찾기
            # 동명이인(중복 티커) 이슈가 있을 수 있으니 인덱스 매칭이 안전하지만, 
            # data_editor는 인덱스를 재정렬할 수 있음. 
            # 여기서는 간단히 기존 df의 인덱스를 보존한다고 가정하거나, 티커로 재매핑.
            
            # 가장 안전한 방법: 기존 df에서 해당 인덱스의 메타데이터 가져오기
            # edit_df와 edited_df는 인덱스가 공유됨 (삭제된 인덱스 제외)
            
            try:
                original_row = df.loc[index]
                sector = original_row['Sector']
                mkt_cap = original_row['Market Cap Class']
                # 가격은 API 최신값 유지를 위해 원본 current price 사용 (수정 불가 컬럼이므로)
                curr_price = original_row['Current Price']
            except KeyError:
                # 만약 인덱스가 없다면? (사용자가 행을 추가한 경우인데, 여기선 막음)
                # 혹시 모르니 기본값 처리
                sector = "Unknown"
                mkt_cap = "Unknown"
                curr_price = 0.0

            new_portfolio.append({
                'Ticker': ticker,
                'Avg Price': float(row['Avg Price ($)']),  # 수정된 값
                'Quantity': float(row['Quantity']),        # 수정된 값
                'Current Price': float(curr_price),
                'Sector': sector,
                'Market Cap Class': mkt_cap
            })
            
        # 2. 세션 스테이트 업데이트
        update_current_portfolio(new_portfolio)
        st.rerun()

else:
    st.info("👈 데이터를 입력하거나 불러와주세요.")
