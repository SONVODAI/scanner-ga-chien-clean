"""
Phase 3J.5 — CF-RD1–10 counterfactual fixtures for first-experiment research decision.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.bb_first_experiment_interpretation_01_fixtures import (
    _base_quintile,
    _base_tool_result,
    _run_case_interpretation,
    _synthetic_envelope,
)
from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import (
    _default_executability,
    all_bbfe_cases,
)
from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
    freeze_interpretation_contract_pre_result,
)
from modules.edge_research.opr_bridge.first_experiment_evidence_interpreter import (
    interpret_first_experiment_evidence,
)
from modules.edge_research.opr_bridge.first_experiment_execution_persistence import package_from_dict
from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
from modules.edge_research.opr_bridge.first_experiment_research_decider import (
    decide_first_experiment_research_action,
)
from modules.edge_research.opr_bridge.lifecycle_records import NextResearchAction, QuintileMetrics
from modules.edge_research.research_search_accounting import HIGH_COMPLEXITY_THRESHOLD
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

BENCHMARK_VERSION = "bb_first_experiment_research_decision_01_v1_3j5"


def _interpret_and_decide(case, *, tool_result=None, quintile=None, budget_exhausted=None, complexity=None):
    prop = case["proposition"]
    panel = pd.DataFrame(case["panel_rows"])
    ex = case.get("executability") or _default_executability(case)
    pkg = run_first_experiment_pipeline(prop, panel, executability=ex)
    if pkg.disposition != "SELECTED":
        return None, None
    spec_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(pkg.selected_experiment_spec))
    core = next(
        c.scientific_action_core_hash
        for c in pkg.deduplicated_candidates
        if c.candidate_id == pkg.selected_candidate_id
    )
    frozen = freeze_interpretation_contract_pre_result(
        prop,
        package_id=pkg.package_id,
        experiment_content_hash=spec_hash,
        scientific_action_core_hash=core,
    )
    tr = tool_result or _base_tool_result(cutoff=ex.data_cutoff)
    qm = quintile or _base_quintile()
    env_exec = _synthetic_envelope(prop=prop, package=pkg, tool_result=tr, quintile_metrics=qm)
    interp = interpret_first_experiment_evidence(
        prop, pkg, env_exec, frozen, session_id="cf-rd", prior_epistemic_state="HYPOTHESIS"
    )
    if not interp.envelope:
        return interp, None
    decision = decide_first_experiment_research_action(
        prop,
        pkg,
        interp.envelope,
        session_id="cf-rd",
        budget_exhausted_override=budget_exhausted,
        complexity_override=complexity,
    )
    return interp, decision


def _mutate_surviving_nulls(interp_result, nulls: tuple):
    env = interp_result.envelope
    assess = env.evidence_assessment
    from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
        IntentAwareEvidenceAssessment,
    )

    new_assess = IntentAwareEvidenceAssessment(
        experiment_intent_summary=assess.experiment_intent_summary,
        cohort_strategy=assess.cohort_strategy,
        target_uncertainty=assess.target_uncertainty,
        evidence_relevance=assess.evidence_relevance,
        evidence_direction=assess.evidence_direction,
        evidence_strength=assess.evidence_strength,
        remaining_uncertainty=assess.remaining_uncertainty,
        other_nulls_still_alive=nulls,
        null_accounting=assess.null_accounting,
        base_evidence_class=assess.base_evidence_class,
        condition_matched=assess.condition_matched,
        limitations=assess.limitations,
        tool_semantic_labels_ignored=assess.tool_semantic_labels_ignored,
    )
    from dataclasses import replace

    new_env = replace(env, evidence_assessment=new_assess)
    return replace(interp_result, envelope=new_env)


def run_cf_rd_counterfactuals() -> Dict[str, Any]:
    cf: Dict[str, Any] = {}
    base_case = next(c for c in all_bbfe_cases() if c["case_id"] == "BBFE-01")
    prop = base_case["proposition"]
    panel = pd.DataFrame(base_case["panel_rows"])
    ex = _default_executability(base_case)
    pkg = run_first_experiment_pipeline(prop, panel, executability=ex)
    spec_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(pkg.selected_experiment_spec))
    core = next(
        c.scientific_action_core_hash
        for c in pkg.deduplicated_candidates
        if c.candidate_id == pkg.selected_candidate_id
    )
    frozen = freeze_interpretation_contract_pre_result(
        prop, package_id=pkg.package_id, experiment_content_hash=spec_hash, scientific_action_core_hash=core
    )
    tr = _base_tool_result(cutoff=ex.data_cutoff)
    qm = _base_quintile()
    env_exec = _synthetic_envelope(prop=prop, package=pkg, tool_result=tr, quintile_metrics=qm)
    interp = interpret_first_experiment_evidence(
        prop, pkg, env_exec, frozen, session_id="cf-rd-base", prior_epistemic_state="HYPOTHESIS"
    )

    # CF-RD1 supportive evidence / confirmation temptation
    rd1 = decide_first_experiment_research_action(prop, pkg, interp.envelope, session_id="cf-rd1")
    repl_rejected = any(
        e.action_family == "SEEK_REPLICATION" and not e.admissible for e in rd1.envelope.candidate_evaluations
    )
    cf["CF-RD1"] = {
        "passed": rd1.envelope is not None
        and rd1.envelope.research_decision["chosen_next_action"] != NextResearchAction.SEEK_REPLICATION.value
        and (repl_rejected or rd1.envelope.confirmation_bias_guard_applied or rd1.envelope.decision_kind == "ACTION"),
        "description": "Supportive evidence does not default to confirmatory replication",
    }

    # CF-RD2 same evidence different surviving nulls → decision may differ
    interp_a = _mutate_surviving_nulls(interp, ("directional_reversal",))
    interp_b = _mutate_surviving_nulls(interp, ("population_concentration",))
    rd2a = decide_first_experiment_research_action(prop, pkg, interp_a.envelope, session_id="cf-rd2a")
    rd2b = decide_first_experiment_research_action(prop, pkg, interp_b.envelope, session_id="cf-rd2b")
    target_a = next(
        (e.target_null_key for e in rd2a.envelope.candidate_evaluations if e.admissible and e.action_family == "TEST_NEXT_NULL"),
        None,
    )
    target_b = next(
        (e.target_null_key for e in rd2b.envelope.candidate_evaluations if e.admissible and e.action_family == "TEST_NEXT_NULL"),
        None,
    )
    cf["CF-RD2"] = {
        "passed": rd2a.envelope is not None
        and rd2b.envelope is not None
        and (target_a != target_b or rd2a.envelope.research_decision != rd2b.envelope.research_decision),
        "description": "Different surviving null structures may yield different decisions",
    }

    # CF-RD3 strong result / exhausted budget
    rd3 = decide_first_experiment_research_action(
        prop,
        pkg,
        interp.envelope,
        session_id="cf-rd3",
        budget_exhausted_override=True,
        complexity_override=HIGH_COMPLEXITY_THRESHOLD + 1,
    )
    cf["CF-RD3"] = {
        "passed": rd3.envelope is not None
        and rd3.envelope.decision_kind == "STOP"
        and rd3.envelope.search_accounting.budget_exhausted,
        "description": "Exhausted budget yields STOP not continuation",
    }

    # CF-RD4 weak evidence / informative next action
    tr_weak = _base_tool_result(spread=0.1)
    qm_weak = _base_quintile(low=0.4, high=0.45)
    _, rd4 = _interpret_and_decide(base_case, tool_result=tr_weak, quintile=qm_weak)
    cf["CF-RD4"] = {
        "passed": rd4 is not None
        and rd4.envelope is not None
        and (
            rd4.envelope.decision_kind == "ACTION"
            or rd4.envelope.research_decision["chosen_next_action"] == NextResearchAction.HOLD_UNRESOLVED.value
        ),
        "description": "Weak evidence may still justify continuation or hold",
    }

    # CF-RD5 negative evidence
    tr_neg = _base_tool_result(spread=-1.0)
    qm_neg = _base_quintile(low=1.5, high=0.0)
    _, rd5 = _interpret_and_decide(base_case, tool_result=tr_neg, quintile=qm_neg)
    cf["CF-RD5"] = {
        "passed": rd5 is not None
        and rd5.envelope is not None
        and rd5.envelope.research_decision["chosen_next_action"]
        in (
            NextResearchAction.SEEK_REPLICATION.value,
            NextResearchAction.ABANDON.value,
            NextResearchAction.HOLD_UNRESOLVED.value,
            NextResearchAction.SEEK_FALSIFICATION.value,
        )
        and rd5.envelope.research_decision["chosen_next_action"] != NextResearchAction.SEEK_REPLICATION.value
        or rd5.envelope.decision_kind == "STOP",
        "description": "Negative evidence does not mechanically continue confirmation",
    }

    # CF-RD6 redundant action rejected
    rd6 = decide_first_experiment_research_action(prop, pkg, interp.envelope, session_id="cf-rd6")
    redundant_rejected = any(
        "redundant" in r for e in rd6.envelope.candidate_evaluations for r in e.rejection_reasons
    )
    cf["CF-RD6"] = {
        "passed": rd6.envelope is not None and redundant_rejected,
        "description": "Redundant confirmatory actions penalized/rejected",
    }

    # CF-RD7 human-choice contamination (ordering invariance)
    rd7a = decide_first_experiment_research_action(prop, pkg, interp.envelope, session_id="cf-rd7a")
    rd7b = decide_first_experiment_research_action(prop, pkg, interp.envelope, session_id="cf-rd7b")
    cf["CF-RD7"] = {
        "passed": rd7a.envelope.research_decision["chosen_next_action"]
        == rd7b.envelope.research_decision["chosen_next_action"],
        "description": "Decision invariant to session ordering",
    }

    # CF-RD8 tool convenience — falsification preferred over replication when nulls survive
    chosen = rd1.envelope.research_decision["chosen_next_action"]
    cf["CF-RD8"] = {
        "passed": chosen == NextResearchAction.SEEK_FALSIFICATION.value or rd1.envelope.decision_kind == "STOP",
        "description": "Scientific falsification prioritized over convenient replication",
    }

    # CF-RD9 no informative action → STOP
    rd9 = decide_first_experiment_research_action(
        prop,
        pkg,
        interp.envelope,
        session_id="cf-rd9",
        budget_exhausted_override=True,
    )
    cf["CF-RD9"] = {
        "passed": rd9.envelope.decision_kind == "STOP",
        "description": "When no informative action, STOP",
    }

    # CF-RD10 execution leakage
    cf["CF-RD10"] = {
        "passed": rd1.envelope.second_experiment_generated is False
        and rd1.envelope.second_experiment_executed is False
        and rd1.experiment_generated is False
        and rd1.experiment_executed is False,
        "description": "No second experiment package or execution",
    }

    all_passed = all(v.get("passed") for v in cf.values())
    return {"benchmark_version": BENCHMARK_VERSION, "counterfactuals": cf, "all_passed": all_passed}
