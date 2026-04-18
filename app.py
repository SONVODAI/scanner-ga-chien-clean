import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến", layout="centered")

st.title("🐔 Scanner Gà Chiến PRO")

# ===== INPUT =====
tickers_input = st.text_area(
    "Nhập danh sách mã (mỗi dòng 1 mã, ví dụ: HPG.VN)",
    value="HPG.VN\nFPT.VN\nMWG.VN\nSSI.VN"
)

tickers = [t.strip().upper() for t in tickers_input.split("\n") if t.strip()]

results = []

# ===== LOOP QUÉT =====
for ticker in tickers:
    try:
        df = yf.download(ticker, period="6mo", progress=False)

        if df is None or df.empty or "Close" not in df.columns:
            continue

        close = df["Close"]

        # Fix trường hợp MultiIndex
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        close = pd.to_numeric(close, errors="coerce").dropna()

        if close.empty:
            continue

        # ===== EMA9 =====
        ema9 = close.ewm(span=9, adjust=False).mean()

        # ===== RSI =====
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        latest_close = close.iloc[-1]
        latest_ema9 = ema9.iloc[-1]
        latest_rsi = rsi.iloc[-1]

        # ===== CHẤM ĐIỂM =====
        score = 0

        if latest_close > latest_ema9:
            score += 1

        if latest_rsi > 55:
            score += 1

        if latest_rsi > rsi.rolling(9).mean().iloc[-1]:
            score += 1

        # ===== XẾP LOẠI =====
        if score == 3:
            status = "🟩 Gà chiến"
        elif score == 2:
            status = "🟨 Theo dõi"
        else:
            status = "🟥 Loại"

        results.append({
            "Ticker": ticker,
            "Close": round(float(latest_close), 2),
            "EMA9": round(float(latest_ema9), 2),
            "RSI": round(float(latest_rsi), 2),
            "Score": score,
            "Status": status
        })

    except:
        continue

# ===== HIỂN THỊ =====
if results:
    df_result = pd.DataFrame(results)

    # Sắp xếp mạnh → yếu
    df_result = df_result.sort_values(by="Score", ascending=False)

    st.write("## 📊 Kết quả quét")
    st.dataframe(df_result, use_container_width=True)

    # Top gà chiến
    st.write("## 🔥 Top Gà Chiến")
    st.dataframe(df_result[df_result["Score"] == 3])

else:
    st.warning("⚠️ Không có dữ liệu hợp lệ")
