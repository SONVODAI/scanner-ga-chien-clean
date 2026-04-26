import streamlit as st
import pandas as pd
import os
import yfinance as yf

# ================= CONFIG =================
st.set_page_config(page_title="Portfolio Manager PRO", layout="wide")
DATA_FILE = "portfolio.csv"

st.title("🐔 Portfolio Manager PRO V13 – Auto Stable")

# ================= LOAD / SAVE =================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_csv(DATA_FILE)
            return df
        except:
            return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])
    return pd.DataFrame(columns=["Mã", "Giá mua", "%NAV"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ================= GET PRICE (YAHOO) =================
def get_price(code):
    try:
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

# ================= UI =================
st.sidebar.header("📥 Nhập danh mục")

raw = st.sidebar.text_area(
    "Format: Mã, Giá mua, %NAV\nVD:\nMBB,22,5",
    height=150
)

if st.sidebar.button("💾 Lưu danh mục"):
    rows = []
    for line in raw.split("\n"):
        parts = line.split(",")
        if len(parts) == 3:
            try:
                code = parts[0].strip().upper()
                buy = float(parts[1])
                nav = float(parts[2])
                rows.append([code, buy, nav])
            except:
                pass

    df_save = pd.DataFrame(rows, columns=["Mã", "Giá mua", "%NAV"])
    save_data(df_save)
    st.sidebar.success("✅ Đã lưu danh mục")

# ================= LOAD DATA =================
df = load_data()

# ================= MAIN =================
st.subheader("📊 Danh mục hiện tại")

if df.empty:
    st.info("👉 Chưa có danh mục")
else:
    rows = []

    for _, r in df.iterrows():
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

    df_show = pd.DataFrame(rows)

    st.dataframe(df_show, use_container_width=True)

    # ===== SUMMARY =====
    avg = df_show["% Lãi/Lỗ"].mean()
    st.metric("📈 Lãi/Lỗ trung bình (%)", round(avg, 2))
