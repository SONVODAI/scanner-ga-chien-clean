"""Phase 3H — Capability Awareness / Research Laboratory Map tests A–K."""

from __future__ import annotations

import json

import pandas as pd

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import generate_action_candidates
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_capability_registry import (
    CAPABILITY_REGISTRY_VERSION,
    CapabilityCategory,
    CapabilityStatus,
    ResearchCapabilityRegistry,
    build_capability_registry,
    ensure_session_capability_registry,
    record_experiment_capability_exercise,
    validate_no_hint_leakage,
)
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_planner import plan_next_action, score_all_candidates
from modules.edge_research.research_state import (
    ExperimentSpec,
    QuestionRationale,
)
from modules.edge_research.research_tools import build_default_tool_registry
from modules.edge_research.storage import read_research_graph, write_research_graph

CUTOFF = "2026-08-20"
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
        "rs5": 1.0,
        "rsi14": 50.0,
        "rs_spread": 0.5,
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


def _panel(**extra_cols) -> pd.DataFrame:
    rows = []
    for d in range(5):
        for s in range(2):
            rows.append(
                _row(
                    trade_date=f"2026-08-{d + 1:02d}",
                    symbol=f"S{d}{s}",
                    t5_return=1.0 + 0.1 * s,
                    rs10=-7.0 if s == 0 else 2.0,
                )
            )
    df = pd.DataFrame(rows)
    for k, v in extra_cols.items():
        df[k] = v
    return df


def _graph_with_experiment(panel: pd.DataFrame) -> tuple[ResearchGraph, str]:
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    oid = graph.add_root_observation(description="Root", node_id="O1")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="test",
        rationale=QuestionRationale(reason_code="TEST", prior_node_id=oid),
        node_id="Q1",
    )
    spec = ExperimentSpec(
        tool_name="partition_group_compare",
        tool_version="v1",
        inputs={"horizon": "T5", "partition_column": "partition_group", "partition_type": "categorical"},
        research_scope={"research_observation_horizon": 0},
        data_cutoff_date=CUTOFF,
    )
    exp_id = graph.add_experiment(question_node_id=qid, spec=spec, node_id="E1")
    return graph, exp_id


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
        branch_observation_codes=(),
    )
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


# A — existing accessible capability
def test_a_existing_accessible_capability():
    panel = _panel()
    reg = build_capability_registry(panel, REGISTRY)
    tool_cap = reg.capabilities.get(f"{CapabilityCategory.RESEARCH_TOOL.value}:threshold_exploration@v1")
    assert tool_cap is not None
    assert tool_cap.status == CapabilityStatus.AVAILABLE.value
    rs10 = reg.capabilities.get(f"{CapabilityCategory.FIELD.value}:rs10")
    assert rs10 is not None
    assert rs10.status in (
        CapabilityStatus.AVAILABLE.value,
        CapabilityStatus.AVAILABLE_WITH_CONSTRAINTS.value,
    )
    assert rs10.panel_included is True


# B — exists but not research-accessible
def test_b_exists_not_research_accessible():
    panel = _panel()
    reg = build_capability_registry(panel, REGISTRY)
    sweetspot = reg.capabilities.get(
        f"{CapabilityCategory.DATA_SOURCE.value}:market_aware_sweetspot_observer_ledger"
    )
    assert sweetspot is not None
    assert sweetspot.exists_in_system is True
    assert sweetspot.status == CapabilityStatus.NOT_RESEARCH_ACCESSIBLE.value
    assert sweetspot.currently_research_accessible is False
    assert sweetspot.status != CapabilityStatus.AVAILABLE.value


# C — missing from panel
def test_c_missing_from_panel():
    panel = _panel()
    assert "health_group" not in panel.columns
    reg = build_capability_registry(panel, REGISTRY)
    hg = reg.capabilities.get(f"{CapabilityCategory.CATEGORICAL_DIMENSION.value}:health_group")
    assert hg is not None
    assert hg.status == CapabilityStatus.MISSING_FROM_PANEL.value
    assert hg.blocker in ("REGISTRY_FIELD_ABSENT_FROM_PANEL", "FIELD_ABSENT_FROM_PANEL")


# D — temporal legality
def test_d_temporal_legality_h0_vs_h5():
    panel = _panel()
    reg_h0 = build_capability_registry(panel, REGISTRY, observation_horizon=0)
    reg_h5 = build_capability_registry(panel, REGISTRY, observation_horizon=5)
    t5_h0 = reg_h0.capabilities.get(f"{CapabilityCategory.OUTCOME.value}:t5_return")
    t5_h5 = reg_h5.capabilities.get(f"{CapabilityCategory.OUTCOME.value}:t5_return")
    assert t5_h0.status == CapabilityStatus.TEMPORALLY_ILLEGAL.value
    assert t5_h5.status in (
        CapabilityStatus.AVAILABLE.value,
        CapabilityStatus.AVAILABLE_WITH_CONSTRAINTS.value,
    )
    lab = reg_h5.laboratory_map()
    legal = lab.legal_fields_at_horizon(5)
    legal_names = {
        x["field"]
        for x in legal
        if x.get("status") != CapabilityStatus.TEMPORALLY_ILLEGAL.value
    }
    assert "t5_return" in legal_names
    illegal_h0 = lab.legal_fields_at_horizon(0)
    t5_entry = next(x for x in illegal_h0 if x["field"] == "t5_return")
    assert t5_entry["status"] == CapabilityStatus.TEMPORALLY_ILLEGAL.value


# E — tool awareness without feature recommendation
def test_e_tool_awareness_no_feature_hints():
    panel = _panel()
    reg = build_capability_registry(panel, REGISTRY)
    ops = reg.laboratory_map().available_operations()
    threshold = next(o for o in ops if o["tool_name"] == "threshold_exploration")
    assert threshold["operation_classes"]
    serialized = json.dumps(ops).lower()
    assert "rs10" not in serialized
    assert "should use" not in serialized


# F — unexplored capability
def test_f_unexplored_capability():
    panel = _panel()
    reg = build_capability_registry(panel, REGISTRY)
    unexplored = reg.unexplored_capabilities()
    assert any(c.name == "rs_spread" for c in unexplored)


# G — exercised capability after experiment
def test_g_exercised_capability_after_experiment():
    panel = _panel()
    graph, exp_id = _graph_with_experiment(panel)
    ensure_session_capability_registry(graph, panel, REGISTRY)
    node = graph.get_node(exp_id)
    record_experiment_capability_exercise(graph, exp_id, node.experiment_spec)
    reg = graph.get_capability_registry()
    assert any("partition_group_compare" in cid for cid in reg.exercised_capability_ids)


# H — persistence save/reload
def test_h_persistence_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(tmp_path))
    panel = _panel()
    graph, _ = _graph_with_experiment(panel)
    ensure_session_capability_registry(graph, panel, REGISTRY)
    reg = graph.get_capability_registry()
    reg.record_exercise(
        ExperimentSpec(
            tool_name="threshold_exploration",
            tool_version="v1",
            inputs={
                "feature_column": "rs10",
                "horizon": "T5",
                "candidate_cuts": [0.0],
                "direction": "above",
            },
            research_scope={"research_observation_horizon": 0},
            data_cutoff_date=CUTOFF,
        ),
        experiment_node_id="exp-test",
    )
    graph.persist_capability_registry()
    write_research_graph(graph, data_dir=tmp_path)
    loaded = read_research_graph(graph.session.research_session_id, data_dir=tmp_path)
    assert loaded.session.research_capabilities is not None
    reloaded = ResearchCapabilityRegistry.from_dict(loaded.session.research_capabilities)
    assert reloaded.version == CAPABILITY_REGISTRY_VERSION
    assert any("threshold_exploration" in cid for cid in reloaded.exercised_capability_ids)
    lab = reloaded.laboratory_map()
    assert lab.version
    assert len(lab.available_operations()) > 0


# I — no human hint leakage
def test_i_no_human_hint_leakage():
    panel = _panel()
    reg = build_capability_registry(panel, REGISTRY)
    payload = reg.to_dict()
    lab = reg.laboratory_map().to_dict()
    violations = validate_no_hint_leakage(payload) + validate_no_hint_leakage(lab)
    assert violations == []
    text = json.dumps(payload).lower()
    for token in ("blind_benchmark", "bb07", "predictive", "recommended", "buy signal", "sell signal"):
        assert token not in text


# J — planner neutrality
def test_j_planner_neutrality_unchanged_by_awareness():
    panel = _panel()
    graph, _ = _graph_with_experiment(panel)
    assess = _assessment(information_gaps=("TIME_DISTRIBUTION",))
    cands = generate_action_candidates(assess, graph, REGISTRY, panel_columns=tuple(panel.columns))
    scores_before = score_all_candidates(assess, cands, graph)
    plan_before = plan_next_action(assess, cands, graph)

    ensure_session_capability_registry(graph, panel, REGISTRY)
    graph.session.research_capabilities = build_capability_registry(panel, REGISTRY).to_dict()

    scores_after = score_all_candidates(assess, cands, graph)
    plan_after = plan_next_action(assess, cands, graph)

    assert plan_before.decision_type == plan_after.decision_type
    assert plan_before.selected == plan_after.selected
    assert scores_before.keys() == scores_after.keys()
    for k in scores_before:
        assert scores_before[k][0] == scores_after[k][0]


# K — production isolation
def test_k_production_isolation():
    import modules.edge_research.research_capability_registry as cap_mod

    source = open(cap_mod.__file__, encoding="utf-8").read().lower()
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden.lower() not in source
    panel = _panel()
    reg = build_capability_registry(panel, REGISTRY)
    assert CapabilityStatus.AVAILABLE.value in {c.status for c in reg.capabilities.values()}
    blocked_text = json.dumps(reg.laboratory_map().blocked_with_reasons()).lower()
    assert "edge active" not in blocked_text
