import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# === 页面配置 ===
st.set_page_config(page_title="全球资产看板", layout="wide", page_icon="🌏")

# === 🛠️ 紧急修复工具：重置按钮 ===
st.sidebar.header("⚙️ 设置")
if st.sidebar.button("🗑️ 重置所有数据 (修复卡顿)", help="如果你发现页面白屏或卡住，请点此按钮"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# === 1. 初始化基础数据 ===
if 'portfolio_setup_v2' not in st.session_state:
    # 定义基础列
    base_cols_cn = ["code", "name", "cost", "qty", "exp_div", "buy_yld", "sell_yld"]
    base_cols_us = ["code", "name", "cost", "qty"]
    
    # 初始化默认数据
    st.session_state.cn_inputs = pd.DataFrame([
        {"code": "601919.SS", "name": "中远海控", "cost": 10.0, "qty": 1000, "exp_div": 1.5, "buy_yld": 12.0, "sell_yld": 5.0},
        {"code": "600900.SS", "name": "长江电力", "cost": 22.0, "qty": 500, "exp_div": 0.9, "buy_yld": 4.0, "sell_yld": 2.0},
        {"code": "0941.HK",    "name": "中国移动HK", "cost": 65.0, "qty": 500, "exp_div": 4.8, "buy_yld": 7.0, "sell_yld": 3.0},
    ], columns=base_cols_cn)
    
    st.session_state.sg_inputs = pd.DataFrame([
        {"code": "C38U.SI", "name": "CapLand IntCom", "cost": 1.90, "qty": 2000, "exp_div": 0.10, "buy_yld": 6.0, "sell_yld": 4.0},
        {"code": "M44U.SI", "name": "Mapletree Log",  "cost": 1.50, "qty": 3000, "exp_div": 0.08, "buy_yld": 6.5, "sell_yld": 4.5},
    ], columns=base_cols_cn)

    st.session_state.us_inputs = pd.DataFrame([
        {"code": "VOO",  "name": "标普500 ETF", "cost": 400.0, "qty": 10},
        {"code": "NVDA", "name": "英伟达",       "cost": 450.0, "qty": 5},
        {"code": "AAPL", "name": "苹果",         "cost": 170.0, "qty": 10},
    ], columns=base_cols_us)
    
    st.session_state.portfolio_setup_v2 = True

# === 2. 侧边栏：资产录入与汇率 ===
st.sidebar.header("💰 现金与固收")

@st.cache_data(ttl=3600)
def get_exchange_rates():
    try:
        tickers = yf.Tickers("CNY=X SGDCNY=X")
        usd_cny = tickers.tickers['CNY=X'].fast_info['last_price']
        sgd_cny = tickers.tickers['SGDCNY=X'].fast_info['last_price']
        return usd_cny, sgd_cny
    except:
        return 7.2, 5.3

usd_rate, sgd_rate = get_exchange_rates()
st.sidebar.caption(f"参考汇率: USD/CNY ≈ {usd_rate:.2f} | SGD/CNY ≈ {sgd_rate:.2f}")

with st.sidebar.form("cash_bond_form"):
    cash_cny = st.number_input("🇨🇳 人民币现金 (CNY)", value=50000.0, step=1000.0)
    cash_sgd = st.number_input("🇸🇬 新币现金 (SGD)", value=10000.0, step=100.0)
    cash_usd = st.number_input("🇺🇸 美元现金 (USD)", value=5000.0, step=100.0)
    bond_usd_val = st.number_input("🇺🇸 美债直持现值 (USD)", value=20000.0)
    st.form_submit_button("更新资产状态")

# === 3. 核心逻辑：计算函数 (增强版) ===
def calculate_market_data(input_df, currency_rate=1.0, mode='yield'):
    df = input_df.copy()
    
    # 预定义所有需要的列，防止因空数据导致 Key Error
    required_cols = ['price', 'change_pct', 'change_amt', 'mkt_val_local', 'mkt_val_cny', 'profit_cny', 'yield_now', 'action', 'total_return_pct']
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0.0
    
    # 清理空行
    df = df[df['code'].notna() & (df['code'] != "")]
    if df.empty: return df

    tickers = " ".join(df['code'].tolist())
    
    try:
        data = yf.Tickers(tickers)
    except Exception:
        return df # 保持默认值返回

    current_prices = []
    day_changes = []
    day_changes_pct = []

    for code in df['code']:
        try:
            info = data.tickers[code].fast_info
            price = info['last_price']
            prev = info['previous_close']
            
            if price is None: price = 0.0
            if prev is None: prev = 0.0
            
            current_prices.append(price)
            change = price - prev if prev else 0
            pct = (change / prev * 100) if prev > 0 else 0
            
            day_changes.append(change)
            day_changes_pct.append(pct)
        except:
            current_prices.append(0.0)
            day_changes.append(0.0)
            day_changes_pct.append(0.0)

    df['price'] = current_prices
    df['change_pct'] = day_changes_pct
    df['change_amt'] = day_changes
    
    # 价值计算
    df['mkt_val_local'] = df['price'] * df['qty']
    df['mkt_val_cny'] = df['mkt_val_local'] * currency_rate
    df['profit_cny'] = (df['price'] - df['cost']) * df['qty'] * currency_rate
    
    # 策略逻辑
    if mode == 'yield':
        df['yield_now'] = df.apply(lambda x: (x['exp_div'] / x['price'] * 100) if x['price'] > 0 else 0, axis=1)
        def get_signal(row):
            if row['price'] <= 0: return "❌"
            if row['yield_now'] >= row['buy_yld']: return "🟢 买入"
            elif row['yield_now'] <= row['sell_yld']: return "🔴 卖出"
            else: return "⚪ 持有"
        df['action'] = df.apply(get_signal, axis=1)
    
    elif mode == 'growth':
        df['total_return_pct'] = df.apply(lambda x: ((x['price'] - x['cost']) / x['cost'] * 100) if x['cost'] > 0 else 0, axis=1)
        
    return df

# === 4. 主界面构建 (带错误捕获) ===
st.title("🌏 个人全球资产概览")
st.caption("本位币: CNY (人民币) | 编辑表格后按回车自动计算")

try:
    # 获取计算结果
    with st.spinner('正在同步全球数据...'):
        df_cn_calc = calculate_market_data(st.session_state.cn_inputs, 1.0, mode='yield')
        df_sg_calc = calculate_market_data(st.session_state.sg_inputs, sgd_rate, mode='yield')
        df_us_calc = calculate_market_data(st.session_state.us_inputs, usd_rate, mode='growth')

    # 总资产计算
    total_stock_cny = df_cn_calc['mkt_val_cny'].sum() + df_sg_calc['mkt_val_cny'].sum() + df_us_calc['mkt_val_cny'].sum()
    total_cash_cny = cash_cny + (cash_sgd * sgd_rate) + (cash_usd * usd_rate)
    total_bond_cny = bond_usd_val * usd_rate
    net_worth = total_stock_cny + total_cash_cny + total_bond_cny

    # 盈亏计算
    total_profit = df_cn_calc['profit_cny'].sum() + df_sg_calc['profit_cny'].sum() + df_us_calc['profit_cny'].sum()
    total_day_gain = (df_cn_calc['change_amt'] * df_cn_calc['qty']).sum() + \
                     (df_sg_calc['change_amt'] * df_sg_calc['qty'] * sgd_rate).sum() + \
                     (df_us_calc['change_amt'] * df_us_calc['qty'] * usd_rate).sum()

    # 顶部核心指标
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 总净值 (CNY)", f"¥{net_worth:,.0f}")
    c2.metric("📅 今日波动", f"¥{total_day_gain:+,.0f}", delta_color="normal")
    c3.metric("🚀 股票总回报", f"¥{total_profit:+,.0f}", f"{(total_profit/(total_stock_cny-total_profit)*100):.1f}%" if (total_stock_cny-total_profit)!=0 else "0%")

    st.markdown("---")

    # 分页展示
    tab1, tab2, tab3, tab4 = st.tabs(["📈 统计图表", "🇨🇳 A股/港股", "🇸🇬 SG Reits", "🇺🇸 美股/ETF"])

    # Tab 1: 统计
    with tab1:
        st.subheader("资产透视")
        col_a, col_b = st.columns(2)
        
        with col_a:
            assets = {
                'A股/港股': df_cn_calc['mkt_val_cny'].sum(),
                '新加坡REITs': df_sg_calc['mkt_val_cny'].sum(),
                '美股/ETF': df_us_calc['mkt_val_cny'].sum(),
                '美债': total_bond_cny,
                '现金': total_cash_cny
            }
            fig_pie = px.pie(values=list(assets.values()), names=list(assets.keys()), title="资产配置 (CNY)")
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_b:
            cost_cn = (st.session_state.cn_inputs['cost'] * st.session_state.cn_inputs['qty']).sum()
            cost_sg = (st.session_state.sg_inputs['cost'] * st.session_state.sg_inputs['qty'] * sgd_rate).sum()
            cost_us = (st.session_state.us_inputs['cost'] * st.session_state.us_inputs['qty'] * usd_rate).sum()
            
            val_cn = df_cn_calc['mkt_val_cny'].sum()
            val_sg = df_sg_calc['mkt_val_cny'].sum()
            val_us = df_us_calc['mkt_val_cny'].sum()

            fig_bar = go.Figure(data=[
                go.Bar(name='投入成本', x=['CN/HK', 'SG', 'US'], y=[cost_cn, cost_sg, cost_us]),
                go.Bar(name='当前市值', x=['CN/HK', 'SG', 'US'], y=[val_cn, val_sg, val_us])
            ])
            fig_bar.update_layout(barmode='group', title="盈亏对比 (CNY)")
            st.plotly_chart(fig_bar, use_container_width=True)

    # 辅助函数
    def render_stock_tab(key_suffix, input_df, calc_df, display_cols, currency_fmt):
        with st.expander("✏️ 编辑持仓 (修改后按Enter)", expanded=False):
            edited = st.data_editor(input_df, num_rows="dynamic", use_container_width=True, key=f"editor_{key_suffix}")
            if key_suffix == 'cn': st.session_state.cn_inputs = edited
            elif key_suffix == 'sg': st.session_state.sg_inputs = edited
            elif key_suffix == 'us': st.session_state.us_inputs = edited

        st.dataframe(
            calc_df[display_cols].style.format(currency_fmt).applymap(
                lambda v: 'color: green; font-weight: bold' if isinstance(v, str) and '买入' in v 
                else ('color: red; font-weight: bold' if isinstance(v, str) and '卖出' in v else ''), 
                subset=['action'] if 'action' in display_cols else None
            ),
            use_container_width=True, hide_index=True, height=400
        )

    # Tab 2: CN
    with tab2:
        render_stock_tab('cn', st.session_state.cn_inputs, df_cn_calc, 
            ['name', 'price', 'change_pct', 'yield_now', 'action', 'qty', 'mkt_val_local', 'profit_cny'],
            {'price': '¥{:.2f}', 'change_pct': '{:+.2f}%', 'yield_now': '{:.2f}%', 'mkt_val_local': '¥{:,.0f}', 'profit_cny': '¥{:+,.0f}'}
        )

    # Tab 3: SG
    with tab3:
        render_stock_tab('sg', st.session_state.sg_inputs, df_sg_calc,
            ['name', 'price', 'change_pct', 'yield_now', 'action', 'qty', 'mkt_val_local', 'profit_cny'],
            {'price': 'S${:.3f}', 'change_pct': '{:+.2f}%', 'yield_now': '{:.2f}%', 'mkt_val_local': 'S${:,.0f}', 'profit_cny': '¥{:+,.0f}'}
        )

    # Tab 4: US
    with tab4:
        with st.expander("✏️ 编辑持仓 (修改后按Enter)", expanded=False):
            edited_us = st.data_editor(st.session_state.us_inputs, num_rows="dynamic", use_container_width=True, key="editor_us")
            st.session_state.us_inputs = edited_us
            
        st.dataframe(
            df_us_calc[['name', 'price', 'change_pct', 'total_return_pct', 'qty', 'mkt_val_local', 'profit_cny']].style.format({
                'price': '${:.2f}', 'change_pct': '{:+.2f}%', 'total_return_pct': '{:+.2f}%',
                'mkt_val_local': '${:,.0f}', 'profit_cny': '¥{:+,.0f}'
            }).applymap(lambda v: 'color: green' if v > 0 else 'color: red', subset=['total_return_pct']),
            use_container_width=True, hide_index=True
        )

except Exception as e:
    st.error(f"⚠️ 发生错误: {e}")
    st.info("建议点击左侧栏的 '🗑️ 重置所有数据' 按钮尝试修复。")
