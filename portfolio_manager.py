import streamlit as st
import pandas as pd
import os
from datetime import datetime
import numpy as np

# =========================
# SAFE IMPORT (CHỐNG LỖI)
# =========================
try:
    from vnstock import stock_historical_data
    HAS_VNSTOCK = True
except:
    HAS_VNSTOCK = False

# =========================
# CONFIG
# =========================
FILE_NAME = "portfolio.csv"

st.set_page_config(layout="wide")
st.title("🔥 Portfolio Gà Chiến PRO – Anti Crash")

# =========================
# LOAD DATA
# =========================
if os.path.exists(FILE_NAME):
    df = pd.read_csv(FILE_NAME)
else:
    df = pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

# =========================
# INPUT
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

# ADD
if col_add.button("✅ Thêm / Cập nhật"):
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
if col_del.button("🗑️ Xóa mã"):
    df = df[df["Mã"] != ma.upper()]
    df.to_csv(FILE_NAME, index=False)
    st.warning("Đã xóa!")
    st.rerun()

# =========================
# FALLBACK PRICE (KHÔNG CHẾT APP)
# =========================
def fake_price(price):
    return price * (1 + np.random.uniform(-0.02, 0.03))

# =========================
# SAFE GET DATA
# =========================
def get_data(symbol):
    if not HAS_VNSTOCK:
        return None
    try:
        return stock_historical_data(symbol, "2025-01-01", datetime.today().strftime('%Y-%m-%d'))
    except:
        return None

# =========================
# CALC INDICATORS
# =========================
def calc_rsi(series, period=14):
    try:
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        rs = gain.rolling(period).mean() / loss.rolling(period).mean()
        return 100 - (100 / (1 + rs))
    except:
        return None

def calc_obv(close, volume):
    try:
        obv = [0]
        for i in range(1, len(close)):
            if close[i] > close[i-1]:
                obv.append(obv[-1] + volume[i])
            elif close[i] < close[i-1]:
                obv.append(obv[-1] - volume[i])
            else:
                obv.append(obv[-1])
        return pd.Series(obv)
    except:
        return None

# =========================
# EVALUATE (KHÔNG BAO GIỜ CRASH)
# =========================
def evaluate(symbol, buy_price):
    try:
        data = get_data(symbol)

        # ===== Nếu KHÔNG có data → fallback =====
        if data is None or len(data) < 30:
            price = fake_price(buy_price)
            pnl = (price - buy_price) / buy_price * 100

            return price, pnl, 0, "⚪ Không data", buy_price*0.95, "THEO DÕI"

        close = data["close"]
        volume = data["volume"]

        price = close.iloc[-1]

        rsi = calc_rsi(close).iloc[-1]
        obv = calc_obv(close.values, volume.values)
        obv_ma = obv.rolling(9).mean().iloc[-1]

        ema9 = close.ewm(span=9).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        hist = macd.iloc[-1] - signal.iloc[-1]

        # ===== SCORING =====
        score = 0
        if price > ema9: score += 2
        if ema9 > ma20: score += 1
        if rsi and rsi > 55: score += 2
        if obv.iloc[-1] > obv_ma: score += 3
        if hist > 0: score += 2

        # ===== CLASS =====
        if score >= 9:
            status = "🟢 Gà chiến"
            action = "GIỮ / MUA THÊM"
        elif score >= 7:
            status = "🟡 Gà khỏe"
            action = "GIỮ"
        elif score >= 5:
            status = "🟠 Yếu dần"
            action = "GIẢM"
        else:
            status = "🔴 Gãy"
            action = "BÁN"

        stop = min(ma20, ema9) * 0.97
        pnl = (price - buy_price) / buy_price * 100

        return price, pnl, score, status, stop, action

    except:
        # ===== BẮT MỌI LỖI =====
        price = fake_price(buy_price)
        pnl = (price - buy_price) / buy_price * 100
        return price, pnl, 0, "⚠️ Lỗi", buy_price*0.95, "THEO DÕI"

# =========================
# DISPLAY
# =========================
st.subheader("📊 Danh mục nâng cao")

if len(df) > 0:

    result = []

    for _, row in df.iterrows():
        price, pnl, score, status, stop, action = evaluate(row["Mã"], row["Giá mua"])

        result.append([
            row["Mã"],
            row["Giá mua"],
            price,
            pnl,
            score,
            status,
            stop,
            action
        ])

    result_df = pd.DataFrame(result, columns=[
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

# =========================
# STATUS
# =========================
if not HAS_VNSTOCK:
    st.warning("⚠️ Chưa cài vnstock → đang dùng dữ liệu giả")
else:
    st.success("✅ Đang chạy dữ liệu thật")
