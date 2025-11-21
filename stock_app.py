import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# === 页面配置 ===
st.set_page_config(page_title="全球资产看板", layout="wide", page_icon="🌏")

# === 1. 初始化基础数据 (仅存储输入项) ===
# 我们把“输入项”和“计算项”彻底分开，避免循环冲突
if 'portfolio_setup' not in st.session_state:
    # 定义基础列，不要包含实时变动的列(如price)
    base_cols_cn = ["code", "name", "cost", "qty", "exp_div", "buy_yld", "sell_yld"]
    base_cols_us = ["code", "name", "cost", "qty"]
    
    # A股/港股初始化
    st.session_state.cn_inputs = pd.DataFrame([
        {"code": "601919.SS", "name": "中远海控", "cost": 10.0, "qty": 1000, "exp_div": 1.5, "buy_yld": 12.0, "sell_yld": 5.0},
        {"code": "600900.SS", "name": "长江电力", "cost": 22.0, "qty": 500, "exp_div": 0.9, "buy_yld": 4.0, "sell_yld": 2.0},
        {"code": "0941.HK",    "name": "中国移动HK", "cost": 65.0, "qty": 500, "exp_div": 4.8, "buy_yld": 7.0, "sell_yld": 3.0},
    ], columns=base_cols_cn)
    
    # 新加坡 REITs 初始化
    st.session_state.sg_inputs = pd.DataFrame([
        {"code": "C38U.SI", "name": "CapLand IntCom", "cost": 1.90, "qty": 2000, "exp_div": 0.10, "buy_yld": 6.0, "sell_yld": 4.0},
        {"code": "M44U.SI", "name": "Mapletree Log",  "cost": 1.50, "qty": 3000, "exp_div": 0.08, "buy_yld": 6.5, "sell_yld": 4.5},
    ], columns=base_cols_cn)

    # 美股/ETF 初始化
    st.session_state.us_inputs = pd.DataFrame([
        {"code": "VOO",  "name": "标普500 ETF", "cost": 400.0, "qty": 10},
        {"code": "NVDA", "name": "英伟达",       "cost": 450.0, "qty": 5},
        {"code": "AAPL", "name": "苹果",         "cost": 170.0, "qty": 10},
    ], columns=base_cols_us)

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

# === 3. 核心逻辑：计算函数 ===
def calculate_market_data(input_df, currency_rate=1.0, mode='yield'):
    # 复制一份数据，避免修改原始输入
    df = input_df.copy()
    
    # 清理空行
    df = df[df['code'].notna() & (df['code'] != "")]
    if df.empty: return df

    tickers = " ".join(df['code'].tolist())
    
    # 获取数据
    try:
        data = yf.Tickers(tickers)
    except:
        return df

    current_prices = []
    day_changes = []
    day_changes_pct = []

    for code in df['code']:
        try:
            # 尝试获取数据
            info = data.tickers[code].fast_info
            price = info['last_price']
            prev = info['previous_close']
            
            # 简单的异常值处理
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

    # 写入计算列
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

# === 4. 主界面构建 ===
st.title("🌏 个人全球资产概览")
st.caption("本位币: CNY (人民币) | 编辑表格后按回车自动计算")

# --- 关键步骤：先获取最新计算结果 ---
# 注意：这里使用 Session State 中的 INPUT 数据进行计算
with st.spinner('正在同步全球数据...'):
    df_cn_calc = calculate_market_data(st.session_state.cn_inputs, 1.0, mode='yield')
    df_sg_calc = calculate_market_data(st.session_state.sg_inputs, sgd_rate, mode='yield')
    df_us_calc = calculate_market_data(st.session_state.us_inputs, usd_rate, mode='growth')

# --- 总资产计算 (使用计算后的数据) ---
total_stock_cny = df_cn_calc['mkt_val_cny'].sum() + df_sg_calc['mkt_val_cny'].sum() + df_us_calc['mkt_val_cny'].sum()
total_cash_cny = cash_cny + (cash_sgd * sgd_rate) + (cash_usd * usd_rate)
total_bond_cny = bond_usd_val * usd_rate
net_worth = total_stock_cny + total_cash_cny
