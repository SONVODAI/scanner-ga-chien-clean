"""
Deterministic research session controller for Edge Research (PATCH 3C).

Orchestrates: execute → interpret → generate → plan → graph update.
No LLM, no production coupling, no arbitrary code execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.research_actions import (
    ResearchActionCandidate,
    generate_action_candidates,
)
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_graph import ResearchGraph, ResearchGraphError
from modules.edge_research.research_interpreter import interpret_tool_result
from modules.edge_research.research_planner import PlanDecision, PlanDecisionType, plan_next_action, score_all_candidates
from modules.edge_research.research_grammar import OutcomeSpec, PopulationSpec
from modules.edge_research.research_search_accounting import (
    build_candidate_research_summary,
    build_parent_comparison,
    lineage_step_roles,
    record_candidates_considered,
    record_experiment_executed,
)
from modules.edge_research.research_state import (
    NextActionCandidate,
    NodeStatus,
    NodeType,
    QuestionRationale,
    ResearchQuestionContext,
    SessionStatus,
)
from modules.edge_research.research_tools import ToolRegistry, ToolResult, execute_research_experiment
from modules.edge_research.storage import write_research_graph

DEFAULT_SESSION_EXPERIMENT_BUDGET = 12


@dataclass
class PlanningRecord:
    """Audit record for one plan-after-experiment step."""

    experiment_node_id: str
    assessment: ResearchAssessment
    decision: PlanDecision
    candidate_scores: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ControllerStepResult:
    tool_result: Optional[ToolResult]
    planning: Optional[PlanningRecord]
    spawned_question_id: Optional[str] = None
    spawned_experiment_id: Optional[str] = None
    terminal: bool = False
    terminal_reason: str = ""


def record_planning_on_experiment(
    graph: ResearchGraph,
    experiment_node_id: str,
    *,
    assessment: ResearchAssessment,
    decision: PlanDecision,
    candidate_scores: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist candidate set, selected action, and uncertainties on experiment node."""
    node = graph.get_node(experiment_node_id)
    if node.node_type != NodeType.EXPERIMENT:
        raise ResearchGraphError("Planning record requires EXPERIMENT node")

    scored = candidate_scores or {}
    next_actions: List[NextActionCandidate] = []
    for cand in decision.all_candidates:
        entry = scored.get(cand.action_id, {})
        total = entry.get("total") if isinstance(entry, dict) else None
        next_actions.append(cand.to_next_action_candidate(score=total))

    node.candidate_next_actions = next_actions
    if decision.selected is not None:
        sel_entry = scored.get(decision.selected.action_id, {})
        sel_total = sel_entry.get("total") if isinstance(sel_entry, dict) else None
        node.selected_next_action = decision.selected.to_next_action_candidate(score=sel_total)
    node.uncertainties = list(assessment.unresolved_uncertainties)


def _enrich_candidates_with_search_hints(
    candidates: Tuple[ResearchActionCandidate, ...],
    tool_result: ToolResult,
) -> Tuple[ResearchActionCandidate, ...]:
    """Attach metric-derived hints for complexity/skepticism scoring."""
    metrics = tool_result.metrics or {}
    base_hints = {
        "observed_success_rate": metrics.get("best_group_success_rate")
        or metrics.get("success_rate")
        or metrics.get("baseline_success_rate"),
        "sample_size": tool_result.sample_size,
        "shape_strength": (metrics.get("shape") or {}).get("strength"),
        "threshold_strength": metrics.get("threshold_strength"),
    }
    enriched: List[ResearchActionCandidate] = []
    for c in candidates:
        merged_hints = dict(c.priority_hints)
        for k, v in base_hints.items():
            if v is not None:
                merged_hints.setdefault(k, v)
        enriched.append(
            ResearchActionCandidate(
                action_id=c.action_id,
                action_code=c.action_code,
                intent=c.intent,
                question_template_id=c.question_template_id,
                question_text=c.question_text,
                tool_name=c.tool_name,
                tool_version=c.tool_version,
                draft_spec=c.draft_spec,
                uncertainty_addressed=c.uncertainty_addressed,
                expected_information=c.expected_information,
                budget_cost=c.budget_cost,
                already_attempted=c.already_attempted,
                blocked=c.blocked,
                blocked_reason=c.blocked_reason,
                rationale_codes=c.rationale_codes,
                priority_hints=merged_hints,
            )
        )
    return tuple(enriched)


def _maybe_build_candidate_summary(
    graph: ResearchGraph,
    experiment_node_id: str,
    assessment: ResearchAssessment,
    tool_result: ToolResult,
) -> None:
    """Persist research-only candidate summary on experiment node when interesting."""
    if not assessment.interesting:
        return
    exp = graph.get_node(experiment_node_id)
    ctx = None
    for pid in exp.parent_node_ids:
        parent = graph.get_node(pid)
        if parent.question_context is not None:
            ctx = parent.question_context
            break
    if ctx is None:
        return

    pop = PopulationSpec.from_dict(ctx.population_spec)
    out = OutcomeSpec.from_dict(ctx.outcome_spec)
    state = graph.get_search_accounting()
    from modules.edge_research.research_search_accounting import branch_root_id

    root = branch_root_id(graph, experiment_node_id)
    branch_ledger = state.branch_ledgers.get(root, state.session_ledger)

    parent_cmp = None
    if pop.parent is not None or pop.kind == "refine":
        parent_pop = pop.parent if pop.parent else PopulationSpec.all_()
        parent_cmp = build_parent_comparison(
            parent_pop,
            out,
            pop,
            out,
            parent_effect=tool_result.metrics.get("baseline_success_rate"),
            candidate_effect=tool_result.metrics.get("best_group_success_rate")
            or tool_result.metrics.get("success_rate"),
            parent_n=tool_result.metrics.get("baseline_n"),
            candidate_n=tool_result.sample_size,
        )

    summary = build_candidate_research_summary(
        candidate_id=experiment_node_id,
        population_spec=pop,
        outcome_spec=out,
        branch_ledger=branch_ledger,
        session_ledger=state.session_ledger,
        metrics=dict(tool_result.metrics),
        assessment_fragility=assessment.fragility_evidence,
        assessment_concentration=assessment.concentration_concerns,
        interesting=assessment.interesting,
        parent_comparison=parent_cmp,
        lineage_roles=lineage_step_roles(graph, experiment_node_id),
        discovery_cutoff=graph.session.data_cutoff_date,
    )
    exp.candidate_summary = summary.to_dict()
    exp.research_status = summary.current_research_status
    state.candidate_summaries[experiment_node_id] = summary.to_dict()
    graph.persist_search_accounting()


def plan_after_experiment(
    graph: ResearchGraph,
    experiment_node_id: str,
    tool_result: ToolResult,
    registry: ToolRegistry,
    *,
    research_scope: Optional[Dict[str, Any]] = None,
) -> PlanningRecord:
    """Interpret result, generate candidates, plan next step, record on graph."""
    assessment = interpret_tool_result(graph, experiment_node_id, tool_result)
    candidates = generate_action_candidates(
        assessment,
        graph,
        registry,
        research_scope=research_scope,
        experiment_node_id=experiment_node_id,
    )
    candidates = _enrich_candidates_with_search_hints(candidates, tool_result)
    record_candidates_considered(
        graph.get_search_accounting(), graph, experiment_node_id, len(candidates)
    )
    graph.persist_search_accounting()
    scores = score_all_candidates(
        assessment, candidates, graph, experiment_node_id=experiment_node_id
    )
    decision = plan_next_action(
        assessment, candidates, graph, experiment_node_id=experiment_node_id
    )
    serializable_scores = {
        aid: {"total": total, "components": comp}
        for aid, (total, comp) in scores.items()
    }
    record_planning_on_experiment(
        graph,
        experiment_node_id,
        assessment=assessment,
        decision=decision,
        candidate_scores=serializable_scores,
    )
    _maybe_build_candidate_summary(graph, experiment_node_id, assessment, tool_result)
    return PlanningRecord(
        experiment_node_id=experiment_node_id,
        assessment=assessment,
        decision=decision,
        candidate_scores=serializable_scores,
    )


def apply_plan_decision(
    graph: ResearchGraph,
    experiment_node_id: str,
    decision: PlanDecision,
) -> ControllerStepResult:
    """Apply planner decision to graph — spawn next experiment or terminate branch."""
    if decision.decision_type == PlanDecisionType.STOP:
        reason = "STOP_NO_FURTHER_VALUE"
        if decision.selected:
            reason = decision.selected.action_code
        graph.resolve_node(experiment_node_id, terminal_reason=reason)
        for pid in graph.get_node(experiment_node_id).parent_node_ids:
            parent = graph.get_node(pid)
            if parent.node_type == NodeType.QUESTION and parent.status == NodeStatus.OPEN:
                graph.resolve_node(pid, terminal_reason=reason)
        _maybe_close_session(graph)
        return ControllerStepResult(
            tool_result=None,
            planning=None,
            terminal=True,
            terminal_reason=reason,
        )

    if decision.decision_type == PlanDecisionType.ABANDON:
        reason = decision.selected.action_code if decision.selected else "ABANDON_FRAGILE"
        graph.abandon_node(experiment_node_id, reason=reason)
        for pid in graph.get_node(experiment_node_id).parent_node_ids:
            parent = graph.get_node(pid)
            if parent.node_type == NodeType.QUESTION and parent.status == NodeStatus.OPEN:
                graph.abandon_node(pid, reason=reason)
        _maybe_close_session(graph)
        return ControllerStepResult(
            tool_result=None,
            planning=None,
            terminal=True,
            terminal_reason=reason,
        )

    selected = decision.selected
    if selected is None or selected.draft_spec is None:
        raise ResearchGraphError("EXPERIMENT decision missing draft ExperimentSpec")

    pending_ctx: Optional[ResearchQuestionContext] = None
    scope = selected.draft_spec.research_scope
    if scope.get("pending_question_context"):
        pending_ctx = ResearchQuestionContext.from_dict(scope["pending_question_context"])

    evidence_summary = {
        "uncertainty_addressed": selected.uncertainty_addressed,
        "intent": selected.intent,
        "planner_rationale": list(decision.rationale_codes),
    }
    if scope.get("pending_lineage"):
        evidence_summary["lineage"] = dict(scope["pending_lineage"])
        evidence_summary["triggering_experiment"] = scope["pending_lineage"].get(
            "triggering_experiment", experiment_node_id
        )
        evidence_summary["triggering_observation"] = scope["pending_lineage"].get(
            "triggering_observation", selected.action_code
        )

    qid = graph.spawn_child_question_from_experiment(
        experiment_node_id,
        question_text=selected.question_text,
        reason_code=selected.action_code,
        evidence_summary=evidence_summary,
        question_context=pending_ctx,
    )
    eid = graph.add_experiment(question_node_id=qid, spec=selected.draft_spec)
    return ControllerStepResult(
        tool_result=None,
        planning=None,
        spawned_question_id=qid,
        spawned_experiment_id=eid,
        terminal=False,
    )


def _maybe_persist_graph(
    graph: ResearchGraph,
    *,
    auto_persist: bool,
    persist_dir: Optional[Path],
) -> None:
    if auto_persist and persist_dir is not None:
        write_research_graph(graph, data_dir=persist_dir)


def run_experiment_and_plan(
    graph: ResearchGraph,
    experiment_node_id: str,
    panel: pd.DataFrame,
    registry: ToolRegistry,
    *,
    research_scope: Optional[Dict[str, Any]] = None,
    auto_persist: bool = False,
    persist_dir: Optional[Path] = None,
) -> ControllerStepResult:
    """Execute tool, attach result, interpret, plan, and apply decision."""
    tool_result = execute_research_experiment(
        graph, experiment_node_id, registry, panel
    )
    record_experiment_executed(graph.get_search_accounting(), graph, experiment_node_id)
    graph.persist_search_accounting()
    planning = plan_after_experiment(
        graph, experiment_node_id, tool_result, registry, research_scope=research_scope
    )
    step = apply_plan_decision(graph, experiment_node_id, planning.decision)
    step.tool_result = tool_result
    step.planning = planning
    _maybe_persist_graph(graph, auto_persist=auto_persist, persist_dir=persist_dir)
    return step


def _has_active_research_frontier(graph: ResearchGraph) -> bool:
    for node in graph.nodes.values():
        if node.node_type == NodeType.QUESTION and node.status == NodeStatus.OPEN:
            return True
        if node.node_type == NodeType.EXPERIMENT and node.status == NodeStatus.RUNNING:
            return True
    return False


def _maybe_close_session(graph: ResearchGraph) -> None:
    if not _has_active_research_frontier(graph):
        graph.set_session_status(SessionStatus.NO_EDGE_FOUND)


def run_research_session(
    graph: ResearchGraph,
    panel: pd.DataFrame,
    registry: ToolRegistry,
    *,
    initial_experiment_id: str,
    research_scope: Optional[Dict[str, Any]] = None,
    max_steps: int = DEFAULT_SESSION_EXPERIMENT_BUDGET,
    auto_persist: bool = False,
    persist_dir: Optional[Path] = None,
) -> List[ControllerStepResult]:
    """
    Minimal deterministic research loop starting from a pending experiment node.

    Executes up to max_steps experiments, replanning after each result.
    """
    steps: List[ControllerStepResult] = []
    current_exp = initial_experiment_id

    for _ in range(max_steps):
        if graph.get_node(current_exp).experiment_result is not None:
            break
        step = run_experiment_and_plan(
            graph,
            current_exp,
            panel,
            registry,
            research_scope=research_scope,
            auto_persist=auto_persist,
            persist_dir=persist_dir,
        )
        steps.append(step)
        if step.terminal:
            break
        if step.spawned_experiment_id is None:
            break
        current_exp = step.spawned_experiment_id

    if auto_persist and persist_dir is not None:
        write_research_graph(graph, data_dir=persist_dir)

    return steps
