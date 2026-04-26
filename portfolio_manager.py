import streamlit as st
import pandas as pd
import yfinance as yf
import os

st.set_page_config(page_title="Portfolio Manager PRO V11", layout="wide")

st.title("🐔 Portfolio Manager PRO V11 – Trading Tool")

DATA_FILE = "portfolio.csv"

# ================= LOAD =================
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            df = pd.read_csv(DATA_FILE)

            if df.empty or "Mã" not in df.columns:
                return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

            return df

        return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

    except:
        return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

# ================= SAVE =================
def save_data(df):
    try:
        if not df.empty:
            df.to_csv(DATA_FILE, index=False)
    except:
        st.error("Lỗi lưu dữ liệu")

# ================= PRICE =================
@st.cache_data(ttl=300)
def get_price(code):
    try:
        ticker = yf.Ticker(code + ".VN")
        df = ticker.history(period="1d")
        if df.empty:
            return None
        return float(df["Close"].iloc[-1])
    except:
        return None

# ================= LOGIC =================
def classify(pct):
    if pct >= 5:
        return "🟢 Gà chạy", "Giữ + trailing", "Thấp"
    elif pct >= 0:
        return "🟡 Gà nghỉ", "Theo dõi", "Trung bình"
    else:
        return "🔴 Gà gãy", "BÁN NGAY", "Cao"

# ================= SIDEBAR =================
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
            try:
                code = parts[0].strip().upper()
                buy = float(parts[1])
                nav = float(parts[2])
                data.append({"Mã": code, "Giá mua": buy, "%NAV": nav})
            except:
                pass

    df_save = pd.DataFrame(data)

    if not df_save.empty:
        save_data(df_save)
        st.sidebar.success("✅ Đã lưu danh mục")
    else:
        st.sidebar.warning("⚠️ Dữ liệu không hợp lệ")

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
    price = price / 1000 
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
    alerts = result[result["Trạng thái"].str.contains("Gà gãy", na=False)]

    if not alerts.empty:
        st.error("🚨 CẢNH BÁO: CÓ MÃ CẦN BÁN NGAY")
        for c in alerts["Mã"]:
            st.write(f"❌ {c}")

# ================= BACKUP =================
if st.button("📂 Backup danh mục"):
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "rb") as f:
            st.download_button("📥 Tải file backup", f, file_name="portfolio_backup.csv")
