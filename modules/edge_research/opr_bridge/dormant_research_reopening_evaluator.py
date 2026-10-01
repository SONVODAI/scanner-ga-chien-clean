"""
Phase 3I.19 — DormantResearchReopeningEvaluator.

Deterministic reopening assessment from research opportunity structure only.
No outcome inspection. No clock-based reopening.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.edge_research.opr_bridge.dormancy_deriver import operator_relevant_to_unresolved
from modules.edge_research.opr_bridge.dormancy_records import (
    BlockingReasonType,
    ForbiddenReopeningTrigger,
    ReopeningEvaluationOutcome,
    ReopeningEvaluationResult,
    ResearchDormancyRecord,
    ResearchMemoryLedger,
    DEFAULT_MATERIAL_OVERLAP_CEILING,
)
from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash


@dataclass
class CurrentResearchSnapshot:
    """Pre-result state for reopening evaluation — no ToolResult."""

    proposition_id: str
    proposition_hash: str
    proposition_record: Dict[str, Any]
    epistemic_state: str
    unresolved_uncertainties: Set[str]
    covered_axes: Set[str]
    redundant_axes: Set[str]
    max_cohort_overlap: float
    available_operators: Set[str]
    previously_blocked_operators: Set[str] = field(default_factory=set)
    ledger_evidence_ids: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class ResearchOpportunityDescriptor:
    """
    Structured description of a potential reopening trigger.
    Used in benchmarks — NOT future market outcomes.
    """

    # Evidence relationship change (pre-result measurable)
    new_evidence_overlap: Optional[float] = None
    overlap_relation_to_prior: str = "unknown"
    additional_row_count: int = 0
    context_values_renamed: bool = False
    identical_evidence_added: bool = False

    # Capability change
    newly_available_operators: Set[str] = field(default_factory=set)
    restored_executability_for: Set[str] = field(default_factory=set)

    # Proposition continuity
    proposition_hash_changed: bool = False
    feature_changed: bool = False
    outcome_changed: bool = False
    horizon_changed: bool = False
    population_claim_changed: bool = False

    # Forbidden temptation signals (must reject)
    outcome_profitability_signal: bool = False
    future_return_magnitude_signal: bool = False
    zone_c_match: bool = False
    human_review_request: bool = False
    subgroup_outcome_mining: bool = False
    known_hidden_edge: bool = False
    clock_elapsed_days: int = 0

    # Resolution
    resolved_uncertainties: Set[str] = field(default_factory=set)

    # Anti-thrashing fingerprint source
    trigger_source: str = ""


def _forbidden_triggers_present(opp: ResearchOpportunityDescriptor) -> List[str]:
    rejected: List[str] = []
    if opp.outcome_profitability_signal:
        rejected.append(ForbiddenReopeningTrigger.OUTCOME_PROFITABILITY.value)
    if opp.future_return_magnitude_signal:
        rejected.append(ForbiddenReopeningTrigger.FUTURE_RETURN_MAGNITUDE.value)
    if opp.zone_c_match:
        rejected.append(ForbiddenReopeningTrigger.ZONE_C_MATCH.value)
    if opp.human_review_request:
        rejected.append(ForbiddenReopeningTrigger.HUMAN_REVIEW_REQUEST.value)
    if opp.subgroup_outcome_mining:
        rejected.append(ForbiddenReopeningTrigger.SUBGROUP_OUTCOME_MINING.value)
    if opp.known_hidden_edge:
        rejected.append(ForbiddenReopeningTrigger.KNOWN_HIDDEN_EDGE.value)
    if opp.clock_elapsed_days > 0 and not _material_scientific_change(opp):
        rejected.append(ForbiddenReopeningTrigger.CLOCK_ELAPSED.value)
    if opp.context_values_renamed and not _material_scientific_change(opp):
        rejected.append(ForbiddenReopeningTrigger.LABEL_RENAME_ONLY.value)
    if opp.additional_row_count > 0 and opp.new_evidence_overlap is None and not opp.newly_available_operators:
        if opp.additional_row_count > 0 and (opp.new_evidence_overlap is None or opp.new_evidence_overlap >= 0.95):
            rejected.append(ForbiddenReopeningTrigger.ROW_COUNT_ONLY.value)
    return rejected


def _material_scientific_change(opp: ResearchOpportunityDescriptor) -> bool:
    if opp.new_evidence_overlap is not None and opp.new_evidence_overlap < DEFAULT_MATERIAL_OVERLAP_CEILING:
        return True
    if opp.newly_available_operators:
        return True
    if opp.restored_executability_for:
        return True
    if opp.resolved_uncertainties:
        return True
    return False


def _proposition_continuity_violated(snapshot: CurrentResearchSnapshot, opp: ResearchOpportunityDescriptor) -> bool:
    if opp.proposition_hash_changed:
        return True
    if opp.feature_changed or opp.outcome_changed or opp.horizon_changed or opp.population_claim_changed:
        return True
    rec = snapshot.proposition_record
    if opp.feature_changed:
        return True
    _ = rec  # explicit continuity check uses flags from opportunity descriptor
    return False


def _evaluate_condition(
    condition,
    snapshot: CurrentResearchSnapshot,
    opp: ResearchOpportunityDescriptor,
) -> Tuple[bool, str]:
    axis = condition.target_uncertainty
    criterion = condition.measurable_criterion

    # Resolved uncertainty — condition disappears (does not reopen)
    if axis in opp.resolved_uncertainties or axis not in snapshot.unresolved_uncertainties:
        if condition.blocking_reason == BlockingReasonType.AXIS_SATURATED.value:
            return False, f"Axis {axis} no longer unresolved — saturated condition inactive"
        if axis not in snapshot.unresolved_uncertainties and axis != "major_unresolved_bundle":
            return False, f"Axis {axis} resolved — reopening condition withdrawn"

    if condition.blocking_reason == BlockingReasonType.AXIS_SATURATED.value:
        if opp.identical_evidence_added or (opp.additional_row_count > 0 and not _material_scientific_change(opp)):
            return False, "Saturated axis — additional same-relationship evidence does not qualify"
        return False, "Axis saturated — no reopening via redundant evidence"

    if condition.blocking_reason == BlockingReasonType.COHORT_INDEPENDENCE_DEFICIT.value:
        if opp.new_evidence_overlap is None:
            return False, "No measured independence change presented"
        ceiling = criterion.get("max_row_overlap_ceiling", DEFAULT_MATERIAL_OVERLAP_CEILING)
        if opp.new_evidence_overlap >= ceiling:
            return False, f"Overlap {opp.new_evidence_overlap} still above ceiling {ceiling}"
        if criterion.get("relation_to_prior_must_not_be") == "subset" and opp.overlap_relation_to_prior == "subset":
            return False, "Candidate remains subset of prior evidence"
        if opp.context_values_renamed and opp.new_evidence_overlap >= ceiling:
            return False, "Label rename without independence improvement"
        return True, f"Material independence improvement: overlap={opp.new_evidence_overlap}"

    if condition.blocking_reason == BlockingReasonType.CAPABILITY_GAP.value:
        target_axis = criterion.get("operator_must_address_axis", axis)
        new_ops = opp.newly_available_operators | opp.restored_executability_for
        if not new_ops:
            return False, "No new capability presented"
        relevant = [op for op in new_ops if operator_relevant_to_unresolved(op, {target_axis})]
        if not relevant:
            return False, f"New operators not relevant to {target_axis}"
        return True, f"Relevant capability added: {relevant}"

    if condition.blocking_reason == BlockingReasonType.MARGINAL_INFORMATION_GATE.value:
        major = set(criterion.get("must_address_major_unresolved", []))
        still_unresolved = major & snapshot.unresolved_uncertainties
        if not still_unresolved:
            return False, "Major unresolved bundle no longer applies"
        if opp.new_evidence_overlap is not None and opp.new_evidence_overlap < DEFAULT_MATERIAL_OVERLAP_CEILING:
            return True, "Major vulnerability now addressable via independence improvement"
        new_ops = opp.newly_available_operators | opp.restored_executability_for
        for op in new_ops:
            if operator_relevant_to_unresolved(op, still_unresolved):
                return True, f"Major vulnerability addressable via {op}"
        return False, "No path to address major unresolved vulnerabilities"

    if condition.blocking_reason == BlockingReasonType.EXECUTABILITY_BLOCKED.value:
        if opp.restored_executability_for:
            return True, f"Executability restored for {opp.restored_executability_for}"
        return False, "Executability still blocked"

    return False, f"Unhandled blocking reason: {condition.blocking_reason}"


def _trigger_fingerprint(dormancy: ResearchDormancyRecord, opp: ResearchOpportunityDescriptor) -> str:
    payload = {
        "dormancy_hash": dormancy.record_hash,
        "overlap": opp.new_evidence_overlap,
        "operators": sorted(opp.newly_available_operators),
        "restored": sorted(opp.restored_executability_for),
        "resolved": sorted(opp.resolved_uncertainties),
        "source": opp.trigger_source,
    }
    return stable_hash(payload)


class DormantResearchReopeningEvaluator:
    """Evaluate whether a dormant proposition should reopen research."""

    def evaluate(
        self,
        dormancy: ResearchDormancyRecord,
        snapshot: CurrentResearchSnapshot,
        opportunity: ResearchOpportunityDescriptor,
        *,
        memory: Optional[ResearchMemoryLedger] = None,
    ) -> ReopeningEvaluationResult:
        fingerprint = _trigger_fingerprint(dormancy, opportunity)

        # Anti-thrashing: duplicate equivalent trigger
        if memory and fingerprint in memory.seen_trigger_fingerprints:
            return self._result(
                ReopeningEvaluationOutcome.REMAIN_DORMANT,
                "Duplicate reopening trigger — anti-thrashing dedup",
                fingerprint=fingerprint,
            )

        rejected = _forbidden_triggers_present(opportunity)
        if rejected:
            return self._result(
                ReopeningEvaluationOutcome.REMAIN_DORMANT,
                f"Forbidden reopening trigger(s): {', '.join(rejected)}",
                rejected_triggers=tuple(rejected),
                fingerprint=fingerprint,
            )

        if _proposition_continuity_violated(snapshot, opportunity):
            return self._result(
                ReopeningEvaluationOutcome.NEW_PROPOSITION_REQUIRED,
                "Future opportunity changes proposition semantics — not a reopen",
                fingerprint=fingerprint,
            )

        if snapshot.epistemic_state in ("FALSIFIED", "ABANDONED"):
            return self._result(
                ReopeningEvaluationOutcome.REMAIN_DORMANT,
                f"Epistemic state {snapshot.epistemic_state} — dormancy superseded by belief update",
                fingerprint=fingerprint,
            )

        if opportunity.identical_evidence_added:
            return self._result(
                ReopeningEvaluationOutcome.REMAIN_DORMANT,
                "Identical evidence added — no scientific opportunity change",
                fingerprint=fingerprint,
            )

        if (
            opportunity.additional_row_count > 0
            and opportunity.new_evidence_overlap is not None
            and opportunity.new_evidence_overlap >= 0.95
            and not opportunity.newly_available_operators
        ):
            return self._result(
                ReopeningEvaluationOutcome.REMAIN_DORMANT,
                "Additional rows with same overlap — correlated data does not reopen",
                fingerprint=fingerprint,
            )

        satisfied: List[str] = []
        rationales: List[str] = []
        active_conditions = [
            c
            for c in dormancy.reopening_conditions
            if c.blocking_reason != BlockingReasonType.AXIS_SATURATED.value
            or c.target_uncertainty in snapshot.unresolved_uncertainties
        ]

        for condition in active_conditions:
            ok, reason = _evaluate_condition(condition, snapshot, opportunity)
            if ok:
                satisfied.append(condition.condition_id)
                rationales.append(reason)

        if satisfied:
            return self._result(
                ReopeningEvaluationOutcome.REOPEN_RESEARCH,
                "; ".join(rationales),
                satisfied_conditions=tuple(satisfied),
                fingerprint=fingerprint,
            )

        if not dormancy.reopening_conditions:
            return self._result(
                ReopeningEvaluationOutcome.INSUFFICIENT_EVIDENCE,
                "No reopening conditions recorded — insufficient structure to reopen",
                fingerprint=fingerprint,
            )

        return self._result(
            ReopeningEvaluationOutcome.REMAIN_DORMANT,
            "No reopening condition satisfied by current opportunity structure",
            fingerprint=fingerprint,
        )

    def _result(
        self,
        outcome: ReopeningEvaluationOutcome,
        rationale: str,
        *,
        satisfied_conditions: Tuple[str, ...] = (),
        rejected_triggers: Tuple[str, ...] = (),
        fingerprint: str = "",
    ) -> ReopeningEvaluationResult:
        body = {
            "outcome": outcome.value,
            "rationale": rationale,
            "satisfied": list(satisfied_conditions),
            "rejected": list(rejected_triggers),
            "fingerprint": fingerprint,
        }
        return ReopeningEvaluationResult(
            outcome=outcome,
            rationale=rationale,
            satisfied_conditions=satisfied_conditions,
            rejected_triggers=rejected_triggers,
            trigger_fingerprint=fingerprint,
            record_hash=stable_hash(body),
        )
