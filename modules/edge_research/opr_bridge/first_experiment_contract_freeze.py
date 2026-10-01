"""
Phase 3J.4 — Pre-result InterpretationContract freeze (before ToolResult interpretation).
"""

from __future__ import annotations

from typing import Any, Dict

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FREEZE_VERSION,
    FrozenInterpretationContractRef,
)
from modules.edge_research.opr_bridge.interpretation_contract import (
    build_interpretation_contract,
    contract_hash_payload,
    interpretation_contract_from_dict,
    proposition_content_hash,
)

FREEZE_POINT_PRE_EXECUTION = "PRE_EXECUTION"
FREEZE_POINT_PACKAGE_SELECTED = "PACKAGE_SELECTED"


def freeze_interpretation_contract_pre_result(
    prop: Dict[str, Any],
    *,
    package_id: str,
    experiment_content_hash: str,
    scientific_action_core_hash: str,
    freeze_point: str = FREEZE_POINT_PRE_EXECUTION,
) -> FrozenInterpretationContractRef:
    """
    Freeze InterpretationContract from proposition commitments only.

    MUST be invoked before ToolResult is read for interpretation.
    """
    contract = build_interpretation_contract(prop)
    contract_dict = contract.to_dict()
    prop_hash = proposition_content_hash(prop)
    frozen_at = utc_now_iso()
    body = {
        "contract_hash": contract.contract_hash,
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop_hash,
        "package_id": package_id,
        "experiment_content_hash": experiment_content_hash,
        "scientific_action_core_hash": scientific_action_core_hash,
        "freeze_point": freeze_point,
        "freeze_version": FREEZE_VERSION,
        "frozen_at": frozen_at,
    }
    return FrozenInterpretationContractRef(
        contract_dict=contract_dict,
        contract_hash=contract.contract_hash,
        proposition_id=prop["proposition_id"],
        proposition_hash=prop_hash,
        package_id=package_id,
        experiment_content_hash=experiment_content_hash,
        scientific_action_core_hash=scientific_action_core_hash,
        freeze_point=freeze_point,
        freeze_version=FREEZE_VERSION,
        frozen_at=frozen_at,
        ref_hash=stable_hash(body),
    )


def frozen_ref_from_historical_contract_artifact(
    contract_artifact: Dict[str, Any],
    *,
    package_id: str,
    experiment_content_hash: str,
    scientific_action_core_hash: str,
) -> FrozenInterpretationContractRef:
    """Load pre-result contract from historical artifact — no rebuild."""
    return FrozenInterpretationContractRef(
        contract_dict=dict(contract_artifact),
        contract_hash=str(contract_artifact["contract_hash"]),
        proposition_id=str(contract_artifact["proposition_id"]),
        proposition_hash=str(contract_artifact["proposition_hash"]),
        package_id=package_id,
        experiment_content_hash=experiment_content_hash,
        scientific_action_core_hash=scientific_action_core_hash,
        freeze_point="HISTORICAL_ARTIFACT_PRE_RESULT",
        freeze_version=FREEZE_VERSION,
        frozen_at=str(contract_artifact.get("frozen_at", utc_now_iso())),
        ref_hash=stable_hash(
            {
                "contract_hash": contract_artifact["contract_hash"],
                "package_id": package_id,
                "experiment_content_hash": experiment_content_hash,
                "scientific_action_core_hash": scientific_action_core_hash,
                "source": "historical_artifact",
            }
        ),
    )


def frozen_ref_from_dict(payload: Dict[str, Any]) -> FrozenInterpretationContractRef:
    return FrozenInterpretationContractRef(
        contract_dict=dict(payload["contract_dict"]),
        contract_hash=str(payload["contract_hash"]),
        proposition_id=str(payload["proposition_id"]),
        proposition_hash=str(payload["proposition_hash"]),
        package_id=str(payload["package_id"]),
        experiment_content_hash=str(payload["experiment_content_hash"]),
        scientific_action_core_hash=str(payload["scientific_action_core_hash"]),
        freeze_point=str(payload["freeze_point"]),
        freeze_version=str(payload.get("freeze_version", FREEZE_VERSION)),
        frozen_at=str(payload["frozen_at"]),
        ref_hash=str(payload["ref_hash"]),
    )


def verify_frozen_contract_ref(ref: FrozenInterpretationContractRef) -> tuple[bool, tuple[str, ...]]:
    """Verify frozen contract integrity — fail closed on mismatch."""
    errors: list[str] = []
    loaded = interpretation_contract_from_dict(ref.contract_dict)
    if loaded.contract_hash != ref.contract_hash:
        errors.append("contract_hash_mismatch")
    recomputed = stable_hash(contract_hash_payload(ref.contract_dict))
    if recomputed != ref.contract_hash and ref.contract_dict.get("contract_hash") != ref.contract_hash:
        errors.append("contract_hash_recomputed_mismatch")
    if loaded.proposition_id != ref.proposition_id:
        errors.append("proposition_id_mismatch")
    if loaded.proposition_hash != ref.proposition_hash:
        errors.append("proposition_hash_mismatch")
    return len(errors) == 0, tuple(errors)


def load_authoritative_contract(ref: FrozenInterpretationContractRef):
    """Load contract from frozen ref only — never rebuild from prop post-result."""
    ok, errs = verify_frozen_contract_ref(ref)
    if not ok:
        raise ValueError(f"Frozen contract ref invalid: {errs}")
    return interpretation_contract_from_dict(ref.contract_dict)
