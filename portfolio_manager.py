import streamlit as st
import pandas as pd
import os
import requests
import yfinance as yf

# ================= CONFIG =================
st.set_page_config(page_title="Portfolio Manager PRO", layout="wide")
DATA_FILE = "portfolio.csv"

st.title("🐔 Portfolio Manager PRO V13 – Auto Stable")

# ================= API GIÁ =================
def get_price(code):
    try:
        # Yahoo dùng .VN cho HOSE
        ticker = yf.Ticker(f"{code}.VN")
        data = ticker.history(period="1d")

        if not data.empty:
            return float(data["Close"].iloc[-1])
    except:
        return None
    return None
# ================= LOGIC =================
def classify(pct):
    if pct >= 5:
        return "🟢 Gà chạy", "Giữ + trailing", "Thấp"
    elif pct >= 0:
        return "🟡 Gà nghỉ", "Theo dõi", "Trung bình"
    else:
        return "🔴 Gà gãy", "BÁN NGAY", "Cao"

# ================= LOAD/SAVE =================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            return pd.read_csv(DATA_FILE)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ================= INPUT =================
st.sidebar.header("📥 Nhập danh mục")

raw = st.sidebar.text_area(
    "Format: Mã, Giá mua, %NAV\nVD:\nMBB,22,5\nVND,18,3"
)

if st.sidebar.button("💾 Lưu danh mục"):
    rows = []
    for line in raw.split("\n"):
        try:
            code, buy, nav = line.split(",")
            rows.append({
                "Mã": code.strip().upper(),
                "Giá mua": float(buy),
                "%NAV": float(nav)
            })
        except:
            st.sidebar.error(f"Lỗi dòng: {line}")

    df_save = pd.DataFrame(rows)
    save_data(df_save)
    st.sidebar.success("Đã lưu danh mục!")

# ================= LOAD =================
df_input = load_data()

# ================= PROCESS =================
if df_input.empty:
    st.info("👉 Chưa có danh mục")
else:
    rows = []

    for _, r in df_input.iterrows():
        code = r["Mã"]
        buy = r["Giá mua"]
        nav = r["%NAV"]

        price = get_price(code)

        if price:
            pct = (price - buy) / buy * 100
            state, action, risk = classify(pct)
        else:
            pct = 0
            state, action, risk = "⚠️ Lỗi data", "Check", "?"

        rows.append({
            "Mã": code,
            "Giá mua": buy,
            "Giá hiện tại": round(price, 2) if price else None,
            "%NAV": nav,
            "% Lãi/Lỗ": round(pct, 2),
            "Trạng thái": state,
            "Hành động": action,
            "Rủi ro": risk
        })

    df = pd.DataFrame(rows)

    # ===== DISPLAY =====
    st.subheader("📊 Danh mục hiện tại")
    st.dataframe(df, use_container_width=True)

    # ===== SUMMARY =====
    avg = df["% Lãi/Lỗ"].mean()
    st.metric("📈 Lãi/Lỗ trung bình (%)", round(avg, 2))

    # ===== ALERT =====
    alert = df[df["Trạng thái"].str.contains("gãy", case=False, na=False)]

    if not alert.empty:
        st.error("🚨 Cảnh báo: Có cổ phiếu cần xử lý!")
        for _, row in alert.iterrows():
            st.write(f"{row['Mã']} → BÁN NGAY")
