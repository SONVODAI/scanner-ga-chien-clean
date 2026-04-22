import streamlit as st
import pandas as pd
import pandas_ta as ta
from vnstock import stock_historical_data
from datetime import datetime

st.set_page_config(layout="wide")

# ======================
# WATCHLIST
# ======================
WATCHLIST = [
    "VIC","VHM","VRE","VCB","BID","CTG","TCB","MBB","VPB",
    "SSI","VND","HCM","HPG","HSG","NKG",
    "DGC","DCM","DPM","GAS","PVD","PVS",
    "MWG","FPT","VNM","MSN"
]

# ======================
# LOAD DATA VNSTOCK
# ======================
def load_data():
    data_all = []

    for symbol in WATCHLIST:
        try:
            df = stock_historical_data(
                symbol=symbol,
                start_date="2024-01-01",
                end_date=datetime.today().strftime('%Y-%m-%d'),
                resolution="1D",
                type="stock"
            )

            df["EMA9"] = ta.ema(df["close"], length=9)
            df["MA20"] = ta.sma(df["close"], length=20)
            df["RSI"] = ta.rsi(df["close"], length=14)

            # OBV
            df["OBV"] = ta.obv(df["close"], df["volume"])
            df["OBV_EMA9"] = ta.ema(df["OBV"], length=9)

            latest = df.iloc[-1]

            data_all.append({
                "symbol": symbol,
                "price": latest["close"],
                "ema9": latest["EMA9"],
                "ma20": latest["MA20"],
                "rsi": latest["RSI"],
                "obv": latest["OBV"],
                "obv_ema9": latest["OBV_EMA9"],
                "volume": latest["volume"]
            })

        except:
            continue

    return pd.DataFrame(data_all)

# ======================
# CLASSIFY (CHUẨN TRADER)
# ======================
def classify(row):
    price = row["price"]
    ema9 = row["ema9"]
    ma20 = row["ma20"]
    rsi = row["rsi"]
    obv_ok = row["obv"] > row["obv_ema9"]

    dist = (price - ema9) / ema9 * 100

    # CP MẠNH (leader)
    if price > ema9 > ma20 and rsi >= 60 and obv_ok:
        return "CP MẠNH"

    # PULL ĐẸP
    if abs(dist) < 1.5 and rsi >= 55:
        return "PULL ĐẸP"

    # PULL VỪA
    if abs(dist) < 3 and rsi >= 50:
        return "PULL VỪA"

    # BREAK
    if rsi > 60 and dist > 2:
        return "MUA BREAK"

    return "THEO DÕI"

# ======================
# MARKET SCORE
# ======================
def market_score(df):
    score = 0

    if (df["price"] > df["ema9"]).mean() > 0.6:
        score += 4

    if df["rsi"].mean() > 55:
        score += 3

    if (df["obv"] > df["obv_ema9"]).mean() > 0.6:
        score += 4

    if (df["rsi"] > 75).mean() > 0.2:
        score -= 1

    return round(score,1)

# ======================
# RUN
# ======================
st.title("📊 SCANNER GÀ CHIẾN V28")

if st.button("SCAN"):
    df = load_data()

    df["group"] = df.apply(classify, axis=1)

    df["dist"] = (df["price"] - df["ema9"]) / df["ema9"] * 100

    # MARKET
    m = market_score(df)
    st.write(f"Market Score: {m}/13")

    # CP MẠNH
    st.subheader("🔥 CP MẠNH")
    st.dataframe(df[df["group"]=="CP MẠNH"])

    # ENTRY
    st.subheader("🎯 ĐIỂM MUA")
    st.dataframe(df[df["group"].isin(["PULL ĐẸP","PULL VỪA","MUA BREAK"])])

    # FULL
    st.subheader("📋 TỔNG")
    st.dataframe(df.sort_values(by="rsi", ascending=False))
