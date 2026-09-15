"""
Research-only comparison with Learning Insight DNA dimensions.

Does not call Learning Insight writers, does not feed Challenger, does not
modify earning-learning knowledge tables.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.adapters import load_lifecycle
from modules.multifamily_discovery_v2.panel import _normalize_health_group, _normalize_obv_status

FAMILY_TO_DNA = {
    "obv": ("p_obv", "obv_status"),
    "volume": ("p_volume", "volume_ratio20"),
    "trend": ("p_slope", "ema9_ma20_slope"),
    "health_group": ("p_health", "health_group"),
    "rs_rsi": ("p_rs10", "rs10"),
}


def _continuation_table(lifecycle: pd.DataFrame, label_col: str) -> Dict[str, Any]:
    if lifecycle.empty or label_col not in lifecycle.columns:
        return {"available": False, "reason": f"missing_{label_col}"}
    work = lifecycle.copy()
    t3 = pd.to_numeric(work.get("t3_return_pct"), errors="coerce")
    t5 = pd.to_numeric(work.get("t5_return_pct"), errors="coerce")
    t10 = pd.to_numeric(work.get("t10_return_pct"), errors="coerce")
    work["_label"] = work[label_col].astype(str)
    work["_t3"] = t3
    work["_t5"] = t5
    work["_t10"] = t10
    rows: List[Dict[str, Any]] = []
    for label, grp in work.groupby("_label", dropna=False):
        if str(label).strip() in {"", "nan", "None"}:
            continue
        has_t3 = grp["_t3"].notna()
        t3_win = has_t3 & (grp["_t3"] > 0)
        elig_t5 = t3_win & grp["_t5"].notna()
        cont_t5 = elig_t5 & (grp["_t5"] > 0)
        elig_t10 = t3_win & grp["_t10"].notna()
        cont_t10 = elig_t10 & (grp["_t10"] > 0)
        rows.append(
            {
                "label": str(label),
                "n_t3": int(has_t3.sum()),
                "t3_winrate": round(float((grp["_t3"] > 0).mean() * 100), 2) if has_t3.any() else None,
                "t3_to_t5_n": int(elig_t5.sum()),
                "t3_to_t5_rate": round(float(cont_t5.sum() / elig_t5.sum() * 100), 2) if elig_t5.any() else None,
                "t3_to_t10_n": int(elig_t10.sum()),
                "t3_to_t10_rate": round(float(cont_t10.sum() / elig_t10.sum() * 100), 2) if elig_t10.any() else None,
            }
        )
    return {"available": True, "dimension": label_col, "bands": rows}


def compare_with_learning_insight(
    scoreboard: List[Dict[str, Any]],
    *,
    lifecycle: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Independent descriptive check: do Insight DNA dimensions already differentiate
    continuation rates in the same warehouse V2 is reading?
    """
    frame = lifecycle.copy() if lifecycle is not None else load_lifecycle()
    if "obv_status" in frame.columns:
        frame = frame.copy()
        frame["obv_status_norm"] = frame["obv_status"].map(_normalize_obv_status)
    if "health_group" in frame.columns:
        frame = frame.copy()
        frame["health_group_norm"] = frame["health_group"].map(_normalize_health_group)

    comparisons: List[Dict[str, Any]] = []
    for row in scoreboard:
        raw_family = str(row.get("family") or "").replace(" (CONTROL)", "")
        mapping = FAMILY_TO_DNA.get(raw_family)
        if not mapping:
            continue
        dna_col, raw_col = mapping
        use_col = dna_col if dna_col in frame.columns else raw_col
        if raw_family == "obv" and "obv_status_norm" in frame.columns:
            use_col = "obv_status_norm"
        if raw_family == "health_group" and "health_group_norm" in frame.columns:
            use_col = "health_group_norm"
        table = _continuation_table(frame, use_col)
        v2_verdict = row.get("verdict")
        nested = row.get("nested_vs_rs_max_inc_median")
        bands = table.get("bands") or []
        rates = [b.get("t3_to_t5_rate") for b in bands if b.get("t3_to_t5_rate") is not None]
        spread = (max(rates) - min(rates)) if len(rates) >= 2 else None
        if v2_verdict in {"PROMISING", "WEAK"} and spread is not None and spread >= 5:
            relation = "COMPATIBLE_DIRECTIONAL"
        elif v2_verdict == "REJECT" and (spread is None or spread < 5):
            relation = "COMPATIBLE_NULL"
        elif v2_verdict == "REDUNDANT":
            relation = "UNRELATED_OR_ABSORBED_BY_RS"
        elif v2_verdict == "DEGENERATE":
            relation = "UNRELATED_DEGENERATE_FIELD"
        elif v2_verdict == "INSUFFICIENT_DATA":
            relation = "UNRELATED_INSUFFICIENT_V2"
        else:
            relation = "CONFLICTING_OR_INCONCLUSIVE"
        comparisons.append(
            {
                "family": raw_family,
                "v2_verdict": v2_verdict,
                "v2_nested_vs_rs_max": nested,
                "insight_dimension": use_col,
                "insight_descriptive": table,
                "insight_t3_to_t5_spread_pct": spread,
                "relation": relation,
                "note": (
                    "Descriptive continuation rates from lifecycle DNA/raw columns. "
                    "Not a joint model and not a production coupling."
                ),
            }
        )
    return {
        "coupled": False,
        "comparisons": comparisons,
    }
