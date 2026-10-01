"""Phase 3J.3 — First-experiment execution integration tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
FROZEN_PROP = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json"


@pytest.fixture
def tmp_data_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_execution_modules_import():
    from modules.edge_research.opr_bridge import first_experiment_execution_gate  # noqa: F401
    from modules.edge_research.opr_bridge import first_experiment_executor  # noqa: F401
    from modules.edge_research.opr_bridge import production_first_experiment_execution  # noqa: F401


def test_bbfex_all_cases():
    from modules.edge_research.opr_bridge.bb_first_experiment_execution_01_fixtures import run_all_bbfex

    result = run_all_bbfex()
    assert result["all_passed"], result["cases"]


def test_cf_ex1_ex8_pass():
    from modules.edge_research.opr_bridge.bb_first_experiment_execution_01_fixtures import run_cf_ex_counterfactuals

    cf = run_cf_ex_counterfactuals()
    assert cf["all_passed"], cf["counterfactuals"]


def test_frozen_scientific_hashes_unchanged():
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash as sag_hash
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import integration_content_hash

    assert engine_content_hash() == "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a"
    assert sag_hash() == "77e665c720b3f8c5050ff1113d076c38cd2c678db8df6773711e665e3fcc7eb9"
    assert dormancy_content_hash() == "a6a70005511d5894ec0fbcead9ad5b4589ce3162cbe01b7c761a12026b9adfa6"
    assert integration_content_hash() == "409f55fd2490cd5f9635bc9c8e1bb946a02f37868591efa2dffd4691d07b1145"


def test_production_orchestrator_3j0_regression_without_execution(tmp_data_dir):
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.production_orchestrator import (
        STOP_NO_AUTO_EXPERIMENT,
        STOP_PROPOSITION_PERSISTED,
        run_production_opr_cycle,
    )

    panel = _anomaly_panel(seed=42)
    r = run_production_opr_cycle(panel, data_cutoff_date="2026-02-15", data_dir=tmp_data_dir)
    assert r.outcome == "SESSION_CREATED"
    assert STOP_PROPOSITION_PERSISTED in r.stop_boundaries
    assert STOP_NO_AUTO_EXPERIMENT in r.stop_boundaries
    assert r.first_experiment is None


def test_production_execution_stops_at_first_experiment_executed(tmp_data_dir):
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.first_experiment_execution_records import STOP_FIRST_EXPERIMENT_EXECUTED
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle

    panel = _anomaly_panel(seed=42)
    r = run_production_opr_cycle(
        panel,
        data_cutoff_date="2026-02-15",
        data_dir=tmp_data_dir,
        execute_first_experiment=True,
    )
    assert r.outcome == "SESSION_CREATED"
    assert STOP_FIRST_EXPERIMENT_EXECUTED in r.stop_boundaries
    assert r.first_experiment is not None
    if r.first_experiment.get("execution", {}).get("envelope"):
        env = r.first_experiment["execution"]["envelope"]
        assert "hypothesis_verdict" not in env
        assert "edge_confirmed" not in str(env)


def test_real_t2_diagnostic_execution():
    if not PANEL.exists() or not FROZEN_PROP.exists():
        pytest.skip("Frozen proposition or panel unavailable")

    from modules.edge_research.opr_bridge.first_experiment_execution_records import STOP_FIRST_EXPERIMENT_EXECUTED
    from modules.edge_research.opr_bridge.production_first_experiment_execution import (
        run_production_first_experiment_execution,
    )

    prop = json.loads(FROZEN_PROP.read_text())["full_record"]
    panel = pd.read_csv(PANEL)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]

    result = run_production_first_experiment_execution(
        prop,
        panel,
        session_id="test-3j3-real",
        data_cutoff_date=cutoff,
    )
    assert STOP_FIRST_EXPERIMENT_EXECUTED in result.stop_boundaries
    assert result.package_dict is not None
    exec_d = result.execution.to_dict() if result.execution else {}
    assert exec_d.get("stop_boundary") == STOP_FIRST_EXPERIMENT_EXECUTED
    if exec_d.get("envelope"):
        audit = exec_d["envelope"]["binding_audit"]
        assert audit["scientific_action_core_hash"] == exec_d["envelope"]["scientific_action_core_hash"]


def test_3j2_regression_bbfe():
    from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import run_all_bbfe

    bb = run_all_bbfe()
    assert bb["all_passed"]

def test_no_hidden_answer_encoding_in_execution_modules():
    import subprocess

    patterns = ["2026-08-02", "zone_c", "hidden_phenomenon", "july 27", "T3/T5/T10"]
    root = REPO / "modules/edge_research/opr_bridge"
    files = list(root.glob("first_experiment_execution*.py")) + list(root.glob("production_first_experiment*.py"))
    hits = []
    for f in files:
        text = f.read_text(encoding="utf-8").lower()
        for p in patterns:
            if p.lower() in text:
                hits.append((f.name, p))
    assert not hits, hits
