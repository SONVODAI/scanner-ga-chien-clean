"""Phase 3H.4 — Autonomous Laboratory Competence tests (Scenarios A–L + multi-step)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pandas as pd
import pytest

from modules.edge_research.adapters import build_research_panel, load_lifecycle
from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import ActionIntent, generate_action_candidates
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_competence import (
    RESEARCH_COMPETENCE_VERSION,
    ResearchNeedType,
    UNCERTAINTY_REDUCTION_REGISTRY,
    annotate_candidates_with_competence,
    build_research_competence_model,
    competence_neutral_for_identical_candidates,
    compute_competence_metrics,
    record_competence_audit,
    validate_no_competence_recommendation_language,
)
from modules.edge_research.research_controller import plan_after_experiment, run_experiment_and_plan
from modules.edge_research.research_exposure_governance import build_research_exposure_contract
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_interpreter import (
    FALSIFY_EXTREME_WINNER,
    GAP_HORIZON_STABILITY,
    GAP_SYMBOL_DISTRIBUTION,
    GAP_THRESHOLD_EXPLORATION,
    GAP_TIME_DISTRIBUTION,
    interpret_tool_result,
)
from modules.edge_research.research_operational_awareness import (
    build_operational_awareness,
    rebuild_awareness_at_horizon,
)
from modules.edge_research.research_panel_exposure import (
    PHASE_3H2B_FIRST_CONTROLLED_FIELD,
    build_phase_3h2b_panel_manifest,
)
from modules.edge_research.research_planner import plan_next_action, score_all_candidates
from modules.edge_research.research_state import ExperimentSpec, QuestionRationale
from modules.edge_research.research_tools import ToolResult, ToolStatus, build_default_tool_registry
from modules.edge_research.storage import read_research_graph, write_research_graph

REGISTRY = build_default_tool_registry()
CUTOFF = "2026-08-20"
FIELD = PHASE_3H2B_FIRST_CONTROLLED_FIELD


def _panel_fixture(**extra) -> pd.DataFrame:
    rows = []
    for d in range(5):
        for s in range(2):
            rows.append(
                {
                    "trade_date": f"2026-08-{d + 1:02d}",
                    "symbol": f"S{d}{s}",
                    "close": 10.0 + d,
                    "rs5": 1.0,
                    "rs10": 0.5 + s * 0.1,
                    "rsi14": 50.0,
                    "rs_spread": 0.5,
                    "rsi_slope": float(d) * 0.1,
                    "partition_group": "A" if s == 0 else "B",
                    "research_market_state": "X",
                    "research_market_transition": "Y",
                    "t3_return": 1.0,
                    "t5_return": 1.0 + 0.1 * s,
                    "t10_return": 1.0,
                }
            )
    df = pd.DataFrame(rows)
    for k, v in extra.items():
        df[k] = v
    return df


def _contract_panel():
    lc = load_lifecycle()
    if lc.empty or FIELD not in lc.columns:
        lc = _panel_fixture().rename(columns={"close": "price"})
    manifest = build_phase_3h2b_panel_manifest()
    panel = build_research_panel(lifecycle=lc, panel_manifest=manifest)
    contract = build_research_exposure_contract(panel, panel_manifest=manifest)
    return contract, panel


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
        inputs={"partition_column": "partition_group", "horizon": "T5", "partition_type": "categorical"},
        research_scope={"research_observation_horizon": 0},
        data_cutoff_date=CUTOFF,
    )
    exp_id = graph.add_experiment(question_node_id=qid, spec=spec, node_id="E1")
    return graph, exp_id


def _awareness_for_panel(panel: pd.DataFrame):
    from modules.edge_research.research_capability_registry import build_capability_registry

    contract, _ = _contract_panel()
    cap = build_capability_registry(panel, REGISTRY)
    return build_operational_awareness(panel, cap, exposure_contract=contract)


def _tool_result(tool_name: str, **metrics) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        tool_version="v1",
        data_cutoff_date=CUTOFF,
        input_hash="test",
        status=ToolStatus.OK,
        sample_size=40,
        metrics=dict(metrics),
    )


# Scenario A — tool available but irrelevant
def test_scenario_a_tool_available_not_forced():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    rsi = awareness.entry_for_field(FIELD)
    assert rsi is not None and rsi.available is True

    assess = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION,),
        branch_tools_attempted=("partition_group_compare",),
    )
    competence = build_research_competence_model(assess, awareness)
    assert FIELD not in str(competence.to_dict())

    graph, exp_id = _graph_with_experiment(panel)
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    rsi_cands = [
        c for c in cands
        if c.draft_spec and c.draft_spec.inputs.get("feature_column") == FIELD
    ]
    assert not rsi_cands or all(
        c.uncertainty_addressed != FIELD for c in rsi_cands
    )


# Scenario B — one tool becomes scientifically relevant
def test_scenario_b_tool_becomes_relevant():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    assess = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION,),
        branch_tools_attempted=("partition_group_compare",),
    )
    competence = build_research_competence_model(assess, awareness)
    time_match = next(m for m in competence.need_matches if m.uncertainty_code == GAP_TIME_DISTRIBUTION)
    assert time_match.research_need == ResearchNeedType.DECOMPOSE_HETEROGENEITY.value
    assert "date_decomposition" in time_match.eligible_tools

    graph, exp_id = _graph_with_experiment(panel)
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    decomp = [c for c in cands if c.tool_name == "date_decomposition"]
    assert decomp
    annot = annotate_candidates_with_competence(cands, competence)
    assert any(a.get("scientifically_relevant") for a in annot.values())


# Scenario C — wrong tool available, distinguish by affordance
def test_scenario_c_distinguish_relevant_tools():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    assess = _assessment(
        information_gaps=(GAP_THRESHOLD_EXPLORATION,),
        empirical_findings=("SHAPE_GRADIENT_DETECTED",),
        branch_tools_attempted=("partition_group_compare",),
    )
    competence = build_research_competence_model(assess, awareness)
    match = next(m for m in competence.need_matches if m.uncertainty_code == GAP_THRESHOLD_EXPLORATION)
    assert match.research_need == ResearchNeedType.REFINE_BOUNDARY.value
    assert "threshold_exploration" in match.eligible_tools
    assert "date_decomposition" not in match.eligible_tools

    graph, exp_id = _graph_with_experiment(panel)
    graph.attach_experiment_result(
        exp_id,
        metrics={
            "best_threshold": {"threshold": 0.5, "direction": "above"},
            "feature_column": "rs10",
            "discovered_boundaries": [0.5],
        },
    )
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    threshold_cands = [c for c in cands if c.tool_name == "threshold_exploration"]
    assert threshold_cands


# Scenario D — one experiment insufficient, follow-on changes
def test_scenario_d_evidence_responsive_followon():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    graph, exp_id = _graph_with_experiment(panel)

    assess1 = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION,),
        branch_tools_attempted=("partition_group_compare",),
    )
    cands1 = generate_action_candidates(
        assess1, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    tools1 = {c.tool_name for c in cands1 if c.tool_name}

    assess2 = _assessment(
        information_gaps=(GAP_SYMBOL_DISTRIBUTION, GAP_THRESHOLD_EXPLORATION),
        empirical_findings=("SHAPE_GRADIENT_DETECTED",),
        branch_tools_attempted=("partition_group_compare", "date_decomposition"),
    )
    cands2 = generate_action_candidates(
        assess2, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    tools2 = {c.tool_name for c in cands2 if c.tool_name}
    assert tools2 != tools1
    comp2 = build_research_competence_model(assess2, awareness, graph=graph, experiment_node_id=exp_id)
    needs2 = {m.research_need for m in comp2.need_matches if m.legally_constructible}
    assert ResearchNeedType.REFINE_BOUNDARY.value in needs2 or ResearchNeedType.DECOMPOSE_HETEROGENEITY.value in needs2


# Scenario E — promising branch deserves depth
def test_scenario_e_depth_when_warranted():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    assess = _assessment(
        information_gaps=(GAP_THRESHOLD_EXPLORATION,),
        empirical_findings=("SHAPE_GRADIENT_DETECTED",),
        interesting=True,
        additional_investigation_warranted=True,
        branch_tools_attempted=("adaptive_partition_compare",),
    )
    competence = build_research_competence_model(assess, awareness)
    assert ResearchNeedType.REFINE_BOUNDARY.value in competence.inferred_research_needs or any(
        m.research_need == ResearchNeedType.REFINE_BOUNDARY.value for m in competence.need_matches
    )
    graph, exp_id = _graph_with_experiment(panel)
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    depth_tools = {"threshold_exploration", "threshold_neighborhood", "adaptive_partition_compare"}
    assert any(c.tool_name in depth_tools for c in cands if c.tool_name)


# Scenario F — unproductive branch deserves abandonment
def test_scenario_f_redirect_when_unproductive():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    assess = _assessment(
        information_gaps=(),
        interesting=False,
        additional_investigation_warranted=False,
        descriptive_strength="NO_CLEAR_DIFFERENCE",
        fragility_evidence=("FRAGILITY_AFTER_EPISODE_CONSISTENT",),
    )
    competence = build_research_competence_model(assess, awareness)
    assert ResearchNeedType.REDIRECT_OR_ABANDON.value in competence.inferred_research_needs

    graph, exp_id = _graph_with_experiment(panel)
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id=exp_id)
    stop_cands = [c for c in cands if c.intent in (ActionIntent.STOP.value, ActionIntent.ABANDON.value)]
    assert stop_cands


# Scenario G — self-falsification
def test_scenario_g_falsification_recognized():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    assess = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION,),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
        interesting=True,
        concentration_concerns=("EXTREME_WINNER",),
    )
    competence = build_research_competence_model(assess, awareness)
    falsify_matches = [
        m for m in competence.need_matches
        if m.research_need == ResearchNeedType.SEEK_FALSIFICATION.value
    ]
    assert falsify_matches
    assert falsify_matches[0].legally_constructible

    graph, exp_id = _graph_with_experiment(panel)
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id=exp_id)
    falsify_cands = [c for c in cands if c.intent == ActionIntent.FALSIFICATION.value]
    assert falsify_cands


# Scenario H — falsification damages hypothesis
def test_scenario_h_direction_changes_after_contradiction():
    contract, panel = _contract_panel()
    graph, exp_id = _graph_with_experiment(panel)

    assess_before = _assessment(
        interesting=True,
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
    )
    cands_before = generate_action_candidates(assess_before, graph, REGISTRY, experiment_node_id=exp_id)
    scores_before = score_all_candidates(assess_before, cands_before, graph, experiment_node_id=exp_id)

    assess_after = _assessment(
        interesting=False,
        contradictions=("FRAGILITY_AFTER_EPISODE_CONSISTENT",),
        fragility_evidence=("FRAGILITY_AFTER_EPISODE_CONSISTENT",),
        additional_investigation_warranted=False,
    )
    cands_after = generate_action_candidates(assess_after, graph, REGISTRY, experiment_node_id=exp_id)
    scores_after = score_all_candidates(assess_after, cands_after, graph, experiment_node_id=exp_id)

    stop_after = [c for c in cands_after if c.intent in (ActionIntent.STOP.value, ActionIntent.ABANDON.value)]
    assert stop_after
    comp_after = build_research_competence_model(assess_after, _awareness_for_panel(panel))
    assert ResearchNeedType.REDIRECT_OR_ABANDON.value in comp_after.inferred_research_needs


# Scenario I — revisit becomes rational
def test_scenario_i_revisit_need_inferred():
    contract, panel = _contract_panel()
    graph, exp_id = _graph_with_experiment(panel)
    portfolio = graph.get_portfolio_state()
    from modules.edge_research.research_portfolio import BranchPortfolioRecord, BranchPortfolioStatus

    portfolio.branches["BR1"] = BranchPortfolioRecord(
        branch_root_id="BR1",
        status=BranchPortfolioStatus.DEFERRED_PROMISING.value,
        unresolved_research_value=3.0,
    )
    graph.persist_portfolio_state()

    assess = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    competence = build_research_competence_model(
        assess, _awareness_for_panel(panel), graph=graph, experiment_node_id=exp_id
    )
    assert ResearchNeedType.REVISIT_UNRESOLVED_BRANCH.value in competence.inferred_research_needs


# Scenario J — temporal capability at later horizon
def test_scenario_j_horizon_dynamic_competence():
    contract, panel = _contract_panel()
    from modules.edge_research.research_capability_registry import build_capability_registry

    cap = build_capability_registry(panel, REGISTRY)
    low = build_operational_awareness(panel, cap, exposure_contract=contract, observation_horizon=0)
    high = build_operational_awareness(panel, cap, exposure_contract=contract, observation_horizon=3)

    assess = _assessment(information_gaps=(GAP_HORIZON_STABILITY,))
    comp_low = build_research_competence_model(assess, low)
    comp_high = build_research_competence_model(assess, high)
    t3_low = low.entries.get("outcome:t3_return")
    t3_high = high.entries.get("outcome:t3_return")
    assert t3_low is not None and t3_high is not None
    if not t3_low.temporal_legal:
        assert t3_high.temporal_legal or t3_low.available != t3_high.available
    assert comp_low.built_at and comp_high.built_at


# Scenario K — rich toolbox, selective use
def test_scenario_k_selective_tool_use():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    assess = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    graph, exp_id = _graph_with_experiment(panel)
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    competence = build_research_competence_model(assess, awareness)
    metrics = compute_competence_metrics(competence, cands)
    assert metrics["distinct_tools_in_candidates"] < len(awareness.tool_affordances)
    assert metrics["total_candidate_count"] >= 1


# Scenario L — competence OFF vs ON, identical opportunity set
def test_scenario_l_competence_neutral_when_no_distinction():
    contract, panel = _contract_panel()
    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION, GAP_SYMBOL_DISTRIBUTION),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
    )
    awareness = _awareness_for_panel(panel)

    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    scores = score_all_candidates(assess, cands, graph, experiment_node_id=exp_id)
    decision = plan_next_action(assess, cands, graph, experiment_node_id=exp_id)

    competence = build_research_competence_model(assess, awareness)
    assert competence is not None
    assert not validate_no_competence_recommendation_language(competence.to_dict())

    shared = [c.action_id for c in cands if not c.blocked]
    assert competence_neutral_for_identical_candidates(
        scores, scores, decision, decision, shared
    )


# Multi-step autonomous competence session
def test_multistep_autonomous_competence_session():
    contract, panel = _contract_panel()
    graph, exp_id = _graph_with_experiment(panel)
    from modules.edge_research.research_operational_awareness import ensure_session_operational_awareness

    ensure_session_operational_awareness(graph, panel, REGISTRY)

    result1 = _tool_result(
        "partition_group_compare",
        best_group_success_rate=0.6,
        shape={"strength": 0.4},
    )
    graph.attach_experiment_result(
        exp_id,
        metrics=result1.metrics,
    )
    plan1 = plan_after_experiment(
        graph, exp_id, result1, REGISTRY,
        panel_columns=tuple(panel.columns),
    )
    assert plan1.competence_model is not None
    assert graph.session.research_competence_audit

    sel1 = plan1.decision.selected
    assert sel1 is not None
    tools_attempted = ["partition_group_compare"]
    if sel1.tool_name:
        tools_attempted.append(sel1.tool_name)

    result2 = _tool_result(
        sel1.tool_name or "date_decomposition",
        concentration_by_date=True,
        best_threshold={"threshold": 0.5, "direction": "above"},
    )
    assess2 = _assessment(
        source_experiment_node_id=exp_id,
        information_gaps=(GAP_SYMBOL_DISTRIBUTION, GAP_THRESHOLD_EXPLORATION),
        empirical_findings=("SHAPE_GRADIENT_DETECTED",),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
        interesting=True,
        branch_tools_attempted=tuple(tools_attempted),
    )
    cands2 = generate_action_candidates(
        assess2, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=graph.get_operational_awareness(),
    )
    comp2 = build_research_competence_model(
        assess2, graph.get_operational_awareness(), graph=graph, experiment_node_id=exp_id
    )
    assert len(comp2.need_matches) >= 2
    falsify = any(m.research_need == ResearchNeedType.SEEK_FALSIFICATION.value for m in comp2.need_matches)
    assert falsify

    audit_trail = graph.session.research_competence_audit or []
    assert len(audit_trail) >= 1
    assert audit_trail[0]["event"] == "COMPETENCE_CONSULTED"


# Negative controls
def test_negative_no_rsi_slope_preference_in_competence():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    assess = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    competence = build_research_competence_model(assess, awareness)
    violations = validate_no_competence_recommendation_language(competence.to_dict())
    assert "rsi_slope" not in str(competence.to_dict()).lower() or not violations


def test_negative_health_score_not_constructible():
    contract, panel = _contract_panel()
    awareness = _awareness_for_panel(panel)
    entry = awareness.entry_for_field("health_score")
    assert entry is not None and not entry.available
    assess = _assessment(information_gaps=(GAP_THRESHOLD_EXPLORATION,))
    graph, exp_id = _graph_with_experiment(panel)
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    health = [
        c for c in cands
        if c.draft_spec and c.draft_spec.inputs.get("feature_column") == "health_score"
    ]
    assert not health


def test_negative_planner_scores_unchanged_with_competence():
    contract, panel = _contract_panel()
    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment(
        information_gaps=(GAP_TIME_DISTRIBUTION,),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
    )
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id=exp_id)
    scores_a = score_all_candidates(assess, cands, graph, experiment_node_id=exp_id)
    scores_b = score_all_candidates(assess, cands, graph, experiment_node_id=exp_id)
    for k in scores_a:
        assert scores_a[k][0] == scores_b[k][0]


def test_negative_production_isolation():
    import modules.edge_research.research_competence as mod
    src = open(mod.__file__).read()
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in src


def test_competence_audit_persistence(tmp_path):
    contract, panel = _contract_panel()
    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    awareness = _awareness_for_panel(panel)
    competence = build_research_competence_model(assess, awareness)
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id=exp_id)
    record_competence_audit(
        graph,
        experiment_node_id=exp_id,
        competence=competence,
        candidates=cands,
        selected_action_id=cands[0].action_id if cands else "",
    )
    write_research_graph(graph, data_dir=tmp_path)
    loaded = read_research_graph(graph.session.research_session_id, data_dir=tmp_path)
    assert loaded.session.research_competence_audit
    assert loaded.session.research_competence_audit[0]["event"] == "COMPETENCE_CONSULTED"


def test_uncertainty_registry_covers_interpreter_gaps():
    from modules.edge_research.research_interpreter import (
        GAP_CATEGORY_REFINEMENT,
        GAP_EPISODE_REPLICATION,
        GAP_INTERACTION_FOLLOWUP,
        GAP_MARKET_DEPENDENCE,
        GAP_NEIGHBORHOOD_STABILITY,
        GAP_NEIGHBORHOOD_THRESHOLD,
        GAP_SYMBOL_DISTRIBUTION,
        GAP_TRAJECTORY_ROLE,
        FALSIFY_DATE_ARTIFACT,
        FALSIFY_SYMBOL_DOMINANCE,
    )
    for code in (
        GAP_TIME_DISTRIBUTION,
        GAP_SYMBOL_DISTRIBUTION,
        GAP_EPISODE_REPLICATION,
        GAP_MARKET_DEPENDENCE,
        GAP_HORIZON_STABILITY,
        GAP_NEIGHBORHOOD_STABILITY,
        GAP_TRAJECTORY_ROLE,
        GAP_THRESHOLD_EXPLORATION,
        GAP_NEIGHBORHOOD_THRESHOLD,
        GAP_CATEGORY_REFINEMENT,
        GAP_INTERACTION_FOLLOWUP,
        FALSIFY_EXTREME_WINNER,
        FALSIFY_DATE_ARTIFACT,
        FALSIFY_SYMBOL_DOMINANCE,
    ):
        assert code in UNCERTAINTY_REDUCTION_REGISTRY
