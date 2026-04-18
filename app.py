import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến", layout="centered")

st.title("🐔 Scanner Gà Chiến")

ticker = st.text_input("Nhập mã cổ phiếu (ví dụ: FPT.VN, HPG.VN):").upper()

if ticker:
    data = yf.download(ticker, period="6mo")

    # Kiểm tra dữ liệu
    if data is not None and not data.empty and "Close" in data.columns:

        # Tính EMA9
        data["EMA9"] = data["Close"].ewm(span=9).mean()

        # Tính RSI (đơn giản)
        delta = data["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        data["RSI"] = 100 - (100 / (1 + rs))

        # Vẽ chart
        st.line_chart(data[["Close", "EMA9"]])

        latest = data.iloc[-1]

        st.write("### 📊 Kết quả:")

        # EMA check
        if latest["Close"] > latest["EMA9"]:
            st.success("✅ Giá trên EMA9 → Xu hướng OK")
        else:
            st.error("❌ Giá dưới EMA9 → Chưa đạt")

        # RSI check
        if latest["RSI"] > 55:
            st.success("✅ RSI > 55 → Mạnh")
        else:
            st.warning("⚠️ RSI yếu")

    else:
        st.error("❌ Không lấy được dữ liệu. Kiểm tra mã (ví dụ: HPG.VN)")
