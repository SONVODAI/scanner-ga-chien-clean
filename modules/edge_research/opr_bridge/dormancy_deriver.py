"""
Phase 3I.19 — Derive ResearchDormancyRecord from frontier assessment.

Dormancy is evidence-derived — not outcome-driven.
"""

from __future__ import annotations

from typing import Any, List, Set, Tuple

from modules.edge_research.opr_bridge.dormancy_records import (
    DORMANCY_VERSION,
    DEFAULT_FORBIDDEN_TRIGGERS,
    DEFAULT_MATERIAL_OVERLAP_CEILING,
    BlockingReasonType,
    DormancyTrigger,
    ForbiddenReopeningTrigger,
    ResearchActivityState,
    ResearchDormancyRecord,
    RequiredScientificChange,
    ReopeningConditionRecord,
    build_reopening_condition,
)
from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.frontier_records import FrontierDecision, FrontierReassessmentResult, ResearchabilityClass
from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext
from modules.edge_research.opr_bridge.scientific_frontier_reassessor import COHORT_DEPENDENT_STRATEGIES

# Operator → unresolved axis mapping (capability relevance, not preference)
_OPERATOR_AXIS_MAP = {
    "counterexample_period_search": ("counterexample_exposure", "alternative_explanation_exposure"),
    "concentration_decomposition": ("concentration_dominance",),
    "measurement_robustness_check": ("measurement_robustness",),
    "population_subgroup_contrast": ("population_robustness",),
    "regime_separated_contrast": ("temporal_regime_robustness", "regime_context_robustness"),
    "rolling_stability_contrast": ("temporal_regime_robustness", "effect_stability"),
}


def should_enter_dormancy(frontier_decision: str, *, priority_action: str = "") -> bool:
    if frontier_decision in (
        FrontierDecision.NO_HIGH_INFORMATION_ACTION.value,
        FrontierDecision.HOLD_PROVISIONALLY.value,
    ):
        return True
    if priority_action in ("HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"):
        return True
    return False


def _dormancy_trigger(frontier_decision: str, priority_action: str) -> str:
    if frontier_decision == FrontierDecision.HOLD_PROVISIONALLY.value:
        return DormancyTrigger.HOLD_PROVISIONALLY.value
    if priority_action in ("HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"):
        return DormancyTrigger.PRIORITY_HOLD.value
    return DormancyTrigger.NO_HIGH_INFORMATION_ACTION.value


def _independence_limitations(ctx: ActionGenerationContext) -> Tuple[str, ...]:
    limits: List[str] = []
    if ctx.max_cohort_overlap >= 0.9:
        limits.append(f"max_cohort_overlap={ctx.max_cohort_overlap:.4f}")
    if ctx.low_population_independence():
        limits.append("population_independence=LOW")
    for e in ctx.ledger_entries:
        if e.cohort_overlap_ratio >= 0.9:
            limits.append(f"evidence_{e.evidence_id}_overlap={e.cohort_overlap_ratio:.4f}")
    return tuple(limits)


def derive_reopening_conditions(
    ctx: ActionGenerationContext,
    frontier: FrontierReassessmentResult,
) -> Tuple[ReopeningConditionRecord, ...]:
    """Derive structured reopening requirements from unresolved uncertainty + blocking reasons."""
    conditions: List[ReopeningConditionRecord] = []
    seen_axes: Set[str] = set()

    for u in frontier.uncertainty_frontier:
        axis = u.uncertainty_axis
        if axis in seen_axes:
            continue
        seen_axes.add(axis)

        if u.researchability == ResearchabilityClass.COHORT_UNAVAILABLE.value:
            conditions.append(
                build_reopening_condition(
                    target_uncertainty=axis,
                    blocking_reason=BlockingReasonType.COHORT_INDEPENDENCE_DEFICIT.value,
                    required_scientific_change=RequiredScientificChange.MATERIAL_INDEPENDENCE_IMPROVEMENT.value,
                    measurable_criterion={
                        "max_row_overlap_ceiling": DEFAULT_MATERIAL_OVERLAP_CEILING,
                        "relation_to_prior_must_not_be": "subset",
                        "requires_measured_overlap_change": True,
                    },
                    independence_requirement="sample_independence>=MEDIUM",
                    does_not_qualify=(
                        ForbiddenReopeningTrigger.LABEL_RENAME_ONLY.value,
                        ForbiddenReopeningTrigger.ROW_COUNT_ONLY.value,
                        ForbiddenReopeningTrigger.CLOCK_ELAPSED.value,
                    ),
                    provenance=(f"frontier:{u.researchability}", u.researchability_rationale),
                )
            )
        elif u.researchability in (
            ResearchabilityClass.RESEARCHABLE_BUT_REDUNDANT.value,
            ResearchabilityClass.LOW_INFORMATION.value,
        ) or axis in ctx.redundant_axes:
            conditions.append(
                build_reopening_condition(
                    target_uncertainty=axis,
                    blocking_reason=BlockingReasonType.AXIS_SATURATED.value,
                    required_scientific_change=RequiredScientificChange.UNCERTAINTY_RESOLVED.value,
                    measurable_criterion={"additional_same_relationship_evidence": False},
                    independence_requirement="N/A_saturated",
                    does_not_qualify=(
                        ForbiddenReopeningTrigger.ROW_COUNT_ONLY.value,
                        ForbiddenReopeningTrigger.LABEL_RENAME_ONLY.value,
                    ),
                    provenance=(f"frontier:{u.researchability}",),
                )
            )

    # Capability gaps from unavailable actions targeting unresolved axes
    for assessment in frontier.action_assessments:
        if assessment.available:
            continue
        axis = assessment.uncertainty_axis
        strategy = assessment.cohort_strategy
        reason = assessment.availability_reason.lower()
        if axis in ctx.redundant_axes or axis in ctx.covered_axes:
            continue
        if "capability" in reason or "not executable" in reason or "blocked by 3i.17b temporal" in reason:
            if any(c.target_uncertainty == axis and c.blocking_reason == BlockingReasonType.CAPABILITY_GAP.value for c in conditions):
                continue
            conditions.append(
                build_reopening_condition(
                    target_uncertainty=axis,
                    blocking_reason=BlockingReasonType.CAPABILITY_GAP.value,
                    required_scientific_change=RequiredScientificChange.NEW_RELEVANT_OPERATOR.value,
                    measurable_criterion={
                        "operator_must_address_axis": axis,
                        "candidate_strategy": strategy,
                        "must_be_non_redundant": True,
                    },
                    independence_requirement="non_redundant_information_path",
                    does_not_qualify=(ForbiddenReopeningTrigger.LABEL_RENAME_ONLY.value,),
                    provenance=(f"action_blocked:{strategy}", assessment.availability_reason),
                )
            )
        elif strategy in COHORT_DEPENDENT_STRATEGIES and "no_defensible" in reason.lower():
            if not any(c.target_uncertainty == axis and c.blocking_reason == BlockingReasonType.COHORT_INDEPENDENCE_DEFICIT.value for c in conditions):
                conditions.append(
                    build_reopening_condition(
                        target_uncertainty=axis,
                        blocking_reason=BlockingReasonType.COHORT_INDEPENDENCE_DEFICIT.value,
                        required_scientific_change=RequiredScientificChange.MATERIAL_INDEPENDENCE_IMPROVEMENT.value,
                        measurable_criterion={
                            "max_row_overlap_ceiling": DEFAULT_MATERIAL_OVERLAP_CEILING,
                            "requires_measured_overlap_change": True,
                        },
                        independence_requirement="sample_independence>=MEDIUM",
                        does_not_qualify=(
                            ForbiddenReopeningTrigger.LABEL_RENAME_ONLY.value,
                            ForbiddenReopeningTrigger.ROW_COUNT_ONLY.value,
                        ),
                        provenance=(f"cohort_blocked:{strategy}",),
                    )
                )

    # Marginal-information gate at frontier level
    if frontier.frontier_decision == FrontierDecision.NO_HIGH_INFORMATION_ACTION and ctx.major_unresolved:
        peripheral_only = all(
            a.uncertainty_axis not in ctx.major_unresolved
            for a in frontier.action_assessments
            if a.available
        )
        if peripheral_only and str(ctx.priority.marginal_information).lower() == "low":
            conditions.append(
                build_reopening_condition(
                    target_uncertainty="major_unresolved_bundle",
                    blocking_reason=BlockingReasonType.MARGINAL_INFORMATION_GATE.value,
                    required_scientific_change=RequiredScientificChange.MAJOR_UNRESOLVED_ADDRESSABLE.value,
                    measurable_criterion={
                        "must_address_major_unresolved": sorted(ctx.major_unresolved),
                        "marginal_information_must_exceed": "low",
                    },
                    independence_requirement="addresses_major_vulnerability",
                    does_not_qualify=(
                        ForbiddenReopeningTrigger.ROW_COUNT_ONLY.value,
                        ForbiddenReopeningTrigger.OUTCOME_PROFITABILITY.value,
                    ),
                    provenance=("frontier:marginal_information_gate", frontier.reason),
                )
            )

    return tuple(conditions)


def derive_dormancy_record(
    ctx: ActionGenerationContext,
    frontier: FrontierReassessmentResult,
    *,
    created_at: str | None = None,
) -> ResearchDormancyRecord | None:
    """Create dormancy record when frontier indicates research budget should stop."""
    decision = frontier.frontier_decision.value
    if not should_enter_dormancy(decision, priority_action=ctx.priority_action):
        return None

    ts = created_at or ctx.synthesis.created_at or utc_now_iso()
    blocked = tuple(
        u.uncertainty_axis
        for u in frontier.uncertainty_frontier
        if u.researchability
        in (ResearchabilityClass.COHORT_UNAVAILABLE.value, ResearchabilityClass.NOT_CURRENTLY_EXECUTABLE.value)
    )
    reopening = derive_reopening_conditions(ctx, frontier)

    body = {
        "version": DORMANCY_VERSION,
        "proposition_id": ctx.proposition_id,
        "proposition_hash": ctx.proposition_hash,
        "synthesis_hash": ctx.synthesis.synthesis_hash,
        "frontier_assessment_hash": frontier.record_hash,
        "epistemic_state": ctx.synthesis.synthesized_epistemic_state,
        "trigger": _dormancy_trigger(decision, ctx.priority_action),
        "unresolved": sorted(ctx.unresolved_axes),
        "reopening_count": len(reopening),
    }
    did = new_id("dorm")

    return ResearchDormancyRecord(
        dormancy_id=did,
        record_version=DORMANCY_VERSION,
        proposition_id=ctx.proposition_id,
        proposition_hash=ctx.proposition_hash,
        synthesis_hash=ctx.synthesis.synthesis_hash,
        frontier_assessment_hash=frontier.record_hash,
        epistemic_state_at_dormancy=ctx.synthesis.synthesized_epistemic_state,
        research_activity_state=ResearchActivityState.DORMANT.value,
        dormancy_trigger=_dormancy_trigger(decision, ctx.priority_action),
        unresolved_uncertainties=ctx.unresolved_axes,
        blocked_axes=blocked,
        redundant_axes=tuple(sorted(ctx.redundant_axes)),
        dormancy_reason=frontier.reason,
        evidence_coverage=tuple(sorted(ctx.covered_axes)),
        independence_limitations=_independence_limitations(ctx),
        reopening_conditions=reopening,
        forbidden_reopening_triggers=DEFAULT_FORBIDDEN_TRIGGERS,
        created_at=ts,
        record_hash=stable_hash(body),
    )


def operator_relevant_to_unresolved(operator_id: str, unresolved: Set[str]) -> bool:
    axes = _OPERATOR_AXIS_MAP.get(operator_id, ())
    return bool(set(axes) & unresolved)
