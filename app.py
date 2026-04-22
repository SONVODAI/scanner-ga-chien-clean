import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import time
from datetime import datetime

st.set_page_config(layout="wide")

# ========================
# WATCHLIST
# ========================
WATCHLIST = [
"VCB","BID","CTG","TCB","VPB","MBB","ACB","STB","HDB","TPB","VIB","LPB","MSB","EIB",
"SSI","VND","HCM","SHS","VIX","BSI","FTS",
"HPG","HSG","NKG",
"VHM","VIC","VRE","DXG","DIG","CEO","TCH",
"GAS","PVS","PVD","BSR","PLX",
"GMD","VSC","HAH","VTO","VOS",
"MWG","FRT","DGW","PET","MSN",
"FPT","CTR","VTP",
"DGC","DCM","DPM","LAS","BFC"
]

# ========================
# LOAD DATA (ỔN ĐỊNH)
# ========================
@st.cache_data(ttl=600)
def load_symbol(symbol):
    try:
        df = yf.download(symbol + ".VN", period="6mo", interval="1d", progress=False)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df is None or df.empty or len(df) < 50:
            return None

        return df
    except:
        return None

# ========================
# INDICATORS
# ========================
def calc(df):
    df["ema9"] = df["Close"].ewm(span=9).mean()
    df["ma20"] = df["Close"].rolling(20).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi_ema9"] = df["rsi"].ewm(span=9).mean()

    df["obv"] = (np.sign(df["Close"].diff()) * df["Volume"]).fillna(0).cumsum()
    df["obv_ema9"] = df["obv"].ewm(span=9).mean()

    return df

# ========================
# SCORE (18.4 CORE)
# ========================
def score(row):
    E = 0
    if row["Close"] > row["ema9"]: E += 1
    if row["ema9"] > row["ma20"]: E += 1

    R = 0
    if row["rsi"] > 55: R += 1
    if row["rsi"] > row["rsi_ema9"]: R += 1

    O = 0
    if row["obv"] > row["obv_ema9"]: O += 2

    total = E + R + O
    return E, R, O, total

def classify(E,R,O,total):
    if total >= 5 and O >= 2 and E >= 1:
        return "CP_MẠNH"
    elif total >= 4:
        return "PULL_ĐẸP"
    elif total >= 3:
        return "PULL_VỪA"
    else:
        return "THEO_DÕI"

# ========================
# UI
# ========================
st.title("🐔 SCANNER GÀ CHIẾN V32.2")

col1, col2 = st.columns(2)
with col1:
    st.write("📅 Ngày:", datetime.now().strftime("%d/%m/%Y"))
with col2:
    st.write("⏰ Giờ VN:", datetime.now().strftime("%H:%M:%S"))

if st.button("🚀 SCAN NGAY"):

    data = []
    progress = st.progress(0)

    for i, symbol in enumerate(WATCHLIST):
        df = load_symbol(symbol)

        if df is None:
            continue

        df = calc(df)
        last = df.iloc[-1].astype(float)

        E,R,O,total = score(last)
        group = classify(E,R,O,total)

        data.append({
            "symbol": symbol,
            "price": round(last["Close"],2),
            "E": E,
            "R": R,
            "O": O,
            "score": total,
            "group": group
        })

        progress.progress((i+1)/len(WATCHLIST))
        time.sleep(0.2)

    df = pd.DataFrame(data)

    if df.empty:
        st.error("❌ Không lấy được dữ liệu (yfinance lag). Bấm lại lần nữa.")
        st.stop()

    # MARKET
    market = round(df["score"].mean()*1.6,1)

    st.subheader("📊 MARKET OVERVIEW")
    st.write("Market:", market)

    # SORT
    rank_map = {"CP_MẠNH":0,"PULL_ĐẸP":1,"PULL_VỪA":2,"THEO_DÕI":3}
    df["rank"] = df["group"].map(rank_map)

    df = df.sort_values(by=["rank","score","O"], ascending=[True,False,False])

    st.subheader("🔥 TOP CỔ PHIẾU")
    st.dataframe(df, use_container_width=True)
