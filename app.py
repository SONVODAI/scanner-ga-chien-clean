import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from streamlit_autorefresh import st_autorefresh
import datetime

st.set_page_config(page_title="Scanner Gà Chiến V15", layout="wide")
st.title("🐔 Scanner Gà Chiến V15 – Alert Realtime")

# =========================
# AUTO REFRESH (5 phút, giờ giao dịch)
# =========================
now = datetime.datetime.now()
if 9 <= now.hour <= 15:
    st.caption("⏱ Tự cập nhật mỗi 5 phút (giờ giao dịch)")
    st_autorefresh(interval=300000, key="refresh")

# =========================
# SIDEBAR
# =========================
st.sidebar.header("Thiết lập")
market_score = st.sidebar.slider("Market Score", 1, 10, 8)
top_n = st.sidebar.slider("Top toàn thị trường", 3, 15, 5)

# =========================
# INPUT
# =========================
watchlist_text = st.text_area(
    "Danh sách mã theo dõi",
    """VCB, BID, CTG, TCB, MBB, VPB, STB, HDB, ACB, SHB, TPB, LPB, EIB, ABB, MSB, KLB, EVF
SSI, VIX, SHS, MBS, HCM, VCI, VND, CTS, FTS, BSI, BVS, ORS, VDS, AGR
VHM, NLG, KDH, CEO, CII, DXG, TCH, DPG, HDC, NVL, NTL, NHA, HUT, DIG, PDR, DXS
VGC, IDC, KBC, SZC, BCM, LHG, IJC, GVR, PHR, DPR, SIP, TRC, DRC, CSM
MWG, DGW, FRT, PET, PNJ, MSN, PAN, FMC, DBC, HAG, VNM, SAB, SBT, TLG
REE, GEE, GEX, PC1, NT2, HDG, GEG, POW
DPM, DCM, LAS, DDV, DGC, CSV, BFC, MSR, BMP, NTP
BSR, PVS, PVD, PVB, PVC, PVT, OIL, PLX, GAS
HAH, GMD, VSC, VOS, VTO, HVN, VJC, ACV""",
    height=220
)

def parse_codes(text):
    items = []
    for x in text.replace("\n", ",").split(","):
        x = x.strip().upper()
        if x:
            if not x.endswith(".VN"):
                x += ".VN"
            items.append(x)
    return list(dict.fromkeys(items))

watchlist = parse_codes(watchlist_text)

# =========================
# FUNCTIONS
# =========================
@st.cache_data(ttl=300)
def fetch(symbol):
    return yf.download(symbol, period="6mo", interval="1d", progress=False)

def rsi(close):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    return 100 - (100/(1+rs))

def analyze(symbol):
    try:
        df = fetch(symbol)
        if df is None or df.empty or len(df) < 60:
            return None

        close = df["Close"]
        vol = df["Volume"]

        ema9 = close.ewm(span=9).mean()
        ma20 = close.rolling(20).mean()
        r = rsi(close)

        latest = close.iloc[-1]

        # CONDITIONS
        cond_price = latest > ema9.iloc[-1] > ma20.iloc[-1]
        cond_rsi = r.iloc[-1] > 55
        cond_rsi_turn = r.iloc[-1] > r.iloc[-3]
        cond_slope = ema9.iloc[-1] > ema9.iloc[-3]

        # RETURN
        ret20 = latest / close.iloc[-20] - 1

        # BREAK
        high20 = close.rolling(20).max().iloc[-2]
        break_signal = latest >= high20 * 0.98

        # STAGE
        if ret20 < 0.1:
            stage = "B1"
        elif ret20 < 0.25:
            stage = "B2"
        else:
            stage = "B3"

        # STATUS
        if cond_price and cond_rsi and cond_slope:
            status = "ƯU TIÊN MUA"
        elif cond_price:
            status = "THEO DÕI"
        else:
            status = "LOẠI"

        # ACTION
        if status == "ƯU TIÊN MUA" and stage == "B2":
            action = "👉 MUA"
        elif stage == "B3":
            action = "👉 GIỮ"
        else:
            action = "👀 CANH"

        return {
            "Ticker": symbol,
            "Close": round(latest,2),
            "EMA9": round(ema9.iloc[-1],2),
            "MA20": round(ma20.iloc[-1],2),
            "RSI": round(r.iloc[-1],2),
            "Ret20": round(ret20*100,1),
            "Break": break_signal,
            "Stage": stage,
            "Status": status,
            "Action": action
        }

    except:
        return None

# =========================
# SESSION STATE (ALERT)
# =========================
if "prev" not in st.session_state:
    st.session_state.prev = {}

# =========================
# RUN
# =========================
if st.button("🚀 Quét V15"):
    results = []
    alerts = []

    for s in watchlist:
        r = analyze(s)
        if r:
            results.append(r)

            prev = st.session_state.prev.get(s)

            if prev:
                # BREAK mới
                if r["Break"] and not prev["Break"]:
                    alerts.append(f"🚀 {s} vừa BREAK")

                # vào B2
                if r["Stage"] == "B2" and prev["Stage"] != "B2":
                    alerts.append(f"🐥 {s} vừa vào B2")

                # gãy
                if prev["Status"] == "ƯU TIÊN MUA" and r["Status"] != "ƯU TIÊN MUA":
                    alerts.append(f"⚠️ {s} gãy trend")

            st.session_state.prev[s] = r

    df = pd.DataFrame(results).sort_values(by="Ret20", ascending=False)

    # ALERT UI
    if alerts:
        st.subheader("🔔 CẢNH BÁO REALTIME")
        for a in alerts:
            st.warning(a)
    else:
        st.info("Không có tín hiệu mới")

    st.subheader("📊 Kết quả")
    st.dataframe(df, use_container_width=True)

    st.subheader("🔥 ƯU TIÊN MUA")
    st.dataframe(df[df["Status"]=="ƯU TIÊN MUA"].head(top_n))

    st.subheader("👀 THEO DÕI")
    st.dataframe(df[df["Status"]=="THEO DÕI"])

    st.subheader("❌ LOẠI")
    st.dataframe(df[df["Status"]=="LOẠI"])

else:
    st.info("Bấm quét để chạy scanner")
