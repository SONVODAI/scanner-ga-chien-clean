from __future__ import annotations

"""
Experience Engine V1
====================

Vai trò
-------
- Nhận dữ liệu `holding_detail` từ `daily_summary.py`.
- Gộp các kết quả T+3 / T+5 / T+10 của cùng một mã và cùng ngày gốc
  thành đúng một bản ghi kinh nghiệm.
- Lưu lịch sử kinh nghiệm theo cơ chế upsert an toàn.
- Không sửa snapshot gốc, không tính lại chỉ báo kỹ thuật, không tác động
  đến Final Decision.

Khóa duy nhất của một Experience:
    experience_id = origin_date + "::" + symbol

File mặc định:
    data/earning_experiences.csv
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
    merge_upsert as storage_merge_upsert,
    save_history as storage_save_history,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EXPERIENCE_FILE = DATA_DIR / "earning_experiences.csv"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DEFAULT_PERIODS: tuple[int, ...] = (3, 5, 10)


EXPERIENCE_COLUMNS = [
    "experience_id",
    "origin_date",
    "symbol",
    "origin_health",
    "origin_rank",
    "origin_price",
    "origin_rs5",
    "origin_rs10",
    "origin_rsi14",

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


REQUIRED_HOLDING_COLUMNS = {
    "origin_date",
    "target_date",
    "holding_period",
    "symbol",
    "origin_health",
    "origin_rank",
    "origin_price",
    "target_price",
    "return_pct",
    "win",
    "origin_rs5",
    "origin_rs10",
    "origin_rsi14",
}


@dataclass
class ExperienceResult:
    current_batch: pd.DataFrame
    history: pd.DataFrame
    saved: bool
    status: str
    experience_file: Path


def _empty_experiences() -> pd.DataFrame:
    return pd.DataFrame(columns=EXPERIENCE_COLUMNS)


def _normalize_symbol(value: Any) -> str:
    return str(value).strip().upper()


def _normalize_date(value: Any) -> str | float:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return np.nan
    return parsed.date().isoformat()


def _normalize_periods(periods: Iterable[int]) -> tuple[int, ...]:
    cleaned = sorted({int(p) for p in periods if int(p) > 0})
    if not cleaned:
        raise ValueError("periods phải có ít nhất một số nguyên dương.")
    return tuple(cleaned)


def _experience_id(origin_date: Any, symbol: Any) -> str:
    date_text = _normalize_date(origin_date)
    symbol_text = _normalize_symbol(symbol)
    if pd.isna(date_text) or not symbol_text or symbol_text == "NAN":
        return ""
    return f"{date_text}::{symbol_text}"


def _safe_bool(value: Any) -> bool | float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, (bool, np.bool_)):
        return bool(value)

    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "win", "w"}:
        return True
    if text in {"false", "0", "no", "n", "loss", "l"}:
        return False
    return np.nan


def _status_from_completed_count(
    completed_count: int,
    expected_count: int,
) -> str:
    if completed_count <= 0:
        return "PENDING"
    if completed_count < expected_count:
        return "PARTIAL"
    return "COMPLETED"


def validate_holding_detail(holding_detail: pd.DataFrame) -> None:
    if holding_detail is None:
        raise ValueError("holding_detail không được là None.")

    missing = REQUIRED_HOLDING_COLUMNS.difference(holding_detail.columns)
    if missing:
        raise ValueError(
            "Experience Engine nhận dữ liệu từ build_holding_detail(). "
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

    detail["origin_date"] = detail["origin_date"].map(_normalize_date)
    detail["target_date"] = detail["target_date"].map(_normalize_date)
    detail["symbol"] = detail["symbol"].map(_normalize_symbol)
    detail["holding_period"] = pd.to_numeric(
        detail["holding_period"], errors="coerce"
    ).astype("Int64")

    numeric_columns = [
        "origin_rank",
        "origin_price",
        "target_price",
        "return_pct",
        "origin_rs5",
        "origin_rs10",
        "origin_rsi14",
    ]
    for col in numeric_columns:
        detail[col] = pd.to_numeric(detail[col], errors="coerce")

    detail["win"] = detail["win"].map(_safe_bool)

    detail = detail[
        detail["origin_date"].notna()
        & detail["symbol"].ne("")
        & detail["symbol"].ne("NAN")
        & detail["holding_period"].isin(periods)
    ].copy()

    # Cùng ngày gốc + mã + kỳ nắm giữ chỉ giữ bản cập nhật cuối cùng.
    detail = detail.drop_duplicates(
        ["origin_date", "symbol", "holding_period"],
        keep="last",
    )

    return detail.sort_values(
        ["origin_date", "symbol", "holding_period"],
        kind="stable",
    ).reset_index(drop=True)


def build_experiences(
    holding_detail: pd.DataFrame,
    periods: Iterable[int] = DEFAULT_PERIODS,
) -> pd.DataFrame:
    """
    Chuyển holding_detail dạng dài thành Experience dạng rộng.

    Một dòng Experience đại diện cho:
        một mã + một ngày gốc

    T+3, T+5, T+10 được cập nhật trên cùng dòng.
    """
    normalized_periods = _normalize_periods(periods)
    detail = _prepare_holding_detail(holding_detail, normalized_periods)

    if detail.empty:
        return _empty_experiences()

    now_text = datetime.now(VN_TZ).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []

    grouped = detail.groupby(["origin_date", "symbol"], sort=True, dropna=False)

    for (origin_date, symbol), group in grouped:
        group = group.sort_values("holding_period", kind="stable")
        origin = group.iloc[-1]

        row: dict[str, Any] = {
            "experience_id": _experience_id(origin_date, symbol),
            "origin_date": origin_date,
            "symbol": symbol,
            "origin_health": origin.get("origin_health", np.nan),
            "origin_rank": origin.get("origin_rank", np.nan),
            "origin_price": origin.get("origin_price", np.nan),
            "origin_rs5": origin.get("origin_rs5", np.nan),
            "origin_rs10": origin.get("origin_rs10", np.nan),
            "origin_rsi14": origin.get("origin_rsi14", np.nan),
            "created_at": now_text,
            "updated_at": now_text,
        }

        completed: list[tuple[int, float]] = []

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
            return_value = pd.to_numeric(
                pd.Series([item.get("return_pct")]),
                errors="coerce",
            ).iloc[0]

            row[f"{prefix}_date"] = item.get("target_date", np.nan)
            row[f"{prefix}_price"] = item.get("target_price", np.nan)
            row[f"{prefix}_return"] = return_value
            row[f"{prefix}_win"] = (
                bool(return_value > 0) if pd.notna(return_value) else np.nan
            )

            if pd.notna(return_value):
                completed.append((period, float(return_value)))

        row["completed_periods"] = len(completed)
        row["latest_completed_period"] = (
            max(period for period, _ in completed) if completed else np.nan
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

        row["experience_status"] = _status_from_completed_count(
            len(completed),
            len(normalized_periods),
        )

        rows.append(row)

    result = pd.DataFrame(rows)

    for col in EXPERIENCE_COLUMNS:
        if col not in result.columns:
            result[col] = np.nan

    result = result[
        result["experience_id"].ne("")
        & result["origin_date"].notna()
        & result["symbol"].ne("")
        & result["symbol"].ne("NAN")
    ].copy()

    result = result.drop_duplicates("experience_id", keep="last")

    return result.sort_values(
        ["origin_date", "symbol"],
        kind="stable",
    ).reset_index(drop=True).reindex(columns=EXPERIENCE_COLUMNS)


def load_experience_history(
    experience_file: str | Path = EXPERIENCE_FILE,
) -> pd.DataFrame:
    """
    Đọc lịch sử Experience qua Snapshot Storage V2.

    Nếu file chưa tồn tại, trả về DataFrame rỗng đúng schema.
    """
    path = Path(experience_file)

    try:
        history = storage_load_history(
            path,
            EXPERIENCE_COLUMNS,
            key_columns=("experience_id",),
            prefer_remote=True,
        )
    except Exception:
        return _empty_experiences()

    for col in EXPERIENCE_COLUMNS:
        if col not in history.columns:
            history[col] = np.nan

    history["origin_date"] = history["origin_date"].map(_normalize_date)
    history["symbol"] = history["symbol"].map(_normalize_symbol)

    for period in DEFAULT_PERIODS:
        date_col = f"t{period}_date"
        if date_col in history.columns:
            history[date_col] = history[date_col].map(_normalize_date)

    numeric_columns = [
        "origin_rank",
        "origin_price",
        "origin_rs5",
        "origin_rs10",
        "origin_rsi14",
        "completed_periods",
        "latest_completed_period",
        "best_period",
        "best_return",
        "worst_period",
        "worst_return",
    ]
    for period in DEFAULT_PERIODS:
        numeric_columns += [
            f"t{period}_price",
            f"t{period}_return",
        ]

    for col in numeric_columns:
        if col in history.columns:
            history[col] = pd.to_numeric(history[col], errors="coerce")

    history["experience_id"] = history.apply(
        lambda row: (
            str(row["experience_id"]).strip()
            if str(row["experience_id"]).strip() not in {"", "nan", "None"}
            else _experience_id(row["origin_date"], row["symbol"])
        ),
        axis=1,
    )

    history = history[
        history["experience_id"].ne("")
        & history["origin_date"].notna()
        & history["symbol"].ne("")
        & history["symbol"].ne("NAN")
    ].copy()

    history = history.drop_duplicates("experience_id", keep="last")

    return history.sort_values(
        ["origin_date", "symbol"],
        kind="stable",
    ).reset_index(drop=True).reindex(columns=EXPERIENCE_COLUMNS)


def merge_experiences(
    history: pd.DataFrame,
    current_batch: pd.DataFrame,
) -> pd.DataFrame:
    """
    Upsert Experience theo experience_id.

    Điểm quan trọng:
    - Không tạo bản ghi trùng.
    - Bản mới được phép bổ sung T+5/T+10 cho Experience cũ.
    - created_at của Experience cũ được giữ nguyên.
    """
    if current_batch is None or current_batch.empty:
        if history is None:
            return _empty_experiences()
        return history.reindex(columns=EXPERIENCE_COLUMNS).copy()

    old = (
        history.reindex(columns=EXPERIENCE_COLUMNS).copy()
        if history is not None and not history.empty
        else _empty_experiences()
    )
    new = current_batch.reindex(columns=EXPERIENCE_COLUMNS).copy()

    if not old.empty:
        created_map = (
            old.drop_duplicates("experience_id", keep="last")
            .set_index("experience_id")["created_at"]
            .to_dict()
        )
        new["created_at"] = new.apply(
            lambda row: created_map.get(
                row["experience_id"],
                row["created_at"],
            ),
            axis=1,
        )

    merged = storage_merge_upsert(
        old,
        new,
        EXPERIENCE_COLUMNS,
        key_columns=("experience_id",),
    )

    return merged.sort_values(
        ["origin_date", "symbol"],
        kind="stable",
    ).reset_index(drop=True).reindex(columns=EXPERIENCE_COLUMNS)


def save_experiences(
    current_batch: pd.DataFrame,
    experience_file: str | Path = EXPERIENCE_FILE,
) -> pd.DataFrame:
    """
    Lưu Experience an toàn:
    load -> merge/upsert -> validate -> backup -> atomic local -> GitHub.

    Không ghi đè lịch sử bằng batch rỗng.
    """
    path = Path(experience_file)

    if current_batch is None or current_batch.empty:
        return load_experience_history(path)

    history = load_experience_history(path)
    merged = merge_experiences(history, current_batch)

    storage_save_history(
        merged,
        path,
        EXPERIENCE_COLUMNS,
        key_columns=("experience_id",),
        push_remote=True,
    )

    return merged


def run_experience_engine(
    holding_detail: pd.DataFrame,
    *,
    periods: Iterable[int] = DEFAULT_PERIODS,
    experience_file: str | Path = EXPERIENCE_FILE,
    save: bool = True,
) -> ExperienceResult:
    """
    Hàm điều phối chính của Experience Engine V1.
    """
    normalized_periods = _normalize_periods(periods)
    current_batch = build_experiences(
        holding_detail,
        periods=normalized_periods,
    )

    old_history = load_experience_history(experience_file)
    history = merge_experiences(old_history, current_batch)

    saved = False
    if save and not current_batch.empty:
        history = save_experiences(current_batch, experience_file)
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
    Lấy các Experience đã hoàn thành ít nhất đến một kỳ T+ nhất định.

    Ví dụ:
        min_period=3  -> có T3
        min_period=5  -> có T5
        min_period=10 -> có T10
    """
    if history is None:
        history = load_experience_history(experience_file)

    if history is None or history.empty:
        return _empty_experiences()

    period = int(min_period)
    return_col = f"t{period}_return"
    if return_col not in history.columns:
        raise ValueError(
            f"Experience schema không có kỳ T{period}. "
            f"Các kỳ mặc định: {DEFAULT_PERIODS}"
        )

    return history[
        pd.to_numeric(history[return_col], errors="coerce").notna()
    ].copy().reset_index(drop=True)


def build_learning_view(
    history: pd.DataFrame | None = None,
    *,
    experience_file: str | Path = EXPERIENCE_FILE,
    target_period: int = 3,
) -> pd.DataFrame:
    """
    Sinh bảng phẳng để Learning Engine dùng ở Sprint tiếp theo.

    Chưa tự huấn luyện và chưa thay đổi trọng số.
    """
    if history is None:
        history = load_experience_history(experience_file)

    if history is None or history.empty:
        return pd.DataFrame()

    period = int(target_period)
    return_col = f"t{period}_return"
    win_col = f"t{period}_win"

    if return_col not in history.columns:
        raise ValueError(f"Không có dữ liệu T{period} trong Experience schema.")

    view = history[
        history[return_col].notna()
    ][
        [
            "experience_id",
            "origin_date",
            "symbol",
            "origin_health",
            "origin_rank",
            "origin_price",
            "origin_rs5",
            "origin_rs10",
            "origin_rsi14",
            return_col,
            win_col,
            "best_period",
            "best_return",
            "worst_period",
            "worst_return",
            "experience_status",
        ]
    ].copy()

    return view.rename(
        columns={
            return_col: "target_return",
            win_col: "target_win",
        }
    ).reset_index(drop=True)

