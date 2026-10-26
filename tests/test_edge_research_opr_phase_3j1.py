"""Phase 3J.1 — First-experiment readiness audit tests (design-only, no execution)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_bbfe_design_preregistered():
    from modules.edge_research.opr_bridge.bb_first_experiment_01_design import all_bbfe_cases

    cases = all_bbfe_cases()
    assert len(cases) >= 20
    families = {c["family"] for c in cases}
    assert len(families) >= 3
    assert "volatility_surface_skew" in families


def test_mechanism_inventory_documents_gap():
    diag = REPO / "diagnostics/phase_3j1_first_experiment_readiness/artifacts/01_mechanism_inventory.json"
    if not diag.exists():
        pytest.skip("Run run_phase_3j1.py first")
    inv = json.loads(diag.read_text())
    classes = {m["classification"] for m in inv["mechanisms"]}
    assert "NOT_APPLICABLE_AT_PROPOSITION_BIRTH" in classes
    assert "TOOL_BINDING_ONLY" in classes


def test_real_proposition_not_executed():
    diag = REPO / "diagnostics/phase_3j1_first_experiment_readiness/artifacts/04_real_proposition_diagnostic.json"
    if not diag.exists():
        pytest.skip("Run run_phase_3j1.py first")
    payload = json.loads(diag.read_text())
    pkg = payload["initial_experiment_package"]
    assert pkg["execution_status"] == "NOT_EXECUTED"
    assert pkg["human_choice_material"] is True


def test_frozen_hashes_unchanged():
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash

    assert engine_content_hash() == "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a"


def test_audit_verdicts_not_ready():
    summary = REPO / "diagnostics/phase_3j1_first_experiment_readiness/artifacts/09_audit_summary.json"
    if not summary.exists():
        pytest.skip("Run run_phase_3j1.py first")
    audit = json.loads(summary.read_text())
    assert audit["verdicts"]["OVERALL"] == "NOT_READY"
