"""Phase 3I.19 — Autonomous research dormancy and reopening tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_dormancy_module_exists():
    from modules.edge_research.opr_bridge.dormant_research_reopening_evaluator import DormantResearchReopeningEvaluator

    assert DormantResearchReopeningEvaluator is not None


def test_learning_vs_answer_leakage():
    from modules.edge_research.opr_bridge.dormancy_audit import learning_vs_answer_leakage_audit

    audit = learning_vs_answer_leakage_audit()
    assert audit["passed"], audit


@pytest.mark.parametrize(
    "case",
    __import__(
        "modules.edge_research.opr_bridge.bb_dormancy_01_fixtures",
        fromlist=["all_bb_dormancy_cases"],
    ).all_bb_dormancy_cases(),
    ids=lambda c: c["case_id"],
)
def test_bb_dormancy_01(case):
    from modules.edge_research.opr_bridge.bb_dormancy_01_fixtures import evaluate_bb_dormancy_case, run_bb_dormancy_case

    run = run_bb_dormancy_case(case)
    ev = evaluate_bb_dormancy_case(case, run)
    assert ev["passed"], f"{case['case_id']} failed: {ev['checks']}"


def test_cf_d1_identical_evidence_remain_dormant():
    from modules.edge_research.opr_bridge.bb_dormancy_01_fixtures import all_bb_dormancy_cases, run_bb_dormancy_case
    from modules.edge_research.opr_bridge.dormancy_records import ReopeningEvaluationOutcome
    from modules.edge_research.opr_bridge.dormant_research_reopening_evaluator import (
        CurrentResearchSnapshot,
        DormantResearchReopeningEvaluator,
        ResearchOpportunityDescriptor,
    )

    base = next(c for c in all_bb_dormancy_cases() if c["case_id"] == "BBD-01")
    run = run_bb_dormancy_case(base)
    ctx = run["ctx"]
    snap = CurrentResearchSnapshot(
        proposition_id=ctx.proposition_id,
        proposition_hash=ctx.proposition_hash,
        proposition_record=run["prop"],
        epistemic_state=ctx.synthesis.synthesized_epistemic_state,
        unresolved_uncertainties=set(ctx.unresolved_axes),
        covered_axes=ctx.covered_axes,
        redundant_axes=ctx.redundant_axes,
        max_cohort_overlap=ctx.max_cohort_overlap,
        available_operators=set(ctx.executability.available_tools),
    )
    result = DormantResearchReopeningEvaluator().evaluate(
        run["dormancy"], snap, ResearchOpportunityDescriptor(identical_evidence_added=True)
    )
    assert result.outcome == ReopeningEvaluationOutcome.REMAIN_DORMANT


def test_cf_d7_proposition_change_new_proposition():
    from modules.edge_research.opr_bridge.bb_dormancy_01_fixtures import all_bb_dormancy_cases, run_bb_dormancy_case
    from modules.edge_research.opr_bridge.dormancy_records import ReopeningEvaluationOutcome
    from modules.edge_research.opr_bridge.dormant_research_reopening_evaluator import (
        CurrentResearchSnapshot,
        DormantResearchReopeningEvaluator,
        ResearchOpportunityDescriptor,
    )

    base = next(c for c in all_bb_dormancy_cases() if c["case_id"] == "BBD-01")
    run = run_bb_dormancy_case(base)
    ctx = run["ctx"]
    snap = CurrentResearchSnapshot(
        proposition_id=ctx.proposition_id,
        proposition_hash=ctx.proposition_hash,
        proposition_record=run["prop"],
        epistemic_state=ctx.synthesis.synthesized_epistemic_state,
        unresolved_uncertainties=set(ctx.unresolved_axes),
        covered_axes=ctx.covered_axes,
        redundant_axes=ctx.redundant_axes,
        max_cohort_overlap=ctx.max_cohort_overlap,
        available_operators=set(ctx.executability.available_tools),
    )
    result = DormantResearchReopeningEvaluator().evaluate(
        run["dormancy"],
        snap,
        ResearchOpportunityDescriptor(feature_changed=True, proposition_hash_changed=True),
    )
    assert result.outcome == ReopeningEvaluationOutcome.NEW_PROPOSITION_REQUIRED


def test_t2_dormancy_diagnostic_frozen():
    diag = REPO / "diagnostics/phase_3i19_research_dormancy/artifacts/03_t2_dormancy_diagnostic.json"
    if not diag.exists():
        pytest.skip("Run diagnostics/phase_3i19_research_dormancy/run_phase_3i19.py first")
    payload = json.loads(diag.read_text())
    assert payload["execution_status"] == "NOT_EXECUTED"
    assert payload["318_frontier_preserved"] is True
    assert payload["frontier_decision"] == "NO_HIGH_INFORMATION_ACTION"
    assert payload["should_enter_dormancy"] is True
    assert payload["epistemic_state"] == "SUPPORTED"
    assert payload["future_result_blindness"]["experiment_executed"] is False


def test_regression_318_frontier():
    """3I.18 frontier reassessor unchanged — T2 still NO_HIGH_INFORMATION_ACTION."""
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
    from modules.edge_research.opr_bridge.evidence_ledger_builder import build_ledger_specs_from_events, proposition_spec_from_record
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_from_ledger_entries
    from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
    from modules.edge_research.opr_bridge.scientific_action_generator import build_context_from_synthesis, generate_scientific_actions
    from modules.edge_research.opr_bridge.scientific_frontier_reassessor import ScientificFrontierReassessor

    prop, events = load_real_lifecycle_events()
    prop_spec = proposition_spec_from_record(prop)
    specs = build_ledger_specs_from_events(prop, events)
    entries = build_ledger_from_specs(prop_spec["proposition_id"], prop_spec["proposition_hash"], specs)
    prior = events[0]["epistemic_update"].get("prior_epistemic_state", "PROPOSED")
    synthesis, priority = synthesize_from_ledger_entries(prop_spec, entries, prior_epistemic_state=prior)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    ex = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)
    ctx = build_context_from_synthesis(prop_spec, prop, synthesis, priority, entries, ex, specs)
    gen = generate_scientific_actions(ctx)
    frontier = ScientificFrontierReassessor().reassess(ctx, gen)
    assert frontier.frontier_decision.value == "NO_HIGH_INFORMATION_ACTION"
