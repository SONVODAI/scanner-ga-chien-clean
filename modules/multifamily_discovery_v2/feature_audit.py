"""
Phase 1 leakage-safe T0 feature audit. Read-only on production CSVs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.adapters import load_lifecycle
from modules.multifamily_discovery_v2.registry import V2_REGISTRY

AUDIT_COLUMNS: tuple[str, ...] = tuple(V2_REGISTRY.keys()) + (
    "volume_ratio",
    "ema9_slope",
    "ma20_slope",
    "near_bottom20",
    "near_bottom60",
    "sector",
)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "null", "<na>"}


def _unique_nonmissing(series: pd.Series) -> int:
    return int(series[~series.map(_is_missing)].nunique(dropna=True))


def audit_feature_frame(frame: pd.DataFrame) -> Dict[str, Any]:
    n = int(len(frame))
    dates = pd.to_datetime(frame.get("trade_date"), errors="coerce")
    symbols = frame["symbol"].astype(str) if "symbol" in frame.columns else pd.Series(dtype=str)
    date_count = int(dates.nunique(dropna=True))
    symbol_count = int(symbols.nunique())
    rows: List[Dict[str, Any]] = []

    for name, spec in V2_REGISTRY.items():
        present = name in frame.columns or (name == "close" and "price" in frame.columns)
        source_col = "price" if name == "close" and "price" in frame.columns and "close" not in frame.columns else name
        series = frame[source_col] if present and source_col in frame.columns else pd.Series([None] * n)
        miss = int(series.map(_is_missing).sum()) if n else 0
        miss_pct = round(100.0 * miss / n, 2) if n else None
        nunique = _unique_nonmissing(series) if present else 0

        by_date_cov = None
        by_symbol_cov = None
        if present and n and "trade_date" in frame.columns:
            tmp = pd.DataFrame(
                {
                    "trade_date": frame["trade_date"],
                    "symbol": frame["symbol"] if "symbol" in frame.columns else "",
                    "ok": ~series.map(_is_missing),
                }
            )
            by_date_cov = round(float(tmp.groupby("trade_date")["ok"].mean().mean() * 100.0), 2)
            by_symbol_cov = round(float(tmp.groupby("symbol")["ok"].mean().mean() * 100.0), 2)

        degenerate = False
        degenerate_reason = ""
        if not present:
            degenerate = True
            degenerate_reason = "absent"
        elif miss_pct == 100.0:
            degenerate = True
            degenerate_reason = "100_percent_missing"
        elif nunique <= 1:
            degenerate = True
            degenerate_reason = "no_variation"

        rows.append(
            {
                "field": name,
                "family": spec.family,
                "source": spec.source,
                "present_in_lifecycle": bool(present),
                "datatype": spec.datatype,
                "t0_available": spec.t0_safe and present,
                "missing_count": miss,
                "missing_pct": miss_pct,
                "coverage_by_date_pct": by_date_cov,
                "coverage_by_symbol_pct": by_symbol_cov,
                "nunique_nonmissing": nunique,
                "leakage_safe": spec.leakage_safe,
                "search_eligible_v2": spec.search_eligible and not degenerate,
                "intended_search_eligible": spec.search_eligible,
                "degenerate": degenerate,
                "degenerate_reason": degenerate_reason,
                "scientifically_suitable": spec.search_eligible and spec.leakage_safe and not degenerate,
                "notes": spec.notes,
            }
        )

    extra_empty: List[Dict[str, Any]] = []
    for col in ("volume_ratio", "ema9_slope", "ma20_slope", "near_bottom20", "near_bottom60", "sector"):
        if col not in frame.columns:
            extra_empty.append({"field": col, "status": "absent"})
            continue
        miss = int(frame[col].map(_is_missing).sum())
        extra_empty.append(
            {
                "field": col,
                "status": "100_percent_empty" if miss == n else "present",
                "missing_pct": round(100.0 * miss / n, 2) if n else None,
            }
        )

    return {
        "n_rows": n,
        "n_symbols": symbol_count,
        "n_dates": date_count,
        "date_min": str(dates.min().date()) if dates.notna().any() else None,
        "date_max": str(dates.max().date()) if dates.notna().any() else None,
        "features": rows,
        "empty_aliases": extra_empty,
        "demoted_from_search": [
            r["field"] for r in rows if r["intended_search_eligible"] and r["degenerate"]
        ],
    }


def run_feature_audit(lifecycle: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    frame = lifecycle.copy() if lifecycle is not None else load_lifecycle()
    return audit_feature_frame(frame)
