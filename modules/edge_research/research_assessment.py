"""
Research assessment contracts for Edge Research (PATCH 3C).

Structured interpretation layer — no planner, no investment semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Tuple


class DescriptiveStrength(str, Enum):
    INSUFFICIENT = "INSUFFICIENT"
    NO_VARIATION = "NO_VARIATION"
    NO_CLEAR_DIFFERENCE = "NO_CLEAR_DIFFERENCE"
    GROUP_DIFFERENCE = "GROUP_DIFFERENCE"


class InterpretationConfidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class ResearchAssessment:
    """Deterministic interpretation of tool output within branch context."""

    source_experiment_node_id: str
    tool_name: str
    tool_status: str

    empirical_findings: Tuple[str, ...] = field(default_factory=tuple)
    unresolved_uncertainties: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)
    concentration_concerns: Tuple[str, ...] = field(default_factory=tuple)
    replication_concerns: Tuple[str, ...] = field(default_factory=tuple)
    fragility_evidence: Tuple[str, ...] = field(default_factory=tuple)
    context_dependence: Tuple[str, ...] = field(default_factory=tuple)
    horizon_dependence: Tuple[str, ...] = field(default_factory=tuple)
    information_gaps: Tuple[str, ...] = field(default_factory=tuple)
    possible_falsification_targets: Tuple[str, ...] = field(default_factory=tuple)

    descriptive_strength: str = DescriptiveStrength.INSUFFICIENT.value
    interpretation_confidence: str = InterpretationConfidence.LOW.value
    additional_investigation_warranted: bool = False
    interesting: bool = False
    validated: bool = False
    actionable: bool = False

    branch_tools_attempted: Tuple[str, ...] = field(default_factory=tuple)
    branch_observation_codes: Tuple[str, ...] = field(default_factory=tuple)
    observation_kind: str = ""
    conditional_candidate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_experiment_node_id": self.source_experiment_node_id,
            "tool_name": self.tool_name,
            "tool_status": self.tool_status,
            "empirical_findings": list(self.empirical_findings),
            "unresolved_uncertainties": list(self.unresolved_uncertainties),
            "contradictions": list(self.contradictions),
            "concentration_concerns": list(self.concentration_concerns),
            "replication_concerns": list(self.replication_concerns),
            "fragility_evidence": list(self.fragility_evidence),
            "context_dependence": list(self.context_dependence),
            "horizon_dependence": list(self.horizon_dependence),
            "information_gaps": list(self.information_gaps),
            "possible_falsification_targets": list(self.possible_falsification_targets),
            "descriptive_strength": self.descriptive_strength,
            "interpretation_confidence": self.interpretation_confidence,
            "additional_investigation_warranted": self.additional_investigation_warranted,
            "interesting": self.interesting,
            "validated": self.validated,
            "actionable": self.actionable,
            "branch_tools_attempted": list(self.branch_tools_attempted),
            "branch_observation_codes": list(self.branch_observation_codes),
            "observation_kind": self.observation_kind,
            "conditional_candidate": self.conditional_candidate,
        }
