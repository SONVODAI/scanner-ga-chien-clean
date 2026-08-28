"""
Phase 3J.4 — First-experiment interpretation eligibility gate (fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import verify_frozen_contract_ref
from modules.edge_research.opr_bridge.first_experiment_execution_records import FirstExperimentExecutionEnvelope
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    GATE_VERSION,
    FirstExperimentInterpretationEnvelope,
    FrozenInterpretationContractRef,
    INTERPRETER_VERSION,
    compute_interpretation_identity_hash,
)
from modules.edge_research.opr_bridge.first_experiment_records import InitialExperimentPackage
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash


@dataclass(frozen=True)
class InterpretationEligibilityResult:
    eligible: bool
    idempotent_replay: bool
    reasons: Tuple[str, ...]
    checks: Dict[str, bool]
    interpretation_identity_hash: Optional[str] = None
    gate_version: str = GATE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible": self.eligible,
            "idempotent_replay": self.idempotent_replay,
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
            "interpretation_identity_hash": self.interpretation_identity_hash,
            "gate_version": self.gate_version,
        }


def validate_interpretation_eligibility(
    *,
    prop: Dict[str, Any],
    package: InitialExperimentPackage,
    execution_envelope: FirstExperimentExecutionEnvelope,
    frozen_contract_ref: FrozenInterpretationContractRef,
    existing_interpretation: Optional[FirstExperimentInterpretationEnvelope] = None,
    alternate_contract_hash: Optional[str] = None,
) -> InterpretationEligibilityResult:
    reasons: list[str] = []
    checks: Dict[str, bool] = {}

    checks["execution_envelope_present"] = execution_envelope is not None
    checks["frozen_contract_present"] = frozen_contract_ref is not None
    checks["package_present"] = package is not None

    if not checks["execution_envelope_present"]:
        return InterpretationEligibilityResult(False, False, ("no_execution_envelope",), checks)

    checks["tool_result_present"] = bool(execution_envelope.tool_result)
    checks["tool_result_hash_present"] = bool(execution_envelope.tool_result_hash)
    if not checks["tool_result_present"]:
        reasons.append("no_tool_result")

    prop_hash = proposition_content_hash(prop)
    checks["proposition_hash_matches"] = execution_envelope.proposition_hash == prop_hash
    checks["package_hash_matches"] = execution_envelope.package_hash == package.package_hash
    checks["package_id_matches"] = execution_envelope.package_id == package.package_id
    checks["scientific_action_hash_matches"] = (
        execution_envelope.scientific_action_core_hash == frozen_contract_ref.scientific_action_core_hash
    )
    checks["experiment_hash_matches"] = (
        execution_envelope.experiment_content_hash == frozen_contract_ref.experiment_content_hash
    )

    contract_ok, contract_errs = verify_frozen_contract_ref(frozen_contract_ref)
    checks["frozen_contract_integrity"] = contract_ok
    if not contract_ok:
        reasons.extend(contract_errs)

    if alternate_contract_hash and alternate_contract_hash != frozen_contract_ref.contract_hash:
        checks["no_post_result_contract_substitution"] = False
        reasons.append("post_result_contract_substitution_rejected")
    else:
        checks["no_post_result_contract_substitution"] = True

    interp_id = compute_interpretation_identity_hash(
        contract_hash=frozen_contract_ref.contract_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        interpreter_version=INTERPRETER_VERSION,
    )

    if existing_interpretation is not None:
        checks["idempotent_identity_match"] = (
            existing_interpretation.interpretation_identity_hash == interp_id
            and existing_interpretation.tool_result_hash == execution_envelope.tool_result_hash
        )
        if checks["idempotent_identity_match"]:
            return InterpretationEligibilityResult(
                True, True, ("identical_interpretation_already_completed",), checks, interp_id
            )
        reasons.append("existing_interpretation_identity_mismatch")

    material = [k for k in checks if k != "idempotent_identity_match"]
    eligible = all(checks[k] for k in material)
    if not eligible:
        failed = [k for k, v in checks.items() if not v and k != "idempotent_identity_match"]
        return InterpretationEligibilityResult(False, False, tuple(reasons or failed), checks, interp_id)

    return InterpretationEligibilityResult(True, False, tuple(), checks, interp_id)
