"""
Phase 3H.4 — Research Competence Model.

Bridges evidence → scientific research need → legal capability matching.
COMPETENCE ≠ PREFERENCE ≠ ACTION — competence names applicable investigation
types; existing planner/ERV/global allocator still decides choice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_interpreter import (
    FALSIFY_DATE_ARTIFACT,
    FALSIFY_EPISODE_FLUKE,
    FALSIFY_EXTREME_WINNER,
    FALSIFY_SYMBOL_DOMINANCE,
    GAP_CATEGORY_REFINEMENT,
    GAP_EPISODE_REPLICATION,
    GAP_HORIZON_STABILITY,
    GAP_INTERACTION_FOLLOWUP,
    GAP_MARKET_DEPENDENCE,
    GAP_NEIGHBORHOOD_THRESHOLD,
    GAP_NEIGHBORHOOD_STABILITY,
    GAP_SYMBOL_DISTRIBUTION,
    GAP_THRESHOLD_EXPLORATION,
    GAP_TIME_DISTRIBUTION,
    GAP_TRAJECTORY_ROLE,
)
from modules.edge_research.research_operational_awareness import (
    OperationalAwareness,
    validate_no_recommendation_language,
)

RESEARCH_COMPETENCE_VERSION = "research_competence_v1"

_FORBIDDEN_COMPETENCE_TOKENS: FrozenSet[str] = frozenset(
    {
        "promising",
        "best feature",
        "should investigate",
        "likely edge",
        "preferred tool",
        "high-potential",
        "recommended",
        "blind_benchmark",
        "bb01",
        "bb02",
        "bb03",
        "bb04",
        "bb05",
        "bb06",
        "bb07",
        "bb08",
        "bb09",
        "chatgpt",
        "buy",
        "sell",
        "edge active",
        "rsi_slope",
    }
)


class ResearchNeedType(str, Enum):
    """Generic scientific investigation types — not market-domain rules."""

    DECOMPOSE_HETEROGENEITY = "DECOMPOSE_HETEROGENEITY"
    EXPLORE_STRUCTURE = "EXPLORE_STRUCTURE"
    REFINE_BOUNDARY = "REFINE_BOUNDARY"
    TEST_INTERACTION = "TEST_INTERACTION"
    COMPARE_OUTCOMES = "COMPARE_OUTCOMES"
    TEST_ROBUSTNESS = "TEST_ROBUSTNESS"
    SEEK_FALSIFICATION = "SEEK_FALSIFICATION"
    REFRAME_POPULATION = "REFRAME_POPULATION"
    ADVANCE_INFORMATION_HORIZON = "ADVANCE_INFORMATION_HORIZON"
    REVISIT_UNRESOLVED_BRANCH = "REVISIT_UNRESOLVED_BRANCH"
    REDIRECT_OR_ABANDON = "REDIRECT_OR_ABANDON"
    REPLICATE = "REPLICATE"
    CONDITION_ON_CONTEXT = "CONDITION_ON_CONTEXT"


@dataclass(frozen=True)
class UncertaintyReductionSpec:
    """Domain-general mapping: uncertainty → research need → operation classes."""

    uncertainty_code: str
    research_need: str
    operation_classes: Tuple[str, ...]
    canonical_tools: Tuple[str, ...]


# Mirrors existing research_actions.py gap → tool mappings (single source for competence).
UNCERTAINTY_REDUCTION_REGISTRY: Dict[str, UncertaintyReductionSpec] = {
    GAP_TIME_DISTRIBUTION: UncertaintyReductionSpec(
        GAP_TIME_DISTRIBUTION,
        ResearchNeedType.DECOMPOSE_HETEROGENEITY.value,
        ("decomposition",),
        ("date_decomposition",),
    ),
    GAP_SYMBOL_DISTRIBUTION: UncertaintyReductionSpec(
        GAP_SYMBOL_DISTRIBUTION,
        ResearchNeedType.DECOMPOSE_HETEROGENEITY.value,
        ("decomposition",),
        ("symbol_decomposition",),
    ),
    GAP_EPISODE_REPLICATION: UncertaintyReductionSpec(
        GAP_EPISODE_REPLICATION,
        ResearchNeedType.REPLICATE.value,
        ("decomposition",),
        ("episode_decomposition",),
    ),
    GAP_MARKET_DEPENDENCE: UncertaintyReductionSpec(
        GAP_MARKET_DEPENDENCE,
        ResearchNeedType.CONDITION_ON_CONTEXT.value,
        ("decomposition", "context"),
        ("market_conditioning",),
    ),
    GAP_HORIZON_STABILITY: UncertaintyReductionSpec(
        GAP_HORIZON_STABILITY,
        ResearchNeedType.TEST_ROBUSTNESS.value,
        ("outcome_comparison",),
        ("horizon_comparison",),
    ),
    GAP_NEIGHBORHOOD_STABILITY: UncertaintyReductionSpec(
        GAP_NEIGHBORHOOD_STABILITY,
        ResearchNeedType.TEST_ROBUSTNESS.value,
        ("falsification", "neighborhood", "robustness"),
        ("neighborhood_stability",),
    ),
    GAP_TRAJECTORY_ROLE: UncertaintyReductionSpec(
        GAP_TRAJECTORY_ROLE,
        ResearchNeedType.EXPLORE_STRUCTURE.value,
        ("decomposition", "partition"),
        ("trajectory_partition_compare",),
    ),
    GAP_THRESHOLD_EXPLORATION: UncertaintyReductionSpec(
        GAP_THRESHOLD_EXPLORATION,
        ResearchNeedType.REFINE_BOUNDARY.value,
        ("threshold",),
        ("threshold_exploration",),
    ),
    GAP_NEIGHBORHOOD_THRESHOLD: UncertaintyReductionSpec(
        GAP_NEIGHBORHOOD_THRESHOLD,
        ResearchNeedType.REFINE_BOUNDARY.value,
        ("threshold", "neighborhood"),
        ("threshold_neighborhood",),
    ),
    GAP_CATEGORY_REFINEMENT: UncertaintyReductionSpec(
        GAP_CATEGORY_REFINEMENT,
        ResearchNeedType.REFRAME_POPULATION.value,
        ("partition",),
        ("categorical_adaptive_compare", "adaptive_partition_compare"),
    ),
    GAP_INTERACTION_FOLLOWUP: UncertaintyReductionSpec(
        GAP_INTERACTION_FOLLOWUP,
        ResearchNeedType.TEST_INTERACTION.value,
        ("interaction", "partition"),
        ("interaction_partition",),
    ),
    FALSIFY_EXTREME_WINNER: UncertaintyReductionSpec(
        FALSIFY_EXTREME_WINNER,
        ResearchNeedType.SEEK_FALSIFICATION.value,
        ("falsification", "robustness"),
        ("sensitivity_analysis",),
    ),
    FALSIFY_DATE_ARTIFACT: UncertaintyReductionSpec(
        FALSIFY_DATE_ARTIFACT,
        ResearchNeedType.SEEK_FALSIFICATION.value,
        ("falsification", "robustness"),
        ("sensitivity_analysis",),
    ),
    FALSIFY_SYMBOL_DOMINANCE: UncertaintyReductionSpec(
        FALSIFY_SYMBOL_DOMINANCE,
        ResearchNeedType.SEEK_FALSIFICATION.value,
        ("falsification", "robustness"),
        ("sensitivity_analysis",),
    ),
    FALSIFY_EPISODE_FLUKE: UncertaintyReductionSpec(
        FALSIFY_EPISODE_FLUKE,
        ResearchNeedType.SEEK_FALSIFICATION.value,
        ("falsification", "robustness"),
        ("sensitivity_analysis",),
    ),
}


@dataclass(frozen=True)
class ResearchNeedMatch:
    """One active uncertainty mapped to legal capability intersection."""

    uncertainty_code: str
    research_need: str
    operation_classes: Tuple[str, ...]
    eligible_tools: Tuple[str, ...]
    legally_constructible: bool
    branch_tools_closed: bool
    excluded_tools: Tuple[str, ...] = field(default_factory=tuple)
    exclusion_reasons: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uncertainty_code": self.uncertainty_code,
            "research_need": self.research_need,
            "operation_classes": list(self.operation_classes),
            "eligible_tools": list(self.eligible_tools),
            "legally_constructible": self.legally_constructible,
            "branch_tools_closed": self.branch_tools_closed,
            "excluded_tools": list(self.excluded_tools),
            "exclusion_reasons": list(self.exclusion_reasons),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchNeedMatch":
        return cls(
            uncertainty_code=str(payload["uncertainty_code"]),
            research_need=str(payload["research_need"]),
            operation_classes=tuple(payload.get("operation_classes") or ()),
            eligible_tools=tuple(payload.get("eligible_tools") or ()),
            legally_constructible=bool(payload.get("legally_constructible", False)),
            branch_tools_closed=bool(payload.get("branch_tools_closed", False)),
            excluded_tools=tuple(payload.get("excluded_tools") or ()),
            exclusion_reasons=tuple(payload.get("exclusion_reasons") or ()),
        )


@dataclass
class ResearchCompetenceModel:
    version: str = RESEARCH_COMPETENCE_VERSION
    built_at: str = ""
    source_experiment_node_id: str = ""
    active_uncertainties: Tuple[str, ...] = field(default_factory=tuple)
    inferred_research_needs: Tuple[str, ...] = field(default_factory=tuple)
    need_matches: Tuple[ResearchNeedMatch, ...] = field(default_factory=tuple)
    unaddressed_gaps: Tuple[str, ...] = field(default_factory=tuple)
    triggering_evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "built_at": self.built_at,
            "source_experiment_node_id": self.source_experiment_node_id,
            "active_uncertainties": list(self.active_uncertainties),
            "inferred_research_needs": list(self.inferred_research_needs),
            "need_matches": [m.to_dict() for m in self.need_matches],
            "unaddressed_gaps": list(self.unaddressed_gaps),
            "triggering_evidence": dict(self.triggering_evidence),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchCompetenceModel":
        return cls(
            version=str(payload.get("version", RESEARCH_COMPETENCE_VERSION)),
            built_at=str(payload.get("built_at", "")),
            source_experiment_node_id=str(payload.get("source_experiment_node_id", "")),
            active_uncertainties=tuple(payload.get("active_uncertainties") or ()),
            inferred_research_needs=tuple(payload.get("inferred_research_needs") or ()),
            need_matches=tuple(
                ResearchNeedMatch.from_dict(m) for m in (payload.get("need_matches") or [])
            ),
            unaddressed_gaps=tuple(payload.get("unaddressed_gaps") or ()),
            triggering_evidence=dict(payload.get("triggering_evidence") or {}),
        )

    def legally_constructible_needs(self) -> Tuple[str, ...]:
        return tuple(
            sorted(
                m.research_need
                for m in self.need_matches
                if m.legally_constructible and not m.branch_tools_closed
            )
        )


@dataclass
class ResearchCompetenceAudit:
    """Auditable record of one competence-mediated planning step."""

    event: str = "COMPETENCE_CONSULTED"
    timestamp: str = ""
    experiment_node_id: str = ""
    competence: Optional[Dict[str, Any]] = None
    candidate_matches: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    selected_action_id: str = ""
    allocator_agreed: bool = True
    alternative_action_id: str = ""
    metrics_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "timestamp": self.timestamp,
            "experiment_node_id": self.experiment_node_id,
            "competence": self.competence,
            "candidate_matches": dict(self.candidate_matches),
            "selected_action_id": self.selected_action_id,
            "allocator_agreed": self.allocator_agreed,
            "alternative_action_id": self.alternative_action_id,
            "metrics_snapshot": dict(self.metrics_snapshot),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchCompetenceAudit":
        return cls(
            event=str(payload.get("event", "COMPETENCE_CONSULTED")),
            timestamp=str(payload.get("timestamp", "")),
            experiment_node_id=str(payload.get("experiment_node_id", "")),
            competence=payload.get("competence"),
            candidate_matches=dict(payload.get("candidate_matches") or {}),
            selected_action_id=str(payload.get("selected_action_id", "")),
            allocator_agreed=bool(payload.get("allocator_agreed", True)),
            alternative_action_id=str(payload.get("alternative_action_id", "")),
            metrics_snapshot=dict(payload.get("metrics_snapshot") or {}),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _available_tools(awareness: Optional[OperationalAwareness]) -> Dict[str, Tuple[str, ...]]:
    """tool_name → operation_classes from awareness tool affordances."""
    if awareness is None:
        return {}
    out: Dict[str, Tuple[str, ...]] = {}
    for ta in awareness.tool_affordances:
        name = str(ta.get("tool_name", ""))
        if not name:
            continue
        ops = tuple(str(o) for o in (ta.get("operation_classes") or ()))
        if ta.get("available", True):
            out[name] = ops
    return out


def _infer_evidence_needs(
    assessment: ResearchAssessment,
    graph: Any = None,
    experiment_node_id: str = "",
) -> Tuple[str, ...]:
    """Evidence-driven research needs beyond explicit gap codes."""
    needs: List[str] = []

    if assessment.possible_falsification_targets:
        needs.append(ResearchNeedType.SEEK_FALSIFICATION.value)

    if assessment.fragility_evidence and not assessment.additional_investigation_warranted:
        needs.append(ResearchNeedType.REDIRECT_OR_ABANDON.value)

    if (
        not assessment.additional_investigation_warranted
        and not assessment.interesting
        and assessment.descriptive_strength in ("NO_CLEAR_DIFFERENCE", "NO_VARIATION", "INSUFFICIENT")
    ):
        needs.append(ResearchNeedType.REDIRECT_OR_ABANDON.value)

    if assessment.interesting and assessment.additional_investigation_warranted:
        if GAP_THRESHOLD_EXPLORATION not in assessment.information_gaps:
            needs.append(ResearchNeedType.EXPLORE_STRUCTURE.value)

    if assessment.horizon_dependence:
        needs.append(ResearchNeedType.COMPARE_OUTCOMES.value)

    if graph is not None and experiment_node_id:
        try:
            from modules.edge_research.research_frame import FrameStatus, assess_frame_saturation

            exp = graph.get_node(experiment_node_id)
            frame_id = ""
            for pid in exp.parent_node_ids:
                parent = graph.get_node(pid)
                if parent.question_context:
                    frame_id = parent.question_context.frame_id
                    break
            if not frame_id:
                frame_id = graph.get_frame_registry().active_frame_id
            frame = graph.get_frame_registry().get(frame_id) if frame_id else None
            if frame is not None:
                status, _ = assess_frame_saturation(frame)
                if status in (FrameStatus.LOW_YIELD.value, FrameStatus.EXHAUSTED.value):
                    needs.append(ResearchNeedType.REFRAME_POPULATION.value)
                if status == FrameStatus.UNDEREXPLORED.value and assessment.interesting:
                    needs.append(ResearchNeedType.EXPLORE_STRUCTURE.value)
        except Exception:
            pass

        try:
            portfolio = graph.get_portfolio_state()
            deferred = [
                b for b in portfolio.branches.values()
                if b.status == "DEFERRED_PROMISING"
            ]
            if deferred:
                needs.append(ResearchNeedType.REVISIT_UNRESOLVED_BRANCH.value)
        except Exception:
            pass

    return tuple(sorted(set(needs)))


def build_research_competence_model(
    assessment: ResearchAssessment,
    awareness: Optional[OperationalAwareness] = None,
    *,
    graph: Any = None,
    experiment_node_id: str = "",
) -> ResearchCompetenceModel:
    """
    Derive research needs from evidence and intersect with legal capabilities.

    No scores, no preferences, no prescriptive tool selection.
    """
    active = tuple(
        sorted(
            set(assessment.information_gaps)
            | set(assessment.possible_falsification_targets)
        )
    )
    available_tools = _available_tools(awareness)
    attempted = set(assessment.branch_tools_attempted)

    matches: List[ResearchNeedMatch] = []
    unaddressed: List[str] = []

    for code in active:
        spec = UNCERTAINTY_REDUCTION_REGISTRY.get(code)
        if spec is None:
            continue

        eligible: List[str] = []
        excluded: List[str] = []
        reasons: List[str] = []

        for tool in spec.canonical_tools:
            if tool in attempted:
                excluded.append(tool)
                reasons.append(f"branch_closed:{tool}")
                continue
            if awareness is not None and tool not in available_tools:
                excluded.append(tool)
                reasons.append(f"not_available:{tool}")
                continue
            if awareness is not None:
                tool_ops = set(available_tools.get(tool, ()))
                if not tool_ops.intersection(spec.operation_classes):
                    excluded.append(tool)
                    reasons.append(f"operation_mismatch:{tool}")
                    continue
            eligible.append(tool)

        branch_closed = all(t in attempted for t in spec.canonical_tools)
        legally = len(eligible) > 0

        matches.append(
            ResearchNeedMatch(
                uncertainty_code=code,
                research_need=spec.research_need,
                operation_classes=spec.operation_classes,
                eligible_tools=tuple(eligible),
                legally_constructible=legally,
                branch_tools_closed=branch_closed,
                excluded_tools=tuple(excluded),
                exclusion_reasons=tuple(reasons),
            )
        )
        if not legally and not branch_closed and awareness is not None:
            unaddressed.append(code)

    inferred = _infer_evidence_needs(assessment, graph, experiment_node_id)

    return ResearchCompetenceModel(
        built_at=_utc_now(),
        source_experiment_node_id=experiment_node_id or assessment.source_experiment_node_id,
        active_uncertainties=active,
        inferred_research_needs=inferred,
        need_matches=tuple(matches),
        unaddressed_gaps=tuple(unaddressed),
        triggering_evidence={
            "information_gaps": list(assessment.information_gaps),
            "falsification_targets": list(assessment.possible_falsification_targets),
            "interesting": assessment.interesting,
            "additional_investigation_warranted": assessment.additional_investigation_warranted,
            "descriptive_strength": assessment.descriptive_strength,
            "fragility_evidence": list(assessment.fragility_evidence),
            "branch_tools_attempted": list(assessment.branch_tools_attempted),
        },
    )


def annotate_candidates_with_competence(
    candidates: Sequence[Any],
    competence: ResearchCompetenceModel,
) -> Dict[str, Dict[str, Any]]:
    """
    Map candidates to competence relevance — metadata only, no score change.

    Returns action_id → {research_need, uncertainty_code, tool_relevant}.
    """
    need_by_uncertainty = {m.uncertainty_code: m for m in competence.need_matches}
    annotations: Dict[str, Dict[str, Any]] = {}

    for c in candidates:
        if getattr(c, "blocked", False):
            continue
        unc = getattr(c, "uncertainty_addressed", "") or ""
        tool = getattr(c, "tool_name", "") or ""
        match = need_by_uncertainty.get(unc)
        relevant = False
        research_need = ""
        if match is not None:
            research_need = match.research_need
            relevant = tool in match.eligible_tools if tool else match.legally_constructible
        elif unc in ("STOP", "ABANDON", "STOP_SESSION"):
            research_need = ResearchNeedType.REDIRECT_OR_ABANDON.value
            relevant = True

        annotations[c.action_id] = {
            "uncertainty_code": unc,
            "research_need": research_need,
            "tool_name": tool,
            "scientifically_relevant": relevant,
            "intent": getattr(c, "intent", ""),
        }

    return annotations


def record_competence_audit(
    graph: Any,
    *,
    experiment_node_id: str,
    competence: ResearchCompetenceModel,
    candidates: Sequence[Any],
    selected_action_id: str = "",
    allocator_agreed: bool = True,
    alternative_action_id: str = "",
) -> ResearchCompetenceAudit:
    """Persist competence audit on session."""
    annotations = annotate_candidates_with_competence(candidates, competence)
    audit = ResearchCompetenceAudit(
        event="COMPETENCE_CONSULTED",
        timestamp=_utc_now(),
        experiment_node_id=experiment_node_id,
        competence=competence.to_dict(),
        candidate_matches=annotations,
        selected_action_id=selected_action_id,
        allocator_agreed=allocator_agreed,
        alternative_action_id=alternative_action_id,
        metrics_snapshot=compute_competence_metrics(competence, candidates, annotations),
    )
    trail = list(getattr(graph.session, "research_competence_audit", None) or [])
    trail.append(audit.to_dict())
    graph.session.research_competence_audit = trail
    return audit


def compute_competence_metrics(
    competence: ResearchCompetenceModel,
    candidates: Sequence[Any],
    annotations: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Neutral competence metrics — tool count is NOT success."""
    annot = annotations or {}
    relevant = [a for a in annot.values() if a.get("scientifically_relevant")]
    falsify_needs = [
        m for m in competence.need_matches
        if m.research_need == ResearchNeedType.SEEK_FALSIFICATION.value
    ]
    falsify_candidates = [
        a for a in annot.values()
        if a.get("research_need") == ResearchNeedType.SEEK_FALSIFICATION.value
    ]
    tools_used = {
        getattr(c, "tool_name", "")
        for c in candidates
        if getattr(c, "tool_name", "") and not getattr(c, "blocked", False)
    }
    return {
        "active_uncertainty_count": len(competence.active_uncertainties),
        "inferred_need_count": len(competence.inferred_research_needs),
        "legally_constructible_need_count": len(competence.legally_constructible_needs()),
        "unaddressed_gap_count": len(competence.unaddressed_gaps),
        "scientifically_relevant_candidate_count": len(relevant),
        "total_candidate_count": len([c for c in candidates if not getattr(c, "blocked", False)]),
        "distinct_tools_in_candidates": len(tools_used),
        "falsification_needs_recognized": len(falsify_needs),
        "falsification_candidates_constructed": len(falsify_candidates),
    }


def validate_no_competence_recommendation_language(payload: Any) -> List[str]:
    text = str(payload).lower()
    return sorted(t for t in _FORBIDDEN_COMPETENCE_TOKENS if t in text)


def competence_neutral_for_identical_candidates(
    scores_without: Dict[str, Any],
    scores_with: Dict[str, Any],
    decision_without: Any,
    decision_with: Any,
    shared_action_ids: Sequence[str],
) -> bool:
    """Counterfactual neutrality check for Scenario L."""
    for aid in shared_action_ids:
        a = scores_without.get(aid)
        b = scores_with.get(aid)
        if a is None or b is None:
            continue
        total_a = a[0] if isinstance(a, tuple) else a.get("total")
        total_b = b[0] if isinstance(b, tuple) else b.get("total")
        if total_a != total_b:
            return False
    sel_a = getattr(getattr(decision_without, "selected", None), "action_id", None)
    sel_b = getattr(getattr(decision_with, "selected", None), "action_id", None)
    if sel_a and sel_b and sel_a == sel_b:
        return True
    if sel_a is None and sel_b is None:
        return True
    return sel_a == sel_b
