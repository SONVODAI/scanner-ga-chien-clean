"""
Phase 3J.8 — Second-experiment multi-evidence interpretation records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    FrozenInterpretationContractRef,
    IntentAwareEvidenceAssessment,
)
from modules.edge_research.opr_bridge.multi_evidence_accounting import CumulativeEvidenceAssessment

INTERPRETER_VERSION = "second_experiment_evidence_interpreter_v1_3j8"
GATE_VERSION = "second_experiment_interpretation_gate_v1_3j8"
ENVELOPE_VERSION = "second_experiment_interpretation_envelope_v1_3j8"
STOP_SECOND_EVIDENCE_INTERPRETED = "STOP_SECOND_EVIDENCE_INTERPRETED"
FREEZE_POINT_PRE_RESULT_SECOND = "PRE_RESULT_SECOND_EXPERIMENT"


@dataclass(frozen=True)
class SecondExperimentInterpretationEnvelope:
    interpretation_id: str
    record_version: str
    experiment_ordinal: int
    execution_id: str
    execution_identity_hash: str
    tool_result_hash: str
    package_id: str
    package_hash: str
    proposition_id: str
    proposition_hash: str
    session_id: str
    scientific_action_core_hash: str
    first_interpretation_id: str
    first_execution_id: str
    frozen_contract_ref: FrozenInterpretationContractRef
    base_interpretation: Dict[str, Any]
    evidence_assessment: IntentAwareEvidenceAssessment
    cumulative_assessment: CumulativeEvidenceAssessment
    epistemic_update: Dict[str, Any]
    prior_epistemic_state: str
    resulting_epistemic_state: str
    interpretation_identity_hash: str
    interpreter_version: str
    research_decision_generated: bool
    created_at: str
    envelope_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interpretation_id": self.interpretation_id,
            "record_version": self.record_version,
            "experiment_ordinal": self.experiment_ordinal,
            "execution_id": self.execution_id,
            "execution_identity_hash": self.execution_identity_hash,
            "tool_result_hash": self.tool_result_hash,
            "package_id": self.package_id,
            "package_hash": self.package_hash,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "session_id": self.session_id,
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "first_interpretation_id": self.first_interpretation_id,
            "first_execution_id": self.first_execution_id,
            "frozen_contract_ref": self.frozen_contract_ref.to_dict(),
            "base_interpretation": dict(self.base_interpretation),
            "evidence_assessment": self.evidence_assessment.to_dict(),
            "cumulative_assessment": self.cumulative_assessment.to_dict(),
            "epistemic_update": dict(self.epistemic_update),
            "prior_epistemic_state": self.prior_epistemic_state,
            "resulting_epistemic_state": self.resulting_epistemic_state,
            "interpretation_identity_hash": self.interpretation_identity_hash,
            "interpreter_version": self.interpreter_version,
            "research_decision_generated": self.research_decision_generated,
            "created_at": self.created_at,
            "envelope_hash": self.envelope_hash,
        }


def compute_second_interpretation_identity_hash(
    *,
    contract_hash: str,
    tool_result_hash: str,
    execution_identity_hash: str,
    scientific_action_core_hash: str,
    first_interpretation_id: str,
    interpreter_version: str = INTERPRETER_VERSION,
) -> str:
    return stable_hash(
        {
            "contract_hash": contract_hash,
            "tool_result_hash": tool_result_hash,
            "execution_identity_hash": execution_identity_hash,
            "scientific_action_core_hash": scientific_action_core_hash,
            "first_interpretation_id": first_interpretation_id,
            "interpreter_version": interpreter_version,
        }
    )


def build_second_interpretation_envelope(
    *,
    execution_id: str,
    execution_identity_hash: str,
    tool_result_hash: str,
    package_id: str,
    package_hash: str,
    proposition_id: str,
    proposition_hash: str,
    session_id: str,
    scientific_action_core_hash: str,
    first_interpretation_id: str,
    first_execution_id: str,
    frozen_contract_ref: FrozenInterpretationContractRef,
    base_interpretation: Dict[str, Any],
    evidence_assessment: IntentAwareEvidenceAssessment,
    cumulative_assessment: CumulativeEvidenceAssessment,
    epistemic_update: Dict[str, Any],
    prior_epistemic_state: str,
    resulting_epistemic_state: str,
    interpretation_identity_hash: str,
    experiment_ordinal: int = 2,
) -> SecondExperimentInterpretationEnvelope:
    ts = utc_now_iso()
    iid = new_id("iefi2")
    body = {
        "interpretation_id": iid,
        "interpretation_identity_hash": interpretation_identity_hash,
        "tool_result_hash": tool_result_hash,
        "contract_hash": frozen_contract_ref.contract_hash,
        "first_interpretation_id": first_interpretation_id,
    }
    return SecondExperimentInterpretationEnvelope(
        interpretation_id=iid,
        record_version=ENVELOPE_VERSION,
        experiment_ordinal=experiment_ordinal,
        execution_id=execution_id,
        execution_identity_hash=execution_identity_hash,
        tool_result_hash=tool_result_hash,
        package_id=package_id,
        package_hash=package_hash,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        session_id=session_id,
        scientific_action_core_hash=scientific_action_core_hash,
        first_interpretation_id=first_interpretation_id,
        first_execution_id=first_execution_id,
        frozen_contract_ref=frozen_contract_ref,
        base_interpretation=base_interpretation,
        evidence_assessment=evidence_assessment,
        cumulative_assessment=cumulative_assessment,
        epistemic_update=epistemic_update,
        prior_epistemic_state=prior_epistemic_state,
        resulting_epistemic_state=resulting_epistemic_state,
        interpretation_identity_hash=interpretation_identity_hash,
        interpreter_version=INTERPRETER_VERSION,
        research_decision_generated=False,
        created_at=ts,
        envelope_hash=stable_hash(body),
    )
