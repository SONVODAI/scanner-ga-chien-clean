"""Phase 3H.11 — Evidence-gated novelty valuation bridge tests (A–G)."""

from __future__ import annotations

import inspect

import pytest

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_assessment import DescriptiveStrength, ResearchAssessment
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_line_freshness import EvidenceSnapshot, FreshnessClassification
from modules.edge_research.research_line_identity import RESEARCH_LINE_IDENTITY_VERSION, ResearchLineIdentity
from modules.edge_research.research_line_registry import assign_experiment_to_line
from modules.edge_research.research_novelty_valuation_bridge import (
    RESEARCH_NOVELTY_VALUATION_BRIDGE_VERSION,
    NoveltyValuationClass,
    apply_novelty_valuation_bridge,
    classify_novelty_valuation,
    gate_novelty_component,
)
from modules.edge_research.research_planner import WEIGHT_NOVELTY
from modules.edge_research.research_portfolio import (
    WEIGHT_NOVELTY_PORTFOLIO,
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
POP_B = {"grammar_version": "research_grammar_v1", "kind": "all", "filters": [{"column": "symbol", "op": "eq", "value": "QQQ"}]}
OUT_B = {
    "grammar_version": "research_grammar_v1",
    "kind": "compare",
    "field": "t10_return",
    "operator": ">",
    "value": 0.0,
}


def _graph() -> ResearchGraph:
    g = ResearchGraph.create_session(
        session_id="novelty-bridge-test",
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


def test_a_same_proposition_different_tool_zero_novelty():
    """A: same proposition + different tool → gated novelty = 0."""
    g = _graph()
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
    cand = _candidate(tool="adaptive_partition_compare", action_id="a2")
    raw = WEIGHT_NOVELTY * (WEIGHT_NOVELTY_PORTFOLIO / 2.0)
    gated, audit = apply_novelty_valuation_bridge(
        g, cand, _assessment(), raw_novelty_component=raw, branch_root_id="obs-root"
    )
    assert gated == 0.0
    assert audit.valuation_class == NoveltyValuationClass.REPRESENTATION_NOVELTY_ONLY.value


def test_b_same_proposition_different_frame_no_representation_reward():
    """B: semantically equivalent frame change → no representation novelty reward."""
    g = _graph()
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
        metadata={"tool_name": "horizon_comparison", "frame_id": "frame-1"},
    )
    assign_experiment_to_line(g, experiment_node_id="E1", identity=id1, gain_level="LOW")
    cand = _candidate(tool="horizon_comparison", action_id="a2", frame_id="frame-2")
    raw = 2.0
    gated, audit = apply_novelty_valuation_bridge(
        g, cand, _assessment(), raw_novelty_component=raw, branch_root_id="obs-root"
    )
    assert gated == 0.0
    assert audit.valuation_class in (
        NoveltyValuationClass.REPRESENTATION_NOVELTY_ONLY.value,
        NoveltyValuationClass.INSUFFICIENT_EVIDENCE.value,
    )


def test_c_fresh_evidence_preserves_novelty():
    """C: same line + fresh evidence → novelty preserved."""
    g = _graph()
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
    cand = _candidate(tool="adaptive_partition_compare", action_id="a2")
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
    raw = 3.5
    gated, audit = apply_novelty_valuation_bridge(
        g,
        cand,
        assessment,
        raw_novelty_component=raw,
        branch_root_id="obs-root",
        defer_snapshot=defer,
    )
    assert gated == raw
    assert audit.evidence_novelty or audit.valuation_class == NoveltyValuationClass.EVIDENCE_NOVELTY.value


def test_d_distinct_proposition_preserves_novelty():
    """D: independent line → existing novelty preserved."""
    g = _graph()
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
    )
    assign_experiment_to_line(g, experiment_node_id="E1", identity=id1, gain_level="ZERO")
    cand = _candidate(tool="horizon_comparison", action_id="a2", pop=POP_B, out=OUT_B)
    raw = 4.0
    gated, audit = apply_novelty_valuation_bridge(
        g, cand, _assessment(), raw_novelty_component=raw, branch_root_id="obs-root"
    )
    assert gated == raw
    assert audit.valuation_class in (
        NoveltyValuationClass.SCIENTIFIC_NOVELTY.value,
        NoveltyValuationClass.INSUFFICIENT_EVIDENCE.value,
    )


def test_e_insufficient_evidence_fail_closed():
    """E: insufficient semantic evidence → no gating."""
    g = _graph()
    cand = _candidate(tool="horizon_comparison", action_id="a1")
    raw = 2.5
    gated, audit = apply_novelty_valuation_bridge(
        g, cand, _assessment(), raw_novelty_component=raw, branch_root_id="obs-root"
    )
    assert gated == raw
    assert audit.gating_applied is False


def test_f_legacy_path_no_registry():
    """F: empty registry / no prior line — backward compatible."""
    g = _graph()
    cand = _candidate(tool="new_tool", action_id="a9", pop=POP_B, out=OUT_B)
    raw = 1.0
    gated, audit = apply_novelty_valuation_bridge(
        g, cand, _assessment(branch_tools_attempted=()), raw_novelty_component=raw
    )
    assert gated == raw
    assert audit.valuation_class in (
        NoveltyValuationClass.LEGACY_NO_SEMANTIC_CONTEXT.value,
        NoveltyValuationClass.INSUFFICIENT_EVIDENCE.value,
        NoveltyValuationClass.SCIENTIFIC_NOVELTY.value,
    )
    assert audit.gating_applied is False


def test_g_gating_never_creates_negative_penalty():
    """G: gated novelty is never negative."""
    for raw in (0.0, 1.5, 3.0):
        assert gate_novelty_component(raw, valuation_class=NoveltyValuationClass.REPRESENTATION_NOVELTY_ONLY.value) >= 0.0
        assert gate_novelty_component(raw, valuation_class=NoveltyValuationClass.INSUFFICIENT_EVIDENCE.value) >= 0.0


def test_portfolio_build_uses_gated_novelty():
    """Integration: build_opportunity_from_candidate applies gating to ERV."""
    g = _graph()
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
    cand = _candidate(tool="adaptive_partition_compare", action_id="a2")
    assessment = _assessment()
    components = {"novelty": WEIGHT_NOVELTY, "information_gap": 1.0}
    opp_gated = build_opportunity_from_candidate(
        cand,
        base_score=5.0,
        components=components,
        graph=g,
        assessment=assessment,
        branch_root_id="obs-root",
    )
    assert opp_gated.gated_novelty_component == 0.0
    assert opp_gated.novelty == WEIGHT_NOVELTY


def test_planner_weights_unchanged():
    from modules.edge_research.research_planner import WEIGHT_NOVELTY as PLANNER_NOVELTY

    assert PLANNER_NOVELTY == 2.0
    assert WEIGHT_NOVELTY_PORTFOLIO == 1.5


def test_production_isolation():
    src = inspect.getsource(__import__("modules.edge_research.research_novelty_valuation_bridge", fromlist=["x"]))
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in src


def test_bridge_version():
    assert RESEARCH_NOVELTY_VALUATION_BRIDGE_VERSION.startswith("research_novelty_valuation_bridge")
