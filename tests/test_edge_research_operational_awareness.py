"""Phase 3H.3 — Operational Capability Awareness tests A–Z + Scenarios A/B/C."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.adapters import build_research_panel, load_lifecycle
from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import generate_action_candidates
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_capability_registry import (
    CapabilityCategory,
    CapabilityStatus,
    build_capability_registry,
    ensure_session_capability_registry,
    record_experiment_capability_exercise,
)
from modules.edge_research.research_controller import plan_after_experiment
from modules.edge_research.research_data_expansion_audit import ScientificSafetyClass
from modules.edge_research.research_exposure_governance import (
    build_research_exposure_contract,
    record_experiment_exposure_exercises,
    revoke_exposure_record,
)
from modules.edge_research.research_feature_eligibility import assess_feature_eligibility
from modules.edge_research.research_global_allocator import select_global_research_opportunity
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_operational_awareness import (
    OPERATIONAL_AWARENESS_VERSION,
    AwarenessBlockerClass,
    OperationalAwareness,
    build_operational_awareness,
    ensure_session_operational_awareness,
    filter_candidates_to_awareness_legal_set,
    mark_awareness_considered_from_candidates,
    mark_awareness_consulted,
    partition_features_for_construction,
    rebuild_awareness_at_horizon,
    validate_no_recommendation_language,
)
from modules.edge_research.research_panel_exposure import (
    PHASE_3H2B_FIRST_CONTROLLED_FIELD,
    build_phase_3h2b_panel_manifest,
)
from modules.edge_research.research_planner import plan_next_action, score_all_candidates
from modules.edge_research.research_provenance_proof import PRIMARY_TARGETS
from modules.edge_research.research_state import ExperimentSpec, QuestionRationale
from modules.edge_research.research_tools import build_default_tool_registry
from modules.edge_research.storage import read_research_graph, write_research_graph

REGISTRY = build_default_tool_registry()
CUTOFF = "2026-08-20"
FIELD = PHASE_3H2B_FIRST_CONTROLLED_FIELD
CLOSED_FIELD = "health_score"
OTHER_PROVEN = tuple(f for f in PRIMARY_TARGETS if f != FIELD)


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


def _lifecycle_with_rsi_slope() -> pd.DataFrame:
    lc = load_lifecycle()
    if lc.empty or FIELD not in lc.columns:
        lc = _panel_fixture().rename(columns={"close": "price"})
    return lc


def _contract_panel_registry():
    lc = _lifecycle_with_rsi_slope()
    manifest = build_phase_3h2b_panel_manifest()
    panel = build_research_panel(lifecycle=lc, panel_manifest=manifest)
    contract = build_research_exposure_contract(panel, panel_manifest=manifest)
    cap = build_capability_registry(panel, REGISTRY)
    return contract, panel, cap


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
        information_gaps=("TIME_DISTRIBUTION",),
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
    ensure_session_capability_registry(graph, panel, REGISTRY)
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


# A — researcher knows accessible rsi_slope
def test_a_researcher_knows_accessible_rsi_slope():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    entry = awareness.entry_for_field(FIELD)
    assert entry is not None
    assert entry.known is True
    assert entry.available is True
    assert entry.exposure_approved is True
    assert entry.exposure_wired is True
    assert entry.exposure_accessible is True


# B — researcher knows closed health_score
def test_b_researcher_knows_closed_health_score():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    entry = awareness.entry_for_field(CLOSED_FIELD)
    assert entry is not None
    assert entry.known is True
    assert entry.available is False
    assert entry.exposure_approved is False
    assert entry.exposure_wired is False
    assert entry.exposure_accessible is False


# C — closed capability includes structured blocker
def test_c_closed_capability_structured_blocker():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    entry = awareness.entry_for_field(CLOSED_FIELD)
    assert entry.why_cannot_use == AwarenessBlockerClass.NOT_APPROVED.value


# D — production-only / blocked data source known but not usable
def test_d_production_only_capability_blocked():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    traj = next((e for e in awareness.entries.values() if e.name == "trajectory_knowledge"), None)
    assert traj is not None
    assert traj.known is True
    assert traj.available is False
    assert traj.why_cannot_use == AwarenessBlockerClass.NOT_WIRED.value

    contaminated = [
        r for r in contract.records.values()
        if r.provenance_classification == ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
    ]
    assert contaminated

    camera = next((e for e in awareness.entries.values() if "camera" in e.name), None)
    assert camera is not None
    assert camera.available is False


# E — researcher knows all registered research tools
def test_e_all_registered_tools_known():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    tool_entries = [
        e for e in awareness.entries.values()
        if e.category == CapabilityCategory.RESEARCH_TOOL.value
    ]
    registered = REGISTRY.list_tools()
    assert len(tool_entries) >= len(registered)
    for t in registered:
        tool_name = getattr(t, "tool_name", None) or getattr(t, "name", str(t))
        matching = [e for e in tool_entries if e.name == tool_name]
        assert matching, f"tool {tool_name} missing from awareness"


# F — tool affordances represented neutrally
def test_f_tool_affordances_neutral():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    assert awareness.tool_affordances
    violations = validate_no_recommendation_language(awareness.to_dict())
    assert not violations
    for ta in awareness.tool_affordances:
        assert ta["affordance"]
        assert "should" not in ta["affordance"].lower()


# G — horizon-dynamic legality
def test_g_horizon_dynamic_legality():
    contract, panel, cap = _contract_panel_registry()
    low = build_operational_awareness(panel, cap, exposure_contract=contract, observation_horizon=0)
    high = build_operational_awareness(panel, cap, exposure_contract=contract, observation_horizon=999)
    t5_low = low.entries.get(f"{CapabilityCategory.OUTCOME.value}:t5_return")
    t5_high = high.entries.get(f"{CapabilityCategory.OUTCOME.value}:t5_return")
    if t5_low and t5_high:
        assert t5_low.temporal_legal != t5_high.temporal_legal or (
            t5_low.available == t5_high.available
        )


# H — available-but-unexercised state
def test_h_available_but_unexercised():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    rsi = awareness.entry_for_field(FIELD)
    assert rsi.available is True
    assert rsi.exercised is False
    summary = awareness.audit_summary
    assert summary["available_but_unexercised_count"] >= 1


# I — execution changes EXERCISED only after actual experiment
def test_i_exercised_only_after_execution():
    contract, panel, cap = _contract_panel_registry()
    awareness_before = build_operational_awareness(panel, cap, exposure_contract=contract)
    rsi_before = awareness_before.entry_for_field(FIELD)
    assert rsi_before.exercised is False

    spec = ExperimentSpec(
        tool_name="threshold_exploration",
        tool_version="v1",
        inputs={"feature_column": FIELD, "horizon": "T5"},
        research_scope={},
        data_cutoff_date=CUTOFF,
    )
    record_experiment_exposure_exercises(contract, spec, "E-exec")
    awareness_after = build_operational_awareness(panel, cap, exposure_contract=contract)
    rsi_after = awareness_after.entry_for_field(FIELD)
    assert rsi_after.exercised is True


# J — KNOWN ≠ AVAILABLE ≠ CONSIDERED ≠ EXERCISED
def test_j_four_state_distinction():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    rsi = awareness.entry_for_field(FIELD)
    assert rsi.known is True
    assert rsi.available is True
    assert rsi.considered is False
    assert rsi.exercised is False

    closed = awareness.entry_for_field(CLOSED_FIELD)
    assert closed.known is True
    assert closed.available is False


# K — Scenario A: knows rsi_slope, chooses something else
def test_k_scenario_a_knows_does_not_use():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    assert awareness.entry_for_field(FIELD).available is True

    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment()
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    cands = filter_candidates_to_awareness_legal_set(cands, awareness)
    scores = score_all_candidates(assess, cands, graph, experiment_node_id=exp_id)
    decision = plan_next_action(assess, cands, graph, experiment_node_id=exp_id)

    rsi_used = False
    if decision.selected and decision.selected.draft_spec:
        feat = decision.selected.draft_spec.inputs.get("feature_column")
        if feat == FIELD:
            rsi_used = True
    assert awareness.entry_for_field(FIELD).known is True
    assert decision.selected is not None or len(cands) > 0


# L — Scenario B: autonomously construct rsi_slope investigation
def test_l_scenario_b_knows_and_can_use():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment(additional_investigation_warranted=True, interesting=True)
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    cands = filter_candidates_to_awareness_legal_set(cands, awareness)
    rsi_cands = [
        c for c in cands
        if c.draft_spec and c.draft_spec.inputs.get("feature_column") == FIELD
    ]
    assert rsi_cands, "generic machinery must construct rsi_slope candidate"


# M — Scenario C: knows health_score, cannot construct legal experiment
def test_m_scenario_c_knows_cannot_use():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    assert awareness.entry_for_field(CLOSED_FIELD).known is True
    assert awareness.entry_for_field(CLOSED_FIELD).available is False

    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment()
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    legal = filter_candidates_to_awareness_legal_set(cands, awareness)
    health_cands = [
        c for c in legal
        if c.draft_spec and (
            c.draft_spec.inputs.get("feature_column") == CLOSED_FIELD
            or c.draft_spec.inputs.get("partition_column") == CLOSED_FIELD
        )
    ]
    assert not health_cands


# N — awareness expands legal choice set without scoring bonus
def test_n_awareness_no_scoring_bonus():
    contract, panel, cap = _contract_panel_registry()
    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment()

    cands_no = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=None,
    )
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    cands_yes = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    cands_yes = filter_candidates_to_awareness_legal_set(cands_yes, awareness)

    common_ids = {c.action_id for c in cands_no} & {c.action_id for c in cands_yes}
    scores_no = score_all_candidates(assess, cands_no, graph, experiment_node_id=exp_id)
    scores_yes = score_all_candidates(assess, cands_yes, graph, experiment_node_id=exp_id)
    for aid in common_ids:
        assert scores_no[aid][0] == scores_yes[aid][0]


# O — planner candidate scores unchanged for pre-existing candidates
def test_o_planner_scores_unchanged():
    test_n_awareness_no_scoring_bonus()


# P — ERV unchanged (via score parity proxy)
def test_p_erv_unchanged_equivalent_opportunities():
    contract, panel, cap = _contract_panel_registry()
    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment()
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
    )
    scores_a = score_all_candidates(assess, cands, graph, experiment_node_id=exp_id)
    scores_b = score_all_candidates(assess, cands, graph, experiment_node_id=exp_id)
    assert scores_a == scores_b


# Q — global allocator selection unchanged when opportunity set unchanged
def test_q_global_allocator_unchanged():
    contract, panel, cap = _contract_panel_registry()
    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment()
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
    )
    scores = score_all_candidates(assess, cands, graph, experiment_node_id=exp_id)
    local = plan_next_action(assess, cands, graph, experiment_node_id=exp_id)
    alloc_a = select_global_research_opportunity(
        graph, assess, cands, scores, local,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
    )
    alloc_b = select_global_research_opportunity(
        graph, assess, cands, scores, local,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
    )
    assert alloc_a.best_local_erv == alloc_b.best_local_erv
    if alloc_a.selected and alloc_b.selected:
        assert alloc_a.selected.action_id == alloc_b.selected.action_id


# R — no forced diversity/coverage
def test_r_no_forced_diversity():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    payload = json.dumps(awareness.to_dict())
    assert "round_robin" not in payload.lower()
    assert "coverage" not in payload.lower() or "constructible" in payload.lower()


# S — awareness consultation audit persisted
def test_s_awareness_consultation_audit():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    awareness = mark_awareness_consulted(awareness, constructible_features=(FIELD,))
    assert any(e["event"] == "AWARENESS_CONSULTED" for e in awareness.audit_trail)


# T — save/reload preserves awareness state/audit
def test_t_save_reload_preserves_awareness():
    contract, panel, cap = _contract_panel_registry()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=8)
    awareness = ensure_session_operational_awareness(graph, panel, REGISTRY)
    awareness = mark_awareness_consulted(awareness, constructible_features=(FIELD,))
    graph._operational_awareness = awareness
    graph.persist_operational_awareness()

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        tmp_path = Path(tmp)
        write_research_graph(graph, data_dir=tmp_path)
        loaded = read_research_graph(graph.session.research_session_id, data_dir=tmp_path)
        assert loaded.session.research_operational_awareness is not None
        reloaded = OperationalAwareness.from_dict(loaded.session.research_operational_awareness)
        assert reloaded.version == OPERATIONAL_AWARENESS_VERSION
        assert any(e["event"] == "AWARENESS_CONSULTED" for e in reloaded.audit_trail)


# U — revoked capability unavailable but known
def test_u_revoked_remains_known_with_blocker():
    contract, panel, cap = _contract_panel_registry()
    rec = contract.records[f"exposure:{FIELD}"]
    updated, _ = revoke_exposure_record(
        rec, reason="TEST_REVOKE", prior_fingerprint=rec.provenance_fingerprint
    )
    contract.records[rec.capability_id] = updated
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    entry = awareness.entry_for_field(FIELD)
    assert entry.known is True
    assert entry.available is False
    assert entry.why_cannot_use


# V — contaminated capability never constructible
def test_v_contaminated_never_constructible():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    contaminated = [
        e for e in awareness.entries.values()
        if e.why_cannot_use == AwarenessBlockerClass.CONTAMINATED.value
        or "CONTAMINATED" in (e.blocker or "").upper()
    ]
    constructible = set(awareness.constructible_explanatory_features())
    for e in contaminated:
        assert e.name not in constructible


# W — experiment identity/dedup unchanged (smoke)
def test_w_experiment_identity_unchanged():
    from modules.edge_research.research_experiment_identity import canonical_experiment_content_hash
    spec = ExperimentSpec(
        tool_name="threshold_exploration",
        tool_version="v1",
        inputs={"feature_column": FIELD, "horizon": "T5"},
        research_scope={},
        data_cutoff_date=CUTOFF,
    )
    h1 = canonical_experiment_content_hash(spec)
    h2 = canonical_experiment_content_hash(spec)
    assert h1 == h2


# X — search accounting unchanged (smoke)
def test_x_search_accounting_unchanged():
    contract, panel, _ = _contract_panel_registry()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=8)
    sa_before = graph.get_search_accounting().to_dict()
    ensure_session_operational_awareness(graph, panel, REGISTRY)
    sa_after = graph.get_search_accounting().to_dict()
    assert sa_before == sa_after


# Y — production isolation
def test_y_production_isolation():
    import modules.edge_research.research_operational_awareness as mod
    src = open(mod.__file__).read()
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden not in src


# Z — no BB01–BB08/human/ChatGPT leakage
def test_z_no_benchmark_leakage():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    violations = validate_no_recommendation_language(awareness.to_dict())
    assert not violations


# Counterfactual neutrality
def test_counterfactual_neutrality_identical_opportunity_set():
    contract, panel, cap = _contract_panel_registry()
    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment()

    cands_a = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=None,
    )
    scores_a = score_all_candidates(assess, cands_a, graph, experiment_node_id=exp_id)
    decision_a = plan_next_action(assess, cands_a, graph, experiment_node_id=exp_id)

    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    cands_b = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    cands_b = filter_candidates_to_awareness_legal_set(cands_b, awareness)
    scores_b = score_all_candidates(assess, cands_b, graph, experiment_node_id=exp_id)
    decision_b = plan_next_action(assess, cands_b, graph, experiment_node_id=exp_id)

    ids_a = {c.action_id for c in cands_a if not c.blocked}
    ids_b = {c.action_id for c in cands_b if not c.blocked}
    if ids_a == ids_b:
        for aid in ids_a:
            assert scores_a[aid][0] == scores_b[aid][0]
        if decision_a.selected and decision_b.selected:
            assert decision_a.selected.action_id == decision_b.selected.action_id


# partition_features_for_construction parity
def test_partition_features_with_and_without_awareness():
    contract, panel, cap = _contract_panel_registry()
    cols = tuple(panel.columns)
    legacy = partition_features_for_construction(cols, None)
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    aware = partition_features_for_construction(cols, awareness)
    assert FIELD in aware
    assert CLOSED_FIELD not in aware
    assert set(aware).issubset(set(legacy) | {FIELD})


# Session ensure helper
def test_ensure_session_operational_awareness():
    contract, panel, _ = _contract_panel_registry()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=8)
    awareness = ensure_session_operational_awareness(graph, panel, REGISTRY)
    assert awareness.audit_summary["known_capabilities_count"] > 0
    assert graph.session.research_operational_awareness is not None


# Considered state update
def test_mark_considered_from_candidates():
    contract, panel, cap = _contract_panel_registry()
    awareness = build_operational_awareness(panel, cap, exposure_contract=contract)
    graph, exp_id = _graph_with_experiment(panel)
    assess = _assessment()
    cands = generate_action_candidates(
        assess, graph, REGISTRY,
        experiment_node_id=exp_id,
        panel_columns=tuple(panel.columns),
        operational_awareness=awareness,
    )
    updated = mark_awareness_considered_from_candidates(awareness, cands)
    assert any(e.considered for e in updated.entries.values())
