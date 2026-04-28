# =========================================================
# SCANNER GÀ CHIẾN V18.4 CLEAN FINAL
# Full rewrite - safe Yahoo parsing + Market REAL/LIVE + OBV
# =========================================================

import time
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# =========================================================
# PAGE
# =========================================================
st.set_page_config(
    page_title="Scanner Gà Chiến V25 PRO",
    page_icon="🐔",
    layout="wide",
)

st.title("🐔 Scanner Gà Chiến V25 PRO")
st.caption("Giữ nguyên V18.4 + thêm Khuyến nghị mua + Quản trị danh mục")


# =========================================================
# WATCHLIST
# =========================================================
WATCHLIST = sorted(list(set([
    # Dầu khí & Vận tải
    "PLX", "PVS", "PVD", "PVB", "PVC", "PVT", "BSR", "OIL", "GAS",
    "HAH", "VSC", "GMD", "VOS", "VTO", "ACV",

    # Xuất khẩu
    "MSH", "TNG", "TCM", "GIL", "VHC", "ANV", "FMC", "VCS", "PTB",

    # Điện & Hóa chất
    "BFC", "DCM", "DPM", "CSV", "DDV", "LAS", "BMP", "NTP", "AAA",
    "PAC", "MSR", "REE", "GEE", "GEX", "PC1", "HDG", "GEG", "NT2",
    "TV2", "DGC",

    # Đầu tư công & vật liệu
    "C4G", "FCN", "CII", "KSB", "DHA", "CTI", "HBC", "HPG", "HSG",
    "NKG", "VGS", "CTD", "HHV", "VCG",

    # Bán lẻ & chăn nuôi
    "MWG", "FRT", "DGW", "PET", "HAX", "MSN", "DBC", "HAG", "BAF",
    "MCH", "PAN", "VNM", "MML",

    # Ngân hàng & tài chính
    "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "SHB", "SSB",
    "STB", "HDB", "TPB", "VIB", "LPB", "OCB", "MSB", "NAB", "EIB",
    "VND", "SSI", "HCM", "SHS", "VIX", "BSI", "FTS", "TVS", "APS",
    "AGR", "VCI", "TCX", "VCK", "VPX", "ORS", "BVS", "VDS", "MBS",
    
    # Bất động sản khu công nghiệp
    "VGC", "SZC", "IDC", "KBC", "LHG", "IJC", "DTD", "BCM",

    # Cao su
    "GVR", "SIP", "DPR", "PHR" , "DRI",
    
    # Công nghệ & logistic
    "FPT", "VGI", "CTR", "VTP", "CMG", "ELC", "FOX",

    # Cổ phiếu lẻ
    "HVN", "VJC", "IMP", "BVH", "SBT", "LSS", "PNJ", "TLG", "DHT",
    "TNH", "VSC", "YEG",

    # BĐS / mã hay xem
    "VIC", "VHM", "VRE", "NVL", "DXG", "DXS", "DIG", "CEO", "TCH",
    "KBC", "IJC", "EVF", "LHG", "SAB"
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
# HELPERS
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


def nav_suggestion(group_name: str, market_real: float) -> str:
    if market_real < 6:
        if group_name == "PULL ĐẸP":
            return "10% NAV"
        if group_name == "PULL VỪA":
            return "5-10% NAV"
        if group_name == "MUA BREAK":
            return "5% NAV"
        return "0-5% NAV"

    if market_real < 8:
        if group_name == "PULL ĐẸP":
            return "20% NAV"
        if group_name == "PULL VỪA":
            return "10-15% NAV"
        if group_name == "MUA BREAK":
            return "10% NAV"
        return "5-10% NAV"

    if group_name == "PULL ĐẸP":
        return "25-30% NAV"
    if group_name == "PULL VỪA":
        return "10-15% NAV"
    if group_name == "MUA BREAK":
        return "15-20% NAV"
    return "10% NAV"


# =========================================================
# DATA
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


def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()

    x["ema9"] = ema(x["close"], 9)
    x["ma20"] = sma(x["close"], 20)

    x["rsi14"] = calc_rsi(x["close"], 14)
    x["rsi_slope"] = x["rsi14"].diff()

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


def build_warning(close_, ema9_, rsi_, rsi_slope_, obv_, obv_ema9_, pull_label):
    warnings = []

    if pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ < obv_ema9_:
        warnings.append("OBV gãy")

    if pd.notna(rsi_) and rsi_ < 55:
        warnings.append("RSI yếu")

    if pd.notna(rsi_slope_) and rsi_slope_ < 0:
        warnings.append("RSI chững")

    if pd.notna(close_) and pd.notna(ema9_) and close_ < ema9_:
        warnings.append("Giá dưới EMA9")

    if pull_label == "PULL XẤU":
        warnings.append("Pull xấu")

    return " | ".join(dict.fromkeys(warnings))


def build_status(total_score, warning, group_name):
    if group_name == "PULL ĐẸP":
        return "🟢"
    if total_score >= 5 and warning == "":
        return "🟢"
    if total_score >= 3:
        return "🟡"
    return "🔴"


# =========================================================
# GROUP
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
    dist_from_ema9 = row["dist_from_ema9_pct"]
    breakout_ref = row["breakout_ref"]
    pull_label = row["pull_label"]

    leader = (
        total >= 5
        and e >= 1
        and o >= 1
        and pd.notna(price)
        and pd.notna(ema9_)
        and price >= ema9_ * 0.97
    )

    if not leader:
        if total <= 1:
            return "THEO DÕI"
        if total == 2:
            return "TÍCH LŨY"
        return "MUA EARLY"

    if (
        pull_label == "PULL ĐẸP"
        and pd.notna(price)
        and pd.notna(ma20_)
        and price >= ma20_
    ):
        return "PULL ĐẸP"

    if (
        pull_label == "PULL VỪA"
        and pd.notna(price)
        and pd.notna(ma20_)
        and price >= ma20_
    ):
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
    if len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = to_float(last["close"])
    ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])
    ema9_prev = to_float(prev["ema9"])

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
    # =========================
# 🌸 NỞ HOA + DIST BONUS
# =========================

# ===== NỞ HOA =====
no_hoa = (
    pd.notna(price) and pd.notna(ema9_) and pd.notna(ma20_) and
    price > ema9_ > ma20_ and
    pd.notna(rsi_) and rsi_ > 55 and
    pd.notna(rsi_slope_) and rsi_slope_ >= 0 and
    pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ >= obv_ema9_
)

# ===== BONUS DIST =====
bonus_dist = 0
if pd.notna(dist_from_ema9):
    if 4 <= dist_from_ema9 <= 7:
        bonus_dist = 1
    elif 3 <= dist_from_ema9 < 4:
        bonus_dist = 0.5
    elif 7 < dist_from_ema9 <= 8:
        bonus_dist = 0.5

total_score = E + R + O + bonus_dist

pull_label = classify_pull_label(
        dist_from_ema9=dist_from_ema9,
        rsi_=rsi_,
        rsi_slope_=rsi_slope_,
        obv_=obv_,
        obv_ema9_=obv_ema9_,
    )

    if pd.notna(obv_) and pd.notna(obv_ema9_) and obv_ >= obv_ema9_:
        obv_status = "🟢"
    else:
        obv_status = "🔴"

    row = {
        "symbol": symbol,
        "price": round(price, 0) if pd.notna(price) else np.nan,
        "ema9": round(ema9_, 2) if pd.notna(ema9_) else np.nan,
        "ma20": round(ma20_, 2) if pd.notna(ma20_) else np.nan,
        "rsi14": round(rsi_, 2) if pd.notna(rsi_) else np.nan,
        "rsi_slope": round(rsi_slope_, 2) if pd.notna(rsi_slope_) else np.nan,
        "obv": round(obv_, 0) if pd.notna(obv_) else np.nan,
        "obv_ema9": round(obv_ema9_, 0) if pd.notna(obv_ema9_) else np.nan,
        "obv_status": obv_status,
        "volume": round(vol_, 0) if pd.notna(vol_) else np.nan,
        "vol_ma20": round(vol_ma20_, 0) if pd.notna(vol_ma20_) else np.nan,
        "breakout_ref": round(breakout_ref, 2) if pd.notna(breakout_ref) else np.nan,
        "dist_from_ema9_pct": round(dist_from_ema9, 2) if pd.notna(dist_from_ema9) else np.nan,
        "pull_label": pull_label,
        "E": E,
        "R": R,
        "O": O,
        "total_score": total_score,
    }

    row["group"] = classify_group(row)
    row["warning"] = build_warning(price, ema9_, rsi_, rsi_slope_, obv_, obv_ema9_, pull_label)
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
        "PULL ĐẸP": 1,
        "MUA BREAK": 2,
        "PULL VỪA": 3,
        "CP MẠNH": 4,
        "MUA EARLY": 5,
        "TÍCH LŨY": 6,
        "THEO DÕI": 7,
    }
    df["group_rank"] = df["group"].map(group_priority).fillna(99)

    df = df.sort_values(
        by=["group_rank", "total_score", "E", "O", "R", "dist_from_ema9_pct"],
        ascending=[True, False, False, False, False, True],
    ).reset_index(drop=True)

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

    strong = len(df[df["group"] == "CP MẠNH"])
    breakout = len(df[df["group"] == "MUA BREAK"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])

    strong_score = min(strong / 10, 1) * 2.5
    breakout_score = min(breakout / 8, 1) * 1.5
    pull_score = min(pull_good / 6, 1) * 1.0

    score = (
        e_ratio * 3
        + r_ratio * 3
        + o_ratio * 2
        + strong_score
        + breakout_score
        + pull_score
    )

    return round(score, 1)


def calc_market_real(df: pd.DataFrame) -> float:
    total = len(df)
    if total == 0:
        return 0.0

    # REAL: giảm trọng số pull/break ngắn hạn, tăng độ rộng các trục
    e_ratio = len(df[df["E"] >= 1]) / total
    r_ratio = len(df[df["R"] >= 1]) / total
    o_ratio = len(df[df["O"] >= 1]) / total

    strong = len(df[df["group"] == "CP MẠNH"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])
    pull_ok = len(df[df["group"] == "PULL VỪA"])

    score = (
        e_ratio * 4
        + r_ratio * 3
        + o_ratio * 3
        + min(strong / 12, 1) * 2
        + min((pull_good + pull_ok) / 12, 1) * 1
    )

    return round(min(score, 13), 1)


def market_status_text(score: float) -> tuple[str, str]:
    if score >= 8:
        return "🟢 THỊ TRƯỜNG KHỎE", "✅ Có thể vào tiền"
    if score >= 6:
        return "🟡 TRUNG TÍNH", "⚠️ Chỉ nên test nhỏ"
    return "🔴 THỊ TRƯỜNG YẾU", "⛔ Không nên vào tiền"



# =========================================================
# V25 BUY SIGNAL + PORTFOLIO HELPERS
# =========================================================
def v25_nav_suggestion(action: str, market_real: float) -> str:
    if market_real < 6:
        return "0%"
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

def v25_buy_recommendation(row, market_real: float):
    price = row.get("price", np.nan)
    ema9_ = row.get("ema9", np.nan)
    group = str(row.get("group", ""))
    score = row.get("total_score", 0)
    dist = row.get("dist_from_ema9_pct", np.nan)
    warning = str(row.get("warning", ""))
    obv_ok = row.get("obv_status", "") == "🟢"
    if market_real < 6:
        return "🔴", "KHÔNG MUA", "-", "0%", "Market REAL < 6"
    if "OBV gãy" in warning or "Giá dưới EMA9" in warning:
        return "🔴", "KHÔNG MUA", "-", "0%", "Trục tiền/giá xấu"
    if group == "PULL ĐẸP" and obv_ok:
        zone = f"{round(ema9_,0)} - {round(ema9_*1.01,0)}" if pd.notna(ema9_) else f"{price}"
        action = "MUA PULL ĐẸP"
        return "🟢", action, zone, v25_nav_suggestion(action, market_real), "Pull sát EMA9, OBV còn xanh"
    if group == "PULL VỪA" and obv_ok:
        zone = f"{round(ema9_*0.99,0)} - {round(ema9_*1.01,0)}" if pd.notna(ema9_) else f"{price}"
        action = "MUA PULL VỪA"
        return "🟡", action, zone, v25_nav_suggestion(action, market_real), "Pull vừa, chỉ mua thăm dò"
    if group == "MUA EARLY" and score >= 3 and obv_ok and pd.notna(dist) and abs(dist) <= 2.5:
        action = "TEST EARLY"
        return "🟡", action, f"{round(price*0.99,0)} - {round(price*1.01,0)}", v25_nav_suggestion(action, market_real), "Early sạch, test nhỏ"
    if group == "MUA BREAK" and obv_ok:
        action = "MUA BREAK"
        return "🟢", action, f"{round(price,0)} - {round(price*1.01,0)}", v25_nav_suggestion(action, market_real), "Break xác nhận, không đuổi quá xa"
    if group == "CP MẠNH" and score >= 5 and obv_ok:
        if pd.notna(dist) and dist > 4:
            return "🟡", "CHỜ PULL", f"Canh {round(ema9_,0)} - {round(ema9_*1.02,0)}", "0%", "CP mạnh nhưng xa EMA9"
        action = "CANH ADD CP MẠNH"
        return "🟡", action, f"{round(price*0.99,0)} - {round(price,0)}", v25_nav_suggestion(action, market_real), "CP mạnh, có thể add nhỏ"
    return "🔴", "KHÔNG MUA", "-", "0%", "Chưa đủ điểm mua"

def v25_parse_portfolio(text: str):
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

def v25_ga_state(row):
    score = row.get("total_score", 0)
    warning = str(row.get("warning", ""))
    group = str(row.get("group", ""))
    obv_ok = row.get("obv_status", "") == "🟢"
    if score >= 5 and warning == "" and group in ["CP MẠNH", "PULL ĐẸP", "MUA BREAK"]:
        return "🟢 Gà chạy"
    if score >= 4 and obv_ok and "Giá dưới EMA9" not in warning:
        return "🟡 Gà nghỉ khỏe"
    if score >= 3 and "OBV gãy" not in warning:
        return "🟠 Gà yếu dần"
    return "🔴 Gà gãy"

def v25_stop_engine(row):
    price = row.get("price", np.nan)
    ema9_ = row.get("ema9", np.nan)
    ma20_ = row.get("ma20", np.nan)
    state = v25_ga_state(row)
    if "Gà chạy" in state:
        stop = ema9_ if pd.notna(ema9_) else price * 0.97
        note = "Trailing EMA9"
    elif "Gà nghỉ" in state:
        stop = ma20_ if pd.notna(ma20_) else price * 0.95
        note = "Stop dưới MA20/nền nghỉ"
    elif "Yếu" in state:
        stop = max(ma20_, price * 0.97) if pd.notna(ma20_) and pd.notna(price) else price * 0.97
        note = "Siết stop"
    else:
        stop = price
        note = "Gãy - bán chủ động"
    return round(stop, 0) if pd.notna(stop) else np.nan, note

def v25_hold_rules(row, market_real: float):
    checks = []
    checks.append(("Market REAL >= 6", market_real >= 6))
    checks.append(("Giá >= EMA9", row.get("price", 0) >= row.get("ema9", 10**18)))
    checks.append(("EMA9 > MA20", row.get("ema9", 0) > row.get("ma20", 10**18)))
    checks.append(("RSI >= 55", row.get("rsi14", 0) >= 55))
    checks.append(("RSI slope >= 0", row.get("rsi_slope", -999) >= 0))
    checks.append(("OBV xanh", row.get("obv_status", "") == "🟢"))
    checks.append(("Không cảnh báo nặng", "OBV gãy" not in str(row.get("warning", ""))))
    passed = sum(ok for _, ok in checks)
    failed = [name for name, ok in checks if not ok]
    return passed, failed

def v25_portfolio_action(row, market_real: float):
    state = v25_ga_state(row)
    passed, failed = v25_hold_rules(row, market_real)
    warning = str(row.get("warning", ""))
    if market_real < 6:
        if passed < 6 or "OBV gãy" in warning:
            return "🔴 GIẢM/BÁN - market yếu"
        return "🟡 GIỮ NHỎ - không add"
    if "OBV gãy" in warning and ("RSI yếu" in warning or "Giá dưới EMA9" in warning):
        return "🔴 BÁN / GIẢM MẠNH"
    if "Gà chạy" in state and passed >= 6:
        return "🟢 GIỮ CHẶT / CANH ADD"
    if "Gà nghỉ" in state and passed >= 5:
        return "🟡 GIỮ - không add"
    if "Yếu" in state:
        return "🟠 GIẢM / SIẾT STOP"
    return "🔴 BÁN / LOẠI"

def v25_build_portfolio_table(scan_df: pd.DataFrame, text: str, market_real: float) -> pd.DataFrame:
    rows = []
    for sym, buy, nav in v25_parse_portfolio(text):
        sub = scan_df[scan_df["symbol"] == sym]
        if sub.empty:
            rows.append({"Mã": sym, "Giá mua": buy, "Giá hiện tại": np.nan, "% Lãi/Lỗ": np.nan, "%NAV": nav, "Điểm": np.nan, "Nhóm": "Không có data", "Trạng thái gà": "⚪ Không rõ", "7 điều giữ": "-", "Cảnh báo": "Không có trong scanner", "Stop Engine": np.nan, "Stop note": "-", "Hành động": "CHECK TAY"})
            continue
        r = sub.iloc[0]
        price = r["price"]
        pnl = (price - buy) / buy * 100 if buy else 0
        stop, note = v25_stop_engine(r)
        passed, failed = v25_hold_rules(r, market_real)
        rows.append({"Mã": sym, "Giá mua": buy, "Giá hiện tại": price, "% Lãi/Lỗ": round(pnl, 2), "%NAV": nav, "Điểm": r["total_score"], "Nhóm": r["group"], "Trạng thái gà": v25_ga_state(r), "7 điều giữ": f"{passed}/7", "Cảnh báo": r["warning"], "Stop Engine": stop, "Stop note": note, "Hành động": v25_portfolio_action(r, market_real)})
    return pd.DataFrame(rows)

# =========================================================
# TOP PICKS
# =========================================================
def build_top_picks(df: pd.DataFrame, market_real: float) -> pd.DataFrame:
    picks = []

    pull_good = df[df["group"] == "PULL ĐẸP"].head(2)
    for _, row in pull_good.iterrows():
        picks.append({
            "symbol": row["symbol"],
            "group": row["group"],
            "price": row["price"],
            "score": row["total_score"],
            "dist_from_ema9_pct": row["dist_from_ema9_pct"],
            "nav": nav_suggestion(row["group"], market_real),
        })

    pull_ok = df[df["group"] == "PULL VỪA"].head(2)
    for _, row in pull_ok.iterrows():
        picks.append({
            "symbol": row["symbol"],
            "group": row["group"],
            "price": row["price"],
            "score": row["total_score"],
            "dist_from_ema9_pct": row["dist_from_ema9_pct"],
            "nav": nav_suggestion(row["group"], market_real),
        })

    breaks = df[df["group"] == "MUA BREAK"].head(1)
    for _, row in breaks.iterrows():
        picks.append({
            "symbol": row["symbol"],
            "group": row["group"],
            "price": row["price"],
            "score": row["total_score"],
            "dist_from_ema9_pct": row["dist_from_ema9_pct"],
            "nav": nav_suggestion(row["group"], market_real),
        })

    if not picks:
        return pd.DataFrame()

    return pd.DataFrame(picks).drop_duplicates(subset=["symbol"]).head(4)


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
# V25 - KHUYẾN NGHỊ MUA
# =========================================================
buy_signal_cols = scan_df.apply(
    lambda r: pd.Series(
        v25_buy_recommendation(r, market_real),
        index=["Đèn", "Khuyến nghị", "Vùng mua", "NAV gợi ý", "Lý do"]
    ),
    axis=1
)
scan_df = pd.concat([scan_df, buy_signal_cols], axis=1)

st.markdown("---")
st.markdown("## 🚦 KHUYẾN NGHỊ MUA V25")

buy_table = scan_df[scan_df["Đèn"].isin(["🟢", "🟡"])].copy()

buy_cols_show = ["symbol", "group", "price", "total_score", "rsi14", "obv_status", "dist_from_ema9_pct", "Đèn", "Khuyến nghị", "Vùng mua", "NAV gợi ý", "Lý do"]

if buy_table.empty:
    st.info("Không có mã đủ điều kiện mua theo Market-first.")
else:
    st.dataframe(buy_table[buy_cols_show].head(20), use_container_width=True, height=420)




# =========================================================
# V25 BUY SIGNAL + PORTFOLIO HELPERS
# =========================================================
def v25_nav_suggestion(action: str, market_real: float) -> str:
    if market_real < 6:
        return "0%"
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

def v25_buy_recommendation(row, market_real: float):
    price = row.get("price", np.nan)
    ema9_ = row.get("ema9", np.nan)
    group = str(row.get("group", ""))
    score = row.get("total_score", 0)
    dist = row.get("dist_from_ema9_pct", np.nan)
    warning = str(row.get("warning", ""))
    obv_ok = row.get("obv_status", "") == "🟢"
    if market_real < 6:
        return "🔴", "KHÔNG MUA", "-", "0%", "Market REAL < 6"
    if "OBV gãy" in warning or "Giá dưới EMA9" in warning:
        return "🔴", "KHÔNG MUA", "-", "0%", "Trục tiền/giá xấu"
    if group == "PULL ĐẸP" and obv_ok:
        zone = f"{round(ema9_,0)} - {round(ema9_*1.01,0)}" if pd.notna(ema9_) else f"{price}"
        action = "MUA PULL ĐẸP"
        return "🟢", action, zone, v25_nav_suggestion(action, market_real), "Pull sát EMA9, OBV còn xanh"
    if group == "PULL VỪA" and obv_ok:
        zone = f"{round(ema9_*0.99,0)} - {round(ema9_*1.01,0)}" if pd.notna(ema9_) else f"{price}"
        action = "MUA PULL VỪA"
        return "🟡", action, zone, v25_nav_suggestion(action, market_real), "Pull vừa, chỉ mua thăm dò"
    if group == "MUA EARLY" and score >= 3 and obv_ok and pd.notna(dist) and abs(dist) <= 2.5:
        action = "TEST EARLY"
        return "🟡", action, f"{round(price*0.99,0)} - {round(price*1.01,0)}", v25_nav_suggestion(action, market_real), "Early sạch, test nhỏ"
    if group == "MUA BREAK" and obv_ok:
        action = "MUA BREAK"
        return "🟢", action, f"{round(price,0)} - {round(price*1.01,0)}", v25_nav_suggestion(action, market_real), "Break xác nhận, không đuổi quá xa"
    if group == "CP MẠNH" and score >= 5 and obv_ok:
        if pd.notna(dist) and dist > 4:
            return "🟡", "CHỜ PULL", f"Canh {round(ema9_,0)} - {round(ema9_*1.02,0)}", "0%", "CP mạnh nhưng xa EMA9"
        action = "CANH ADD CP MẠNH"
        return "🟡", action, f"{round(price*0.99,0)} - {round(price,0)}", v25_nav_suggestion(action, market_real), "CP mạnh, có thể add nhỏ"
    return "🔴", "KHÔNG MUA", "-", "0%", "Chưa đủ điểm mua"

def v25_parse_portfolio(text: str):
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

def v25_ga_state(row):
    score = row.get("total_score", 0)
    warning = str(row.get("warning", ""))
    group = str(row.get("group", ""))
    obv_ok = row.get("obv_status", "") == "🟢"
    if score >= 5 and warning == "" and group in ["CP MẠNH", "PULL ĐẸP", "MUA BREAK"]:
        return "🟢 Gà chạy"
    if score >= 4 and obv_ok and "Giá dưới EMA9" not in warning:
        return "🟡 Gà nghỉ khỏe"
    if score >= 3 and "OBV gãy" not in warning:
        return "🟠 Gà yếu dần"
    return "🔴 Gà gãy"

def v25_stop_engine(row):
    price = row.get("price", np.nan)
    ema9_ = row.get("ema9", np.nan)
    ma20_ = row.get("ma20", np.nan)
    state = v25_ga_state(row)
    if "Gà chạy" in state:
        stop = ema9_ if pd.notna(ema9_) else price * 0.97
        note = "Trailing EMA9"
    elif "Gà nghỉ" in state:
        stop = ma20_ if pd.notna(ma20_) else price * 0.95
        note = "Stop dưới MA20/nền nghỉ"
    elif "Yếu" in state:
        stop = max(ma20_, price * 0.97) if pd.notna(ma20_) and pd.notna(price) else price * 0.97
        note = "Siết stop"
    else:
        stop = price
        note = "Gãy - bán chủ động"
    return round(stop, 0) if pd.notna(stop) else np.nan, note

def v25_hold_rules(row, market_real: float):
    checks = []
    checks.append(("Market REAL >= 6", market_real >= 6))
    checks.append(("Giá >= EMA9", row.get("price", 0) >= row.get("ema9", 10**18)))
    checks.append(("EMA9 > MA20", row.get("ema9", 0) > row.get("ma20", 10**18)))
    checks.append(("RSI >= 55", row.get("rsi14", 0) >= 55))
    checks.append(("RSI slope >= 0", row.get("rsi_slope", -999) >= 0))
    checks.append(("OBV xanh", row.get("obv_status", "") == "🟢"))
    checks.append(("Không cảnh báo nặng", "OBV gãy" not in str(row.get("warning", ""))))
    passed = sum(ok for _, ok in checks)
    failed = [name for name, ok in checks if not ok]
    return passed, failed

def v25_portfolio_action(row, market_real: float):
    state = v25_ga_state(row)
    passed, failed = v25_hold_rules(row, market_real)
    warning = str(row.get("warning", ""))
    if market_real < 6:
        if passed < 6 or "OBV gãy" in warning:
            return "🔴 GIẢM/BÁN - market yếu"
        return "🟡 GIỮ NHỎ - không add"
    if "OBV gãy" in warning and ("RSI yếu" in warning or "Giá dưới EMA9" in warning):
        return "🔴 BÁN / GIẢM MẠNH"
    if "Gà chạy" in state and passed >= 6:
        return "🟢 GIỮ CHẶT / CANH ADD"
    if "Gà nghỉ" in state and passed >= 5:
        return "🟡 GIỮ - không add"
    if "Yếu" in state:
        return "🟠 GIẢM / SIẾT STOP"
    return "🔴 BÁN / LOẠI"

def v25_build_portfolio_table(scan_df: pd.DataFrame, text: str, market_real: float) -> pd.DataFrame:
    rows = []
    for sym, buy, nav in v25_parse_portfolio(text):
        sub = scan_df[scan_df["symbol"] == sym]
        if sub.empty:
            rows.append({"Mã": sym, "Giá mua": buy, "Giá hiện tại": np.nan, "% Lãi/Lỗ": np.nan, "%NAV": nav, "Điểm": np.nan, "Nhóm": "Không có data", "Trạng thái gà": "⚪ Không rõ", "7 điều giữ": "-", "Cảnh báo": "Không có trong scanner", "Stop Engine": np.nan, "Stop note": "-", "Hành động": "CHECK TAY"})
            continue
        r = sub.iloc[0]
        price = r["price"]
        pnl = (price - buy) / buy * 100 if buy else 0
        stop, note = v25_stop_engine(r)
        passed, failed = v25_hold_rules(r, market_real)
        rows.append({"Mã": sym, "Giá mua": buy, "Giá hiện tại": price, "% Lãi/Lỗ": round(pnl, 2), "%NAV": nav, "Điểm": r["total_score"], "Nhóm": r["group"], "Trạng thái gà": v25_ga_state(r), "7 điều giữ": f"{passed}/7", "Cảnh báo": r["warning"], "Stop Engine": stop, "Stop note": note, "Hành động": v25_portfolio_action(r, market_real)})
    return pd.DataFrame(rows)

# =========================================================
# TOP PICKS
# =========================================================
st.markdown("## 🎯 TOP VÀO TIỀN HÔM NAY")

top_df = build_top_picks(scan_df, market_real)

if top_df.empty:
    st.warning("Không có cổ phiếu đủ chuẩn để vào tiền.")
else:
    for _, row in top_df.iterrows():
        st.markdown(
            f"""
**{row['symbol']}** — {row['group']}  
Giá: **{row['price']}** | Score: **{row['score']}** | Dist EMA9: **{row['dist_from_ema9_pct']}%** | Gợi ý NAV: **{row['nav']}**
"""
        )


# =========================================================
# SUMMARY
# =========================================================
GROUP_ORDER = ["CP MẠNH", "MUA BREAK", "PULL ĐẸP", "PULL VỪA", "MUA EARLY", "TÍCH LŨY", "THEO DÕI"]

sum_cols = st.columns(len(GROUP_ORDER))
for i, group_name in enumerate(GROUP_ORDER):
    cnt = int((scan_df["group"] == group_name).sum())
    with sum_cols[i]:
        st.metric(group_name, cnt)


# =========================================================
# DISPLAY
# =========================================================
DISPLAY_COLUMNS = ["symbol", "price", "E", "R", "O", "total_score", "obv_status", "status"]

def show_group_table(df: pd.DataFrame, group_name: str):
    sub = df[df["group"] == group_name].copy()
    if sub.empty:
        st.info("Không có mã")
        return

    if group_name in ["PULL ĐẸP", "PULL VỪA"]:
        cols = [
            "symbol", "price", "E", "R", "O", "total_score",
            "dist_from_ema9_pct", "rsi_slope", "obv_status", "status"
        ]
    elif group_name == "MUA BREAK":
        cols = [
            "symbol", "price", "E", "R", "O", "total_score",
            "breakout_ref", "obv_status", "status"
        ]
    else:
        cols = DISPLAY_COLUMNS

    out = sub[cols].copy()
    out.index = range(len(out))

    st.dataframe(
        out,
        use_container_width=True,
        height=min(520, 80 + len(out) * 35)
    )
# =========================================================
# EARLY SẠCH – GOM HÀNG
# =========================================================

st.markdown("---")
st.markdown("🐣 EARLY SẠCH – GOM HÀNG (STAGE 1)")

def filter_early_clean(df):
    rows = []

    for _, row in df.iterrows():
        rsi = row["rsi14"]
        rsi_slope = row["rsi_slope"]
        obv = row["obv"]
        obv_ema9 = row["obv_ema9"]
        price = row["price"]
        ema9 = row["ema9"]
        vol = row["volume"]
        vol_ma20 = row["vol_ma20"]
        score = row["total_score"]

        if not pd.notna(rsi):
            continue

        # ===== ĐIỀU KIỆN =====
        cond_rsi = 45 <= rsi <= 55
        cond_slope = pd.notna(rsi_slope) and rsi_slope >= -0.5
        cond_obv = pd.notna(obv) and pd.notna(obv_ema9) and obv >= obv_ema9 * 0.98
        cond_price = pd.notna(price) and pd.notna(ema9) and abs(price / ema9 - 1) <= 0.03
        cond_vol = pd.notna(vol) and pd.notna(vol_ma20) and vol <= vol_ma20
        cond_score = score >= 3

        if (
            cond_rsi
            and cond_slope
            and cond_obv
            and cond_price
            and cond_vol
            and cond_score
        ):
            rows.append(row)

    return pd.DataFrame(rows)


early_df = filter_early_clean(scan_df)

if early_df.empty:
    st.info("Không có mã EARLY sạch")
else:
    out = early_df[[
        "symbol", "price", "rsi14", "rsi_slope",
        "E", "R", "O", "total_score", "obv_status"
    ]].copy()

    out.index = range(len(out))

    st.dataframe(out, use_container_width=True, height=300)
# =========================================================
# >>> THÊM SAU PHẦN TOP PICKS (KHÔNG SỬA CODE CŨ)
# =========================================================
# =========================================================
# TRIGGER VÀO TIỀN – NẾN XANH ĐẦU TIÊN
# =========================================================

st.markdown("---")
st.markdown("🎯 TRIGGER VÀO TIỀN – NẾN XANH ĐẦU TIÊN")

def check_first_green_trigger(symbol: str):
    raw = download_symbol_data(symbol)
    if raw.empty or len(raw) < 40:
        return None

    df = build_indicators(raw)
    if len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    open_ = to_float(last["open"])
    close_ = to_float(last["close"])
    volume_ = to_float(last["volume"])
    prev_volume = to_float(prev["volume"])

    rsi_ = to_float(last["rsi14"])
    rsi_prev = to_float(prev["rsi14"])
    rsi_slope = to_float(last["rsi_slope"])

    obv_ = to_float(last["obv"])
    obv_prev = to_float(prev["obv"])
    obv_ema9 = to_float(last["obv_ema9"])

    ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])

    green_candle = close_ > open_
    vol_up = volume_ > prev_volume
    rsi_turn = rsi_ > rsi_prev and rsi_slope > 0
    obv_turn = obv_ > obv_prev and obv_ >= obv_ema9
    price_near_ema9 = abs(close_ / ema9_ - 1) <= 0.04 if ema9_ else False
    not_overheat = rsi_ <= 60

    trigger_score = sum([
        green_candle,
        vol_up,
        rsi_turn,
        obv_turn,
        price_near_ema9,
        not_overheat
    ])

    if trigger_score >= 5:
        return {
            "symbol": symbol,
            "price": round(close_, 0),
            "rsi14": round(rsi_, 2),
            "rsi_slope": round(rsi_slope, 2),
            "volume": round(volume_, 0),
            "prev_volume": round(prev_volume, 0),
            "obv_status": "🟢" if obv_ >= obv_ema9 else "🔴",
            "trigger_score": trigger_score,
            "no_hoa": no_hoa,
            "action": "TEST 5-10% NAV"
        }

    return None


def build_trigger_table(early_df):
    rows = []

    if early_df.empty:
        return pd.DataFrame()

    for symbol in early_df["symbol"].tolist():
        try:
            item = check_first_green_trigger(symbol)
            if item is not None:
                rows.append(item)
        except Exception:
            continue

    return pd.DataFrame(rows)


trigger_df = build_trigger_table(early_df)

if trigger_df.empty:
    st.info("Chưa có mã kích hoạt trigger vào tiền")
else:
    st.dataframe(
        trigger_df,
        use_container_width=True,
        height=300
    )
 # =========================
# 🔵 PULL TRIGGER TABLE
# =========================

pull_rows = []

for symbol in early_df["symbol"].tolist():
    try:
        item = check_pull_trigger(symbol)
        if item is not None:
            pull_rows.append(item)
    except:
        continue

pull_df = pd.DataFrame(pull_rows)

if pull_df.empty:
    st.info("Chưa có mã PULL đẹp")
else:
    st.markdown("## 🔵 PULL TRIGGER")
    st.dataframe(
        pull_df,
        use_container_width=True,
        height=300
    )  
# =========================
# 🔴 BREAK TRIGGER TABLE
# =========================

break_rows = []

for symbol in early_df["symbol"].tolist():
    try:
        item = check_break_trigger(symbol)
        if item is not None:
            break_rows.append(item)
    except:
        continue

break_df = pd.DataFrame(break_rows)

if break_df.empty:
    st.info("Chưa có mã BREAK đẹp")
else:
    st.markdown("## 🔴 BREAK TRIGGER")
    st.dataframe(
        break_df,
        use_container_width=True,
        height=300
    )    
# =========================
# 🔵 PULL TRIGGER (CHUẨN HỆ THỐNG)
# =========================

def check_pull_trigger(symbol: str):
    raw = download_symbol_data(symbol)
    if raw.empty or len(raw) < 40:
        return None

    df = build_indicators(raw)
    if len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close_ = to_float(last["close"])
    volume_ = to_float(last["volume"])
    prev_volume = to_float(prev["volume"])

    rsi_ = to_float(last["rsi14"])
    obv_ = to_float(last["obv"])
    obv_ema9 = to_float(last["obv_ema9"])

    ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])

    # ===== LOGIC PULL =====
    near_ema9 = abs(close_ / ema9_ - 1) <= 0.03 if ema9_ else False
    near_ma20 = abs(close_ / ma20_ - 1) <= 0.04 if ma20_ else False

    vol_dry = volume_ < prev_volume
    rsi_ok = rsi_ > 50
    obv_ok = obv_ >= obv_ema9

    pull_score = sum([
        near_ema9 or near_ma20,
        vol_dry,
        rsi_ok,
        obv_ok
    ])

    if pull_score >= 3:
        return {
            "symbol": symbol,
            "price": round(close_, 0),
            "rsi14": round(rsi_, 2),
            "volume": round(volume_, 0),
            "obv_status": "🟢" if obv_ok else "🔴",
            "score": pull_score,
            "action": "PULL BUY 30% NAV"
        }

    return None    
st.markdown("---")
st.markdown("## 🐔 GÀ CHIẾN (LEVEL 1–2–3)")
# =========================
def classify_ga_chien(df):
    level1 = []
    level2 = []
    level3 = []

    for _, row in df.iterrows():
        rsi = row["rsi14"]
        obv = row["obv"]
        obv_ema9 = row["obv_ema9"]
        price = row["price"]
        ema9 = row["ema9"]
        ma20 = row["ma20"]
        score = row["total_score"]
        warning = row["warning"]

        obv_ok = pd.notna(obv) and pd.notna(obv_ema9) and obv >= obv_ema9
        price_ok = pd.notna(price) and pd.notna(ema9) and pd.notna(ma20) and price > ema9 > ma20

        # ===== LEVEL 1 =====
        if (
            pd.notna(rsi)
            and 60 <= rsi <= 70
            and obv_ok
            and price_ok
            and score >= 5
            and warning == ""
        ):
            level1.append(row)
            continue

        # ===== LEVEL 2 =====
        if (
            pd.notna(rsi)
            and 55 <= rsi < 60
            and obv_ok
            and price >= ema9
            and score >= 4
        ):
            level2.append(row)
            continue

        # ===== LEVEL 3 =====
        if (
            pd.notna(rsi)
            and rsi > 50
            and obv_ok
            and score >= 3
        ):
            level3.append(row)

    return (
        pd.DataFrame(level1),
        pd.DataFrame(level2),
        pd.DataFrame(level3),
    )


lv1, lv2, lv3 = classify_ga_chien(scan_df)


def show_ga_table(df, title, color):
    st.markdown(f"### {title}")

    if df.empty:
        st.info("Không có mã")
        return

    out = df[[
        "symbol", "price", "rsi14", "E", "R", "O", "total_score", "obv_status"
    ]].copy()

    out.index = range(len(out))

    st.dataframe(out, use_container_width=True, height=300)


col1, col2, col3 = st.columns(3)

with col1:
    show_ga_table(lv1, "🟢 LEVEL 1 – GÀ CHIẾN XỊN", "green")

with col2:
    show_ga_table(lv2, "🟡 LEVEL 2 – GÀ KHỎE", "orange")

with col3:
    show_ga_table(lv3, "🔵 LEVEL 3 – GÀ TIỀM NĂNG", "blue")
st.markdown("---")

cols = st.columns(len(GROUP_ORDER))
for i, group_name in enumerate(GROUP_ORDER):
    with cols[i]:
        st.subheader(group_name)
        show_group_table(scan_df, group_name)



# =========================================================
# V25 - QUẢN TRỊ DANH MỤC
# =========================================================
st.markdown("---")
st.markdown("## 📊 QUẢN TRỊ DANH MỤC V25")

portfolio_text = st.text_area(
    "Anh chỉ nhập: Mã,Giá mua,%NAV",
    placeholder="BAF,36600,4.5\nGVR,33217,12\nVHM,144300,3.5",
    height=130,
    key="v25_portfolio_input"
)

pf_df = v25_build_portfolio_table(scan_df, portfolio_text, market_real)

if pf_df.empty:
    st.info("Chưa nhập danh mục.")
else:
    st.dataframe(pf_df, use_container_width=True, height=360)
    p1, p2, p3 = st.columns(3)
    p1.metric("Lãi/Lỗ TB", f"{round(pf_df['% Lãi/Lỗ'].dropna().mean(), 2)}%")
    p2.metric("Tổng NAV", f"{round(pd.to_numeric(pf_df['%NAV'], errors='coerce').fillna(0).sum(), 2)}%")
    p3.metric("Số mã", len(pf_df))

# =========================================================
# DETAIL
# =========================================================
if show_detail:
    st.markdown("---")
    st.subheader("BẢNG TỔNG CHI TIẾT")

    detail_cols = [
        "symbol", "group", "price",
        "ema9", "ma20",
        "rsi14", "rsi_slope",
        "obv", "obv_ema9", "obv_status",
        "E", "R", "O", "total_score",
        "dist_from_ema9_pct", "pull_label", "breakout_ref",
        "status", "warning"
    ]

    detail_df = scan_df[detail_cols].copy()
    detail_df.index = range(len(detail_df))

    st.dataframe(detail_df, use_container_width=True, height=720)


# =========================================================
# FOOTER
# =========================================================
st.markdown("---")
st.caption(
    "Đọc nhanh: "
    "REAL = quyết định, LIVE = quan sát. "
    "R dùng RSI zone + slope. "
    "OBV_status cho biết tiền lớn còn giữ hay đã gãy. "
    "Market REAL ≥ 8 mới đánh mạnh."
)






