"""Tests for Phase 3G search accounting, complexity control, and scientific skepticism."""

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
    plan_after_experiment,
    run_experiment_and_plan,
    run_research_session,
)
from modules.edge_research.research_grammar import OutcomeSpec, PopulationSpec
from modules.edge_research.research_graph import DuplicateExperimentError, ResearchGraph
from modules.edge_research.research_planner import plan_next_action, score_candidate
from modules.edge_research.research_search_accounting import (
    ConfirmationSplitMetadata,
    ConfirmationStatus,
    ResearchStatus,
    SearchAccountingState,
    SearchCountLedger,
    compute_complexity_score,
    compute_effective_hypotheses,
    compute_evidence_burden,
    compute_skepticism_escalation,
    record_experiment_executed,
    validate_confirmation_independence,
    weak_evidence_high_complexity_should_stop,
)
from modules.edge_research.research_state import (
    ExperimentSpec,
    NodeType,
    QuestionRationale,
    ResearchQuestionContext,
    StructuredResearchObservation,
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


def _targets(t0: str) -> dict:
    ts = pd.Timestamp(t0)
    return {
        "t3_target_date": (ts + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
        "t5_target_date": (ts + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        "t10_target_date": (ts + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
    }


def _row(i: int, *, fx: float, t5: float, date: str = "2026-08-01", symbol: str = "S0") -> dict:
    return {
        "trade_date": date,
        "symbol": symbol,
        "feature_alpha": fx,
        "t3_return": t5 * 0.8,
        "t5_return": t5,
        "t10_return": t5 * 1.1,
        "partition_group": "G1" if fx > 0 else "G2",
        "rs10": fx,
        "research_market_state": "STATE_A",
        **_targets(date),
    }


def _noise_panel(n: int = 60, seed: int = 99) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        fx = float(rng.normal(0, 1))
        t5 = float(rng.normal(0, 1))
        rows.append(_row(i, fx=fx, t5=t5, date=f"2026-08-{(i % 15) + 1:02d}", symbol=f"S{i % 8}"))
    return pd.DataFrame(rows)


def _signal_panel(n: int = 50, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        fx = float(rng.uniform(-2, 2))
        t5 = fx * 2.0 + float(rng.normal(0, 0.3))
        rows.append(_row(i, fx=fx, t5=t5, date=f"2026-08-{(i % 12) + 1:02d}", symbol=f"S{i % 6}"))
    return pd.DataFrame(rows)


def _concentrated_panel() -> pd.DataFrame:
    rows = []
    for i in range(40):
        fx = 1.0 if i < 20 else -1.0
        t5 = 5.0 if i == 0 else (0.1 if fx > 0 else -0.1)
        rows.append(_row(i, fx=fx, t5=t5, date="2026-08-01" if i == 0 else f"2026-08-{(i % 10) + 2:02d}"))
    return pd.DataFrame(rows)


def _session_graph(*, budget: int = 12) -> ResearchGraph:
    return ResearchGraph.create_session(
        data_cutoff_date=CUTOFF,
        experiment_budget=budget,
        session_id="rs-3g-test",
    )


def _spec(tool: str, inputs: dict | None = None, scope: dict | None = None) -> ExperimentSpec:
    return ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs=inputs or {"horizon": "T5", "partition_column": "partition_group", "partition_type": "categorical"},
        research_scope=scope or {},
        data_cutoff_date=CUTOFF,
    )


def _seed_experiment(graph: ResearchGraph, *, tool: str = "partition_group_compare") -> str:
    oid = graph.add_root_observation(description="seed", node_id="O-seed")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Initial?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        node_id="Q-seed",
        question_context=ResearchQuestionContext(
            population_spec=PopulationSpec.all_().to_dict(),
            outcome_spec=OutcomeSpec.compare("t5_return", ">", 0.0).to_dict(),
            research_depth=0,
        ),
    )
    return graph.add_experiment(question_node_id=qid, spec=_spec(tool), node_id="E-seed")


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(
        source_experiment_node_id="E-seed",
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


def _tool_result(**metrics) -> ToolResult:
    base = {"horizon": "T5", "success_rate": 0.5}
    base.update(metrics)
    return ToolResult(
        tool_name="partition_group_compare",
        tool_version="v1",
        data_cutoff_date=CUTOFF,
        input_hash="x",
        sample_size=int(metrics.get("sample_size", 50)),
        status=ToolStatus.OK,
        metrics=base,
        structured_observations=(
            StructuredResearchObservation(code=OBS_TRAJECTORY_GROUP_DIFFERENCE, severity="MEDIUM"),
        ),
    )


def _candidate(action_code: str, intent: str, tool: str = "", hints: dict | None = None) -> ResearchActionCandidate:
    return ResearchActionCandidate(
        action_id=f"id-{action_code}",
        action_code=action_code,
        intent=intent,
        question_template_id=action_code,
        question_text="?",
        tool_name=tool,
        tool_version="v1",
        draft_spec=_spec(tool) if tool else None,
        uncertainty_addressed="X",
        expected_information="MEDIUM",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
        rationale_codes=(action_code,),
        priority_hints=dict(hints or {}),
    )


# --- Required tests 1-4 ---


def test_session_level_search_counts_accumulate():
    graph = _session_graph()
    eid = _seed_experiment(graph)
    state = graph.get_search_accounting()
    record_experiment_executed(state, graph, eid)
    graph.persist_search_accounting()
    assert state.session_ledger.experiments_executed == 1
    assert state.session_ledger.partitions_evaluated == 1


def test_branch_level_counts_differ_from_session():
    graph = _session_graph()
    e1 = _seed_experiment(graph)
    state = graph.get_search_accounting()
    record_experiment_executed(state, graph, e1)
    oid2 = graph.add_root_observation(description="other", node_id="O2")
    q2 = graph.spawn_question(
        parent_node_ids=[oid2],
        question_text="Q2?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid2),
        node_id="Q2",
    )
    e2 = graph.add_experiment(question_node_id=q2, spec=_spec("date_decomposition", {"horizon": "T5"}), node_id="E2")
    record_experiment_executed(state, graph, e2)
    assert len(state.branch_ledgers) == 2
    assert state.session_ledger.experiments_executed == 2


def test_duplicate_experiments_do_not_inflate_executed_count():
    graph = _session_graph()
    eid = _seed_experiment(graph)
    state = graph.get_search_accounting()
    record_experiment_executed(state, graph, eid)
    before = state.session_ledger.experiments_executed
    state.session_ledger.duplicate_experiments_blocked += 1
    with pytest.raises(DuplicateExperimentError):
        graph.add_experiment(
            question_node_id=graph.get_node(eid).parent_node_ids[0],
            spec=graph.get_node(eid).experiment_spec,
        )
    assert state.session_ledger.experiments_executed == before


def test_population_refinement_increases_complexity():
    all_pop = PopulationSpec.all_()
    refined = PopulationSpec.refine(
        all_pop,
        PopulationSpec.filter_numeric("rs10", ">", 0.0),
        reason_code="TEST",
    )
    ledger = SearchCountLedger(refinements_reframes=1)
    c_all = compute_complexity_score(ledger, population_complexity=all_pop.complexity())
    c_ref = compute_complexity_score(ledger, population_complexity=refined.complexity())
    assert c_ref.aggregate_score > c_all.aggregate_score


# --- Required tests 5-7 ---


def test_outcome_composition_increases_complexity():
    simple = OutcomeSpec.compare("t5_return", ">", 0.0)
    composite = OutcomeSpec.and_(
        OutcomeSpec.compare("t5_return", ">", 0.0),
        OutcomeSpec.compare("t3_return", ">", 0.0),
    )
    ledger = SearchCountLedger()
    c1 = compute_complexity_score(ledger, outcome_complexity=simple.complexity())
    c2 = compute_complexity_score(ledger, outcome_complexity=composite.complexity())
    assert c2.outcome_complexity > c1.outcome_complexity


def test_threshold_exploration_increases_search_cardinality():
    ledger = SearchCountLedger(threshold_candidates_evaluated=10)
    mh = compute_effective_hypotheses(ledger)
    ledger2 = SearchCountLedger(threshold_candidates_evaluated=0)
    mh2 = compute_effective_hypotheses(ledger2)
    assert mh.effective_hypotheses_tested > mh2.effective_hypotheses_tested


def test_interaction_increases_complexity_more_than_single_feature():
    ledger_single = SearchCountLedger(explanatory_features_tested={"feat_a"}, partitions_evaluated=1)
    ledger_inter = SearchCountLedger(
        explanatory_features_tested={"feat_a", "feat_b"},
        interactions_attempted=1,
        partitions_evaluated=1,
    )
    c_single = compute_complexity_score(ledger_single)
    c_inter = compute_complexity_score(ledger_inter)
    assert c_inter.aggregate_score > c_single.aggregate_score


# --- Required tests 8-10 ---


def test_planner_prefers_simpler_equal_evidence_candidate():
    graph = _session_graph()
    _seed_experiment(graph)
    assessment = _assessment(
        branch_tools_attempted=("partition_group_compare", "interaction_partition"),
    )
    simple = _candidate(
        "EXPLORE_SIMPLE",
        ActionIntent.EXPLORATION.value,
        "partition_group_compare",
        {"draft_complexity": 1.0, "parent_complexity": 1.0, "observed_success_rate": 0.6},
    )
    complex_c = _candidate(
        "EXPLORE_COMPLEX",
        ActionIntent.EXPLORATION.value,
        "interaction_partition",
        {"draft_complexity": 8.0, "parent_complexity": 1.0, "observed_success_rate": 0.6},
    )
    s_simple, _ = score_candidate(simple, assessment, graph, experiment_node_id="E-seed")
    s_complex, _ = score_candidate(complex_c, assessment, graph, experiment_node_id="E-seed")
    assert s_simple > s_complex


def test_stronger_evidence_can_justify_additional_exploration():
    graph = _session_graph()
    _seed_experiment(graph)
    assessment = _assessment()
    strong = _candidate(
        "EXPLORE",
        ActionIntent.EXPLORATION.value,
        "adaptive_partition_compare",
        {"observed_success_rate": 0.85, "sample_size": 80, "shape_strength": 0.9},
    )
    weak = _candidate(
        "EXPLORE",
        ActionIntent.EXPLORATION.value,
        "adaptive_partition_compare",
        {"observed_success_rate": 0.02, "sample_size": 80},
    )
    _, comp_strong = score_candidate(strong, assessment, graph, experiment_node_id="E-seed")
    _, comp_weak = score_candidate(weak, assessment, graph, experiment_node_id="E-seed")
    assert comp_strong.get("strong_evidence_exploration", 0) > comp_weak.get("strong_evidence_exploration", 0)


def test_weak_evidence_high_complexity_produces_stop_abandon_boost():
    graph = _session_graph()
    _seed_experiment(graph)
    state = graph.get_search_accounting()
    from modules.edge_research.research_search_accounting import branch_root_id

    root = branch_root_id(graph, "E-seed")
    ledger = SearchCountLedger(
        experiments_executed=15,
        threshold_candidates_evaluated=20,
        partitions_evaluated=10,
        refinements_reframes=5,
        branch_depth_max=6,
    )
    state.branch_ledgers[root] = ledger
    graph.persist_search_accounting()
    assessment = _assessment(additional_investigation_warranted=False, interesting=False)
    stop = _candidate("STOP_BRANCH", ActionIntent.STOP.value, hints={"raw_effect": 0.01})
    _, comp = score_candidate(stop, assessment, graph, experiment_node_id="E-seed")
    assert comp.get("weak_complexity_stop", 0) > 0


# --- Required tests 11-14 ---


def test_high_winrate_increases_falsification_priority():
    bonuses = compute_skepticism_escalation(success_rate=0.85)
    assert bonuses.get("skepticism_high_winrate", 0) > 0


def test_refined_candidate_compared_to_parent():
    from modules.edge_research.research_search_accounting import build_parent_comparison

    parent = PopulationSpec.all_()
    refined = PopulationSpec.refine(
        parent,
        PopulationSpec.filter_numeric("feature_alpha", ">", 0.5),
        reason_code="REFINE",
    )
    out = OutcomeSpec.compare("t5_return", ">", 0.0)
    cmp = build_parent_comparison(
        parent,
        out,
        refined,
        out,
        parent_effect=0.5,
        candidate_effect=0.65,
        parent_n=100,
        candidate_n=40,
    )
    assert cmp.incremental_effect == pytest.approx(0.15)
    assert cmp.sample_loss == 60


def test_confirmation_cannot_reuse_discovery_observations():
    bad = ConfirmationSplitMetadata(
        discovery_cutoff="2026-08-20",
        confirmation_cutoff="2026-08-20",
        observations_overlap=True,
        confirmation_status=ConfirmationStatus.PENDING.value,
    )
    assert validate_confirmation_independence(bad) is False


def test_not_available_confirmation_supported():
    na = ConfirmationSplitMetadata(confirmation_status=ConfirmationStatus.NOT_AVAILABLE.value)
    assert validate_confirmation_independence(na) is True
    assert na.confirmation_status == "NOT_AVAILABLE"


# --- Required tests 15-17 ---


def test_pure_noise_synthetic_does_not_force_edge_discovery():
    graph = _session_graph(budget=8)
    panel = _noise_panel()
    eid = _seed_experiment(graph)
    steps = run_research_session(
        graph,
        panel,
        REGISTRY,
        initial_experiment_id=eid,
        max_steps=6,
    )
    terminal = any(s.terminal for s in steps) or graph.session.status.value in ("NO_EDGE_FOUND", "COMPLETE")
    assert terminal or graph.session.experiments_used <= 8
    for node in graph.nodes.values():
        if node.candidate_summary:
            assert node.candidate_summary.get("why_not_validated")


def test_search_accounting_survives_serialization_reload(tmp_path: Path):
    graph = _session_graph()
    eid = _seed_experiment(graph)
    record_experiment_executed(graph.get_search_accounting(), graph, eid)
    graph.persist_search_accounting()
    write_research_graph(graph, data_dir=tmp_path)
    loaded = read_research_graph(graph.session.research_session_id, data_dir=tmp_path)
    state = loaded.get_search_accounting()
    assert state.session_ledger.experiments_executed == 1
    roundtrip = SearchAccountingState.deserialize(state.serialize())
    assert roundtrip.session_ledger.experiments_executed == 1


def test_research_lineage_preserves_discovery_vs_falsification():
    from modules.edge_research.research_search_accounting import lineage_step_roles

    graph = _session_graph()
    eid = _seed_experiment(graph)
    record_experiment_executed(graph.get_search_accounting(), graph, eid)
    roles = lineage_step_roles(graph, eid)
    assert roles == ("DISCOVERY",)


# --- Required test 18-19 ---


def test_production_isolation_intact():
    forbidden = [i for i in PRODUCTION_FORBIDDEN_IMPORTS if "research_search_accounting" in i]
    assert forbidden == []


def test_existing_assessment_validated_false():
    a = _assessment()
    assert a.validated is False
    assert a.actionable is False


# --- Adversarial synthetic scenarios A-E ---


def test_adversarial_pure_noise():
    """A: many features, no true relationship — should not manufacture strong candidate."""
    panel = _noise_panel(n=80)
    graph = _session_graph(budget=10)
    oid = graph.add_root_observation(description="seed", node_id="O-noise")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Noise?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        node_id="Q-noise",
        question_context=ResearchQuestionContext(
            population_spec=PopulationSpec.all_().to_dict(),
            outcome_spec=OutcomeSpec.compare("t5_return", ">", 0.0).to_dict(),
        ),
    )
    eid = graph.add_experiment(
        question_node_id=qid,
        spec=_spec(
            "adaptive_partition_compare",
            {"feature_column": "feature_alpha", "max_bins": 4, "min_bin_n": 5, "min_total_n": 20},
        ),
        node_id="E-noise",
    )
    steps = run_research_session(graph, panel, REGISTRY, initial_experiment_id=eid, max_steps=5)
    summaries = [n.candidate_summary for n in graph.nodes.values() if n.candidate_summary]
    if summaries:
        for s in summaries:
            assert s.get("current_research_status") != ResearchStatus.CANDIDATE_DISCOVERED.value or (
                s.get("evidence_burden", {}).get("evidence_search_assessment")
                != "STRONG_RELATIVE_TO_SEARCH"
            )
    assert len(steps) >= 1


def test_adversarial_simple_true_signal():
    """B: simple feature with stable signal — prefer simple explanation."""
    graph = _session_graph()
    _seed_experiment(graph)
    assessment = _assessment()
    simple = _candidate(
        "SIMPLE",
        ActionIntent.EXPLORATION.value,
        "partition_group_compare",
        {"draft_complexity": 1.0, "parent_complexity": 1.0, "observed_success_rate": 0.7, "sample_size": 50},
    )
    ornate = _candidate(
        "ORNATE",
        ActionIntent.SLICING.value,
        "interaction_partition",
        {"draft_complexity": 10.0, "parent_complexity": 1.0, "observed_success_rate": 0.7, "sample_size": 50},
    )
    s_s, _ = score_candidate(simple, assessment, graph, experiment_node_id="E-seed")
    s_o, _ = score_candidate(ornate, assessment, graph, experiment_node_id="E-seed")
    assert s_s >= s_o


def test_adversarial_complex_fake_signal_penalized():
    """C: attractive result only after refinements — complexity penalized."""
    ledger = SearchCountLedger(
        experiments_executed=12,
        refinements_reframes=6,
        threshold_candidates_evaluated=15,
        branch_depth_max=5,
    )
    complexity = compute_complexity_score(ledger)
    evidence = compute_evidence_burden(
        raw_effect=0.12,
        incremental_effect=0.02,
        sample_size=30,
        uncertainty=0.5,
        shape_strength=0.3,
        complexity=complexity,
        search_cardinality=compute_effective_hypotheses(ledger).effective_hypotheses_tested,
    )
    assert evidence.evidence_search_assessment in (
        "WEAK_RELATIVE_TO_SEARCH",
        "MODERATE_RELATIVE_TO_SEARCH",
        "INSUFFICIENT",
    )


def test_adversarial_concentrated_signal_raises_falsification():
    """D: high winrate from one date — falsification priority rises."""
    graph = _session_graph()
    _seed_experiment(graph)
    assessment = _assessment(concentration_concerns=("DATE",), possible_falsification_targets=("DATE_ARTIFACT",))
    falsify = _candidate(
        "FALSIFY_DATE",
        ActionIntent.FALSIFICATION.value,
        "date_decomposition",
        {"observed_success_rate": 0.9},
    )
    _, comp = score_candidate(falsify, assessment, graph, experiment_node_id="E-seed")
    assert comp.get("skepticism_escalation", 0) > 0 or comp.get("falsification_threat", 0) > 0


def test_adversarial_robust_signal_continues_despite_penalty():
    """E: robust signal — exploration may continue despite complexity penalty."""
    graph = _session_graph()
    _seed_experiment(graph)
    assessment = _assessment()
    explore = _candidate(
        "ROBUST_EXPLORE",
        ActionIntent.ROBUSTNESS.value,
        "neighborhood_stability",
        {"observed_success_rate": 0.75, "sample_size": 100, "shape_strength": 0.85},
    )
    score, comp = score_candidate(explore, assessment, graph, experiment_node_id="E-seed")
    assert comp.get("strong_evidence_exploration", 0) > 0
    assert score > 0


def test_weak_evidence_high_complexity_helper():
    complexity = compute_complexity_score(
        SearchCountLedger(threshold_candidates_evaluated=30, branch_depth_max=8),
        branch_depth=8,
    )
    evidence = compute_evidence_burden(
        raw_effect=0.01,
        incremental_effect=0.005,
        sample_size=20,
        uncertainty=1.0,
        shape_strength=0.0,
        complexity=complexity,
        search_cardinality=50,
    )
    assert weak_evidence_high_complexity_should_stop(evidence, complexity)


def test_effective_hypotheses_has_disclaimer():
    mh = compute_effective_hypotheses(SearchCountLedger(experiments_executed=5))
    assert mh.correction_applicable is False
    assert "adaptive" in mh.limitation_disclaimer.lower()


def test_research_status_enum_values():
    assert ResearchStatus.EXPLORATORY.value == "EXPLORATORY"
    assert ResearchStatus.NEEDS_FALSIFICATION.value == "NEEDS_FALSIFICATION"
    assert ResearchStatus.NEEDS_CONFIRMATION.value == "NEEDS_CONFIRMATION"
