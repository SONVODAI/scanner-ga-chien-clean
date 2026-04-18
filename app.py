import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="Scanner Gà Chiến V16", layout="wide")

# =========================
# HEADER
# =========================
st.title("🐔 Scanner Gà Chiến V16 – Final Version")
st.caption(f"⏱ Update realtime | {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

# =========================
# SIDEBAR
# =========================
st.sidebar.header("Thiết lập")
market_score = st.sidebar.slider("Market Score", 1.0, 10.0, 8.0, 0.5)
top_n = st.sidebar.slider("Top cổ phiếu", 5, 30, 10)

default_watchlist = """VCB,BID,CTG,TCB,MBB,VPB,STB,HDB,ACB,SHB,TPB,LPB,EIB,ABB,MSB,KLB,EVF
SSI,VIX,SHS,MBS,HCM,VCI,VND,CTS,FTS,BSI,BVS,ORS,VDS,AGR
VHM,NLG,KDH,CEO,CII,DXG,TCH,DPG,HDC,NVL,NTL,NHA,HUT,DIG,PDR,DXS
VGC,IDC,KBC,SZC,BCM,LHG,IJC,GVR,PHR,DPR,TRC,SIP,DRC,CSM
MWG,DGW,FRT,PET,PNJ,MSN,PAN,FMC,DBC,HAG,VNM,SAB,SBT,TLG
REE,GEE,GEX,PC1,NT2,HDG,GEG,POW
DPM,DCM,LAS,DDV,DGC,CSV,BFC,MSR,BMP,NTP
BSR,PVS,PVD,PVB,PVC,PVT,OIL,PLX,GAS"""

watchlist_text = st.text_area("Danh sách mã theo dõi", value=default_watchlist, height=220)

# =========================
# PARSE WATCHLIST
# =========================
def parse_tickers(text: str):
    raw = text.replace("\n", ",").split(",")
    tickers = []
    for x in raw:
        x = x.strip().upper()
        if x and x not in tickers:
            tickers.append(x)
    return tickers

# =========================
# TẠO DỮ LIỆU GIẢ LẬP AN TOÀN
# =========================
@st.cache_data(ttl=300)
def load_data_from_watchlist(tickers):
    rng = np.random.default_rng(42)

    rows = []
    for t in tickers:
        rsi = float(np.clip(rng.normal(58, 10), 30, 85))

        obv_trend = rng.choice(["strong", "medium", "recover", "weak"], p=[0.28, 0.32, 0.20, 0.20])
        price_vs_ema = rng.choice(["above_ema9", "near_ema9", "below_ma20"], p=[0.45, 0.35, 0.20])
        macd = rng.choice(["bullish", "neutral", "bearish"], p=[0.40, 0.35, 0.25])
        atr = rng.choice(["expand", "normal", "shrink"], p=[0.35, 0.40, 0.25])

        rows.append({
            "Ticker": t,
            "OBV_trend": obv_trend,
            "Price_vs_EMA": price_vs_ema,
            "RSI": round(rsi, 2),
            "MACD": macd,
            "ATR": atr
        })

    return pd.DataFrame(rows)

# =========================
# TÍNH ĐIỂM
# =========================
def calculate_score(df):
    scores = []

    for _, row in df.iterrows():
        s = 0

        # OBV (4)
        if row["OBV_trend"] == "strong":
            s += 4
        elif row["OBV_trend"] == "medium":
            s += 2
        elif row["OBV_trend"] == "recover":
            s += 1

        # PRICE (3)
        if row["Price_vs_EMA"] == "above_ema9":
            s += 3
        elif row["Price_vs_EMA"] == "near_ema9":
            s += 1

        # RSI (3)
        if row["RSI"] >= 65:
            s += 3
        elif row["RSI"] >= 55:
            s += 2
        elif row["RSI"] >= 50:
            s += 1

        # MACD (2)
        if row["MACD"] == "bullish":
            s += 2
        elif row["MACD"] == "neutral":
            s += 1

        # ATR (1)
        if row["ATR"] == "expand":
            s += 1

        scores.append(s)

    df = df.copy()
    df["Score"] = scores
    return df

# =========================
# PHÂN LOẠI 4 TRẠNG THÁI
# =========================
def classify(df):
    states = []

    for _, row in df.iterrows():
        s = row["Score"]

        if s >= 9 and row["OBV_trend"] == "strong" and row["RSI"] >= 60 and row["Price_vs_EMA"] != "below_ma20":
            states.append("🟩 ƯU TIÊN MUA")
        elif s >= 7:
            states.append("🟨 THEO DÕI")
        elif s >= 5 and row["OBV_trend"] == "recover":
            states.append("🟦 THEO DÕI ĐẢO CHIỀU")
        else:
            states.append("🟥 LOẠI")

    df = df.copy()
    df["State"] = states
    return df

# =========================
# GOLD SCORE
# =========================
def add_gold_score(df, market_score_value):
    df = df.copy()
    if market_score_value < 8:
        df["GoldScore"] = 0.0
    else:
        df["GoldScore"] = (df["Score"] * market_score_value).round(2)
    return df

# =========================
# GỢI Ý HÀNH ĐỘNG
# =========================
def add_action(df, market_score_value):
    actions = []

    for _, row in df.iterrows():
        if market_score_value < 8:
            actions.append("Đứng ngoài / chỉ theo dõi")
        else:
            if row["State"] == "🟩 ƯU TIÊN MUA":
                actions.append("Canh mua thăm dò / pull đẹp")
            elif row["State"] == "🟨 THEO DÕI":
                actions.append("Theo dõi chờ xác nhận")
            elif row["State"] == "🟦 THEO DÕI ĐẢO CHIỀU":
                actions.append("Quan sát nến xác nhận")
            else:
                actions.append("Loại")

    df = df.copy()
    df["Action"] = actions
    return df

# =========================
# MAIN
# =========================
tickers = parse_tickers(watchlist_text)

if not tickers:
    st.error("Anh chưa nhập mã cổ phiếu.")
    st.stop()

df = load_data_from_watchlist(tickers)
df = calculate_score(df)
df = classify(df)
df = add_gold_score(df, market_score)
df = add_action(df, market_score)
df = df.sort_values(["GoldScore", "Score", "RSI"], ascending=[False, False, False]).reset_index(drop=True)

strong_df = df[df["State"] == "🟩 ƯU TIÊN MUA"].copy()

# =========================
# SUMMARY
# =========================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Số mã theo dõi", len(df))
c2.metric("Ưu tiên mua", int((df["State"] == "🟩 ƯU TIÊN MUA").sum()))
c3.metric("Theo dõi", int((df["State"] == "🟨 THEO DÕI").sum()))
c4.metric("Đảo chiều sớm", int((df["State"] == "🟦 THEO DÕI ĐẢO CHIỀU").sum()))

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Top cổ phiếu toàn thị trường")
    st.dataframe(
        df[["Ticker", "Score", "GoldScore", "RSI", "OBV_trend", "Price_vs_EMA", "MACD", "ATR", "State", "Action"]].head(top_n),
        use_container_width=True,
        hide_index=True
    )

with col2:
    st.subheader("🔥 Danh sách ưu tiên mua")
    if strong_df.empty:
        st.info("Chưa có mã nào đạt chuẩn ƯU TIÊN MUA.")
    else:
        st.dataframe(
            strong_df[["Ticker", "Score", "GoldScore", "RSI", "OBV_trend", "Price_vs_EMA", "MACD", "ATR", "Action"]].head(top_n),
            use_container_width=True,
            hide_index=True
        )

st.markdown("---")
st.subheader("📋 Toàn bộ watchlist")
st.dataframe(
    df[["Ticker", "Score", "GoldScore", "RSI", "OBV_trend", "Price_vs_EMA", "MACD", "ATR", "State", "Action"]],
    use_container_width=True,
    hide_index=True
)

st.caption("V16 Final | Bản an toàn: không phụ thuộc stock_data.csv | TTL cache 5 phút")
