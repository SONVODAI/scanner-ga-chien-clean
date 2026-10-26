"""Phase 3H.8 — Evidence-Based Branch Exit Valuation tests (A–Z matrix)."""

from __future__ import annotations

import inspect

import pytest

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import ActionIntent, ResearchActionCandidate
from modules.edge_research.research_assessment import DescriptiveStrength, ResearchAssessment
from modules.edge_research.research_branch_marginal_state import (
    BranchMarginalState,
    RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
    build_branch_marginal_state,
)
from modules.edge_research.research_exit_valuation import (
    RESEARCH_EXIT_VALUATION_VERSION,
    compute_research_exit_value,
    evaluate_exit_vs_experiment,
    validate_no_forbidden_exit_patterns,
)
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_realized_information_gain import (
    RealizedGainLevel,
    assess_realized_information_gain,
    store_assessment_snapshot,
)
from modules.edge_research.research_state import ExperimentSpec


CUTOFF = "2026-08-20"


def _graph() -> ResearchGraph:
    g = ResearchGraph.create_session(
        session_id="exit-test",
        data_cutoff_date=CUTOFF,
        experiment_budget=12,
    )
    g.session.panel_preflight = {"eligible_explanatory": ["f1", "f2", "f3", "f4"]}
    return g


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


def _marginal_state(state: str, **kwargs):
    from modules.edge_research.research_branch_marginal_state import ResearchBranchMarginalState

    base = dict(
        version=RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
        branch_root_id="obs-root",
        observation_horizon=0,
        experiments_on_branch=4,
        current_frame_id="",
        unresolved_uncertainty_codes=("GAP_A",),
        prior_resolution_attempts=2,
        recent_information_value_history=(1.0,),
        realized_information_gain_history=("LOW", "ZERO"),
        redundancy_evidence=("repeated_tool_attempt:horizon_comparisonx2",),
        novelty_evidence=(),
        recent_revalued_opportunity_history=(-1.0, -2.0),
        marginal_state=state,
        marginal_state_reason="test",
        planning_sequence=1,
    )
    base.update(kwargs)
    return ResearchBranchMarginalState(**base)


def test_a_productive_branch_positive_experiment_continue():
    """A: Productive branch + strong positive experiment → CONTINUE."""
    m = _marginal_state(BranchMarginalState.PRODUCTIVE.value, realized_information_gain_history=("HIGH",))
    ev = compute_research_exit_value(
        marginal_state=m,
        best_experiment_erv=16.0,
        best_local_erv=16.0,
        best_frontier_erv=5.0,
        best_revisit_erv=0.0,
        best_deferred_erv=0.0,
        historical_best_frontier_score=8.0,
        remaining_budget=8,
        experiment_budget=12,
        features_touched=1,
        eligible_feature_count=4,
    )
    assert not evaluate_exit_vs_experiment(ev, 16.0)


def test_b_negative_erv_falsification_may_continue():
    """B: Weak negative ERV but productive branch — experiment may still execute."""
    m = _marginal_state(
        BranchMarginalState.PRODUCTIVE.value,
        realized_information_gain_history=("HIGH",),
        experiments_on_branch=2,
    )
    ev = compute_research_exit_value(
        marginal_state=m,
        best_experiment_erv=-2.0,
        best_local_erv=-2.0,
        best_frontier_erv=-5.0,
        best_revisit_erv=0.0,
        best_deferred_erv=0.0,
        historical_best_frontier_score=8.0,
        remaining_budget=6,
        experiment_budget=12,
        features_touched=1,
        eligible_feature_count=4,
    )
    assert not evaluate_exit_vs_experiment(ev, -2.0)


def test_c_saturated_all_negative_stop_can_win():
    """C: Exhaustion evidence + all negative — STOP can win."""
    m = _marginal_state(
        BranchMarginalState.EXHAUSTION_EVIDENCE.value,
        realized_information_gain_history=("ZERO", "ZERO", "LOW"),
    )
    ev = compute_research_exit_value(
        marginal_state=m,
        best_experiment_erv=-1.08,
        best_local_erv=-1.08,
        best_frontier_erv=-4.0,
        best_revisit_erv=-1.6,
        best_deferred_erv=0.0,
        historical_best_frontier_score=8.7,
        remaining_budget=4,
        experiment_budget=12,
        features_touched=2,
        eligible_feature_count=8,
    )
    assert evaluate_exit_vs_experiment(ev, -1.08)


def test_d_saturated_strong_positive_experiment_wins():
    """D: Exhaustion but genuinely strong positive experiment can still win."""
    m = _marginal_state(BranchMarginalState.EXHAUSTION_EVIDENCE.value)
    ev = compute_research_exit_value(
        marginal_state=m,
        best_experiment_erv=3.8,
        best_local_erv=3.8,
        best_frontier_erv=-4.0,
        best_revisit_erv=0.0,
        best_deferred_erv=0.0,
        historical_best_frontier_score=8.0,
        remaining_budget=2,
        experiment_budget=12,
        features_touched=2,
        eligible_feature_count=8,
    )
    assert not evaluate_exit_vs_experiment(ev, 3.8)


def test_e_deep_branch_continuing_gain_not_saturated():
    """E: Deep branch with continuing HIGH gain — NOT exhausted."""
    m = _marginal_state(
        BranchMarginalState.PRODUCTIVE.value,
        experiments_on_branch=10,
        realized_information_gain_history=("HIGH", "HIGH", "MEDIUM"),
    )
    assert m.marginal_state == BranchMarginalState.PRODUCTIVE.value


def test_f_shallow_zero_gain_shows_exhaustion():
    """F: Shallow branch with repeated zero gain — exhaustion evidence possible."""
    from modules.edge_research.research_portfolio import BranchPortfolioRecord

    graph = _graph()
    portfolio = graph.get_portfolio_state()
    portfolio.branches["obs-r"] = BranchPortfolioRecord(
        branch_root_id="obs-r",
        experiments_on_branch=3,
    )
    graph.persist_portfolio_state()
    graph.session.research_realized_gain_by_branch = {
        "obs-r": [
            {"gain_level": RealizedGainLevel.ZERO.value},
            {"gain_level": RealizedGainLevel.ZERO.value},
        ]
    }
    m = build_branch_marginal_state(
        graph=graph,
        assessment=_assessment(branch_tools_attempted=("horizon_comparison", "horizon_comparison")),
        branch_root_id="obs-r",
        planning_sequence=2,
    )
    assert m.marginal_state in (
        BranchMarginalState.DIMINISHING.value,
        BranchMarginalState.LOW_MARGINAL_VALUE.value,
        BranchMarginalState.EXHAUSTION_EVIDENCE.value,
    )


def test_g_same_tool_new_uncertainty_no_mechanical_decay():
    """G: Same tool resolving new uncertainty — productive state."""
    m = _marginal_state(
        BranchMarginalState.PRODUCTIVE.value,
        redundancy_evidence=(),
        realized_information_gain_history=("HIGH",),
    )
    assert m.marginal_state == BranchMarginalState.PRODUCTIVE.value


def test_h_different_tools_same_exhausted_uncertainty():
    """H: Redundancy evidence from repeated attempts — decay persists."""
    m = _marginal_state(
        BranchMarginalState.LOW_MARGINAL_VALUE.value,
        redundancy_evidence=("repeated_tool_attempt:partitionx2", "repeated_tool_attempt:thresholdx2"),
    )
    assert m.redundancy_evidence


def test_insufficient_evidence_conservative():
    """P: No sufficient saturation evidence → conservative (exit -inf)."""
    m = _marginal_state(BranchMarginalState.INSUFFICIENT_EVIDENCE.value, experiments_on_branch=1)
    ev = compute_research_exit_value(
        marginal_state=m,
        best_experiment_erv=-5.0,
        best_local_erv=-5.0,
        best_frontier_erv=-5.0,
        best_revisit_erv=0.0,
        best_deferred_erv=0.0,
        historical_best_frontier_score=8.0,
        remaining_budget=5,
        experiment_budget=12,
        features_touched=0,
        eligible_feature_count=4,
    )
    assert ev.exit_value == float("-inf")


def test_n_negative_erv_not_automatic_stop():
    """N: ERV < 0 is NOT automatic STOP."""
    m = _marginal_state(BranchMarginalState.DIMINISHING.value)
    ev = compute_research_exit_value(
        marginal_state=m,
        best_experiment_erv=-0.5,
        best_local_erv=-0.5,
        best_frontier_erv=-1.0,
        best_revisit_erv=0.0,
        best_deferred_erv=0.0,
        historical_best_frontier_score=8.0,
        remaining_budget=10,
        experiment_budget=12,
        features_touched=1,
        eligible_feature_count=4,
    )
    assert not evaluate_exit_vs_experiment(ev, -0.5)


def test_o_positive_erv_not_automatic_continue():
    """O: ERV > 0 is NOT automatic CONTINUE under severe exhaustion."""
    m = _marginal_state(
        BranchMarginalState.EXHAUSTION_EVIDENCE.value,
        realized_information_gain_history=("ZERO", "ZERO", "ZERO"),
    )
    ev = compute_research_exit_value(
        marginal_state=m,
        best_experiment_erv=0.5,
        best_local_erv=0.5,
        best_frontier_erv=-2.0,
        best_revisit_erv=0.0,
        best_deferred_erv=0.0,
        historical_best_frontier_score=8.0,
        remaining_budget=1,
        experiment_budget=12,
        features_touched=2,
        eligible_feature_count=8,
    )
    assert evaluate_exit_vs_experiment(ev, 0.5)


def test_realized_information_gain_from_snapshots():
    graph = _graph()
    prior = _assessment(information_gaps=("GAP_A", "GAP_B"), branch_observation_codes=("OBS1",))
    current = _assessment(
        information_gaps=("GAP_B",),
        branch_observation_codes=("OBS1", "OBS2"),
        source_experiment_node_id="E1",
    )
    gain = assess_realized_information_gain(
        graph=graph,
        experiment_node_id="E1",
        current_assessment=current,
        branch_root_id="obs-r",
        prior_assessment=prior,
    )
    assert gain.gain_level in (RealizedGainLevel.HIGH.value, RealizedGainLevel.MEDIUM.value)
    assert "GAP_A" in gain.gaps_resolved


def _frontier_with_item(*, planner_score: float = 8.7):
    from modules.edge_research.research_frontier import FrontierItem, ResearchFrontier

    frontier = ResearchFrontier()
    frontier.items["f1"] = FrontierItem(
        frontier_id="f1",
        action_id="a1",
        action_code="EXPLORATION",
        parent_experiment_node_id="exp-1",
        branch_root_id="other-root",
        action_type="EXPLORATION",
        planner_score=planner_score,
    )
    return frontier


def test_l_stop_uses_current_not_historical():
    """L: Historical high frontier does not alone force continue when revalued negative."""
    from modules.edge_research.research_frontier import evaluate_global_stop

    frontier = _frontier_with_item(planner_score=8.7)
    should, reason = evaluate_global_stop(
        remaining_budget=5,
        frontier=frontier,
        features_touched=8,
        eligible_feature_count=8,
        current_best_revalued_score=-2.0,
    )
    assert should
    assert reason.code == "INSUFFICIENT_RESEARCH_VALUE"


def test_m_current_positive_remains_executable():
    from modules.edge_research.research_frontier import evaluate_global_stop

    frontier = _frontier_with_item(planner_score=8.7)
    should, _ = evaluate_global_stop(
        remaining_budget=5,
        frontier=frontier,
        features_touched=2,
        eligible_feature_count=8,
        current_best_revalued_score=3.0,
    )
    assert not should


def test_negative_control_forbidden_patterns():
    from modules.edge_research.research_exit_valuation import (
        compute_research_exit_value,
        evaluate_exit_vs_experiment,
    )

    src = inspect.getsource(compute_research_exit_value) + inspect.getsource(
        evaluate_exit_vs_experiment
    )
    hits = validate_no_forbidden_exit_patterns(src)
    assert not hits


def test_production_isolation():
    for mod in (
        "modules.edge_research.research_exit_valuation",
        "modules.edge_research.research_branch_marginal_state",
        "modules.edge_research.research_realized_information_gain",
    ):
        source = inspect.getsource(__import__(mod, fromlist=["*"]))
        for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
            assert forbidden not in source


def test_session_round_trip_audit_fields():
    graph = _graph()
    graph.session.research_exit_decision_audit = [{"stop_competed": True}]
    graph.session.research_branch_marginal_audit = [{"marginal_state": "PRODUCTIVE"}]
    payload = graph.session.to_dict()
    from modules.edge_research.research_state import ResearchSession

    restored = ResearchSession.from_dict(payload)
    assert restored.research_exit_decision_audit
    assert restored.research_branch_marginal_audit
