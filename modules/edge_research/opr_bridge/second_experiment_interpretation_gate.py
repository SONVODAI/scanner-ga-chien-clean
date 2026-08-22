"""
Phase 3J.8 — Second-experiment interpretation eligibility gate (history-aware, fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import verify_frozen_contract_ref
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FirstExperimentInterpretationEnvelope,
    FrozenInterpretationContractRef,
)
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.opr_bridge.second_experiment_execution_records import SecondExperimentExecutionEnvelope
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    GATE_VERSION,
    INTERPRETER_VERSION,
    SecondExperimentInterpretationEnvelope,
    compute_second_interpretation_identity_hash,
)
from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentPackage


@dataclass(frozen=True)
class SecondInterpretationEligibilityResult:
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


def validate_second_interpretation_eligibility(
    *,
    prop: Dict[str, Any],
    package: SecondExperimentPackage,
    execution_envelope: SecondExperimentExecutionEnvelope,
    first_interpretation: FirstExperimentInterpretationEnvelope,
    frozen_contract_ref: FrozenInterpretationContractRef,
    existing_interpretation: Optional[SecondExperimentInterpretationEnvelope] = None,
    alternate_contract_hash: Optional[str] = None,
    expected_ordinal: int = 2,
) -> SecondInterpretationEligibilityResult:
    reasons: list[str] = []
    checks: Dict[str, bool] = {}

    checks["execution_envelope_present"] = execution_envelope is not None
    checks["first_interpretation_present"] = first_interpretation is not None
    checks["frozen_contract_present"] = frozen_contract_ref is not None
    checks["package_present"] = package is not None

    if not checks["execution_envelope_present"]:
        return SecondInterpretationEligibilityResult(False, False, ("no_execution_envelope",), checks)

    checks["experiment_ordinal_two"] = execution_envelope.experiment_ordinal == expected_ordinal
    checks["tool_result_present"] = bool(execution_envelope.tool_result)
    checks["tool_result_hash_present"] = bool(execution_envelope.tool_result_hash)
    checks["novelty_decomposition_present"] = bool(execution_envelope.novelty_decomposition)

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
    checks["first_interpretation_proposition_matches"] = first_interpretation.proposition_id == prop.get(
        "proposition_id"
    )
    checks["first_execution_lineage"] = execution_envelope.first_execution_id == first_interpretation.execution_id

    contract_ok, contract_errs = verify_frozen_contract_ref(frozen_contract_ref)
    checks["frozen_contract_integrity"] = contract_ok
    if not contract_ok:
        reasons.extend(contract_errs)

    if alternate_contract_hash and alternate_contract_hash != frozen_contract_ref.contract_hash:
        checks["no_post_result_contract_substitution"] = False
        reasons.append("post_result_contract_substitution_rejected")
    else:
        checks["no_post_result_contract_substitution"] = True

    interp_id = compute_second_interpretation_identity_hash(
        contract_hash=frozen_contract_ref.contract_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        first_interpretation_id=first_interpretation.interpretation_id,
        interpreter_version=INTERPRETER_VERSION,
    )

    if existing_interpretation is not None:
        checks["idempotent_identity_match"] = (
            existing_interpretation.interpretation_identity_hash == interp_id
            and existing_interpretation.tool_result_hash == execution_envelope.tool_result_hash
        )
        if checks["idempotent_identity_match"]:
            return SecondInterpretationEligibilityResult(
                True, True, ("identical_interpretation_already_completed",), checks, interp_id
            )
        reasons.append("existing_interpretation_identity_mismatch")

    material = [k for k in checks if k != "idempotent_identity_match"]
    eligible = all(checks[k] for k in material)
    if not eligible:
        failed = [k for k, v in checks.items() if not v and k != "idempotent_identity_match"]
        return SecondInterpretationEligibilityResult(False, False, tuple(reasons or failed), checks, interp_id)

    return SecondInterpretationEligibilityResult(True, False, tuple(), checks, interp_id)
