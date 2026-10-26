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
from modules.edge_research.research_frontier import (
    FrontierItem,
    SessionStopReason,
    evaluate_global_stop,
)
from modules.edge_research.research_frame import (
    FrameStatus,
    ResearchFrame,
    assess_frame_saturation,
    frame_from_question_context,
)
from modules.edge_research.research_graph import ResearchGraph, ResearchGraphError
from modules.edge_research.research_interpreter import interpret_tool_result
from modules.edge_research.research_panel_preflight import (
    build_panel_preflight,
    filter_candidates_for_panel,
    validate_action_against_panel,
)
from modules.edge_research.research_capability_registry import (
    ensure_session_capability_registry,
    record_experiment_capability_exercise,
)
from modules.edge_research.research_data_expansion_audit import ensure_session_expansion_audit
from modules.edge_research.research_provenance_proof import ensure_session_provenance_proof
from modules.edge_research.research_exposure_governance import ensure_session_exposure_contract
from modules.edge_research.research_exposure_governance import record_experiment_exposure_exercises
from modules.edge_research.research_planner import PlanDecision, PlanDecisionType, plan_next_action, score_all_candidates
from modules.edge_research.research_portfolio import (
    BranchPortfolioStatus,
    compute_session_portfolio_metrics,
    record_branch_revisit,
    record_dimension_experiment,
    update_branch_on_experiment,
    update_branch_on_leave,
)
from modules.edge_research.research_grammar import OutcomeSpec, PopulationSpec
from modules.edge_research.research_search_accounting import (
    build_candidate_research_summary,
    build_parent_comparison,
    lineage_step_roles,
    record_candidates_considered,
    record_experiment_executed,
    branch_root_id,
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
    session_terminal: bool = False
    branch_terminal: bool = False
    terminal_reason: str = ""


def _update_frame_from_experiment(
    graph: ResearchGraph,
    experiment_node_id: str,
    assessment: ResearchAssessment,
    tool_result: ToolResult,
) -> None:
    """Accumulate frame-level stats after each experiment."""
    exp = graph.get_node(experiment_node_id)
    frame_id = ""
    for pid in exp.parent_node_ids:
        parent = graph.get_node(pid)
        if parent.question_context:
            frame_id = parent.question_context.frame_id
            break

    reg = graph.get_frame_registry()
    if not frame_id:
        frame_id = reg.active_frame_id
    frame = reg.get(frame_id)
    if frame is None:
        return

    frame.experiments_in_frame += 1
    if exp.experiment_spec:
        inputs = exp.experiment_spec.inputs or {}
        for key in ("feature_column", "partition_column", "primary_feature"):
            if key in inputs:
                feat = str(inputs[key])
                if feat not in frame.features_explored:
                    frame.features_explored = frame.features_explored + (feat,)

    if assessment.conditional_candidate:
        frame.candidate_yield += 1
    if assessment.possible_falsification_targets and exp.experiment_spec:
        if exp.experiment_spec.tool_name == "sensitivity_analysis":
            frame.falsification_yield += 1

    codes = {o.code for o in tool_result.structured_observations}
    if "SHAPE_FLAT" in codes or "SHAPE_NOISY" in codes or "NO_CLEAR_DIFFERENCE" in codes:
        frame.flat_noisy_count += 1

    status, _ = assess_frame_saturation(frame)
    frame.status = status

    portfolio = graph.get_portfolio_state()
    mig = 0.5 if assessment.interesting else 0.1
    if assessment.conditional_candidate:
        mig = 1.0
    codes = set(assessment.branch_observation_codes)
    if "SHAPE_FLAT" in codes or "NO_CLEAR_DIFFERENCE" in codes:
        mig = 0.05
    frame.information_gain_score = frame.information_gain_score * 0.7 + mig * 0.3
    from modules.edge_research.research_search_accounting import compute_complexity_score, branch_depth
    branch_ledger = graph.get_search_accounting().branch_ledgers.get(
        branch_root_id(graph, experiment_node_id),
        graph.get_search_accounting().session_ledger,
    )
    frame.complexity_burden = compute_complexity_score(
        branch_ledger, branch_depth=branch_depth(graph, experiment_node_id)
    ).aggregate_score

    reg.frames[frame_id] = frame
    graph.persist_frames()


def _resolve_parent_frame_id(graph: ResearchGraph, experiment_node_id: str) -> str:
    """Resolve parent frame ID from question context, falling back to active frame."""
    reg = graph.get_frame_registry()
    for pid in graph.get_node(experiment_node_id).parent_node_ids:
        parent = graph.get_node(pid)
        if parent.question_context and parent.question_context.frame_id:
            return parent.question_context.frame_id
    return reg.active_frame_id


def _ensure_parent_frame_registered(
    graph: ResearchGraph,
    parent_frame_id: str,
    experiment_node_id: str,
) -> str:
    """Ensure parent frame exists in registry; reconstruct from question context if needed."""
    reg = graph.get_frame_registry()
    if parent_frame_id and reg.get(parent_frame_id):
        return parent_frame_id

    for pid in graph.get_node(experiment_node_id).parent_node_ids:
        parent = graph.get_node(pid)
        if parent.question_context is None:
            continue
        ctx = parent.question_context
        fid = parent_frame_id or ctx.frame_id or reg.active_frame_id
        if not fid:
            fid = reg.next_id()
        if reg.get(fid) is None:
            pop = PopulationSpec.from_dict(ctx.population_spec)
            out = OutcomeSpec.from_dict(ctx.outcome_spec)
            preflight = graph.session.panel_preflight or {}
            eligible = len(preflight.get("eligible_explanatory") or [])
            frame = frame_from_question_context(
                fid,
                pop,
                out,
                observation_horizon=ctx.observation_horizon,
            )
            frame.eligible_feature_count = eligible
            frame.status = FrameStatus.UNDEREXPLORED.value
            reg.register(frame, set_active=not bool(reg.active_frame_id))
            graph.persist_frames()
        return fid
    return parent_frame_id


def _register_frame_transition_on_spawn(
    graph: ResearchGraph,
    *,
    pending_ctx: Optional[ResearchQuestionContext],
    parent_frame_id: str,
    experiment_node_id: str,
    planner_action_code: str = "",
    planner_score: Optional[float] = None,
) -> None:
    """Record frame lineage when spawning a reframe question — before downstream operations."""
    if pending_ctx is None or not pending_ctx.frame_id:
        return

    parent_frame_id = _ensure_parent_frame_registered(
        graph, parent_frame_id, experiment_node_id
    )
    if not parent_frame_id:
        return
    if pending_ctx.frame_id == parent_frame_id:
        return

    reg = graph.get_frame_registry()
    old = reg.get(parent_frame_id)
    if old is None:
        return

    pop = PopulationSpec.from_dict(pending_ctx.population_spec)
    out = OutcomeSpec.from_dict(pending_ctx.outcome_spec)
    pc = pending_ctx.population_change or {}
    new_frame = ResearchFrame(
        frame_id=pending_ctx.frame_id,
        population=pop,
        outcome=out,
        observation_horizon=pending_ctx.observation_horizon,
        parent_frame_id=parent_frame_id,
        reason_created=str(pc.get("reason_code", "REFRAME")),
        triggering_evidence=dict(pc.get("triggering_evidence") or {}),
        transformation=str(pc.get("reason_code", "REFRAME")),
        frame_depth=old.frame_depth + 1,
        eligible_feature_count=old.eligible_feature_count,
        status=FrameStatus.UNDEREXPLORED.value,
    )
    reg.record_transition(
        old,
        new_frame,
        trigger=pc.get("reason_code", "REFRAME"),
        sample_n=pending_ctx.population_n,
        triggering_experiment_id=experiment_node_id,
        planner_action_code=planner_action_code,
        planner_score=planner_score,
    )
    graph.persist_frames()


def _record_session_failure(
    graph: ResearchGraph,
    *,
    experiment_node_id: str,
    operation: str,
    error: Exception,
    tool_result: Optional[ToolResult] = None,
) -> None:
    """Mark session ERROR/INCOMPLETE with auditable failure context; preserve committed lineage."""
    exp = graph.get_node(experiment_node_id)
    frame_id = ""
    for pid in exp.parent_node_ids:
        parent = graph.get_node(pid)
        if parent.question_context:
            frame_id = parent.question_context.frame_id or graph.get_frame_registry().active_frame_id
            break

    graph.set_session_status(SessionStatus.ERROR)
    graph.session.session_stop_reason = {
        "code": "DOWNSTREAM_FAILURE",
        "operation": operation,
        "experiment_node_id": experiment_node_id,
        "frame_id": frame_id,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "experiment_executed": tool_result is not None,
    }
    if tool_result is not None:
        exp.terminal_reason = f"PLANNING_FAILED:{operation}"
    graph.persist_frames()
    graph.persist_frontier()
    graph.persist_search_accounting()


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
        conditional_candidate=assessment.conditional_candidate,
        parent_comparison=parent_cmp,
        lineage_roles=lineage_step_roles(graph, experiment_node_id),
        discovery_cutoff=graph.session.data_cutoff_date,
    )
    exp.candidate_summary = summary.to_dict()
    exp.research_status = summary.current_research_status
    state.candidate_summaries[experiment_node_id] = summary.to_dict()
    graph.persist_search_accounting()


def _question_context_dict(graph: ResearchGraph, experiment_node_id: str) -> Dict[str, Any]:
    exp = graph.get_node(experiment_node_id)
    for pid in exp.parent_node_ids:
        parent = graph.get_node(pid)
        if parent.question_context is not None:
            return parent.question_context.to_dict()
    return {}


def _enqueue_frontier_from_planning(
    graph: ResearchGraph,
    experiment_node_id: str,
    decision: PlanDecision,
    candidate_scores: Dict[str, Any],
) -> None:
    """Add non-selected viable candidates to session frontier."""
    from modules.edge_research.research_search_accounting import branch_root_id as _branch_root

    frontier = graph.get_frontier()
    scores = {
        aid: (entry.get("total", 0.0), entry.get("components", {}))
        for aid, entry in candidate_scores.items()
        if isinstance(entry, dict)
    }
    selected_id = decision.selected.action_id if decision.selected else None
    root = _branch_root(graph, experiment_node_id)
    portfolio = graph.get_portfolio_state()
    frontier.add_from_candidates(
        candidates=decision.all_candidates,
        scores=scores,
        parent_experiment_node_id=experiment_node_id,
        branch_root_id=root,
        selected_action_id=selected_id,
        question_context=_question_context_dict(graph, experiment_node_id),
        enqueued_sequence=portfolio.sequence_counter,
    )
    graph.persist_frontier()


def _is_budget_exhausted(graph: ResearchGraph) -> bool:
    """True when no further experiments may be scheduled under session budget."""
    budget = graph.session.experiment_budget
    if budget is None:
        return False
    return graph.session.experiments_used >= budget


def _count_unresolved_promising_deferred(graph: ResearchGraph) -> int:
    portfolio = graph.get_portfolio_state()
    return sum(
        1
        for branch in portfolio.branches.values()
        if branch.status == BranchPortfolioStatus.DEFERRED_PROMISING.value
    )


def build_budget_exhausted_stop_reason(
    graph: ResearchGraph,
    final_experiment_id: str,
) -> SessionStopReason:
    """Structured session stop when experiment budget is fully consumed."""
    features_touched, eligible_count = _coverage_counts(graph)
    frontier = graph.get_frontier()
    budget = graph.session.experiment_budget or 0
    return SessionStopReason(
        code="BUDGET_EXHAUSTED",
        detail="Experiment budget exhausted",
        remaining_budget=0,
        unexplored_frontier_count=len(frontier.unexplored_items()),
        features_touched=features_touched,
        eligible_features=eligible_count,
        terminal_status="BUDGET_EXHAUSTED",
        experiment_budget=budget,
        experiments_executed=graph.session.experiments_used,
        final_experiment_id=final_experiment_id,
        unresolved_promising_deferred_count=_count_unresolved_promising_deferred(graph),
    )


def _apply_post_experiment_bookkeeping(
    graph: ResearchGraph,
    experiment_node_id: str,
    assessment: ResearchAssessment,
    tool_result: ToolResult,
) -> None:
    """Persist audit, frame, branch, and dimension state for a completed experiment."""
    _maybe_build_candidate_summary(graph, experiment_node_id, assessment, tool_result)
    _update_frame_from_experiment(graph, experiment_node_id, assessment, tool_result)

    root = branch_root_id(graph, experiment_node_id)
    mig = 0.5 if assessment.interesting else 0.1
    if assessment.conditional_candidate:
        mig = 1.0
    unresolved = mig * 2.0 if assessment.additional_investigation_warranted else 0.0
    update_branch_on_experiment(
        graph,
        branch_root_id=root,
        assessment=assessment,
        marginal_gain=mig,
        unresolved_value=unresolved,
    )

    exp = graph.get_node(experiment_node_id)
    if exp.experiment_spec:
        inputs = exp.experiment_spec.inputs or {}
        feat = ""
        for key in ("feature_column", "partition_column", "primary_feature"):
            if key in inputs:
                feat = str(inputs[key])
                break
        qctx = _question_context_dict(graph, experiment_node_id)
        out_h = ""
        pop_h = ""
        frame_id = ""
        if qctx.get("outcome_spec"):
            out_h = OutcomeSpec.from_dict(qctx["outcome_spec"]).content_hash()
        if qctx.get("population_spec"):
            pop_h = PopulationSpec.from_dict(qctx["population_spec"]).content_hash()
        frame_id = str(qctx.get("frame_id") or "")
        record_dimension_experiment(
            graph,
            feature=feat,
            outcome_hash=out_h,
            population_hash=pop_h,
            frame_id=frame_id,
            tool=exp.experiment_spec.tool_name,
        )


def _terminate_session_on_budget_exhaustion(
    graph: ResearchGraph,
    experiment_node_id: str,
    tool_result: ToolResult,
    *,
    research_scope: Optional[Dict[str, Any]] = None,
) -> PlanningRecord:
    """
    Finalize the last allowed experiment without entering planning/spawn.

    Order: interpret → bookkeeping → budget stop reason → session finalize.
    """
    assessment = interpret_tool_result(graph, experiment_node_id, tool_result)
    _apply_post_experiment_bookkeeping(
        graph, experiment_node_id, assessment, tool_result
    )
    reason = build_budget_exhausted_stop_reason(graph, experiment_node_id)
    finalize_session(graph, reason)
    graph.persist_search_accounting()
    graph.persist_portfolio_state()
    return PlanningRecord(
        experiment_node_id=experiment_node_id,
        assessment=assessment,
        decision=PlanDecision(
            decision_type=PlanDecisionType.STOP_SESSION,
            selected=None,
            all_candidates=[],
            score_breakdown={"reason": "BUDGET_EXHAUSTED"},
            rationale_codes=("STOP_SESSION", "BUDGET_EXHAUSTED"),
        ),
        candidate_scores={},
    )


def plan_after_experiment(
    graph: ResearchGraph,
    experiment_node_id: str,
    tool_result: ToolResult,
    registry: ToolRegistry,
    *,
    research_scope: Optional[Dict[str, Any]] = None,
    panel_columns: Optional[Tuple[str, ...]] = None,
) -> PlanningRecord:
    """Interpret result, generate candidates, plan next step, record on graph."""
    assessment = interpret_tool_result(graph, experiment_node_id, tool_result)
    candidates = generate_action_candidates(
        assessment,
        graph,
        registry,
        research_scope=research_scope,
        experiment_node_id=experiment_node_id,
        panel_columns=panel_columns,
    )
    if panel_columns:
        candidates = filter_candidates_for_panel(candidates, panel_columns)
    candidates = _enrich_candidates_with_search_hints(candidates, tool_result)
    record_candidates_considered(
        graph.get_search_accounting(), graph, experiment_node_id, len(candidates)
    )
    graph.persist_search_accounting()
    scores = score_all_candidates(
        assessment, candidates, graph, experiment_node_id=experiment_node_id
    )
    local_decision = plan_next_action(
        assessment, candidates, graph, experiment_node_id=experiment_node_id
    )
    from modules.edge_research.research_global_allocator import (
        apply_global_allocation_to_plan_decision,
        select_global_research_opportunity,
    )
    from modules.edge_research.research_portfolio import score_opportunities_for_selection
    from modules.edge_research.research_search_accounting import branch_root_id as _branch_root

    root = _branch_root(graph, experiment_node_id)
    local_opps, _ = score_opportunities_for_selection(
        graph,
        assessment,
        candidates,
        scores,
        experiment_node_id=experiment_node_id,
        branch_root_id=root,
    )
    allocation = select_global_research_opportunity(
        graph,
        assessment,
        candidates,
        scores,
        local_decision,
        experiment_node_id=experiment_node_id,
        panel_columns=panel_columns,
    )
    decision = apply_global_allocation_to_plan_decision(
        graph,
        local_decision,
        allocation,
        local_opportunities=local_opps,
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
    _apply_post_experiment_bookkeeping(
        graph, experiment_node_id, assessment, tool_result
    )

    _enqueue_frontier_from_planning(
        graph, experiment_node_id, decision, serializable_scores
    )
    return PlanningRecord(
        experiment_node_id=experiment_node_id,
        assessment=assessment,
        decision=decision,
        candidate_scores=serializable_scores,
    )


def _resolve_branch(graph: ResearchGraph, experiment_node_id: str, reason: str) -> None:
    graph.resolve_node(experiment_node_id, terminal_reason=reason)
    for pid in graph.get_node(experiment_node_id).parent_node_ids:
        parent = graph.get_node(pid)
        if parent.node_type == NodeType.QUESTION and parent.status == NodeStatus.OPEN:
            graph.resolve_node(pid, terminal_reason=reason)


def _coverage_counts(graph: ResearchGraph) -> Tuple[int, int]:
    state = graph.get_search_accounting()
    preflight = graph.session.panel_preflight or {}
    eligible = preflight.get("eligible_explanatory") or []
    return len(state.session_ledger.explanatory_features_tested), len(eligible)


def _remaining_budget(graph: ResearchGraph) -> int:
    budget = graph.session.experiment_budget
    if budget is None:
        return 999999
    return max(0, budget - graph.session.experiments_used)


def _has_conditional_candidates(graph: ResearchGraph) -> bool:
    for node in graph.nodes.values():
        if node.research_status == "CANDIDATE_DISCOVERED":
            return True
        summary = node.candidate_summary or {}
        if summary.get("current_research_status") == "CANDIDATE_DISCOVERED":
            return True
    return False


def _session_status_from_stop(reason: SessionStopReason) -> SessionStatus:
    code = reason.code
    if code == "BUDGET_EXHAUSTED":
        return SessionStatus.BUDGET_EXHAUSTED
    if code == "NO_VALID_FRONTIER":
        if _has_conditional_candidates(graph=None):  # noqa — patched below
            pass
        return SessionStatus.NO_VALID_FRONTIER
    if code in ("INSUFFICIENT_RESEARCH_VALUE", "CONTINUE", "CONTINUE_LOW_COVERAGE"):
        return SessionStatus.NO_EDGE_FOUND
    return SessionStatus.NO_EDGE_FOUND


def finalize_session(
    graph: ResearchGraph,
    reason: SessionStopReason,
) -> None:
    """Apply global session terminal status — never leave session ACTIVE."""
    graph.session.session_stop_reason = reason.to_dict()
    if reason.code == "BUDGET_EXHAUSTED":
        graph.set_session_status(SessionStatus.BUDGET_EXHAUSTED)
    elif reason.code == "NO_VALID_FRONTIER":
        if _has_conditional_candidates(graph):
            graph.set_session_status(SessionStatus.RESEARCH_COMPLETE_WITH_CANDIDATES)
        else:
            graph.set_session_status(SessionStatus.NO_EDGE_FOUND)
    elif reason.code == "INSUFFICIENT_RESEARCH_VALUE":
        graph.set_session_status(SessionStatus.NO_EDGE_FOUND)
    else:
        graph.set_session_status(SessionStatus.NO_EDGE_FOUND)
    graph.persist_frontier()


def evaluate_and_maybe_stop_session(graph: ResearchGraph) -> Tuple[bool, SessionStopReason]:
    """Global stopping evaluation — session stop requires frontier inspection."""
    remaining = _remaining_budget(graph)
    features_touched, eligible_count = _coverage_counts(graph)
    should_stop, reason = evaluate_global_stop(
        remaining_budget=remaining,
        frontier=graph.get_frontier(),
        features_touched=features_touched,
        eligible_feature_count=eligible_count,
    )
    if should_stop:
        finalize_session(graph, reason)
    return should_stop, reason


def _spawn_from_frontier_item(
    graph: ResearchGraph,
    item: FrontierItem,
    panel_columns: Tuple[str, ...],
) -> Optional[str]:
    """Activate frontier item — mark INVALID and return None if panel mismatch."""
    cand = item.to_action_candidate()
    valid, invalid_reason = validate_action_against_panel(cand, panel_columns)
    if not valid:
        graph.get_frontier().mark_invalid(item.frontier_id, invalid_reason)
        graph.persist_frontier()
        return None

    graph.get_frontier().mark_selected(item.frontier_id)
    parent_id = item.parent_experiment_node_id
    if parent_id not in graph.nodes:
        graph.get_frontier().mark_invalid(item.frontier_id, "missing_parent_node")
        graph.persist_frontier()
        return None

    if cand.draft_spec is None:
        graph.get_frontier().mark_invalid(item.frontier_id, "missing_draft_spec")
        graph.persist_frontier()
        return None

    pending_ctx: Optional[ResearchQuestionContext] = None
    scope = cand.draft_spec.research_scope
    if scope.get("pending_question_context"):
        pending_ctx = ResearchQuestionContext.from_dict(scope["pending_question_context"])

    evidence_summary = {
        "uncertainty_addressed": cand.uncertainty_addressed,
        "intent": cand.intent,
        "frontier_id": item.frontier_id,
        "from_frontier": True,
    }
    parent_frame_id = _resolve_parent_frame_id(graph, parent_id)
    _register_frame_transition_on_spawn(
        graph,
        pending_ctx=pending_ctx,
        parent_frame_id=parent_frame_id,
        experiment_node_id=parent_id,
        planner_action_code=cand.action_code,
    )
    qid = graph.spawn_child_question_from_experiment(
        parent_id,
        question_text=cand.question_text or item.question_text,
        reason_code=cand.action_code,
        evidence_summary=evidence_summary,
        question_context=pending_ctx,
    )
    eid = graph.add_experiment(question_node_id=qid, spec=cand.draft_spec)
    graph.persist_frontier()
    return eid


def _neutral_frontier_assessment() -> ResearchAssessment:
    """Minimal assessment for portfolio frontier selection without experiment context."""
    return ResearchAssessment(
        source_experiment_node_id="",
        tool_name="",
        tool_status="OK",
        additional_investigation_warranted=True,
    )


def _select_next_experiment_from_frontier(
    graph: ResearchGraph,
    panel_columns: Tuple[str, ...],
) -> Optional[str]:
    """Deterministically pick next unexplored frontier experiment."""
    frontier = graph.get_frontier()
    assessment = _neutral_frontier_assessment()
    while True:
        item = frontier.select_best_unexplored(graph=graph, assessment=assessment)
        if item is None:
            return None
        eid = _spawn_from_frontier_item(graph, item, panel_columns)
        if eid is not None:
            return eid
        # INVALID item — try next


def apply_plan_decision(
    graph: ResearchGraph,
    experiment_node_id: str,
    decision: PlanDecision,
    *,
    panel_columns: Optional[Tuple[str, ...]] = None,
    planner_score: Optional[float] = None,
) -> ControllerStepResult:
    """Apply planner decision — STOP_BRANCH returns to frontier; STOP_SESSION ends session."""
    if decision.decision_type in (PlanDecisionType.STOP_BRANCH, PlanDecisionType.STOP):
        reason = "STOP_NO_FURTHER_VALUE"
        if decision.selected:
            reason = decision.selected.action_code
        _resolve_branch(graph, experiment_node_id, reason)
        reg = graph.get_frame_registry()
        frame = reg.get(reg.active_frame_id)
        if frame:
            frame.stop_branch_count += 1
            graph.persist_frames()
        root = branch_root_id(graph, experiment_node_id)
        branch = graph.get_portfolio_state().get_branch(root)
        update_branch_on_leave(
            graph,
            branch_root_id=root,
            unresolved_value=branch.unresolved_research_value,
            reason=reason,
        )
        should_stop, _ = evaluate_and_maybe_stop_session(graph)
        if should_stop:
            return ControllerStepResult(
                tool_result=None,
                planning=None,
                terminal=True,
                session_terminal=True,
                branch_terminal=True,
                terminal_reason=reason,
            )
        if panel_columns:
            next_eid = _select_next_experiment_from_frontier(graph, panel_columns)
            if next_eid:
                return ControllerStepResult(
                    tool_result=None,
                    planning=None,
                    spawned_experiment_id=next_eid,
                    terminal=False,
                    branch_terminal=True,
                    terminal_reason=reason,
                )
        return ControllerStepResult(
            tool_result=None,
            planning=None,
            terminal=True,
            session_terminal=False,
            branch_terminal=True,
            terminal_reason=reason,
        )

    if decision.decision_type == PlanDecisionType.STOP_SESSION:
        reason = decision.selected.action_code if decision.selected else "STOP_SESSION"
        _resolve_branch(graph, experiment_node_id, reason)
        _, stop_reason = evaluate_global_stop(
            remaining_budget=_remaining_budget(graph),
            frontier=graph.get_frontier(),
            features_touched=_coverage_counts(graph)[0],
            eligible_feature_count=_coverage_counts(graph)[1],
        )
        finalize_session(graph, stop_reason)
        return ControllerStepResult(
            tool_result=None,
            planning=None,
            terminal=True,
            session_terminal=True,
            branch_terminal=True,
            terminal_reason=reason,
        )

    if decision.decision_type == PlanDecisionType.ABANDON:
        reason = decision.selected.action_code if decision.selected else "ABANDON_FRAGILE"
        graph.abandon_node(experiment_node_id, reason=reason)
        for pid in graph.get_node(experiment_node_id).parent_node_ids:
            parent = graph.get_node(pid)
            if parent.node_type == NodeType.QUESTION and parent.status == NodeStatus.OPEN:
                graph.abandon_node(pid, reason=reason)
        should_stop, _ = evaluate_and_maybe_stop_session(graph)
        if should_stop:
            return ControllerStepResult(
                tool_result=None,
                planning=None,
                terminal=True,
                session_terminal=True,
                branch_terminal=True,
                terminal_reason=reason,
            )
        if panel_columns:
            next_eid = _select_next_experiment_from_frontier(graph, panel_columns)
            if next_eid:
                return ControllerStepResult(
                    tool_result=None,
                    planning=None,
                    spawned_experiment_id=next_eid,
                    terminal=False,
                    branch_terminal=True,
                    terminal_reason=reason,
                )
        return ControllerStepResult(
            tool_result=None,
            planning=None,
            terminal=True,
            branch_terminal=True,
            terminal_reason=reason,
        )

    if decision.decision_type == PlanDecisionType.SWITCH_OPPORTUNITY:
        selected = decision.selected
        if selected is None or selected.draft_spec is None:
            raise ResearchGraphError("SWITCH_OPPORTUNITY decision missing draft ExperimentSpec")

        frontier_id = decision.selected_frontier_id
        frontier = graph.get_frontier()
        item = frontier.items.get(frontier_id) if frontier_id else None

        root = branch_root_id(graph, experiment_node_id)
        branch = graph.get_portfolio_state().get_branch(root)
        leave_reason = "GLOBAL_ALLOCATION_SWITCH"
        if decision.global_allocation_source == "REVISIT":
            leave_reason = "GLOBAL_REVISIT"
        update_branch_on_leave(
            graph,
            branch_root_id=root,
            unresolved_value=branch.unresolved_research_value,
            reason=leave_reason,
        )

        if item is not None:
            valid, invalid_reason = validate_action_against_panel(selected, panel_columns or ())
            if not valid:
                graph.get_frontier().mark_invalid(frontier_id, invalid_reason)
                graph.persist_frontier()
                next_eid = _select_next_experiment_from_frontier(graph, panel_columns or ())
                if next_eid:
                    return ControllerStepResult(
                        tool_result=None,
                        planning=None,
                        spawned_experiment_id=next_eid,
                        terminal=False,
                        branch_terminal=True,
                        terminal_reason=invalid_reason,
                    )
            frontier.mark_selected(frontier_id)
            if decision.global_allocation_source == "REVISIT":
                record_branch_revisit(graph, item.branch_root_id)

        pending_ctx: Optional[ResearchQuestionContext] = None
        scope = selected.draft_spec.research_scope
        if scope.get("pending_question_context"):
            pending_ctx = ResearchQuestionContext.from_dict(scope["pending_question_context"])

        evidence_summary = {
            "uncertainty_addressed": selected.uncertainty_addressed,
            "intent": selected.intent,
            "planner_rationale": list(decision.rationale_codes),
            "from_global_allocation": True,
            "global_allocation_source": decision.global_allocation_source,
            "frontier_id": frontier_id,
        }

        spawn_parent = item.parent_experiment_node_id if item else experiment_node_id
        if spawn_parent not in graph.nodes:
            graph.get_frontier().mark_invalid(frontier_id, "missing_parent_node")
            graph.persist_frontier()
            return ControllerStepResult(
                tool_result=None,
                planning=None,
                terminal=True,
                branch_terminal=True,
                terminal_reason="missing_parent_node",
            )

        parent_frame_id = _resolve_parent_frame_id(graph, spawn_parent)
        _register_frame_transition_on_spawn(
            graph,
            pending_ctx=pending_ctx,
            parent_frame_id=parent_frame_id,
            experiment_node_id=spawn_parent,
            planner_action_code=selected.action_code,
            planner_score=planner_score,
        )
        qid = graph.spawn_child_question_from_experiment(
            spawn_parent,
            question_text=selected.question_text,
            reason_code=selected.action_code,
            evidence_summary=evidence_summary,
            question_context=pending_ctx,
        )
        eid = graph.add_experiment(question_node_id=qid, spec=selected.draft_spec)
        graph.persist_frontier()
        return ControllerStepResult(
            tool_result=None,
            planning=None,
            spawned_question_id=qid,
            spawned_experiment_id=eid,
            terminal=False,
            branch_terminal=True,
            terminal_reason=leave_reason,
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

    parent_frame_id = _resolve_parent_frame_id(graph, experiment_node_id)
    _register_frame_transition_on_spawn(
        graph,
        pending_ctx=pending_ctx,
        parent_frame_id=parent_frame_id,
        experiment_node_id=experiment_node_id,
        planner_action_code=selected.action_code,
        planner_score=planner_score,
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


def _maybe_mark_frontier_executed(graph: ResearchGraph, experiment_node_id: str) -> None:
    """Mark frontier item EXECUTED when its spawned experiment runs."""
    node = graph.get_node(experiment_node_id)
    for pid in node.parent_node_ids:
        parent = graph.get_node(pid)
        if parent.node_type.value != "QUESTION":
            continue
        summary: Dict[str, Any] = {}
        if parent.rationale is not None:
            summary = parent.rationale.evidence_summary or {}
        frontier_id = summary.get("frontier_id")
        if frontier_id:
            graph.get_frontier().mark_executed(str(frontier_id))
            graph.persist_frontier()
            return


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
    panel_columns = tuple(panel.columns)
    if not graph.session.panel_preflight:
        graph.session.panel_preflight = build_panel_preflight(panel).to_dict()
    ensure_session_capability_registry(graph, panel, registry)
    ensure_session_expansion_audit(graph)
    ensure_session_provenance_proof(graph)
    ensure_session_exposure_contract(graph)

    tool_result = execute_research_experiment(
        graph, experiment_node_id, registry, panel
    )
    record_experiment_executed(graph.get_search_accounting(), graph, experiment_node_id)
    graph.persist_search_accounting()
    _maybe_mark_frontier_executed(graph, experiment_node_id)
    node = graph.get_node(experiment_node_id)
    record_experiment_capability_exercise(graph, experiment_node_id, node.experiment_spec)
    exposure = graph.get_exposure_contract()
    record_experiment_exposure_exercises(
        exposure, node.experiment_spec, experiment_node_id
    )
    graph.persist_exposure_contract()

    if _is_budget_exhausted(graph):
        planning = _terminate_session_on_budget_exhaustion(
            graph,
            experiment_node_id,
            tool_result,
            research_scope=research_scope,
        )
        _maybe_persist_graph(graph, auto_persist=auto_persist, persist_dir=persist_dir)
        return ControllerStepResult(
            tool_result=tool_result,
            planning=planning,
            terminal=True,
            session_terminal=True,
            terminal_reason="BUDGET_EXHAUSTED",
        )

    try:
        planning = plan_after_experiment(
            graph,
            experiment_node_id,
            tool_result,
            registry,
            research_scope=research_scope,
            panel_columns=panel_columns,
        )
        planner_score: Optional[float] = None
        if planning.decision.selected is not None:
            sel_entry = planning.candidate_scores.get(planning.decision.selected.action_id, {})
            if isinstance(sel_entry, dict):
                planner_score = sel_entry.get("total")
        step = apply_plan_decision(
            graph,
            experiment_node_id,
            planning.decision,
            panel_columns=panel_columns,
            planner_score=planner_score,
        )
        step.tool_result = tool_result
        step.planning = planning
    except Exception as exc:
        _record_session_failure(
            graph,
            experiment_node_id=experiment_node_id,
            operation="plan_after_experiment",
            error=exc,
            tool_result=tool_result,
        )
        _maybe_persist_graph(graph, auto_persist=auto_persist, persist_dir=persist_dir)
        return ControllerStepResult(
            tool_result=tool_result,
            planning=None,
            terminal=True,
            session_terminal=True,
            terminal_reason=f"ERROR:{type(exc).__name__}",
        )
    _maybe_persist_graph(graph, auto_persist=auto_persist, persist_dir=persist_dir)
    return step


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
    Frontier-driven research loop starting from a pending experiment node.

    Executes up to max_steps experiments. STOP_BRANCH returns to frontier;
    STOP_SESSION ends only after global stopping evaluation.
    """
    panel_columns = tuple(panel.columns)
    if not graph.session.panel_preflight:
        graph.session.panel_preflight = build_panel_preflight(panel).to_dict()
    ensure_session_capability_registry(graph, panel, registry)
    ensure_session_expansion_audit(graph)
    ensure_session_provenance_proof(graph)
    ensure_session_exposure_contract(graph)

    steps: List[ControllerStepResult] = []
    current_exp: Optional[str] = initial_experiment_id

    for _ in range(max_steps):
        if current_exp is None:
            current_exp = _select_next_experiment_from_frontier(graph, panel_columns)
            if current_exp is None:
                should_stop, _ = evaluate_and_maybe_stop_session(graph)
                if should_stop:
                    break
                break

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

        if step.session_terminal or (
            step.terminal and graph.session.status != SessionStatus.ACTIVE
        ):
            break

        if step.branch_terminal and step.spawned_experiment_id:
            current_exp = step.spawned_experiment_id
            continue

        if step.terminal:
            break

        if step.spawned_experiment_id is None:
            current_exp = _select_next_experiment_from_frontier(graph, panel_columns)
            continue

        current_exp = step.spawned_experiment_id

    if graph.session.status == SessionStatus.ACTIVE:
        evaluate_and_maybe_stop_session(graph)

    portfolio = graph.get_portfolio_state()
    portfolio.metrics = compute_session_portfolio_metrics(graph).to_dict()
    graph.persist_portfolio_state()

    if auto_persist and persist_dir is not None:
        write_research_graph(graph, data_dir=persist_dir)

    return steps
