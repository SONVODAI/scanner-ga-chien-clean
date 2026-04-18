import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến PRO V2", layout="centered")

st.title("🐔 Scanner Gà Chiến PRO V2")

# ================= INPUT =================
tickers_input = st.text_area(
    "Nhập danh sách mã (mỗi dòng 1 mã, ví dụ: HPG.VN)",
    height=150
)

tickers = [t.strip().upper() for t in tickers_input.split("\n") if t.strip()]

# ================= MARKET SCORE (giả lập) =================
# Sau này sẽ nâng cấp theo VNINDEX
market_score = st.slider("Market Score (điểm thị trường)", 1, 10, 8)

results = []

# ================= LOOP =================
for ticker in tickers:
    try:
        data = yf.download(ticker, period="6mo")

        if data is None or data.empty or "Close" not in data.columns:
            continue

        # ===== EMA9 =====
        data["EMA9"] = data["Close"].ewm(span=9).mean()

        # ===== RSI =====
        delta = data["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        data["RSI"] = 100 - (100 / (1 + rs))
        data["RSI_EMA9"] = data["RSI"].ewm(span=9).mean()

        # ===== OBV =====
        direction = data["Close"].diff()
        data["OBV"] = ((direction > 0) * data["Volume"] -
                       (direction < 0) * data["Volume"]).cumsum()
        data["OBV_EMA9"] = data["OBV"].ewm(span=9).mean()

        latest = data.iloc[-1]

        # ================= SCORE =================
        score = 0

        if latest["Close"] > latest["EMA9"]:
            score += 1

        if latest["RSI"] > 55:
            score += 1

        if latest["RSI"] > latest["RSI_EMA9"]:
            score += 1

        if latest["OBV"] > latest["OBV_EMA9"]:
            score += 1

        if data["OBV"].iloc[-1] > data["OBV"].iloc[-2]:
            score += 1

        # ================= PHÂN LOẠI =================
        if score >= 4:
            status = "🟩 ƯU TIÊN MUA"
        elif score == 3:
            status = "🟨 THEO DÕI"
        elif score == 2:
            status = "🟦 EARLY REVERSAL"
        else:
            status = "🟥 LOẠI"

        # ================= GOLD SCORE =================
        gold_score = score * market_score if market_score >= 8 else 0

        results.append({
            "Ticker": ticker,
            "Close": round(latest["Close"], 2),
            "EMA9": round(latest["EMA9"], 2),
            "RSI": round(latest["RSI"], 2),
            "Score": score,
            "Gold Score": gold_score,
            "Status": status
        })

    except:
        continue

# ================= OUTPUT =================
if results:
    df = pd.DataFrame(results).sort_values(by="Score", ascending=False)

    st.subheader("📊 Kết quả quét")
    st.dataframe(df, use_container_width=True)

    # ===== TOP GÀ CHIẾN =====
    top = df[df["Score"] >= 4]

    if not top.empty:
        st.subheader("🔥 Top Gà Chiến")
        st.dataframe(top, use_container_width=True)

    # ===== KHUYẾN NGHỊ =====
    st.subheader("🧠 Gợi ý hành động")

    if market_score < 8:
        st.warning("⚠️ Thị trường yếu → Không nên mua")
    else:
        if not top.empty:
            st.success("🚀 Có gà chiến → Ưu tiên mua")
        else:
            st.info("👀 Chưa có gà mạnh → Chờ thêm")

else:
    st.warning("Chưa có dữ liệu hợp lệ")
