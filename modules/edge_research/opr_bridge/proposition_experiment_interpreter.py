"""
Phase 3I.7 — PropositionExperimentInterpreter.

Deterministic, narrow interpreter: compares ToolResult + quintile metrics
against frozen pre-result interpretation contract.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from modules.edge_research.opr_bridge.interpretation_contract import build_interpretation_contract
from modules.edge_research.opr_bridge.lifecycle_records import (
    EpistemicUpdateRecord,
    EvidenceClass,
    InterpretationContract,
    InterpretationResult,
    LIFECYCLE_VERSION,
    NextResearchAction,
    QuintileMetrics,
    ResearchDecisionRecord,
    new_id,
    stable_hash,
    utc_now_iso,
)
from modules.edge_research.research_tools import ToolResult, ToolStatus


def _direction_matches(contract: InterpretationContract, qm: QuintileMetrics) -> bool:
    if contract.contrast_direction == "positive":
        return qm.high_quintile_mean > qm.low_quintile_mean
    if contract.contrast_direction == "negative":
        return qm.low_quintile_mean > qm.high_quintile_mean
    return abs(qm.low_high_delta) < 1e-9


def _direction_violation(contract: InterpretationContract, qm: QuintileMetrics) -> bool:
    if contract.contrast_direction == "positive":
        return qm.high_quintile_mean <= qm.low_quintile_mean
    if contract.contrast_direction == "negative":
        return qm.low_quintile_mean <= qm.high_quintile_mean
    return False


def validate_evidence(
    contract: InterpretationContract,
    tool_result: ToolResult,
    quintile_metrics: QuintileMetrics,
    *,
    expected_cutoff: str,
) -> tuple[bool, tuple[str, ...]]:
    failures = []
    if tool_result.status != ToolStatus.OK:
        failures.append(f"tool_status:{tool_result.status.value}")
    if tool_result.data_cutoff_date != expected_cutoff:
        failures.append(f"cutoff_mismatch:{tool_result.data_cutoff_date}!={expected_cutoff}")
    if quintile_metrics.sample_size < contract.min_sample:
        failures.append(f"sample_size:{quintile_metrics.sample_size}<{contract.min_sample}")
    if len(quintile_metrics.quintile_means) < 2:
        failures.append("missing_quintile_metrics")
    return len(failures) == 0, tuple(failures)


def interpret_experiment_evidence(
    contract: InterpretationContract,
    tool_result: ToolResult,
    quintile_metrics: QuintileMetrics,
    *,
    expected_cutoff: str,
) -> InterpretationResult:
    """
    Classify evidence against frozen contract. Does not mutate proposition.
    """
    valid, failures = validate_evidence(
        contract, tool_result, quintile_metrics, expected_cutoff=expected_cutoff
    )
    outcome_spread = tool_result.metrics.get("outcome_spread")
    if outcome_spread is None:
        outcome_spread = tool_result.metrics.get("median_spread")
    if outcome_spread is None:
        outcome_spread = quintile_metrics.quintile_mean_spread

    metrics_used = {
        "quintile_means": list(quintile_metrics.quintile_means),
        "low_quintile_mean": quintile_metrics.low_quintile_mean,
        "high_quintile_mean": quintile_metrics.high_quintile_mean,
        "quintile_mean_spread": quintile_metrics.quintile_mean_spread,
        "low_high_delta": quintile_metrics.low_high_delta,
        "outcome_spread": outcome_spread,
        "tool_status": tool_result.status.value,
        "sample_size": quintile_metrics.sample_size,
        "contrast_direction": contract.contrast_direction,
    }

    if not valid:
        return InterpretationResult(
            evidence_class=EvidenceClass.INVALID,
            metrics_used=metrics_used,
            condition_matched=contract.invalid_rule,
            validity_passed=False,
            validity_failures=failures,
        )

    direction_ok = _direction_matches(contract, quintile_metrics)
    direction_bad = _direction_violation(contract, quintile_metrics)

    # Contradictory: quintile direction vs outcome_spread sign conflict
    if direction_ok and outcome_spread is not None:
        spread_supports = outcome_spread > contract.spread_disconfirm_ceiling
        if contract.contrast_direction == "positive" and quintile_metrics.low_high_delta > 0 and outcome_spread <= contract.spread_disconfirm_ceiling:
            return InterpretationResult(
                evidence_class=EvidenceClass.CONTRADICTORY,
                metrics_used=metrics_used,
                condition_matched=contract.contradictory_rule,
                validity_passed=True,
            )
        if contract.contrast_direction == "negative" and quintile_metrics.low_high_delta < 0 and spread_supports:
            return InterpretationResult(
                evidence_class=EvidenceClass.CONTRADICTORY,
                metrics_used=metrics_used,
                condition_matched=contract.contradictory_rule,
                validity_passed=True,
            )

    # Strong falsification
    if direction_bad and quintile_metrics.quintile_mean_spread >= contract.spread_support_floor:
        return InterpretationResult(
            evidence_class=EvidenceClass.DISCONFIRMING,
            metrics_used={**metrics_used, "falsify_strength": "STRONG"},
            condition_matched=contract.falsify_strong_rule,
            validity_passed=True,
        )

    # Disconfirming (operational test from birth spec)
    if (
        direction_bad
        or (outcome_spread is not None and outcome_spread <= contract.spread_disconfirm_ceiling)
    ):
        return InterpretationResult(
            evidence_class=EvidenceClass.DISCONFIRMING,
            metrics_used={**metrics_used, "falsify_strength": "WEAK"},
            condition_matched=contract.disconfirming_rule,
            validity_passed=True,
        )

    # Supporting
    if direction_ok and quintile_metrics.quintile_mean_spread >= contract.spread_support_floor:
        return InterpretationResult(
            evidence_class=EvidenceClass.SUPPORTING,
            metrics_used=metrics_used,
            condition_matched=contract.supporting_rule,
            validity_passed=True,
        )

    # Non-informative
    return InterpretationResult(
        evidence_class=EvidenceClass.NON_INFORMATIVE,
        metrics_used=metrics_used,
        condition_matched=contract.non_informative_rule,
        validity_passed=True,
    )


def apply_epistemic_transition(
    contract: InterpretationContract,
    interpretation: InterpretationResult,
    prior_state: str,
) -> tuple[str, str]:
    """Map evidence class to resulting epistemic state using frozen transition_mapping."""
    ec = interpretation.evidence_class
    if ec == EvidenceClass.DISCONFIRMING:
        strength = interpretation.metrics_used.get("falsify_strength", "WEAK")
        key = "DISCONFIRMING_STRONG" if strength == "STRONG" else "DISCONFIRMING"
    else:
        key = ec.value

    mapping = contract.transition_mapping
    if key not in mapping and ec.value in mapping:
        key = ec.value

    result = mapping.get(key, "UNCHANGED")
    if result == "UNCHANGED":
        return prior_state, key
    return result, key


def decide_next_action(
    contract: InterpretationContract,
    interpretation: InterpretationResult,
    transition_key: str,
) -> ResearchDecisionRecord:
    """Evidence-causal next action from frozen decision_mapping."""
    ec = interpretation.evidence_class
    if ec == EvidenceClass.DISCONFIRMING:
        map_key = "DISCONFIRMING_STRONG" if interpretation.metrics_used.get("falsify_strength") == "STRONG" else "DISCONFIRMING"
    else:
        map_key = ec.value

    chosen = contract.decision_mapping.get(map_key, "HOLD_UNRESOLVED")

    candidates = [
        {"action_code": NextResearchAction.SEEK_FALSIFICATION.value, "scientific_justification": "Active disconfirm test of pre-registered spec"},
        {"action_code": NextResearchAction.SEEK_REPLICATION.value, "scientific_justification": "Independent replication of partition contrast"},
        {"action_code": NextResearchAction.HOLD_UNRESOLVED.value, "scientific_justification": "Insufficient information to change research course"},
        {"action_code": NextResearchAction.ABANDON.value, "scientific_justification": "Pre-registered falsification threshold crossed"},
    ]

    rejected = [c for c in candidates if c["action_code"] != chosen]

    if ec == EvidenceClass.SUPPORTING:
        reason = (
            f"Evidence class SUPPORTING ({interpretation.condition_matched}): "
            f"direction matches pre-registered expectation; "
            f"seek falsification before further confirmation (falsification-first)."
        )
    elif map_key == "DISCONFIRMING_STRONG":
        reason = (
            f"Strong disconfirmation ({interpretation.condition_matched}): "
            f"{contract.abandon_requires}"
        )
    elif ec == EvidenceClass.DISCONFIRMING:
        reason = f"Weak disconfirmation ({interpretation.condition_matched}): seek independent replication."
    elif ec == EvidenceClass.CONTRADICTORY:
        reason = f"Contradictory evidence ({interpretation.condition_matched}): prioritize falsification."
    elif ec == EvidenceClass.NON_INFORMATIVE:
        reason = f"Non-informative experiment ({interpretation.condition_matched}): hold unresolved."
    elif ec == EvidenceClass.INVALID:
        reason = f"Invalid evidence ({interpretation.validity_failures}): no belief change."
    else:
        reason = f"Evidence class {ec.value}: {interpretation.condition_matched}"

    return chosen, reason, rejected


def build_epistemic_update(
    prop: Dict[str, Any],
    contract: InterpretationContract,
    interpretation: InterpretationResult,
    *,
    experiment_ref: str,
    tool_result_hash: str,
    prior_state: str,
    resulting_state: str,
) -> EpistemicUpdateRecord:
    update_id = new_id("epu")
    created = utc_now_iso()
    body = {
        "update_id": update_id,
        "proposition_id": prop["proposition_id"],
        "prior_epistemic_state": prior_state,
        "resulting_epistemic_state": resulting_state,
        "evidence_class": interpretation.evidence_class.value,
        "experiment_ref": experiment_ref,
        "tool_result_hash": tool_result_hash,
        "metrics_used": interpretation.metrics_used,
        "condition_matched": interpretation.condition_matched,
        "created_at": created,
        "lifecycle_version": LIFECYCLE_VERSION,
    }
    return EpistemicUpdateRecord(
        update_id=update_id,
        proposition_id=prop["proposition_id"],
        prior_epistemic_state=prior_state,
        resulting_epistemic_state=resulting_state,
        evidence_class=interpretation.evidence_class.value,
        experiment_ref=experiment_ref,
        tool_result_hash=tool_result_hash,
        metrics_used=interpretation.metrics_used,
        condition_matched=interpretation.condition_matched,
        unresolved_uncertainty=prop.get("scientific_question", ""),
        created_at=created,
        lifecycle_version=LIFECYCLE_VERSION,
        record_hash=stable_hash(body),
    )


def build_research_decision(
    prop: Dict[str, Any],
    contract: InterpretationContract,
    interpretation: InterpretationResult,
    update: EpistemicUpdateRecord,
    *,
    chosen_action: str,
    reason: str,
    rejected: list,
) -> ResearchDecisionRecord:
    decision_id = new_id("dec")
    created = utc_now_iso()
    candidates = [
        {"action_code": NextResearchAction.SEEK_FALSIFICATION.value, "scientific_justification": "Falsification-first"},
        {"action_code": NextResearchAction.SEEK_REPLICATION.value, "scientific_justification": "Replication"},
        {"action_code": NextResearchAction.HOLD_UNRESOLVED.value, "scientific_justification": "Hold"},
        {"action_code": NextResearchAction.ABANDON.value, "scientific_justification": "Abandon"},
    ]
    body = {
        "decision_id": decision_id,
        "proposition_id": prop["proposition_id"],
        "epistemic_update_id": update.update_id,
        "chosen_next_action": chosen_action,
        "reason": reason,
        "created_at": created,
    }
    return ResearchDecisionRecord(
        decision_id=decision_id,
        proposition_id=prop["proposition_id"],
        epistemic_update_id=update.update_id,
        prior_epistemic_state=update.prior_epistemic_state,
        resulting_epistemic_state=update.resulting_epistemic_state,
        evidence_considered=[
            {
                "experiment_ref": update.experiment_ref,
                "evidence_class": update.evidence_class,
                "metrics_used": update.metrics_used,
                "condition_matched": update.condition_matched,
            }
        ],
        unresolved_uncertainty=prop.get("scientific_question", ""),
        candidate_next_actions=candidates,
        chosen_next_action=chosen_action,
        reason=reason,
        rejected_alternatives=rejected,
        created_at=created,
        lifecycle_version=LIFECYCLE_VERSION,
        record_hash=stable_hash(body),
    )
