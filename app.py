# =========================================================
# SCANNER GÀ CHIẾN V18.1 FULL
# (GIỮ NGUYÊN V18 + THÊM MARKET SCORE)
# =========================================================

import time
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# =========================================================
# PAGE
# =========================================================
st.set_page_config(
    page_title="Scanner Gà Chiến V18.1",
    page_icon="🐔",
    layout="wide",
)

st.title("🐔 Scanner Gà Chiến V18.1")
st.caption("V18 + Market Score | Leader first")


# =========================================================
# WATCHLIST (GIỮ NGUYÊN)
# =========================================================
WATCHLIST = sorted(list(set([
    "VCB","TCB","MBB","VPB","ACB","STB","VIB","SSI","VND","HCM",
    "GEX","GEE","VSC","VIX","FPT","CTR","VTP","HPG","HSG","NKG",
    "MWG","FRT","DGW","MSN","VNM","DGC","DCM","DPM","REE","PC1",
    "KBC","DIG","DXG","VHM","VIC","NVL","PNJ","TLG","IMP","HVN","VJC"
])))

DEFAULT_SUFFIX = ".VN"


# =========================================================
# INDICATOR
# =========================================================
def ema(s,n): return s.ewm(span=n,adjust=False).mean()
def sma(s,n): return s.rolling(n).mean()

def rsi(close,n=14):
    d=close.diff()
    gain=d.clip(lower=0)
    loss=-d.clip(upper=0)
    rs=gain.ewm(alpha=1/n).mean()/loss.ewm(alpha=1/n).mean()
    return 100-(100/(1+rs))

def obv(close,vol):
    return (np.sign(close.diff()).fillna(0)*vol).cumsum()


# =========================================================
# DATA
# =========================================================
@st.cache_data(ttl=300)
def get_data(symbol):
    df=yf.download(symbol+DEFAULT_SUFFIX,period="6mo",progress=False)
    if df.empty: return None

    df["EMA9"]=ema(df["Close"],9)
    df["MA20"]=sma(df["Close"],20)

    df["RSI"]=rsi(df["Close"])
    df["RSI_EMA9"]=ema(df["RSI"],9)

    df["OBV"]=obv(df["Close"],df["Volume"])
    df["OBV_EMA9"]=ema(df["OBV"],9)

    df["VOL_MA20"]=sma(df["Volume"],20)

    return df


# =========================================================
# SCORE (GIỮ NGUYÊN)
# =========================================================
def score(df):
    last=df.iloc[-1]
    prev=df.iloc[-2]

    if last.Close>last.EMA9>last.MA20 and last.EMA9>prev.EMA9:
        E=2
    elif last.Close>last.EMA9:
        E=1
    else:
        E=0

    if last.RSI>60 and last.RSI>last.RSI_EMA9:
        R=2
    elif last.RSI>55:
        R=1
    else:
        R=0

    if last.OBV>last.OBV_EMA9 and last.OBV>prev.OBV:
        O=2
    elif last.OBV>last.OBV_EMA9:
        O=1
    else:
        O=0

    total=E+R+O

    return {
        "price":round(last.Close,0),
        "E":E,"R":R,"O":O,"total":total,
        "EMA9":last.EMA9,"MA20":last.MA20,
        "RSI":last.RSI,"RSI_EMA9":last.RSI_EMA9,
        "OBV":last.OBV,"OBV_EMA9":last.OBV_EMA9,
        "VOL":last.Volume,"VOL_MA20":last.VOL_MA20
    }


# =========================================================
# CLASSIFY (GIỮ NGUYÊN V18)
# =========================================================
def classify(x):

    leader = x["total"]>=5 and x["O"]>=1

    if not leader:
        if x["total"]<=1:
            return "THEO DÕI"
        elif x["total"]==2:
            return "TÍCH LŨY"
        else:
            return "MUA EARLY"

    price=x["price"]
    ema9=x["EMA9"]
    ma20=x["MA20"]

    if ema9*0.97 <= price <= ema9*1.01 and price>=ma20:
        return "MUA PULL"

    if price>ema9*1.02 and x["VOL"]>x["VOL_MA20"]:
        return "MUA BREAK"

    if price>ema9*1.03:
        return "CP MẠNH"

    if x["RSI"]>x["RSI_EMA9"] and x["OBV"]>x["OBV_EMA9"]:
        return "MUA EARLY"

    return "TÍCH LŨY"


# =========================================================
# SCAN
# =========================================================
@st.cache_data(ttl=300)
def run():
    data=[]
    for s in WATCHLIST:
        df=get_data(s)
        if df is None or len(df)<30: continue

        sc=score(df)
        sc["symbol"]=s
        sc["group"]=classify(sc)

        data.append(sc)

    return pd.DataFrame(data)


df=run()

# =========================================================
# 🔥 MARKET SCORE (THÊM MỚI)
# =========================================================
def calc_market_score(df):
    total=len(df)
    if total==0: return 0

    E_ratio=len(df[df["E"]>=1])/total
    R_ratio=len(df[df["R"]>=1])/total
    O_ratio=len(df[df["O"]>=1])/total

    strong=len(df[df["group"]=="CP MẠNH"])
    breakout=len(df[df["group"]=="MUA BREAK"])

    strong_score=min(strong/10,1)*3
    breakout_score=min(breakout/8,1)*2

    score=(
        E_ratio*3+
        R_ratio*3+
        O_ratio*3+
        strong_score+
        breakout_score
    )

    return round(score,1)


market_score=calc_market_score(df)

if market_score>=8:
    market_status="🟢 THỊ TRƯỜNG KHỎE"
elif market_score>=6:
    market_status="🟡 TRUNG TÍNH"
else:
    market_status="🔴 THỊ TRƯỜNG YẾU"

# =========================================================
# HIỂN THỊ MARKET
# =========================================================
st.markdown("## 📊 MARKET OVERVIEW")

col1,col2=st.columns([1,2])

with col1:
    st.metric("Market Score",f"{market_score}/13")

with col2:
    st.subheader(market_status)

if market_score<6:
    st.warning("⚠️ Không nên vào tiền")
elif market_score<8:
    st.info("⚠️ Chỉ nên test nhỏ")
else:
    st.success("✅ Có thể vào tiền")


# =========================================================
# DISPLAY (GIỮ NGUYÊN)
# =========================================================
groups=["CP MẠNH","MUA BREAK","MUA PULL","MUA EARLY","TÍCH LŨY","THEO DÕI"]

cols=st.columns(6)

for i,g in enumerate(groups):
    with cols[i]:
        st.subheader(g)
        sub=df[df["group"]==g][["symbol","price","E","R","O","total"]]
        st.dataframe(sub,use_container_width=True)

st.markdown("---")
st.caption("Market ≥8 đánh mạnh | <8 giảm NAV")
