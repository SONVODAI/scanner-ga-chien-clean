"""Phase 3G.4.1 — global experiment identity and deduplication synthetic tests A–L."""

from __future__ import annotations

import inspect
from unittest import mock

import pytest

import modules.edge_research.research_portfolio as portfolio_mod
from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import ActionIntent, ResearchActionCandidate
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_experiment_identity import (
    EXPERIMENT_IDENTITY_VERSION,
    REASON_ALREADY_EXECUTED,
    REASON_SAME_CYCLE,
    apply_experiment_identity_deduplication,
    canonical_experiment_content_hash,
    canonical_hash_from_candidate,
)
from modules.edge_research.research_frontier import FrontierItem, FrontierItemStatus, ResearchFrontier
from modules.edge_research.research_global_allocator import (
    GLOBAL_ALLOCATOR_VERSION,
    OpportunitySource,
    collect_global_opportunities,
    select_global_research_opportunity,
    apply_global_allocation_to_plan_decision,
)
from modules.edge_research.research_graph import DuplicateExperimentError, ResearchGraph
from modules.edge_research.research_grammar import OutcomeSpec, PopulationSpec
from modules.edge_research.research_planner import PlanDecisionType, plan_next_action, score_all_candidates
from modules.edge_research.research_portfolio import BranchPortfolioStatus
from modules.edge_research.research_search_accounting import record_experiment_executed
from modules.edge_research.research_state import ExperimentSpec, QuestionRationale, compute_experiment_content_hash

CUTOFF = "2026-08-20"
SCOPE: dict = {}


def _graph(*, budget: int = 12) -> ResearchGraph:
    return ResearchGraph.create_session(
        data_cutoff_date=CUTOFF,
        experiment_budget=budget,
        session_id="rs-experiment-identity",
    )


def _spec(
    tool: str = "adaptive_partition_compare",
    inputs: dict | None = None,
    feature: str = "feat_alpha",
    *,
    scope: dict | None = None,
) -> ExperimentSpec:
    ins = inputs or {"horizon": "T5", "feature_column": feature}
    return ExperimentSpec(
        tool_name=tool,
        tool_version="v1",
        inputs=ins,
        research_scope=scope if scope is not None else SCOPE,
        data_cutoff_date=CUTOFF,
    )


def _scoped_spec(
    feature: str = "feat_alpha",
    *,
    population: PopulationSpec | None = None,
    outcome: OutcomeSpec | None = None,
    observation_horizon: int | None = None,
    threshold: float | None = None,
) -> ExperimentSpec:
    pop = population or PopulationSpec.all_()
    out = outcome or OutcomeSpec.compare("t5_return", ">", 0.0)
    inputs: dict = {"feature_column": feature, "horizon": "T5"}
    if threshold is not None:
        inputs["threshold"] = threshold
    scope = {
        "pending_question_context": {
            "observation_horizon": observation_horizon if observation_horizon is not None else 5,
            "population_spec": pop.to_dict(),
            "outcome_spec": out.to_dict(),
        }
    }
    return _spec(inputs=inputs, feature=feature, scope=scope)


def _seed_lineage(graph: ResearchGraph, *, feature: str = "feat_alpha") -> str:
    oid = graph.add_root_observation(description="Root", node_id="O-root")
    qid = graph.spawn_question(
        parent_node_ids=[oid],
        question_text="Initial?",
        rationale=QuestionRationale(reason_code="SEED", prior_node_id=oid),
        node_id="Q-root",
    )
    return graph.add_experiment(
        question_node_id=qid,
        spec=_spec(feature=feature),
        node_id="E-root",
    )


def _execute_experiment(graph: ResearchGraph, parent_eid: str, spec: ExperimentSpec, *, node_id: str) -> str:
    qid = graph.spawn_question(
        parent_node_ids=[parent_eid],
        question_text=f"Follow-up for {node_id}?",
        rationale=QuestionRationale(reason_code="FOLLOWUP", prior_node_id=parent_eid),
        node_id=f"Q-{node_id}",
    )
    return graph.add_experiment(question_node_id=qid, spec=spec, node_id=node_id)


def _assessment(**kwargs) -> ResearchAssessment:
    defaults = dict(
        source_experiment_node_id="E1",
        tool_name="adaptive_partition_compare",
        tool_status="OK",
        additional_investigation_warranted=True,
        conditional_candidate=True,
        branch_observation_codes=("SHAPE_STEP_CHANGE",),
    )
    defaults.update(kwargs)
    return ResearchAssessment(**defaults)


def _candidate(
    action_code: str,
    *,
    spec: ExperimentSpec | None = None,
    feature: str = "feat_alpha",
    action_id: str | None = None,
    hints: dict | None = None,
) -> ResearchActionCandidate:
    draft = spec or _spec(feature=feature)
    return ResearchActionCandidate(
        action_id=action_id or f"act-{action_code}",
        action_code=action_code,
        intent=ActionIntent.EXPLORATION.value,
        question_template_id=action_code,
        question_text=f"Question for {action_code}?",
        tool_name=draft.tool_name,
        tool_version=draft.tool_version,
        draft_spec=draft,
        uncertainty_addressed="GAP_EXPLORATION",
        expected_information="HIGH",
        budget_cost=1,
        already_attempted=False,
        blocked=False,
        blocked_reason=None,
        rationale_codes=(action_code,),
        priority_hints=dict(hints or {}),
    )


def _frontier_item(
    *,
    frontier_id: str,
    action_id: str,
    spec: ExperimentSpec,
    parent: str = "E-root",
    branch: str = "obs-branch-b",
    planner_score: float = 5.0,
) -> FrontierItem:
    return FrontierItem(
        frontier_id=frontier_id,
        action_id=action_id,
        action_code=f"FRONTIER_{frontier_id}",
        parent_experiment_node_id=parent,
        branch_root_id=branch,
        action_type=ActionIntent.EXPLORATION.value,
        target_feature=spec.inputs.get("feature_column", ""),
        planner_score=planner_score,
        draft_spec=spec.to_dict(),
        question_text=f"Frontier {frontier_id}?",
    )


def _panel_preflight(graph: ResearchGraph, features: list[str]) -> None:
    graph.session.panel_preflight = {
        "eligible_explanatory": features,
        "partition_columns_available": features,
    }


def _patch_opportunity_erv(score_fn):
    real_build = portfolio_mod.build_opportunity_from_candidate

    def _side(cand, **kw):
        opp = real_build(cand, **kw)
        opp.expected_research_value = score_fn(cand, opp)
        return opp

    return mock.patch.object(
        portfolio_mod,
        "build_opportunity_from_candidate",
        side_effect=_side,
    )


def _plan_with_global(
    graph: ResearchGraph,
    assessment: ResearchAssessment,
    candidates: list[ResearchActionCandidate],
    experiment_node_id: str,
    panel_columns: tuple[str, ...] | None = None,
):
    scores = score_all_candidates(assessment, candidates, graph, experiment_node_id=experiment_node_id)
    local = plan_next_action(assessment, candidates, graph, experiment_node_id=experiment_node_id)
    allocation = select_global_research_opportunity(
        graph,
        assessment,
        candidates,
        scores,
        local,
        experiment_node_id=experiment_node_id,
        panel_columns=panel_columns,
    )
    return apply_global_allocation_to_plan_decision(graph, local, allocation, local_opportunities=[])


# --- A. BB06 failure reproduction ---


def test_a_bb06_local_executed_equivalent_frontier_excluded_b_wins():
    """LOCAL A executed; equivalent FRONTIER A' higher ERV than B; B wins; no duplicate spawn."""
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta", "feat_gamma"])
    eid = _seed_lineage(graph)

    spec_a = _spec(feature="feat_gamma")
    executed_id = _execute_experiment(graph, eid, spec_a, node_id="E-executed-A")
    assert executed_id in graph.experiment_index.values()

    frontier = graph.get_frontier()
    frontier.items["f-dup-A"] = _frontier_item(
        frontier_id="f-dup-A",
        action_id="ea37630b08516f35",
        spec=spec_a,
        parent=eid,
        planner_score=99.0,
    )
    graph.persist_frontier()

    spec_b = _spec(feature="feat_beta")
    local_b = _candidate("EXPERIMENT_B", spec=spec_b, action_id="act-experiment-b")

    def _erv(cand, _opp):
        if cand.action_id == "ea37630b08516f35":
            return 8.39
        if cand.action_code == "EXPERIMENT_B":
            return 5.49
        return 1.0

    with _patch_opportunity_erv(_erv):
        decision = _plan_with_global(
            graph,
            _assessment(),
            [local_b],
            executed_id,
            ("feat_alpha", "feat_beta", "feat_gamma"),
        )

    assert decision.decision_type == PlanDecisionType.EXPERIMENT
    assert decision.selected is not None
    assert decision.selected.action_code == "EXPERIMENT_B"
    excluded = [
        e
        for e in (decision.global_allocation or {}).get("excluded", [])
        if e.get("frontier_id") == "f-dup-A"
    ]
    assert excluded, "duplicate frontier must remain in audit excluded list"
    assert REASON_ALREADY_EXECUTED in excluded[0]["exclusion_reason"]
    assert decision.selected.draft_spec is not None
    assert (
        compute_experiment_content_hash(decision.selected.draft_spec)
        != canonical_experiment_content_hash(spec_a)
    )


def test_a_bb06_no_duplicate_experiment_error_at_selection():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta", "feat_gamma"])
    eid = _seed_lineage(graph)
    spec_a = _spec(feature="feat_gamma")
    executed_id = _execute_experiment(graph, eid, spec_a, node_id="E-A")

    graph.get_frontier().items["f-dup"] = _frontier_item(
        frontier_id="f-dup",
        action_id="frontier-dup-id",
        spec=spec_a,
        parent=executed_id,
    )
    graph.persist_frontier()

    local_b = _candidate("VALID_B", spec=_spec(feature="feat_beta"))

    with _patch_opportunity_erv(
        lambda cand, _opp: 8.39 if cand.action_id == "frontier-dup-id" else 5.49
    ):
        decision = _plan_with_global(
            graph, _assessment(), [local_b], executed_id, ("feat_alpha", "feat_beta", "feat_gamma")
        )

    assert decision.decision_type == PlanDecisionType.EXPERIMENT
    assert decision.selected.action_code == "VALID_B"


# --- B. Cross-source identity ---


def test_b_cross_source_same_canonical_identity():
    spec = _scoped_spec("feat_alpha")
    content_hash = canonical_experiment_content_hash(spec)

    local = _candidate("LOCAL", spec=spec, action_id="local-id")
    frontier_item = _frontier_item(
        frontier_id="f-1",
        action_id="frontier-id",
        spec=spec,
    )
    frontier_hash = canonical_hash_from_candidate(frontier_item.to_action_candidate())

    graph = _graph()
    eid = _seed_lineage(graph)
    branch_id = "obs-deferred"
    portfolio = graph.get_portfolio_state()
    branch = portfolio.get_branch(branch_id)
    branch.status = BranchPortfolioStatus.DEFERRED_PROMISING.value
    branch.experiments_on_branch = 2
    graph.persist_portfolio_state()

    deferred_item = _frontier_item(
        frontier_id="f-def",
        action_id="deferred-id",
        spec=spec,
        branch=branch_id,
    )
    revisit_item = _frontier_item(
        frontier_id="f-rev",
        action_id="revisit-id",
        spec=spec,
        branch=branch_id,
    )

    assert canonical_hash_from_candidate(local) == content_hash
    assert frontier_hash == content_hash
    assert canonical_hash_from_candidate(deferred_item.to_action_candidate()) == content_hash
    assert canonical_hash_from_candidate(revisit_item.to_action_candidate()) == content_hash


# --- C. Different action IDs still deduplicate ---


def test_c_different_action_ids_same_semantics_deduplicate():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_gamma"])
    eid = _seed_lineage(graph)
    spec = _spec(feature="feat_gamma")
    executed_id = _execute_experiment(graph, eid, spec, node_id="E-done")

    local_dup = _candidate("LOCAL_DUP", spec=spec, action_id="local-action-111")
    graph.get_frontier().items["f-dup"] = _frontier_item(
        frontier_id="frontier-222",
        action_id="frontier-action-222",
        spec=spec,
        parent=executed_id,
    )
    graph.persist_frontier()

    assessment = _assessment()
    scores = score_all_candidates(assessment, [local_dup], graph, experiment_node_id=executed_id)
    comparable, excluded = collect_global_opportunities(
        graph,
        assessment,
        [local_dup],
        scores,
        experiment_node_id=executed_id,
        panel_columns=("feat_alpha", "feat_gamma"),
    )

    dup_excluded = [
        e
        for e in excluded
        if e.experiment_content_hash == canonical_experiment_content_hash(spec)
    ]
    assert len(dup_excluded) >= 1
    assert all(REASON_ALREADY_EXECUTED in e.exclusion_reason for e in dup_excluded)
    assert not any(
        o.experiment_content_hash == canonical_experiment_content_hash(spec) for o in comparable
    )


# --- D. Same tool, different population ---


def test_d_same_tool_different_population_not_deduplicated():
    pop_a = PopulationSpec.all_()
    pop_b = PopulationSpec.filter_numeric("rs10", ">", 0.0)
    spec_a = _scoped_spec("feat_alpha", population=pop_a)
    spec_b = _scoped_spec("feat_alpha", population=pop_b)
    assert canonical_experiment_content_hash(spec_a) != canonical_experiment_content_hash(spec_b)


# --- E. Same tool/population, different outcome ---


def test_e_same_tool_population_different_outcome_not_deduplicated():
    pop = PopulationSpec.all_()
    out_a = OutcomeSpec.compare("t5_return", ">", 0.0)
    out_b = OutcomeSpec.compare("t10_return", ">", 0.0)
    spec_a = _scoped_spec("feat_alpha", population=pop, outcome=out_a)
    spec_b = _scoped_spec("feat_alpha", population=pop, outcome=out_b)
    assert canonical_experiment_content_hash(spec_a) != canonical_experiment_content_hash(spec_b)


# --- F. Different observation horizon ---


def test_f_different_observation_horizon_not_deduplicated():
    spec_a = _scoped_spec("feat_alpha", observation_horizon=5)
    spec_b = _scoped_spec("feat_alpha", observation_horizon=10)
    assert canonical_experiment_content_hash(spec_a) != canonical_experiment_content_hash(spec_b)


# --- G. Different threshold/partition ---


def test_g_different_threshold_not_deduplicated():
    spec_a = _scoped_spec("feat_alpha", threshold=0.5)
    spec_b = _scoped_spec("feat_alpha", threshold=0.75)
    assert canonical_experiment_content_hash(spec_a) != canonical_experiment_content_hash(spec_b)


def test_g_different_feature_partition_not_deduplicated():
    spec_a = _spec(feature="feat_alpha")
    spec_b = _spec(feature="feat_beta")
    assert canonical_experiment_content_hash(spec_a) != canonical_experiment_content_hash(spec_b)


# --- H. Same-cycle duplicate representations ---


def test_h_same_cycle_only_one_representative_competes():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_gamma"])
    eid = _seed_lineage(graph)
    spec = _spec(feature="feat_gamma")

    local = _candidate("LOCAL_REP", spec=spec, action_id="act-local-rep")
    graph.get_frontier().items["f-rep"] = _frontier_item(
        frontier_id="f-rep",
        action_id="act-frontier-rep",
        spec=spec,
        parent=eid,
    )
    graph.persist_frontier()

    assessment = _assessment()

    def _erv(cand, _opp):
        if cand.action_id == "act-frontier-rep":
            return 9.0
        if cand.action_id == "act-local-rep":
            return 7.0
        return 1.0

    with _patch_opportunity_erv(_erv):
        scores = score_all_candidates(assessment, [local], graph, experiment_node_id=eid)
        comparable, excluded = collect_global_opportunities(
            graph,
            assessment,
            [local],
            scores,
            experiment_node_id=eid,
            panel_columns=("feat_alpha", "feat_gamma"),
        )

    hash_a = canonical_experiment_content_hash(spec)
    competing = [o for o in comparable if o.experiment_content_hash == hash_a]
    assert len(competing) == 1
    assert competing[0].action_id == "act-frontier-rep"

    same_cycle = [e for e in excluded if REASON_SAME_CYCLE in e.exclusion_reason]
    assert len(same_cycle) == 1
    assert same_cycle[0].action_id == "act-local-rep"
    assert f"kept=frontier:f-rep" in same_cycle[0].exclusion_reason or "kept=" in same_cycle[0].exclusion_reason


# --- I. Frontier executed first ---


def test_i_frontier_executed_first_equivalent_local_excluded():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_gamma"])
    eid = _seed_lineage(graph)
    spec = _spec(feature="feat_gamma")
    executed_id = _execute_experiment(graph, eid, spec, node_id="E-frontier-first")

    local_dup = _candidate("LOCAL_AFTER", spec=spec, action_id="act-local-after")
    alt = _candidate("ALT", spec=_spec(feature="feat_beta"), action_id="act-alt")

    with _patch_opportunity_erv(
        lambda cand, _opp: 10.0 if cand.action_id == "act-local-after" else 6.0
    ):
        decision = _plan_with_global(
            graph,
            _assessment(),
            [local_dup, alt],
            executed_id,
            ("feat_alpha", "feat_beta", "feat_gamma"),
        )

    assert decision.selected.action_code == "ALT"
    excluded_ids = {e.get("action_id") for e in (decision.global_allocation or {}).get("excluded", [])}
    assert "act-local-after" in excluded_ids


# --- J. Spawn safety remains ---


def test_j_spawn_safety_duplicate_experiment_error_still_raised():
    graph = _graph()
    eid = _seed_lineage(graph)
    spec = graph.get_node(eid).experiment_spec
    qid = graph.get_node(eid).parent_node_ids[0]
    with pytest.raises(DuplicateExperimentError) as exc:
        graph.add_experiment(question_node_id=qid, spec=spec)
    assert exc.value.existing_node_id == eid


# --- K. Search accounting ---


def test_k_duplicate_representations_do_not_inflate_executed_count():
    graph = _graph()
    eid = _seed_lineage(graph)
    state = graph.get_search_accounting()
    record_experiment_executed(state, graph, eid)
    before = state.session_ledger.experiments_executed

    spec = _spec(feature="feat_gamma")
    local = _candidate("LOCAL", spec=spec)
    graph.get_frontier().items["f-dup"] = _frontier_item(
        frontier_id="f-dup",
        action_id="act-f-dup",
        spec=spec,
        parent=eid,
    )
    graph.persist_frontier()

    assessment = _assessment()
    scores = score_all_candidates(assessment, [local], graph, experiment_node_id=eid)
    comparable, excluded = collect_global_opportunities(
        graph,
        assessment,
        [local],
        scores,
        experiment_node_id=eid,
        panel_columns=("feat_alpha", "feat_gamma"),
    )

    assert len([o for o in comparable if o.experiment_content_hash == canonical_experiment_content_hash(spec)]) <= 1
    assert state.session_ledger.experiments_executed == before


# --- L. Production isolation ---


def test_l_production_isolation():
    from modules.edge_research import research_experiment_identity, research_global_allocator

    for mod in (research_experiment_identity, research_global_allocator):
        source = inspect.getsource(mod)
        for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
            assert forbidden not in source


# --- Lifecycle: frontier sync on execution ---


def test_frontier_marked_duplicate_when_experiment_executed():
    graph = _graph()
    eid = _seed_lineage(graph)
    spec = _spec(feature="feat_gamma")
    graph.get_frontier().items["f-pending"] = _frontier_item(
        frontier_id="f-pending",
        action_id="act-pending",
        spec=spec,
        parent=eid,
    )
    graph.persist_frontier()

    _execute_experiment(graph, eid, spec, node_id="E-new")
    item = graph.get_frontier().items["f-pending"]
    assert item.status == FrontierItemStatus.DUPLICATE.value
    assert REASON_ALREADY_EXECUTED in item.invalid_reason


def test_global_explanation_includes_identity_version():
    graph = _graph()
    _panel_preflight(graph, ["feat_alpha", "feat_beta"])
    eid = _seed_lineage(graph)
    local = _candidate("LOCAL", feature="feat_beta")
    decision = _plan_with_global(graph, _assessment(), [local], eid, ("feat_alpha", "feat_beta"))
    expl = decision.portfolio_explanation or {}
    assert expl.get("experiment_identity_version") == EXPERIMENT_IDENTITY_VERSION
    assert expl.get("allocator_version") == GLOBAL_ALLOCATOR_VERSION
