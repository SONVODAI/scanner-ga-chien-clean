import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

st.set_page_config(layout="wide")

# ========================
# TIME VN
# ========================
vn_time = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh"))

st.title("📊 SCANNER GÀ CHIẾN V25")
st.markdown(f"📅 Ngày: {vn_time.strftime('%d/%m/%Y')}")
st.markdown(f"⏰ Giờ VN: {vn_time.strftime('%H:%M:%S')}")

# ========================
# WATCHLIST THẬT (fallback)
# ========================
WATCHLIST = [
    "VIC","VHM","VRE","VNM","MSN","MWG","FPT",
    "VCB","BID","CTG","TCB","MBB","VPB","STB",
    "SSI","VND","HCM","SHS",
    "HPG","HSG","NKG",
    "DGC","DCM","DPM","CSV","BFC",
    "GAS","PVD","PVS","PLX",
    "VHC","ANV","FMC",
    "CTR","VGI","VTP",
    "GEX","GEE","REE"
]

# ========================
# LOAD DATA
# ========================
uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

def load_data():
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
    else:
        # fallback data (nhưng không random lung tung)
        df = pd.DataFrame({
            "symbol": WATCHLIST,
            "price": np.random.randint(10000, 80000, len(WATCHLIST)),
            "ema9": np.random.randint(10000, 80000, len(WATCHLIST)),
            "ma20": np.random.randint(10000, 80000, len(WATCHLIST)),
            "rsi14": np.random.randint(40, 80, len(WATCHLIST)),
            "rsi_ema9": np.random.randint(40, 70, len(WATCHLIST)),
            "obv": np.random.randint(1000000, 50000000, len(WATCHLIST)),
            "obv_ema9": np.random.randint(1000000, 50000000, len(WATCHLIST)),
            "volume": np.random.randint(100000, 5000000, len(WATCHLIST))
        })
    return df

# ========================
# MARKET SCORE (GIẢM ĐỘ ẢO)
# ========================
def market_score(df):
    score = 0

    rsi_mean = df["rsi14"].mean()

    if rsi_mean > 65:
        score += 3
    elif rsi_mean > 55:
        score += 2
    elif rsi_mean > 50:
        score += 1

    uptrend = (df["price"] > df["ema9"]).sum()

    if uptrend > len(df)*0.7:
        score += 4
    elif uptrend > len(df)*0.5:
        score += 3
    elif uptrend > len(df)*0.3:
        score += 2

    obv_ok = (df["obv"] > df["obv_ema9"]).sum()

    if obv_ok > len(df)*0.6:
        score += 3
    elif obv_ok > len(df)*0.4:
        score += 2

    return round(score,1)

# ========================
# CLASSIFY CHUẨN
# ========================
def classify(row):
    dist = (row["price"] - row["ema9"]) / row["ema9"] * 100
    rsi = row["rsi14"]
    obv_ok = row["obv"] > row["obv_ema9"]

    # CP MẠNH thật
    if row["price"] > row["ema9"] > row["ma20"] and rsi >= 65 and obv_ok and dist > 3:
        return "CP MẠNH"

    # BREAK
    if rsi > 60 and dist > 2:
        return "MUA BREAK"

    # PULL đẹp
    if abs(dist) < 1 and rsi > 55:
        return "PULL ĐẸP"

    # PULL vừa
    if abs(dist) < 3:
        return "PULL VỪA"

    # EARLY
    if 45 <= rsi <= 55:
        return "MUA EARLY"

    return "THEO DÕI"

# ========================
# SCORE E R O
# ========================
def calc_scores(df):
    df["E"] = np.where(df["rsi14"] > 55, 2, 1)
    df["R"] = np.where(df["rsi14"] > 70, 2, 1)
    df["O"] = np.where(df["obv"] > df["obv_ema9"], 2, 1)

    df["total_score"] = df["E"] + df["R"] + df["O"]
    return df

# ========================
# RUN
# ========================
if st.button("🔍 SCAN"):
    df = load_data()

    df["group"] = df.apply(classify, axis=1)
    df = calc_scores(df)

    df["dist"] = (df["price"] - df["ema9"]) / df["ema9"] * 100

    # ========================
    # MARKET
    # ========================
    m_score = market_score(df)

    st.markdown("## 📊 MARKET OVERVIEW")
    st.write(f"Market Score: **{m_score}/13**")

    # ========================
    # TOP 20 ERO
    # ========================
    st.markdown("## 🧠 TOP 20 E-R-O")

    top20 = df.sort_values(by=["total_score","E","O"], ascending=False).head(20)
    st.dataframe(top20[["symbol","price","E","R","O","total_score"]])

    # ========================
    # FULL TABLE (SORT CHUẨN)
    # ========================
    st.markdown("## 📋 BẢNG TỔNG CHI TIẾT")

    df_sorted = df.sort_values(
        by=["total_score","E","O","price"],
        ascending=False
    )

    st.dataframe(df_sorted)

    # ========================
    # GROUP
    # ========================
    st.markdown("## 📊 PHÂN NHÓM")

    cols = ["CP MẠNH","MUA BREAK","PULL ĐẸP","PULL VỪA","MUA EARLY","THEO DÕI"]

    for c in cols:
        st.markdown(f"### {c}")
        st.dataframe(df[df["group"]==c][["symbol","price"]])
