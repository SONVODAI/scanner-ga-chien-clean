"""
Phase 3J.8 — Production second-experiment interpretation integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
    freeze_interpretation_contract_pre_result,
    frozen_ref_from_dict,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_persistence import (
    interpretation_envelope_from_dict,
)
from modules.edge_research.opr_bridge.second_experiment_design_persistence import package_from_dict
from modules.edge_research.opr_bridge.second_experiment_evidence_interpreter import (
    SecondExperimentInterpretationResult,
    interpret_second_experiment_evidence,
)
from modules.edge_research.opr_bridge.second_experiment_execution_persistence import envelope_from_dict
from modules.edge_research.opr_bridge.second_experiment_execution_records import STOP_SECOND_EXPERIMENT_EXECUTED
from modules.edge_research.opr_bridge.second_experiment_interpretation_persistence import (
    lookup_second_interpretation_by_identity,
    persist_second_interpretation_envelope,
)
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    FREEZE_POINT_PRE_RESULT_SECOND,
    INTERPRETER_VERSION,
    STOP_SECOND_EVIDENCE_INTERPRETED,
    compute_second_interpretation_identity_hash,
)

INTEGRATION_VERSION = "production_second_experiment_interpretation_v1_3j8"


@dataclass
class ProductionSecondExperimentInterpretationResult:
    integration_version: str = INTEGRATION_VERSION
    interpretation: Optional[SecondExperimentInterpretationResult] = None
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


def run_production_second_experiment_interpretation(
    prop: Dict[str, Any],
    *,
    session_id: str,
    package_dict: Dict[str, Any],
    execution_dict: Dict[str, Any],
    first_interpretation_dict: Dict[str, Any],
    frozen_contract_dict: Optional[Dict[str, Any]] = None,
    data_dir: Optional[Path] = None,
) -> ProductionSecondExperimentInterpretationResult:
    """
    STOP_SECOND_EXPERIMENT_EXECUTED → cumulative interpret → EpistemicUpdate #2 → STOP.
    """
    package = package_from_dict(package_dict)
    execution_envelope = envelope_from_dict(execution_dict)
    first_interpretation = interpretation_envelope_from_dict(first_interpretation_dict)

    if frozen_contract_dict:
        frozen_ref = frozen_ref_from_dict(frozen_contract_dict)
    else:
        frozen_ref = freeze_interpretation_contract_pre_result(
            prop,
            package_id=package.package_id,
            experiment_content_hash=execution_envelope.experiment_content_hash,
            scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
            freeze_point=FREEZE_POINT_PRE_RESULT_SECOND,
        )

    interp_id = compute_second_interpretation_identity_hash(
        contract_hash=frozen_ref.contract_hash,
        tool_result_hash=execution_envelope.tool_result_hash,
        execution_identity_hash=execution_envelope.execution_identity_hash,
        scientific_action_core_hash=execution_envelope.scientific_action_core_hash,
        first_interpretation_id=first_interpretation.interpretation_id,
        interpreter_version=INTERPRETER_VERSION,
    )
    cached = lookup_second_interpretation_by_identity(interp_id, data_dir=data_dir)

    result = interpret_second_experiment_evidence(
        prop,
        package,
        execution_envelope,
        first_interpretation,
        frozen_ref,
        session_id=session_id,
        existing_interpretation=cached,
    )

    idempotent = result.outcome == "IDEMPOTENT_REPLAY"
    if result.envelope and not idempotent:
        persist_second_interpretation_envelope(result.envelope, data_dir=data_dir)

    return ProductionSecondExperimentInterpretationResult(
        interpretation=result,
        frozen_contract_ref=frozen_ref.to_dict(),
        stop_boundaries=[STOP_SECOND_EXPERIMENT_EXECUTED, STOP_SECOND_EVIDENCE_INTERPRETED],
        idempotent_replay=idempotent,
    )
