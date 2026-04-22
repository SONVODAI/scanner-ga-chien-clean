# app.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

# ==============================
# CONFIG
# ==============================
st.set_page_config(layout="wide")

st.title("📊 SCANNER GÀ CHIẾN V21")

# ==============================
# GIỜ VIỆT NAM
# ==============================
vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
now_vn = datetime.now(vn_tz)

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"🗓 **Ngày:** {now_vn.strftime('%d/%m/%Y')}")
with col2:
    st.markdown(f"⏰ **Giờ VN:** {now_vn.strftime('%H:%M:%S')}")

# ==============================
# NÚT SCAN
# ==============================
scan = st.button("🔄 SCAN")

# ==============================
# DEMO DATA (anh thay bằng data thật)
# ==============================
def load_data():
    return pd.read_csv("data.csv")

if scan:
    df = load_data()
else:
    st.stop()

# ==============================
# FEATURE
# ==============================
df["dist_from_ema9"] = (df["price"] - df["ema9"]) / df["ema9"] * 100
df["ema9_ma20_gap"] = (df["ema9"] - df["ma20"]) / df["ma20"] * 100

# ==============================
# LOGIC PHÂN LOẠI
# ==============================

def is_strong(row):
    return (
        row["price"] > row["ema9"]
        and row["ema9"] > row["ma20"]
        and row["rsi"] >= 65
        and row["obv"] > row["obv_ema9"]
    )

def is_pull_dep(row):
    return (
        abs(row["dist_from_ema9"]) <= 2
        and row["rsi"] >= 55
    )

def is_pull_vua(row):
    return abs(row["dist_from_ema9"]) <= 4

def is_break(row):
    return row["price"] > row["high_prev"]

def is_early(row):
    return (
        40 <= row["rsi"] <= 60
        and abs(row["ema9"] - row["ma20"]) / row["ma20"] < 0.05
    )

def classify(row):
    if is_break(row):
        return "MUA BREAK"
    if is_pull_dep(row):
        return "PULL ĐẸP"
    if is_pull_vua(row):
        return "PULL VỪA"
    if is_strong(row):
        return "CP MẠNH"
    if is_early(row):
        return "MUA EARLY"
    if row["rsi"] >= 45:
        return "TÍCH LŨY"
    return "THEO DÕI"

df["group"] = df.apply(classify, axis=1)

# ==============================
# CHIA LIST
# ==============================
df_cp_manh = df[df["group"] == "CP MẠNH"]
df_break = df[df["group"] == "MUA BREAK"]
df_pull_dep = df[df["group"] == "PULL ĐẸP"]
df_pull_vua = df[df["group"] == "PULL VỪA"]
df_early = df[df["group"] == "MUA EARLY"]
df_tich_luy = df[df["group"] == "TÍCH LŨY"]
df_theo_doi = df[df["group"] == "THEO DÕI"]

# ==============================
# TOP VÀO TIỀN
# ==============================
st.subheader("🎯 TOP VÀO TIỀN HÔM NAY")
top = df_pull_vua.head(3)

for _, r in top.iterrows():
    st.write(f"{r['symbol']} — {r['group']} | Giá: {r['price']}")

# ==============================
# GRID HIỂN THỊ
# ==============================
col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

with col1:
    st.subheader("CP MẠNH")
    st.dataframe(df_cp_manh[["symbol", "price"]])

with col2:
    st.subheader("MUA BREAK")
    st.dataframe(df_break[["symbol", "price"]])

with col3:
    st.subheader("PULL ĐẸP")
    st.dataframe(df_pull_dep[["symbol", "price"]])

with col4:
    st.subheader("PULL VỪA")
    st.dataframe(df_pull_vua[["symbol", "price"]])

with col5:
    st.subheader("MUA EARLY")
    st.dataframe(df_early[["symbol", "price"]])

with col6:
    st.subheader("TÍCH LŨY")
    st.dataframe(df_tich_luy[["symbol", "price"]])

with col7:
    st.subheader("THEO DÕI")
    st.dataframe(df_theo_doi[["symbol", "price"]])

# ==============================
# BẢNG TỔNG CHI TIẾT
# ==============================
st.subheader("📊 BẢNG TỔNG CHI TIẾT")

st.dataframe(df)
