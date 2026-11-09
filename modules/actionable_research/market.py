"""Read-only market context. Context only — not BUY permission."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from modules.actionable_research.paths import FusionPaths
from modules.edge_research.market_state import resolve_current_market_research


def _norm_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return str(value or "").strip()[:10]
    return str(ts.date())


def _read_csv(path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size <= 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return pd.DataFrame()


def load_market_context(trade_date: str, *, paths: FusionPaths) -> Dict[str, Any]:
    """
    Canonical market context for one session.

    Prefers market_daily_t0.csv (official daily freeze). Falls back to
    market_t0_snapshot.csv. Uses existing research-state helpers only as
    labels — never as a universal Market Real BUY gate.
    """
    td = str(trade_date)[:10]
    daily = _read_csv(paths.market_daily_t0_path())
    snap = _read_csv(paths.market_t0_snapshot_path())
    row = None
    source = "UNAVAILABLE"
    source_status = "UNAVAILABLE"

    if not daily.empty and "trade_date" in daily.columns:
        daily = daily.copy()
        daily["trade_date"] = daily["trade_date"].map(_norm_date)
        hit = daily[daily["trade_date"] == td]
        if not hit.empty:
            row = hit.iloc[-1]
            source = "market_daily_t0.csv"
            source_status = "OK"

    if row is None and not snap.empty and "trade_date" in snap.columns:
        snap = snap.copy()
        snap["trade_date"] = snap["trade_date"].map(_norm_date)
        hit = snap[snap["trade_date"] == td]
        if not hit.empty:
            if "session_slot" in hit.columns:
                preferred = hit[
                    hit["session_slot"].astype(str).str.upper().isin(
                        {"AFTER_CLOSE", "CLOSE", "EOD", "EOD_PLUS_3H", "MIDDAY"}
                    )
                ]
                hit = preferred if not preferred.empty else hit
            row = hit.iloc[-1]
            source = "market_t0_snapshot.csv"
            source_status = "OK_SNAPSHOT_FALLBACK"

    if row is None:
        return {
            "market_state": "UNKNOWN",
            "market_transition": "UNKNOWN -> UNKNOWN",
            "market_trajectory": "UNKNOWN",
            "market_level": "UNKNOWN",
            "market_real": None,
            "market_forecast": None,
            "breadth_score": None,
            "market_regime": None,
            "trading_today": None,
            "market_context_source": source,
            "market_context_source_status": source_status,
        }

    def _num(key: str) -> Optional[float]:
        if key not in row.index:
            return None
        val = pd.to_numeric(pd.Series([row[key]]), errors="coerce").iloc[0]
        if pd.isna(val):
            return None
        return float(val)

    market_real = _num("market_real")
    series = None
    hist_src = daily if source.startswith("market_daily") else snap
    if hist_src is not None and not hist_src.empty and "trade_date" in hist_src.columns:
        work = hist_src.copy()
        work["date"] = work["trade_date"].map(_norm_date)
        work = work[work["date"] <= td]
        if "market_real" in work.columns:
            series = work[["date", "market_real"]].copy()
            if "market_forecast" in work.columns:
                series["market_forecast"] = work["market_forecast"]
            if "breadth_score" in work.columns:
                series["breadth_score"] = work["breadth_score"]
            series["ambiguous"] = False

    research = resolve_current_market_research(market_real, series)
    stored_regime = None
    if "market_regime" in row.index and not pd.isna(row["market_regime"]):
        stored_regime = str(row["market_regime"])
    trading_today = None
    if "trading_today" in row.index and not pd.isna(row["trading_today"]):
        trading_today = row["trading_today"]

    return {
        "market_state": research.get("research_market_state") or "UNKNOWN",
        "market_transition": research.get("research_market_transition") or "UNKNOWN -> UNKNOWN",
        "market_trajectory": research.get("research_market_trajectory") or "UNKNOWN",
        "market_level": research.get("research_market_level") or "UNKNOWN",
        "market_real": market_real,
        "market_forecast": _num("market_forecast"),
        "breadth_score": _num("breadth_score"),
        "market_regime": stored_regime,
        "trading_today": trading_today,
        "market_context_source": source,
        "market_context_source_status": source_status,
        "note": "Market First is context only; not BUY permission.",
    }
