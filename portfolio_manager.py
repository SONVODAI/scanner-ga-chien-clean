import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Portfolio Manager", layout="wide")

st.title("🐔 Portfolio Manager – Nuôi & Bán Gà")

# ===== INPUT =====
st.sidebar.header("Nhập danh mục")
portfolio = st.sidebar.text_area(
    "Nhập (mã, giá mua, %NAV) - mỗi dòng 1 mã",
    "MBB,22,30\nVND,18,20\nDIG,25,10"
)

# ===== PARSE =====
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

# ===== DATA =====
def get_price(ticker):
    try:
        data = yf.download(ticker + ".VN", period="3mo", interval="1d", progress=False)
        if data is None or data.empty:
            return None

        close = data["Close"]
        volume = data["Volume"]

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
            "price": float(close.iloc[-1]),
            "ema9": float(ema9.iloc[-1]),
            "rsi": float(rsi.iloc[-1]),
            "rsi_ema9": float(rsi_ema9.iloc[-1]),
            "obv": float(obv.iloc[-1]),
            "obv_ema9": float(obv_ema9.iloc[-1])
        }
    except:
        return None

# ===== LOGIC GÀ =====
def classify(info):
    price = info["price"]
    ema9 = info["ema9"]
    rsi = info["rsi"]
    rsi_ema9 = info["rsi_ema9"]
    obv = info["obv"]
    obv_ema9 = info["obv_ema9"]

    # Gà chạy
    if price > ema9 and obv > obv_ema9 and rsi > rsi_ema9:
        return "🟩 Gà chạy", "Giữ + trailing"

    # Gà yếu
    if price < ema9 and obv < obv_ema9:
        return "🟥 Gà yếu", "Bán ngay"

    # Gà nghỉ
    return "🟨 Gà nghỉ", "Theo dõi"

# ===== MAIN =====
results = []

for _, row in df.iterrows():
    ticker = row["ticker"]
    buy = row["buy_price"]

    info = get_price(ticker)

    if info is None:
        results.append({
            "Mã": ticker,
            "Giá mua": buy,
            "Trạng thái": "❌ Không có dữ liệu",
            "Hành động": "Check mã"
        })
        continue

    price = info["price"]
    pnl = (price - buy) / buy * 100

    status, action = classify(info)

    stop = info["ema9"] * 0.98

    results.append({
        "Mã": ticker,
        "Giá mua": round(buy,2),
        "Giá hiện tại": round(price,2),
        "% Lãi/Lỗ": round(pnl,2),
        "Trạng thái": status,
        "Hành động": action,
        "Stop gợi ý": round(stop,2)
    })

result_df = pd.DataFrame(results)

# ===== DISPLAY =====
st.subheader("📊 Danh mục hiện tại")
st.dataframe(result_df, use_container_width=True)

# ===== SUMMARY =====
if not result_df.empty and "% Lãi/Lỗ" in result_df.columns:
    avg = result_df["% Lãi/Lỗ"].mean()
    st.metric("📈 Lãi/Lỗ trung bình (%)", round(avg,2))
