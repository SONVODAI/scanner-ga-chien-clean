import streamlit as st
import pandas as pd
import os

# ================= CONFIG =================
st.set_page_config(page_title="Portfolio Manager PRO V5", layout="wide")
st.title("🐔 Portfolio Manager PRO V5 – Nuôi Gà Chiến")

DATA_FILE = "portfolio.csv"

# ================= DATA =================
def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Mã", "Giá mua", "Giá hiện tại", "%NAV"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

def parse_full_input(text):
    rows = []
    for line in text.split("\n"):
        if not line.strip():
            continue
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

def update_prices(df, text):
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            code, price = line.split(",")
            code = code.strip().upper()
            price = float(price)
            df.loc[df["Mã"] == code, "Giá hiện tại"] = price
        except:
            continue
    return df

# ================= ENGINE =================
def evaluate(row):
    buy = float(row["Giá mua"])
    price = float(row["Giá hiện tại"])
    nav = float(row["%NAV"])

    pnl = (price - buy) / buy * 100

    # 1) GÀ CHẠY
    if pnl >= 5:
        status = "🟩 Gà chạy"
        action = "Giữ + trailing"
        stop = price * 0.97
        risk = "Thấp"
        nav_action = "Có thể tăng"
        early = "Đã chạy"
        note = "Đang có lãi rõ → ưu tiên giữ, không bán sớm"

    # 2) EARLY SIGNAL – GÀ SẮP CHẠY
    elif 3 <= pnl < 5:
        status = "🟦 Gà sắp chạy"
        action = "Canh tăng NAV"
        stop = buy * 0.98
        risk = "Thấp-Trung bình"
        nav_action = "Tăng nhẹ nếu chart xác nhận"
        early = "EARLY BUY"
        note = "Sát ngưỡng chạy → soi chart, nếu đẹp có thể tăng tỷ trọng"

    # 3) GÀ NGHỈ
    elif -3 <= pnl < 3:
        status = "🟨 Gà nghỉ"
        action = "Theo dõi"
        stop = buy * 0.95
        risk = "Trung bình"
        nav_action = "Giữ nguyên"
        early = "Chưa có"
        note = "Chưa rõ xu hướng → quan sát"

    # 4) YẾU DẦN
    elif -6 <= pnl < -3:
        status = "⚠️ Yếu dần"
        action = "Siết stop"
        stop = price * 0.98
        risk = "Cao"
        nav_action = "Giảm 1/2"
        early = "Không"
        note = "Nguy hiểm → chuẩn bị thoát, không bình quân giá"

    # 5) GÀ GÃY
    else:
        status = "🟥 Gà gãy"
        action = "BÁN NGAY"
        stop = None
        risk = "Rất cao"
        nav_action = "Thoát toàn bộ"
        early = "Không"
        note = "Gãy cấu trúc → không giữ"

    return {
        "Mã": row["Mã"],
        "Giá mua": buy,
        "Giá hiện tại": price,
        "%NAV": nav,
        "% Lãi/Lỗ": round(pnl, 2),
        "Trạng thái": status,
        "Early Signal": early,
        "Hành động": action,
        "Stop gợi ý": "-" if stop is None else round(stop, 2),
        "Rủi ro": risk,
        "NAV đề xuất": nav_action,
        "Ghi chú": note
    }

# ================= LOAD =================
df = load_data()

# ================= SIDEBAR =================
st.sidebar.header("1️⃣ Nhập / Lưu danh mục")

full_text = st.sidebar.text_area(
    "Nhập full: Mã, Giá mua, Giá hiện tại, %NAV",
    "",
    height=130
)

if st.sidebar.button("💾 Lưu danh mục"):
    new_df = parse_full_input(full_text)
    if not new_df.empty:
        save_data(new_df)
        df = new_df
        st.sidebar.success("Đã lưu danh mục.")
    else:
        st.sidebar.warning("Chưa có dữ liệu hợp lệ.")

st.sidebar.header("2️⃣ Cập nhật giá mới")

price_text = st.sidebar.text_area(
    "Chỉ nhập: Mã, Giá hiện tại",
    "",
    height=110
)

if st.sidebar.button("🔄 Cập nhật giá"):
    if not df.empty:
        df = update_prices(df, price_text)
        save_data(df)
        st.sidebar.success("Đã cập nhật giá.")
    else:
        st.sidebar.warning("Chưa có danh mục để cập nhật.")

# ================= PROCESS =================
results = []
for _, row in df.iterrows():
    try:
        results.append(evaluate(row))
    except:
        continue

result_df = pd.DataFrame(results)

# ================= DISPLAY =================
st.subheader("📊 Danh mục hiện tại")
st.dataframe(result_df, use_container_width=True)

if not result_df.empty:
    avg_pnl = result_df["% Lãi/Lỗ"].mean()
    total_nav = result_df["%NAV"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("📈 Lãi/Lỗ trung bình (%)", round(avg_pnl, 2))
    col2.metric("💰 Tổng %NAV đang dùng", round(total_nav, 2))
    col3.metric("🧺 Số mã đang nắm", len(result_df))

# ================= ALERT =================
st.subheader("🚨 Cảnh báo nhanh")

if result_df.empty:
    st.info("Chưa có dữ liệu danh mục.")
else:
    for _, row in result_df.iterrows():
        code = row["Mã"]

        if "🟥" in row["Trạng thái"]:
            st.error(f"{code} → GÀ GÃY → BÁN NGAY / THOÁT TOÀN BỘ")
        elif "⚠️" in row["Trạng thái"]:
            st.warning(f"{code} → YẾU DẦN → SIẾT STOP / GIẢM 1/2")
        elif "🟦" in row["Trạng thái"]:
            st.info(f"{code} → GÀ SẮP CHẠY → SOI CHART, CÓ THỂ TĂNG NAV")
        elif "🟩" in row["Trạng thái"]:
            st.success(f"{code} → GÀ CHẠY → GIỮ + TRAILING")

# ================= GUIDE =================
st.subheader("📌 Quy tắc dùng nhanh")
st.write("""
- Lần đầu: nhập đầy đủ **Mã, Giá mua, Giá hiện tại, %NAV** rồi bấm **Lưu danh mục**.
- Mỗi ngày: chỉ nhập **Mã, Giá hiện tại** ở ô cập nhật giá rồi bấm **Cập nhật giá**.
- 🟦 Gà sắp chạy = chưa mua/tăng vội, phải soi chart xác nhận.
- 🟥 Gà gãy = ưu tiên xử lý trước.
""")
