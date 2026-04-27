import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os

st.set_page_config(page_title="Portfolio Manager PRO V15", layout="wide")
st.title("🐔 Portfolio Manager PRO V15 – Stable Version")

DATA_FILE = "portfolio.csv"

# ================= LOAD / SAVE =================
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            df = pd.read_csv(DATA_FILE)
            if {"Mã", "Giá mua", "%NAV"}.issubset(df.columns):
                return df
    except:
        pass
    return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ================= GET DATA =================
@st.cache_data(ttl=300)
def get_price(code):
    try:
        ticker = yf.Ticker(f"{code}.VN")
        df = ticker.history(period="3mo")

        if df is None or df.empty:
            ticker = yf.Ticker(code)
            df = ticker.history(period="3mo")

        if df is None or df.empty:
            return None

        return float(df["Close"].iloc[-1])
    except:
        return None

# ================= SIDEBAR =================
st.sidebar.header("📥 Nhập danh mục")

raw = st.sidebar.text_area(
    "Format: Mã,Giá,%NAV\nVD:\nMBB,27000,5",
    height=150
)

if st.sidebar.button("💾 Lưu danh mục"):
    rows = []
    for line in raw.split("\n"):
        parts = line.split(",")
        if len(parts) == 3:
            try:
                rows.append({
                    "Mã": parts[0].strip().upper(),
                    "Giá mua": float(parts[1]),
                    "%NAV": float(parts[2])
                })
            except:
                pass

    df_save = pd.DataFrame(rows)
    save_data(df_save)
    st.sidebar.success("✅ Đã lưu")

# ================= MAIN =================
df = load_data()

st.subheader("📊 Danh mục hiện tại")

if df.empty:
    st.info("👉 Chưa có dữ liệu")
else:
    result = []

    for _, r in df.iterrows():
        code = r["Mã"]
        buy = float(r["Giá mua"])
        nav = float(r["%NAV"])

        price = get_price(code)

        if price is None:
            result.append({
                "Mã": code,
                "Giá mua": buy,
                "Giá hiện tại": "Lỗi data",
                "%NAV": nav
            })
            continue

        pnl = (price - buy) / buy * 100

        result.append({
            "Mã": code,
            "Giá mua": buy,
            "Giá hiện tại": round(price, 2),
            "%NAV": nav,
            "%Lãi/Lỗ": round(pnl, 2)
        })

    df_out = pd.DataFrame(result)

    st.dataframe(df_out, use_container_width=True)

    # ================= METRICS ANTI-CRASH =================
    c1, c2 = st.columns(2)

    if "%Lãi/Lỗ" in df_out.columns:
        c1.metric("📈 Lãi/Lỗ TB (%)", round(df_out["%Lãi/Lỗ"].mean(), 2))
    else:
        c1.metric("📈 Lãi/Lỗ TB (%)", "N/A")

    c2.metric("💰 Tổng %NAV", round(df_out["%NAV"].sum(), 2))
