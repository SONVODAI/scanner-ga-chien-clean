import streamlit as st
import pandas as pd

# ===== CONFIG =====
st.set_page_config(page_title="Portfolio Manager PRO", layout="wide")

st.title("🐔 Portfolio Manager PRO – Nuôi Gà Chiến")

# ===== INPUT =====
st.sidebar.header("Nhập danh mục")

portfolio_text = st.sidebar.text_area(
    "Nhập (Mã, Giá mua, Giá hiện tại, %NAV)",
    "MBB,22,23.5,30\nVND,18,17.5,20\nDIG,25,26,10"
)

# ===== PARSE DATA =====
def parse_portfolio(text):
    rows = []
    for line in text.split("\n"):
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
    return pd.DataFrame(rows)

df = parse_portfolio(portfolio_text)

# ===== STOP ENGINE 2.0 =====
def stop_engine(row):
    buy = row["Giá mua"]
    price = row["Giá hiện tại"]

    pnl = (price - buy) / buy * 100

    # 🟩 GÀ CHẠY
    if pnl >= 5:
        status = "🟩 Gà chạy"
        action = "Giữ + trailing"
        stop = price * 0.97
        risk = "Thấp"
        note = "Có lãi → giữ, trailing theo giá"

    # 🟨 GÀ NGHỈ
    elif -3 <= pnl < 5:
        status = "🟨 Gà nghỉ"
        action = "Theo dõi"
        stop = buy * 0.95
        risk = "Trung bình"
        note = "Chưa rõ xu hướng → quan sát"

    # ⚠️ YẾU DẦN
    elif -6 <= pnl < -3:
        status = "⚠️ Yếu dần"
        action = "Siết stop"
        stop = price * 0.98
        risk = "Cao"
        note = "Nguy hiểm → chuẩn bị thoát"

    # 🟥 GÀ GÃY
    else:
        status = "🟥 Gà gãy"
        action = "BÁN NGAY"
        stop = None
        risk = "Rất cao"
        note = "Gãy cấu trúc → không giữ"

    return pnl, status, action, stop, risk, note

# ===== PROCESS =====
def process(df):
    results = []

    for _, row in df.iterrows():
        pnl, status, action, stop, risk, note = stop_engine(row)

        results.append({
            "Mã": row["Mã"],
            "Giá mua": row["Giá mua"],
            "Giá hiện tại": row["Giá hiện tại"],
            "% Lãi/Lỗ": round(pnl, 2),
            "Trạng thái": status,
            "Hành động": action,
            "Stop gợi ý": "-" if stop is None else round(stop, 2),
            "Rủi ro": risk,
            "Ghi chú": note
        })

    return pd.DataFrame(results)

result_df = process(df)

# ===== DISPLAY =====
st.subheader("📊 Danh mục hiện tại")

st.dataframe(result_df, use_container_width=True)

# ===== SUMMARY =====
if not result_df.empty:
    avg = result_df["% Lãi/Lỗ"].mean()
    st.metric("📈 Lãi/Lỗ trung bình (%)", round(avg, 2))

# ===== ALERT SYSTEM =====
st.subheader("🚨 Cảnh báo nhanh")

for _, row in result_df.iterrows():
    if "🟥" in row["Trạng thái"]:
        st.error(f"{row['Mã']} → GÀ GÃY → BÁN NGAY")
    elif "⚠️" in row["Trạng thái"]:
        st.warning(f"{row['Mã']} → YẾU DẦN → SIẾT STOP")
    elif "🟩" in row["Trạng thái"]:
        st.success(f"{row['Mã']} → GÀ CHẠY → GIỮ")
