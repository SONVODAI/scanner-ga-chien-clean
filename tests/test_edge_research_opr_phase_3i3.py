"""Phase 3I.3 tests — panel expansion and Zone C isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ZONE_C = REPO / "benchmarks" / "bb_prop_01" / "zone_c_hidden" / "phenomena_registry.json"


def test_zone_c_populated():
    assert ZONE_C.exists()
    reg = json.loads(ZONE_C.read_text())
    assert reg.get("phenomenon_count", 0) >= 8


def test_generator_does_not_import_zone_c():
    opr_dir = REPO / "modules" / "edge_research" / "opr_bridge"
    scan_targets = (
        "constants.py",
        "evidence_ingest.py",
        "surprise_detector.py",
        "proposition_synthesizer.py",
        "proposition_record.py",
        "executability_adapter.py",
        "template_independence.py",
        "laundering_audit.py",
        "pipeline.py",
    )
    forbidden = ("zone_c_hidden", "phenomena_registry", "PHEN_")
    for name in scan_targets:
        py = opr_dir / name
        if not py.exists():
            continue
        text = py.read_text(encoding="utf-8")
        for pat in forbidden:
            assert pat not in text, f"{name} contains forbidden {pat}"


def test_expanded_panel_deterministic_fingerprint():
    from diagnostics.phase_3i3_real_evidence_expansion.build_expanded_panel import build_expanded_panel

    r1 = build_expanded_panel(write=False)
    r2 = build_expanded_panel(write=False)
    assert r1.fingerprint == r2.fingerprint
    assert r1.specification["total_dates"] >= 40
    assert r1.specification["no_synthetic_rows"] is True


def test_observational_accounting_on_expanded_panel():
    from diagnostics.phase_3i3_real_evidence_expansion.build_expanded_panel import build_expanded_panel
    from diagnostics.phase_3i3_real_evidence_expansion.observational_accounting import (
        compute_observational_accounting,
    )

    panel = build_expanded_panel(write=False).panel
    cutoff = panel["trade_date"].astype(str).max()
    acct = compute_observational_accounting(panel, data_cutoff_date=cutoff)
    assert acct["total_dates_in_panel"] >= 40
    assert acct["baseline_ready_dates"] >= 20
    assert acct["anomaly_trigger_dates"] >= 1


def test_frozen_generator_version_unchanged():
    from modules.edge_research.opr_bridge.constants import OPR_GENERATOR_VERSION

    assert OPR_GENERATOR_VERSION == "opr_generator_v1_3i2"


def test_hidden_evaluator_abstract_output_only():
    from benchmarks.bb_prop_01.zone_d_evaluator.hidden_evaluator import aggregate_hidden_convergence

    fake_prop = {
        "scientific_question": "Does rs_spread dispersion predict t5_return?",
        "motivating_observation": "observed spread",
        "surprise_or_uncertainty": "z=2.5",
        "outcome": {"field": "t5_return"},
        "explanatory_relation": {"feature_or_contrast": "rs_spread"},
        "observation_horizon": 0,
    }
    result = aggregate_hidden_convergence([fake_prop])
    assert "hidden_convergence_class" in result
    assert "PHEN_" not in json.dumps(result)
