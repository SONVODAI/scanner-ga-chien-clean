"""
Phase 3I.18 — ScientificFrontierReassessor.

Reassesses the non-cohort scientific frontier after cohort-binding constraints.
Consumes 3I.17b NO_DEFENSIBLE_COHORT as authoritative — does not retry cohorts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from modules.edge_research.opr_bridge.cohort_binding_records import CohortSelectionDisposition
from modules.edge_research.opr_bridge.evidence_derived_cohort_binder import EvidenceDerivedCohortBinder
from modules.edge_research.opr_bridge.frontier_records import (
    FRONTIER_REASSESSOR_VERSION,
    FrontierActionAssessment,
    FrontierDecision,
    FrontierReassessmentResult,
    MarginalInformationProfile,
    ResearchabilityClass,
    StrategyFamilyClass,
    UncertaintyFrontierRecord,
    reassessor_content_hash,
)
from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext
from modules.edge_research.opr_bridge.scientific_action_records import (
    ExecutabilityClass,
    NextActionPackage,
    PACKAGE_RECORD_VERSION,
    RedundancyClass,
    RescueRiskClass,
    ScientificActionCandidateRecord,
    build_candidate_record,
)
from modules.edge_research.opr_bridge.scientific_action_generator import GenerationResult
from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, new_id

# Strategies whose scientific value depends on evidence-derived cohort binding.
COHORT_DEPENDENT_STRATEGIES: frozenset[str] = frozenset(
    {
        "population_subgroup_contrast",
        "regime_separated_contrast",
        "rolling_stability_contrast",
        "episode_holdout_excluding_motivating",
        "independent_replication_cohort",
        "counterexample_period_search",
        "full_panel_contrast",
    }
)

NON_COHORT_STRATEGIES: frozenset[str] = frozenset(
    {
        "concentration_decomposition",
        "measurement_robustness_check",
        "contradiction_discriminating_test",
    }
)

_AXIS_MEANING: Dict[str, str] = {
    "temporal_regime_robustness": "Effect stability across temporal regimes and episodes",
    "population_robustness": "Effect generalization across population subgroups",
    "horizon_robustness": "Effect stability across observation horizons",
    "effect_stability": "Magnitude and direction stability of claimed effect",
    "concentration_dominance": "Whether effect is driven by symbol/date concentration",
    "measurement_robustness": "Dependence on measurement specification",
    "counterexample_exposure": "Existence of observable conditions falsifying the claim",
    "alternative_explanation_exposure": "Competing explanation distinct from proposition null",
    "regime_context_robustness": "Context/regime modulation robustness",
    "episode_robustness": "Episode-level instability vulnerability",
    "directional_effect_full_universe": "Directional claim on full universe",
}


@dataclass
class CohortAxisConstraint:
    axis: str
    disposition: str
    reason: str


def _strategy_family(strategy: str, candidate: ScientificActionCandidateRecord) -> str:
    if strategy in NON_COHORT_STRATEGIES:
        return StrategyFamilyClass.NON_COHORT.value
    if strategy in COHORT_DEPENDENT_STRATEGIES:
        return StrategyFamilyClass.COHORT_DEPENDENT.value
    if candidate.executability_classification == ExecutabilityClass.REPRESENTATION_ONLY.value:
        return StrategyFamilyClass.REPRESENTATION_ONLY.value
    if candidate.redundancy_classification == RedundancyClass.REDUNDANT.value:
        return StrategyFamilyClass.REDUNDANT_WITH_EVIDENCE.value
    if candidate.rescue_risk_classification != RescueRiskClass.PASS.value:
        return StrategyFamilyClass.PROPOSITION_MUTATING.value
    if candidate.executability_classification == ExecutabilityClass.SCIENTIFICALLY_VALID_NOT_EXECUTABLE.value:
        return StrategyFamilyClass.NON_EXECUTABLE.value
    return StrategyFamilyClass.SCIENTIFICALLY_DISTINCT.value


def _cohort_constraints(ctx: ActionGenerationContext, panel: Any) -> Dict[str, CohortAxisConstraint]:
    """Run binder per axis that requires cohort independence."""
    from modules.edge_research.opr_bridge.scientific_action_objectives import generate_objectives

    binder = EvidenceDerivedCohortBinder()
    objectives = generate_objectives(ctx)
    constraints: Dict[str, CohortAxisConstraint] = {}
    for obj in objectives:
        axis = obj.target_uncertainty
        if axis in constraints:
            continue
        if axis == "population_robustness":
            binding = binder.bind_population_axis(ctx, obj, panel)
        elif axis in (
            "temporal_regime_robustness",
            "horizon_robustness",
            "effect_stability",
            "regime_context_robustness",
            "episode_robustness",
        ):
            binding = binder.bind_temporal_axis(ctx, obj, panel)
        else:
            continue
        constraints[axis] = CohortAxisConstraint(
            axis=axis,
            disposition=binding.disposition.value,
            reason=binding.reason,
        )
    return constraints


def _researchability_for_axis(
    axis: str,
    ctx: ActionGenerationContext,
    cohort_constraints: Dict[str, CohortAxisConstraint],
) -> Tuple[str, str]:
    if axis in ctx.redundant_axes:
        return ResearchabilityClass.RESEARCHABLE_BUT_REDUNDANT.value, f"Axis {axis} marked redundant in saturation assessment"
    if axis in ctx.covered_axes:
        return ResearchabilityClass.LOW_INFORMATION.value, f"Axis {axis} already in covered set"

    cc = cohort_constraints.get(axis)
    if cc and cc.disposition == CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value:
        non_cohort_exists = axis in ("concentration_dominance", "measurement_robustness", "counterexample_exposure", "alternative_explanation_exposure")
        if non_cohort_exists:
            return (
                ResearchabilityClass.RESEARCHABLE_NOW.value,
                f"Cohort routes unavailable for {axis}; non-cohort investigation may remain viable",
            )
        return (
            ResearchabilityClass.COHORT_UNAVAILABLE.value,
            f"3I.17b binder: {cc.reason}",
        )

    if axis in ("counterexample_exposure", "alternative_explanation_exposure"):
        if not ctx.null_competing_explanation and axis == "alternative_explanation_exposure":
            return ResearchabilityClass.HOLD.value, "No competing explanation derivable from evidence structure"
        return ResearchabilityClass.RESEARCHABLE_NOW.value, "Non-cohort counterexample/alternative route available"

    if axis in ("concentration_dominance", "measurement_robustness"):
        return ResearchabilityClass.RESEARCHABLE_NOW.value, "Non-cohort decomposition/robustness route available"

    if cc and cc.disposition == CohortSelectionDisposition.AMBIGUOUS_COHORT_SELECTION.value:
        return ResearchabilityClass.HOLD.value, "Cohort binding ambiguous — cannot commit to cohort-dependent investigation"

    return ResearchabilityClass.RESEARCHABLE_NOW.value, "Unresolved axis with potential investigation path"


def enumerate_uncertainty_frontier(
    ctx: ActionGenerationContext,
    cohort_constraints: Dict[str, CohortAxisConstraint],
) -> Tuple[UncertaintyFrontierRecord, ...]:
    records: List[UncertaintyFrontierRecord] = []
    for axis in ctx.unresolved_axes:
        meaning = _AXIS_MEANING.get(axis, f"Unresolved uncertainty dimension: {axis}")
        covered = tuple(sorted(ctx.covered_axes))
        partial = axis not in ctx.covered_axes and bool(covered)
        cc = cohort_constraints.get(axis)
        cohort_impact = "none"
        if cc:
            cohort_impact = cc.disposition
        researchability, rationale = _researchability_for_axis(axis, ctx, cohort_constraints)
        epistemic_impact = "material" if axis in ctx.major_unresolved else "marginal"
        exec_exists = researchability in (
            ResearchabilityClass.RESEARCHABLE_NOW.value,
            ResearchabilityClass.RESEARCHABLE_BUT_REDUNDANT.value,
        )
        records.append(
            UncertaintyFrontierRecord(
                uncertainty_axis=axis,
                scientific_meaning=meaning,
                evidence_coverage=covered,
                why_unresolved=f"Listed in synthesis.uncertainty_unresolved; priority={ctx.priority_action}",
                partially_addressed=partial,
                cohort_binding_impact=cohort_impact,
                epistemic_interpretation_impact=epistemic_impact,
                executable_investigation_exists=exec_exists,
                researchability=researchability,
                researchability_rationale=rationale,
            )
        )
    return tuple(records)


def _marginal_information(
    candidate: ScientificActionCandidateRecord,
    ctx: ActionGenerationContext,
) -> MarginalInformationProfile:
    axis = candidate.expected_new_uncertainty_coverage
    strategy = candidate.scientific_action_core.cohort_strategy
    indep = candidate.expected_independence_profile
    overlap = "HIGH" if ctx.max_cohort_overlap >= 0.9 else ("MEDIUM" if ctx.max_cohort_overlap >= 0.5 else "LOW")

    counterexample = "NONE"
    if strategy == "counterexample_period_search" and ctx.null_competing_explanation:
        counterexample = "DERIVABLE_FROM_PROPOSITION_NULL"
    elif strategy == "counterexample_period_search":
        counterexample = "TEMPORAL_HOLDOUT_ONLY"

    vuln = "HIGH" if axis in ctx.major_unresolved else "MEDIUM"
    epistemic = "MATERIAL" if candidate.falsification_capability and axis in ctx.unresolved_axes else "LOW"

    return MarginalInformationProfile(
        unresolved_dimension=axis,
        ledger_overlap_estimate=overlap,
        independence_estimate=indep.get("sample_independence", "UNKNOWN"),
        counterexample_potential=counterexample,
        vulnerability_challenge=vuln,
        epistemic_state_change_potential=epistemic,
        redundancy=candidate.redundancy_classification,
        executability=candidate.executability_classification,
        rescue_risk=candidate.rescue_risk_classification,
        rationale=(f"strategy={strategy}", f"axis={axis}"),
    )


def _cohort_disposition_for_candidate(
    candidate: ScientificActionCandidateRecord,
    cohort_constraints: Dict[str, CohortAxisConstraint],
) -> Optional[str]:
    axis = candidate.expected_new_uncertainty_coverage
    strategy = candidate.scientific_action_core.cohort_strategy
    if strategy not in COHORT_DEPENDENT_STRATEGIES:
        return None
    cc = cohort_constraints.get(axis)
    if cc:
        return cc.disposition
    if strategy in ("counterexample_period_search",):
        return None
    return cohort_constraints.get(axis, CohortAxisConstraint(axis, "UNKNOWN", "")).disposition


def _is_available(
    candidate: ScientificActionCandidateRecord,
    cohort_constraints: Dict[str, CohortAxisConstraint],
    ctx: ActionGenerationContext,
) -> Tuple[bool, str]:
    strategy = candidate.scientific_action_core.cohort_strategy
    axis = candidate.expected_new_uncertainty_coverage

    if axis in ctx.redundant_axes:
        return False, f"Axis {axis} marked redundant in saturation assessment"

    if strategy == "episode_holdout_excluding_motivating":
        temporal = cohort_constraints.get("temporal_regime_robustness")
        if temporal and temporal.disposition == CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value:
            return False, "Episode holdout uses temporal cohort exclusion — blocked by 3I.17b"

    if strategy == "counterexample_period_search":
        temporal = cohort_constraints.get("temporal_regime_robustness")
        if temporal and temporal.disposition == CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value:
            return False, "Counterexample search uses temporal cohort exclusion — blocked by 3I.17b temporal constraint"

    if strategy in COHORT_DEPENDENT_STRATEGIES:
        disp = _cohort_disposition_for_candidate(candidate, cohort_constraints)
        if disp == CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value:
            return False, "Cohort binding NO_DEFENSIBLE — action unavailable (3I.17b constraint)"
        if disp == CohortSelectionDisposition.AMBIGUOUS_COHORT_SELECTION.value:
            return False, "Cohort binding ambiguous"
        if candidate.executability_classification == ExecutabilityClass.EXECUTABLE_BUT_LOW_INFORMATION.value:
            return False, "Cohort-bound low-information fallback rejected at frontier"
        if candidate.redundancy_classification == RedundancyClass.REDUNDANT.value:
            return False, "Redundant with prior evidence"

    if candidate.executability_classification in (
        ExecutabilityClass.INVALID.value,
        ExecutabilityClass.RESCUE_RISK.value,
        ExecutabilityClass.REPRESENTATION_ONLY.value,
        ExecutabilityClass.EXECUTABLE_BUT_LOW_INFORMATION.value,
    ):
        return False, f"Executability class: {candidate.executability_classification}"

    if candidate.redundancy_classification == RedundancyClass.REDUNDANT.value:
        return False, "Redundant with prior evidence"

    if candidate.rescue_risk_classification != RescueRiskClass.PASS.value:
        return False, f"Rescue risk: {candidate.rescue_risk_classification}"

    if candidate.executability_classification != ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value:
        return False, f"Not executable: {candidate.executability_classification}"

    if axis == "alternative_explanation_exposure" and not ctx.null_competing_explanation:
        return False, "Alternative explanation requires proposition null — not human-invented"

    return True, "Available non-cohort or defensible cohort-bound action"


def _rank_frontier_key(assessment: FrontierActionAssessment) -> Tuple:
    mi = assessment.marginal_information
    non_cohort = 0 if assessment.strategy_family_class == StrategyFamilyClass.NON_COHORT.value else 1
    vuln = 0 if mi.vulnerability_challenge == "HIGH" else 1
    redundant = 0 if mi.redundancy == RedundancyClass.NOVEL.value else 1
    indep = 0 if mi.independence_estimate == "HIGH" else (1 if mi.independence_estimate == "MEDIUM" else 2)
    epistemic = 0 if mi.epistemic_state_change_potential == "MATERIAL" else 1
    rescue = 0 if mi.rescue_risk == RescueRiskClass.PASS.value else 1
    exec_rank = 0 if mi.executability == ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value else 1
    return (non_cohort, rescue, redundant, vuln, indep, epistemic, exec_rank, assessment.uncertainty_axis)


def reassess_frontier(
    ctx: ActionGenerationContext,
    generation: GenerationResult,
    *,
    panel: Any = None,
    cohort_constraints_override: Optional[Dict[str, CohortAxisConstraint]] = None,
) -> FrontierReassessmentResult:
    """
    Reassess scientific frontier after consuming cohort-binding constraints.
    Does not execute experiments or read ToolResults.
    """
    from modules.edge_research.opr_bridge.evidence_derived_cohort_binder import panel_from_context

    panel_index = panel if panel is not None else panel_from_context(ctx)
    cohort_constraints = cohort_constraints_override or _cohort_constraints(ctx, panel_index)
    uncertainty_frontier = enumerate_uncertainty_frontier(ctx, cohort_constraints)

    assessments: List[FrontierActionAssessment] = []
    for candidate in generation.deduplicated:
        strategy = candidate.scientific_action_core.cohort_strategy
        available, avail_reason = _is_available(candidate, cohort_constraints, ctx)
        family = _strategy_family(strategy, candidate)
        if strategy in COHORT_DEPENDENT_STRATEGIES and not available:
            family = StrategyFamilyClass.COHORT_DEPENDENT.value

        disp = "AVAILABLE" if available else "UNAVAILABLE"
        assessments.append(
            FrontierActionAssessment(
                candidate_id=candidate.action_candidate_id,
                core_hash=candidate.scientific_action_core_hash,
                uncertainty_axis=candidate.expected_new_uncertainty_coverage,
                cohort_strategy=strategy,
                strategy_family_class=family,
                scientific_identity=candidate.scientific_action_core_hash,
                marginal_information=_marginal_information(candidate, ctx),
                cohort_binding_required=strategy in COHORT_DEPENDENT_STRATEGIES,
                cohort_binding_disposition=_cohort_disposition_for_candidate(candidate, cohort_constraints),
                available=available,
                availability_reason=avail_reason,
                disposition=disp,
            )
        )

    eligible = [a for a in assessments if a.available]
    priority = ctx.priority_action

    if priority in ("HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"):
        return _finalize_result(
            ctx,
            generation,
            uncertainty_frontier,
            assessments,
            FrontierDecision.HOLD_PROVISIONALLY,
            None,
            None,
            f"Priority {priority} — provisional hold without forced selection",
            silence_rationale="Authoritative priority mandates hold",
        )

    if not eligible:
        silence = _build_silence_rationale(ctx, uncertainty_frontier, cohort_constraints)
        return _finalize_result(
            ctx,
            generation,
            uncertainty_frontier,
            assessments,
            FrontierDecision.NO_HIGH_INFORMATION_ACTION,
            None,
            None,
            "No high-information non-cohort actions remain after cohort constraint propagation",
            silence_rationale=silence,
        )

    major_addressed = [a for a in eligible if a.uncertainty_axis in ctx.major_unresolved]
    if not major_addressed and str(ctx.priority.marginal_information).lower() == "low":
        silence = _build_silence_rationale(ctx, uncertainty_frontier, cohort_constraints)
        silence += " Priority marginal_information=low and no eligible action addresses major unresolved dimensions."
        return _finalize_result(
            ctx,
            generation,
            uncertainty_frontier,
            assessments,
            FrontierDecision.NO_HIGH_INFORMATION_ACTION,
            None,
            None,
            "Major unresolved vulnerabilities require cohort independence unavailable after 3I.17b; marginal information too low for peripheral axes",
            silence_rationale=silence,
        )

    ranked = sorted(eligible, key=_rank_frontier_key)
    best_key = _rank_frontier_key(ranked[0])
    ties = [a for a in ranked if _rank_frontier_key(a) == best_key]

    if len(ties) > 1:
        return _finalize_result(
            ctx,
            generation,
            uncertainty_frontier,
            assessments,
            FrontierDecision.AMBIGUOUS_FRONTIER,
            None,
            None,
            f"Ambiguous tie among {len(ties)} frontier actions at rank {best_key}",
            silence_rationale=None,
        )

    winner_assessment = ranked[0]
    winner = next(c for c in generation.deduplicated if c.action_candidate_id == winner_assessment.candidate_id)
    package = _freeze_frontier_package(ctx, generation, winner, winner_assessment, eligible_count=len(eligible))

    return _finalize_result(
        ctx,
        generation,
        uncertainty_frontier,
        assessments,
        FrontierDecision.SELECTED_NON_COHORT_ACTION,
        winner.action_candidate_id,
        winner.scientific_action_core_hash,
        f"Frontier winner: {winner.scientific_action_core.cohort_strategy} on {winner.expected_new_uncertainty_coverage}",
        silence_rationale=None,
        package=package,
    )


def _build_silence_rationale(
    ctx: ActionGenerationContext,
    frontier: Sequence[UncertaintyFrontierRecord],
    cohort_constraints: Dict[str, CohortAxisConstraint],
) -> str:
    cohort_blocked = [f"{a.uncertainty_axis}" for a in frontier if a.researchability == ResearchabilityClass.COHORT_UNAVAILABLE.value]
    parts = [
        f"Epistemic state remains {ctx.synthesis.synthesized_epistemic_state} with {len(ctx.unresolved_axes)} unresolved dimensions.",
        f"Cohort-dependent routes blocked for: {', '.join(cohort_blocked) or 'none'}.",
        "Remaining non-cohort candidates fail redundancy, rescue, or marginal-information gates.",
        "Silence is rational: further investigation requires new evidence structure or capability change.",
    ]
    return " ".join(parts)


def _freeze_frontier_package(
    ctx: ActionGenerationContext,
    generation: GenerationResult,
    winner: ScientificActionCandidateRecord,
    assessment: FrontierActionAssessment,
    *,
    eligible_count: int = 1,
) -> NextActionPackage:
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash
    from modules.edge_research.opr_bridge.scientific_action_operators import operator_set_hash
    from modules.edge_research.opr_bridge.scientific_action_records import GENERATOR_VERSION, SELECTOR_VERSION

    ts = ctx.synthesis.created_at
    pid = new_id("nsap")
    cset_hash = stable_hash({"candidate_hashes": sorted(c.record_hash for c in generation.deduplicated)})
    payload = {
        "record_version": PACKAGE_RECORD_VERSION,
        "proposition_id": ctx.proposition_id,
        "proposition_hash": ctx.proposition_hash,
        "synthesis_id": ctx.synthesis.synthesis_id,
        "synthesis_hash": ctx.synthesis.synthesis_hash,
        "priority_decision_id": ctx.priority.decision_id,
        "priority_record_hash": ctx.priority.record_hash,
        "disposition": FrontierDecision.SELECTED_NON_COHORT_ACTION.value,
        "candidate_set_hash": cset_hash,
        "generator_version": GENERATOR_VERSION,
        "generator_content_hash": generator_content_hash(),
        "operator_set_hash": operator_set_hash(),
        "selector_version": SELECTOR_VERSION,
        "execution_status": "NOT_EXECUTED",
        "created_at": ts,
    }
    hash_payload = {
        **payload,
        "frontier_reassessor_version": FRONTIER_REASSESSOR_VERSION,
        "reassessor_content_hash": reassessor_content_hash(),
        "marginal_information": assessment.marginal_information.to_dict(),
    }
    package_hash = stable_hash(hash_payload)
    obj = next(
        (o for o in generation.objectives if o.target_uncertainty == winner.expected_new_uncertainty_coverage),
        generation.selection.selected_objective,
    )
    return NextActionPackage(
        package_id=pid,
        package_hash=package_hash,
        selected_objective=obj,
        selected_candidate=winner,
        selected_core_hash=winner.scientific_action_core_hash,
        experiment_spec=winner.experiment_spec,
        epistemic_consequence_contract=winner.epistemic_consequences.to_dict(),
        cutoff_leakage_policy=f"data_cutoff_date={ctx.executability.data_cutoff}; frontier reassessment pre-result",
        anti_rescue_constraints=("outcome_field", "horizon", "population_refine", "feature_change"),
        candidate_count=len(generation.deduplicated),
        eligible_count=eligible_count,
        record_version=payload["record_version"],
        proposition_id=payload["proposition_id"],
        proposition_hash=payload["proposition_hash"],
        synthesis_id=payload["synthesis_id"],
        synthesis_hash=payload["synthesis_hash"],
        priority_decision_id=payload["priority_decision_id"],
        priority_record_hash=payload["priority_record_hash"],
        disposition=payload["disposition"],
        candidate_set_hash=payload["candidate_set_hash"],
        generator_version=payload["generator_version"],
        generator_content_hash=payload["generator_content_hash"],
        operator_set_hash=payload["operator_set_hash"],
        selector_version=payload["selector_version"],
        execution_status=payload["execution_status"],
        created_at=payload["created_at"],
    )


def _finalize_result(
    ctx: ActionGenerationContext,
    generation: GenerationResult,
    uncertainty_frontier: Sequence[UncertaintyFrontierRecord],
    assessments: Sequence[FrontierActionAssessment],
    decision: FrontierDecision,
    selected_id: Optional[str],
    selected_hash: Optional[str],
    reason: str,
    *,
    silence_rationale: Optional[str],
    package: Optional[NextActionPackage] = None,
) -> FrontierReassessmentResult:
    body = {
        "reassessor_version": FRONTIER_REASSESSOR_VERSION,
        "frontier_decision": decision.value,
        "synthesis_hash": ctx.synthesis.synthesis_hash,
        "selected_core_hash": selected_hash,
        "assessment_count": len(assessments),
    }
    return FrontierReassessmentResult(
        reassessor_version=FRONTIER_REASSESSOR_VERSION,
        frontier_decision=decision,
        uncertainty_frontier=tuple(uncertainty_frontier),
        action_assessments=tuple(assessments),
        selected_candidate_id=selected_id,
        selected_core_hash=selected_hash,
        package=package,
        reason=reason,
        silence_rationale=silence_rationale,
        record_hash=stable_hash(body),
    )


class ScientificFrontierReassessor:
    """Entry point for Phase 3I.18 frontier reassessment."""

    def reassess(
        self,
        ctx: ActionGenerationContext,
        generation: GenerationResult,
        *,
        panel: Any = None,
        cohort_constraints_override: Optional[Dict[str, CohortAxisConstraint]] = None,
    ) -> FrontierReassessmentResult:
        return reassess_frontier(
            ctx,
            generation,
            panel=panel,
            cohort_constraints_override=cohort_constraints_override,
        )
