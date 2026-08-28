"""
Phase 3K.1 — Living research observation orchestrator and historical multi-day replay.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.production_daily_assessment import (
    build_daily_assessment,
    build_daily_summary,
)
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    persist_summary,
)
from modules.edge_research.opr_bridge.production_living_observation_records import (
    HISTORICAL_MULTI_DAY_REPLAY,
    STOP_LIVING_RESEARCH_OBSERVATION_READY,
)
from modules.edge_research.opr_bridge.production_market_delta import extract_market_snapshot
from modules.edge_research.opr_bridge.production_observation_cutoff import truncate_panel_at_cutoff
from modules.edge_research.opr_bridge.production_observation_persistence import (
    load_observation_index,
    lookup_birth_record,
)
from modules.edge_research.opr_bridge.production_research_observation import (
    run_production_research_observation,
)


def list_active_observation_ids(data_dir: Optional[Path] = None) -> List[str]:
    index = load_observation_index(data_dir)
    return sorted(index.get("observations", {}).keys())


def run_daily_living_assessment(
    panel: pd.DataFrame,
    *,
    assessment_trade_date: str,
    observation_ids: Optional[List[str]] = None,
    data_dir: Optional[Path] = None,
    persist: bool = True,
    replay_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run daily assessment for all active observations on assessment_trade_date.
    Idempotent: same inputs reproduce same assessment identity.
    """
    truncated, _ = truncate_panel_at_cutoff(panel, assessment_trade_date)
    dates = sorted(truncated["trade_date"].astype(str).unique().tolist())
    oids = observation_ids or list_active_observation_ids(data_dir)
    assessments = []
    all_new_outcomes = []

    for oid in oids:
        birth = lookup_birth_record(oid, data_dir=data_dir)
        if birth is None:
            continue
        if birth.cutoff.trade_date > assessment_trade_date:
            continue
        a, outcomes = build_daily_assessment(
            panel,
            birth,
            assessment_trade_date=assessment_trade_date,
            trading_dates=dates,
            data_dir=data_dir,
            persist=persist,
            replay_mode=replay_mode,
        )
        assessments.append(a)
        all_new_outcomes.extend(outcomes)

    snap = extract_market_snapshot(truncated, assessment_trade_date)
    summary = build_daily_summary(
        trade_date=assessment_trade_date,
        assessments=assessments,
        market_snapshot=snap,
        replay_mode=replay_mode,
    )
    if persist:
        persist_summary(summary, data_dir=data_dir)

    return {
        "assessment_trade_date": assessment_trade_date,
        "assessments": [a.to_dict() for a in assessments],
        "summary": summary.to_dict(),
        "new_outcome_count": len(all_new_outcomes),
        "idempotent_keys": [a.assessment_identity_hash for a in assessments],
    }


def run_historical_multi_day_replay(
    panel: pd.DataFrame,
    *,
    start_trade_date: str,
    num_trading_days: int = 10,
    birth_cutoff_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    HISTORICAL_MULTI_DAY_REPLAY — infrastructure validation only, NOT forward evidence.
    """
    all_dates = sorted(panel["trade_date"].astype(str).unique().tolist())

    birth_date = birth_cutoff_date or start_trade_date
    if birth_date not in all_dates:
        birth_date = all_dates[0] if all_dates else start_trade_date

    birth_session = run_production_research_observation(
        panel,
        data_cutoff_date=birth_date,
        data_dir=data_dir,
        repo_root=repo_root,
        persist=True,
    )
    observation_id = birth_session.observation_id

    start_idx = all_dates.index(birth_date) if birth_date in all_dates else 0
    replay_dates = all_dates[start_idx : start_idx + num_trading_days]
    if len(replay_dates) < num_trading_days:
        replay_dates = all_dates[start_idx:]

    daily_results = []
    unchanged_belief_days = []
    market_delta_days = []
    forward_arrival_days = []
    changed_assessment_days = []

    for d in replay_dates:
        result = run_daily_living_assessment(
            panel,
            assessment_trade_date=d,
            observation_ids=[observation_id],
            data_dir=data_dir,
            persist=True,
            replay_mode=HISTORICAL_MULTI_DAY_REPLAY,
        )
        daily_results.append(result)
        for a_dict in result.get("assessments", []):
            if not a_dict.get("epistemic_delta", {}).get("changed"):
                unchanged_belief_days.append(d)
            else:
                changed_assessment_days.append(d)
            mkt_keys = a_dict.get("market_delta", {}).get("summary_keys", [])
            if mkt_keys and mkt_keys != ["market:unchanged"]:
                market_delta_days.append(d)
            if a_dict.get("forward_outcomes_newly_available"):
                forward_arrival_days.append(d)

    return {
        "test_kind": HISTORICAL_MULTI_DAY_REPLAY,
        "observation_id": observation_id,
        "birth_cutoff_date": birth_date,
        "replay_dates": replay_dates,
        "num_days": len(replay_dates),
        "daily_results": daily_results,
        "demonstrations": {
            "unchanged_belief_days": unchanged_belief_days[:3],
            "market_delta_days": market_delta_days[:3],
            "forward_horizon_arrival_days": forward_arrival_days[:3],
            "changed_assessment_days": changed_assessment_days,
        },
        "counts_as_forward_evidence": False,
        "stop_boundary": STOP_LIVING_RESEARCH_OBSERVATION_READY,
    }
