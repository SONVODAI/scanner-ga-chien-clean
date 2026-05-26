# =========================================================
# MARKET FORECAST ENGINE
# =========================================================
def calc_market_forecast(df: pd.DataFrame):

    total = len(df)

    if total == 0:
        return 0, "Không có dữ liệu"

    # =========================
    # Đếm nhóm khỏe
    # =========================
    strong = len(df[df["group"] == "CP MẠNH"])
    accel = len(df[df["group"] == "GÀ TĂNG TỐC"])
    breakout = len(df[df["group"] == "MUA BREAK"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])

    # =========================
    # Đếm nhóm yếu
    # =========================
    weak = len(df[df["group"] == "THEO DÕI"])

    # =========================
    # Breadth khỏe
    # =========================
    obv_good = len(df[df["obv_status"] == "🟢"]) / total

    # =========================
    # Slope market
    # =========================
    slope_good = len(df[df["ema9_ma20_slope"] > 0]) / total

    # =========================
    # Forecast score
    # =========================
    score = 0

    score += min(accel / 5, 2)
    score += min(strong / 10, 2)
    score += min(breakout / 8, 2)
    score += min(pull_good / 8, 2)

    score += obv_good * 1
    score += slope_good * 1

    score -= min(weak / 15, 2)

    score = round(max(min(score, 10), 0), 1)

    # =========================
    # TEXT
    # =========================
    if score >= 8:
        text = "🟢 Forecast tốt 5-10 ngày"
    elif score >= 6:
        text = "🟡 Forecast trung tính-khá"
    elif score >= 7:
        text = "🟠 Forecast yếu"
    else:
        text = "🔴 Forecast rủi ro"

    return score, text
# =========================================================
# SCANNER GÀ CHIẾN V18.4 + SLOPE CLEAN REWRITE
# Full app.py - viết lại sạch từ đầu
# Có: Market REAL/LIVE, EMA9/MA20 slope, RSI, OBV, nhóm CP,
# khuyến nghị mua, bảng gà tăng tốc, quản trị danh mục.
# =========================================================
import time
import os
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import base64
import streamlit as st
import streamlit as st
import yfinance as yf
from market_analog_engine import find_similar_periods, generate_market_prediction

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
    "HAH", "VSC", "GMD", "VOS", "VTO", "ACV", "HVN", "VJC", 

    "MSH", "TNG", "TCM", "GIL", "VHC", "ANV", "FMC", "VCS", "PTB", "VGT",

    "BFC", "DCM", "DPM", "CSV", "DDV", "LAS", "BMP", "NTP", "AAA",
    "PAC", "MSR", "REE", "GEE", "GEX", "PC1", "HDG", "GEG", "NT2",
    "TV2", "DGC", "POW",

    "C4G", "FCN", "CII", "KSB", "DHA", "CTI", "HBC", "HPG", "HSG",
    "NKG", "VGS", "CTD", "HHV", "VCG", "PLC", "TLH", "TVN",

    "MWG", "FRT", "DGW", "PET", "HAX", "MSN", "DBC", "HAG", "BAF",
    "MCH", "PAN", "VNM", "MML", "FMC", "MCH", "TLG",

    "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "SHB", "SSB",
    "STB", "HDB", "TPB", "VIB", "LPB", "OCB", "MSB", "NAB", "EIB",
    "VND", "SSI", "HCM", "VIX", "BSI", "FTS", "TVS", "SHS",
    "AGR", "VCI", "TCX", "VCK", "VPX", "ORS", "BVS", "VDS", "MBS",

    "VGC", "SZC", "IDC", "KBC", "LHG", "IJC", "DTD", "BCM",

    "GVR", "SIP", "DPR", "PHR", "DRI",

    "FPT", "VGI", "CTR", "VTP", "CMG", "ELC", "FOX",

    "IMP", "BVH", "SBT", "LSS", "PNJ", "TLG", "DHT",
    "TNH", "YEG",

    "VIC", "VHM", "VRE", "NVL", "DXG", "DXS", "DIG", "CEO", "TCH",
    "EVF", "SAB", "VPL", "PDR", "CEO", "DPG", "NHA", "HDC", "NTL", "CII", "HDG","HHS", "NLG", "KDH", "HUT",
])))

DEFAULT_SUFFIX = ".VN"


# =========================================================
# STYLE
# =========================================================

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
def download_symbol_data(symbol: str) -> pd.DataFrame:

    try:
        from vnstock import stock_historical_data

        df = stock_historical_data(
            symbol=symbol,
            start_date="2025-01-01",
            end_date=datetime.now().strftime("%Y-%m-%d"),
            resolution="1D",
            type="stock",
            beautify=True,
        )

        if df is None or len(df) == 0:
            return pd.DataFrame()

        # =========================
        # RENAME COLUMNS
        # =========================
        rename_map = {}

        for c in df.columns:

            cl = str(c).lower()

            if "date" in cl or "time" in cl:
                rename_map[c] = "date"

            elif cl == "open":
                rename_map[c] = "open"

            elif cl == "high":
                rename_map[c] = "high"

            elif cl == "low":
                rename_map[c] = "low"

            elif cl == "close":
                rename_map[c] = "close"

            elif cl == "volume":
                rename_map[c] = "volume"

        df = df.rename(columns=rename_map)

        needed = [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]

        for c in needed:
            if c not in df.columns:
                st.write(f"Thiếu cột: {c}")
                return pd.DataFrame()

        df = df[needed].copy()

        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=["close"])

        return df.reset_index(drop=True)

    except Exception as e:
        st.write(f"🔥 {symbol}: {e}")
        return pd.DataFrame() 
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
    # =====================================================
    # RS - RELATIVE STRENGTH NGẮN HẠN
    # =====================================================

    # % thay đổi giá so với 5 phiên trước
    x["rs5"] = (
        (x["close"] / x["close"].shift(5)) - 1
    ) * 100

    # % thay đổi giá so với 10 phiên trước
    x["rs10"] = (
        (x["close"] / x["close"].shift(10)) - 1
    ) * 100

    # =====================================================
    # 🟢 GREEN 2 CONFIRM
    # =====================================================
    
    x["green_candle"] = x["close"] > x["open"]
    
    x["green_1"] = x["green_candle"].shift(1)
    x["green_2"] = x["green_candle"]
    
    # Volume tăng dần
    x["vol_up_confirm"] = (
        x["volume"] > x["volume"].shift(1)
    )
    
    # RSI xác nhận
    x["rsi_confirm"] = (
        (x["rsi14"] > 55)
        & (x["rsi14"] > x["rsi14"].shift(1))
    )
    
    # OBV xác nhận
    x["obv_confirm"] = (
        (x["obv"] > x["obv_ema9"])
        & (x["obv"] > x["obv"].shift(1))
    )
    
    # GREEN 2 SIGNAL
    x["green_2_confirm"] = np.where(
    
        (
            x["green_1"]
            & x["green_2"]
            & x["vol_up_confirm"]
            & x["rsi_confirm"]
            & x["obv_confirm"]
        ),
    
        "🟢 GREEN 2",
    
        ""
        )    
    
    return x
# =========================================================
# DRY-UP ENGINE
# =========================================================
def calculate_dryup_score(df):
    try:
        score = 0

        # =========================
        # Volume MA20
        # =========================
        vol_ma20 = df["volume"].rolling(20).mean()

        vol_now = df["volume"].iloc[-1]
        vol_ma_now = vol_ma20.iloc[-1]

        dry_ratio = vol_now / vol_ma_now

        # =========================
        # Low Vol Days
        # =========================
        low_vol_days = (
                df["volume"] < vol_ma20 * 0.7
            ).tail(20).sum()
    
            # =========================
            # Vol Slope
            # =========================
        vol_20 = pd.to_numeric(
            df["volume"].tail(20),
            errors="coerce"
        ).dropna().values
        
        if len(vol_20) < 5:
            vol_slope = 0
        else:
            x = np.arange(len(vol_20))
            vol_slope = np.polyfit(x, vol_20, 1)[0]
            # =========================
            # Range Compression
            # =========================
            range_pct = (
            (df["high"] - df["low"]) / df["close"]
        ).tail(10).mean()

        # =========================
         # =========================
        # RSI giữ nền
        # =========================
        rsi_now = df["rsi14"].iloc[-1]

        # =========================
        # OBV giữ nền
        # =========================
        obv_now = df["obv"].iloc[-1]

        if "obv_ema9" in df.columns:
            obv_ema9 = df["obv_ema9"].iloc[-1]
        else:
            obv_ema9 = obv_now

        # =========================
        # CHẤM ĐIỂM
        # =========================     # =========================
        # CHẤM ĐIỂM
        # =========================

        if dry_ratio < 0.5:
            score += 1.5
        elif dry_ratio < 0.8:
            score += 1

        if low_vol_days > 12:
            score += 1.5
        elif low_vol_days > 7:
            score += 1

        if vol_slope < 0:
            score += 0.5

        if range_pct < 0.02:
            score += 1
        elif range_pct < 0.03:
            score += 0.5

        if rsi_now > 45:
            score += 0.5

        if obv_now >= obv_ema9:
            score += 1

        # =========================
        # LABEL
        # =========================
        if score >= 5:
            label = "🟢🟢 SIÊU CẠN"
        elif score >= 4:
            label = "🟢 CẠN ĐẸP"
        elif score >= 2.5:
            label = "🟡 CẠN NHẸ"
        else:
            label = "🔴 KHÔNG CẠN"

        return round(score, 2), label

    except:
        return 0, "ERROR"

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
def calc_rs_score(rs5_, rs10_):
    """
    RS = sức mạnh giá ngắn hạn so với chính nó 5-10 phiên trước.
    2 điểm: tăng tốt cả 5 phiên và 10 phiên
    1 điểm: có sức mạnh vừa
    0 điểm: yếu / chưa rõ
    """
    if pd.notna(rs5_) and pd.notna(rs10_):
        if rs5_ >= 3 and rs10_ >= 5:
            return 2
        if rs5_ >= 1 or rs10_ >= 2:
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
# BREAK QUALITY COMMENT
# =========================================================
def break_quality_comment(df, row):
    comments = []

    try:
        # =========================
        # Độ dài nền
        # =========================
        recent = df.tail(20)

        hh = recent["high"].max()
        ll = recent["low"].min()

        base_range = ((hh - ll) / ll) * 100 if ll != 0 else 999

        if base_range <= 8:
            comments.append("nền tích lũy chặt")
        elif base_range <= 15:
            comments.append("nền tích lũy trung bình")
        else:
            comments.append("nền còn rộng")

        # =========================
        # Volume co hẹp
        # =========================
        vol_now = row.get("volume", np.nan)
        vol_ma20 = row.get("vol_ma20", np.nan)

        if pd.notna(vol_now) and pd.notna(vol_ma20):
            if vol_now < vol_ma20 * 0.8:
                comments.append("volume co hẹp tốt")
            elif vol_now > vol_ma20 * 1.5:
                comments.append("volume breakout mạnh")

        # =========================
        # RSI
        # =========================
        rsi = row.get("rsi14", np.nan)

        if pd.notna(rsi):
            if 55 <= rsi <= 70:
                comments.append("RSI khỏe")
            elif rsi > 75:
                comments.append("RSI hơi nóng")

        # =========================
        # OBV
        # =========================
        obv = row.get("obv", np.nan)
        obv_ema9 = row.get("obv_ema9", np.nan)

        if pd.notna(obv) and pd.notna(obv_ema9):
            if obv >= obv_ema9:
                comments.append("OBV xác nhận")
            else:
                comments.append("OBV chưa xác nhận rõ")

        # =========================
        # Khoảng cách EMA9
        # =========================
        dist = row.get("dist_from_ema9_pct", np.nan)

        if pd.notna(dist):
            if dist <= 3:
                comments.append("break còn gần EMA9")
            elif dist >= 7:
                comments.append("break hơi nóng")

        if len(comments) == 0:
            return "Break cần theo dõi thêm"

        return " | ".join(comments)

    except:
        return "Break chưa đủ dữ liệu"

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
    
    if pull_label == "PULL ĐẸP":
        return "PULL ĐẸP"
    
    if pull_label == "PULL VỪA":
        return "PULL VỪA"
    
    if not leader:
        if total <= 1:
            return "THEO DÕI"
    
        if total == 2:
            return "TÍCH LŨY"
    
        return "MUA EARLY"
   
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
@st.cache_data(ttl=300)
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
    # =====================================================
    # RS NGẮN HẠN
    # =====================================================
    rs5_ = to_float(last["rs5"])
    rs10_ = to_float(last["rs10"])
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

    # =====================================================
    # RS SCORE
    # =====================================================
    RS = calc_rs_score(rs5_, rs10_)

    total_score = E + R + O + S + RS
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
        "RS": RS,

        "rs5": safe_round(rs5_, 2),
        "rs10": safe_round(rs10_, 2),
        "green_2_confirm": last["green_2_confirm"],
        "total_score": total_score,    
    }
   
    row["group"] = classify_group(row)
    row["warning"] = build_warning(price, ema9_, rsi_, rsi_slope_, obv_, obv_ema9_, pull_label, slope_)
    row["status"] = build_status(total_score, row["warning"], row["group"])

    return row


# =========================================================
# SCAN
# =========================================================

def run_scan(symbols: list[str]) -> pd.DataFrame:
    rows = []

    for symbol in symbols:
        try:
            item = analyze_symbol(symbol)
            if item is not None:
                rows.append(item)
        except Exception as e:
            st.write(symbol, e)
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
        # =========================
    # DRY-UP ENGINE
    # =========================
    dry_score, dry_label = calculate_dryup_score(df)
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
# ===== ENTRY QUALITY SCORE - ƯU TIÊN ĐIỂM MUA ĐẸP =====
def entry_quality_score(row):
    dist = row.get("dist_from_ema9_pct", 999)
    pull = str(row.get("pull_label", ""))
    rs = row.get("RS", 0)
    score = row.get("total_score", 0)

    q = 0

    # 1. Vị trí so với EMA9
    if pd.notna(dist):
        if 0 <= dist <= 3:
            q += 3
        elif 3 < dist <= 5:
            q += 2
        elif 5 < dist <= 8:
            q += 1
        elif dist > 8:
            q -= 2

    # 2. Pull label
    if pull == "PULL ĐẸP":
        q += 3
    elif pull == "PULL VỪA":
        q += 2
    elif pull == "PULL XẤU":
        q -= 1

    # 3. RS vẫn phải có sức mạnh
    if rs >= 2:
        q += 1
    elif rs <= 0:
        q -= 1

    # 4. Tổng điểm nền tảng
    if score >= 8:
        q += 1

    return q
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
market_forecast, market_forecast_text = calc_market_forecast(scan_df)
market_status, market_action = market_status_text(market_real)

st.markdown("## 📊 MARKET OVERVIEW")

m1, m2, m3, m4 = st.columns(4)

with m1:
    st.metric("REAL", f"{market_real}/13")

with m2:
    st.metric("LIVE", f"{market_live}/13")

with m3:
    st.metric("FORECAST", f"{market_forecast}/10")

with m4:
    st.metric("WATCHLIST", len(scan_df))

if market_real < 6:
    st.error(market_action)
elif market_real < 8:
    st.warning(market_action)
else:
    st.success(market_action)

st.caption(market_forecast_text)

# =========================================================
# GROUP SUMMARY
# =========================================================
st.markdown("---")
st.markdown("## 📦 NHÓM CỔ PHIẾU")

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

cols = st.columns(len(GROUP_ORDER))

for i, g in enumerate(GROUP_ORDER):

    cnt = int((scan_df["group"] == g).sum())

    with cols[i]:
        st.metric(g, cnt)

# =========================================================
# BẢNG THEO NHÓM
# =========================================================
st.markdown("---")
st.markdown("## 🐔 BẢNG THEO NHÓM")

SHOW_COLS = [
    "symbol",
    "group",
    "price",
    "total_score",
    "ema9_ma20_slope",
    "rsi14",
    "obv_status",
    "dist_from_ema9_pct",
    "status",
    "warning"
]

tabs = st.tabs(GROUP_ORDER)

for tab, g in zip(tabs, GROUP_ORDER):

    with tab:

        sub = scan_df[
            scan_df["group"] == g
        ].copy()

        if sub.empty:
            st.info("Không có mã")
            continue

        cols_show = [
            c for c in SHOW_COLS
            if c in sub.columns
        ]

        out = sub[cols_show].copy()

        out.index = range(len(out))

        st.dataframe(
            out,
            use_container_width=True,
            height=min(600, 80 + len(out) * 35)
        )

# =========================================================
# DETAIL TABLE
# =========================================================
if show_detail:

    st.markdown("---")
    st.markdown("## 📋 BẢNG CHI TIẾT")

    detail_cols = [
        "symbol",
        "group",
        "price",
        "ema9",
        "ma20",
        "ema9_ma20_slope",
        "ema9_ma20_slope_change",
        "rsi14",
        "rsi_slope",
        "obv_status",
        "E",
        "R",
        "O",
        "S",
        "RS",
        "total_score",
        "dist_from_ema9_pct",
        "pull_label",
        "status",
        "warning"
    ]

    detail_cols = [
        c for c in detail_cols
        if c in scan_df.columns
    ]

    detail_df = scan_df[
        detail_cols
    ].copy()

    detail_df.index = range(len(detail_df))

    st.dataframe(
        detail_df,
        use_container_width=True,
        height=700
    )

# =========================================================
# FOOTER
# =========================================================
st.markdown("---")

st.caption(
    "Realtime VNStock | V18.4 lightweight rebuild"
)
# =========================================================
# EVOLUTION 5 DAYS
# =========================================================

GROUP_RANK = {
    "THEO DÕI": 0,
    "TÍCH LŨY": 1,
    "MUA EARLY": 2,
    "PULL VỪA": 3,
    "PULL ĐẸP": 4,
    "MUA BREAK": 5,
    "CP MẠNH": 6,
    "GÀ TĂNG TỐC": 7
}

# =========================================================
# SAVE EVOLUTION
# =========================================================
def save_evolution(scan_df):

    today = datetime.now().strftime("%Y-%m-%d")

    rows = []

    for _, r in scan_df.iterrows():

        rows.append({
            "date": today,
            "symbol": r["symbol"],
            "group": r["group"]
        })

    new_df = pd.DataFrame(rows)

    FILE_NAME = "group_evolution_history.csv"

    try:

        old_df = pd.read_csv(FILE_NAME)

        evo_df = pd.concat(
            [old_df, new_df],
            ignore_index=True
        )

    except:
        evo_df = new_df

    evo_df = evo_df.drop_duplicates(
        subset=["date", "symbol"],
        keep="last"
    )

    evo_df.to_csv(FILE_NAME, index=False)

    return evo_df


# =========================================================
# BUILD EVOLUTION TABLE
# =========================================================
def build_evolution_table():

    FILE_NAME = "group_evolution_history.csv"

    try:
        evo_df = pd.read_csv(FILE_NAME)

    except:
        return pd.DataFrame(), pd.DataFrame()

    if evo_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    pivot = evo_df.pivot_table(
        index="symbol",
        columns="date",
        values="group",
        aggfunc="first"
    )

    pivot = pivot.sort_index(axis=1)

    if len(pivot.columns) < 5:
        return pd.DataFrame(), pd.DataFrame()

    last_cols = pivot.columns[-5:]

    evo_list = []

    for symbol in pivot.index:

        row = pivot.loc[symbol]

        groups = row[last_cols].tolist()

        if any(pd.isna(groups)):
            continue

        ranks = [
            GROUP_RANK.get(g, 0)
            for g in groups
        ]

        evolution_score = ranks[-1] - ranks[0]

        evo_list.append({
            "symbol": symbol,
            "D-4": groups[0],
            "D-3": groups[1],
            "D-2": groups[2],
            "D-1": groups[3],
            "TODAY": groups[4],
            "evolution": evolution_score
        })

    evo_table = pd.DataFrame(evo_list)

    if evo_table.empty:
        return pd.DataFrame(), pd.DataFrame()

    evo_table = evo_table.sort_values(
        "evolution",
        ascending=False
    )

    # =========================================
    # BẢNG CHỌN LỌC (BẢNG MUA)
    # =========================================

    buy_table = evo_table[
        (evo_table["evolution"] >= 1)
        &
        (
            evo_table["TODAY"].isin([
                "MUA EARLY",
                "PULL ĐẸP",
                "CP MẠNH"
            ])
        )
    ].copy()

    return evo_table, buy_table


# =========================================================
# SAVE EVOLUTION DATA
# =========================================================
save_evolution(scan_df)

evo_table, buy_table = build_evolution_table()


# =========================================================
# SHOW EVOLUTION
# =========================================================
st.markdown("---")

st.subheader("🚀 BẢNG TIẾN HÓA 5 NGÀY")

if not evo_table.empty:

    st.dataframe(
        evo_table,
        use_container_width=True,
        height=400
    )

else:
    st.info("Chưa đủ dữ liệu 5 ngày")


# =========================================================
# BUY TABLE
# =========================================================
st.markdown("---")

st.subheader("🔥 BẢNG TIẾN HÓA CHỌN LỌC")

if not buy_table.empty:

    st.dataframe(
        buy_table,
        use_container_width=True,
        height=400
    )

else:
    st.info("Chưa có cổ phiếu đạt điều kiện")
# =========================================================
