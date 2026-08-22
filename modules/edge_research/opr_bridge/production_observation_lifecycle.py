"""
Phase 3K.1 — Observation lifecycle state derivation (presentation/scientific layer).

Does NOT mutate BirthRecord or frozen 3I/3J epistemic semantics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.production_forward_outcome_evaluator import interpret_outcome_evidence
from modules.edge_research.opr_bridge.production_living_observation_records import (
    ChangeKind,
    ObservationLifecycleState,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    ObservationOutcomeKind,
    ResearchObservationBirthRecord,
    ResearchObservationOutcomeRecord,
)


def derive_lifecycle_state(
    *,
    birth: ResearchObservationBirthRecord,
    current_epistemic_state: Optional[str],
    outcomes: Tuple[ResearchObservationOutcomeRecord, ...],
    observation_age_trading_days: int,
    has_new_forward_evidence: bool,
    epistemic_changed: bool,
) -> str:
    """Derive lifecycle state from structured evidence — no hardcoded expiry tuning."""
    birth_kind = birth.observation_outcome_kind
    if birth_kind in (ObservationOutcomeKind.NO_DISCOVERY.value, ObservationOutcomeKind.SILENCE.value):
        return ObservationLifecycleState.SILENCE.value

    if current_epistemic_state == "REJECTED":
        return ObservationLifecycleState.REJECTED.value

    if current_epistemic_state == "RESOLVED":
        return ObservationLifecycleState.RESOLVED.value

    pending = [
        h for h in birth.forward_horizons
        if h.status in ("PENDING_FUTURE", "ELIGIBLE") and h.realized_outcome is None
    ]
    evaluated_outcomes = [o for o in outcomes if o.evaluation_status == "EVALUATED"]

    if epistemic_changed and current_epistemic_state == "STRENGTHENED":
        return ObservationLifecycleState.STRENGTHENED.value
    if epistemic_changed and current_epistemic_state == "WEAKENED":
        return ObservationLifecycleState.WEAKENED.value
    if epistemic_changed and current_epistemic_state == "CHALLENGED":
        return ObservationLifecycleState.CHALLENGED.value

    if has_new_forward_evidence and evaluated_outcomes:
        interpretations = [interpret_outcome_evidence(birth=birth, outcome=o) for o in evaluated_outcomes]
        if any(i.get("contradicts_birth_expectation") for i in interpretations):
            return ObservationLifecycleState.CHALLENGED.value
        if any(i.get("supports_birth_expectation") for i in interpretations):
            return ObservationLifecycleState.STRENGTHENED.value

    if observation_age_trading_days == 0:
        return ObservationLifecycleState.BORN.value

    if pending:
        return ObservationLifecycleState.ACTIVE_PENDING.value

    if current_epistemic_state in ("SUPPORTED", "UNRESOLVED", "INSUFFICIENT_EVIDENCE"):
        return ObservationLifecycleState.UNCHANGED.value

    return ObservationLifecycleState.ACTIVE_PENDING.value


def compute_observation_age_trading_days(
    birth_trade_date: str,
    assessment_trade_date: str,
    trading_dates: List[str],
) -> int:
    """Count trading days from birth (inclusive) to assessment (inclusive)."""
    ordered = sorted(set(trading_dates))
    if birth_trade_date not in ordered or assessment_trade_date not in ordered:
        return 0
    bi = ordered.index(birth_trade_date)
    ai = ordered.index(assessment_trade_date)
    return max(0, ai - bi)


def derive_epistemic_update(
    *,
    birth: ResearchObservationBirthRecord,
    previous_epistemic: Optional[str],
    new_outcome_interpretations: List[Dict[str, Any]],
    new_evidence_keys: Tuple[str, ...],
) -> Tuple[Optional[str], ChangeKind, Tuple[str, ...], bool]:
    """
    Derive epistemic state update from new evidence.
    Returns (current_state, change_kind, rationale_keys, belief_changed).
    Belief change requires relevant new evidence — no fake daily change.
    """
    base = previous_epistemic or birth.final_epistemic_state or "UNRESOLVED"
    rationale: List[str] = []
    belief_changed = False
    current = base

    if not new_outcome_interpretations and not new_evidence_keys:
        return base, ChangeKind.UNCHANGED, ("no_relevant_new_evidence",), False

    for interp in new_outcome_interpretations:
        if interp.get("automatic_belief_change"):
            belief_changed = True
            rationale.extend(interp.get("rationale_keys") or [])
        elif interp.get("contradicts_birth_expectation"):
            rationale.append(f"forward_contradiction:{interp.get('horizon')}")
        elif interp.get("supports_birth_expectation"):
            rationale.append(f"forward_support:{interp.get('horizon')}")

    if new_evidence_keys and not belief_changed:
        rationale.extend(list(new_evidence_keys))

    change_kind = ChangeKind.EVIDENCE_CHANGED if new_outcome_interpretations else ChangeKind.UNCHANGED
    if belief_changed:
        change_kind = ChangeKind.BELIEF_CHANGED

    return current, change_kind, tuple(rationale), belief_changed


def detect_stale_copy_risk(
    *,
    previous_why: Optional[str],
    current_why: Optional[str],
    market_delta_keys: Tuple[str, ...],
    belief_unchanged: bool,
) -> bool:
    """
    Detect stale presentation: same explanation despite changed market context.
    """
    if not belief_unchanged:
        return False
    market_changed = any(k for k in market_delta_keys if k != "market:unchanged")
    if not market_changed:
        return False
    if previous_why and current_why and previous_why.strip() == current_why.strip():
        return True
    return False


def reject_artificial_belief_change(
    *,
    previous_epistemic: Optional[str],
    proposed_epistemic: Optional[str],
    new_evidence_keys: Tuple[str, ...],
    new_outcome_interpretations: List[Dict[str, Any]],
) -> Tuple[bool, str]:
    """
    CF-LIVE10 — reject belief change without relevant evidence.
    Returns (allowed, reason).
    """
    if previous_epistemic == proposed_epistemic:
        return True, "unchanged"
    has_evidence = bool(new_evidence_keys) or any(
        i.get("supports_birth_expectation") or i.get("contradicts_birth_expectation")
        for i in new_outcome_interpretations
    )
    if not has_evidence:
        return False, "artificial_belief_change_rejected:no_relevant_evidence"
    return True, "evidence_supported_change"
