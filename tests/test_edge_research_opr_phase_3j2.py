"""Phase 3J.2 — Autonomous first-experiment selection tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
FROZEN_PROP = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json"


def test_bbfe_all_cases_pass():
    from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import run_all_bbfe

    result = run_all_bbfe()
    assert result["total"] == 20
    assert result["all_passed"], result["cases"]


def test_counterfactuals_cf_fe1_fe8_pass():
    from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import run_counterfactuals

    cf = run_counterfactuals()
    assert cf["all_passed"], cf


def test_frozen_scientific_hashes_unchanged():
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash
    from modules.edge_research.opr_bridge.scientific_action_generator import generator_content_hash as sag_hash
    from modules.edge_research.opr_bridge.dormancy_records import dormancy_content_hash
    from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import integration_content_hash

    assert engine_content_hash() == "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a"
    assert sag_hash() == "77e665c720b3f8c5050ff1113d076c38cd2c678db8df6773711e665e3fcc7eb9"
    assert dormancy_content_hash() == "a6a70005511d5894ec0fbcead9ad5b4589ce3162cbe01b7c761a12026b9adfa6"
    assert integration_content_hash() == "409f55fd2490cd5f9635bc9c8e1bb946a02f37868591efa2dffd4691d07b1145"


def test_package_execution_status_not_executed():
    from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import all_bbfe_cases, run_bbfe_case

    case = all_bbfe_cases()[0]
    run = run_bbfe_case(case)
    assert run["package"].execution_status == "NOT_EXECUTED"


def test_real_t2_diagnostic_not_executed():
    if not PANEL.exists() or not FROZEN_PROP.exists():
        pytest.skip("Frozen proposition or panel unavailable")

    from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

    prop = json.loads(FROZEN_PROP.read_text())["full_record"]
    panel = pd.read_csv(PANEL)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    pkg = run_first_experiment_pipeline(
        prop,
        panel,
        executability=ExecutabilityContext.real_partition_default(data_cutoff=cutoff),
    )
    assert pkg.execution_status == "NOT_EXECUTED"
    assert pkg.proposition_id == "prop-efb650d9bd5c451f"


def test_real_t2_rejects_birth_redundant_default():
    if not PANEL.exists() or not FROZEN_PROP.exists():
        pytest.skip("Frozen proposition or panel unavailable")

    from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

    prop = json.loads(FROZEN_PROP.read_text())["full_record"]
    panel = pd.read_csv(PANEL)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    pkg = run_first_experiment_pipeline(
        prop,
        panel,
        executability=ExecutabilityContext.real_partition_default(data_cutoff=cutoff),
    )
    rejected_reasons = {r["reason"] for r in pkg.rejected}
    assert "confirmatory_only_when_falsification_available" in rejected_reasons
    assert pkg.human_choice_material is False
    if pkg.selected_experiment_spec:
        pop = pkg.selected_experiment_spec.get("research_scope", {}).get("population_spec", {})
        assert pop.get("operator") == "not_in" or pop.get("kind") == "filter"


def test_objectives_derived_without_tool_names():
    from modules.edge_research.opr_bridge.first_experiment_objective import derive_initial_experiment_objectives

    prop = {
        "proposition_id": "p1",
        "scientific_question": "Q?",
        "canonical_proposition_core": "core",
        "falsifiable_expectation": "expect",
        "disconfirming_observation_spec": {"description": "d", "operational_test": "t"},
        "null_competing_explanation": "artifact",
        "observation_provenance": {
            "evidence_anchor": {"focal_date": "2019-01-01", "data_cutoff_date": "2019-06-01"},
            "empirical_artifacts": [{"date": "2019-01-01"}],
        },
    }
    objs = derive_initial_experiment_objectives(prop)
    assert len(objs) >= 1
    blob = json.dumps([o.to_dict() for o in objs]).lower()
    assert "partition_group_compare" not in blob
    assert "tier_compare" not in blob
