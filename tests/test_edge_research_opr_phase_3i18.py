"""Phase 3I.18 — Non-cohort scientific frontier reassessment tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_frontier_module_exists():
    from modules.edge_research.opr_bridge.scientific_frontier_reassessor import ScientificFrontierReassessor

    assert ScientificFrontierReassessor is not None


def test_learning_vs_answer_leakage_audit():
    from modules.edge_research.opr_bridge.frontier_audit import learning_vs_answer_leakage_audit

    audit = learning_vs_answer_leakage_audit()
    assert audit["passed"], audit
    assert audit["uses_lexicographic_rank_only"]
    assert audit["no_strategy_name_preference"]


@pytest.mark.parametrize(
    "case",
    __import__(
        "modules.edge_research.opr_bridge.bb_frontier_01_fixtures",
        fromlist=["all_bb_frontier_cases"],
    ).all_bb_frontier_cases(),
    ids=lambda c: c["case_id"],
)
def test_bb_frontier_01(case):
    from modules.edge_research.opr_bridge.bb_frontier_01_fixtures import (
        evaluate_bb_frontier_case,
        run_bb_frontier_case,
    )

    run = run_bb_frontier_case(case)
    ev = evaluate_bb_frontier_case(case, run)
    assert ev["passed"], f"{case['case_id']} failed: {ev['checks']}"


def test_cf_f1_resolved_uncertainty_removes_actions():
    from modules.edge_research.opr_bridge.bb_frontier_01_fixtures import all_bb_frontier_cases
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
    from modules.edge_research.opr_bridge.scientific_action_generator import (
        build_context_from_synthesis,
        generate_scientific_actions,
    )
    from modules.edge_research.opr_bridge.scientific_frontier_reassessor import ScientificFrontierReassessor

    base = next(c for c in all_bb_frontier_cases() if c["case_id"] == "BBF-01")
    prop = base["proposition"]
    ps = {
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop["proposition_hash"],
        "proposition_type": prop["proposition_type"],
    }
    syn, pri = synthesize_evidence(ps, base["evidence"], prior_epistemic_state="SUPPORTED")
    syn_resolved = replace(
        syn,
        uncertainty_unresolved=tuple(a for a in syn.uncertainty_unresolved if a != "concentration_dominance"),
        uncertainty_covered=tuple(sorted(set(syn.uncertainty_covered) | {"concentration_dominance"})),
    )
    entries = build_ledger_from_specs(ps["proposition_id"], ps["proposition_hash"], base["evidence"])
    ctx = build_context_from_synthesis(
        ps, prop, syn_resolved, pri, entries, ExecutabilityContext.abstract_default(), evidence_specs=base["evidence"]
    )
    gen = generate_scientific_actions(ctx)
    result = ScientificFrontierReassessor().reassess(ctx, gen)
    conc = [a for a in result.action_assessments if a.uncertainty_axis == "concentration_dominance" and a.available]
    assert len(conc) == 0


def test_cf_f3_cohort_unavailable_blocks_cohort_actions():
    from modules.edge_research.opr_bridge.bb_frontier_01_fixtures import all_bb_frontier_cases, run_bb_frontier_case
    from modules.edge_research.opr_bridge.cohort_binding_records import CohortSelectionDisposition
    from modules.edge_research.opr_bridge.scientific_frontier_reassessor import (
        COHORT_DEPENDENT_STRATEGIES,
        CohortAxisConstraint,
    )

    base = next(c for c in all_bb_frontier_cases() if c["case_id"] == "BBF-01")
    run = run_bb_frontier_case(
        {
            **base,
            "cohort_constraints_override": {
                "population_robustness": CohortAxisConstraint(
                    "population_robustness",
                    CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value,
                    "test",
                ),
                "temporal_regime_robustness": CohortAxisConstraint(
                    "temporal_regime_robustness",
                    CohortSelectionDisposition.NO_DEFENSIBLE_COHORT.value,
                    "test",
                ),
            },
        }
    )
    cohort_avail = [
        a for a in run["result"].action_assessments if a.cohort_strategy in COHORT_DEPENDENT_STRATEGIES and a.available
    ]
    assert len(cohort_avail) == 0


def test_cf_f7_all_redundant_hold():
    from modules.edge_research.opr_bridge.bb_frontier_01_fixtures import all_bb_frontier_cases, run_bb_frontier_case
    from modules.edge_research.opr_bridge.frontier_records import FrontierDecision

    case = next(c for c in all_bb_frontier_cases() if c["case_id"] == "BBF-02")
    run = run_bb_frontier_case(case)
    assert run["decision"] in (
        FrontierDecision.NO_HIGH_INFORMATION_ACTION.value,
        FrontierDecision.HOLD_PROVISIONALLY.value,
    )


def test_t2_frontier_not_executed():
    diag = REPO / "diagnostics/phase_3i18_non_cohort_frontier/artifacts/03_t2_frontier_diagnostic.json"
    if not diag.exists():
        pytest.skip("Run diagnostics/phase_3i18_non_cohort_frontier/run_phase_3i18.py first")
    payload = json.loads(diag.read_text())
    assert payload["execution_status"] == "NOT_EXECUTED"
    assert payload["future_result_blindness"]["experiment_executed"] is False
    assert payload["future_result_blindness"]["tool_result_accessed"] is False
    assert payload["frozen_package"] is None
    assert payload["frontier_decision"] == "NO_HIGH_INFORMATION_ACTION"
