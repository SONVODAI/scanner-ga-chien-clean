"""
Phase 3I.16 — Generic scientific action operators.

Operators express scientific transformations — not GAP/template catalogs.
Tool binding occurs after scientific action definition.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.opr_bridge.cohort_binding_records import CohortSelectionDisposition
from modules.edge_research.opr_bridge.evidence_derived_cohort_binder import (
    EvidenceDerivedCohortBinder,
    panel_from_context,
)
from modules.edge_research.opr_bridge.scientific_action_core import _commitment_label, _contrast_relation
from modules.edge_research.opr_bridge.scientific_action_records import (
    EpistemicConsequenceContract,
    ExecutabilityClass,
    RedundancyClass,
    RescueRiskClass,
    ScientificActionCore,
    ScientificActionCandidateRecord,
    ScientificObjectiveRecord,
    build_candidate_record,
)
from modules.edge_research.opr_bridge.scientific_action_executability import (
    assess_executability,
    bind_experiment_spec,
)

OPERATOR_REGISTRY: Dict[str, "ScientificActionOperator"] = {}


class ScientificActionOperator(ABC):
    operator_id: str

    @abstractmethod
    def applies_to(self, objective: ScientificObjectiveRecord, ctx: ActionGenerationContext) -> bool:
        ...

    @abstractmethod
    def propose(
        self,
        objective: ScientificObjectiveRecord,
        ctx: ActionGenerationContext,
    ) -> List[ScientificActionCandidateRecord]:
        ...


def register_operator(op: ScientificActionOperator) -> None:
    OPERATOR_REGISTRY[op.operator_id] = op


def operator_set_hash() -> str:
    from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
    from modules.edge_research.opr_bridge.scientific_action_records import OPERATOR_SET_VERSION

    return stable_hash({"version": OPERATOR_SET_VERSION, "operators": sorted(OPERATOR_REGISTRY.keys())})


def _default_consequences(axis: str, *, falsify: bool) -> EpistemicConsequenceContract:
    if falsify:
        return EpistemicConsequenceContract(
            if_supporting=f"{axis} remains unresolved — supporting sub-result does not confirm proposition",
            if_disconfirming=f"Proposition vulnerable on {axis}; may transition to CONFLICTED/FALSIFIED",
            if_contradictory=f"Contradiction emerges on {axis}",
            if_non_informative=f"{axis} remains unresolved — cohort insufficient or ambiguous",
            if_invalid="No scientific belief change — invalid execution only",
        )
    return EpistemicConsequenceContract(
        if_supporting=f"{axis} moves toward covered; reduces unresolved uncertainty",
        if_disconfirming=f"Challenges support on {axis}",
        if_contradictory=f"Conflict on {axis} requires resolution",
        if_non_informative=f"{axis} remains unresolved",
        if_invalid="No scientific belief change",
    )


def _independence_from_cohort(cohort_record: Optional[Any], strategy: str) -> Dict[str, str]:
    """Evidence-computed independence when cohort binding available; else conservative fallback."""
    if cohort_record is not None:
        return cohort_record.independence_profile.to_dict()
    # Non-cohort strategies retain structural defaults (not market-state hardcodes)
    mapping = {
        "episode_holdout_excluding_motivating": {
            "sample_independence": "MEDIUM",
            "temporal_independence": "MEDIUM",
            "episode_independence": "HIGH",
        },
        "rolling_stability_contrast": {
            "sample_independence": "MEDIUM",
            "temporal_independence": "HIGH",
        },
        "counterexample_period_search": {
            "temporal_independence": "HIGH",
            "episode_independence": "HIGH",
        },
        "independent_replication_cohort": {
            "sample_independence": "HIGH",
            "episode_independence": "HIGH",
        },
        "contradiction_discriminating_test": {
            "methodological_independence": "HIGH",
            "sample_independence": "HIGH",
        },
        "concentration_decomposition": {"sample_independence": "MEDIUM"},
        "measurement_robustness_check": {"measurement_independence": "HIGH"},
    }
    return mapping.get(strategy, {"sample_independence": "MEDIUM"})


_COHORT_BINDER = EvidenceDerivedCohortBinder()


def _classify_redundancy(
    core: ScientificActionCore,
    ctx: ActionGenerationContext,
    axis: str,
) -> str:
    if core.core_hash in ctx.executed_core_hashes:
        return RedundancyClass.REDUNDANT.value
    if axis in ctx.redundant_axes:
        return RedundancyClass.REDUNDANT.value
    if ctx.max_cohort_overlap >= 0.95 and core.cohort_strategy == "episode_holdout_excluding_motivating":
        return RedundancyClass.REDUNDANT.value
    if ctx.max_cohort_overlap >= 0.9 and core.cohort_strategy in (
        "episode_holdout_excluding_motivating",
        "independent_replication_cohort",
        "full_panel_contrast",
    ):
        return RedundancyClass.REDUNDANT.value
    return RedundancyClass.NOVEL.value


def _finalize_candidate(
    *,
    objective: ScientificObjectiveRecord,
    ctx: ActionGenerationContext,
    core: ScientificActionCore,
    semantics: str,
    cohort_semantics: str,
    operator_id: str,
    rescue_risk: str = RescueRiskClass.PASS.value,
    tool_override: Optional[str] = None,
    alt_envelope: Optional[Dict[str, Any]] = None,
    population_spec_override: Optional[Dict[str, Any]] = None,
    cohort_binding_record: Optional[Any] = None,
) -> ScientificActionCandidateRecord:
    axis = objective.target_uncertainty
    redundancy = _classify_redundancy(core, ctx, axis)
    falsify = objective.falsification_relevant
    consequences = _default_consequences(axis, falsify=falsify)
    commitment = _commitment_label(ctx)

    spec, envelope, exec_class, exec_detail = bind_experiment_spec(
        ctx,
        core=core,
        rescue_risk=rescue_risk,
        tool_override=tool_override,
        alt_envelope=alt_envelope,
        population_spec_override=population_spec_override,
    )

    if redundancy == RedundancyClass.REDUNDANT.value and exec_class == ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value:
        exec_class = ExecutabilityClass.EXECUTABLE_BUT_LOW_INFORMATION.value
        exec_detail = f"Redundant axis or core: {exec_detail}"

    if rescue_risk != RescueRiskClass.PASS.value:
        exec_class = ExecutabilityClass.RESCUE_RISK.value

    if cohort_binding_record is not None and cohort_binding_record.rescue_risk_status != RescueRiskClass.PASS.value:
        exec_class = ExecutabilityClass.RESCUE_RISK.value
        exec_detail = f"Cohort rescue risk: {cohort_binding_record.rescue_risk_status}"

    return build_candidate_record(
        objective=objective,
        action_scientific_semantics=semantics,
        proposition_commitment_challenged=commitment,
        evidence_cohort_semantics=cohort_semantics,
        expected_new_uncertainty_coverage=axis,
        expected_independence_profile=_independence_from_cohort(cohort_binding_record, core.cohort_strategy),
        epistemic_consequences=consequences,
        falsification_capability=falsify,
        contradiction_resolution_capability=objective.contradiction_resolution_relevant,
        redundancy_classification=redundancy,
        rescue_risk_classification=rescue_risk,
        executability_classification=exec_class,
        executability_detail=exec_detail,
        scientific_action_core=core,
        representation_envelope=envelope,
        experiment_spec=spec,
        operator_id=operator_id,
        provenance={
            "objective_hash": objective.objective_hash,
            "operator_id": operator_id,
            "synthesis_hash": ctx.synthesis.synthesis_hash,
        },
        created_at=ctx.synthesis.created_at,
    )


_COHORT_BOUND_STRATEGIES = frozenset({"population_subgroup_contrast", "regime_separated_contrast"})


def _propose_cohort_bound_action(
    *,
    objective: ScientificObjectiveRecord,
    ctx: ActionGenerationContext,
    strategy: str,
    cohort_sem: str,
    rationale: str,
    operator_id: str,
    panel_fixture: Optional[Dict[str, Any]] = None,
) -> List[ScientificActionCandidateRecord]:
    """Use EvidenceDerivedCohortBinder for strategies requiring cohort selection."""
    panel = panel_from_context(ctx, fixture=panel_fixture)
    if strategy == "population_subgroup_contrast":
        binding = _COHORT_BINDER.bind_population_axis(ctx, objective, panel)
    else:
        binding = _COHORT_BINDER.bind_temporal_axis(ctx, objective, panel)

    if binding.disposition == CohortSelectionDisposition.NO_DEFENSIBLE_COHORT:
        if binding.candidates:
            fallback = binding.candidates[0]
            return _emit_cohort_candidate(
                objective=objective,
                ctx=ctx,
                strategy=strategy,
                cohort_sem=cohort_sem,
                rationale=rationale,
                operator_id=operator_id,
                selected=fallback,
                low_information=True,
            )
        return []

    if binding.disposition == CohortSelectionDisposition.AMBIGUOUS_COHORT_SELECTION:
        return []

    selected = binding.selected
    if selected is None:
        return []

    return _emit_cohort_candidate(
        objective=objective,
        ctx=ctx,
        strategy=strategy,
        cohort_sem=cohort_sem,
        rationale=rationale,
        operator_id=operator_id,
        selected=selected,
        low_information=False,
    )


def _emit_cohort_candidate(
    *,
    objective: ScientificObjectiveRecord,
    ctx: ActionGenerationContext,
    strategy: str,
    cohort_sem: str,
    rationale: str,
    operator_id: str,
    selected: Any,
    low_information: bool,
) -> List[ScientificActionCandidateRecord]:
    contrast = _contrast_relation(ctx)
    core = ScientificActionCore(
        objective_target_uncertainty=objective.target_uncertainty,
        proposition_commitment_challenged=_commitment_label(ctx),
        cohort_strategy=strategy,
        contrast_relation=contrast,
        expected_epistemic_consequence_type=f"falsify_{objective.target_uncertainty}",
        information_gain_type="falsify",
    )
    rescue = selected.rescue_risk_status
    if low_information:
        rescue = RescueRiskClass.PASS.value
    cand = _finalize_candidate(
        objective=objective,
        ctx=ctx,
        core=core,
        semantics=f"Falsify {objective.target_uncertainty}: {rationale} [{selected.cohort_semantic_definition}]",
        cohort_semantics=f"{cohort_sem} — {selected.cohort_semantic_definition}",
        operator_id=operator_id,
        population_spec_override=selected.population_spec,
        cohort_binding_record=selected,
        rescue_risk=rescue,
    )
    if low_information:
        from modules.edge_research.opr_bridge.scientific_action_records import ExecutabilityClass, RedundancyClass, build_candidate_record

        return [
            build_candidate_record(
                objective=objective,
                action_scientific_semantics=cand.action_scientific_semantics,
                proposition_commitment_challenged=cand.proposition_commitment_challenged,
                evidence_cohort_semantics=cand.evidence_cohort_semantics,
                expected_new_uncertainty_coverage=cand.expected_new_uncertainty_coverage,
                expected_independence_profile=cand.expected_independence_profile,
                epistemic_consequences=cand.epistemic_consequences,
                falsification_capability=cand.falsification_capability,
                contradiction_resolution_capability=cand.contradiction_resolution_capability,
                redundancy_classification=RedundancyClass.REDUNDANT.value,
                rescue_risk_classification=cand.rescue_risk_classification,
                executability_classification=ExecutabilityClass.EXECUTABLE_BUT_LOW_INFORMATION.value,
                executability_detail="No defensible cohort — best-effort binding for audit",
                scientific_action_core=cand.scientific_action_core,
                representation_envelope=cand.representation_envelope,
                experiment_spec=cand.experiment_spec,
                operator_id=operator_id,
                provenance=cand.provenance,
                created_at=cand.created_at,
            )
        ]
    return [cand]


def _cohort_strategies_for_axis(
    axis: str,
    ctx: ActionGenerationContext,
) -> List[Tuple[str, str, str]]:
    """
    Context-sensitive cohort strategies — NOT fixed uncertainty→action map.
    Returns (strategy_key, semantics_description, human_rationale_fragment).
    """
    strategies: List[Tuple[str, str, str]] = []

    if axis == "temporal_regime_robustness":
        if ctx.axis_is_saturated("episode_robustness") or "episode_robustness" in ctx.covered_axes:
            strategies.append(
                (
                    "regime_separated_contrast",
                    "regime-separated cohort contrast excluding prior episode tests",
                    "Episode holdout redundant — test temporal regime separation",
                )
            )
            if ctx.executability.has_regime_column:
                strategies.append(
                    (
                        "rolling_stability_contrast",
                        "rolling temporal stability contrast across non-motivating windows",
                        "Complementary temporal robustness via rolling stability",
                    )
                )
        else:
            if ctx.motivating_dates:
                strategies.append(
                    (
                        "episode_holdout_excluding_motivating",
                        "episode holdout excluding motivating dates",
                        "Test on episodes independent of birth evidence",
                    )
                )
            strategies.append(
                (
                    "regime_separated_contrast",
                    "regime-separated quintile contrast",
                    "Test temporal regime robustness",
                )
            )

    elif axis == "population_robustness":
        strategies.append(
            (
                "population_subgroup_contrast",
                "population subgroup contrast with low overlap to prior cohort",
                "Challenge population specificity with independent subgroup",
            )
        )

    elif axis == "episode_robustness":
        if not ctx.axis_is_saturated(axis):
            strategies.append(
                (
                    "episode_holdout_excluding_motivating",
                    "independent episode holdout",
                    "Test episode instability vulnerability",
                )
            )

    elif axis in ("counterexample_exposure", "alternative_explanation_exposure"):
        strategies.append(
            (
                "counterexample_period_search",
                "bounded counterexample period search per null explanation",
                f"Seek counterexample motivated by: {ctx.null_competing_explanation[:80]}",
            )
        )

    elif axis == "concentration_dominance":
        strategies.append(
            (
                "concentration_decomposition",
                "symbol-level concentration/dominance decomposition",
                "Test whether effect is driven by single-name dominance",
            )
        )

    elif axis == "measurement_robustness":
        strategies.append(
            (
                "measurement_robustness_check",
                "measurement specification robustness without outcome mutation",
                "Test measurement dependence without changing proposition outcome",
            )
        )

    elif axis in ("horizon_robustness", "effect_stability", "regime_context_robustness"):
        strategies.append(
            (
                "regime_separated_contrast",
                f"robustness test for {axis} via regime/context separation",
                f"Test uncovered dimension: {axis}",
            )
        )

    elif axis == "directional_effect_full_universe":
        strategies.append(
            (
                "full_panel_contrast",
                "full universe directional contrast",
                "Challenge directional claim on full panel",
            )
        )

    elif axis.startswith("context_") or axis == "context_modulation_direction":
        strategies.append(
            (
                "regime_separated_contrast",
                "context-modulation contrast across independent cohort",
                "Test context modulation robustness",
            )
        )

    else:
        strategies.append(
            (
                "regime_separated_contrast",
                f"general robustness test for {axis}",
                f"Test unresolved dimension {axis}",
            )
        )

    return strategies


class FalsificationOperator(ScientificActionOperator):
    operator_id = "FalsificationOperator"

    def applies_to(self, objective: ScientificObjectiveRecord, ctx: ActionGenerationContext) -> bool:
        return (
            ctx.priority_action == "SEEK_FALSIFICATION"
            and objective.falsification_relevant
            and not objective.contradiction_resolution_relevant
        )

    def propose(
        self,
        objective: ScientificObjectiveRecord,
        ctx: ActionGenerationContext,
    ) -> List[ScientificActionCandidateRecord]:
        axis = objective.target_uncertainty
        if ctx.axis_is_saturated(axis) and axis != "contradiction_resolution":
            return []

        contrast = _contrast_relation(ctx)
        candidates: List[ScientificActionCandidateRecord] = []
        for strategy, cohort_sem, rationale in _cohort_strategies_for_axis(axis, ctx):
            if strategy in _COHORT_BOUND_STRATEGIES:
                candidates.extend(
                    _propose_cohort_bound_action(
                        objective=objective,
                        ctx=ctx,
                        strategy=strategy,
                        cohort_sem=cohort_sem,
                        rationale=rationale,
                        operator_id=self.operator_id,
                    )
                )
                continue
            core = ScientificActionCore(
                objective_target_uncertainty=axis,
                proposition_commitment_challenged=_commitment_label(ctx),
                cohort_strategy=strategy,
                contrast_relation=contrast,
                expected_epistemic_consequence_type=f"falsify_{axis}",
                information_gain_type="falsify",
            )
            candidates.append(
                _finalize_candidate(
                    objective=objective,
                    ctx=ctx,
                    core=core,
                    semantics=f"Falsify {axis}: {rationale}",
                    cohort_semantics=cohort_sem,
                    operator_id=self.operator_id,
                )
            )
        return candidates


class RobustnessOperator(ScientificActionOperator):
    operator_id = "RobustnessOperator"

    def applies_to(self, objective: ScientificObjectiveRecord, ctx: ActionGenerationContext) -> bool:
        return (
            ctx.priority_action in ("SEEK_FALSIFICATION", "HOLD_UNRESOLVED")
            and not objective.contradiction_resolution_relevant
            and objective.target_uncertainty
            in (
                "horizon_robustness",
                "effect_stability",
                "measurement_robustness",
                "concentration_dominance",
                "regime_context_robustness",
            )
        )

    def propose(
        self,
        objective: ScientificObjectiveRecord,
        ctx: ActionGenerationContext,
    ) -> List[ScientificActionCandidateRecord]:
        return FalsificationOperator().propose(objective, ctx)


class ReplicationOperator(ScientificActionOperator):
    operator_id = "ReplicationOperator"

    def applies_to(self, objective: ScientificObjectiveRecord, ctx: ActionGenerationContext) -> bool:
        return ctx.priority_action == "SEEK_REPLICATION"

    def propose(
        self,
        objective: ScientificObjectiveRecord,
        ctx: ActionGenerationContext,
    ) -> List[ScientificActionCandidateRecord]:
        axis = objective.target_uncertainty
        contrast = _contrast_relation(ctx)
        core = ScientificActionCore(
            objective_target_uncertainty=axis,
            proposition_commitment_challenged=_commitment_label(ctx),
            cohort_strategy="independent_replication_cohort",
            contrast_relation=contrast,
            expected_epistemic_consequence_type=f"replicate_{axis}",
            information_gain_type="replicate",
        )
        return [
            _finalize_candidate(
                objective=objective,
                ctx=ctx,
                core=core,
                semantics=f"Independent replication of {axis} with high sample independence",
                cohort_semantics="independent replication cohort excluding prior overlap",
                operator_id=self.operator_id,
            )
        ]


class ContradictionResolutionOperator(ScientificActionOperator):
    operator_id = "ContradictionResolutionOperator"

    def applies_to(self, objective: ScientificObjectiveRecord, ctx: ActionGenerationContext) -> bool:
        return objective.contradiction_resolution_relevant and ctx.has_contradiction

    def propose(
        self,
        objective: ScientificObjectiveRecord,
        ctx: ActionGenerationContext,
    ) -> List[ScientificActionCandidateRecord]:
        axis = objective.target_uncertainty
        contrast = _contrast_relation(ctx)
        core = ScientificActionCore(
            objective_target_uncertainty=axis,
            proposition_commitment_challenged=_commitment_label(ctx),
            cohort_strategy="contradiction_discriminating_test",
            contrast_relation=contrast,
            expected_epistemic_consequence_type="resolve_contradiction",
            information_gain_type="resolve_contradiction",
        )
        return [
            _finalize_candidate(
                objective=objective,
                ctx=ctx,
                core=core,
                semantics="Discriminating test to resolve contradictory independent evidence",
                cohort_semantics="cohort designed to distinguish supporting vs disconfirming paths",
                operator_id=self.operator_id,
            )
        ]


class CounterexampleOperator(ScientificActionOperator):
    operator_id = "CounterexampleOperator"

    def applies_to(self, objective: ScientificObjectiveRecord, ctx: ActionGenerationContext) -> bool:
        return objective.target_uncertainty in (
            "counterexample_exposure",
            "alternative_explanation_exposure",
        ) and bool(ctx.null_competing_explanation)

    def propose(
        self,
        objective: ScientificObjectiveRecord,
        ctx: ActionGenerationContext,
    ) -> List[ScientificActionCandidateRecord]:
        return FalsificationOperator().propose(objective, ctx)


def all_operators() -> Sequence[ScientificActionOperator]:
    return [
        ContradictionResolutionOperator(),
        CounterexampleOperator(),
        FalsificationOperator(),
        ReplicationOperator(),
        RobustnessOperator(),
    ]


def ensure_operators_registered() -> None:
    if not OPERATOR_REGISTRY:
        for op in all_operators():
            register_operator(op)


ensure_operators_registered()
