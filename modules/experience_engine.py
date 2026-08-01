from __future__ import annotations

"""
experience_engine.py
Mr.BOT PRO - Experience Engine V2.0

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
- Cung cấp Learning View đầy đủ cho Learning Engine ở Sprint tiếp theo.
- Chưa tác động trực tiếp đến Final Decision.

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

EXPERIENCE_COLUMNS = [
    "experience_id",
    "origin_date",
    "symbol",
    *ORIGIN_FEATURE_COLUMNS,

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

    return row


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

