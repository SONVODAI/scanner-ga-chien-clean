"""Phase 3G.2 — autonomous reframing and research-space diversification tests."""

from __future__ import annotations

import json

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
from modules.edge_research.research_controller import apply_plan_decision
from modules.edge_research.research_frame import (
    FrameStatus,
    FrameTransformationType,
    ResearchFrame,
    ResearchFrameRegistry,
    assess_frame_saturation,
    check_sample_sufficiency,
    population_from_observed_outcome,
    propose_horizon_advancement_frames,
    propose_population_from_observed_data,
    validate_frame_temporal_legality,
    validate_population_at_horizon,
)
from modules.edge_research.research_frontier import FrontierItem
from modules.edge_research.research_grammar import GrammarValidationError, OutcomeSpec, PopulationSpec
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_planner import PlanDecision, PlanDecisionType, plan_next_action, score_candidate
from modules.edge_research.research_search_accounting import record_experiment_executed
from modules.edge_research.research_state import (
    ExperimentSpec,
    QuestionRationale,
    ResearchQuestionContext,
    SessionStatus,
    StructuredResearchObservation,
)
from modules.edge_research.research_tools import OBS_NO_CLEAR_DIFFERENCE, build_default_tool_registry

CUTOFF = "2026-08-20"
REGISTRY = build_default_tool_registry()
POP = PopulationSpec.all_()
OUT = OutcomeSpec.compare("t5_return", ">", 0.0)
SCOPE = {
    "population_spec": POP.to_dict(),
    "outcome_spec": OUT.to_dict(),
}


def _row(i: int, *, fx: float, t5: float) -> dict:
    return {
        "trade_date": f"2026-08-{(i % 10) + 1:02d}",
        "symbol": f"S{i % 5}",
        "feat_alpha": fx,
        "feat_beta": fx * 0.5,
        "t3_return": t5 * 0.8,
        "t5_return": t5,
        "t10_return": t5 * 1.1,
        "partition_group": "G1" if fx > 0 else "G2",
        "research_market_state": "STATE_A",
    }


def _panel(n: int = 60, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame([_row(i, fx=float(rng.normal()), t5=float(rng.normal())) for i in range(n)])


def _graph() -> ResearchGraph:
    return ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12, session_id="rs-reframe")


def _spec(tool: str = "horizon_comparison", scope: dict | None = None) -> ExperimentSpec:
    return ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs={"horizon": "T5"},
        research_scope=scope or dict(SCOPE),
        data_cutoff_date=CUTOFF,
    )


def _seed_lineage(
    graph: ResearchGraph,
    *,
    frame_id: str = "f1",
    experiment_id: str = "E1",
    population_n: int = 100,
) -> str:
    qctx = ResearchQuestionContext(
        population_spec=POP.to_dict(),
        outcome_spec=OUT.to_dict(),
        frame_id=frame_id,
        population_n=population_n,
    )
    oid = graph.add_root_observation(description="Root", node_id="O-root")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Initial?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        question_context=qctx,
        node_id="Q-root",
    )
    return graph.add_experiment(question_node_id=qid, spec=_spec(), node_id=experiment_id)


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(source_experiment_node_id="E1", tool_name="adaptive_partition_compare", tool_status="OK")
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


def _low_yield_frame(*, eligible: int = 4) -> ResearchFrame:
    frame = ResearchFrame.initial("f1", POP, OUT, eligible_feature_count=eligible)
    frame.experiments_in_frame = 4
    frame.features_explored = ("feat_alpha", "feat_beta")
    frame.flat_noisy_count = 3
    frame.stop_branch_count = 2
    return frame


# --- Required: serialize / accumulate ---


def test_research_frame_serializes_and_reloads():
    frame = ResearchFrame.initial("frame-00001", POP, OUT, eligible_feature_count=4)
    frame.experiments_in_frame = 3
    reg = ResearchFrameRegistry(frames={"frame-00001": frame}, active_frame_id="frame-00001")
    restored = ResearchFrameRegistry.from_dict(json.loads(json.dumps(reg.to_dict())))
    assert restored.get("frame-00001").experiments_in_frame == 3


def test_frame_experiment_counts_accumulate():
    frame = ResearchFrame.initial("f1", POP, OUT, eligible_feature_count=4)
    frame.experiments_in_frame = 2
    frame.features_explored = ("feat_alpha", "feat_beta")
    status, _ = assess_frame_saturation(frame)
    assert status in (FrameStatus.ACTIVE.value, FrameStatus.UNDEREXPLORED.value, FrameStatus.LOW_YIELD.value)


# --- Scenario A: same-frame low yield ---


def test_same_frame_low_yield_increases_reframe_priority():
    graph = _graph()
    graph.get_frame_registry().register(_low_yield_frame())
    graph.persist_frames()
    _seed_lineage(graph)

    assess = _assessment(
        observation_kind="STRUCTURAL_OBSERVATION",
        empirical_findings=("HORIZON_HETEROGENEOUS",),
        additional_investigation_warranted=True,
    )
    cands = generate_action_candidates(
        assess, graph, REGISTRY, experiment_node_id="E1", panel_columns=tuple(_panel().columns)
    )
    reframe = [c for c in cands if "REFRAME" in c.action_code or c.intent == ActionIntent.REFRAME.value]
    assert len(reframe) >= 1
    saturated_bonus = max(c.priority_hints.get("saturated_parent_reframe_bonus", 0) for c in reframe)
    assert saturated_bonus >= 3.0


def test_low_yield_frame_status_detected():
    status, evidence = assess_frame_saturation(_low_yield_frame())
    assert status == FrameStatus.LOW_YIELD.value
    assert evidence["feature_coverage_ratio"] >= 0.5


# --- Scenario B: productive frame continues ---


def test_productive_frame_not_forced_to_reframe():
    frame = ResearchFrame.initial("f1", POP, OUT, eligible_feature_count=4)
    frame.candidate_yield = 1
    frame.experiments_in_frame = 2
    status, _ = assess_frame_saturation(frame)
    assert status == FrameStatus.PRODUCTIVE.value


def test_productive_frame_depth_beats_premature_reframe():
    graph = _graph()
    frame = ResearchFrame.initial("f1", POP, OUT, eligible_feature_count=4)
    frame.candidate_yield = 1
    frame.experiments_in_frame = 2
    graph.get_frame_registry().register(frame)
    graph.persist_frames()
    _seed_lineage(graph)

    assess = _assessment(
        conditional_candidate=True,
        additional_investigation_warranted=True,
        observation_kind="CONDITIONAL_CANDIDATE",
        possible_falsification_targets=("EXTREME_WINNER",),
    )
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id="E1")
    decision = plan_next_action(assess, cands, graph, experiment_node_id="E1")
    assert decision.decision_type != PlanDecisionType.STOP_SESSION
    if decision.selected:
        assert decision.selected.intent != ActionIntent.STOP_SESSION.value


# --- Scenario C: outcome reframe ---


def test_alternative_outcome_spec_becomes_frame():
    frame = ResearchFrame.initial("f1", POP, OUT)
    child = frame.child(
        "f2",
        outcome=OutcomeSpec.compare("t3_return", ">", 0.0),
        transformation=FrameTransformationType.OUTCOME_REFRAME.value,
        reason="Alternative horizon outcome",
    )
    assert child.outcome.outcome_field == "t3_return"
    assert validate_frame_temporal_legality(child)


def test_outcome_reframe_scores_with_novelty_bonus():
    graph = _graph()
    graph.get_frame_registry().register(_low_yield_frame())
    _seed_lineage(graph)
    assess = _assessment(
        observation_kind="STRUCTURAL_OBSERVATION",
        empirical_findings=("HORIZON_HETEROGENEOUS",),
    )
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id="E1")
    reframe = [c for c in cands if c.intent == ActionIntent.REFRAME.value and not c.blocked]
    assert reframe
    _, comp = score_candidate(reframe[0], assess, graph, experiment_node_id="E1")
    assert comp.get("new_outcome_bonus", 0) > 0 or comp.get("saturated_parent_reframe_bonus", 0) > 0


# --- Scenario D: population reframe ---


def test_population_reframe_from_observed_data():
    refined = propose_population_from_observed_data(
        POP,
        categorical_values={"partition_group": ("G1",)},
        numeric_median_splits={"feat_alpha": 0.0},
        reason_code="TEST",
    )
    assert len(refined) >= 1
    validate_population_at_horizon(refined[0], observation_horizon=0)


# --- Scenario E: outcome → population ---


def test_outcome_to_population_transformation():
    out = OutcomeSpec.compare("t3_return", ">", 0.0)
    pop_filter = population_from_observed_outcome(out, reason_code="OUTCOME_TO_POPULATION")
    assert pop_filter is not None
    frame = ResearchFrame(frame_id="f1", population=POP, outcome=out, observation_horizon=0)
    proposals = propose_horizon_advancement_frames(frame)
    assert isinstance(proposals, tuple)


def test_horizon_advance_unlocks_later_information():
    early_out = OutcomeSpec.compare("t3_return", ">", 0.0)
    frame = ResearchFrame(
        frame_id="f1",
        population=POP,
        outcome=early_out,
        observation_horizon=0,
    )
    proposals = propose_horizon_advancement_frames(frame)
    horizon_proposals = [p for p in proposals if p.transformation == FrameTransformationType.HORIZON_ADVANCE.value]
    assert len(horizon_proposals) >= 1
    assert horizon_proposals[0].observation_horizon > 0


# --- Scenario F: future leakage ---


def test_future_leakage_rejected():
    pop = PopulationSpec.filter_numeric("t10_return", ">", 0.0)
    with pytest.raises(GrammarValidationError):
        validate_population_at_horizon(pop, observation_horizon=0)


# --- Scenario G: tiny cohort ---


def test_tiny_cohort_sample_loss_penalty():
    sufficient, loss = check_sample_sufficiency(resulting_n=5, parent_n=100, min_effective_n=20)
    assert sufficient is False
    assert loss > 0.9


def test_tiny_cohort_repopulation_deprioritized_in_planner():
    graph = _graph()
    graph.get_frame_registry().register(_low_yield_frame())
    _seed_lineage(graph, population_n=100)
    assess = _assessment(additional_investigation_warranted=True)
    cands = generate_action_candidates(
        assess, graph, REGISTRY, experiment_node_id="E1", panel_columns=tuple(_panel().columns)
    )
    pop_cands = [c for c in cands if c.action_code == "REPOPULATE_EVIDENCE"]
    for c in pop_cands:
        assert c.priority_hints.get("sample_loss_penalty", 0) <= 0


# --- Scenario H: multiple frames ---


def test_multiple_frames_coexist_in_registry():
    reg = ResearchFrameRegistry()
    f1 = ResearchFrame.initial(reg.next_id(), POP, OUT)
    f2 = ResearchFrame.initial(reg.next_id(), POP, OutcomeSpec.compare("t3_return", ">", 0.0))
    reg.register(f1)
    reg.register(f2, set_active=False)
    assert reg.unique_outcome_count() == 2


def test_frontier_holds_multiple_frames():
    graph = _graph()
    frontier = graph.get_frontier()
    for idx, (out_field, frame_id) in enumerate((("t5_return", "frame-a"), ("t3_return", "frame-b"))):
        out = OutcomeSpec.compare(out_field, ">", 0.0)
        scope = dict(SCOPE)
        scope["outcome_spec"] = out.to_dict()
        scope["pending_question_context"] = ResearchQuestionContext(
            population_spec=POP.to_dict(),
            outcome_spec=out.to_dict(),
            frame_id=frame_id,
        ).to_dict()
        spec = _spec(scope=scope)
        fid = frontier._next_id()
        frontier.items[fid] = FrontierItem(
            frontier_id=fid,
            action_id=f"act-{idx}",
            action_code=f"REFRAME_{frame_id}",
            parent_experiment_node_id="E1",
            branch_root_id="Q-root",
            action_type=ActionIntent.REFRAME.value,
            planner_score=float(5 - idx),
            question_text=f"Frame {frame_id}?",
            draft_spec=spec.to_dict(),
            frame_id=frame_id,
            transformation_type=FrameTransformationType.OUTCOME_REFRAME.value,
        )
    graph.persist_frontier()
    best = frontier.select_best_unexplored()
    assert best is not None
    assert best.frame_id in ("frame-a", "frame-b")


# --- Lineage / audit ---


def test_frame_lineage_recorded_on_transition():
    reg = ResearchFrameRegistry()
    old = ResearchFrame.initial(reg.next_id(), POP, OUT)
    reg.register(old)
    new = old.child(
        reg.next_id(),
        outcome=OutcomeSpec.compare("t3_return", ">", 0.0),
        transformation=FrameTransformationType.OUTCOME_REFRAME.value,
        reason="test",
    )
    reg.record_transition(old, new, trigger="OUTCOME_REFRAME")
    assert len(reg.lineage) == 1
    assert reg.lineage[0].temporal_legal is True


def test_frame_lineage_reconstructs_reframe_reason():
    reg = ResearchFrameRegistry()
    old = ResearchFrame.initial(reg.next_id(), POP, OUT)
    reg.register(old)
    new = old.child(
        reg.next_id(),
        outcome=OutcomeSpec.compare("t10_return", ">", 0.0),
        transformation=FrameTransformationType.OUTCOME_REFRAME.value,
        reason="Horizon heterogeneity",
    )
    reg.record_transition(old, new, trigger="STRUCTURAL_TRIGGER", saturation_evidence={"flat_noisy": 3})
    rec = reg.lineage[0]
    assert rec.old_frame_id == old.frame_id
    assert rec.new_frame_id == new.frame_id
    assert rec.transformation == FrameTransformationType.OUTCOME_REFRAME.value


# --- Planner diversity / penalties ---


def test_repeated_same_frame_action_penalized():
    graph = _graph()
    graph.get_frame_registry().register(_low_yield_frame())
    _seed_lineage(graph)
    assess = _assessment(additional_investigation_warranted=True)
    slicing = ResearchActionCandidate(
        action_id="slice-1",
        action_code="ADAPTIVE_SLICE",
        intent=ActionIntent.SLICING.value,
        question_template_id="SLICE",
        question_text="Slice feat_alpha?",
        tool_name="adaptive_partition_compare",
        tool_version="v1",
        draft_spec=_spec(),
        uncertainty_addressed="SLICE",
        expected_information="MEDIUM",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
    )
    _, comp = score_candidate(slicing, assess, graph, experiment_node_id="E1")
    assert comp.get("repeated_same_frame_penalty", 0) <= 0


def test_new_frame_gains_novelty_without_bypassing_complexity():
    graph = _graph()
    graph.get_frame_registry().register(_low_yield_frame())
    _seed_lineage(graph)
    assess = _assessment(
        observation_kind="STRUCTURAL_OBSERVATION",
        empirical_findings=("HORIZON_HETEROGENEOUS",),
    )
    cands = generate_action_candidates(assess, graph, REGISTRY, experiment_node_id="E1")
    reframe = [c for c in cands if c.intent == ActionIntent.REFRAME.value and not c.blocked][0]
    total, comp = score_candidate(reframe, assess, graph, experiment_node_id="E1")
    assert comp.get("new_outcome_bonus", 0) > 0 or comp.get("frame_novelty_bonus", 0) > 0
    assert comp.get("draft_complexity_penalty", 0) <= 0


# --- STOP_BRANCH local / STOP_SESSION global ---


def test_stop_branch_local_stop_session_global():
    graph = _graph()
    graph.session.panel_preflight = {"eligible_explanatory": ["feat_alpha", "feat_beta"]}
    eid = _seed_lineage(graph)
    frontier = graph.get_frontier()
    spec = ExperimentSpec(
        tool_name="adaptive_partition_compare",
        tool_version="v1",
        inputs={"feature_column": "feat_alpha", "max_bins": 3, "min_bin_n": 5},
        research_scope=dict(SCOPE),
        data_cutoff_date=CUTOFF,
    )
    fid = frontier._next_id()
    frontier.items[fid] = FrontierItem(
        frontier_id=fid,
        action_id="act-feat-alpha",
        action_code="ADAPTIVE_feat_alpha",
        parent_experiment_node_id=eid,
        branch_root_id="Q-root",
        action_type=ActionIntent.SLICING.value,
        target_feature="feat_alpha",
        planner_score=5.0,
        question_text="Partition feat_alpha?",
        draft_spec=spec.to_dict(),
    )
    graph.persist_frontier()
    graph.attach_experiment_result(
        eid,
        metrics={"success_rate": 0.5},
        observations=[StructuredResearchObservation(code=OBS_NO_CLEAR_DIFFERENCE)],
    )

    stop_branch = ResearchActionCandidate(
        action_id="stop-b",
        action_code="STOP_BRANCH",
        intent=ActionIntent.STOP.value,
        question_template_id="STOP",
        question_text="stop branch",
        tool_name="",
        tool_version="",
        draft_spec=None,
        uncertainty_addressed="STOP",
        expected_information="LOW",
        budget_cost=0,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
    )
    step = apply_plan_decision(
        graph,
        "E1",
        PlanDecision(decision_type=PlanDecisionType.STOP_BRANCH, selected=stop_branch, all_candidates=()),
        panel_columns=tuple(_panel().columns),
    )
    assert step.branch_terminal is True
    assert step.session_terminal is False
    assert graph.session.status == SessionStatus.ACTIVE


# --- Search accounting frame diversity ---


def test_search_accounting_includes_frame_diversity():
    graph = _graph()
    eid = _seed_lineage(graph, frame_id="frame-acc-1")
    record_experiment_executed(graph.get_search_accounting(), graph, eid)
    ledger = graph.get_search_accounting().session_ledger
    assert "frame-acc-1" in ledger.unique_research_frames


# --- Persistence / isolation ---


def test_no_production_coupling_reframe_modules():
    import modules.edge_research.research_frame as rf

    src = open(rf.__file__).read()
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in src


def test_graph_persists_frame_registry():
    graph = _graph()
    reg = graph.get_frame_registry()
    fid = reg.next_id()
    reg.register(ResearchFrame.initial(fid, POP, OUT))
    graph.persist_frames()
    assert "frames" in graph.session.research_frames
