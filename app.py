# =========================================================
# SCANNER GÀ CHIẾN V18.4 FINAL
# FIX MARKET NOISE + ADD OBV DISPLAY
# =========================================================

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến V18.4", layout="wide")

st.title("🐔 Scanner Gà Chiến V18.4")
st.caption("Market REAL + LIVE | OBV hiển thị | Pull chuẩn")

# =========================================================
# WATCHLIST (rút gọn demo, anh có thể giữ list cũ)
# =========================================================
WATCHLIST = [
    "VCB","TCB","MBB","VPB","ACB","STB",
    "SSI","VND","HCM","GEX","FPT","HPG",
    "MWG","DGC","REE","KBC","DIG","VHM",
    "VIC","PNJ","MSN","NVL","DXG","CII","LHG","FMC"
]

# =========================================================
# INDICATOR
# =========================================================
def ema(s,n): return s.ewm(span=n).mean()
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
    df=yf.download(symbol+".VN",period="6mo",progress=False)
    if df.empty: return None

    df["EMA9"]=ema(df["Close"],9)
    df["MA20"]=sma(df["Close"],20)

    df["RSI"]=rsi(df["Close"])
    df["RSI_slope"]=df["RSI"].diff()

    df["OBV"]=obv(df["Close"],df["Volume"])
    df["OBV_EMA9"]=ema(df["OBV"],9)

    df["VOL_MA20"]=sma(df["Volume"],20)

    return df

# =========================================================
# SCORE
# =========================================================
def score(df):
    last=df.iloc[-1]
    prev=df.iloc[-2]

    close=float(last["Close"])
    ema9=float(last["EMA9"])
    ma20=float(last["MA20"])
    ema9_prev=float(prev["EMA9"])

    rsi_=float(last["RSI"])
    slope=float(last["RSI_slope"])

    obv_=float(last["OBV"])
    obv_ema=float(last["OBV_EMA9"])
    obv_prev=float(prev["OBV"])

    # PRICE
    if close>ema9>ma20 and ema9>ema9_prev:
        E=2
    elif close>ema9:
        E=1
    else:
        E=0

    # RSI
    if rsi_>65 and slope>0:
        R=2
    elif rsi_>55:
        R=1
    else:
        R=0

    # OBV
    if obv_>obv_ema and obv_>obv_prev:
        O=2
    elif obv_>obv_ema:
        O=1
    else:
        O=0

    return E,R,O

# =========================================================
# PULL
# =========================================================
def classify_pull(price, ema9, rsi, slope, obv, obv_ema):
    dist=(price/ema9-1)*100

    if -1<=dist<=1 and rsi>60 and slope>0 and obv>=obv_ema:
        return "PULL ĐẸP",dist

    if -2.5<=dist<=2 and rsi>55 and obv>=obv_ema:
        return "PULL VỪA",dist

    return "PULL XẤU",dist

# =========================================================
# GROUP
# =========================================================
def classify(total, pull, price, ema9, vol, vol_ma):
    if total>=5:
        if pull=="PULL ĐẸP":
            return "PULL ĐẸP"
        if pull=="PULL VỪA":
            return "PULL VỪA"
        if price>ema9*1.02 and vol>vol_ma:
            return "MUA BREAK"
        return "CP MẠNH"

    if total>=3:
        return "MUA EARLY"

    return "THEO DÕI"

# =========================================================
# RUN
# =========================================================
def run():
    data=[]
    for s in WATCHLIST:
        df=get_data(s)
        if df is None or len(df)<30: continue

        last=df.iloc[-1]

        E,R,O=score(df)

        price=float(last["Close"])
        ema9=float(last["EMA9"])
        rsi_=float(last["RSI"])
        slope=float(last["RSI_slope"])
        obv_=float(last["OBV"])
        obv_ema=float(last["OBV_EMA9"])

        pull,dist=classify_pull(price,ema9,rsi_,slope,obv_,obv_ema)

        group=classify(E+R+O,pull,price,ema9,last["Volume"],last["VOL_MA20"])

        # OBV status
        if obv_>=obv_ema:
            obv_status="🟢"
        else:
            obv_status="🔴"

        data.append({
            "symbol":s,
            "price":round(price,0),
            "E":E,"R":R,"O":O,
            "total":E+R+O,
            "group":group,
            "dist":round(dist,2),
            "OBV":round(obv_,0),
            "OBV_EMA9":round(obv_ema,0),
            "OBV_status":obv_status
        })

    return pd.DataFrame(data)

df=run()

# =========================================================
# MARKET (REAL vs LIVE)
# =========================================================
def market_score(df):
    if len(df)==0: return 0

    strong=len(df[df.group=="CP MẠNH"])
    pull=len(df[df.group=="PULL ĐẸP"])
    breakc=len(df[df.group=="MUA BREAK"])

    score= strong*0.3 + pull*0.5 + breakc*0.4
    return round(min(score,10),1)

ms=market_score(df)

# REAL (cố định hơn)
ms_real=round(ms*0.8+2,1) if ms<8 else ms

# LIVE (nhiễu)
ms_live=ms

# hiển thị
st.markdown("## 📊 MARKET OVERVIEW")

col1,col2=st.columns(2)

with col1:
    st.metric("Market REAL", f"{ms_real}/13")

with col2:
    st.metric("Market LIVE", f"{ms_live}/13")

if ms_real>=8:
    st.success("🟢 Market khỏe → có thể vào tiền")
elif ms_real>=6:
    st.warning("🟡 Trung tính → chỉ test nhỏ")
else:
    st.error("🔴 Market yếu → không nên vào tiền")

# =========================================================
# TOP PICKS
# =========================================================
st.markdown("## 🎯 TOP VÀO TIỀN")

top=[]

top+=list(df[df.group=="PULL ĐẸP"].head(2).itertuples())
top+=list(df[df.group=="PULL VỪA"].head(2).itertuples())
top+=list(df[df.group=="MUA BREAK"].head(1).itertuples())

top=top[:4]

for t in top:
    if t.group=="PULL ĐẸP":
        nav="25%"
    elif t.group=="PULL VỪA":
        nav="10-15%"
    else:
        nav="10%"

    st.write(f"{t.symbol} | {t.group} | NAV: {nav}")

# =========================================================
# DISPLAY
# =========================================================
groups=["CP MẠNH","MUA BREAK","PULL ĐẸP","PULL VỪA","MUA EARLY","THEO DÕI"]

cols=st.columns(len(groups))

for i,g in enumerate(groups):
    with cols[i]:
        st.subheader(g)
        sub=df[df.group==g][["symbol","price","total","dist","OBV_status"]]
        st.dataframe(sub)
