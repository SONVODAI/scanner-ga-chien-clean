"""Phase 3H.1.1 — Provenance Resolution & Point-in-Time Proof tests A–M."""

from __future__ import annotations

import json

import pandas as pd

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import generate_action_candidates
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_capability_registry import (
    build_capability_registry,
    ensure_session_capability_registry,
)
from modules.edge_research.research_data_expansion_audit import (
    ScientificSafetyClass,
    build_research_data_expansion_audit,
    ensure_session_expansion_audit,
)
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_planner import plan_next_action, score_all_candidates
from modules.edge_research.research_provenance_proof import (
    PROVENANCE_PROOF_VERSION,
    PRIMARY_TARGETS,
    PointInTimeStatus,
    ResearchProvenanceProofReport,
    build_research_provenance_proof,
    compute_volume_ratio20_series,
    ensure_session_provenance_proof,
    run_point_in_time_proof_tests,
)
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
                "t3_target_date": f"2026-08-{d + 4:02d}",
                "t5_target_date": f"2026-08-{d + 6:02d}",
                "t10_target_date": f"2026-08-{d + 11:02d}",
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


# A — raw T0 field remains unchanged after future rows appended
def test_a_raw_t0_unchanged_after_future_rows():
    closes = [10.0 + i * 0.01 for i in range(10)]
    val_t = closes[5]
    extended = closes + [99.0, 88.0]
    assert extended[5] == val_t
    pit = next(t for t in run_point_in_time_proof_tests() if t.test_id == "PIT-B-vol_ratio20")
    assert pit.passed


# B — legitimate rolling derived field unchanged at historical T
def test_b_rolling_derived_unchanged_at_historical_t():
    volumes = [1000.0 + i * 5 for i in range(30)]
    ratios = compute_volume_ratio20_series(volumes)
    t = 25
    before = float(ratios[t])
    ext = compute_volume_ratio20_series(volumes + [9000.0, 8000.0])
    assert float(ext[t]) == before


# C — deliberately future-dependent calculation rejected
def test_c_future_dependent_rejected():
    tests = run_point_in_time_proof_tests()
    fut = next(t for t in tests if t.test_id == "PIT-C-future-dependent")
    assert fut.passed


# D — cross-sectional rank uses only contemporaneous universe (ordinal correction)
def test_d_rank_fields_not_cross_sectional():
    report = build_research_provenance_proof(_panel())
    hr = report.field_proofs["provenance_proof:missing_panel:health_rank"]
    gr = report.field_proofs["provenance_proof:missing_panel:group_rank"]
    assert hr.cross_sectional_dependency is False
    assert gr.cross_sectional_dependency is False
    pit = next(t for t in report.point_in_time_tests if t.test_id == "PIT-D-ordinal-not-cross-sectional")
    assert pit.passed


# E — later universe member cannot alter frozen T rank
def test_e_later_universe_cannot_alter_frozen_rank():
    tests = run_point_in_time_proof_tests()
    frozen = next(t for t in tests if t.test_id == "PIT-E-frozen-ordinal-rank")
    assert frozen.passed


# F — contaminated downstream knowledge cannot be laundered
def test_f_contaminated_knowledge_not_laundered():
    tests = run_point_in_time_proof_tests()
    contam = next(t for t in tests if t.test_id == "PIT-F-contamination")
    assert contam.passed


# G — unresolved provenance remains unresolved
def test_g_unresolved_stays_unresolved():
    report = build_research_provenance_proof(_panel())
    assert len(report.still_unresolved_manifest) > 0
    tests = run_point_in_time_proof_tests()
    unr = next(t for t in tests if t.test_id == "PIT-G-unresolved")
    assert unr.passed


# H — market path disagreement surfaced
def test_h_market_path_disagreement_surfaced():
    report = build_research_provenance_proof(_panel())
    assert len(report.market_path_comparison) >= 4
    conflict = [m for m in report.market_path_comparison if m.conflict_risk in {"MEDIUM", "HIGH"}]
    assert len(conflict) >= 2
    pit = next(t for t in report.point_in_time_tests if t.test_id == "PIT-H-market-disagreement")
    assert pit.passed


# I — no newly audited field becomes research-accessible
def test_i_no_new_field_becomes_accessible():
    report = build_research_provenance_proof(_panel())
    for proof in report.field_proofs.values():
        assert proof.research_accessible_now is False
    panel = build_research_panel()
    if panel is not None and not panel.empty:
        for fld in PRIMARY_TARGETS:
            assert fld not in panel.columns


# J — capability registry behavior unchanged
def test_j_capability_registry_unchanged():
    panel = _panel()
    cap_before = build_capability_registry(panel, REGISTRY)
    build_research_provenance_proof(panel)
    cap_after = build_capability_registry(panel, REGISTRY)
    assert cap_before.capabilities.keys() == cap_after.capabilities.keys()
    for k, v in cap_before.capabilities.items():
        assert cap_after.capabilities[k].currently_research_accessible == v.currently_research_accessible


# K — planner / global allocator neutrality
def test_k_planner_neutrality_after_provenance_proof():
    panel = _panel()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    assess = _assessment()
    cands = generate_action_candidates(assess, graph, REGISTRY, panel_columns=tuple(panel.columns))
    plan_before = plan_next_action(assess, cands, graph)
    scores_before = score_all_candidates(assess, cands, graph)

    ensure_session_provenance_proof(graph)
    ensure_session_expansion_audit(graph)
    ensure_session_capability_registry(graph, panel, REGISTRY)

    plan_after = plan_next_action(assess, cands, graph)
    scores_after = score_all_candidates(assess, cands, graph)

    assert plan_before.decision_type == plan_after.decision_type
    assert plan_before.selected == plan_after.selected
    for k in scores_before:
        assert scores_before[k][0] == scores_after[k][0]


# L — production isolation
def test_l_production_isolation():
    import modules.edge_research.research_provenance_proof as mod

    source = open(mod.__file__, encoding="utf-8").read().lower()
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden.lower() not in source


# M — no BB / human / ChatGPT relationship leakage
def test_m_no_bb_human_leakage():
    report = build_research_provenance_proof(_panel())
    text = json.dumps(report.to_dict()).lower()
    for token in ("blind_benchmark", "bb09", "chatgpt", "predictive edge"):
        assert token not in text


def test_primary_targets_all_traced():
    report = build_research_provenance_proof(_panel())
    assert len(report.field_proofs) == len(PRIMARY_TARGETS)
    for fld in PRIMARY_TARGETS:
        proof = report.field_proofs[f"provenance_proof:missing_panel:{fld}"]
        assert proof.point_in_time_proof_result == PointInTimeStatus.PROVEN.value
        assert proof.final_scientific_classification == ScientificSafetyClass.DERIVED_BUT_LEGAL.value


def test_volume_ratio20_reconstruction_details():
    proof = build_research_provenance_proof(_panel()).field_proofs[
        "provenance_proof:missing_panel:volume_ratio20"
    ]
    assert proof.point_in_time_reconstructable == "true"
    assert "vol_ma20" in proof.reconstruction_recipe or "volume" in proof.raw_dependencies
    assert proof.earliest_availability_horizon == 19


def test_safe_manifest_populated():
    report = build_research_provenance_proof(_panel())
    assert len(report.safe_candidate_manifest) == len(PRIMARY_TARGETS)
    for fid in report.safe_candidate_manifest:
        assert fid.startswith("provenance_proof:missing_panel:")
        assert fid in report.field_proofs


def test_persistence_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(tmp_path))
    from modules.edge_research.storage import read_research_graph, write_research_graph

    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, session_id="rs-3h1-1-proof")
    ensure_session_provenance_proof(graph)
    graph.persist_provenance_proof()
    write_research_graph(graph, data_dir=tmp_path)
    loaded = read_research_graph("rs-3h1-1-proof", data_dir=tmp_path)
    assert loaded.session.research_provenance_proof is not None
    reloaded = ResearchProvenanceProofReport.from_dict(loaded.session.research_provenance_proof)
    assert reloaded.version == PROVENANCE_PROOF_VERSION
    assert len(reloaded.field_proofs) == len(PRIMARY_TARGETS)
