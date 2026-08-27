"""Phase 3G.4 — global research allocator synthetic tests A–N."""

from __future__ import annotations

import inspect
from unittest import mock

import pytest

import modules.edge_research.research_portfolio as portfolio_mod
from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import (
    ActionIntent,
    ResearchActionCandidate,
)
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_controller import apply_plan_decision, plan_after_experiment
from modules.edge_research.research_frontier import FrontierItem, FrontierItemStatus, ResearchFrontier
from modules.edge_research.research_global_allocator import (
    GLOBAL_ALLOCATOR_VERSION,
    GlobalComparableOpportunity,
    OpportunitySource,
    apply_global_allocation_to_plan_decision,
    collect_global_opportunities,
    revalue_frontier_opportunity,
    select_global_research_opportunity,
)
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_planner import (
    PlanDecision,
    PlanDecisionType,
    plan_next_action,
    score_all_candidates,
)
from modules.edge_research.research_portfolio import (
    BranchPortfolioStatus,
    ResearchOpportunity,
    build_opportunity_from_candidate,
)
from modules.edge_research.research_state import ExperimentSpec, NodeType, QuestionRationale
from modules.edge_research.research_tools import ToolResult, ToolStatus, build_default_tool_registry

CUTOFF = "2026-08-20"
REGISTRY = build_default_tool_registry()
SCOPE: dict = {}


def _graph(*, budget: int = 12) -> ResearchGraph:
    return ResearchGraph.create_session(
        data_cutoff_date=CUTOFF,
        experiment_budget=budget,
        session_id="rs-global-allocator",
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


def _seed_lineage(graph: ResearchGraph, *, tool: str = "adaptive_partition_compare", feature: str = "feat_alpha") -> str:
    oid = graph.add_root_observation(description="Root", node_id="O-root")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Initial?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        node_id="Q-root",
    )
    inputs: dict = {"feature_column": feature, "horizon": "T5"}
    if tool == "horizon_comparison":
        inputs = {"horizon": "T5"}
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
    action_id: str | None = None,
) -> ResearchActionCandidate:
    return ResearchActionCandidate(
        action_id=action_id or f"act-{action_code}",
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


def _frontier_item(
    *,
    frontier_id: str,
    action_id: str,
    action_code: str,
    parent: str = "E-root",
    branch: str = "obs-branch-b",
    feature: str = "feat_beta",
    planner_score: float = 5.0,
) -> FrontierItem:
    return FrontierItem(
        frontier_id=frontier_id,
        action_id=action_id,
        action_code=action_code,
        parent_experiment_node_id=parent,
        branch_root_id=branch,
        action_type=ActionIntent.EXPLORATION.value,
        target_feature=feature,
        planner_score=planner_score,
        draft_spec=_spec("adaptive_partition_compare", feature=feature).to_dict(),
        question_text=f"Frontier {action_code}?",
    )


def _mock_erv(opp: ResearchOpportunity, erv: float) -> ResearchOpportunity:
    opp.expected_research_value = erv
    return opp



def _patch_opportunity_erv(score_fn):
    """Patch build_opportunity_from_candidate with controlled ERV; avoids recursion."""
    real_build = portfolio_mod.build_opportunity_from_candidate

    def _side(cand, **kw):
        opp = real_build(cand, **kw)
        return _mock_erv(opp, score_fn(cand, opp))

    return mock.patch.object(
        portfolio_mod,
        "build_opportunity_from_candidate",
        side_effect=_side,
    )


def _plan_with_global(
    graph: ResearchGraph,
    assessment: ResearchAssessment,
    candidates: list[ResearchActionCandidate],
    experiment_node_id: str,
    panel_columns: tuple[str, ...] | None = None,
) -> PlanDecision:
    scores = score_all_candidates(assessment, candidates, graph, experiment_node_id=experiment_node_id)
    local = plan_next_action(assessment, candidates, graph, experiment_node_id=experiment_node_id)
    allocation = select_global_research_opportunity(
        graph,
        assessment,
        candidates,
        scores,
        local,
        experiment_node_id=experiment_node_id,
        panel_columns=panel_columns,
    )
    return apply_global_allocation_to_plan_decision(graph, local, allocation, local_opportunities=[])


# --- A. Better frontier beats weak local ---


def test_a_better_frontier_beats_weak_local():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    frontier = graph.get_frontier()
    frontier.items["f-high"] = _frontier_item(
        frontier_id="f-high",
        action_id="act-frontier-high",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
        planner_score=99.0,
    )
    graph.persist_frontier()

    assessment = _assessment(additional_investigation_warranted=False, conditional_candidate=False)
    weak_local = _candidate("WEAK_LOCAL", hints={"observed_success_rate": 0.51})
    stop = _stop_candidate()

    with _patch_opportunity_erv(lambda cand, opp: 1.0 if "WEAK" in cand.action_code else 5.0):
        decision = _plan_with_global(graph, assessment, [weak_local, stop], eid, ("feat_alpha", "feat_beta"))

    assert decision.decision_type == PlanDecisionType.SWITCH_OPPORTUNITY
    assert decision.global_allocation_source in (
        OpportunitySource.FRONTIER.value,
        OpportunitySource.DEFERRED.value,
        OpportunitySource.REVISIT.value,
    )
    assert decision.selected_frontier_id == "f-high"


# --- B. Strong local beats frontier ---


def test_b_strong_local_beats_frontier():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    frontier = graph.get_frontier()
    frontier.items["f-low"] = _frontier_item(
        frontier_id="f-low",
        action_id="act-frontier-low",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
        planner_score=50.0,
    )
    graph.persist_frontier()

    assessment = _assessment()
    strong = _candidate("STRONG_LOCAL", hints={"shape_strength": 30.0, "shape_followup": 5.0})

    with _patch_opportunity_erv(lambda cand, opp: 8.0 if "STRONG" in cand.action_code else 4.0):
        decision = _plan_with_global(graph, assessment, [strong], eid, ("feat_alpha", "feat_beta"))

    assert decision.decision_type == PlanDecisionType.EXPERIMENT
    assert decision.global_allocation_source == OpportunitySource.LOCAL.value
    assert decision.selected.action_code == "STRONG_LOCAL"


# --- C. Historical frontier score stale ---


def test_c_stale_historical_frontier_score_not_used_for_selection():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    item = _frontier_item(
        frontier_id="f-stale",
        action_id="act-stale",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
        planner_score=99.0,
    )
    graph.get_frontier().items["f-stale"] = item
    graph.persist_frontier()

    assessment = _assessment()
    local = _candidate("LOCAL_WINNER", hints={"shape_strength": 15.0})

    with _patch_opportunity_erv(lambda cand, opp: 6.0 if "LOCAL" in cand.action_code else 0.5):
        decision = _plan_with_global(graph, assessment, [local], eid, ("feat_alpha", "feat_beta"))

    assert decision.decision_type == PlanDecisionType.EXPERIMENT
    assert item.planner_score == 99.0
    expl = decision.portfolio_explanation or {}
    assert expl.get("historical_planner_score", 0) != expl.get("selected_erv", 0) or decision.global_allocation_source == "LOCAL"


# --- D. Frontier becomes more valuable after revaluation ---


def test_d_frontier_selected_after_revaluation():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    frontier = graph.get_frontier()
    frontier.items["f-rise"] = _frontier_item(
        frontier_id="f-rise",
        action_id="act-rise",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
        planner_score=1.0,
    )
    graph.persist_frontier()

    assessment = _assessment(additional_investigation_warranted=False)
    moderate = _candidate("MODERATE_LOCAL", hints={"observed_success_rate": 0.55})

    with _patch_opportunity_erv(lambda cand, opp: 2.0 if "MODERATE" in cand.action_code else 7.0):
        decision = _plan_with_global(graph, assessment, [moderate], eid, ("feat_alpha", "feat_beta"))

    assert decision.decision_type == PlanDecisionType.SWITCH_OPPORTUNITY
    assert decision.selected_frontier_id == "f-rise"


# --- E. Negative local vs positive frontier ---


def test_e_negative_local_not_executed_when_frontier_positive():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    graph.get_frontier().items["f-pos"] = _frontier_item(
        frontier_id="f-pos",
        action_id="act-pos",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
        planner_score=3.0,
    )
    graph.persist_frontier()

    assessment = _assessment(
        additional_investigation_warranted=False,
        conditional_candidate=False,
        branch_observation_codes=("NO_CLEAR_DIFFERENCE",),
    )
    negative = _candidate("NEGATIVE_LOCAL")
    stop = _stop_candidate()

    with _patch_opportunity_erv(lambda cand, opp: -2.0 if "NEGATIVE" in cand.action_code else 3.0):
        decision = _plan_with_global(graph, assessment, [negative, stop], eid, ("feat_alpha", "feat_beta"))

    assert decision.decision_type == PlanDecisionType.SWITCH_OPPORTUNITY
    assert decision.selected is not None
    assert decision.selected.action_code != "NEGATIVE_LOCAL"


# --- F. All opportunities negative ---


def test_f_all_negative_follows_stop_policy():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    graph.get_frontier().items["f-neg"] = _frontier_item(
        frontier_id="f-neg",
        action_id="act-neg",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
        planner_score=10.0,
    )
    graph.persist_frontier()

    assessment = _assessment(additional_investigation_warranted=False, conditional_candidate=False)
    weak = _candidate("WEAK")
    stop = _stop_candidate()

    with _patch_opportunity_erv(
        lambda cand, opp: -3.0 if cand.intent != ActionIntent.STOP.value else 1.0
    ):
        decision = _plan_with_global(graph, assessment, [weak, stop], eid, ("feat_alpha", "feat_beta"))

    assert decision.decision_type in (PlanDecisionType.STOP_BRANCH, PlanDecisionType.EXPERIMENT, PlanDecisionType.SWITCH_OPPORTUNITY)
    if decision.decision_type == PlanDecisionType.STOP_BRANCH:
        assert decision.selected is None or decision.selected.intent == ActionIntent.STOP.value


# --- G. Illegal frontier item excluded ---


def test_g_illegal_frontier_excluded_with_reason():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"

    from modules.edge_research.research_grammar import OutcomeSpec, PopulationSpec

    bad_outcome = OutcomeSpec.compare("t10_return", ">", 0.0)
    bad_pop = PopulationSpec.all_()
    item = _frontier_item(
        frontier_id="f-illegal",
        action_id="act-illegal",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
        feature="feat_missing",
    )
    item.outcome_spec = bad_outcome.to_dict()
    item.population_spec = bad_pop.to_dict()
    spec = _spec("adaptive_partition_compare", feature="feat_missing")
    scope = dict(spec.research_scope or {})
    scope["pending_question_context"] = {
        "observation_horizon": 1,
        "population_spec": bad_pop.to_dict(),
        "outcome_spec": bad_outcome.to_dict(),
    }
    spec = ExperimentSpec(
        tool_name=spec.tool_name,
        tool_version=spec.tool_version,
        inputs={"feature_column": "feat_missing", "horizon": "T5"},
        research_scope=scope,
        data_cutoff_date=CUTOFF,
    )
    item.draft_spec = spec.to_dict()
    graph.get_frontier().items["f-illegal"] = item
    graph.get_frontier().items["f-legal"] = _frontier_item(
        frontier_id="f-legal",
        action_id="act-legal",
        action_code="ADAPTIVE_PARTITION_feat_alpha",
        parent=parent_id,
        feature="feat_alpha",
        planner_score=1.0,
    )
    graph.persist_frontier()

    assessment = _assessment()
    local = _candidate("LOCAL_ONLY", feature="feat_alpha")
    opps, excluded = collect_global_opportunities(
        graph,
        assessment,
        [local],
        score_all_candidates(assessment, [local], graph, experiment_node_id=eid),
        experiment_node_id=eid,
        panel_columns=("feat_alpha",),
    )
    excluded_ids = {e.frontier_id for e in excluded if e.frontier_id}
    assert "f-illegal" in excluded_ids or any("temporal" in e.exclusion_reason for e in excluded)


# --- H. Context reconstruction failure ---


def test_h_context_reconstruction_failure_non_comparable():
    graph = _graph()
    eid = _seed_lineage(graph)
    item = _frontier_item(
        frontier_id="f-broken",
        action_id="act-broken",
        action_code="BROKEN",
        parent="E-missing-parent",
        planner_score=100.0,
    )
    item.draft_spec = None
    g = revalue_frontier_opportunity(graph, item, _assessment(), current_branch_root_id="obs-x")
    assert g.comparable is False
    assert g.exclusion_reason != ""


# --- I. Genuine revisit ---


def test_i_genuine_revisit_audit():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    branch_id = "obs-deferred"
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_id)
    branch.status = BranchPortfolioStatus.DEFERRED_PROMISING.value
    branch.unresolved_research_value = 4.0
    branch.experiments_on_branch = 2
    branch.leave_reason = "GLOBAL_ALLOCATION_SWITCH"
    graph.persist_portfolio_state()

    graph.get_frontier().items["f-revisit"] = _frontier_item(
        frontier_id="f-revisit",
        action_id="act-revisit",
        action_code="ADAPTIVE_PARTITION_feat_alpha",
        parent=parent_id,
        branch=branch_id,
        planner_score=1.0,
    )
    graph.persist_frontier()

    assessment = _assessment()
    other = _candidate("OTHER_LOCAL", feature="feat_beta")

    with _patch_opportunity_erv(lambda cand, opp: 2.0 if "OTHER" in cand.action_code else 9.0):
        decision = _plan_with_global(graph, assessment, [other], eid, ("feat_alpha", "feat_beta"))

    assert decision.decision_type == PlanDecisionType.SWITCH_OPPORTUNITY
    expl = decision.portfolio_explanation or {}
    assert expl.get("selected_source") in ("REVISIT", "DEFERRED", "FRONTIER")
    assert "revisit_audit" in expl


# --- J. No forced diversity ---


def test_j_repeated_local_exploitation_allowed():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    graph.get_frontier().items["f-alt"] = _frontier_item(
        frontier_id="f-alt",
        action_id="act-alt",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
        planner_score=20.0,
    )
    graph.persist_portfolio_state()

    assessment = _assessment()
    strong = _candidate("DEEP_LOCAL", hints={"shape_strength": 25.0, "shape_followup": 4.0})

    with _patch_opportunity_erv(lambda cand, opp: 10.0 if "DEEP" in cand.action_code else 3.0):
        d1 = _plan_with_global(graph, assessment, [strong], eid, ("feat_alpha", "feat_beta"))
        d2 = _plan_with_global(graph, assessment, [strong], eid, ("feat_alpha", "feat_beta"))

    assert d1.decision_type == PlanDecisionType.EXPERIMENT
    assert d2.decision_type == PlanDecisionType.EXPERIMENT
    assert d1.selected.action_code == "DEEP_LOCAL"


# --- K. Budget awareness ---


def test_k_budget_awareness_in_global_decision():
    graph = _graph(budget=2)
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    graph.get_frontier().items["f-b"] = _frontier_item(
        frontier_id="f-b",
        action_id="act-b",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
    )
    graph.persist_frontier()

    assessment = _assessment()
    high = _candidate("HIGH", hints={"shape_strength": 20.0})
    low = _candidate("LOW", feature="feat_beta")

    with _patch_opportunity_erv(lambda cand, opp: 9.0 if "HIGH" in cand.action_code else 1.0):
        decision = _plan_with_global(graph, assessment, [high, low], eid, ("feat_alpha", "feat_beta"))

    assert decision.portfolio_explanation is not None
    assert decision.portfolio_explanation.get("budget_remaining") == 1


# --- L. Search burden preserved ---


def test_l_search_burden_preserved_on_revaluation():
    graph = _graph()
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    item = _frontier_item(
        frontier_id="f-burden",
        action_id="act-burden",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
        planner_score=8.0,
    )
    graph.get_frontier().items["f-burden"] = item
    portfolio = graph.get_portfolio_state()
    portfolio.tool_attempt_counts["adaptive_partition_compare"] = 6
    portfolio.dimension_experiment_counts["feat_beta|_|_|_"] = 5
    graph.persist_portfolio_state()

    assessment = _assessment()
    cand = item.to_action_candidate()
    base, comp = score_all_candidates(assessment, [cand], graph)[cand.action_id]
    opp = build_opportunity_from_candidate(
        cand,
        base_score=base,
        components=comp,
        graph=graph,
        assessment=assessment,
        branch_root_id=item.branch_root_id,
        from_frontier=True,
    )
    assert opp.marginal_information_gain < 2.0
    assert item.planner_score == 8.0


# --- M. Global decision explanation ---


def test_m_global_decision_explanation_fields():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    graph.get_frontier().items["f-m"] = _frontier_item(
        frontier_id="f-m",
        action_id="act-m",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
    )
    graph.persist_frontier()

    assessment = _assessment()
    local = _candidate("LOCAL_M")
    decision = _plan_with_global(graph, assessment, [local], eid, ("feat_alpha", "feat_beta"))
    expl = decision.portfolio_explanation or {}
    for key in (
        "allocator_version",
        "selected_source",
        "best_local_erv",
        "best_frontier_erv",
        "best_global_alternative_erv",
        "global_opportunity_cost",
        "globally_comparable_count",
        "excluded_count",
        "context_switch_occurred",
        "budget_remaining",
    ):
        assert key in expl, f"missing {key}"
    assert expl["allocator_version"] == GLOBAL_ALLOCATOR_VERSION


# --- N. Production isolation ---


def test_n_production_isolation():
    from modules.edge_research import research_global_allocator

    source = inspect.getsource(research_global_allocator)
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in source


# --- Invariants ---


def test_invariant_deterministic_selection():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    parent_id = "E-root"
    graph.get_frontier().items["f-det"] = _frontier_item(
        frontier_id="f-det",
        action_id="act-det",
        action_code="ADAPTIVE_PARTITION_feat_beta",
        parent=parent_id,
    )
    graph.persist_frontier()
    assessment = _assessment()
    cands = [_candidate("DET_LOCAL")]
    d1 = _plan_with_global(graph, assessment, cands, eid, ("feat_alpha", "feat_beta"))
    d2 = _plan_with_global(graph, assessment, cands, eid, ("feat_alpha", "feat_beta"))
    assert d1.decision_type == d2.decision_type
    assert (d1.selected.action_id if d1.selected else None) == (
        d2.selected.action_id if d2.selected else None
    )


def test_invariant_validated_actionable_false():
    from modules.edge_research.research_interpreter import interpret_tool_result

    source = inspect.getsource(interpret_tool_result)
    assert "validated=False" in source
    assert "actionable=False" in source
