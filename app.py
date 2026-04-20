import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from vnstock import stock_historical_data

st.set_page_config(layout="wide")

# ================= WATCHLIST =================
WATCHLIST = [
"VCB","BID","CTG","TCB","MBB","VPB","STB","HDB","ACB","SHB",
"SSI","VIX","SHS","HCM","VCI","VND",
"VHM","VIC","DXG","DIG","NVL",
"MWG","FRT","PNJ",
"REE","GEX","PC1",
"DGC","DCM","DPM",
"BSR","PVS","GAS",
"GMD","HAH","VSC",
"FPT","CTR",
"VHC","ANV",
"HPG","HSG","NKG"
]

# ================= DATA =================
@st.cache_data(ttl=600)
def fetch_data(symbol):
    try:
        df = stock_historical_data(
            symbol=symbol,
            start_date="2023-01-01",
            end_date=datetime.now().strftime("%Y-%m-%d"),
            resolution="1D",
            type="stock"
        )

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "close": "close",
            "volume": "volume"
        })

        return df

    except:
        return pd.DataFrame()

# ================= INDICATORS =================
def calc_indicators(df):
    try:
        df = df.copy()

        df["EMA9"] = df["close"].ewm(span=9).mean()

        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))

        df["OBV"] = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()
        df["OBV_EMA"] = df["OBV"].ewm(span=9).mean()

        return df

    except:
        return pd.DataFrame()

# ================= CLASSIFY =================
def classify(row):
    try:
        rsi = float(row["RSI"])
        ema9 = float(row["EMA9"])
        price = float(row["close"])
        obv = float(row["OBV"])
        obv_ema = float(row["OBV_EMA"])

        if np.isnan(rsi):
            return "AVOID"

        dist = (price - ema9) / ema9 * 100

        if rsi >= 65 and price > ema9 and obv > obv_ema:
            return "STRONG_TREND"

        elif 55 <= rsi < 65:
            return "BUY_PULL"

        elif 45 < rsi < 55:
            return "BUY_EARLY"

        elif rsi >= 75:
            return "WAIT_PULL"

        elif 40 <= rsi <= 50:
            return "ACCUMULATION"

        else:
            return "AVOID"

    except:
        return "AVOID"

# ================= UI =================
st.title("🔥 SCANNER GÀ CHIẾN V16 PRO (VN DATA)")

if st.button("🚀 SCAN"):

    results = []

    for symbol in WATCHLIST:

        df = fetch_data(symbol)

        if df.empty:
            continue

        df = calc_indicators(df)

        if df.empty or len(df) < 20:
            continue

        row = df.iloc[-1]

        results.append({
            "symbol": symbol,
            "price": round(row["close"], 2),
            "RSI": round(row["RSI"], 1),
            "action": classify(row)
        })

    if len(results) == 0:
        st.warning("Không có dữ liệu")
    else:
        df = pd.DataFrame(results)

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.subheader("BUY_PULL")
            st.dataframe(df[df.action=="BUY_PULL"])

        with col2:
            st.subheader("BUY_EARLY")
            st.dataframe(df[df.action=="BUY_EARLY"])

        with col3:
            st.subheader("WAIT_PULL")
            st.dataframe(df[df.action=="WAIT_PULL"])

        with col4:
            st.subheader("ACCUMULATION")
            st.dataframe(df[df.action=="ACCUMULATION"])

        with col5:
            st.subheader("🔥 STRONG")
            st.dataframe(df[df.action=="STRONG_TREND"])
