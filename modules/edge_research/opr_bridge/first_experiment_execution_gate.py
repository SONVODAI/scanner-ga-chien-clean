"""
Phase 3J.3 — First-experiment execution eligibility gate (fail closed).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    GATE_VERSION,
    ExecutionEligibility,
    ExecutionEligibilityResult,
    FirstExperimentExecutionEnvelope,
)
from modules.edge_research.opr_bridge.first_experiment_records import (
    FirstExperimentDisposition,
    InitialExperimentPackage,
    PackageExecutionStatus,
)
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash
from modules.edge_research.opr_bridge.first_experiment_execution_tool_resolver import tool_is_executable
from modules.edge_research.research_tools import ToolRegistry, build_default_tool_registry


def compute_panel_provenance_hash(panel: pd.DataFrame, *, data_cutoff_date: str) -> str:
    return stable_hash(
        {
            "data_cutoff_date": data_cutoff_date,
            "row_count": len(panel),
            "columns": sorted(str(c) for c in panel.columns),
            "date_span": (
                str(panel["trade_date"].min()) if "trade_date" in panel.columns and len(panel) else "",
                str(panel["trade_date"].max()) if "trade_date" in panel.columns and len(panel) else "",
            ),
        }
    )


def compute_execution_identity_hash(
    *,
    package_hash: str,
    experiment_content_hash: str,
    panel_provenance_hash: str,
) -> str:
    return stable_hash(
        {
            "package_hash": package_hash,
            "experiment_content_hash": experiment_content_hash,
            "panel_provenance_hash": panel_provenance_hash,
        }
    )


def _find_selected_candidate(package: InitialExperimentPackage):
    if not package.selected_candidate_id:
        return None
    for c in package.deduplicated_candidates:
        if c.candidate_id == package.selected_candidate_id:
            return c
    for c in package.candidates_considered:
        if c.candidate_id == package.selected_candidate_id:
            return c
    return None


def _population_representable(
    spec: ExperimentSpec,
    panel: pd.DataFrame,
    *,
    executability: ExecutabilityContext,
) -> Tuple[bool, str]:
    scope = spec.research_scope or {}
    pop = scope.get("population_spec") or {}
    outcome = scope.get("outcome_spec") or {}
    outcome_field = outcome.get("field", "")
    required = {"trade_date", outcome_field}
    part_col = spec.inputs.get("partition_column")
    if part_col:
        required.add(str(part_col))
    if pop.get("kind") == "filter":
        required.add(str(pop.get("field", "trade_date")))
    missing = required - executability.panel_columns
    if missing and not executability.abstract_mode:
        return False, f"missing_panel_columns:{sorted(missing)}"
    if outcome_field and outcome_field not in panel.columns and not executability.abstract_mode:
        return False, f"outcome_field_not_in_panel:{outcome_field}"
    return True, "population_representable"


def validate_execution_eligibility(
    package: InitialExperimentPackage,
    prop: Dict[str, Any],
    panel: pd.DataFrame,
    *,
    executability: ExecutabilityContext,
    existing_envelope: Optional[FirstExperimentExecutionEnvelope] = None,
    requested_tool_override: Optional[str] = None,
    binding_mutation: Optional[Dict[str, Any]] = None,
) -> ExecutionEligibilityResult:
    """
    Explicit production execution gate — no silent conversion to executable.
    """
    reasons: List[str] = []
    checks: Dict[str, bool] = {}

    checks["package_exists"] = package is not None
    if not checks["package_exists"]:
        return ExecutionEligibilityResult(
            eligibility=ExecutionEligibility.INELIGIBLE.value,
            reasons=("package_missing",),
            checks=checks,
        )

    checks["disposition_selected"] = package.disposition == FirstExperimentDisposition.SELECTED.value
    if not checks["disposition_selected"]:
        reasons.append(f"disposition_not_selected:{package.disposition}")

    checks["selected_spec_present"] = bool(package.selected_experiment_spec)
    if not checks["selected_spec_present"]:
        reasons.append("no_selected_experiment_spec")

    checks["selected_candidate_present"] = bool(package.selected_candidate_id)
    if not checks["selected_candidate_present"]:
        reasons.append("no_selected_candidate_id")

    candidate = _find_selected_candidate(package)
    checks["candidate_record_found"] = candidate is not None
    if candidate is None and package.selected_candidate_id:
        reasons.append("selected_candidate_not_in_package")

    prop_hash = proposition_content_hash(prop)
    checks["proposition_id_matches"] = package.proposition_id == prop.get("proposition_id")
    checks["proposition_hash_matches"] = package.proposition_hash == prop_hash
    if not checks["proposition_id_matches"]:
        reasons.append("proposition_id_mismatch")
    if not checks["proposition_hash_matches"]:
        reasons.append("proposition_hash_mismatch")

    body = {
        "package_id": package.package_id,
        "proposition_id": package.proposition_id,
        "proposition_hash": package.proposition_hash,
        "disposition": package.disposition,
        "selected_candidate_id": package.selected_candidate_id,
        "candidate_hashes": sorted(c.record_hash for c in package.deduplicated_candidates),
    }
    checks["package_hash_recomputed"] = stable_hash(body) == package.package_hash
    if not checks["package_hash_recomputed"]:
        reasons.append("package_hash_mismatch")

    spec_dict = package.selected_experiment_spec or {}
    spec = ExperimentSpec.from_dict(spec_dict) if spec_dict else None
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
                eligibility=ExecutionEligibility.IDEMPOTENT_REPLAY.value,
                reasons=("identical_execution_already_completed",),
                checks=checks,
            )
        reasons.append("existing_envelope_identity_mismatch")

    already_executed = package.execution_status != PackageExecutionStatus.NOT_EXECUTED.value
    checks["execution_status_not_executed"] = not already_executed
    if already_executed and not existing_envelope:
        reasons.append(f"package_already_executed:{package.execution_status}")

    if candidate:
        checks["candidate_executable"] = candidate.executability_status == "EXECUTABLE"
        if not checks["candidate_executable"]:
            reasons.append(f"candidate_not_executable:{candidate.executability_status}")

        checks["candidate_spec_matches_package"] = candidate.experiment_spec == spec_dict
        if not checks["candidate_spec_matches_package"]:
            reasons.append("candidate_spec_package_spec_mismatch")

        checks["scientific_action_hash_intact"] = bool(candidate.scientific_action_core_hash)
        if spec_dict:
            cand_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(candidate.experiment_spec or {}))
            checks["experiment_content_hash_matches"] = cand_hash == exp_hash
            if not checks["experiment_content_hash_matches"]:
                reasons.append("experiment_content_hash_mismatch")

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
        if not checks["outcome_spec_present"]:
            reasons.append("missing_outcome_spec")

        checks["population_spec_present"] = bool(scope.get("population_spec"))
        if not checks["population_spec_present"]:
            reasons.append("missing_population_spec")

        if binding_mutation:
            checks["no_binding_mutation"] = False
            reasons.append("binding_mutation_rejected")
        else:
            checks["no_binding_mutation"] = True

        if candidate:
            pop = (scope.get("population_spec") or {}).get("kind")
            strat = candidate.scientific_identity.get("cohort_strategy", "")
            if strat == "episode_holdout_excluding_motivating" and pop == "all":
                checks["no_confirmatory_substitution"] = False
                reasons.append("confirmatory_full_panel_substitution_rejected")
            else:
                checks["no_confirmatory_substitution"] = True

    material_checks = [k for k in checks if k not in ("package_exists", "idempotent_identity_match")]
    passed = all(checks[k] for k in material_checks)

    if passed:
        return ExecutionEligibilityResult(
            eligibility=ExecutionEligibility.ELIGIBLE.value,
            reasons=tuple(),
            checks=checks,
        )

    return ExecutionEligibilityResult(
        eligibility=ExecutionEligibility.INELIGIBLE.value,
        reasons=tuple(reasons),
        checks=checks,
    )
