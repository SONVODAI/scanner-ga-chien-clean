import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import yfinance as yf

st.set_page_config(layout="wide")

# ================= WATCHLIST =================
WATCHLIST = [
"VCB","BID","CTG","TCB","MBB","VPB","STB","HDB","ACB","SHB","TPB","LPB","EIB","MSB","VIB","OCB",
"SSI","VIX","SHS","MBS","HCM","VCI","VND","FTS","BSI",
"VHM","VIC","NLG","KDH","DXG","TCH","DIG","PDR","NVL",
"GVR","PHR","DPR",
"MWG","DGW","FRT","PNJ","MSN",
"REE","GEX","PC1","POW",
"DPM","DCM","DGC","BFC",
"BSR","PVS","PVD","PLX","GAS",
"HAH","GMD","VSC",
"VTP","CTR","FPT",
"VHC","ANV",
"CTD","HHV","FCN","VCG",
"HPG","HSG","NKG"
]

# ================= DATA FETCH =================
@st.cache_data(ttl=900)
def fetch_data(symbol):
    try:
        df = yf.download(symbol + ".VN", period="6mo", progress=False)

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "Close": "close",
            "Volume": "volume"
        })

        return df

    except:
        return pd.DataFrame()
        return df

    except:
        return pd.DataFrame()

# ================= INDICATORS =================
def calc_indicators(df):
    df = df.copy()

    df["EMA9"] = df["close"].ewm(span=9).mean()

    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    df["OBV"] = (np.sign(df["close"].diff().fillna(0)) * df["volume"]).cumsum()
    df["OBV_EMA"] = df["OBV"].ewm(span=9).mean()

    return df

# ================= CLASSIFY =================
def classify(row):
    rsi = row["RSI"]
    ema9 = row["EMA9"]
    price = row["close"]
    obv = row["OBV"]
    obv_ema = row["OBV_EMA"]

    if pd.isna(rsi):
        return "AVOID"

    dist = (price - ema9)/ema9*100 if ema9 != 0 else 0

    if 70 <= rsi < 75 and price > ema9 and obv > obv_ema:
        return "STRONG_TREND"

    elif 60 <= rsi < 70 and abs(dist) < 4:
        return "BUY_PULL"

    elif 45 < rsi < 60:
        return "BUY_EARLY"

    elif rsi >= 75:
        return "WAIT_PULL"

    elif 40 <= rsi <= 50:
        return "ACCUMULATION"

    else:
        return "AVOID"

# ================= UI =================
st.title("🔥 SCANNER GÀ CHIẾN V15 CLEAN")

if st.button("🚀 SCAN"):

    results = []

    progress = st.progress(0)

    for i, symbol in enumerate(WATCHLIST):
        df = fetch_data(symbol)

        if df.empty:
            continue

        df = calc_indicators(df)
        row = df.iloc[-1]

        results.append({
            "symbol": symbol,
            "price": round(row["close"], 2),
            "RSI": round(row["RSI"], 2),
            "action": classify(row)
        })

        progress.progress((i+1)/len(WATCHLIST))

    df = pd.DataFrame(results)

    if df.empty:
        st.warning("Không có dữ liệu")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            st.subheader("BUY_PULL")
            st.dataframe(df[df.action=="BUY_PULL"])

        with c2:
            st.subheader("BUY_EARLY")
            st.dataframe(df[df.action=="BUY_EARLY"])

        with c3:
            st.subheader("WAIT_PULL")
            st.dataframe(df[df.action=="WAIT_PULL"])

        with c4:
            st.subheader("ACCUMULATION")
            st.dataframe(df[df.action=="ACCUMULATION"])

        with c5:
            st.subheader("🔥 STRONG TREND")
            st.dataframe(df[df.action=="STRONG_TREND"])
