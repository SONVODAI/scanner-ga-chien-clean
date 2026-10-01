"""
Phase 3K.3 — Pre-outcome state snapshot (freeze belief before T3/T5/T10 observable).
"""

from __future__ import annotations

from typing import List, Optional

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.production_calibration_records import PreOutcomeStateSnapshot
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    list_assessments_for_observation,
)
from modules.edge_research.opr_bridge.production_living_observation_records import DailyResearchAssessment
from modules.edge_research.opr_bridge.production_observation_persistence import lookup_birth_record


def find_pre_outcome_assessment(
    observation_id: str,
    *,
    eligible_evaluation_date: str,
    release_trade_date: str,
    data_dir=None,
) -> Optional[DailyResearchAssessment]:
    """
    Latest assessment strictly before outcome became observable.
    CF-CAL4: post-outcome assessment cannot substitute for pre-outcome belief.
    """
    assessments = list_assessments_for_observation(observation_id, data_dir=data_dir)
    if not assessments:
        return None

    cutoff_date = min(eligible_evaluation_date, release_trade_date)
    prior = [a for a in assessments if a.assessment_trade_date < cutoff_date]
    if prior:
        return max(prior, key=lambda a: a.assessment_trade_date)

    # If birth-day assessment exists and is before release, use earliest
    earliest = min(assessments, key=lambda a: a.assessment_trade_date)
    if earliest.assessment_trade_date <= release_trade_date:
        return earliest
    return None


def build_pre_outcome_snapshot(
    observation_id: str,
    horizon: str,
    *,
    eligible_evaluation_date: str,
    release_trade_date: str,
    data_dir=None,
) -> Optional[PreOutcomeStateSnapshot]:
    birth = lookup_birth_record(observation_id, data_dir=data_dir)
    assessment = find_pre_outcome_assessment(
        observation_id,
        eligible_evaluation_date=eligible_evaluation_date,
        release_trade_date=release_trade_date,
        data_dir=data_dir,
    )

    if assessment is None and birth is None:
        return None

    if assessment is None and birth is not None:
        epistemic = birth.final_epistemic_state
        strength = birth.evidence_strength
        lifecycle = "BORN"
        nulls = birth.surviving_nulls
        unresolved = birth.unresolved_uncertainties
        mkt_hash = birth.cutoff.market_context_hash
        age = 0
        assessment_id = None
        assessment_date = birth.cutoff.trade_date
    else:
        assert assessment is not None
        epistemic = assessment.current_epistemic_state
        strength = None
        birth_strength = birth.evidence_strength if birth else None
        strength = birth_strength
        lifecycle = assessment.observation_lifecycle_state
        nulls = tuple(
            str(n.get("null_key", n)) if isinstance(n, dict) else str(n)
            for n in assessment.null_ledger_current
        ) or (birth.surviving_nulls if birth else ())
        unresolved = assessment.unresolved_uncertainties
        mkt_hash = assessment.current_market_context_hash
        age = assessment.observation_age_trading_days
        assessment_id = assessment.assessment_id
        assessment_date = assessment.assessment_trade_date

    payload = {
        "observation_id": observation_id,
        "horizon": horizon,
        "assessment_id": assessment_id,
        "assessment_trade_date": assessment_date,
        "epistemic_state": epistemic,
        "eligible_date": eligible_evaluation_date,
        "release_date": release_trade_date,
    }
    prov_hash = stable_hash(payload)
    snapshot_id = f"preout-{prov_hash[:16]}"

    return PreOutcomeStateSnapshot(
        snapshot_id=snapshot_id,
        observation_id=observation_id,
        horizon=horizon,
        assessment_id=assessment_id,
        assessment_trade_date=assessment_date,
        epistemic_state=epistemic,
        evidence_strength=strength,
        lifecycle_state=lifecycle,
        surviving_nulls=tuple(nulls),
        unresolved_uncertainties=tuple(unresolved),
        market_context_hash=mkt_hash,
        observation_age_trading_days=age,
        voice_assessment_id=assessment_id,
        snapshot_provenance_hash=prov_hash,
    )


def reject_post_outcome_assessment_substitution(
    *,
    pre_assessment_date: str,
    release_trade_date: str,
    eligible_evaluation_date: str,
) -> bool:
    """CF-CAL4 — True if substitution detected (reject)."""
    cutoff = min(eligible_evaluation_date, release_trade_date)
    return pre_assessment_date >= cutoff
