import streamlit as st
import yfinance as yf
import pandas as pd

# === 页面配置 ===
st.set_page_config(page_title="我的高股息投资看板", layout="wide", page_icon="📈")

# === 1. 初始化数据 (Session State) ===
# 如果是第一次运行，加载默认股票池
if 'portfolio' not in st.session_state:
    # 默认股票列表 (代码后缀: SS=上海, SZ=深圳, HK=港股)
    default_data = [
        {"code": "601919.SS", "name": "中远海控", "cost": 10.0, "qty": 1000, "expected_div": 1.5, "buy_yield": 12.0, "sell_yield": 5.0},
        {"code": "603565.SS", "name": "中谷物流", "cost": 9.0,  "qty": 0,    "expected_div": 0.8, "buy_yield": 8.0,  "sell_yield": 3.0},
        {"code": "601668.SS", "name": "中国建筑", "cost": 5.5,  "qty": 2000, "expected_div": 0.3, "buy_yield": 6.0,  "sell_yield": 3.0},
        {"code": "600900.SS", "name": "长江电力", "cost": 22.0, "qty": 500,  "expected_div": 0.9, "buy_yield": 4.0,  "sell_yield": 2.0},
        {"code": "601088.SS", "name": "中国神华", "cost": 30.0, "qty": 0,    "expected_div": 2.5, "buy_yield": 9.0,  "sell_yield": 4.0},
        {"code": "600938.SS", "name": "中国海油", "cost": 18.0, "qty": 0,    "expected_div": 1.8, "buy_yield": 10.0, "sell_yield": 5.0},
        {"code": "000651.SZ", "name": "格力电器", "cost": 35.0, "qty": 100,  "expected_div": 2.8, "buy_yield": 7.0,  "sell_yield": 3.0},
        {"code": "600941.SS", "name": "中国移动", "cost": 90.0, "qty": 200,  "expected_div": 4.5, "buy_yield": 6.0,  "sell_yield": 3.0},
    ]
    st.session_state.portfolio = pd.DataFrame(default_data)

# === 2. 侧边栏：添加/管理股票 ===
st.sidebar.header("🛠️ 管理工具")
st.sidebar.write("在下方添加新股票或刷新数据")

with st.sidebar.form("add_stock_form"):
    new_code = st.text_input("股票代码 (如 600519.SS)", "")
    new_name = st.text_input("股票名称", "")
    submitted = st.form_submit_button("添加股票")
    if submitted and new_code and new_name:
        new_row = {"code": new_code, "name": new_name, "cost": 0.0, "qty": 0, "expected_div": 0.0, "buy_yield": 5.0, "sell_yield": 2.0}
        st.session_state.portfolio = pd.concat([st.session_state.portfolio, pd.DataFrame([new_row])], ignore_index=True)
        st.success(f"已添加 {new_name}")

if st.sidebar.button("🔄 强制刷新股价"):
    st.rerun()

# === 3. 核心逻辑：获取股价并计算 ===
def get_market_data(df):
    tickers = " ".join(df['code'].tolist())
    if not tickers:
        return df
    
    try:
        # 从 Yahoo Finance 批量获取数据
        data = yf.Tickers(tickers)
        
        # 创建临时列表存储计算结果
        current_prices = []
        
        for code in df['code']:
            try:
                # 获取最新收盘价 (fast_info 比 history 更快)
                price = data.tickers[code].fast_info['last_price']
                current_prices.append(price)
            except:
                current_prices.append(0.0) # 获取失败
        
        df['current_price'] = current_prices
        
        # 计算逻辑
        # 1. 股息率 = 预期每股分红 / 当前股价
        df['yield_now'] = df.apply(lambda x: (x['expected_div'] / x['current_price'] * 100) if x['current_price'] > 0 else 0, axis=1)
        
        # 2. 持仓市值
        df['market_value'] = df['current_price'] * df['qty']
        
        # 3. 浮动盈亏
        df['profit'] = (df['current_price'] - df['cost']) * df['qty']
        
        # 4. 仓位比例 (计算总市值后处理)
        total_asset = df['market_value'].sum()
        df['weight'] = df.apply(lambda x: (x['market_value'] / total_asset * 100) if total_asset > 0 else 0, axis=1)
        
        # 5. 操作建议 (Signal)
        def get_signal(row):
            if row['current_price'] <= 0: return "数据错误"
            if row['yield_now'] >= row['buy_yield']:
                return "🟢 极低估 (买入)"
            elif row['yield_now'] <= row['sell_yield']:
                return "🔴 极高估 (卖出)"
            else:
                return "⚪ 持有/观望"
        
        df['action'] = df.apply(get_signal, axis=1)
        
        return df
        
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return df

# === 4. 主界面展示 ===
st.title("📊 个人高股息投资看板")
st.markdown("---")

# 编辑模式开关
edit_mode = st.checkbox("✏️ 开启编辑模式 (修改持仓、成本、预期股息)")

# 处理数据
df_display = st.session_state.portfolio.copy()

if edit_mode:
    st.info("💡 在表格中直接双击单元格进行修改，修改后按 Enter 键。")
    # 使用 DataEditor 允许用户直接修改数据
    edited_df = st.data_editor(
        df_display,
        column_config={
            "code": "代码",
            "name": "名称",
            "cost": st.column_config.NumberColumn("持仓成本", format="¥%.2f"),
            "qty": st.column_config.NumberColumn("持仓数量", min_value=0),
            "expected_div": st.column_config.NumberColumn("预期股息(每股)", format="¥%.2f"),
            "buy_yield": st.column_config.NumberColumn("买入阈值(%)", help="当股息率高于此值提醒买入"),
            "sell_yield": st.column_config.NumberColumn("卖出阈值(%)", help="当股息率低于此值提醒卖出"),
        },
        hide_index=True,
        num_rows="dynamic"
    )
    # 更新 Session State
    if not edited_df.equals(st.session_state.portfolio):
        st.session_state.portfolio = edited_df
        st.rerun()
else:
    # 获取实时价格并计算
    with st.spinner('正在从交易所同步最新股价...'):
        final_df = get_market_data(df_display)

    # --- 概览指标 ---
    total_market_value = final_df['market_value'].sum()
    total_profit = final_df['profit'].sum()
    # 估算年股息收入
    est_annual_dividend = (final_df['qty'] * final_df['expected_div']).sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("总持仓市值", f"¥{total_market_value:,.0f}")
    col2.metric("总浮动盈亏", f"¥{total_profit:,.0f}", delta_color="normal")
    col3.metric("预期年分红", f"¥{est_annual_dividend:,.0f}", help="基于持仓数量 * 预期每股分红")

    st.markdown("---")
    
    # --- 重点提醒区域 ---
    st.subheader("🔔 操作提醒")
    alerts = final_df[final_df['action'].str.contains("买入|卖出")]
    if not alerts.empty:
        for index, row in alerts.iterrows():
            color = "green" if "买入" in row['action'] else "red"
            msg = f"**{row['name']}**: 当前股息率 **{row['yield_now']:.2f}%** ({row['action']}) - 现价: ¥{row['current_price']:.2f}"
            if color == "green":
                st.success(msg)
            else:
                st.error(msg)
    else:
        st.info("当前没有触发阈值的操作建议，安心持有。")

    # --- 详细表格 ---
    st.subheader("📋 持仓详情")
    
    # 格式化显示
    display_cols = ['name', 'current_price', 'yield_now', 'action', 'qty', 'cost', 'profit', 'weight', 'buy_yield', 'sell_yield']
    
    # 样式美化：高亮操作建议
    def highlight_action(val):
        if '买入' in str(val):
            return 'background-color: #d4edda; color: #155724; font-weight: bold'
        elif '卖出' in str(val):
            return 'background-color: #f8d7da; color: #721c24; font-weight: bold'
        return ''

    st.dataframe(
        final_df[display_cols].style.format({
            'current_price': '¥{:.2f}',
            'yield_now': '{:.2f}%',
            'cost': '¥{:.2f}',
            'profit': '¥{:,.0f}',
            'weight': '{:.1f}%',
            'buy_yield': '{:.1f}%',
            'sell_yield': '{:.1f}%'
        }).applymap(highlight_action, subset=['action']),
        column_config={
            "name": "名称",
            "current_price": "现价",
            "yield_now": "当前股息率",
            "action": "操作建议",
            "qty": "持股数",
            "cost": "成本价",
            "profit": "浮动盈亏",
            "weight": "仓位占比",
            "buy_yield": "目标买入率",
            "sell_yield": "目标卖出率"
        },
        height=500,
        use_container_width=True,
        hide_index=True
    )