"""Phase 3I.17 audit tests — frozen artifact integrity, no execution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FROZEN = REPO / "diagnostics/phase_3i16_scientific_action_generator/artifacts/04_t2_one_shot_generation.json"
AUDIT = REPO / "diagnostics/phase_3i17_first_action_audit/artifacts"


@pytest.fixture(scope="module")
def frozen():
    return json.loads(FROZEN.read_text())


def test_frozen_package_not_executed(frozen):
    assert frozen["package"]["execution_status"] == "NOT_EXECUTED"
    assert frozen["execution_status"] == "NOT_EXECUTED"


def test_scientific_core_hash_stable(frozen):
    assert frozen["package"]["selected_core_hash"] == "efe9abd43ea9a8fbae86a69ea3648adefe83f955df34fafb61cc9221ed1a712f"


def test_selected_strategy(frozen):
    sc = frozen["package"]["selected_candidate"]
    assert sc["scientific_action_core"]["cohort_strategy"] == "population_subgroup_contrast"
    assert sc["expected_new_uncertainty_coverage"] == "population_robustness"


def test_audit_verdict_partial():
    summary = json.loads((AUDIT / "17_audit_summary.json").read_text())
    assert summary["verdict"] == "FIRST_AUTONOMOUS_ACTION_AUDIT_PARTIAL"
    assert summary["execution_status"] == "NOT_EXECUTED"


def test_objective_counterfactuals_pass():
    cf = json.loads((AUDIT / "07_objective_counterfactuals.json").read_text())
    assert cf["CF-O1_remove_population_unresolved"]["passed"]
    assert cf["CF-O2_population_saturated"]["passed"]
    assert cf["CF-O4_prior_population_evidence"]["passed"]
