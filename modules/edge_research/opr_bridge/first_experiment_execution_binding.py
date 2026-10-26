"""
Phase 3J.3 — Scientific spec → execution spec binding audit (meaning-preserving only).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    BINDING_VERSION,
    ExecutionBindingAudit,
)
from modules.edge_research.opr_bridge.first_experiment_records import InitialExperimentPackage
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash
from modules.edge_research.opr_bridge.first_experiment_execution_tool_resolver import (
    tool_is_executable,
)
from modules.edge_research.research_tools import ToolRegistry, build_default_tool_registry


def _tool_in_registry(registry: ToolRegistry, tool_name: str, tool_version: str) -> bool:
    return tool_is_executable(tool_name, tool_version, registry)


def _find_selected_candidate(package: InitialExperimentPackage):
    if not package.selected_candidate_id:
        return None
    for c in package.deduplicated_candidates:
        if c.candidate_id == package.selected_candidate_id:
            return c
    return None


def build_scientific_spec_hash(
    *,
    scientific_identity: Dict[str, str],
    population_spec: Dict[str, Any],
    outcome_spec: Dict[str, Any],
    observation_horizon: int,
) -> str:
    return stable_hash(
        {
            "scientific_identity": dict(sorted(scientific_identity.items())),
            "population_spec": population_spec,
            "outcome_spec": outcome_spec,
            "observation_horizon": observation_horizon,
        }
    )


def bind_frozen_experiment_spec(
    package: InitialExperimentPackage,
    *,
    mutation: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[ExperimentSpec], Optional[ExecutionBindingAudit], Tuple[str, ...]]:
    """
    Bind execution spec from frozen package — no semantic mutation.

    Returns (spec, audit, errors).
    """
    errors: List[str] = []
    if not package.selected_experiment_spec:
        return None, None, ("no_selected_experiment_spec",)

    candidate = _find_selected_candidate(package)
    if candidate is None:
        return None, None, ("selected_candidate_not_found",)

    spec_dict = dict(package.selected_experiment_spec)
    if mutation:
        if "population_spec" in mutation:
            scope = dict(spec_dict.get("research_scope") or {})
            scope["population_spec"] = mutation["population_spec"]
            spec_dict["research_scope"] = scope
            errors.append("binding_mutation_population_rejected")
        if "tool_name" in mutation:
            spec_dict["tool_name"] = mutation["tool_name"]
            errors.append("binding_mutation_tool_rejected")
        if "inputs" in mutation:
            spec_dict["inputs"] = mutation["inputs"]
            errors.append("binding_mutation_inputs_rejected")
        return None, None, tuple(errors)

    if candidate.experiment_spec != spec_dict:
        return None, None, ("package_spec_candidate_spec_mismatch",)

    spec = ExperimentSpec.from_dict(spec_dict)
    scope = spec.research_scope or {}
    population_spec = dict(scope.get("population_spec") or {})
    outcome_spec = dict(scope.get("outcome_spec") or {})
    horizon = int(scope.get("observation_horizon", 0))

    scientific_hash = build_scientific_spec_hash(
        scientific_identity=dict(candidate.scientific_identity),
        population_spec=population_spec,
        outcome_spec=outcome_spec,
        observation_horizon=horizon,
    )
    execution_hash = compute_experiment_content_hash(spec)

    registry = build_default_tool_registry()
    tool_version = spec.tool_version
    if not _tool_in_registry(registry, spec.tool_name, tool_version):
        return None, None, (f"tool_not_in_registry:{spec.tool_name}",)

    audit = ExecutionBindingAudit(
        scientific_spec_hash=scientific_hash,
        execution_spec_hash=execution_hash,
        scientific_action_core_hash=candidate.scientific_action_core_hash,
        population_spec=population_spec,
        outcome_spec=outcome_spec,
        observation_horizon=horizon,
        tool_name=spec.tool_name,
        tool_version=tool_version,
        inputs=dict(spec.inputs),
        binding_notes=(
            f"binding_version={BINDING_VERSION}",
            "executed_question_equals_selected_question",
            f"cohort_strategy={candidate.scientific_identity.get('cohort_strategy', '')}",
        ),
    )
    return spec, audit, tuple()


def verify_binding_identity(
    audit: ExecutionBindingAudit,
    package: InitialExperimentPackage,
) -> Tuple[bool, Tuple[str, ...]]:
    """Post-bind check: execution spec resolves to selected scientific action."""
    candidate = _find_selected_candidate(package)
    if candidate is None:
        return False, ("candidate_missing",)
    if audit.scientific_action_core_hash != candidate.scientific_action_core_hash:
        return False, ("scientific_action_core_hash_mismatch",)
    if package.selected_experiment_spec:
        spec = ExperimentSpec.from_dict(package.selected_experiment_spec)
        if compute_experiment_content_hash(spec) != audit.execution_spec_hash:
            return False, ("execution_spec_hash_mismatch",)
    return True, tuple()
