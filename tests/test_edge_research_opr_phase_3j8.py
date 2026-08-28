"""Phase 3J.8 — Multi-evidence interpretation & EpistemicUpdate #2 tests."""

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
J7_DIAG = REPO / "diagnostics/phase_3j7_second_experiment_execution/artifacts/03_real_diagnostic.json"


@pytest.fixture
def tmp_data_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_second_experiment_interpretation_modules_import():
    from modules.edge_research.opr_bridge import second_experiment_evidence_interpreter  # noqa: F401
    from modules.edge_research.opr_bridge import production_second_experiment_interpretation  # noqa: F401


def test_cf_mei1_mei10_pass():
    from modules.edge_research.opr_bridge.bb_multi_evidence_interpretation_01_fixtures import (
        run_cf_mei_counterfactuals,
    )

    cf = run_cf_mei_counterfactuals()
    assert cf["all_passed"], cf


def test_no_research_decision_in_interpretation_pipeline():
    root = Path(__file__).resolve().parents[1] / "modules/edge_research/opr_bridge"
    targets = list(root.glob("second_experiment_*interpret*.py")) + [
        root / "multi_evidence_accounting.py",
        root / "production_second_experiment_interpretation.py",
    ]
    forbidden = {
        "decide_first_experiment_research_action",
        "decide_next_action",
        "run_second_experiment_design_pipeline",
        "execute_second_experiment",
    }
    for path in targets:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, f"{path.name} calls {node.func.id}"


def test_production_stops_at_second_evidence_interpreted(tmp_data_dir):
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle
    from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
        STOP_SECOND_EVIDENCE_INTERPRETED,
    )

    panel = _anomaly_panel(seed=42)
    r = run_production_opr_cycle(
        panel,
        data_cutoff_date="2026-02-15",
        data_dir=tmp_data_dir,
        execute_first_experiment=True,
        interpret_first_experiment=True,
        decide_first_experiment=True,
        design_second_experiment=True,
        execute_second_experiment=True,
        interpret_second_experiment=True,
    )
    assert r.outcome == "SESSION_CREATED"
    assert STOP_SECOND_EVIDENCE_INTERPRETED in r.stop_boundaries
    assert r.second_experiment_interpretation is not None
    interp = (r.second_experiment_interpretation.get("interpretation") or {}).get("envelope") or {}
    assert interp.get("experiment_ordinal") == 2
    assert interp.get("research_decision_generated") is False
    assert "cumulative_assessment" in interp


def test_persisted_real_diagnostic_multi_evidence_interpretation(tmp_data_dir):
    if not all(p.exists() for p in (FROZEN_PROP, FROZEN_CONTRACT, J2_DIAG, PERSISTED_EXEC, PANEL)):
        pytest.skip("Persisted artifacts unavailable")

    from diagnostics.phase_3j4_evidence_interpretation.run_phase_3j4 import (
        _package_stub_from_persisted_execution,
    )
    from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
        frozen_ref_from_historical_contract_artifact,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_interpretation import (
        run_production_first_experiment_interpretation,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_research_decision import (
        run_production_first_experiment_research_decision,
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
    from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
        STOP_SECOND_EVIDENCE_INTERPRETED,
    )

    prop = json.loads(FROZEN_PROP.read_text())["full_record"]
    assert prop["proposition_id"] == "prop-efb650d9bd5c451f"
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

    ix = run_production_first_experiment_interpretation(
        prop,
        session_id="j8-persisted",
        package_dict=package_dict,
        execution_dict=execution_dict,
        frozen_contract_dict=frozen_ref.to_dict(),
        data_dir=tmp_data_dir,
    )
    dx = run_production_first_experiment_research_decision(
        prop,
        session_id="j8-persisted",
        package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
        data_dir=tmp_data_dir,
    )
    sx = run_production_second_experiment_design(
        prop,
        panel,
        session_id="j8-persisted",
        package_dict=package_dict,
        execution_dict=execution_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
        data_dir=tmp_data_dir,
    )
    ex2 = run_production_second_experiment_execution(
        prop,
        panel,
        session_id="j8-persisted",
        package_dict=sx.design.package.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
        first_execution_dict=execution_dict,
        data_dir=tmp_data_dir,
    )
    assert ex2.execution.envelope is not None

    ix2 = run_production_second_experiment_interpretation(
        prop,
        session_id="j8-persisted",
        package_dict=sx.design.package.to_dict(),
        execution_dict=ex2.execution.envelope.to_dict(),
        first_interpretation_dict=ix.interpretation.envelope.to_dict(),
        data_dir=tmp_data_dir,
    )
    assert STOP_SECOND_EVIDENCE_INTERPRETED in ix2.stop_boundaries
    env = ix2.interpretation.envelope
    assert env is not None
    assert env.prior_epistemic_state == ix.interpretation.envelope.resulting_epistemic_state
    cum = env.cumulative_assessment
    assert cum.dependence_accounting.row_overlap_fraction >= 0.9
    assert not cum.dependence_accounting.counted_as_independent_replication
    assert env.research_decision_generated is False


def test_idempotent_second_interpretation(tmp_data_dir):
    if not all(p.exists() for p in (FROZEN_PROP, FROZEN_CONTRACT, J2_DIAG, PERSISTED_EXEC, PANEL)):
        pytest.skip("Persisted artifacts unavailable")

    from diagnostics.phase_3j4_evidence_interpretation.run_phase_3j4 import (
        _package_stub_from_persisted_execution,
    )
    from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
        frozen_ref_from_historical_contract_artifact,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_interpretation import (
        run_production_first_experiment_interpretation,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_design import (
        run_production_second_experiment_design,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_research_decision import (
        run_production_first_experiment_research_decision,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_execution import (
        run_production_second_experiment_execution,
    )
    from modules.edge_research.opr_bridge.production_second_experiment_interpretation import (
        run_production_second_experiment_interpretation,
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

    ix = run_production_first_experiment_interpretation(
        prop, session_id="j8-idem", package_dict=package_dict,
        execution_dict=execution_dict, frozen_contract_dict=frozen_ref.to_dict(), data_dir=tmp_data_dir,
    )
    dx = run_production_first_experiment_research_decision(
        prop, session_id="j8-idem", package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(), data_dir=tmp_data_dir,
    )
    sx = run_production_second_experiment_design(
        prop, panel, session_id="j8-idem", package_dict=package_dict,
        execution_dict=execution_dict, interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(), data_dir=tmp_data_dir,
    )
    ex2 = run_production_second_experiment_execution(
        prop, panel, session_id="j8-idem", package_dict=sx.design.package.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(), first_execution_dict=execution_dict,
        data_dir=tmp_data_dir,
    )
    pkg = sx.design.package.to_dict()
    exec_d = ex2.execution.envelope.to_dict()
    ix1_d = ix.interpretation.envelope.to_dict()

    r1 = run_production_second_experiment_interpretation(
        prop, session_id="j8-idem", package_dict=pkg, execution_dict=exec_d,
        first_interpretation_dict=ix1_d, data_dir=tmp_data_dir,
    )
    r2 = run_production_second_experiment_interpretation(
        prop, session_id="j8-idem", package_dict=pkg, execution_dict=exec_d,
        first_interpretation_dict=ix1_d, data_dir=tmp_data_dir,
    )
    assert r1.interpretation.envelope is not None
    assert r2.idempotent_replay is True
    assert r1.interpretation.envelope.interpretation_id == r2.interpretation.envelope.interpretation_id


def test_hidden_answer_firewall_second_interpretation():
    root = Path(__file__).resolve().parents[1] / "modules/edge_research/opr_bridge"
    forbidden = ["july 27", "july_27", "2.352", "expected_state", "directional_answer", "known_answer"]
    for path in list(root.glob("second_experiment_*interpret*.py")) + [root / "multi_evidence_accounting.py"]:
        if not path.exists():
            continue
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            assert tok not in blob, f"hidden-answer token {tok} in {path.name}"
