import streamlit as st
import pandas as pd
import numpy as np
from vnstock import Vnstock
import os
import json

# ================= CONFIG =================
st.set_page_config(page_title="Portfolio Manager PRO", layout="wide")
st.title("🐔 Portfolio Manager PRO V7 – Full Auto Scanner")

DATA_FILE = "portfolio_data.json"

# ================= LOAD DATA =================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

portfolio = load_data()

# ================= INPUT =================
st.sidebar.header("1️⃣ Nhập danh mục")

input_data = st.sidebar.text_area(
    "Format: Mã, Giá mua, %NAV\nVí dụ:\nMBB,22,10\nVND,18,20"
)

if st.sidebar.button("💾 Lưu danh mục"):
    new_port = []
    lines = input_data.strip().split("\n")
    for line in lines:
        try:
            symbol, buy, nav = line.split(",")
            new_port.append({
                "symbol": symbol.strip().upper(),
                "buy": float(buy),
                "nav": float(nav)
            })
        except:
            pass
    save_data(new_port)
    st.sidebar.success("Đã lưu danh mục")

portfolio = load_data()

# ================= GET REALTIME DATA =================
def get_price(symbol):
    try:
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        df = stock.quote.history(start="2024-01-01")
        return df["close"].iloc[-1]
    except:
        return None

# ================= LOGIC GÀ =================
def classify(pct):
    if pct > 5:
        return "🟢 Gà chạy", "Giữ + trailing"
    elif pct > 0:
        return "🟡 Gà nghỉ", "Theo dõi"
    else:
        return "🔴 Gà gãy", "BÁN NGAY"

# ================= STOP ENGINE 2.0 =================
def stop_engine(price, pct):
    if pct > 5:
        return round(price * 0.95, 2)
    elif pct > 0:
        return round(price * 0.9, 2)
    else:
        return "-"

# ================= PROCESS =================
rows = []

for item in portfolio:
    symbol = item["symbol"]
    buy = item["buy"]
    nav = item["nav"]

    current = get_price(symbol)

    if current:
        pct = round((current - buy) / buy * 100, 2)
        state, action = classify(pct)
        stop = stop_engine(current, pct)
    else:
        pct = 0
        state = "❌ Không có dữ liệu"
        action = "Check mã"
        stop = "-"

    rows.append({
        "Mã": symbol,
        "Giá mua": buy,
        "Giá hiện tại": current,
        "%NAV": nav,
        "% Lãi/Lỗ": pct,
        "Trạng thái": state,
        "Hành động": action,
        "Stop": stop
    })

df = pd.DataFrame(rows)

# ================= DISPLAY =================
st.subheader("📊 Danh mục hiện tại")
st.dataframe(df, use_container_width=True)

# ================= SUMMARY =================
if not df.empty:
    avg = df["% Lãi/Lỗ"].mean()
    st.metric("📉 Lãi/Lỗ trung bình (%)", round(avg, 2))

# ================= ALERT =================
# ALERT
if not df.empty and "Trạng thái" in df.columns:
    alerts = df[df["Trạng thái"].str.contains("Gãy")]

    if not alerts.empty:
        st.error("🚨 CẢNH BÁO: Có cổ phiếu cần xử lý ngay!")
        st.write(alerts[["Mã", "Hành động"]])
    st.error("🚨 CẢNH BÁO: Có cổ phiếu cần xử lý ngay!")
    st.write(alerts[["Mã", "Hành động"]])
