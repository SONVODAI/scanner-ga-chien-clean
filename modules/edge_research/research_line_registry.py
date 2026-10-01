"""
Phase 3H.10 — Session-level semantic research-line registry.

Tracks scientific propositions, member experiments, and line-level gain history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.research_line_identity import (
    RESEARCH_LINE_IDENTITY_VERSION,
    ResearchLineIdentity,
    derive_identity_from_graph_experiment,
)
from modules.edge_research.research_line_relationship import (
    ResearchLineRelationship,
    best_relationship_to_registry,
    classify_research_line_relationship,
)

RESEARCH_LINE_REGISTRY_VERSION = "research_line_registry_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_line_id(proposition_key: str) -> str:
    return f"rl-{proposition_key[:12]}-{uuid.uuid4().hex[:8]}"


@dataclass
class ResearchLineRecord:
    research_line_id: str
    canonical_identity: Dict[str, Any]
    member_experiments: List[str] = field(default_factory=list)
    member_frames: List[str] = field(default_factory=list)
    uncertainty_codes: List[str] = field(default_factory=list)
    realized_gain_history: List[str] = field(default_factory=list)
    realized_gain_entries: List[Dict[str, Any]] = field(default_factory=list)
    relationship_history: List[Dict[str, Any]] = field(default_factory=list)
    assignment_history: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "active"
    last_evidence_update: str = field(default_factory=_utc_now)
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "research_line_id": self.research_line_id,
            "canonical_identity": dict(self.canonical_identity),
            "member_experiments": list(self.member_experiments),
            "member_frames": list(self.member_frames),
            "uncertainty_codes": list(self.uncertainty_codes),
            "realized_gain_history": list(self.realized_gain_history),
            "realized_gain_entries": list(self.realized_gain_entries),
            "relationship_history": list(self.relationship_history),
            "assignment_history": list(self.assignment_history),
            "status": self.status,
            "last_evidence_update": self.last_evidence_update,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchLineRecord":
        return cls(
            research_line_id=str(payload["research_line_id"]),
            canonical_identity=dict(payload.get("canonical_identity") or {}),
            member_experiments=list(payload.get("member_experiments") or []),
            member_frames=list(payload.get("member_frames") or []),
            uncertainty_codes=list(payload.get("uncertainty_codes") or []),
            realized_gain_history=list(payload.get("realized_gain_history") or []),
            realized_gain_entries=list(payload.get("realized_gain_entries") or []),
            relationship_history=list(payload.get("relationship_history") or []),
            assignment_history=list(payload.get("assignment_history") or []),
            status=str(payload.get("status", "active")),
            last_evidence_update=str(payload.get("last_evidence_update", _utc_now())),
            created_at=str(payload.get("created_at", _utc_now())),
        )


@dataclass
class ResearchLineRegistry:
    version: str
    lines: Dict[str, ResearchLineRecord] = field(default_factory=dict)
    experiment_to_line: Dict[str, str] = field(default_factory=dict)
    proposition_to_line: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "lines": {lid: rec.to_dict() for lid, rec in sorted(self.lines.items())},
            "experiment_to_line": dict(self.experiment_to_line),
            "proposition_to_line": dict(self.proposition_to_line),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchLineRegistry":
        lines_raw = payload.get("lines") or {}
        lines = {lid: ResearchLineRecord.from_dict(rec) for lid, rec in lines_raw.items()}
        return cls(
            version=str(payload.get("version", RESEARCH_LINE_REGISTRY_VERSION)),
            lines=lines,
            experiment_to_line=dict(payload.get("experiment_to_line") or {}),
            proposition_to_line=dict(payload.get("proposition_to_line") or {}),
        )


def get_registry(graph: Any) -> ResearchLineRegistry:
    raw = getattr(graph.session, "research_line_registry", None)
    if raw:
        return ResearchLineRegistry.from_dict(raw)
    return ResearchLineRegistry(version=RESEARCH_LINE_REGISTRY_VERSION)


def persist_registry(graph: Any, registry: ResearchLineRegistry) -> None:
    graph.session.research_line_registry = registry.to_dict()


def assign_experiment_to_line(
    graph: Any,
    *,
    experiment_node_id: str,
    identity: ResearchLineIdentity,
    gain_level: str = "",
    frame_id: str = "",
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Assign experiment to existing, related, or new research line.

    Returns (research_line_id, assignment_reason, relationship_audit).
    """
    registry = get_registry(graph)
    prop_key = identity.scientific_proposition_key()

    if experiment_node_id in registry.experiment_to_line:
        line_id = registry.experiment_to_line[experiment_node_id]
        return line_id, "already_assigned", {}

    if prop_key in registry.proposition_to_line:
        line_id = registry.proposition_to_line[prop_key]
        record = registry.lines[line_id]
        record.member_experiments.append(experiment_node_id)
        if frame_id and frame_id not in record.member_frames:
            record.member_frames.append(frame_id)
        for u in identity.uncertainty_codes:
            if u not in record.uncertainty_codes:
                record.uncertainty_codes.append(u)
        if gain_level:
            record.realized_gain_history.append(gain_level)
        record.last_evidence_update = _utc_now()
        record.assignment_history.append(
            {
                "experiment_node_id": experiment_node_id,
                "reason": "existing_semantic_line",
                "proposition_key": prop_key,
                "at": _utc_now(),
            }
        )
        registry.experiment_to_line[experiment_node_id] = line_id
        persist_registry(graph, registry)
        return line_id, "existing_semantic_line", {"classification": "IDENTICAL"}

    lines_dict = {lid: rec.to_dict() for lid, rec in registry.lines.items()}
    rel_audit = best_relationship_to_registry(identity, lines_dict)
    transfer_class = rel_audit.classification if rel_audit else ""

    if rel_audit and transfer_class in (
        ResearchLineRelationship.IDENTICAL.value,
        ResearchLineRelationship.NEAR_DUPLICATE.value,
        ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
        ResearchLineRelationship.SAME_LINE_NEW_EVIDENCE.value,
    ):
        line_id = rel_audit.prior_line_id
        record = registry.lines[line_id]
        record.member_experiments.append(experiment_node_id)
        if frame_id and frame_id not in record.member_frames:
            record.member_frames.append(frame_id)
        if gain_level:
            record.realized_gain_history.append(gain_level)
        record.relationship_history.append(rel_audit.to_dict())
        record.assignment_history.append(
            {
                "experiment_node_id": experiment_node_id,
                "reason": f"related_line:{transfer_class}",
                "proposition_key": prop_key,
                "at": _utc_now(),
            }
        )
        registry.experiment_to_line[experiment_node_id] = line_id
        registry.proposition_to_line[prop_key] = line_id
        persist_registry(graph, registry)
        return line_id, f"related_line:{transfer_class}", rel_audit.to_dict()

    if rel_audit and transfer_class == ResearchLineRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value:
        line_id = _new_line_id(prop_key)
        record = ResearchLineRecord(
            research_line_id=line_id,
            canonical_identity=identity.to_dict(),
            member_experiments=[experiment_node_id],
            member_frames=[frame_id] if frame_id else [],
            uncertainty_codes=list(identity.uncertainty_codes),
            realized_gain_history=[gain_level] if gain_level else [],
            relationship_history=[rel_audit.to_dict()],
            assignment_history=[
                {
                    "experiment_node_id": experiment_node_id,
                    "reason": "new_slice_line",
                    "related_line": rel_audit.prior_line_id,
                    "at": _utc_now(),
                }
            ],
        )
        registry.lines[line_id] = record
        registry.experiment_to_line[experiment_node_id] = line_id
        registry.proposition_to_line[prop_key] = line_id
        persist_registry(graph, registry)
        return line_id, "new_slice_line", rel_audit.to_dict()

    line_id = _new_line_id(prop_key)
    reason = "new_independent_line"
    if rel_audit and transfer_class == ResearchLineRelationship.GENUINELY_INDEPENDENT.value:
        reason = "genuinely_independent_line"
    elif rel_audit and transfer_class == ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value:
        reason = "insufficient_evidence_new_line"

    record = ResearchLineRecord(
        research_line_id=line_id,
        canonical_identity=identity.to_dict(),
        member_experiments=[experiment_node_id],
        member_frames=[frame_id] if frame_id else [],
        uncertainty_codes=list(identity.uncertainty_codes),
        realized_gain_history=[gain_level] if gain_level else [],
        relationship_history=[rel_audit.to_dict()] if rel_audit else [],
        assignment_history=[
            {
                "experiment_node_id": experiment_node_id,
                "reason": reason,
                "proposition_key": prop_key,
                "at": _utc_now(),
            }
        ],
    )
    registry.lines[line_id] = record
    registry.experiment_to_line[experiment_node_id] = line_id
    registry.proposition_to_line[prop_key] = line_id
    persist_registry(graph, registry)
    return line_id, reason, rel_audit.to_dict() if rel_audit else {}


def record_line_realized_gain(
    graph: Any,
    *,
    research_line_id: str,
    experiment_node_id: str,
    gain_level: str,
    gain_entry: Dict[str, Any],
) -> None:
    registry = get_registry(graph)
    record = registry.lines.get(research_line_id)
    if not record:
        return
    record.realized_gain_history.append(gain_level)
    record.realized_gain_entries.append(gain_entry)
    record.realized_gain_history = record.realized_gain_history[-20:]
    record.realized_gain_entries = record.realized_gain_entries[-20:]
    record.last_evidence_update = _utc_now()
    persist_registry(graph, registry)


def get_line_for_experiment(graph: Any, experiment_node_id: str) -> Optional[str]:
    registry = get_registry(graph)
    return registry.experiment_to_line.get(experiment_node_id)


def get_line_realized_gain_history(graph: Any, research_line_id: str) -> List[str]:
    registry = get_registry(graph)
    record = registry.lines.get(research_line_id)
    if not record:
        return []
    return list(record.realized_gain_history)


def assign_and_record_experiment_line(
    graph: Any,
    *,
    experiment_node_id: str,
    gain_level: str,
    gain_entry: Dict[str, Any],
    frame_id: str = "",
) -> Tuple[str, str, Dict[str, Any]]:
    """Post-experiment hook: derive identity, assign line, record gain."""
    identity = derive_identity_from_graph_experiment(graph, experiment_node_id)
    if identity is None:
        return "", "no_identity", {}
    line_id, reason, rel = assign_experiment_to_line(
        graph,
        experiment_node_id=experiment_node_id,
        identity=identity,
        gain_level=gain_level,
        frame_id=frame_id,
    )
    if line_id:
        record_line_realized_gain(
            graph,
            research_line_id=line_id,
            experiment_node_id=experiment_node_id,
            gain_level=gain_level,
            gain_entry=gain_entry,
        )
    return line_id, reason, rel


def resolve_line_for_candidate(
    graph: Any,
    identity: ResearchLineIdentity,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Resolve candidate to best matching line without assignment."""
    registry = get_registry(graph)
    prop_key = identity.scientific_proposition_key()
    if prop_key in registry.proposition_to_line:
        line_id = registry.proposition_to_line[prop_key]
        return line_id, {"classification": "IDENTICAL", "prior_line_id": line_id}
    lines_dict = {lid: rec.to_dict() for lid, rec in registry.lines.items()}
    rel = best_relationship_to_registry(identity, lines_dict)
    if rel:
        return rel.prior_line_id or None, rel.to_dict()
    return None, None
