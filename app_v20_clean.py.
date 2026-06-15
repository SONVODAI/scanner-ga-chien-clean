# =========================================================
# SCANNER GÀ CHIẾN V19.2 - SAFE MODE REALTIME UNIFIED
# Viết lại sạch 100% từ bản V18.4-Lite
# Mục tiêu:
#   1) Một nguồn dữ liệu sống duy nhất: scan_df
#   2) Live price được bơm vào cây nến cuối TRƯỚC khi tính indicator
#   3) Market / bảng nhóm / bảng chi tiết / bảng hành động / evolution dùng chung scan_df
#   4) Không còn tình trạng price đúng nhưng group/evo/detail lệch phaF
# =========================================================

import os
import time
import base64
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

try:
    import yfinance as yf
except Exception:
    yf = None

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Scanner Gà Chiến V19.2 Safe Mode",
    page_icon="🐔",
    layout="wide",
)

st.title("🐔 Scanner Gà Chiến V19.2 - Safe Mode Realtime Unified")
st.caption("Một pipeline duy nhất + SAFE MODE: live lỗi thì dùng D1, một mã lỗi không làm sập app")

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
    "EVF", "SAB", "VPL", "PDR", "DPG", "NHA", "HDC", "NTL", "HHS",
    "NLG", "KDH", "HUT",
])))

# =========================================================
# CONFIG
# =========================================================
EVOLUTION_FILE = "group_evolution_history.csv"
YAHOO_SUFFIX = ".VN"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Nếu có GITHUB_TOKEN trong Streamlit secrets thì evolution sẽ được lưu bền trên GitHub.
# Nếu không có token, app vẫn chạy bằng file local như bản cũ.
GITHUB_REPO_OWNER = "SONVODAI"
GITHUB_REPO_NAME = "scanner-ga-chien-clean"
GITHUB_EVO_PATH = EVOLUTION_FILE

# Daily data cache giữ nhẹ để không spam vnstock.
# Live price cache ngắn để bảng không lệch quá lâu.
DAILY_CACHE_TTL = 20 * 60
LIVE_CACHE_TTL = 90

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

# =========================================================
# HELPERS
# =========================================================
def to_float(value, default=np.nan):
    """Ép mọi kiểu dữ liệu về float an toàn.

    Mục tiêu: chặn các giá trị bẩn từ API như None, "", "--", Series,
    DataFrame, ndarray, inf... để không làm sập app khi gán vào candle cuối.
    """
    try:
        if value is None:
            return default

        if isinstance(value, pd.DataFrame):
            if value.empty:
                return default
            value = value.iloc[-1, -1]

        if isinstance(value, pd.Series):
            if len(value) == 0:
                return default
            value = value.iloc[-1]

        if isinstance(value, np.ndarray):
            if value.size == 0:
                return default
            value = value.flatten()[-1]

        if isinstance(value, str):
            value = value.strip()
            if value in ["", "--", "nan", "NaN", "None", "N/A", "null"]:
                return default
            value = value.replace(",", "")

        out = float(value)
        if pd.isna(out) or np.isinf(out):
            return default
        return out

    except Exception:
        return default


def is_valid_price(value) -> bool:
    v = to_float(value)
    return pd.notna(v) and v > 0


def safe_max_number(*values):
    nums = [to_float(v) for v in values]
    nums = [v for v in nums if pd.notna(v)]
    return max(nums) if nums else np.nan


def safe_min_number(*values):
    nums = [to_float(v) for v in values]
    nums = [v for v in nums if pd.notna(v)]
    return min(nums) if nums else np.nan


def log_runtime_error(symbol: str, stage: str, error):
    """Ghi lỗi mềm ra CSV để app không chết vì một mã hoặc một API lỗi."""
    try:
        row = pd.DataFrame([{
            "time": vn_time_str("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "stage": stage,
            "error": str(error),
        }])
        file_name = "runtime_error_log.csv"
        if os.path.exists(file_name):
            old = pd.read_csv(file_name)
            row = pd.concat([old, row], ignore_index=True).tail(300)
        row.to_csv(file_name, index=False)
    except Exception:
        pass

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


def slope_state_text(slope: float) -> str:
    if pd.isna(slope):
        return ""
    if slope > 2:
        return "🟢 Tăng tốc"
    if slope > 0:
        return "🟡 Ổn định"
    return "🔴 Yếu"


def vn_now() -> datetime:
    """Luôn lấy giờ Việt Nam, tránh lệch UTC trên server Streamlit Cloud."""
    return datetime.now(VN_TZ)


def today_str() -> str:
    return vn_now().strftime("%Y-%m-%d")


def vn_time_str(fmt: str = "%d/%m/%Y %H:%M:%S") -> str:
    return vn_now().strftime(fmt)

# =========================================================
# DATA DOWNLOAD
# =========================================================
@st.cache_data(ttl=DAILY_CACHE_TTL, show_spinner=False)
def download_symbol_data(symbol: str) -> pd.DataFrame:
    """Tải dữ liệu D1. Chỉ cache ở tầng dữ liệu nền, không cache analyze_symbol."""
    try:
        from vnstock import stock_historical_data

        df = stock_historical_data(
            symbol=symbol,
            start_date="2025-01-01",
            end_date=today_str(),
            resolution="1D",
            type="stock",
            beautify=True,
        )

        if df is None or len(df) == 0:
            return pd.DataFrame()

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
        needed = ["date", "open", "high", "low", "close", "volume"]
        for c in needed:
            if c not in df.columns:
                return pd.DataFrame()

        df = df[needed].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=["date", "close"]).sort_values("date")
        return df.reset_index(drop=True)

    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=LIVE_CACHE_TTL, show_spinner=False)
def fetch_live_price(symbol: str) -> dict:
    """
    Lấy giá live 15m từ yfinance.
    Trả về dict để sau này dễ mở rộng.
    Quan trọng: volume ở đây là tổng volume intraday YF nếu có, không lấy riêng cây 15m cuối.
    """
    if yf is None:
        return {"price": np.nan, "volume": np.nan, "source": "NO_YF", "ts": ""}

    ticker = f"{symbol}{YAHOO_SUFFIX}"

    try:
        data = yf.download(
            ticker,
            period="1d",
            interval="15m",
            progress=False,
            auto_adjust=False,
            threads=False,
        )

        source = "YF_15M"

        if data is None or data.empty:
            data = yf.download(
                ticker,
                period="5d",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
            )
            source = "YF_1D_FALLBACK"

        if data is None or data.empty:
            return {"price": np.nan, "volume": np.nan, "source": "NO_DATA", "ts": ""}

        # Xử lý cả trường hợp columns MultiIndex.
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [c[0] for c in data.columns]

        if "Close" not in data.columns:
            return {"price": np.nan, "volume": np.nan, "source": "NO_CLOSE", "ts": ""}

        close_series = pd.to_numeric(data["Close"], errors="coerce").dropna()
        if close_series.empty:
            return {"price": np.nan, "volume": np.nan, "source": "BAD_CLOSE", "ts": ""}

        live_price = to_float(close_series.iloc[-1])
        live_volume = np.nan
        if "Volume" in data.columns:
            vol_series = pd.to_numeric(data["Volume"], errors="coerce").dropna()
            if not vol_series.empty:
                live_volume = to_float(vol_series.sum())

        if pd.isna(live_price) or live_price <= 0:
            return {"price": np.nan, "volume": np.nan, "source": "BAD_PRICE", "ts": ""}

        try:
            ts = str(data.index[-1])
        except Exception:
            ts = ""

        return {
            "price": live_price,
            "volume": live_volume,
            "source": source,
            "ts": ts,
        }

    except Exception:
        return {"price": np.nan, "volume": np.nan, "source": "ERROR", "ts": ""}


# =========================================================
# REALTIME INJECTION - FIX FINAL
# =========================================================
def inject_live_into_daily(raw: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, dict]:
    """Bơm live price vào candle cuối theo chế độ an toàn.

    Nguyên tắc V19.2 SAFE:
    - Live lỗi / dữ liệu bẩn / giá rỗng => dùng D1, không crash.
    - Chỉ gán vào df sau khi final_price đã được kiểm tra là số hợp lệ.
    - Bất kỳ lỗi nào trong injection đều fallback về daily dataframe.
    """
    live = {
        "price": np.nan,
        "volume": np.nan,
        "source": "INIT",
        "ts": "",
        "daily_last_close_before_live": np.nan,
    }

    try:
        live = fetch_live_price(symbol)
        if not isinstance(live, dict):
            live = {"price": np.nan, "volume": np.nan, "source": "BAD_LIVE_DICT", "ts": ""}

        df = raw.copy().sort_values("date").reset_index(drop=True)
        if df.empty:
            live["source"] = "EMPTY_DAILY"
            return df, live

        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        df["is_live_adjusted"] = False
        last_idx = df.index[-1]

        last_close = to_float(df.loc[last_idx, "close"])
        last_open = to_float(df.loc[last_idx, "open"])
        last_high = to_float(df.loc[last_idx, "high"])
        last_low = to_float(df.loc[last_idx, "low"])
        last_volume = to_float(df.loc[last_idx, "volume"])

        live_price = to_float(live.get("price", np.nan))
        live_volume = to_float(live.get("volume", np.nan))
        live["daily_last_close_before_live"] = last_close

        now_vn = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh")
        market_closed = (now_vn.hour > 15) or (now_vn.hour == 15 and now_vn.minute >= 0)

        # CASE 1: không có live hợp lệ -> giữ nguyên candle D1, không đánh dấu live.
        if not is_valid_price(live_price):
            live["price"] = last_close
            live["volume"] = last_volume
            live["source"] = "NO_DATA"
            return df.reset_index(drop=True), live

        # CASE 2: có live hợp lệ.
        if market_closed and is_valid_price(last_close):
            # Sau giờ đóng cửa: nếu live gần sát D1 thì ưu tiên D1 để tránh lệch dữ liệu.
            if abs(live_price - last_close) <= max(50, last_close * 0.003):
                final_price = last_close
                final_volume = safe_max_number(last_volume, live_volume)
                live["source"] = "D1_FINAL"
            else:
                final_price = live_price
                final_volume = safe_max_number(last_volume, live_volume)
                live["source"] = live.get("source", "YF_15M") or "YF_15M"
        else:
            final_price = live_price
            final_volume = safe_max_number(last_volume, live_volume)

        final_price = to_float(final_price)

        # Chốt chặn cuối: tuyệt đối không gán giá bẩn vào cột close.
        if not is_valid_price(final_price):
            live["price"] = last_close
            live["volume"] = last_volume
            live["source"] = "BAD_FINAL_PRICE"
            return df.reset_index(drop=True), live

        final_high = safe_max_number(last_high, last_open, final_price)
        final_low = safe_min_number(last_low, last_open, final_price)

        if not is_valid_price(final_high):
            final_high = final_price
        if not is_valid_price(final_low):
            final_low = final_price

        df.loc[last_idx, "close"] = float(final_price)
        df.loc[last_idx, "high"] = float(final_high)
        df.loc[last_idx, "low"] = float(final_low)

        if pd.notna(final_volume) and final_volume > 0:
            df.loc[last_idx, "volume"] = float(final_volume)

        df.loc[last_idx, "is_live_adjusted"] = True

        live["price"] = final_price
        live["volume"] = final_volume

        return df.reset_index(drop=True), live

    except Exception as e:
        log_runtime_error(symbol, "inject_live_into_daily", e)
        try:
            df = raw.copy().sort_values("date").reset_index(drop=True)
            if not df.empty:
                df["is_live_adjusted"] = False
                last = df.iloc[-1]
                live = {
                    "price": to_float(last.get("close", np.nan)),
                    "volume": to_float(last.get("volume", np.nan)),
                    "source": "SAFE_MODE_D1",
                    "ts": "",
                    "daily_last_close_before_live": to_float(last.get("close", np.nan)),
                }
                return df, live
        except Exception as e2:
            log_runtime_error(symbol, "inject_fallback", e2)

        live = {
            "price": np.nan,
            "volume": np.nan,
            "source": "SAFE_MODE_EMPTY",
            "ts": "",
            "daily_last_close_before_live": np.nan,
        }
        return pd.DataFrame(), live

# =========================================================
# INDICATORS
# =========================================================
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
    x["rsi_slope"] = x["rsi14"] - x["rsi14"].shift(3)

    x["obv"] = calc_obv(x["close"], x["volume"])
    x["obv_ema9"] = ema(x["obv"], 9)

    x["vol_ma20"] = sma(x["volume"], 20)

    x["rs5"] = ((x["close"] / x["close"].shift(5)) - 1) * 100
    x["rs10"] = ((x["close"] / x["close"].shift(10)) - 1) * 100

    x["green_candle"] = x["close"] > x["open"]
    x["green_2_confirm"] = np.where(
        (
            x["green_candle"].shift(1)
            & x["green_candle"]
            & (x["volume"] > x["volume"].shift(1))
            & (x["rsi14"] > 55)
            & (x["rsi14"] > x["rsi14"].shift(1))
            & (x["obv"] > x["obv_ema9"])
            & (x["obv"] > x["obv"].shift(1))
        ),
        "🟢 GREEN 2",
        "",
    )

    return x


# =========================================================
# SCORE ENGINE
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
def calc_volume_score(close_, open_, volume_, vol_ma20_):
    """
    Đánh giá chất lượng volume.
    Không đo volume lớn hay nhỏ đơn thuần.
    Đo volume có đi cùng giá đúng hướng hay không.
    """

    if (
        pd.isna(close_)
        or pd.isna(open_)
        or pd.isna(volume_)
        or pd.isna(vol_ma20_)
        or vol_ma20_ <= 0
    ):
        return 0

    vol_ratio = volume_ / vol_ma20_

    # Giá tăng + vol lớn
    if close_ > open_ and vol_ratio >= 1.2:
        return 2

    # Giá tăng + vol trung bình
    if close_ > open_ and vol_ratio >= 0.8:
        return 1

    # Giá giảm mạnh nhưng vol lớn
    if close_ < open_ and vol_ratio >= 1.2:
        return -2

    # Giá giảm nhẹ nhưng vol thấp
    if close_ < open_ and vol_ratio < 0.8:
        return 1

    return 0

# =========================================================
# LABELS / GROUPS
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


def classify_group(row: dict) -> str:
    price = row["price"]
    ema9_ = row["ema9"]
    vol_ = row["volume"]
    vol_ma20_ = row["vol_ma20"]
    total = row["total_score"]
    V = row["V"]
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
        and total >= 7
        and e >= 1
        and r >= 1
        and o >= 1
        and V >= 1
    ):
        return "GÀ TĂNG TỐC"

    if pull_label == "PULL ĐẸP":
        return "PULL ĐẸP"

    if pull_label == "PULL VỪA":
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
        leader
        and pd.notna(dist_from_ema9)
        and dist_from_ema9 > 1.5
        and e == 2
        and r >= 1
        and o >= 1
        and V >= 1
    ):
        return "CP MẠNH"

    if not leader:
        if total <= 1:
            return "THEO DÕI"
        if total == 2:
            return "TÍCH LŨY"
        return "MUA EARLY"

    return "MUA EARLY"


# =========================================================
# ANALYZE ONE SYMBOL
# =========================================================
def analyze_symbol(symbol: str) -> dict | None:
    raw = download_symbol_data(symbol)
    if raw.empty or len(raw) < 40:
        return None

    # Sửa bệnh chính: bơm live vào D1 trước khi tính indicator.
    live_df, live_info = inject_live_into_daily(raw, symbol)
    if live_df.empty or len(live_df) < 40:
        return None

    df = build_indicators(live_df)
    if df.empty or len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = to_float(last["close"])
    daily_price_before_live = live_info.get("daily_last_close_before_live", np.nan)

    ema9_ = to_float(last["ema9"])
    ma20_ = to_float(last["ma20"])
    ema9_prev = to_float(prev["ema9"])

    slope_ = to_float(last["ema9_ma20_slope"])
    slope_change_ = to_float(last["ema9_ma20_slope_change"])

    rsi_ = to_float(last["rsi14"])
    rsi_slope_ = to_float(last["rsi_slope"])

    obv_ = to_float(last["obv"])
    obv_ema9_ = to_float(last["obv_ema9"])
    obv_prev = to_float(prev["obv"])

    vol_ = to_float(last["volume"])
    vol_ma20_ = to_float(last["vol_ma20"])

    rs5_ = to_float(last["rs5"])
    rs10_ = to_float(last["rs10"])

    breakout_ref = to_float(df["high"].iloc[-21:-1].max())

    dist_from_ema9 = np.nan
    if pd.notna(price) and pd.notna(ema9_) and ema9_ != 0:
        dist_from_ema9 = (price / ema9_ - 1) * 100

    E = calc_price_score(price, ema9_, ma20_, ema9_prev)
    R = calc_rsi_score(rsi_, rsi_slope_)
    O = calc_obv_score(obv_, obv_ema9_, obv_prev)
    S = calc_slope_score(slope_, slope_change_)
    RS = calc_rs_score(rs5_, rs10_)

    V = calc_volume_score(
    close_=last["close"],
    open_=last["open"],
    volume_=vol_,
    vol_ma20_=vol_ma20_,
)

    total_score = E + R + O + S + RS + V
    
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
            "date": last.get("date", None),
            "price": safe_round(price, 0),
            "daily_price_before_live": safe_round(daily_price_before_live, 0),
            "live_source": live_info.get("source", ""),
            "live_ts": live_info.get("ts", ""),
            "is_live_adjusted": bool(last.get("is_live_adjusted", False)),
            "ema9": safe_round(ema9_, 2),
            "ma20": safe_round(ma20_, 2),
            "ema9_ma20_slope": safe_round(slope_, 2),
            "ema9_ma20_slope_change": safe_round(slope_change_, 2),
            "slope_state": slope_state_text(slope_),
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
            "V": V,
            "rs5": safe_round(rs5_, 2),
            "rs10": safe_round(rs10_, 2),
            "green_2_confirm": str(last.get("green_2_confirm", "")),
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
    """Quét watchlist theo chế độ chịu lỗi.

    Một mã lỗi không được phép làm sập toàn bộ scanner.
    Lỗi được ghi vào runtime_error_log.csv, các mã còn lại vẫn chạy bình thường.
    """
    rows = []
    progress = st.progress(0)
    total = len(symbols)

    for i, symbol in enumerate(symbols):
        try:
            item = analyze_symbol(symbol)
            if item is not None:
                rows.append(item)
        except Exception as e:
            log_runtime_error(symbol, "analyze_symbol", e)
            continue
        finally:
            try:
                progress.progress((i + 1) / total)
            except Exception:
                pass

    progress.empty()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["group_rank"] = df["group"].map({g: i for i, g in enumerate(GROUP_ORDER)}).fillna(99)

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
    ascending_map = {
        "group_rank": True,
        "total_score": False,
        "S": False,
        "E": False,
        "O": False,
        "R": False,
        "ema9_ma20_slope": False,
    }

    if existing_sort_cols:
        ascending = [ascending_map.get(c, False) for c in existing_sort_cols]
        df = df.sort_values(by=existing_sort_cols, ascending=ascending).reset_index(drop=True)

    return df

# =========================================================
# MARKET SCORE - DÙNG CHUNG scan_df
# =========================================================
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


def calc_market_live(df: pd.DataFrame) -> float:
    total = len(df)
    if total == 0:
        return 0.0

    live_ok_ratio = len(df[df["is_live_adjusted"] == True]) / total if "is_live_adjusted" in df.columns else 0
    green_price_ratio = len(df[df["price"] >= df["daily_price_before_live"]]) / total if "daily_price_before_live" in df.columns else 0

    e_ratio = len(df[df["E"] >= 1]) / total
    o_ratio = len(df[df["O"] >= 1]) / total
    s_ratio = len(df[df["S"] >= 1]) / total

    accel = len(df[df["group"] == "GÀ TĂNG TỐC"])
    breakout = len(df[df["group"] == "MUA BREAK"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])

    score = (
        e_ratio * 2.5
        + o_ratio * 2.0
        + s_ratio * 2.0
        + green_price_ratio * 2.0
        + live_ok_ratio * 1.0
        + min(accel / 6, 1) * 1.5
        + min(breakout / 8, 1) * 1.0
        + min(pull_good / 6, 1) * 1.0
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
# BUY RECOMMENDATION
# =========================================================
def nav_suggestion(action: str, market_real: float) -> str:
    if market_real < 6:
        return "0%"

    if action in ["MUA GÀ TĂNG TỐC", "MUA PULL ĐẸP", "MUA BREAK"]:
        return "15-20% NAV" if market_real >= 8 else "5-10% NAV"

    if action in ["MUA PULL VỪA", "CANH ADD CP MẠNH", "TEST EARLY"]:
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
        return "🟡", action, zone, nav_suggestion(action, market_real), "Pull vừa, mua thăm dò"

    if group == "MUA BREAK" and obv_ok:
        action = "MUA BREAK"
        return "🟢", action, f"{round(price, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Break xác nhận, không đuổi quá xa"

    if group == "MUA EARLY" and score >= 3 and obv_ok and pd.notna(dist) and abs(dist) <= 2.5:
        action = "TEST EARLY"
        return "🟡", action, f"{round(price * 0.99, 0)} - {round(price * 1.01, 0)}", nav_suggestion(action, market_real), "Early sạch, test nhỏ"

    if group == "CP MẠNH" and score >= 5 and obv_ok:
        if pd.notna(dist) and dist > 4:
            return "🟡", "CHỜ PULL", f"Canh {round(ema9_, 0)} - {round(ema9_ * 1.02, 0)}", "0%", "CP mạnh nhưng xa EMA9"
        action = "CANH ADD CP MẠNH"
        return "🟡", action, f"{round(price * 0.99, 0)} - {round(price, 0)}", nav_suggestion(action, market_real), "CP mạnh, có thể add nhỏ"

    return "🔴", "KHÔNG MUA", "-", "0%", "Chưa đủ điểm mua"


def build_buy_table(scan_df: pd.DataFrame, market_real: float) -> pd.DataFrame:
    rows = []

    for _, row in scan_df.iterrows():
        light, action, zone, nav, reason = buy_recommendation(row, market_real)
        rows.append({
            "Mã": row["symbol"],
            "Đèn": light,
            "Hành động": action,
            "Nhóm": row["group"],
            "Giá": row["price"],
            "Vùng mua": zone,
            "NAV": nav,
            "Điểm": row["total_score"],
            "Slope": row["ema9_ma20_slope"],
            "RSI": row["rsi14"],
            "OBV": row["obv_status"],
            "Dist EMA9%": row["dist_from_ema9_pct"],
            "Live": "✅" if row.get("is_live_adjusted", False) else "",
            "Lý do": reason,
            "Cảnh báo": row["warning"],
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["rank_action"] = out["Hành động"].map({
        "MUA PULL ĐẸP": 0,
        "MUA BREAK": 1,
        "MUA GÀ TĂNG TỐC": 2,
        "MUA PULL VỪA": 3,
        "TEST EARLY": 4,
        "CANH ADD CP MẠNH": 5,
        "CHỜ PULL": 6,
        "KHÔNG MUA": 9,
    }).fillna(9)

    out = out.sort_values(
        by=["rank_action", "Điểm", "Slope"],
        ascending=[True, False, False],
    ).drop(columns=["rank_action"])

    return out


# =========================================================
# EVOLUTION ENGINE - HIỂN THỊ REALTIME, LƯU BỀN THEO PHIÊN
# =========================================================
def get_github_token():
    try:
        return st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        return None


def read_evolution_history() -> pd.DataFrame:
    """
    Đọc lịch sử evolution.
    Ưu tiên GitHub nếu có token để tránh mất ngày khi Streamlit redeploy/restart.
    Nếu GitHub lỗi thì fallback về file local.
    """
    token = get_github_token()

    if token:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_EVO_PATH}"
            headers = {"Authorization": f"token {token}"}
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                content = r.json().get("content", "")
                decoded = base64.b64decode(content).decode("utf-8")
                from io import StringIO
                return pd.read_csv(StringIO(decoded))
        except Exception:
            pass

    try:
        return pd.read_csv(EVOLUTION_FILE)
    except Exception:
        return pd.DataFrame()


def write_evolution_history(evo_df: pd.DataFrame) -> str:
    """
    Ghi evolution ra local và nếu có GITHUB_TOKEN thì commit lên GitHub.
    Đây là điểm sửa bệnh mất ngày 27/5: dữ liệu phải có nơi lưu bền, không chỉ local trên Streamlit.
    """
    try:
        evo_df.to_csv(EVOLUTION_FILE, index=False)
    except Exception:
        pass

    token = get_github_token()
    if not token:
        return "LOCAL_ONLY"

    try:
        csv_content = evo_df.to_csv(index=False)
        encoded_content = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_EVO_PATH}"
        headers = {"Authorization": f"token {token}"}

        sha = None
        get_r = requests.get(url, headers=headers, timeout=10)
        if get_r.status_code == 200:
            sha = get_r.json().get("sha")

        payload = {
            "message": f"Update evolution history {vn_time_str('%Y-%m-%d %H:%M:%S')}",
            "content": encoded_content,
        }
        if sha:
            payload["sha"] = sha

        put_r = requests.put(url, headers=headers, json=payload, timeout=15)
        if put_r.status_code in [200, 201]:
            return "GITHUB_OK"
        return f"GITHUB_FAIL_{put_r.status_code}"
    except Exception:
        return "GITHUB_ERROR"
@st.cache_data(ttl=5 * 60, show_spinner=False)
def is_vnindex_trading_today() -> tuple[bool, str]:
    """
    Chỉ trả True khi VNINDEX có dữ liệu ngày hôm nay.
    Nếu thứ 7, CN hoặc ngày lễ: dữ liệu VNINDEX mới nhất sẽ là phiên trước đó => False.
    """
    today = today_str()

    try:
        from vnstock import stock_historical_data

        attempts = [
            {"symbol": "VNINDEX", "type": "index"},
            {"symbol": "VNINDEX", "type": "stock"},
        ]

        last_seen_date = ""

        for cfg in attempts:
            try:
                df = stock_historical_data(
                    symbol=cfg["symbol"],
                    start_date=(vn_now() - timedelta(days=10)).strftime("%Y-%m-%d"),
                    end_date=today,
                    resolution="1D",
                    type=cfg["type"],
                    beautify=True,
                )

                if df is None or df.empty:
                    continue

                date_col = None
                for c in df.columns:
                    if "date" in str(c).lower() or "time" in str(c).lower():
                        date_col = c
                        break

                if date_col is None:
                    continue

                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df.dropna(subset=[date_col]).sort_values(date_col)

                if df.empty:
                    continue

                last_date = df[date_col].iloc[-1].strftime("%Y-%m-%d")
                last_seen_date = last_date

                if last_date == today:
                    return True, f"VNINDEX có giao dịch hôm nay: {today}"

            except Exception:
                continue

        return False, f"Không lưu Evolution: VNINDEX mới nhất là {last_seen_date}, không phải {today}"

    except Exception as e:
        return False, f"Không kiểm tra được VNINDEX: {e}"
def save_evolution(scan_df: pd.DataFrame, allow_save: bool = True, reason: str = "") -> tuple[pd.DataFrame, str]:

    """
    Lưu 1 bản cuối cho mỗi ngày/mã.
    Dữ liệu được đọc/ghi qua read_evolution_history + write_evolution_history để không mất phiên khi app restart.
    """
    if not allow_save:
        old_df = read_evolution_history()
        return old_df, f"SKIP_NO_TRADING_SESSION | {reason}"
    today = today_str()
    now_time = vn_time_str("%H:%M:%S")

    rows = []
    for _, r in scan_df.iterrows():
        rows.append({
            "date": today,
            "time": now_time,
            "symbol": r["symbol"],
            "group": r["group"],
            "rank": GROUP_RANK.get(r["group"], 0),
            "score": r.get("total_score", np.nan),
            "price": r.get("price", np.nan),
            "obv": r.get("obv", np.nan),
            "volume": r.get("volume", np.nan),
            "vol_ma20": r.get("vol_ma20", np.nan),
            "is_live_adjusted": r.get("is_live_adjusted", False),
            
        })

    new_df = pd.DataFrame(rows)
    old_df = read_evolution_history()

    if old_df.empty:
        evo_df = new_df
    else:
        evo_df = pd.concat([old_df, new_df], ignore_index=True)

    evo_df = evo_df.drop_duplicates(subset=["date", "symbol"], keep="last")
    evo_df["date"] = pd.to_datetime(evo_df["date"], errors="coerce")
    evo_df = evo_df.dropna(subset=["date"])

    last_dates = sorted(evo_df["date"].dt.strftime("%Y-%m-%d").unique())[-120:]
    evo_df["date_str"] = evo_df["date"].dt.strftime("%Y-%m-%d")
    evo_df = evo_df[evo_df["date_str"].isin(last_dates)].copy()
    evo_df = evo_df.drop(columns=["date_str"])
    evo_df["date"] = evo_df["date"].dt.strftime("%Y-%m-%d")

    save_status = write_evolution_history(evo_df)
    return evo_df, save_status
    # =========================================================
# STORM LEADERS - CP ĐANG MẠNH LÊN NHANH + TIỀN VÀO MẠNH
# =========================================================
def build_storm_leaders(scan_df: pd.DataFrame) -> pd.DataFrame:
    if scan_df.empty:
        return pd.DataFrame()

    current = scan_df.copy()

    # GREEN2 từ tín hiệu thật của hệ thống
    if "green_2_confirm" in current.columns:
        current["GREEN2"] = np.where(
            current["green_2_confirm"].astype(str).str.contains("GREEN 2", na=False),
            "✅",
            ""
        )
    else:
        current["GREEN2"] = ""

    for col in ["volume", "vol_ma20", "obv", "total_score", "O", "V", "rsi14", "ema9_ma20_slope"]:
        if col not in current.columns:
            current[col] = np.nan

    current["vol_ratio"] = np.where(
        current["vol_ma20"] > 0,
        current["volume"] / current["vol_ma20"],
        np.nan
    )

    current["volume_surge_score"] = np.select(
        [
            current["vol_ratio"] >= 2.0,
            current["vol_ratio"] >= 1.5,
            current["vol_ratio"] >= 1.2,
        ],
        [3, 2, 1],
        default=0
    )

    current["dna_accel"] = 0.0
    current["obv_accel_score"] = 0.0

    evo_df = read_evolution_history()

    if not evo_df.empty and {"date", "symbol", "score", "obv"}.issubset(evo_df.columns):
        hist = evo_df.copy()
        hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
        hist["score"] = pd.to_numeric(hist["score"], errors="coerce")
        hist["obv"] = pd.to_numeric(hist["obv"], errors="coerce")
        hist = hist.dropna(subset=["date", "symbol"])
        hist = hist.sort_values(["symbol", "date"])

        old_rows = []

        for symbol, sub in hist.groupby("symbol"):
            sub = sub.drop_duplicates("date", keep="last").sort_values("date")

            if len(sub) >= 5:
                old = sub.iloc[-5]
            elif len(sub) >= 2:
                old = sub.iloc[0]
            else:
                continue

            old_rows.append({
                "symbol": symbol,
                "old_score": old.get("score", np.nan),
                "old_obv": old.get("obv", np.nan),
            })

        old_df = pd.DataFrame(old_rows)

        if not old_df.empty:
            current = current.merge(old_df, on="symbol", how="left")
            current["dna_accel"] = current["total_score"] - current["old_score"]

            current["obv_accel_score"] = np.where(
                (pd.notna(current["obv"])) &
                (pd.notna(current["old_obv"])) &
                (current["obv"] > current["old_obv"]),
                2,
                0
            )

    current["storm_score"] = (
        current["dna_accel"].fillna(0) * 1.5
        + current["obv_accel_score"].fillna(0) * 2.0
        + current["volume_surge_score"].fillna(0) * 2.0
        + current["O"].fillna(0)
        + current["V"].fillna(0)
    )

    valid_groups = [
        "MUA EARLY",
        "PULL VỪA",
        "PULL ĐẸP",
        "MUA BREAK",
        "CP MẠNH",
        "GÀ TĂNG TỐC",
    ]

    out = current[
        (current["storm_score"] > 0)
        & (current["group"].isin(valid_groups))
    ].copy()

    if out.empty:
        return pd.DataFrame()

    out = out.sort_values(
        ["storm_score", "volume_surge_score", "dna_accel", "obv_accel_score", "O", "V"],
        ascending=False
    )

    out = out.rename(columns={
        "symbol": "MÃ",
        "group": "NHÓM",
        "price": "GIÁ",
        "storm_score": "STORM",
        "dna_accel": "DNA ACCEL",
        "obv_accel_score": "OBV ACCEL",
        "volume_surge_score": "VOL SURGE",
        "vol_ratio": "VOL/MA20",
        "total_score": "SCORE",
        "rsi14": "RSI",
        "ema9_ma20_slope": "SLOPE",
        "obv_status": "OBV",
        "warning": "CẢNH BÁO",
    })

    cols = [
        "MÃ",
        "NHÓM",
        "GIÁ",
        "STORM",
        "GREEN2",
        "DNA ACCEL",
        "OBV ACCEL",
        "VOL SURGE",
        "VOL/MA20",
        "SCORE",
        "RSI",
        "SLOPE",
        "OBV",
        "CẢNH BÁO",
    ]

    cols = [c for c in cols if c in out.columns]
   
    return out[cols].head(20)


def build_evolution_tables(scan_df: pd.DataFrame):
    evo_df = read_evolution_history()

    current = scan_df[["symbol", "group", "total_score", "price"]].copy()
    current = current.rename(columns={
        "group": "TODAY",
        "total_score": "today_score",
        "price": "today_price",
    })
    current["today_rank"] = current["TODAY"].map(GROUP_RANK).fillna(0)

    if evo_df.empty or not {"date", "symbol", "group"}.issubset(set(evo_df.columns)):
        base = current.copy()
        base["evolution"] = 0
        base["recent_change"] = 0
        base["arrow"] = "➡️"
        base["status"] = "⚪"
        return base, pd.DataFrame()

    evo_df["date"] = pd.to_datetime(evo_df["date"], errors="coerce")
    evo_df = evo_df.dropna(subset=["date"])
    evo_df["date"] = evo_df["date"].dt.strftime("%Y-%m-%d")

    dates = sorted(evo_df["date"].unique())[-5:]

    pivot = evo_df.pivot_table(
        index="symbol",
        columns="date",
        values="group",
        aggfunc="first",
    ).reindex(columns=dates)

    hist_rows = []

    for symbol in pivot.index:
        row = {"symbol": symbol}
        for d in dates:
            row[d] = pivot.loc[symbol, d]
        hist_rows.append(row)

    hist = pd.DataFrame(hist_rows)

    if hist.empty:
        base = current.copy()
    else:
        base = hist.merge(current, on="symbol", how="outer")
    evo_scores = []
    recent_changes = []
    arrows = []
    status_icons = []

    persistences = []
    dna_flags = []
    
    for _, r in base.iterrows():

        hist_groups = []

        for d in dates:
            g = r.get(d, np.nan)
            if pd.notna(g):
                hist_groups.append(g)

        today_group = r.get("TODAY", np.nan)
        today_rank = GROUP_RANK.get(today_group, 0)
        if hist_groups:

            first_rank = GROUP_RANK.get(hist_groups[0], 0)
            last_rank = GROUP_RANK.get(hist_groups[-1], 0)

            evolution = today_rank - first_rank
            recent_change = today_rank - last_rank

            ranks = [GROUP_RANK.get(g, 0) for g in hist_groups]

            if today_group and pd.notna(today_group):
                ranks.append(today_rank)

            persistence = round(sum(ranks) / len(ranks), 1)

            if persistence >= 5.0:
                dna = "🟢 DNA MẠNH"
            elif persistence >= 3.5:
                dna = "🟡 BỀN"
            else:
                dna = "⚪ MỚI"

        else:

            evolution = 0
            recent_change = 0
            persistence = 0
            dna = "⚪ MỚI"

        evo_scores.append(evolution)
        recent_changes.append(recent_change)
        persistences.append(persistence)
        dna_flags.append(dna)
        
        if recent_change > 0:
            arrows.append("⬆️")
        elif recent_change < 0:
            arrows.append("⬇️")
        else:
            arrows.append("➡️")

        if evolution > 0:
            status_icons.append("🟢")
        elif evolution < 0:
            status_icons.append("🔴")
        else:
            status_icons.append("⚪")

    
    base["evolution"] = evo_scores
    base["recent_change"] = recent_changes

    base["Persistence"] = persistences
    base["DNA"] = dna_flags

    base["arrow"] = arrows
    base["status"] = status_icons
    
    sort_cols = [
    "Persistence",
    "evolution",
    "recent_change",
    "today_score",
]
    sort_cols = [c for c in sort_cols if c in base.columns]

    if sort_cols:
        base = base.sort_values(
            by=sort_cols,
            ascending=[False] * len(sort_cols)
        ).reset_index(drop=True)

    buy_table = base[
        (
            (base["evolution"] >= 1)
            | (base["recent_change"] >= 1)
        )
        & base["TODAY"].isin([
            "MUA EARLY",
            "PULL VỪA",
            "PULL ĐẸP",
            "MUA BREAK",
            "CP MẠNH",
            "GÀ TĂNG TỐC",
        ])
    ].copy()

    return base, buy_table
# =========================================================
# GROUP PERFORMANCE STATISTICS
# =========================================================
def build_group_statistics():
    evo_df = read_evolution_history()

    if evo_df.empty:
        return pd.DataFrame()

    required = {"date", "symbol", "group", "price"}
    if not required.issubset(set(evo_df.columns)):
        return pd.DataFrame()

    evo_df = evo_df.copy()
    evo_df["date"] = pd.to_datetime(evo_df["date"], errors="coerce")
    evo_df["price"] = pd.to_numeric(evo_df["price"], errors="coerce")
    evo_df["group"] = evo_df["group"].astype(str).str.strip()

    evo_df = evo_df.dropna(subset=["date", "symbol", "group", "price"])
    evo_df = evo_df[evo_df["symbol"] != "VNINDEX"].copy()
    evo_df = evo_df.sort_values(["symbol", "date"])

    horizons = {
        "T+1": 1,
        "T+3": 3,
        "T+5": 5,
    }

    results = []

    total_signals = (
        evo_df.groupby("group")
        .size()
        .reset_index(name="TotalSignals")
    )

    for symbol, sub in evo_df.groupby("symbol"):
        sub = (
            sub.sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
            .reset_index(drop=True)
        )

        for i in range(len(sub)):
            start_row = sub.iloc[i]
            start_group = start_row["group"]
            start_price = start_row["price"]

            if pd.isna(start_price) or start_price <= 0:
                continue

            for horizon_name, step in horizons.items():
                future_i = i + step

                if future_i >= len(sub):
                    continue

                future_row = sub.iloc[future_i]
                future_price = future_row["price"]

                if pd.isna(future_price) or future_price <= 0:
                    continue

                ret = (future_price / start_price - 1) * 100

                results.append({
                    "Horizon": horizon_name,
                    "group": start_group,
                    "return_pct": ret,
                    "win": 1 if ret > 0 else 0,
                })

    if not results:
        return pd.DataFrame()

    stat_df = pd.DataFrame(results)

    summary = (
        stat_df.groupby(["Horizon", "group"])
        .agg(
            Samples=("return_pct", "count"),
            WinRate=("win", "mean"),
            AvgReturn=("return_pct", "mean"),
            MedianReturn=("return_pct", "median"),
            MaxReturn=("return_pct", "max"),
            MinReturn=("return_pct", "min"),
        )
        .reset_index()
    )

    summary = summary.merge(total_signals, on="group", how="left")
    summary["Pending"] = summary["TotalSignals"] - summary["Samples"]

    summary["WinRate"] = (summary["WinRate"] * 100).round(1)
    summary["AvgReturn"] = summary["AvgReturn"].round(2)
    summary["MedianReturn"] = summary["MedianReturn"].round(2)
    summary["MaxReturn"] = summary["MaxReturn"].round(2)
    summary["MinReturn"] = summary["MinReturn"].round(2)

    horizon_order = {"T+1": 1, "T+3": 2, "T+5": 3}
    summary["horizon_rank"] = summary["Horizon"].map(horizon_order).fillna(9)

    summary = summary.sort_values(
        ["horizon_rank", "AvgReturn", "WinRate"],
        ascending=[True, False, False]
    ).drop(columns=["horizon_rank"])

    return summary

# =========================================================
# BẢNG TỔNG HỢP NHANH
# =========================================================

def build_group_summary(stats_df):
    if stats_df.empty:
        return pd.DataFrame()

    rows = []

    for group in stats_df["group"].unique():

        sub = stats_df[stats_df["group"] == group]

        t1 = sub[sub["Horizon"] == "T+1"]
        t3 = sub[sub["Horizon"] == "T+3"]
        t5 = sub[sub["Horizon"] == "T+5"]

        def get_val(df, col):
            if df.empty:
                return 0
            return float(df.iloc[0][col])

        win_score = (
            get_val(t1, "WinRate") * 0.5 +
            get_val(t3, "WinRate") * 0.3 +
            get_val(t5, "WinRate") * 0.2
        )

        return_score = (
            get_val(t1, "AvgReturn") * 0.5 +
            get_val(t3, "AvgReturn") * 0.3 +
            get_val(t5, "AvgReturn") * 0.2
        )

        rows.append({
            "group": group,
            "Score": round(win_score, 1),
            "AvgReturn": round(return_score, 2),
            "T+1 Win": get_val(t1, "WinRate"),
            "T+3 Win": get_val(t3, "WinRate"),
            "T+5 Win": get_val(t5, "WinRate"),
        })

    summary = pd.DataFrame(rows)

    summary = summary.sort_values(
        ["Score", "AvgReturn"],
        ascending=False
    ).reset_index(drop=True)

    return summary

# =========================================================
# 👑 TINH HOA LEADERS - TINH HOA CỦA TINH HOA
# =========================================================
def score_rsi_tinh_hoa(rsi):
    """RSI đẹp nhất là vùng 60-70. Quá thấp là yếu, quá cao là nóng."""
    rsi = to_float(rsi)
    if pd.isna(rsi):
        return 0
    if 60 <= rsi <= 70:
        return 15
    if 55 <= rsi < 60 or 70 < rsi <= 75:
        return 11
    if 50 <= rsi < 55 or 75 < rsi <= 80:
        return 6
    if rsi > 80:
        return 3
    return 0


def score_slope_tinh_hoa(slope):
    """Slope đẹp nhất là dương vừa phải: có lực nhưng chưa quá nóng."""
    slope = to_float(slope)
    if pd.isna(slope):
        return 0
    if 1.0 <= slope <= 3.0:
        return 15
    if 0.3 <= slope < 1.0:
        return 10
    if 3.0 < slope <= 5.0:
        return 10
    if 0 < slope < 0.3:
        return 5
    if slope > 5.0:
        return 6
    return 0


def build_tinh_hoa_leaders(
    scan_df: pd.DataFrame,
    evo_table: pd.DataFrame,
    storm_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
) -> pd.DataFrame:
    """
    Bảng Tinh Hoa = giao thoa mềm giữa DNA + Evolution + Storm + chất lượng hiện tại.

    Tư duy:
    - DNA/Persistence: cổ phiếu mạnh bền, không phải mạnh một phiên.
    - GroupStrength: hôm nay đang thuộc nhóm tốt hay không.
    - RSI: ưu tiên vùng 60-70, tránh quá yếu hoặc quá nóng.
    - Slope: ưu tiên tăng đều, chưa quá dốc.
    - Storm: có tiền mới vào hiện tại.
    - Evolution: có tiến hóa hoặc giữ hạng tốt.
    """
    if scan_df.empty:
        return pd.DataFrame()

    valid_groups = [
        "MUA EARLY",
        "PULL VỪA",
        "PULL ĐẸP",
        "MUA BREAK",
        "CP MẠNH",
        "GÀ TĂNG TỐC",
    ]

    base_cols = [
        "symbol", "group", "price", "total_score", "rsi14", "ema9_ma20_slope",
        "obv_status", "dist_from_ema9_pct", "green_2_confirm", "warning"
    ]
    base_cols = [c for c in base_cols if c in scan_df.columns]
    base = scan_df[base_cols].copy()

    if "group" not in base.columns or "symbol" not in base.columns:
        return pd.DataFrame()

    base = base[base["group"].isin(valid_groups)].copy()
    if base.empty:
        return pd.DataFrame()

    # Ghép DNA/Evolution từ evo_table
    if evo_table is not None and not evo_table.empty and "symbol" in evo_table.columns:
        evo_cols = [
            "symbol", "Persistence", "DNA", "evolution", "recent_change", "TODAY", "today_score"
        ]
        evo_cols = [c for c in evo_cols if c in evo_table.columns]
        evo_small = evo_table[evo_cols].copy()
        base = base.merge(evo_small, on="symbol", how="left")
    else:
        base["Persistence"] = 0
        base["DNA"] = "⚪ MỚI"
        base["evolution"] = 0
        base["recent_change"] = 0

    for c in ["Persistence", "evolution", "recent_change", "total_score", "rsi14", "ema9_ma20_slope", "dist_from_ema9_pct"]:
        if c not in base.columns:
            base[c] = np.nan
        base[c] = pd.to_numeric(base[c], errors="coerce")

    # Storm set: dùng bảng đã rename cột MÃ từ build_storm_leaders
    storm_symbols = set()
    if storm_df is not None and not storm_df.empty:
        if "MÃ" in storm_df.columns:
            storm_symbols = set(storm_df["MÃ"].astype(str))
        elif "symbol" in storm_df.columns:
            storm_symbols = set(storm_df["symbol"].astype(str))

    base["Storm"] = np.where(base["symbol"].astype(str).isin(storm_symbols), "✅", "")
    base["Green2"] = np.where(
        base.get("green_2_confirm", "").astype(str).str.contains("GREEN 2", na=False),
        "✅",
        ""
    )

    group_strength_map = {
        "GÀ TĂNG TỐC": 25,
        "CP MẠNH": 22,
        "MUA BREAK": 20,
        "PULL ĐẸP": 21,
        "PULL VỪA": 17,
        "MUA EARLY": 13,
    }

    base["DNA_SCORE"] = (base["Persistence"].fillna(0).clip(lower=0, upper=7) / 7 * 30).round(2)
    base["GROUP_SCORE"] = base["group"].map(group_strength_map).fillna(0)
    base["RSI_SCORE"] = base["rsi14"].apply(score_rsi_tinh_hoa)
    base["SLOPE_SCORE"] = base["ema9_ma20_slope"].apply(score_slope_tinh_hoa)
    base["STORM_SCORE"] = np.where(base["Storm"] == "✅", 10, 0)
    base["EVO_SCORE"] = np.select(
        [
            base["evolution"] >= 3,
            base["evolution"] >= 1,
            base["recent_change"] >= 1,
        ],
        [5, 4, 3],
        default=0,
    )

    base["TinhHoa"] = (
        base["DNA_SCORE"]
        + base["GROUP_SCORE"]
        + base["RSI_SCORE"]
        + base["SLOPE_SCORE"]
        + base["STORM_SCORE"]
        + base["EVO_SCORE"]
    ).round(1)

    # Số bảng đồng thuận: DNA đủ bền + Evolution có tiến hóa + Storm có tiền hiện tại
    base["Số bảng"] = (
        (base["Persistence"].fillna(0) >= 3.5).astype(int)
        + ((base["evolution"].fillna(0) >= 1) | (base["recent_change"].fillna(0) >= 1)).astype(int)
        + (base["Storm"] == "✅").astype(int)
    )

    base["Tier"] = np.select(
        [
            base["TinhHoa"] >= 90,
            base["TinhHoa"] >= 80,
            base["TinhHoa"] >= 70,
        ],
        ["🏆 S", "🥇 A", "🥈 B"],
        default="⚪ C",
    )

    def action_row(r):
        if market_real < 6:
            return "🟡 THEO DÕI - MARKET CHƯA ỦNG HỘ"
        if market_forecast < 3:
            return "🟡 CANH NHỎ - FORECAST CÒN YẾU"
        if str(r.get("warning", "")).find("OBV gãy") >= 0:
            return "🔴 LOẠI TẠM - OBV GÃY"
        dist = to_float(r.get("dist_from_ema9_pct", np.nan))
        group = str(r.get("group", ""))
        tier = str(r.get("Tier", ""))
        if group in ["GÀ TĂNG TỐC", "CP MẠNH", "MUA BREAK"] and pd.notna(dist) and dist > 4:
            return "🟡 CHỜ PULL VỀ EMA9"
        if tier == "🏆 S":
            return "🟢 ƯU TIÊN MUA KHI CÓ ĐIỂM ĐẸP"
        if tier == "🥇 A":
            return "🟡 CANH MUA ĐỎ / TEST NHỎ"
        if tier == "🥈 B":
            return "⚪ THEO DÕI THÊM"
        return "⚪ CHƯA PHẢI TINH HOA"

    base["Hành động"] = base.apply(action_row, axis=1)

    # Lọc tinh hoa: ưu tiên điểm cao, hoặc có ít nhất 2 bảng đồng thuận.
    base = base[(base["TinhHoa"] >= 65) | (base["Số bảng"] >= 2)].copy()
    if base.empty:
        return pd.DataFrame()

    base = base.sort_values(
        ["TinhHoa", "Số bảng", "Persistence", "STORM_SCORE", "GROUP_SCORE", "SLOPE_SCORE"],
        ascending=[False, False, False, False, False, False]
    ).reset_index(drop=True)

    base.insert(0, "Rank", range(1, len(base) + 1))
    out = base.rename(columns={
    "symbol": "MÃ",
    "group": "NHÓM",
    "price": "GIÁ",
    "Persistence": "DNA_GOC",
            "rsi14": "RSI",
        "ema9_ma20_slope": "SLOPE",
        "total_score": "SCORE",
        "evolution": "TIẾN HÓA",
        "recent_change": "GẦN NHẤT",
        "obv_status": "OBV",
        "dist_from_ema9_pct": "DIST EMA9%",
        "warning": "CẢNH BÁO",
    })

    cols = [
        "Rank", "Tier", "MÃ", "TinhHoa", "Số bảng", "NHÓM", "GIÁ", "DNA_GOC", "DNA_SCORE",    
        "DNA", "RSI", "SLOPE", "Storm", "Green2", "TIẾN HÓA", "GẦN NHẤT",
        "SCORE", "OBV", "DIST EMA9%", "Hành động", "CẢNH BÁO"
    ]
    cols = [c for c in cols if c in out.columns]

    return out[cols].head(20)

# =========================================================
# UI CONTROLS
# =========================================================
left1, left2, left3, left4, left5 = st.columns([1.1, 1.2, 1.1, 1.3, 2.3])

with left1:
    scan_btn = st.button("🚀 SCAN", use_container_width=True)

with left2:
    auto_refresh = st.checkbox("Auto refresh", value=True)

with left3:
    refresh_seconds = st.selectbox("Nhịp", [60, 90, 120, 300, 600], index=2)

with left4:
    show_detail = st.checkbox("Hiện bảng chi tiết", value=False)

with left5:
    st.markdown(
        f"""
        <div style="font-size:14px">
        Watchlist: <b>{len(WATCHLIST)}</b> mã &nbsp; | &nbsp;
        Live cache: <b>{LIVE_CACHE_TTL}s</b> &nbsp; | &nbsp;
        Daily cache: <b>{DAILY_CACHE_TTL // 60} phút</b> &nbsp; | &nbsp;
        Update VN: <b>{vn_time_str()}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

if "last_auto_refresh" not in st.session_state:
    st.session_state["last_auto_refresh"] = time.time()

if scan_btn:
    st.cache_data.clear()

if auto_refresh:
    now_ts = time.time()
    if now_ts - st.session_state["last_auto_refresh"] >= refresh_seconds:
        st.session_state["last_auto_refresh"] = now_ts
        st.cache_data.clear()
        st.rerun()
# =========================================================
# RUN SCAN
# =========================================================
with st.spinner("Đang quét realtime unified..."):
    scan_df = run_scan(WATCHLIST)

if scan_df.empty:
    st.error("Không lấy được dữ liệu. Anh kiểm tra mạng, vnstock hoặc requirements.txt.")
    st.stop()

# =========================================================
# MARKET OVERVIEW
# =========================================================
market_real = calc_market_real(scan_df)
market_live = calc_market_live(scan_df)
market_forecast, market_forecast_text = calc_market_forecast(scan_df)
market_status, market_action = market_status_text(market_real)

live_count = int(scan_df["is_live_adjusted"].sum()) if "is_live_adjusted" in scan_df.columns else 0
safe_mode_count = int((scan_df["live_source"].astype(str).str.contains("SAFE_MODE|NO_DATA|BAD", na=False)).sum()) if "live_source" in scan_df.columns else 0

st.markdown("## 📊 MARKET OVERVIEW")

m1, m2, m3, m4, m5, m6 = st.columns(6)
with m1:
    st.metric("REAL", f"{market_real}/13")
with m2:
    st.metric("LIVE", f"{market_live}/13")
with m3:
    st.metric("FORECAST", f"{market_forecast}/10")
with m4:
    st.metric("SCAN OK", len(scan_df))
with m5:
    st.metric("LIVE OK", live_count)
with m6:
    st.metric("WATCHLIST", len(WATCHLIST))

if safe_mode_count > 0:
    st.caption(f"🟡 SAFE DATA: {safe_mode_count} mã đang dùng D1/NO_DATA thay cho live để tránh app bị crash.")

if market_real < 6:
    st.error(market_action)
elif market_real < 8:
    st.warning(market_action)
else:
    st.success(market_action)

st.caption(market_forecast_text)
st.caption("V19: live price đã được bơm vào candle cuối trước khi tính indicator, nên market/bảng nhóm/detail/evo dùng cùng một scan_df.")
# =========================================================
# STORM LEADERS - CP ĐANG MẠNH LÊN NHANH + TIỀN VÀO MẠNH
# =========================================================
st.markdown("---")
st.markdown("## 🚀 STORM LEADERS - TIỀN LỚN ĐANG TĂNG TỐC")
storm_df = build_storm_leaders(scan_df)

if not storm_df.empty:
    st.dataframe(
        storm_df,
        use_container_width=True,
        hide_index=True,
        height=420,
    )
else:
    st.info("Chưa có mã đạt tiêu chí Storm Leaders.")
# =========================================================
# GROUP SUMMARY
# =========================================================
st.markdown("---")
st.markdown("## 📦 NHÓM CỔ PHIẾU")
cols = st.columns(len(GROUP_ORDER))
for i, g in enumerate(GROUP_ORDER):
    with cols[i]:
        st.metric(g, int((scan_df["group"] == g).sum()))

# =========================================================
# BUY ACTION TABLE
# =========================================================
st.markdown("---")
st.markdown("## ⚡ BẢNG HÀNH ĐỘNG NHANH")

buy_action_df = build_buy_table(scan_df, market_real)
show_buy = buy_action_df[buy_action_df["Hành động"] != "KHÔNG MUA"].copy()

if not show_buy.empty:
    st.dataframe(show_buy.head(30), use_container_width=True, height=500)
else:
    st.info("Chưa có mã đạt điều kiện mua. Bot ưu tiên không mua khi market hoặc trục tiền/giá chưa đạt.")

# =========================================================
# TABLE BY GROUP
# =========================================================
st.markdown("---")
st.markdown("## 🐔 BẢNG THEO NHÓM")

SHOW_COLS = [
    "symbol",
    "group",
    "price",
    "daily_price_before_live",
    "live_source",
    "is_live_adjusted",
    "total_score",
    "E",
    "R",
    "O",
    "S",
    "RS",
    "V",
    "ema9_ma20_slope",
    "rsi14",
    "obv_status",
    "dist_from_ema9_pct",
    "green_2_confirm",
    "status",
    "warning",
]

tabs = st.tabs(GROUP_ORDER)
for tab, g in zip(tabs, GROUP_ORDER):
    with tab:
        sub = scan_df[scan_df["group"] == g].copy()
        if sub.empty:
            st.info("Không có mã")
            continue
        cols_show = [c for c in SHOW_COLS if c in sub.columns]
        out = sub[cols_show].copy()
        out.index = range(len(out))
        st.dataframe(out, use_container_width=True, height=min(600, 80 + len(out) * 35))

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
        "daily_price_before_live",
        "live_source",
        "live_ts",
        "is_live_adjusted",
        "ema9",
        "ma20",
        "ema9_ma20_slope",
        "ema9_ma20_slope_change",
        "slope_state",
        "rsi14",
        "rsi_slope",
        "obv_status",
        "volume",
        "vol_ma20",
        "E",
        "R",
        "O",
        "S",
        "RS",
        "total_score",
        "rs5",
        "rs10",
        "breakout_ref",
        "dist_from_ema9_pct",
        "pull_label",
        "green_2_confirm",
        "status",
        "warning",
    ]

    detail_cols = [c for c in detail_cols if c in scan_df.columns]
    detail_df = scan_df[detail_cols].copy()
    detail_df.index = range(len(detail_df))
    st.dataframe(detail_df, use_container_width=True, height=700)

# =========================================================
# EVOLUTION
# =========================================================
st.markdown("---")
st.markdown("## 🚀 TIẾN HÓA CỔ PHIẾU")


trading_today, trading_reason = is_vnindex_trading_today()

evo_saved_df, evo_save_status = save_evolution(
    scan_df,
    allow_save=trading_today,
    reason=trading_reason,
)
evo_table, evo_buy_table = build_evolution_tables(scan_df)

# =========================================================
# 🏆 DNA LEADERS V2 - BẢNG MUA LÕI
# =========================================================

try:

    if not evo_table.empty and "Persistence" in evo_table.columns:

        dna_leaders = evo_table.copy()

        # Ghép thêm dữ liệu realtime từ scan hiện tại
        extra_cols = [
            "symbol",
            "rsi14",
            "ema9_ma20_slope",
            "total_score",
            "group"
        ]

        scan_extra = scan_df[
            [c for c in extra_cols if c in scan_df.columns]
        ].copy()

        dna_leaders = dna_leaders.merge(
            scan_extra,
            on="symbol",
            how="left"
        )

        cols = [
            "symbol",
            "Persistence",
            "DNA",
            "group",
            "rsi14",
            "ema9_ma20_slope",
            "total_score",
            "evolution",
            "recent_change"
        ]

        cols = [c for c in cols if c in dna_leaders.columns]

        dna_leaders = dna_leaders[cols]

        dna_leaders = dna_leaders.rename(columns={
            "symbol": "MÃ",
            "Persistence": "DNA",
            "DNA": "LOẠI",
            "group": "NHÓM",
            "rsi14": "RSI",
            "ema9_ma20_slope": "SLOPE",
            "total_score": "SCORE",
            "evolution": "TIẾN HÓA",
            "recent_change": "GẦN NHẤT"
        })

        dna_leaders = dna_leaders.sort_values(
            ["DNA", "TIẾN HÓA", "SCORE"],
            ascending=[False, False, False]
        ).head(15)

        st.markdown("## 🏆 DNA LEADERS V2 - BẢNG MUA")

        st.dataframe(
            dna_leaders,
            use_container_width=True,
            hide_index=True,
            height=500
        )

except Exception as e:
    st.warning(f"DNA LEADERS ERROR: {e}")

# =========================================================
# 👑 TINH HOA LEADERS - BẢNG LỌC CUỐI CÙNG
# =========================================================
st.markdown("---")
st.markdown("## 👑 TINH HOA LEADERS - TINH HOA CỦA TINH HOA")

try:
    tinh_hoa_df = build_tinh_hoa_leaders(
        scan_df=scan_df,
        evo_table=evo_table,
        storm_df=storm_df,
        market_real=market_real,
        market_forecast=market_forecast,
    )

    if not tinh_hoa_df.empty:
        s_count = int((tinh_hoa_df["Tier"] == "🏆 S").sum()) if "Tier" in tinh_hoa_df.columns else 0
        a_count = int((tinh_hoa_df["Tier"] == "🥇 A").sum()) if "Tier" in tinh_hoa_df.columns else 0
        b_count = int((tinh_hoa_df["Tier"] == "🥈 B").sum()) if "Tier" in tinh_hoa_df.columns else 0

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Tinh hoa S", s_count)
        with c2:
            st.metric("Tinh hoa A", a_count)
        with c3:
            st.metric("Tinh hoa B", b_count)
        with c4:
            st.metric("Tổng theo dõi", len(tinh_hoa_df))

        if market_real < 6:
            st.warning("Market REAL < 6: bảng Tinh Hoa chỉ dùng để theo dõi, chưa dùng để đánh lớn.")
        elif market_forecast < 3:
            st.warning("Forecast còn yếu: chỉ ưu tiên mua đỏ/test nhỏ, chưa mua đuổi.")
        else:
            st.success("Market bắt đầu ủng hộ: ưu tiên các mã Tier S/A khi có điểm mua đẹp.")

        st.dataframe(
            tinh_hoa_df,
            use_container_width=True,
            hide_index=True,
            height=520,
        )

        st.caption(
            "TinhHoa = DNA bền + nhóm hiện tại + RSI đẹp + slope đẹp + Storm + Evolution. "
            "Tier S/A/B là để chọn rổ theo dõi, không thay thế điểm mua và kỷ luật market first."
        )
    else:
        st.info("Chưa có mã đạt chuẩn Tinh Hoa. Đây là tín hiệu nên kiên nhẫn, không ép giao dịch.")

except Exception as e:
    st.warning(f"TINH HOA LEADERS ERROR: {e}")

saved_dates = []
try:
    saved_dates = sorted(pd.to_datetime(evo_saved_df["date"], errors="coerce").dropna().dt.strftime("%Y-%m-%d").unique())
except Exception:
    saved_dates = []


st.caption(
    f"Evolution save: {evo_save_status} | {trading_reason} | Dates: "
    f"{', '.join(saved_dates[-7:]) if saved_dates else 'chưa có'}"
)
e1, e2 = st.columns(2)

with e1:
    st.subheader("Bảng tiến hóa")
    if not evo_table.empty:
        st.dataframe(evo_table, use_container_width=True, height=420)
    else:
        st.info("Chưa đủ dữ liệu tiến hóa. Chỉ cần từ 2 phiên là bắt đầu có tín hiệu.")

with e2:
    st.subheader("Bảng tiến hóa chọn lọc")
    if not evo_buy_table.empty:
        st.dataframe(evo_buy_table, use_container_width=True, height=420)
    else:
        st.info("Chưa có cổ phiếu tiến hóa đạt điều kiện mua/theo dõi.")
# =========================================================
# GROUP STATISTICS
# =========================================================
st.markdown("---")
st.markdown("## 📊 THỐNG KÊ HIỆU SUẤT NHÓM")

group_stats = build_group_statistics()
summary_df = build_group_summary(group_stats)
# =========================================================
# MARKET REGIME
# =========================================================

market_regime = "🧊 MÙA ĐÔNG"
market_reason = []

if not summary_df.empty:

    top_group = summary_df.iloc[0]["group"]
    top_score = summary_df.iloc[0]["Score"]

    gt_count = len(scan_df[scan_df["group"] == "GÀ TĂNG TỐC"])
    strong_count = len(scan_df[scan_df["group"] == "CP MẠNH"])

    total_strong = gt_count + strong_count

    if market_real >= 6:
        market_regime = "🌱 MÙA XUÂN"

    elif (
        market_real >= 4
        and top_score >= 40
        and total_strong >= 5
    ):
        market_regime = "🌿 TÍCH LŨY CẢI THIỆN"

    elif (
        market_real < 4
        and total_strong > 0
    ):
        market_regime = "🟡 HỒI KỸ THUẬT"

    else:
        market_regime = "🧊 MÙA ĐÔNG"

    market_reason = [
        f"REAL = {market_real:.1f}/13",
        f"FORECAST = {market_forecast:.1f}/10",
        f"TOP GROUP = {top_group}",
        f"GÀ TĂNG TỐC + CP MẠNH = {total_strong}"
    ]
    # =========================================================
# HIỂN THỊ MARKET REGIME
# =========================================================

st.subheader("🧭 MARKET REGIME")

st.success(market_regime)

for r in market_reason:
    st.caption(r)
if not summary_df.empty:
    st.subheader("🏆 XẾP HẠNG NHÓM TỔNG HỢP")
    st.dataframe(
        summary_df,
        use_container_width=True,
        hide_index=True
    )
if not group_stats.empty:
    st.dataframe(
        group_stats,
        use_container_width=True,
        height=350
    )

    st.caption(
        "WinRate và AvgReturn được tính sau 3 phiên kể từ ngày cổ phiếu xuất hiện trong nhóm."
    )
else:
    st.info("Chưa đủ dữ liệu để thống kê.")
# =========================================================
# FOOTER
# =========================================================
st.markdown("---")
st.caption("V19.2 SAFE MODE | Giờ VN chuẩn Asia/Ho_Chi_Minh | Live price 15m qua yfinance | Live lỗi tự fallback D1 | Một mã lỗi không làm sập app | Tất cả bảng dùng chung scan_df")
