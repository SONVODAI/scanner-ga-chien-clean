"""
Shared scanner core — Streamlit-free board construction & market scores.

Consumed by app.py UI and production headless EOD. REAL/LIVE/FC formulas unchanged.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

from forecast_engine import ForecastEngine

_FORECAST_ENGINE = ForecastEngine()

WATCHLIST = sorted(list(set([
    "PLX", "PVS", "PVD", "PVB", "PVC", "PVT", "BSR", "OIL", "GAS",
    "HAH", "VSC", "GMD", "VOS", "VTO", "ACV", "HVN", "VJC",
    "MSH", "TNG", "TCM", "GIL", "VHC", "ANV", "PTB", "VGT",
    "BFC", "DCM", "DPM", "CSV", "DDV", "LAS", "BMP", "NTP",
    "MSR", "REE", "GEE", "GEX", "PC1", "HDG", "GEG", "NT2",
    "DGC", "POW",
    "C4G", "FCN", "CII", "KSB", "HPG", "HSG",
    "NKG", "VGS", "CTD", "HHV", "VCG", "PLC", "TVN",
    "MWG", "FRT", "DGW", "PET", "MSN", "DBC", "HAG", "BAF",
    "MCH", "VNM", "MML",
    "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "SHB", "SSB",
    "STB", "HDB", "TPB", "VIB", "LPB", "OCB", "MSB", "NAB", "EIB",
    "VND", "SSI", "HCM", "VIX", "BSI", "FTS", "TVS", "SHS",
    "AGR", "VCI", "TCX", "VCK", "VPX", "ORS", "BVS", "VDS", "MBS",
    "VGC", "SZC", "IDC", "KBC", "IJC",
    "GVR", "SIP", "DPR", "PHR", "DRI",
    "FPT", "VGI", "CTR", "VTP", "CMG", "FOX",
    "BVH", "SBT", "PNJ",
    "VIC", "VHM", "VRE", "NVL", "DXG", "DXS", "DIG", "CEO", "TCH",
    "EVF", "SAB", "VPL", "PDR", "DPG", "NHA", "HDC", "NTL", "HHS",
    "NLG", "KDH", "HUT",
])))

# =========================================================
# CONFIG
# =========================================================

YAHOO_SUFFIX = ".VN"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
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
            old = guard_dataframe_dtypes(pd.read_csv(file_name), text_cols=["time", "symbol", "stage", "error"], numeric_cols=[])
            row = pd.concat([old, row], ignore_index=True).tail(300)
        row = guard_dataframe_dtypes(row, text_cols=["time", "symbol", "stage", "error"], numeric_cols=[])
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
# DATA GUARD LAYER - CHỐNG LỖI DTYPE PANDAS MỚI
# =========================================================
TEXT_GUARD_COLS = {
    "date", "time", "created_at", "updated_at", "last_outcome_update",
    "symbol", "group", "regime", "learning_mode", "conclusion", "nav",
    "dna", "obv", "status", "personality", "message", "mode", "note",
    "current_thought", "source", "stage", "error", "name", "version",
}

NUMERIC_GUARD_COLS = {
    "rank", "score", "price", "entry_price", "market_real", "market_forecast",
    "winprob", "elite_score", "storm", "persistence", "evolution",
    "recent_change", "rsi", "slope", "dist_ema9", "market_score",
    "action_score", "storm_score", "evo_score", "zone_score", "penalty",
    "t1_return", "t3_return", "t5_return", "t1_win", "t3_win", "t5_win",
    "obv_value", "volume", "vol_ma20", "completed_t5", "baseline_winrate",
    "confidence", "age_days", "signals_today", "avg_winprob", "avg_elite_score",
    "high_consensus_count",
}


def ensure_object_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Ép các cột chữ/ngày giờ sang object để Pandas không báo lỗi khi gán string."""
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].astype("object")
        out[col] = out[col].where(pd.notna(out[col]), "")
    return out


def ensure_numeric_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Ép các cột số về numeric an toàn, lỗi thì thành NaN."""
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def guard_dataframe_dtypes(
    df: pd.DataFrame,
    text_cols=None,
    numeric_cols=None,
) -> pd.DataFrame:
    """Chuẩn hóa dtype trước khi setitem/concat/to_csv.

    Lỗi anh gặp xuất phát từ việc một cột đang là float64 nhưng bị gán chuỗi
    dạng '2026-06-29 07:16:49'. Hàm này tách rõ cột chữ và cột số để tránh
    Pandas 2.x/3.x chặn kiểu dữ liệu.
    """
    if df is None:
        return pd.DataFrame()
    out = df.copy()

    text_cols = list(TEXT_GUARD_COLS if text_cols is None else text_cols)
    numeric_cols = list(NUMERIC_GUARD_COLS if numeric_cols is None else numeric_cols)

    existing_text = [c for c in text_cols if c in out.columns]
    existing_numeric = [c for c in numeric_cols if c in out.columns and c not in existing_text]

    if existing_text:
        out = ensure_object_columns(out, existing_text)
    if existing_numeric:
        out = ensure_numeric_columns(out, existing_numeric)

    return out


def safe_read_csv_text(text: str | None) -> pd.DataFrame:
    if not text:
        return pd.DataFrame()
    try:
        from io import StringIO
        return pd.read_csv(StringIO(text))
    except Exception:
        return pd.DataFrame()


# =========================================================
# BOT LEARNING INSIGHT PANEL - READ ONLY
# Chỉ đọc dữ liệu Learning V3.1; tuyệt đối không ghi/xóa dữ liệu học.
# =========================================================
def _best_numeric_feature_band(
    df: pd.DataFrame,
    feature: str,
    success_mask: pd.Series,
    eligible_mask: pd.Series,
    bins: list[float],
    *,
    min_samples: int,
) -> dict | None:
    """Tìm vùng feature có tỷ lệ thành công cao nhất, có chặn mẫu nhỏ."""
    if df is None or df.empty or feature not in df.columns:
        return None

    values = _insight_numeric(df[feature])
    eligible = eligible_mask.fillna(False) & values.notna()
    if int(eligible.sum()) < max(1, min_samples):
        return None

    temp = pd.DataFrame({
        "value": values,
        "eligible": eligible,
        "success": success_mask.fillna(False),
    })
    temp = temp[temp["eligible"]].copy()
    if temp.empty:
        return None

    edges = [-np.inf, *bins, np.inf]
    temp["band"] = pd.cut(
        temp["value"],
        bins=edges,
        include_lowest=True,
        right=False,
    )

    stats = (
        temp.groupby("band", observed=True)
        .agg(samples=("success", "size"), wins=("success", "sum"))
        .reset_index()
    )
    stats["rate"] = np.where(
        stats["samples"] > 0,
        stats["wins"] / stats["samples"] * 100.0,
        np.nan,
    )
    stats = stats[stats["samples"] >= max(1, min_samples)].copy()
    if stats.empty:
        return None

    # Ưu tiên tỷ lệ, sau đó ưu tiên mẫu lớn hơn.
    stats = stats.sort_values(
        ["rate", "samples"], ascending=[False, False], kind="stable"
    )
    best = stats.iloc[0]
    interval = best["band"]
    return {
        "feature": feature,
        "label": _insight_band_label(float(interval.left), float(interval.right)),
        "samples": int(best["samples"]),
        "wins": int(best["wins"]),
        "rate": round(float(best["rate"]), 1),
    }


def _best_category_feature(
    df: pd.DataFrame,
    feature: str,
    success_mask: pd.Series,
    eligible_mask: pd.Series,
    *,
    min_samples: int,
) -> dict | None:
    """Tìm trạng thái/cụm chữ có tỷ lệ thành công cao nhất."""
    if df is None or df.empty or feature not in df.columns:
        return None

    values = df[feature].astype("string").fillna("").str.strip()
    eligible = eligible_mask.fillna(False) & values.ne("")
    if int(eligible.sum()) < max(1, min_samples):
        return None

    temp = pd.DataFrame({
        "value": values,
        "eligible": eligible,
        "success": success_mask.fillna(False),
    })
    temp = temp[temp["eligible"]].copy()
    stats = (
        temp.groupby("value", dropna=False)
        .agg(samples=("success", "size"), wins=("success", "sum"))
        .reset_index()
    )
    stats["rate"] = np.where(
        stats["samples"] > 0,
        stats["wins"] / stats["samples"] * 100.0,
        np.nan,
    )
    stats = stats[stats["samples"] >= max(1, min_samples)].copy()
    if stats.empty:
        return None

    stats = stats.sort_values(
        ["rate", "samples"], ascending=[False, False], kind="stable"
    )
    best = stats.iloc[0]
    return {
        "feature": feature,
        "label": str(best["value"]),
        "samples": int(best["samples"]),
        "wins": int(best["wins"]),
        "rate": round(float(best["rate"]), 1),
    }


def _friendly_pattern_key(pattern_key: str) -> str:
    """Rút gọn pattern_key để đọc được trên giao diện."""
    text = str(pattern_key or "").strip()
    if not text:
        return ""
    parts = [part for part in text.split("|") if part and part != "NA"]
    # Giữ các mảnh có ý nghĩa nhất, tránh một câu quá dài trên mobile.
    preferred = []
    for part in parts:
        upper = part.upper()
        if any(token in upper for token in (
            "RECOVER", "NEUTRAL", "WEAK", "RSI", "EARLY", "PULL",
            "DRYUP", "POSITIVE", "NEGATIVE", "G2", ">=", "60-", "55-",
        )):
            preferred.append(part)
    chosen = preferred[:6] if preferred else parts[:6]
    return " + ".join(chosen)


def _latest_matching_symbols(
    snapshot: pd.DataFrame,
    pattern_key: str,
    *,
    limit: int = 5,
) -> list[str]:
    if (
        snapshot is None
        or snapshot.empty
        or not pattern_key
        or "pattern_key" not in snapshot.columns
        or "symbol" not in snapshot.columns
    ):
        return []

    matched = snapshot[snapshot["pattern_key"].astype(str) == str(pattern_key)].copy()
    if matched.empty:
        return []

    date_col = "trade_date" if "trade_date" in matched.columns else "entry_date"
    if date_col in matched.columns:
        matched[date_col] = pd.to_datetime(matched[date_col], errors="coerce")
        latest_date = matched[date_col].max()
        if pd.notna(latest_date):
            matched = matched[matched[date_col] == latest_date]

    return (
        matched["symbol"]
        .astype(str)
        .str.upper()
        .drop_duplicates()
        .head(max(1, int(limit)))
        .tolist()
    )


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


def fetch_live_price(symbol: str, *, allow_yahoo: bool = True) -> dict:
    """
    Optional Yahoo live quote. NOT a primary Vietnam EOD provider.
    Headless EOD must call with allow_yahoo=False so HNX/UPCoM never depend on Yahoo.
    """
    if not allow_yahoo:
        return {"price": np.nan, "volume": np.nan, "source": "YAHOO_SKIPPED_EOD", "ts": ""}

    if yf is None:
        return {"price": np.nan, "volume": np.nan, "source": "NO_YF", "ts": ""}

    ticker = f"{symbol}{YAHOO_SUFFIX}"

    try:
        import logging as _logging
        import warnings

        yf_logger = _logging.getLogger("yfinance")
        prev_level = yf_logger.level
        yf_logger.setLevel(_logging.CRITICAL)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = yf.download(
                    ticker,
                    period="1d",
                    interval="15m",
                    progress=False,
                    auto_adjust=False,
                    threads=False,
                )
        finally:
            yf_logger.setLevel(prev_level)

        source = "YF_15M"

        if data is None or data.empty:
            yf_logger.setLevel(_logging.CRITICAL)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    data = yf.download(
                        ticker,
                        period="5d",
                        interval="1d",
                        progress=False,
                        auto_adjust=False,
                        threads=False,
                    )
            finally:
                yf_logger.setLevel(prev_level)
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
def inject_live_into_daily(
    raw: pd.DataFrame,
    symbol: str,
    *,
    allow_yahoo: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Bơm live price vào candle cuối theo chế độ an toàn.

    Nguyên tắc V19.2 SAFE:
    - Live lỗi / dữ liệu bẩn / giá rỗng => dùng D1, không crash.
    - Chỉ gán vào df sau khi final_price đã được kiểm tra là số hợp lệ.
    - Bất kỳ lỗi nào trong injection đều fallback về daily dataframe.
    - EOD/headless: allow_yahoo=False keeps VNSTOCK D1 only (Yahoo never primary).
    """
    live = {
        "price": np.nan,
        "volume": np.nan,
        "source": "INIT",
        "ts": "",
        "daily_last_close_before_live": np.nan,
        "eod_provider": "VNSTOCK_D1",
        "bar_date": "",
    }

    try:
        live = fetch_live_price(symbol, allow_yahoo=allow_yahoo)
        if not isinstance(live, dict):
            live = {"price": np.nan, "volume": np.nan, "source": "BAD_LIVE_DICT", "ts": ""}
        live["eod_provider"] = "VNSTOCK_D1"

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
        try:
            live["bar_date"] = str(pd.Timestamp(df.loc[last_idx, "date"]).date())
        except Exception:
            live["bar_date"] = ""

        if not allow_yahoo:
            live["price"] = last_close
            live["volume"] = last_volume
            live["source"] = "VNSTOCK_D1_EOD"
            return df.reset_index(drop=True), live

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
                    "source": "SAFE_MODE_D1",
                    "ts": "",
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

    # Volume nền và volume trước phiên hiện tại.
    # Dry-up phải đo TRƯỚC khi GREEN2 xuất hiện, vì phiên GREEN2 thường volume đã tăng lại.
    x["vol_ma5"] = sma(x["volume"], 5)
    x["vol_ma10"] = sma(x["volume"], 10)
    x["vol_ma20"] = sma(x["volume"], 20)

    x["pre_vol_ma5"] = sma(x["volume"].shift(1), 5)
    x["pre_vol_ma10"] = sma(x["volume"].shift(1), 10)
    x["pre_vol_ma20"] = sma(x["volume"].shift(1), 20)

    x["dryup_ratio_5"] = np.where(
        x["pre_vol_ma20"] > 0,
        x["pre_vol_ma5"] / x["pre_vol_ma20"],
        np.nan,
    )
    x["dryup_ratio_10"] = np.where(
        x["pre_vol_ma20"] > 0,
        x["pre_vol_ma10"] / x["pre_vol_ma20"],
        np.nan,
    )
    x["dryup_ok"] = (x["dryup_ratio_5"] <= 0.75) | (x["dryup_ratio_10"] <= 0.85)

    # Gần đáy: đo khoảng cách so với đáy 20 phiên và 60 phiên.
    low20 = x["close"].rolling(20).min()
    low60 = x["close"].rolling(60).min()
    x["near_bottom_20_pct"] = np.where(low20 > 0, (x["close"] / low20 - 1) * 100, np.nan)
    x["near_bottom_60_pct"] = np.where(low60 > 0, (x["close"] / low60 - 1) * 100, np.nan)

    # Khoảng cách tới đỉnh gần nhất để tránh mua mã đã chạy lưng chừng.
    high20_prev = x["high"].shift(1).rolling(20).max()
    x["dist_high20_pct"] = np.where(high20_prev > 0, (x["close"] / high20_prev - 1) * 100, np.nan)

    x["rs5"] = ((x["close"] / x["close"].shift(5)) - 1) * 100
    x["rs10"] = ((x["close"] / x["close"].shift(10)) - 1) * 100

    x["green_candle"] = x["close"] > x["open"]
    x["body_pct"] = np.where(x["open"] > 0, (x["close"] / x["open"] - 1) * 100, np.nan)

    # GREEN2 bản cũ vẫn giữ để các bảng Storm/Pullback không bị lệch logic.
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

    # GREEN2 EARLY: nhẹ hơn bản cũ, dùng riêng cho vùng đáy.
    # Mục tiêu là bắt 2 nến xanh nhỏ đầu tiên khi RSI còn 45-58.
    x["early_green2"] = np.where(
        (
            x["green_candle"].shift(1)
            & x["green_candle"]
            & (x["close"] > x["close"].shift(1))
            & (x["rsi14"] >= 45)
            & (x["rsi14"] <= 58)
            & (x["rsi14"] > x["rsi14"].shift(1))
            & (x["obv"] > x["obv"].shift(1))
            & (x["body_pct"].fillna(0).abs() <= 5.5)
        ),
        "✅ EARLY GREEN2",
        "",
    )

    x["early_dry_green2"] = np.where(
        (
            x["dryup_ok"]
            & x["early_green2"].astype(str).str.contains("EARLY GREEN2", na=False)
            & (x["near_bottom_20_pct"] <= 12)
            & (x["near_bottom_60_pct"] <= 22)
            & (x["ema9_ma20_slope"] <= 2.5)
        ),
        "🌱 EARLY DRY GREEN2",
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
def analyze_symbol(symbol: str, *, eod_mode: bool = False) -> dict | None:
    raw = download_symbol_data(symbol)
    if raw.empty or len(raw) < 40:
        return None

    # EOD/headless: VNSTOCK D1 only — do not use Yahoo as primary/fallback provider.
    live_df, live_info = inject_live_into_daily(raw, symbol, allow_yahoo=not eod_mode)
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
            "price": safe_round(price, 0),
            "daily_price_before_live": safe_round(daily_price_before_live, 0),
            "live_source": live_info.get("source", ""),
            "live_ts": live_info.get("ts", ""),
            "eod_provider": live_info.get("eod_provider", "VNSTOCK_D1"),
            "bar_date": live_info.get("bar_date", ""),
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
            "total_score": total_score,
        }

    row["group"] = classify_group(row)
    row["warning"] = build_warning(price, ema9_, rsi_, rsi_slope_, obv_, obv_ema9_, pull_label, slope_)
    row["status"] = build_status(total_score, row["warning"], row["group"])

    return row


# =========================================================
# SCAN
# =========================================================
def run_scan(symbols: list[str], *, eod_mode: bool = False) -> pd.DataFrame:
    """Quét watchlist theo chế độ chịu lỗi.

    Một mã lỗi không được phép làm sập toàn bộ scanner.
    Lỗi được ghi vào runtime_error_log.csv, các mã còn lại vẫn chạy bình thường.
    eod_mode=True: Vietnam D1 via vnstock only (no Yahoo live injection).
    """
    rows = []
    total = len(symbols)
    missing = []

    for i, symbol in enumerate(symbols):
        try:
            item = analyze_symbol(symbol, eod_mode=eod_mode)
            if item is not None:
                rows.append(item)
            else:
                missing.append(str(symbol).upper())
        except Exception as e:
            log_runtime_error(symbol, "analyze_symbol", e)
            missing.append(str(symbol).upper())
            continue
        if (i + 1) % 20 == 0 or (i + 1) == total:
            print(
                f"[headless_scan] progress {i+1}/{total} ok={len(rows)} missing={len(missing)}",
                flush=True,
            )

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
        
        return _FORECAST_ENGINE.build_result(
            score=0,
            text="Không có dữ liệu",
        ) 

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
    # =====================================================
    # FORECAST CONFIDENCE V1
    # =====================================================

    confidence = 50.0

    confidence += min(accel * 3, 12)
    confidence += min(strong * 2, 10)
    confidence += min(breakout * 2, 10)
    confidence += min(pull_good * 2, 10)

    confidence += obv_good * 10
    confidence += slope_good * 10

    confidence -= min(weak * 2, 20)

    confidence = round(max(0.0, min(confidence, 100.0)), 1)
    if score >= 8:
        text = "🟢 Forecast tốt 5-10 ngày"

    elif score >= 6:
        text = "🟡 Forecast trung tính-khá"

    elif score >= 4:
        text = "🟠 Forecast yếu"

    else:
        text = "🔴 Forecast rủi ro"
    return _FORECAST_ENGINE.build_result(
        score=score,
        text=text,
        confidence=confidence,
    )
    
