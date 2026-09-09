"""Phase 3G.4.2 — budget termination and post-final-experiment lifecycle tests A–K."""

from __future__ import annotations

import inspect
from unittest import mock

import pandas as pd
import pytest

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import ActionIntent
from modules.edge_research.research_controller import (
    _spawn_from_frontier_item,
    build_budget_exhausted_stop_reason,
    run_experiment_and_plan,
    run_research_session,
)
from modules.edge_research.research_frontier import FrontierItem, FrontierItemStatus
from modules.edge_research.research_graph import ResearchGraph, ResearchGraphError
from modules.edge_research.research_planner import PlanDecisionType
from modules.edge_research.research_portfolio import BranchPortfolioStatus
from modules.edge_research.research_state import (
    ExperimentSpec,
    NodeType,
    QuestionRationale,
    SessionStatus,
)
from modules.edge_research.research_tools import build_default_tool_registry

CUTOFF = "2026-08-20"
SCOPE: dict = {}
REGISTRY = build_default_tool_registry()


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
    t0 = pd.Timestamp(defaults["trade_date"])
    defaults.update(
        {
            "t3_target_date": (t0 + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
            "t5_target_date": (t0 + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
            "t10_target_date": (t0 + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        }
    )
    return defaults


def _broad_panel() -> pd.DataFrame:
    rows = []
    for d in range(5):
        for s in range(2):
            rows.append(
                _row(
                    trade_date=f"2026-08-{d + 1:02d}",
                    symbol=f"S{d}{s}",
                    t5_return=1.0 + 0.1 * s + (2.0 if s == 0 else 0.0),
                    partition_group="A" if s == 0 else "B",
                    rs10=-7.0 if s == 0 else 2.0,
                )
            )
    return pd.DataFrame(rows)


def _spec(tool: str = "partition_group_compare", inputs: dict | None = None) -> ExperimentSpec:
    ins = inputs or {
        "horizon": "T5",
        "partition_column": "partition_group",
        "partition_type": "categorical",
    }
    return ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs=ins,
        research_scope=SCOPE,
        data_cutoff_date=CUTOFF,
    )


def _graph(*, budget: int = 3) -> ResearchGraph:
    return ResearchGraph.create_session(
        data_cutoff_date=CUTOFF,
        experiment_budget=budget,
        session_id="rs-budget-termination",
    )


def _seed(graph: ResearchGraph, *, node_id: str = "E1") -> str:
    oid = graph.add_root_observation(description="Root", node_id="O1")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Seed?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        node_id="Q1",
    )
    return graph.add_experiment(question_node_id=qid, spec=_spec(), node_id=node_id)


def _panel_preflight(graph: ResearchGraph) -> None:
    graph.session.panel_preflight = {
        "eligible_explanatory": ["partition_group", "rs10", "rs5"],
        "partition_columns_available": ["partition_group"],
    }


def _run_session(graph: ResearchGraph, *, max_steps: int, initial: str) -> list:
    _panel_preflight(graph)
    return run_research_session(
        graph,
        _broad_panel(),
        REGISTRY,
        initial_experiment_id=initial,
        max_steps=max_steps,
    )


# --- A. Exact budget exhaustion ---


def test_a_exact_budget_exhaustion_terminates_cleanly():
    graph = _graph(budget=3)
    eid = _seed(graph)
    steps = _run_session(graph, max_steps=3, initial=eid)

    assert graph.session.experiments_used == 3
    assert graph.session.status == SessionStatus.BUDGET_EXHAUSTED
    assert len(steps) == 3
    final = steps[-1]
    assert final.session_terminal is True
    assert final.terminal_reason == "BUDGET_EXHAUSTED"
    assert final.spawned_experiment_id is None
    stop = graph.session.session_stop_reason or {}
    assert stop.get("code") == "BUDGET_EXHAUSTED"
    assert stop.get("terminal_status") == "BUDGET_EXHAUSTED"
    assert stop.get("experiments_executed") == 3
    assert stop.get("experiment_budget") == 3
    assert stop.get("remaining_budget") == 0
    assert stop.get("final_experiment_id") == steps[-1].planning.experiment_node_id


# --- B. One below budget ---


def test_b_one_below_budget_continues_planning():
    graph = _graph(budget=3)
    eid = _seed(graph)
    _panel_preflight(graph)
    step = run_experiment_and_plan(graph, eid, _broad_panel(), REGISTRY)

    assert graph.session.experiments_used < graph.session.experiment_budget
    assert graph.session.status == SessionStatus.ACTIVE
    assert step.session_terminal is False
    assert step.planning is not None
    assert step.planning.decision.decision_type == PlanDecisionType.EXPERIMENT


# --- C. Final experiment from LOCAL ---


def test_c_final_experiment_from_local_clean_termination():
    graph = _graph(budget=2)
    eid = _seed(graph)
    steps = _run_session(graph, max_steps=2, initial=eid)

    assert graph.session.status == SessionStatus.BUDGET_EXHAUSTED
    assert steps[-1].terminal_reason == "BUDGET_EXHAUSTED"
    assert steps[-1].planning is not None
    assert steps[-1].planning.decision.rationale_codes[-1] == "BUDGET_EXHAUSTED"


# --- D. Final experiment from FRONTIER ---


def test_d_final_experiment_from_frontier_clean_termination():
    graph = _graph(budget=2)
    e1 = _seed(graph, node_id="E1")
    _panel_preflight(graph)

    from modules.edge_research.research_search_accounting import record_experiment_executed
    from modules.edge_research.research_tools import execute_research_experiment

    execute_research_experiment(graph, e1, REGISTRY, _broad_panel())
    record_experiment_executed(graph.get_search_accounting(), graph, e1)

    item = FrontierItem(
        frontier_id="f-final",
        action_id="act-frontier-final",
        action_code="FRONTIER_FINAL",
        parent_experiment_node_id=e1,
        branch_root_id="O1",
        action_type=ActionIntent.EXPLORATION.value,
        planner_score=99.0,
        draft_spec=_spec(
            inputs={"horizon": "T5", "partition_column": "rs10", "partition_type": "numeric"}
        ).to_dict(),
        question_text="Frontier final?",
    )
    graph.get_frontier().items["f-final"] = item
    graph.persist_frontier()

    e_frontier = _spawn_from_frontier_item(graph, item, tuple(_broad_panel().columns))
    assert e_frontier is not None
    assert graph.session.experiments_used == 2

    step2 = run_experiment_and_plan(graph, e_frontier, _broad_panel(), REGISTRY)

    assert graph.session.status == SessionStatus.BUDGET_EXHAUSTED
    assert step2.session_terminal is True
    assert step2.terminal_reason == "BUDGET_EXHAUSTED"
    assert step2.spawned_experiment_id is None
    assert graph.get_node(e_frontier).experiment_result is not None
    assert graph.get_frontier().items["f-final"].status == FrontierItemStatus.EXECUTED.value


# --- E. Final experiment from REVISIT ---


def test_e_final_experiment_from_revisit_clean_termination():
    graph = _graph(budget=2)
    e1 = _seed(graph, node_id="E1")
    _panel_preflight(graph)

    from modules.edge_research.research_search_accounting import record_experiment_executed
    from modules.edge_research.research_tools import execute_research_experiment

    execute_research_experiment(graph, e1, REGISTRY, _broad_panel())
    record_experiment_executed(graph.get_search_accounting(), graph, e1)

    branch_id = "O1"
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_id)
    branch.status = BranchPortfolioStatus.DEFERRED_PROMISING.value
    branch.experiments_on_branch = 1
    branch.unresolved_research_value = 5.0
    graph.persist_portfolio_state()

    item = FrontierItem(
        frontier_id="f-revisit",
        action_id="act-revisit-final",
        action_code="REVISIT_FINAL",
        parent_experiment_node_id=e1,
        branch_root_id=branch_id,
        action_type=ActionIntent.EXPLORATION.value,
        planner_score=8.0,
        draft_spec=_spec(
            inputs={"horizon": "T10", "partition_column": "rs10", "partition_type": "numeric"}
        ).to_dict(),
        question_text="Revisit final?",
    )
    graph.get_frontier().items["f-revisit"] = item
    graph.persist_frontier()

    e_revisit = _spawn_from_frontier_item(graph, item, tuple(_broad_panel().columns))
    assert e_revisit is not None

    step = run_experiment_and_plan(graph, e_revisit, _broad_panel(), REGISTRY)

    assert graph.session.status == SessionStatus.BUDGET_EXHAUSTED
    assert step.session_terminal is True
    assert step.terminal_reason == "BUDGET_EXHAUSTED"


# --- F. High-value frontier remains unresolved ---


def test_f_high_value_frontier_unresolved_at_exhaustion():
    graph = _graph(budget=2)
    eid = _seed(graph)
    frontier = graph.get_frontier()
    frontier.items["f-high"] = FrontierItem(
        frontier_id="f-high",
        action_id="act-high",
        action_code="HIGH_VALUE",
        parent_experiment_node_id=eid,
        branch_root_id="obs-x",
        action_type=ActionIntent.EXPLORATION.value,
        planner_score=99.0,
        draft_spec=_spec().to_dict(),
        question_text="High value?",
    )
    graph.persist_frontier()

    steps = _run_session(graph, max_steps=2, initial=eid)

    assert graph.session.status == SessionStatus.BUDGET_EXHAUSTED
    item = graph.get_frontier().items["f-high"]
    assert item.status == FrontierItemStatus.UNEXPLORED.value
    assert steps[-1].spawned_experiment_id is None
    stop = graph.session.session_stop_reason or {}
    assert stop.get("unexplored_frontier_count", 0) >= 1


# --- G. Final experiment result persistence ---


def test_g_final_experiment_fully_persisted_in_audit():
    graph = _graph(budget=2)
    eid = _seed(graph)
    steps = _run_session(graph, max_steps=2, initial=eid)

    final_id = steps[-1].planning.experiment_node_id
    final_node = graph.get_node(final_id)
    assert final_node.experiment_result is not None
    assert final_node.experiment_result.finalized is True

    ledger = graph.get_search_accounting().session_ledger
    assert ledger.experiments_executed == 2

    portfolio = graph.get_portfolio_state()
    assert portfolio.metrics is not None
    assert graph.get_frame_registry() is not None
    assert final_id in graph.experiment_index.values()


# --- H. No false ERROR on budget exhaustion ---


def test_h_budget_exhaustion_not_recorded_as_error():
    graph = _graph(budget=2)
    eid = _seed(graph)
    _run_session(graph, max_steps=2, initial=eid)

    assert graph.session.status != SessionStatus.ERROR
    stop = graph.session.session_stop_reason or {}
    assert stop.get("code") == "BUDGET_EXHAUSTED"
    assert stop.get("error_type") is None
    assert "ResearchGraphError" not in stop.get("error_message", "")


# --- I. Genuine finalization failure still ERROR ---


def test_i_genuine_persistence_failure_still_error():
    graph = _graph(budget=1)
    eid = _seed(graph)
    _panel_preflight(graph)

    with mock.patch.object(
        graph,
        "persist_portfolio_state",
        side_effect=RuntimeError("disk full"),
    ):
        with pytest.raises(RuntimeError, match="disk full"):
            run_experiment_and_plan(graph, eid, _broad_panel(), REGISTRY)


def test_i_planning_failure_after_non_final_experiment_records_error():
    graph = _graph(budget=5)
    eid = _seed(graph)
    _panel_preflight(graph)

    with mock.patch(
        "modules.edge_research.research_controller.plan_after_experiment",
        side_effect=ResearchGraphError("genuine planning defect"),
    ):
        step = run_experiment_and_plan(graph, eid, _broad_panel(), REGISTRY)

    assert graph.session.status == SessionStatus.ERROR
    assert step.session_terminal is True
    stop = graph.session.session_stop_reason or {}
    assert stop.get("error_type") == "ResearchGraphError"


# --- J. Experiment identity ledger ---


def test_j_final_experiment_identity_registered_once():
    graph = _graph(budget=2)
    eid = _seed(graph)
    steps = _run_session(graph, max_steps=2, initial=eid)

    assert len(graph.experiment_index) == 2
    hashes = list(graph.experiment_index.keys())
    assert len(hashes) == len(set(hashes))
    final_id = steps[-1].planning.experiment_node_id
    assert final_id in graph.experiment_index.values()


# --- K. Production isolation ---


def test_k_production_isolation():
    from modules.edge_research import research_controller

    source = inspect.getsource(research_controller)
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in source


def test_build_budget_exhausted_stop_reason_schema():
    graph = _graph(budget=3)
    eid = _seed(graph)
    graph.session.experiments_used = 3
    reason = build_budget_exhausted_stop_reason(graph, eid)
    payload = reason.to_dict()
    assert payload["terminal_status"] == "BUDGET_EXHAUSTED"
    assert payload["experiment_budget"] == 3
    assert payload["experiments_executed"] == 3
    assert payload["final_experiment_id"] == eid
    assert payload["remaining_budget"] == 0
