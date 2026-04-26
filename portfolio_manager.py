import streamlit as st
import pandas as pd

st.set_page_config(page_title="Portfolio Manager", layout="wide")

st.title("🐔 Portfolio Manager – Nuôi & Bán Gà")

# ===== INPUT =====
st.sidebar.header("Nhập danh mục")

portfolio = st.sidebar.text_area(
    "Nhập (Mã, Giá mua, Giá hiện tại, %NAV)",
    "MBB,22,23.5,30\nVND,18,17.5,20\nDIG,25,26,10"
)

# ===== PARSE =====
rows = []

for line in portfolio.split("\n"):
    try:
        code, buy, price, nav = line.split(",")
        rows.append({
            "Mã": code.strip().upper(),
            "Giá mua": float(buy),
            "Giá hiện tại": float(price),
            "%NAV": float(nav)
        })
    except:
        continue

df = pd.DataFrame(rows)

# ===== LOGIC GÀ =====
def classify(row):
    buy = row["Giá mua"]
    price = row["Giá hiện tại"]

    pnl = (price - buy) / buy * 100

    # 🟩 Gà chạy
    if pnl > 5:
        return "🟩 Gà chạy", "Giữ + trailing"

    # 🟥 Gà yếu
    if pnl < -5:
        return "🟥 Gà yếu", "Bán ngay"

    # 🟨 Gà nghỉ
    return "🟨 Gà nghỉ", "Theo dõi"

# ===== XỬ LÝ =====
results = []

for _, row in df.iterrows():
    pnl = (row["Giá hiện tại"] - row["Giá mua"]) / row["Giá mua"] * 100

    status, action = classify(row)

    results.append({
        "Mã": row["Mã"],
        "Giá mua": row["Giá mua"],
        "Giá hiện tại": row["Giá hiện tại"],
        "% Lãi/Lỗ": round(pnl,2),
        "Trạng thái": status,
        "Hành động": action
    })

result_df = pd.DataFrame(results)

# ===== DISPLAY =====
st.subheader("📊 Danh mục hiện tại")
st.dataframe(result_df, use_container_width=True)

# ===== SUMMARY =====
if not result_df.empty:
    avg = result_df["% Lãi/Lỗ"].mean()
    st.metric("📈 Lãi/Lỗ trung bình (%)", round(avg,2))
