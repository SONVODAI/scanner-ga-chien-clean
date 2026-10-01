"""Phase 3H.13 — Semantic novelty rank reconciliation tests (A–I)."""

from __future__ import annotations

import pytest

from modules.edge_research.research_assessment import DescriptiveStrength, ResearchAssessment
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_line_freshness import EvidenceSnapshot
from modules.edge_research.research_line_identity import ResearchLineIdentity
from modules.edge_research.research_line_registry import assign_experiment_to_line
from modules.edge_research.research_novelty_rank_reconciliation import (
    RESEARCH_NOVELTY_RANK_RECONCILIATION_VERSION,
    reconcile_planner_novelty_in_base_score,
)
from modules.edge_research.research_novelty_valuation_bridge import (
    NoveltyGatingAudit,
    NoveltyValuationClass,
)
from modules.edge_research.research_planner import WEIGHT_NOVELTY, score_all_candidates
from modules.edge_research.research_portfolio import (
    score_opportunities_for_selection,
    build_opportunity_from_candidate,
)
from modules.edge_research.research_state import ExperimentSpec

CUTOFF = "2026-08-20"
POP = {"grammar_version": "research_grammar_v1", "kind": "all", "filters": []}
OUT = {
    "grammar_version": "research_grammar_v1",
    "kind": "compare",
    "field": "t5_return",
    "operator": ">",
    "value": 0.0,
}
POP_B = {
    "grammar_version": "research_grammar_v1",
    "kind": "all",
    "filters": [{"column": "symbol", "op": "eq", "value": "QQQ"}],
}
OUT_B = {
    "grammar_version": "research_grammar_v1",
    "kind": "compare",
    "field": "t10_return",
    "operator": ">",
    "value": 0.0,
}


def _graph() -> ResearchGraph:
    g = ResearchGraph.create_session(
        session_id="rank-recon-test",
        data_cutoff_date=CUTOFF,
        experiment_budget=12,
    )
    g.session.panel_preflight = {"eligible_explanatory": ["f1", "f2", "f3"]}
    return g


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(
        source_experiment_node_id="E1",
        tool_name="horizon_comparison",
        tool_status="OK",
        information_gaps=("GAP_A",),
        branch_tools_attempted=("horizon_comparison",),
        branch_observation_codes=(),
        descriptive_strength=DescriptiveStrength.GROUP_DIFFERENCE.value,
        interesting=True,
    )
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


def _candidate(*, tool: str, action_id: str, pop=None, out=None, frame_id: str = "") -> "ResearchActionCandidate":
    from modules.edge_research.research_actions import ResearchActionCandidate

    spec = ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs={"feature_column": "f1"},
        research_scope={
            "population_spec": pop or POP,
            "outcome_spec": out or OUT,
            "pending_question_context": {
                "observation_horizon": 0,
                "population_spec": pop or POP,
                "outcome_spec": out or OUT,
                "frame_id": frame_id,
            },
        },
        data_cutoff_date=CUTOFF,
    )
    return ResearchActionCandidate(
        action_id=action_id,
        action_code="TEST",
        intent="RUN_TOOL",
        question_template_id="TEST",
        question_text="test",
        tool_name=tool,
        tool_version="v1",
        draft_spec=spec,
        uncertainty_addressed="GAP_A",
        expected_information="HIGH",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
    )


def _prior_line(g: ResearchGraph) -> None:
    from modules.edge_research.research_line_identity import RESEARCH_LINE_IDENTITY_VERSION

    id1 = ResearchLineIdentity(
        version=RESEARCH_LINE_IDENTITY_VERSION,
        population_spec=POP,
        outcome_spec=OUT,
        observation_horizon=0,
        uncertainty_codes=("GAP_A",),
        research_needs=(),
        conditioning_context={},
        feature_slice=("f1",),
        evidence_lineage=(),
        metadata={"tool_name": "horizon_comparison"},
    )
    assign_experiment_to_line(g, experiment_node_id="E1", identity=id1, gain_level="ZERO")


def _erv(g, cand, assessment, base_score, components, branch_root_id="obs-root"):
    return build_opportunity_from_candidate(
        cand,
        base_score=base_score,
        components=components,
        graph=g,
        assessment=assessment,
        branch_root_id=branch_root_id,
    ).expected_research_value


def test_a_representation_loses_rank_to_independent():
    """A: same proposition/different tool vs independent — rep loses false novelty boost."""
    g = _graph()
    _prior_line(g)
    assessment = _assessment()
    rep = _candidate(tool="adaptive_partition_compare", action_id="rep1")
    ind = _candidate(tool="horizon_comparison", action_id="ind1", pop=POP_B, out=OUT_B)
    candidates = [rep, ind]
    base_scores = score_all_candidates(assessment, candidates, g)

    raw_rep_novelty = base_scores["rep1"][1].get("novelty", 0.0)
    raw_ind_novelty = base_scores["ind1"][1].get("novelty", 0.0)
    assert raw_rep_novelty > raw_ind_novelty

    _, adjusted = score_opportunities_for_selection(g, assessment, candidates, base_scores)
    rep_trail = [
        a for a in (g.session.research_rank_reconciliation_audit or []) if a["action_id"] == "rep1"
    ]
    assert rep_trail[-1]["reconciliation_applied"] is True
    assert rep_trail[-1]["gated_planner_novelty"] == 0.0

    rep_score = adjusted["rep1"][0]
    ind_score = adjusted["ind1"][0]
    assert ind_score >= rep_score


def test_b_genuine_scientific_novelty_unchanged():
    """B: independent proposition retains full novelty contribution."""
    g = _graph()
    _prior_line(g)
    cand = _candidate(tool="horizon_comparison", action_id="sci1", pop=POP_B, out=OUT_B)
    raw_novelty = WEIGHT_NOVELTY
    components = {"novelty": raw_novelty, "information_gap": 1.0}
    base = 5.0

    opp = build_opportunity_from_candidate(
        cand, base_score=base, components=components, graph=g, assessment=_assessment()
    )
    trail = g.session.research_rank_reconciliation_audit or []
    assert trail
    last = trail[-1]
    assert last["reconciliation_applied"] is False
    assert last["gated_planner_novelty"] == raw_novelty
    assert opp.expected_research_value > base


def test_c_fresh_evidence_preserves_novelty():
    """C: same proposition + fresh evidence retains novelty."""
    g = _graph()
    _prior_line(g)
    cand = _candidate(tool="adaptive_partition_compare", action_id="ev1")
    defer = EvidenceSnapshot(
        uncertainty_codes=("GAP_A",),
        observation_horizon=0,
        population_spec=POP,
        outcome_spec=OUT,
        observation_count=1,
    )
    assessment = _assessment(
        branch_observation_codes=("O1", "O2", "O3", "O4"),
        information_gaps=("GAP_A", "GAP_B"),
    )
    raw_novelty = WEIGHT_NOVELTY
    components = {"novelty": raw_novelty}
    build_opportunity_from_candidate(
        cand,
        base_score=8.0,
        components=components,
        graph=g,
        assessment=assessment,
        defer_evidence_snapshot=defer.to_dict(),
    )
    trail = g.session.research_rank_reconciliation_audit or []
    assert trail[-1]["gated_planner_novelty"] == raw_novelty


def test_d_insufficient_evidence_fail_closed():
    """D: insufficient semantic evidence preserves existing behavior."""
    g = _graph()
    cand = _candidate(tool="horizon_comparison", action_id="ins1")
    raw = WEIGHT_NOVELTY
    components = {"novelty": raw}
    opp = build_opportunity_from_candidate(
        cand, base_score=6.0, components=components, graph=g, assessment=_assessment()
    )
    trail = g.session.research_rank_reconciliation_audit or []
    assert trail[-1]["reconciliation_applied"] is False
    assert opp.expected_research_value > 6.0


def test_e_legacy_no_semantic_context():
    """E: no identity — legacy deterministic behavior."""
    g = _graph()
    cand = _candidate(tool="new_tool_x", action_id="leg1", pop=POP_B, out=OUT_B)
    raw = WEIGHT_NOVELTY
    components = {"novelty": raw}
    opp = build_opportunity_from_candidate(
        cand,
        base_score=4.0,
        components=components,
        graph=g,
        assessment=_assessment(branch_tools_attempted=()),
    )
    trail = g.session.research_rank_reconciliation_audit or []
    assert trail[-1]["reconciliation_applied"] is False
    assert opp.expected_research_value > 4.0


def test_f_representation_still_eligible_with_strong_value():
    """F: representation-only with high base value remains eligible."""
    g = _graph()
    _prior_line(g)
    cand = _candidate(tool="adaptive_partition_compare", action_id="strong1")
    high_base = 50.0
    components = {"novelty": WEIGHT_NOVELTY, "information_gap": 5.0}
    opp = build_opportunity_from_candidate(
        cand, base_score=high_base, components=components, graph=g, assessment=_assessment()
    )
    assert opp.expected_research_value > 0
    assert opp.expected_research_value >= high_base - WEIGHT_NOVELTY


def test_g_ranking_ties_deterministic():
    """G: equal reconciled scores tie-break by action_id."""
    g = _graph()
    c1 = _candidate(tool="horizon_comparison", action_id="aaa")
    c2 = _candidate(tool="horizon_comparison", action_id="bbb")
    assessment = _assessment()
    base_scores = {
        "aaa": (5.0, {"novelty": 0.0}),
        "bbb": (5.0, {"novelty": 0.0}),
    }
    _, adjusted = score_opportunities_for_selection(g, assessment, [c1, c2], base_scores)
    ranked = sorted(adjusted.items(), key=lambda x: (-x[1][0], x[0]))
    assert ranked[0][0] == "aaa"


def test_h_no_negative_novelty_values():
    """H: reconciliation never produces negative gated planner novelty."""
    audit = NoveltyGatingAudit(
        version="v1",
        action_id="x",
        valuation_class=NoveltyValuationClass.REPRESENTATION_NOVELTY_ONLY.value,
        relationship_classification="NEAR_DUPLICATE",
        freshness_classification="INSUFFICIENT_EVIDENCE",
        raw_novelty_component=2.0,
        gated_novelty_component=0.0,
        novelty_component_delta=-2.0,
        representation_novelty_only=True,
        scientific_novelty=False,
        evidence_novelty=False,
        gating_applied=True,
        component_explanation="test",
    )
    reconciled, rank_audit = reconcile_planner_novelty_in_base_score(10.0, 2.0, audit)
    assert rank_audit.gated_planner_novelty >= 0.0
    assert reconciled == 8.0


def test_i_scientific_candidates_rank_unchanged():
    """I: scientific novelty candidates have zero reconciliation delta."""
    g = _graph()
    _prior_line(g)
    cand = _candidate(tool="horizon_comparison", action_id="unch1", pop=POP_B, out=OUT_B)
    raw = WEIGHT_NOVELTY
    opp = build_opportunity_from_candidate(
        cand,
        base_score=7.0,
        components={"novelty": raw},
        graph=g,
        assessment=_assessment(),
    )
    trail = g.session.research_rank_reconciliation_audit or []
    assert trail[-1]["planner_novelty_delta"] == 0.0
    assert opp.gated_novelty_component > 0


def test_integration_score_opportunities_uses_reconciled_erv():
    """Integration: score_opportunities_for_selection returns reconciled ERV."""
    g = _graph()
    _prior_line(g)
    rep = _candidate(tool="adaptive_partition_compare", action_id="rep_int")
    ind = _candidate(tool="horizon_comparison", action_id="ind_int", pop=POP_B, out=OUT_B)
    assessment = _assessment()
    candidates = [rep, ind]
    base_scores = score_all_candidates(assessment, candidates, g)
    _, adjusted = score_opportunities_for_selection(g, assessment, candidates, base_scores)
    rep_score = adjusted["rep_int"][0]
    ind_score = adjusted["ind_int"][0]
    assert ind_score >= rep_score


def test_reconciliation_audit_version():
    assert RESEARCH_NOVELTY_RANK_RECONCILIATION_VERSION == "research_novelty_rank_reconciliation_v1"
