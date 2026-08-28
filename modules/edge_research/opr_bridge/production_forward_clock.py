"""
Phase 3K.2 — Forward clock / eligibility ledger for production observations.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.production_forward_outcome_evaluator import (
    horizon_eligible_on_date,
)
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    list_outcomes_for_observation,
)
from modules.edge_research.opr_bridge.production_observation_lifecycle import (
    compute_observation_age_trading_days,
)
from modules.edge_research.opr_bridge.production_observation_persistence import lookup_birth_record
from modules.edge_research.opr_bridge.production_observation_records import (
    ResearchObservationBirthRecord,
)
from modules.edge_research.opr_bridge.production_daily_run_records import ForwardClockEntry
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    compute_horizon_eligible_date_vn,
)


HORIZON_OFFSETS = {"T3": 3, "T5": 5, "T10": 10}


def compute_horizon_eligible_date(birth_trade_date: str, horizon: str, trading_sessions: List[str]) -> str:
    """
    Compute eligibility date using VN trading calendar session offsets.
    Panel sessions retained as compatibility fallback only.
    """
    return compute_horizon_eligible_date_vn(
        birth_trade_date, horizon, panel_sessions=trading_sessions
    )


def build_forward_clock_entry(
    birth: ResearchObservationBirthRecord,
    *,
    assessment_trade_date: str,
    trading_sessions: List[str],
    data_dir=None,
) -> ForwardClockEntry:
    birth_date = birth.cutoff.trade_date
    age = compute_observation_age_trading_days(birth_date, assessment_trade_date, trading_sessions)
    t3_elig = compute_horizon_eligible_date(birth_date, "T3", trading_sessions)
    t5_elig = compute_horizon_eligible_date(birth_date, "T5", trading_sessions)
    t10_elig = compute_horizon_eligible_date(birth_date, "T10", trading_sessions)

    outcomes = list_outcomes_for_observation(birth.observation_id, data_dir=data_dir)
    release: Dict[str, Optional[str]] = {"T3": None, "T5": None, "T10": None}
    for o in outcomes:
        if o.evaluation_status == "EVALUATED":
            release[o.horizon] = (o.provenance or {}).get("assessment_trade_date") or o.actual_evaluation_timestamp

    missing_delay = None
    for h, elig in [("T3", t3_elig), ("T5", t5_elig), ("T10", t10_elig)]:
        if assessment_trade_date >= elig and release[h] is None:
            if not horizon_eligible_on_date(h, birth_date, assessment_trade_date):
                continue
            missing_delay = f"{h}:eligible_but_not_released"

    return ForwardClockEntry(
        observation_id=birth.observation_id,
        birth_trade_date=birth_date,
        age_trading_sessions=age,
        t3_eligible_date=t3_elig,
        t5_eligible_date=t5_elig,
        t10_eligible_date=t10_elig,
        t3_release_date=release["T3"],
        t5_release_date=release["T5"],
        t10_release_date=release["T10"],
        missing_data_delay=missing_delay,
    )


def build_forward_clock_ledger(
    observation_ids: List[str],
    *,
    assessment_trade_date: str,
    trading_sessions: List[str],
    data_dir=None,
) -> List[ForwardClockEntry]:
    entries = []
    for oid in observation_ids:
        birth = lookup_birth_record(oid, data_dir=data_dir)
        if birth is None:
            continue
        if birth.cutoff.trade_date > assessment_trade_date:
            continue
        entries.append(
            build_forward_clock_entry(
                birth,
                assessment_trade_date=assessment_trade_date,
                trading_sessions=trading_sessions,
                data_dir=data_dir,
            )
        )
    return entries
