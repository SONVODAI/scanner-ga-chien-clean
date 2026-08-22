"""
Phase 3I.19 — Research dormancy and reopening records.

Epistemic state and research activity state are intentionally separate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, new_id, utc_now_iso

DORMANCY_VERSION = "research_dormancy_v1_3i19"
REOPENING_CONDITION_VERSION = "reopening_condition_v1_3i19"


class ResearchActivityState(str, Enum):
    """Research budget activity — orthogonal to epistemic belief."""

    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"


class DormancyTrigger(str, Enum):
    NO_HIGH_INFORMATION_ACTION = "NO_HIGH_INFORMATION_ACTION"
    HOLD_PROVISIONALLY = "HOLD_PROVISIONALLY"
    FRONTIER_EXHAUSTED = "FRONTIER_EXHAUSTED"


class BlockingReasonType(str, Enum):
    COHORT_INDEPENDENCE_DEFICIT = "COHORT_INDEPENDENCE_DEFICIT"
    CAPABILITY_GAP = "CAPABILITY_GAP"
    AXIS_SATURATED = "AXIS_SATURATED"
    MARGINAL_INFORMATION_GATE = "MARGINAL_INFORMATION_GATE"
    EXECUTABILITY_BLOCKED = "EXECUTABILITY_BLOCKED"
    PRIORITY_HOLD = "PRIORITY_HOLD"


class RequiredScientificChange(str, Enum):
    MATERIAL_INDEPENDENCE_IMPROVEMENT = "MATERIAL_INDEPENDENCE_IMPROVEMENT"
    NEW_RELEVANT_OPERATOR = "NEW_RELEVANT_OPERATOR"
    EXECUTABILITY_RESTORATION = "EXECUTABILITY_RESTORATION"
    MAJOR_UNRESOLVED_ADDRESSABLE = "MAJOR_UNRESOLVED_ADDRESSABLE"
    UNCERTAINTY_RESOLVED = "UNCERTAINTY_RESOLVED"


class ForbiddenReopeningTrigger(str, Enum):
    OUTCOME_PROFITABILITY = "OUTCOME_PROFITABILITY"
    FUTURE_RETURN_MAGNITUDE = "FUTURE_RETURN_MAGNITUDE"
    ZONE_C_MATCH = "ZONE_C_MATCH"
    HUMAN_REVIEW_REQUEST = "HUMAN_REVIEW_REQUEST"
    LABEL_RENAME_ONLY = "LABEL_RENAME_ONLY"
    ROW_COUNT_ONLY = "ROW_COUNT_ONLY"
    CLOCK_ELAPSED = "CLOCK_ELAPSED"
    SUBGROUP_OUTCOME_MINING = "SUBGROUP_OUTCOME_MINING"
    KNOWN_HIDDEN_EDGE = "KNOWN_HIDDEN_EDGE"


class ReopeningEvaluationOutcome(str, Enum):
    REMAIN_DORMANT = "REMAIN_DORMANT"
    REOPEN_RESEARCH = "REOPEN_RESEARCH"
    NEW_PROPOSITION_REQUIRED = "NEW_PROPOSITION_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# Generic independence threshold — not tuned from T2; structural ceiling for "materially different"
DEFAULT_MATERIAL_OVERLAP_CEILING = 0.5


@dataclass(frozen=True)
class ReopeningConditionRecord:
    """Structured reopening requirement derived from scientific limitations."""

    condition_id: str
    target_uncertainty: str
    blocking_reason: str
    required_scientific_change: str
    measurable_criterion: Dict[str, Any]
    independence_requirement: str
    minimum_semantic_continuity: str
    does_not_qualify: Tuple[str, ...]
    provenance: Tuple[str, ...]
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "target_uncertainty": self.target_uncertainty,
            "blocking_reason": self.blocking_reason,
            "required_scientific_change": self.required_scientific_change,
            "measurable_criterion": dict(self.measurable_criterion),
            "independence_requirement": self.independence_requirement,
            "minimum_semantic_continuity": self.minimum_semantic_continuity,
            "does_not_qualify": list(self.does_not_qualify),
            "provenance": list(self.provenance),
            "record_hash": self.record_hash,
        }


@dataclass(frozen=True)
class ResearchDormancyRecord:
    """Append-only record: proposition epistemically alive, research budget inactive."""

    dormancy_id: str
    record_version: str
    proposition_id: str
    proposition_hash: str
    synthesis_hash: str
    frontier_assessment_hash: str
    epistemic_state_at_dormancy: str
    research_activity_state: str
    dormancy_trigger: str
    unresolved_uncertainties: Tuple[str, ...]
    blocked_axes: Tuple[str, ...]
    redundant_axes: Tuple[str, ...]
    dormancy_reason: str
    evidence_coverage: Tuple[str, ...]
    independence_limitations: Tuple[str, ...]
    reopening_conditions: Tuple[ReopeningConditionRecord, ...]
    forbidden_reopening_triggers: Tuple[str, ...]
    created_at: str
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dormancy_id": self.dormancy_id,
            "record_version": self.record_version,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "synthesis_hash": self.synthesis_hash,
            "frontier_assessment_hash": self.frontier_assessment_hash,
            "epistemic_state_at_dormancy": self.epistemic_state_at_dormancy,
            "research_activity_state": self.research_activity_state,
            "dormancy_trigger": self.dormancy_trigger,
            "unresolved_uncertainties": list(self.unresolved_uncertainties),
            "blocked_axes": list(self.blocked_axes),
            "redundant_axes": list(self.redundant_axes),
            "dormancy_reason": self.dormancy_reason,
            "evidence_coverage": list(self.evidence_coverage),
            "independence_limitations": list(self.independence_limitations),
            "reopening_conditions": [c.to_dict() for c in self.reopening_conditions],
            "forbidden_reopening_triggers": list(self.forbidden_reopening_triggers),
            "created_at": self.created_at,
            "record_hash": self.record_hash,
        }


@dataclass(frozen=True)
class ReopeningEvaluationResult:
    outcome: ReopeningEvaluationOutcome
    rationale: str
    satisfied_conditions: Tuple[str, ...] = field(default_factory=tuple)
    rejected_triggers: Tuple[str, ...] = field(default_factory=tuple)
    trigger_fingerprint: str = ""
    record_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "rationale": self.rationale,
            "satisfied_conditions": list(self.satisfied_conditions),
            "rejected_triggers": list(self.rejected_triggers),
            "trigger_fingerprint": self.trigger_fingerprint,
            "record_hash": self.record_hash,
        }


@dataclass
class ResearchMemoryLedger:
    """Append-only cross-session research memory for dormant propositions."""

    dormancy_records: List[ResearchDormancyRecord] = field(default_factory=list)
    reopening_evaluations: List[ReopeningEvaluationResult] = field(default_factory=list)
    seen_trigger_fingerprints: set = field(default_factory=set)

    def append_dormancy(self, record: ResearchDormancyRecord) -> None:
        self.dormancy_records.append(record)

    def append_evaluation(self, result: ReopeningEvaluationResult) -> None:
        self.reopening_evaluations.append(result)
        if result.trigger_fingerprint:
            self.seen_trigger_fingerprints.add(result.trigger_fingerprint)

    def latest_dormancy_for(self, proposition_id: str) -> Optional[ResearchDormancyRecord]:
        matches = [r for r in self.dormancy_records if r.proposition_id == proposition_id]
        return matches[-1] if matches else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dormancy_count": len(self.dormancy_records),
            "evaluation_count": len(self.reopening_evaluations),
            "proposition_ids": sorted({r.proposition_id for r in self.dormancy_records}),
        }


def build_reopening_condition(
    *,
    target_uncertainty: str,
    blocking_reason: str,
    required_scientific_change: str,
    measurable_criterion: Dict[str, Any],
    independence_requirement: str,
    does_not_qualify: Tuple[str, ...],
    provenance: Tuple[str, ...],
) -> ReopeningConditionRecord:
    cid = new_id("rc")
    body = {
        "version": REOPENING_CONDITION_VERSION,
        "target_uncertainty": target_uncertainty,
        "blocking_reason": blocking_reason,
        "required_scientific_change": required_scientific_change,
        "measurable_criterion": measurable_criterion,
        "independence_requirement": independence_requirement,
        "minimum_semantic_continuity": "same_proposition_hash_and_semantics",
        "does_not_qualify": does_not_qualify,
        "provenance": provenance,
    }
    return ReopeningConditionRecord(
        condition_id=cid,
        target_uncertainty=target_uncertainty,
        blocking_reason=blocking_reason,
        required_scientific_change=required_scientific_change,
        measurable_criterion=measurable_criterion,
        independence_requirement=independence_requirement,
        minimum_semantic_continuity="same_proposition_hash_and_semantics",
        does_not_qualify=does_not_qualify,
        provenance=provenance,
        record_hash=stable_hash(body),
    )


def dormancy_content_hash() -> str:
    return stable_hash({"version": DORMANCY_VERSION})


DEFAULT_FORBIDDEN_TRIGGERS: Tuple[str, ...] = tuple(t.value for t in ForbiddenReopeningTrigger)
