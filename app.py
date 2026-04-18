import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến", layout="centered")

st.title("🐔 Scanner Gà Chiến")

ticker = st.text_input("Nhập mã cổ phiếu (ví dụ: FPT.VN, HPG.VN):").upper()

if ticker:
    data = yf.download(ticker.upper(), period="6mo")

    if data is not None and not data.empty and "Close" in data.columns:
        data["EMA9"] = data["Close"].ewm(span=9).mean()
        data["RSI"] = 100 - (100 / (1 + data["Close"].pct_change().rolling(14).mean()))

        st.line_chart(data[["Close", "EMA9"]])

        latest = data.iloc[-1]

        st.write("### Kết quả:")

        if latest["Close"] > latest["EMA9"]:
            st.success("✅ Giá trên EMA9 → Xu hướng OK")
        else:
            st.error("❌ Giá dưới EMA9 → Chưa đạt")

        if latest["RSI"] > 55:
            st.success("✅ RSI > 55 → Mạnh")
        else:
            st.warning("⚠️ RSI yếu")
