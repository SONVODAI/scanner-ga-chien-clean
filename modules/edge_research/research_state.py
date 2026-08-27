"""
Research graph state contracts for Edge Research (PATCH 3A).

Memory + lineage substrate only — no planner, no edge search, no investment logic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.contracts import GUARDRAILS_CONFIG_VERSION

RESEARCH_GRAPH_SCHEMA_VERSION = "research_graph_v1"

SUPPORTED_RESEARCH_GRAPH_SCHEMA_VERSIONS: Tuple[str, ...] = (RESEARCH_GRAPH_SCHEMA_VERSION,)


class NodeType(str, Enum):
    OBSERVATION = "OBSERVATION"
    QUESTION = "QUESTION"
    EXPERIMENT = "EXPERIMENT"
    CONCLUSION = "CONCLUSION"
    FROZEN_HYPOTHESIS = "FROZEN_HYPOTHESIS"


class NodeStatus(str, Enum):
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    RESOLVED = "RESOLVED"
    ABANDONED = "ABANDONED"
    FROZEN = "FROZEN"


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETE = "COMPLETE"
    NO_EDGE_FOUND = "NO_EDGE_FOUND"
    RESEARCH_COMPLETE_WITH_CANDIDATES = "RESEARCH_COMPLETE_WITH_CANDIDATES"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    NO_VALID_FRONTIER = "NO_VALID_FRONTIER"
    INCOMPLETE = "INCOMPLETE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ResearchTrigger:
    """What caused an observation or question to exist."""

    kind: str
    source_node_id: Optional[str] = None
    description: str = ""
    source_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "source_node_id": self.source_node_id,
            "description": self.description,
            "source_metrics": dict(self.source_metrics),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchTrigger":
        return cls(
            kind=str(payload.get("kind", "")),
            source_node_id=payload.get("source_node_id"),
            description=str(payload.get("description", "")),
            source_metrics=dict(payload.get("source_metrics") or {}),
        )


@dataclass(frozen=True)
class QuestionRationale:
    """Why a question was chosen — structured, not prose-only reasoning."""

    reason_code: str
    prior_node_id: str
    evidence_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "prior_node_id": self.prior_node_id,
            "evidence_summary": dict(self.evidence_summary),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "QuestionRationale":
        return cls(
            reason_code=str(payload.get("reason_code", "")),
            prior_node_id=str(payload.get("prior_node_id", "")),
            evidence_summary=dict(payload.get("evidence_summary") or {}),
        )


@dataclass(frozen=True)
class ResearchQuestionContext:
    """
    Structured question frame — population + outcome specs and search accounting hooks.

    Answers: why did Bot ask this question?
    """

    population_spec: Dict[str, Any]
    outcome_spec: Dict[str, Any]
    research_depth: int = 0
    search_complexity: int = 0
    population_n: Optional[int] = None
    search_accounting: Dict[str, Any] = field(default_factory=dict)
    population_change: Optional[Dict[str, Any]] = None
    frame_id: str = ""
    observation_horizon: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "population_spec": dict(self.population_spec),
            "outcome_spec": dict(self.outcome_spec),
            "research_depth": self.research_depth,
            "search_complexity": self.search_complexity,
            "population_n": self.population_n,
            "search_accounting": dict(self.search_accounting),
            "population_change": dict(self.population_change) if self.population_change else None,
            "frame_id": self.frame_id,
            "observation_horizon": self.observation_horizon,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchQuestionContext":
        pc = payload.get("population_change")
        return cls(
            population_spec=dict(payload.get("population_spec") or {}),
            outcome_spec=dict(payload.get("outcome_spec") or {}),
            research_depth=int(payload.get("research_depth", 0)),
            search_complexity=int(payload.get("search_complexity", 0)),
            population_n=payload.get("population_n"),
            search_accounting=dict(payload.get("search_accounting") or {}),
            population_change=dict(pc) if pc else None,
            frame_id=str(payload.get("frame_id", "")),
            observation_horizon=int(payload.get("observation_horizon", 0)),
        )


@dataclass(frozen=True)
class ExperimentSpec:
    """Immutable experiment identity for deduplication and audit."""

    tool_name: str
    tool_version: str
    inputs: Dict[str, Any]
    research_scope: Dict[str, Any]
    data_cutoff_date: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "inputs": dict(self.inputs),
            "research_scope": dict(self.research_scope),
            "data_cutoff_date": self.data_cutoff_date,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExperimentSpec":
        return cls(
            tool_name=str(payload["tool_name"]),
            tool_version=str(payload.get("tool_version", "v1")),
            inputs=dict(payload.get("inputs") or {}),
            research_scope=dict(payload.get("research_scope") or {}),
            data_cutoff_date=str(payload["data_cutoff_date"]),
        )


@dataclass(frozen=True)
class StructuredResearchObservation:
    """Deterministic empirical description produced from experiment metrics."""

    code: str
    severity: str = "MEDIUM"
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StructuredResearchObservation":
        return cls(
            code=str(payload.get("code", "")),
            severity=str(payload.get("severity", "MEDIUM")),
            evidence=dict(payload.get("evidence") or {}),
        )


@dataclass(frozen=True)
class EvidenceReference:
    """Pointer to supporting or weakening evidence from a prior experiment."""

    experiment_node_id: str
    observation_codes: Tuple[str, ...] = field(default_factory=tuple)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_node_id": self.experiment_node_id,
            "observation_codes": list(self.observation_codes),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "EvidenceReference":
        return cls(
            experiment_node_id=str(payload.get("experiment_node_id", "")),
            observation_codes=tuple(payload.get("observation_codes") or ()),
            note=str(payload.get("note", "")),
        )


@dataclass(frozen=True)
class NextActionCandidate:
    """Recorded candidate next action — not scored or chosen by PATCH 3A."""

    action_code: str
    tool_name: Optional[str] = None
    rationale: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_code": self.action_code,
            "tool_name": self.tool_name,
            "rationale": self.rationale,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "NextActionCandidate":
        return cls(
            action_code=str(payload.get("action_code", "")),
            tool_name=payload.get("tool_name"),
            rationale=str(payload.get("rationale", "")),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ExperimentResult:
    """Deterministic tool output attached to an experiment node."""

    metrics: Dict[str, Any]
    result_hash: str
    observations: Tuple[StructuredResearchObservation, ...] = field(default_factory=tuple)
    finalized: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics": dict(self.metrics),
            "result_hash": self.result_hash,
            "observations": [o.to_dict() for o in self.observations],
            "finalized": self.finalized,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExperimentResult":
        return cls(
            metrics=dict(payload.get("metrics") or {}),
            result_hash=str(payload.get("result_hash", "")),
            observations=tuple(
                StructuredResearchObservation.from_dict(o)
                for o in (payload.get("observations") or [])
            ),
            finalized=bool(payload.get("finalized", True)),
        )


def compute_experiment_content_hash(spec: ExperimentSpec) -> str:
    """
    Deterministic identity hash for experiment deduplication.

    Excludes timestamps, node IDs, prose formatting, and result values.
    """
    canonical = json.dumps(
        {
            "tool_name": spec.tool_name,
            "tool_version": spec.tool_version,
            "inputs": _normalize_for_hash(spec.inputs),
            "research_scope": _normalize_for_hash(spec.research_scope),
            "data_cutoff_date": spec.data_cutoff_date,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_result_hash(metrics: Dict[str, Any]) -> str:
    """Reproducible hash of deterministic experiment metrics."""
    canonical = json.dumps(
        _normalize_for_hash(metrics),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _normalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_for_hash(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_hash(v) for v in value]
    if isinstance(value, float):
        return round(value, 12)
    return value


@dataclass
class ResearchSession:
    research_session_id: str
    started_at: str
    data_cutoff_date: str
    guardrails_config_version: str
    status: SessionStatus
    root_node_ids: List[str] = field(default_factory=list)
    experiment_budget: Optional[int] = None
    experiments_used: int = 0
    schema_version: str = RESEARCH_GRAPH_SCHEMA_VERSION
    search_accounting: Dict[str, Any] = field(default_factory=dict)
    research_frontier: Dict[str, Any] = field(default_factory=dict)
    session_stop_reason: Optional[Dict[str, Any]] = None
    panel_preflight: Optional[Dict[str, Any]] = None
    research_frames: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "research_session_id": self.research_session_id,
            "started_at": self.started_at,
            "data_cutoff_date": self.data_cutoff_date,
            "guardrails_config_version": self.guardrails_config_version,
            "status": self.status.value,
            "root_node_ids": list(self.root_node_ids),
            "experiment_budget": self.experiment_budget,
            "experiments_used": self.experiments_used,
            "schema_version": self.schema_version,
        }
        if self.search_accounting:
            payload["search_accounting"] = dict(self.search_accounting)
        if self.research_frontier:
            payload["research_frontier"] = dict(self.research_frontier)
        if self.session_stop_reason:
            payload["session_stop_reason"] = dict(self.session_stop_reason)
        if self.panel_preflight:
            payload["panel_preflight"] = dict(self.panel_preflight)
        if self.research_frames:
            payload["research_frames"] = dict(self.research_frames)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchSession":
        return cls(
            research_session_id=str(payload["research_session_id"]),
            started_at=str(payload["started_at"]),
            data_cutoff_date=str(payload["data_cutoff_date"]),
            guardrails_config_version=str(
                payload.get("guardrails_config_version", GUARDRAILS_CONFIG_VERSION)
            ),
            status=SessionStatus(str(payload.get("status", SessionStatus.ACTIVE.value))),
            root_node_ids=list(payload.get("root_node_ids") or []),
            experiment_budget=payload.get("experiment_budget"),
            experiments_used=int(payload.get("experiments_used", 0)),
            schema_version=str(payload.get("schema_version", RESEARCH_GRAPH_SCHEMA_VERSION)),
            search_accounting=dict(payload.get("search_accounting") or {}),
            research_frontier=dict(payload.get("research_frontier") or {}),
            session_stop_reason=dict(payload["session_stop_reason"])
            if payload.get("session_stop_reason")
            else None,
            panel_preflight=dict(payload["panel_preflight"]) if payload.get("panel_preflight") else None,
            research_frames=dict(payload.get("research_frames") or {}),
        )


@dataclass
class ResearchNode:
    node_id: str
    session_id: str
    node_type: NodeType
    status: NodeStatus
    created_at: str
    parent_node_ids: List[str] = field(default_factory=list)
    child_node_ids: List[str] = field(default_factory=list)
    completed_at: Optional[str] = None
    trigger: Optional[ResearchTrigger] = None
    question_text: str = ""
    rationale: Optional[QuestionRationale] = None
    question_context: Optional[ResearchQuestionContext] = None
    experiment_spec: Optional[ExperimentSpec] = None
    experiment_content_hash: Optional[str] = None
    experiment_result: Optional[ExperimentResult] = None
    evidence_for: List[EvidenceReference] = field(default_factory=list)
    evidence_against: List[EvidenceReference] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    candidate_next_actions: List[NextActionCandidate] = field(default_factory=list)
    selected_next_action: Optional[NextActionCandidate] = None
    terminal_reason: str = ""
    frozen_spec_ref: Optional[Dict[str, Any]] = None
    revisit_allowed: bool = False
    research_status: str = ""
    candidate_summary: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "session_id": self.session_id,
            "node_type": self.node_type.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "parent_node_ids": list(self.parent_node_ids),
            "child_node_ids": list(self.child_node_ids),
            "completed_at": self.completed_at,
            "trigger": self.trigger.to_dict() if self.trigger else None,
            "question_text": self.question_text,
            "rationale": self.rationale.to_dict() if self.rationale else None,
            "question_context": self.question_context.to_dict() if self.question_context else None,
            "experiment_spec": self.experiment_spec.to_dict() if self.experiment_spec else None,
            "experiment_content_hash": self.experiment_content_hash,
            "experiment_result": self.experiment_result.to_dict() if self.experiment_result else None,
            "evidence_for": [e.to_dict() for e in self.evidence_for],
            "evidence_against": [e.to_dict() for e in self.evidence_against],
            "uncertainties": list(self.uncertainties),
            "candidate_next_actions": [a.to_dict() for a in self.candidate_next_actions],
            "selected_next_action": (
                self.selected_next_action.to_dict() if self.selected_next_action else None
            ),
            "terminal_reason": self.terminal_reason,
            "frozen_spec_ref": dict(self.frozen_spec_ref) if self.frozen_spec_ref else None,
            "revisit_allowed": self.revisit_allowed,
            "research_status": self.research_status,
            "candidate_summary": dict(self.candidate_summary) if self.candidate_summary else None,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchNode":
        trigger = payload.get("trigger")
        rationale = payload.get("rationale")
        qctx = payload.get("question_context")
        spec = payload.get("experiment_spec")
        result = payload.get("experiment_result")
        selected = payload.get("selected_next_action")
        frozen = payload.get("frozen_spec_ref")
        return cls(
            node_id=str(payload["node_id"]),
            session_id=str(payload["session_id"]),
            node_type=NodeType(str(payload["node_type"])),
            status=NodeStatus(str(payload["status"])),
            created_at=str(payload["created_at"]),
            parent_node_ids=list(payload.get("parent_node_ids") or []),
            child_node_ids=list(payload.get("child_node_ids") or []),
            completed_at=payload.get("completed_at"),
            trigger=ResearchTrigger.from_dict(trigger) if trigger else None,
            question_text=str(payload.get("question_text", "")),
            rationale=QuestionRationale.from_dict(rationale) if rationale else None,
            question_context=ResearchQuestionContext.from_dict(qctx) if qctx else None,
            experiment_spec=ExperimentSpec.from_dict(spec) if spec else None,
            experiment_content_hash=payload.get("experiment_content_hash"),
            experiment_result=ExperimentResult.from_dict(result) if result else None,
            evidence_for=[
                EvidenceReference.from_dict(e) for e in (payload.get("evidence_for") or [])
            ],
            evidence_against=[
                EvidenceReference.from_dict(e) for e in (payload.get("evidence_against") or [])
            ],
            uncertainties=list(payload.get("uncertainties") or []),
            candidate_next_actions=[
                NextActionCandidate.from_dict(a)
                for a in (payload.get("candidate_next_actions") or [])
            ],
            selected_next_action=NextActionCandidate.from_dict(selected) if selected else None,
            terminal_reason=str(payload.get("terminal_reason", "")),
            frozen_spec_ref=dict(frozen) if frozen else None,
            revisit_allowed=bool(payload.get("revisit_allowed", False)),
            research_status=str(payload.get("research_status", "")),
            candidate_summary=dict(payload.get("candidate_summary")) if payload.get("candidate_summary") else None,
        )


@dataclass
class ResearchGraphSnapshot:
    """Serializable full graph state for one session."""

    schema_version: str
    session: ResearchSession
    nodes: Dict[str, ResearchNode]
    experiment_index: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session": self.session.to_dict(),
            "nodes": {nid: n.to_dict() for nid, n in sorted(self.nodes.items())},
            "experiment_index": dict(sorted(self.experiment_index.items())),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchGraphSnapshot":
        schema_version = str(payload.get("schema_version", ""))
        if schema_version not in SUPPORTED_RESEARCH_GRAPH_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported research graph schema version: {schema_version!r}. "
                f"Supported: {SUPPORTED_RESEARCH_GRAPH_SCHEMA_VERSIONS}"
            )
        nodes_raw = payload.get("nodes") or {}
        return cls(
            schema_version=schema_version,
            session=ResearchSession.from_dict(payload["session"]),
            nodes={nid: ResearchNode.from_dict(n) for nid, n in nodes_raw.items()},
            experiment_index=dict(payload.get("experiment_index") or {}),
        )

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)

    @classmethod
    def deserialize(cls, text: str) -> "ResearchGraphSnapshot":
        return cls.from_dict(json.loads(text))
