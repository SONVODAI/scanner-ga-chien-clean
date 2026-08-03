from __future__ import annotations

"""
experience_engine.py
Mr.BOT PRO - Experience Engine V3.0

Mục tiêu
--------
- Nhận `holding_detail` do daily_summary.py tạo ra.
- Gộp T+3 / T+5 / T+10 của cùng một mã và cùng ngày gốc thành một Experience.
- Upsert theo khóa duy nhất: origin_date + symbol.
- Không tạo bản ghi trùng.
- Không làm mất T+ cũ khi batch mới thiếu một kỳ.
- Lưu local an toàn bằng cơ chế validate + backup + atomic write của
  snapshot_storage.py.
- Mang toàn bộ DNA ngày gốc từ Daily Summary vào từng Experience.
- Cung cấp Learning View đầy đủ cho Learning Engine.
- Sinh Experience DNA, Market Context, Pattern Family và Trust Score.
- Cung cấp Dynamic Weights để Pattern Match/Leader Brain dùng chung.
- Chưa tự thay đổi Final Decision; chỉ cung cấp tri thức qua API công khai.

Lưu ý an toàn quan trọng
------------------------
snapshot_storage.py hiện dùng chung biến cấu hình `GITHUB_SNAPSHOT_PATH`.
Vì vậy V2.0 tiếp tục chủ động:
- prefer_remote=False
- push_remote=False

để tuyệt đối không ghi nhầm earning_experiences.csv đè lên file snapshot
trên GitHub. File Experience vẫn được lưu local, có backup và atomic write.
"""

from dataclasses import dataclass
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .snapshot_storage import (
    load_history as storage_load_history,
    save_history as storage_save_history,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EXPERIENCE_FILE = DATA_DIR / "earning_experiences.csv"

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DEFAULT_PERIODS: tuple[int, ...] = (3, 5, 10)


# DNA ngày gốc phải khớp với daily_summary.py V3.
ORIGIN_NUMERIC_COLUMNS = [
    "origin_rank",
    "origin_price",
    "origin_rs5",
    "origin_rs10",
    "origin_rsi14",
    "origin_rsi_slope",
    "origin_ema9",
    "origin_ma20",
    "origin_ema9_ma20_slope",
    "origin_ema9_ma20_slope_change",
    "origin_dist_from_ema9_pct",
    "origin_obv",
    "origin_obv_ema9",
    "origin_volume",
    "origin_vol_ma20",
    "origin_volume_ratio20",
    "origin_dryup_ratio_5",
    "origin_dryup_ratio_10",
    "origin_near_bottom_20_pct",
    "origin_near_bottom_60_pct",
    "origin_dist_high20_pct",
    "origin_body_pct",
    "origin_total_score",
    "origin_E",
    "origin_R",
    "origin_O",
    "origin_S",
    "origin_RS",
    "origin_V",
    "origin_market_real",
    "origin_market_live",
    "origin_market_forecast",
    "origin_market_breadth",
    "origin_market_breadth_score",
]

ORIGIN_TEXT_COLUMNS = [
    "origin_health",
    "origin_action",
    "origin_reason",
    "origin_obv_status",
    "origin_group",
    "origin_pull_label",
    "origin_warning",
    "origin_status",
    "origin_green_2_confirm",
    "origin_early_green2",
    "origin_early_dry_green2",
    "origin_slope_state",
    "origin_market_regime",
]

ORIGIN_BOOLEAN_COLUMNS = [
    "origin_is_live_adjusted",
]

ORIGIN_FEATURE_COLUMNS = (
    ORIGIN_TEXT_COLUMNS
    + ORIGIN_NUMERIC_COLUMNS
    + ORIGIN_BOOLEAN_COLUMNS
)

INTELLIGENCE_COLUMNS = [
    "stock_dna_key",
    "market_context_key",
    "decision_context_key",
    "pattern_family",
    "verified_level",
    "outcome_score",
    "trust_score",
    "experience_quality",
]


EXPERIENCE_COLUMNS = [
    "experience_id",
    "origin_date",
    "symbol",
    *ORIGIN_FEATURE_COLUMNS,
    *INTELLIGENCE_COLUMNS,

    "t3_date",
    "t3_price",
    "t3_return",
    "t3_win",

    "t5_date",
    "t5_price",
    "t5_return",
    "t5_win",

    "t10_date",
    "t10_price",
    "t10_return",
    "t10_win",

    "completed_periods",
    "latest_completed_period",
    "best_period",
    "best_return",
    "worst_period",
    "worst_return",
    "experience_status",

    "created_at",
    "updated_at",
]


# Chỉ yêu cầu các cột thật sự cần để tạo Experience.
# Các cột origin_rank / RS / RSI là tùy chọn để module chịu được schema cũ.
REQUIRED_HOLDING_COLUMNS = {
    "origin_date",
    "target_date",
    "holding_period",
    "symbol",
    "origin_health",
    "origin_price",
    "target_price",
    "return_pct",
}


@dataclass(frozen=True)
class ExperienceResult:
    current_batch: pd.DataFrame
    history: pd.DataFrame
    saved: bool
    status: str
    experience_file: Path


def _empty_experiences() -> pd.DataFrame:
    return pd.DataFrame(columns=EXPERIENCE_COLUMNS)


def _now_text() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


def _normalize_symbol(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def _normalize_date(value: Any) -> str | float:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return np.nan
    return parsed.date().isoformat()


def _normalize_periods(periods: Iterable[int]) -> tuple[int, ...]:
    cleaned: set[int] = set()

    for value in periods:
        try:
            period = int(value)
        except (TypeError, ValueError):
            continue

        if period > 0:
            cleaned.add(period)

    if not cleaned:
        raise ValueError("periods phải có ít nhất một kỳ T+ hợp lệ.")

    return tuple(sorted(cleaned))


def _make_experience_id(origin_date: Any, symbol: Any) -> str:
    date_text = _normalize_date(origin_date)
    symbol_text = _normalize_symbol(symbol)

    if pd.isna(date_text) or not symbol_text:
        return ""

    return f"{date_text}::{symbol_text}"


def _to_number(value: Any) -> float:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(converted) if pd.notna(converted) else np.nan


def _is_missing(value: Any) -> bool:
    if value is None:
        return True

    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass

    if isinstance(value, str):
        return value.strip().lower() in {"", "nan", "none", "nat"}

    return False


def _to_bool(value: Any) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return bool(value)
    return str(value).strip().lower() in {
        "1", "true", "yes", "y", "ok", "x", "có", "co", "đúng", "dung"
    }


def _first_available(row: pd.Series, *columns: str) -> Any:
    for column in columns:
        if column in row.index and not _is_missing(row[column]):
            return row[column]
    return np.nan


def validate_holding_detail(holding_detail: pd.DataFrame) -> None:
    if holding_detail is None:
        raise ValueError("holding_detail không được là None.")

    if not isinstance(holding_detail, pd.DataFrame):
        raise TypeError("holding_detail phải là pandas.DataFrame.")

    missing = REQUIRED_HOLDING_COLUMNS.difference(holding_detail.columns)
    if missing:
        raise ValueError(
            "Experience Engine cần dữ liệu từ build_holding_detail(). "
            f"Thiếu cột: {sorted(missing)}"
        )


def _prepare_holding_detail(
    holding_detail: pd.DataFrame,
    periods: tuple[int, ...],
) -> pd.DataFrame:
    validate_holding_detail(holding_detail)

    if holding_detail.empty:
        return holding_detail.copy()

    detail = holding_detail.copy()

    # Schema cũ vẫn chạy: trường DNA chưa có sẽ được bổ sung rỗng.
    for column in ORIGIN_TEXT_COLUMNS:
        if column not in detail.columns:
            detail[column] = ""

    for column in ORIGIN_NUMERIC_COLUMNS:
        if column not in detail.columns:
            detail[column] = np.nan

    for column in ORIGIN_BOOLEAN_COLUMNS:
        if column not in detail.columns:
            detail[column] = False

    detail["origin_date"] = detail["origin_date"].map(_normalize_date)
    detail["target_date"] = detail["target_date"].map(_normalize_date)
    detail["symbol"] = detail["symbol"].map(_normalize_symbol)

    detail["holding_period"] = pd.to_numeric(
        detail["holding_period"],
        errors="coerce",
    ).astype("Int64")

    numeric_columns = [
        "target_price",
        "return_pct",
        *ORIGIN_NUMERIC_COLUMNS,
    ]
    for column in numeric_columns:
        detail[column] = pd.to_numeric(detail[column], errors="coerce")

    for column in ORIGIN_TEXT_COLUMNS:
        detail[column] = (
            detail[column]
            .astype("object")
            .where(detail[column].notna(), "")
            .astype(str)
        )

    for column in ORIGIN_BOOLEAN_COLUMNS:
        detail[column] = detail[column].map(_to_bool)

    detail = detail[
        detail["origin_date"].notna()
        & detail["symbol"].ne("")
        & detail["holding_period"].isin(periods)
    ].copy()

    if detail.empty:
        return detail.reset_index(drop=True)

    # Mỗi mã + ngày gốc + kỳ T chỉ có một kết quả cuối cùng.
    detail = detail.drop_duplicates(
        ["origin_date", "symbol", "holding_period"],
        keep="last",
    )

    return detail.sort_values(
        ["origin_date", "symbol", "holding_period"],
        kind="stable",
    ).reset_index(drop=True)

def _bucket_number(value: Any, edges: tuple[float, ...], labels: tuple[str, ...]) -> str:
    number = _to_number(value)
    if pd.isna(number):
        return "NA"
    for edge, label in zip(edges, labels):
        if number < edge:
            return label
    return labels[-1]


def _normalize_text_token(value: Any, fallback: str = "NA") -> str:
    if _is_missing(value):
        return fallback
    text = str(value).strip().upper()
    safe = "".join(ch if ch.isalnum() else "_" for ch in text)
    safe = "_".join(part for part in safe.split("_") if part)
    return safe[:40] or fallback


def _obv_token(value: Any) -> str:
    text = _normalize_text_token(value)
    if any(token in text for token in ("UP", "TANG", "DUONG", "XANH", "POSITIVE", "MANH")):
        return "OBV_POSITIVE"
    if any(token in text for token in ("DOWN", "GIAM", "AM", "DO", "NEGATIVE", "YEU")):
        return "OBV_NEGATIVE"
    return "OBV_NEUTRAL"


def _derive_pattern_family(row: dict[str, Any]) -> str:
    group = _normalize_text_token(row.get("origin_group"))
    pull = _normalize_text_token(row.get("origin_pull_label"))
    if bool(row.get("origin_early_green2")) or bool(row.get("origin_early_dry_green2")) or "EARLY" in group:
        return "EARLY"
    if "PULL" in group or "PULL" in pull:
        return "PULLBACK"
    if "BREAK" in group:
        return "BREAKOUT"
    if "HOI" in group or "RECOVER" in group:
        return "RECOVERY"
    if "MANH" in group or "TANG_TOC" in group or "MOMENTUM" in group:
        return "MOMENTUM"
    if "TICH_LUY" in group or "ACCUM" in group:
        return "ACCUMULATION"
    return "GENERAL"


def _derive_stock_dna_key(row: dict[str, Any]) -> str:
    parts = [
        _derive_pattern_family(row),
        "RSI_" + _bucket_number(row.get("origin_rsi14"), (40, 45, 50, 55, 60, 70, math.inf), ("LT40", "40_45", "45_50", "50_55", "55_60", "60_70", "70P")),
        "RS5_" + _bucket_number(row.get("origin_rs5"), (-2, 0, 2, 5, 10, math.inf), ("LTN2", "N2_0", "0_2", "2_5", "5_10", "10P")),
        "RS10_" + _bucket_number(row.get("origin_rs10"), (-2, 0, 2, 5, 10, math.inf), ("LTN2", "N2_0", "0_2", "2_5", "5_10", "10P")),
        _obv_token(row.get("origin_obv_status")),
        "SLOPE_" + _bucket_number(row.get("origin_ema9_ma20_slope"), (-0.2, 0, 0.2, math.inf), ("STRONG_NEG", "NEG", "POS", "STRONG_POS")),
        "VOL_" + _bucket_number(row.get("origin_volume_ratio20"), (0.7, 1.0, 1.2, 1.5, math.inf), ("DRY", "LOW", "NORMAL", "HIGH", "SURGE")),
    ]
    return "|".join(parts)


def _derive_market_context_key(row: dict[str, Any]) -> str:
    regime = _normalize_text_token(row.get("origin_market_regime"), "UNKNOWN")
    real_bucket = _bucket_number(row.get("origin_market_real"), (2, 4, 6, 8, math.inf), ("REAL_LT2", "REAL_2_4", "REAL_4_6", "REAL_6_8", "REAL_8P"))
    forecast_bucket = _bucket_number(row.get("origin_market_forecast"), (2, 4, 6, 8, math.inf), ("FC_LT2", "FC_2_4", "FC_4_6", "FC_6_8", "FC_8P"))
    breadth_bucket = _bucket_number(row.get("origin_market_breadth"), (10, 25, 45, 65, math.inf), ("BR_LT10", "BR_10_25", "BR_25_45", "BR_45_65", "BR_65P"))
    return "|".join(("REGIME_" + regime, real_bucket, forecast_bucket, breadth_bucket))


def _derive_verified_level(row: dict[str, Any]) -> str:
    completed = int(_to_number(row.get("completed_periods")) or 0)
    latest = _to_number(row.get("latest_completed_period"))
    if completed <= 0 or pd.isna(latest):
        return "PENDING"
    return f"T{int(latest)}_VERIFIED"


def _derive_outcome_score(row: dict[str, Any], periods: tuple[int, ...]) -> float:
    weighted_returns: list[tuple[float, float]] = []
    max_period = max(periods) if periods else 10
    for period in periods:
        value = _to_number(row.get(f"t{period}_return"))
        if pd.notna(value):
            weighted_returns.append((value, period / max_period))
    if not weighted_returns:
        return np.nan
    total_weight = sum(weight for _, weight in weighted_returns)
    weighted_return = sum(value * weight for value, weight in weighted_returns) / total_weight
    best = _to_number(row.get("best_return"))
    worst = _to_number(row.get("worst_return"))
    risk_penalty = abs(min(worst, 0.0)) * 1.5 if pd.notna(worst) else 0.0
    upside_bonus = max(best, 0.0) * 0.35 if pd.notna(best) else 0.0
    raw = 50.0 + weighted_return * 4.0 + upside_bonus - risk_penalty
    return round(float(min(max(raw, 0.0), 100.0)), 2)


def _derive_trust_score(row: dict[str, Any], periods: tuple[int, ...]) -> float:
    completed = int(_to_number(row.get("completed_periods")) or 0)
    if completed <= 0:
        return 0.0
    completion = completed / max(len(periods), 1)
    returns = [
        _to_number(row.get(f"t{period}_return"))
        for period in periods
        if pd.notna(_to_number(row.get(f"t{period}_return")))
    ]
    consistency = 1.0
    if len(returns) >= 2:
        consistency = max(0.0, 1.0 - min(float(np.std(returns)) / 12.0, 1.0))
    direction = abs(sum(1 if value > 0 else -1 if value < 0 else 0 for value in returns)) / len(returns)
    latest = max((period for period in periods if pd.notna(_to_number(row.get(f"t{period}_return")))), default=0)
    maturity = latest / max(periods)
    score = 100.0 * (0.45 * completion + 0.25 * consistency + 0.20 * direction + 0.10 * maturity)
    return round(float(min(max(score, 0.0), 100.0)), 2)


def _apply_intelligence_fields(row: dict[str, Any], periods: tuple[int, ...]) -> dict[str, Any]:
    row["pattern_family"] = _derive_pattern_family(row)
    row["stock_dna_key"] = _derive_stock_dna_key(row)
    row["market_context_key"] = _derive_market_context_key(row)
    raw_key = f"{row['market_context_key']}||{row['stock_dna_key']}"
    row["decision_context_key"] = "CTX-" + hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:16].upper()
    row["verified_level"] = _derive_verified_level(row)
    row["outcome_score"] = _derive_outcome_score(row, periods)
    row["trust_score"] = _derive_trust_score(row, periods)
    if row["trust_score"] >= 75 and (pd.notna(row["outcome_score"]) and row["outcome_score"] >= 65):
        row["experience_quality"] = "HIGH_CONFIDENCE_WIN"
    elif row["trust_score"] >= 55 and (pd.notna(row["outcome_score"]) and row["outcome_score"] >= 55):
        row["experience_quality"] = "CONFIRMED_WIN"
    elif row["trust_score"] >= 55 and (pd.notna(row["outcome_score"]) and row["outcome_score"] < 45):
        row["experience_quality"] = "CONFIRMED_LOSS"
    elif row["verified_level"] == "PENDING":
        row["experience_quality"] = "PENDING"
    else:
        row["experience_quality"] = "MIXED"
    return row


def _recalculate_derived_fields(
    row: dict[str, Any],
    periods: tuple[int, ...],
) -> dict[str, Any]:
    completed: list[tuple[int, float]] = []

    for period in periods:
        value = _to_number(row.get(f"t{period}_return"))
        if pd.notna(value):
            completed.append((period, value))
            row[f"t{period}_win"] = bool(value > 0)
        else:
            row[f"t{period}_win"] = np.nan

    row["completed_periods"] = len(completed)
    row["latest_completed_period"] = (
        max(period for period, _ in completed)
        if completed
        else np.nan
    )

    if completed:
        best_period, best_return = max(completed, key=lambda item: item[1])
        worst_period, worst_return = min(completed, key=lambda item: item[1])

        row["best_period"] = best_period
        row["best_return"] = best_return
        row["worst_period"] = worst_period
        row["worst_return"] = worst_return
    else:
        row["best_period"] = np.nan
        row["best_return"] = np.nan
        row["worst_period"] = np.nan
        row["worst_return"] = np.nan

    if not completed:
        row["experience_status"] = "PENDING"
    elif len(completed) < len(periods):
        row["experience_status"] = "PARTIAL"
    else:
        row["experience_status"] = "COMPLETED"

    return _apply_intelligence_fields(row, periods)


def build_experiences(
    holding_detail: pd.DataFrame,
    periods: Iterable[int] = DEFAULT_PERIODS,
) -> pd.DataFrame:
    """
    Chuyển holding_detail dạng dài thành Experience dạng rộng.

    Một dòng tương ứng:
        một ngày gốc + một mã

    Các kỳ T+ được đặt trên cùng dòng.
    """
    normalized_periods = _normalize_periods(periods)
    detail = _prepare_holding_detail(holding_detail, normalized_periods)

    if detail.empty:
        return _empty_experiences()

    now_text = _now_text()
    rows: list[dict[str, Any]] = []

    grouped = detail.groupby(
        ["origin_date", "symbol"],
        sort=True,
        dropna=False,
    )

    for (origin_date, symbol), group in grouped:
        group = group.sort_values("holding_period", kind="stable")
        origin = group.iloc[0]

        row: dict[str, Any] = {
            "experience_id": _make_experience_id(origin_date, symbol),
            "origin_date": origin_date,
            "symbol": symbol,
            "created_at": now_text,
            "updated_at": now_text,
        }

        # Đóng băng toàn bộ DNA tại ngày gốc trên cùng một Experience.
        for feature in ORIGIN_FEATURE_COLUMNS:
            row[feature] = _first_available(origin, feature)

        for period in normalized_periods:
            prefix = f"t{period}"
            period_rows = group[group["holding_period"].eq(period)]

            if period_rows.empty:
                row[f"{prefix}_date"] = np.nan
                row[f"{prefix}_price"] = np.nan
                row[f"{prefix}_return"] = np.nan
                row[f"{prefix}_win"] = np.nan
                continue

            item = period_rows.iloc[-1]
            return_value = _to_number(item.get("return_pct"))

            row[f"{prefix}_date"] = item.get("target_date", np.nan)
            row[f"{prefix}_price"] = _to_number(item.get("target_price"))
            row[f"{prefix}_return"] = return_value
            row[f"{prefix}_win"] = (
                bool(return_value > 0)
                if pd.notna(return_value)
                else np.nan
            )

        row = _recalculate_derived_fields(row, normalized_periods)
        rows.append(row)

    result = pd.DataFrame(rows)

    for column in EXPERIENCE_COLUMNS:
        if column not in result.columns:
            result[column] = np.nan

    result = result[
        result["experience_id"].ne("")
        & result["origin_date"].notna()
        & result["symbol"].ne("")
    ].copy()

    result = result.drop_duplicates("experience_id", keep="last")

    return (
        result.sort_values(
            ["origin_date", "symbol"],
            kind="stable",
        )
        .reset_index(drop=True)
        .reindex(columns=EXPERIENCE_COLUMNS)
    )


def load_experience_history(
    experience_file: str | Path = EXPERIENCE_FILE,
) -> pd.DataFrame:
    """
    Đọc lịch sử Experience local.

    V2.0 không đọc GitHub để tránh dùng nhầm GITHUB_SNAPSHOT_PATH.
    """
    path = Path(experience_file)

    try:
        history = storage_load_history(
            path,
            EXPERIENCE_COLUMNS,
            key_columns=("experience_id",),
            prefer_remote=False,
        )
    except Exception:
        return _empty_experiences()

    if history.empty:
        return _empty_experiences()

    for column in EXPERIENCE_COLUMNS:
        if column not in history.columns:
            history[column] = np.nan

    history["origin_date"] = history["origin_date"].map(_normalize_date)
    history["symbol"] = history["symbol"].map(_normalize_symbol)

    for column in ORIGIN_NUMERIC_COLUMNS:
        history[column] = pd.to_numeric(history[column], errors="coerce")

    for column in ORIGIN_TEXT_COLUMNS:
        history[column] = (
            history[column]
            .astype("object")
            .where(history[column].notna(), "")
            .astype(str)
        )

    for column in ORIGIN_BOOLEAN_COLUMNS:
        history[column] = history[column].map(_to_bool)

    for period in DEFAULT_PERIODS:
        date_column = f"t{period}_date"
        if date_column in history.columns:
            history[date_column] = history[date_column].map(_normalize_date)

    # V3: tự backfill Intelligence cho lịch sử V2 mà không cần migrate thủ công.
    history = history.apply(
        lambda item: pd.Series(
            _apply_intelligence_fields(item.to_dict(), DEFAULT_PERIODS)
        ),
        axis=1,
    )

    # Tái tạo khóa nếu file cũ bị thiếu experience_id.
    history["experience_id"] = history.apply(
        lambda row: (
            str(row["experience_id"]).strip()
            if not _is_missing(row["experience_id"])
            else _make_experience_id(
                row["origin_date"],
                row["symbol"],
            )
        ),
        axis=1,
    )

    history = history[
        history["experience_id"].ne("")
        & history["origin_date"].notna()
        & history["symbol"].ne("")
    ].copy()

    history = history.drop_duplicates("experience_id", keep="last")

    return (
        history.sort_values(
            ["origin_date", "symbol"],
            kind="stable",
        )
        .reset_index(drop=True)
        .reindex(columns=EXPERIENCE_COLUMNS)
    )


def _merge_one_experience(
    old_row: pd.Series | None,
    new_row: pd.Series,
    periods: tuple[int, ...],
) -> dict[str, Any]:
    """
    Merge theo từng trường.

    Giá trị mới chỉ thay giá trị cũ khi nó thực sự có dữ liệu.
    Vì vậy batch chỉ có T3 sẽ không xóa T5/T10 đã lưu từ trước.
    """
    now_text = _now_text()
    merged: dict[str, Any] = {}

    for column in EXPERIENCE_COLUMNS:
        new_value = new_row.get(column, np.nan)

        if old_row is None:
            merged[column] = new_value
            continue

        old_value = old_row.get(column, np.nan)
        merged[column] = (
            new_value
            if not _is_missing(new_value)
            else old_value
        )

    if old_row is not None and not _is_missing(old_row.get("created_at")):
        merged["created_at"] = old_row.get("created_at")
    elif _is_missing(merged.get("created_at")):
        merged["created_at"] = now_text

    merged["updated_at"] = now_text
    merged = _recalculate_derived_fields(merged, periods)

    return merged


def merge_experiences(
    history: pd.DataFrame,
    current_batch: pd.DataFrame,
    periods: Iterable[int] = DEFAULT_PERIODS,
) -> pd.DataFrame:
    """
    Upsert Experience theo experience_id mà không làm mất dữ liệu T+ cũ.
    """
    normalized_periods = _normalize_periods(periods)

    old = (
        history.reindex(columns=EXPERIENCE_COLUMNS).copy()
        if history is not None and not history.empty
        else _empty_experiences()
    )
    new = (
        current_batch.reindex(columns=EXPERIENCE_COLUMNS).copy()
        if current_batch is not None and not current_batch.empty
        else _empty_experiences()
    )

    if new.empty:
        return old.reset_index(drop=True)

    old_map: dict[str, pd.Series] = {}
    if not old.empty:
        old = old.drop_duplicates("experience_id", keep="last")
        old_map = {
            str(row["experience_id"]): row
            for _, row in old.iterrows()
        }

    merged_rows: list[dict[str, Any]] = []

    # Giữ các Experience cũ không xuất hiện trong batch.
    new_ids = set(new["experience_id"].astype(str))
    for experience_id, row in old_map.items():
        if experience_id not in new_ids:
            merged_rows.append(row.to_dict())

    # Upsert từng Experience trong batch.
    for _, new_row in new.iterrows():
        experience_id = str(new_row["experience_id"])
        old_row = old_map.get(experience_id)

        merged_rows.append(
            _merge_one_experience(
                old_row,
                new_row,
                normalized_periods,
            )
        )

    merged = pd.DataFrame(merged_rows)

    for column in EXPERIENCE_COLUMNS:
        if column not in merged.columns:
            merged[column] = np.nan

    merged = merged[
        merged["experience_id"].notna()
        & merged["experience_id"].astype(str).str.strip().ne("")
    ].copy()

    merged = merged.drop_duplicates("experience_id", keep="last")

    return (
        merged.sort_values(
            ["origin_date", "symbol"],
            kind="stable",
        )
        .reset_index(drop=True)
        .reindex(columns=EXPERIENCE_COLUMNS)
    )


def save_experience_history(
    history: pd.DataFrame,
    experience_file: str | Path = EXPERIENCE_FILE,
) -> None:
    """
    Lưu toàn bộ lịch sử Experience local bằng Snapshot Storage.

    Có:
    - validate schema,
    - backup file cũ,
    - atomic write.

    Không push GitHub ở V2.0 để tránh ghi nhầm remote snapshot.
    """
    if history is None or history.empty:
        raise ValueError("Từ chối lưu Experience history rỗng.")

    storage_save_history(
        history,
        Path(experience_file),
        EXPERIENCE_COLUMNS,
        key_columns=("experience_id",),
        push_remote=False,
    )


def run_experience_engine(
    holding_detail: pd.DataFrame,
    *,
    periods: Iterable[int] = DEFAULT_PERIODS,
    experience_file: str | Path = EXPERIENCE_FILE,
    save: bool = True,
) -> ExperienceResult:
    """
    Hàm điều phối chính.

    Quy trình:
        holding_detail
            -> build current batch
            -> load local history
            -> field-wise upsert
            -> safe local save
    """
    normalized_periods = _normalize_periods(periods)

    current_batch = build_experiences(
        holding_detail,
        periods=normalized_periods,
    )

    old_history = load_experience_history(experience_file)

    history = merge_experiences(
        old_history,
        current_batch,
        periods=normalized_periods,
    )

    saved = False
    if save and not current_batch.empty:
        save_experience_history(
            history,
            experience_file=experience_file,
        )
        saved = True

    total = len(history)
    completed = (
        int(history["experience_status"].eq("COMPLETED").sum())
        if not history.empty
        else 0
    )
    partial = (
        int(history["experience_status"].eq("PARTIAL").sum())
        if not history.empty
        else 0
    )
    pending = (
        int(history["experience_status"].eq("PENDING").sum())
        if not history.empty
        else 0
    )

    if current_batch.empty:
        status = (
            "Experience Engine chưa nhận được phép thử T+ hợp lệ. "
            f"Lịch sử hiện có {total} Experience."
        )
    else:
        action = "Đã lưu" if saved else "Đã tạo"
        status = (
            f"{action} {len(current_batch)} Experience trong batch hiện tại. "
            f"Tổng lịch sử: {total} — Completed: {completed}, "
            f"Partial: {partial}, Pending: {pending}."
        )

    return ExperienceResult(
        current_batch=current_batch,
        history=history,
        saved=saved,
        status=status,
        experience_file=Path(experience_file),
    )


def get_completed_experiences(
    history: pd.DataFrame | None = None,
    *,
    experience_file: str | Path = EXPERIENCE_FILE,
    min_period: int = 3,
) -> pd.DataFrame:
    """
    Lấy các Experience có kết quả tại một kỳ T+ cụ thể.
    """
    if history is None:
        history = load_experience_history(experience_file)

    if history is None or history.empty:
        return _empty_experiences()

    period = int(min_period)
    return_column = f"t{period}_return"

    if return_column not in history.columns:
        raise ValueError(f"Experience schema không có kỳ T{period}.")

    mask = pd.to_numeric(
        history[return_column],
        errors="coerce",
    ).notna()

    return history[mask].copy().reset_index(drop=True)


def build_learning_view(
    history: pd.DataFrame | None = None,
    *,
    experience_file: str | Path = EXPERIENCE_FILE,
    target_period: int = 3,
) -> pd.DataFrame:
    """
    Sinh bảng đầu vào phẳng cho Learning Engine.

    Toàn bộ DNA ngày gốc được giữ lại tự động; target_return và target_win
    là nhãn của kỳ T+ được chọn.
    """
    if history is None:
        history = load_experience_history(experience_file)

    if history is None or history.empty:
        return pd.DataFrame()

    period = int(target_period)
    return_column = f"t{period}_return"
    win_column = f"t{period}_win"

    if return_column not in history.columns:
        raise ValueError(f"Không có dữ liệu T{period} trong Experience schema.")

    base_columns = [
        "experience_id",
        "origin_date",
        "symbol",
        *ORIGIN_FEATURE_COLUMNS,
        return_column,
        win_column,
        "best_period",
        "best_return",
        "worst_period",
        "worst_return",
        "experience_status",
    ]
    available_columns = [
        column for column in base_columns if column in history.columns
    ]

    mask = pd.to_numeric(
        history[return_column],
        errors="coerce",
    ).notna()

    view = history.loc[mask, available_columns].copy()

    return view.rename(
        columns={
            return_column: "target_return",
            win_column: "target_win",
        }
    ).reset_index(drop=True)

def build_experience_knowledge(
    history: pd.DataFrame | None = None,
    *,
    experience_file: str | Path = EXPERIENCE_FILE,
    target_period: int = 5,
    min_samples: int = 2,
) -> pd.DataFrame:
    """Tổng hợp Verified Experience theo Market Context + Stock DNA."""
    if history is None:
        history = load_experience_history(experience_file)
    if history is None or history.empty:
        return pd.DataFrame()
    period = int(target_period)
    return_col = f"t{period}_return"
    if return_col not in history.columns:
        raise ValueError(f"Experience schema không có kỳ T{period}.")
    data = history.copy()
    data[return_col] = pd.to_numeric(data[return_col], errors="coerce")
    data = data[data[return_col].notna()].copy()
    if data.empty:
        return pd.DataFrame()
    data["_win"] = (data[return_col] > 0).astype(int)
    data["trust_score"] = pd.to_numeric(data["trust_score"], errors="coerce").fillna(0)
    grouped = (
        data.groupby(
            ["market_context_key", "stock_dna_key", "pattern_family"],
            dropna=False,
        )
        .agg(
            samples=("experience_id", "count"),
            symbols=("symbol", "nunique"),
            wins=("_win", "sum"),
            avg_return=(return_col, "mean"),
            median_return=(return_col, "median"),
            avg_trust=("trust_score", "mean"),
            first_seen=("origin_date", "min"),
            last_seen=("origin_date", "max"),
        )
        .reset_index()
    )
    grouped = grouped[grouped["samples"] >= max(int(min_samples), 1)].copy()
    if grouped.empty:
        return grouped
    grouped["winrate"] = grouped["wins"] / grouped["samples"] * 100.0
    sample_confidence = np.minimum(grouped["samples"] / 20.0, 1.0) * 100.0
    grouped["experience_confidence"] = (
        grouped["winrate"] * 0.45
        + grouped["avg_trust"] * 0.30
        + sample_confidence * 0.25
    ).clip(0, 100).round(2)
    grouped["experience_score"] = (
        grouped["experience_confidence"] * 0.55
        + (50 + grouped["avg_return"] * 5).clip(0, 100) * 0.45
    ).clip(0, 100).round(2)
    grouped["target_period"] = period
    grouped["updated_at"] = _now_text()
    return grouped.sort_values(
        ["experience_score", "samples"],
        ascending=[False, False],
        kind="stable",
    ).reset_index(drop=True)


def get_dynamic_weights(
    history: pd.DataFrame | None = None,
    *,
    experience_file: str | Path = EXPERIENCE_FILE,
    target_period: int = 5,
) -> dict[str, float]:
    """Ước lượng trọng số động từ khả năng phân tách thắng/thua của từng feature."""
    defaults = {
        "rsi": 22.0,
        "rs": 18.0,
        "obv": 15.0,
        "leader": 20.0,
        "market": 15.0,
        "continuation": 10.0,
    }
    if history is None:
        history = load_experience_history(experience_file)
    if history is None or history.empty:
        return defaults
    period = int(target_period)
    return_col = f"t{period}_return"
    if return_col not in history.columns:
        return defaults
    data = history.copy()
    data[return_col] = pd.to_numeric(data[return_col], errors="coerce")
    data = data[data[return_col].notna()].copy()
    if len(data) < 12:
        return defaults
    data["_win"] = (data[return_col] > 0).astype(int)
    feature_groups = {
        "rsi": ["origin_rsi14", "origin_rsi_slope"],
        "rs": ["origin_rs5", "origin_rs10", "origin_RS"],
        "obv": ["origin_obv", "origin_obv_ema9"],
        "leader": ["origin_total_score", "origin_rank"],
        "market": ["origin_market_real", "origin_market_forecast", "origin_market_breadth"],
        "continuation": ["t3_return", "t5_return"],
    }
    raw: dict[str, float] = {}
    for name, columns in feature_groups.items():
        strengths: list[float] = []
        for column in columns:
            if column not in data.columns:
                continue
            values = pd.to_numeric(data[column], errors="coerce")
            valid = values.notna()
            if valid.sum() < 8 or values[valid].nunique() < 2:
                continue
            winners = values[valid & data["_win"].eq(1)]
            losers = values[valid & data["_win"].eq(0)]
            if winners.empty or losers.empty:
                continue
            pooled = float(values[valid].std(ddof=0))
            if not math.isfinite(pooled) or pooled <= 1e-9:
                continue
            strengths.append(abs(float(winners.mean() - losers.mean())) / pooled)
        raw[name] = float(np.mean(strengths)) if strengths else 0.0
    if sum(raw.values()) <= 1e-9:
        return defaults
    total_budget = sum(defaults.values())
    floor = 5.0
    remaining = total_budget - floor * len(defaults)
    strength_sum = sum(raw.values())
    weights = {
        name: round(floor + remaining * raw.get(name, 0.0) / strength_sum, 2)
        for name in defaults
    }
    return weights


def get_experience_brain(
    history: pd.DataFrame | None = None,
    *,
    experience_file: str | Path = EXPERIENCE_FILE,
    target_period: int = 5,
) -> dict[str, Any]:
    """API chung để Pattern Match và Leader Brain lấy cùng một nguồn tri thức."""
    if history is None:
        history = load_experience_history(experience_file)
    return {
        "history": history,
        "knowledge": build_experience_knowledge(
            history, target_period=target_period
        ),
        "dynamic_weights": get_dynamic_weights(
            history, target_period=target_period
        ),
        "target_period": int(target_period),
        "generated_at": _now_text(),
    }

