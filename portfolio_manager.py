import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Portfolio Manager PRO V6", layout="wide")
st.title("🐔 Portfolio Manager PRO V6 – Nuôi Gà Chiến Full Logic")

DATA_FILE = "portfolio.csv"

COLUMNS = [
    "Mã", "Giá mua", "Giá hiện tại", "%NAV",
    "Giá_OK", "RSI", "RSI_OK", "OBV_OK", "MACD_OK", "VOL_OK"
]

def load_data():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = 0
        return df[COLUMNS]
    return pd.DataFrame(columns=COLUMNS)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

def to_bool(x):
    return str(x).strip().lower() in ["1", "yes", "y", "true", "ok", "đúng", "co", "có"]

def parse_full_input(text):
    rows = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            parts = [x.strip() for x in line.split(",")]

            code = parts[0].upper()
            buy = float(parts[1])
            price = float(parts[2])
            nav = float(parts[3])

            gia_ok = int(to_bool(parts[4]))
            rsi = float(parts[5])
            rsi_ok = int(to_bool(parts[6]))
            obv_ok = int(to_bool(parts[7]))
            macd_ok = int(to_bool(parts[8]))
            vol_ok = int(to_bool(parts[9]))

            rows.append({
                "Mã": code,
                "Giá mua": buy,
                "Giá hiện tại": price,
                "%NAV": nav,
                "Giá_OK": gia_ok,
                "RSI": rsi,
                "RSI_OK": rsi_ok,
                "OBV_OK": obv_ok,
                "MACD_OK": macd_ok,
                "VOL_OK": vol_ok
            })
        except:
            continue

    return pd.DataFrame(rows, columns=COLUMNS)

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

def score_stock(row):
    score = 0

    # Trục 1: Giá / EMA9 / cấu trúc
    if row["Giá_OK"] == 1:
        score += 2

    # Trục 2: RSI
    if row["RSI"] >= 55:
        score += 2
    elif row["RSI"] >= 50:
        score += 1

    if row["RSI_OK"] == 1:
        score += 1

    # Trục 3: OBV – trọng số cao nhất
    if row["OBV_OK"] == 1:
        score += 3

    # Trục 4: MACD
    if row["MACD_OK"] == 1:
        score += 1.5

    # Trục 5: Volume
    if row["VOL_OK"] == 1:
        score += 0.5

    return round(score, 2)

def technical_status(score):
    if score >= 8.5:
        return "🟩 Gà chiến"
    elif score >= 7:
        return "🟦 Gà sắp chạy"
    elif score >= 5.5:
        return "🟨 Gà nghỉ khỏe"
    elif score >= 4:
        return "⚠️ Yếu dần"
    else:
        return "🟥 Gãy kỹ thuật"

def decision_engine(row):
    buy = float(row["Giá mua"])
    price = float(row["Giá hiện tại"])
    pnl = (price - buy) / buy * 100

    score = score_stock(row)
    tech = technical_status(score)

    # Stop Engine 2.0 + Technical Logic
    if "🟩" in tech and pnl >= 0:
        action = "GIỮ / CÓ THỂ TĂNG"
        nav_action = "Tăng NAV nếu thị trường ủng hộ"
        stop = price * 0.97
        risk = "Thấp"
        note = "Kỹ thuật mạnh + không âm → ưu tiên giữ"

    elif "🟦" in tech and pnl > -3:
        action = "SOI CHART / CANH TĂNG"
        nav_action = "Tăng nhẹ nếu chart xác nhận"
        stop = buy * 0.98
        risk = "Thấp-Trung bình"
        note = "Gần chuyển pha chạy → theo dõi sát"

    elif "🟨" in tech and -5 < pnl < 5:
        action = "THEO DÕI"
        nav_action = "Giữ nguyên"
        stop = buy * 0.95
        risk = "Trung bình"
        note = "Chưa đủ mạnh để tăng, chưa yếu để bán"

    elif "⚠️" in tech or (-6 <= pnl <= -3):
        action = "SIẾT STOP / GIẢM"
        nav_action = "Giảm 1/2 nếu không hồi"
        stop = price * 0.98
        risk = "Cao"
        note = "Có dấu hiệu yếu → không bình quân giá"

    else:
        action = "BÁN NGAY"
        nav_action = "Thoát toàn bộ"
        stop = "-"
        risk = "Rất cao"
        note = "Gãy kỹ thuật hoặc lỗ sâu → ưu tiên bảo vệ vốn"

    return {
        "Mã": row["Mã"],
        "Giá mua": buy,
        "Giá hiện tại": price,
        "%NAV": row["%NAV"],
        "% Lãi/Lỗ": round(pnl, 2),
        "Điểm 5 trục": score,
        "Trạng thái kỹ thuật": tech,
        "Hành động": action,
        "Stop gợi ý": "-" if stop == "-" else round(stop, 2),
        "NAV đề xuất": nav_action,
        "Rủi ro": risk,
        "Ghi chú": note
    }

df = load_data()

st.sidebar.header("1️⃣ Nhập / Lưu danh mục full")

full_text = st.sidebar.text_area(
    "Format: Mã, Giá mua, Giá hiện tại, %NAV, Giá_OK, RSI, RSI_OK, OBV_OK, MACD_OK, VOL_OK",
    "VJC,172.8,180.5,6,1,62,1,1,1,1\nVSC,25.3,22.2,3,0,42,0,0,0,0",
    height=150
)

if st.sidebar.button("💾 Lưu danh mục"):
    new_df = parse_full_input(full_text)
    if not new_df.empty:
        save_data(new_df)
        df = new_df
        st.sidebar.success("Đã lưu danh mục.")
    else:
        st.sidebar.warning("Dữ liệu chưa hợp lệ.")

st.sidebar.header("2️⃣ Cập nhật giá mới")

price_text = st.sidebar.text_area(
    "Chỉ nhập: Mã, Giá hiện tại",
    "",
    height=100
)

if st.sidebar.button("🔄 Cập nhật giá"):
    df = update_prices(df, price_text)
    save_data(df)
    st.sidebar.success("Đã cập nhật giá.")

results = []
for _, row in df.iterrows():
    try:
        results.append(decision_engine(row))
    except:
        continue

result_df = pd.DataFrame(results)

st.subheader("📊 Danh mục hiện tại – Full Logic Scanner")
st.dataframe(result_df, use_container_width=True)

if not result_df.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric("📈 Lãi/Lỗ TB (%)", round(result_df["% Lãi/Lỗ"].mean(), 2))
    col2.metric("🔥 Điểm kỹ thuật TB", round(result_df["Điểm 5 trục"].mean(), 2))
    col3.metric("💰 Tổng %NAV", round(result_df["%NAV"].sum(), 2))

st.subheader("🚨 Cảnh báo nhanh")

for _, row in result_df.iterrows():
    code = row["Mã"]
    tech = row["Trạng thái kỹ thuật"]
    action = row["Hành động"]

    if "BÁN" in action:
        st.error(f"{code} → {tech} → {action}")
    elif "SIẾT" in action:
        st.warning(f"{code} → {tech} → {action}")
    elif "SOI" in action:
        st.info(f"{code} → {tech} → {action}")
    elif "GIỮ" in action:
        st.success(f"{code} → {tech} → {action}")

st.subheader("📌 Hướng dẫn nhập dữ liệu")
st.write("""
Format đầy đủ:

**Mã, Giá mua, Giá hiện tại, %NAV, Giá_OK, RSI, RSI_OK, OBV_OK, MACD_OK, VOL_OK**

Trong đó:
- **Giá_OK**: giá trên EMA9 / cấu trúc còn tốt = 1, không = 0
- **RSI**: nhập số RSI hiện tại
- **RSI_OK**: RSI trên EMA9 RSI = 1, không = 0
- **OBV_OK**: OBV trên EMA9 OBV = 1, không = 0
- **MACD_OK**: MACD / Histogram tốt = 1, không = 0
- **VOL_OK**: volume ủng hộ = 1, không = 0
""")
