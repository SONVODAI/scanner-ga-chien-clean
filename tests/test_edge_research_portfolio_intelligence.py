"""Phase 3G.3 — research portfolio intelligence synthetic adversarial tests A–O."""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import (
    ActionIntent,
    ResearchActionCandidate,
    generate_action_candidates,
)
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_controller import (
    apply_plan_decision,
    plan_after_experiment,
)
from modules.edge_research.research_frontier import FrontierItem, FrontierItemStatus, ResearchFrontier
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_planner import (
    PlanDecision,
    PlanDecisionType,
    plan_next_action,
    score_candidate,
)
from modules.edge_research.research_portfolio import (
    BranchPortfolioStatus,
    OpportunityStatus,
    PortfolioSessionState,
    build_decision_explanation,
    build_opportunity_from_candidate,
    compute_exploration_debt,
    compute_exploitation_value,
    estimate_marginal_information_gain,
    mark_dominated_opportunities,
    portfolio_score_adjustments,
    score_opportunities_for_selection,
    select_best_frontier_opportunity,
    update_branch_on_experiment,
    update_branch_on_leave,
)
from modules.edge_research.research_state import (
    ExperimentSpec,
    NodeType,
    QuestionRationale,
)
from modules.edge_research.research_tools import ToolResult, ToolStatus, build_default_tool_registry

CUTOFF = "2026-08-20"
REGISTRY = build_default_tool_registry()
SCOPE: dict = {}


def _graph(*, budget: int = 12) -> ResearchGraph:
    return ResearchGraph.create_session(
        data_cutoff_date=CUTOFF,
        experiment_budget=budget,
        session_id="rs-portfolio-intelligence",
    )


def _spec(tool: str, inputs: dict | None = None, feature: str = "feat_alpha") -> ExperimentSpec:
    ins = inputs or {"horizon": "T5", "feature_column": feature}
    return ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs=ins,
        research_scope=SCOPE,
        data_cutoff_date=CUTOFF,
    )


def _seed_lineage(graph: ResearchGraph, *, tool: str = "horizon_comparison", feature: str = "feat_alpha") -> str:
    oid = graph.add_root_observation(description="Root", node_id="O-root")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Initial?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        node_id="Q-root",
    )
    inputs: dict = {"horizon": "T5"}
    if tool == "adaptive_partition_compare":
        inputs = {"feature_column": feature, "max_bins": 4}
    elif tool != "horizon_comparison":
        inputs = {"horizon": "T5", "feature_column": feature}
    return graph.add_experiment(
        question_node_id=qid,
        spec=_spec(tool, inputs, feature=feature),
        node_id="E-root",
    )


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(
        source_experiment_node_id="E1",
        tool_name="adaptive_partition_compare",
        tool_status="OK",
        additional_investigation_warranted=True,
        conditional_candidate=True,
        branch_observation_codes=("SHAPE_STEP_CHANGE",),
    )
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


def _candidate(
    action_code: str,
    *,
    intent: str = ActionIntent.EXPLORATION.value,
    feature: str = "feat_alpha",
    tool: str = "adaptive_partition_compare",
    hints: dict | None = None,
) -> ResearchActionCandidate:
    return ResearchActionCandidate(
        action_id=f"act-{action_code}",
        action_code=action_code,
        intent=intent,
        question_template_id=action_code,
        question_text=f"Question for {action_code}?",
        tool_name=tool,
        tool_version="v1",
        draft_spec=_spec(tool, {"feature_column": feature, "horizon": "T5"}, feature=feature),
        uncertainty_addressed="GAP_EXPLORATION",
        expected_information="HIGH",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
        rationale_codes=(action_code,),
        priority_hints=dict(hints or {}),
    )


def _stop_candidate() -> ResearchActionCandidate:
    return ResearchActionCandidate(
        action_id="act-STOP_BRANCH",
        action_code="STOP_BRANCH",
        intent=ActionIntent.STOP.value,
        question_template_id="STOP_NO_FURTHER_VALUE",
        question_text="Stop branch",
        tool_name="",
        tool_version="",
        draft_spec=None,
        uncertainty_addressed="STOP",
        expected_information="LOW",
        budget_cost=0,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
        rationale_codes=("STOP",),
        priority_hints={"stop_urgency": 1.0},
    )


def _panel_preflight(graph: ResearchGraph, features: list[str]) -> None:
    graph.session.panel_preflight = {
        "eligible_explanatory": features,
        "partition_columns_available": features,
    }


# --- A. Promising branch deserves depth ---


def test_a_promising_branch_deserves_depth():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    assessment = _assessment()
    deep = _candidate("ADAPTIVE_PARTITION_feat_alpha", hints={"shape_strength": 20.0, "shape_followup": 3.0})
    weak = _candidate("ADAPTIVE_PARTITION_feat_beta", feature="feat_beta", hints={"slicing_explore": 1.0})
    stop = _stop_candidate()
    decision = plan_next_action(assessment, [deep, weak, stop], graph, experiment_node_id=eid)
    assert decision.decision_type == PlanDecisionType.EXPERIMENT
    assert decision.selected is not None
    assert decision.selected.action_code == "ADAPTIVE_PARTITION_feat_alpha"


# --- B. Moderate branch should not monopolize ---


def test_b_moderate_branch_should_not_monopolize():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta", "feat_gamma"])
    eid = _seed_lineage(graph)
    portfolio = graph.get_portfolio_state()
    portfolio.dimension_experiment_counts["feat_alpha|_|_|"] = 4
    portfolio.tool_attempt_counts["adaptive_partition_compare"] = 4
    graph.persist_portfolio_state()

    assessment = _assessment(
        conditional_candidate=False,
        additional_investigation_warranted=False,
        branch_observation_codes=("NO_CLEAR_DIFFERENCE",),
    )
    moderate = _candidate("ADAPTIVE_PARTITION_feat_alpha", hints={"observed_success_rate": 0.52})
    fresh = _candidate("ADAPTIVE_PARTITION_feat_gamma", feature="feat_gamma", hints={"slicing_explore": 2.0})
    stop = _stop_candidate()
    decision = plan_next_action(assessment, [moderate, fresh, stop], graph, experiment_node_id=eid)
    assert decision.selected is not None
    assert decision.selected.action_code == "ADAPTIVE_PARTITION_feat_gamma"


# --- C. Redundant confirmation ---


def test_c_redundant_confirmation_diminishes_value():
    graph = _graph()
    eid = _seed_lineage(graph)
    assessment = _assessment(branch_tools_attempted=("adaptive_partition_compare",))
    repeat = _candidate("ADAPTIVE_PARTITION_feat_alpha", feature="feat_alpha")
    mig_before = estimate_marginal_information_gain(graph, repeat, assessment, experiment_node_id=eid)
    portfolio = graph.get_portfolio_state()
    portfolio.tool_attempt_counts["adaptive_partition_compare"] = 5
    graph.persist_portfolio_state()
    mig_after = estimate_marginal_information_gain(graph, repeat, assessment, experiment_node_id=eid)
    assert mig_after < mig_before


# --- D. Falsification still matters ---


def test_d_falsification_can_beat_exploitation():
    graph = _graph()
    eid = _seed_lineage(graph)
    assessment = _assessment(
        possible_falsification_targets=("EXTREME_WINNER",),
        fragility_evidence=("EXTREME_WINNER",),
    )
    falsify = _candidate(
        "FALSIFY_EXTREME",
        intent=ActionIntent.FALSIFICATION.value,
        tool="sensitivity_analysis",
        hints={"falsification_threat": 4.0},
    )
    explore = _candidate("ADAPTIVE_PARTITION_feat_alpha", hints={"shape_strength": 5.0})
    decision = plan_next_action(assessment, [falsify, explore], graph, experiment_node_id=eid)
    assert decision.selected.action_code == "FALSIFY_EXTREME"


# --- E. Return to promising branch ---


def test_e_return_to_promising_branch():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    assessment = _assessment()
    frontier = graph.get_frontier()
    branch_a = "obs-branch-a"
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_a)
    branch.status = BranchPortfolioStatus.DEFERRED_PROMISING.value
    branch.unresolved_research_value = 3.0
    branch.experiments_on_branch = 2
    graph.persist_portfolio_state()

    item_a = FrontierItem(
        frontier_id="frontier-a",
        action_id="act-a",
        action_code="ADAPTIVE_PARTITION_feat_alpha",
        parent_experiment_node_id="E-parent-a",
        branch_root_id=branch_a,
        action_type=ActionIntent.EXPLORATION.value,
        target_feature="feat_alpha",
        planner_score=1.0,
        draft_spec=_spec("adaptive_partition_compare").to_dict(),
        question_text="Return to A?",
    )
    item_b = FrontierItem(
        frontier_id="frontier-b",
        action_id="act-b",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent_experiment_node_id="E-parent-b",
        branch_root_id="obs-branch-b",
        action_type=ActionIntent.EXPLORATION.value,
        target_feature="feat_beta",
        planner_score=2.0,
        draft_spec=_spec("adaptive_partition_compare", feature="feat_beta").to_dict(),
        question_text="Explore B?",
    )
    frontier.items["frontier-a"] = item_a
    frontier.items["frontier-b"] = item_b
    graph.persist_frontier()

    selected = select_best_frontier_opportunity(graph, frontier, assessment)
    assert selected is not None
    assert selected.branch_root_id == branch_a


# --- F. Do not return to dead branch ---


def test_f_do_not_return_to_falsified_branch():
    graph = _graph()
    assessment = _assessment()
    frontier = graph.get_frontier()
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch("obs-dead")
    branch.falsified = True
    branch.status = BranchPortfolioStatus.FALSIFIED.value
    branch.unresolved_research_value = 5.0
    graph.persist_portfolio_state()

    item_dead = FrontierItem(
        frontier_id="frontier-dead",
        action_id="act-dead",
        action_code="ADAPTIVE_PARTITION_feat_alpha",
        parent_experiment_node_id="E-dead",
        branch_root_id="obs-dead",
        action_type=ActionIntent.EXPLORATION.value,
        planner_score=10.0,
        draft_spec=_spec("adaptive_partition_compare").to_dict(),
        question_text="Dead branch?",
    )
    item_live = FrontierItem(
        frontier_id="frontier-live",
        action_id="act-live",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent_experiment_node_id="E-live",
        branch_root_id="obs-live",
        action_type=ActionIntent.EXPLORATION.value,
        planner_score=0.5,
        draft_spec=_spec("adaptive_partition_compare", feature="feat_beta").to_dict(),
        question_text="Live branch?",
    )
    frontier.items["frontier-dead"] = item_dead
    frontier.items["frontier-live"] = item_live
    graph.persist_frontier()

    selected = select_best_frontier_opportunity(graph, frontier, assessment)
    assert selected.branch_root_id == "obs-live"


# --- G. High exploration debt ---


def test_g_high_exploration_debt_prioritizes_unexplored():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta", "feat_gamma"])
    eid = _seed_lineage(graph)
    state = graph.get_search_accounting()
    state.session_ledger.explanatory_features_tested = {"feat_alpha"}
    graph.persist_search_accounting()

    assessment = _assessment(conditional_candidate=False, additional_investigation_warranted=False)
    same = _candidate("ADAPTIVE_PARTITION_feat_alpha")
    new = _candidate("ADAPTIVE_PARTITION_feat_gamma", feature="feat_gamma")
    debt_new = compute_exploration_debt(graph, target_feature="feat_gamma")
    debt_same = compute_exploration_debt(graph, target_feature="feat_alpha")
    assert debt_new > debt_same
    decision = plan_next_action(assessment, [same, new], graph, experiment_node_id=eid)
    assert decision.selected.action_code == "ADAPTIVE_PARTITION_feat_gamma"


# --- H. Strong branch overrides exploration debt ---


def test_h_strong_branch_overrides_exploration_debt():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    state = graph.get_search_accounting()
    state.session_ledger.explanatory_features_tested = {"feat_alpha"}
    graph.persist_search_accounting()

    assessment = _assessment(conditional_candidate=True, additional_investigation_warranted=True)
    strong = _candidate(
        "ADAPTIVE_PARTITION_feat_alpha",
        hints={"shape_strength": 25.0, "shape_followup": 4.0, "threshold_explore": 3.0},
    )
    weak_new = _candidate("ADAPTIVE_PARTITION_feat_beta", feature="feat_beta", hints={"slicing_explore": 0.5})
    exploit_strong = compute_exploitation_value(assessment, strong)
    exploit_weak = compute_exploitation_value(assessment, weak_new)
    assert exploit_strong > exploit_weak
    decision = plan_next_action(assessment, [strong, weak_new], graph, experiment_node_id=eid)
    assert decision.selected.action_code == "ADAPTIVE_PARTITION_feat_alpha"


# --- I. Opportunity cost audit ---


def test_i_opportunity_cost_stored_in_decision():
    graph = _graph()
    eid = _seed_lineage(graph)
    assessment = _assessment()
    c1 = _candidate("ADAPTIVE_PARTITION_feat_alpha", hints={"shape_strength": 10.0})
    c2 = _candidate("ADAPTIVE_PARTITION_feat_beta", feature="feat_beta")
    decision = plan_next_action(assessment, [c1, c2], graph, experiment_node_id=eid)
    assert decision.portfolio_explanation is not None
    assert "best_alternative_id" in decision.portfolio_explanation
    assert "opportunity_cost" in decision.portfolio_explanation
    assert decision.portfolio_explanation["why_selected_over_alternative"]


# --- J. Limited budget ---


def test_j_limited_budget_selects_highest_value():
    graph = _graph(budget=2)
    eid = _seed_lineage(graph)  # 1 experiment used, 1 remaining
    assessment = _assessment()
    high = _candidate("ADAPTIVE_PARTITION_feat_alpha", hints={"shape_strength": 30.0, "shape_followup": 5.0})
    low = _candidate("ADAPTIVE_PARTITION_feat_beta", feature="feat_beta")
    stop = _stop_candidate()
    decision = plan_next_action(assessment, [low, high, stop], graph, experiment_node_id=eid)
    assert decision.decision_type == PlanDecisionType.EXPERIMENT
    assert decision.selected.action_code == "ADAPTIVE_PARTITION_feat_alpha"
    assert decision.portfolio_explanation is not None
    assert decision.portfolio_explanation["budget_remaining"] == 1


# --- K. Dominated opportunity ---


def test_k_dominated_opportunity_marked():
    graph = _graph()
    assessment = _assessment()
    simple = build_opportunity_from_candidate(
        _candidate("SIMPLE"),
        base_score=5.0,
        components={},
        graph=graph,
        assessment=assessment,
    )
    complex_dup = build_opportunity_from_candidate(
        _candidate("COMPLEX", hints={"draft_complexity": 5.0}),
        base_score=4.0,
        components={"draft_complexity_penalty": -2.0, "redundancy_penalty": -1.0},
        graph=graph,
        assessment=assessment,
    )
    complex_dup.complexity_burden = 5.0
    complex_dup.redundancy = 2.0
    complex_dup.marginal_information_gain = simple.marginal_information_gain - 0.5
    marked = mark_dominated_opportunities([simple, complex_dup])
    dominated = [o for o in marked if o.status == OpportunityStatus.DOMINATED.value]
    assert len(dominated) >= 1


# --- L. Novel but useless ---


def test_l_novelty_alone_does_not_win():
    graph = _graph()
    eid = _seed_lineage(graph)
    assessment = _assessment(
        conditional_candidate=False,
        additional_investigation_warranted=False,
        branch_observation_codes=("NO_CLEAR_DIFFERENCE",),
    )
    novel = _candidate("ADAPTIVE_PARTITION_feat_gamma", feature="feat_gamma")
    useful = _candidate("FALSIFY_EXTREME", intent=ActionIntent.FALSIFICATION.value, tool="sensitivity_analysis",
                        hints={"falsification_threat": 4.0})
    assessment = assessment.__class__(
        **{**assessment.__dict__, "possible_falsification_targets": ("EXTREME_WINNER",)}
    )
    decision = plan_next_action(assessment, [novel, useful], graph, experiment_node_id=eid)
    assert decision.selected.action_code == "FALSIFY_EXTREME"


# --- M. Deep but useless ---


def test_m_sunk_cost_avoids_flat_deep_branch():
    graph = _graph()
    eid = _seed_lineage(graph)
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch("O-root")
    branch.experiments_on_branch = 6
    branch.last_marginal_gain = 0.05
    graph.persist_portfolio_state()
    assessment = _assessment(
        additional_investigation_warranted=False,
        branch_observation_codes=("SHAPE_FLAT",),
    )
    deeper = _candidate("ADAPTIVE_PARTITION_feat_alpha")
    stop = _stop_candidate()
    decision = plan_next_action(assessment, [deeper, stop], graph, experiment_node_id=eid)
    assert decision.decision_type in (PlanDecisionType.STOP_BRANCH, PlanDecisionType.EXPERIMENT)
    if decision.decision_type == PlanDecisionType.STOP_BRANCH:
        assert decision.selected.action_code == "STOP_BRANCH"


# --- N. Small-sample temptation ---


def test_n_sample_burden_penalizes_high_sample_loss():
    graph = _graph()
    assessment = _assessment()
    heavy = _candidate("REFINE_POP", hints={"sample_loss_penalty": -3.0})
    light = _candidate("ADAPTIVE_PARTITION_feat_alpha")
    _, _, opp_heavy = portfolio_score_adjustments(
        heavy, assessment, graph, base_score=3.0, components={"sample_loss_penalty": -3.0}
    )
    _, _, opp_light = portfolio_score_adjustments(
        light, assessment, graph, base_score=3.0, components={}
    )
    assert opp_heavy.sample_loss_burden >= opp_light.sample_loss_burden


# --- O. Multiple productive branches ---


def test_o_portfolio_allocates_between_productive_branches():
    graph = _graph()
    assessment = _assessment()
    frontier = graph.get_frontier()
    for i, (root, feat, score) in enumerate(
        [("obs-a", "feat_alpha", 2.0), ("obs-b", "feat_beta", 2.5)]
    ):
        portfolio = graph.get_portfolio_state()
        branch = portfolio.get_branch(root)
        branch.unresolved_research_value = score
        branch.status = BranchPortfolioStatus.DEFERRED_PROMISING.value
        graph.persist_portfolio_state()
        frontier.items[f"f-{i}"] = FrontierItem(
            frontier_id=f"f-{i}",
            action_id=f"act-{i}",
            action_code=f"ADAPTIVE_PARTITION_{feat}",
            parent_experiment_node_id=f"E-{i}",
            branch_root_id=root,
            action_type=ActionIntent.EXPLORATION.value,
            target_feature=feat,
            planner_score=score,
            draft_spec=_spec("adaptive_partition_compare", feature=feat).to_dict(),
            question_text=f"Branch {i}?",
        )
    graph.persist_frontier()
    first = select_best_frontier_opportunity(graph, frontier, assessment)
    assert first is not None
    second_candidates = [i for i in frontier.unexplored_items() if i.frontier_id != first.frontier_id]
    assert len(second_candidates) >= 1


# --- Invariants ---


def test_no_bb04_or_feature_names_in_portfolio_module():
    src = Path("modules/edge_research/research_portfolio.py").read_text()
    forbidden = [
        "rs10", "RS10", "t5_return", "t10_return", "t3_return",
        "frame-00007", "frame-00017", "blind_benchmark_04",
        "HORIZON_HETEROGENEOUS", "win_rate", "58.9",
    ]
    for token in forbidden:
        assert token not in src, f"Forbidden token {token!r} found in research_portfolio.py"


def test_production_isolation_portfolio_module():
    import modules.edge_research.research_portfolio as mod
    source = inspect.getsource(mod)
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in source


def test_portfolio_state_persistence_roundtrip():
    graph = _graph()
    state = graph.get_portfolio_state()
    state.branches["b1"] = state.get_branch("b1")
    state.branches["b1"].unresolved_research_value = 2.5
    graph.persist_portfolio_state()
    g2 = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    g2.session.research_portfolio = graph.session.research_portfolio
    loaded = g2.get_portfolio_state()
    assert loaded.branches["b1"].unresolved_research_value == 2.5
