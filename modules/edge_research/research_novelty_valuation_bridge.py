"""
Phase 3H.11 — Evidence-gated novelty valuation bridge.

Connects 3H.10 semantic relationship evidence to portfolio novelty_component
without changing planner weights or ERV scales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.research_line_decay_transfer import (
    SemanticMarginalEvidence,
    build_semantic_marginal_evidence,
)
from modules.edge_research.research_line_freshness import (
    EvidenceSnapshot,
    FreshnessClassification,
    assess_freshness,
)
from modules.edge_research.research_line_identity import (
    ResearchLineIdentity,
    derive_identity_from_candidate,
)
from modules.edge_research.research_line_relationship import ResearchLineRelationship
from modules.edge_research.research_realized_information_gain import (
    get_branch_realized_gain_history,
)

RESEARCH_NOVELTY_VALUATION_BRIDGE_VERSION = "research_novelty_valuation_bridge_v1"


class NoveltyValuationClass(str, Enum):
    REPRESENTATION_NOVELTY_ONLY = "REPRESENTATION_NOVELTY_ONLY"
    EVIDENCE_NOVELTY = "EVIDENCE_NOVELTY"
    SCIENTIFIC_NOVELTY = "SCIENTIFIC_NOVELTY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    LEGACY_NO_SEMANTIC_CONTEXT = "LEGACY_NO_SEMANTIC_CONTEXT"


@dataclass(frozen=True)
class NoveltyGatingAudit:
    version: str
    action_id: str
    valuation_class: str
    relationship_classification: str
    freshness_classification: str
    raw_novelty_component: float
    gated_novelty_component: float
    novelty_component_delta: float
    representation_novelty_only: bool
    scientific_novelty: bool
    evidence_novelty: bool
    gating_applied: bool
    component_explanation: str
    built_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "action_id": self.action_id,
            "valuation_class": self.valuation_class,
            "relationship_classification": self.relationship_classification,
            "freshness_classification": self.freshness_classification,
            "raw_novelty_component": self.raw_novelty_component,
            "gated_novelty_component": self.gated_novelty_component,
            "novelty_component_delta": self.novelty_component_delta,
            "representation_novelty_only": self.representation_novelty_only,
            "scientific_novelty": self.scientific_novelty,
            "evidence_novelty": self.evidence_novelty,
            "gating_applied": self.gating_applied,
            "component_explanation": self.component_explanation,
            "built_at": self.built_at,
        }


_REPRESENTATION_RELATIONSHIPS = frozenset(
    {
        ResearchLineRelationship.IDENTICAL.value,
        ResearchLineRelationship.NEAR_DUPLICATE.value,
        ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
    }
)

_SCIENTIFIC_PRESERVE_RELATIONSHIPS = frozenset(
    {
        ResearchLineRelationship.GENUINELY_INDEPENDENT.value,
        ResearchLineRelationship.RELATED_BUT_DISTINCT.value,
        ResearchLineRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value,
    }
)


def classify_novelty_valuation(
    semantic: SemanticMarginalEvidence,
) -> Tuple[str, str]:
    """Map semantic marginal evidence to novelty valuation class."""
    if semantic.evidence_novelty:
        return (
            NoveltyValuationClass.EVIDENCE_NOVELTY.value,
            "Fresh evidence available — preserve novelty contribution",
        )

    rel = semantic.relationship_classification
    if rel in _SCIENTIFIC_PRESERVE_RELATIONSHIPS or semantic.scientific_novelty:
        return (
            NoveltyValuationClass.SCIENTIFIC_NOVELTY.value,
            f"Scientific relationship {rel} — preserve novelty",
        )

    if rel in _REPRESENTATION_RELATIONSHIPS or semantic.representation_novelty_only:
        return (
            NoveltyValuationClass.REPRESENTATION_NOVELTY_ONLY.value,
            f"Representation-only change ({rel}) — zero novelty reward",
        )

    if rel == ResearchLineRelationship.SAME_LINE_NEW_EVIDENCE.value:
        return (
            NoveltyValuationClass.EVIDENCE_NOVELTY.value,
            "Same line with new evidence classification — preserve novelty",
        )

    return (
        NoveltyValuationClass.INSUFFICIENT_EVIDENCE.value,
        "Insufficient semantic evidence — fail closed, no gating",
    )


def gate_novelty_component(
    raw_novelty_component: float,
    *,
    valuation_class: str,
) -> float:
    """
    Apply evidence-gated novelty to portfolio layer only.

    Zero means removal of novelty bonus, never a penalty.
    """
    raw = max(0.0, float(raw_novelty_component))
    if valuation_class == NoveltyValuationClass.REPRESENTATION_NOVELTY_ONLY.value:
        return 0.0
    return raw


def build_semantic_context_for_candidate(
    graph: Any,
    candidate: Any,
    assessment: Any,
    *,
    branch_root_id: str = "",
    defer_snapshot: Optional[EvidenceSnapshot] = None,
    planning_sequence: int = 0,
) -> Tuple[Optional[SemanticMarginalEvidence], str]:
    """Build semantic marginal evidence + freshness for one candidate."""
    identity = derive_identity_from_candidate(
        candidate, graph=graph, branch_root_id=branch_root_id
    )
    if identity is None:
        return None, ""

    branch_levels = [
        e.get("gain_level", "UNRESOLVED")
        for e in get_branch_realized_gain_history(graph, branch_root_id)
    ]
    current_snap = EvidenceSnapshot.from_assessment(
        assessment, identity=identity, planning_sequence=planning_sequence
    )
    from modules.edge_research.research_line_registry import resolve_line_for_candidate

    line_id, _ = resolve_line_for_candidate(graph, identity)
    fresh = assess_freshness(
        identity=identity,
        research_line_id=line_id or "",
        defer_snapshot=defer_snapshot,
        current_snapshot=current_snap,
    )
    semantic = build_semantic_marginal_evidence(
        graph,
        candidate_identity=identity,
        branch_levels=branch_levels,
        branch_tools_attempted=tuple(getattr(assessment, "branch_tools_attempted", None) or ()),
        freshness_classification=fresh.classification,
        new_evidence_available=fresh.evidence_added_since_last_attempt,
    )
    return semantic, fresh.classification


def apply_novelty_valuation_bridge(
    graph: Any,
    candidate: Any,
    assessment: Any,
    *,
    raw_novelty_component: float,
    branch_root_id: str = "",
    defer_snapshot: Optional[EvidenceSnapshot] = None,
    planning_sequence: int = 0,
) -> Tuple[float, NoveltyGatingAudit]:
    """
    Gate portfolio novelty_component using 3H.10 semantic evidence.

    Returns (gated_novelty_component, audit).
    """
    action_id = getattr(candidate, "action_id", "")
    raw = max(0.0, float(raw_novelty_component))

    semantic, freshness = build_semantic_context_for_candidate(
        graph,
        candidate,
        assessment,
        branch_root_id=branch_root_id,
        defer_snapshot=defer_snapshot,
        planning_sequence=planning_sequence,
    )

    if semantic is None or not semantic.candidate_proposition_key:
        gated = raw
        audit = NoveltyGatingAudit(
            version=RESEARCH_NOVELTY_VALUATION_BRIDGE_VERSION,
            action_id=action_id,
            valuation_class=NoveltyValuationClass.LEGACY_NO_SEMANTIC_CONTEXT.value,
            relationship_classification="",
            freshness_classification=freshness,
            raw_novelty_component=raw,
            gated_novelty_component=gated,
            novelty_component_delta=0.0,
            representation_novelty_only=False,
            scientific_novelty=False,
            evidence_novelty=False,
            gating_applied=False,
            component_explanation="No candidate identity — legacy path",
        )
        return gated, audit

    valuation_class, explanation = classify_novelty_valuation(semantic)
    gated = gate_novelty_component(raw, valuation_class=valuation_class)
    gating_applied = gated != raw

    audit = NoveltyGatingAudit(
        version=RESEARCH_NOVELTY_VALUATION_BRIDGE_VERSION,
        action_id=action_id,
        valuation_class=valuation_class,
        relationship_classification=semantic.relationship_classification,
        freshness_classification=freshness,
        raw_novelty_component=raw,
        gated_novelty_component=gated,
        novelty_component_delta=gated - raw,
        representation_novelty_only=semantic.representation_novelty_only,
        scientific_novelty=semantic.scientific_novelty,
        evidence_novelty=semantic.evidence_novelty,
        gating_applied=gating_applied,
        component_explanation=explanation,
    )
    return gated, audit


def record_novelty_gating_audit(graph: Any, audit: NoveltyGatingAudit) -> None:
    trail = list(getattr(graph.session, "research_novelty_gating_audit", None) or [])
    trail.append(audit.to_dict())
    graph.session.research_novelty_gating_audit = trail[-300:]
