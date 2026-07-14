from __future__ import annotations

"""DAILY SUMMARY ENGINE V1.0 - Earning Money Board performance tracker."""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SNAPSHOT_FILE = DATA_DIR / "earning_money_snapshots.csv"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

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
    comparison: pd.DataFrame
    summary: pd.DataFrame
    movements: pd.DataFrame
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
    date_col = _first_existing(scan_df, ["date", "Date", "datetime", "Date/Time", "trading_date"])
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
        out["health_rank"] = pd.to_numeric(scan_df["evolution_health_rank"], errors="coerce")
    else:
        out["health_rank"] = out["health"].map(HEALTH_ORDER)
    price_col = _first_existing(scan_df, ["price", "close", "Close", "daily_price_before_live"])
    out["price"] = _safe_numeric(scan_df[price_col] if price_col else None, scan_df.index)
    out["rs5"] = _safe_numeric(scan_df["rs5"] if "rs5" in scan_df.columns else None, scan_df.index)
    out["rs10"] = _safe_numeric(scan_df["rs10"] if "rs10" in scan_df.columns else None, scan_df.index)
    out["rsi14"] = _safe_numeric(scan_df["rsi14"] if "rsi14" in scan_df.columns else None, scan_df.index)
    out["action"] = scan_df["evolution_action"].astype(str) if "evolution_action" in scan_df.columns else ""
    out["reason"] = scan_df["evolution_reason"].astype(str) if "evolution_reason" in scan_df.columns else ""
    out["saved_at"] = datetime.now(VN_TZ).isoformat(timespec="seconds")
    out = out[out["symbol"].ne("") & out["symbol"].ne("NAN") & out["health"].isin(HEALTH_ORDER)].copy()
    out = out.drop_duplicates(subset=["snapshot_date", "symbol"], keep="last")
    out = out.sort_values(["health_rank", "symbol"], ascending=[True, True], kind="stable").reset_index(drop=True)
    return out.reindex(columns=SNAPSHOT_COLUMNS)


def load_snapshot_history(snapshot_file: str | Path = SNAPSHOT_FILE) -> pd.DataFrame:
    path = Path(snapshot_file)
    if not path.exists() or path.stat().st_size == 0:
        return _empty_snapshot()
    try:
        history = pd.read_csv(path, encoding="utf-8-sig")
    except (pd.errors.EmptyDataError, UnicodeDecodeError):
        return _empty_snapshot()
    for col in SNAPSHOT_COLUMNS:
        if col not in history.columns:
            history[col] = np.nan
    history["snapshot_date"] = history["snapshot_date"].astype(str)
    history["symbol"] = history["symbol"].map(_normalize_symbol)
    history["health"] = history["health"].map(_normalize_health)
    history["health_rank"] = pd.to_numeric(history["health_rank"], errors="coerce")
    for col in ["price", "rs5", "rs10", "rsi14"]:
        history[col] = pd.to_numeric(history[col], errors="coerce")
    history = history.drop_duplicates(subset=["snapshot_date", "symbol"], keep="last")
    return history.reindex(columns=SNAPSHOT_COLUMNS)


def save_snapshot(snapshot: pd.DataFrame, snapshot_file: str | Path = SNAPSHOT_FILE) -> pd.DataFrame:
    if snapshot is None or snapshot.empty:
        return load_snapshot_history(snapshot_file)
    path = Path(snapshot_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    history = load_snapshot_history(path)
    key_date = str(snapshot["snapshot_date"].iloc[0])
    symbols = set(snapshot["symbol"].astype(str))
    if not history.empty:
        history = history.loc[~(history["snapshot_date"].eq(key_date) & history["symbol"].isin(symbols))].copy()
    merged = pd.concat([history, snapshot], ignore_index=True)
    merged = merged.drop_duplicates(subset=["snapshot_date", "symbol"], keep="last")
    merged = merged.sort_values(["snapshot_date", "health_rank", "symbol"], kind="stable").reset_index(drop=True)
    merged.to_csv(path, index=False, encoding="utf-8-sig")
    return merged


def get_previous_snapshot(history: pd.DataFrame, current_date: str) -> tuple[str | None, pd.DataFrame]:
    if history is None or history.empty:
        return None, _empty_snapshot()
    dates = sorted(d for d in history["snapshot_date"].dropna().astype(str).unique() if d < current_date)
    if not dates:
        return None, _empty_snapshot()
    previous_date = dates[-1]
    previous = history[history["snapshot_date"].astype(str).eq(previous_date)].copy()
    return previous_date, previous.reset_index(drop=True)


def compare_snapshots(previous_snapshot: pd.DataFrame, current_snapshot: pd.DataFrame) -> pd.DataFrame:
    if previous_snapshot is None or previous_snapshot.empty:
        return pd.DataFrame()
    prev = previous_snapshot[["snapshot_date", "symbol", "health", "health_rank", "price", "rs5", "rs10"]].rename(columns={
        "snapshot_date": "previous_date", "health": "previous_health", "health_rank": "previous_rank",
        "price": "previous_price", "rs5": "previous_rs5", "rs10": "previous_rs10",
    })
    curr = current_snapshot[["snapshot_date", "symbol", "health", "health_rank", "price", "rs5", "rs10"]].rename(columns={
        "snapshot_date": "current_date", "health": "current_health", "health_rank": "current_rank",
        "price": "current_price", "rs5": "current_rs5", "rs10": "current_rs10",
    })
    comparison = prev.merge(curr, on="symbol", how="left", validate="one_to_one")
    valid_price = comparison["previous_price"].notna() & comparison["current_price"].notna() & comparison["previous_price"].gt(0)
    comparison["return_pct"] = np.where(valid_price, (comparison["current_price"] / comparison["previous_price"] - 1.0) * 100.0, np.nan)
    comparison["price_direction"] = np.select(
        [comparison["return_pct"].gt(1e-9), comparison["return_pct"].lt(-1e-9), comparison["return_pct"].notna()],
        ["TĂNG", "GIẢM", "ĐỨNG GIÁ"], default="KHÔNG CÓ GIÁ",
    )
    comparison["movement"] = comparison.apply(lambda r: _movement_label(r["previous_rank"], r["current_rank"]), axis=1)
    comparison["matched_today"] = comparison["current_health"].notna()
    return comparison.sort_values(["previous_rank", "return_pct", "symbol"], ascending=[True, False, True], na_position="last", kind="stable").reset_index(drop=True)


def build_summary_table(comparison: pd.DataFrame) -> pd.DataFrame:
    columns = ["Nhóm hôm qua", "Số CP", "Có dữ liệu hôm nay", "Tăng", "Giảm", "Đứng giá", "Tỷ lệ tăng", "TB tăng (%)", "Ở lại", "Lên nhóm", "Xuống nhóm", "Rời bảng", "Đánh giá"]
    if comparison is None or comparison.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for health, rank in sorted(HEALTH_ORDER.items(), key=lambda item: item[1]):
        group = comparison[comparison["previous_health"].eq(health)].copy()
        if group.empty:
            continue
        priced = group[group["return_pct"].notna()]
        priced_count = len(priced)
        up_count = int(priced["return_pct"].gt(0).sum())
        down_count = int(priced["return_pct"].lt(0).sum())
        flat_count = int(priced["return_pct"].eq(0).sum())
        win_rate = up_count / priced_count * 100.0 if priced_count else np.nan
        avg_return = float(priced["return_pct"].mean()) if priced_count else np.nan
        rows.append({
            "Nhóm hôm qua": health, "Số CP": len(group), "Có dữ liệu hôm nay": int(group["matched_today"].sum()),
            "Tăng": up_count, "Giảm": down_count, "Đứng giá": flat_count, "Tỷ lệ tăng": win_rate,
            "TB tăng (%)": avg_return, "Ở lại": int(group["movement"].eq("Ở LẠI").sum()),
            "Lên nhóm": int(group["movement"].eq("LÊN NHÓM").sum()),
            "Xuống nhóm": int(group["movement"].eq("XUỐNG NHÓM").sum()),
            "Rời bảng": int(group["movement"].eq("RỜI BẢNG").sum()),
            "Đánh giá": _rating(win_rate, avg_return, priced_count), "_rank": rank,
        })
    return pd.DataFrame(rows).sort_values("_rank").drop(columns="_rank").reindex(columns=columns).reset_index(drop=True)


def build_movements_table(comparison: pd.DataFrame) -> pd.DataFrame:
    columns = ["Mã", "Nhóm hôm qua", "Nhóm hôm nay", "Chuyển nhóm", "Giá hôm qua", "Giá hôm nay", "Thay đổi (%)", "RS5 hôm qua", "RS5 hôm nay", "RS10 hôm qua", "RS10 hôm nay"]
    if comparison is None or comparison.empty:
        return pd.DataFrame(columns=columns)
    moved = comparison[~comparison["movement"].eq("Ở LẠI")].copy()
    if moved.empty:
        return pd.DataFrame(columns=columns)
    moved["movement_sort"] = moved["movement"].map({"LÊN NHÓM": 0, "XUỐNG NHÓM": 1, "RỜI BẢNG": 2}).fillna(9)
    moved = moved.sort_values(["movement_sort", "previous_rank", "return_pct"], ascending=[True, True, False], na_position="last", kind="stable")
    result = moved.rename(columns={
        "symbol": "Mã", "previous_health": "Nhóm hôm qua", "current_health": "Nhóm hôm nay",
        "movement": "Chuyển nhóm", "previous_price": "Giá hôm qua", "current_price": "Giá hôm nay",
        "return_pct": "Thay đổi (%)", "previous_rs5": "RS5 hôm qua", "current_rs5": "RS5 hôm nay",
        "previous_rs10": "RS10 hôm qua", "current_rs10": "RS10 hôm nay",
    })
    return result.reindex(columns=columns).reset_index(drop=True)


def run_daily_summary(
    scan_df: pd.DataFrame,
    *,
    snapshot_date: str | date | datetime | None = None,
    snapshot_file: str | Path = SNAPSHOT_FILE,
    save: bool = True,
) -> DailySummaryResult:
    current = build_snapshot(scan_df, snapshot_date=snapshot_date)
    current_date = str(current["snapshot_date"].iloc[0]) if not current.empty else _resolve_snapshot_date(scan_df, snapshot_date)
    history = load_snapshot_history(snapshot_file)
    previous_date, previous = get_previous_snapshot(history, current_date)
    comparison = compare_snapshots(previous, current)
    summary = build_summary_table(comparison)
    movements = build_movements_table(comparison)
    if save and not current.empty:
        save_snapshot(current, snapshot_file)
    if current.empty:
        status = "Không có dữ liệu để tạo snapshot."
    elif previous_date is None:
        status = f"Đã lưu snapshot đầu tiên ngày {current_date}. Từ phiên dữ liệu kế tiếp Bot sẽ tự so sánh."
    else:
        status = f"Đã so sánh nhóm ngày {previous_date} với dữ liệu ngày {current_date}."
    return DailySummaryResult(current_date, previous_date, current, previous, comparison, summary, movements, status, Path(snapshot_file))


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
    if result.previous_date is None:
        st.info(result.status)
        st.caption(f"Snapshot lưu tại: {result.snapshot_file}. Ngày đầu tiên chưa có dữ liệu hôm qua để so sánh.")
        return result
    st.caption(f"Đánh giá các nhóm ngày {result.previous_date} bằng kết quả ngày {result.current_date}. Nhóm mạnh nhất nằm trên.")
    if result.summary.empty:
        st.warning("Chưa đủ dữ liệu chung giữa hai ngày để tổng hợp.")
        return result
    display = result.summary.copy()
    display["Tỷ lệ tăng"] = display["Tỷ lệ tăng"].map(lambda x: "—" if pd.isna(x) else f"{x:.1f}%")
    display["TB tăng (%)"] = display["TB tăng (%)"].map(lambda x: "—" if pd.isna(x) else f"{x:+.2f}%")
    def style_group(value: object) -> str:
        return {
            "🌱 ĐANG HỒI": "background-color:#d9ead3;color:#1b4332;font-weight:700",
            "🟡 TRUNG TÍNH": "background-color:#fff2cc;color:#7f6000;font-weight:700",
            "🔴 YẾU": "background-color:#fce5cd;color:#9c5700;font-weight:700",
            "⚠️ YẾU DẦN": "background-color:#f4cccc;color:#990000;font-weight:700",
            "⛔ RẤT YẾU": "background-color:#d9d9d9;color:#333333;font-weight:700",
        }.get(str(value), "")
    st.dataframe(display.style.map(style_group, subset=["Nhóm hôm qua"]), use_container_width=True, hide_index=True)
    ranked = result.summary.dropna(subset=["Tỷ lệ tăng", "TB tăng (%)"]).sort_values(["Tỷ lệ tăng", "TB tăng (%)"], ascending=[False, False])
    if not ranked.empty:
        best = ranked.iloc[0]
        st.success(f"Nhóm tốt nhất: {best['Nhóm hôm qua']} — {best['Tăng']}/{best['Có dữ liệu hôm nay']} mã tăng ({best['Tỷ lệ tăng']:.1f}%), TB {best['TB tăng (%)']:+.2f}%.")
    with st.expander("🔄 Chi tiết các mã chuyển nhóm", expanded=expanded_movements):
        if result.movements.empty:
            st.caption("Không có mã nào chuyển nhóm.")
        else:
            movement_display = result.movements.copy()
            for col in ["Giá hôm qua", "Giá hôm nay", "Thay đổi (%)", "RS5 hôm qua", "RS5 hôm nay", "RS10 hôm qua", "RS10 hôm nay"]:
                movement_display[col] = pd.to_numeric(movement_display[col], errors="coerce").round(2)
            st.dataframe(movement_display, use_container_width=True, hide_index=True)
    csv_bytes = result.summary.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Tải báo cáo Daily Summary", data=csv_bytes,
        file_name=f"daily_earning_money_{result.previous_date}_to_{result.current_date}.csv",
        mime="text/csv", key=f"download_daily_summary_{result.current_date}",
    )
    st.caption(result.status)
    return result


def process_and_render_daily_summary(
    scan_df: pd.DataFrame,
    *,
    snapshot_date: str | date | datetime | None = None,
    snapshot_file: str | Path = SNAPSHOT_FILE,
    title: str = "📊 DAILY EARNING MONEY REPORT",
) -> DailySummaryResult:
    result = run_daily_summary(scan_df, snapshot_date=snapshot_date, snapshot_file=snapshot_file, save=True)
    return render_daily_summary(result, title=title)

