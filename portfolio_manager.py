import streamlit as st
import pandas as pd
import numpy as np
from vnstock import stock_historical_data

st.set_page_config(page_title="Portfolio Manager", layout="wide")

st.title("🐔 Portfolio Manager – Nuôi & Bán Gà")

# ===== Nhập danh mục =====
st.sidebar.header("Nhập danh mục")

portfolio = st.sidebar.text_area(
    "Nhập (mã, giá mua, %NAV) - mỗi dòng 1 mã",
    "MBB,22,30\nVND,18,20\nDIG,25,10"
)

# ===== Parse dữ liệu =====
rows = []
for line in portfolio.split("\n"):
    try:
        code, buy, nav = line.split(",")
        rows.append({
            "ticker": code.strip().upper(),
            "buy_price": float(buy),
            "nav": float(nav)
        })
    except:
        continue

df = pd.DataFrame(rows)

# ===== Hàm phân tích =====
def analyze_stock(ticker):
    try:
        data = stock_historical_data(ticker, "2024-01-01")
        data = data.tail(50)

        close = data['close']
        volume = data['volume']

        ema9 = close.ewm(span=9).mean()

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        rs = gain.rolling(14).mean() / loss.rolling(14).mean()
        rsi = 100 - (100 / (1 + rs))

        rsi_ema9 = rsi.ewm(span=9).mean()

        # OBV
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        obv_ema9 = obv.ewm(span=9).mean()

        return {
            "price": close.iloc[-1],
            "ema9": ema9.iloc[-1],
            "rsi": rsi.iloc[-1],
            "rsi_ema9": rsi_ema9.iloc[-1],
            "obv": obv.iloc[-1],
            "obv_ema9": obv_ema9.iloc[-1]
        }
    except:
        return None

# ===== Xử lý =====
results = []

for _, row in df.iterrows():
    ticker = row['ticker']
    buy_price = row['buy_price']

    info = analyze_stock(ticker)

    if info is None:
        continue

    price = info['price']
    pnl = (price - buy_price) / buy_price * 100

    # ===== Xác định trạng thái gà =====
    if price > info['ema9'] and info['obv'] > info['obv_ema9'] and info['rsi'] > info['rsi_ema9']:
        status = "🟩 Gà chạy"
        action = "Giữ + trailing EMA9"

    elif price < info['ema9'] and info['obv'] < info['obv_ema9']:
        status = "🟥 Gà yếu"
        action = "Bán / giảm tỷ trọng"

    else:
        status = "🟨 Gà nghỉ"
        action = "Theo dõi"

    results.append({
        "Mã": ticker,
        "Giá mua": buy_price,
        "Giá hiện tại": round(price,2),
        "% Lãi/Lỗ": round(pnl,2),
        "Trạng thái": status,
        "Hành động": action
    })

result_df = pd.DataFrame(results)

# ===== Hiển thị =====
st.subheader("📊 Danh mục hiện tại")

st.dataframe(result_df, use_container_width=True)

# ===== Tổng kết =====
if not result_df.empty:
    st.subheader("📈 Tổng quan")

    avg_pnl = result_df["% Lãi/Lỗ"].mean()

    st.metric("Lãi/Lỗ trung bình (%)", round(avg_pnl,2))
