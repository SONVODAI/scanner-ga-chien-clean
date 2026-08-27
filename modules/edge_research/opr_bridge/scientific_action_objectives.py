"""
Phase 3I.16 — ScientificObjective generation from authoritative synthesis state.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext
from modules.edge_research.opr_bridge.scientific_action_records import (
    ScientificObjectiveRecord,
    build_objective_record,
)

# Vulnerability derivation — axis + proposition context, not fixed action templates.
_AXIS_VULNERABILITY: Dict[str, str] = {
    "temporal_regime_robustness": "temporal_regime_instability",
    "population_robustness": "population_specificity",
    "horizon_robustness": "horizon_sensitivity",
    "effect_stability": "effect_magnitude_instability",
    "concentration_dominance": "symbol_concentration",
    "measurement_robustness": "measurement_dependence",
    "counterexample_exposure": "hidden_counterexample",
    "alternative_explanation_exposure": "competing_explanation",
    "regime_context_robustness": "regime_context_dependence",
    "episode_robustness": "episode_instability",
    "directional_effect_full_universe": "directional_reversal",
    "context_modulation_direction": "context_modulation_reversal",
    "context_independence": "context_independence_failure",
}

_PRIORITY_GAIN = {
    "SEEK_FALSIFICATION": "falsify_unresolved_claim",
    "SEEK_REPLICATION": "independent_replication",
    "SEEK_CONTRADICTION_RESOLUTION": "resolve_contradiction",
    "HOLD_PROVISIONALLY": "hold_marginal_information",
    "HOLD_UNRESOLVED": "hold_unresolved",
    "ABANDON": "abandon",
}


def generate_objectives(ctx: ActionGenerationContext) -> List[ScientificObjectiveRecord]:
    """Derive bounded objectives from synthesis + priority — not from tools."""
    action = ctx.priority_action
    if action in ("ABANDON", "HOLD_PROVISIONALLY", "HOLD_UNRESOLVED"):
        return []

    objectives: List[ScientificObjectiveRecord] = []
    provenance_base = {
        "synthesis_hash": ctx.synthesis.synthesis_hash,
        "priority_record_hash": ctx.priority.record_hash,
        "generator_stage": "objective_generation",
    }

    if action == "SEEK_CONTRADICTION_RESOLUTION" and ctx.has_contradiction:
        for i, contra in enumerate(ctx.synthesis.contradiction_structure):
            axis = contra.get("uncertainty_axis") or "contradiction_resolution"
            objectives.append(
                _build_objective(
                    ctx,
                    target_uncertainty=axis,
                    vulnerability="contradictory_evidence",
                    reason=f"Independent evidence in contradiction — {contra.get('relationship', 'CONFLICT')}",
                    gain="resolve_contradiction",
                    independence=("sample_independence", "methodological_independence"),
                    falsify=False,
                    contradiction=True,
                    provenance={**provenance_base, "contradiction_index": str(i)},
                )
            )
        if objectives:
            return objectives

    axes = _select_target_axes(ctx)
    for axis in axes:
        vuln = _derive_vulnerability(axis, ctx)
        reason = _derive_reason(axis, ctx)
        gain = _PRIORITY_GAIN.get(action, "inform")
        falsify = action == "SEEK_FALSIFICATION"
        replication = action == "SEEK_REPLICATION"
        independence = _independence_requirements(axis, ctx, replication=replication)
        objectives.append(
            _build_objective(
                ctx,
                target_uncertainty=axis,
                vulnerability=vuln,
                reason=reason,
                gain=gain,
                independence=independence,
                falsify=falsify,
                contradiction=False,
                provenance={**provenance_base, "axis": axis},
            )
        )
    return objectives


def _select_target_axes(ctx: ActionGenerationContext) -> Tuple[str, ...]:
    unresolved = list(ctx.unresolved_axes)
    major = ctx.major_unresolved
    redundant = ctx.redundant_axes

    if ctx.priority_action == "SEEK_REPLICATION":
        return tuple(unresolved[:3]) if unresolved else ("directional_effect_full_universe",)

    filtered = [a for a in unresolved if a not in redundant]
    if major:
        major_first = [a for a in filtered if a in major]
        rest = [a for a in filtered if a not in major]
        ordered = major_first + rest
    else:
        ordered = filtered

    if not ordered and ctx.priority_action == "SEEK_FALSIFICATION":
        ordered = [a for a in unresolved if a not in redundant]
    return tuple(ordered)


def _derive_vulnerability(axis: str, ctx: ActionGenerationContext) -> str:
    base = _AXIS_VULNERABILITY.get(axis, "general_uncertainty")
    null = ctx.null_competing_explanation.lower()
    if axis == "counterexample_exposure" and ("artifact" in null or "fluke" in null or "episode" in null):
        return "episode_counterexample"
    if axis == "concentration_dominance" and ("dominance" in null or "concentration" in null):
        return "symbol_concentration"
    if axis == "alternative_explanation_exposure" and null:
        return "competing_explanation_from_null"
    if ctx.proposition_type == "context_modulation" and "context" in axis:
        return "context_modulation_instability"
    return base


def _derive_reason(axis: str, ctx: ActionGenerationContext) -> str:
    covered = ", ".join(ctx.covered_axes) or "none"
    if axis in ctx.redundant_axes:
        return f"Axis {axis} marked redundant in saturation assessment."
    if axis in ctx.major_unresolved:
        return (
            f"Major unresolved uncertainty '{axis}' remains after covering [{covered}]; "
            f"priority={ctx.priority_action}."
        )
    return f"Unresolved uncertainty '{axis}' not yet covered; current coverage: [{covered}]."


def _independence_requirements(
    axis: str,
    ctx: ActionGenerationContext,
    *,
    replication: bool,
) -> Tuple[str, ...]:
    if replication:
        return ("sample_independence", "episode_independence")
    if axis in ("population_robustness",):
        return ("population_independence", "sample_independence")
    if axis in ("temporal_regime_robustness", "episode_robustness", "effect_stability"):
        return ("temporal_independence", "episode_independence")
    if axis in ("measurement_robustness",):
        return ("measurement_independence",)
    return ("sample_independence",)


def _build_objective(
    ctx: ActionGenerationContext,
    *,
    target_uncertainty: str,
    vulnerability: str,
    reason: str,
    gain: str,
    independence: Tuple[str, ...],
    falsify: bool,
    contradiction: bool,
    provenance: Dict[str, str],
) -> ScientificObjectiveRecord:
    return build_objective_record(
        proposition_id=ctx.proposition_id,
        proposition_hash=ctx.proposition_hash,
        synthesis_id=ctx.synthesis.synthesis_id,
        synthesis_hash=ctx.synthesis.synthesis_hash,
        priority_decision_id=ctx.priority.decision_id,
        priority_record_hash=ctx.priority.record_hash,
        target_uncertainty=target_uncertainty,
        scientific_vulnerability=vulnerability,
        reason_this_uncertainty_matters=reason,
        current_evidence_coverage=tuple(sorted(ctx.covered_axes)),
        desired_information_contribution=gain,
        required_independence_characteristics=independence,
        falsification_relevant=falsify,
        contradiction_resolution_relevant=contradiction,
        provenance=provenance,
        created_at=ctx.synthesis.created_at,
    )
