import streamlit as st
import pandas as pd
import requests
st.set_page_config(page_title="Portfolio Manager PRO V1.5", layout="wide")

st.title("🐔 Portfolio Manager PRO V15 – 5 Trục + Stop Engine 2.0")

# ================== INPUT ==================
st.sidebar.header("📥 Nhập danh mục")

input_text = st.sidebar.text_area(
    "Format: Mã,Giá mua,%NAV\nVD: MBB,23000,10",
    height=200
)

save_btn = st.sidebar.button("💾 Lưu danh mục")

# ================== PARSE DATA ==================
def parse_input(text):
    data = []
    lines = text.strip().split("\n")

    for line in lines:
        try:
            parts = line.split(",")
            ticker = parts[0].strip().upper()
            buy_price = float(parts[1])
            nav = float(parts[2])

            data.append({
                "Mã": ticker,
                "Giá mua": buy_price,
                "%NAV": nav
            })
        except:
            continue

    return pd.DataFrame(data)

# ================== FAKE PRICE (TẠM) ==================
# 👉 Sau này sẽ thay bằng API VN
def get_price(ticker):
    try:
        from vnstock import stock_historical_data

        df = stock_historical_data(
            symbol=ticker,
            start_date="2024-01-01",
            end_date="2026-12-31",
            resolution="1D",
            type="stock",
            beautify=True
        )

        if df is not None and not df.empty:
            return float(df["close"].iloc[-1])
        else:
            return None
    except:
        return None
# ================== MAIN ==================
st.subheader("📊 Danh mục hiện tại – V15")

if save_btn and input_text:

    df = parse_input(input_text)

    if df.empty:
        st.warning("⚠️ Không đọc được dữ liệu")
    else:
        result = pd.DataFrame()

        for _, row in df.iterrows():
            ticker = row["Mã"]
            buy_price = row["Giá mua"]
            nav = row["%NAV"]

            current_price = get_price(ticker)

            # ===== xử lý =====
            if current_price is None or current_price == 0:
                status = "⚠️ Lỗi data"
                action = "Check mã / nguồn dữ liệu"
                pl_percent = None
            else:
                pl_percent = (current_price - buy_price) / buy_price * 100
                status = "OK"
                action = "Theo dõi"

            data_row = {
                "Mã": ticker,
                "Giá mua": buy_price,
                "Giá hiện tại": current_price,
                "%NAV": nav,
                "Trạng thái": status,
                "Hành động": action
            }

            if pl_percent is not None:
                data_row["Lãi/Lỗ (%)"] = round(pl_percent, 2)

            result = pd.concat([result, pd.DataFrame([data_row])], ignore_index=True)

        # ===== HIỂN THỊ =====
        st.dataframe(result, use_container_width=True)

        st.success("✅ Đã lưu danh mục")

        # ================== METRICS ==================
        col1, col2, col3 = st.columns(3)

        total_nav = result["%NAV"].sum()
        col1.metric("📊 Tổng %NAV", round(total_nav, 2))

        if "Lãi/Lỗ (%)" in result.columns:
            avg_pl = result["Lãi/Lỗ (%)"].mean()
            col2.metric("📈 Lãi/Lỗ TB (%)", round(avg_pl, 2))
        else:
            col2.metric("📈 Lãi/Lỗ TB (%)", "N/A")

        col3.metric("📦 Số mã", len(result))

else:
    st.info("👉 Chưa có danh mục")
