"""
Deterministic research planner for Edge Research (PATCH 3C).

Scores candidate actions and selects one, STOP, or ABANDON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.research_actions import (
    ActionIntent,
    ResearchActionCandidate,
    viable_candidates,
)
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_graph import ResearchGraph

# Fixed weights — NOT tuned from production outcomes.
WEIGHT_INFORMATION_GAP = 3.0
WEIGHT_FALSIFICATION_THREAT = 4.0
WEIGHT_NOVELTY = 2.0
WEIGHT_STOP = 5.0
WEIGHT_ABANDON = 4.5
BLOCKED_SCORE = -1000.0


class PlanDecisionType(str, Enum):
    EXPERIMENT = "EXPERIMENT"
    STOP = "STOP"
    ABANDON = "ABANDON"


@dataclass(frozen=True)
class PlanDecision:
    decision_type: PlanDecisionType
    selected: Optional[ResearchActionCandidate]
    all_candidates: Tuple[ResearchActionCandidate, ...]
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    rationale_codes: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_type": self.decision_type.value,
            "selected_action_id": self.selected.action_id if self.selected else None,
            "selected_action_code": self.selected.action_code if self.selected else None,
            "score_breakdown": dict(self.score_breakdown),
            "rationale_codes": list(self.rationale_codes),
            "candidate_count": len(self.all_candidates),
        }


def _remaining_budget(graph: ResearchGraph) -> Optional[int]:
    budget = graph.session.experiment_budget
    if budget is None:
        return None
    return max(0, budget - graph.session.experiments_used)


def _gap_match(assessment: ResearchAssessment, candidate: ResearchActionCandidate) -> float:
    if candidate.uncertainty_addressed in assessment.information_gaps:
        return candidate.priority_hints.get("information_gap", WEIGHT_INFORMATION_GAP)
    hints = candidate.priority_hints.get("information_gap", 0.0)
    return hints if hints else 0.0


def _falsification_match(assessment: ResearchAssessment, candidate: ResearchActionCandidate) -> float:
    if candidate.intent != ActionIntent.FALSIFICATION.value:
        return 0.0
    if candidate.uncertainty_addressed not in assessment.possible_falsification_targets:
        return 0.0
    base = candidate.priority_hints.get("falsification_threat", WEIGHT_FALSIFICATION_THREAT)
    # Reduce falsification priority if that exact sensitivity test already ran.
    if candidate.tool_name in assessment.branch_tools_attempted:
        return base * 0.2
    return base


def _novelty_bonus(assessment: ResearchAssessment, candidate: ResearchActionCandidate) -> float:
    if candidate.intent in (ActionIntent.STOP.value, ActionIntent.ABANDON.value):
        return 0.0
    if candidate.tool_name and candidate.tool_name not in assessment.branch_tools_attempted:
        return WEIGHT_NOVELTY
    return WEIGHT_NOVELTY * 0.3


def _stop_score(assessment: ResearchAssessment, candidate: ResearchActionCandidate) -> float:
    if candidate.intent != ActionIntent.STOP.value:
        return 0.0
    base = candidate.priority_hints.get("stop_urgency", 0.0)
    if not assessment.additional_investigation_warranted:
        base += WEIGHT_STOP
    return base


def _abandon_score(assessment: ResearchAssessment, candidate: ResearchActionCandidate) -> float:
    if candidate.intent != ActionIntent.ABANDON.value:
        return 0.0
    base = candidate.priority_hints.get("abandon_urgency", 0.0)
    if assessment.fragility_evidence:
        base += WEIGHT_ABANDON
    return base


def _grammar_bonus(candidate: ResearchActionCandidate) -> float:
    hints = candidate.priority_hints
    return (
        hints.get("grammar_reframe", 0.0)
        + hints.get("grammar_repopulate", 0.0)
        + hints.get("grammar_widen", 0.0)
    )


def _adaptive_bonus(candidate: ResearchActionCandidate) -> float:
    hints = candidate.priority_hints
    return (
        hints.get("threshold_explore", 0.0)
        + hints.get("shape_followup", 0.0)
        + hints.get("neighborhood_test", 0.0)
        + hints.get("slicing_explore", 0.0)
        + hints.get("category_refinement", 0.0)
        + hints.get("region_refinement", 0.0)
        + hints.get("interaction_followup", 0.0)
    )


def score_candidate(
    candidate: ResearchActionCandidate,
    assessment: ResearchAssessment,
    graph: ResearchGraph,
) -> Tuple[float, Dict[str, float]]:
    """Deterministic score with auditable components."""
    if candidate.blocked and candidate.intent not in (ActionIntent.STOP.value, ActionIntent.ABANDON.value):
        return BLOCKED_SCORE, {"blocked": BLOCKED_SCORE}

    components: Dict[str, float] = {}
    components["information_gap"] = _gap_match(assessment, candidate)
    components["falsification_threat"] = _falsification_match(assessment, candidate)
    components["novelty"] = _novelty_bonus(assessment, candidate)
    components["grammar"] = _grammar_bonus(candidate)
    components["adaptive"] = _adaptive_bonus(candidate)
    components["stop"] = _stop_score(assessment, candidate)
    components["abandon"] = _abandon_score(assessment, candidate)

    total = sum(components.values())
    return total, components


def plan_next_action(
    assessment: ResearchAssessment,
    candidates: Sequence[ResearchActionCandidate],
    graph: ResearchGraph,
) -> PlanDecision:
    """
    Choose among candidates, STOP, or ABANDON using weighted deterministic scoring.

    Falsification competes with exploration — no automatic pipeline ordering.
    """
    remaining = _remaining_budget(graph)
    scored: List[Tuple[float, ResearchActionCandidate, Dict[str, float]]] = []

    experiment_viable = [
        c for c in candidates
        if not c.blocked
        and c.intent not in (ActionIntent.STOP.value, ActionIntent.ABANDON.value)
    ]

    # Budget exhaustion boosts STOP but does not remove other candidates from record.
    budget_exhausted = remaining is not None and remaining <= 0

    for candidate in candidates:
        total, components = score_candidate(candidate, assessment, graph)
        if budget_exhausted and candidate.intent == ActionIntent.STOP.value:
            total += WEIGHT_STOP * 2
            components["budget_exhausted"] = WEIGHT_STOP * 2
        scored.append((total, candidate, components))

    scored.sort(key=lambda x: (-x[0], x[1].action_id))

    if not scored:
        return PlanDecision(
            decision_type=PlanDecisionType.STOP,
            selected=None,
            all_candidates=tuple(candidates),
            score_breakdown={"reason": "NO_CANDIDATES"},
            rationale_codes=("STOP", "NO_CANDIDATES"),
        )

    best_score, best, best_components = scored[0]

    # If no viable experiment candidates, prefer STOP/ABANDON.
    if not experiment_viable:
        for total, cand, comp in scored:
            if cand.intent == ActionIntent.ABANDON.value and assessment.fragility_evidence:
                return PlanDecision(
                    decision_type=PlanDecisionType.ABANDON,
                    selected=cand,
                    all_candidates=tuple(candidates),
                    score_breakdown={"components": comp, "total": total},
                    rationale_codes=cand.rationale_codes,
                )
        for total, cand, comp in scored:
            if cand.intent == ActionIntent.STOP.value:
                return PlanDecision(
                    decision_type=PlanDecisionType.STOP,
                    selected=cand,
                    all_candidates=tuple(candidates),
                    score_breakdown={"components": comp, "total": total},
                    rationale_codes=cand.rationale_codes,
                )

    if best.intent == ActionIntent.STOP.value:
        return PlanDecision(
            decision_type=PlanDecisionType.STOP,
            selected=best,
            all_candidates=tuple(candidates),
            score_breakdown={"components": best_components, "total": best_score},
            rationale_codes=best.rationale_codes,
        )

    if best.intent == ActionIntent.ABANDON.value:
        return PlanDecision(
            decision_type=PlanDecisionType.ABANDON,
            selected=best,
            all_candidates=tuple(candidates),
            score_breakdown={"components": best_components, "total": best_score},
            rationale_codes=best.rationale_codes,
        )

    if budget_exhausted:
        stop_cand = next((c for _, c, _ in scored if c.intent == ActionIntent.STOP.value), None)
        return PlanDecision(
            decision_type=PlanDecisionType.STOP,
            selected=stop_cand,
            all_candidates=tuple(candidates),
            score_breakdown={"reason": "BUDGET_EXHAUSTED"},
            rationale_codes=("STOP", "BUDGET_EXHAUSTED"),
        )

    return PlanDecision(
        decision_type=PlanDecisionType.EXPERIMENT,
        selected=best,
        all_candidates=tuple(candidates),
        score_breakdown={"components": best_components, "total": best_score},
        rationale_codes=best.rationale_codes,
    )


def score_all_candidates(
    assessment: ResearchAssessment,
    candidates: Sequence[ResearchActionCandidate],
    graph: ResearchGraph,
) -> Dict[str, Tuple[float, Dict[str, float]]]:
    """Expose scores for tests and audit."""
    return {
        c.action_id: score_candidate(c, assessment, graph)
        for c in candidates
    }
