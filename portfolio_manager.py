import streamlit as st
import pandas as pd
import numpy as np
from vnstock import stock_historical_data

st.set_page_config(layout="wide")
st.title("🐔 GÀ CHIẾN TERMINAL V7 (Scanner + Portfolio)")

# ================= SCANNER =================
@st.cache_data(ttl=300)
def get_data(symbol):
    try:
        df = stock_historical_data(symbol, "2024-01-01")
        return df
    except:
        return None

def calc_indicator(df):
    if df is None or len(df) < 30:
        return None

    close = df["close"]
    volume = df["volume"]

    # EMA9
    ema9 = close.ewm(span=9).mean()

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # OBV
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    obv_ema = obv.ewm(span=9).mean()

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()

    return {
        "Giá_OK": int(close.iloc[-1] > ema9.iloc[-1]),
        "RSI": round(rsi.iloc[-1], 1),
        "RSI_OK": int(rsi.iloc[-1] > rsi.ewm(span=9).mean().iloc[-1]),
        "OBV_OK": int(obv.iloc[-1] > obv_ema.iloc[-1]),
        "MACD_OK": int(macd.iloc[-1] > signal.iloc[-1]),
        "VOL_OK": int(volume.iloc[-1] > volume.rolling(20).mean().iloc[-1])
    }

# ================= TAB =================
tab1, tab2 = st.tabs(["🧠 Scanner", "💰 Portfolio"])

# ================= TAB 1 =================
with tab1:
    st.subheader("Quét nhanh cổ phiếu")

    symbols = st.text_input("Nhập mã (cách nhau dấu phẩy)", "VJC,VNM,VSC,MSB")

    if st.button("SCAN"):
        result = []
        for code in symbols.split(","):
            code = code.strip().upper()
            df = get_data(code)
            ind = calc_indicator(df)

            if ind:
                ind["Mã"] = code
                result.append(ind)

        scanner_df = pd.DataFrame(result)
        st.session_state["scanner"] = scanner_df
        st.dataframe(scanner_df, use_container_width=True)

# ================= SCORE =================
def score(row):
    s = 0
    if row["Giá_OK"]: s += 2
    if row["RSI"] >= 55: s += 2
    if row["RSI_OK"]: s += 1
    if row["OBV_OK"]: s += 3
    if row["MACD_OK"]: s += 1.5
    if row["VOL_OK"]: s += 0.5
    return round(s,2)

def classify(s):
    if s >= 8.5: return "🟩 Gà chiến"
    elif s >= 7: return "🟦 Sắp chạy"
    elif s >= 5.5: return "🟨 Nghỉ"
    elif s >= 4: return "⚠️ Yếu"
    else: return "🟥 Gãy"

# ================= TAB 2 =================
with tab2:
    st.subheader("Danh mục của anh")

    input_text = st.text_area(
        "Nhập: Mã, Giá mua, %NAV",
        "VJC,172.8,5\nVSC,25.3,3"
    )

    if "scanner" not in st.session_state:
        st.warning("👉 Chưa scan dữ liệu ở tab Scanner")
    else:
        scanner_df = st.session_state["scanner"]

        rows = []
        for line in input_text.split("\n"):
            try:
                code, buy, nav = line.split(",")
                code = code.strip().upper()
                buy = float(buy)

                sc = scanner_df[scanner_df["Mã"] == code]

                if len(sc) == 0:
                    continue

                sc = sc.iloc[0]

                price = buy  # tạm, có thể nâng cấp lấy realtime

                pnl = (price - buy)/buy*100
                sc_score = score(sc)
                status = classify(sc_score)

                if "🟥" in status:
                    action = "BÁN NGAY"
                elif "⚠️" in status:
                    action = "SIẾT STOP"
                elif "🟦" in status:
                    action = "CANH MUA"
                elif "🟩" in status:
                    action = "GIỮ"
                else:
                    action = "THEO DÕI"

                rows.append({
                    "Mã": code,
                    "Giá mua": buy,
                    "Điểm": sc_score,
                    "Trạng thái": status,
                    "Hành động": action
                })

            except:
                continue

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
