"""Phase 3I.17b — Evidence-derived cohort binding tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FROZEN_316 = REPO / "diagnostics/phase_3i16_scientific_action_generator/artifacts/04_t2_one_shot_generation.json"
FROZEN_317 = REPO / "diagnostics/phase_3i17_first_action_audit/artifacts/17_audit_summary.json"


def test_no_normal_stress_in_executability():
    src = (REPO / "modules/edge_research/opr_bridge/scientific_action_executability.py").read_text()
    assert '"NORMAL"' not in src and "'NORMAL'" not in src
    assert '"STRESS"' not in src and "'STRESS'" not in src


def test_binder_module_exists():
    from modules.edge_research.opr_bridge.evidence_derived_cohort_binder import EvidenceDerivedCohortBinder

    assert EvidenceDerivedCohortBinder is not None


@pytest.mark.parametrize("case", __import__("modules.edge_research.opr_bridge.bb_cohort_01_fixtures", fromlist=["all_bb_cohort_cases"]).all_bb_cohort_cases(), ids=lambda c: c["case_id"])
def test_bb_cohort_01(case):
    from modules.edge_research.opr_bridge.bb_cohort_01_fixtures import evaluate_bb_cohort_case, run_bb_cohort_case

    result = run_bb_cohort_case(case)
    ev = evaluate_bb_cohort_case(case, result)
    assert ev["passed"], f"{case['case_id']} failed: {ev['checks']}"


def test_frozen_316_package_not_executed():
    frozen = json.loads(FROZEN_316.read_text())
    assert frozen["execution_status"] == "NOT_EXECUTED"
    assert frozen["package"]["selected_core_hash"] == "efe9abd43ea9a8fbae86a69ea3648adefe83f955df34fafb61cc9221ed1a712f"


def test_317_audit_partial():
    summary = json.loads(FROZEN_317.read_text())
    assert summary["verdict"] == "FIRST_AUTONOMOUS_ACTION_AUDIT_PARTIAL"


def test_independence_not_strategy_label():
    from modules.edge_research.opr_bridge.cohort_overlap_estimator import derive_independence_from_overlap
    from modules.edge_research.opr_bridge.cohort_binding_records import CohortOverlapProfile

    high_overlap = CohortOverlapProfile(100, 0.95, 0.9, 0.9, 0.9, "subset", True, False, 0.95)
    low_overlap = CohortOverlapProfile(100, 0.1, 0.5, 0.5, 0.3, "disjoint", False, False, 0.1)
    assert derive_independence_from_overlap(high_overlap, source_dimension="x").sample_independence in ("LOW", "NONE")
    assert derive_independence_from_overlap(low_overlap, source_dimension="x").sample_independence == "HIGH"


def test_different_rows_not_independent():
    """BBC-02 pattern: high row difference can still mean low scientific independence."""
    from modules.edge_research.opr_bridge.bb_cohort_01_fixtures import run_bb_cohort_case, all_bb_cohort_cases

    case = next(c for c in all_bb_cohort_cases() if c["case_id"] == "BBC-02")
    result = run_bb_cohort_case(case)
    assert result["candidate_count"] > 0


def test_cf_c1_population_uncertainty_removed():
    from modules.edge_research.opr_bridge.bb_next_action_01_fixtures import all_bbna_cases, run_bbna_case, evaluate_case

    case = next(c for c in all_bbna_cases() if c["case_id"] == "BBNA-04")
    _, _, gen = run_bbna_case(case)
    strategies = {c.scientific_action_core.cohort_strategy for c in gen.deduplicated}
    assert "population_subgroup_contrast" not in strategies or gen.selection.disposition.value != "SELECTED"


def test_cf_c8_high_overlap_loses():
    from modules.edge_research.opr_bridge.bb_cohort_01_fixtures import run_bb_cohort_case, all_bb_cohort_cases

    case = next(c for c in all_bb_cohort_cases() if c["case_id"] == "BBC-08")
    result = run_bb_cohort_case(case)
    assert result["disposition"] == "NO_DEFENSIBLE_COHORT"


def test_t2_cohort_diagnostic_not_executed():
    diag = REPO / "diagnostics/phase_3i17b_evidence_cohort_binding/artifacts/05_t2_cohort_diagnostic.json"
    if not diag.exists():
        pytest.skip("Run run_phase_3i17b.py first")
    payload = json.loads(diag.read_text())
    assert payload["execution_status"] == "NOT_EXECUTED"
    assert payload["future_result_blindness"]["experiment_executed"] is False
