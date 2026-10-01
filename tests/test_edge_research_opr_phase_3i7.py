"""Tests for Phase 3I.7 minimal evidence-responsive proposition lifecycle."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.opr_bridge.interpretation_contract import build_interpretation_contract
from modules.edge_research.opr_bridge.lifecycle_records import EvidenceClass, QuintileMetrics
from modules.edge_research.opr_bridge.lifecycle_runner import (
    extract_frozen_proposition_from_3i5,
    run_minimal_lifecycle,
)
from modules.edge_research.opr_bridge.proposition_experiment_interpreter import (
    apply_epistemic_transition,
    decide_next_action,
    interpret_experiment_evidence,
)
from modules.edge_research.research_tools import ToolResult, ToolStatus

REPLAY = Path("diagnostics/phase_3i5_observation_prioritization/artifacts/02_counterfactual_replay.json")
PANEL = Path("benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv")
PREREG = Path("diagnostics/phase_3i7_minimal_lifecycle/artifacts/01_synthetic_expectations.json")


@pytest.fixture(scope="module")
def frozen_prop() -> dict:
    return extract_frozen_proposition_from_3i5(REPLAY)


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return pd.read_csv(PANEL)


@pytest.fixture(scope="module")
def contract(frozen_prop):
    return build_interpretation_contract(frozen_prop)


def _tool_result(status=ToolStatus.OK, outcome_spread=1.0, sample_size=100, cutoff="2026-08-17"):
    return ToolResult(
        tool_name="partition_group_compare",
        tool_version="v1",
        data_cutoff_date=cutoff,
        input_hash="test",
        sample_size=sample_size,
        status=status,
        metrics={"outcome_spread": outcome_spread, "uses_outcome_spec": True},
        groups={},
    )


def _qm(low=1.0, high=3.0, spread=2.0, n=142):
    return QuintileMetrics(
        quintile_means=(low, 1.5, 2.0, 2.5, high),
        quintile_ns=(29, 28, 28, 28, 29),
        low_quintile_mean=low,
        high_quintile_mean=high,
        quintile_mean_spread=spread,
        low_high_delta=high - low,
        sample_size=n,
    )


def test_frozen_proposition_from_3i5_representative(frozen_prop):
    assert frozen_prop["proposition_id"] == "prop-efb650d9bd5c451f"
    assert frozen_prop["observation_provenance"]["evidence_anchor"]["focal_date"] == "2026-08-02"
    assert frozen_prop["explanatory_relation"]["contrast_direction"] == "positive"


def test_contract_frozen_before_result(frozen_prop, contract):
    assert contract.proposition_id == frozen_prop["proposition_id"]
    assert contract.contrast_direction == "positive"
    assert contract.spread_support_floor == 0.5
    assert contract.decision_mapping["SUPPORTING"] == "SEEK_FALSIFICATION"


@pytest.mark.parametrize(
    "case,low,high,spread,outcome_spread,status,expected",
    [
        ("A_clear_support", 1.0, 4.0, 3.0, 2.0, ToolStatus.OK, EvidenceClass.SUPPORTING),
        ("B_clear_disconfirm", 4.0, 1.0, 2.0, -1.0, ToolStatus.OK, EvidenceClass.DISCONFIRMING),
        ("C_contradictory", 1.0, 4.0, 3.0, -0.5, ToolStatus.OK, EvidenceClass.CONTRADICTORY),
        ("D_non_informative", 1.0, 1.2, 0.2, 0.3, ToolStatus.OK, EvidenceClass.NON_INFORMATIVE),
        ("E_invalid", 1.0, 4.0, 3.0, 2.0, ToolStatus.INSUFFICIENT_DATA, EvidenceClass.INVALID),
        ("F_strong_falsify", 5.0, 0.5, 4.5, -2.0, ToolStatus.OK, EvidenceClass.DISCONFIRMING),
    ],
)
def test_interpreter_synthetic_cases(contract, case, low, high, spread, outcome_spread, status, expected):
    tr = _tool_result(status=status, outcome_spread=outcome_spread)
    qm = _qm(low=low, high=high, spread=spread)
    result = interpret_experiment_evidence(contract, tr, qm, expected_cutoff="2026-08-17")
    assert result.evidence_class == expected, f"{case}: got {result.evidence_class}"


def test_support_seeks_falsification_not_replication(contract):
    tr = _tool_result(outcome_spread=2.0)
    qm = _qm(low=1.0, high=4.0, spread=3.0)
    interp = interpret_experiment_evidence(contract, tr, qm, expected_cutoff="2026-08-17")
    _, tkey = apply_epistemic_transition(contract, interp, "HYPOTHESIS")
    chosen, reason, _ = decide_next_action(contract, interp, tkey)
    assert chosen == "SEEK_FALSIFICATION"
    assert "falsification" in reason.lower()


def test_strong_disconfirm_abandon(contract):
    tr = _tool_result(outcome_spread=-2.0)
    qm = _qm(low=5.0, high=0.5, spread=4.5)
    interp = interpret_experiment_evidence(contract, tr, qm, expected_cutoff="2026-08-17")
    assert interp.metrics_used.get("falsify_strength") == "STRONG"
    state, tkey = apply_epistemic_transition(contract, interp, "HYPOTHESIS")
    assert state == "FALSIFIED"
    chosen, _, _ = decide_next_action(contract, interp, tkey)
    assert chosen == "ABANDON"


def test_invalid_no_belief_change(contract):
    tr = _tool_result(status=ToolStatus.INSUFFICIENT_DATA, sample_size=10)
    qm = _qm(n=10)
    interp = interpret_experiment_evidence(contract, tr, qm, expected_cutoff="2026-08-17")
    state, _ = apply_epistemic_transition(contract, interp, "HYPOTHESIS")
    assert state == "HYPOTHESIS"
    assert interp.evidence_class == EvidenceClass.INVALID


def test_counterfactual_decision_changes(contract):
    tr_support = _tool_result(outcome_spread=2.0)
    qm_support = _qm(low=1.0, high=4.0, spread=3.0)
    interp_s = interpret_experiment_evidence(contract, tr_support, qm_support, expected_cutoff="2026-08-17")
    _, tk_s = apply_epistemic_transition(contract, interp_s, "HYPOTHESIS")
    chosen_s, _, _ = decide_next_action(contract, interp_s, tk_s)

    tr_dis = _tool_result(outcome_spread=-2.0)
    qm_dis = _qm(low=5.0, high=0.5, spread=4.5)
    interp_d = interpret_experiment_evidence(contract, tr_dis, qm_dis, expected_cutoff="2026-08-17")
    _, tk_d = apply_epistemic_transition(contract, interp_d, "HYPOTHESIS")
    chosen_d, _, _ = decide_next_action(contract, interp_d, tk_d)

    assert chosen_s != chosen_d


def test_real_lifecycle_once(frozen_prop, panel):
    """Single real ToolResult interpretation — no retry."""
    result = run_minimal_lifecycle(frozen_prop, panel, experiment_ref="lifecycle_real_001")
    assert result["epistemic_update"]["prior_epistemic_state"] == "HYPOTHESIS"
    assert result["research_decision"]["chosen_next_action"] in (
        "SEEK_FALSIFICATION",
        "SEEK_REPLICATION",
        "HOLD_UNRESOLVED",
        "ABANDON",
    )
    assert result["lineage"]["proposition_immutable"] is True
    assert result["proposition_hash"] == result["lineage"]["proposition_hash"]


def test_preregistration_file_exists():
    assert PREREG.exists()
    data = json.loads(PREREG.read_text())
    assert "synthetic_cases" in data
    assert len(data["synthetic_cases"]) >= 7
