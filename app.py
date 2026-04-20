import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from vnstock import *

st.set_page_config(layout="wide")

# ================= WATCHLIST =================
WATCHLIST = [
"VCB","BID","CTG","TCB","MBB","VPB","STB","HDB","ACB","SHB","TPB","LPB","EIB","ABB","MSB","KLB","EVF","SSB","VIB","BVB","OCB",
"SSI","VIX","SHS","MBS","TCX","VCK","VPX","HCM","VCI","VND","CTS","FTS","BSI","BVS","ORS","VDS","AGR",
"VHM","VIC","NLG","KDH","CEO","CII","DXG","TCH","HHS","DPG","HDC","NVL","NTL","NHA","HUT","DIG","PDR","DXS","VRE","VPL",
"VGC","IDC","KBC","SZC","BCM","DTD","LHG","IJC","GVR","PHR","DPR","DRI","SIP","TRC","DRC","CSM",
"MWG","DGW","FRT","PET","PNJ","MSN","MCH","PAN","FMC","DBC","HAG","VNM","MML","SAB","SBT","TLG","HPA","BAF",
"REE","GEE","GEX","PC1","NT2","GEL","HDG","GEG","POW",
"DPM","DCM","LAS","DDV","DGC","CSV","BFC","MSR","BMP","NTP",
"BSR","PVS","PVD","PVB","PVC","PVT","OIL","PLX","GAS",
"HAH","GMD","VSC","VOS","VTO","HVN","VJC","ACV",
"VTP","CTR","VGI","FPT","FOX","CMG","MFS","ELC",
"MSH","TNG","TCM","GIL","VGT","HTG","VHC","ANV","VCS","PTB",
"CTD","HHV","FCN","LCG","CTI","KSB","C4G","VCG","DHA","PLC","HT1",
"HPG","HSG","NKG","VGS","TLH","TVN",
"DVN","DCL","DHG","IMP","DBD","DHT",
"BVH","MIG","BMI"
]

# ================= INDICATORS =================
def calc_indicators(df):
    df['EMA9'] = df['close'].ewm(span=9).mean()
    df['EMA20'] = df['close'].ewm(span=20).mean()

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    df['MACD'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    df['MACD_SIGNAL'] = df['MACD'].ewm(span=9).mean()

    df['OBV'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    df['OBV_EMA'] = df['OBV'].ewm(span=9).mean()

    return df

# ================= CLASSIFY =================
def classify(row):
    rsi = row["RSI"]
    ema9 = row["EMA9"]
    price = row["close"]
    obv = row["OBV"]
    obv_ema = row["OBV_EMA"]

    dist = (price - ema9)/ema9*100

    # 🚀 GÀ ĐANG CHẠY (ưu tiên cao nhất)
    if rsi >= 70 and price > ema9 and obv > obv_ema:
        return "STRONG_TREND"

    # 🟢 Pull đẹp
    elif 60 <= rsi < 70 and abs(dist) < 4:
        return "BUY_PULL"

    # 🌱 Early
    elif 45 < rsi < 60:
        return "BUY_EARLY"

    # ⏳ Quá nóng
    elif rsi >= 75:
        return "WAIT_PULL"

    # 🐢 Tích lũy
    elif 40 <= rsi <= 50:
        return "ACCUMULATION"

    else:
        return "AVOID"
# ================= MAIN =================
results = []
       
for symbol in WATCHLIST:
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        df = stock_historical_data(symbol, "2023-01-01", today, "1D")
        df = calc_indicators(df)

        if df is None or len(df) == 0:
            raise Exception("No data")

        row = df.iloc[-1]

        results.append({
            "symbol": symbol,
            "price": row['close'],
            "RSI": row['RSI'],
            "action": classify(row)
        })

    except Exception as e:
        st.write(f"Lỗi {symbol}: {e}")
               

df = pd.DataFrame(results)

st.title("🔥 SCANNER GÀ CHIẾN V15.3 PRO")

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
    st.subheader("🔥 STRONG TREND")
    st.dataframe(df[df.action=="STRONG_TREND"])
