"""
Phase 3I.16 — Generic scientific action operators.

Operators express scientific transformations — not GAP/template catalogs.
Tool binding occurs after scientific action definition.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext
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


def _independence_estimate(strategy: str) -> Dict[str, str]:
    mapping = {
        "episode_holdout_excluding_motivating": {
            "sample_independence": "MEDIUM",
            "temporal_independence": "MEDIUM",
            "episode_independence": "HIGH",
        },
        "regime_separated_contrast": {
            "sample_independence": "MEDIUM",
            "temporal_independence": "HIGH",
            "episode_independence": "MEDIUM",
        },
        "rolling_stability_contrast": {
            "sample_independence": "MEDIUM",
            "temporal_independence": "HIGH",
        },
        "population_subgroup_contrast": {
            "population_independence": "HIGH",
            "sample_independence": "HIGH",
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
        "concentration_decomposition": {
            "sample_independence": "MEDIUM",
        },
        "measurement_robustness_check": {
            "measurement_independence": "HIGH",
        },
    }
    return mapping.get(strategy, {"sample_independence": "MEDIUM"})


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
    )

    if redundancy == RedundancyClass.REDUNDANT.value and exec_class == ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value:
        exec_class = ExecutabilityClass.EXECUTABLE_BUT_LOW_INFORMATION.value
        exec_detail = f"Redundant axis or core: {exec_detail}"

    if rescue_risk != RescueRiskClass.PASS.value:
        exec_class = ExecutabilityClass.RESCUE_RISK.value

    return build_candidate_record(
        objective=objective,
        action_scientific_semantics=semantics,
        proposition_commitment_challenged=commitment,
        evidence_cohort_semantics=cohort_semantics,
        expected_new_uncertainty_coverage=axis,
        expected_independence_profile=_independence_estimate(core.cohort_strategy),
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
