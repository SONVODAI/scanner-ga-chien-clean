import streamlit as st
import pandas as pd
import os

# =========================
# CẤU HÌNH
# =========================
FILE_NAME = "portfolio.csv"

st.set_page_config(page_title="Portfolio Gà Chiến", layout="wide")

st.title("📊 Danh mục Gà Chiến – V18.5")

# =========================
# LOAD DATA
# =========================
if os.path.exists(FILE_NAME):
    df = pd.read_csv(FILE_NAME)
else:
    df = pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

# =========================
# FORM NHẬP NHANH
# =========================
st.subheader("➕ Thêm / Sửa mã")

col1, col2, col3 = st.columns(3)

with col1:
    ma = st.text_input("Mã cổ phiếu")

with col2:
    gia = st.number_input("Giá mua", step=1000)

with col3:
    nav = st.number_input("% NAV", step=0.5)

col_add, col_delete = st.columns(2)

# =========================
# THÊM / UPDATE
# =========================
with col_add:
    if st.button("✅ Thêm / Cập nhật"):
        if ma != "":
            if ma in df["Mã"].values:
                df.loc[df["Mã"] == ma, ["Giá mua", "%NAV"]] = [gia, nav]
            else:
                df.loc[len(df)] = [ma, gia, nav]

            df.to_csv(FILE_NAME, index=False)
            st.success("Đã lưu!")
            st.rerun()

# =========================
# XÓA MÃ
# =========================
with col_delete:
    if st.button("🗑️ Xóa mã"):
        df = df[df["Mã"] != ma]
        df.to_csv(FILE_NAME, index=False)
        st.warning("Đã xóa!")
        st.rerun()

# =========================
# HIỂN THỊ DANH MỤC
# =========================
st.subheader("📋 Danh mục hiện tại")

if len(df) > 0:
    st.dataframe(df, use_container_width=True)
else:
    st.info("Chưa có danh mục")

# =========================
# RESET TOÀN BỘ
# =========================
if st.button("❌ Xóa toàn bộ danh mục"):
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)
    st.warning("Đã reset!")
    st.rerun()
