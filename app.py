import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến", layout="centered")

st.title("🐔 Scanner Gà Chiến")

ticker = st.text_input("Nhập mã cổ phiếu (ví dụ: FPT.VN, HPG.VN):").upper().strip()

if ticker:
    df = yf.download(ticker, period="6mo", auto_adjust=False, progress=False)

    if df is None or df.empty:
        st.error("❌ Không lấy được dữ liệu. Hãy thử mã như HPG.VN")
    else:
        close = df["Close"]

        # Nếu yfinance trả về DataFrame nhiều tầng thì lấy cột đầu tiên
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        close = pd.to_numeric(close, errors="coerce").dropna()

        if close.empty:
            st.error("❌ Không có dữ liệu giá đóng cửa.")
        else:
            ema9 = close.ewm(span=9, adjust=False).mean()

            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            chart_df = pd.DataFrame({
                "Close": close,
                "EMA9": ema9
            })

            st.line_chart(chart_df)

            latest_close = float(close.iloc[-1])
            latest_ema9 = float(ema9.iloc[-1])
            latest_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None

            st.write("### 📊 Kết quả:")

            if latest_close > latest_ema9:
                st.success("✅ Giá trên EMA9 → Xu hướng OK")
            else:
                st.error("❌ Giá dưới EMA9 → Chưa đạt")

            if latest_rsi is None:
                st.warning("⚠️ RSI chưa đủ dữ liệu")
            elif latest_rsi > 55:
                st.success("✅ RSI > 55 → Mạnh")
            else:
                st.warning("⚠️ RSI yếu")
