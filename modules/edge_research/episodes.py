"""
Market episode segmentation for Edge Research (Phase 3).

Uses Market state/transition ONLY — never candidate performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from modules.edge_research.contracts import EPISODE_CONFIG_VERSION, EPISODE_DATE_GAP_MAX


@dataclass(frozen=True)
class MarketEpisode:
    episode_id: str
    episode_version: str
    start_date: str
    end_date: str
    start_state: str
    end_state: str
    transition_sequence: str
    min_market_real: Optional[float]
    max_market_real: Optional[float]
    number_of_trading_dates: int
    dates: Tuple[str, ...]


def _daily_market_summary(panel: pd.DataFrame) -> pd.DataFrame:
    """One row per T0 date with market fields only."""
    if panel.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "research_market_state",
                "research_market_transition",
                "market_real",
            ]
        )
    df = panel.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    agg_spec: Dict[str, tuple] = {
        "research_market_state": ("research_market_state", "first"),
        "research_market_transition": ("research_market_transition", "first"),
    }
    if "market_real" in df.columns:
        agg_spec["market_real"] = ("market_real", "first")
    daily = df.groupby("trade_date", sort=True).agg(**agg_spec).reset_index()
    if "market_real" not in daily.columns:
        daily["market_real"] = pd.NA
    return daily.sort_values("trade_date").reset_index(drop=True)


def segment_market_episodes(panel: pd.DataFrame) -> List[MarketEpisode]:
    """
    Episode v1: contiguous trading dates sharing the same research_market_transition.

    New episode when transition changes or calendar gap > EPISODE_DATE_GAP_MAX.
    """
    daily = _daily_market_summary(panel)
    if daily.empty:
        return []

    episodes: List[MarketEpisode] = []
    current_dates: List[str] = []
    current_transitions: List[str] = []
    current_states: List[str] = []
    current_mrs: List[float] = []
    prev_date: Optional[pd.Timestamp] = None
    anchor_transition: Optional[str] = None

    def _flush() -> None:
        nonlocal current_dates, current_transitions, current_states, current_mrs
        if not current_dates:
            return
        seq = " -> ".join(dict.fromkeys(current_transitions))
        mr_vals = [v for v in current_mrs if v is not None and pd.notna(v)]
        ep = MarketEpisode(
            episode_id=f"EP-{len(episodes) + 1:04d}",
            episode_version=EPISODE_CONFIG_VERSION,
            start_date=current_dates[0],
            end_date=current_dates[-1],
            start_state=current_states[0],
            end_state=current_states[-1],
            transition_sequence=seq,
            min_market_real=min(mr_vals) if mr_vals else None,
            max_market_real=max(mr_vals) if mr_vals else None,
            number_of_trading_dates=len(current_dates),
            dates=tuple(current_dates),
        )
        episodes.append(ep)
        current_dates = []
        current_transitions = []
        current_states = []
        current_mrs = []

    for _, row in daily.iterrows():
        d_str = str(row["trade_date"])
        d_ts = pd.Timestamp(d_str)
        transition = str(row.get("research_market_transition", "UNKNOWN"))
        state = str(row.get("research_market_state", "UNKNOWN"))
        mr = row.get("market_real")
        mr_f = None if pd.isna(mr) else float(mr)

        gap_break = False
        if prev_date is not None:
            gap = (d_ts - prev_date).days
            if gap > EPISODE_DATE_GAP_MAX:
                gap_break = True

        transition_break = anchor_transition is not None and transition != anchor_transition

        if current_dates and (gap_break or transition_break):
            _flush()
            anchor_transition = None

        if not current_dates:
            anchor_transition = transition

        current_dates.append(d_str)
        current_transitions.append(transition)
        current_states.append(state)
        if mr_f is not None:
            current_mrs.append(mr_f)
        prev_date = d_ts

    _flush()
    return episodes


def assign_episodes_to_candidate_rows(
    candidate_rows: pd.DataFrame,
    episodes: Sequence[MarketEpisode],
) -> pd.DataFrame:
    """Map each candidate observation to an episode_id by trade_date."""
    if candidate_rows.empty:
        return candidate_rows.copy()
    out = candidate_rows.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    date_to_episode: Dict[str, str] = {}
    for ep in episodes:
        for d in ep.dates:
            date_to_episode[d] = ep.episode_id
    out["episode_id"] = out["trade_date"].map(date_to_episode).fillna("UNKNOWN_EPISODE")
    return out


def summarize_candidate_episodes(
    candidate_rows: pd.DataFrame,
    episodes: Sequence[MarketEpisode],
    *,
    best_horizon: str,
    baseline_incremental_by_episode: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """
    Count observed Market episodes for a candidate.
    Does NOT imply validated independent episodes.
    """
    from modules.edge_research.metrics import RETURN_COLUMNS, compute_horizon_profile, compute_incremental_metrics

    if candidate_rows.empty:
        return {
            "observed_episodes": 0,
            "positive_episodes": 0,
            "negative_episodes": 0,
            "mixed_episodes": 0,
            "episode_details": [],
        }

    tagged = assign_episodes_to_candidate_rows(candidate_rows, episodes)
    col = RETURN_COLUMNS.get(best_horizon, "t5_return")
    episode_ids = tagged["episode_id"].unique()
    observed = [e for e in episode_ids if e != "UNKNOWN_EPISODE"]

    positive = negative = mixed = 0
    details: List[Dict[str, Any]] = []

    for eid in observed:
        ep_rows = tagged[tagged["episode_id"] == eid]
        ep_meta = next((e for e in episodes if e.episode_id == eid), None)
        rets = pd.to_numeric(ep_rows[col], errors="coerce").dropna()
        if rets.empty:
            result = "INSUFFICIENT"
        else:
            med = float(rets.median())
            if med > 0.5:
                result = "POSITIVE"
                positive += 1
            elif med < -0.5:
                result = "NEGATIVE"
                negative += 1
            else:
                result = "MIXED"
                mixed += 1
        details.append(
            {
                "episode_id": eid,
                "observations": len(ep_rows),
                "episode_result": result,
                "start_date": ep_meta.start_date if ep_meta else "",
                "end_date": ep_meta.end_date if ep_meta else "",
            }
        )

    return {
        "observed_episodes": len(observed),
        "positive_episodes": positive,
        "negative_episodes": negative,
        "mixed_episodes": mixed,
        "episode_details": details,
    }
