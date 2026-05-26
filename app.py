# =========================================================
# SCANNER GÀ CHIẾN V20 CLEAN
# Rebuild sạch: data -> indicators -> analyze -> scan -> UI
# Giữ lõi: Market REAL/LIVE, Pull/Break, Dryup, Gà 1KG,
# Portfolio, Top Risk, Market Analog, Evolution.
# =========================================================

import time
import base64
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import streamlit as st
from vnstock import stock_historical_data

try:
    from vnstock import stock_intraday_data
except Exception:
    stock_intraday_data = None

try:
    from market_analog_engine import find_similar_periods, generate_market_prediction
    from evolution_engine import (
    save_evolution_history,
    build_evolution_leaders,
)
except Exception:
    find_similar_periods = None
    generate_market_prediction = None

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Scanner Gà Chiến V20 CLEAN",
    page_icon="🐔",
    layout="wide",
)

st.title("🐔 Scanner Gà Chiến V20 CLEAN")
st.caption("Bản rebuild sạch: không vá víu, đủ indicator lõi, Market-first, Gà 1KG, Evolution")

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
    "MCH", "PAN", "VNM", "MML", "TLG",
    "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "SHB", "SSB",
    "STB", "HDB", "TPB", "VIB", "LPB", "OCB", "MSB", "NAB", "EIB",
    "VND", "SSI", "HCM", "VIX", "BSI", "FTS", "TVS", "SHS",
    "AGR", "VCI", "TCX", "VCK", "VPX", "ORS", "BVS", "VDS", "MBS",
    "VGC", "SZC", "IDC", "KBC", "LHG", "IJC", "DTD", "BCM",
    "GVR", "SIP", "DPR", "PHR", "DRI",
    "FPT", "VGI", "CTR", "VTP", "CMG", "ELC", "FOX",
    "IMP", "BVH", "SBT", "LSS", "PNJ", "DHT", "TNH", "YEG",
    "VIC", "VHM", "VRE", "NVL", "DXG", "DXS", "DIG", "CEO", "TCH",
    "EVF", "SAB", "VPL", "PDR", "DPG", "NHA", "HDC", "NTL",
    "HHS", "NLG", "KDH", "HUT",
])))

GROUP_RANK = {
    "THEO DÕI": 0,
    "TÍCH LŨY": 1,
    "MUA EARLY": 2,
    "PULL VỪA": 3,
    "PULL ĐẸP": 4,
    "MUA BREAK": 5,
    "CP MẠNH": 6,
    "GÀ TĂNG TỐC": 7,
}

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

EVOLUTION_FILE = "group_evolution_history.csv"

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
    return series.rolling(window).mean()


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

# =========================================================
# DATA DOWNLOAD
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def download_symbol_data(symbol: str, days: int = 260) -> pd.DataFrame:
    """Download daily OHLCV from vnstock. Robust against time/date column variants."""
    try:
        df = stock_historical_data(
            symbol=symbol,
            start_date="2024-01-01",
            end_date=datetime.now().strftime("%Y-%m-%d"),
            resolution="1D",
            type="stock",
            beautify=True,
        )
    except Exception as e:
        print("DATA ERROR", symbol, e)
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    df = df.rename(columns={
        "time": "date",
        "tradingdate": "date",
        "datetime": "date",
        "ticker": "symbol",
    })

    needed = ["date", "open", "high", "low", "close", "volume"]
    for col in needed:
        if col not in df.columns:
            print("MISSING COL", symbol, col, list(df.columns))
            return pd.DataFrame()

    out = df[needed].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")

    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["date", "close"])
    out = out.sort_values("date").drop_duplicates("date", keep="last")
    out = out.tail(days).reset_index(drop=True)

    return out
# =========================================================
# REALTIME OVERLAY
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def get_realtime_overlay(symbol: str) -> dict:
    if stock_intraday_data is None:
        return {}

    try:
        rt = stock_intraday_data(
            symbol=symbol,
            page_size=100,
            page_num=0
        )

        if rt is None or rt.empty:
            return {}

        rt.columns = [str(c).lower().strip() for c in rt.columns]

        price_col = None
        vol_col = None

        for c in rt.columns:
            if c in ["price", "matchprice", "close"]:
                price_col = c
            if c in ["volume", "matchvolume"]:
                vol_col = c

        if price_col is None:
            return {}

        last_price = pd.to_numeric(rt[price_col], errors="coerce").dropna()

        if last_price.empty:
            return {}

        result = {
            "rt_price": float(last_price.iloc[-1])
        }

        if vol_col is not None:
            result["rt_volume"] = pd.to_numeric(
                rt[vol_col],
                errors="coerce"
            ).fillna(0).sum()

        return result

    except Exception as e:
        print("REALTIME ERROR", symbol, e)
        return {}
# =========================================================
# INDICATOR ENGINE
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

    x["ema9_ma20_slope"] = np.where(
        x["ma20"] != 0,
        (x["ema9"] - x["ma20"]) / x["ma20"] * 100,
        np.nan,
    )
    x["ema9_ma20_slope_change"] = x["ema9_ma20_slope"] - x["ema9_ma20_slope"].shift(3)
    x["slope_state"] = x["ema9_ma20_slope"].apply(slope_state_text)

    x["rsi14"] = calc_rsi(x["close"], 14)
    x["rsi_ema9"] = ema(x["rsi14"], 9)
    x["rsi_slope"] = x["rsi14"] - x["rsi14"].shift(3)

    x["obv"] = calc_obv(x["close"], x["volume"])
    x["obv_ema9"] = ema(x["obv"], 9)
    x["obv_slope"] = x["obv"] - x["obv"].shift(3)

    x["vol_ma20"] = sma(x["volume"], 20)
    x["vol_ratio"] = np.where(x["vol_ma20"] != 0, x["volume"] / x["vol_ma20"], np.nan)

    x["rs5"] = (x["close"] / x["close"].shift(5) - 1) * 100
    x["rs10"] = (x["close"] / x["close"].shift(10) - 1) * 100
    x["pct_change"] = x["close"].pct_change() * 100

    x["green_candle"] = x["close"] > x["open"]
    x["green_1"] = x["green_candle"].shift(1).fillna(False)
    x["green_2"] = x["green_candle"].fillna(False)
    x["vol_up_confirm"] = x["volume"] > x["volume"].shift(1)
    x["rsi_confirm"] = (x["rsi14"] > 55) & (x["rsi14"] > x["rsi14"].shift(1))
    x["obv_confirm"] = (x["obv"] > x["obv_ema9"]) & (x["obv"] > x["obv"].shift(1))
    x["green_2_confirm"] = np.where(
        x["green_1"] & x["green_2"] & x["vol_up_confirm"] & x["rsi_confirm"] & x["obv_confirm"],
        "🟢 GREEN 2",
        "",
    )

    return x

# =========================================================
# DRY-UP ENGINE
# =========================================================
def calculate_dryup_score(df: pd.DataFrame):
    try:
        if df is None or df.empty or len(df) < 20:
            return 0, "ERROR"

        score = 0
        vol_ma20 = df["volume"].rolling(20).mean()
        vol_now = df["volume"].iloc[-1]
        vol_ma_now = vol_ma20.iloc[-1]

        if pd.isna(vol_ma_now) or vol_ma_now == 0:
            return 0, "ERROR"

        dry_ratio = vol_now / vol_ma_now
        low_vol_days = (df["volume"] < vol_ma20 * 0.7).tail(20).sum()
        vol_20 = pd.to_numeric(df["volume"].tail(20), errors="coerce").dropna().values
        vol_slope = 0 if len(vol_20) < 5 else np.polyfit(np.arange(len(vol_20)), vol_20, 1)[0]
        range_pct = ((df["high"] - df["low"]) / df["close"]).tail(10).mean()
        rsi_now = df["rsi14"].iloc[-1] if "rsi14" in df.columns else np.nan
        obv_now = df["obv"].iloc[-1] if "obv" in df.columns else np.nan
        obv_ema9 = df["obv_ema9"].iloc[-1] if "obv_ema9" in df.columns else obv_now

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

        if pd.notna(range_pct):
            if range_pct < 0.02:
                score += 1
            elif range_pct < 0.03:
                score += 0.5

        if pd.notna(rsi_now) and rsi_now > 45:
            score += 0.5

        if pd.notna(obv_now) and pd.notna(obv_ema9) and obv_now >= obv_ema9:
            score += 1

        if score >= 5:
            label = "🟢🟢 SIÊU CẠN"
        elif score >= 4:
            label = "🟢 CẠN ĐẸP"
        elif score >= 2.5:
            label = "🟡 CẠN NHẸ"
        else:
            label = "🔴 KHÔNG CẠN"

        return round(score, 2), label
    except Exception:
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
    if pd.notna(rs5_) and pd.notna(rs10_):
        if rs5_ >= 3 and rs10_ >= 5:
            return 2
        if rs5_ >= 1 or rs10_ >= 2:
            return 1
    return 0

# =========================================================
# CLASSIFY / WARNING
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


def classify_obv_power(row):
    obv = row.get("obv", np.nan)
    obv_ema9 = row.get("obv_ema9", np.nan)
    if not pd.notna(obv) or not pd.notna(obv_ema9) or obv_ema9 == 0:
        return "⚪ OBV KHÔNG RÕ"
    if obv < obv_ema9:
        return "🔴 OBV YẾU"
    diff_pct = (obv - obv_ema9) / abs(obv_ema9) * 100
    if diff_pct > 2:
        return "🟢 OBV MẠNH"
    return "🟡 OBV TRUNG TÍNH"


def classify_group(row: dict) -> str:
    price = row["price"]
    ema9_ = row["ema9"]
    vol_ = row["volume"]
    vol_ma20_ = row["vol_ma20"]
    total = row["total_score"]
    e = row["E"]
    r = row["R"]
    o = row["O"]
    dist = row["dist_from_ema9_pct"]
    breakout_ref = row["breakout_ref"]
    pull_label = row["pull_label"]
    slope_ = row["ema9_ma20_slope"]

    leader = total >= 5 and e >= 1 and o >= 1 and pd.notna(price) and pd.notna(ema9_) and price >= ema9_ * 0.97

    if pd.notna(slope_) and slope_ > 2 and total >= 6 and e >= 1 and r >= 1 and o >= 1:
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

    if pd.notna(breakout_ref) and pd.notna(price) and pd.notna(vol_) and pd.notna(vol_ma20_):
        if price >= breakout_ref * 1.01 and vol_ >= vol_ma20_ * 1.2 and r >= 1 and o >= 1:
            return "MUA BREAK"

    if pd.notna(dist) and dist > 1.5 and e == 2 and r >= 1 and o >= 1:
        return "CP MẠNH"

    return "MUA EARLY"
# =========================================================
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
volume = to_float(last["volume"])

# REALTIME OVERLAY
rt = get_realtime_overlay(symbol)

if rt:

    rt_price = rt.get("rt_price")
    rt_vol = rt.get("rt_volume")

    if rt_price is not None:
        price = rt_price

    if rt_vol is not None and rt_vol > volume:
        volume = rt_vol

        ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])
    ema9_prev = to_float(prev["ema9"])

    slope_ = to_float(last["ema9_ma20_slope"])
    slope_change_ = to_float(last["ema9_ma20_slope_change"])
    slope_state_ = str(last["slope_state"])

    rsi_ = to_float(last["rsi14"])
    rsi_slope_ = to_float(last["rsi_slope"])
    rs5_ = to_float(last["rs5"])
    rs10_ = to_float(last["rs10"])

    obv_ = to_float(last["obv"])
    obv_ema9_ = to_float(last["obv_ema9"])
    obv_prev = to_float(prev["obv"])

    vol_ = volume
    vol_ma20_ = to_float(last["vol_ma20"])

    vol_ratio_ = np.nan
    if pd.notna(vol_) and pd.notna(vol_ma20_) and vol_ma20_ != 0:
        vol_ratio_ = vol_ / vol_ma20_

    pct_change_ = np.nan
    prev_close = to_float(prev["close"])
    if pd.notna(price) and pd.notna(prev_close) and prev_close != 0:
        pct_change_ = (price / prev_close - 1) * 100

    breakout_ref = to_float(df["high"].iloc[-21:-1].max())

    dist_from_ema9 = np.nan
    if pd.notna(price) and pd.notna(ema9_) and ema9_ != 0:
        dist_from_ema9 = (price / ema9_ - 1) * 100

    E = calc_price_score(price, ema9_, ma20_, ema9_prev)
    R = calc_rsi_score(rsi_, rsi_slope_)
    O = calc_obv_score(obv_, obv_ema9_, obv_prev)
    S = calc_slope_score(slope_, slope_change_)
    RS = calc_rs_score(rs5_, rs10_)

    total_score = E + R + O + S + RS

    dry_score, dry_label = calculate_dryup_score(df)

    pull_label = classify_pull_label(
        dist_from_ema9,
        rsi_,
        rsi_slope_,
        obv_,
        obv_ema9_
    )

    obv_status = "🟢" if (
        pd.notna(obv_)
        and pd.notna(obv_ema9_)
        and obv_ >= obv_ema9_
    ) else "🔴"

    row = {
        "symbol": symbol,
        "data_date": last["date"],
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
        "vol_ratio": safe_round(vol_ratio_, 2),
        "pct_change": safe_round(pct_change_, 2),
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
        "green_2_confirm": str(last.get("green_2_confirm", "")),
        "total_score": total_score,
        "dry_score": dry_score,
        "dry_label": dry_label,
    }
row["OBV_POWER"] = classify_obv_power(row)

row["group"] = classify_group(row)

row["warning"] = build_warning(
    price,
    ema9_,
    rsi_,
    rsi_slope_,
    obv_,
    obv_ema9_,
    pull_label,
    slope_
    )

row["status"] = build_status(
        total_score,
        row["warning"],
        row["group"]
    )
    
return row
# =========================================================
# SCAN ENGINE
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def run_scan(symbols: list[str]) -> pd.DataFrame:
    rows = []
    errors = []

    for symbol in symbols:
        try:
            item = analyze_symbol(symbol)
            if item is not None:
                rows.append(item)
        except Exception as e:
            errors.append({"symbol": symbol, "error": str(e)})
            print("SCAN ERROR", symbol, e)

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

    df = df.sort_values(
        by=["group_rank", "total_score", "S", "E", "O", "R", "ema9_ma20_slope"],
        ascending=[True, False, False, False, False, False, False],
    ).reset_index(drop=True)

    return df

# =========================================================
# MARKET
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
        e_ratio * 2.5 + r_ratio * 2.5 + o_ratio * 2.0 + s_ratio * 2.0
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
        e_ratio * 3.0 + r_ratio * 2.5 + o_ratio * 2.5 + s_ratio * 2.0
        + min(strong / 12, 1) * 1.0
        + min(accel / 8, 1) * 1.2
        + min((pull_good + pull_ok) / 12, 1) * 0.8
    )
    return round(min(score, 13), 1)


def calc_market_forecast(df: pd.DataFrame):
    total = len(df)
    if total == 0:
        return 0, "Không có dữ liệu"

    strong = len(df[df["group"] == "CP MẠNH"])
    accel = len(df[df["group"] == "GÀ TĂNG TỐC"])
    breakout = len(df[df["group"] == "MUA BREAK"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])
    weak = len(df[df["group"] == "THEO DÕI"])
    obv_good = len(df[df["obv_status"] == "🟢"]) / total
    slope_good = len(df[df["ema9_ma20_slope"] > 0]) / total

    score = 0
    score += min(accel / 5, 2)
    score += min(strong / 10, 2)
    score += min(breakout / 8, 2)
    score += min(pull_good / 8, 2)
    score += obv_good * 1
    score += slope_good * 1
    score -= min(weak / 15, 2)
    score = round(max(min(score, 10), 0), 1)

    if score >= 8:
        text = "🟢 Forecast tốt 5-10 ngày"
    elif score >= 6:
        text = "🟡 Forecast trung tính-khá"
    elif score >= 4:
        text = "🟠 Forecast yếu"
    else:
        text = "🔴 Forecast rủi ro"
    return score, text


def market_status_text(score: float) -> tuple[str, str]:
    if score >= 8:
        return "🟢 THỊ TRƯỜNG KHỎE", "✅ Có thể vào tiền"
    if score >= 6:
        return "🟡 TRUNG TÍNH", "⚠️ Chỉ nên test nhỏ"
    return "🔴 THỊ TRƯỜNG YẾU", "⛔ Không nên vào tiền"

# =========================================================
# BUY / NAV
# =========================================================
def nav_suggestion(action: str, market_real: float) -> str:
    if market_real < 6:
        return "0%"
    if action in ["MUA GÀ TĂNG TỐC", "MUA PULL ĐẸP", "MUA BREAK"]:
        return "15-20% NAV" if market_real >= 8 else "5-10% NAV"
    if action in ["MUA PULL VỪA", "TEST EARLY", "CANH ADD CP MẠNH"]:
        return "10-15% NAV" if market_real >= 8 else "5-10% NAV"
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
        action = "MUA PULL ĐẸP"
        zone = f"{round(ema9_, 0)} - {round(ema9_ * 1.01, 0)}" if pd.notna(ema9_) else f"{price}"
        return "🟢", action, zone, nav_suggestion(action, market_real), "Pull sát EMA9, OBV còn xanh"

    if group == "PULL VỪA" and obv_ok:
        action = "MUA PULL VỪA"
        zone = f"{round(ema9_ * 0.99, 0)} - {round(ema9_ * 1.01, 0)}" if pd.notna(ema9_) else f"{price}"
        return "🟡", action, zone, nav_suggestion(action, market_real), "Pull vừa, chỉ mua thăm dò"

    if group == "MUA EARLY" and score >= 3 and obv_ok and pd.notna(dist) and abs(dist) <= 2.5:
        action = "TEST EARLY"
        return "🟡", action, f"{round(price * 0.99, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Early sạch, test nhỏ"

    if group == "MUA BREAK" and obv_ok:
        action = "MUA BREAK"
        return "🟢", action, f"{round(price, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Break xác nhận"

    if group == "CP MẠNH" and score >= 5 and obv_ok:
        if pd.notna(dist) and dist > 4:
            return "🟡", "CHỜ PULL", f"Canh {round(ema9_, 0)} - {round(ema9_ * 1.02, 0)}", "0%", "CP mạnh nhưng xa EMA9"
        action = "CANH ADD CP MẠNH"
        return "🟡", action, f"{round(price * 0.99, 0)} - {round(price, 0)}", nav_suggestion(action, market_real), "CP mạnh, có thể add nhỏ"

    return "🔴", "KHÔNG MUA", "-", "0%", "Chưa đủ điểm mua"


def auto_buy_signal(row):
    if row.get("pull_label", "") == "PULL ĐẸP" and "MẠNH" in str(row.get("OBV_POWER", "")) and row.get("rsi14", 0) >= 55 and row.get("ema9_ma20_slope", 0) > 1:
        return "🟢 MUA PULL"
    if row.get("price", 0) >= row.get("breakout_ref", 0) and row.get("dist_from_ema9_pct", 999) <= 5 and "MẠNH" in str(row.get("OBV_POWER", "")) and 55 <= row.get("rsi14", 0) <= 70:
        return "🟢 MUA BREAK"
    if row.get("group", "") == "MUA EARLY" and "MẠNH" in str(row.get("OBV_POWER", "")) and row.get("rsi14", 0) >= 50 and row.get("ema9_ma20_slope", 0) >= 0:
        return "🟡 TEST EARLY"
    return "⚪ CHỜ"

# =========================================================
# EXTRA TABLES
# =========================================================
def entry_quality_score(row):
    dist = row.get("dist_from_ema9_pct", 999)
    pull = str(row.get("pull_label", ""))
    rs = row.get("RS", 0)
    score = row.get("total_score", 0)
    q = 0
    if pd.notna(dist):
        if 0 <= dist <= 3:
            q += 3
        elif 3 < dist <= 5:
            q += 2
        elif 5 < dist <= 8:
            q += 1
        elif dist > 8:
            q -= 2
    if pull == "PULL ĐẸP":
        q += 3
    elif pull == "PULL VỪA":
        q += 2
    elif pull == "PULL XẤU":
        q -= 1
    if rs >= 2:
        q += 1
    elif rs <= 0:
        q -= 1
    if score >= 8:
        q += 1
    return q


def entry_type(row):
    if row["rsi14"] >= 65 and row["ema9_ma20_slope"] > 3:
        return "BREAK"
    if 55 <= row["rsi14"] < 65 and row["ema9_ma20_slope"] > 2:
        return "PULL"
    return "EARLY"


def entry_signal(row):
    if row["ENTRY_TYPE"] == "BREAK":
        return "🔥 MUA NGAY" if row["rsi14"] <= 70 else "🔵 CHỜ PULL"
    if row["ENTRY_TYPE"] == "PULL":
        return "🟢 CANH MUA"
    return "🔵 CHỜ XÁC NHẬN"


def nav_goi_y(i):
    if i == 0:
        return "30%"
    if i == 1:
        return "25%"
    if i == 2:
        return "20%"
    return "10%"


def action_goi_y(row, i):
    if i == 0:
        return "🔥 MUA MẠNH"
    if i <= 2:
        return "🟢 MUA"
    return "🟡 THEO DÕI"


def filter_early_clean(df):
    if df.empty:
        return pd.DataFrame()
    cond = (
        df["rsi14"].between(45, 58)
        & (df["rsi_slope"] >= -0.5)
        & (df["obv"] >= df["obv_ema9"] * 0.98)
        & (abs(df["price"] / df["ema9"] - 1) <= 0.035)
        & (df["volume"] <= df["vol_ma20"] * 1.2)
        & (df["total_score"] >= 3)
        & (df["ema9_ma20_slope"] >= -1)
    )
    return df[cond].copy()


def build_top_picks(df: pd.DataFrame, market_real: float) -> pd.DataFrame:
    picks = []
    for group_name, n in [("GÀ TĂNG TỐC", 3), ("PULL ĐẸP", 2), ("MUA BREAK", 2), ("PULL VỪA", 2)]:
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
    return pd.DataFrame(picks).drop_duplicates("symbol").head(8)


def build_top_risk_detector(base_df):
    if base_df is None or base_df.empty:
        return pd.DataFrame()
    rows = []
    for _, row in base_df.iterrows():
        symbol = row.get("symbol", "")
        score = 0
        reasons = []
        rsi = pd.to_numeric(row.get("rsi14", np.nan), errors="coerce")
        dist = pd.to_numeric(row.get("dist_from_ema9_pct", np.nan), errors="coerce")
        vol = pd.to_numeric(row.get("vol_ratio", np.nan), errors="coerce")
        pct = pd.to_numeric(row.get("pct_change", np.nan), errors="coerce")
        obv_text = str(row.get("OBV_POWER", "")).upper()
        group_text = str(row.get("group", "")).upper()

        if pd.notna(dist) and pd.notna(vol) and pd.notna(pct):
            if dist >= 7 and vol >= 2 and pct >= 4:
                score += 8
                reasons.append("🔥 Nến FOMO cuối sóng")
            elif dist >= 5 and vol >= 1.8 and pct >= 3:
                score += 5
                reasons.append("⚠️ Nến tăng nóng + vol cao")
        if pd.notna(rsi):
            if rsi >= 80:
                score += 3
                reasons.append("RSI quá nóng ≥80")
            elif rsi >= 75:
                score += 2
                reasons.append("RSI nóng ≥75")
            elif rsi >= 70:
                score += 1
                reasons.append("RSI vùng cao ≥70")
        if pd.notna(dist):
            if dist >= 10:
                score += 3
                reasons.append("Giá xa EMA9 >10%")
            elif dist >= 7:
                score += 2
                reasons.append("Giá xa EMA9 7–10%")
            elif dist >= 5:
                score += 1
                reasons.append("Giá bắt đầu nóng >5%")
        if pd.notna(vol):
            if vol >= 2.5 and pd.notna(dist) and dist >= 5:
                score += 3
                reasons.append("Volume đột biến rất cao")
            elif vol >= 1.8 and pd.notna(dist) and dist >= 4:
                score += 2
                reasons.append("Volume cao bất thường")
            elif vol >= 1.3:
                score += 1
                reasons.append("Volume tăng mạnh")
        if "YẾU" in obv_text:
            score += 3
            reasons.append("OBV yếu")
        elif "TRUNG" in obv_text:
            score += 1
            reasons.append("OBV không còn thật mạnh")
        if "GÀ TĂNG TỐC" in group_text:
            score += 2
            reasons.append("Đang ở nhóm Gà tăng tốc")
        elif "CP MẠNH" in group_text:
            score += 1
            reasons.append("Đang ở nhóm CP mạnh")

        if score >= 7:
            level = "🔴 RỦI RO TẠO ĐỈNH CAO" if score >= 10 else "🟠 CẢNH BÁO NÓNG"
            action = "Không mua đuổi / siết stop" if score >= 10 else "Không mua mới"
            rows.append({
                "symbol": symbol,
                "pct": safe_round(pct, 2),
                "dist": safe_round(dist, 2),
                "vol": safe_round(vol, 2),
                "rsi": safe_round(rsi, 2),
                "top_risk_score": score,
                "risk_level": level,
                "reason": " | ".join(reasons),
                "action": action,
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("top_risk_score", ascending=False).reset_index(drop=True)

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
        return safe_round(ema9_ if pd.notna(ema9_) else price * 0.97, 0), "Trailing EMA9"
    if "nghỉ" in state:
        return safe_round(ma20_ if pd.notna(ma20_) else price * 0.95, 0), "Stop dưới MA20/nền nghỉ"
    if "yếu" in state:
        stop = max(ma20_, price * 0.97) if pd.notna(ma20_) and pd.notna(price) else price * 0.97
        return safe_round(stop, 0), "Siết stop"
    return safe_round(price, 0), "Gãy - bán chủ động"


def hold_rules(row, market_real: float):
    checks = [
        ("Market REAL >= 6", market_real >= 6),
        ("Giá >= EMA9", row.get("price", 0) >= row.get("ema9", 10**18)),
        ("EMA9 > MA20", row.get("ema9", 0) > row.get("ma20", 10**18)),
        ("Slope >= 0", row.get("ema9_ma20_slope", -999) >= 0),
        ("RSI >= 55", row.get("rsi14", 0) >= 55),
        ("RSI slope >= 0", row.get("rsi_slope", -999) >= 0),
        ("OBV xanh", row.get("obv_status", "") == "🟢"),
        ("Không cảnh báo nặng", "OBV gãy" not in str(row.get("warning", ""))),
    ]
    passed = sum(ok for _, ok in checks)
    failed = [name for name, ok in checks if not ok]
    return passed, failed


def portfolio_action(row, market_real: float):
    state = ga_state(row)
    passed, _ = hold_rules(row, market_real)
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
            rows.append({"Mã": sym, "Giá mua": buy, "Giá hiện tại": np.nan, "% Lãi/Lỗ": np.nan, "%NAV": nav, "Điểm": np.nan, "Nhóm": "Không có data", "Trạng thái gà": "⚪ Không rõ", "Cảnh báo": "Không có trong scanner", "Stop Engine": np.nan, "Stop note": "-", "Hành động": "CHECK TAY"})
            continue
        r = sub.iloc[0]
        price = r["price"]
        pnl = (price - buy) / buy * 100 if buy else 0
        stop, note = stop_engine(r)
        passed, _ = hold_rules(r, market_real)
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
# EVOLUTION
# =========================================================
def save_evolution_history(scan_df: pd.DataFrame):
    today_str = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = [{"date": today_str, "time": current_time, "symbol": "VNINDEX", "group": "THEO DÕI", "rank": 0}]
    for _, r in scan_df.iterrows():
        group = r.get("group", "")
        symbol = r.get("symbol", "")
        if pd.notna(group) and group != "" and symbol != "":
            rows.append({"date": today_str, "time": current_time, "symbol": symbol, "group": group, "rank": GROUP_RANK.get(group, 0)})

    new_df = pd.DataFrame(rows)
    try:
        old_df = pd.read_csv(EVOLUTION_FILE)
        full_df = pd.concat([old_df, new_df], ignore_index=True)
    except Exception:
        full_df = new_df.copy()

    full_df["date"] = full_df["date"].astype(str)
    full_df = full_df.drop_duplicates(subset=["date", "symbol"], keep="last")
    latest_days = sorted(full_df["date"].unique())[-15:]
    full_df = full_df[full_df["date"].isin(latest_days)].copy()
    full_df.to_csv(EVOLUTION_FILE, index=False)

    try:
        github_token = st.secrets["GITHUB_TOKEN"]
        repo_owner = "SONVODAI"
        repo_name = "scanner-ga-chien-clean"
        file_path = EVOLUTION_FILE
        
        csv_content = full_df.to_csv(index=False)
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
        headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github+json"}
        get_response = requests.get(url, headers=headers)
        sha = get_response.json().get("sha") if get_response.status_code == 200 else None
        data = {"message": "update evolution history", "content": base64.b64encode(csv_content.encode("utf-8")).decode("utf-8"), "branch": "main"}
        if sha:
            data["sha"] = sha
        put_response = requests.put(url, headers=headers, json=data)
        
        if put_response.status_code not in [200, 201]:
            st.warning(f"GitHub push lỗi: {put_response.status_code}")
    except Exception as e:
        st.warning(f"GitHub push error: {e}")

    return full_df, latest_days


def build_evolution_leaders(full_df: pd.DataFrame):

    if full_df is None or full_df.empty:
        return pd.DataFrame()

    try:
        pivot = (
            full_df.pivot_table(
                index="symbol",
                columns="date",
                values="group",
                aggfunc="first"
            )
            .sort_index(axis=1)
        )

        leaders = []

        for symbol in pivot.index:

            row = pivot.loc[symbol].dropna()

            if len(row) < 2:
                continue

            groups = row.values.tolist()
            ranks = [GROUP_RANK.get(g, 0) for g in groups]

            current_group = groups[-1]
            current_rank = ranks[-1]
            prev_rank = ranks[-2]

            rank_change = current_rank - prev_rank

            up_days = 0

            for i in range(1, len(ranks)):
                if ranks[i] > ranks[i - 1]:
                    up_days += 1

            # =========================
            # CHỈ GIỮ CP TIẾN HÓA THẬT
            # =========================

            if (
                rank_change > 0
                and current_group != "THEO DÕI"
            ):

                leaders.append({
                    "symbol": symbol,
                    "current_group": current_group,
                    "rank_change": rank_change,
                    "up_days": up_days,
                    "days_seen": len(row),
                    "evolution": " ➜ ".join(groups[-5:])
                })

        out = pd.DataFrame(leaders)

        if not out.empty:

            out = out.sort_values(
                by=[
                    "rank_change",
                    "up_days",
                    "days_seen"
                ],
                ascending=False
            ).reset_index(drop=True)

        return out

    except Exception:
        return pd.DataFrame()
# =========================================================
# MARKET ANALOG
# =========================================================
def classify_vnindex(prediction):
    confidence = prediction.get("confidence", 0)
    regime = prediction.get("regime", "")
    if confidence >= 70 and "BULL" in regime.upper():
        return "GÀ TĂNG TỐC"
    if confidence >= 60 and "BULL" in regime.upper():
        return "CP MẠNH"
    if confidence >= 55:
        return "MUA EARLY"
    if confidence >= 45:
        return "TÍCH LŨY"
    return "THEO DÕI"

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
    st.markdown(f"""
        <div class="small-note">
        Watchlist: <b>{len(WATCHLIST)}</b> mã &nbsp; | &nbsp;
        Update: <b>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</b>
        </div>
        """, unsafe_allow_html=True)

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
    st.rerun()

# =========================================================
# RUN SCAN
# =========================================================
with st.spinner("Đang quét dữ liệu..."):
    scan_df = run_scan(WATCHLIST)

st.caption(f"Last scan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if scan_df.empty:
    st.error("Không lấy được dữ liệu. Anh kiểm tra lại mạng hoặc nguồn vnstock.")
    st.stop()

scan_df["AUTO_BUY"] = scan_df.apply(auto_buy_signal, axis=1)

# =========================================================
# MARKET OVERVIEW
# =========================================================
market_live = calc_market_live(scan_df)
market_real = calc_market_real(scan_df)
market_forecast, market_forecast_text = calc_market_forecast(scan_df)
market_status, market_action = market_status_text(market_real)

st.markdown("## 📊 MARKET OVERVIEW")
m1, m2, m3, m5 = st.columns([1, 1, 1, 2])
with m1:
    st.metric("Market REAL", f"{market_real}/13")
with m2:
    st.metric("Market LIVE", f"{market_live}/13")
with m3:
    st.metric("Forecast 5-10D", f"{market_forecast}/10")
with m5:
    st.subheader(market_status)
    st.caption(market_forecast_text)

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
buy_signal_cols = scan_df.apply(lambda r: pd.Series(buy_recommendation(r, market_real), index=["Đèn", "Khuyến nghị", "Vùng mua", "NAV gợi ý", "Lý do"]), axis=1)
scan_df = pd.concat([scan_df, buy_signal_cols], axis=1)

st.markdown("---")
st.markdown("## 🚦 KHUYẾN NGHỊ MUA")
buy_table = scan_df[scan_df["Đèn"].isin(["🟢", "🟡"])].copy()
buy_cols_show = ["symbol", "group", "price", "total_score", "ema9_ma20_slope", "slope_state", "rsi14", "obv_status", "OBV_POWER", "green_2_confirm", "dist_from_ema9_pct", "Đèn", "Khuyến nghị", "Vùng mua", "NAV gợi ý", "Lý do"]
if buy_table.empty:
    st.info("Không có mã đủ điều kiện mua theo Market-first.")
else:
    st.dataframe(buy_table[[c for c in buy_cols_show if c in buy_table.columns]].head(30), use_container_width=True, height=420)

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
sum_cols = st.columns(len(GROUP_ORDER))
for i, group_name in enumerate(GROUP_ORDER):
    cnt = int((scan_df["group"] == group_name).sum())
    with sum_cols[i]:
        st.metric(group_name, cnt)

# =========================================================
# GROUP TABLES
# =========================================================
DISPLAY_COLUMNS = ["symbol", "price", "E", "R", "O", "S", "RS", "total_score", "dry_score", "dry_label", "ema9_ma20_slope", "slope_state", "obv_status", "OBV_POWER", "status"]


def show_group_table(df: pd.DataFrame, group_name: str):
    sub = df[df["group"] == group_name].copy()
    if sub.empty:
        st.info("Không có mã")
        return
    if group_name in ["PULL ĐẸP", "PULL VỪA"]:
        cols = ["symbol", "price", "E", "R", "O", "S", "total_score", "dist_from_ema9_pct", "ema9_ma20_slope", "slope_state", "rsi_slope", "obv_status", "OBV_POWER", "status"]
    elif group_name == "MUA BREAK":
        cols = ["symbol", "price", "E", "R", "O", "S", "total_score", "breakout_ref", "ema9_ma20_slope", "slope_state", "obv_status", "OBV_POWER", "status"]
    else:
        cols = DISPLAY_COLUMNS
    cols = [c for c in cols if c in sub.columns]
    out = sub[cols].copy()
    out.index = range(len(out))
    st.dataframe(out, use_container_width=True, height=min(520, 80 + len(out) * 35))

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
early_df = filter_early_clean(scan_df)
if early_df.empty:
    st.info("Không có mã EARLY sạch")
else:
    early_cols = ["symbol", "price", "rsi14", "rsi_slope", "ema9_ma20_slope", "slope_state", "E", "R", "O", "S", "total_score", "obv_status", "OBV_POWER"]
    st.dataframe(early_df[[c for c in early_cols if c in early_df.columns]].reset_index(drop=True), use_container_width=True, height=300)

# =========================================================
# GÀ TĂNG TỐC SPECIAL
# =========================================================
st.markdown("---")
st.markdown("## 🚀 GÀ TĂNG TỐC – BẢNG RIÊNG")
accel_df = scan_df[(scan_df["ema9_ma20_slope"] > 2) & (scan_df["S"] >= 1) & (scan_df["R"] >= 1) & (scan_df["O"] >= 1) & (scan_df["price"] >= scan_df["ema9"])].copy()
if accel_df.empty:
    st.info("Chưa có mã gà tăng tốc rõ.")
else:
    accel_cols = ["symbol", "price", "group", "ema9", "ma20", "ema9_ma20_slope", "ema9_ma20_slope_change", "slope_state", "rsi14", "rsi_slope", "obv_status", "OBV_POWER", "E", "R", "O", "S", "total_score", "warning"]
    st.dataframe(accel_df[[c for c in accel_cols if c in accel_df.columns]].reset_index(drop=True), use_container_width=True, height=360)

# =========================================================
# PORTFOLIO
# =========================================================
st.markdown("---")
st.markdown("## 📊 QUẢN TRỊ DANH MỤC")
portfolio_text = st.text_area("Anh nhập: Mã,Giá mua,%NAV", placeholder="BAF,36600,4.5\nGVR,33217,12\nVHM,144300,3.5", height=130, key="portfolio_input")
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
    detail_cols = ["symbol", "data_date", "group", "price", "ema9", "ma20", "ema9_ma20_slope", "ema9_ma20_slope_change", "slope_state", "rsi14", "rsi_slope", "obv", "obv_ema9", "obv_status", "OBV_POWER", "E", "R", "O", "S", "RS", "rs5", "rs10", "total_score", "dry_score", "dry_label", "dist_from_ema9_pct", "pull_label", "breakout_ref", "status", "warning", "AUTO_BUY"]
    st.dataframe(scan_df[[c for c in detail_cols if c in scan_df.columns]].reset_index(drop=True), use_container_width=True, height=720)

# =========================================================
# GÀ 1KG
# =========================================================
st.markdown("---")
st.markdown("## 🐔 GÀ 1KG - TỰ ĐỘNG (CHỈ LẤY HÀNG CHUẨN)")
ga_1kg_df = scan_df[(scan_df["OBV_POWER"].fillna("").str.contains("MẠNH")) & (scan_df["rsi14"] >= 60) & (scan_df["rsi14"] <= 70) & (scan_df["ema9_ma20_slope"] > 2) & (scan_df["ema9"] > scan_df["ma20"])].copy()
if ga_1kg_df.empty:
    st.warning("Không có gà 1kg đạt chuẩn")
else:
    ga_1kg_df["ENTRY_Q"] = ga_1kg_df.apply(entry_quality_score, axis=1)
    ga_1kg_df = ga_1kg_df.sort_values(["ENTRY_Q", "total_score", "RS"], ascending=False).reset_index(drop=True)
    ga_1kg_df["ENTRY_TYPE"] = ga_1kg_df.apply(entry_type, axis=1)
    ga_1kg_df["ENTRY_SIGNAL"] = ga_1kg_df.apply(entry_signal, axis=1)
    ga_1kg_df["NAV_%"] = [nav_goi_y(i) for i in range(len(ga_1kg_df))]
    ga_1kg_df["ACTION"] = [action_goi_y(row, i) for i, row in ga_1kg_df.iterrows()]
    cols_show = ["symbol", "price", "rsi14", "ema9_ma20_slope", "obv_status", "OBV_POWER", "E", "R", "O", "S", "RS", "rs5", "rs10", "ENTRY_Q", "ENTRY_TYPE", "ENTRY_SIGNAL", "total_score", "AUTO_BUY", "NAV_%", "ACTION"]
    st.dataframe(ga_1kg_df[[c for c in cols_show if c in ga_1kg_df.columns]], use_container_width=True, height=400)

# =========================================================
# TOP RISK
# =========================================================
st.markdown("---")
st.markdown("## 🔺 CỔ PHIẾU CÓ DẤU HIỆU TẠO ĐỈNH / FOMO CUỐI SÓNG")
top_risk_df = build_top_risk_detector(scan_df)
if top_risk_df.empty:
    st.success("✅ Chưa phát hiện cổ phiếu có dấu hiệu tạo đỉnh rõ.")
else:
    st.dataframe(top_risk_df, use_container_width=True, hide_index=True)

# =========================================================
# EVOLUTION
# =========================================================
st.markdown("---")
st.markdown("## 🧬 EVOLUTION LEADERS")
try:
    evo_df, latest_days = save_evolution_history(scan_df)
    leaders_df = build_evolution_leaders(evo_df)
    if leaders_df.empty:
        st.info("Chưa có CP tiến hóa mạnh liên tục")
    else:
        st.dataframe(leaders_df, use_container_width=True, height=360)
except Exception as e:
    st.warning(f"Evolution chưa chạy được: {e}")
# =========================================================
# EVOLUTION FULL HISTORY TABLE
# =========================================================
st.markdown("---")
st.markdown("## 🧬 BẢNG TIẾN HÓA TOÀN BỘ CỔ PHIẾU")

try:
    evo_full = pd.read_csv(EVOLUTION_FILE)

    evo_pivot = evo_full.pivot_table(
        index="symbol",
        columns="date",
        values="group",
        aggfunc="first"
    )

    evo_pivot = evo_pivot.sort_index(axis=1)

    latest_cols = list(evo_pivot.columns)[-15:]
    evo_pivot = evo_pivot[latest_cols]

    group_color = {
        "GÀ TĂNG TỐC": "background-color: #b7f7c2",
        "CP MẠNH": "background-color: #d5f5d5",
        "MUA BREAK": "background-color: #d9ecff",
        "PULL ĐẸP": "background-color: #fff2b2",
        "PULL VỪA": "background-color: #fff7d6",
        "MUA EARLY": "background-color: #e8ddff",
        "TÍCH LŨY": "background-color: #eeeeee",
        "THEO DÕI": "background-color: #ffd6d6",
    }

    def color_group(val):
        return group_color.get(val, "")

    st.dataframe(
        evo_pivot.style.map(color_group),
        use_container_width=True,
        height=600
    )

except Exception as e:
    st.warning(f"Lỗi bảng evolution tổng: {e}")
# =========================================================
# MARKET ANALOG
# =========================================================
st.markdown("---")
st.subheader("🔮 DỰ BÁO THỊ TRƯỜNG - MARKET ANALOG V1")
try:
    if find_similar_periods is None or generate_market_prediction is None:
        st.warning("Chưa import được market_analog_engine.py")
    else:
        vnindex = pd.read_csv("vnindex_history.csv")
        vnindex["Date"] = pd.to_datetime(vnindex["Date"], dayfirst=True, errors="coerce")
        vnindex = vnindex.dropna(subset=["Date"])[["Date", "Close", "Volume"]]
        if vnindex.empty or len(vnindex) < 100:
            st.warning("VNINDEX tải về bị rỗng hoặc quá ít dữ liệu.")
        else:
            analog_window = 40 if market_real >= 8 else 30 if market_real >= 6 else 20
            analog_mode = "TREND MODE" if market_real >= 8 else "BALANCE MODE" if market_real >= 6 else "FAST MODE"
            similar_df = find_similar_periods(vnindex, window=analog_window, top_k=5)
            prediction = generate_market_prediction(similar_df)
            st.info(f"🧠 ANALOG MODE: {analog_mode} ({analog_window})")
            col1, col2, col3 = st.columns(3)
            col1.metric("Regime", prediction.get("regime", "-"))
            col2.metric("NAV gợi ý", prediction.get("nav", "-"))
            col3.metric("Confidence", f"{prediction.get('confidence', 0)}%")
            st.dataframe(similar_df, use_container_width=True)
except Exception as e:
    st.warning(f"Market Analog chưa chạy được: {e}")
