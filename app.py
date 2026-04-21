import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(layout="wide", page_title="Scanner Gà Chiến V16 Clean")

# =========================================================
# WATCHLIST CHÍNH
# =========================================================
WATCHLIST = [
    "VCB","BID","CTG","TCB","MBB","VPB","STB","HDB","ACB","SHB","TPB","LPB","EIB","ABB","MSB","KLB","EVF","SSB","VIB","BVB","OCB",
    "SSI","VIX","SHS","MBS","HCM","VCI","VND","CTS","FTS","BSI","BVS","ORS","VDS","AGR",
    "VHM","VIC","NLG","KDH","CEO","CII","DXG","TCH","HHS","DPG","HDC","NVL","NTL","NHA","HUT","DIG","PDR","DXS","VRE",
    "VGC","IDC","KBC","SZC","BCM","DTD","LHG","IJC","GVR","PHR","DPR","SIP","TRC",
    "MWG","DGW","FRT","PET","PNJ","MSN","MCH","PAN","FMC","DBC","HAG","VNM","MML","SAB","SBT","TLG","BAF",
    "REE","GEE","GEX","PC1","NT2","HDG","GEG","POW",
    "DPM","DCM","LAS","DDV","DGC","CSV","BFC","MSR","BMP","NTP",
    "BSR","PVS","PVD","PVB","PVC","PVT","OIL","PLX","GAS",
    "HAH","GMD","VSC","VOS","VTO","HVN","VJC","ACV",
    "VTP","CTR","VGI","FPT","FOX","CMG","ELC",
    "MSH","TNG","TCM","GIL","VGT","VHC","ANV","VCS","PTB",
    "CTD","HHV","FCN","LCG","CTI","KSB","C4G","VCG","DHA","PLC","HT1",
    "HPG","HSG","NKG","VGS","TLH","TVN",
    "DVN","DCL","DHG","IMP","DBD","DHT",
    "BVH","MIG","BMI"
]

# =========================================================
# PHÂN NHÓM
# =========================================================
SECTOR_MAP = {
    "NGÂN HÀNG": ["VCB","BID","CTG","TCB","MBB","VPB","STB","HDB","ACB","SHB","TPB","LPB","EIB","ABB","MSB","KLB","SSB","VIB","BVB","OCB"],
    "CHỨNG KHOÁN": ["SSI","VIX","SHS","MBS","HCM","VCI","VND","CTS","FTS","BSI","BVS","ORS","VDS","AGR"],
    "BĐS DÂN CƯ": ["VHM","VIC","NLG","KDH","CEO","CII","DXG","TCH","HHS","DPG","HDC","NVL","NTL","NHA","HUT","DIG","PDR","DXS","VRE"],
    "KCN - CAO SU": ["VGC","IDC","KBC","SZC","BCM","DTD","LHG","IJC","GVR","PHR","DPR","SIP","TRC"],
    "BÁN LẺ - TIÊU DÙNG": ["MWG","DGW","FRT","PET","PNJ","MSN","MCH","PAN","FMC","DBC","HAG","VNM","MML","SAB","SBT","TLG","BAF"],
    "ĐIỆN - HẠ TẦNG": ["REE","GEE","GEX","PC1","NT2","HDG","GEG","POW"],
    "PHÂN BÓN - HÓA CHẤT": ["DPM","DCM","LAS","DDV","DGC","CSV","BFC","MSR","BMP","NTP"],
    "DẦU KHÍ": ["BSR","PVS","PVD","PVB","PVC","PVT","OIL","PLX","GAS"],
    "VẬN TẢI - LOGISTICS": ["HAH","GMD","VSC","VOS","VTO","HVN","VJC","ACV"],
    "CÔNG NGHỆ - VIỄN THÔNG": ["VTP","CTR","VGI","FPT","FOX","CMG","ELC"],
    "XUẤT KHẨU": ["MSH","TNG","TCM","GIL","VGT","VHC","ANV","VCS","PTB"],
    "ĐẦU TƯ CÔNG - VLXD": ["CTD","HHV","FCN","LCG","CTI","KSB","C4G","VCG","DHA","PLC","HT1"],
    "THÉP": ["HPG","HSG","NKG","VGS","TLH","TVN"],
    "DƯỢC - BẢO HIỂM": ["DVN","DCL","DHG","IMP","DBD","DHT","BVH","MIG","BMI"],
}

# =========================================================
# HÀM PHỤ
# =========================================================
def get_symbols_by_sector(sector_name: str):
    if sector_name == "TẤT CẢ":
        return WATCHLIST
    return SECTOR_MAP.get(sector_name, WATCHLIST)


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return np.nan


def fmt_num(x, digits=2):
    if pd.isna(x):
        return ""
    return round(float(x), digits)


# =========================================================
# DATA
# =========================================================
@st.cache_data(ttl=600)
def fetch_data(symbol: str) -> pd.DataFrame:
    try:
        df = yf.download(
            symbol + ".VN",
            period="8mo",
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=False
        )

        if df is None or df.empty:
            return pd.DataFrame()

        df = flatten_columns(df).copy()

        rename_map = {}
        for col in df.columns:
            c = str(col).lower()
            if c == "open":
                rename_map[col] = "open"
            elif c == "high":
                rename_map[col] = "high"
            elif c == "low":
                rename_map[col] = "low"
            elif c == "close":
                rename_map[col] = "close"
            elif c == "volume":
                rename_map[col] = "volume"

        df = df.rename(columns=rename_map)

        required = ["open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in required):
            return pd.DataFrame()

        df = df[required].dropna().copy()
        if len(df) < 35:
            return pd.DataFrame()

        return df
    except Exception:
        return pd.DataFrame()


# =========================================================
# INDICATORS
# =========================================================
def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    try:
        out = df.copy()

        out["EMA9"] = out["close"].ewm(span=9, adjust=False).mean()
        out["EMA20"] = out["close"].ewm(span=20, adjust=False).mean()
        out["EMA50"] = out["close"].ewm(span=50, adjust=False).mean()

        delta = out["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        out["RSI"] = 100 - (100 / (1 + rs))
        out["RSI_EMA9"] = out["RSI"].ewm(span=9, adjust=False).mean()

        obv_delta = np.sign(out["close"].diff().fillna(0)) * out["volume"]
        out["OBV"] = obv_delta.cumsum()
        out["OBV_EMA9"] = out["OBV"].ewm(span=9, adjust=False).mean()

        ema12 = out["close"].ewm(span=12, adjust=False).mean()
        ema26 = out["close"].ewm(span=26, adjust=False).mean()
        out["MACD"] = ema12 - ema26
        out["MACD_SIGNAL"] = out["MACD"].ewm(span=9, adjust=False).mean()
        out["MACD_HIST"] = out["MACD"] - out["MACD_SIGNAL"]

        prev_close = out["close"].shift(1)
        tr1 = out["high"] - out["low"]
        tr2 = (out["high"] - prev_close).abs()
        tr3 = (out["low"] - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        out["ATR14"] = tr.ewm(alpha=1/14, adjust=False).mean()

        out["VOL_MA20"] = out["volume"].rolling(20).mean()

        return out.dropna().copy()
    except Exception:
        return pd.DataFrame()


# =========================================================
# SCORING & CLASSIFY
# =========================================================
def classify_stock(row: pd.Series, prev_row: pd.Series) -> tuple:
    try:
        price = safe_float(row["close"])
        ema9 = safe_float(row["EMA9"])
        ema20 = safe_float(row["EMA20"])
        ema50 = safe_float(row["EMA50"])
        rsi = safe_float(row["RSI"])
        rsi_ema9 = safe_float(row["RSI_EMA9"])
        obv = safe_float(row["OBV"])
        obv_ema9 = safe_float(row["OBV_EMA9"])
        macd = safe_float(row["MACD"])
        macd_hist = safe_float(row["MACD_HIST"])
        volume = safe_float(row["volume"])
        vol_ma20 = safe_float(row["VOL_MA20"])
        atr = safe_float(row["ATR14"])

        prev_high = safe_float(prev_row["high"])
        prev_close = safe_float(prev_row["close"])
        prev_rsi = safe_float(prev_row["RSI"])

        if any(pd.isna(v) for v in [price, ema9, ema20, rsi, obv, obv_ema9]):
            return ("LOẠI", 0)

        score = 0

        # 1. Giá và cấu trúc
        if price > ema9:
            score += 2
        if ema9 > ema20:
            score += 2
        if ema20 > ema50:
            score += 1

        # 2. RSI
        if rsi > 55:
            score += 2
        if rsi > rsi_ema9:
            score += 1

        # 3. OBV
        if obv > obv_ema9:
            score += 2

        # 4. MACD
        if macd > 0:
            score += 1
        if macd_hist > 0:
            score += 1

        # 5. Volume
        if not pd.isna(vol_ma20) and vol_ma20 > 0 and volume > vol_ma20:
            score += 1

        # 6. ATR
        if not pd.isna(atr) and atr > 0:
            score += 1

        dist_pct = ((price - ema9) / ema9) * 100 if ema9 > 0 else np.nan
        break_signal = price > prev_high and volume > vol_ma20 and rsi >= 60 if not pd.isna(prev_high) and not pd.isna(vol_ma20) else False
        pull_signal = price > ema9 and ema9 > ema20 and 55 <= rsi <= 70 and abs(dist_pct) <= 4 and obv > obv_ema9
        early_signal = price >= ema9 * 0.98 and 45 <= rsi < 60 and rsi >= prev_rsi and obv >= obv_ema9 * 0.98 if not pd.isna(prev_rsi) else False
        accumulation_signal = 40 <= rsi <= 55 and abs(dist_pct) <= 5 if not pd.isna(dist_pct) else False
        strong_signal = price > ema9 and ema9 > ema20 and rsi >= 70 and obv > obv_ema9 and macd > 0

        if strong_signal and score >= 9:
            action = "CP MẠNH"
        elif break_signal and score >= 8:
            action = "MUA BREAK"
        elif pull_signal and score >= 8:
            action = "MUA PULL"
        elif early_signal and score >= 6:
            action = "MUA EARLY"
        elif accumulation_signal and score >= 5:
            action = "TÍCH LŨY"
        elif score >= 4:
            action = "THEO DÕI"
        else:
            action = "LOẠI"

        return (action, score)

    except Exception:
        return ("LOẠI", 0)


# =========================================================
# SCAN ENGINE
# =========================================================
def run_scan(symbols: list[str]) -> pd.DataFrame:
    records = []

    for symbol in symbols:
        raw = fetch_data(symbol)
        if raw.empty:
            continue

        df = calc_indicators(raw)
        if df.empty or len(df) < 25:
            continue

        row = df.iloc[-1]
        prev_row = df.iloc[-2]

        action, score = classify_stock(row, prev_row)

        if action == "LOẠI":
            continue

        records.append({
            "symbol": symbol,
            "price": fmt_num(row["close"], 2),
            "EMA9": fmt_num(row["EMA9"], 2),
            "EMA20": fmt_num(row["EMA20"], 2),
            "RSI": fmt_num(row["RSI"], 1),
            "OBV>EMA": "Có" if safe_float(row["OBV"]) > safe_float(row["OBV_EMA9"]) else "Không",
            "MACD": fmt_num(row["MACD"], 2),
            "VOL/MA20": fmt_num(row["volume"] / row["VOL_MA20"], 2) if safe_float(row["VOL_MA20"]) > 0 else np.nan,
            "score": score,
            "action": action
        })

    if len(records) == 0:
        return pd.DataFrame()

    result = pd.DataFrame(records).sort_values(
        by=["score", "RSI", "VOL/MA20"],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    return result


# =========================================================
# UI
# =========================================================
st.title("🔥 SCANNER GÀ CHIẾN V16 PRO (.VN CLEAN)")

sector_options = ["TẤT CẢ"] + list(SECTOR_MAP.keys())
selected_sector = st.selectbox("Chọn nhóm", sector_options, index=0)

show_strong_only = st.checkbox("Chỉ hiện nhóm mạnh / mua", value=False)

symbols = get_symbols_by_sector(selected_sector)

if st.button("🚀 SCAN", use_container_width=False):
    result_df = run_scan(symbols)

    if result_df.empty:
        st.warning("Không có dữ liệu hoặc chưa có mã đạt điều kiện.")
    else:
        if show_strong_only:
            result_df = result_df[result_df["action"].isin(["CP MẠNH", "MUA BREAK", "MUA PULL", "MUA EARLY"])]

        col1, col2, col3, col4, col5, col6 = st.columns(6)

        with col1:
            st.subheader("CP MẠNH")
            st.dataframe(result_df[result_df["action"] == "CP MẠNH"], use_container_width=True)

        with col2:
            st.subheader("MUA BREAK")
            st.dataframe(result_df[result_df["action"] == "MUA BREAK"], use_container_width=True)

        with col3:
            st.subheader("MUA PULL")
            st.dataframe(result_df[result_df["action"] == "MUA PULL"], use_container_width=True)

        with col4:
            st.subheader("MUA EARLY")
            st.dataframe(result_df[result_df["action"] == "MUA EARLY"], use_container_width=True)

        with col5:
            st.subheader("TÍCH LŨY")
            st.dataframe(result_df[result_df["action"] == "TÍCH LŨY"], use_container_width=True)

        with col6:
            st.subheader("THEO DÕI")
            st.dataframe(result_df[result_df["action"] == "THEO DÕI"], use_container_width=True)

        st.divider()
        st.subheader("Tổng hợp toàn bộ mã đạt điều kiện")
        st.dataframe(result_df, use_container_width=True)
