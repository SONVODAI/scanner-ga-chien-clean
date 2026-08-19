"""
Research-only Market state / trajectory (separate from production Market First).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.edge_research.contracts import (
    MARKET_LEVEL_CONFIG_VERSION,
    MARKET_LEVEL_V1_THRESHOLDS,
    MARKET_STATE_CONFIG_VERSION,
    RESEARCH_MARKET_STATES,
    SNAPSHOT_POLICY_VERSION,
)


@dataclass(frozen=True)
class RawMarketSnapshot:
    date: str
    time: str
    market_real: float
    market_forecast: Optional[float] = None
    breadth_score: Optional[float] = None
    session_slot: str = ""
    source: str = ""


@dataclass(frozen=True)
class CanonicalMarketSnapshot:
    date: str
    time: str
    market_real: Optional[float]
    market_forecast: Optional[float]
    breadth_score: Optional[float]
    snapshot_count: int
    ambiguous: bool
    distinct_market_real_values: Tuple[float, ...]
    policy_version: str = SNAPSHOT_POLICY_VERSION
    selected_tier: str = ""


def _normalize_time(time_str: str) -> str:
    return str(time_str or "").strip()


def _is_eod_snapshot(snapshot: RawMarketSnapshot) -> bool:
    """Identify EOD / after-close snapshots deterministically."""
    slot = str(snapshot.session_slot or "").upper()
    if slot in {"AFTER_CLOSE", "EOD", "EOD_PLUS_3H"}:
        return True
    time_str = _normalize_time(snapshot.time)
    if not time_str:
        return False
    parts = time_str.split(":")
    if len(parts) >= 2:
        try:
            hour = int(parts[0])
            return hour >= 15
        except ValueError:
            pass
    return False


def dedupe_market_snapshots(snapshots: Sequence[RawMarketSnapshot]) -> List[RawMarketSnapshot]:
    """
    Collapse duplicate timestamps — e.g. stock-level pattern_history rows
    sharing the same (date, time, market_real).
    """
    seen: Dict[Tuple[str, str, float], RawMarketSnapshot] = {}
    for snap in snapshots:
        key = (snap.date, _normalize_time(snap.time), float(snap.market_real))
        if key not in seen:
            seen[key] = snap
        elif _is_eod_snapshot(snap) and not _is_eod_snapshot(seen[key]):
            seen[key] = snap
    return sorted(seen.values(), key=lambda s: (s.date, _normalize_time(s.time)))


def select_canonical_market_snapshot(
    snapshots: Sequence[RawMarketSnapshot],
) -> CanonicalMarketSnapshot:
    """
    Policy canonical_market_t0_v2_eod_preferred:
    - Dedupe by (date, time, market_real)
    - Prefer EOD / AFTER_CLOSE tier when available
    - Canonical = latest time within selected tier
    - ambiguous=True when selected tier has >1 distinct market_real
    - If no EOD tier exists, fall back to latest intraday time with same rule
    """
    if not snapshots:
        return CanonicalMarketSnapshot(
            date="",
            time="",
            market_real=None,
            market_forecast=None,
            breadth_score=None,
            snapshot_count=0,
            ambiguous=True,
            distinct_market_real_values=(),
            selected_tier="none",
        )

    deduped = dedupe_market_snapshots(list(snapshots))
    date = deduped[0].date
    eod = [s for s in deduped if _is_eod_snapshot(s)]
    tier = eod if eod else deduped
    tier_name = "eod" if eod else "intraday"
    distinct_mr = tuple(sorted({float(s.market_real) for s in tier if s.market_real is not None}))
    ambiguous = len(distinct_mr) > 1
    ordered = sorted(tier, key=lambda s: (s.date, _normalize_time(s.time)))
    canonical = ordered[-1]
    return CanonicalMarketSnapshot(
        date=date,
        time=canonical.time,
        market_real=canonical.market_real,
        market_forecast=canonical.market_forecast,
        breadth_score=canonical.breadth_score,
        snapshot_count=len(deduped),
        ambiguous=ambiguous,
        distinct_market_real_values=distinct_mr,
        selected_tier=tier_name,
    )


def classify_market_level(market_real: Optional[float]) -> str:
    """Provisional coarse level — not optimized from outcomes."""
    if market_real is None or not np.isfinite(market_real):
        return "UNKNOWN"
    mr = float(market_real)
    for label, upper in MARKET_LEVEL_V1_THRESHOLDS:
        if mr <= upper:
            return label
    return "UNKNOWN"


def build_market_real_series(
    canonical_by_date: Dict[str, CanonicalMarketSnapshot],
    sorted_dates: Sequence[str],
) -> pd.DataFrame:
    rows = []
    for d in sorted_dates:
        snap = canonical_by_date.get(d)
        rows.append(
            {
                "date": d,
                "market_real": snap.market_real if snap else np.nan,
                "market_forecast": snap.market_forecast if snap else np.nan,
                "breadth_score": snap.breadth_score if snap else np.nan,
                "ambiguous": bool(snap.ambiguous) if snap else True,
            }
        )
    return pd.DataFrame(rows)


def resolve_current_market_research(
    market_real: Optional[float],
    market_series: Optional[pd.DataFrame] = None,
) -> Dict[str, str]:
    """Compute live research market state/transition for UI (T0/past only)."""
    mr = float(market_real) if market_real is not None and np.isfinite(market_real) else None
    level = classify_market_level(mr)

    if market_series is None or market_series.empty or mr is None:
        traj = derive_research_market_trajectory(None, None)
        state = derive_research_market_state(level, traj, ambiguous=False)
        return {
            "research_market_state": state,
            "research_market_transition": derive_market_transition("UNKNOWN", state),
            "research_market_level": level,
            "research_market_trajectory": traj,
        }

    ms = market_series.sort_values("date").reset_index(drop=True)
    state_history: Dict[str, str] = {}
    for _, row in ms.iterrows():
        d = str(row["date"])
        enrich_date_with_market_research(d, ms, pd.DataFrame(), state_history)

    dates = ms["date"].astype(str).tolist()
    mr_lags: list[Optional[float]] = []
    for lag in (1, 2, 3):
        lag_idx = len(dates) - 1 - lag
        if lag_idx >= 0:
            val = ms.iloc[lag_idx]["market_real"]
            mr_lags.append(None if pd.isna(val) else float(val))
        else:
            mr_lags.append(None)

    delta_1 = compute_delta(mr, mr_lags[0] if mr_lags else None)
    delta_3 = compute_delta(mr, mr_lags[2] if len(mr_lags) > 2 else None)
    traj = derive_research_market_trajectory(delta_1, delta_3)
    last_ambiguous = bool(ms.iloc[-1].get("ambiguous", False)) if len(ms) else False
    state = derive_research_market_state(level, traj, ambiguous=last_ambiguous)
    prior = state_history.get(dates[-1], "UNKNOWN") if dates else "UNKNOWN"
    return {
        "research_market_state": state,
        "research_market_transition": derive_market_transition(str(prior), state),
        "research_market_level": level,
        "research_market_trajectory": traj,
    }


def compute_delta(current: Optional[float], prior: Optional[float]) -> Optional[float]:
    if current is None or prior is None:
        return None
    if not np.isfinite(current) or not np.isfinite(prior):
        return None
    return float(current) - float(prior)


def derive_research_market_trajectory(
    delta_mr_1: Optional[float],
    delta_mr_3: Optional[float],
) -> str:
    if delta_mr_1 is None and delta_mr_3 is None:
        return "UNKNOWN"
    if delta_mr_1 is not None and delta_mr_1 > 0.5:
        return "IMPROVING"
    if delta_mr_3 is not None and delta_mr_3 > 0.8:
        return "IMPROVING"
    if delta_mr_1 is not None and delta_mr_1 < -0.5:
        return "DETERIORATING"
    if delta_mr_3 is not None and delta_mr_3 < -1.0:
        return "DETERIORATING"
    if delta_mr_1 is not None and abs(delta_mr_1) <= 0.2:
        return "FLAT"
    return "UNKNOWN"


def derive_research_market_state(
    level: str,
    trajectory: str,
    ambiguous: bool,
) -> str:
    """
    Provisional deterministic state rules (market_state_v1_provisional).
    Never uses forward returns.
    """
    if ambiguous:
        return "UNKNOWN"
    if level == "UNKNOWN":
        return "UNKNOWN"

    if level in {"VERY_LOW", "LOW"}:
        if trajectory == "IMPROVING":
            return "EARLY_RECOVERY"
        if trajectory == "DETERIORATING":
            return "STRESS"
        return "STRESS"

    if level == "MID":
        if trajectory == "IMPROVING":
            return "BROAD_RECOVERY"
        if trajectory == "DETERIORATING":
            return "ROLLOVER"
        return "UNKNOWN"

    if level == "HIGH":
        if trajectory == "IMPROVING":
            return "MATURE"
        if trajectory == "DETERIORATING":
            return "ROLLOVER"
        return "MATURE"

    return "UNKNOWN"


def derive_market_transition(prior_state: str, current_state: str) -> str:
    prior = prior_state if prior_state in RESEARCH_MARKET_STATES else "UNKNOWN"
    current = current_state if current_state in RESEARCH_MARKET_STATES else "UNKNOWN"
    return f"{prior} -> {current}"


def compute_market_internals(stock_panel: pd.DataFrame) -> Dict[str, Optional[float]]:
    """Universe-internal proxies at T0 — research only."""
    if stock_panel.empty:
        return {
            "pct_rs10_negative": None,
            "pct_rsi_le_40": None,
            "pct_rs5_positive": None,
            "median_rs5": None,
            "median_rs10": None,
        }
    rs10 = pd.to_numeric(stock_panel.get("rs10"), errors="coerce")
    rs5 = pd.to_numeric(stock_panel.get("rs5"), errors="coerce")
    rsi = pd.to_numeric(stock_panel.get("rsi14"), errors="coerce")
    n = max(len(stock_panel), 1)
    return {
        "pct_rs10_negative": float((rs10 <= -5).sum() / n * 100) if rs10.notna().any() else None,
        "pct_rsi_le_40": float((rsi <= 40).sum() / n * 100) if rsi.notna().any() else None,
        "pct_rs5_positive": float((rs5 > 0).sum() / n * 100) if rs5.notna().any() else None,
        "median_rs5": float(rs5.median()) if rs10.notna().any() else None,
        "median_rs10": float(rs10.median()) if rs10.notna().any() else None,
    }


def enrich_date_with_market_research(
    date: str,
    market_series: pd.DataFrame,
    stock_panel_for_date: pd.DataFrame,
    state_history: Dict[str, str],
) -> Dict[str, Any]:
    """Build research market fields for one T0 date using only data <= T0."""
    row = market_series[market_series["date"] == date]
    if row.empty:
        mr_t0 = None
        mf = None
        breadth = None
        ambiguous = True
    else:
        r = row.iloc[0]
        mr_t0 = None if pd.isna(r["market_real"]) else float(r["market_real"])
        mf = None if pd.isna(r.get("market_forecast", np.nan)) else float(r["market_forecast"])
        breadth = None if pd.isna(r.get("breadth_score", np.nan)) else float(r["breadth_score"])
        ambiguous = bool(r.get("ambiguous", True))

    idx_list = market_series.index[market_series["date"] == date].tolist()
    if not idx_list:
        return _unknown_market_fields(date)

    idx = int(idx_list[0])
    mr_lags = []
    for lag in (1, 2, 3):
        lag_idx = idx - lag
        if lag_idx >= 0:
            val = market_series.iloc[lag_idx]["market_real"]
            mr_lags.append(None if pd.isna(val) else float(val))
        else:
            mr_lags.append(None)

    delta_mr_1 = compute_delta(mr_t0, mr_lags[0])
    delta_mr_3 = compute_delta(mr_t0, mr_lags[2] if len(mr_lags) > 2 else None)

    breadth_t0 = breadth
    delta_b1 = None
    delta_b3 = None
    if idx >= 1 and "breadth_score" in market_series.columns:
        b_prev = market_series.iloc[idx - 1]["breadth_score"]
        delta_b1 = compute_delta(breadth_t0, None if pd.isna(b_prev) else float(b_prev))
    if idx >= 3 and "breadth_score" in market_series.columns:
        b_prev3 = market_series.iloc[idx - 3]["breadth_score"]
        delta_b3 = compute_delta(breadth_t0, None if pd.isna(b_prev3) else float(b_prev3))

    level = classify_market_level(mr_t0)
    trajectory = derive_research_market_trajectory(delta_mr_1, delta_mr_3)
    state = derive_research_market_state(level, trajectory, ambiguous)

    prior_dates = [d for d in sorted(state_history.keys()) if d < date]
    prior_state = state_history[prior_dates[-1]] if prior_dates else "UNKNOWN"
    transition = derive_market_transition(prior_state, state)
    state_history[date] = state

    internals = compute_market_internals(stock_panel_for_date)

    return {
        "research_market_level": level,
        "research_market_trajectory": trajectory,
        "research_market_state": state,
        "research_market_transition": transition,
        "mr_t0": mr_t0,
        "mr_t_minus_1": mr_lags[0],
        "mr_t_minus_2": mr_lags[1] if len(mr_lags) > 1 else None,
        "mr_t_minus_3": mr_lags[2] if len(mr_lags) > 2 else None,
        "delta_mr_1": delta_mr_1,
        "delta_mr_3": delta_mr_3,
        "breadth_t0": breadth_t0,
        "delta_breadth_1": delta_b1,
        "delta_breadth_3": delta_b3,
        **internals,
        "market_config_version": MARKET_STATE_CONFIG_VERSION,
        "market_level_config_version": MARKET_LEVEL_CONFIG_VERSION,
    }


def _unknown_market_fields(date: str) -> Dict[str, Any]:
    return {
        "research_market_level": "UNKNOWN",
        "research_market_trajectory": "UNKNOWN",
        "research_market_state": "UNKNOWN",
        "research_market_transition": "UNKNOWN",
        "mr_t0": None,
        "mr_t_minus_1": None,
        "mr_t_minus_2": None,
        "mr_t_minus_3": None,
        "delta_mr_1": None,
        "delta_mr_3": None,
        "breadth_t0": None,
        "delta_breadth_1": None,
        "delta_breadth_3": None,
        "pct_rs10_negative": None,
        "pct_rsi_le_40": None,
        "pct_rs5_positive": None,
        "median_rs5": None,
        "median_rs10": None,
    }
