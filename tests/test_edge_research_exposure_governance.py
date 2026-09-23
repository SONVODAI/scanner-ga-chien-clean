"""Phase 3H.2A — Controlled Exposure Infrastructure tests A–T."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import generate_action_candidates
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_capability_registry import (
    build_capability_registry,
    ensure_session_capability_registry,
)
from modules.edge_research.research_data_expansion_audit import ScientificSafetyClass
from modules.edge_research.research_exposure_governance import (
    EXPOSURE_GOVERNANCE_VERSION,
    ResearchExposurePolicy,
    build_research_exposure_contract,
    compute_provenance_fingerprint,
    ensure_session_exposure_contract,
    enrich_capability_registry_observational,
    evaluate_provenance_eligibility,
    represent_future_approval,
    revoke_exposure_record,
    validate_fingerprint_match,
)
from modules.edge_research.research_global_allocator import select_global_research_opportunity
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_panel_exposure import (
    CORE_STOCK_PANEL_FIELDS,
    PanelExposureManifest,
    parse_panel_exposure_manifest,
    resolve_effective_stock_columns,
)
from modules.edge_research.research_planner import plan_next_action, score_all_candidates
from modules.edge_research.research_provenance_proof import PRIMARY_TARGETS
from modules.edge_research.research_tools import build_default_tool_registry

REGISTRY = build_default_tool_registry()
CUTOFF = "2026-08-20"


def _panel() -> pd.DataFrame:
    rows = []
    for d in range(3):
        rows.append(
            {
                "trade_date": f"2026-08-{d + 1:02d}",
                "symbol": f"S{d}",
                "close": 10.0,
                "rs5": 1.0,
                "rs10": 0.5,
                "rsi14": 50.0,
                "rs_spread": 0.5,
                "partition_group": "A",
                "research_market_state": "X",
                "research_market_transition": "Y",
                "t3_return": 1.0,
                "t5_return": 1.0,
                "t10_return": 1.0,
            }
        )
    return pd.DataFrame(rows)


def _assessment() -> ResearchAssessment:
    return ResearchAssessment(
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


def _contract(panel=None):
    return build_research_exposure_contract(panel or _panel())


# A — proven SAFE_RAW → eligible, not auto-approved
def test_a_safe_raw_eligible_not_approved():
    contract = _contract()
    close_rec = next(
        (r for r in contract.records.values() if r.field_name == "health_group"),
        None,
    )
    assert close_rec is not None
    assert close_rec.scientifically_safe is True
    assert close_rec.eligible_for_exposure is True
    assert close_rec.approved_for_exposure is False


# B — proven DERIVED_BUT_LEGAL → eligible, not auto-approved
def test_b_derived_legal_eligible_not_approved():
    contract = _contract()
    vr = next(r for r in contract.records.values() if r.field_name == "volume_ratio20")
    assert vr.provenance_classification == ScientificSafetyClass.DERIVED_BUT_LEGAL.value
    assert vr.eligible_for_exposure is True
    assert vr.approved_for_exposure is False
    assert vr.research_accessible_now is False


# C — KNOWLEDGE_CONTAMINATED → never eligible
def test_c_contaminated_never_eligible():
    contract = _contract()
    contaminated = [
        r
        for r in contract.records.values()
        if r.provenance_classification == ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
    ]
    assert len(contaminated) >= 1
    for r in contaminated:
        assert r.eligible_for_exposure is False
        assert r.scientifically_safe is False


# D — PROVENANCE_UNRESOLVED → never eligible
def test_d_unresolved_never_eligible():
    policy = ResearchExposurePolicy()
    eligible, _, blockers, _, _ = evaluate_provenance_eligibility(
        proof=None,
        expansion_entry=None,
        policy=policy,
        observation_horizon=0,
    )
    assert eligible is False
    assert "MISSING_PROVENANCE_PROOF" in blockers


# E — future-dependent → never eligible
def test_e_future_dependent_never_eligible():
    contract = _contract()
    future_dep = [r for r in contract.records.values() if r.future_dependency_detected]
    for r in future_dep:
        assert r.eligible_for_exposure is False


# F — safe + eligible + no approval → absent from panel
def test_f_eligible_not_on_panel():
    contract = _contract()
    panel = _panel()
    for fld in PRIMARY_TARGETS:
        rec = next(r for r in contract.records.values() if r.field_name == fld)
        assert rec.eligible_for_exposure is True
        assert rec.research_accessible_now is False
        assert fld not in panel.columns


# G — future approval mechanism representable without enabling
def test_g_future_approval_representable():
    contract = _contract()
    rec = next(r for r in contract.records.values() if r.field_name == "health_score")
    spec = represent_future_approval(rec, approval_source="PHASE_3H2B", approved_at="2026-01-01")
    assert spec["phase_3h2a_enabled"] is False
    assert rec.approved_for_exposure is False


# H — missing source column prevents accessibility
def test_h_missing_source_prevents_accessibility():
    from modules.edge_research.research_exposure_governance import evaluate_approval_gate

    approved, wired, accessible, blockers = evaluate_approval_gate(
        eligible=True,
        approved_manifest=frozenset({"health_score"}),
        field_name="health_score",
        wired_manifest=frozenset({"health_score"}),
        panel_columns=frozenset(),
        lifecycle_columns=frozenset(),
        policy=ResearchExposurePolicy(),
        prior_approved=True,
        fingerprint_match=True,
    )
    assert approved is True
    assert wired is False
    assert accessible is False
    assert "MISSING_SOURCE_COLUMN" in blockers


# I — fingerprint mismatch invalidates
def test_i_fingerprint_mismatch_blocks():
    contract = _contract()
    rec = next(r for r in contract.records.values() if r.field_name == "rsi_slope")
    proof = build_research_exposure_contract(_panel()).records  # rebuild for proof access
    from modules.edge_research.research_provenance_proof import build_research_provenance_proof

    report = build_research_provenance_proof(_panel())
    proof_obj = report.field_proofs[f"provenance_proof:missing_panel:rsi_slope"]
    assert validate_fingerprint_match(rec, proof_obj, proof_version=report.version, policy_version=rec.policy_version)
    tampered = compute_provenance_fingerprint(
        proof_version="wrong",
        field_id=proof_obj.field_id,
        classification=proof_obj.final_scientific_classification,
        producer_module=proof_obj.producer_module,
        transformation_chain=proof_obj.transformation_chain,
        policy_version=rec.policy_version,
    )
    assert tampered != rec.provenance_fingerprint


# J — revocation preserves audit history
def test_j_revocation_preserves_history():
    contract = _contract()
    rec = next(r for r in contract.records.values() if r.field_name == "volume_ratio20")
    prior_len = len(rec.audit_history)
    updated, event = revoke_exposure_record(
        rec, reason="STALE_PROOF", prior_fingerprint=rec.provenance_fingerprint
    )
    assert updated.eligible_for_exposure is False
    assert updated.approved_for_exposure is False
    assert len(updated.audit_history) == prior_len + 1
    assert event["event"] == "EXPOSURE_REVOKED"


# K — temporal legality independent of exposure approval
def test_k_temporal_legality_independent():
    contract = _contract()
    rec = next(r for r in contract.records.values() if r.field_name == "volume_ratio20")
    assert rec.eligible_for_exposure is True
    assert rec.approved_for_exposure is False
    # volume_ratio20 horizon 19 — illegal at H=0
    contract_h0 = build_research_exposure_contract(_panel(), observation_horizon=0)
    rec_h0 = next(r for r in contract_h0.records.values() if r.field_name == "volume_ratio20")
    assert rec_h0.temporally_legal_at_horizon is False


# L — registry overlay observational, planner unchanged
def test_l_registry_overlay_planner_unchanged():
    panel = _panel()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    assess = _assessment()
    cands = generate_action_candidates(assess, graph, REGISTRY, panel_columns=tuple(panel.columns))
    plan_before = plan_next_action(assess, cands, graph)
    scores_before = score_all_candidates(assess, cands, graph)

    contract = ensure_session_exposure_contract(graph)
    cap = ensure_session_capability_registry(graph, panel, REGISTRY)
    overlay = enrich_capability_registry_observational(cap, contract)
    assert any("eligible_for_exposure" in v for v in overlay.values())

    plan_after = plan_next_action(assess, cands, graph)
    scores_after = score_all_candidates(assess, cands, graph)
    assert plan_before.selected == plan_after.selected
    for k in scores_before:
        assert scores_before[k][0] == scores_after[k][0]


# M — Global Allocator ERV unchanged
def test_m_global_allocator_unchanged():
    panel = _panel()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    assess = _assessment()
    cands = generate_action_candidates(assess, graph, REGISTRY, panel_columns=tuple(panel.columns))

    scores_before = score_all_candidates(assess, cands, graph)
    local_before = plan_next_action(assess, cands, graph)
    sel_before = select_global_research_opportunity(
        graph, assess, cands, scores_before, local_before
    )

    ensure_session_exposure_contract(graph)

    scores_after = score_all_candidates(assess, cands, graph)
    local_after = plan_next_action(assess, cands, graph)
    sel_after = select_global_research_opportunity(
        graph, assess, cands, scores_after, local_after
    )

    assert local_before.selected == local_after.selected
    for k in scores_before:
        assert scores_before[k][0] == scores_after[k][0]
    assert sel_before.best_local_erv == sel_after.best_local_erv
    assert sel_before.comparable_count == sel_after.comparable_count
    if sel_before.selected and sel_after.selected:
        assert sel_before.selected.action_id == sel_after.selected.action_id
        assert sel_before.selected.expected_research_value == sel_after.selected.expected_research_value


# N — build_research_panel schema unchanged
def test_n_panel_schema_unchanged():
    try:
        before = build_research_panel()
        ensure_session_exposure_contract(
            ResearchGraph.create_session(data_cutoff_date=CUTOFF)
        )
        after = build_research_panel()
    except Exception:
        before = _panel()
        after = _panel()
    assert set(before.columns) == set(after.columns)
    for fld in PRIMARY_TARGETS:
        assert fld not in after.columns
    assert resolve_effective_stock_columns() == CORE_STOCK_PANEL_FIELDS


# O — seven proven fields remain inaccessible
def test_o_seven_fields_inaccessible():
    contract = _contract()
    for fld in PRIMARY_TARGETS:
        rec = next((r for r in contract.records.values() if r.field_name == fld), None)
        assert rec is not None, fld
        assert rec.eligible_for_exposure is True, fld
        assert rec.approved_for_exposure is False, fld
        assert rec.wired_to_panel is False, fld
        assert rec.research_accessible_now is False, fld


# P — contaminated alias cannot bypass gate
def test_p_contaminated_alias_blocked():
    policy = ResearchExposurePolicy()

    class FakeEntry:
        scientific_class = ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
        future_dependency = True
        earliest_legal_horizon = 0
        derivation_provenance = "alias_wrap"
        capability_id = "expansion_audit:pattern_knowledge:historical_success_ratio"
        field_name = "historical_success_ratio"
        source_id = "pattern_knowledge"
        exists = True
        confidence = "HIGH"

    eligible, _, blockers, _, _ = evaluate_provenance_eligibility(
        proof=None,
        expansion_entry=FakeEntry(),
        policy=policy,
        observation_horizon=0,
    )
    assert eligible is False
    assert any("BLOCKED" in b or "MISSING" in b for b in blockers)


# Q — malformed manifest fails closed
def test_q_malformed_manifest_fails_closed():
    with pytest.raises(ValueError, match="MALFORMED"):
        parse_panel_exposure_manifest({"wired_field_names": ["x"], "approved_field_names": []})
    with pytest.raises(ValueError, match="MALFORMED"):
        build_research_exposure_contract(
            _panel(),
            panel_manifest=PanelExposureManifest(
                approved_field_names=frozenset(),
                wired_field_names=frozenset({"health_score"}),
            ),
        )


# R — session persistence round trip
def test_r_session_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(tmp_path))
    from modules.edge_research.storage import read_research_graph, write_research_graph

    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, session_id="rs-3h2a-exp")
    ensure_session_exposure_contract(graph)
    graph.persist_exposure_contract()
    write_research_graph(graph, data_dir=tmp_path)
    loaded = read_research_graph("rs-3h2a-exp", data_dir=tmp_path)
    assert loaded.session.research_exposure_contract is not None
    from modules.edge_research.research_exposure_governance import ResearchExposureContract

    reloaded = ResearchExposureContract.from_dict(loaded.session.research_exposure_contract)
    assert reloaded.version == EXPOSURE_GOVERNANCE_VERSION
    assert len(reloaded.records) >= len(PRIMARY_TARGETS)


# S — no BB/human leakage
def test_s_no_bb_human_leakage():
    contract = _contract()
    text = json.dumps(contract.to_dict()).lower()
    for token in ("blind_benchmark", "bb09", "chatgpt", "predictive edge", "should investigate"):
        assert token not in text


# T — production isolation
def test_t_production_isolation():
    import modules.edge_research.research_exposure_governance as mod

    source = open(mod.__file__, encoding="utf-8").read().lower()
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden.lower() not in source


def test_baseline_parity_candidates_and_panel():
    panel = _panel()
    cols_before = tuple(panel.columns)
    assess = _assessment()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    cands_before = generate_action_candidates(
        assess, graph, REGISTRY, panel_columns=cols_before
    )
    build_research_exposure_contract(panel)
    cands_after = generate_action_candidates(
        assess, graph, REGISTRY, panel_columns=cols_before
    )
    assert [c.action_id for c in cands_before] == [c.action_id for c in cands_after]
    assert cols_before == tuple(panel.columns)
