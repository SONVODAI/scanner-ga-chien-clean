"""Phase 3J.6 — Second-experiment design from frozen research decision tests."""

from __future__ import annotations

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


def test_second_experiment_modules_import():
    from modules.edge_research.opr_bridge import second_experiment_pipeline  # noqa: F401
    from modules.edge_research.opr_bridge import production_second_experiment_design  # noqa: F401


def test_cf_sd1_sd10_pass():
    from modules.edge_research.opr_bridge.bb_second_experiment_design_01_fixtures import (
        run_cf_sd_counterfactuals,
    )

    cf = run_cf_sd_counterfactuals()
    assert cf["all_passed"], cf


def test_no_decide_next_action_in_design_pipeline():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "modules/edge_research/opr_bridge"
    targets = list(root.glob("second_experiment*.py"))
    forbidden = {"decide_next_action", "execute_first_experiment"}
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, f"{path.name} calls {node.func.id}"


def test_production_design_stops_at_second_experiment_designed(tmp_data_dir):
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.second_experiment_records import STOP_SECOND_EXPERIMENT_DESIGNED
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle

    panel = _anomaly_panel(seed=42)
    r = run_production_opr_cycle(
        panel,
        data_cutoff_date="2026-02-15",
        data_dir=tmp_data_dir,
        execute_first_experiment=True,
        interpret_first_experiment=True,
        decide_first_experiment=True,
        design_second_experiment=True,
    )
    assert r.outcome == "SESSION_CREATED"
    assert STOP_SECOND_EXPERIMENT_DESIGNED in r.stop_boundaries
    assert r.second_experiment_design is not None
    pkg = (r.second_experiment_design.get("design") or {}).get("package") or {}
    assert pkg.get("execution_status") == "NOT_EXECUTED"
    assert "tool_result" not in pkg


def test_persisted_3j5_state_second_experiment_design(tmp_data_dir):
    if not all(p.exists() for p in (FROZEN_PROP, FROZEN_CONTRACT, J2_DIAG, PERSISTED_EXEC, PANEL)):
        pytest.skip("Persisted artifacts unavailable")

    from diagnostics.phase_3j4_evidence_interpretation.run_phase_3j4 import (
        _package_stub_from_persisted_execution,
    )
    from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
        frozen_ref_from_historical_contract_artifact,
    )
    from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
        STOP_RESEARCH_DECISION_FROZEN,
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
    from modules.edge_research.opr_bridge.second_experiment_records import STOP_SECOND_EXPERIMENT_DESIGNED

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
        prop,
        session_id="j6-persisted",
        package_dict=package_dict,
        execution_dict=execution_dict,
        frozen_contract_dict=frozen_ref.to_dict(),
        data_dir=tmp_data_dir,
    )
    dx = run_production_first_experiment_research_decision(
        prop,
        session_id="j6-persisted",
        package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
        data_dir=tmp_data_dir,
    )
    assert STOP_RESEARCH_DECISION_FROZEN in dx.stop_boundaries

    sx = run_production_second_experiment_design(
        prop,
        panel,
        session_id="j6-persisted",
        package_dict=package_dict,
        execution_dict=execution_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
        data_dir=tmp_data_dir,
    )
    assert STOP_SECOND_EXPERIMENT_DESIGNED in sx.stop_boundaries
    assert sx.design.package is not None
    assert sx.design.package.execution_status == "NOT_EXECUTED"
    obj = sx.design.package.objective
    assert obj.target_null_key == "directional_reversal"
    assert obj.selected_action == "SEEK_FALSIFICATION"
    assert sx.design.package.experiment_ordinal == 2


def test_3j5_regression():
    from modules.edge_research.opr_bridge.bb_first_experiment_research_decision_01_fixtures import (
        run_cf_rd_counterfactuals,
    )

    assert run_cf_rd_counterfactuals()["all_passed"]


def test_3j4_regression():
    from modules.edge_research.opr_bridge.bb_first_experiment_interpretation_01_fixtures import (
        run_cf_int_counterfactuals,
    )

    assert run_cf_int_counterfactuals()["all_passed"]


def test_3j3_regression():
    from modules.edge_research.opr_bridge.bb_first_experiment_execution_01_fixtures import run_cf_ex_counterfactuals

    assert run_cf_ex_counterfactuals()["all_passed"]


def test_3j2_regression():
    from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import run_all_bbfe

    assert run_all_bbfe()["all_passed"]


def test_frozen_scientific_hashes_unchanged():
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash as sag_hash
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import integration_content_hash

    assert engine_content_hash() == "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a"
    assert sag_hash() == "77e665c720b3f8c5050ff1113d076c38cd2c678db8df6773711e665e3fcc7eb9"
    assert dormancy_content_hash() == "a6a70005511d5894ec0fbcead9ad5b4589ce3162cbe01b7c761a12026b9adfa6"
    assert integration_content_hash() == "409f55fd2490cd5f9635bc9c8e1bb946a02f37868591efa2dffd4691d07b1145"


def test_no_hidden_answer_in_design_modules():
    root = REPO / "modules/edge_research/opr_bridge"
    files = list(root.glob("second_experiment*.py")) + list(root.glob("production_second_experiment*.py"))
    hits = []
    for f in files:
        text = f.read_text(encoding="utf-8").lower()
        for tok in ("2026-08-02", "july 27", "hidden_phenomenon", "prop-efb650d9bd5c451f"):
            if tok in text:
                hits.append((f.name, tok))
    assert not hits, hits
