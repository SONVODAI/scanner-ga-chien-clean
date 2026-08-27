"""
Phase 3H.10 — Evidence-based marginal decay transfer across semantic equivalents.

No global decay. No blanket branch-root decay. Fail-closed on insufficient evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.research_line_freshness import FreshnessClassification
from modules.edge_research.research_line_identity import ResearchLineIdentity
from modules.edge_research.research_line_registry import (
    get_line_realized_gain_history,
    get_registry,
    resolve_line_for_candidate,
)
from modules.edge_research.research_line_relationship import (
    ResearchLineRelationship,
    classify_research_line_relationship,
)

RESEARCH_LINE_DECAY_TRANSFER_VERSION = "research_line_decay_transfer_v1"


@dataclass(frozen=True)
class SemanticMarginalEvidence:
    """Auditable semantic marginal evidence fed into 3H.8 marginal state."""

    version: str
    candidate_proposition_key: str
    matched_line_id: str
    relationship_classification: str
    transfer_allowed: bool
    branch_realized_levels: Tuple[str, ...]
    line_realized_levels: Tuple[str, ...]
    merged_realized_levels: Tuple[str, ...]
    freshness_classification: str
    component_explanations: Dict[str, str]
    representation_novelty_only: bool
    scientific_novelty: bool
    evidence_novelty: bool
    built_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "candidate_proposition_key": self.candidate_proposition_key,
            "matched_line_id": self.matched_line_id,
            "relationship_classification": self.relationship_classification,
            "transfer_allowed": self.transfer_allowed,
            "branch_realized_levels": list(self.branch_realized_levels),
            "line_realized_levels": list(self.line_realized_levels),
            "merged_realized_levels": list(self.merged_realized_levels),
            "freshness_classification": self.freshness_classification,
            "component_explanations": dict(self.component_explanations),
            "representation_novelty_only": self.representation_novelty_only,
            "scientific_novelty": self.scientific_novelty,
            "evidence_novelty": self.evidence_novelty,
            "built_at": self.built_at,
        }


_TRANSFER_RULES: Dict[str, bool] = {
    ResearchLineRelationship.IDENTICAL.value: True,
    ResearchLineRelationship.NEAR_DUPLICATE.value: True,
    ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value: True,
    ResearchLineRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value: False,
    ResearchLineRelationship.SAME_LINE_NEW_EVIDENCE.value: True,
    ResearchLineRelationship.RELATED_BUT_DISTINCT.value: False,
    ResearchLineRelationship.GENUINELY_INDEPENDENT.value: False,
    ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value: False,
}


def _partial_slice_transfer(
    prior: ResearchLineIdentity,
    candidate: ResearchLineIdentity,
    line_levels: List[str],
) -> List[str]:
    """Partial transfer when slice differs but proposition overlaps."""
    if prior.population_spec == candidate.population_spec and prior.outcome_spec == candidate.outcome_spec:
        return line_levels[-2:]
    return []


def merge_semantic_realized_levels(
    branch_levels: List[str],
    line_levels: List[str],
    *,
    transfer_allowed: bool,
    relationship: str,
    prior_identity: Optional[ResearchLineIdentity] = None,
    candidate_identity: Optional[ResearchLineIdentity] = None,
    freshness: str = "",
) -> Tuple[List[str], Dict[str, str]]:
    """
    Merge branch and line realized gain for marginal state inputs.

    When transfer disallowed, return branch-only (independent line protection).
    Fresh evidence on same line may offset decay via freshness metadata only —
    merged history still visible for SAME_LINE_NEW_EVIDENCE.
    """
    explanations: Dict[str, str] = {}

    if not transfer_allowed or relationship == ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value:
        explanations["transfer"] = "No decay transfer — insufficient evidence or distinct line"
        return list(branch_levels), explanations

    if relationship == ResearchLineRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value:
        if prior_identity and candidate_identity:
            partial = _partial_slice_transfer(prior_identity, candidate_identity, line_levels)
            if partial:
                merged = list(branch_levels) + partial
                explanations["transfer"] = "Partial contextual transfer for overlapping slice proposition"
                return merged[-8:], explanations
        explanations["transfer"] = "Different slice — no automatic decay transfer"
        return list(branch_levels), explanations

    if relationship == ResearchLineRelationship.SAME_LINE_NEW_EVIDENCE.value:
        if freshness in (
            FreshnessClassification.FRESH_NEW_EVIDENCE.value,
            FreshnessClassification.FRESH_NEW_HORIZON.value,
            FreshnessClassification.FRESH_NEW_POPULATION.value,
            FreshnessClassification.FRESH_NEW_OUTCOME.value,
        ):
            explanations["transfer"] = "Same line with fresh evidence — history visible, freshness offsets decay"
        else:
            explanations["transfer"] = "Same line — prior history visible"

    merged = list(line_levels) + list(branch_levels)
    explanations.setdefault("transfer", f"Full relevant history transfer for {relationship}")
    return merged[-8:], explanations


def audit_novelty_components(
    *,
    relationship: str,
    candidate: ResearchLineIdentity,
    tool_not_on_branch: bool,
    freshness: str,
) -> Tuple[bool, bool, bool]:
    """
    Separate representation vs scientific vs evidence novelty.

    representation_novelty_only: tool/frame change without scientific change
    scientific_novelty: genuinely distinct proposition
    evidence_novelty: fresh evidence makes revisit scientifically new
    """
    rep_only = (
        relationship
        in (
            ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
            ResearchLineRelationship.NEAR_DUPLICATE.value,
        )
        and tool_not_on_branch
    )
    scientific = relationship in (
        ResearchLineRelationship.GENUINELY_INDEPENDENT.value,
        ResearchLineRelationship.RELATED_BUT_DISTINCT.value,
    )
    evidence = freshness in (
        FreshnessClassification.FRESH_NEW_EVIDENCE.value,
        FreshnessClassification.FRESH_NEW_HORIZON.value,
        FreshnessClassification.FRESH_NEW_POPULATION.value,
        FreshnessClassification.FRESH_NEW_OUTCOME.value,
        FreshnessClassification.FRESH_NEW_CONTEXT.value,
    )
    return rep_only, scientific, evidence


def build_semantic_marginal_evidence(
    graph: Any,
    *,
    candidate_identity: Optional[ResearchLineIdentity],
    branch_levels: List[str],
    branch_tools_attempted: Tuple[str, ...] = (),
    freshness_classification: str = "",
    new_evidence_available: bool = False,
) -> SemanticMarginalEvidence:
    """Build auditable semantic evidence for marginal state integration."""
    if candidate_identity is None:
        return SemanticMarginalEvidence(
            version=RESEARCH_LINE_DECAY_TRANSFER_VERSION,
            candidate_proposition_key="",
            matched_line_id="",
            relationship_classification=ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value,
            transfer_allowed=False,
            branch_realized_levels=tuple(branch_levels),
            line_realized_levels=(),
            merged_realized_levels=tuple(branch_levels),
            freshness_classification=freshness_classification,
            component_explanations={"reason": "No candidate identity"},
            representation_novelty_only=False,
            scientific_novelty=False,
            evidence_novelty=False,
        )

    line_id, rel_dict = resolve_line_for_candidate(graph, candidate_identity)
    relationship = (rel_dict or {}).get("classification", ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value)
    transfer_allowed = _TRANSFER_RULES.get(relationship, False)

    line_levels: List[str] = []
    prior_identity: Optional[ResearchLineIdentity] = None
    if line_id:
        line_levels = get_line_realized_gain_history(graph, line_id)
        registry = get_registry(graph)
        rec = registry.lines.get(line_id)
        if rec:
            from modules.edge_research.research_line_identity import ResearchLineIdentity as RLI

            prior_identity = RLI.from_dict(rec.canonical_identity)
            if relationship == ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value:
                audit = classify_research_line_relationship(
                    prior_identity,
                    candidate_identity,
                    prior_line_id=line_id,
                    new_evidence_available=new_evidence_available,
                )
                relationship = audit.classification
                transfer_allowed = _TRANSFER_RULES.get(relationship, False)

    merged, explanations = merge_semantic_realized_levels(
        branch_levels,
        line_levels,
        transfer_allowed=transfer_allowed,
        relationship=relationship,
        prior_identity=prior_identity,
        candidate_identity=candidate_identity,
        freshness=freshness_classification,
    )

    tool_name = (candidate_identity.metadata or {}).get("tool_name", "")
    tool_not_on_branch = bool(tool_name) and tool_name not in branch_tools_attempted
    rep, sci, ev = audit_novelty_components(
        relationship=relationship,
        candidate=candidate_identity,
        tool_not_on_branch=tool_not_on_branch,
        freshness=freshness_classification,
    )

    return SemanticMarginalEvidence(
        version=RESEARCH_LINE_DECAY_TRANSFER_VERSION,
        candidate_proposition_key=candidate_identity.scientific_proposition_key(),
        matched_line_id=line_id or "",
        relationship_classification=relationship,
        transfer_allowed=transfer_allowed,
        branch_realized_levels=tuple(branch_levels),
        line_realized_levels=tuple(line_levels),
        merged_realized_levels=tuple(merged),
        freshness_classification=freshness_classification,
        component_explanations=explanations,
        representation_novelty_only=rep,
        scientific_novelty=sci,
        evidence_novelty=ev,
    )


def record_semantic_marginal_audit(graph: Any, evidence: SemanticMarginalEvidence) -> None:
    trail = list(getattr(graph.session, "research_line_marginal_audit", None) or [])
    trail.append(evidence.to_dict())
    graph.session.research_line_marginal_audit = trail[-200:]
