"""Phase 3H.6 — Evidence-Based Research Information Value bridge tests (A–U)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import (
    ActionIntent,
    ResearchActionCandidate,
    generate_action_candidates,
)
from modules.edge_research.research_assessment import DescriptiveStrength, ResearchAssessment
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_information_value import (
    RESEARCH_INFORMATION_VALUE_VERSION,
    apply_information_value_bridge,
    assess_research_information_value,
    build_selection_counterfactual_audit,
    record_information_value_audit,
    validate_no_forbidden_bridge_patterns,
    _falsification_pathway,
    _heterogeneity_pathway,
)
from modules.edge_research.research_interpreter import (
    FALSIFY_EXTREME_WINNER,
    GAP_SYMBOL_DISTRIBUTION,
    GAP_TIME_DISTRIBUTION,
)
from modules.edge_research.research_planner import score_all_candidates
from modules.edge_research.research_portfolio import score_opportunities_for_selection
from modules.edge_research.research_state import ExperimentSpec
from modules.edge_research.research_tools import build_default_tool_registry

REGISTRY = build_default_tool_registry()
CUTOFF = "2026-08-20"


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(
        source_experiment_node_id="E1",
        tool_name="horizon_comparison",
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
        descriptive_strength=DescriptiveStrength.NO_CLEAR_DIFFERENCE.value,
        interpretation_confidence="HIGH",
        additional_investigation_warranted=True,
        interesting=True,
        validated=False,
        actionable=False,
        branch_tools_attempted=(),
        branch_observation_codes=(),
        observation_kind="",
        conditional_candidate=False,
    )
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


def _candidate(
    action_id: str,
    *,
    tool: str,
    intent: str,
    uncertainty: str,
    feature_column: str = "",
) -> ResearchActionCandidate:
    inputs = {"horizon": "T5"}
    if feature_column:
        inputs["feature_column"] = feature_column
    return ResearchActionCandidate(
        action_id=action_id,
        action_code=f"ACT_{action_id}",
        intent=intent,
        question_template_id="T1",
        question_text="test?",
        tool_name=tool,
        tool_version="v1",
        draft_spec=ExperimentSpec(
            tool_name=tool,
            tool_version="v1",
            data_cutoff_date=CUTOFF,
            inputs=inputs,
            research_scope={"population_spec": {"kind": "all", "grammar_version": "research_grammar_v1"}},
        ),
        uncertainty_addressed=uncertainty,
        expected_information="HIGH",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
        rationale_codes=("TEST",),
        priority_hints={},
    )


def _minimal_graph() -> ResearchGraph:
    g = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    g.session.panel_preflight = {"eligible_explanatory": ["rs10", "rsi14"]}
    return g


def test_a_unresolved_uncertainty_increases_value():
    assessment = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    cand = _candidate("c1", tool="date_decomposition", intent=ActionIntent.DECOMPOSITION.value, uncertainty=GAP_TIME_DISTRIBUTION)
    riv = assess_research_information_value(cand, assessment)
    assert riv.valuation_contribution > 0
    assert riv.can_directly_address


def test_b_resolved_uncertainty_zero_value():
    assessment = _assessment(
        information_gaps=(),
        branch_observation_codes=("EXTREME_WINNER_ROBUST",),
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
    )
    cand = _candidate("f1", tool="sensitivity_analysis", intent=ActionIntent.FALSIFICATION.value, uncertainty=FALSIFY_EXTREME_WINNER)
    riv = assess_research_information_value(cand, assessment)
    assert riv.valuation_contribution == 0
    assert "adequate" in riv.contribution_zero_reason


def test_c_falsification_need_alone_no_bonus_without_target():
    assessment = _assessment(
        possible_falsification_targets=(),
        interesting=False,
        descriptive_strength=DescriptiveStrength.INSUFFICIENT.value,
    )
    cand = _candidate("f2", tool="sensitivity_analysis", intent=ActionIntent.FALSIFICATION.value, uncertainty=FALSIFY_EXTREME_WINNER)
    riv = assess_research_information_value(cand, assessment)
    assert riv.valuation_contribution == 0


def test_d_first_falsification_outranks_via_bridge():
    graph = _minimal_graph()
    assessment = _assessment(
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
        interesting=True,
        descriptive_strength=DescriptiveStrength.GROUP_DIFFERENCE.value,
    )
    fals = _candidate("f3", tool="sensitivity_analysis", intent=ActionIntent.FALSIFICATION.value, uncertainty=FALSIFY_EXTREME_WINNER)
    reframe = _candidate("r1", tool="horizon_comparison", intent=ActionIntent.REFRAME.value, uncertainty="OUTCOME_SPEC_ALTERNATIVE")
    base_scores = {"f3": (1.0, {}), "r1": (3.0, {})}
    bridged, _ = apply_information_value_bridge(base_scores, graph=graph, assessment=assessment, candidates=[fals, reframe])
    assert bridged["f3"][0] > bridged["r1"][0]


def test_e_repeated_falsification_diminishing():
    assessment_first = _assessment(possible_falsification_targets=(FALSIFY_EXTREME_WINNER,), interesting=True)
    assessment_repeat = _assessment(
        possible_falsification_targets=(FALSIFY_EXTREME_WINNER,),
        branch_tools_attempted=("sensitivity_analysis",),
        interesting=True,
    )
    cand = _candidate("f4", tool="sensitivity_analysis", intent=ActionIntent.FALSIFICATION.value, uncertainty=FALSIFY_EXTREME_WINNER)
    first = assess_research_information_value(cand, assessment_first)
    second = assess_research_information_value(cand, assessment_repeat)
    assert second.valuation_contribution < first.valuation_contribution


def test_f_heterogeneity_increases_decomposition_value():
    assessment = _assessment(information_gaps=(GAP_SYMBOL_DISTRIBUTION,))
    cand = _candidate("d1", tool="symbol_decomposition", intent=ActionIntent.DECOMPOSITION.value, uncertainty=GAP_SYMBOL_DISTRIBUTION)
    riv = assess_research_information_value(cand, assessment)
    assert riv.valuation_contribution > 0
    assert riv.heterogeneity_relevance > 0


def test_g_resolved_heterogeneity_zero():
    assessment = _assessment(information_gaps=())
    cand = _candidate("d2", tool="symbol_decomposition", intent=ActionIntent.DECOMPOSITION.value, uncertainty=GAP_SYMBOL_DISTRIBUTION)
    riv = assess_research_information_value(cand, assessment)
    assert riv.valuation_contribution == 0


def test_h_tool_name_alone_no_advantage():
    assessment = _assessment(information_gaps=())
    for tool in ("sensitivity_analysis", "date_decomposition", "horizon_comparison"):
        cand = _candidate(f"t_{tool}", tool=tool, intent=ActionIntent.EXPLORATION.value, uncertainty="UNRELATED")
        riv = assess_research_information_value(cand, assessment)
        assert riv.valuation_contribution == 0


def test_i_feature_name_alone_no_advantage():
    assessment = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    c1 = _candidate(
        "x1", tool="date_decomposition", intent=ActionIntent.DECOMPOSITION.value,
        uncertainty=GAP_TIME_DISTRIBUTION, feature_column="rsi_slope",
    )
    c2 = _candidate(
        "x2", tool="date_decomposition", intent=ActionIntent.DECOMPOSITION.value,
        uncertainty=GAP_TIME_DISTRIBUTION, feature_column="rs10",
    )
    v1 = assess_research_information_value(c1, assessment).valuation_contribution
    v2 = assess_research_information_value(c2, assessment).valuation_contribution
    assert v1 == v2


def test_j_no_evidence_deficit_no_bridge():
    assessment = _assessment(information_gaps=(), possible_falsification_targets=())
    cand = _candidate("u1", tool="date_decomposition", intent=ActionIntent.DECOMPOSITION.value, uncertainty=GAP_TIME_DISTRIBUTION)
    riv = assess_research_information_value(cand, assessment)
    assert riv.valuation_contribution == 0


def test_k_unrelated_candidate_no_benefit():
    assessment = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    cand = _candidate("u2", tool="horizon_comparison", intent=ActionIntent.REFRAME.value, uncertainty="OUTCOME_SPEC_ALTERNATIVE")
    riv = assess_research_information_value(cand, assessment)
    assert riv.valuation_contribution == 0


def test_l_high_base_candidate_still_wins():
    graph = _minimal_graph()
    assessment = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    decomp = _candidate("d3", tool="date_decomposition", intent=ActionIntent.DECOMPOSITION.value, uncertainty=GAP_TIME_DISTRIBUTION)
    strong = _candidate("s1", tool="horizon_comparison", intent=ActionIntent.REFRAME.value, uncertainty="OUTCOME_SPEC_ALTERNATIVE")
    base_scores = {"d3": (0.0, {}), "s1": (50.0, {})}
    bridged, _ = apply_information_value_bridge(base_scores, graph=graph, assessment=assessment, candidates=[decomp, strong])
    assert bridged["s1"][0] > bridged["d3"][0]


def test_m_selection_unchanged_when_bridge_zero():
    assessment = _assessment(information_gaps=())
    c1 = _candidate("a1", tool="horizon_comparison", intent=ActionIntent.REFRAME.value, uncertainty="OUTCOME")
    c2 = _candidate("a2", tool="threshold_exploration", intent=ActionIntent.EXPLORATION.value, uncertainty="OTHER")
    base = {"a1": (5.0, {}), "a2": (3.0, {})}
    graph = _minimal_graph()
    bridged, assessments = apply_information_value_bridge(base, graph=graph, assessment=assessment, candidates=[c1, c2])
    audit = build_selection_counterfactual_audit(
        experiment_node_id="E1", candidates=[c1, c2], base_scores=base, bridged_scores=bridged, assessments=assessments
    )
    assert not audit.selection_changed


def test_n_counterfactual_audit_persisted():
    graph = _minimal_graph()
    assessment = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,), possible_falsification_targets=(FALSIFY_EXTREME_WINNER,))
    fals = _candidate("f5", tool="sensitivity_analysis", intent=ActionIntent.FALSIFICATION.value, uncertainty=FALSIFY_EXTREME_WINNER)
    refr = _candidate("r2", tool="horizon_comparison", intent=ActionIntent.REFRAME.value, uncertainty="OUTCOME")
    base = {"f5": (2.0, {}), "r2": (4.0, {})}
    bridged, assessments = apply_information_value_bridge(base, graph=graph, assessment=assessment, candidates=[fals, refr])
    audit = build_selection_counterfactual_audit(
        experiment_node_id="E1", candidates=[fals, refr], base_scores=base, bridged_scores=bridged, assessments=assessments
    )
    record_information_value_audit(graph, audit)
    assert graph.session.research_information_value_audit
    assert graph.session.research_information_value_audit[0]["winner_without_bridge"] == "r2"


def test_o_information_value_audit_survives_reload():
    graph = _minimal_graph()
    graph.session.research_information_value_audit = [
        {"event": "INFORMATION_VALUE_SELECTION_AUDIT", "selection_changed": False}
    ]
    payload = graph.serialize()
    loaded = ResearchGraph.deserialize(payload)
    assert loaded.session.research_information_value_audit == graph.session.research_information_value_audit


def test_p_temporal_legality_unchanged():
    graph = _minimal_graph()
    assessment = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION, GAP_SYMBOL_DISTRIBUTION))
    candidates = generate_action_candidates(assessment, graph, REGISTRY)
    scores = score_all_candidates(assessment, candidates, graph)
    bridged, _ = apply_information_value_bridge(scores, graph=graph, assessment=assessment, candidates=candidates)
    assert len(bridged) == len(scores)


def test_q_bridge_does_not_alter_candidate_set():
    graph = _minimal_graph()
    assessment = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    candidates = generate_action_candidates(assessment, graph, REGISTRY)
    before = {c.action_id for c in candidates}
    scores = score_all_candidates(assessment, candidates, graph)
    apply_information_value_bridge(scores, graph=graph, assessment=assessment, candidates=candidates)
    after = {c.action_id for c in candidates}
    assert before == after


def test_r_portfolio_layer_still_applied():
    graph = _minimal_graph()
    assessment = _assessment(information_gaps=(GAP_TIME_DISTRIBUTION,))
    candidates = list(generate_action_candidates(assessment, graph, REGISTRY)[:5])
    base = score_all_candidates(assessment, candidates, graph, experiment_node_id="E1")
    opps, adj = score_opportunities_for_selection(
        graph, assessment, candidates, base, use_information_value_bridge=True
    )
    assert opps
    assert any("information_value_adjustment" in comp for _, comp in adj.values())


def test_s_no_forced_diversity():
    src = inspect.getsource(apply_information_value_bridge) + inspect.getsource(assess_research_information_value)
    assert "coverage_quota" not in src.lower()


def test_t_production_isolation():
    import modules.edge_research.research_information_value as riv

    src = inspect.getsource(riv)
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in src


def test_u_no_bb09_leakage():
    src = inspect.getsource(assess_research_information_value) + inspect.getsource(apply_information_value_bridge)
    violations = validate_no_forbidden_bridge_patterns(src)
    assert not violations


def test_negative_controls_forbidden_patterns():
    src = (
        inspect.getsource(assess_research_information_value)
        + inspect.getsource(apply_information_value_bridge)
        + inspect.getsource(_falsification_pathway)
        + inspect.getsource(_heterogeneity_pathway)
    ).lower()
    for term in (
        "competence_match_bonus",
        "falsification_bonus",
        "decomposition_bonus",
        "sensitivity_analysis_bonus",
        "preferred_tool",
        "preferred_feature",
    ):
        assert term not in src


def test_version_constant():
    assert RESEARCH_INFORMATION_VALUE_VERSION == "research_information_value_v1"
