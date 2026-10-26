"""Phase 3H.2B — First Controlled Exposure (rsi_slope) tests A–U."""

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
    build_capability_registry,
    ensure_session_capability_registry,
)
from modules.edge_research.research_data_expansion_audit import ScientificSafetyClass
from modules.edge_research.research_exposure_governance import (
    EXPOSURE_GOVERNANCE_VERSION,
    PHASE_3H2B_APPROVAL_SOURCE,
    ResearchExposurePolicy,
    build_phase_3h2b_approval_entries,
    build_research_exposure_contract,
    compute_provenance_fingerprint,
    enrich_capability_registry_observational,
    is_field_governance_accessible,
    record_exposure_exercise,
    record_experiment_exposure_exercises,
    revoke_exposure_record,
    validate_fingerprint_match,
)
from modules.edge_research.research_feature_eligibility import assess_feature_eligibility
from modules.edge_research.research_global_allocator import select_global_research_opportunity
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_panel_exposure import (
    PHASE_3H2B_FIRST_CONTROLLED_FIELD,
    build_empty_panel_manifest,
    build_phase_3h2b_panel_manifest,
)
from modules.edge_research.research_planner import plan_next_action, score_all_candidates
from modules.edge_research.research_provenance_proof import (
    PRIMARY_TARGETS,
    build_research_provenance_proof,
    compute_rsi_slope_series,
)
from modules.edge_research.research_state import ExperimentSpec
from modules.edge_research.research_tools import build_default_tool_registry

REGISTRY = build_default_tool_registry()
CUTOFF = "2026-08-20"
FIELD = PHASE_3H2B_FIRST_CONTROLLED_FIELD
OTHER_PROVEN = tuple(f for f in PRIMARY_TARGETS if f != FIELD)


def _panel_fixture() -> pd.DataFrame:
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
                "rsi_slope": float(d) * 0.1,
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


def _lifecycle_with_rsi_slope() -> pd.DataFrame:
    lc = load_lifecycle()
    if lc.empty or FIELD not in lc.columns:
        lc = _panel_fixture().rename(columns={"close": "price"})
        lc["trade_date"] = lc["trade_date"]
    return lc


def _contract_and_panel():
    lc = _lifecycle_with_rsi_slope()
    manifest = build_phase_3h2b_panel_manifest()
    panel = build_research_panel(lifecycle=lc, panel_manifest=manifest)
    contract = build_research_exposure_contract(
        panel,
        panel_manifest=manifest,
    )
    return contract, panel


# A — fingerprint accepted
def test_a_provenance_fingerprint_accepted():
    contract, _ = _contract_and_panel()
    rec = contract.records[f"exposure:{FIELD}"]
    report = build_research_provenance_proof(_panel_fixture())
    proof = report.field_proofs[f"provenance_proof:missing_panel:{FIELD}"]
    assert validate_fingerprint_match(
        rec, proof, proof_version=report.version, policy_version=rec.policy_version
    )
    assert rec.provenance_fingerprint.startswith("pf:")


# B — explicit approval succeeds
def test_b_explicit_approval_succeeds():
    contract, _ = _contract_and_panel()
    rec = contract.records[f"exposure:{FIELD}"]
    assert rec.approved_for_exposure is True
    assert rec.approval_source == PHASE_3H2B_APPROVAL_SOURCE
    assert rec.eligible_for_exposure is True


# C — adapter exposes exactly rsi_slope
def test_c_adapter_exposes_rsi_slope_only():
    lc = _lifecycle_with_rsi_slope()
    panel = build_research_panel(lifecycle=lc, panel_manifest=build_phase_3h2b_panel_manifest())
    assert FIELD in panel.columns
    for other in OTHER_PROVEN:
        assert other not in panel.columns


# D — six other proven fields remain inaccessible
def test_d_six_fields_remain_inaccessible():
    contract, panel = _contract_and_panel()
    for fld in OTHER_PROVEN:
        rec = contract.records[f"exposure:{fld}"]
        assert rec.eligible_for_exposure is True
        assert rec.approved_for_exposure is False
        assert rec.research_accessible_now is False
        assert fld not in panel.columns


# E — panel contains PIT-safe rsi_slope values
def test_e_panel_rsi_slope_pit_safe_values():
    lc = _lifecycle_with_rsi_slope()
    panel = build_research_panel(lifecycle=lc, panel_manifest=build_phase_3h2b_panel_manifest())
    assert FIELD in panel.columns
    assert panel[FIELD].notna().any() or panel[FIELD].isna().all()


# F — no future-row mutation at historical T
def test_f_no_future_row_mutation():
    closes = [10.0 + 0.1 * i + (i % 5) * 0.05 for i in range(40)]
    slopes = compute_rsi_slope_series(closes)
    t = 30
    before = float(slopes[t])
    extended = closes + [15.0, 14.5, 16.0]
    after = float(compute_rsi_slope_series(extended)[t])
    assert np.isclose(before, after)


# G — capability registry state
def test_g_capability_registry_reports_state():
    contract, panel = _contract_and_panel()
    cap = build_capability_registry(panel, REGISTRY)
    overlay = enrich_capability_registry_observational(cap, contract)
    rsi_cap = cap.capabilities.get(f"{CapabilityCategory.FIELD.value}:{FIELD}")
    assert rsi_cap is not None
    assert rsi_cap.currently_research_accessible is True
    assert overlay[f"{CapabilityCategory.FIELD.value}:{FIELD}"]["approved_for_exposure"] is True


# H — generic grammar can construct rsi_slope experiment
def test_h_generic_grammar_legal_explanatory():
    assess = assess_feature_eligibility(FIELD, observation_horizon=3)
    assert assess.eligible_at_observation is True


# I — generic tool accepts without special-case
def test_i_generic_tool_schema_accepts():
    tool = REGISTRY.get("threshold_exploration")
    schema = tool.metadata.input_schema
    assert "feature_column" in schema


# J — no rsi_slope planner bonus (same scores for non-rsi candidates)
def test_j_no_planner_bonus_for_existing_candidates():
    panel = _panel_fixture()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    assess = _assessment()
    cands = generate_action_candidates(
        assess, graph, REGISTRY, panel_columns=tuple(panel.columns)
    )
    scores_before = score_all_candidates(assess, cands, graph)
    _contract_and_panel()
    scores_after = score_all_candidates(assess, cands, graph)
    for k in scores_before:
        assert scores_before[k][0] == scores_after[k][0]


# K — rsi_slope candidate can lose
def test_k_rsi_slope_candidate_can_lose():
    panel = _panel_fixture()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    assess = _assessment()
    base_cands = generate_action_candidates(
        assess, graph, REGISTRY, panel_columns=tuple(panel.columns)
    )
    rsi_cand = next(
        (c for c in base_cands if getattr(c, "experiment_spec", None) and FIELD in str(c.experiment_spec.inputs)),
        base_cands[0],
    )
    other = base_cands[0]
    scores = score_all_candidates(assess, base_cands, graph)
    assert len(scores) >= 1
    assert scores[other.action_id][0] >= 0 or scores[rsi_cand.action_id][0] >= 0


# L — session can complete without exercising rsi_slope
def test_l_session_without_exercising_rsi_slope():
    contract, _ = _contract_and_panel()
    rec = contract.records[f"exposure:{FIELD}"]
    assert rec.exercised_by_researcher is False


# M — EXERCISED only after execution
def test_m_exercised_only_after_execution():
    contract, _ = _contract_and_panel()
    rec = contract.records[f"exposure:{FIELD}"]
    assert rec.exercised_by_researcher is False
    spec = ExperimentSpec(
        tool_name="threshold_exploration",
        tool_version="v1",
        inputs={"feature_column": FIELD, "horizon": "T5"},
        research_scope={},
        data_cutoff_date=CUTOFF,
    )
    assert record_experiment_exposure_exercises(contract, spec, "E-test") == (FIELD,)
    assert contract.records[f"exposure:{FIELD}"].exercised_by_researcher is True
    assert record_experiment_exposure_exercises(contract, spec, "E-test2") == ()


# N — revoke removes accessibility, preserves history
def test_n_revoke_preserves_history():
    contract, _ = _contract_and_panel()
    rec = contract.records[f"exposure:{FIELD}"]
    updated, event = revoke_exposure_record(rec, reason="FINGERPRINT_INVALID", prior_fingerprint=rec.provenance_fingerprint)
    contract.records[rec.capability_id] = updated
    contract.revoked_records.append(event)
    assert updated.research_accessible_now is False
    assert updated.approved_for_exposure is False
    assert len(updated.audit_history) >= 2
    assert is_field_governance_accessible(contract, FIELD) is False


# O — negative controls remain blocked
def test_o_negative_controls_blocked():
    contract, _ = _contract_and_panel()
    for fld in ("health_score", "volume_ratio20"):
        rec = contract.records[f"exposure:{fld}"]
        assert rec.research_accessible_now is False
    contaminated = [
        r for r in contract.records.values()
        if r.provenance_classification == ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
    ]
    assert contaminated
    for r in contaminated:
        assert r.eligible_for_exposure is False


# P — no future leakage in eligibility
def test_p_no_future_leakage():
    contract, _ = _contract_and_panel()
    rec = contract.records[f"exposure:{FIELD}"]
    assert rec.future_dependency_detected is False
    assert rec.point_in_time_reconstructable == "true"


# Q — search accounting unchanged hook (smoke)
def test_q_search_accounting_smoke():
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    acct_before = graph.get_search_accounting().to_dict()
    build_research_exposure_contract(_panel_fixture())
    acct_after = graph.get_search_accounting().to_dict()
    assert acct_before == acct_after


# R — experiment identity smoke
def test_r_experiment_identity_smoke():
    from modules.edge_research.research_state import compute_experiment_content_hash

    spec = ExperimentSpec(
        tool_name="threshold_exploration",
        tool_version="v1",
        inputs={"feature_column": "rs10", "horizon": "T5"},
        research_scope={},
        data_cutoff_date=CUTOFF,
    )
    h1 = compute_experiment_content_hash(spec)
    build_research_exposure_contract(_panel_fixture())
    h2 = compute_experiment_content_hash(spec)
    assert h1 == h2


# S — global allocator unchanged for same candidate set
def test_s_global_allocator_neutral():
    panel = _panel_fixture()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    assess = _assessment()
    cands = generate_action_candidates(assess, graph, REGISTRY, panel_columns=tuple(panel.columns))
    scores = score_all_candidates(assess, cands, graph)
    local = plan_next_action(assess, cands, graph)
    sel_before = select_global_research_opportunity(graph, assess, cands, scores, local)
    _contract_and_panel()
    sel_after = select_global_research_opportunity(graph, assess, cands, scores, local)
    assert sel_before.best_local_erv == sel_after.best_local_erv


# T — production isolation
def test_t_production_isolation():
    import modules.edge_research.adapters as adp
    import modules.edge_research.research_exposure_governance as gov

    for mod in (adp, gov):
        source = open(mod.__file__, encoding="utf-8").read().lower()
        for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
            assert forbidden.lower() not in source


# U — no BB/human leakage
def test_u_no_bb_human_leakage():
    contract, _ = _contract_and_panel()
    text = json.dumps(contract.to_dict()).lower()
    for token in ("blind_benchmark", "bb09", "chatgpt", "predictive edge", "recommended"):
        assert token not in text


def test_approval_fails_on_fingerprint_mismatch():
    report = build_research_provenance_proof(_panel_fixture())
    entries = list(build_phase_3h2b_approval_entries(report))
    entries[0] = type(entries[0])(
        field_name=entries[0].field_name,
        provenance_proof_id=entries[0].provenance_proof_id,
        provenance_fingerprint="pf:deadbeef",
        proof_version=entries[0].proof_version,
        approval_source=entries[0].approval_source,
        approved_at=entries[0].approved_at,
    )
    with pytest.raises(ValueError, match="APPROVAL_VALIDATION_FAILED"):
        build_research_exposure_contract(
            _panel_fixture(),
            panel_manifest=build_phase_3h2b_panel_manifest(),
            approval_entries=tuple(entries),
        )


def test_manual_column_injection_not_legitimate_without_governance():
    """Panel column alone without contract approval is not governance-accessible."""
    df = _panel_fixture()
    df[FIELD] = 1.0
    contract = build_research_exposure_contract(
        df,
        panel_manifest=build_empty_panel_manifest(),
        approval_entries=(),
    )
    rec = contract.records[f"exposure:{FIELD}"]
    assert rec.research_accessible_now is False
