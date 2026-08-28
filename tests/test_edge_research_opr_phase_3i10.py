"""Tests for Phase 3I.10 one-shot falsification execution."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.opr_bridge.falsification_execution_runner import (
    EXPECTED_CONTRACT_HASH,
    EXPECTED_PACKAGE_HASH,
    audit_evidence_independence,
    load_one_shot_package,
    run_one_shot_falsification_execution,
    verify_package_integrity,
)

I37 = Path("diagnostics/phase_3i7_minimal_lifecycle/artifacts")
I39 = Path("diagnostics/phase_3i9_falsification_selection/artifacts")
PANEL = Path("benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv")


@pytest.fixture(scope="module")
def frozen_inputs():
    package = load_one_shot_package(I39 / "09_one_shot_package.json")
    return {
        "package": package,
        "proposition": json.loads((I37 / "02_frozen_proposition.json").read_text())["full_record"],
        "prior_update": json.loads((I37 / "07_epistemic_update.json").read_text()),
        "prior_decision": json.loads((I37 / "08_research_decision.json").read_text()),
        "candidate": json.loads((I39 / "07_real_candidate_set.json").read_text())["candidates"][0],
        "lineage": json.loads((I37 / "09_append_only_lineage.json").read_text()),
        "contract": json.loads((I37 / "03_interpretation_contract.json").read_text()),
    }


@pytest.fixture(scope="module")
def panel():
    return pd.read_csv(PANEL)


def test_package_hash_matches_expected(frozen_inputs):
    assert frozen_inputs["package"]["package_hash"] == EXPECTED_PACKAGE_HASH
    assert frozen_inputs["package"]["execution_status"] == "NOT_EXECUTED"
    assert frozen_inputs["package"]["interpretation_contract_hash"] == EXPECTED_CONTRACT_HASH


def test_integrity_gate_passes(frozen_inputs):
    integrity = verify_package_integrity(
        frozen_inputs["package"],
        candidate_record=frozen_inputs["candidate"],
        prior_epistemic_update=frozen_inputs["prior_update"],
        proposition=frozen_inputs["proposition"],
        lineage=frozen_inputs["lineage"],
    )
    assert integrity["passed"], integrity["failures"]


def test_independence_audit_passes(frozen_inputs, panel):
    audit = audit_evidence_independence(
        frozen_inputs["package"], frozen_inputs["proposition"], panel
    )
    assert audit["independence_pass"]
    assert "2026-08-02" not in audit.get("overlap_with_motivating", [])


def test_one_shot_execution(frozen_inputs, panel):
    result = run_one_shot_falsification_execution(
        frozen_inputs["package"],
        proposition=frozen_inputs["proposition"],
        prior_epistemic_update=frozen_inputs["prior_update"],
        prior_research_decision=frozen_inputs["prior_decision"],
        candidate_record=frozen_inputs["candidate"],
        lineage=frozen_inputs["lineage"],
        interpretation_contract_dict=frozen_inputs["contract"],
        panel=panel,
    )
    assert result["executed"]
    assert result["one_shot_proof"]["execution_count"] == 1
    assert result["verdict"] in (
        "AUTONOMOUS_FALSIFICATION_PASS",
        "AUTONOMOUS_FALSIFICATION_PARTIAL",
        "EXECUTION_INVALID",
    )
    assert result["raw_tool_result"] is not None
    assert result["epistemic_update"] is not None
    assert result["proposition_audit"]["proposition_hash_unchanged"]
    assert result["package_audit"]["package_hash_unchanged"]
    assert result["prior_state"] == "SUPPORTED"
    assert result["interpretation_contract_hash"] == EXPECTED_CONTRACT_HASH


def test_integrity_fail_on_tampered_hash(frozen_inputs):
    bad = dict(frozen_inputs["package"])
    bad["package_hash"] = "0" * 64
    integrity = verify_package_integrity(
        bad,
        candidate_record=frozen_inputs["candidate"],
        prior_epistemic_update=frozen_inputs["prior_update"],
        proposition=frozen_inputs["proposition"],
        lineage=frozen_inputs["lineage"],
    )
    assert not integrity["passed"]
