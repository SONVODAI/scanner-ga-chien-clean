"""
Phase 3J.4 — Production first-experiment evidence interpretation integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import frozen_ref_from_dict
from modules.edge_research.opr_bridge.first_experiment_evidence_interpreter import (
    FirstExperimentInterpretationResult,
    interpret_first_experiment_evidence,
)
from modules.edge_research.opr_bridge.first_experiment_execution_persistence import (
    envelope_from_dict,
    package_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    STOP_FIRST_EXPERIMENT_EXECUTED,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_persistence import (
    lookup_interpretation_by_identity,
    persist_interpretation_envelope,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    STOP_FIRST_EVIDENCE_INTERPRETED,
    compute_interpretation_identity_hash,
    INTERPRETER_VERSION,
)

INTEGRATION_VERSION = "production_first_experiment_interpretation_v1_3j4"


@dataclass
class ProductionFirstExperimentInterpretationResult:
    integration_version: str = INTEGRATION_VERSION
    interpretation: Optional[FirstExperimentInterpretationResult] = None
    frozen_contract_ref: Optional[Dict[str, Any]] = None
    stop_boundaries: List[str] = field(default_factory=list)
    idempotent_replay: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_version": self.integration_version,
            "interpretation": self.interpretation.to_dict() if self.interpretation else None,
            "frozen_contract_ref": self.frozen_contract_ref,
            "stop_boundaries": list(self.stop_boundaries),
            "idempotent_replay": self.idempotent_replay,
        }


def run_production_first_experiment_interpretation(
    prop: Dict[str, Any],
    *,
    session_id: str,
    package_dict: Dict[str, Any],
    execution_dict: Dict[str, Any],
    frozen_contract_dict: Optional[Dict[str, Any]] = None,
    data_dir: Optional[Path] = None,
    prior_epistemic_state: Optional[str] = None,
) -> ProductionFirstExperimentInterpretationResult:
    """
    STOP_FIRST_EXPERIMENT_EXECUTED → interpret → epistemic update → STOP_FIRST_EVIDENCE_INTERPRETED.
    """
    package = package_from_dict(package_dict)
    execution_envelope = envelope_from_dict(execution_dict)

    if not frozen_contract_dict:
        from modules.edge_research.opr_bridge.first_experiment_interpretation_gate import InterpretationEligibilityResult

        inelig = InterpretationEligibilityResult(
            False, False, ("missing_pre_result_frozen_contract",), {"frozen_contract_present": False}
        )
        return ProductionFirstExperimentInterpretationResult(
            interpretation=FirstExperimentInterpretationResult(
                outcome="NOT_ATTEMPTED",
                eligibility=inelig,
                envelope=None,
                stop_boundary=STOP_FIRST_EVIDENCE_INTERPRETED,
                errors=("missing_pre_result_frozen_contract",),
            ),
            stop_boundaries=[STOP_FIRST_EVIDENCE_INTERPRETED],
        )

    frozen_ref = frozen_ref_from_dict(frozen_contract_dict)

    interp_id = compute_interpretation_identity_hash(
        contract_hash=frozen_ref.contract_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        interpreter_version=INTERPRETER_VERSION,
    )
    cached = lookup_interpretation_by_identity(interp_id, data_dir=data_dir)
    existing = cached

    result = interpret_first_experiment_evidence(
        prop,
        package,
        execution_envelope,
        frozen_ref,
        session_id=session_id,
        prior_epistemic_state=prior_epistemic_state,
        existing_interpretation=existing,
    )

    idempotent = result.outcome == "IDEMPOTENT_REPLAY"
    if result.envelope and not idempotent:
        persist_interpretation_envelope(result.envelope, data_dir=data_dir)

    return ProductionFirstExperimentInterpretationResult(
        interpretation=result,
        frozen_contract_ref=frozen_ref.to_dict(),
        stop_boundaries=[STOP_FIRST_EXPERIMENT_EXECUTED, STOP_FIRST_EVIDENCE_INTERPRETED],
        idempotent_replay=idempotent,
    )
