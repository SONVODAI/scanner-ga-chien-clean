# ============================================
# SCANNER GÀ CHIẾN V17.1 - LEADER FIRST
# ============================================

import time
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến V17.1", layout="wide")

# ================= WATCHLIST =================
WATCHLIST = ["VCB","TCB","MBB","VPB","ACB","STB","VIB","SSI","VND","HCM",
             "GEX","GEE","VSC","VIX","FPT","CTR","VTP","HPG","HSG","NKG",
             "MWG","FRT","DGW","MSN","VNM","DGC","DCM","DPM","REE","PC1",
             "KBC","DIG","DXG","VHM","VIC","NVL","PNJ","TLG","IMP","HVN","VJC"]

DEFAULT_SUFFIX = ".VN"

# ================= INDICATOR =================
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def sma(s, n): return s.rolling(n).mean()

def rsi(close, n=14):
    d = close.diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    rs = gain.ewm(alpha=1/n).mean() / loss.ewm(alpha=1/n).mean()
    return 100 - (100/(1+rs))

def obv(close, vol):
    return (np.sign(close.diff()).fillna(0)*vol).cumsum()

# ================= DATA =================
@st.cache_data(ttl=300)
def get_data(symbol):
    df = yf.download(symbol+DEFAULT_SUFFIX, period="6mo", progress=False)
    if df.empty: return None

    df["EMA9"] = ema(df["Close"],9)
    df["MA20"] = sma(df["Close"],20)

    df["RSI"] = rsi(df["Close"])
    df["RSI_EMA9"] = ema(df["RSI"],9)

    df["OBV"] = obv(df["Close"],df["Volume"])
    df["OBV_EMA9"] = ema(df["OBV"],9)

    df["VOL_MA20"] = sma(df["Volume"],20)

    return df

# ================= SCORE =================
def score(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # PRICE
    if last.Close > last.EMA9 > last.MA20 and last.EMA9 > prev.EMA9:
        E = 2
    elif last.Close > last.EMA9:
        E = 1
    else:
        E = 0

    # RSI
    if last.RSI > 60 and last.RSI > last.RSI_EMA9:
        R = 2
    elif last.RSI > 55:
        R = 1
    else:
        R = 0

    # OBV
    if last.OBV > last.OBV_EMA9 and last.OBV > prev.OBV:
        O = 2
    elif last.OBV > last.OBV_EMA9:
        O = 1
    else:
        O = 0

    total = E + R + O

    return {
        "price": round(last.Close,0),
        "E":E,"R":R,"O":O,"total":total,
        "EMA9":last.EMA9,"MA20":last.MA20,
        "RSI":last.RSI,"RSI_EMA9":last.RSI_EMA9,
        "OBV":last.OBV,"OBV_EMA9":last.OBV_EMA9,
        "VOL":last.Volume,"VOL_MA20":last.VOL_MA20
    }

# ================= CLASSIFY =================
def classify(x):

    # ====== LEADER FIRST ======
    if x["total"] >= 5 and x["O"] >= 1:
        leader = True
    else:
        leader = False

    if not leader:
        if x["total"] <= 1:
            return "THEO DÕI"
        elif x["total"] == 2:
            return "TÍCH LŨY"
        else:
            return "MUA EARLY"

    # ====== LEADER ZONE ======

    price = x["price"]
    ema9 = x["EMA9"]
    ma20 = x["MA20"]

    # 🟢 STRONG
    if price > ema9*1.03:
        return "CP MẠNH"

    # 🟡 PULL (CHUẨN)
    if ema9*0.97 <= price <= ema9*1.01 and x["O"] >= 1:
        return "MUA PULL"

    # 🔥 BREAK
    if price > ema9*1.02 and x["VOL"] > x["VOL_MA20"]:
        return "MUA BREAK"

    # 🔵 EARLY
    if x["RSI"] > x["RSI_EMA9"] and x["OBV"] > x["OBV_EMA9"]:
        return "MUA EARLY"

    return "TÍCH LŨY"

# ================= SCAN =================
def run():
    data = []
    for s in WATCHLIST:
        df = get_data(s)
        if df is None or len(df)<30: continue

        sc = score(df)
        sc["symbol"] = s
        sc["group"] = classify(sc)

        data.append(sc)

    df = pd.DataFrame(data)
    df = df.sort_values("total",ascending=False)
    return df

# ================= UI =================
st.title("🐔 Scanner Gà Chiến V17.1")

if st.button("SCAN"):
    st.cache_data.clear()

df = run()

groups = ["CP MẠNH","MUA BREAK","MUA PULL","MUA EARLY","TÍCH LŨY","THEO DÕI"]

cols = st.columns(6)

for i,g in enumerate(groups):
    with cols[i]:
        st.subheader(g)
        sub = df[df["group"]==g][["symbol","price","E","R","O","total"]]
        st.dataframe(sub, use_container_width=True)

st.markdown("---")
st.caption("Logic: Leader trước → rồi mới Break / Pull / Early")
