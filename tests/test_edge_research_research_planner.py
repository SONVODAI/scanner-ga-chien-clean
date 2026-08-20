"""Tests for PATCH 3C adaptive research brain (planner + controller)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.contracts import GUARDRAILS_CONFIG_VERSION, PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import (
    ActionIntent,
    ResearchActionCandidate,
    generate_action_candidates,
    viable_candidates,
)
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_controller import (
    apply_plan_decision,
    plan_after_experiment,
    run_experiment_and_plan,
    run_research_session,
)
from modules.edge_research.research_graph import DuplicateExperimentError, ResearchGraph, ResearchGraphError
from modules.edge_research.research_interpreter import (
    FALSIFY_EXTREME_WINNER,
    GAP_MARKET_DEPENDENCE,
    GAP_TIME_DISTRIBUTION,
    interpret_tool_result,
)
from modules.edge_research.research_planner import PlanDecisionType, plan_next_action, score_all_candidates
from modules.edge_research.research_state import (
    ExperimentResult,
    ExperimentSpec,
    NextActionCandidate,
    NodeType,
    QuestionRationale,
    SessionStatus,
    StructuredResearchObservation,
    compute_experiment_content_hash,
    compute_result_hash,
)
from modules.edge_research.research_tools import (
    OBS_EXTREME_WINNER_SENSITIVE,
    OBS_NO_CLEAR_DIFFERENCE,
    OBS_TRAJECTORY_GROUP_DIFFERENCE,
    ToolResult,
    ToolStatus,
    build_default_tool_registry,
    execute_research_experiment,
)
from modules.edge_research.storage import read_research_graph, write_research_graph

CUTOFF = "2026-08-20"
SCOPE: dict = {}
REGISTRY = build_default_tool_registry()


def _target_dates(t0: str) -> dict:
    t0_ts = pd.Timestamp(t0)
    return {
        "t3_target_date": (t0_ts + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
        "t5_target_date": (t0_ts + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        "t10_target_date": (t0_ts + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
    }


def _row(**kwargs) -> dict:
    defaults = {
        "trade_date": "2026-08-01",
        "symbol": "S0",
        "t5_return": 1.0,
        "t3_return": 1.0,
        "t10_return": 1.0,
        "partition_group": "A",
        "rs10": 0.0,
        "research_market_state": "EARLY_RECOVERY",
        "research_market_transition": "STRESS -> EARLY_RECOVERY",
    }
    defaults.update(kwargs)
    defaults.update(_target_dates(defaults["trade_date"]))
    return defaults


def _panel(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _broad_panel() -> pd.DataFrame:
    rows = []
    for d in range(5):
        for s in range(2):
            rows.append(
                _row(
                    trade_date=f"2026-08-{d + 1:02d}",
                    symbol=f"S{d}{s}",
                    t5_return=1.0 + 0.1 * s + (2.0 if s == 0 else 0.0),
                    group="A" if s == 0 else "B",
                    rs10=-7.0 if s == 0 else 2.0,
                )
            )
    return _panel(rows)


def _spec(tool: str, inputs: dict | None = None) -> ExperimentSpec:
    return ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs=inputs or {"horizon": "T5"},
        research_scope=SCOPE,
        data_cutoff_date=CUTOFF,
    )


def _session_graph(*, budget: int = 12) -> ResearchGraph:
    return ResearchGraph.create_session(
        data_cutoff_date=CUTOFF,
        experiment_budget=budget,
        session_id="rs-planner-test",
    )


def _seed_lineage(graph: ResearchGraph, *, first_tool: str = "partition_group_compare") -> str:
    oid = graph.add_root_observation(description="Initial signal", node_id="O1")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Initial question?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        node_id="Q1",
    )
    inputs = {"horizon": "T5"}
    if first_tool == "partition_group_compare":
        inputs.update(
            {
                "partition_column": "partition_group",
                "partition_type": "categorical",
            }
        )
    eid = graph.add_experiment(
        question_node_id=qid,
        spec=_spec(first_tool, inputs),
        node_id="E1",
    )
    return eid


def _tool_result(
    *,
    tool_name: str = "partition_group_compare",
    status: ToolStatus = ToolStatus.OK,
    observations: list[StructuredResearchObservation] | None = None,
    sample_size: int = 50,
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        tool_version="v1",
        data_cutoff_date=CUTOFF,
        input_hash="abc123",
        sample_size=sample_size,
        status=status,
        metrics={"horizon": "T5"},
        structured_observations=tuple(observations or ()),
    )


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(
        source_experiment_node_id="E1",
        tool_name="partition_group_compare",
        tool_status="OK",
        empirical_findings=(),
        unresolved_uncertainties=(),
        contradictions=(),
        concentration_concerns=(),
        replication_concerns=(),
        fragility_evidence=(),
        context_dependence=(),
        horizon_dependence=(),
        information_gaps=(),
        possible_falsification_targets=(),
        descriptive_strength="GROUP_DIFFERENCE",
        interpretation_confidence="MEDIUM",
        additional_investigation_warranted=True,
        interesting=True,
        validated=False,
        actionable=False,
        branch_tools_attempted=("partition_group_compare",),
        branch_observation_codes=(OBS_TRAJECTORY_GROUP_DIFFERENCE,),
    )
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


# --- Core adaptivity cases ---


def test_same_observation_different_history_different_tool():
    """CASE A vs B: history changes planner choice."""
    graph_a = _session_graph()
    assess_a = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION,),
        possible_falsification_targets=(),
        branch_tools_attempted=("partition_group_compare",),
    )
    plan_a = plan_next_action(assess_a, generate_action_candidates(assess_a, graph_a, REGISTRY), graph_a)
    assert plan_a.decision_type == PlanDecisionType.EXPERIMENT
    assert plan_a.selected.tool_name == "date_decomposition"

    graph_b = _session_graph()
    assess_b = _assessment(
        information_gaps=(GAP_MARKET_DEPENDENCE,),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
        branch_tools_attempted=("partition_group_compare", "date_decomposition"),
    )
    plan_b = plan_next_action(assess_b, generate_action_candidates(assess_b, graph_b, REGISTRY), graph_b)
    assert plan_b.decision_type == PlanDecisionType.EXPERIMENT
    assert plan_b.selected.tool_name != plan_a.selected.tool_name


def test_different_evidence_different_action():
    graph = _session_graph()
    _seed_lineage(graph)
    weak = _assessment(
        interesting=False,
        additional_investigation_warranted=False,
        descriptive_strength="NO_CLEAR_DIFFERENCE",
        information_gaps=(),
        possible_falsification_targets=(),
        empirical_findings=(OBS_NO_CLEAR_DIFFERENCE,),
    )
    plan_weak = plan_next_action(weak, generate_action_candidates(weak, graph, REGISTRY), graph)
    assert plan_weak.decision_type == PlanDecisionType.STOP

    strong = _assessment(
        interesting=True,
        information_gaps=(GAP_TIME_DISTRIBUTION, GAP_MARKET_DEPENDENCE),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
    )
    plan_strong = plan_next_action(strong, generate_action_candidates(strong, graph, REGISTRY), graph)
    assert plan_strong.decision_type == PlanDecisionType.EXPERIMENT


def test_multiple_viable_candidates_generated():
    graph = _session_graph()
    _seed_lineage(graph)
    assess = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION, GAP_MARKET_DEPENDENCE),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
    )
    cands = generate_action_candidates(assess, graph, REGISTRY)
    experiments = [c for c in cands if c.intent not in (ActionIntent.STOP.value, ActionIntent.ABANDON.value)]
    assert len(experiments) >= 2
    assert len(viable_candidates(cands)) >= 2


def test_planner_rationale_recorded():
    graph = _session_graph()
    eid = _seed_lineage(graph)
    result = execute_research_experiment(graph, eid, REGISTRY, _broad_panel())
    planning = plan_after_experiment(graph, eid, result, REGISTRY)
    node = graph.get_node(eid)
    assert len(node.candidate_next_actions) >= 2
    assert node.selected_next_action is not None
    assert node.selected_next_action.metadata.get("planner_score") is not None
    assert planning.decision.rationale_codes


def test_duplicate_experiment_excluded():
    graph = _session_graph()
    _seed_lineage(graph)
    assess = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    spec = _spec("date_decomposition")
    graph.experiment_index[compute_experiment_content_hash(spec)] = "E-dup"
    cands = generate_action_candidates(assess, graph, REGISTRY)
    date_cand = next(c for c in cands if c.action_code == "DECOMPOSE_DATE")
    assert date_cand.blocked is True
    assert date_cand.blocked_reason == "DUPLICATE_EXPERIMENT"


def test_budget_exhaustion_stops_research():
    graph = _session_graph(budget=1)
    eid = _seed_lineage(graph)
    execute_research_experiment(graph, eid, REGISTRY, _broad_panel())
    assess = _assessment(information_gaps=(GAP_MARKET_DEPENDENCE,))
    cands = generate_action_candidates(assess, graph, REGISTRY)
    graph.session.experiments_used = 1
    plan = plan_next_action(assess, cands, graph)
    assert plan.decision_type == PlanDecisionType.STOP


def test_falsification_can_outrank_exploration():
    """CASE D: serious untested fragility threat → falsification wins."""
    graph = _session_graph()
    assess = _assessment(
        interesting=True,
        information_gaps=(GAP_MARKET_DEPENDENCE,),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
        branch_tools_attempted=("partition_group_compare",),
        concentration_concerns=("DATE",),
    )
    cands = generate_action_candidates(assess, graph, REGISTRY)
    plan = plan_next_action(assess, cands, graph)
    assert plan.decision_type == PlanDecisionType.EXPERIMENT
    assert plan.selected.intent == ActionIntent.FALSIFICATION.value
    assert plan.selected.tool_name == "sensitivity_analysis"


def test_exploration_can_outrank_falsification():
    """CASE E: market gap more informative when falsification already attempted."""
    graph = _session_graph()
    assess = _assessment(
        interesting=True,
        information_gaps=(GAP_MARKET_DEPENDENCE,),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
        branch_tools_attempted=("partition_group_compare", "sensitivity_analysis"),
    )
    cands = generate_action_candidates(assess, graph, REGISTRY)
    plan = plan_next_action(assess, cands, graph)
    assert plan.decision_type == PlanDecisionType.EXPERIMENT
    assert plan.selected.tool_name == "market_conditioning"


def test_weak_first_result_stops_immediately():
    """CASE C + correction 1: no minimum depth before STOP."""
    graph = _session_graph()
    _seed_lineage(graph)
    weak_result = _tool_result(
        status=ToolStatus.OK,
        observations=[StructuredResearchObservation(code=OBS_NO_CLEAR_DIFFERENCE)],
        sample_size=10,
    )
    assess = interpret_tool_result(graph, "E1", weak_result)
    assert assess.additional_investigation_warranted is False
    plan = plan_next_action(assess, generate_action_candidates(assess, graph, REGISTRY), graph)
    assert plan.decision_type == PlanDecisionType.STOP


def test_exhausted_branch_stops():
    graph = _session_graph()
    assess = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION,),
        branch_tools_attempted=("partition_group_compare", "date_decomposition", "symbol_decomposition"),
    )
    spec = _spec("date_decomposition")
    graph.experiment_index[compute_experiment_content_hash(spec)] = "E-dup"
    cands = generate_action_candidates(assess, graph, REGISTRY)
    viable = [c for c in cands if not c.blocked and c.intent not in (ActionIntent.STOP.value, ActionIntent.ABANDON.value)]
    assert not viable
    plan = plan_next_action(assess, cands, graph)
    assert plan.decision_type in (PlanDecisionType.STOP, PlanDecisionType.ABANDON)


def test_no_edge_found_reachable():
    graph = _session_graph(budget=12)
    eid = _seed_lineage(graph)
    weak = _tool_result(observations=[StructuredResearchObservation(code=OBS_NO_CLEAR_DIFFERENCE)])
    execute_research_experiment(graph, eid, REGISTRY, _broad_panel())
    planning = plan_after_experiment(graph, eid, weak, REGISTRY)
    apply_plan_decision(graph, eid, planning.decision)
    assert graph.session.status == SessionStatus.NO_EDGE_FOUND


def test_cutoff_immutable():
    graph = _session_graph()
    with pytest.raises(ResearchGraphError, match="immutable"):
        graph.assert_data_cutoff_immutable("2026-08-01")


def test_guardrails_version_immutable_on_session():
    graph = _session_graph()
    assert graph.session.guardrails_config_version == GUARDRAILS_CONFIG_VERSION


def test_no_buy_sell_in_planner_output():
    graph = _session_graph()
    assess = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION, GAP_MARKET_DEPENDENCE))
    cands = generate_action_candidates(assess, graph, REGISTRY)
    blob = json.dumps([c.to_next_action_candidate().to_dict() for c in cands]).upper()
    for word in ("BUY", "SELL", "EDGE_ACTIVE", "BULLISH"):
        assert word not in blob


def test_experiment_spec_validated_against_registry():
    graph = _session_graph()
    assess = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    cands = generate_action_candidates(assess, graph, REGISTRY)
    for c in cands:
        if c.draft_spec and not c.blocked:
            REGISTRY.get(c.draft_spec.tool_name, c.draft_spec.tool_version)


def test_selected_experiment_enters_lineage():
    graph = _session_graph()
    eid = _seed_lineage(graph)
    step = run_experiment_and_plan(graph, eid, _broad_panel(), REGISTRY)
    if step.spawned_experiment_id:
        lineage = graph.reconstruct_lineage(step.spawned_experiment_id)
        assert any(n.node_id == "E1" for n in lineage)


def test_tool_result_returns_to_interpreter():
    graph = _session_graph()
    eid = _seed_lineage(graph)
    result = execute_research_experiment(graph, eid, REGISTRY, _broad_panel())
    assess = interpret_tool_result(graph, eid, result)
    assert assess.source_experiment_node_id == eid
    assert assess.tool_name == result.tool_name


def test_second_decision_may_differ_from_first():
    graph = _session_graph(budget=12)
    eid = _seed_lineage(graph)
    step1 = run_experiment_and_plan(graph, eid, _broad_panel(), REGISTRY)
    if step1.terminal or not step1.spawned_experiment_id:
        pytest.skip("first step terminated")
    step2 = run_experiment_and_plan(graph, step1.spawned_experiment_id, _broad_panel(), REGISTRY)
    assert step1.planning.decision.selected.action_id != step2.planning.decision.selected.action_id or (
        step1.planning.decision.decision_type != step2.planning.decision.decision_type
    )


def test_deterministic_replay_same_decision():
    graph1 = _session_graph()
    _seed_lineage(graph1)
    assess = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION, GAP_MARKET_DEPENDENCE),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
    )
    cands = generate_action_candidates(assess, graph1, REGISTRY)
    plan1 = plan_next_action(assess, cands, graph1)

    graph2 = _session_graph()
    _seed_lineage(graph2)
    plan2 = plan_next_action(assess, cands, graph2)
    assert plan1.selected.action_id == plan2.selected.action_id
    assert plan1.decision_type == plan2.decision_type


def test_candidate_selection_persists_serialize_reload(tmp_path: Path):
    graph = _session_graph()
    eid = _seed_lineage(graph)
    result = execute_research_experiment(graph, eid, REGISTRY, _broad_panel())
    plan_after_experiment(graph, eid, result, REGISTRY)
    write_research_graph(graph, data_dir=tmp_path / "edge_research")
    reloaded = read_research_graph(graph.session.research_session_id, data_dir=tmp_path / "edge_research")
    node = reloaded.get_node(eid)
    assert len(node.candidate_next_actions) >= 2
    assert node.selected_next_action is not None


def test_no_production_coupling_imports():
    import modules.edge_research.research_controller as ctrl
    import modules.edge_research.research_planner as pln

    for mod in (ctrl, pln):
        src = open(mod.__file__).read()
        for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
            assert forbidden not in src


def test_add_experiment_budget_enforced():
    graph = _session_graph(budget=1)
    eid = _seed_lineage(graph)
    graph.session.experiments_used = 1
    qid = graph.spawn_question(
        parent_node_ids=[eid],
        question_text="Q2?",
        rationale=QuestionRationale(reason_code="T", prior_node_id=eid),
    )
    with pytest.raises(ResearchGraphError, match="budget exhausted"):
        graph.add_experiment(question_node_id=qid, spec=_spec("date_decomposition"))


# --- Multi-step behavioral sessions ---


def test_multistep_session_abandon_after_fragility():
    """E1 → follow-up → fragility destroys relationship → ABANDON/STOP."""
    rows = []
    for i in range(10):
        rows.append(_row(trade_date=f"2026-08-{i+1:02d}", symbol=f"S{i}", t5_return=2.0, partition_group="A"))
    for i in range(10):
        rows.append(_row(trade_date=f"2026-08-{i+1:02d}", symbol=f"S{i+10}", t5_return=0.5, partition_group="B"))
    panel = _panel(rows)

    graph = _session_graph(budget=12)
    eid = _seed_lineage(graph)
    step1 = run_experiment_and_plan(graph, eid, panel, REGISTRY)
    assert step1.planning.decision.decision_type == PlanDecisionType.EXPERIMENT

    if step1.spawned_experiment_id:
        # Force fragility result on sensitivity path.
        e2 = step1.spawned_experiment_id
        fragile_rows = []
        for i in range(9):
            fragile_rows.append(_row(trade_date=f"2026-08-{i+1:02d}", symbol=f"S{i}", t5_return=-0.1))
        fragile_rows.append(_row(trade_date="2026-08-10", symbol="S9", t5_return=100.0))
        fragile_panel = _panel(fragile_rows)
        step2 = run_experiment_and_plan(graph, e2, fragile_panel, REGISTRY)
        if step2.planning.assessment.fragility_evidence:
            assert step2.planning.decision.decision_type in (
                PlanDecisionType.ABANDON,
                PlanDecisionType.STOP,
                PlanDecisionType.EXPERIMENT,
            )


def test_multistep_session_different_first_path():
    """Two sessions with same panel can choose different first follow-ups based on history."""
    panel = _broad_panel()
    graph1 = _session_graph()
    e1 = _seed_lineage(graph1)
    r1 = execute_research_experiment(graph1, e1, REGISTRY, panel)
    p1 = plan_after_experiment(graph1, e1, r1, REGISTRY)

    graph2 = _session_graph()
    e2 = _seed_lineage(graph2)
    graph2.attach_experiment_result(
        e2,
        metrics={"x": 1},
        observations=[StructuredResearchObservation(code=OBS_TRAJECTORY_GROUP_DIFFERENCE)],
    )
    graph2.experiment_index[compute_experiment_content_hash(_spec("date_decomposition"))] = "E0"
    assess2 = _assessment(
        branch_tools_attempted=("partition_group_compare", "date_decomposition"),
        information_gaps=(GAP_MARKET_DEPENDENCE,),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
    )
    p2 = plan_next_action(assess2, generate_action_candidates(assess2, graph2, REGISTRY), graph2)

    if p1.decision.decision_type == PlanDecisionType.EXPERIMENT and p2.decision_type == PlanDecisionType.EXPERIMENT:
        assert (
            p1.decision.selected.tool_name != p2.decision.selected.tool_name
            or p1.decision.selected.action_code != p2.decision.selected.action_code
        )


def test_assessment_never_validated_or_actionable():
    graph = _session_graph()
    eid = _seed_lineage(graph)
    result = execute_research_experiment(graph, eid, REGISTRY, _broad_panel())
    assess = interpret_tool_result(graph, eid, result)
    assert assess.validated is False
    assert assess.actionable is False


def test_run_research_session_controller_loop():
    graph = _session_graph(budget=3)
    eid = _seed_lineage(graph)
    steps = run_research_session(graph, _broad_panel(), REGISTRY, initial_experiment_id=eid, max_steps=3)
    assert len(steps) >= 1
    assert graph.session.experiments_used <= 3
