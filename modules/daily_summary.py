from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .snapshot_storage import (
    get_last_storage_status,
    load_history as storage_load_history,
    merge_upsert as storage_merge_upsert,
    save_history as storage_save_history,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SNAPSHOT_FILE = DATA_DIR / "earning_money_snapshots.csv"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
HOLDING_PERIODS: tuple[int, ...] = (3, 5, 10)

HEALTH_ORDER: dict[str, int] = {
    "🌱 ĐANG HỒI": 0,
    "🟡 TRUNG TÍNH": 1,
    "🔴 YẾU": 2,
    "⚠️ YẾU DẦN": 3,
    "⛔ RẤT YẾU": 4,
}

SNAPSHOT_COLUMNS = [
    "snapshot_date", "symbol", "health", "health_rank", "price",
    "rs5", "rs10", "rsi14", "action", "reason", "saved_at",
]


@dataclass
class DailySummaryResult:
    current_date: str
    previous_date: str | None
    current_snapshot: pd.DataFrame
    previous_snapshot: pd.DataFrame
    history: pd.DataFrame
    comparison: pd.DataFrame
    summary: pd.DataFrame
    movements: pd.DataFrame
    holding_detail: pd.DataFrame
    holding_summary: pd.DataFrame
    status: str
    snapshot_file: Path


def _empty_snapshot() -> pd.DataFrame:
    return pd.DataFrame(columns=SNAPSHOT_COLUMNS)


def _safe_numeric(series: pd.Series | None, index: pd.Index) -> pd.Series:
    if series is None:
        return pd.Series(np.nan, index=index, dtype="float64")
    return pd.to_numeric(series, errors="coerce").reindex(index)


def _first_existing(df: pd.DataFrame, names: list[str]) -> str | None:
    return next((name for name in names if name in df.columns), None)


def _normalize_symbol(value: Any) -> str:
    return str(value).strip().upper()


def _normalize_health(value: Any) -> str:
    text = str(value).strip()
    aliases = {
        "ĐANG HỒI": "🌱 ĐANG HỒI",
        "TRUNG TÍNH": "🟡 TRUNG TÍNH",
        "YẾU": "🔴 YẾU",
        "YẾU DẦN": "⚠️ YẾU DẦN",
        "RẤT YẾU": "⛔ RẤT YẾU",
    }
    return aliases.get(text, text)


def _resolve_snapshot_date(
    scan_df: pd.DataFrame,
    snapshot_date: str | date | datetime | None = None,
) -> str:
    if snapshot_date is not None:
        return pd.Timestamp(snapshot_date).date().isoformat()

    date_col = _first_existing(
        scan_df, ["date", "Date", "datetime", "Date/Time", "trading_date"]
    )
    if date_col is not None:
        valid = pd.to_datetime(scan_df[date_col], errors="coerce").dropna()
        if not valid.empty:
            return valid.max().date().isoformat()

    return datetime.now(VN_TZ).date().isoformat()


def _rating(win_rate: float, avg_return: float, sample_size: int) -> str:
    if sample_size <= 0 or pd.isna(win_rate):
        return "—"

    score = 0
    if win_rate >= 80:
        score += 3
    elif win_rate >= 65:
        score += 2
    elif win_rate >= 50:
        score += 1

    if pd.notna(avg_return):
        if avg_return >= 2.0:
            score += 2
        elif avg_return >= 0.5:
            score += 1
        elif avg_return < 0:
            score -= 1

    return "⭐" * max(1, min(5, score))


def _movement_label(previous_rank: float, current_rank: float) -> str:
    if pd.isna(current_rank):
        return "RỜI BẢNG"
    if current_rank < previous_rank:
        return "LÊN NHÓM"
    if current_rank > previous_rank:
        return "XUỐNG NHÓM"
    return "Ở LẠI"


def _style_group(value: object) -> str:
    return {
        "🌱 ĐANG HỒI": "background-color:#d9ead3;color:#1b4332;font-weight:700",
        "🟡 TRUNG TÍNH": "background-color:#fff2cc;color:#7f6000;font-weight:700",
        "🔴 YẾU": "background-color:#fce5cd;color:#9c5700;font-weight:700",
        "⚠️ YẾU DẦN": "background-color:#f4cccc;color:#990000;font-weight:700",
        "⛔ RẤT YẾU": "background-color:#d9d9d9;color:#333333;font-weight:700",
    }.get(str(value), "")


def _normalize_periods(periods: Iterable[int]) -> tuple[int, ...]:
    cleaned = sorted({int(p) for p in periods if int(p) > 0})
    if not cleaned:
        raise ValueError("holding_periods phải có ít nhất một số nguyên dương.")
    return tuple(cleaned)


def build_snapshot(
    scan_df: pd.DataFrame,
    snapshot_date: str | date | datetime | None = None,
) -> pd.DataFrame:
    if scan_df is None or scan_df.empty:
        return _empty_snapshot()

    missing = {"symbol", "evolution_health_group"}.difference(scan_df.columns)
    if missing:
        raise ValueError(
            "Daily Summary cần scan_df đã qua add_evolution_health(). "
            f"Thiếu cột: {sorted(missing)}"
        )

    out = pd.DataFrame(index=scan_df.index)
    out["snapshot_date"] = _resolve_snapshot_date(scan_df, snapshot_date)
    out["symbol"] = scan_df["symbol"].map(_normalize_symbol)
    out["health"] = scan_df["evolution_health_group"].map(_normalize_health)

    if "evolution_health_rank" in scan_df.columns:
        out["health_rank"] = pd.to_numeric(
            scan_df["evolution_health_rank"], errors="coerce"
        )
    else:
        out["health_rank"] = out["health"].map(HEALTH_ORDER)

    price_col = _first_existing(
        scan_df, ["price", "close", "Close", "daily_price_before_live"]
    )
    out["price"] = _safe_numeric(
        scan_df[price_col] if price_col else None, scan_df.index
    )
    out["rs5"] = _safe_numeric(
        scan_df["rs5"] if "rs5" in scan_df.columns else None, scan_df.index
    )
    out["rs10"] = _safe_numeric(
        scan_df["rs10"] if "rs10" in scan_df.columns else None, scan_df.index
    )
    out["rsi14"] = _safe_numeric(
        scan_df["rsi14"] if "rsi14" in scan_df.columns else None, scan_df.index
    )
    out["action"] = (
        scan_df["evolution_action"].astype(str)
        if "evolution_action" in scan_df.columns else ""
    )
    out["reason"] = (
        scan_df["evolution_reason"].astype(str)
        if "evolution_reason" in scan_df.columns else ""
    )
    out["saved_at"] = datetime.now(VN_TZ).isoformat(timespec="seconds")

    out = out[
        out["symbol"].ne("")
        & out["symbol"].ne("NAN")
        & out["health"].isin(HEALTH_ORDER)
    ].copy()

    out = out.drop_duplicates(["snapshot_date", "symbol"], keep="last")
    out = out.sort_values(
        ["health_rank", "symbol"], ascending=[True, True], kind="stable"
    ).reset_index(drop=True)

    return out.reindex(columns=SNAPSHOT_COLUMNS)


def load_snapshot_history(snapshot_file: str | Path = SNAPSHOT_FILE) -> pd.DataFrame:
    """
    Đọc lịch sử snapshot qua Snapshot Storage V2.

    Storage sẽ ưu tiên GitHub khi có GITHUB_TOKEN, sau đó fallback về
    file local và backup. Phần dưới chỉ chuẩn hóa dữ liệu cho Daily Summary.
    """
    path = Path(snapshot_file)

    try:
        history = storage_load_history(
            path,
            SNAPSHOT_COLUMNS,
            key_columns=("snapshot_date", "symbol"),
            prefer_remote=True,
        )
    except Exception:
        # Không làm app crash nếu hệ lưu trữ gặp lỗi ngoài dự kiến.
        return _empty_snapshot()

    for col in SNAPSHOT_COLUMNS:
        if col not in history.columns:
            history[col] = np.nan

    dates = pd.to_datetime(history["snapshot_date"], errors="coerce")
    history["snapshot_date"] = dates.dt.strftime("%Y-%m-%d")
    history["symbol"] = history["symbol"].map(_normalize_symbol)
    history["health"] = history["health"].map(_normalize_health)
    history["health_rank"] = pd.to_numeric(history["health_rank"], errors="coerce")

    for col in ["price", "rs5", "rs10", "rsi14"]:
        history[col] = pd.to_numeric(history[col], errors="coerce")

    history = history[
        history["snapshot_date"].notna()
        & history["symbol"].ne("")
        & history["symbol"].ne("NAN")
    ].copy()

    history = history.drop_duplicates(["snapshot_date", "symbol"], keep="last")
    return history.sort_values(
        ["snapshot_date", "health_rank", "symbol"], kind="stable"
    ).reset_index(drop=True).reindex(columns=SNAPSHOT_COLUMNS)


def merge_snapshot_into_history(
    history: pd.DataFrame,
    snapshot: pd.DataFrame,
) -> pd.DataFrame:
    """
    Upsert theo khóa snapshot_date + symbol.

    Dữ liệu ngày cũ được giữ nguyên; nếu cùng ngày/cùng mã thì chỉ cập nhật
    bản mới nhất. Không giới hạn số phiên lịch sử.
    """
    return storage_merge_upsert(
        history,
        snapshot,
        SNAPSHOT_COLUMNS,
        key_columns=("snapshot_date", "symbol"),
    )


def save_snapshot(
    snapshot: pd.DataFrame,
    snapshot_file: str | Path = SNAPSHOT_FILE,
) -> pd.DataFrame:
    """
    Lưu snapshot bằng cơ chế:
    load bền -> merge/upsert -> validate -> backup -> atomic local -> GitHub.

    Tuyệt đối không ghi đè lịch sử bằng snapshot rỗng.
    """
    path = Path(snapshot_file)

    if snapshot is None or snapshot.empty:
        return load_snapshot_history(path)

    history = load_snapshot_history(path)
    merged = merge_snapshot_into_history(history, snapshot)

    storage_save_history(
        merged,
        path,
        SNAPSHOT_COLUMNS,
        key_columns=("snapshot_date", "symbol"),
        push_remote=True,
    )
    return merged


def get_previous_snapshot(
    history: pd.DataFrame,
    current_date: str,
) -> tuple[str | None, pd.DataFrame]:
    if history is None or history.empty:
        return None, _empty_snapshot()

    dates = sorted(
        d for d in history["snapshot_date"].dropna().astype(str).unique()
        if d < current_date
    )
    if not dates:
        return None, _empty_snapshot()

    previous_date = dates[-1]
    previous = history[
        history["snapshot_date"].astype(str).eq(previous_date)
    ].copy()
    return previous_date, previous.reset_index(drop=True)


def compare_snapshots(
    previous_snapshot: pd.DataFrame,
    current_snapshot: pd.DataFrame,
) -> pd.DataFrame:
    if previous_snapshot is None or previous_snapshot.empty:
        return pd.DataFrame()

    prev = previous_snapshot[
        ["snapshot_date", "symbol", "health", "health_rank", "price", "rs5", "rs10"]
    ].rename(columns={
        "snapshot_date": "previous_date",
        "health": "previous_health",
        "health_rank": "previous_rank",
        "price": "previous_price",
        "rs5": "previous_rs5",
        "rs10": "previous_rs10",
    })
    curr = current_snapshot[
        ["snapshot_date", "symbol", "health", "health_rank", "price", "rs5", "rs10"]
    ].rename(columns={
        "snapshot_date": "current_date",
        "health": "current_health",
        "health_rank": "current_rank",
        "price": "current_price",
        "rs5": "current_rs5",
        "rs10": "current_rs10",
    })

    comparison = prev.merge(curr, on="symbol", how="left", validate="one_to_one")
    valid = (
        comparison["previous_price"].notna()
        & comparison["current_price"].notna()
        & comparison["previous_price"].gt(0)
    )
    comparison["return_pct"] = np.where(
        valid,
        (comparison["current_price"] / comparison["previous_price"] - 1) * 100,
        np.nan,
    )
    comparison["price_direction"] = np.select(
        [
            comparison["return_pct"].gt(1e-9),
            comparison["return_pct"].lt(-1e-9),
            comparison["return_pct"].notna(),
        ],
        ["TĂNG", "GIẢM", "ĐỨNG GIÁ"],
        default="KHÔNG CÓ GIÁ",
    )
    comparison["movement"] = comparison.apply(
        lambda r: _movement_label(r["previous_rank"], r["current_rank"]), axis=1
    )
    comparison["matched_today"] = comparison["current_health"].notna()

    return comparison.sort_values(
        ["previous_rank", "return_pct", "symbol"],
        ascending=[True, False, True],
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)


def build_summary_table(comparison: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Nhóm hôm qua", "Số CP", "Có dữ liệu hôm nay", "Tăng", "Giảm",
        "Đứng giá", "Tỷ lệ tăng", "TB tăng (%)", "Ở lại", "Lên nhóm",
        "Xuống nhóm", "Rời bảng", "Đánh giá",
    ]
    if comparison is None or comparison.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for health, rank in sorted(HEALTH_ORDER.items(), key=lambda x: x[1]):
        group = comparison[comparison["previous_health"].eq(health)].copy()
        if group.empty:
            continue

        priced = group[group["return_pct"].notna()]
        n = len(priced)
        up = int(priced["return_pct"].gt(0).sum())
        down = int(priced["return_pct"].lt(0).sum())
        flat = int(priced["return_pct"].eq(0).sum())
        win = up / n * 100 if n else np.nan
        avg = float(priced["return_pct"].mean()) if n else np.nan

        rows.append({
            "Nhóm hôm qua": health,
            "Số CP": len(group),
            "Có dữ liệu hôm nay": int(group["matched_today"].sum()),
            "Tăng": up,
            "Giảm": down,
            "Đứng giá": flat,
            "Tỷ lệ tăng": win,
            "TB tăng (%)": avg,
            "Ở lại": int(group["movement"].eq("Ở LẠI").sum()),
            "Lên nhóm": int(group["movement"].eq("LÊN NHÓM").sum()),
            "Xuống nhóm": int(group["movement"].eq("XUỐNG NHÓM").sum()),
            "Rời bảng": int(group["movement"].eq("RỜI BẢNG").sum()),
            "Đánh giá": _rating(win, avg, n),
            "_rank": rank,
        })

    return (
        pd.DataFrame(rows).sort_values("_rank").drop(columns="_rank")
        .reindex(columns=columns).reset_index(drop=True)
    )


def build_movements_table(comparison: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Mã", "Nhóm hôm qua", "Nhóm hôm nay", "Chuyển nhóm",
        "Giá hôm qua", "Giá hôm nay", "Thay đổi (%)",
        "RS5 hôm qua", "RS5 hôm nay", "RS10 hôm qua", "RS10 hôm nay",
    ]
    if comparison is None or comparison.empty:
        return pd.DataFrame(columns=columns)

    moved = comparison[~comparison["movement"].eq("Ở LẠI")].copy()
    if moved.empty:
        return pd.DataFrame(columns=columns)

    moved["movement_sort"] = moved["movement"].map({
        "LÊN NHÓM": 0, "XUỐNG NHÓM": 1, "RỜI BẢNG": 2
    }).fillna(9)
    moved = moved.sort_values(
        ["movement_sort", "previous_rank", "return_pct"],
        ascending=[True, True, False],
        na_position="last",
        kind="stable",
    )

    result = moved.rename(columns={
        "symbol": "Mã",
        "previous_health": "Nhóm hôm qua",
        "current_health": "Nhóm hôm nay",
        "movement": "Chuyển nhóm",
        "previous_price": "Giá hôm qua",
        "current_price": "Giá hôm nay",
        "return_pct": "Thay đổi (%)",
        "previous_rs5": "RS5 hôm qua",
        "current_rs5": "RS5 hôm nay",
        "previous_rs10": "RS10 hôm qua",
        "current_rs10": "RS10 hôm nay",
    })
    return result.reindex(columns=columns).reset_index(drop=True)


def build_holding_detail(
    history: pd.DataFrame,
    holding_periods: Iterable[int] = HOLDING_PERIODS,
) -> pd.DataFrame:
    periods = _normalize_periods(holding_periods)
    columns = [
        "origin_date", "target_date", "holding_period", "symbol",
        "origin_health", "origin_rank", "origin_price", "target_price",
        "return_pct", "win", "origin_rs5", "origin_rs10", "origin_rsi14",
    ]
    if history is None or history.empty:
        return pd.DataFrame(columns=columns)

    hist = history.copy()
    hist["snapshot_date"] = hist["snapshot_date"].astype(str)
    for col in ["health_rank", "price", "rs5", "rs10", "rsi14"]:
        hist[col] = pd.to_numeric(hist[col], errors="coerce")

    hist = hist.drop_duplicates(["snapshot_date", "symbol"], keep="last")
    dates = sorted(hist["snapshot_date"].dropna().unique())
    frames = []

    for pos, origin_date in enumerate(dates):
        origin = hist[hist["snapshot_date"].eq(origin_date)][
            ["symbol", "health", "health_rank", "price", "rs5", "rs10", "rsi14"]
        ].rename(columns={
            "health": "origin_health",
            "health_rank": "origin_rank",
            "price": "origin_price",
            "rs5": "origin_rs5",
            "rs10": "origin_rs10",
            "rsi14": "origin_rsi14",
        })
        origin["origin_date"] = origin_date

        for period in periods:
            target_pos = pos + period
            if target_pos >= len(dates):
                continue

            target_date = dates[target_pos]
            target = hist[hist["snapshot_date"].eq(target_date)][
                ["symbol", "price"]
            ].rename(columns={"price": "target_price"})

            matched = origin.merge(target, on="symbol", how="left", validate="one_to_one")
            matched["target_date"] = target_date
            matched["holding_period"] = period

            valid = (
                matched["origin_price"].notna()
                & matched["target_price"].notna()
                & matched["origin_price"].gt(0)
            )
            matched["return_pct"] = np.where(
                valid,
                (matched["target_price"] / matched["origin_price"] - 1) * 100,
                np.nan,
            )
            matched["win"] = np.where(
                matched["return_pct"].notna(),
                matched["return_pct"].gt(0),
                np.nan,
            )
            frames.append(matched.reindex(columns=columns))

    if not frames:
        return pd.DataFrame(columns=columns)

    detail = pd.concat(frames, ignore_index=True)
    detail = detail[detail["origin_health"].isin(HEALTH_ORDER)].copy()
    return detail.sort_values(
        ["holding_period", "origin_date", "origin_rank", "symbol"],
        kind="stable",
    ).reset_index(drop=True)


def build_holding_summary(
    holding_detail: pd.DataFrame,
    holding_periods: Iterable[int] = HOLDING_PERIODS,
) -> pd.DataFrame:
    periods = _normalize_periods(holding_periods)
    columns = ["Nhóm gốc"]
    for p in periods:
        columns += [f"Mẫu T{p}", f"Win T{p}", f"TB T{p} (%)"]
    columns += ["Đánh giá"]

    rows = []
    for health, rank in sorted(HEALTH_ORDER.items(), key=lambda x: x[1]):
        row = {"Nhóm gốc": health, "_rank": rank}
        latest_win = latest_avg = np.nan
        latest_n = 0

        for p in periods:
            completed = (
                holding_detail[
                    holding_detail["origin_health"].eq(health)
                    & holding_detail["holding_period"].eq(p)
                    & holding_detail["return_pct"].notna()
                ].copy()
                if holding_detail is not None and not holding_detail.empty
                else pd.DataFrame()
            )
            n = len(completed)
            win = float(completed["return_pct"].gt(0).mean() * 100) if n else np.nan
            avg = float(completed["return_pct"].mean()) if n else np.nan

            row[f"Mẫu T{p}"] = n
            row[f"Win T{p}"] = win
            row[f"TB T{p} (%)"] = avg
            if n:
                latest_n, latest_win, latest_avg = n, win, avg

        row["Đánh giá"] = _rating(latest_win, latest_avg, latest_n)
        rows.append(row)

    return (
        pd.DataFrame(rows).sort_values("_rank").drop(columns="_rank")
        .reindex(columns=columns).reset_index(drop=True)
    )


def get_statistics(
    history: pd.DataFrame | None = None,
    *,
    snapshot_file: str | Path = SNAPSHOT_FILE,
    holding_periods: Iterable[int] = HOLDING_PERIODS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if history is None:
        history = load_snapshot_history(snapshot_file)
    detail = build_holding_detail(history, holding_periods)
    summary = build_holding_summary(detail, holding_periods)
    return summary, detail


def run_daily_summary(
    scan_df: pd.DataFrame,
    *,
    snapshot_date: str | date | datetime | None = None,
    snapshot_file: str | Path = SNAPSHOT_FILE,
    save: bool = True,
    holding_periods: Iterable[int] = HOLDING_PERIODS,
) -> DailySummaryResult:
    periods = _normalize_periods(holding_periods)
    current = build_snapshot(scan_df, snapshot_date)
    current_date = (
        str(current["snapshot_date"].iloc[0])
        if not current.empty else _resolve_snapshot_date(scan_df, snapshot_date)
    )

    old_history = load_snapshot_history(snapshot_file)
    previous_date, previous = get_previous_snapshot(old_history, current_date)
    comparison = compare_snapshots(previous, current)
    summary = build_summary_table(comparison)
    movements = build_movements_table(comparison)

    effective_history = merge_snapshot_into_history(old_history, current)
    if save and not current.empty:
        effective_history = save_snapshot(current, snapshot_file)

    holding_detail = build_holding_detail(effective_history, periods)
    holding_summary = build_holding_summary(holding_detail, periods)
    session_count = effective_history["snapshot_date"].dropna().astype(str).nunique()
    if current.empty:
        status = "Không có dữ liệu để tạo snapshot."
    elif previous_date is None:
        status = (
            f"Đã lưu snapshot đầu tiên ngày {current_date}. "
            "Từ phiên dữ liệu kế tiếp Bot sẽ tự so sánh."
        )
    else:
        status = (
            f"Đã so sánh nhóm ngày {previous_date} với dữ liệu ngày {current_date}. "
            f"Lịch sử hiện có {session_count} phiên snapshot."
        )

    return DailySummaryResult(
        current_date, previous_date, current, previous, effective_history,
        comparison, summary, movements, holding_detail, holding_summary,
        status, Path(snapshot_file),
    )


def _format_percent(value: Any, decimals: int = 1) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "—" if pd.isna(numeric) else f"{numeric:.{decimals}f}%"


def _format_return(value: Any, decimals: int = 2) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "—" if pd.isna(numeric) else f"{numeric:+.{decimals}f}%"


def render_daily_summary(
    result: DailySummaryResult,
    *,
    title: str = "📊 DAILY EARNING MONEY REPORT",
    expanded_movements: bool = False,
) -> DailySummaryResult:
    try:
        import streamlit as st
    except ImportError:
        return result

    st.markdown("---")
    st.markdown(f"## {title}")
    st.markdown("### 1️⃣ Kết quả phiên kế tiếp")

    if result.previous_date is None:
        st.info(result.status)
    elif result.summary.empty:
        st.warning("Chưa đủ dữ liệu chung giữa hai phiên để tổng hợp.")
    else:
        st.caption(
            f"Đánh giá các nhóm ngày {result.previous_date} "
            f"bằng kết quả ngày {result.current_date}."
        )
        display = result.summary.copy()
        display["Tỷ lệ tăng"] = display["Tỷ lệ tăng"].map(_format_percent)
        display["TB tăng (%)"] = display["TB tăng (%)"].map(_format_return)
        st.dataframe(
            display.style.map(_style_group, subset=["Nhóm hôm qua"]),
            use_container_width=True,
            hide_index=True,
        )

        ranked = result.summary.dropna(
            subset=["Tỷ lệ tăng", "TB tăng (%)"]
        ).sort_values(
            ["Tỷ lệ tăng", "TB tăng (%)"], ascending=[False, False]
        )
        if not ranked.empty:
            best = ranked.iloc[0]
            st.success(
                f"Nhóm tốt nhất phiên kế tiếp: {best['Nhóm hôm qua']} — "
                f"{best['Tăng']}/{best['Có dữ liệu hôm nay']} mã tăng "
                f"({best['Tỷ lệ tăng']:.1f}%), TB {best['TB tăng (%)']:+.2f}%."
            )

        with st.expander("🔄 Chi tiết các mã chuyển nhóm", expanded=expanded_movements):
            if result.movements.empty:
                st.caption("Không có mã nào chuyển nhóm.")
            else:
                movement_display = result.movements.copy()
                for col in [
                    "Giá hôm qua", "Giá hôm nay", "Thay đổi (%)",
                    "RS5 hôm qua", "RS5 hôm nay", "RS10 hôm qua", "RS10 hôm nay",
                ]:
                    movement_display[col] = pd.to_numeric(
                        movement_display[col], errors="coerce"
                    ).round(2)
                st.dataframe(movement_display, use_container_width=True, hide_index=True)

    st.markdown("### 2️⃣ EARNING MONEY PERFORMANCE — T+3 / T+5 / T+10")
    st.caption(
        "T+N được tính theo số phiên snapshot thực tế, không theo ngày lịch. "
        "Mỗi cổ phiếu luôn được đánh giá theo nhóm tại ngày xuất phát."
    )

    holding_display = result.holding_summary.copy()
    periods = sorted(
        int(col.replace("Win T", ""))
        for col in holding_display.columns if col.startswith("Win T")
    )

    for p in periods:
        holding_display[f"Win T{p}"] = holding_display[f"Win T{p}"].map(_format_percent)
        holding_display[f"TB T{p} (%)"] = holding_display[f"TB T{p} (%)"].map(_format_return)

    st.dataframe(
        holding_display.style.map(_style_group, subset=["Nhóm gốc"]),
        use_container_width=True,
        hide_index=True,
    )

    shown = False
    for p in sorted(periods, reverse=True):
        sample_col, win_col, avg_col = f"Mẫu T{p}", f"Win T{p}", f"TB T{p} (%)"
        ranked = result.holding_summary[
            result.holding_summary[sample_col].gt(0)
            & result.holding_summary[win_col].notna()
        ].sort_values(
            [win_col, avg_col, sample_col], ascending=[False, False, False]
        )
        if not ranked.empty:
            best = ranked.iloc[0]
            st.success(
                f"Nhóm tốt nhất tại T+{p}: {best['Nhóm gốc']} — "
                f"{int(best[sample_col])} mẫu, WinRate {best[win_col]:.1f}%, "
                f"TB {best[avg_col]:+.2f}%."
            )
            shown = True
            break

    if not shown:
        n_dates = result.history["snapshot_date"].dropna().astype(str).nunique()
        st.info(
            f"Hiện có {n_dates} phiên snapshot. "
            "Bot đang chờ đủ dữ liệu để hoàn thành kỳ T+3 đầu tiên."
        )

    with st.expander("🧪 Chi tiết từng phép thử T+3/T+5/T+10", expanded=False):
        completed = result.holding_detail[
            result.holding_detail["return_pct"].notna()
        ].copy()
        if completed.empty:
            st.caption("Chưa có phép thử nào hoàn thành đủ kỳ nắm giữ.")
        else:
            detail = completed.rename(columns={
                "origin_date": "Ngày gốc",
                "target_date": "Ngày chốt",
                "holding_period": "T+",
                "symbol": "Mã",
                "origin_health": "Nhóm gốc",
                "origin_price": "Giá gốc",
                "target_price": "Giá chốt",
                "return_pct": "Lợi nhuận (%)",
                "origin_rs5": "RS5 gốc",
                "origin_rs10": "RS10 gốc",
                "origin_rsi14": "RSI14 gốc",
            })
            detail = detail.reindex(columns=[
                "Ngày gốc", "Ngày chốt", "T+", "Mã", "Nhóm gốc",
                "Giá gốc", "Giá chốt", "Lợi nhuận (%)",
                "RS5 gốc", "RS10 gốc", "RSI14 gốc",
            ])
            for col in [
                "Giá gốc", "Giá chốt", "Lợi nhuận (%)",
                "RS5 gốc", "RS10 gốc", "RSI14 gốc",
            ]:
                detail[col] = pd.to_numeric(detail[col], errors="coerce").round(2)
            st.dataframe(detail, use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Tải Daily Report",
            data=result.summary.to_csv(index=False).encode("utf-8-sig"),
            file_name=(
                f"daily_earning_money_{result.previous_date or 'first'}"
                f"_to_{result.current_date}.csv"
            ),
            mime="text/csv",
            key=f"download_daily_summary_{result.current_date}",
        )
    with col2:
        st.download_button(
            "⬇️ Tải T+3/T+5/T+10",
            data=result.holding_summary.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"earning_money_t3_t5_t10_{result.current_date}.csv",
            mime="text/csv",
            key=f"download_holding_summary_{result.current_date}",
        )

    st.caption(result.status)

    storage_status = get_last_storage_status()
    st.caption(
        "🛡️ Snapshot Storage: "
        f"{storage_status.as_text()}"
    )
    return result


def process_and_render_daily_summary(
    scan_df: pd.DataFrame,
    *,
    snapshot_date: str | date | datetime | None = None,
    snapshot_file: str | Path = SNAPSHOT_FILE,
    title: str = "📊 DAILY EARNING MONEY REPORT",
    holding_periods: Iterable[int] = HOLDING_PERIODS,
) -> DailySummaryResult:
    result = run_daily_summary(
        scan_df,
        snapshot_date=snapshot_date,
        snapshot_file=snapshot_file,
        save=True,
        holding_periods=holding_periods,
    )
    return render_daily_summary(result, title=title)
