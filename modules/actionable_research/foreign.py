"""
Foreign-flow evidence adapter.

VPS Camera 5-minute bars do NOT contain per-stock foreign buy/sell.
Canonical available source on this repo family is EOD HSX symbol-level
foreign VALUE (foreign_flow_history / injected frames). Timing is labeled EOD.
Missing data → UNKNOWN, never net=0.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import pandas as pd

from modules.actionable_research.contracts import (
    FOREIGN_BUY,
    FOREIGN_BUY_PERCENTILE,
    FOREIGN_COMPLETENESS_COMPLETE,
    FOREIGN_COMPLETENESS_PARTIAL,
    FOREIGN_COMPLETENESS_UNAVAILABLE,
    FOREIGN_COMPLETENESS_UNKNOWN,
    FOREIGN_NEUTRAL,
    FOREIGN_SELL,
    FOREIGN_SELL_PERCENTILE,
    FOREIGN_STRONG_BUY,
    FOREIGN_STRONG_PERCENTILE,
    FOREIGN_STRONG_SELL,
    FOREIGN_STRONG_SELL_PERCENTILE,
    FOREIGN_TIMING_EOD,
    FOREIGN_TIMING_UNKNOWN,
    FOREIGN_UNKNOWN,
    MIN_CROSS_SECTION,
)
from modules.actionable_research.paths import FusionPaths

CAMERA_HAS_INTRADAY_FOREIGN = False
CAMERA_FOREIGN_AUDIT = (
    "VPS Camera canonical 5-minute schema is OHLCV only "
    "(symbol, timestamp, session_date, open, high, low, close, volume, source, "
    "collected_at, quality_flag). No foreign buy/sell/net fields exist."
)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size <= 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return pd.DataFrame()


def _norm_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return str(value or "").strip()[:10]
    return str(ts.date())


def load_foreign_panel(
    trade_date: str,
    *,
    paths: FusionPaths,
    injected: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Load EOD per-symbol foreign flow for trade_date.

    Search order:
    1. injected DataFrame (tests / production caller)
    2. data/foreign_flow_history/canonical/session=DATE.parquet or daily csv
    3. data/foreign_flow_history/canonical/by_symbol/*.csv filtered to date
    """
    td = str(trade_date)[:10]
    if injected is not None:
        df = injected.copy()
        source = "injected"
        timing = str(df.attrs.get("timing") or FOREIGN_TIMING_EOD) if hasattr(df, "attrs") else FOREIGN_TIMING_EOD
        return _normalize_panel(df, td, source=source, timing=timing)

    root = paths.foreign_root()
    session_parquet = root / "canonical" / f"session_date={td}" / "foreign.parquet"
    session_csv = root / "canonical" / f"{td}.csv"
    daily_csv = root / "canonical" / "daily" / f"{td}.csv"
    for candidate, _label in (
        (session_parquet, "foreign_flow_history.session_parquet"),
        (session_csv, "foreign_flow_history.session_csv"),
        (daily_csv, "foreign_flow_history.daily_csv"),
    ):
        if candidate.suffix == ".parquet" and candidate.exists():
            try:
                df = pd.read_parquet(candidate)
            except Exception:
                df = pd.DataFrame()
            if not df.empty:
                return _normalize_panel(df, td, source=str(candidate), timing=FOREIGN_TIMING_EOD)
        elif candidate.exists():
            df = _read_csv(candidate)
            if not df.empty:
                return _normalize_panel(df, td, source=str(candidate), timing=FOREIGN_TIMING_EOD)

    by_symbol_dir = root / "canonical" / "by_symbol"
    if by_symbol_dir.is_dir():
        frames = []
        for csv_path in sorted(by_symbol_dir.glob("*.csv")):
            part = _read_csv(csv_path)
            if part.empty:
                continue
            frames.append(part)
        if frames:
            df = pd.concat(frames, ignore_index=True)
            panel = _normalize_panel(
                df,
                td,
                source=str(by_symbol_dir),
                timing=FOREIGN_TIMING_EOD,
            )
            if panel.get("available"):
                return panel

    return {
        "available": False,
        "source": str(root),
        "timing": FOREIGN_TIMING_UNKNOWN,
        "completeness": FOREIGN_COMPLETENESS_UNAVAILABLE,
        "frame": pd.DataFrame(),
        "note": "FOREIGN_DATA_UNAVAILABLE — not zero flow. Camera has no intraday foreign.",
        "camera_intraday_foreign": CAMERA_HAS_INTRADAY_FOREIGN,
        "camera_audit": CAMERA_FOREIGN_AUDIT,
    }


def _normalize_panel(
    df: pd.DataFrame,
    trade_date: str,
    *,
    source: str,
    timing: str,
) -> Dict[str, Any]:
    if df is None or df.empty:
        return {
            "available": False,
            "source": source,
            "timing": timing or FOREIGN_TIMING_UNKNOWN,
            "completeness": FOREIGN_COMPLETENESS_UNAVAILABLE,
            "frame": pd.DataFrame(),
            "note": "FOREIGN_DATA_UNAVAILABLE",
            "camera_intraday_foreign": CAMERA_HAS_INTRADAY_FOREIGN,
            "camera_audit": CAMERA_FOREIGN_AUDIT,
        }
    work = df.copy()
    if "trade_date" in work.columns:
        work["trade_date"] = work["trade_date"].map(_norm_date)
        work = work[work["trade_date"] == trade_date]
    if work.empty:
        return {
            "available": False,
            "source": source,
            "timing": timing,
            "completeness": FOREIGN_COMPLETENESS_UNAVAILABLE,
            "frame": work,
            "note": "FOREIGN_DATA_UNAVAILABLE for this trade_date (not zero).",
            "camera_intraday_foreign": CAMERA_HAS_INTRADAY_FOREIGN,
            "camera_audit": CAMERA_FOREIGN_AUDIT,
        }
    if "symbol" in work.columns:
        work["symbol"] = work["symbol"].astype(str).str.upper().str.strip()
    rename = {}
    cols = {c.lower(): c for c in work.columns}
    for want, aliases in (
        ("foreign_net_value", ("foreign_net_value", "net_value", "nn_net_value")),
        ("foreign_buy_value", ("foreign_buy_value", "buy_value")),
        ("foreign_sell_value", ("foreign_sell_value", "sell_value")),
        ("foreign_net_volume", ("foreign_net_volume", "net_volume")),
        ("foreign_buy_volume", ("foreign_buy_volume", "buy_volume")),
        ("foreign_sell_volume", ("foreign_sell_volume", "sell_volume")),
    ):
        for alias in aliases:
            if alias in cols:
                rename[cols[alias]] = want
                break
    work = work.rename(columns=rename)
    if "foreign_net_value" not in work.columns:
        if "foreign_buy_value" in work.columns and "foreign_sell_value" in work.columns:
            buy = pd.to_numeric(work["foreign_buy_value"], errors="coerce")
            sell = pd.to_numeric(work["foreign_sell_value"], errors="coerce")
            work["foreign_net_value"] = buy - sell
    return {
        "available": True,
        "source": source,
        "timing": timing or FOREIGN_TIMING_EOD,
        "completeness": FOREIGN_COMPLETENESS_UNKNOWN,
        "frame": work,
        "note": "EOD HSX/symbol-level foreign VALUE. Not Camera realtime foreign flow.",
        "camera_intraday_foreign": CAMERA_HAS_INTRADAY_FOREIGN,
        "camera_audit": CAMERA_FOREIGN_AUDIT,
    }


def classify_foreign_flow(
    trade_date: str,
    symbols: Sequence[str],
    *,
    paths: FusionPaths,
    injected: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    panel = load_foreign_panel(trade_date, paths=paths, injected=injected)
    timing = str(panel.get("timing") or FOREIGN_TIMING_UNKNOWN)
    source = str(panel.get("source") or "")
    by_symbol: Dict[str, Dict[str, Any]] = {}
    n_univ = len(tuple(symbols))

    if not panel.get("available"):
        for raw in symbols:
            symbol = str(raw).upper()
            by_symbol[symbol] = {
                "foreign_flow_status": FOREIGN_UNKNOWN,
                "foreign_net_value": None,
                "foreign_net_volume": None,
                "foreign_buy_value": None,
                "foreign_sell_value": None,
                "source": source,
                "timing": timing,
                "data_completeness": FOREIGN_COMPLETENESS_UNAVAILABLE,
                "note": "FOREIGN_DATA_UNAVAILABLE — not NO_FOREIGN_BUY / not zero.",
            }
        return {
            "available": False,
            "timing": timing,
            "source": source,
            "completeness": FOREIGN_COMPLETENESS_UNAVAILABLE,
            "cross_section_n": 0,
            "by_symbol": by_symbol,
            "camera_intraday_foreign": CAMERA_HAS_INTRADAY_FOREIGN,
            "camera_audit": CAMERA_FOREIGN_AUDIT,
        }

    frame: pd.DataFrame = panel["frame"]
    nets: Dict[str, float] = {}
    extra: Dict[str, Dict[str, Any]] = {}
    for _, row in frame.iterrows():
        symbol = str(row.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        net = pd.to_numeric(pd.Series([row.get("foreign_net_value")]), errors="coerce").iloc[0]
        if pd.isna(net):
            continue
        nets[symbol] = float(net)
        extra[symbol] = {
            "foreign_net_value": float(net),
            "foreign_net_volume": _opt_num(row, "foreign_net_volume"),
            "foreign_buy_value": _opt_num(row, "foreign_buy_value"),
            "foreign_sell_value": _opt_num(row, "foreign_sell_value"),
        }

    cross_n = len(nets)
    completeness = (
        FOREIGN_COMPLETENESS_COMPLETE
        if n_univ and cross_n >= n_univ
        else (FOREIGN_COMPLETENESS_PARTIAL if cross_n else FOREIGN_COMPLETENESS_UNAVAILABLE)
    )
    percentiles: Dict[str, float] = {}
    can_rank = cross_n >= MIN_CROSS_SECTION
    if can_rank:
        series = pd.Series(nets)
        ranks = series.rank(method="average", pct=True) * 100.0
        percentiles = {str(k): float(v) for k, v in ranks.items()}

    for raw in symbols:
        symbol = str(raw).upper()
        if symbol not in nets:
            by_symbol[symbol] = {
                "foreign_flow_status": FOREIGN_UNKNOWN,
                "foreign_net_value": None,
                "foreign_net_volume": None,
                "foreign_buy_value": None,
                "foreign_sell_value": None,
                "source": source,
                "timing": timing,
                "data_completeness": completeness,
                "note": "FOREIGN_DATA_UNAVAILABLE for symbol — not zero flow.",
            }
            continue
        net = nets[symbol]
        if not can_rank:
            status = FOREIGN_UNKNOWN
            note = "INSUFFICIENT_CROSS_SECTION — not converted to NEUTRAL/zero."
        else:
            pct = percentiles.get(symbol, 50.0)
            extra[symbol]["foreign_net_value_percentile"] = pct
            if net > 0 and pct >= FOREIGN_STRONG_PERCENTILE:
                status = FOREIGN_STRONG_BUY
            elif net > 0 and pct >= FOREIGN_BUY_PERCENTILE:
                status = FOREIGN_BUY
            elif net < 0 and pct <= FOREIGN_STRONG_SELL_PERCENTILE:
                status = FOREIGN_STRONG_SELL
            elif net < 0 and pct <= FOREIGN_SELL_PERCENTILE:
                status = FOREIGN_SELL
            else:
                status = FOREIGN_NEUTRAL
            note = "EOD universe-relative net foreign value. Not Camera realtime."
        row_extra = extra.get(symbol) or {}
        by_symbol[symbol] = {
            "foreign_flow_status": status,
            "foreign_net_value": row_extra.get("foreign_net_value"),
            "foreign_net_volume": row_extra.get("foreign_net_volume"),
            "foreign_buy_value": row_extra.get("foreign_buy_value"),
            "foreign_sell_value": row_extra.get("foreign_sell_value"),
            "foreign_net_value_percentile": row_extra.get("foreign_net_value_percentile"),
            "source": source,
            "timing": timing,
            "data_completeness": completeness,
            "note": note,
        }

    return {
        "available": True,
        "timing": timing,
        "source": source,
        "completeness": completeness,
        "cross_section_n": cross_n,
        "by_symbol": by_symbol,
        "camera_intraday_foreign": CAMERA_HAS_INTRADAY_FOREIGN,
        "camera_audit": CAMERA_FOREIGN_AUDIT,
    }


def _opt_num(row: pd.Series, key: str) -> Optional[float]:
    if key not in row.index:
        return None
    val = pd.to_numeric(pd.Series([row[key]]), errors="coerce").iloc[0]
    if pd.isna(val):
        return None
    return float(val)
