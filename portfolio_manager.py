import streamlit as st
import pandas as pd
import os
from vnstock import stock_historical_data

st.set_page_config(page_title="Portfolio Manager PRO V10", layout="wide")

st.title("🐔 Portfolio Manager PRO V10 – Auto Scanner + Save")

DATA_FILE = "portfolio.csv"

# ================= LOAD DATA =================
def load_portfolio():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

# ================= SAVE DATA =================
def save_portfolio(df):
    df.to_csv(DATA_FILE, index=False)

# ================= GET PRICE =================
def get_price(code):
    try:
        df = stock_historical_data(symbol=code, start_date="2024-01-01", end_date="2025-12-31")
        return df["close"].iloc[-1]
    except:
        return None

# ================= LOGIC GÀ =================
def classify(pct):
    if pct >= 5:
        return "Gà chạy", "Giữ + trailing"
    elif pct >= 0:
        return "Gà nghỉ", "Theo dõi"
    else:
        return "Gà gãy", "BÁN NGAY"

# ================= UI =================
st.sidebar.header("📥 Nhập danh mục")

input_text = st.sidebar.text_area(
    "Format: Mã, Giá mua, %NAV\nVD:\nVIC,172,6",
    height=150
)

if st.sidebar.button("💾 Lưu danh mục"):
    lines = input_text.strip().split("\n")
    data = []

    for line in lines:
        parts = line.split(",")
        if len(parts) == 3:
            code = parts[0].strip().upper()
            buy = float(parts[1])
            nav = float(parts[2])
            data.append({"Mã": code, "Giá mua": buy, "%NAV": nav})

    df = pd.DataFrame(data)
    save_portfolio(df)

    st.sidebar.success("✅ Đã lưu danh mục")

# ================= LOAD =================
df = load_portfolio()

# ================= PROCESS =================
rows = []

for _, row in df.iterrows():
    code = row["Mã"]
    buy = row["Giá mua"]
    nav = row["%NAV"]

    price = get_price(code)

    if price:
        pct = (price - buy) / buy * 100
        state, action = classify(pct)
    else:
        pct = 0
        state, action = "Lỗi data", "Check"

    rows.append({
        "Mã": code,
        "Giá mua": buy,
        "Giá hiện tại": round(price, 2) if price else None,
        "%NAV": nav,
        "% Lãi/Lỗ": round(pct, 2),
        "Trạng thái": state,
        "Hành động": action
    })

result = pd.DataFrame(rows)

# ================= DISPLAY =================
st.subheader("📊 Danh mục hiện tại")

if result.empty:
    st.info("👉 Chưa có danh mục")
else:
    st.dataframe(result, use_container_width=True)

    avg = result["% Lãi/Lỗ"].mean()
    st.metric("📈 Lãi/Lỗ trung bình (%)", round(avg, 2))

    # ALERT
    alerts = result[result["Trạng thái"] == "Gà gãy"]

    if not alerts.empty:
        st.error("🚨 CẢNH BÁO: Có mã cần bán ngay")
        for code in alerts["Mã"]:
            st.write(f"❌ {code} → BÁN NGAY")
