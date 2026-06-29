# =========================================================
# MR.BOT V21 - MARKET SNAPSHOT ENGINE
# File: market_snapshot.py
# Nhiệm vụ:
#   - Chụp ảnh trạng thái thị trường mỗi phiên
#   - Lưu REAL / LIVE / FORECAST / Breadth / nhóm cổ phiếu
#   - Dùng BrainStorage để lưu bền CSV + GitHub
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
MARKET_SNAPSHOT_TABLE = "market_snapshot"


def ms_now():
    return datetime.now(VN_TZ)


def ms_today_str():
    return ms_now().strftime("%Y-%m-%d")


def ms_time_str():
    return ms_now().strftime("%H:%M:%S")


def market_session_slot(now=None) -> str:
    if now is None:
        now = ms_now()

    hm = now.hour * 60 + now.minute

    if hm < 9 * 60:
        return "PRE_MARKET"
    if hm < 11 * 60 + 30:
        return "MORNING"
    if hm < 13 * 60:
        return "MIDDAY"
    if hm < 14 * 60 + 45:
        return "AFTERNOON"
    if hm < 15 * 60 + 30:
        return "CLOSE"
    return "AFTER_CLOSE"


def safe_num(s, default=np.nan):
    try:
        return pd.to_numeric(s, errors="coerce")
    except Exception:
        return default


def pct_true(series) -> float:
    try:
        if series is None or len(series) == 0:
            return np.nan
        return round(float(series.sum()) / len(series) * 100, 2)
    except Exception:
        return np.nan


def count_group(scan_df: pd.DataFrame, group_name: str) -> int:
    if scan_df is None or scan_df.empty or "group" not in scan_df.columns:
        return 0
    return int((scan_df["group"].astype(str) == group_name).sum())


def count_contains(scan_df: pd.DataFrame, col: str, keyword: str) -> int:
    if scan_df is None or scan_df.empty or col not in scan_df.columns:
        return 0
    return int(scan_df[col].astype(str).str.contains(keyword, na=False).sum())


def mean_col(scan_df: pd.DataFrame, col: str):
    if scan_df is None or scan_df.empty or col not in scan_df.columns:
        return np.nan
    x = pd.to_numeric(scan_df[col], errors="coerce")
    if x.dropna().empty:
        return np.nan
    return round(float(x.mean()), 3)


def median_col(scan_df: pd.DataFrame, col: str):
    if scan_df is None or scan_df.empty or col not in scan_df.columns:
        return np.nan
    x = pd.to_numeric(scan_df[col], errors="coerce")
    if x.dropna().empty:
        return np.nan
    return round(float(x.median()), 3)


def top_symbols_by_score(scan_df: pd.DataFrame, n: int = 10) -> str:
    if scan_df is None or scan_df.empty or "symbol" not in scan_df.columns:
        return ""

    df = scan_df.copy()

    score_col = None
    for c in ["total_score", "TREND_SCORE", "BUY_SCORE", "storm_score", "evolution"]:
        if c in df.columns:
            score_col = c
            break

    if score_col:
        df[score_col] = pd.to_numeric(df[score_col], errors="coerce")
        df = df.sort_values(score_col, ascending=False)

    return ",".join(df["symbol"].astype(str).head(n).tolist())


def build_market_snapshot_row(
    scan_df: pd.DataFrame,
    market_real,
    market_live,
    market_forecast,
    market_forecast_text: str = "",
    market_status: str = "",
    market_action: str = "",
    trading_today: bool = True,
    trading_reason: str = "",
    extra_note: str = "",
) -> dict:
    """
    Tạo một dòng snapshot thị trường.
    Không ghi file ở đây.
    """

    if scan_df is None:
        scan_df = pd.DataFrame()

    total = len(scan_df)
    slot = market_session_slot()

    live_ok = int(scan_df["is_live_adjusted"].sum()) if "is_live_adjusted" in scan_df.columns else 0

    safe_data = 0
    if "live_source" in scan_df.columns:
        safe_data = int(
            scan_df["live_source"]
            .astype(str)
            .str.contains("SAFE_MODE|NO_DATA|BAD", na=False)
            .sum()
        )

    obv_green_pct = np.nan
    if "obv_status" in scan_df.columns and total > 0:
        obv_green_pct = pct_true(scan_df["obv_status"].astype(str).eq("🟢"))

    slope_positive_pct = np.nan
    if "ema9_ma20_slope" in scan_df.columns and total > 0:
        slope_positive_pct = pct_true(
            pd.to_numeric(scan_df["ema9_ma20_slope"], errors="coerce").gt(0)
        )

    rsi_above_50_pct = np.nan
    if "rsi14" in scan_df.columns and total > 0:
        rsi_above_50_pct = pct_true(
            pd.to_numeric(scan_df["rsi14"], errors="coerce").gt(50)
        )

    dist_near_ema9_pct = np.nan
    if "dist_from_ema9_pct" in scan_df.columns and total > 0:
        dist_near_ema9_pct = pct_true(
            pd.to_numeric(scan_df["dist_from_ema9_pct"], errors="coerce").abs().le(3)
        )

    row = {
        "date": ms_today_str(),
        "time": ms_time_str(),
        "session_slot": slot,

        "trading_today": bool(trading_today),
        "trading_reason": trading_reason,
        "note": extra_note,

        "market_real": market_real,
        "market_live": market_live,
        "market_forecast": market_forecast,
        "forecast_text": market_forecast_text,
        "market_status": market_status,
        "market_action": market_action,

        "total_symbols": total,
        "live_ok": live_ok,
        "safe_data": safe_data,

        "obv_green_pct": obv_green_pct,
        "slope_positive_pct": slope_positive_pct,
        "rsi_above_50_pct": rsi_above_50_pct,
        "dist_near_ema9_pct": dist_near_ema9_pct,

        "avg_total_score": mean_col(scan_df, "total_score"),
        "avg_rsi14": mean_col(scan_df, "rsi14"),
        "avg_slope": mean_col(scan_df, "ema9_ma20_slope"),
        "avg_dist_ema9_pct": mean_col(scan_df, "dist_from_ema9_pct"),
        "avg_vol_ratio": mean_col(scan_df, "vol_ratio"),

        "median_total_score": median_col(scan_df, "total_score"),
        "median_rsi14": median_col(scan_df, "rsi14"),
        "median_slope": median_col(scan_df, "ema9_ma20_slope"),

        "ga_tang_toc": count_group(scan_df, "GÀ TĂNG TỐC"),
        "cp_manh": count_group(scan_df, "CP MẠNH"),
        "mua_break": count_group(scan_df, "MUA BREAK"),
        "pull_dep": count_group(scan_df, "PULL ĐẸP"),
        "pull_vua": count_group(scan_df, "PULL VỪA"),
        "mua_early": count_group(scan_df, "MUA EARLY"),
        "tich_luy": count_group(scan_df, "TÍCH LŨY"),
        "theo_doi": count_group(scan_df, "THEO DÕI"),

        "green2_count": count_contains(scan_df, "green2", "GREEN"),
        "storm_count": count_contains(scan_df, "Storm", "🌪|STORM|storm"),
        "early_dry_green2_count": count_contains(scan_df, "early_dry_green2", "EARLY|GREEN"),

        "top_symbols": top_symbols_by_score(scan_df, n=12),
    }

    return row


def save_market_snapshot(
    brain,
    scan_df: pd.DataFrame,
    market_real,
    market_live,
    market_forecast,
    market_forecast_text: str = "",
    market_status: str = "",
    market_action: str = "",
    trading_today: bool = True,
    trading_reason: str = "",
    keep_days: int = 240,
    extra_note: str = "",
):
    """
    Hàm chính app.py sẽ gọi.

    Trả về:
    - snapshot_df
    - status
    - snapshot_row
    """

    old_df = brain.recall(MARKET_SNAPSHOT_TABLE)

    if not trading_today:
        return old_df, f"SKIP_NO_TRADING_DAY | {trading_reason}", {}

    row = build_market_snapshot_row(
        scan_df=scan_df,
        market_real=market_real,
        market_live=market_live,
        market_forecast=market_forecast,
        market_forecast_text=market_forecast_text,
        market_status=market_status,
        market_action=market_action,
        trading_today=trading_today,
        trading_reason=trading_reason,
        extra_note=extra_note,
    )

    snapshot_df, status = brain.remember(
        table=MARKET_SNAPSHOT_TABLE,
        data=row,
        key=["date", "session_slot"],
        keep_days=keep_days,
        date_col="date",
        sort_by=["date", "session_slot"],
        sync_github=True,
        prefer_github=True,
    )

    return snapshot_df, status, row


def load_market_snapshot(brain) -> pd.DataFrame:
    return brain.recall(MARKET_SNAPSHOT_TABLE)


def latest_market_snapshot(brain) -> dict:
    df = load_market_snapshot(brain)

    if df is None or df.empty:
        return {}

    sort_cols = [c for c in ["date", "time"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)

    return df.tail(1).iloc[0].to_dict()


def build_market_snapshot_view(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bảng gọn để hiển thị trong Streamlit.
    """

    if df is None or df.empty:
        return pd.DataFrame()

    show_cols = [
        "date", "time", "session_slot",
        "market_real", "market_live", "market_forecast",
        "obv_green_pct", "slope_positive_pct", "rsi_above_50_pct",
        "pull_dep", "pull_vua", "mua_early",
        "cp_manh", "ga_tang_toc",
        "safe_data",
        "top_symbols",
    ]

    cols = [c for c in show_cols if c in df.columns]
    out = df[cols].copy()

    if "date" in out.columns:
        out = out.sort_values(["date", "time"] if "time" in out.columns else ["date"], ascending=False)

    return out


def market_snapshot_summary(snapshot_df: pd.DataFrame) -> dict:
    """
    Tóm tắt nhanh cho dashboard.
    """

    if snapshot_df is None or snapshot_df.empty:
        return {
            "count": 0,
            "days": 0,
            "message": "Chưa có snapshot thị trường.",
        }

    df = snapshot_df.copy()

    days = 0
    if "date" in df.columns:
        days = df["date"].astype(str).nunique()

    latest = df.tail(1).iloc[0].to_dict()

    msg = (
        f"Đã lưu {len(df)} snapshot / {days} ngày. "
        f"Snapshot mới nhất: {latest.get('date', '')} {latest.get('session_slot', '')} "
        f"| REAL {latest.get('market_real', '')} "
        f"| FORECAST {latest.get('market_forecast', '')}."
    )

    return {
        "count": len(df),
        "days": days,
        "latest": latest,
        "message": msg,
    }
