import streamlit as st
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Scanner Gà Chiến V15.1", layout="wide")

st.title("🐔 Scanner Gà Chiến V15.1 – Stable Version")
st.caption(f"Cập nhật: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

# ======================
# SIDEBAR
# ======================
market_score = st.sidebar.slider("Market Score", 1.0, 10.0, 8.0, 0.5)
top_n = st.sidebar.slider("Top cổ phiếu", 5, 20, 10)

# ======================
# LOAD DATA
# ======================
def load_data():
    if not os.path.exists("stock_data.csv"):
        st.error("Thiếu file stock_data.csv")
        st.stop()

    df = pd.read_csv("stock_data.csv")
    return df

df = load_data()

# ======================
# CHẤM ĐIỂM (GIỮ LOGIC V15)
# ======================
def score(row):
    s = 0

    # OBV
    if row['OBV_trend'] == "strong": s += 3
    elif row['OBV_trend'] == "medium": s += 2

    # PRICE
    if row['Price_vs_EMA'] == "above_ema9": s += 3
    elif row['Price_vs_EMA'] == "near_ema9": s += 1

    # RSI
    if row['RSI'] > 60: s += 2
    elif row['RSI'] > 50: s += 1

    # MACD
    if row['MACD'] == "bullish": s += 2

    return s

df['Score'] = df.apply(score, axis=1)

# ======================
# PHÂN LOẠI
# ======================
def classify(row):

    if row['Score'] >= 8 and row['OBV_trend']=="strong":
        return "🟩 ƯU TIÊN MUA"

    elif row['Score'] >= 6:
        return "🟨 THEO DÕI"

    elif row['Score'] >= 5:
        return "🟦 ĐẢO CHIỀU SỚM"

    else:
        return "🟥 LOẠI"

df['State'] = df.apply(classify, axis=1)

# ======================
# GOLD SCORE
# ======================
if market_score >= 8:
    df['GoldScore'] = df['Score'] * market_score
else:
    df['GoldScore'] = 0

# ======================
# SORT
# ======================
df = df.sort_values(by="GoldScore", ascending=False)

strong = df[df['State']=="🟩 ƯU TIÊN MUA"]

# ======================
# UI
# ======================
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Top cổ phiếu")
    st.dataframe(df.head(top_n), use_container_width=True)

with col2:
    st.subheader("🔥 Ưu tiên mua")
    st.dataframe(strong.head(top_n), use_container_width=True)

# ======================
# SUMMARY
# ======================
st.markdown("---")

c1, c2, c3 = st.columns(3)
c1.metric("Ưu tiên mua", len(strong))
c2.metric("Theo dõi", len(df[df['State']=="🟨 THEO DÕI"]))
c3.metric("Đảo chiều", len(df[df['State']=="🟦 ĐẢO CHIỀU SỚM"]))
