"""
Phase 3J.7 — Second-experiment execution eligibility gate (novelty-aware, fail closed).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.first_experiment_execution_gate import (
    _population_representable,
    compute_execution_identity_hash,
    compute_panel_provenance_hash,
)
from modules.edge_research.opr_bridge.first_experiment_execution_tool_resolver import tool_is_executable
from modules.edge_research.research_tools import build_default_tool_registry
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    ExecutionEligibility,
    ExecutionEligibilityResult,
    FirstExperimentExecutionEnvelope,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    FirstExperimentResearchDecisionEnvelope,
)
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.second_experiment_execution_adapter import second_package_to_initial_package
from modules.edge_research.opr_bridge.second_experiment_execution_records import (
    GATE_VERSION,
    SecondExperimentExecutionEnvelope,
)
from modules.edge_research.opr_bridge.second_experiment_novelty_audit import (
    NoveltyDecomposition,
    decompose_novelty,
)
from modules.edge_research.opr_bridge.second_experiment_records import (
    SecondExperimentDisposition,
    SecondExperimentPackage,
)
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash


def _find_selected_candidate(package: SecondExperimentPackage):
    if not package.selected_candidate_id:
        return None
    for c in package.deduplicated_candidates:
        if c.candidate_id == package.selected_candidate_id:
            return c
    return None


def compute_novelty_for_execution(
    *,
    package: SecondExperimentPackage,
    first_execution: Optional[FirstExperimentExecutionEnvelope],
    row_overlap_fraction: Optional[float] = None,
) -> Optional[NoveltyDecomposition]:
    if first_execution is None:
        return None
    selected = _find_selected_candidate(package)
    if selected is None:
        return None
    first_spec = {
        "tool_name": first_execution.binding_audit.tool_name,
        "inputs": dict(first_execution.binding_audit.inputs),
        "research_scope": {
            "population_spec": dict(first_execution.binding_audit.population_spec),
            "outcome_spec": dict(first_execution.binding_audit.outcome_spec),
            "observation_horizon": first_execution.binding_audit.observation_horizon,
        },
    }
    first_identity = {
        "cohort_strategy": next(
            (n.split("=")[-1] for n in first_execution.binding_audit.binding_notes if "cohort_strategy=" in n),
            "unknown",
        ),
        "contrast_relation": "partition_quintile_contrast",
        "objective_target_uncertainty": "episode_robustness",
        "information_gain_type": "falsify",
        "expected_epistemic_consequence_type": "falsify_episode_robustness",
    }
    overlap = row_overlap_fraction if row_overlap_fraction is not None else 0.0
    return decompose_novelty(
        first_spec=first_spec,
        first_identity=first_identity,
        first_target_null="episode_artifact",
        first_target_uncertainty="episode_robustness",
        second_spec=selected.experiment_spec or {},
        second_identity=dict(selected.scientific_identity),
        second_target_null=package.objective.target_null_key,
        second_target_uncertainty=package.objective.target_uncertainty,
        row_overlap_fraction=overlap,
    )


def validate_second_execution_eligibility(
    package: SecondExperimentPackage,
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    decision_envelope: FirstExperimentResearchDecisionEnvelope,
    executability: ExecutabilityContext,
    first_execution: Optional[FirstExperimentExecutionEnvelope] = None,
    existing_envelope: Optional[SecondExperimentExecutionEnvelope] = None,
    novelty_decomposition: Optional[NoveltyDecomposition] = None,
    row_overlap_fraction: Optional[float] = None,
    requested_tool_override: Optional[str] = None,
    binding_mutation: Optional[Dict[str, Any]] = None,
) -> Tuple[ExecutionEligibilityResult, Optional[NoveltyDecomposition]]:
    reasons: List[str] = []
    checks: Dict[str, bool] = {}

    checks["package_exists"] = package is not None
    if not checks["package_exists"]:
        return ExecutionEligibilityResult(ExecutionEligibility.INELIGIBLE.value, ("package_missing",), checks), None

    checks["experiment_ordinal_two"] = package.experiment_ordinal == 2
    checks["disposition_selected"] = package.disposition == SecondExperimentDisposition.SELECTED.value
    checks["execution_status_not_executed"] = package.execution_status == "NOT_EXECUTED"
    checks["selected_spec_present"] = bool(package.selected_experiment_spec)
    checks["selected_candidate_present"] = bool(package.selected_candidate_id)

    if package.experiment_ordinal != 2:
        reasons.append("experiment_ordinal_not_2")
    if package.disposition != SecondExperimentDisposition.SELECTED.value:
        reasons.append(f"disposition_not_selected:{package.disposition}")
    if package.execution_status != "NOT_EXECUTED" and existing_envelope is None:
        reasons.append(f"package_already_executed:{package.execution_status}")

    prop_hash = proposition_content_hash(prop)
    checks["proposition_id_matches"] = package.proposition_id == prop.get("proposition_id")
    checks["proposition_hash_matches"] = package.proposition_hash == prop_hash
    if not checks["proposition_id_matches"]:
        reasons.append("proposition_id_mismatch")

    rd = decision_envelope.research_decision
    checks["research_decision_hash_matches"] = package.research_decision_hash == str(rd.get("record_hash", ""))
    checks["decision_envelope_id_matches"] = package.research_decision_id == str(rd.get("decision_id", ""))
    if not checks["research_decision_hash_matches"]:
        reasons.append("research_decision_hash_mismatch")

    obj = package.objective
    checks["target_null_matches_objective"] = obj.target_null_key == package.objective.target_null_key
    selected_eval_null = obj.target_null_key
    checks["package_null_matches_decision_intent"] = bool(selected_eval_null)
    if obj.selected_action and "SEEK_FALSIFICATION" in obj.selected_action:
        checks["falsification_action_preserved"] = True
    else:
        checks["falsification_action_preserved"] = obj.selected_action != ""

    candidate = _find_selected_candidate(package)
    checks["candidate_record_found"] = candidate is not None
    if candidate:
        checks["target_null_candidate_matches"] = candidate.target_null_key == obj.target_null_key
        if candidate.target_null_key != obj.target_null_key:
            reasons.append("candidate_target_null_mismatch")

    decomp = novelty_decomposition or compute_novelty_for_execution(
        package=package,
        first_execution=first_execution,
        row_overlap_fraction=row_overlap_fraction,
    )
    checks["novelty_decomposition_present"] = decomp is not None
    if decomp is None:
        reasons.append("novelty_decomposition_unavailable")
    else:
        checks["not_scientific_redundancy"] = decomp.coarse_redundancy_interpretation != "SCIENTIFIC_REDUNDANCY"
        if decomp.coarse_redundancy_interpretation == "SCIENTIFIC_REDUNDANCY":
            reasons.append("scientific_redundancy_blocked")
        checks["null_target_overlap_zero_or_allowed"] = decomp.null_target_overlap == 0.0 or decomp.scientific_contrast_novelty == "HIGH"

    body = {
        "package_id": package.package_id,
        "proposition_id": package.proposition_id,
        "research_decision_hash": package.research_decision_hash,
        "disposition": package.disposition,
        "selected_candidate_id": package.selected_candidate_id,
        "experiment_ordinal": package.experiment_ordinal,
    }
    checks["package_hash_valid"] = stable_hash(body) == package.package_hash or bool(package.package_hash)
    if not package.package_hash:
        reasons.append("package_hash_missing")

    initial = second_package_to_initial_package(package)
    spec_dict = package.selected_experiment_spec or {}
    spec = ExperimentSpec.from_dict(spec_dict) if spec_dict else None

    if candidate:
        checks["candidate_executable"] = candidate.executability_status == "EXECUTABLE"
        if not checks["candidate_executable"]:
            reasons.append(f"candidate_not_executable:{candidate.executability_status}")
        checks["candidate_spec_matches_package"] = candidate.experiment_spec == spec_dict
        if not checks["candidate_spec_matches_package"]:
            reasons.append("candidate_spec_package_spec_mismatch")

    if spec:
        registry = build_default_tool_registry()
        checks["tool_in_registry"] = tool_is_executable(spec.tool_name, spec.tool_version, registry)
        if not checks["tool_in_registry"]:
            reasons.append(f"unsupported_tool:{spec.tool_name}")
        if requested_tool_override and requested_tool_override != spec.tool_name:
            checks["no_fallback_tool_substitution"] = False
            reasons.append(f"fallback_tool_rejected:{requested_tool_override}!={spec.tool_name}")
        else:
            checks["no_fallback_tool_substitution"] = True
        pop_ok, pop_detail = _population_representable(spec, panel, executability=executability)
        checks["population_representable"] = pop_ok
        if not pop_ok:
            reasons.append(pop_detail)
        scope = spec.research_scope or {}
        checks["outcome_spec_present"] = bool(scope.get("outcome_spec"))
        checks["population_spec_present"] = bool(scope.get("population_spec"))
        if binding_mutation:
            checks["no_binding_mutation"] = False
            reasons.append("binding_mutation_rejected")
        else:
            checks["no_binding_mutation"] = True

    exp_hash = compute_experiment_content_hash(spec) if spec else ""
    panel_hash = compute_panel_provenance_hash(panel, data_cutoff_date=executability.data_cutoff)
    exec_id_hash = (
        compute_execution_identity_hash(
            package_hash=package.package_hash,
            experiment_content_hash=exp_hash,
            panel_provenance_hash=panel_hash,
        )
        if spec
        else ""
    )

    if existing_envelope is not None:
        checks["idempotent_identity_match"] = (
            existing_envelope.execution_identity_hash == exec_id_hash
            and existing_envelope.package_hash == package.package_hash
        )
        if checks.get("idempotent_identity_match"):
            return ExecutionEligibilityResult(
                ExecutionEligibility.IDEMPOTENT_REPLAY.value,
                ("identical_execution_already_completed",),
                checks,
                gate_version=GATE_VERSION,
            ), decomp
        reasons.append("existing_envelope_identity_mismatch")

    material = [k for k in checks if k not in ("package_exists", "idempotent_identity_match")]
    passed = all(checks[k] for k in material)
    if passed:
        return ExecutionEligibilityResult(
            ExecutionEligibility.ELIGIBLE.value, tuple(), checks, gate_version=GATE_VERSION
        ), decomp

    return ExecutionEligibilityResult(
        ExecutionEligibility.INELIGIBLE.value, tuple(reasons), checks, gate_version=GATE_VERSION
    ), decomp
