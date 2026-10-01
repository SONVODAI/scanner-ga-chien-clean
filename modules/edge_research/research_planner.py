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
from modules.edge_research.research_search_accounting import (
    COMPLEXITY_PENALTY_SCALE,
    compute_complexity_score,
    compute_effective_hypotheses,
    compute_evidence_burden,
    compute_planner_complexity_penalty,
    compute_skepticism_escalation,
    branch_depth as accounting_branch_depth,
    weak_evidence_high_complexity_should_stop,
)

# Fixed weights — NOT tuned from production outcomes.
WEIGHT_INFORMATION_GAP = 3.0
WEIGHT_FALSIFICATION_THREAT = 4.0
WEIGHT_NOVELTY = 2.0
WEIGHT_STOP = 5.0
WEIGHT_ABANDON = 4.5
WEIGHT_STRONG_EVIDENCE_EXPLORATION = 3.0
BLOCKED_SCORE = -1000.0

# Phase 3G.1 — exploration coverage (generic, not BB01-tuned).
WEIGHT_UNEXPLORED_FEATURE = 2.5
WEIGHT_UNEXPLORED_OUTCOME = 1.5
WEIGHT_UNEXPLORED_POPULATION = 1.5
WEIGHT_INDEPENDENT_BRANCH = 2.0
WEIGHT_INFORMATION_GAIN = 2.0
WEIGHT_REDUNDANCY_PENALTY = 3.0
EARLY_SESSION_FALSIFICATION_DAMPEN = 0.45
LOW_COVERAGE_STOP_PENALTY = 4.0

# Phase 3G.2 — frame diversity (generic, not benchmark-tuned).
WEIGHT_NEW_OUTCOME = 3.0
WEIGHT_NEW_POPULATION = 3.0
WEIGHT_NEW_HORIZON = 3.5
WEIGHT_NEW_CONTEXT = 2.5
WEIGHT_FRAME_NOVELTY = 2.0
WEIGHT_SATURATED_REFRAME = 4.0
WEIGHT_SAME_FRAME_PENALTY = 2.5
WEIGHT_SAMPLE_LOSS_PENALTY = 3.0


class PlanDecisionType(str, Enum):
    EXPERIMENT = "EXPERIMENT"
    STOP_BRANCH = "STOP_BRANCH"
    STOP_SESSION = "STOP_SESSION"
    ABANDON = "ABANDON"
    STOP = "STOP_BRANCH"  # backward-compatible alias


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


def _branch_complexity_context(graph: ResearchGraph, experiment_node_id: str) -> Optional[Dict[str, Any]]:
    """Load branch search accounting for planner penalties."""
    from modules.edge_research.research_search_accounting import branch_root_id

    if experiment_node_id not in graph.nodes:
        return None
    state = graph.get_search_accounting()
    root = branch_root_id(graph, experiment_node_id)
    branch_ledger = state.branch_ledgers.get(root, state.session_ledger)
    depth = accounting_branch_depth(graph, experiment_node_id)
    complexity = compute_complexity_score(branch_ledger, branch_depth=depth)
    mh = compute_effective_hypotheses(branch_ledger)
    return {
        "branch_ledger": branch_ledger,
        "branch_depth": depth,
        "complexity": complexity,
        "effective_hypotheses": mh.effective_hypotheses_tested,
    }


def _complexity_penalty(graph: ResearchGraph, experiment_node_id: str) -> Tuple[float, Dict[str, float]]:
    ctx = _branch_complexity_context(graph, experiment_node_id)
    if ctx is None:
        return 0.0, {}
    search_pen, branch_pen = compute_planner_complexity_penalty(
        ctx["complexity"], branch_depth=ctx["branch_depth"]
    )
    return search_pen + branch_pen, {
        "search_complexity_penalty": -search_pen,
        "branch_complexity_penalty": -branch_pen,
    }


def _skepticism_bonus(
    assessment: ResearchAssessment,
    candidate: ResearchActionCandidate,
    graph: ResearchGraph,
    experiment_node_id: str,
) -> float:
    """Escalate falsification priority when candidate looks too good."""
    if candidate.intent != ActionIntent.FALSIFICATION.value:
        return 0.0
    ctx = _branch_complexity_context(graph, experiment_node_id)
    if ctx is None:
        return 0.0
    hints = candidate.priority_hints
    success_rate = hints.get("observed_success_rate")
    threshold_strength = hints.get("threshold_strength")
    pop_refined = hints.get("population_refined", False) or "REPOPULATE" in candidate.action_code
    extreme_bin = "EXTREME" in candidate.action_code or "EXTREME_WINNER" in assessment.fragility_evidence
    has_interaction = candidate.tool_name == "interaction_partition"
    bonuses = compute_skepticism_escalation(
        success_rate=success_rate,
        threshold_strength=threshold_strength,
        has_interaction=has_interaction,
        population_refined=bool(pop_refined),
        extreme_bin=extreme_bin,
        effective_hypotheses=ctx["effective_hypotheses"],
    )
    return sum(bonuses.values())


def _strong_evidence_exploration_bonus(
    assessment: ResearchAssessment,
    candidate: ResearchActionCandidate,
    graph: ResearchGraph,
    experiment_node_id: str,
) -> float:
    """Strong evidence can justify additional exploration despite complexity."""
    if candidate.intent in (ActionIntent.STOP.value, ActionIntent.ABANDON.value):
        return 0.0
    ctx = _branch_complexity_context(graph, experiment_node_id)
    if ctx is None:
        return 0.0
    hints = candidate.priority_hints
    raw_effect = hints.get("observed_success_rate") or hints.get("raw_effect")
    if raw_effect is None and assessment.interesting:
        raw_effect = 0.15
    if raw_effect is None:
        return 0.0
    evidence = compute_evidence_burden(
        raw_effect=float(raw_effect),
        incremental_effect=hints.get("incremental_effect"),
        sample_size=hints.get("sample_size"),
        uncertainty=None,
        shape_strength=hints.get("shape_strength"),
        complexity=ctx["complexity"],
        search_cardinality=ctx["effective_hypotheses"],
        concentration_flags=assessment.concentration_concerns,
    )
    if evidence.evidence_search_assessment == "STRONG_RELATIVE_TO_SEARCH":
        return WEIGHT_STRONG_EVIDENCE_EXPLORATION
    return 0.0


def _weak_complexity_stop_bonus(
    assessment: ResearchAssessment,
    candidate: ResearchActionCandidate,
    graph: ResearchGraph,
    experiment_node_id: str,
) -> float:
    """Weak evidence + high complexity boosts STOP/ABANDON."""
    if candidate.intent not in (ActionIntent.STOP.value, ActionIntent.ABANDON.value):
        return 0.0
    ctx = _branch_complexity_context(graph, experiment_node_id)
    if ctx is None:
        return 0.0
    hints = candidate.priority_hints
    raw_effect = hints.get("observed_success_rate") or hints.get("raw_effect") or 0.0
    evidence = compute_evidence_burden(
        raw_effect=float(raw_effect) if raw_effect else None,
        incremental_effect=hints.get("incremental_effect"),
        sample_size=hints.get("sample_size"),
        uncertainty=None,
        shape_strength=None,
        complexity=ctx["complexity"],
        search_cardinality=ctx["effective_hypotheses"],
    )
    if weak_evidence_high_complexity_should_stop(evidence, ctx["complexity"]):
        return WEIGHT_STOP * 1.5 if candidate.intent == ActionIntent.STOP.value else WEIGHT_ABANDON * 1.5
    if not assessment.additional_investigation_warranted and ctx["complexity"].aggregate_score > 10:
        return WEIGHT_STOP if candidate.intent == ActionIntent.STOP.value else WEIGHT_ABANDON * 0.5
    return 0.0


def _branch_complexity_penalty_for_candidate(
    candidate: ResearchActionCandidate,
) -> float:
    """Penalize unnecessarily complex branch actions (higher draft complexity)."""
    hints = candidate.priority_hints
    draft_complexity = hints.get("draft_complexity", 0.0)
    parent_complexity = hints.get("parent_complexity", 0.0)
    incremental = draft_complexity - parent_complexity
    if incremental <= 0:
        return 0.0
    return incremental * COMPLEXITY_PENALTY_SCALE * 1.5


def _extract_candidate_feature(candidate: ResearchActionCandidate) -> str:
    if candidate.draft_spec is None:
        return ""
    inputs = candidate.draft_spec.inputs or {}
    for key in ("feature_column", "partition_column", "primary_feature", "trajectory_feature"):
        if key in inputs:
            return str(inputs[key])
    return ""


def _session_coverage_context(graph: ResearchGraph) -> Dict[str, Any]:
    state = graph.get_search_accounting()
    session = state.session_ledger
    preflight = graph.session.panel_preflight or {}
    eligible = preflight.get("eligible_explanatory") or []
    features_tested = set(session.explanatory_features_tested)
    budget = graph.session.experiment_budget
    used = graph.session.experiments_used
    return {
        "features_touched": len(features_tested),
        "eligible_feature_count": len(eligible),
        "features_tested": features_tested,
        "experiments_used": used,
        "experiment_budget": budget,
        "low_coverage": len(eligible) > 0 and len(features_tested) < len(eligible),
        "early_session": budget is not None and used <= max(1, budget // 4),
    }


def _coverage_bonuses(
    candidate: ResearchActionCandidate,
    graph: ResearchGraph,
) -> Dict[str, float]:
    """Transparent coverage / information-gain terms competing with STOP/falsification."""
    if candidate.intent in (
        ActionIntent.STOP.value,
        ActionIntent.STOP_SESSION.value,
        ActionIntent.ABANDON.value,
    ):
        return {}

    ctx = _session_coverage_context(graph)
    components: Dict[str, float] = {}
    feat = _extract_candidate_feature(candidate)
    tested = ctx["features_tested"]

    if feat and feat not in tested:
        components["unexplored_feature_bonus"] = WEIGHT_UNEXPLORED_FEATURE
    elif feat and feat in tested:
        components["redundancy_penalty"] = -WEIGHT_REDUNDANCY_PENALTY

    scope = candidate.draft_spec.research_scope if candidate.draft_spec else {}
    if scope.get("pending_question_context"):
        components["unexplored_population_bonus"] = WEIGHT_UNEXPLORED_POPULATION * 0.5
    if scope.get("outcome_reframe") or candidate.intent == ActionIntent.REDESCRIBE_OUTCOME.value:
        components["unexplored_outcome_bonus"] = WEIGHT_UNEXPLORED_OUTCOME

    if candidate.intent in (
        ActionIntent.SLICING.value,
        ActionIntent.EXPLORATION.value,
        ActionIntent.DECOMPOSITION.value,
    ):
        components["information_gain_bonus"] = WEIGHT_INFORMATION_GAIN

    if ctx["low_coverage"] and ctx["early_session"]:
        components["independent_branch_bonus"] = WEIGHT_INDEPENDENT_BRANCH

    return components


def _stop_branch_penalty(candidate: ResearchActionCandidate, graph: ResearchGraph) -> float:
    """Global STOP should lose when substantial unexplored coverage remains."""
    if candidate.intent != ActionIntent.STOP.value:
        return 0.0
    ctx = _session_coverage_context(graph)
    frontier = graph.get_frontier()
    if ctx["low_coverage"] and ctx["experiment_budget"] and ctx["experiments_used"] < ctx["experiment_budget"]:
        remaining = ctx["experiment_budget"] - ctx["experiments_used"]
        if remaining > 1 and frontier.count_by_status("UNEXPLORED") > 0:
            return -LOW_COVERAGE_STOP_PENALTY
        if ctx["features_touched"] == 0 and ctx["eligible_feature_count"] >= 2:
            return -LOW_COVERAGE_STOP_PENALTY
    return 0.0


def _stop_session_score(candidate: ResearchActionCandidate) -> float:
    """STOP_SESSION is controller-driven — keep score low in branch planner."""
    if candidate.intent != ActionIntent.STOP_SESSION.value:
        return 0.0
    return -100.0


def _frame_diversity_bonuses(
    candidate: ResearchActionCandidate,
    graph: ResearchGraph,
) -> Dict[str, float]:
    """Frame-level diversity scoring — reframes compete with same-frame feature tests."""
    if candidate.intent in (
        ActionIntent.STOP.value,
        ActionIntent.STOP_SESSION.value,
        ActionIntent.ABANDON.value,
    ):
        return {}

    hints = candidate.priority_hints
    components: Dict[str, float] = {}

    for key, weight in (
        ("new_outcome_bonus", WEIGHT_NEW_OUTCOME),
        ("new_population_bonus", WEIGHT_NEW_POPULATION),
        ("new_information_horizon_bonus", WEIGHT_NEW_HORIZON),
        ("new_context_bonus", WEIGHT_NEW_CONTEXT),
        ("frame_novelty_bonus", WEIGHT_FRAME_NOVELTY),
        ("saturated_parent_reframe_bonus", WEIGHT_SATURATED_REFRAME),
    ):
        val = hints.get(key, 0.0)
        if val:
            components[key] = float(val) if val != True else weight  # noqa: E712

    sample_pen = hints.get("sample_loss_penalty", 0.0)
    if sample_pen:
        components["sample_loss_penalty"] = float(sample_pen)

    scope = candidate.draft_spec.research_scope if candidate.draft_spec else {}
    reg = graph.get_frame_registry()
    active = reg.get(reg.active_frame_id) if reg.active_frame_id else None

    if active and scope.get("frame_transformation"):
        if not scope.get("outcome_reframe") and not scope.get("population_reframe"):
            if candidate.intent == ActionIntent.SLICING.value:
                components["repeated_same_frame_penalty"] = -WEIGHT_SAME_FRAME_PENALTY

    known_outcomes = {f.outcome.content_hash() for f in reg.frames.values()}
    known_pops = {f.population.content_hash() for f in reg.frames.values()}
    pending = scope.get("pending_question_context") or {}
    if pending.get("outcome_spec"):
        from modules.edge_research.research_grammar import OutcomeSpec
        oh = OutcomeSpec.from_dict(pending["outcome_spec"]).content_hash()
        if oh not in known_outcomes:
            components.setdefault("new_outcome_bonus", WEIGHT_NEW_OUTCOME)
    if pending.get("population_spec"):
        from modules.edge_research.research_grammar import PopulationSpec
        ph = PopulationSpec.from_dict(pending["population_spec"]).content_hash()
        if ph not in known_pops:
            components.setdefault("new_population_bonus", WEIGHT_NEW_POPULATION)

    return components


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


def _falsification_match(
    assessment: ResearchAssessment,
    candidate: ResearchActionCandidate,
    graph: ResearchGraph,
) -> float:
    if candidate.intent != ActionIntent.FALSIFICATION.value:
        return 0.0
    if candidate.uncertainty_addressed not in assessment.possible_falsification_targets:
        return 0.0
    base = candidate.priority_hints.get("falsification_threat", WEIGHT_FALSIFICATION_THREAT)
    # Reduce falsification priority if that exact sensitivity test already ran.
    if candidate.tool_name in assessment.branch_tools_attempted:
        return base * 0.2
    ctx = _session_coverage_context(graph)
    if ctx["early_session"] and ctx["low_coverage"] and assessment.conditional_candidate:
        return base
    if ctx["early_session"] and ctx["low_coverage"] and not assessment.conditional_candidate:
        return base * EARLY_SESSION_FALSIFICATION_DAMPEN
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
    *,
    experiment_node_id: Optional[str] = None,
) -> Tuple[float, Dict[str, float]]:
    """Deterministic score with auditable components."""
    if candidate.blocked and candidate.intent not in (ActionIntent.STOP.value, ActionIntent.ABANDON.value):
        return BLOCKED_SCORE, {"blocked": BLOCKED_SCORE}

    components: Dict[str, float] = {}
    components["information_gap"] = _gap_match(assessment, candidate)
    components["falsification_threat"] = _falsification_match(assessment, candidate, graph)
    components["novelty"] = _novelty_bonus(assessment, candidate)
    components["grammar"] = _grammar_bonus(candidate)
    components["adaptive"] = _adaptive_bonus(candidate)
    components["stop"] = _stop_score(assessment, candidate)
    components["abandon"] = _abandon_score(assessment, candidate)
    components.update(_coverage_bonuses(candidate, graph))
    components.update(_frame_diversity_bonuses(candidate, graph))
    components["stop_branch_penalty"] = _stop_branch_penalty(candidate, graph)
    components["stop_session_block"] = _stop_session_score(candidate)

    exp_id = experiment_node_id or assessment.source_experiment_node_id
    if exp_id:
        pen_total, pen_parts = _complexity_penalty(graph, exp_id)
        components.update(pen_parts)
        components["draft_complexity_penalty"] = -_branch_complexity_penalty_for_candidate(candidate)
        components["skepticism_escalation"] = _skepticism_bonus(
            assessment, candidate, graph, exp_id
        )
        components["strong_evidence_exploration"] = _strong_evidence_exploration_bonus(
            assessment, candidate, graph, exp_id
        )
        components["weak_complexity_stop"] = _weak_complexity_stop_bonus(
            assessment, candidate, graph, exp_id
        )

    total = sum(components.values())
    return total, components


def plan_next_action(
    assessment: ResearchAssessment,
    candidates: Sequence[ResearchActionCandidate],
    graph: ResearchGraph,
    *,
    experiment_node_id: Optional[str] = None,
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
        total, components = score_candidate(
            candidate, assessment, graph, experiment_node_id=experiment_node_id
        )
        if budget_exhausted and candidate.intent == ActionIntent.STOP.value:
            total += WEIGHT_STOP * 2
            components["budget_exhausted"] = WEIGHT_STOP * 2
        scored.append((total, candidate, components))

    scored.sort(key=lambda x: (-x[0], x[1].action_id))

    if not scored:
        return PlanDecision(
            decision_type=PlanDecisionType.STOP_BRANCH,
            selected=None,
            all_candidates=tuple(candidates),
            score_breakdown={"reason": "NO_CANDIDATES"},
            rationale_codes=("STOP_BRANCH", "NO_CANDIDATES"),
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
                    decision_type=PlanDecisionType.STOP_BRANCH,
                    selected=cand,
                    all_candidates=tuple(candidates),
                    score_breakdown={"components": comp, "total": total},
                    rationale_codes=cand.rationale_codes,
                )

    if best.intent == ActionIntent.STOP.value:
        return PlanDecision(
            decision_type=PlanDecisionType.STOP_BRANCH,
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
            decision_type=PlanDecisionType.STOP_BRANCH,
            selected=stop_cand,
            all_candidates=tuple(candidates),
            score_breakdown={"reason": "BUDGET_EXHAUSTED"},
            rationale_codes=("STOP_BRANCH", "BUDGET_EXHAUSTED"),
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
    *,
    experiment_node_id: Optional[str] = None,
) -> Dict[str, Tuple[float, Dict[str, float]]]:
    """Expose scores for tests and audit."""
    return {
        c.action_id: score_candidate(
            c, assessment, graph, experiment_node_id=experiment_node_id
        )
        for c in candidates
    }
