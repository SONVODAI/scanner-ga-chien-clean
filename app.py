import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Scanner Gà Chiến V16", layout="wide")

# =========================
# HEADER
# =========================
st.title("🐔 Scanner Gà Chiến V16 – Final Version")
st.caption(f"⏱ Update realtime | {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

# =========================
# SIDEBAR
# =========================
st.sidebar.header("Thiết lập")

market_score = st.sidebar.slider("Market Score", 1.0, 10.0, 8.0, 0.5)
top_n = st.sidebar.slider("Top cổ phiếu", 5, 20, 10)

# =========================
# LOAD DATA
# =========================
@st.cache_data(ttl=300)
def load_data():
    df = pd.read_csv("stock_data.csv")
    return df

# =========================
# TÍNH ĐIỂM
# =========================
def calculate_score(df):

    scores = []

    for _, row in df.iterrows():

        s = 0

        # OBV (4)
        if row['OBV_trend'] == "strong": s += 4
        elif row['OBV_trend'] == "medium": s += 2

        # PRICE (3)
        if row['Price_vs_EMA'] == "above_ema9": s += 3
        elif row['Price_vs_EMA'] == "near_ema9": s += 1

        # RSI (3)
        if row['RSI'] > 65: s += 3
        elif row['RSI'] > 55: s += 2

        # MACD (2)
        if row['MACD'] == "bullish": s += 2
        elif row['MACD'] == "neutral": s += 1

        # ATR (1)
        if row['ATR'] == "expand": s += 1

        scores.append(s)

    df['Score'] = scores
    return df

# =========================
# PHÂN LOẠI
# =========================
def classify(df):

    states = []

    for _, row in df.iterrows():

        s = row['Score']

        if s >= 9 and row['OBV_trend'] == "strong" and row['RSI'] > 60:
            states.append("🟩 ƯU TIÊN MUA")

        elif 7 <= s < 9:
            states.append("🟨 THEO DÕI")

        elif s >= 6 and row['OBV_trend'] == "recover":
            states.append("🟦 ĐẢO CHIỀU SỚM")

        else:
            states.append("🟥 LOẠI")

    df['State'] = states
    return df

# =========================
# GOLD SCORE
# =========================
def gold_score(df):

    if market_score < 8:
        df['GoldScore'] = 0
    else:
        df['GoldScore'] = df['Score'] * market_score

    return df

# =========================
# FILTER
# =========================
def filter_stock(df):

    return df[
        (df['State'] == "🟩 ƯU TIÊN MUA") &
        (df['OBV_trend'] == "strong") &
        (df['Price_vs_EMA'] != "below_ma20")
    ]

# =========================
# MAIN
# =========================
df = load_data()

df = calculate_score(df)
df = classify(df)
df = gold_score(df)

df = df.sort_values(by="GoldScore", ascending=False)

strong = filter_stock(df)

# =========================
# HIỂN THỊ
# =========================
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Top cổ phiếu toàn thị trường")
    st.dataframe(df[['Ticker','Score','GoldScore','State']].head(top_n), use_container_width=True)

with col2:
    st.subheader("🔥 Cổ phiếu đáng mua")
    st.dataframe(strong[['Ticker','Score','GoldScore']], use_container_width=True)

# =========================
# FOOTER
# =========================
st.markdown("---")
st.caption("V16 Final – Chuẩn theo hệ Nuôi Gà Chiến + Gold Score")
