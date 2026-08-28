"""Phase 3J.0 — Production OPR lifecycle integration tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_data_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def anomaly_panel():
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel

    return _anomaly_panel(seed=42)


@pytest.fixture
def silent_panel():
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _silent_panel

    return _silent_panel(seed=99)


def test_production_modules_import():
    from modules.edge_research.opr_bridge import production_orchestrator  # noqa: F401
    from modules.edge_research.opr_bridge import production_persistence  # noqa: F401
    from modules.edge_research.opr_bridge import production_trigger  # noqa: F401
    from modules.edge_research.opr_bridge import production_authority  # noqa: F401


@pytest.mark.parametrize(
    "case",
    __import__(
        "modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures",
        fromlist=["all_bbpa_cases"],
    ).all_bbpa_cases(),
    ids=lambda c: c["case_id"],
)
def test_bb_production_autonomy_01(case, tmp_data_dir):
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import (
        evaluate_bbpa_case,
        run_bbpa_case,
    )

    run = run_bbpa_case(case, tmp_data_dir=tmp_data_dir)
    ev = evaluate_bbpa_case(case, run)
    assert ev["passed"], f"{case['case_id']} failed: {ev['checks']}"


def test_cf_j1_identical_evidence_replay(anomaly_panel, tmp_data_dir):
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle

    r1 = run_production_opr_cycle(anomaly_panel, data_cutoff_date="2026-02-15", data_dir=tmp_data_dir)
    r2 = run_production_opr_cycle(anomaly_panel, data_cutoff_date="2026-02-15", data_dir=tmp_data_dir)
    assert r1.outcome == "SESSION_CREATED"
    assert r2.outcome == "NO_NEW_RESEARCH_OPPORTUNITY"
    assert r2.idempotent_skip is True


def test_cf_j2_no_eligible_observation(silent_panel, tmp_data_dir):
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle

    r = run_production_opr_cycle(silent_panel, data_cutoff_date="2026-02-15", data_dir=tmp_data_dir)
    assert r.outcome in ("SILENT", "NO_ELIGIBLE_OBSERVATION")


def test_cf_j3_process_restart(anomaly_panel, tmp_data_dir):
    from modules.edge_research.opr_bridge.production_orchestrator import (
        run_production_opr_cycle,
        simulate_process_restart,
    )

    r = run_production_opr_cycle(anomaly_panel, data_cutoff_date="2026-02-15", data_dir=tmp_data_dir)
    assert r.session_id
    restart = simulate_process_restart(r.session_id, data_dir=tmp_data_dir)
    assert restart["session_id"] == r.session_id
    assert restart["authoritative_state"]["proposition_id"]


def test_cf_j4_legacy_planner_disagreement():
    from modules.edge_research.opr_bridge.production_authority import (
        OprLegacyPlannerBlockedError,
        assert_legacy_planner_blocked,
        mark_session_opr_authority,
    )
    from modules.edge_research.research_graph import ResearchGraph

    graph = ResearchGraph.create_session(
        data_cutoff_date="2026-02-15",
        guardrails_config_version="guardrails_v1",
    )
    mark_session_opr_authority(graph)
    with pytest.raises(OprLegacyPlannerBlockedError):
        assert_legacy_planner_blocked(graph)


def test_cf_j5_dormant_redundant_evidence(tmp_data_dir):
    from modules.edge_research.opr_bridge.dormancy_records import ReopeningEvaluationOutcome
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import ResearchOpportunityState
    from modules.edge_research.opr_bridge.production_orchestrator import (
        T2_CANONICAL_PROPOSITION_ID,
        run_production_opr_cycle,
    )

    panel_path = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
    if not panel_path.exists():
        pytest.skip("Blind panel not available")
    panel = pd.read_csv(panel_path)
    r = run_production_opr_cycle(
        panel,
        data_cutoff_date="2026-08-17",
        data_dir=tmp_data_dir,
        replay_frozen_lineage=True,
    )
    assert r.outcome == "SESSION_CREATED"
    assert r.authoritative_state.get("research_activity_state") == "DORMANT"

    from modules.edge_research.opr_bridge.production_persistence import read_opr_session, deserialize_knowledge_state
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import on_research_opportunity_state_changed

    record = read_opr_session(r.session_id, tmp_data_dir)
    state = deserialize_knowledge_state(record.knowledge_state)
    opp = ResearchOpportunityState(
        proposition_id=T2_CANONICAL_PROPOSITION_ID,
        proposition_hash=record.proposition_hash,
        identical_evidence_added=True,
        max_cohort_overlap=0.99,
    )
    hook = on_research_opportunity_state_changed(record.proposition_record, state, opp)
    assert hook.evaluation_result.outcome == ReopeningEvaluationOutcome.REMAIN_DORMANT


def test_cf_j6_dormant_qualifying_opportunity(tmp_data_dir):
    from modules.edge_research.opr_bridge.dormancy_records import ReopeningEvaluationOutcome
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import ResearchOpportunityState
    from modules.edge_research.opr_bridge.production_orchestrator import (
        T2_CANONICAL_PROPOSITION_ID,
        run_production_opr_cycle,
    )

    panel_path = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
    if not panel_path.exists():
        pytest.skip("Blind panel not available")
    panel = pd.read_csv(panel_path)
    r = run_production_opr_cycle(
        panel,
        data_cutoff_date="2026-08-17",
        data_dir=tmp_data_dir,
        replay_frozen_lineage=True,
    )
    from modules.edge_research.opr_bridge.production_persistence import read_opr_session, deserialize_knowledge_state
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import on_research_opportunity_state_changed

    record = read_opr_session(r.session_id, tmp_data_dir)
    state = deserialize_knowledge_state(record.knowledge_state)
    opp = ResearchOpportunityState(
        proposition_id=T2_CANONICAL_PROPOSITION_ID,
        proposition_hash=record.proposition_hash,
        max_cohort_overlap=0.15,
        overlap_relation_to_prior="disjoint",
    )
    hook = on_research_opportunity_state_changed(record.proposition_record, state, opp)
    assert hook.evaluation_result.outcome == ReopeningEvaluationOutcome.REOPEN_RESEARCH
    assert state.research_activity_state == "REOPEN_CANDIDATE"


def test_cf_j7_forbidden_input_unchanged(anomaly_panel, tmp_data_dir):
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle

    r = run_production_opr_cycle(anomaly_panel, data_cutoff_date="2026-02-15", data_dir=tmp_data_dir)
    assert r.frozen_integrity["passed"] is True
    assert "zone_c" not in json.dumps(r.to_dict()).lower()


def test_cf_j8_execution_unavailable_stops_safely(anomaly_panel, tmp_data_dir):
    from modules.edge_research.opr_bridge.production_orchestrator import (
        STOP_NO_AUTO_EXPERIMENT,
        run_production_opr_cycle,
    )

    r = run_production_opr_cycle(anomaly_panel, data_cutoff_date="2026-02-15", data_dir=tmp_data_dir)
    assert STOP_NO_AUTO_EXPERIMENT in r.stop_boundaries
    assert r.detection is not None
    record = r.session_record
    assert record is not None
    assert record.knowledge_state is not None


def test_frozen_scientific_hashes_unchanged():
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import integration_content_hash

    assert engine_content_hash() == "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a"
    assert generator_content_hash() == "77e665c720b3f8c5050ff1113d076c38cd2c678db8df6773711e665e3fcc7eb9"
    assert dormancy_content_hash() == "a6a70005511d5894ec0fbcead9ad5b4589ce3162cbe01b7c761a12026b9adfa6"
    assert integration_content_hash() == "409f55fd2490cd5f9635bc9c8e1bb946a02f37868591efa2dffd4691d07b1145"


def test_trading_isolation_audit():
    """OPR production modules must not import trading systems."""
    import ast

    opr_dir = REPO / "modules/edge_research/opr_bridge"
    prod_files = [
        "production_authority.py",
        "production_persistence.py",
        "production_trigger.py",
        "production_orchestrator.py",
    ]
    forbidden = ("market_first", "earning", "sweetspot", "position_guardian")
    for name in prod_files:
        tree = ast.parse((opr_dir / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(f in alias.name.lower() for f in forbidden), alias.name
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(f in node.module.lower() for f in forbidden), node.module


def test_opr_production_entrypoint(anomaly_panel, tmp_data_dir):
    from modules.edge_research.autonomous_research import run_opr_production_research_cycle
    from modules.edge_research.opr_bridge.production_authority import session_has_opr_authority

    result = run_opr_production_research_cycle(
        anomaly_panel,
        data_cutoff_date="2026-02-15",
        data_dir=tmp_data_dir,
        enabled=True,
    )
    assert result.cycle_result.outcome == "SESSION_CREATED"
    assert result.graph is not None
    assert session_has_opr_authority(result.graph)
