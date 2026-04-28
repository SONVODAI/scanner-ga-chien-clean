import streamlit as st
import pandas as pd
import os

# =========================
# CONFIG
# =========================
st.set_page_config(layout="wide")
FILE_NAME = "portfolio.csv"

st.title("🔥 Portfolio Gà Chiến – V21 (Thực chiến)")

# =========================
# LOAD DATA
# =========================
def load_data():
    if os.path.exists(FILE_NAME):
        return pd.read_csv(FILE_NAME)
    return pd.DataFrame(columns=["Mã", "Giá mua", "Giá hiện tại", "%NAV"])

def save_data(df):
    df.to_csv(FILE_NAME, index=False)

df = load_data()

# =========================
# SIDEBAR INPUT
# =========================
st.sidebar.header("📌 Nhập / sửa danh mục")

ma = st.sidebar.text_input("Mã cổ phiếu").upper()
gia_mua = st.sidebar.number_input("Giá mua", min_value=0.0, step=100.0)
gia_hien_tai = st.sidebar.number_input("Giá hiện tại", min_value=0.0, step=100.0)
nav = st.sidebar.number_input("% NAV", min_value=0.0, step=0.5)

col1, col2 = st.sidebar.columns(2)

# SAVE
with col1:
    if st.button("✅ Lưu mã"):
        if ma:
            if ma in df["Mã"].values:
                df.loc[df["Mã"] == ma] = [ma, gia_mua, gia_hien_tai, nav]
            else:
                df.loc[len(df)] = [ma, gia_mua, gia_hien_tai, nav]
            save_data(df)
            st.success(f"Đã lưu {ma}")
            st.rerun()

# DELETE
with col2:
    if st.button("🗑️ Xóa mã"):
        df = df[df["Mã"] != ma]
        save_data(df)
        st.warning("Đã xóa")
        st.rerun()

# RESET
if st.sidebar.button("❌ Xóa toàn bộ"):
    df = pd.DataFrame(columns=df.columns)
    save_data(df)
    st.warning("Đã reset")
    st.rerun()

st.sidebar.info("👉 Nhập giá từ bảng điện → chính xác tuyệt đối")

# =========================
# LOGIC ĐÁNH GIÁ
# =========================
def evaluate(row):
    buy = row["Giá mua"]
    price = row["Giá hiện tại"]

    if price <= 0 or buy <= 0:
        return None, None, "⚪ Chưa đủ dữ liệu", "", None, "CHỜ"

    pnl = (price - buy) / buy * 100

    # ===== CHẤM ĐIỂM =====
    score = 0

    if pnl > 0:
        score += 3
    if pnl > 5:
        score += 3
    if pnl > 10:
        score += 2
    if pnl < -3:
        score -= 3

    # ===== TRẠNG THÁI =====
    if score >= 7:
        status = "🟢 Gà chạy"
        action = "GIỮ / CÓ THỂ MUA THÊM"
    elif score >= 4:
        status = "🟡 Gà ổn"
        action = "GIỮ"
    elif score >= 1:
        status = "🟠 Yếu dần"
        action = "GIẢM"
    else:
        status = "🔴 Gãy"
        action = "BÁN NGAY"

    # ===== STOP =====
    stop = buy * 0.95

    return round(price,0), round(pnl,2), status, "", round(stop,0), action

# =========================
# DISPLAY
# =========================
st.subheader("📊 Danh mục hiện tại")

if len(df) == 0:
    st.info("Chưa có danh mục")
else:
    result = []

    for _, row in df.iterrows():
        price, pnl, status, warn, stop, action = evaluate(row)

        result.append({
            "Mã": row["Mã"],
            "Giá mua": row["Giá mua"],
            "Giá hiện tại": price,
            "% Lãi/Lỗ": pnl,
            "%NAV": row["%NAV"],
            "Trạng thái": status,
            "Stoploss": stop,
            "Hành động": action
        })

    result_df = pd.DataFrame(result)

    st.dataframe(result_df, use_container_width=True)

    # ===== SUMMARY =====
    st.markdown("### 📌 Tổng quan")

    col1, col2, col3 = st.columns(3)

    avg_pnl = result_df["% Lãi/Lỗ"].dropna().mean()
    total_nav = result_df["%NAV"].sum()

    col1.metric("Lãi/Lỗ TB", f"{round(avg_pnl,2)}%")
    col2.metric("Tổng NAV", f"{round(total_nav,2)}%")
    col3.metric("Số mã", len(result_df))
