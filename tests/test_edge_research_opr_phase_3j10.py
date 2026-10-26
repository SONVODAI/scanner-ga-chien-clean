"""Phase 3J.10 — Bounded autonomous research lifecycle tests."""

from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
FROZEN_PROP = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json"
FROZEN_CONTRACT = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/03_interpretation_contract.json"
J2_DIAG = REPO / "diagnostics/phase_3j2_first_experiment_selection/artifacts/03_real_proposition_diagnostic.json"
PERSISTED_EXEC = (
    REPO / "diagnostics/phase_3j4_evidence_interpretation/artifacts/05_persisted_3j3_execution_envelope.json"
)


@pytest.fixture
def tmp_data_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_bounded_lifecycle_modules_import():
    from modules.edge_research.opr_bridge import bounded_lifecycle_controller  # noqa: F401
    from modules.edge_research.opr_bridge import production_bounded_lifecycle  # noqa: F401


def test_cf_arl1_arl12_pass():
    from modules.edge_research.opr_bridge.bb_bounded_autonomous_lifecycle_01_fixtures import (
        run_cf_arl_counterfactuals,
    )

    cf = run_cf_arl_counterfactuals()
    assert cf["all_passed"], cf


def test_no_experiment_pipeline_in_controller():
    root = REPO / "modules/edge_research/opr_bridge"
    targets = [
        root / "bounded_lifecycle_controller.py",
        root / "production_bounded_lifecycle.py",
    ]
    forbidden = {"run_first_experiment_pipeline", "run_second_experiment_design_pipeline"}
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, f"{path.name} calls {node.func.id}"


def test_fresh_bounded_lifecycle(tmp_data_dir):
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import (
        ResearchBudget,
        STOP_LIFECYCLE_BOUNDED,
    )
    from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
    from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity

    panel = _anomaly_panel(seed=42)
    det = detect_production_opportunity(panel, data_cutoff_date="2026-02-15")
    if det.outcome != "OPPORTUNITY_DETECTED":
        pytest.skip("No opportunity on synthetic panel")
    r = run_bounded_autonomous_research(
        det.proposition_record,
        panel,
        data_cutoff_date="2026-02-15",
        data_dir=tmp_data_dir,
        budget=ResearchBudget(max_experiment_iterations=2),
        bootstrap_new_session=True,
    )
    assert r.lifecycle is not None
    assert STOP_LIFECYCLE_BOUNDED in r.stop_boundaries or r.lifecycle.outcome in (
        "SCIENTIFIC_STOP",
        "BUDGET_EXHAUSTED",
        "FAILED_CLOSED",
    )
    assert r.session_record is not None
    assert r.session_record.bounded_lifecycle_enabled is True


def test_stop_resume_real_journey_no_experiment_three(tmp_data_dir):
    if not all(p.exists() for p in (FROZEN_PROP, FROZEN_CONTRACT, J2_DIAG, PERSISTED_EXEC, PANEL)):
        pytest.skip("Persisted artifacts unavailable")

    from diagnostics.phase_3j4_evidence_interpretation.run_phase_3j4 import (
        _package_stub_from_persisted_execution,
    )
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import (
        LifecyclePhase,
        ResearchBudget,
        STOP_LIFECYCLE_BOUNDED,
        STOP_LIFECYCLE_SCIENTIFIC_STOP,
    )
    from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
        frozen_ref_from_historical_contract_artifact,
    )
    from modules.edge_research.opr_bridge.production_bounded_lifecycle import (
        materialize_session_from_chain,
        run_bounded_autonomous_research,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_interpretation import (
        run_production_first_experiment_interpretation,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_research_decision import (
        run_production_first_experiment_research_decision,
    )
    from modules.edge_research.opr_bridge.production_orchestrator import new_production_session_id
    from modules.edge_research.opr_bridge.production_persistence import (
        OprProductionSessionRecord,
        write_opr_session,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_design import (
        run_production_second_experiment_design,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_execution import (
        run_production_second_experiment_execution,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_interpretation import (
        run_production_second_experiment_interpretation,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_research_decision import (
        run_production_second_experiment_research_decision,
    )
    from modules.edge_research.opr_bridge.second_experiment_research_decision_records import (
        STOP_SECOND_RESEARCH_DECISION_FROZEN,
    )

    prop = json.loads(FROZEN_PROP.read_text())["full_record"]
    execution_dict = json.loads(PERSISTED_EXEC.read_text())
    j2_package = json.loads(J2_DIAG.read_text())["package"]
    hist_contract = json.loads(FROZEN_CONTRACT.read_text())
    package_dict = _package_stub_from_persisted_execution(execution_dict, j2_package)
    frozen_ref = frozen_ref_from_historical_contract_artifact(
        hist_contract,
        package_id=execution_dict["package_id"],
        experiment_content_hash=execution_dict["experiment_content_hash"],
        scientific_action_core_hash=execution_dict["scientific_action_core_hash"],
    )
    panel = pd.read_csv(PANEL)
    session_id = new_production_session_id(prop["proposition_id"])

    record = OprProductionSessionRecord(
        session_id=session_id,
        opportunity_identity="resume-test",
        replay_identity="replay-test",
        proposition_id=prop["proposition_id"],
        proposition_hash=prop.get("proposition_hash", ""),
        data_cutoff_date="2026-02-15",
        evidence_cutoff_hash="test",
        proposition_record=prop,
        initial_experiment_package=package_dict,
        first_experiment_execution=execution_dict,
        frozen_interpretation_contract=frozen_ref.to_dict(),
    )
    write_opr_session(record, data_dir=tmp_data_dir)

    ix = run_production_first_experiment_interpretation(
        prop, session_id=session_id, package_dict=package_dict,
        execution_dict=execution_dict, frozen_contract_dict=frozen_ref.to_dict(), data_dir=tmp_data_dir,
    )
    record.first_experiment_interpretation = ix.interpretation.envelope.to_dict()
    dx = run_production_first_experiment_research_decision(
        prop, session_id=session_id, package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(), data_dir=tmp_data_dir,
    )
    record.first_experiment_research_decision = dx.decision.envelope.to_dict()
    sx = run_production_second_experiment_design(
        prop, panel, session_id=session_id, package_dict=package_dict,
        execution_dict=execution_dict, interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(), data_dir=tmp_data_dir,
    )
    record.second_experiment_package = sx.design.package.to_dict()
    ex2 = run_production_second_experiment_execution(
        prop, panel, session_id=session_id, package_dict=sx.design.package.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(), first_execution_dict=execution_dict,
        data_dir=tmp_data_dir,
    )
    record.second_experiment_execution = ex2.execution.envelope.to_dict()
    ix2 = run_production_second_experiment_interpretation(
        prop, session_id=session_id, package_dict=sx.design.package.to_dict(),
        execution_dict=ex2.execution.envelope.to_dict(),
        first_interpretation_dict=ix.interpretation.envelope.to_dict(), data_dir=tmp_data_dir,
    )
    record.second_experiment_interpretation = ix2.interpretation.envelope.to_dict()
    dx2 = run_production_second_experiment_research_decision(
        prop, session_id=session_id,
        second_interpretation_dict=ix2.interpretation.envelope.to_dict(),
        first_decision_dict=dx.decision.envelope.to_dict(),
        first_interpretation_dict=ix.interpretation.envelope.to_dict(),
        data_dir=tmp_data_dir,
    )
    record.second_experiment_research_decision = dx2.decision.envelope.to_dict()
    record.stop_boundaries_reached.append(STOP_SECOND_RESEARCH_DECISION_FROZEN)
    materialize_session_from_chain(record, data_dir=tmp_data_dir)

    assert dx2.decision.envelope.decision_kind == "STOP"
    assert dx2.decision.envelope.stop_reason == "STOP_LOW_INCREMENTAL"

    r = run_bounded_autonomous_research(
        prop,
        panel,
        session_id=session_id,
        data_cutoff_date="2026-02-15",
        data_dir=tmp_data_dir,
        budget=ResearchBudget(max_experiment_iterations=5),
    )
    assert r.lifecycle.outcome == "SCIENTIFIC_STOP"
    assert r.lifecycle.experiments_completed == 2
    assert r.session_record.second_experiment_package is not None
    assert r.session_record.lifecycle_phase == LifecyclePhase.STOPPED
    assert STOP_LIFECYCLE_SCIENTIFIC_STOP in r.stop_boundaries or STOP_LIFECYCLE_BOUNDED in r.stop_boundaries
    assert not any(
        e.get("ordinal", 0) >= 3 for e in (r.session_record.experiment_history or [])
    )


def test_3j9_regression_still_passes():
    from modules.edge_research.opr_bridge.bb_cumulative_research_decision_01_fixtures import (
        run_cf_cd_counterfactuals,
    )

    assert run_cf_cd_counterfactuals()["all_passed"]


def test_frozen_scientific_hashes_unchanged():
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash as sag_hash
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import integration_content_hash

    assert engine_content_hash() == "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a"
    assert sag_hash() == "77e665c720b3f8c5050ff1113d076c38cd2c678db8df6773711e665e3fcc7eb9"
    assert dormancy_content_hash() == "a6a70005511d5894ec0fbcead9ad5b4589ce3162cbe01b7c761a12026b9adfa6"
    assert integration_content_hash() == "409f55fd2490cd5f9635bc9c8e1bb946a02f37868591efa2dffd4691d07b1145"


def test_no_hidden_answer_in_lifecycle_modules():
    root = REPO / "modules/edge_research/opr_bridge"
    files = list(root.glob("bounded_lifecycle*.py")) + [
        root / "production_bounded_lifecycle.py",
        root / "bb_bounded_autonomous_lifecycle_01_fixtures.py",
    ]
    hits = []
    for f in files:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8").lower()
        for tok in ("2026-08-02", "july 27", "hidden_phenomenon", "prop-efb650d9bd5c451f"):
            if tok in text:
                hits.append((f.name, tok))
    assert not hits, hits
