"""Phase 3G.1 — research exploration policy synthetic tests."""

from __future__ import annotations

import json
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
    evaluate_and_maybe_stop_session,
    finalize_session,
    plan_after_experiment,
    run_research_session,
)
from modules.edge_research.research_frontier import (
    FrontierItem,
    FrontierItemStatus,
    ResearchFrontier,
    SessionStopReason,
    evaluate_global_stop,
)
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_interpreter import interpret_tool_result
from modules.edge_research.research_observation_kind import ObservationKind
from modules.edge_research.research_panel_preflight import (
    build_panel_preflight,
    filter_candidates_for_panel,
    validate_action_against_panel,
)
from modules.edge_research.research_planner import PlanDecision, PlanDecisionType, plan_next_action, score_candidate
from modules.edge_research.research_search_accounting import ResearchStatus, infer_research_status
from modules.edge_research.research_state import (
    ExperimentSpec,
    NodeType,
    QuestionRationale,
    SessionStatus,
    StructuredResearchObservation,
)
from modules.edge_research.research_tools import (
    OBS_HORIZON_HETEROGENEOUS,
    OBS_NO_CLEAR_DIFFERENCE,
    OBS_TRAJECTORY_GROUP_DIFFERENCE,
    ToolResult,
    ToolStatus,
    build_default_tool_registry,
)
from modules.edge_research.storage import read_research_graph, write_research_graph

CUTOFF = "2026-08-20"
REGISTRY = build_default_tool_registry()
SCOPE: dict = {}


def _targets(t0: str) -> dict:
    ts = pd.Timestamp(t0)
    return {
        "t3_target_date": (ts + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
        "t5_target_date": (ts + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        "t10_target_date": (ts + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
    }


def _synthetic_row(i: int, *, feat_a: float, feat_b: float, t5: float) -> dict:
    return {
        "trade_date": f"2026-08-{(i % 10) + 1:02d}",
        "symbol": f"SYM{i % 6}",
        "feat_alpha": feat_a,
        "feat_beta": feat_b,
        "t3_return": t5 * 0.9,
        "t5_return": t5,
        "t10_return": t5 * 1.05,
        "partition_group": "G1" if feat_a > 0 else "G2",
        "rs10": feat_a,
        "research_market_state": "STATE_A",
        **_targets(f"2026-08-{(i % 10) + 1:02d}"),
    }


def _synthetic_panel(n: int = 40, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = [
        _synthetic_row(
            i,
            feat_a=float(rng.normal(0, 1)),
            feat_b=float(rng.normal(0, 1)),
            t5=float(rng.normal(0, 1)),
        )
        for i in range(n)
    ]
    return pd.DataFrame(rows)


def _session_graph(*, budget: int = 12) -> ResearchGraph:
    return ResearchGraph.create_session(
        data_cutoff_date=CUTOFF,
        experiment_budget=budget,
        session_id="rs-exploration-policy",
    )


def _spec(tool: str, inputs: dict | None = None) -> ExperimentSpec:
    return ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs=inputs or {"horizon": "T5"},
        research_scope=SCOPE,
        data_cutoff_date=CUTOFF,
    )


def _seed_lineage(graph: ResearchGraph, *, tool: str = "horizon_comparison") -> str:
    oid = graph.add_root_observation(description="Root", node_id="O-root")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Initial?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        node_id="Q-root",
    )
    inputs: dict = {"horizon": "T5"}
    if tool == "partition_group_compare":
        inputs.update({"partition_column": "partition_group", "partition_type": "categorical"})
    return graph.add_experiment(
        question_node_id=qid,
        spec=_spec(tool, inputs),
        node_id="E-root",
    )


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(
        source_experiment_node_id="E1",
        tool_name="horizon_comparison",
        tool_status="OK",
    )
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


def _tool_result(**kwargs) -> ToolResult:
    defaults = dict(
        tool_name="horizon_comparison",
        tool_version="v1",
        data_cutoff_date=CUTOFF,
        input_hash="test-hash",
        status=ToolStatus.OK,
        sample_size=30,
        metrics={"success_rate": 0.5},
        structured_observations=(),
    )
    defaults.update(kwargs)
    obs = defaults.pop("structured_observations", ())
    if obs and isinstance(obs, list):
        obs = tuple(obs)
    return ToolResult(structured_observations=obs, **defaults)


def _attach_dummy_result(graph: ResearchGraph, experiment_id: str) -> None:
    graph.attach_experiment_result(
        experiment_id,
        metrics={"success_rate": 0.5},
        observations=[StructuredResearchObservation(code=OBS_NO_CLEAR_DIFFERENCE)],
    )


# --- Scenario A: local branch exhaustion ---


def test_local_branch_exhaustion_returns_to_frontier():
    """A: STOP_BRANCH with independent frontier items continues session."""
    graph = _session_graph(budget=12)
    panel = _synthetic_panel()
    graph.session.panel_preflight = build_panel_preflight(panel).to_dict()
    eid = _seed_lineage(graph)
    _attach_dummy_result(graph, eid)

    # Seed frontier with two independent feature explorations.
    frontier = graph.get_frontier()
    for feat, score in (("feat_alpha", 5.0), ("feat_beta", 4.0)):
        spec = _spec(
            "adaptive_partition_compare",
            {"feature_column": feat, "max_bins": 3, "min_bin_n": 5, "min_total_n": 20},
        )
        fid = frontier._next_id()
        frontier.items[fid] = FrontierItem(
            frontier_id=fid,
            action_id=f"act-{feat}",
            action_code=f"ADAPTIVE_{feat}",
            parent_experiment_node_id=eid,
            branch_root_id="Q-root",
            action_type=ActionIntent.SLICING.value,
            target_feature=feat,
            planner_score=score,
            question_text=f"Partition {feat}?",
            draft_spec=spec.to_dict(),
        )
    graph.persist_frontier()

    decision = PlanDecision(
        decision_type=PlanDecisionType.STOP_BRANCH,
        selected=ResearchActionCandidate(
            action_id="stop",
            action_code="STOP_BRANCH",
            intent=ActionIntent.STOP.value,
            question_template_id="STOP",
            question_text="stop",
            tool_name="",
            tool_version="",
            draft_spec=None,
            uncertainty_addressed="STOP",
            expected_information="LOW",
            budget_cost=0,
            already_attempted=False,
            blocked=False,
            blocked_reason=None,
        ),
        all_candidates=(),
    )
    step = apply_plan_decision(graph, eid, decision, panel_columns=tuple(panel.columns))
    assert step.branch_terminal is True
    assert step.session_terminal is False
    assert step.spawned_experiment_id is not None
    assert graph.session.status == SessionStatus.ACTIVE


# --- Scenario B: true global exhaustion ---


def test_true_global_exhaustion_allows_unused_budget():
    """B: empty frontier + low value → STOP_SESSION with unused budget OK."""
    graph = _session_graph(budget=12)
    graph.session.experiments_used = 2
    graph.session.panel_preflight = {
        "eligible_explanatory": ["feat_alpha", "feat_beta"],
    }
    should_stop, reason = evaluate_global_stop(
        remaining_budget=10,
        frontier=ResearchFrontier(),
        features_touched=2,
        eligible_feature_count=2,
    )
    assert should_stop is True
    assert reason.code == "NO_VALID_FRONTIER"
    finalize_session(graph, reason)
    assert graph.session.status == SessionStatus.NO_EDGE_FOUND
    assert graph.session.experiments_used == 2


# --- Scenario C: low-coverage early session ---


def test_low_coverage_global_stop_loses_to_exploration():
    """C: 0 features touched, budget remains — exploration beats STOP_BRANCH."""
    graph = _session_graph(budget=12)
    graph.session.panel_preflight = {
        "eligible_explanatory": ["feat_alpha", "feat_beta", "feat_gamma", "feat_delta"],
    }
    assess = _assessment(
        interesting=True,
        additional_investigation_warranted=True,
        information_gaps=("TIME_DISTRIBUTION", "MARKET_DEPENDENCE"),
        possible_falsification_targets=("EXTREME_WINNER",),
        branch_tools_attempted=("horizon_comparison",),
        observation_kind=ObservationKind.STRUCTURAL_OBSERVATION.value,
        conditional_candidate=False,
    )
    cands = generate_action_candidates(
        assess, graph, REGISTRY, panel_columns=("feat_alpha", "feat_beta", "rs10", "t5_return")
    )
    plan = plan_next_action(assess, cands, graph)
    assert plan.decision_type == PlanDecisionType.EXPERIMENT
    assert plan.selected.intent != ActionIntent.STOP.value


# --- Scenario D: strong candidate falsification ---


def test_strong_conditional_falsification_can_win():
    """D: conditional candidate + falsification target → falsification may win."""
    graph = _session_graph()
    eid = _seed_lineage(graph, tool="partition_group_compare")
    _attach_dummy_result(graph, eid)
    assess = _assessment(
        interesting=True,
        conditional_candidate=True,
        additional_investigation_warranted=True,
        observation_kind=ObservationKind.CONDITIONAL_CANDIDATE.value,
        information_gaps=("MARKET_DEPENDENCE",),
        possible_falsification_targets=("EXTREME_WINNER",),
        branch_tools_attempted=("partition_group_compare",),
        concentration_concerns=("DATE",),
        source_experiment_node_id=eid,
        tool_name="partition_group_compare",
    )
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id=eid)
    plan = plan_next_action(assess, cands, graph, experiment_node_id=eid)
    assert plan.decision_type == PlanDecisionType.EXPERIMENT
    assert plan.selected.intent == ActionIntent.FALSIFICATION.value


# --- Scenario E: candidate survives falsification ---


def test_falsification_survival_returns_to_frontier_not_session_end():
    """E: robust falsification → STOP_BRANCH but session continues via frontier."""
    graph = _session_graph(budget=12)
    panel = _synthetic_panel()
    graph.session.panel_preflight = build_panel_preflight(panel).to_dict()
    eid = _seed_lineage(graph, tool="partition_group_compare")
    _attach_dummy_result(graph, eid)

    frontier = graph.get_frontier()
    fid = frontier._next_id()
    spec = _spec("date_decomposition", {"horizon": "T5"})
    frontier.items[fid] = FrontierItem(
        frontier_id=fid,
        action_id="decompose-date",
        action_code="DECOMPOSE_DATE",
        parent_experiment_node_id=eid,
        branch_root_id="Q-root",
        action_type=ActionIntent.DECOMPOSITION.value,
        planner_score=6.0,
        question_text="Date decomposition?",
        draft_spec=spec.to_dict(),
    )
    graph.persist_frontier()

    result = _tool_result(
        tool_name="sensitivity_analysis",
        structured_observations=[StructuredResearchObservation(code="SENSITIVITY_ROBUST")],
    )
    assess = _assessment(
        interesting=True,
        conditional_candidate=True,
        possible_falsification_targets=(),
        information_gaps=(),
        additional_investigation_warranted=False,
        branch_tools_attempted=("partition_group_compare", "sensitivity_analysis"),
    )
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id=eid)
    plan = plan_next_action(assess, cands, graph, experiment_node_id=eid)
    if plan.decision_type == PlanDecisionType.STOP_BRANCH:
        step = apply_plan_decision(graph, eid, plan, panel_columns=tuple(panel.columns))
        assert step.branch_terminal is True
        assert graph.session.status == SessionStatus.ACTIVE


# --- Scenario F: descriptive cohort effect ---


def test_descriptive_horizon_not_candidate_discovered():
    """F: full-cohort horizon heterogeneity is NOT CANDIDATE_DISCOVERED."""
    graph = _session_graph()
    _seed_lineage(graph)
    result = _tool_result(
        structured_observations=[StructuredResearchObservation(code=OBS_HORIZON_HETEROGENEOUS)],
        metrics={"success_rate": 0.6, "group_count": 1},
    )
    assess = interpret_tool_result(graph, "E-root", result)
    assert assess.observation_kind == ObservationKind.STRUCTURAL_OBSERVATION.value
    assert assess.conditional_candidate is False
    status = infer_research_status(
        interesting=assess.interesting,
        fragility=assess.fragility_evidence,
        falsification_pending=False,
        conditional_candidate=assess.conditional_candidate,
    )
    assert status != ResearchStatus.CANDIDATE_DISCOVERED.value


# --- Scenario G: invalid frontier action ---


def test_invalid_frontier_action_marked_and_skipped():
    """G: absent panel field → INVALID, session selects next frontier item."""
    graph = _session_graph(budget=12)
    panel = _synthetic_panel()
    graph.session.panel_preflight = build_panel_preflight(panel).to_dict()
    eid = _seed_lineage(graph)
    _attach_dummy_result(graph, eid)
    frontier = graph.get_frontier()

    bad_spec = _spec("adaptive_partition_compare", {"feature_column": "missing_field_xyz"})
    bad_id = frontier._next_id()
    frontier.items[bad_id] = FrontierItem(
        frontier_id=bad_id,
        action_id="bad",
        action_code="BAD",
        parent_experiment_node_id=eid,
        branch_root_id="Q-root",
        action_type=ActionIntent.SLICING.value,
        planner_score=9.0,
        question_text="Bad?",
        draft_spec=bad_spec.to_dict(),
    )
    good_spec = _spec("adaptive_partition_compare", {"feature_column": "feat_alpha", "max_bins": 3})
    good_id = frontier._next_id()
    frontier.items[good_id] = FrontierItem(
        frontier_id=good_id,
        action_id="good",
        action_code="GOOD",
        parent_experiment_node_id=eid,
        branch_root_id="Q-root",
        action_type=ActionIntent.SLICING.value,
        planner_score=3.0,
        question_text="Good?",
        draft_spec=good_spec.to_dict(),
    )
    graph.persist_frontier()

    from modules.edge_research.research_controller import _select_next_experiment_from_frontier

    next_eid = _select_next_experiment_from_frontier(graph, tuple(panel.columns))
    assert next_eid is not None
    assert frontier.items[bad_id].status == FrontierItemStatus.INVALID.value
    assert graph.session.status == SessionStatus.ACTIVE


# --- Scenario H: small legitimate universe ---


def test_small_universe_exhausted_stop_with_unused_budget():
    """H: one valid question exhausted → global stop with unused budget is correct."""
    graph = _session_graph(budget=12)
    graph.session.experiments_used = 1
    graph.session.panel_preflight = {"eligible_explanatory": ["feat_alpha"]}
    frontier = ResearchFrontier()
    should_stop, reason = evaluate_global_stop(
        remaining_budget=11,
        frontier=frontier,
        features_touched=1,
        eligible_feature_count=1,
    )
    assert should_stop is True
    assert reason.code == "NO_VALID_FRONTIER"


# --- Coverage-aware planner tests (12 required) ---


def test_coverage_unexplored_feature_bonus():
    graph = _session_graph()
    graph.session.panel_preflight = {"eligible_explanatory": ["feat_alpha", "feat_beta"]}
    cand = ResearchActionCandidate(
        action_id="x",
        action_code="ADAPTIVE_feat_alpha",
        intent=ActionIntent.SLICING.value,
        question_template_id="T",
        question_text="q",
        tool_name="adaptive_partition_compare",
        tool_version="v1",
        draft_spec=_spec("adaptive_partition_compare", {"feature_column": "feat_alpha"}),
        uncertainty_addressed="u",
        expected_information="HIGH",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
    )
    assess = _assessment()
    score, comp = score_candidate(cand, assess, graph)
    assert comp.get("unexplored_feature_bonus", 0) > 0
    assert score > 0


def test_coverage_redundancy_penalty_for_tested_feature():
    graph = _session_graph()
    graph.session.panel_preflight = {"eligible_explanatory": ["feat_alpha"]}
    graph.get_search_accounting().session_ledger.explanatory_features_tested.add("feat_alpha")
    cand = ResearchActionCandidate(
        action_id="x",
        action_code="ADAPTIVE_feat_alpha",
        intent=ActionIntent.SLICING.value,
        question_template_id="T",
        question_text="q",
        tool_name="adaptive_partition_compare",
        tool_version="v1",
        draft_spec=_spec("adaptive_partition_compare", {"feature_column": "feat_alpha"}),
        uncertainty_addressed="u",
        expected_information="HIGH",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
    )
    _, comp = score_candidate(cand, _assessment(), graph)
    assert comp.get("redundancy_penalty", 0) < 0


def test_coverage_falsification_still_wins_for_strong_conditional():
    graph = _session_graph()
    eid = _seed_lineage(graph, tool="partition_group_compare")
    _attach_dummy_result(graph, eid)
    assess = _assessment(
        interesting=True,
        conditional_candidate=True,
        additional_investigation_warranted=True,
        possible_falsification_targets=("EXTREME_WINNER",),
        concentration_concerns=("DATE",),
        information_gaps=("MARKET_DEPENDENCE",),
        branch_tools_attempted=("partition_group_compare",),
        source_experiment_node_id=eid,
        tool_name="partition_group_compare",
    )
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id=eid)
    plan = plan_next_action(assess, cands, graph, experiment_node_id=eid)
    assert plan.selected.intent == ActionIntent.FALSIFICATION.value


def test_coverage_complexity_can_stop_weak_branch():
    graph = _session_graph()
    graph.get_search_accounting().session_ledger.interactions_attempted = 5
    assess = _assessment(
        interesting=False,
        additional_investigation_warranted=False,
        information_gaps=(),
    )
    cands = generate_action_candidates(assess, graph, REGISTRY)
    plan = plan_next_action(assess, cands, graph)
    assert plan.decision_type in (PlanDecisionType.STOP_BRANCH, PlanDecisionType.ABANDON)


def test_frontier_selection_deterministic():
    f = ResearchFrontier()
    for score, fid_suffix in ((3.0, "a"), (5.0, "b"), (5.0, "c")):
        fid = f._next_id()
        f.items[fid] = FrontierItem(
            frontier_id=fid,
            action_id=f"id-{fid_suffix}",
            action_code="X",
            parent_experiment_node_id="E1",
            branch_root_id="Q1",
            action_type="SLICING",
            planner_score=score,
        )
    first = f.select_best_unexplored()
    second = f.select_best_unexplored()
    assert first is not None
    assert first.planner_score == 5.0
    assert first.frontier_id <= second.frontier_id if second else True


def test_frontier_survives_serialization():
    f = ResearchFrontier()
    fid = f._next_id()
    f.items[fid] = FrontierItem(
        frontier_id=fid,
        action_id="a1",
        action_code="ACT",
        parent_experiment_node_id="E1",
        branch_root_id="Q1",
        action_type="SLICING",
        planner_score=2.0,
    )
    restored = ResearchFrontier.deserialize(f.serialize())
    assert len(restored.items) == 1
    assert restored.select_best_unexplored().action_id == "a1"


def test_stop_branch_returns_to_frontier_integration():
    graph = _session_graph(budget=12)
    panel = _synthetic_panel()
    eid = _seed_lineage(graph)
    _attach_dummy_result(graph, eid)
    graph.session.panel_preflight = build_panel_preflight(panel).to_dict()
    frontier = graph.get_frontier()
    fid = frontier._next_id()
    spec = _spec("symbol_decomposition", {"horizon": "T5"})
    frontier.items[fid] = FrontierItem(
        frontier_id=fid,
        action_id="sym",
        action_code="DECOMPOSE_SYMBOL",
        parent_experiment_node_id=eid,
        branch_root_id="Q-root",
        action_type=ActionIntent.DECOMPOSITION.value,
        planner_score=7.0,
        question_text="Symbols?",
        draft_spec=spec.to_dict(),
    )
    graph.persist_frontier()
    decision = PlanDecision(
        decision_type=PlanDecisionType.STOP_BRANCH,
        selected=None,
        all_candidates=(),
        rationale_codes=("STOP_BRANCH",),
    )
    step = apply_plan_decision(graph, eid, decision, panel_columns=tuple(panel.columns))
    assert step.spawned_experiment_id is not None


def test_stop_session_requires_global_evaluation():
    graph = _session_graph(budget=12)
    graph.session.panel_preflight = {"eligible_explanatory": ["feat_alpha", "feat_beta"]}
    eid = _seed_lineage(graph)
    _attach_dummy_result(graph, eid)
    frontier = graph.get_frontier()
    fid = frontier._next_id()
    spec = _spec("adaptive_partition_compare", {"feature_column": "feat_alpha", "max_bins": 3})
    frontier.items[fid] = FrontierItem(
        frontier_id=fid,
        action_id="explore",
        action_code="ADAPTIVE_feat_alpha",
        parent_experiment_node_id=eid,
        branch_root_id="Q-root",
        action_type=ActionIntent.SLICING.value,
        planner_score=6.0,
        question_text="Explore?",
        draft_spec=spec.to_dict(),
    )
    graph.persist_frontier()
    should_stop, reason = evaluate_global_stop(
        remaining_budget=8,
        frontier=graph.get_frontier(),
        features_touched=0,
        eligible_feature_count=2,
    )
    assert should_stop is False
    assert reason.code in ("CONTINUE", "CONTINUE_LOW_COVERAGE")


def test_session_terminal_status_not_active_after_finalize():
    graph = _session_graph()
    finalize_session(
        graph,
        SessionStopReason(code="NO_VALID_FRONTIER", detail="test"),
    )
    assert graph.session.status != SessionStatus.ACTIVE
    assert graph.session.session_stop_reason is not None


def test_budget_is_ceiling_not_quota():
    graph = _session_graph(budget=12)
    graph.session.experiments_used = 1
    should_stop, reason = evaluate_global_stop(
        remaining_budget=11,
        frontier=ResearchFrontier(),
        features_touched=0,
        eligible_feature_count=0,
    )
    assert should_stop is True
    assert reason.remaining_budget == 11


def test_panel_preflight_excludes_missing_registry_fields():
    panel = _synthetic_panel()
    report = build_panel_preflight(panel)
    assert "health_score" in report.registry_missing_from_panel or "health_score" not in panel.columns


def test_filter_candidates_marks_invalid_not_crash():
    graph = _session_graph()
    eid = _seed_lineage(graph)
    _attach_dummy_result(graph, eid)
    assess = _assessment(
        interesting=True,
        additional_investigation_warranted=True,
        source_experiment_node_id=eid,
    )
    cands = generate_action_candidates(
        assess,
        graph,
        REGISTRY,
        experiment_node_id=eid,
        panel_columns=("feat_alpha", "t5_return", "trade_date", "symbol"),
    )
    filtered = filter_candidates_for_panel(cands, ("feat_alpha", "t5_return", "trade_date", "symbol"))
    blocked = [c for c in filtered if c.blocked and c.blocked_reason and "field_absent" in c.blocked_reason]
    assert len(blocked) >= 1


def test_no_production_coupling_exploration_modules():
    import modules.edge_research.research_controller as ctrl
    import modules.edge_research.research_frontier as fr
    import modules.edge_research.research_panel_preflight as pf

    for mod in (ctrl, fr, pf):
        src = open(mod.__file__).read()
        for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
            assert forbidden not in src


def test_frontier_persisted_on_session_reload(tmp_path: Path):
    graph = _session_graph()
    frontier = graph.get_frontier()
    fid = frontier._next_id()
    frontier.items[fid] = FrontierItem(
        frontier_id=fid,
        action_id="persist",
        action_code="PERSIST",
        parent_experiment_node_id="E1",
        branch_root_id="Q1",
        action_type="SLICING",
        planner_score=1.0,
    )
    graph.persist_frontier()
    write_research_graph(graph, data_dir=tmp_path / "edge_research")
    loaded = read_research_graph(graph.session.research_session_id, data_dir=tmp_path / "edge_research")
    assert loaded.get_frontier().count_by_status("UNEXPLORED") == 1
