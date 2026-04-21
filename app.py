# =========================================================
# SCANNER GÀ CHIẾN V18.2
# RSI SLOPE + PULL PHÂN LOẠI
# =========================================================

import time
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Scanner Gà Chiến V18.2", layout="wide")

st.title("🐔 Scanner Gà Chiến V18.2")
st.caption("RSI chuẩn hơn + Pull đẹp / vừa / xấu")

WATCHLIST = ["VCB","TCB","MBB","VPB","ACB","STB","SSI","VND","HCM",
             "GEX","FPT","HPG","MWG","DGC","REE","KBC","DIG","VHM","VIC","PNJ"]

DEFAULT_SUFFIX = ".VN"

# ================= INDICATOR =================
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

# ================= DATA =================
@st.cache_data(ttl=300)
def get_data(symbol):
    df=yf.download(symbol+DEFAULT_SUFFIX,period="6mo",progress=False)
    if df.empty: return None

    df["EMA9"]=ema(df["Close"],9)
    df["MA20"]=sma(df["Close"],20)

    df["RSI"]=rsi(df["Close"])
    df["RSI_slope"]=df["RSI"].diff()

    df["OBV"]=obv(df["Close"],df["Volume"])
    df["OBV_EMA9"]=ema(df["OBV"],9)

    df["VOL_MA20"]=sma(df["Volume"],20)

    return df

# ================= SCORE =================
def score(df):
    last=df.iloc[-1]
    prev=df.iloc[-2]

    # PRICE
    if last.Close>last.EMA9>last.MA20 and last.EMA9>prev.EMA9:
        E=2
    elif last.Close>last.EMA9:
        E=1
    else:
        E=0

    # RSI NEW
    if last.RSI>65 and last.RSI_slope>0:
        R=2
    elif last.RSI>55:
        R=1
    else:
        R=0

    # OBV
    if last.OBV>last.OBV_EMA9 and last.OBV>prev.OBV:
        O=2
    elif last.OBV>last.OBV_EMA9:
        O=1
    else:
        O=0

    return {
        "price":round(last.Close,0),
        "E":E,"R":R,"O":O,"total":E+R+O,
        "EMA9":last.EMA9,"MA20":last.MA20,
        "RSI":last.RSI,"RSI_slope":last.RSI_slope,
        "OBV":last.OBV,"OBV_EMA9":last.OBV_EMA9,
        "VOL":last.Volume,"VOL_MA20":last.VOL_MA20
    }

# ================= CLASSIFY =================
def classify(x):

    leader = x["total"]>=5 and x["O"]>=1
    if not leader:
        return "THEO DÕI"

    price=x["price"]
    ema9=x["EMA9"]

    dist = (price/ema9 -1)*100

    # 🟢 PULL ĐẸP
    if -1 <= dist <= 1 and x["RSI"]>60 and x["RSI_slope"]>0:
        return "🟢 PULL ĐẸP"

    # 🟡 PULL VỪA
    if -2.5 <= dist <= 2 and x["RSI"]>55:
        return "🟡 PULL VỪA"

    # 🔥 BREAK
    if price>ema9*1.02 and x["VOL"]>x["VOL_MA20"]:
        return "MUA BREAK"

    # 💪 STRONG
    if price>ema9*1.03:
        return "CP MẠNH"

    return "THEO DÕI"

# ================= RUN =================
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

# ================= UI =================
groups=["CP MẠNH","MUA BREAK","🟢 PULL ĐẸP","🟡 PULL VỪA","THEO DÕI"]

cols=st.columns(len(groups))

for i,g in enumerate(groups):
    with cols[i]:
        st.subheader(g)
        sub=df[df["group"]==g][["symbol","price","E","R","O","total"]]
        st.dataframe(sub,use_container_width=True)

st.markdown("---")
st.caption("Pull đẹp = điểm vào tiền chính")
