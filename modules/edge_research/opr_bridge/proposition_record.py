"""
PropositionRecord v1 — frozen 3I.1 contract implementation (research-only).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.constants import OPR_GENERATOR_VERSION


class EpistemicStatus(str, Enum):
    HYPOTHESIS = "HYPOTHESIS"
    SUPPORTED = "SUPPORTED"
    WEAKENED = "WEAKENED"
    FALSIFIED = "FALSIFIED"
    ABANDONED = "ABANDONED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ExecutabilityStatus(str, Enum):
    EXECUTABLE = "EXECUTABLE"
    GRAMMAR_BLOCKED = "GRAMMAR_BLOCKED"
    TOOL_BLOCKED = "TOOL_BLOCKED"
    SAMPLE_INSUFFICIENT = "SAMPLE_INSUFFICIENT"
    NOT_EXECUTABLE = "NOT_EXECUTABLE"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


class TemplateClassification(str, Enum):
    TEMPLATE_INSTANCE = "TEMPLATE_INSTANCE"
    TEMPLATE_REFRAME = "TEMPLATE_REFRAME"
    TEMPLATE_ADJACENT = "TEMPLATE_ADJACENT"
    SCIENTIFICALLY_NOVEL = "SCIENTIFICALLY_NOVEL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


PROPOSITION_RECORD_VERSION = "proposition_record_v1"


@dataclass
class ObservationProvenance:
    evidence_anchor: Dict[str, Any]
    empirical_artifacts: Tuple[Dict[str, Any], ...]
    structural_context: Dict[str, Any]
    surprise_basis: str
    evidence_hash: str
    obs_codes_index: Tuple[str, ...] = ()
    gap_codes_index: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_anchor": dict(self.evidence_anchor),
            "empirical_artifacts": list(self.empirical_artifacts),
            "structural_context": dict(self.structural_context),
            "surprise_basis": self.surprise_basis,
            "evidence_hash": self.evidence_hash,
            "obs_codes_index": list(self.obs_codes_index),
            "gap_codes_index": list(self.gap_codes_index),
        }

    def passes_minimum_payload(self) -> bool:
        if not self.empirical_artifacts:
            return False
        if not self.surprise_basis or not self.surprise_basis.strip():
            return False
        if not self.evidence_hash:
            return False
        if not self.evidence_anchor.get("data_cutoff_date"):
            return False
        return True


@dataclass
class DisconfirmingObservationSpec:
    description: str
    operational_test: str
    threshold: str
    alternative_interpretation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "operational_test": self.operational_test,
            "threshold": self.threshold,
            "alternative_interpretation": self.alternative_interpretation,
        }


@dataclass
class BirthCertificateAnswer:
    question_id: str
    passed: bool
    answer: str

    def to_dict(self) -> Dict[str, Any]:
        return {"question_id": self.question_id, "passed": self.passed, "answer": self.answer}


@dataclass
class ScientificBirthCertificate:
    answers: Tuple[BirthCertificateAnswer, ...]

    def all_passed(self) -> bool:
        return all(a.passed for a in self.answers)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answers": [a.to_dict() for a in self.answers],
            "all_passed": self.all_passed(),
        }


@dataclass
class TemplateIndependenceResult:
    classification: TemplateClassification
    structural_match_score: float
    semantic_similarity: float
    best_template_match: str
    new_observational_axis_documented: bool
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification.value,
            "structural_match_score": self.structural_match_score,
            "semantic_similarity": self.semantic_similarity,
            "best_template_match": self.best_template_match,
            "new_observational_axis_documented": self.new_observational_axis_documented,
            "rationale": self.rationale,
        }


@dataclass
class PropositionRecord:
    proposition_id: str
    record_version: str
    created_at: str
    research_step: int
    generator_version: str
    observation_provenance: ObservationProvenance
    motivating_observation: str
    surprise_or_uncertainty: str
    scientific_question: str
    canonical_proposition_core: Dict[str, Any]
    population_context: Dict[str, Any]
    explanatory_relation: Dict[str, Any]
    outcome: Dict[str, Any]
    observation_horizon: int
    falsifiable_expectation: str
    null_competing_explanation: str
    disconfirming_observation_spec: DisconfirmingObservationSpec
    evidence_required: str
    execution_requirements: Dict[str, Any]
    epistemic_status: EpistemicStatus
    confidence: Confidence
    semantic_parent_id: Optional[str]
    generation_lineage: Tuple[str, ...]
    birth_certificate: ScientificBirthCertificate
    template_independence_audit: Optional[TemplateIndependenceResult] = None
    leakage_audit: Optional[Dict[str, Any]] = None
    executability_status: ExecutabilityStatus = ExecutabilityStatus.NOT_ATTEMPTED
    experiment_spec_draft: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposition_id": self.proposition_id,
            "record_version": self.record_version,
            "created_at": self.created_at,
            "research_step": self.research_step,
            "generator_version": self.generator_version,
            "observation_provenance": self.observation_provenance.to_dict(),
            "motivating_observation": self.motivating_observation,
            "surprise_or_uncertainty": self.surprise_or_uncertainty,
            "scientific_question": self.scientific_question,
            "canonical_proposition_core": dict(self.canonical_proposition_core),
            "population_context": dict(self.population_context),
            "explanatory_relation": dict(self.explanatory_relation),
            "outcome": dict(self.outcome),
            "observation_horizon": self.observation_horizon,
            "falsifiable_expectation": self.falsifiable_expectation,
            "null_competing_explanation": self.null_competing_explanation,
            "disconfirming_observation_spec": self.disconfirming_observation_spec.to_dict(),
            "evidence_required": self.evidence_required,
            "execution_requirements": dict(self.execution_requirements),
            "epistemic_status": self.epistemic_status.value,
            "confidence": self.confidence.value,
            "semantic_parent_id": self.semantic_parent_id,
            "generation_lineage": list(self.generation_lineage),
            "birth_certificate": self.birth_certificate.to_dict(),
            "template_independence_audit": (
                self.template_independence_audit.to_dict()
                if self.template_independence_audit
                else None
            ),
            "leakage_audit": self.leakage_audit,
            "executability_status": self.executability_status.value,
            "experiment_spec_draft": self.experiment_spec_draft,
        }

    def qualifies_as_autonomous(self) -> bool:
        if not self.observation_provenance.passes_minimum_payload():
            return False
        if not self.birth_certificate.all_passed():
            return False
        if self.template_independence_audit is None:
            return False
        cls = self.template_independence_audit.classification
        return cls in (
            TemplateClassification.TEMPLATE_ADJACENT,
            TemplateClassification.SCIENTIFICALLY_NOVEL,
        )


@dataclass
class NoPropositionEmitted:
    reason_code: str
    detail: str
    evidence_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": "NO_PROPOSITION_EMITTED",
            "reason_code": self.reason_code,
            "detail": self.detail,
            "evidence_hash": self.evidence_hash,
        }


def stable_proposition_id(core: Dict[str, Any], evidence_hash: str) -> str:
    payload = {"core": core, "evidence_hash": evidence_hash, "version": PROPOSITION_RECORD_VERSION}
    return "prop-" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
