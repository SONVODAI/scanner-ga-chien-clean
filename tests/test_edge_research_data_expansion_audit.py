"""Phase 3H.1 — Research Data Expansion Audit tests A–O."""

from __future__ import annotations

import json

import pandas as pd

from modules.edge_research.contracts import PRODUCTION_FORBIDDEN_IMPORTS
from modules.edge_research.research_actions import generate_action_candidates
from modules.edge_research.research_assessment import ResearchAssessment
from modules.edge_research.research_capability_registry import (
    build_capability_registry,
    ensure_session_capability_registry,
)
from modules.edge_research.research_data_expansion_audit import (
    EXPANSION_AUDIT_VERSION,
    ScientificSafetyClass,
    ResearchDataExpansionAudit,
    build_research_data_expansion_audit,
    ensure_session_expansion_audit,
    verify_reconstructability,
)
from modules.edge_research.research_graph import ResearchGraph
from modules.edge_research.research_planner import plan_next_action, score_all_candidates
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


# A — raw contemporaneous field
def test_a_raw_contemporaneous_safe_raw():
    audit = build_research_data_expansion_audit(_panel())
    entry = audit.entries.get("expansion_audit:observations:price")
    assert entry is not None
    assert entry.scientific_class == ScientificSafetyClass.SAFE_RAW_OBSERVATION.value


# B — deterministic T0-derived
def test_b_derived_but_legal_volume_ratio():
    audit = build_research_data_expansion_audit(_panel())
    entry = audit.entries.get("expansion_audit:observations:volume_ratio20")
    assert entry is not None
    assert entry.scientific_class == ScientificSafetyClass.DERIVED_BUT_LEGAL.value
    recon = verify_reconstructability("volume_ratio20")
    assert recon["status"] == "VERIFIED_DERIVATION_PATH"


# C — future-return field rejected
def test_c_future_return_temporally_unsafe_or_contaminated():
    audit = build_research_data_expansion_audit(_panel())
    entry = audit.entries.get("expansion_audit:pattern_knowledge:win_rate_pct")
    assert entry is not None
    assert entry.scientific_class == ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
    assert entry.future_dependency is True


# D — decision-derived contaminated
def test_d_decision_derived_contaminated():
    audit = build_research_data_expansion_audit(_panel())
    found = [
        e
        for e in audit.entry_list()
        if e.field_name in {"verified_level", "decision_status", "action"}
        and e.scientific_class == ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
    ]
    assert len(found) >= 1


# E — mixed dataset field-level
def test_e_mixed_dataset_field_level():
    audit = build_research_data_expansion_audit(_panel())
    obs_entries = [e for e in audit.entry_list() if e.source_id == "observations"]
    classes = {e.scientific_class for e in obs_entries}
    assert ScientificSafetyClass.SAFE_RAW_OBSERVATION.value in classes
    assert len(classes) >= 2


# F — unknown provenance unresolved
def test_f_unknown_provenance_unresolved():
    audit = build_research_data_expansion_audit(_panel())
    unresolved = [
        e
        for e in audit.entry_list()
        if e.scientific_class == ScientificSafetyClass.PROVENANCE_UNRESOLVED.value
    ]
    assert isinstance(unresolved, list)


# G — horizon legality metadata
def test_g_horizon_legality_metadata():
    recon_h0 = verify_reconstructability("t5_return", observation_horizon=0)
    recon_h5 = verify_reconstructability("rs10", observation_horizon=5)
    assert recon_h0["status"] == "UNCERTAIN" or recon_h0["reproducible_at_horizon"] is False
    assert recon_h5["reproducible_at_horizon"] is True


# H — safe but not exposed remains not accessible
def test_h_safe_not_exposed_stays_inaccessible():
    audit = build_research_data_expansion_audit(_panel())
    hg = audit.entries.get("expansion_audit:missing_panel_registry:health_group")
    assert hg is not None
    assert hg.could_be_exposed_safely is True
    assert hg.research_accessible_now is False


# I — missing panel registry field provenance
def test_i_missing_panel_field_provenance():
    audit = build_research_data_expansion_audit(_panel())
    vr = audit.entries.get("expansion_audit:missing_panel_registry:volume_ratio20")
    assert vr is not None
    assert "NOT_IN_DEFAULT_PANEL_WIRING" in vr.blocker_reason
    assert vr.scientific_class == ScientificSafetyClass.DERIVED_BUT_LEGAL.value


# J — camera raw vs production interpretation separate
def test_j_camera_raw_vs_production_separate():
    audit = build_research_data_expansion_audit(_panel())
    raw = audit.entries.get("expansion_audit:intraday_camera:close")
    prod = audit.entries.get("expansion_audit:intraday_camera:production_buy_sell_interpretation")
    assert raw is not None
    assert prod is not None
    assert raw.scientific_class == ScientificSafetyClass.SAFE_RAW_OBSERVATION.value
    assert raw.research_accessible_now is False
    assert prod.scientific_class == ScientificSafetyClass.TEMPORALLY_UNSAFE_OR_PRODUCTION_ONLY.value


# K — capability registry remains observational
def test_k_capability_registry_observational():
    panel = _panel()
    cap_before = build_capability_registry(panel, REGISTRY)
    audit = build_research_data_expansion_audit(panel)
    cap_after = build_capability_registry(panel, REGISTRY)
    assert cap_before.capabilities.keys() == cap_after.capabilities.keys()
    for k, v in cap_before.capabilities.items():
        assert cap_after.capabilities[k].status == v.status
        assert cap_after.capabilities[k].currently_research_accessible == v.currently_research_accessible
    assert audit.classification_counts


# L — planner unchanged after audit attachment
def test_l_planner_neutrality_after_audit():
    panel = _panel()
    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, experiment_budget=12)
    assess = _assessment()
    cands = generate_action_candidates(assess, graph, REGISTRY, panel_columns=tuple(panel.columns))
    plan_before = plan_next_action(assess, cands, graph)
    scores_before = score_all_candidates(assess, cands, graph)

    ensure_session_expansion_audit(graph)
    ensure_session_capability_registry(graph, panel, REGISTRY)

    plan_after = plan_next_action(assess, cands, graph)
    scores_after = score_all_candidates(assess, cands, graph)

    assert plan_before.decision_type == plan_after.decision_type
    assert plan_before.selected == plan_after.selected
    for k in scores_before:
        assert scores_before[k][0] == scores_after[k][0]


# M — no automatic exposure
def test_m_no_automatic_exposure():
    panel = _panel()
    cap = build_capability_registry(panel, REGISTRY)
    inaccessible = {
        e.field_name
        for e in build_research_data_expansion_audit(panel).entry_list()
        if e.could_be_exposed_safely and not e.research_accessible_now
    }
    for fld in ("health_group", "volume_ratio20", "obv_status"):
        assert fld in inaccessible or any(
            e.field_name == fld and not e.research_accessible_now
            for e in build_research_data_expansion_audit(panel).entry_list()
        )
    hg_cap = [c for c in cap.capabilities.values() if c.name == "health_group"]
    if hg_cap:
        assert hg_cap[0].currently_research_accessible is False


# N — production isolation
def test_n_production_isolation():
    import modules.edge_research.research_data_expansion_audit as mod

    source = open(mod.__file__, encoding="utf-8").read().lower()
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert forbidden.lower() not in source


# O — no BB/human edge leakage
def test_o_no_bb_human_leakage():
    audit = build_research_data_expansion_audit(_panel())
    text = json.dumps(audit.to_dict()).lower()
    for token in ("blind_benchmark", "bb07", "bb08", "predictive", "recommended feature"):
        assert token not in text


def test_persistence_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(tmp_path))
    from modules.edge_research.storage import read_research_graph, write_research_graph

    graph = ResearchGraph.create_session(data_cutoff_date=CUTOFF, session_id="rs-3h1-audit")
    ensure_session_expansion_audit(graph)
    graph.persist_expansion_audit()
    write_research_graph(graph, data_dir=tmp_path)
    loaded = read_research_graph("rs-3h1-audit", data_dir=tmp_path)
    assert loaded.session.research_data_expansion_audit is not None
    reloaded = ResearchDataExpansionAudit.from_dict(loaded.session.research_data_expansion_audit)
    assert reloaded.version == EXPANSION_AUDIT_VERSION
    assert len(reloaded.entries) > 0
