"""Phase 3J.4 — Evidence interpretation and epistemic update tests."""

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
J3_DIAG = REPO / "diagnostics/phase_3j3_first_experiment_execution/artifacts/03_real_proposition_diagnostic.json"


@pytest.fixture
def tmp_data_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_interpretation_modules_import():
    from modules.edge_research.opr_bridge import first_experiment_evidence_interpreter  # noqa: F401
    from modules.edge_research.opr_bridge import production_first_experiment_interpretation  # noqa: F401


def test_cf_int1_int10_pass():
    from modules.edge_research.opr_bridge.bb_first_experiment_interpretation_01_fixtures import run_cf_int_counterfactuals

    cf = run_cf_int_counterfactuals()
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


def test_production_interpret_stops_at_evidence_interpreted(tmp_data_dir):
    from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
    from modules.edge_research.opr_bridge.first_experiment_interpretation_records import STOP_FIRST_EVIDENCE_INTERPRETED
    from modules.edge_research.opr_bridge.production_orchestrator import run_production_opr_cycle

    panel = _anomaly_panel(seed=42)
    r = run_production_opr_cycle(
        panel,
        data_cutoff_date="2026-02-15",
        data_dir=tmp_data_dir,
        execute_first_experiment=True,
        interpret_first_experiment=True,
    )
    assert r.outcome == "SESSION_CREATED"
    assert STOP_FIRST_EVIDENCE_INTERPRETED in r.stop_boundaries
    assert r.first_experiment_interpretation is not None


def test_no_decide_next_action_in_interpreter():
    import modules.edge_research.opr_bridge.first_experiment_evidence_interpreter as mod
    import inspect

    src = inspect.getsource(mod)
    assert "decide_next_action(" not in src
    assert "on_epistemic_update_completed(" not in src
    assert "build_research_decision(" not in src


def test_real_t2_diagnostic_interpretation():
    if not all(p.exists() for p in (PANEL, FROZEN_PROP, FROZEN_CONTRACT)):
        pytest.skip("Artifacts unavailable")

    from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
        frozen_ref_from_historical_contract_artifact,
    )
    from modules.edge_research.opr_bridge.first_experiment_execution_persistence import envelope_from_dict
    from modules.edge_research.opr_bridge.first_experiment_interpretation_records import STOP_FIRST_EVIDENCE_INTERPRETED
    from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
    from modules.edge_research.opr_bridge.production_first_experiment_execution import (
        run_production_first_experiment_execution,
    )
    from modules.edge_research.opr_bridge.production_first_experiment_interpretation import (
        run_production_first_experiment_interpretation,
    )
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

    prop = json.loads(FROZEN_PROP.read_text())["full_record"]
    panel = pd.read_csv(PANEL)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    ex = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)

    fx = run_production_first_experiment_execution(
        prop, panel, session_id="j4-real", data_cutoff_date=cutoff
    )
    assert fx.frozen_contract_ref is not None
    assert fx.execution and fx.execution.envelope

    ix = run_production_first_experiment_interpretation(
        prop,
        session_id="j4-real",
        package_dict=fx.package_dict,
        execution_dict=fx.execution.envelope.to_dict(),
        frozen_contract_dict=fx.frozen_contract_ref,
    )
    assert STOP_FIRST_EVIDENCE_INTERPRETED in ix.stop_boundaries
    assert ix.interpretation.outcome == "INTERPRETED"
    env = ix.interpretation.envelope
    assert env is not None
    assert env.frozen_contract_ref.contract_hash
    assert env.epistemic_update["tool_result_hash"] == fx.execution.envelope.tool_result_hash


def test_3j3_regression_still_passes():
    from modules.edge_research.opr_bridge.bb_first_experiment_execution_01_fixtures import run_cf_ex_counterfactuals

    assert run_cf_ex_counterfactuals()["all_passed"]


def test_3j2_regression():
    from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import run_all_bbfe

    assert run_all_bbfe()["all_passed"]


def test_no_hidden_answer_in_interpretation_modules():
    root = REPO / "modules/edge_research/opr_bridge"
    files = list(root.glob("first_experiment_interpretation*.py")) + list(root.glob("first_experiment_evidence*.py"))
    hits = []
    for f in files:
        text = f.read_text(encoding="utf-8").lower()
        for tok in ("2026-08-02", "july 27", "hidden_phenomenon"):
            if tok in text:
                hits.append((f.name, tok))
    assert not hits, hits
