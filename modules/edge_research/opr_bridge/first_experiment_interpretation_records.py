"""
Phase 3J.4 — First-experiment evidence interpretation records (no research decision).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso

INTERPRETER_VERSION = "first_experiment_evidence_interpreter_v1_3j4"
FREEZE_VERSION = "first_experiment_contract_freeze_v1_3j4"
GATE_VERSION = "first_experiment_interpretation_gate_v1_3j4"
ENVELOPE_VERSION = "first_experiment_interpretation_envelope_v1_3j4"
STOP_FIRST_EVIDENCE_INTERPRETED = "STOP_FIRST_EVIDENCE_INTERPRETED"


class EvidenceRelevance(str, Enum):
    HIGH = "HIGH"
    PARTIAL = "PARTIAL"
    LOW = "LOW"
    NOT_ADDRESSED = "NOT_ADDRESSED"
    UNKNOWN = "UNKNOWN"


class EvidenceDirection(str, Enum):
    SUPPORTS = "SUPPORTS"
    WEAKENS = "WEAKENS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class EvidenceStrength(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"


class NullExplanationState(str, Enum):
    ADDRESSED = "ADDRESSED"
    WEAKENED = "WEAKENED"
    STILL_PLAUSIBLE = "STILL_PLAUSIBLE"
    STRENGTHENED = "STRENGTHENED"
    NOT_TESTED = "NOT_TESTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FrozenInterpretationContractRef:
    """Pre-result frozen InterpretationContract reference — authoritative for interpretation."""

    contract_dict: Dict[str, Any]
    contract_hash: str
    proposition_id: str
    proposition_hash: str
    package_id: str
    experiment_content_hash: str
    scientific_action_core_hash: str
    freeze_point: str
    freeze_version: str
    frozen_at: str
    ref_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_dict": dict(self.contract_dict),
            "contract_hash": self.contract_hash,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "package_id": self.package_id,
            "experiment_content_hash": self.experiment_content_hash,
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "freeze_point": self.freeze_point,
            "freeze_version": self.freeze_version,
            "frozen_at": self.frozen_at,
            "ref_hash": self.ref_hash,
        }


@dataclass(frozen=True)
class NullExplanationAccounting:
    null_explanation_text: str
    null_key: str
    state_before: str
    state_after: str
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "null_explanation_text": self.null_explanation_text,
            "null_key": self.null_key,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class IntentAwareEvidenceAssessment:
    """What evidence does and does not establish — separate dimensions, no scalar collapse."""

    experiment_intent_summary: str
    cohort_strategy: str
    target_uncertainty: str
    evidence_relevance: str
    evidence_direction: str
    evidence_strength: str
    remaining_uncertainty: Tuple[str, ...]
    other_nulls_still_alive: Tuple[str, ...]
    null_accounting: Tuple[NullExplanationAccounting, ...]
    base_evidence_class: str
    condition_matched: str
    limitations: Tuple[str, ...]
    tool_semantic_labels_ignored: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_intent_summary": self.experiment_intent_summary,
            "cohort_strategy": self.cohort_strategy,
            "target_uncertainty": self.target_uncertainty,
            "evidence_relevance": self.evidence_relevance,
            "evidence_direction": self.evidence_direction,
            "evidence_strength": self.evidence_strength,
            "remaining_uncertainty": list(self.remaining_uncertainty),
            "other_nulls_still_alive": list(self.other_nulls_still_alive),
            "null_accounting": [n.to_dict() for n in self.null_accounting],
            "base_evidence_class": self.base_evidence_class,
            "condition_matched": self.condition_matched,
            "limitations": list(self.limitations),
            "tool_semantic_labels_ignored": list(self.tool_semantic_labels_ignored),
        }


@dataclass(frozen=True)
class FirstExperimentInterpretationEnvelope:
    interpretation_id: str
    record_version: str
    execution_id: str
    execution_identity_hash: str
    tool_result_hash: str
    package_id: str
    package_hash: str
    proposition_id: str
    proposition_hash: str
    session_id: str
    scientific_action_core_hash: str
    frozen_contract_ref: FrozenInterpretationContractRef
    base_interpretation: Dict[str, Any]
    evidence_assessment: IntentAwareEvidenceAssessment
    epistemic_update: Dict[str, Any]
    prior_epistemic_state: str
    resulting_epistemic_state: str
    interpretation_identity_hash: str
    interpreter_version: str
    created_at: str
    envelope_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interpretation_id": self.interpretation_id,
            "record_version": self.record_version,
            "execution_id": self.execution_id,
            "execution_identity_hash": self.execution_identity_hash,
            "tool_result_hash": self.tool_result_hash,
            "package_id": self.package_id,
            "package_hash": self.package_hash,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "session_id": self.session_id,
            "scientific_action_core_hash": self.scientific_action_core_hash,
            "frozen_contract_ref": self.frozen_contract_ref.to_dict(),
            "base_interpretation": dict(self.base_interpretation),
            "evidence_assessment": self.evidence_assessment.to_dict(),
            "epistemic_update": dict(self.epistemic_update),
            "prior_epistemic_state": self.prior_epistemic_state,
            "resulting_epistemic_state": self.resulting_epistemic_state,
            "interpretation_identity_hash": self.interpretation_identity_hash,
            "interpreter_version": self.interpreter_version,
            "created_at": self.created_at,
            "envelope_hash": self.envelope_hash,
        }


def compute_interpretation_identity_hash(
    *,
    contract_hash: str,
    tool_result_hash: str,
    execution_identity_hash: str,
    scientific_action_core_hash: str,
    interpreter_version: str = INTERPRETER_VERSION,
) -> str:
    return stable_hash(
        {
            "contract_hash": contract_hash,
            "tool_result_hash": tool_result_hash,
            "execution_identity_hash": execution_identity_hash,
            "scientific_action_core_hash": scientific_action_core_hash,
            "interpreter_version": interpreter_version,
        }
    )


def build_interpretation_envelope(
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
    frozen_contract_ref: FrozenInterpretationContractRef,
    base_interpretation: Dict[str, Any],
    evidence_assessment: IntentAwareEvidenceAssessment,
    epistemic_update: Dict[str, Any],
    prior_epistemic_state: str,
    resulting_epistemic_state: str,
    interpretation_identity_hash: str,
) -> FirstExperimentInterpretationEnvelope:
    ts = utc_now_iso()
    iid = new_id("iefi")
    body = {
        "interpretation_id": iid,
        "interpretation_identity_hash": interpretation_identity_hash,
        "tool_result_hash": tool_result_hash,
        "contract_hash": frozen_contract_ref.contract_hash,
    }
    return FirstExperimentInterpretationEnvelope(
        interpretation_id=iid,
        record_version=ENVELOPE_VERSION,
        execution_id=execution_id,
        execution_identity_hash=execution_identity_hash,
        tool_result_hash=tool_result_hash,
        package_id=package_id,
        package_hash=package_hash,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        session_id=session_id,
        scientific_action_core_hash=scientific_action_core_hash,
        frozen_contract_ref=frozen_contract_ref,
        base_interpretation=base_interpretation,
        evidence_assessment=evidence_assessment,
        epistemic_update=epistemic_update,
        prior_epistemic_state=prior_epistemic_state,
        resulting_epistemic_state=resulting_epistemic_state,
        interpretation_identity_hash=interpretation_identity_hash,
        interpreter_version=INTERPRETER_VERSION,
        created_at=ts,
        envelope_hash=stable_hash(body),
    )
