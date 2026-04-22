import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from vnstock import Vnstock

st.set_page_config(layout="wide")

# =========================
# TIME VN
# =========================
now = datetime.now()
date_str = now.strftime("%d/%m/%Y")
time_str = now.strftime("%H:%M:%S")

# =========================
# HEADER
# =========================
st.title("📊 SCANNER GÀ CHIẾN V30")
col1, col2 = st.columns([1,1])
with col1:
    st.markdown(f"📅 Ngày theo dõi: **{date_str}**")
with col2:
    st.markdown(f"⏰ Giờ VN: **{time_str}**")

# =========================
# SECTOR LIST
# =========================
SECTORS = {
    "BANK_CHUNGKHOAN": ["VCB","BID","CTG","TCB","VPB","MBB","ACB","SHB","STB","SSI","VND","HCM","VIX"],
    "BDS_THEP": ["VHM","VIC","NVL","DXG","HPG","HSG","NKG"],
    "DAUKHI": ["GAS","PVD","PVS","PLX"],
    "BANLE": ["MWG","FRT","DGW"],
    "XUATKHAU": ["VHC","ANV","FMC"],
    "KHAC": ["FPT","REE","GEX"]
}

SECTOR_ORDER = list(SECTORS.keys())

# =========================
# SESSION STATE
# =========================
if "data" not in st.session_state:
    st.session_state.data = pd.DataFrame()

if "sector_index" not in st.session_state:
    st.session_state.sector_index = 0

# =========================
# AUTO LOAD FIRST TIME
# =========================
def load_initial_data():
    vn = Vnstock().stock(symbol="VCB", source="VCI")
    symbols = SECTORS["BANK_CHUNGKHOAN"]

    rows = []
    progress = st.progress(0)

    for i, s in enumerate(symbols):
        try:
            df = vn.quote.history(symbol=s, interval="1D", count=50)
            close = df["close"]

            ema9 = close.ewm(span=9).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]

            rsi = 100 - (100 / (1 + close.pct_change().rolling(14).mean().iloc[-1]))

            rows.append({
                "symbol": s,
                "price": close.iloc[-1],
                "ema9": ema9,
                "ma20": ma20,
                "rsi": rsi
            })

        except:
            continue

        progress.progress((i+1)/len(symbols))

    return pd.DataFrame(rows)

if st.session_state.data.empty:
    st.info("🔄 Đang load dữ liệu ban đầu...")
    st.session_state.data = load_initial_data()

# =========================
# SCAN NEXT SECTOR
# =========================
def scan_next():
    vn = Vnstock().stock(symbol="VCB", source="VCI")

    sector_name = SECTOR_ORDER[st.session_state.sector_index]
    symbols = SECTORS[sector_name]

    rows = []
    progress = st.progress(0)

    for i, s in enumerate(symbols):
        try:
            df = vn.quote.history(symbol=s, interval="1D", count=50)
            close = df["close"]

            ema9 = close.ewm(span=9).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]

            rsi = 100 - (100 / (1 + close.pct_change().rolling(14).mean().iloc[-1]))

            rows.append({
                "symbol": s,
                "price": close.iloc[-1],
                "ema9": ema9,
                "ma20": ma20,
                "rsi": rsi
            })

        except:
            continue

        progress.progress((i+1)/len(symbols))

    df_new = pd.DataFrame(rows)

    st.session_state.data = pd.concat([st.session_state.data, df_new]).drop_duplicates("symbol")

    st.session_state.sector_index += 1
    if st.session_state.sector_index >= len(SECTOR_ORDER):
        st.session_state.sector_index = 0

# =========================
# BUTTONS
# =========================
col1, col2 = st.columns(2)

with col1:
    if st.button("🔍 SCAN NGÀNH TIẾP"):
        scan_next()

with col2:
    if st.button("🔄 RESET"):
        st.session_state.data = pd.DataFrame()
        st.session_state.sector_index = 0

# =========================
# MARKET SCORE (simple)
# =========================
df = st.session_state.data.copy()

score = 0
if not df.empty:
    if (df["price"] > df["ema9"]).mean() > 0.6:
        score += 4
    if (df["price"] > df["ma20"]).mean() > 0.6:
        score += 4
    if (df["rsi"] > 55).mean() > 0.6:
        score += 4

st.subheader("📊 MARKET OVERVIEW")
st.write(f"Market Score: {score}/12")

# =========================
# CLASSIFY STOCK
# =========================
def classify(row):
    if row["price"] > row["ema9"] and row["ema9"] > row["ma20"] and row["rsi"] > 60:
        return "CP MẠNH"
    elif row["price"] > row["ema9"]:
        return "PULL"
    else:
        return "THEO DÕI"

df["group"] = df.apply(classify, axis=1)

# =========================
# DISPLAY GROUPS
# =========================
st.subheader("📌 PHÂN LOẠI CỔ PHIẾU")

cols = st.columns(3)

groups = ["CP MẠNH","PULL","THEO DÕI"]

for i, g in enumerate(groups):
    with cols[i]:
        st.markdown(f"### {g}")
        st.dataframe(df[df["group"]==g][["symbol","price"]])

# =========================
# FULL TABLE
# =========================
st.subheader("📋 BẢNG TỔNG CHI TIẾT")

df = df.sort_values(by="rsi", ascending=False)

st.dataframe(df)
