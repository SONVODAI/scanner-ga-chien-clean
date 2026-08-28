"""Phase 3J.7 — Second-experiment execution tests."""

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


def test_second_experiment_execution_modules_import():
    from modules.edge_research.opr_bridge import second_experiment_executor  # noqa: F401
    from modules.edge_research.opr_bridge import production_second_experiment_execution  # noqa: F401


def test_cf_se1_se10_pass():
    from modules.edge_research.opr_bridge.bb_second_experiment_execution_01_fixtures import (
        run_cf_se_counterfactuals,
    )

    cf = run_cf_se_counterfactuals()
    assert cf["all_passed"], cf


def test_no_interpretation_in_execution_pipeline():
    root = Path(__file__).resolve().parents[1] / "modules/edge_research/opr_bridge"
    targets = list(root.glob("second_experiment_execution*.py")) + [
        root / "second_experiment_executor.py",
        root / "production_second_experiment_execution.py",
    ]
    forbidden = {
        "interpret_first_experiment_evidence",
        "decide_first_experiment_research_action",
        "decide_next_action",
        "run_second_experiment_design_pipeline",
    }
    for path in targets:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, f"{path.name} calls {node.func.id}"


def test_production_execution_stops_at_second_experiment_executed(tmp_data_dir):
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle
    from modules.edge_research.opr_bridge.second_experiment_execution_records import (
        STOP_SECOND_EXPERIMENT_EXECUTED,
    )
    from modules.edge_research.opr_bridge.second_experiment_records import STOP_SECOND_EXPERIMENT_DESIGNED

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
    )
    assert r.outcome == "SESSION_CREATED"
    assert STOP_SECOND_EXPERIMENT_DESIGNED in r.stop_boundaries
    assert STOP_SECOND_EXPERIMENT_EXECUTED in r.stop_boundaries
    assert r.second_experiment_execution is not None
    exec_d = r.second_experiment_execution.get("execution") or {}
    env = exec_d.get("envelope") or {}
    assert env.get("experiment_ordinal") == 2
    assert env.get("interpretation_generated") is False
    assert env.get("research_decision_generated") is False
    assert "evidence_assessment" not in str(env)


def test_persisted_real_diagnostic_second_experiment_execution(tmp_data_dir):
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
    from modules.edge_research.opr_bridge.second_experiment_execution_records import (
        STOP_SECOND_EXPERIMENT_EXECUTED,
    )
    from modules.edge_research.opr_bridge.second_experiment_records import STOP_SECOND_EXPERIMENT_DESIGNED

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
        session_id="j7-persisted",
        package_dict=package_dict,
        execution_dict=execution_dict,
        frozen_contract_dict=frozen_ref.to_dict(),
        data_dir=tmp_data_dir,
    )
    dx = run_production_first_experiment_research_decision(
        prop,
        session_id="j7-persisted",
        package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
        data_dir=tmp_data_dir,
    )
    sx = run_production_second_experiment_design(
        prop,
        panel,
        session_id="j7-persisted",
        package_dict=package_dict,
        execution_dict=execution_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
        data_dir=tmp_data_dir,
    )
    assert STOP_SECOND_EXPERIMENT_DESIGNED in sx.stop_boundaries
    pkg = sx.design.package
    assert pkg is not None
    assert pkg.objective.target_null_key == "directional_reversal"
    assert pkg.execution_status == "NOT_EXECUTED"

    ex2 = run_production_second_experiment_execution(
        prop,
        panel,
        session_id="j7-persisted",
        package_dict=pkg.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(),
        first_execution_dict=execution_dict,
        data_dir=tmp_data_dir,
    )
    assert STOP_SECOND_EXPERIMENT_EXECUTED in ex2.stop_boundaries
    assert ex2.execution is not None
    assert ex2.execution.envelope is not None
    env = ex2.execution.envelope
    assert env.experiment_ordinal == 2
    assert env.target_null_key == "directional_reversal"
    assert env.interpretation_generated is False
    nd = env.novelty_decomposition
    assert nd.get("NULL_TARGET_OVERLAP") == 0.0
    assert nd.get("coarse_redundancy_interpretation") == "HIGH_SAMPLE_REUSE_NEW_QUESTION"


def test_idempotent_second_execution(tmp_data_dir):
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
        prop, session_id="idempotent-se", package_dict=package_dict,
        execution_dict=execution_dict, frozen_contract_dict=frozen_ref.to_dict(),
        data_dir=tmp_data_dir,
    )
    dx = run_production_first_experiment_research_decision(
        prop, session_id="idempotent-se", package_dict=package_dict,
        interpretation_dict=ix.interpretation.envelope.to_dict(), data_dir=tmp_data_dir,
    )
    sx = run_production_second_experiment_design(
        prop, panel, session_id="idempotent-se", package_dict=package_dict,
        execution_dict=execution_dict, interpretation_dict=ix.interpretation.envelope.to_dict(),
        decision_dict=dx.decision.envelope.to_dict(), data_dir=tmp_data_dir,
    )
    pkg_dict = sx.design.package.to_dict()

    ex1 = run_production_second_experiment_execution(
        prop, panel, session_id="idempotent-se", package_dict=pkg_dict,
        decision_dict=dx.decision.envelope.to_dict(),
        first_execution_dict=execution_dict, data_dir=tmp_data_dir,
    )
    ex2 = run_production_second_experiment_execution(
        prop, panel, session_id="idempotent-se", package_dict=pkg_dict,
        decision_dict=dx.decision.envelope.to_dict(),
        first_execution_dict=execution_dict, data_dir=tmp_data_dir,
    )
    assert ex1.execution.envelope is not None
    assert ex2.idempotent_replay is True
    assert ex2.execution.outcome == "IDEMPOTENT_REPLAY"
    assert ex1.execution.envelope.execution_id == ex2.execution.envelope.execution_id


def test_hidden_answer_firewall_second_execution():
    root = Path(__file__).resolve().parents[1] / "modules/edge_research/opr_bridge"
    forbidden = ["july 27", "july_27", "t3_return", "t10_return", "expected_outcome", "known_answer"]
    for path in root.glob("second_experiment_execution*.py"):
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            assert tok not in blob, f"hidden-answer token {tok} in {path.name}"
    for path in (root / "second_experiment_executor.py", root / "production_second_experiment_execution.py"):
        blob = path.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            assert tok not in blob, f"hidden-answer token {tok} in {path.name}"
