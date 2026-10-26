"""
Phase 3I.7 — Lifecycle record types (append-only, research-only).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

LIFECYCLE_VERSION = "opr_lifecycle_v1_3i7"


class EvidenceClass(str, Enum):
    SUPPORTING = "SUPPORTING"
    DISCONFIRMING = "DISCONFIRMING"
    CONTRADICTORY = "CONTRADICTORY"
    NON_INFORMATIVE = "NON_INFORMATIVE"
    INVALID = "INVALID"


class NextResearchAction(str, Enum):
    SEEK_REPLICATION = "SEEK_REPLICATION"
    SEEK_FALSIFICATION = "SEEK_FALSIFICATION"
    HOLD_UNRESOLVED = "HOLD_UNRESOLVED"
    ABANDON = "ABANDON"


@dataclass(frozen=True)
class QuintileMetrics:
    """Pre-registered quintile extraction — same semantics as OPR evidence ingest."""

    quintile_means: Tuple[float, ...]
    quintile_ns: Tuple[int, ...]
    low_quintile_mean: float
    high_quintile_mean: float
    quintile_mean_spread: float
    low_high_delta: float
    sample_size: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quintile_means": list(self.quintile_means),
            "quintile_ns": list(self.quintile_ns),
            "low_quintile_mean": self.low_quintile_mean,
            "high_quintile_mean": self.high_quintile_mean,
            "quintile_mean_spread": self.quintile_mean_spread,
            "low_high_delta": self.low_high_delta,
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class InterpretationContract:
    """Frozen before ToolResult interpretation."""

    contract_version: str
    proposition_id: str
    proposition_hash: str
    contrast_direction: str
    partition_column: str
    outcome_field: str
    min_sample: int
    spread_support_floor: float
    spread_disconfirm_ceiling: float
    expected_direction_rule: str
    supporting_rule: str
    disconfirming_rule: str
    falsify_strong_rule: str
    non_informative_rule: str
    contradictory_rule: str
    invalid_rule: str
    transition_mapping: Dict[str, str]
    decision_mapping: Dict[str, str]
    abandon_requires: str
    frozen_at: str
    contract_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "contrast_direction": self.contrast_direction,
            "partition_column": self.partition_column,
            "outcome_field": self.outcome_field,
            "min_sample": self.min_sample,
            "spread_support_floor": self.spread_support_floor,
            "spread_disconfirm_ceiling": self.spread_disconfirm_ceiling,
            "expected_direction_rule": self.expected_direction_rule,
            "supporting_rule": self.supporting_rule,
            "disconfirming_rule": self.disconfirming_rule,
            "falsify_strong_rule": self.falsify_strong_rule,
            "non_informative_rule": self.non_informative_rule,
            "contradictory_rule": self.contradictory_rule,
            "invalid_rule": self.invalid_rule,
            "transition_mapping": dict(self.transition_mapping),
            "decision_mapping": dict(self.decision_mapping),
            "abandon_requires": self.abandon_requires,
            "frozen_at": self.frozen_at,
            "contract_hash": self.contract_hash,
        }


@dataclass(frozen=True)
class InterpretationResult:
    evidence_class: EvidenceClass
    metrics_used: Dict[str, Any]
    condition_matched: str
    validity_passed: bool
    validity_failures: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_class": self.evidence_class.value,
            "metrics_used": dict(self.metrics_used),
            "condition_matched": self.condition_matched,
            "validity_passed": self.validity_passed,
            "validity_failures": list(self.validity_failures),
        }


@dataclass(frozen=True)
class EpistemicUpdateRecord:
    update_id: str
    proposition_id: str
    prior_epistemic_state: str
    resulting_epistemic_state: str
    evidence_class: str
    experiment_ref: str
    tool_result_hash: str
    metrics_used: Dict[str, Any]
    condition_matched: str
    unresolved_uncertainty: str
    created_at: str
    lifecycle_version: str
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "update_id": self.update_id,
            "proposition_id": self.proposition_id,
            "prior_epistemic_state": self.prior_epistemic_state,
            "resulting_epistemic_state": self.resulting_epistemic_state,
            "evidence_class": self.evidence_class,
            "experiment_ref": self.experiment_ref,
            "tool_result_hash": self.tool_result_hash,
            "metrics_used": dict(self.metrics_used),
            "condition_matched": self.condition_matched,
            "unresolved_uncertainty": self.unresolved_uncertainty,
            "created_at": self.created_at,
            "lifecycle_version": self.lifecycle_version,
            "record_hash": self.record_hash,
        }


@dataclass(frozen=True)
class ResearchDecisionRecord:
    decision_id: str
    proposition_id: str
    epistemic_update_id: str
    prior_epistemic_state: str
    resulting_epistemic_state: str
    evidence_considered: List[Dict[str, Any]]
    unresolved_uncertainty: str
    candidate_next_actions: List[Dict[str, str]]
    chosen_next_action: str
    reason: str
    rejected_alternatives: List[Dict[str, str]]
    created_at: str
    lifecycle_version: str
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "proposition_id": self.proposition_id,
            "epistemic_update_id": self.epistemic_update_id,
            "prior_epistemic_state": self.prior_epistemic_state,
            "resulting_epistemic_state": self.resulting_epistemic_state,
            "evidence_considered": list(self.evidence_considered),
            "unresolved_uncertainty": self.unresolved_uncertainty,
            "candidate_next_actions": list(self.candidate_next_actions),
            "chosen_next_action": self.chosen_next_action,
            "reason": self.reason,
            "rejected_alternatives": list(self.rejected_alternatives),
            "created_at": self.created_at,
            "lifecycle_version": self.lifecycle_version,
            "record_hash": self.record_hash,
        }


def stable_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
