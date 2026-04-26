import streamlit as st
import pandas as pd
import yfinance as yf
import os

st.set_page_config(page_title="Portfolio Manager PRO V10", layout="wide")

st.title("🐔 Portfolio Manager PRO V10 – Stable Version")

DATA_FILE = "portfolio.csv"

# ================= LOAD =================
def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

# ================= SAVE =================
def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ================= GET PRICE =================
def get_price(code):
    try:
        ticker = yf.Ticker(code + ".VN")
        df = ticker.history(period="1d")
        return float(df["Close"].iloc[-1])
    except:
        return None

# ================= LOGIC =================
def classify(pct):
    if pct >= 5:
        return "🟢 Gà chạy", "Giữ + trailing"
    elif pct >= 0:
        return "🟡 Gà nghỉ", "Theo dõi"
    else:
        return "🔴 Gà gãy", "BÁN NGAY"

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
    save_data(df)
    st.sidebar.success("✅ Đã lưu")

# ================= LOAD =================
df = load_data()

# ================= PROCESS =================
rows = []

for _, r in df.iterrows():
    code = r["Mã"]
    buy = r["Giá mua"]
    nav = r["%NAV"]

    price = get_price(code)

    if price:
        pct = (price - buy) / buy * 100
        state, action = classify(pct)
    else:
        pct = 0
        state, action = "⚠️ Lỗi data", "Check"

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

    alerts = result[result["Trạng thái"].str.contains("gãy")]

    if not alerts.empty:
        st.error("🚨 CÓ MÃ CẦN BÁN NGAY")
        for c in alerts["Mã"]:
            st.write(f"❌ {c}")
