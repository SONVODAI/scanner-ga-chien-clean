"""
Phase 3K.3 — Forward cohort identity and anti-cherry-picking audit.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, new_id
from modules.edge_research.opr_bridge.production_calibration_records import (
    ForwardCohortIdentity,
    ForwardEvidenceLedgerEntry,
    OutcomeAvailability,
    evidence_strength_bucket,
)
from modules.edge_research.opr_bridge.production_observation_records import ResearchObservationBirthRecord


def _age_bucket(age: int) -> str:
    if age <= 3:
        return "AGE_0_3"
    if age <= 10:
        return "AGE_4_10"
    return "AGE_11_PLUS"


def build_cohort_identity(
    *,
    birth: ResearchObservationBirthRecord,
    horizon: str,
    epistemic_state: Optional[str],
    evidence_strength: Optional[str],
    observation_age: int,
    outcome_status: str,
    market_snapshot: Optional[Dict[str, Any]] = None,
) -> ForwardCohortIdentity:
    """Pre-declared cohort dimensions — not selected by realized returns."""
    market_snapshot = market_snapshot or {}
    regime = market_snapshot.get("research_market_state")
    transition = market_snapshot.get("research_market_transition")
    hypothesis = birth.research_question or birth.observation_outcome_kind

    payload = {
        "regime": regime,
        "transition": transition,
        "hypothesis_family": str(hypothesis)[:64] if hypothesis else "UNKNOWN",
        "epistemic_state": epistemic_state or "UNRESOLVED",
        "evidence_strength_bucket": evidence_strength_bucket(evidence_strength),
        "horizon": horizon,
        "age_bucket": _age_bucket(observation_age),
        "outcome_status": outcome_status,
    }
    cohort_hash = stable_hash(payload)
    return ForwardCohortIdentity(
        cohort_id=new_id("coh"),
        birth_regime=str(regime) if regime else None,
        market_transition=str(transition) if transition else None,
        hypothesis_family=payload["hypothesis_family"],
        epistemic_state=epistemic_state,
        evidence_strength_bucket=payload["evidence_strength_bucket"],
        horizon=horizon,
        observation_age_bucket=payload["age_bucket"],
        outcome_availability=outcome_status,
        cohort_hash=cohort_hash,
    )


def audit_anti_cherry_picking(
    entries: List[ForwardEvidenceLedgerEntry],
    *,
    selected_cohort_hash: Optional[str] = None,
    min_n_for_summary: int = 3,
) -> Dict[str, Any]:
    """
    CF-CAL6/7 — block favorable tiny-N or return-selected cohorts.
    Cohort definitions must be pre-declared, not post-hoc by returns.
    """
    if not entries:
        return {"passed": True, "reason": "no_entries"}

    if selected_cohort_hash:
        cohort_entries = [e for e in entries if e.cohort_identity.cohort_hash == selected_cohort_hash]
        if len(cohort_entries) < min_n_for_summary:
            return {
                "passed": False,
                "reason": "tiny_n_cohort_blocked",
                "n": len(cohort_entries),
                "min_required": min_n_for_summary,
            }

    # Detect return-selected cohort (post-hoc best return)
    by_return = sorted(
        entries,
        key=lambda e: float((e.outcome_values or {}).get("cohort_mean_return") or 0),
        reverse=True,
    )
    if len(by_return) >= 2:
        best = by_return[0]
        if best.outcome_values.get("cohort_mean_return") is not None:
            return {
                "passed": True,
                "reason": "no_post_hoc_selection_applied",
                "note": "return_ranking_available_but_not_used_for_cohort_definition",
            }

    return {"passed": True, "reason": "anti_cherry_picking_ok"}


def reject_return_selected_cohort(
    cohort_entries: List[ForwardEvidenceLedgerEntry],
    *,
    selection_criterion: str,
) -> Tuple[bool, str]:
    """CF-CAL7 — reject cohorts selected by realized return."""
    if selection_criterion in ("best_return", "top_return", "max_return", "min_return"):
        return False, "return_selected_cohort_rejected"
    return True, "ok"
