import streamlit as st
import pandas as pd
import os

# ===== CONFIG =====
st.set_page_config(page_title="Portfolio Manager PRO", layout="wide")

st.title("🐔 Portfolio Manager PRO – Nuôi Gà Chiến")

DATA_FILE = "portfolio.csv"

# ===== LOAD DATA =====
def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Mã","Giá mua","Giá hiện tại","%NAV"])

# ===== SAVE DATA =====
def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ===== STOP ENGINE 2.0 =====
def stop_engine(row):
    buy = row["Giá mua"]
    price = row["Giá hiện tại"]
    pnl = (price - buy) / buy * 100

    if pnl >= 5:
        return pnl, "🟩 Gà chạy", "Giữ + trailing", price*0.97, "Thấp", "Có lãi → giữ"
    elif -3 <= pnl < 5:
        return pnl, "🟨 Gà nghỉ", "Theo dõi", buy*0.95, "Trung bình", "Quan sát"
    elif -6 <= pnl < -3:
        return pnl, "⚠️ Yếu dần", "Siết stop", price*0.98, "Cao", "Chuẩn bị thoát"
    else:
        return pnl, "🟥 Gà gãy", "BÁN NGAY", None, "Rất cao", "Gãy cấu trúc"

# ===== SMART NAV =====
def suggest_nav(row):
    status = row["Trạng thái"]

    if "🟩" in status:
        return "Tăng tỷ trọng"
    elif "🟨" in status:
        return "Giữ nguyên"
    elif "⚠️" in status:
        return "Giảm 1/2"
    else:
        return "Thoát toàn bộ"

# ===== LOAD =====
df = load_data()

# ===== INPUT =====
st.sidebar.header("Nhập / Cập nhật danh mục")

new_data = st.sidebar.text_area(
    "Nhập (Mã, Giá mua, Giá hiện tại, %NAV)",
    ""
)

if st.sidebar.button("Lưu danh mục"):
    rows = []
    for line in new_data.split("\n"):
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
    save_data(df)
    st.success("Đã lưu danh mục!")

# ===== UPDATE PRICE =====
st.sidebar.header("Cập nhật giá mới")

update_text = st.sidebar.text_area(
    "Chỉ nhập (Mã, Giá hiện tại)",
    ""
)

if st.sidebar.button("Cập nhật giá"):
    for line in update_text.split("\n"):
        try:
            code, price = line.split(",")
            df.loc[df["Mã"] == code.strip().upper(), "Giá hiện tại"] = float(price)
        except:
            continue

    save_data(df)
    st.success("Đã cập nhật giá!")

# ===== PROCESS =====
results = []

for _, row in df.iterrows():
    pnl, status, action, stop, risk, note = stop_engine(row)

    results.append({
        "Mã": row["Mã"],
        "Giá mua": row["Giá mua"],
        "Giá hiện tại": row["Giá hiện tại"],
        "% Lãi/Lỗ": round(pnl,2),
        "Trạng thái": status,
        "Hành động": action,
        "Stop gợi ý": "-" if stop is None else round(stop,2),
        "Rủi ro": risk,
        "NAV đề xuất": suggest_nav({"Trạng thái":status}),
        "Ghi chú": note
    })

result_df = pd.DataFrame(results)

# ===== DISPLAY =====
st.subheader("📊 Danh mục hiện tại")
st.dataframe(result_df, use_container_width=True)

# ===== SUMMARY =====
if not result_df.empty:
    avg = result_df["% Lãi/Lỗ"].mean()
    st.metric("📈 Lãi/Lỗ trung bình (%)", round(avg,2))

# ===== ALERT =====
st.subheader("🚨 Cảnh báo nhanh")

for _, row in result_df.iterrows():
    if "🟥" in row["Trạng thái"]:
        st.error(f"{row['Mã']} → BÁN NGAY")
    elif "⚠️" in row["Trạng thái"]:
        st.warning(f"{row['Mã']} → SIẾT STOP")
    elif "🟩" in row["Trạng thái"]:
        st.success(f"{row['Mã']} → GIỮ")
