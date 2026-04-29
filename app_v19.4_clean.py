# =========================================================
# SCANNER GÀ CHIẾN V18.4 + SLOPE CLEAN REWRITE
# Full app.py - viết lại sạch từ đầu
# Có: Market REAL/LIVE, EMA9/MA20 slope, RSI, OBV, nhóm CP,
# khuyến nghị mua, bảng gà tăng tốc, quản trị danh mục.
# =========================================================

import time
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Scanner Gà Chiến V18.4 + SLOPE",
    page_icon="🐔",
    layout="wide",
)

st.title("🐔 Scanner Gà Chiến V18.4 + SLOPE CLEAN")
st.caption("Bản viết lại sạch: giữ lõi V18.4 + thêm độ dốc EMA9 so với MA20")


# =========================================================
# WATCHLIST
# =========================================================
WATCHLIST = sorted(list(set([
    "PLX", "PVS", "PVD", "PVB", "PVC", "PVT", "BSR", "OIL", "GAS",
    "HAH", "VSC", "GMD", "VOS", "VTO", "ACV",

    "MSH", "TNG", "TCM", "GIL", "VHC", "ANV", "FMC", "VCS", "PTB",

    "BFC", "DCM", "DPM", "CSV", "DDV", "LAS", "BMP", "NTP", "AAA",
    "PAC", "MSR", "REE", "GEE", "GEX", "PC1", "HDG", "GEG", "NT2",
    "TV2", "DGC",

    "C4G", "FCN", "CII", "KSB", "DHA", "CTI", "HBC", "HPG", "HSG",
    "NKG", "VGS", "CTD", "HHV", "VCG",

    "MWG", "FRT", "DGW", "PET", "HAX", "MSN", "DBC", "HAG", "BAF",
    "MCH", "PAN", "VNM", "MML",

    "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "SHB", "SSB",
    "STB", "HDB", "TPB", "VIB", "LPB", "OCB", "MSB", "NAB", "EIB",
    "VND", "SSI", "HCM", "SHS", "VIX", "BSI", "FTS", "TVS", "APS",
    "AGR", "VCI", "TCX", "VCK", "VPX", "ORS", "BVS", "VDS", "MBS",

    "VGC", "SZC", "IDC", "KBC", "LHG", "IJC", "DTD", "BCM",

    "GVR", "SIP", "DPR", "PHR", "DRI",

    "FPT", "VGI", "CTR", "VTP", "CMG", "ELC", "FOX",

    "HVN", "VJC", "IMP", "BVH", "SBT", "LSS", "PNJ", "TLG", "DHT",
    "TNH", "YEG",

    "VIC", "VHM", "VRE", "NVL", "DXG", "DXS", "DIG", "CEO", "TCH",
    "EVF", "SAB"
])))

DEFAULT_SUFFIX = ".VN"


# =========================================================
# STYLE
# =========================================================
st.markdown("""
<style>
div[data-testid="stDataFrame"] {
    border-radius: 10px;
}
.small-note {
    color: #666;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# BASIC HELPERS
# =========================================================
def to_float(value, default=np.nan):
    try:
        if isinstance(value, pd.Series):
            if len(value) == 0:
                return default
            value = value.iloc[-1]
        if isinstance(value, np.ndarray):
            if len(value) == 0:
                return default
            value = value[-1]
        return float(value)
    except Exception:
        return default


def safe_round(value, digits=2):
    try:
        if pd.isna(value):
            return np.nan
        return round(float(value), digits)
    except Exception:
        return np.nan


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).fillna(0).cumsum()


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join([str(x) for x in col if str(x) != ""]).strip("_")
            for col in df.columns.to_list()
        ]
    else:
        df.columns = [str(c) for c in df.columns]
        
    return df


def find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {str(c).lower(): c for c in df.columns}

    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]

    for c in df.columns:
        cl = str(c).lower()
        for cand in candidates:
            if cand.lower() in cl:
                return c

    return None


# =========================================================
# DATA DOWNLOAD
# =========================================================
@st.cache_data(ttl=300, show_spinner=False)
def download_symbol_data(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    ticker = f"{symbol}{DEFAULT_SUFFIX}"

    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
            group_by="column",
        )
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = flatten_columns(df).reset_index()

    date_col = find_col(df, ["Date", "Datetime"])
    open_col = find_col(df, ["Open"])
    high_col = find_col(df, ["High"])
    low_col = find_col(df, ["Low"])
    close_col = find_col(df, ["Close"])
    vol_col = find_col(df, ["Volume"])

    needed = [date_col, open_col, high_col, low_col, close_col, vol_col]
    if any(col is None for col in needed):
        return pd.DataFrame()

    out = df[[date_col, open_col, high_col, low_col, close_col, vol_col]].copy()
    out.columns = ["date", "open", "high", "low", "close", "volume"]

    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["close"])
    out = out.sort_values("date").reset_index(drop=True)

    return out


# =========================================================
# INDICATORS
# =========================================================
def slope_state_text(slope: float) -> str:
    if pd.isna(slope):
        return ""
    if slope > 2:
        return "🟢 Tăng tốc"
    if slope > 0:
        return "🟡 Ổn định"
    return "🔴 Yếu"


def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()

    x["ema9"] = ema(x["close"], 9)
    x["ma20"] = sma(x["close"], 20)

    # =====================================================
    # SLOPE EMA9 VS MA20 - CỘT MỚI
    # =====================================================
    x["ema9_ma20_slope"] = np.where(
        x["ma20"] != 0,
        (x["ema9"] - x["ma20"]) / x["ma20"] * 100,
        np.nan
    )
    x["ema9_ma20_slope_change"] = x["ema9_ma20_slope"] - x["ema9_ma20_slope"].shift(3)
    x["slope_state"] = x["ema9_ma20_slope"].apply(slope_state_text)

    x["rsi14"] = calc_rsi(x["close"], 14)
    x["rsi_slope"] = x["rsi14"] - x["rsi14"].shift(3)

    x["obv"] = calc_obv(x["close"], x["volume"])
    x["obv_ema9"] = ema(x["obv"], 9)

    x["vol_ma20"] = sma(x["volume"], 20)

    return x


# =========================================================
# SCORE
# =========================================================
def calc_price_score(close_, ema9_, ma20_, ema9_prev):
    if pd.notna(close_) and pd.notna(ema9_) and pd.notna(ma20_) and pd.notna(ema9_prev):
        if close_ > ema9_ > ma20_ and ema9_ > ema9_prev:
            return 2
        if close_ > ema9_:
            return 1
    return 0


def calc_rsi_score(rsi_, rsi_slope_):
    if pd.notna(rsi_) and pd.notna(rsi_slope_):
        if rsi_ > 65 and rsi_slope_ > 0:
            return 2
        if rsi_ > 55:
            return 1
    return 0


def calc_obv_score(obv_, obv_ema9_, obv_prev):
    if pd.notna(obv_) and pd.notna(obv_ema9_) and pd.notna(obv_prev):
        if obv_ > obv_ema9_ and obv_ > obv_prev:
            return 2
        if obv_ > obv_ema9_:
            return 1
    return 0


def calc_slope_score(slope_, slope_change_):
    if pd.notna(slope_) and pd.notna(slope_change_):
        if slope_ > 2 and slope_change_ > 0:
            return 2
        if slope_ > 0:
            return 1
    return 0


# =========================================================
# PULL / WARNING / STATUS
# =========================================================
def classify_pull_label(dist_from_ema9, rsi_, rsi_slope_, obv_, obv_ema9_):
    if not pd.notna(dist_from_ema9):
        return ""

    obv_ok = pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ >= obv_ema9_
    rsi_ok = pd.notna(rsi_) and rsi_ > 55
    rsi_strong = pd.notna(rsi_) and rsi_ > 60
    slope_up = pd.notna(rsi_slope_) and rsi_slope_ > 0

    if -1.0 <= dist_from_ema9 <= 1.0 and rsi_strong and slope_up and obv_ok:
        return "PULL ĐẸP"

    if -2.5 <= dist_from_ema9 <= 2.0 and rsi_ok and obv_ok:
        return "PULL VỪA"

    return "PULL XẤU"


def build_warning(close_, ema9_, rsi_, rsi_slope_, obv_, obv_ema9_, pull_label, slope_):
    warnings = []

    if pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ < obv_ema9_:
        warnings.append("OBV gãy")

    if pd.notna(rsi_) and rsi_ < 55:
        warnings.append("RSI yếu")

    if pd.notna(rsi_slope_) and rsi_slope_ < 0:
        warnings.append("RSI chững")

    if pd.notna(close_) and pd.notna(ema9_) and close_ < ema9_:
        warnings.append("Giá dưới EMA9")

    if pd.notna(slope_) and slope_ < 0:
        warnings.append("Slope âm")

    if pull_label == "PULL XẤU":
        warnings.append("Pull xấu")

    return " | ".join(dict.fromkeys(warnings))


def build_status(total_score, warning, group_name):
    if group_name == "PULL ĐẸP":
        return "🟢"
    if total_score >= 6 and warning == "":
        return "🟢"
    if total_score >= 3:
        return "🟡"
    return "🔴"


# =========================================================
# GROUP CLASSIFY
# =========================================================
def classify_group(row: dict) -> str:
    price = row["price"]
    ema9_ = row["ema9"]
    ma20_ = row["ma20"]
    vol_ = row["volume"]
    vol_ma20_ = row["vol_ma20"]
    total = row["total_score"]
    e = row["E"]
    r = row["R"]
    o = row["O"]
    s = row["S"]
    dist_from_ema9 = row["dist_from_ema9_pct"]
    breakout_ref = row["breakout_ref"]
    pull_label = row["pull_label"]
    slope_ = row["ema9_ma20_slope"]

    leader = (
        total >= 5
        and e >= 1
        and o >= 1
        and pd.notna(price)
        and pd.notna(ema9_)
        and price >= ema9_ * 0.97
    )

    if (
        pd.notna(slope_)
        and slope_ > 2
        and total >= 6
        and e >= 1
        and r >= 1
        and o >= 1
    ):
        return "GÀ TĂNG TỐC"

    if not leader:
        if total <= 1:
            return "THEO DÕI"
        if total == 2:
            return "TÍCH LŨY"
        return "MUA EARLY"

    if pull_label == "PULL ĐẸP" and pd.notna(price) and pd.notna(ma20_) and price >= ma20_:
        return "PULL ĐẸP"

    if pull_label == "PULL VỪA" and pd.notna(price) and pd.notna(ma20_) and price >= ma20_:
        return "PULL VỪA"

    if (
        pd.notna(breakout_ref)
        and pd.notna(price)
        and pd.notna(vol_)
        and pd.notna(vol_ma20_)
        and price >= breakout_ref * 1.01
        and vol_ >= vol_ma20_ * 1.2
        and r >= 1
        and o >= 1
    ):
        return "MUA BREAK"

    if (
        pd.notna(dist_from_ema9)
        and dist_from_ema9 > 1.5
        and e == 2
        and r >= 1
        and o >= 1
    ):
        return "CP MẠNH"

    return "MUA EARLY"


# =========================================================
# ANALYZE ONE SYMBOL
# =========================================================
def analyze_symbol(symbol: str) -> dict | None:
    raw = download_symbol_data(symbol)

    if raw.empty or len(raw) < 40:
        return None

    df = build_indicators(raw)

    if df.empty or len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = to_float(last["close"])
    ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])
    ema9_prev = to_float(prev["ema9"])

    slope_ = to_float(last["ema9_ma20_slope"])
    slope_change_ = to_float(last["ema9_ma20_slope_change"])
    slope_state_ = str(last["slope_state"])

    rsi_ = to_float(last["rsi14"])
    rsi_slope_ = to_float(last["rsi_slope"])

    obv_ = to_float(last["obv"])
    obv_ema9_ = to_float(last["obv_ema9"])
    obv_prev = to_float(prev["obv"])

    vol_ = to_float(last["volume"])
    vol_ma20_ = to_float(last["vol_ma20"])

    breakout_ref = to_float(df["high"].iloc[-21:-1].max())

    dist_from_ema9 = np.nan
    if pd.notna(price) and pd.notna(ema9_) and ema9_ != 0:
        dist_from_ema9 = (price / ema9_ - 1) * 100

    E = calc_price_score(price, ema9_, ma20_, ema9_prev)
    R = calc_rsi_score(rsi_, rsi_slope_)
    O = calc_obv_score(obv_, obv_ema9_, obv_prev)
    S = calc_slope_score(slope_, slope_change_)

    total_score = E + R + O + S

    pull_label = classify_pull_label(
        dist_from_ema9=dist_from_ema9,
        rsi_=rsi_,
        rsi_slope_=rsi_slope_,
        obv_=obv_,
        obv_ema9_=obv_ema9_,
    )

    obv_status = "🟢" if pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ >= obv_ema9_ else "🔴"

    row = {
        "symbol": symbol,
        "price": safe_round(price, 0),
        "ema9": safe_round(ema9_, 2),
        "ma20": safe_round(ma20_, 2),

        "ema9_ma20_slope": safe_round(slope_, 2),
        "ema9_ma20_slope_change": safe_round(slope_change_, 2),
        "slope_state": slope_state_,

        "rsi14": safe_round(rsi_, 2),
        "rsi_slope": safe_round(rsi_slope_, 2),

        "obv": safe_round(obv_, 0),
        "obv_ema9": safe_round(obv_ema9_, 0),
        "obv_status": obv_status,

        "volume": safe_round(vol_, 0),
        "vol_ma20": safe_round(vol_ma20_, 0),

        "breakout_ref": safe_round(breakout_ref, 2),
        "dist_from_ema9_pct": safe_round(dist_from_ema9, 2),
        "pull_label": pull_label,

        "E": E,
        "R": R,
        "O": O,
        "S": S,
        "total_score": total_score,
    }

    row["group"] = classify_group(row)
    row["warning"] = build_warning(price, ema9_, rsi_, rsi_slope_, obv_, obv_ema9_, pull_label, slope_)
    row["status"] = build_status(total_score, row["warning"], row["group"])

    return row


# =========================================================
# SCAN
# =========================================================
@st.cache_data(ttl=300, show_spinner=False)
def run_scan(symbols: list[str]) -> pd.DataFrame:
    rows = []

    for symbol in symbols:
        try:
            item = analyze_symbol(symbol)
            if item is not None:
                rows.append(item)
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    group_priority = {
        "GÀ TĂNG TỐC": 0,
        "PULL ĐẸP": 1,
        "MUA BREAK": 2,
        "PULL VỪA": 3,
        "CP MẠNH": 4,
        "MUA EARLY": 5,
        "TÍCH LŨY": 6,
        "THEO DÕI": 7,
    }

    df["group_rank"] = df["group"].map(group_priority).fillna(99)

    sort_cols = [
        "group_rank",
        "total_score",
        "S",
        "E",
        "O",
        "R",
        "ema9_ma20_slope",
    ]

    existing_sort_cols = [c for c in sort_cols if c in df.columns]

    if existing_sort_cols:
        ascending_map = {
            "group_rank": True,
            "total_score": False,
            "S": False,
            "E": False,
            "O": False,
            "R": False,
            "ema9_ma20_slope": False,
        }
        ascending = [ascending_map.get(c, False) for c in existing_sort_cols]
        df = df.sort_values(by=existing_sort_cols, ascending=ascending).reset_index(drop=True)

    return df


# =========================================================
# MARKET REAL / LIVE
# =========================================================
def calc_market_live(df: pd.DataFrame) -> float:
    total = len(df)
    if total == 0:
        return 0.0

    e_ratio = len(df[df["E"] >= 1]) / total
    r_ratio = len(df[df["R"] >= 1]) / total
    o_ratio = len(df[df["O"] >= 1]) / total
    s_ratio = len(df[df["S"] >= 1]) / total

    strong = len(df[df["group"] == "CP MẠNH"])
    accel = len(df[df["group"] == "GÀ TĂNG TỐC"])
    breakout = len(df[df["group"] == "MUA BREAK"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])

    score = (
        e_ratio * 2.5
        + r_ratio * 2.5
        + o_ratio * 2.0
        + s_ratio * 2.0
        + min(strong / 10, 1) * 1.0
        + min(accel / 6, 1) * 1.5
        + min(breakout / 8, 1) * 1.0
        + min(pull_good / 6, 1) * 0.5
    )

    return round(min(score, 13), 1)


def calc_market_real(df: pd.DataFrame) -> float:
    total = len(df)
    if total == 0:
        return 0.0

    e_ratio = len(df[df["E"] >= 1]) / total
    r_ratio = len(df[df["R"] >= 1]) / total
    o_ratio = len(df[df["O"] >= 1]) / total
    s_ratio = len(df[df["S"] >= 1]) / total

    strong = len(df[df["group"] == "CP MẠNH"])
    accel = len(df[df["group"] == "GÀ TĂNG TỐC"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])
    pull_ok = len(df[df["group"] == "PULL VỪA"])

    score = (
        e_ratio * 3.0
        + r_ratio * 2.5
        + o_ratio * 2.5
        + s_ratio * 2.0
        + min(strong / 12, 1) * 1.0
        + min(accel / 8, 1) * 1.2
        + min((pull_good + pull_ok) / 12, 1) * 0.8
    )

    return round(min(score, 13), 1)


def market_status_text(score: float) -> tuple[str, str]:
    if score >= 8:
        return "🟢 THỊ TRƯỜNG KHỎE", "✅ Có thể vào tiền"
    if score >= 6:
        return "🟡 TRUNG TÍNH", "⚠️ Chỉ nên test nhỏ"
    return "🔴 THỊ TRƯỜNG YẾU", "⛔ Không nên vào tiền"


# =========================================================
# NAV / BUY RECOMMENDATION
# =========================================================
def nav_suggestion(action: str, market_real: float) -> str:
    if market_real < 6:
        return "0%"

    if action == "MUA GÀ TĂNG TỐC":
        return "15-20% NAV" if market_real >= 8 else "5-10% NAV"

    if action == "MUA PULL ĐẸP":
        return "15-20% NAV" if market_real >= 8 else "5-10% NAV"

    if action == "MUA PULL VỪA":
        return "10-15% NAV" if market_real >= 8 else "5-10% NAV"

    if action == "TEST EARLY":
        return "5-10% NAV"

    if action == "MUA BREAK":
        return "15-20% NAV" if market_real >= 8 else "5-10% NAV"

    if action == "CANH ADD CP MẠNH":
        return "5-10% NAV"

    return "0%"


def buy_recommendation(row, market_real: float):
    price = row.get("price", np.nan)
    ema9_ = row.get("ema9", np.nan)
    group = str(row.get("group", ""))
    score = row.get("total_score", 0)
    dist = row.get("dist_from_ema9_pct", np.nan)
    warning = str(row.get("warning", ""))
    obv_ok = row.get("obv_status", "") == "🟢"
    slope_ = row.get("ema9_ma20_slope", np.nan)

    if market_real < 6:
        return "🔴", "KHÔNG MUA", "-", "0%", "Market REAL < 6"

    if "OBV gãy" in warning or "Giá dưới EMA9" in warning:
        return "🔴", "KHÔNG MUA", "-", "0%", "Trục tiền/giá xấu"

    if group == "GÀ TĂNG TỐC" and obv_ok and pd.notna(slope_) and slope_ > 2:
        action = "MUA GÀ TĂNG TỐC"
        return "🟢", action, f"{round(price * 0.99, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Slope mở mạnh + OBV giữ"

    if group == "PULL ĐẸP" and obv_ok:
        zone = f"{round(ema9_,0)} - {round(ema9_*1.01,0)}" if pd.notna(ema9_) else f"{price}"
        action = "MUA PULL ĐẸP"
        return "🟢", action, zone, nav_suggestion(action, market_real), "Pull sát EMA9, OBV còn xanh"

    if group == "PULL VỪA" and obv_ok:
        zone = f"{round(ema9_*0.99,0)} - {round(ema9_*1.01,0)}" if pd.notna(ema9_) else f"{price}"
        action = "MUA PULL VỪA"
        return "🟡", action, zone, nav_suggestion(action, market_real), "Pull vừa, chỉ mua thăm dò"

    if group == "MUA EARLY" and score >= 3 and obv_ok and pd.notna(dist) and abs(dist) <= 2.5:
        action = "TEST EARLY"
        return "🟡", action, f"{round(price*0.99,0)} - {round(price*1.01,0)}", nav_suggestion(action, market_real), "Early sạch, test nhỏ"

    if group == "MUA BREAK" and obv_ok:
        action = "MUA BREAK"
        return "🟢", action, f"{round(price,0)} - {round(price*1.01,0)}", nav_suggestion(action, market_real), "Break xác nhận, không đuổi quá xa"

    if group == "CP MẠNH" and score >= 5 and obv_ok:
        if pd.notna(dist) and dist > 4:
            return "🟡", "CHỜ PULL", f"Canh {round(ema9_,0)} - {round(ema9_*1.02,0)}", "0%", "CP mạnh nhưng xa EMA9"
        action = "CANH ADD CP MẠNH"
        return "🟡", action, f"{round(price*0.99,0)} - {round(price,0)}", nav_suggestion(action, market_real), "CP mạnh, có thể add nhỏ"

    return "🔴", "KHÔNG MUA", "-", "0%", "Chưa đủ điểm mua"


# =========================================================
# PORTFOLIO
# =========================================================
def parse_portfolio(text: str):
    rows = []
    if not text or text.strip() == "":
        return rows

    for line in text.strip().splitlines():
        try:
            parts = line.split(",")
            if len(parts) < 2:
                continue
            symbol = parts[0].strip().upper()
            buy = float(parts[1].strip())
            nav = float(parts[2].strip()) if len(parts) >= 3 else 0
            if symbol:
                rows.append((symbol, buy, nav))
        except Exception:
            continue

    return rows


def ga_state(row):
    score = row.get("total_score", 0)
    warning = str(row.get("warning", ""))
    group = str(row.get("group", ""))
    obv_ok = row.get("obv_status", "") == "🟢"
    slope_ = row.get("ema9_ma20_slope", np.nan)

    if group == "GÀ TĂNG TỐC" and obv_ok and pd.notna(slope_) and slope_ > 2:
        return "🟢 Gà tăng tốc"

    if score >= 6 and warning == "" and group in ["CP MẠNH", "PULL ĐẸP", "MUA BREAK"]:
        return "🟢 Gà chạy"

    if score >= 4 and obv_ok and "Giá dưới EMA9" not in warning:
        return "🟡 Gà nghỉ khỏe"

    if score >= 3 and "OBV gãy" not in warning:
        return "🟠 Gà yếu dần"

    return "🔴 Gà gãy"


def stop_engine(row):
    price = row.get("price", np.nan)
    ema9_ = row.get("ema9", np.nan)
    ma20_ = row.get("ma20", np.nan)
    state = ga_state(row)

    if "tăng tốc" in state or "chạy" in state:
        stop = ema9_ if pd.notna(ema9_) else price * 0.97
        note = "Trailing EMA9"

    elif "nghỉ" in state:
        stop = ma20_ if pd.notna(ma20_) else price * 0.95
        note = "Stop dưới MA20/nền nghỉ"

    elif "yếu" in state:
        stop = max(ma20_, price * 0.97) if pd.notna(ma20_) and pd.notna(price) else price * 0.97
        note = "Siết stop"

    else:
        stop = price
        note = "Gãy - bán chủ động"

    return safe_round(stop, 0), note


def hold_rules(row, market_real: float):
    checks = []
    checks.append(("Market REAL >= 6", market_real >= 6))
    checks.append(("Giá >= EMA9", row.get("price", 0) >= row.get("ema9", 10**18)))
    checks.append(("EMA9 > MA20", row.get("ema9", 0) > row.get("ma20", 10**18)))
    checks.append(("Slope >= 0", row.get("ema9_ma20_slope", -999) >= 0))
    checks.append(("RSI >= 55", row.get("rsi14", 0) >= 55))
    checks.append(("RSI slope >= 0", row.get("rsi_slope", -999) >= 0))
    checks.append(("OBV xanh", row.get("obv_status", "") == "🟢"))
    checks.append(("Không cảnh báo nặng", "OBV gãy" not in str(row.get("warning", ""))))

    passed = sum(ok for _, ok in checks)
    failed = [name for name, ok in checks if not ok]

    return passed, failed


def portfolio_action(row, market_real: float):
    state = ga_state(row)
    passed, failed = hold_rules(row, market_real)
    warning = str(row.get("warning", ""))

    if market_real < 6:
        if passed < 6 or "OBV gãy" in warning:
            return "🔴 GIẢM/BÁN - market yếu"
        return "🟡 GIỮ NHỎ - không add"

    if "OBV gãy" in warning and ("RSI yếu" in warning or "Giá dưới EMA9" in warning):
        return "🔴 BÁN / GIẢM MẠNH"

    if "tăng tốc" in state and passed >= 7:
        return "🟢 GIỮ CHẶT / CANH ADD"

    if "chạy" in state and passed >= 6:
        return "🟢 GIỮ CHẶT"

    if "nghỉ" in state and passed >= 5:
        return "🟡 GIỮ - không add"

    if "yếu" in state:
        return "🟠 GIẢM / SIẾT STOP"

    return "🔴 BÁN / LOẠI"


def build_portfolio_table(scan_df: pd.DataFrame, text: str, market_real: float) -> pd.DataFrame:
    rows = []

    for sym, buy, nav in parse_portfolio(text):
        sub = scan_df[scan_df["symbol"] == sym]

        if sub.empty:
            rows.append({
                "Mã": sym,
                "Giá mua": buy,
                "Giá hiện tại": np.nan,
                "% Lãi/Lỗ": np.nan,
                "%NAV": nav,
                "Điểm": np.nan,
                "Nhóm": "Không có data",
                "Trạng thái gà": "⚪ Không rõ",
                "Cảnh báo": "Không có trong scanner",
                "Stop Engine": np.nan,
                "Stop note": "-",
                "Hành động": "CHECK TAY",
            })
            continue

        r = sub.iloc[0]
        price = r["price"]
        pnl = (price - buy) / buy * 100 if buy else 0
        stop, note = stop_engine(r)
        passed, failed = hold_rules(r, market_real)

        rows.append({
            "Mã": sym,
            "Giá mua": buy,
            "Giá hiện tại": price,
            "% Lãi/Lỗ": safe_round(pnl, 2),
            "%NAV": nav,
            "Điểm": r["total_score"],
            "Nhóm": r["group"],
            "Slope": r["ema9_ma20_slope"],
            "Trạng thái gà": ga_state(r),
            "Checklist": f"{passed}/8",
            "Cảnh báo": r["warning"],
            "Stop Engine": stop,
            "Stop note": note,
            "Hành động": portfolio_action(r, market_real),
        })

    return pd.DataFrame(rows)


# =========================================================
# TOP PICKS
# =========================================================
def build_top_picks(df: pd.DataFrame, market_real: float) -> pd.DataFrame:
    picks = []

    for group_name, n in [
        ("GÀ TĂNG TỐC", 3),
        ("PULL ĐẸP", 2),
        ("MUA BREAK", 2),
        ("PULL VỪA", 2),
    ]:
        sub = df[df["group"] == group_name].head(n)

        for _, row in sub.iterrows():
            action = "MUA GÀ TĂNG TỐC" if group_name == "GÀ TĂNG TỐC" else group_name
            picks.append({
                "symbol": row["symbol"],
                "group": row["group"],
                "price": row["price"],
                "score": row["total_score"],
                "slope": row["ema9_ma20_slope"],
                "dist_from_ema9_pct": row["dist_from_ema9_pct"],
                "nav": nav_suggestion(action, market_real),
            })

    if not picks:
        return pd.DataFrame()

    return pd.DataFrame(picks).drop_duplicates(subset=["symbol"]).head(8)


# =========================================================
# UI CONTROLS
# =========================================================
left1, left2, left3, left4 = st.columns([1.1, 1.2, 1.1, 2.2])

with left1:
    scan_btn = st.button("🚀 SCAN", use_container_width=True)

with left2:
    auto_refresh = st.checkbox("Auto refresh 5 phút", value=True)

with left3:
    show_detail = st.checkbox("Hiện bảng tổng", value=False)

with left4:
    st.markdown(
        f"""
        <div class="small-note">
        Watchlist: <b>{len(WATCHLIST)}</b> mã &nbsp; | &nbsp;
        Update: <b>{datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</b>
        </div>
        """,
        unsafe_allow_html=True
    )

if "last_auto_refresh" not in st.session_state:
    st.session_state["last_auto_refresh"] = time.time()

if auto_refresh:
    now_ts = time.time()
    if now_ts - st.session_state["last_auto_refresh"] > 300:
        st.session_state["last_auto_refresh"] = now_ts
        st.cache_data.clear()
        st.rerun()

if scan_btn:
    st.cache_data.clear()


# =========================================================
# RUN SCAN
# =========================================================
with st.spinner("Đang quét dữ liệu..."):
    scan_df = run_scan(WATCHLIST)

if scan_df.empty:
    st.error("Không lấy được dữ liệu. Anh kiểm tra lại mạng hoặc nguồn Yahoo Finance.")
    st.stop()


# =========================================================
# MARKET OVERVIEW
# =========================================================
market_live = calc_market_live(scan_df)
market_real = calc_market_real(scan_df)
market_status, market_action = market_status_text(market_real)

st.markdown("## 📊 MARKET OVERVIEW")

m1, m2, m3 = st.columns([1, 1, 2])

with m1:
    st.metric("Market REAL", f"{market_real}/13")

with m2:
    st.metric("Market LIVE", f"{market_live}/13")

with m3:
    st.subheader(market_status)

if market_real < 6:
    st.error(market_action)
elif market_real < 8:
    st.warning(market_action)
else:
    st.success(market_action)

st.caption("REAL để ra quyết định. LIVE để quan sát trong phiên.")


# =========================================================
# BUY RECOMMENDATION
# =========================================================
buy_signal_cols = scan_df.apply(
    lambda r: pd.Series(
        buy_recommendation(r, market_real),
        index=["Đèn", "Khuyến nghị", "Vùng mua", "NAV gợi ý", "Lý do"]
    ),
    axis=1
)

scan_df = pd.concat([scan_df, buy_signal_cols], axis=1)

st.markdown("---")
st.markdown("## 🚦 KHUYẾN NGHỊ MUA")

buy_table = scan_df[scan_df["Đèn"].isin(["🟢", "🟡"])].copy()

buy_cols_show = [
    "symbol", "group", "price", "total_score",
    "ema9_ma20_slope", "slope_state",
    "rsi14", "obv_status", "dist_from_ema9_pct",
    "Đèn", "Khuyến nghị", "Vùng mua", "NAV gợi ý", "Lý do"
]

if buy_table.empty:
    st.info("Không có mã đủ điều kiện mua theo Market-first.")
else:
    st.dataframe(buy_table[buy_cols_show].head(30), use_container_width=True, height=420)


# =========================================================
# TOP PICKS
# =========================================================
st.markdown("---")
st.markdown("## 🎯 TOP VÀO TIỀN HÔM NAY")

top_df = build_top_picks(scan_df, market_real)

if top_df.empty:
    st.warning("Không có cổ phiếu đủ chuẩn để vào tiền.")
else:
    st.dataframe(top_df, use_container_width=True, height=300)


# =========================================================
# GROUP SUMMARY
# =========================================================
st.markdown("---")

GROUP_ORDER = [
    "GÀ TĂNG TỐC",
    "CP MẠNH",
    "MUA BREAK",
    "PULL ĐẸP",
    "PULL VỪA",
    "MUA EARLY",
    "TÍCH LŨY",
    "THEO DÕI",
]

sum_cols = st.columns(len(GROUP_ORDER))

for i, group_name in enumerate(GROUP_ORDER):
    cnt = int((scan_df["group"] == group_name).sum())
    with sum_cols[i]:
        st.metric(group_name, cnt)


# =========================================================
# DISPLAY GROUP TABLES
# =========================================================
DISPLAY_COLUMNS = [
    "symbol", "price", "E", "R", "O", "S", "total_score",
    "ema9_ma20_slope", "slope_state", "obv_status", "status"
]


def show_group_table(df: pd.DataFrame, group_name: str):
    sub = df[df["group"] == group_name].copy()

    if sub.empty:
        st.info("Không có mã")
        return

    if group_name in ["PULL ĐẸP", "PULL VỪA"]:
        cols = [
            "symbol", "price", "E", "R", "O", "S", "total_score",
            "dist_from_ema9_pct", "ema9_ma20_slope", "slope_state",
            "rsi_slope", "obv_status", "status"
        ]

    elif group_name == "MUA BREAK":
        cols = [
            "symbol", "price", "E", "R", "O", "S", "total_score",
            "breakout_ref", "ema9_ma20_slope", "slope_state",
            "obv_status", "status"
        ]

    else:
        cols = DISPLAY_COLUMNS

    cols = [c for c in cols if c in sub.columns]

    out = sub[cols].copy()
    out.index = range(len(out))

    st.dataframe(
        out,
        use_container_width=True,
        height=min(520, 80 + len(out) * 35)
    )


st.markdown("---")
st.markdown("## 🐔 BẢNG THEO NHÓM")

tabs = st.tabs(GROUP_ORDER)

for tab, group_name in zip(tabs, GROUP_ORDER):
    with tab:
        show_group_table(scan_df, group_name)


# =========================================================
# EARLY CLEAN
# =========================================================
st.markdown("---")
st.markdown("## 🐣 EARLY SẠCH – GOM HÀNG")

def filter_early_clean(df):
    rows = []

    for _, row in df.iterrows():
        rsi = row["rsi14"]
        rsi_slope = row["rsi_slope"]
        obv = row["obv"]
        obv_ema9 = row["obv_ema9"]
        price = row["price"]
        ema9_ = row["ema9"]
        vol = row["volume"]
        vol_ma20 = row["vol_ma20"]
        score = row["total_score"]
        slope_ = row["ema9_ma20_slope"]

        cond_rsi = pd.notna(rsi) and 45 <= rsi <= 58
        cond_slope_rsi = pd.notna(rsi_slope) and rsi_slope >= -0.5
        cond_obv = pd.notna(obv) and pd.notna(obv_ema9) and obv >= obv_ema9 * 0.98
        cond_price = pd.notna(price) and pd.notna(ema9_) and abs(price / ema9_ - 1) <= 0.035
        cond_vol = pd.notna(vol) and pd.notna(vol_ma20) and vol <= vol_ma20 * 1.2
        cond_score = score >= 3
        cond_slope = pd.notna(slope_) and slope_ >= -1

        if cond_rsi and cond_slope_rsi and cond_obv and cond_price and cond_vol and cond_score and cond_slope:
            rows.append(row)

    return pd.DataFrame(rows)


early_df = filter_early_clean(scan_df)

if early_df.empty:
    st.info("Không có mã EARLY sạch")
else:
    early_cols = [
        "symbol", "price", "rsi14", "rsi_slope",
        "ema9_ma20_slope", "slope_state",
        "E", "R", "O", "S", "total_score", "obv_status"
    ]

    early_cols = [c for c in early_cols if c in early_df.columns]
    out = early_df[early_cols].copy()
    out.index = range(len(out))

    st.dataframe(out, use_container_width=True, height=300)


# =========================================================
# GÀ TĂNG TỐC SPECIAL TABLE
# =========================================================
st.markdown("---")
st.markdown("## 🚀 GÀ TĂNG TỐC – BẢNG RIÊNG")

accel_df = scan_df[
    (scan_df["ema9_ma20_slope"] > 2)
    & (scan_df["S"] >= 1)
    & (scan_df["R"] >= 1)
    & (scan_df["O"] >= 1)
    & (scan_df["price"] >= scan_df["ema9"])
].copy()

if accel_df.empty:
    st.info("Chưa có mã gà tăng tốc rõ.")
else:
    accel_cols = [
        "symbol", "price", "group",
        "ema9", "ma20", "ema9_ma20_slope",
        "ema9_ma20_slope_change", "slope_state",
        "rsi14", "rsi_slope", "obv_status",
        "E", "R", "O", "S", "total_score",
        "warning"
    ]

    accel_cols = [c for c in accel_cols if c in accel_df.columns]
    accel_out = accel_df[accel_cols].copy()
    accel_out.index = range(len(accel_out))

    st.dataframe(accel_out, use_container_width=True, height=360)


# =========================================================
# PORTFOLIO MANAGEMENT
# =========================================================
st.markdown("---")
st.markdown("## 📊 QUẢN TRỊ DANH MỤC")

portfolio_text = st.text_area(
    "Anh nhập: Mã,Giá mua,%NAV",
    placeholder="BAF,36600,4.5\nGVR,33217,12\nVHM,144300,3.5",
    height=130,
    key="portfolio_input"
)

pf_df = build_portfolio_table(scan_df, portfolio_text, market_real)

if pf_df.empty:
    st.info("Chưa nhập danh mục.")
else:
    st.dataframe(pf_df, use_container_width=True, height=360)

    p1, p2, p3 = st.columns(3)

    pnl_series = pd.to_numeric(pf_df["% Lãi/Lỗ"], errors="coerce").dropna()
    nav_series = pd.to_numeric(pf_df["%NAV"], errors="coerce").fillna(0)

    p1.metric("Lãi/Lỗ TB", f"{safe_round(pnl_series.mean(), 2)}%" if len(pnl_series) else "-")
    p2.metric("Tổng NAV", f"{safe_round(nav_series.sum(), 2)}%")
    p3.metric("Số mã", len(pf_df))


# =========================================================
# DETAIL TABLE
# =========================================================
if show_detail:
    st.markdown("---")
    st.subheader("BẢNG TỔNG CHI TIẾT")

    detail_cols = [
        "symbol", "group", "price",
        "ema9", "ma20",
        "ema9_ma20_slope", "ema9_ma20_slope_change", "slope_state",
        "rsi14", "rsi_slope",
        "obv", "obv_ema9", "obv_status",
        "E", "R", "O", "S", "total_score",
        "dist_from_ema9_pct", "pull_label", "breakout_ref",
        "status", "warning"
    ]

    detail_cols = [c for c in detail_cols if c in scan_df.columns]

    detail_df = scan_df[detail_cols].copy()
    detail_df.index = range(len(detail_df))

    st.dataframe(detail_df, use_container_width=True, height=720)


# =========================================================
# FOOTER
# =========================================================
st.markdown("---")
st.caption(
    "Đọc nhanh: REAL = quyết định, LIVE = quan sát. "
    "S = điểm slope EMA9/MA20. "
    "Slope > 2% + OBV xanh + RSI tốt = gà tăng tốc. "
    "Market REAL ≥ 8 mới đánh mạnh."
)

