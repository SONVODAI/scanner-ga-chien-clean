"""
Phase 3K.1 — Market context delta computation for daily assessments.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.production_living_observation_records import MarketDelta
from modules.edge_research.opr_bridge.production_observation_cutoff import compute_market_context_identity


def extract_market_snapshot(panel: pd.DataFrame, trade_date: str) -> Dict[str, Any]:
    if panel.empty:
        return {}
    sub = panel[panel["trade_date"].astype(str) == str(trade_date)]
    if sub.empty:
        sub = panel.sort_values("trade_date").tail(1)
    if sub.empty:
        return {}
    row = sub.iloc[0]
    snap: Dict[str, Any] = {}
    for col in (
        "market_real",
        "market_forecast",
        "breadth_score",
        "research_market_state",
        "research_market_transition",
        "research_market_level",
        "research_market_trajectory",
        "breadth_t0",
    ):
        if col in sub.columns and pd.notna(row.get(col)):
            snap[col] = row[col]
    return snap


def _direction(prev: Optional[float], curr: Optional[float], *, higher_is_stronger: bool = True) -> str:
    if prev is None or curr is None:
        return "UNKNOWN"
    if abs(curr - prev) < 1e-9:
        return "UNCHANGED"
    increased = curr > prev
    if higher_is_stronger:
        return "STRENGTHENED" if increased else "WEAKENED"
    return "WEAKENED" if increased else "STRENGTHENED"


def _transition_direction(prev: Optional[str], curr: Optional[str]) -> str:
    if not prev or not curr:
        return "UNKNOWN"
    if prev == curr:
        return "UNCHANGED"
    accelerating = {"ACCELERATING", "EXPANDING", "RISING"}
    decelerating = {"DECELERATING", "CONTRACTING", "FALLING"}
    if curr in accelerating and prev not in accelerating:
        return "ACCELERATED"
    if curr in decelerating and prev not in decelerating:
        return "DECELERATED"
    return "CHANGED"


def compute_cohort_relative_behavior(
    panel: pd.DataFrame,
    trade_date: str,
    symbols: Tuple[str, ...],
    *,
    return_col: str = "t3_return",
) -> Optional[float]:
    if not symbols or panel.empty:
        return None
    sub = panel[
        (panel["trade_date"].astype(str) == str(trade_date))
        & (panel["symbol"].astype(str).isin(symbols))
    ]
    if sub.empty or return_col not in sub.columns:
        return None
    vals = sub[return_col].dropna()
    if vals.empty:
        return None
    return float(vals.mean())


def compute_market_delta(
    panel: pd.DataFrame,
    *,
    current_trade_date: str,
    previous_trade_date: Optional[str],
    cohort_symbols: Tuple[str, ...] = (),
) -> MarketDelta:
    curr_snap = extract_market_snapshot(panel, current_trade_date)
    prev_snap = extract_market_snapshot(panel, previous_trade_date) if previous_trade_date else {}

    curr_id, curr_hash = compute_market_context_identity(panel, current_trade_date)
    prev_id, prev_hash = (
        compute_market_context_identity(panel, previous_trade_date)
        if previous_trade_date
        else ("NONE", stable_hash({"none": True}))
    )

    prev_state = prev_snap.get("research_market_state")
    curr_state = curr_snap.get("research_market_state")
    regime_changed = bool(prev_state and curr_state and prev_state != curr_state)

    prev_breadth = prev_snap.get("breadth_score")
    curr_breadth = curr_snap.get("breadth_score")
    breadth_dir = _direction(
        float(prev_breadth) if prev_breadth is not None else None,
        float(curr_breadth) if curr_breadth is not None else None,
    )

    prev_trans = prev_snap.get("research_market_transition")
    curr_trans = curr_snap.get("research_market_transition")
    transition_dir = _transition_direction(
        str(prev_trans) if prev_trans is not None else None,
        str(curr_trans) if curr_trans is not None else None,
    )

    dispersion_changed = False
    if "market_real" in curr_snap and "market_forecast" in curr_snap:
        curr_disp = abs(float(curr_snap["market_real"]) - float(curr_snap["market_forecast"]))
        if prev_snap.get("market_real") is not None and prev_snap.get("market_forecast") is not None:
            prev_disp = abs(float(prev_snap["market_real"]) - float(prev_snap["market_forecast"]))
            dispersion_changed = abs(curr_disp - prev_disp) > 0.01

    prev_cohort = compute_cohort_relative_behavior(panel, previous_trade_date, cohort_symbols) if previous_trade_date else None
    curr_cohort = compute_cohort_relative_behavior(panel, current_trade_date, cohort_symbols)
    cohort_changed = (
        prev_cohort is not None
        and curr_cohort is not None
        and abs(curr_cohort - prev_cohort) > 0.05
    )

    compatibility = "UNCHANGED"
    if curr_state and curr_snap.get("research_market_level"):
        compatibility = "UNKNOWN"
        if regime_changed:
            compatibility = "LESS_COMPATIBLE" if curr_state in ("RISK_OFF", "CONTRACTING") else "MORE_COMPATIBLE"

    summary_keys: List[str] = []
    if regime_changed:
        summary_keys.append(f"regime:{prev_state}->{curr_state}")
    if breadth_dir != "UNCHANGED":
        summary_keys.append(f"breadth:{breadth_dir}")
    if transition_dir not in ("UNCHANGED", "UNKNOWN"):
        summary_keys.append(f"transition:{transition_dir}")
    if dispersion_changed:
        summary_keys.append("dispersion:changed")
    if cohort_changed:
        summary_keys.append("cohort_relative:changed")
    if not summary_keys:
        summary_keys.append("market:unchanged")

    delta_payload = {
        "prev": prev_snap,
        "curr": curr_snap,
        "prev_hash": prev_hash,
        "curr_hash": curr_hash,
        "summary_keys": summary_keys,
    }
    delta_hash = stable_hash(delta_payload)

    return MarketDelta(
        regime_changed=regime_changed,
        breadth_direction=breadth_dir,
        transition_direction=transition_dir,
        dispersion_changed=dispersion_changed,
        cohort_relative_changed=cohort_changed,
        compatibility_direction=compatibility,
        summary_keys=tuple(summary_keys),
        previous_context_hash=prev_hash,
        current_context_hash=curr_hash,
        delta_hash=delta_hash,
    )
