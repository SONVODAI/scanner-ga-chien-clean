import streamlit as st
import pandas as pd

st.set_page_config(page_title="Portfolio Manager PRO", layout="wide")

st.title("🐔 Portfolio Manager PRO – Nuôi Gà Chiến")

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

# ===== CORE LOGIC GÀ CHIẾN =====
def classify(row):
    buy = row["Giá mua"]
    price = row["Giá hiện tại"]

    pnl = (price - buy) / buy * 100

    # 🟩 GÀ CHẠY (có lợi nhuận rõ)
    if pnl >= 5:
        status = "🟩 Gà chạy"
        action = "Giữ + trailing"
        stop = price * 0.97   # trailing sát
        note = "Đang có lãi → ưu tiên giữ, không bán sớm"

    # 🟨 GÀ NGHỈ (dao động nhẹ)
    elif -3 <= pnl < 5:
        status = "🟨 Gà nghỉ"
        action = "Theo dõi"
        stop = buy * 0.95
        note = "Chưa rõ xu hướng → quan sát"

    # ⚠️ GÀ YẾU SỚM (cảnh báo trước)
    elif -6 <= pnl < -3:
        status = "⚠️ Yếu dần"
        action = "Siết stop"
        stop = price * 0.98
        note = "Bắt đầu nguy hiểm → giảm rủi ro"

    # 🟥 GÀ GÃY (bán)
    else:
        status = "🟥 Gà gãy"
        action = "BÁN NGAY"
        stop = None
        note = "Gãy cấu trúc → không giữ"

    return pnl, status, action, stop, note


# ===== XỬ LÝ =====
results = []

for _, row in df.iterrows():

    pnl, status, action, stop, note = classify(row)

    results.append({
        "Mã": row["Mã"],
        "Giá mua": row["Giá mua"],
        "Giá hiện tại": row["Giá hiện tại"],
        "% Lãi/Lỗ": round(pnl,2),
        "Trạng thái": status,
        "Hành động": action,
        "Stop gợi ý": "-" if stop is None else round(stop,2),
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

# ===== ALERT BOX =====
st.subheader("🚨 Cảnh báo nhanh")

for _, row in result_df.iterrows():
    if "🟥" in row["Trạng thái"]:
        st.error(f"{row['Mã']} → GÀ GÃY → BÁN NGAY")
    elif "⚠️" in row["Trạng thái"]:
        st.warning(f"{row['Mã']} → YẾU DẦN → SIẾT STOP")
    elif "🟩" in row["Trạng thái"]:
        st.success(f"{row['Mã']} → GÀ CHẠY → GIỮ")
