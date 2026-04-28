import streamlit as st
import pandas as pd
import os
from datetime import datetime
from vnstock import stock_historical_data
import numpy as np

# =========================
# CONFIG
# =========================
FILE_NAME = "portfolio.csv"

st.set_page_config(layout="wide")
st.title("🔥 Portfolio Gà Chiến PRO – V19")

# =========================
# LOAD DATA
# =========================
if os.path.exists(FILE_NAME):
    df = pd.read_csv(FILE_NAME)
else:
    df = pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

# =========================
# INPUT FORM
# =========================
st.subheader("➕ Thêm / Sửa mã")

col1, col2, col3 = st.columns(3)

with col1:
    ma = st.text_input("Mã")

with col2:
    gia = st.number_input("Giá mua", step=1000)

with col3:
    nav = st.number_input("% NAV", step=0.5)

col_add, col_del = st.columns(2)

# ADD / UPDATE
with col_add:
    if st.button("✅ Thêm / Cập nhật"):
        if ma != "":
            ma = ma.upper()

            if ma in df["Mã"].values:
                df.loc[df["Mã"] == ma, ["Giá mua", "%NAV"]] = [gia, nav]
            else:
                df.loc[len(df)] = [ma, gia, nav]

            df.to_csv(FILE_NAME, index=False)
            st.success("Đã lưu!")
            st.rerun()

# DELETE
with col_del:
    if st.button("🗑️ Xóa mã"):
        df = df[df["Mã"] != ma.upper()]
        df.to_csv(FILE_NAME, index=False)
        st.warning("Đã xóa!")
        st.rerun()

# =========================
# HÀM TÍNH TOÁN
# =========================

def get_price(symbol):
    try:
        data = stock_historical_data(symbol, "2025-01-01", datetime.today().strftime('%Y-%m-%d'))
        return data.iloc[-1]["close"]
    except:
        return None

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_obv(close, volume):
    obv = [0]
    for i in range(1, len(close)):
        if close[i] > close[i-1]:
            obv.append(obv[-1] + volume[i])
        elif close[i] < close[i-1]:
            obv.append(obv[-1] - volume[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv)

def evaluate_stock(symbol, buy_price):
    try:
        data = stock_historical_data(symbol, "2025-01-01", datetime.today().strftime('%Y-%m-%d'))

        close = data["close"]
        volume = data["volume"]

        price = close.iloc[-1]

        # RSI
        rsi = calc_rsi(close).iloc[-1]

        # OBV
        obv = calc_obv(close.values, volume.values)
        obv_ma = obv.rolling(9).mean().iloc[-1]

        # EMA
        ema9 = close.ewm(span=9).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        hist = macd.iloc[-1] - signal.iloc[-1]

        # =====================
        # CHẤM ĐIỂM (13 POINT)
        # =====================
        score = 0

        if price > ema9: score += 2
        if ema9 > ma20: score += 1
        if rsi > 55: score += 2
        if obv.iloc[-1] > obv_ma: score += 3
        if hist > 0: score += 2

        # =====================
        # PHÂN LOẠI
        # =====================
        if score >= 9:
            status = "🟢 Gà chiến"
            action = "GIỮ / CANH MUA"
        elif score >= 7:
            status = "🟡 Gà khỏe"
            action = "GIỮ"
        elif score >= 5:
            status = "🟠 Yếu dần"
            action = "GIẢM"
        else:
            status = "🔴 Gãy"
            action = "BÁN"

        # STOP ENGINE
        stop = min(ma20, ema9) * 0.97

        pnl = (price - buy_price) / buy_price * 100

        return price, pnl, score, status, stop, action

    except:
        return None, None, None, "Lỗi", None, None


# =========================
# HIỂN THỊ DANH MỤC
# =========================
st.subheader("📊 Danh mục nâng cao")

if len(df) > 0:

    results = []

    for _, row in df.iterrows():
        price, pnl, score, status, stop, action = evaluate_stock(row["Mã"], row["Giá mua"])

        results.append([
            row["Mã"],
            row["Giá mua"],
            price,
            pnl,
            score,
            status,
            stop,
            action
        ])

    result_df = pd.DataFrame(results, columns=[
        "Mã", "Giá mua", "Giá hiện tại", "%Lãi/lỗ",
        "Điểm", "Trạng thái", "Stoploss", "Hành động"
    ])

    st.dataframe(result_df, use_container_width=True)

else:
    st.info("Chưa có danh mục")

# =========================
# RESET
# =========================
if st.button("❌ Reset toàn bộ"):
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)
    st.warning("Đã xóa toàn bộ")
    st.rerun()
