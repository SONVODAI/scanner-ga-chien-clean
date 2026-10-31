"""Sweetspot adapter — auxiliary heuristic only. Never scientific ACTIVE edge."""

from __future__ import annotations

from typing import Any, Dict, Sequence

import pandas as pd

from modules.actionable_research.contracts import (
    SWEETSPOT_AUTHORITY_NON_AUTHORITATIVE,
    SWEETSPOT_AUTHORITY_NONE,
    SWEETSPOT_STATUS_LEGACY_HEURISTIC,
    SWEETSPOT_STATUS_NONE,
    SWEETSPOT_STATUS_UNAVAILABLE,
)
from modules.actionable_research.paths import FusionPaths


def load_sweetspot_auxiliary(
    trade_date: str,
    symbols: Sequence[str],
    *,
    paths: FusionPaths,
) -> Dict[str, Dict[str, Any]]:
    """
    Expose already-persisted observer ledger rows as clearly labeled
    NON-AUTHORITATIVE heuristic evidence. Does not run sweetspot_analyzer.
    Does not promote anything to ACTIVE edge.
    """
    td = str(trade_date)[:10]
    path = paths.sweetspot_observer_ledger_path()
    blank = {
        "sweetspot_status": SWEETSPOT_STATUS_UNAVAILABLE,
        "source": str(path),
        "authority_level": SWEETSPOT_AUTHORITY_NONE,
        "matched_sweetspot": None,
        "sweetspot_horizon": None,
        "note": "Legacy RS/RSI sweetspot is heuristic; not a scientific ACTIVE edge.",
    }
    if not path.exists() or path.stat().st_size <= 0:
        return {str(s).upper(): dict(blank) for s in symbols}

    try:
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except Exception:
        out = dict(blank)
        out["sweetspot_status"] = SWEETSPOT_STATUS_UNAVAILABLE
        return {str(s).upper(): out for s in symbols}

    if df.empty or "symbol" not in df.columns:
        none = dict(blank)
        none["sweetspot_status"] = SWEETSPOT_STATUS_NONE
        none["authority_level"] = SWEETSPOT_AUTHORITY_NONE
        return {str(s).upper(): none for s in symbols}

    date_col = "trade_date" if "trade_date" in df.columns else ("t0_date" if "t0_date" in df.columns else None)
    if date_col:
        dates = pd.to_datetime(df[date_col], errors="coerce")
        df = df[dates.dt.strftime("%Y-%m-%d") == td]

    by_symbol: Dict[str, pd.Series] = {}
    for _, row in df.iterrows():
        by_symbol[str(row["symbol"]).upper().strip()] = row

    result: Dict[str, Dict[str, Any]] = {}
    for raw in symbols:
        symbol = str(raw).upper()
        row = by_symbol.get(symbol)
        if row is None:
            result[symbol] = {
                "sweetspot_status": SWEETSPOT_STATUS_NONE,
                "source": str(path),
                "authority_level": SWEETSPOT_AUTHORITY_NONE,
                "matched_sweetspot": None,
                "sweetspot_horizon": None,
                "note": "No observer-ledger sweetspot for this symbol; not an ACTIVE edge.",
            }
            continue
        matched = row.get("matched_sweetspot") if "matched_sweetspot" in row.index else None
        if matched is not None and not pd.isna(matched) and str(matched).strip():
            result[symbol] = {
                "sweetspot_status": SWEETSPOT_STATUS_LEGACY_HEURISTIC,
                "source": str(path),
                "authority_level": SWEETSPOT_AUTHORITY_NON_AUTHORITATIVE,
                "matched_sweetspot": str(matched),
                "sweetspot_horizon": (
                    None
                    if "sweetspot_horizon" not in row.index or pd.isna(row.get("sweetspot_horizon"))
                    else str(row.get("sweetspot_horizon"))
                ),
                "note": "AUXILIARY heuristic only. Never treated as scientific ACTIVE edge.",
            }
        else:
            result[symbol] = {
                "sweetspot_status": SWEETSPOT_STATUS_NONE,
                "source": str(path),
                "authority_level": SWEETSPOT_AUTHORITY_NONE,
                "matched_sweetspot": None,
                "sweetspot_horizon": None,
                "note": "Observer row present without matched sweetspot; not an ACTIVE edge.",
            }
    return result
