import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from vnstock import stock_historical_data

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
def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["EMA9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["EMA20"] = df["close"].ewm(span=20, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    df["RSI"] = df["RSI"].fillna(50)

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

    signed_vol = np.sign(df["close"].diff().fillna(0)) * df["volume"].fillna(0)
    df["OBV"] = signed_vol.cumsum()
    df["OBV_EMA"] = df["OBV"].ewm(span=9, adjust=False).mean()

    return df

# ================= CLASSIFY =================
def classify(row: pd.Series) -> str:
    rsi = row["RSI"]
    ema9 = row["EMA9"]
    price = row["close"]
    obv = row["OBV"]
    obv_ema = row["OBV_EMA"]

    if pd.isna(rsi) or pd.isna(ema9) or pd.isna(price) or pd.isna(obv) or pd.isna(obv_ema):
        return "AVOID"

    dist = (price - ema9) / ema9 * 100 if ema9 != 0 else 0

    # Ưu tiên: mạnh nhưng chưa quá nóng
    if 70 <= rsi < 75 and price > ema9 and obv > obv_ema:
        return "STRONG_TREND"

    elif 60 <= rsi < 70 and abs(dist) < 4 and price >= ema9:
        return "BUY_PULL"

    elif 45 < rsi < 60 and price >= ema9 * 0.98:
        return "BUY_EARLY"

    elif rsi >= 75:
        return "WAIT_PULL"

    elif 40 <= rsi <= 50:
        return "ACCUMULATION"

    else:
        return "AVOID"

# ================= DATA FETCH =================
@st.cache_data(ttl=900)
def fetch_symbol_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        df = stock_historical_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            resolution="1D"
        )
        if df is None or df.empty:
            return pd.DataFrame()

        required_cols = {"close", "volume"}
        if not required_cols.issubset(df.columns):
            return pd.DataFrame()

        return df
    except Exception:
        return pd.DataFrame()

# ================= SCAN =================
def run_scan(symbols, min_rsi_filter=None):
    results = []
    today = datetime.now().strftime("%Y-%m-%d")

    progress = st.progress(0)
    status_box = st.empty()

    total = len(symbols)

    for i, symbol in enumerate(symbols, start=1):
        status_box.write(f"Đang quét: {symbol} ({i}/{total})")
        progress.progress(i / total)

        df = fetch_symbol_data(symbol, "2023-01-01", today)
        if df.empty:
            continue

        df = calc_indicators(df)
        if df.empty:
            continue

        row = df.iloc[-1]
        action = classify(row)

        if min_rsi_filter is not None and row["RSI"] < min_rsi_filter:
            continue

        results.append({
            "symbol": symbol,
            "price": round(float(row["close"]), 2),
            "RSI": round(float(row["RSI"]), 2),
            "EMA9": round(float(row["EMA9"]), 2),
            "OBV": round(float(row["OBV"]), 0),
            "action": action
        })

    progress.empty()
    status_box.empty()

    if not results:
        return pd.DataFrame(columns=["symbol", "price", "RSI", "EMA9", "OBV", "action"])

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values(by=["action", "RSI"], ascending=[True, False]).reset_index(drop=True)
    return result_df

# ================= UI =================
st.title("🔥 SCANNER GÀ CHIẾN V15.3 PRO")

st.markdown("### Watchlist đang dùng")
st.write(", ".join(WATCHLIST))

col_a, col_b = st.columns([1, 3])

with col_a:
    only_priority = st.checkbox("Chỉ hiện ƯU TIÊN MUA / THEO DÕI", value=False)
    scan_btn = st.button("🚀 SCAN")

if scan_btn:
    min_rsi = 40 if only_priority else None
    df = run_scan(WATCHLIST, min_rsi_filter=min_rsi)

    if df.empty:
        st.warning("Không có dữ liệu")
    else:
        if only_priority:
            df = df[df["action"].isin(["BUY_PULL", "BUY_EARLY", "STRONG_TREND", "ACCUMULATION"])]

        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            st.subheader("BUY_PULL")
            st.dataframe(
                df[df["action"] == "BUY_PULL"][["symbol", "price", "RSI", "EMA9"]],
                use_container_width=True
            )

        with c2:
            st.subheader("BUY_EARLY")
            st.dataframe(
                df[df["action"] == "BUY_EARLY"][["symbol", "price", "RSI", "EMA9"]],
                use_container_width=True
            )

        with c3:
            st.subheader("WAIT_PULL")
            st.dataframe(
                df[df["action"] == "WAIT_PULL"][["symbol", "price", "RSI", "EMA9"]],
                use_container_width=True
            )

        with c4:
            st.subheader("ACCUMULATION")
            st.dataframe(
                df[df["action"] == "ACCUMULATION"][["symbol", "price", "RSI", "EMA9"]],
                use_container_width=True
            )

        with c5:
            st.subheader("🔥 STRONG_TREND")
            st.dataframe(
                df[df["action"] == "STRONG_TREND"][["symbol", "price", "RSI", "EMA9"]],
                use_container_width=True
            )

        st.markdown("### Tổng hợp")
        st.dataframe(df, use_container_width=True)
