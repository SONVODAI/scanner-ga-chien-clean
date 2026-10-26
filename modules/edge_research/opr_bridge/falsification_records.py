"""
Phase 3I.9 — Falsification candidate records and selection outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.lifecycle_records import stable_hash, utc_now_iso, new_id

GENERATOR_VERSION = "falsification_candidate_generator_v1_3i9"
SELECTOR_VERSION = "lexicographic_falsification_selector_v1_3i9"
CANDIDATE_RECORD_VERSION = "falsification_candidate_record_v1_3i9"


class EvidenceIndependenceClass(str, Enum):
    SAME_FALSIFICATION_DIFFERENT_INSTRUMENT = "SAME_FALSIFICATION_DIFFERENT_INSTRUMENT"
    RELATED_FALSIFICATION = "RELATED_FALSIFICATION"
    INDEPENDENT_FALSIFICATION = "INDEPENDENT_FALSIFICATION"
    NOT_ACTUALLY_FALSIFICATION = "NOT_ACTUALLY_FALSIFICATION"


class VulnerabilityKind(str, Enum):
    DIRECTIONAL_REVERSAL = "directional_reversal"
    EPISODE_INSTABILITY = "episode_instability"
    POPULATION_CONCENTRATION = "population_concentration"
    CONTEXT_INSTABILITY = "context_instability"


class SelectionOutcome(str, Enum):
    SELECTED = "SELECTED"
    NO_VALID_FALSIFICATION_CANDIDATE = "NO_VALID_FALSIFICATION_CANDIDATE"
    AMBIGUOUS_TIE = "AMBIGUOUS_TIE"


@dataclass(frozen=True)
class PropositionVulnerability:
    kind: VulnerabilityKind
    description: str
    operational_basis: str
    motivating_episode_dates: Tuple[str, ...] = field(default_factory=tuple)
    directness_rank: int = 0


@dataclass(frozen=True)
class FalsificationCandidateRecord:
    candidate_id: str
    record_version: str
    proposition_id: str
    proposition_hash: str
    source_epistemic_update_id: str
    source_research_decision_id: str
    vulnerability_tested: str
    scientific_rationale: str
    possible_disconfirming_outcome: str
    possible_non_informative_outcome: str
    proposed_experiment_spec: Dict[str, Any]
    experiment_content_hash: str
    evidence_independence_class: str
    independence_rationale: str
    prior_experiment_content_hash: str
    content_hash_differs_from_prior: bool
    counterfactual_falsifiable: bool
    rescue_risk_status: str
    executability_status: str
    executability_detail: str
    leakage_cutoff_requirements: str
    lineage_refs: Dict[str, str]
    created_at: str
    generator_version: str
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "record_version": self.record_version,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "source_epistemic_update_id": self.source_epistemic_update_id,
            "source_research_decision_id": self.source_research_decision_id,
            "vulnerability_tested": self.vulnerability_tested,
            "scientific_rationale": self.scientific_rationale,
            "possible_disconfirming_outcome": self.possible_disconfirming_outcome,
            "possible_non_informative_outcome": self.possible_non_informative_outcome,
            "proposed_experiment_spec": dict(self.proposed_experiment_spec),
            "experiment_content_hash": self.experiment_content_hash,
            "evidence_independence_class": self.evidence_independence_class,
            "independence_rationale": self.independence_rationale,
            "prior_experiment_content_hash": self.prior_experiment_content_hash,
            "content_hash_differs_from_prior": self.content_hash_differs_from_prior,
            "counterfactual_falsifiable": self.counterfactual_falsifiable,
            "rescue_risk_status": self.rescue_risk_status,
            "executability_status": self.executability_status,
            "executability_detail": self.executability_detail,
            "leakage_cutoff_requirements": self.leakage_cutoff_requirements,
            "lineage_refs": dict(self.lineage_refs),
            "created_at": self.created_at,
            "generator_version": self.generator_version,
            "record_hash": self.record_hash,
        }


def build_candidate_record(
    *,
    proposition_id: str,
    proposition_hash: str,
    source_epistemic_update_id: str,
    source_research_decision_id: str,
    vulnerability_tested: str,
    scientific_rationale: str,
    possible_disconfirming_outcome: str,
    possible_non_informative_outcome: str,
    proposed_experiment_spec: Dict[str, Any],
    experiment_content_hash: str,
    evidence_independence_class: str,
    independence_rationale: str,
    prior_experiment_content_hash: str,
    counterfactual_falsifiable: bool,
    rescue_risk_status: str,
    executability_status: str,
    executability_detail: str,
    leakage_cutoff_requirements: str,
    lineage_refs: Dict[str, str],
    candidate_id: Optional[str] = None,
) -> FalsificationCandidateRecord:
    cid = candidate_id or new_id("fc")
    created = utc_now_iso()
    body = {
        "candidate_id": cid,
        "record_version": CANDIDATE_RECORD_VERSION,
        "proposition_id": proposition_id,
        "proposition_hash": proposition_hash,
        "source_epistemic_update_id": source_epistemic_update_id,
        "source_research_decision_id": source_research_decision_id,
        "vulnerability_tested": vulnerability_tested,
        "scientific_rationale": scientific_rationale,
        "possible_disconfirming_outcome": possible_disconfirming_outcome,
        "possible_non_informative_outcome": possible_non_informative_outcome,
        "proposed_experiment_spec": proposed_experiment_spec,
        "experiment_content_hash": experiment_content_hash,
        "evidence_independence_class": evidence_independence_class,
        "independence_rationale": independence_rationale,
        "prior_experiment_content_hash": prior_experiment_content_hash,
        "counterfactual_falsifiable": counterfactual_falsifiable,
        "rescue_risk_status": rescue_risk_status,
        "executability_status": executability_status,
        "leakage_cutoff_requirements": leakage_cutoff_requirements,
        "lineage_refs": lineage_refs,
        "generator_version": GENERATOR_VERSION,
    }
    return FalsificationCandidateRecord(
        candidate_id=cid,
        record_version=CANDIDATE_RECORD_VERSION,
        proposition_id=proposition_id,
        proposition_hash=proposition_hash,
        source_epistemic_update_id=source_epistemic_update_id,
        source_research_decision_id=source_research_decision_id,
        vulnerability_tested=vulnerability_tested,
        scientific_rationale=scientific_rationale,
        possible_disconfirming_outcome=possible_disconfirming_outcome,
        possible_non_informative_outcome=possible_non_informative_outcome,
        proposed_experiment_spec=proposed_experiment_spec,
        experiment_content_hash=experiment_content_hash,
        evidence_independence_class=evidence_independence_class,
        independence_rationale=independence_rationale,
        prior_experiment_content_hash=prior_experiment_content_hash,
        content_hash_differs_from_prior=experiment_content_hash != prior_experiment_content_hash,
        counterfactual_falsifiable=counterfactual_falsifiable,
        rescue_risk_status=rescue_risk_status,
        executability_status=executability_status,
        executability_detail=executability_detail,
        leakage_cutoff_requirements=leakage_cutoff_requirements,
        lineage_refs=lineage_refs,
        created_at=created,
        generator_version=GENERATOR_VERSION,
        record_hash=stable_hash(body),
    )
