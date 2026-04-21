import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime


st.set_page_config(layout="wide")

# ================= WATCHLIST =================
WATCHLIST = [
"VCB","BID","CTG","TCB","MBB","VPB","STB","HDB","ACB","SHB","VPB", "VIB", "MSB","TPB","ABB","LPB","EIB","ACB","EVF","KLB","OCB"
"SSI","VIX","SHS","HCM","VCI","VND","CTS","FTS","MBS","BSI","BVS","ORS","AGR","TCX","VPX","VCK","VDS"
"VHM","VIC","DXG","DIG","NVL","VPL","VRE","NLG","KDH","CII","HHS","TCH","CEO","DIG","PDR","HDG","HDC","NHA","NTL","DPG""DXS","HUT"
"MWG","FRT","PNJ","DGW","PET","MSN","MCH","MML","DBC","HAG","MML","SAB","PAN","FMC","BAF","HPA","TLG","SBT"
"REE","GEX","PC1","NT2","GEG","POW"
"DGC","DCM","DPM","CSV","BFC","LAS","MSR","BMP","NTP","DDV",
"BSR","PVS","GAS","OIL","GAS","PLX","PVD","PVB","PVC","PVT",
"GMD","HAH","VSC","HVN","ACV","VJC","VOS","VTO",
"FPT","CTR","VTP","VGI","FOX","CMG","MFS","ELC"
"VHC","ANV","MSH","TNG","TCM","VGT","VCS","PTB",
"HPG","HSG","NKG","CTD","HHV","FCN","KSB","LCG","C4G","CTI","DHA","PLC","HT1"
"VGC","IDC","SZC","LHG","KBC","DTD","IJC","GVR","SIP","PHR","DPR","DRI","TRC"
"BVH","MIG","BMI"
"DCL","TNH","DVN","IMP","DBD"
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
            type="stock",
            beautify=True
        )

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "close": "close",
            "volume": "volume"
        })

        return df

    except Exception:
        return pd.DataFrame()
        # ================= INDICATORS =================

@st.cache_data(ttl=600)
def fetch_data(symbol):
    try:
        df = yf.download(symbol + ".VN", period="6mo", progress=False, auto_adjust=True)

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "Close": "close",
            "Volume": "volume"
        })

        return df

    except Exception:
        return pd.DataFrame()


# ============== INDICATORS ==============
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

    except Exception:
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
