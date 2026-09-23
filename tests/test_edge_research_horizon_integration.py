"""Phase 3G.2.1 — horizon-aware integration repair (synthetic scenarios A–I)."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import (
    ActionIntent,
    _add_adaptive_candidates,
    _add_grammar_candidates,
    _add_frame_reframe_candidates,
    generate_action_candidates,
)
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_controller import (
    _register_frame_transition_on_spawn,
    _resolve_parent_frame_id,
    apply_plan_decision,
    run_experiment_and_plan,
)
from modules.edge_research.research_frame import (
    FrameTransformationType,
    ResearchFrame,
    ResearchFrameRegistry,
    build_grammar_scope_at_horizon,
    validate_outcome_at_horizon,
    validate_population_at_horizon,
    validate_specs_at_horizon,
)
from modules.edge_research.research_grammar import GrammarValidationError, OutcomeSpec, PopulationSpec
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_planner import PlanDecision, PlanDecisionType
from modules.edge_research.research_state import (
    ExperimentSpec,
    QuestionRationale,
    ResearchQuestionContext,
    SessionStatus,
)
from modules.edge_research.research_tools import build_default_tool_registry

CUTOFF = "2026-08-20"
REGISTRY = build_default_tool_registry()
POP_ALL = PopulationSpec.all_()
OUT_T5 = OutcomeSpec.compare("t5_return", ">", 0.0)
OUT_T10 = OutcomeSpec.compare("t10_return", ">", 0.0)
OUT_T3 = OutcomeSpec.compare("t3_return", ">", 0.0)


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
    return ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12, session_id="rs-h-integr")


def _spec(scope: dict | None = None) -> ExperimentSpec:
    return ExperimentSpec(
        tool_name="horizon_comparison",
        tool_version="v1",
        inputs={"horizons": ["T3", "T5", "T10"]},
        research_scope=scope or {},
        data_cutoff_date=CUTOFF,
    )


def _horizon_advanced_population() -> PopulationSpec:
    filt = PopulationSpec.filter_numeric("t5_return", ">", 0.0)
    return PopulationSpec.refine(POP_ALL, filt, reason_code="OUTCOME_TO_POPULATION")


def _seed_h5_frame(graph: ResearchGraph, *, frame_id: str = "frame-h5") -> str:
    """Seed experiment at observation horizon 5 with t5_return population."""
    pop = _horizon_advanced_population()
    ctx = ResearchQuestionContext(
        population_spec=pop.to_dict(),
        outcome_spec=OUT_T10.to_dict(),
        frame_id=frame_id,
        observation_horizon=5,
        population_n=100,
    )
    scope = build_grammar_scope_at_horizon(pop, OUT_T10, {}, observation_horizon=5)
    assert scope is not None

    reg = graph.get_frame_registry()
    reg.register(
        ResearchFrame(
            frame_id=frame_id,
            population=pop,
            outcome=OUT_T10,
            observation_horizon=5,
            eligible_feature_count=4,
        )
    )
    graph.persist_frames()

    oid = graph.add_root_observation(description="Root", node_id="O-h5")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="H5 frame?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        question_context=ctx,
        node_id="Q-h5",
    )
    return graph.add_experiment(question_node_id=qid, spec=_spec(scope), node_id="E-h5")


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(source_experiment_node_id="E-h5", tool_name="horizon_comparison", tool_status="OK")
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


# --- A: H0 future population rejected ---


def test_h0_future_population_rejected():
    pop = _horizon_advanced_population()
    with pytest.raises(GrammarValidationError, match="Future leakage"):
        validate_population_at_horizon(pop, observation_horizon=0)
    assert build_grammar_scope_at_horizon(pop, OUT_T10, {}, observation_horizon=0) is None


# --- B: H5 observed outcome population accepted ---


def test_h5_observed_outcome_population_accepted():
    pop = _horizon_advanced_population()
    validate_population_at_horizon(pop, observation_horizon=5)
    validate_outcome_at_horizon(OUT_T10, observation_horizon=5)
    scope = build_grammar_scope_at_horizon(pop, OUT_T10, {}, observation_horizon=5)
    assert scope is not None
    assert scope["research_observation_horizon"] == 5


# --- C: follow-on grammar generation without T0 crash ---


def test_follow_on_grammar_generation_at_h5():
    graph = _graph()
    eid = _seed_h5_frame(graph)
    assess = _assessment(
        interesting=True,
        descriptive_strength="GROUP_DIFFERENCE",
        additional_investigation_warranted=True,
    )
    cands: list = []
    _add_grammar_candidates(
        cands,
        assessment=assess,
        graph=graph,
        registry=REGISTRY,
        scope={},
        cutoff=CUTOFF,
        experiment_node_id=eid,
    )
    assert cands, "grammar candidates should be generated at horizon 5"
    for c in cands:
        if c.draft_spec and c.draft_spec.research_scope.get("population_spec"):
            assert c.draft_spec.research_scope.get("research_observation_horizon") == 5


# --- D: follow-on adaptive generation ---


def test_follow_on_adaptive_generation_at_h5():
    graph = _graph()
    eid = _seed_h5_frame(graph)
    assess = _assessment(
        additional_investigation_warranted=True,
        information_gaps=("CATEGORY_REFINEMENT",),
        empirical_findings=("CATEGORY_SEPARATION_DETECTED",),
    )
    graph.attach_experiment_result(
        eid,
        metrics={"feature_column": "feat_alpha", "best_category": "G1"},
    )
    cands: list = []
    _add_adaptive_candidates(
        cands,
        assessment=assess,
        graph=graph,
        registry=REGISTRY,
        scope={},
        cutoff=CUTOFF,
        experiment_node_id=eid,
        panel_columns=tuple(_panel().columns),
    )
    repop = [c for c in cands if c.intent == ActionIntent.REPOPULATE.value]
    assert repop, "adaptive repopulate candidates expected at horizon 5"


# --- E: follow-on reframe ---


def test_follow_on_reframe_at_h5():
    graph = _graph()
    eid = _seed_h5_frame(graph)
    frame = graph.get_frame_registry().get("frame-h5")
    assert frame is not None
    frame.experiments_in_frame = 4
    frame.flat_noisy_count = 3
    frame.stop_branch_count = 2
    graph.persist_frames()

    assess = _assessment(
        observation_kind="STRUCTURAL_OBSERVATION",
        empirical_findings=("HORIZON_HETEROGENEOUS",),
    )
    cands: list = []
    _add_frame_reframe_candidates(
        cands,
        assessment=assess,
        graph=graph,
        registry=REGISTRY,
        scope={},
        cutoff=CUTOFF,
        experiment_node_id=eid,
        panel_columns=tuple(_panel().columns),
    )
    reframe = [c for c in cands if c.intent in (ActionIntent.REFRAME.value, ActionIntent.REPOPULATE.value)]
    assert reframe, "horizon-advanced frame should produce legal reframe candidates"


# --- F: illegal later target rejected ---


def test_illegal_later_target_rejected_at_h10():
    pop = _horizon_advanced_population()
    with pytest.raises(GrammarValidationError, match="Outcome not forward"):
        validate_specs_at_horizon(pop, OUT_T10, observation_horizon=10)


# --- G: lineage before failure ---


def test_lineage_persisted_before_downstream_failure():
    graph = _graph()
    reg = graph.get_frame_registry()
    parent_id = reg.next_id()
    child_id = reg.next_id()
    reg.register(ResearchFrame.initial(parent_id, POP_ALL, OUT_T5))
    graph.persist_frames()

    pending = ResearchQuestionContext(
        population_spec=_horizon_advanced_population().to_dict(),
        outcome_spec=OUT_T10.to_dict(),
        frame_id=child_id,
        observation_horizon=5,
        population_change={
            "reason_code": FrameTransformationType.OUTCOME_TO_POPULATION.value,
            "triggering_evidence": {"code": "HORIZON_HETEROGENEOUS"},
        },
    )

    _register_frame_transition_on_spawn(
        graph,
        pending_ctx=pending,
        parent_frame_id=parent_id,
        experiment_node_id="E-trigger",
        planner_action_code="REFRAME_OUTCOME_TO_POPULATION",
        planner_score=10.15,
    )
    assert len(reg.lineage) == 1
    rec = reg.lineage[0]
    assert rec.new_frame_id == child_id
    assert rec.parent_observation_horizon == 0
    assert rec.observation_horizon == 5
    assert rec.planner_action_code == "REFRAME_OUTCOME_TO_POPULATION"
    assert rec.planner_score == 10.15


# --- H: session failure state ---


def test_session_failure_state_after_planning_error():
    graph = _graph()
    eid = _seed_h5_frame(graph)
    panel = _panel()

    with patch(
        "modules.edge_research.research_controller.apply_plan_decision",
        side_effect=RuntimeError("injected downstream failure"),
    ):
        step = run_experiment_and_plan(graph, eid, panel, REGISTRY)

    assert graph.session.status == SessionStatus.ERROR
    assert graph.session.session_stop_reason["operation"] == "plan_after_experiment"
    assert graph.session.session_stop_reason["experiment_executed"] is True
    assert step.session_terminal is True
    assert graph.get_node(eid).experiment_result is not None


# --- I: generic horizon (metadata-driven, not T5-specific) ---


def test_generic_horizon_uses_metadata_not_t5_hardcode():
    """t3_return population legal at H3; t10 outcome still forward."""
    pop = PopulationSpec.refine(
        POP_ALL,
        PopulationSpec.filter_numeric("t3_return", ">", 0.0),
        reason_code="GENERIC_H3",
    )
    validate_population_at_horizon(pop, observation_horizon=3)
    scope = build_grammar_scope_at_horizon(pop, OUT_T10, {}, observation_horizon=3)
    assert scope is not None

    with pytest.raises(GrammarValidationError):
        validate_population_at_horizon(pop, observation_horizon=0)


def test_resolve_parent_frame_falls_back_to_active_frame():
    graph = _graph()
    reg = graph.get_frame_registry()
    fid = reg.next_id()
    reg.register(ResearchFrame.initial(fid, POP_ALL, OUT_T5))
    graph.persist_frames()

    oid = graph.add_root_observation(description="Root", node_id="O-fb")
    qctx = ResearchQuestionContext(
        population_spec=POP_ALL.to_dict(),
        outcome_spec=OUT_T5.to_dict(),
        frame_id="",
    )
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="No frame_id on question?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        question_context=qctx,
        node_id="Q-fb",
    )
    eid = graph.add_experiment(question_node_id=qid, spec=_spec(), node_id="E-fb")
    assert _resolve_parent_frame_id(graph, eid) == fid


def test_apply_plan_decision_registers_lineage_before_spawn():
    graph = _graph()
    reg = graph.get_frame_registry()
    parent_id = reg.next_id()
    child_id = reg.next_id()
    reg.register(ResearchFrame.initial(parent_id, POP_ALL, OUT_T5))
    graph.persist_frames()

    oid = graph.add_root_observation(description="Root", node_id="O-lineage")
    qctx = ResearchQuestionContext(
        population_spec=POP_ALL.to_dict(),
        outcome_spec=OUT_T5.to_dict(),
        frame_id=parent_id,
    )
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Parent?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        question_context=qctx,
        node_id="Q-lineage",
    )
    eid = graph.add_experiment(question_node_id=qid, spec=_spec(), node_id="E-lineage")
    graph.attach_experiment_result(eid, metrics={"sample_size": 100})

    pop = _horizon_advanced_population()
    scope = build_grammar_scope_at_horizon(pop, OUT_T10, {}, observation_horizon=5)
    assert scope is not None
    scope["pending_question_context"] = ResearchQuestionContext(
        population_spec=pop.to_dict(),
        outcome_spec=OUT_T10.to_dict(),
        frame_id=child_id,
        observation_horizon=5,
        population_change={"reason_code": FrameTransformationType.OUTCOME_TO_POPULATION.value},
    ).to_dict()

    from modules.edge_research.research_actions import ResearchActionCandidate

    selected = ResearchActionCandidate(
        action_id="act-1",
        action_code="REFRAME_OUTCOME_TO_POPULATION",
        intent=ActionIntent.REFRAME.value,
        question_template_id="FRAME_REFRAME",
        question_text="Advance horizon?",
        tool_name="horizon_comparison",
        tool_version="v1",
        draft_spec=_spec(scope),
        uncertainty_addressed="FRAME_REFRAME",
        expected_information="HIGH",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
        rationale_codes=("REFRAME",),
        priority_hints={},
    )
    decision = PlanDecision(
        decision_type=PlanDecisionType.EXPERIMENT,
        selected=selected,
        all_candidates=(selected,),
        rationale_codes=("REFRAME",),
    )

    lineage_before = len(reg.lineage)
    apply_plan_decision(graph, eid, decision, planner_score=10.15)
    assert len(reg.lineage) == lineage_before + 1
    assert reg.lineage[-1].planner_score == 10.15


def test_production_isolation_maintained():
    import modules.edge_research.research_frame as rf
    import modules.edge_research.research_actions as ra
    import modules.edge_research.research_controller as rc

    for mod in (rf, ra, rc):
        source = open(mod.__file__).read()
        for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
            assert forbidden not in source
