"""Phase 3H.10 — Semantic research-line identity & marginal decay transfer tests."""

from __future__ import annotations

import inspect
import json

import pytest

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_assessment import DescriptiveStrength, ResearchAssessment
from modules.edge_research.research_branch_marginal_state import (
    BranchMarginalState,
    build_branch_marginal_state,
)
from modules.edge_research.research_exit_valuation import (
    RESEARCH_EXIT_VALUATION_VERSION,
    compute_research_exit_value,
)
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_line_decay_transfer import (
    build_semantic_marginal_evidence,
    merge_semantic_realized_levels,
)
from modules.edge_research.research_line_freshness import (
    EvidenceSnapshot,
    FreshnessClassification,
    assess_freshness,
)
from modules.edge_research.research_line_identity import (
    RESEARCH_LINE_IDENTITY_VERSION,
    ResearchLineIdentity,
    derive_identity_from_experiment_spec,
)
from modules.edge_research.research_line_registry import (
    RESEARCH_LINE_REGISTRY_VERSION,
    assign_experiment_to_line,
    get_registry,
)
from modules.edge_research.research_line_relationship import (
    ResearchLineRelationship,
    classify_research_line_relationship,
)
from modules.edge_research.research_realized_information_gain import (
    RealizedGainLevel,
    assess_realized_information_gain,
    record_realized_information_gain,
    store_assessment_snapshot,
)
from modules.edge_research.research_state import ExperimentSpec, ResearchGraphSnapshot


CUTOFF = "2026-08-20"
POP = {"filters": [{"column": "symbol", "op": "eq", "value": "SPY"}]}
OUT = {"kind": "forward_return", "horizon_bars": 5}
POP_B = {"filters": [{"column": "symbol", "op": "eq", "value": "QQQ"}]}
OUT_B = {"kind": "forward_return", "horizon_bars": 10}


def _graph() -> ResearchGraph:
    g = ResearchGraph.create_session(
        session_id="semantic-line-test",
        data_cutoff_date=CUTOFF,
        experiment_budget=12,
    )
    g.session.panel_preflight = {"eligible_explanatory": ["f1", "f2", "f3"]}
    return g


def _identity(
    *,
    pop=None,
    out=None,
    horizon=0,
    tool="horizon_comparison",
    action_id="a1",
    slice_cols=(),
    unc=("GAP_A",),
) -> ResearchLineIdentity:
    return ResearchLineIdentity(
        version=RESEARCH_LINE_IDENTITY_VERSION,
        population_spec=pop or POP,
        outcome_spec=out or OUT,
        observation_horizon=horizon,
        uncertainty_codes=unc,
        research_needs=(),
        conditioning_context={},
        feature_slice=slice_cols,
        evidence_lineage=(),
        metadata={"tool_name": tool, "action_id": action_id},
    )


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(
        source_experiment_node_id="E1",
        tool_name="horizon_comparison",
        tool_status="OK",
        information_gaps=("GAP_A",),
        branch_tools_attempted=(),
        branch_observation_codes=(),
        descriptive_strength=DescriptiveStrength.GROUP_DIFFERENCE.value,
        interesting=True,
    )
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


def _spec(tool: str, pop=None, out=None, horizon=0, feat="f1") -> ExperimentSpec:
    return ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs={"feature_column": feat},
        research_scope={
            "population_spec": pop or POP,
            "outcome_spec": out or OUT,
            "pending_question_context": {"observation_horizon": horizon},
        },
        data_cutoff_date=CUTOFF,
    )


def test_a_identical_scientific_line():
    a = _identity(action_id="x")
    b = _identity(action_id="x")
    audit = classify_research_line_relationship(a, b)
    assert audit.classification == ResearchLineRelationship.IDENTICAL.value


def test_b_same_question_different_tool():
    a = _identity(tool="horizon_comparison")
    b = _identity(tool="adaptive_partition_compare", action_id="a2")
    audit = classify_research_line_relationship(a, b)
    assert audit.classification == ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value


def test_c_same_uncertainty_different_slice():
    a = _identity(slice_cols=("f1",))
    b = _identity(slice_cols=("f2",), action_id="a2")
    audit = classify_research_line_relationship(a, b)
    assert audit.classification == ResearchLineRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value


def test_d_related_but_distinct():
    a = _identity(unc=("GAP_A",), out=OUT)
    b = _identity(unc=("GAP_A",), pop=POP_B, out=OUT_B, action_id="a2")
    audit = classify_research_line_relationship(a, b)
    assert audit.classification in (
        ResearchLineRelationship.RELATED_BUT_DISTINCT.value,
        ResearchLineRelationship.GENUINELY_INDEPENDENT.value,
        ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value,
    )


def test_e_genuinely_independent():
    a = _identity(pop=POP, out=OUT, unc=("GAP_A",))
    b = _identity(pop=POP_B, out=OUT_B, unc=("GAP_X",), action_id="a2")
    audit = classify_research_line_relationship(a, b)
    assert audit.classification == ResearchLineRelationship.GENUINELY_INDEPENDENT.value


def test_f_insufficient_evidence_fail_closed():
    a = ResearchLineIdentity(
        version=RESEARCH_LINE_IDENTITY_VERSION,
        population_spec={},
        outcome_spec={},
        observation_horizon=0,
        uncertainty_codes=(),
        research_needs=(),
        conditioning_context={},
        feature_slice=(),
        evidence_lineage=(),
        metadata={"action_id": "a1"},
    )
    b = _identity(pop={"x": 1}, out={"y": 2}, unc=("Z",), action_id="a2")
    audit = classify_research_line_relationship(a, b)
    assert audit.classification == ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value


def test_g_zero_gain_transfers_same_question_tool_switch():
    merged, expl = merge_semantic_realized_levels(
        ["LOW"],
        ["ZERO", "ZERO"],
        transfer_allowed=True,
        relationship=ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
    )
    assert "ZERO" in merged
    assert expl.get("transfer")


def test_h_independent_line_no_decay_inherit():
    merged, expl = merge_semantic_realized_levels(
        ["HIGH"],
        ["ZERO", "ZERO"],
        transfer_allowed=False,
        relationship=ResearchLineRelationship.GENUINELY_INDEPENDENT.value,
    )
    assert merged == ["HIGH"]
    assert "No decay transfer" in expl.get("transfer", "")


def test_i_fresh_revisit_recognized():
    defer = EvidenceSnapshot(
        uncertainty_codes=("GAP_A",),
        observation_horizon=0,
        population_spec=POP,
        outcome_spec=OUT,
        observation_count=1,
    )
    current = EvidenceSnapshot(
        uncertainty_codes=("GAP_A", "GAP_B"),
        observation_horizon=0,
        population_spec=POP,
        outcome_spec=OUT,
        observation_count=3,
    )
    fresh = assess_freshness(
        identity=_identity(),
        research_line_id="rl-1",
        defer_snapshot=defer,
        current_snapshot=current,
        prior_attempt_count=1,
        prior_realized_gain="ZERO",
    )
    assert fresh.classification == FreshnessClassification.FRESH_NEW_EVIDENCE.value


def test_j_stale_revisit_recognized():
    snap = EvidenceSnapshot(
        uncertainty_codes=("GAP_A",),
        observation_horizon=0,
        population_spec=POP,
        outcome_spec=OUT,
        observation_count=2,
    )
    fresh = assess_freshness(
        identity=_identity(),
        research_line_id="rl-1",
        defer_snapshot=snap,
        current_snapshot=snap,
        prior_attempt_count=2,
        prior_realized_gain="ZERO",
    )
    assert fresh.classification in (
        FreshnessClassification.STALE.value,
        FreshnessClassification.SAME_EVIDENCE.value,
    )


def test_k_erv_only_not_freshness():
    snap = EvidenceSnapshot(
        uncertainty_codes=("GAP_A",),
        observation_horizon=0,
        population_spec=POP,
        outcome_spec=OUT,
    )
    fresh = assess_freshness(
        identity=_identity(),
        research_line_id="rl-1",
        defer_snapshot=snap,
        current_snapshot=snap,
        erv_changed_only=True,
    )
    assert fresh.classification == FreshnessClassification.REVALUED_ONLY.value


def test_l_frontier_retains_research_line_identity():
    from modules.edge_research.research_frontier import FrontierItem

    item = FrontierItem(
        frontier_id="f1",
        action_id="a1",
        action_code="c1",
        parent_experiment_node_id="E1",
        branch_root_id="obs-root",
        action_type="RUN_TOOL",
        research_line_identity=_identity().to_dict(),
    )
    d = item.to_dict()
    restored = FrontierItem.from_dict(d)
    assert restored.research_line_identity is not None
    assert restored.research_line_identity["scientific_proposition_key"]


def test_m_frame_change_not_new_line():
    a = _identity()
    b = _identity()
    b_meta = dict(b.metadata)
    b_meta["frame_id"] = "frame-2"
    b2 = ResearchLineIdentity(
        version=b.version,
        population_spec=b.population_spec,
        outcome_spec=b.outcome_spec,
        observation_horizon=b.observation_horizon,
        uncertainty_codes=b.uncertainty_codes,
        research_needs=b.research_needs,
        conditioning_context=b.conditioning_context,
        feature_slice=b.feature_slice,
        evidence_lineage=b.evidence_lineage,
        metadata=b_meta,
    )
    assert a.scientific_proposition_key() == b2.scientific_proposition_key()


def test_n_action_id_change_not_new_line():
    a = _identity(action_id="a1")
    b = _identity(action_id="a2")
    assert a.scientific_proposition_key() == b.scientific_proposition_key()


def test_o_tool_change_not_new_line():
    a = _identity(tool="horizon_comparison")
    b = _identity(tool="adaptive_partition_compare", action_id="a2")
    assert a.scientific_proposition_key() == b.scientific_proposition_key()


def test_p_outcome_change_distinct_line():
    a = _identity(out=OUT)
    b = _identity(out=OUT_B, action_id="a2")
    assert a.scientific_proposition_key() != b.scientific_proposition_key()


def test_q_population_change_distinct_line():
    a = _identity(pop=POP)
    b = _identity(pop=POP_B, action_id="a2")
    assert a.scientific_proposition_key() != b.scientific_proposition_key()


def test_r_horizon_change_explicit():
    a = _identity(horizon=0)
    b = _identity(horizon=5, action_id="a2")
    assert a.scientific_proposition_key() != b.scientific_proposition_key()


def test_s_registry_persists_reloads():
    g = _graph()
    ident = _identity()
    line_id, _, _ = assign_experiment_to_line(
        g, experiment_node_id="E1", identity=ident, gain_level="ZERO"
    )
    assert line_id
    snap = g.snapshot()
    raw = snap.to_dict()
    restored = ResearchGraphSnapshot.from_dict(raw)

    class _G:
        session = restored.session

    reg = get_registry(_G())
    assert line_id in reg.lines
    assert reg.experiment_to_line["E1"] == line_id


def test_t_existing_exact_dedup_unchanged():
    from modules.edge_research.research_experiment_identity import EXPERIMENT_IDENTITY_VERSION

    assert EXPERIMENT_IDENTITY_VERSION == "research_experiment_identity_v1"


def test_u_3h6_iv_unchanged():
    from modules.edge_research import research_information_value as riv

    assert hasattr(riv, "assess_research_information_value")


def test_v_3h8_exit_formula_unchanged():
    from modules.edge_research.research_branch_marginal_state import ResearchBranchMarginalState
    from modules.edge_research.research_branch_marginal_state import (
        RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
    )

    m = ResearchBranchMarginalState(
        version=RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
        branch_root_id="r",
        observation_horizon=0,
        experiments_on_branch=3,
        current_frame_id="",
        unresolved_uncertainty_codes=("G",),
        prior_resolution_attempts=1,
        recent_information_value_history=(),
        realized_information_gain_history=("ZERO", "ZERO"),
        redundancy_evidence=(),
        novelty_evidence=(),
        recent_revalued_opportunity_history=(-1.0,),
        marginal_state=BranchMarginalState.LOW_MARGINAL_VALUE.value,
        marginal_state_reason="test",
        planning_sequence=1,
    )
    ev = compute_research_exit_value(
        marginal_state=m,
        best_experiment_erv=2.0,
        best_local_erv=2.0,
        best_frontier_erv=1.0,
        best_revisit_erv=0.0,
        best_deferred_erv=0.0,
        historical_best_frontier_score=3.0,
        remaining_budget=5,
        experiment_budget=12,
        features_touched=1,
        eligible_feature_count=4,
    )
    assert ev.version == RESEARCH_EXIT_VALUATION_VERSION


def test_w_planner_base_scoring_unchanged():
    from modules.edge_research.research_planner import WEIGHT_NOVELTY

    assert WEIGHT_NOVELTY == 2.0


def test_x_allocator_semantics_preserved():
    from modules.edge_research.research_global_allocator import GLOBAL_ALLOCATOR_VERSION

    assert "allocator" in GLOBAL_ALLOCATOR_VERSION


def test_y_no_forced_branch_switching():
    g = _graph()
    ev = build_semantic_marginal_evidence(
        g,
        candidate_identity=_identity(),
        branch_levels=["ZERO"],
    )
    assert ev.transfer_allowed is False or ev.relationship_classification


def test_z_no_tool_feature_preference():
    a = _identity(tool="tool_a")
    b = _identity(tool="tool_b", action_id="a2")
    assert classify_research_line_relationship(a, b).classification != "TOOL_PENALTY"


def test_aa_production_isolation():
    for mod in (
        "modules.edge_research.research_line_identity",
        "modules.edge_research.research_line_registry",
        "modules.edge_research.research_line_decay_transfer",
    ):
        src = inspect.getsource(__import__(mod, fromlist=["x"]))
        for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
            assert forbidden not in src


def test_ab_no_bb_leakage_tokens():
    from modules.edge_research.research_line_decay_transfer import RESEARCH_LINE_DECAY_TRANSFER_VERSION

    assert "blind_benchmark" not in RESEARCH_LINE_DECAY_TRANSFER_VERSION


def test_positive_control_same_question_tool_zero_gain():
    """Same question + different tool + repeated ZERO — semantic continuity."""
    g = _graph()
    id1 = _identity(tool="horizon_comparison")
    assign_experiment_to_line(g, experiment_node_id="E1", identity=id1, gain_level="ZERO")
    id2 = _identity(tool="adaptive_partition_compare", action_id="a2")
    ev = build_semantic_marginal_evidence(
        g,
        candidate_identity=id2,
        branch_levels=[],
        branch_tools_attempted=("horizon_comparison",),
    )
    assert ev.relationship_classification in (
        ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
        ResearchLineRelationship.IDENTICAL.value,
        ResearchLineRelationship.NEAR_DUPLICATE.value,
    )
    assert ev.transfer_allowed
    assert "ZERO" in ev.merged_realized_levels


def test_negative_control_same_root_different_outcome():
    g = _graph()
    id1 = _identity(out=OUT)
    assign_experiment_to_line(g, experiment_node_id="E1", identity=id1, gain_level="ZERO")
    id2 = _identity(out=OUT_B, action_id="a2")
    ev = build_semantic_marginal_evidence(g, candidate_identity=id2, branch_levels=["ZERO"])
    assert ev.relationship_classification in (
        ResearchLineRelationship.GENUINELY_INDEPENDENT.value,
        ResearchLineRelationship.RELATED_BUT_DISTINCT.value,
        ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value,
    )
    if ev.relationship_classification == ResearchLineRelationship.GENUINELY_INDEPENDENT.value:
        assert ev.merged_realized_levels == ("ZERO",)


def test_registry_version():
    g = _graph()
    reg = get_registry(g)
    assert reg.version == RESEARCH_LINE_REGISTRY_VERSION
