"""Tests for Phase 3I.9 falsification candidate generation and selection."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.opr_bridge.falsification_candidate_generator import (
    GENERATOR_VERSION,
    collect_motivating_episode_dates,
    derive_proposition_vulnerabilities,
    generate_falsification_candidates,
)
from modules.edge_research.opr_bridge.falsification_records import (
    EvidenceIndependenceClass,
    SelectionOutcome,
)
from modules.edge_research.opr_bridge.falsification_runner import (
    build_abstract_proposition_fixture,
    load_frozen_3i7_lineage,
    run_falsification_selection,
    verify_3i7_lineage_integrity,
)
from modules.edge_research.opr_bridge.falsification_selector import select_falsification_candidate
from modules.edge_research.opr_bridge.interpretation_contract import (
    build_interpretation_contract,
    contract_hash_payload,
    contract_rule_content,
    interpretation_contract_from_dict,
)
from modules.edge_research.opr_bridge.dev_fixtures import build_extended_dev_panel
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

I37 = Path("diagnostics/phase_3i7_minimal_lifecycle/artifacts")
PANEL = Path("benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv")


@pytest.fixture(scope="module")
def frozen_3i7():
    return load_frozen_3i7_lineage(I37)


@pytest.fixture(scope="module")
def panel():
    return pd.read_csv(PANEL)


@pytest.fixture(scope="module")
def contract_artifact(frozen_3i7):
    return frozen_3i7["interpretation_contract"]


@pytest.fixture(scope="module")
def contract(contract_artifact):
    return interpretation_contract_from_dict(contract_artifact)


def test_3i7_lineage_integrity(frozen_3i7):
    audit = verify_3i7_lineage_integrity(frozen_3i7)
    assert audit["passed"]
    assert audit["decision_action"] == "SEEK_FALSIFICATION"
    assert audit["resulting_state"] == "SUPPORTED"


def test_contract_provenance_load_preserves_hash(contract_artifact, contract):
    assert contract.contract_hash == contract_artifact["contract_hash"]
    assert contract.frozen_at == contract_artifact["frozen_at"]


def test_contract_rule_content_stable_without_frozen_at(frozen_3i7):
    prop = frozen_3i7["proposition"]
    c1 = build_interpretation_contract(prop)
    c2 = build_interpretation_contract(prop)
    assert contract_rule_content(c1.to_dict()) == contract_rule_content(c2.to_dict())
    assert c1.contract_hash == c2.contract_hash


def test_vulnerabilities_derived_from_proposition_not_tools(frozen_3i7):
    vulns = derive_proposition_vulnerabilities(frozen_3i7["proposition"])
    kinds = {v.kind.value for v in vulns}
    assert "directional_reversal" in kinds
    assert "episode_instability" in kinds
    dates = collect_motivating_episode_dates(frozen_3i7["proposition"])
    assert "2026-08-02" in dates


def test_abstract_fixture_generalization(panel):
    abstract = build_abstract_proposition_fixture(
        dispersion_feature="vol_dispersion",
        outcome_field="t3_return",
        focal_date="2026-03-15",
    )
    assert "rs_spread" not in abstract["scientific_question"]
    assert "t5_return" not in abstract["scientific_question"]
    contract = build_interpretation_contract(abstract)
    dev_panel = build_extended_dev_panel(panel.head(100), n_dates=20, symbols_per_date=30)
    dev_panel["vol_dispersion"] = dev_panel["rs_spread"]
    dev_panel["t3_return"] = dev_panel["t5_return"]
    decision = {
        "decision_id": "dec-test",
        "chosen_next_action": "SEEK_FALSIFICATION",
    }
    update = {"update_id": "epu-test", "tool_result_hash": "abc"}
    prior = {
        "tool_name": "partition_group_compare",
        "tool_version": "v1",
        "inputs": {"partition_column": "vol_dispersion", "n_groups": 5},
        "research_scope": {
            "population_spec": {"kind": "all", "grammar_version": "research_grammar_v1"},
            "outcome_spec": abstract["outcome"],
            "observation_horizon": 0,
        },
        "data_cutoff_date": "2026-04-01",
    }
    prior_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(prior))
    candidates = generate_falsification_candidates(
        abstract,
        interpretation_contract=contract,
        epistemic_update=update,
        research_decision=decision,
        prior_experiment_spec=prior,
        prior_experiment_content_hash=prior_hash,
        lineage_hash="lineage-test",
        prior_tool_result_hash="abc",
        panel=dev_panel,
    )
    holdout = [c for c in candidates if c.candidate_id == "fc-independent_episode_holdout"]
    assert holdout, "Abstract proposition should generate holdout candidate"
    assert holdout[0].executability_status == "EXECUTABLE"


def _prior_hash_from_lineage(frozen_3i7):
    spec = frozen_3i7["lineage"]["experiment_spec"]
    return compute_experiment_content_hash(
        ExperimentSpec(
            tool_name=spec["tool_name"],
            tool_version=spec.get("tool_version", "v1"),
            inputs=dict(spec["inputs"]),
            research_scope=dict(spec["research_scope"]),
            data_cutoff_date=spec["data_cutoff_date"],
        )
    )


@pytest.fixture
def audit_candidates(frozen_3i7, panel, contract):
    prior_hash = _prior_hash_from_lineage(frozen_3i7)
    return generate_falsification_candidates(
        frozen_3i7["proposition"],
        interpretation_contract=contract,
        epistemic_update=frozen_3i7["epistemic_update"],
        research_decision=frozen_3i7["research_decision"],
        prior_experiment_spec=frozen_3i7["lineage"]["experiment_spec"],
        prior_experiment_content_hash=prior_hash,
        lineage_hash=frozen_3i7["lineage"]["lineage_hash"],
        prior_tool_result_hash=frozen_3i7["epistemic_update"]["tool_result_hash"],
        panel=panel,
        include_audit_sketches=True,
    )


@pytest.mark.parametrize(
    "candidate_id,expected_class,rejected_reason_fragment",
    [
        ("fc-audit_confirmatory_retest", EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION, "not_actually_falsification"),
        ("fc-audit_same_question_different_tool", EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION, "counterfactual"),
        ("fc-audit_population_narrow", EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION, "anti_rescue"),
        ("fc-audit_horizon_mutation", EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION, "anti_rescue"),
        ("fc-audit_invalid_leaky", EvidenceIndependenceClass.NOT_ACTUALLY_FALSIFICATION, "executability"),
    ],
)
def test_bb_falsify_rejects_bad_candidates(audit_candidates, candidate_id, expected_class, rejected_reason_fragment):
    by_id = {c.candidate_id: c for c in audit_candidates}
    assert candidate_id in by_id
    assert by_id[candidate_id].evidence_independence_class == expected_class.value
    sel = select_falsification_candidate(audit_candidates)
    rejected_ids = {r["candidate_id"] for r in sel.rejected}
    assert candidate_id in rejected_ids


def test_bb_falsify_independent_episode_eligible(audit_candidates):
    holdout = next(c for c in audit_candidates if c.candidate_id == "fc-independent_episode_holdout")
    assert holdout.evidence_independence_class == EvidenceIndependenceClass.INDEPENDENT_FALSIFICATION.value
    assert holdout.counterfactual_falsifiable
    assert holdout.executability_status == "EXECUTABLE"
    sel = select_falsification_candidate(audit_candidates)
    assert sel.outcome == SelectionOutcome.SELECTED
    assert sel.selected.candidate_id == "fc-independent_episode_holdout"


def test_bb_falsify_no_viable_when_only_confirmatory(frozen_3i7, panel, contract):
    prior_hash = _prior_hash_from_lineage(frozen_3i7)
    only_confirm = generate_falsification_candidates(
        frozen_3i7["proposition"],
        interpretation_contract=contract,
        epistemic_update=frozen_3i7["epistemic_update"],
        research_decision=frozen_3i7["research_decision"],
        prior_experiment_spec=frozen_3i7["lineage"]["experiment_spec"],
        prior_experiment_content_hash=prior_hash,
        lineage_hash=frozen_3i7["lineage"]["lineage_hash"],
        prior_tool_result_hash=frozen_3i7["epistemic_update"]["tool_result_hash"],
        panel=panel,
        include_audit_sketches=True,
    )
    # Remove holdout by mocking empty holdout — filter candidates to only audit confirmatory
    confirm_only = [c for c in only_confirm if c.candidate_id == "fc-audit_confirmatory_retest"]
    sel = select_falsification_candidate(confirm_only)
    assert sel.outcome == SelectionOutcome.NO_VALID_FALSIFICATION_CANDIDATE


def test_real_selection_once_no_execution(frozen_3i7, panel):
    result = run_falsification_selection(frozen_3i7, panel, include_audit_sketches=False)
    assert result["second_experiment_executed"] is False
    assert result["selection"]["outcome"] == SelectionOutcome.SELECTED.value
    assert result["one_shot_package"] is not None
    assert result["one_shot_package"]["execution_status"] == "NOT_EXECUTED"
    assert result["one_shot_package"]["interpretation_contract_hash"] == frozen_3i7["interpretation_contract"]["contract_hash"]
    pkg = result["one_shot_package"]
    assert pkg["selected_experiment_content_hash"] != compute_experiment_content_hash(
        ExperimentSpec(
            tool_name=frozen_3i7["lineage"]["experiment_spec"]["tool_name"],
            tool_version="v1",
            inputs=dict(frozen_3i7["lineage"]["experiment_spec"]["inputs"]),
            research_scope=dict(frozen_3i7["lineage"]["experiment_spec"]["research_scope"]),
            data_cutoff_date=frozen_3i7["lineage"]["experiment_spec"]["data_cutoff_date"],
        )
    )


def test_generator_version_hash():
    assert GENERATOR_VERSION.startswith("falsification_candidate_generator_v1")
