import streamlit as st
import pandas as pd
import json
import os

# ================= CONFIG =================
st.set_page_config(page_title="Portfolio Manager PRO", layout="wide")
st.title("🐔 Portfolio Manager PRO V8 – Trading System")

DATA_FILE = "portfolio.json"

# ================= LOAD / SAVE =================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

portfolio = load_data()

# ================= SIDEBAR =================
st.sidebar.header("1️⃣ Nhập danh mục (chỉ 1 lần)")

input_data = st.sidebar.text_area(
    "Format: Mã, Giá mua, %NAV\nVD:\nMBB,22,10\nVND,18,20"
)

if st.sidebar.button("💾 Lưu danh mục"):
    new_port = []
    for line in input_data.strip().split("\n"):
        try:
            symbol, buy, nav = line.split(",")
            new_port.append({
                "symbol": symbol.strip().upper(),
                "buy": float(buy),
                "nav": float(nav),
                "current": None
            })
        except:
            pass

    save_data(new_port)
    st.sidebar.success("Đã lưu danh mục")

# ================= UPDATE PRICE =================
st.sidebar.header("2️⃣ Cập nhật giá mỗi ngày")

update_data = st.sidebar.text_area(
    "Chỉ nhập: Mã, Giá hiện tại\nVD:\nMBB,23.5\nVND,17.8"
)

if st.sidebar.button("🔄 Cập nhật giá"):
    data = load_data()

    for line in update_data.strip().split("\n"):
        try:
            symbol, price = line.split(",")
            symbol = symbol.strip().upper()

            for item in data:
                if item["symbol"] == symbol:
                    item["current"] = float(price)
        except:
            pass

    save_data(data)
    st.sidebar.success("Đã cập nhật giá")

portfolio = load_data()

# ================= LOGIC =================
def classify(pct):
    if pct > 5:
        return "🟢 Gà chạy", "Giữ + trailing"
    elif pct > 0:
        return "🟡 Gà nghỉ", "Theo dõi"
    else:
        return "🔴 Gà gãy", "BÁN NGAY"

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
    current = item.get("current")

    if current:
        pct = round((current - buy) / buy * 100, 2)
        state, action = classify(pct)
        stop = stop_engine(current, pct)
    else:
        pct = 0
        state = "⚠️ Chưa có giá"
        action = "Cập nhật giá"
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

if df.empty:
    st.info("👉 Chưa có danh mục")
else:
    st.dataframe(df, use_container_width=True)

# ================= SUMMARY =================
if not df.empty:
    avg = df["% Lãi/Lỗ"].mean()
    st.metric("📉 Lãi/Lỗ trung bình (%)", round(avg, 2))

# ================= ALERT =================
if not df.empty and "Trạng thái" in df.columns:
    alerts = df[df["Trạng thái"].str.contains("Gãy")]

    if not alerts.empty:
        st.error("🚨 CẢNH BÁO: Có cổ phiếu cần xử lý ngay!")
        st.write(alerts[["Mã", "Hành động"]])
