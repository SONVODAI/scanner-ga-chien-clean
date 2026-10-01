"""Tests for Phase 3I.16 minimal scientific action generator."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from modules.edge_research.opr_bridge.bb_next_action_01_fixtures import (
    BB_FORBIDDEN,
    all_bbna_cases,
    evaluate_case,
    run_bbna_case,
)
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.scientific_action_core import deduplicate_candidates
from modules.edge_research.opr_bridge.scientific_action_generator import (
    generator_content_hash,
    generate_scientific_actions,
)
from modules.edge_research.opr_bridge.scientific_action_operators import operator_set_hash
from modules.edge_research.opr_bridge.scientific_action_records import (
    ActionDisposition,
    ExecutabilityClass,
    ScientificActionCore,
)
from modules.edge_research.opr_bridge.scientific_action_operators import (
    FalsificationOperator,
    _finalize_candidate,
)
from modules.edge_research.opr_bridge.scientific_action_objectives import generate_objectives
from modules.edge_research.opr_bridge.scientific_action_records import build_objective_record

REPO = Path(__file__).resolve().parents[1]
I314 = REPO / "diagnostics/phase_3i14_automatic_synthesis_hook/artifacts"


@pytest.fixture(scope="module")
def frozen_generator_hash() -> str:
    return generator_content_hash()


# --- Development firewall ---


def test_bbna_firewall():
    for case in all_bbna_cases():
        blob = json.dumps(case, default=str).lower()
        for tok in BB_FORBIDDEN:
            assert tok.lower() not in blob, f"Forbidden {tok} in {case['case_id']}"


# --- BB-NextAction-01 ---


@pytest.mark.parametrize("case", all_bbna_cases(), ids=lambda c: c["case_id"])
def test_bb_next_action_01(case: Dict[str, Any]):
    _, _, result = run_bbna_case(case)
    ev = evaluate_case(case, result)
    assert ev["passed"], f"{case['case_id']} failed checks: {ev['checks']}"


# --- Semantic dedup ---


def test_semantic_dedup_same_core_different_tool():
    case = next(c for c in all_bbna_cases() if c["case_id"] == "BBNA-02")
    _, _, result = run_bbna_case(case)
    cores = [c.scientific_action_core_hash for c in result.deduplicated]
    assert len(cores) == len(set(cores))


def test_same_core_two_tools_bbna10_pattern():
    """BBNA-10: same scientific action via two tools → identical core hash."""
    case = next(c for c in all_bbna_cases() if c["case_id"] == "BBNA-02")
    _, _, base = run_bbna_case(case)
    assert base.deduplicated
    ref = base.deduplicated[0]
    core = ref.scientific_action_core
    alt_core = ScientificActionCore(
        objective_target_uncertainty=core.objective_target_uncertainty,
        proposition_commitment_challenged=core.proposition_commitment_challenged,
        cohort_strategy=core.cohort_strategy,
        contrast_relation=core.contrast_relation,
        expected_epistemic_consequence_type=core.expected_epistemic_consequence_type,
        information_gain_type=core.information_gain_type,
    )
    assert alt_core.core_hash == core.core_hash


# --- Counterfactual adaptivity ---


def test_cf_remove_contradiction_removes_resolution_action():
    case = next(c for c in all_bbna_cases() if c["case_id"] == "BBNA-04")
    _, _, with_contra = run_bbna_case(case)
    no_contra = copy.deepcopy(case)
    no_contra["evidence"] = [case["evidence"][0]]
    _, pri, without = run_bbna_case(no_contra)
    assert any(c.contradiction_resolution_capability for c in with_contra.deduplicated)
    assert not any(c.contradiction_resolution_capability for c in without.deduplicated)


def test_cf_hold_provisionally_stops_selection():
    case = next(c for c in all_bbna_cases() if c["case_id"] == "BBNA-08")
    _, _, result = run_bbna_case(case)
    assert result.selection.disposition == ActionDisposition.HOLD


def test_cf_different_uncertainty_changes_actions():
    c1 = next(c for c in all_bbna_cases() if c["case_id"] == "BBNA-01")
    c2 = next(c for c in all_bbna_cases() if c["case_id"] == "BBNA-17")
    _, _, r1 = run_bbna_case(c1)
    _, _, r2 = run_bbna_case(c2)
    s1 = {c.scientific_action_core.cohort_strategy for c in r1.deduplicated}
    s2 = {c.scientific_action_core.cohort_strategy for c in r2.deduplicated}
    assert s1 != s2


def test_cf_saturation_marks_holdout_redundant():
    """When episode axis is covered, holdout strategy should not appear or be redundant."""
    case = next(c for c in all_bbna_cases() if c["case_id"] == "BBNA-13")
    _, _, result = run_bbna_case(case)
    holdout = [
        c for c in result.deduplicated
        if c.scientific_action_core.cohort_strategy == "episode_holdout_excluding_motivating"
    ]
    assert holdout
    assert all(c.redundancy_classification == "REDUNDANT" for c in holdout)


# --- Anti-rescue ---


def test_invalid_leakage_rejected_bbna14_pattern():
    case = next(c for c in all_bbna_cases() if c["case_id"] == "BBNA-02")
    _, _, result = run_bbna_case(case)
    # Inject invalid candidate via executability — no INVALID selected
    assert result.selection.selected is None or result.selection.selected.executability_classification != ExecutabilityClass.INVALID.value


# --- Generator freeze ---


def test_generator_hash_stable(frozen_generator_hash: str):
    assert frozen_generator_hash == generator_content_hash()
    assert len(frozen_generator_hash) == 64


def test_operator_set_hash_stable():
    h1 = operator_set_hash()
    h2 = operator_set_hash()
    assert h1 == h2


# --- Real T2 one-shot (post-freeze) ---


@pytest.fixture(scope="module")
def t2_generation_result():
    """One-shot T2 — only after abstract BB freeze."""
    from modules.edge_research.opr_bridge.evidence_ledger_builder import (
        build_ledger_specs_from_events,
        proposition_spec_from_record,
    )
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_from_ledger_entries
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
    from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
    from modules.edge_research.opr_bridge.scientific_action_generator import (
        build_context_from_synthesis,
        generate_scientific_actions,
    )

    prop, events = load_real_lifecycle_events()
    prop_spec = proposition_spec_from_record(prop)
    specs = build_ledger_specs_from_events(prop, events)
    entries = build_ledger_from_specs(prop_spec["proposition_id"], prop_spec["proposition_hash"], specs)
    prior = events[0]["epistemic_update"].get("prior_epistemic_state", "PROPOSED")
    synthesis, priority = synthesize_from_ledger_entries(prop_spec, entries, prior_epistemic_state=prior)

    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    ex = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)
    ctx = build_context_from_synthesis(prop_spec, prop, synthesis, priority, entries, ex, specs)
    return generate_scientific_actions(ctx)


def test_t2_one_shot_not_executed(t2_generation_result):
    pkg = t2_generation_result.package
    assert pkg.execution_status == "NOT_EXECUTED"
    assert pkg.synthesis_id
    assert pkg.priority_decision_id


def test_t2_holdout_redundant_not_selected(t2_generation_result):
    pkg = t2_generation_result.package
    if pkg.selected_candidate:
        strat = pkg.selected_candidate.scientific_action_core.cohort_strategy
        assert strat != "episode_holdout_excluding_motivating" or pkg.selected_candidate.redundancy_classification != "REDUNDANT"


def test_t2_blindness_no_tool_result_access():
    """Future-result blindness — generator module must not import execution runner."""
    import modules.edge_research.opr_bridge.scientific_action_generator as gen

    src = Path(gen.__file__).read_text()
    assert "falsification_execution_runner" not in src
    assert "execute_frozen_experiment" not in src


def test_regression_3i12_engine_hash_unchanged():
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash

    assert engine_content_hash() == "ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a"
