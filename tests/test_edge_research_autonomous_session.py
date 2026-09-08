"""Tests for PATCH 3D autonomous research integration + durable sessions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.autonomous_research import (
    AutonomousResearchConfig,
    autonomous_research_enabled,
    bootstrap_research_graph,
    run_autonomous_research_session,
)
from modules.edge_research.engine import EdgeResearchEngine
from modules.edge_research.research_actions import generate_action_candidates
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_controller import run_research_session
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_grammar import OutcomeSpec, PopulationSpec
from modules.edge_research.research_state import (
    ExperimentResult,
    ExperimentSpec,
    NodeType,
    QuestionRationale,
    ResearchQuestionContext,
    compute_result_hash,
)
from modules.edge_research.research_tools import (
    OBS_TRAJECTORY_GROUP_DIFFERENCE,
    ToolResult,
    ToolStatus,
    build_default_tool_registry,
)
from modules.edge_research.storage import read_research_graph, write_research_graph

CUTOFF = "2026-08-20"
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


def _grammar_config(**kwargs) -> AutonomousResearchConfig:
    defaults = dict(
        data_cutoff_date=CUTOFF,
        initial_observation="Synthetic panel signal for autonomous test",
        initial_question="Do partition groups differ on forward outcomes?",
        population_spec=PopulationSpec.all_(),
        outcome_spec=OutcomeSpec.compare("t5_return", ">", 0.0),
        experiment_budget=4,
        max_steps=2,
        auto_persist=False,
    )
    defaults.update(kwargs)
    return AutonomousResearchConfig(**defaults)


def test_autonomous_session_bootstrap():
    config = _grammar_config()
    graph, qid, eid = bootstrap_research_graph(config)
    q = graph.get_node(qid)
    assert q.question_context is not None
    assert q.question_context.population_spec["kind"] == "all"
    assert q.question_context.outcome_spec["kind"] == "compare"
    assert graph.get_node(eid).experiment_spec is not None


def test_autonomous_session_runs_with_flag(tmp_path: Path):
    config = _grammar_config(auto_persist=True, max_steps=1)
    result = run_autonomous_research_session(
        _broad_panel(),
        config,
        data_dir=tmp_path,
        enabled=True,
    )
    assert result.graph.session.experiments_used >= 1
    assert len(result.steps) >= 1
    assert result.session_path is not None
    assert result.session_path.exists()


def test_session_persist_reload_preserves_graph_meaning(tmp_path: Path):
    config = _grammar_config(auto_persist=True, max_steps=1, session_id="rs-persist-test")
    run_autonomous_research_session(
        _broad_panel(),
        config,
        data_dir=tmp_path,
        enabled=True,
    )
    loaded = read_research_graph("rs-persist-test", data_dir=tmp_path)
    assert loaded.session.research_session_id == "rs-persist-test"
    with_ctx = [
        n for n in loaded.nodes.values()
        if n.node_type == NodeType.QUESTION and n.question_context is not None
    ]
    assert len(with_ctx) >= 1
    original = json.dumps(
        with_ctx[0].question_context.to_dict(),
        sort_keys=True,
    )
    reloaded = json.dumps(
        read_research_graph("rs-persist-test", data_dir=tmp_path)
        .get_node(with_ctx[0].node_id)
        .question_context.to_dict(),
        sort_keys=True,
    )
    assert original == reloaded


def test_engine_entry_point_feature_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EDGE_RESEARCH_AUTONOMOUS", "0")
    engine = EdgeResearchEngine(data_dir=tmp_path)
    assert engine.is_autonomous_research_enabled() is False
    with pytest.raises(RuntimeError, match="disabled"):
        engine.run_autonomous_research(_grammar_config(), panel=_broad_panel())

    monkeypatch.setenv("EDGE_RESEARCH_AUTONOMOUS", "1")
    assert engine.is_autonomous_research_enabled() is True
    result = engine.run_autonomous_research(
        _grammar_config(max_steps=1, auto_persist=True),
        panel=_broad_panel(),
        enabled=True,
    )
    assert result.graph.session.experiments_used >= 1


def test_planner_generates_grammar_candidates_without_t3_rules():
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, session_id="rs-grammar-cand")
    pop = PopulationSpec.all_()
    out = OutcomeSpec.compare("t5_return", ">", 0.0)
    qctx = ResearchQuestionContext(
        population_spec=pop.to_dict(),
        outcome_spec=out.to_dict(),
        research_depth=0,
    )
    oid = graph.add_root_observation(description="seed")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="test?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        question_context=qctx,
    )
    scope = {"population_spec": pop.to_dict()}
    eid = graph.add_experiment(
        question_node_id=qid,
        spec=ExperimentSpec(
            tool_name="partition_group_compare",
            tool_version="v1",
            inputs={"horizon": "T5", "partition_column": "partition_group", "partition_type": "categorical"},
            research_scope=scope,
            data_cutoff_date=CUTOFF,
        ),
    )
    assessment = ResearchAssessment(
        source_experiment_node_id=eid,
        tool_name="partition_group_compare",
        tool_status="OK",
        descriptive_strength="GROUP_DIFFERENCE",
        interesting=True,
        additional_investigation_warranted=True,
        information_gaps=("TIME_DISTRIBUTION",),
    )
    candidates = generate_action_candidates(
        assessment,
        graph,
        REGISTRY,
        experiment_node_id=eid,
    )
    codes = {c.action_code for c in candidates}
    assert "REFRAME_OUTCOME" in codes or "REPOPULATE_REFINE" in codes
    assert "STOP_BRANCH" in codes
    # No T3-specific action codes
    assert not any("T3_WINNER" in c.action_code for c in candidates)


def test_lineage_shows_question_changed_from_prior_result():
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, session_id="rs-lineage")
    pop = PopulationSpec.all_()
    out = OutcomeSpec.compare("t5_return", ">", 0.0)
    qctx = ResearchQuestionContext(
        population_spec=pop.to_dict(),
        outcome_spec=out.to_dict(),
        research_depth=0,
    )
    oid = graph.add_root_observation(description="seed", node_id="O1")
    q1 = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Initial?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        question_context=qctx,
        node_id="Q1",
    )
    e1 = graph.add_experiment(
        question_node_id=q1,
        spec=ExperimentSpec(
            tool_name="partition_group_compare",
            tool_version="v1",
            inputs={"horizon": "T5", "partition_column": "partition_group", "partition_type": "categorical"},
            research_scope={},
            data_cutoff_date=CUTOFF,
        ),
        node_id="E1",
    )
    graph.attach_experiment_result(
        e1,
        metrics={"sample_size": 10, "status": "OK"},
    )
    refined = PopulationSpec.refine(
        pop,
        PopulationSpec.filter_numeric("rs10", ">", 0.0),
        reason_code="REPOPULATE_REFINE",
        triggering_evidence={"interesting": True},
    )
    new_out = OutcomeSpec.compare("t10_return", ">", 0.0)
    child_ctx = ResearchQuestionContext(
        population_spec=refined.to_dict(),
        outcome_spec=new_out.to_dict(),
        research_depth=1,
        population_change={
            "parent_population_hash": pop.content_hash(),
            "reason_code": "REPOPULATE_REFINE",
            "triggering_evidence": {"source": "E1"},
        },
    )
    q2 = graph.spawn_child_question_from_experiment(
        e1,
        question_text="Refined population?",
        reason_code="REPOPULATE_REFINE",
        evidence_summary={"prior_result": "GROUP_DIFFERENCE"},
        question_context=child_ctx,
        node_id="Q2",
    )
    lineage = graph.reconstruct_lineage(q2)
    ids = [n.node_id for n in lineage]
    assert ids == ["O1", "Q1", "E1", "Q2"]
    q2_node = graph.get_node(q2)
    assert q2_node.rationale.reason_code == "REPOPULATE_REFINE"
    assert q2_node.question_context.population_spec["kind"] == "refine"
    assert q2_node.question_context.outcome_spec["field"] == "t10_return"


def test_controller_auto_persist(tmp_path: Path):
    graph = ResearchGraph.create_session(
        data_cutoff_date=CUTOFF,
        experiment_budget=3,
        session_id="rs-auto-persist",
    )
    oid = graph.add_root_observation(description="seed")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
    )
    eid = graph.add_experiment(
        question_node_id=qid,
        spec=ExperimentSpec(
            tool_name="partition_group_compare",
            tool_version="v1",
            inputs={"horizon": "T5", "partition_column": "partition_group", "partition_type": "categorical"},
            research_scope={},
            data_cutoff_date=CUTOFF,
        ),
    )
    run_research_session(
        graph,
        _broad_panel(),
        REGISTRY,
        initial_experiment_id=eid,
        max_steps=1,
        auto_persist=True,
        persist_dir=tmp_path,
    )
    path = tmp_path / "research_sessions" / "rs-auto-persist.json"
    assert path.exists()
    loaded = read_research_graph("rs-auto-persist", data_dir=tmp_path)
    assert loaded.session.experiments_used == graph.session.experiments_used


def test_feature_flag_default_off():
    assert autonomous_research_enabled(False) is False
    assert autonomous_research_enabled(True) is True
