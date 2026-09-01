"""
Phase 3K.1 — Forward T3/T5/T10 outcome evaluator.

Populates ResearchObservationOutcomeRecord when horizons become legally observable.
Outcome evidence does NOT automatically change epistemic state.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.production_observation_records import (
    ForwardEvaluationStatus,
    ForwardHorizon,
    ResearchObservationBirthRecord,
    ResearchObservationOutcomeRecord,
)
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    HORIZON_SESSION_OFFSETS,
    compute_horizon_eligible_date_vn,
)

HORIZON_RETURN_FIELDS = {
    ForwardHorizon.T3.value: "t3_return",
    ForwardHorizon.T5.value: "t5_return",
    ForwardHorizon.T10.value: "t10_return",
}

HORIZON_OFFSETS = HORIZON_SESSION_OFFSETS


def horizon_eligible_on_date(horizon: str, birth_trade_date: str, assessment_trade_date: str) -> bool:
    """Return True iff assessment_trade_date is on or after the canonical VN T3/T5/T10 date."""
    eligible = compute_horizon_eligible_date_vn(birth_trade_date, horizon)
    if not eligible:
        return False
    return str(assessment_trade_date)[:10] >= eligible


def reject_early_outcome(horizon: str, birth_trade_date: str, assessment_trade_date: str) -> bool:
    """Return True if outcome is attempted before legal eligibility (fail closed)."""
    return not horizon_eligible_on_date(horizon, birth_trade_date, assessment_trade_date)


def compute_outcome_identity(
    *,
    observation_id: str,
    horizon: str,
    eligible_evaluation_date: str,
    contract_hash: str,
    realized_hash: str,
) -> str:
    return stable_hash({
        "observation_id": observation_id,
        "horizon": horizon,
        "eligible_evaluation_date": eligible_evaluation_date,
        "contract_hash": contract_hash,
        "realized_hash": realized_hash,
    })


def _cohort_returns(
    panel: pd.DataFrame,
    birth: ResearchObservationBirthRecord,
    horizon: str,
) -> Tuple[Optional[Dict[str, Any]], str]:
    ret_col = HORIZON_RETURN_FIELDS.get(horizon, "")
    if not ret_col or panel.empty:
        return None, ForwardEvaluationStatus.MISSING_DATA.value

    birth_date = birth.cutoff.trade_date
    symbols = birth.cohort_attribution.symbols_at_birth
    sub = panel[
        (panel["trade_date"].astype(str) == str(birth_date))
        & (panel["symbol"].astype(str).isin(symbols) if symbols else True)
    ]
    if sub.empty:
        sub = panel[panel["trade_date"].astype(str) == str(birth_date)]
    if sub.empty or ret_col not in sub.columns:
        return None, ForwardEvaluationStatus.MISSING_DATA.value

    vals = sub[ret_col].dropna()
    if vals.empty:
        return None, ForwardEvaluationStatus.MISSING_DATA.value

    outcomes = {
        "horizon": horizon,
        "return_field": ret_col,
        "cohort_mean_return": float(vals.mean()),
        "cohort_median_return": float(vals.median()),
        "cohort_size": int(len(vals)),
        "positive_fraction": float((vals > 0).mean()),
        "symbols_evaluated": sorted(sub.loc[vals.index, "symbol"].astype(str).unique().tolist())[:50],
    }
    return outcomes, ForwardEvaluationStatus.EVALUATED.value


def interpret_outcome_evidence(
    *,
    birth: ResearchObservationBirthRecord,
    outcome: ResearchObservationOutcomeRecord,
) -> Dict[str, Any]:
    """
    Interpret forward outcome per frozen contract — does NOT auto-upgrade/downgrade epistemic state.
    Returns structured evidence interpretation only.
    """
    realized = outcome.realized_outcomes or {}
    mean_ret = realized.get("cohort_mean_return")
    birth_state = birth.final_epistemic_state or "UNRESOLVED"
    strongest = birth.strongest_evidence or {}
    birth_direction = strongest.get("direction")

    interpretation: Dict[str, Any] = {
        "horizon": outcome.horizon,
        "outcome_record_id": outcome.outcome_record_id,
        "evaluation_status": outcome.evaluation_status,
        "cohort_mean_return": mean_ret,
        "supports_birth_expectation": None,
        "contradicts_birth_expectation": None,
        "suggested_lifecycle_signal": None,
        "automatic_belief_change": False,
        "rationale_keys": [],
    }

    if mean_ret is None or outcome.evaluation_status != ForwardEvaluationStatus.EVALUATED.value:
        interpretation["rationale_keys"].append("outcome:missing_or_incomplete")
        return interpretation

    if birth_direction == "SUPPORTING" and mean_ret > 0:
        interpretation["supports_birth_expectation"] = True
        interpretation["suggested_lifecycle_signal"] = "FORWARD_EVIDENCE_SUPPORTING"
        interpretation["rationale_keys"].append("return:positive_vs_supporting_direction")
    elif birth_direction == "SUPPORTING" and mean_ret < 0:
        interpretation["contradicts_birth_expectation"] = True
        interpretation["suggested_lifecycle_signal"] = "FORWARD_EVIDENCE_CHALLENGING"
        interpretation["rationale_keys"].append("return:negative_vs_supporting_direction")
    elif birth_direction == "CONTRADICTING" and mean_ret < 0:
        interpretation["supports_birth_expectation"] = True
        interpretation["suggested_lifecycle_signal"] = "FORWARD_EVIDENCE_CONSISTENT_WITH_CONTRADICTION"
        interpretation["rationale_keys"].append("return:negative_vs_contradicting_direction")
    else:
        interpretation["rationale_keys"].append("return:ambiguous_relative_to_birth_direction")
        interpretation["suggested_lifecycle_signal"] = "FORWARD_EVIDENCE_AMBIGUOUS"

    interpretation["rationale_keys"].append(f"birth_epistemic:{birth_state}")
    interpretation["automatic_belief_change"] = False
    return interpretation


def evaluate_eligible_outcomes(
    panel: pd.DataFrame,
    birth: ResearchObservationBirthRecord,
    *,
    assessment_trade_date: str,
    existing_outcome_ids: Tuple[str, ...] = (),
) -> Tuple[List[ResearchObservationOutcomeRecord], List[str]]:
    """
    Evaluate forward horizons legally eligible on assessment_trade_date.
    Returns (new_outcome_records, errors).
    """
    records: List[ResearchObservationOutcomeRecord] = []
    errors: List[str] = []
    contract = birth.forward_evaluation_contract
    birth_date = birth.cutoff.trade_date

    for placeholder in birth.forward_horizons:
        horizon = placeholder.horizon
        eligible_date = placeholder.eligible_evaluation_date or ""

        if reject_early_outcome(horizon, birth_date, assessment_trade_date):
            continue

        if placeholder.status == ForwardEvaluationStatus.EVALUATED.value:
            continue

        realized, status = _cohort_returns(panel, birth, horizon)
        realized_hash = stable_hash(realized) if realized else stable_hash({"missing": True})
        identity = compute_outcome_identity(
            observation_id=birth.observation_id,
            horizon=horizon,
            eligible_evaluation_date=eligible_date,
            contract_hash=contract.contract_hash,
            realized_hash=realized_hash,
        )
        outcome_id = f"out-{identity[:16]}"
        if outcome_id in existing_outcome_ids:
            continue

        record = ResearchObservationOutcomeRecord(
            outcome_record_id=outcome_id,
            observation_id=birth.observation_id,
            horizon=horizon,
            eligible_evaluation_date=eligible_date,
            actual_evaluation_timestamp=utc_now_iso(),
            realized_outcomes=realized,
            evaluation_status=status,
            data_identity=stable_hash({"panel_rows": len(panel), "assessment_date": assessment_trade_date}),
            missing_handling="MARK_MISSING_DO_NOT_IMPUTE" if status == ForwardEvaluationStatus.MISSING_DATA.value else None,
            contract_id=contract.contract_id,
            contract_hash=contract.contract_hash,
            provenance={
                "assessment_trade_date": assessment_trade_date,
                "birth_trade_date": birth_date,
                "outcome_identity_hash": identity,
            },
        )
        records.append(record)

    return records, errors


def attempt_early_outcome_evaluation(
    horizon: str,
    birth_trade_date: str,
    assessment_trade_date: str,
) -> Tuple[bool, str]:
    """
    Explicit rejection helper for CF-LIVE4 — T5 before eligible date.
    Returns (allowed, reason).
    """
    if reject_early_outcome(horizon, birth_trade_date, assessment_trade_date):
        return False, f"early_outcome_rejected:{horizon}:eligible_after_bday_offset"
    return True, "eligible"
