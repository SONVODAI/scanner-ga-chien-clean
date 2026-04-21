# =========================================================
# SCANNER GÀ CHIẾN V18.3 FINAL
# CLEAN + RSI SLOPE + PULL + TOP PICKS
# =========================================================

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# =========================================================
# PAGE
# =========================================================
st.set_page_config(page_title="Scanner Gà Chiến V18.3", layout="wide")

st.title("🐔 Scanner Gà Chiến V18.3")
st.caption("Full hệ: Market + Pull + Top vào tiền")

# =========================================================
# WATCHLIST
# =========================================================
WATCHLIST = [
    "VCB","TCB","MBB","VPB","ACB","STB",
    "SSI","VND","HCM",
    "GEX","FPT","HPG",
    "MWG","DGC","REE",
    "KBC","DIG","VHM","VIC",
    "PNJ","MSN","NVL","DXG","CII","LHG","FMC"
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

    # PRICE
    if last.Close>last.EMA9>last.MA20:
        E=2
    elif last.Close>last.EMA9:
        E=1
    else:
        E=0

    # RSI
    if last.RSI>65 and last.RSI_slope>0:
        R=2
    elif last.RSI>55:
        R=1
    else:
        R=0

    # OBV
    if last.OBV>last.OBV_EMA9:
        O=2
    elif last.OBV>last.OBV_EMA9*0.98:
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
# CLASSIFY
# =========================================================
def classify(total, pull_label, price, ema9, vol, vol_ma):
    
    if total>=5:
        if pull_label=="PULL ĐẸP":
            return "PULL ĐẸP"
        if pull_label=="PULL VỪA":
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

        pull_label,dist=classify_pull(
            last.Close,last.EMA9,
            last.RSI,last.RSI_slope,
            last.OBV,last.OBV_EMA9
        )

        group=classify(E+R+O,pull_label,last.Close,last.EMA9,last.Volume,last.VOL_MA20)

        data.append({
            "symbol":s,
            "price":round(last.Close,0),
            "E":E,"R":R,"O":O,
            "total":E+R+O,
            "group":group,
            "dist":round(dist,2)
        })

    return pd.DataFrame(data)

df=run()

# =========================================================
# MARKET
# =========================================================
def market_score(df):
    if len(df)==0: return 0

    strong=len(df[df.group=="CP MẠNH"])
    pull=len(df[df.group=="PULL ĐẸP"])
    breakc=len(df[df.group=="MUA BREAK"])

    score= strong*0.3 + pull*0.5 + breakc*0.4

    return round(min(score,10),1)

ms=market_score(df)

if ms>=8:
    status="🟢 THỊ TRƯỜNG KHỎE"
elif ms>=6:
    status="🟡 TRUNG TÍNH"
else:
    status="🔴 YẾU"

st.metric("Market Score",ms)
st.subheader(status)

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
        nav="30%"
    elif t.group=="PULL VỪA":
        nav="15%"
    else:
        nav="20%"

    st.write(f"{t.symbol} | {t.group} | Giá: {t.price} | NAV: {nav}")

# =========================================================
# DISPLAY
# =========================================================
groups=["CP MẠNH","MUA BREAK","PULL ĐẸP","PULL VỪA","MUA EARLY","THEO DÕI"]

cols=st.columns(len(groups))

for i,g in enumerate(groups):
    with cols[i]:
        st.subheader(g)
        sub=df[df.group==g][["symbol","price","total"]]
        st.dataframe(sub)
