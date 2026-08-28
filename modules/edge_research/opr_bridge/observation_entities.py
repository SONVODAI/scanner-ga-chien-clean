"""
Phase 3I.5 — Observation / proposition / evidence entity model.

Separates three entities:
  OBSERVATION EVENT — empirical anomaly at a focal date
  SCIENTIFIC PROPOSITION — underlying scientific uncertainty
  EVIDENCE EVENT — motivation/support/contradiction for a proposition
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_ingest import DispersionEvidencePayload
from modules.edge_research.opr_bridge.surprise_detector import SurpriseAssessment


@dataclass(frozen=True)
class ObservationEvent:
    """A specific empirical anomaly at a specific evidence cutoff/date."""

    focal_date: str
    data_cutoff_date: str
    evidence: DispersionEvidencePayload
    surprise: SurpriseAssessment

    @property
    def evidence_hash(self) -> str:
        return self.evidence.evidence_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": "OBSERVATION_EVENT",
            "focal_date": self.focal_date,
            "data_cutoff_date": self.data_cutoff_date,
            "evidence_hash": self.evidence_hash,
            "is_surprising": self.surprise.is_surprising,
            "quintile_spread": self.evidence.quintile_return_spread,
            "cross_sectional_n": self.evidence.cross_sectional_n,
            "zscore_vs_baseline": self.surprise.zscore_vs_baseline,
        }


@dataclass(frozen=True)
class EvidenceEvent:
    """Observation providing motivation/support/contradiction for a proposition."""

    observation_event: ObservationEvent
    role: str  # SUPPORT | CONTRADICT | NEUTRAL
    contrast_direction: str
    empirical_delta: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": "EVIDENCE_EVENT",
            "focal_date": self.observation_event.focal_date,
            "evidence_hash": self.observation_event.evidence_hash,
            "role": self.role,
            "contrast_direction": self.contrast_direction,
            "empirical_delta": self.empirical_delta,
        }


@dataclass
class ScientificPropositionGroup:
    """Underlying scientific uncertainty with aggregated evidence lineage."""

    identity_key: str
    scientific_question: str
    uncertainty_family: str
    population_spec: Dict[str, Any]
    outcome_spec: Dict[str, Any]
    observation_horizon: int
    feature: str
    relation_type: str
    evidence_events: List[EvidenceEvent] = field(default_factory=list)
    representative: Optional[ObservationEvent] = None

    @property
    def independent_evidence_count(self) -> int:
        return len(self.evidence_events)

    @property
    def has_contradiction(self) -> bool:
        directions = {e.contrast_direction for e in self.evidence_events if e.contrast_direction != "flat"}
        return len(directions) > 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": "SCIENTIFIC_PROPOSITION_GROUP",
            "identity_key": self.identity_key,
            "scientific_question": self.scientific_question,
            "uncertainty_family": self.uncertainty_family,
            "feature": self.feature,
            "relation_type": self.relation_type,
            "independent_evidence_count": self.independent_evidence_count,
            "has_contradiction": self.has_contradiction,
            "representative_focal_date": (
                self.representative.focal_date if self.representative else None
            ),
            "evidence_events": [e.to_dict() for e in self.evidence_events],
        }
