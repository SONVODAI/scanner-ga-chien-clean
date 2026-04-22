import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")

st.title("🐔 SCANNER GÀ CHIẾN V31 FINAL")

# ========================
# LOAD DATA AN TOÀN
# ========================

try:
    df = pd.read_csv("data_full.csv")
except:
    st.error("❌ Chưa có file data_full.csv. Anh chạy scanner trước.")
    st.stop()

# ========================
# CHECK CỘT
# ========================

required_cols = ["symbol", "price", "score", "group"]

for col in required_cols:
    if col not in df.columns:
        st.error(f"❌ Thiếu cột: {col} → file scan chưa chuẩn")
        st.stop()

# ========================
# MARKET
# ========================

market = round(df["score"].mean() * 2, 1)

st.subheader("📊 MARKET")
st.write("Score:", market)

# ========================
# GROUP
# ========================

st.subheader("🔥 CP MẠNH")
st.dataframe(df[df["group"]=="CP_MẠNH"])

col1, col2, col3 = st.columns(3)

with col1:
    st.write("PULL ĐẸP")
    st.dataframe(df[df["group"]=="PULL_ĐẸP"])

with col2:
    st.write("PULL VỪA")
    st.dataframe(df[df["group"]=="PULL_VỪA"])

with col3:
    st.write("THEO DÕI")
    st.dataframe(df[df["group"]=="THEO_DÕI"])

# ========================
# FULL TABLE
# ========================

st.subheader("📋 TOÀN BỘ")
st.dataframe(df.sort_values("score", ascending=False))
