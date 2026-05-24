# =========================================================
# SCANNER GÀ CHIẾN V19 CLEAN
# Rebuild sạch từ bản V18.4 + SLOPE
# Giữ lõi: Market REAL/LIVE, Forecast, Pull/Break, Dryup,
# Gà tăng tốc, Gà 1KG, Portfolio, Analog, Top Risk, Evolution.
# =========================================================

import time
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
from vnstock import stock_historical_data
try:
    from market_analog_engine import find_similar_periods, generate_market_prediction
except Exception:
    find_similar_periods = None
    generate_market_prediction = None


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Scanner Gà Chiến V19 CLEAN",
    page_icon="🐔",
    layout="wide",
)

st.title("🐔 Scanner Gà Chiến V19 CLEAN")
st.caption("Bản clean: giữ lõi V18.4 + sửa sạch indent, dryup, OBV_POWER, Gà 1KG, Evolution")


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

DEFAULT_SUFFIX = ".VN"


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
    x["vol_ratio"] = np.where(
        x["vol_ma20"] != 0,
        x["volume"] / x["vol_ma20"],
        np.nan
    )

    x["rs5"] = ((x["close"] / x["close"].shift(5)) - 1) * 100
    x["rs10"] = ((x["close"] / x["close"].shift(10)) - 1) * 100

    x["pct_change"] = x["close"].pct_change() * 100
    x["green_candle"] = x["close"] > x["open"]
    x["green_1"] = x["green_candle"].shift(1)
    x["green_2"] = x["green_candle"]

    x["vol_up_confirm"] = x["volume"] > x["volume"].shift(1)
    x["rsi_confirm"] = (x["rsi14"] > 55) & (x["rsi14"] > x["rsi14"].shift(1))
    x["obv_confirm"] = (x["obv"] > x["obv_ema9"]) & (x["obv"] > x["obv"].shift(1))

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
        if len(vol_20) < 5:
            vol_slope = 0
        else:
            xs = np.arange(len(vol_20))
            vol_slope = np.polyfit(xs, vol_20, 1)[0]

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


# =========================================================
# BREAK QUALITY COMMENT
# =========================================================
def break_quality_comment(df, row):
    comments = []

    try:
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

        vol_now = row.get("volume", np.nan)
        vol_ma20 = row.get("vol_ma20", np.nan)

        if pd.notna(vol_now) and pd.notna(vol_ma20):
            if vol_now < vol_ma20 * 0.8:
                comments.append("volume co hẹp tốt")
            elif vol_now > vol_ma20 * 1.5:
                comments.append("volume breakout mạnh")

        rsi = row.get("rsi14", np.nan)
        if pd.notna(rsi):
            if 55 <= rsi <= 70:
                comments.append("RSI khỏe")
            elif rsi > 75:
                comments.append("RSI hơi nóng")

        obv = row.get("obv", np.nan)
        obv_ema9 = row.get("obv_ema9", np.nan)

        if pd.notna(obv) and pd.notna(obv_ema9):
            if obv >= obv_ema9:
                comments.append("OBV xác nhận")
            else:
                comments.append("OBV chưa xác nhận rõ")

        dist = row.get("dist_from_ema9_pct", np.nan)
        if pd.notna(dist):
            if dist <= 3:
                comments.append("break còn gần EMA9")
            elif dist >= 7:
                comments.append("break hơi nóng")

        if len(comments) == 0:
            return "Break cần theo dõi thêm"

        return " | ".join(comments)

    except Exception:
        return "Break chưa đủ dữ liệu"


# =========================================================
# GROUP CLASSIFY
# =========================================================
def classify_group(row: dict) -> str:
    price = row["price"]
    ema9_ = row["ema9"]
    vol_ = row["volume"]
    vol_ma20_ = row["vol_ma20"]
    total = row["total_score"]
    e = row["E"]
    r = row["R"]
    o = row["O"]
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
# GET STOCK DATA
# =========================================================
def get_stock_data(symbol, days=250):

    try:

        df = stock_historical_data(
            symbol=symbol,
            start_date="2024-01-01",
            end_date="2026-12-31",
            resolution="1D",
            type="stock",
            beautify=True,
            decor=False,
            source="DNSE"
        )

        if df is None or len(df) == 0:
            return pd.DataFrame()

        df.columns = [c.lower() for c in df.columns]

        return df.tail(days)

    except Exception as e:

        print(symbol, e)

        return pd.DataFrame()
# =========================================================
# ANALYZE ONE SYMBOL
# =========================================================
def analyze_symbol(symbol: str) -> dict | None:
    raw = get_stock_data(symbol)

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

    rs5_ = to_float(last["rs5"])
    rs10_ = to_float(last["rs10"])

    obv_ = to_float(last["obv"])
    obv_ema9_ = to_float(last["obv_ema9"])
    obv_prev = to_float(prev["obv"])

    vol_ = to_float(last["volume"])
    vol_ma20_ = to_float(last["vol_ma20"])
    vol_ratio_ = to_float(last.get("vol_ratio", np.nan))

    pct_change_ = to_float(last.get("pct_change", np.nan))

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
        "green_2_confirm": last["green_2_confirm"],
        "total_score": total_score,
        "dry_score": dry_score,
        "dry_label": dry_label,
    }

    row["OBV_POWER"] = classify_obv_power(row)
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
            print(f"Đang quét: {symbol}")

            item = analyze_symbol(symbol)

            print(f"Xong: {symbol}")
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
# MARKET REAL / LIVE / FORECAST
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
# NAV / BUY RECOMMENDATION
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
        zone = f"{round(ema9_, 0)} - {round(ema9_ * 1.01, 0)}" if pd.notna(ema9_) else f"{price}"
        action = "MUA PULL ĐẸP"
        return "🟢", action, zone, nav_suggestion(action, market_real), "Pull sát EMA9, OBV còn xanh"

    if group == "PULL VỪA" and obv_ok:
        zone = f"{round(ema9_ * 0.99, 0)} - {round(ema9_ * 1.01, 0)}" if pd.notna(ema9_) else f"{price}"
        action = "MUA PULL VỪA"
        return "🟡", action, zone, nav_suggestion(action, market_real), "Pull vừa, chỉ mua thăm dò"

    if group == "MUA EARLY" and score >= 3 and obv_ok and pd.notna(dist) and abs(dist) <= 2.5:
        action = "TEST EARLY"
        return "🟡", action, f"{round(price * 0.99, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Early sạch, test nhỏ"

    if group == "MUA BREAK" and obv_ok:
        action = "MUA BREAK"
        return "🟢", action, f"{round(price, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Break xác nhận, không đuổi quá xa"

    if group == "CP MẠNH" and score >= 5 and obv_ok:
        if pd.notna(dist) and dist > 4:
            return "🟡", "CHỜ PULL", f"Canh {round(ema9_, 0)} - {round(ema9_ * 1.02, 0)}", "0%", "CP mạnh nhưng xa EMA9"
        action = "CANH ADD CP MẠNH"
        return "🟡", action, f"{round(price * 0.99, 0)} - {round(price, 0)}", nav_suggestion(action, market_real), "CP mạnh, có thể add nhỏ"

    return "🔴", "KHÔNG MUA", "-", "0%", "Chưa đủ điểm mua"


def auto_buy_signal(row):
    if (
        row.get("pull_label", "") == "PULL ĐẸP"
        and "MẠNH" in str(row.get("OBV_POWER", ""))
        and row.get("rsi14", 0) >= 55
        and row.get("ema9_ma20_slope", 0) > 1
    ):
        return "🟢 MUA PULL"

    if (
        row.get("price", 0) >= row.get("breakout_ref", 0)
        and row.get("dist_from_ema9_pct", 999) <= 5
        and "MẠNH" in str(row.get("OBV_POWER", ""))
        and 55 <= row.get("rsi14", 0) <= 70
    ):
        return "🟢 MUA BREAK"

    if (
        row.get("group", "") == "MUA EARLY"
        and "MẠNH" in str(row.get("OBV_POWER", ""))
        and row.get("rsi14", 0) >= 50
        and row.get("ema9_ma20_slope", 0) >= 0
    ):
        return "🟡 TEST EARLY"

    return "⚪ CHỜ"


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
# TOP PICKS / FILTERS
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


def entry_type(row):
    if row["rsi14"] >= 65 and row["ema9_ma20_slope"] > 3:
        return "BREAK"
    if 55 <= row["rsi14"] < 65 and row["ema9_ma20_slope"] > 2:
        return "PULL"
    return "EARLY"


def entry_signal(row):
    if row["ENTRY_TYPE"] == "BREAK":
        if row["rsi14"] <= 70:
            return "🔥 MUA NGAY"
        return "🔵 CHỜ PULL"
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


def build_top_risk_detector(base_df):
    if base_df is None or base_df.empty:
        return pd.DataFrame()

    df = base_df.copy()
    rows = []

    for _, row in df.iterrows():
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
                reasons.append("🔥 Nến FOMO cuối sóng - tăng mạnh + vol cực lớn")
            elif dist >= 5 and vol >= 1.8 and pct >= 3:
                score += 5
                reasons.append("⚠️ Nến tăng nóng + vol cao bất thường")

        if pd.notna(rsi):
            if rsi >= 80:
                score += 3
                reasons.append("RSI quá nóng ≥80")
            elif rsi >= 75:
                score += 2
                reasons.append("RSI nóng ≥75")
            elif rsi >= 70:
                score += 1
                reasons.append("RSI vào vùng cao ≥70")

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

        if obv_text:
            if "YẾU" in obv_text or "WEAK" in obv_text:
                score += 3
                reasons.append("OBV yếu")
            elif "VỪA" in obv_text or "TRUNG" in obv_text:
                score += 1
                reasons.append("OBV không còn thật mạnh")

        if group_text:
            if "GÀ TĂNG TỐC" in group_text:
                score += 2
                reasons.append("Đang ở nhóm Gà tăng tốc")
            elif "CP MẠNH" in group_text:
                score += 1
                reasons.append("Đang ở nhóm CP mạnh")

        if score >= 7:
            if score >= 10:
                level = "🔴 RỦI RO TẠO ĐỈNH CAO"
                action = "Không mua đuổi / canh hạ tỷ trọng / siết stop"
            else:
                level = "🟠 CẢNH BÁO NÓNG"
                action = "Chỉ giữ nếu trend còn tốt, không mua mới"

            rows.append({
                "symbol": symbol,
                "pct": round(pct, 2) if pd.notna(pct) else None,
                "dist": round(dist, 2) if pd.notna(dist) else None,
                "vol": round(vol, 2) if pd.notna(vol) else None,
                "rsi": round(rsi, 2) if pd.notna(rsi) else None,
                "top_risk_score": score,
                "risk_level": level,
                "reason": " | ".join(reasons),
                "action": action,
            })

    out = pd.DataFrame(rows)

    if out.empty:
        return out

    return out.sort_values(by="top_risk_score", ascending=False).reset_index(drop=True)


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
buy_signal_cols = scan_df.apply(
    lambda r: pd.Series(
        buy_recommendation(r, market_real),
        index=["Đèn", "Khuyến nghị", "Vùng mua", "NAV gợi ý", "Lý do"]
    ),
    axis=1
)

scan_df = pd.concat([scan_df, buy_signal_cols], axis=1)

# =====================================================
# BREAK QUALITY COMMENT
# =====================================================
break_comments = []
for _, row in scan_df.iterrows():
    symbol = row["symbol"]
    raw_df = download_symbol_data(symbol)

    if raw_df.empty:
        break_comments.append("")
        continue

    raw_df = build_indicators(raw_df)
    comment = break_quality_comment(raw_df, row)
    break_comments.append(comment)

scan_df["BREAK_COMMENT"] = break_comments

st.markdown("---")
st.markdown("## 🚦 KHUYẾN NGHỊ MUA")

buy_table = scan_df[scan_df["Đèn"].isin(["🟢", "🟡"])].copy()

buy_cols_show = [
    "symbol", "group", "price", "total_score",
    "ema9_ma20_slope", "slope_state",
    "rsi14", "obv_status", "OBV_POWER", "green_2_confirm", "dist_from_ema9_pct",
    "Đèn", "Khuyến nghị", "Vùng mua", "NAV gợi ý", "Lý do"
]

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
    "symbol", "price", "E", "R", "O", "S", "RS", "total_score",
    "dry_score", "dry_label",
    "ema9_ma20_slope", "slope_state", "obv_status", "OBV_POWER", "status"
]


def show_group_table(df: pd.DataFrame, group_name: str, return_df=False):
    sub = df[df["group"] == group_name].copy()
    if return_df:
        return sub
    if sub.empty:
        st.info("Không có mã")
        return

    if group_name in ["PULL ĐẸP", "PULL VỪA"]:
        cols = [
            "symbol", "price", "E", "R", "O", "S", "total_score",
            "dist_from_ema9_pct", "ema9_ma20_slope", "slope_state",
            "rsi_slope", "obv_status", "OBV_POWER", "status"
        ]

    elif group_name == "MUA BREAK":
        cols = [
            "symbol", "price", "E", "R", "O", "S", "total_score",
            "breakout_ref", "BREAK_COMMENT", "ema9_ma20_slope", "slope_state",
            "obv_status", "OBV_POWER", "status"
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

early_df = filter_early_clean(scan_df)

if early_df.empty:
    st.info("Không có mã EARLY sạch")
else:
    early_cols = [
        "symbol", "price", "rsi14", "rsi_slope",
        "ema9_ma20_slope", "slope_state",
        "E", "R", "O", "S", "total_score", "obv_status",
        "OBV_POWER"
    ]

    out = early_df.copy()
    out.index = range(len(out))
    early_cols = [c for c in early_cols if c in out.columns]
    out = out[early_cols]
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
        "rsi14", "rsi_slope", "obv_status", "OBV_POWER",
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
        "ema9_ma20_slope",
        "ema9_ma20_slope_change",
        "slope_state",
        "rsi14", "rsi_slope",
        "obv", "obv_ema9",
        "obv_status",
        "OBV_POWER",
        "E", "R", "O", "S", "RS",
        "rs5", "rs10",
        "total_score",
        "dry_score", "dry_label",
        "dist_from_ema9_pct",
        "pull_label",
        "breakout_ref",
        "status",
        "warning",
        "AUTO_BUY",
    ]

    detail_cols = [c for c in detail_cols if c in scan_df.columns]
    detail_df = scan_df[detail_cols].copy()
    detail_df.index = range(len(detail_df))

    st.dataframe(
        detail_df,
        use_container_width=True,
        height=720
    )


# ============================================
# GÀ 1KG – AUTO SELECT + XẾP HẠNG + NAV
# ============================================
st.markdown("---")
st.markdown("## 🐔 GÀ 1KG - TỰ ĐỘNG (CHỈ LẤY HÀNG CHUẨN)")

ga_1kg_df = scan_df[
    (scan_df["OBV_POWER"].fillna("").str.contains("MẠNH"))
    & (scan_df["rsi14"] >= 60)
    & (scan_df["rsi14"] <= 70)
    & (scan_df["ema9_ma20_slope"] > 2)
    & (scan_df["ema9"] > scan_df["ma20"])
].copy()

if ga_1kg_df.empty:
    st.warning("Không có gà 1kg đạt chuẩn")
else:
    ga_1kg_df["ENTRY_Q"] = ga_1kg_df.apply(entry_quality_score, axis=1)
    ga_1kg_df = ga_1kg_df.sort_values(
        by=["ENTRY_Q", "total_score", "RS"],
        ascending=False
    ).reset_index(drop=True)

    ga_1kg_df["ENTRY_TYPE"] = ga_1kg_df.apply(entry_type, axis=1)
    ga_1kg_df["ENTRY_SIGNAL"] = ga_1kg_df.apply(entry_signal, axis=1)
    ga_1kg_df["NAV_%"] = [nav_goi_y(i) for i in range(len(ga_1kg_df))]
    ga_1kg_df["ACTION"] = [
        action_goi_y(row, i)
        for i, row in ga_1kg_df.iterrows()
    ]

    cols_show = [
        "symbol", "price",
        "rsi14", "ema9_ma20_slope",
        "obv_status", "OBV_POWER",
        "E", "R", "O", "S", "RS",
        "rs5", "rs10",
        "ENTRY_Q",
        "ENTRY_TYPE",
        "ENTRY_SIGNAL",
        "total_score",
        "AUTO_BUY",
        "NAV_%", "ACTION"
    ]

    cols_show = [c for c in cols_show if c in ga_1kg_df.columns]
    st.dataframe(ga_1kg_df[cols_show], use_container_width=True, height=400)


# =========================================================
# TOP RISK DETECTOR
# =========================================================
st.markdown("---")
st.markdown("## 🔺 CỔ PHIẾU CÓ DẤU HIỆU TẠO ĐỈNH / FOMO CUỐI SÓNG")

try:
    top_risk_df = build_top_risk_detector(scan_df)

    if top_risk_df.empty:
        st.success("✅ Chưa phát hiện cổ phiếu có dấu hiệu tạo đỉnh rõ.")
    else:
        st.dataframe(
            top_risk_df,
            use_container_width=True,
            hide_index=True
        )
except Exception as e:
    st.warning(f"TOP RISK detector chưa chạy được: {e}")


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

        vnindex["Date"] = pd.to_datetime(
            vnindex["Date"],
            dayfirst=True,
            errors="coerce"
        )

        vnindex = vnindex.dropna(subset=["Date"])
        vnindex = vnindex[["Date", "Close", "Volume"]]

        if vnindex.empty or len(vnindex) < 100:
            st.warning("VNINDEX tải về bị rỗng hoặc quá ít dữ liệu.")
        else:
            st.success("Đã tải dữ liệu VNINDEX thành công")

            if market_real >= 8:
                analog_window = 40
                analog_mode = "TREND MODE"
            elif market_real >= 6:
                analog_window = 30
                analog_mode = "BALANCE MODE"
            else:
                analog_window = 20
                analog_mode = "FAST MODE"

            similar_df = find_similar_periods(
                vnindex,
                window=analog_window,
                top_k=5
            )

            prediction = generate_market_prediction(similar_df)

            st.info(f"🧠 ANALOG MODE: {analog_mode} ({analog_window})")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("REGIME", prediction.get("regime", "N/A"))

            with col2:
                st.metric("NAV GỢI Ý", prediction.get("nav", "N/A"))

            with col3:
                st.metric("CONFIDENCE", f"{prediction.get('confidence', 0)}%")

            with st.expander("Xem các đoạn lịch sử tương đồng"):
                st.dataframe(similar_df, use_container_width=True)

except Exception as e:
    st.warning(f"Market Analog tạm lỗi, app vẫn chạy bình thường: {e}")


# =========================================================
# EVOLUTION ENGINE
# =========================================================
try:
    from evolution_engine import save_evolution_history, build_evolution_leaders

    full_df, latest_days = save_evolution_history(scan_df)

    st.markdown("---")
    st.markdown("## 🧬 TIẾN HÓA NHÓM CỔ PHIẾU - 15 PHIÊN GẦN NHẤT")

    pivot = full_df.pivot_table(
        index="symbol",
        columns="date",
        values="group",
        aggfunc="first"
    )

    pivot = pivot.sort_index(axis=1)

    st.dataframe(
        pivot,
        use_container_width=True,
        height=500
    )

    st.markdown("---")
    st.markdown("## 🚀 CỔ PHIẾU TIẾN HÓA CHỌN LỌC")

    leaders_df = build_evolution_leaders(full_df)

    if leaders_df.empty:
        st.info("Chưa có cổ phiếu tiến hóa mạnh")
    else:
        st.dataframe(
            leaders_df,
            use_container_width=True,
            height=300
        )

except Exception as e:
    st.warning(f"Evolution engine tạm lỗi, app vẫn chạy bình thường: {e}")


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

