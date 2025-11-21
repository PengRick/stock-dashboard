import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# === 页面配置 ===
st.set_page_config(page_title="全球资产看板", layout="wide", page_icon="🌏")

# === 1. 初始化 Session State (数据存储) ===
if 'portfolio' not in st.session_state:
    # A股/港股 (高股息策略)
    st.session_state.cn_stocks = pd.DataFrame([
        {"code": "601919.SS", "name": "中远海控", "cost": 10.0, "qty": 1000, "exp_div": 1.5, "buy_yld": 12.0, "sell_yld": 5.0},
        {"code": "600900.SS", "name": "长江电力", "cost": 22.0, "qty": 500, "exp_div": 0.9, "buy_yld": 4.0, "sell_yld": 2.0},
        {"code": "0941.HK",    "name": "中国移动HK", "cost": 65.0, "qty": 500, "exp_div": 4.8, "buy_yld": 7.0, "sell_yld": 3.0},
    ])
    
    # 新加坡 REITs (高股息策略)
    st.session_state.sg_reits = pd.DataFrame([
        {"code": "C38U.SI", "name": "CapLand IntCom", "cost": 1.90, "qty": 2000, "exp_div": 0.10, "buy_yld": 6.0, "sell_yld": 4.0},
        {"code": "M44U.SI", "name": "Mapletree Log",  "cost": 1.50, "qty": 3000, "exp_div": 0.08, "buy_yld": 6.5, "sell_yld": 4.5},
    ])

    # 美股/ETF (成长/定投策略)
    st.session_state.us_stocks = pd.DataFrame([
        {"code": "VOO",  "name": "标普500 ETF", "cost": 400.0, "qty": 10},
        {"code": "NVDA", "name": "英伟达",       "cost": 450.0, "qty": 5},
        {"code": "AAPL", "name": "苹果",         "cost": 170.0, "qty": 10},
    ])

# === 2. 侧边栏：资产录入与汇率 ===
st.sidebar.header("💰 现金与固收 (手动)")

# 汇率获取函数
@st.cache_data(ttl=3600) # 缓存1小时
def get_exchange_rates():
    try:
        tickers = yf.Tickers("CNY=X SGDCNY=X")
        usd_cny = tickers.tickers['CNY=X'].fast_info['last_price']
        sgd_cny = tickers.tickers['SGDCNY=X'].fast_info['last_price']
        return usd_cny, sgd_cny
    except:
        return 7.2, 5.3 # 默认保底汇率

usd_rate, sgd_rate = get_exchange_rates()
st.sidebar.caption(f"参考汇率: USD/CNY ≈ {usd_rate:.2f} | SGD/CNY ≈ {sgd_rate:.2f}")

with st.sidebar.form("cash_bond_form"):
    st.write("请更新当前余额 (原币种):")
    cash_cny = st.number_input("🇨🇳 人民币现金 (CNY)", value=50000.0, step=1000.0)
    cash_sgd = st.number_input("🇸🇬 新币现金 (SGD)", value=10000.0, step=100.0)
    cash_usd = st.number_input("🇺🇸 美元现金 (USD)", value=5000.0, step=100.0)
    bond_usd_val = st.number_input("🇺🇸 美债直持现值 (USD)", value=20000.0, help="直接持有美债的当前总市值")
    st.form_submit_button("更新资产状态")

# === 3. 核心逻辑：获取行情 ===
def get_realtime_data(df, currency_rate=1.0, mode='yield'):
    if df.empty: return df
    
    tickers = " ".join(df['code'].tolist())
    try:
        data = yf.Tickers(tickers)
        
        current_prices = []
        day_changes = []
        day_changes_pct = []

        for code in df['code']:
            try:
                info = data.tickers[code].fast_info
                price = info['last_price']
                prev_close = info['previous_close']
                
                current_prices.append(price)
                change = price - prev_close
                day_changes.append(change)
                day_changes_pct.append((change / prev_close) * 100)
            except:
                current_prices.append(0.0)
                day_changes.append(0.0)
                day_changes_pct.append(0.0)

        df['price'] = current_prices
        df['change_amt'] = day_changes
        df['change_pct'] = day_changes_pct
        
        # 计算基础价值
        df['mkt_val_local'] = df['price'] * df['qty']          # 原币市值
        df['mkt_val_cny'] = df['mkt_val_local'] * currency_rate # 人民币市值
        df['profit_cny'] = (df['price'] - df['cost']) * df['qty'] * currency_rate # 人民币盈亏
        
        # 策略逻辑区分
        if mode == 'yield':
            df['yield_now'] = df.apply(lambda x: (x['exp_div'] / x['price'] * 100) if x['price'] > 0 else 0, axis=1)
            def get_signal(row):
                if row['price'] <= 0: return "❌"
                if row['yield_now'] >= row['buy_yld']: return "🟢 买入"
                elif row['yield_now'] <= row['sell_yld']: return "🔴 卖出"
                else: return "⚪ 持有"
            df['action'] = df.apply(get_signal, axis=1)
        
        elif mode == 'growth':
            df['total_return_pct'] = (df['price'] - df['cost']) / df['cost'] * 100
            
        return df
    except Exception as e:
        st.error(f"数据获取失败: {e}")
        return df

# === 4. 主界面 ===

st.title("🌏 个人全球资产概览")
st.caption("本位币: CNY (人民币) | 自动折算")

# 获取数据 (带Spinner)
with st.spinner('正在连接全球交易所...'):
    df_cn = get_realtime_data(st.session_state.cn_stocks, 1.0, mode='yield')
    df_sg = get_realtime_data(st.session_state.sg_reits, sgd_rate, mode='yield')
    df_us = get_realtime_data(st.session_state.us_stocks, usd_rate, mode='growth')

# --- 总资产计算 ---
total_stock_cny = df_cn['mkt_val_cny'].sum() + df_sg['mkt_val_cny'].sum() + df_us['mkt_val_cny'].sum()
total_cash_cny = cash_cny + (cash_sgd * sgd_rate) + (cash_usd * usd_rate)
total_bond_cny = bond_usd_val * usd_rate
net_worth = total_stock_cny + total_cash_cny + total_bond_cny

# 昨收估算 (用于计算当日总盈亏，简化算法)
day_gain_cn = (df_cn['change_amt'] * df_cn['qty']).sum()
day_gain_sg = (df_sg['change_amt'] * df_sg['qty'] * sgd_rate).sum()
day_gain_us = (df_us['change_amt'] * df_us['qty'] * usd_rate).sum()
total_day_gain = day_gain_cn + day_gain_sg + day_gain_us

# 累计总盈亏
total_profit = df_cn['profit_cny'].sum() + df_sg['profit_cny'].sum() + df_us['profit_cny'].sum()
# (注意：现金和债券这里暂未计算汇率波动盈亏，仅计算股票部分)

# --- 顶部核心指标 ---
c1, c2, c3 = st.columns(3)
c1.metric("💰 总净值 (CNY)", f"¥{net_worth:,.0f}")
c2.metric("📅 今日波动", f"¥{total_day_gain:+,.0f}", delta_color="normal")
c3.metric("🚀 股票总回报", f"¥{total_profit:+,.0f}", f"{(total_profit/(total_stock_cny-total_profit)*100):.1f}%")

st.markdown("---")

# --- 分页展示 ---
tab1, tab2, tab3, tab4 = st.tabs(["📈 统计与分析", "🇨🇳 A股/港股", "🇸🇬 SG Reits", "🇺🇸 美股/ETF"])

# Tab 1: 统计分析 (你的“增长趋势”需求)
with tab1:
    st.subheader("资金分布与增长")
    
    # 1. 资产配置饼图
    assets = {
        'A股/港股': df_cn['mkt_val_cny'].sum(),
        '新加坡REITs': df_sg['mkt_val_cny'].sum(),
        '美股/ETF': df_us['mkt_val_cny'].sum(),
        '美债': total_bond_cny,
        '现金': total_cash_cny
    }
    fig_pie = px.pie(values=list(assets.values()), names=list(assets.keys()), title="资产配置比例 (CNY)")
    st.plotly_chart(fig_pie, use_container_width=True)

    # 2. 成本 vs 现值 (展示增长)
    # 汇总各市场的成本和现值
    cost_vs_val = pd.DataFrame({
        'Market': ['CN/HK', 'SG', 'US'],
        'Cost': [
            (df_cn['cost']*df_cn['qty']).sum(),
            (df_sg['cost']*df_sg['qty']*sgd_rate).sum(),
            (df_us['cost']*df_us['qty']*usd_rate).sum()
        ],
        'Value': [
            df_cn['mkt_val_cny'].sum(),
            df_sg['mkt_val_cny'].sum(),
            df_us['mkt_val_cny'].sum()
        ]
    })
    
    fig_bar = go.Figure(data=[
        go.Bar(name='投入成本', x=cost_vs_val['Market'], y=cost_vs_val['Cost']),
        go.Bar(name='当前市值', x=cost_vs_val['Market'], y=cost_vs_val['Value'])
    ])
    fig_bar.update_layout(barmode='group', title="各市场 投入成本 vs 当前市值 (CNY)")
    st.plotly_chart(fig_bar, use_container_width=True)


# Tab 2: A股/港股 (高股息)
with tab2:
    st.caption("策略：高股息 | 关注：买卖阈值提醒")
    # 编辑器
    edited_cn = st.data_editor(
        df_cn[['code', 'name', 'qty', 'cost', 'exp_div', 'buy_yld', 'sell_yld']],
        column_config={"code":"代码", "qty":"股数", "exp_div":"预期股息", "buy_yld":"买入%", "sell_yld":"卖出%"},
        num_rows="dynamic",
        key="editor_cn"
    )
    # 展示结果
    show_cols = ['name', 'price', 'change_pct', 'yield_now', 'action', 'mkt_val_local', 'profit_cny']
    st.dataframe(
        df_cn[show_cols].style.format({
            'price': '{:.2f}', 'change_pct': '{:+.2f}%', 'yield_now': '{:.2f}%', 
            'mkt_val_local': '{:,.0f}', 'profit_cny': '{:+,.0f}'
        }),
        use_container_width=True, hide_index=True
    )
    if not edited_cn.equals(st.session_state.cn_stocks[['code', 'name', 'qty', 'cost', 'exp_div', 'buy_yld', 'sell_yld']]):
        st.session_state.cn_stocks = pd.merge(edited_cn, st.session_state.cn_stocks[['code']], on='code', how='left').fillna(0)
        st.rerun()

# Tab 3: 新加坡 REITs
with tab3:
    st.caption("策略：收息 REITs | 货币：SGD")
    edited_sg = st.data_editor(
        df_sg[['code', 'name', 'qty', 'cost', 'exp_div', 'buy_yld', 'sell_yld']],
        num_rows="dynamic",
        key="editor_sg"
    )
    show_cols_sg = ['name', 'price', 'change_pct', 'yield_now', 'action', 'mkt_val_local', 'profit_cny']
    st.dataframe(
        df_sg[show_cols_sg].style.format({
            'price': 'S${:.3f}', 'change_pct': '{:+.2f}%', 'yield_now': '{:.2f}%', 
            'mkt_val_local': 'S${:,.0f}', 'profit_cny': '¥{:+,.0f}'
        }),
        use_container_width=True, hide_index=True
    )

# Tab 4: 美股/ETF
with tab4:
    st.caption("策略：成长/定投 | 重点：总回报率")
    edited_us = st.data_editor(
        df_us[['code', 'name', 'qty', 'cost']],
        num_rows="dynamic",
        key="editor_us"
    )
    # 美股不展示股息率，展示回报率
    show_cols_us = ['name', 'price', 'change_pct', 'total_return_pct', 'mkt_val_local', 'profit_cny']
    st.dataframe(
        df_us[show_cols_us].style.format({
            'price': '${:.2f}', 'change_pct': '{:+.2f}%', 'total_return_pct': '{:+.2f}%',
            'mkt_val_local': '${:,.0f}', 'profit_cny': '¥{:+,.0f}'
        }).applymap(lambda v: 'color: green' if v > 0 else 'color: red', subset=['total_return_pct']),
        use_container_width=True, hide_index=True
    )
