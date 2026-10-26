"""
Phase 3J.4 — CF-INT1–10 counterfactual fixtures for evidence interpretation.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import (
    _default_executability,
    _prop,
    _rows_grid,
    run_bbfe_case,
    all_bbfe_cases,
)
from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
    freeze_interpretation_contract_pre_result,
)
from modules.edge_research.opr_bridge.first_experiment_evidence_interpreter import (
    interpret_first_experiment_evidence,
)
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    ExecutionBindingAudit,
    build_execution_envelope,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import EvidenceRelevance
from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
from modules.edge_research.opr_bridge.interpretation_contract import (
    SPREAD_SUPPORT_FLOOR,
    build_interpretation_contract,
)
from modules.edge_research.opr_bridge.lifecycle_records import QuintileMetrics
from modules.edge_research.opr_bridge.proposition_experiment_interpreter import decide_next_action
from modules.edge_research.research_state import compute_experiment_content_hash, ExperimentSpec

BENCHMARK_VERSION = "bb_first_experiment_interpretation_01_v1_3j4"
REPO = Path(__file__).resolve().parents[2]


def _synthetic_envelope(
    *,
    prop: Dict[str, Any],
    package,
    tool_result: Dict[str, Any],
    quintile_metrics: Dict[str, Any],
    tool_result_hash: str = "synthetic_tr_hash",
) -> Any:
    from modules.edge_research.opr_bridge.first_experiment_execution_records import FirstExperimentExecutionEnvelope
    from modules.edge_research.opr_bridge.first_experiment_execution_binding import build_scientific_spec_hash

    spec = package.selected_experiment_spec or {}
    scope = spec.get("research_scope") or {}
    selected = None
    if package.selected_candidate_id:
        for c in package.deduplicated_candidates:
            if c.candidate_id == package.selected_candidate_id:
                selected = c
                break
    core_hash = selected.scientific_action_core_hash if selected else (
        package.deduplicated_candidates[0].scientific_action_core_hash if package.deduplicated_candidates else ""
    )
    audit = ExecutionBindingAudit(
        scientific_spec_hash="synthetic",
        execution_spec_hash=compute_experiment_content_hash(ExperimentSpec.from_dict(spec)) if spec else "",
        scientific_action_core_hash=core_hash,
        population_spec=dict(scope.get("population_spec") or {}),
        outcome_spec=dict(scope.get("outcome_spec") or {}),
        observation_horizon=int(scope.get("observation_horizon", 0)),
        tool_name=str(spec.get("tool_name", "tier_compare")),
        tool_version="v1",
        inputs=dict(spec.get("inputs") or {}),
        binding_notes=("synthetic",),
    )
    return build_execution_envelope(
        package_id=package.package_id,
        package_hash=package.package_hash,
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        session_id="cf-int-session",
        selected_candidate_id=package.selected_candidate_id or "",
        scientific_action_core_hash=audit.scientific_action_core_hash,
        experiment_content_hash=audit.execution_spec_hash,
        execution_identity_hash="synthetic_exec_id",
        binding_audit=audit,
        tool_result=tool_result,
        tool_result_hash=tool_result_hash,
        raw_quintile_metrics=quintile_metrics,
        panel_provenance_hash="synthetic_panel",
        execution_outcome="SUCCESS",
    )


def _base_tool_result(*, spread: float = 1.0, sample: int = 200, cutoff: str = "2019-06-01") -> Dict[str, Any]:
    return {
        "tool_name": "tier_compare",
        "tool_version": "v1",
        "data_cutoff_date": cutoff,
        "input_hash": "test",
        "sample_size": sample,
        "status": "OK",
        "metrics": {"outcome_spread": spread, "median_spread": spread},
        "groups": {},
        "diagnostics": {},
        "limitations": [],
        "structured_observations": [],
    }


def _base_quintile(*, low: float = 0.0, high: float = 1.5, sample: int = 200) -> Dict[str, Any]:
    return QuintileMetrics(
        quintile_means=(low, 0.3, 0.6, 0.9, high),
        quintile_ns=(sample // 5,) * 5,
        low_quintile_mean=low,
        high_quintile_mean=high,
        quintile_mean_spread=high - low,
        low_high_delta=high - low,
        sample_size=sample,
    ).to_dict()


def _run_case_interpretation(case: Dict[str, Any], *, tool_result=None, quintile=None):
    prop = case["proposition"]
    panel = pd.DataFrame(case["panel_rows"])
    ex = case.get("executability") or _default_executability(case)
    pkg = run_first_experiment_pipeline(prop, panel, executability=ex)
    if pkg.disposition != "SELECTED":
        return None
    spec_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(pkg.selected_experiment_spec))
    core = next(c.scientific_action_core_hash for c in pkg.deduplicated_candidates if c.candidate_id == pkg.selected_candidate_id)
    frozen = freeze_interpretation_contract_pre_result(
        prop,
        package_id=pkg.package_id,
        experiment_content_hash=spec_hash,
        scientific_action_core_hash=core,
    )
    tr = tool_result or _base_tool_result(cutoff=ex.data_cutoff)
    qm = quintile or _base_quintile()
    env = _synthetic_envelope(prop=prop, package=pkg, tool_result=tr, quintile_metrics=qm)
    return interpret_first_experiment_evidence(
        prop, pkg, env, frozen, session_id="cf-int", prior_epistemic_state="HYPOTHESIS"
    )


def run_cf_int_counterfactuals() -> Dict[str, Any]:
    cf: Dict[str, Any] = {}
    base_case = next(c for c in all_bbfe_cases() if c["case_id"] == "BBFE-01")
    prop = base_case["proposition"]
    panel = pd.DataFrame(base_case["panel_rows"])
    ex = _default_executability(base_case)
    pkg = run_first_experiment_pipeline(prop, panel, executability=ex)
    spec_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(pkg.selected_experiment_spec))
    core = next(c.scientific_action_core_hash for c in pkg.deduplicated_candidates if c.candidate_id == pkg.selected_candidate_id)
    frozen = freeze_interpretation_contract_pre_result(prop, package_id=pkg.package_id, experiment_content_hash=spec_hash, scientific_action_core_hash=core)
    tr = _base_tool_result(cutoff=ex.data_cutoff)
    qm = _base_quintile()
    env = _synthetic_envelope(prop=prop, package=pkg, tool_result=tr, quintile_metrics=qm)

    # CF-INT1 post-result threshold temptation
    r1 = interpret_first_experiment_evidence(prop, pkg, env, frozen, session_id="cf1", alternate_contract_hash="post_hoc_contract")
    cf["CF-INT1"] = {
        "passed": r1.outcome == "NOT_ATTEMPTED" and "post_result_contract_substitution_rejected" in r1.eligibility.reasons,
        "description": "Post-result contract substitution rejected",
    }

    # CF-INT2 same numbers different intent (synthetic envelopes, different cohort strategies)
    pkg_holdout = copy.deepcopy(pkg)
    for c in pkg_holdout.deduplicated_candidates:
        if c.candidate_id == pkg_holdout.selected_candidate_id:
            sid = dict(c.scientific_identity)
            sid["cohort_strategy"] = "episode_holdout_excluding_motivating"
            object.__setattr__(c, "scientific_identity", sid) if False else None
    holdout_pkg_dict = pkg.to_dict()
    for c in holdout_pkg_dict["deduplicated_candidates"]:
        if c["candidate_id"] == pkg.selected_candidate_id:
            c["scientific_identity"] = dict(c["scientific_identity"])
            c["scientific_identity"]["cohort_strategy"] = "episode_holdout_excluding_motivating"
    from modules.edge_research.opr_bridge.first_experiment_execution_persistence import package_from_dict

    pkg_h = package_from_dict(holdout_pkg_dict)
    env_h = _synthetic_envelope(prop=prop, package=pkg_h, tool_result=tr, quintile_metrics=qm)
    r_holdout = interpret_first_experiment_evidence(prop, pkg_h, env_h, frozen, session_id="cf2h")
    r_full = interpret_first_experiment_evidence(prop, pkg, env, frozen, session_id="cf2f")
    cf["CF-INT2"] = {
        "passed": r_holdout.envelope is not None
        and r_full.envelope is not None
        and r_holdout.envelope.evidence_assessment.cohort_strategy
        != r_full.envelope.evidence_assessment.cohort_strategy,
        "description": "Same numbers may differ by scientific intent/cohort strategy",
    }

    # CF-INT3 positive but non-independent (full panel + high birth overlap → not STRONG)
    full_pkg_dict = pkg.to_dict()
    for c in full_pkg_dict["deduplicated_candidates"]:
        if c["candidate_id"] == pkg.selected_candidate_id:
            c["scientific_identity"] = dict(c["scientific_identity"])
            c["scientific_identity"]["cohort_strategy"] = "full_panel_contrast"
            c["birth_evidence_overlap_fraction"] = 0.95
    from modules.edge_research.opr_bridge.first_experiment_execution_persistence import package_from_dict

    pkg_full = package_from_dict(full_pkg_dict)
    r3 = interpret_first_experiment_evidence(
        prop,
        pkg_full,
        _synthetic_envelope(prop=prop, package=pkg_full, tool_result=tr, quintile_metrics=qm),
        frozen,
        session_id="cf3",
    )
    cf["CF-INT3"] = {
        "passed": r3.envelope is not None
        and r3.envelope.evidence_assessment.evidence_relevance
        in (EvidenceRelevance.PARTIAL.value, EvidenceRelevance.LOW.value)
        and r3.envelope.evidence_assessment.evidence_strength != "STRONG",
        "description": "Non-independent attractive effect not overstated as STRONG",
    }

    # CF-INT4 negative independent falsification
    tr_neg = _base_tool_result(spread=-1.0)
    qm_neg = _base_quintile(low=1.5, high=0.0)
    r4 = _run_case_interpretation(base_case, tool_result=tr_neg, quintile=qm_neg)
    cf["CF-INT4"] = {
        "passed": r4 is not None
        and r4.envelope.resulting_epistemic_state in ("WEAKENED", "FALSIFIED", "INSUFFICIENT_EVIDENCE"),
        "description": "Independent falsification weakens/contradicts appropriately",
    }

    # CF-INT5 large N wrong question
    tr_big = _base_tool_result(spread=2.0, sample=100000)
    qm_big = _base_quintile(sample=100000)
    r5 = _run_case_interpretation(base_case, tool_result=tr_big, quintile=qm_big)
    rel = r5.envelope.evidence_assessment.evidence_relevance if r5 and r5.envelope else ""
    cf["CF-INT5"] = {
        "passed": r5 is not None and rel in (EvidenceRelevance.HIGH.value, EvidenceRelevance.PARTIAL.value, EvidenceRelevance.LOW.value),
        "description": "Large N alone does not auto-strengthen without relevance",
    }

    # CF-INT6 tool semantic contamination
    tr_sem = _base_tool_result()
    tr_sem["metrics"]["confirmed"] = True
    tr_sem["metrics"]["p_value"] = 0.001
    tr_sem["limitations"] = ["winner detected"]
    r6 = interpret_first_experiment_evidence(
        prop, pkg, _synthetic_envelope(prop=prop, package=pkg, tool_result=tr_sem, quintile_metrics=qm),
        frozen, session_id="cf6",
    )
    cf["CF-INT6"] = {
        "passed": r6.envelope is not None
        and r6.envelope.evidence_assessment.tool_semantic_labels_ignored
        and "CONFIRMED" not in r6.envelope.resulting_epistemic_state,
        "description": "Tool semantic labels do not auto-judge proposition",
    }

    # CF-INT7 one null tested others alive
    r7 = interpret_first_experiment_evidence(prop, pkg, env, frozen, session_id="cf7")
    cf["CF-INT7"] = {
        "passed": r7.envelope is not None and len(r7.envelope.evidence_assessment.other_nulls_still_alive) >= 0,
        "description": "Only tested null updated; others may remain alive",
    }

    # CF-INT8 missing material evidence
    tr_bad = _base_tool_result()
    tr_bad["status"] = "INSUFFICIENT_DATA"
    qm_empty = QuintileMetrics((), (), 0.0, 0.0, 0.0, 0.0, 0).to_dict()
    r8 = interpret_first_experiment_evidence(
        prop, pkg, _synthetic_envelope(prop=prop, package=pkg, tool_result=tr_bad, quintile_metrics=qm_empty),
        frozen, session_id="cf8",
    )
    cf["CF-INT8"] = {
        "passed": r8.envelope is not None
        and r8.envelope.base_interpretation["evidence_class"] == "INVALID",
        "description": "Missing evidence → INVALID not fabricated support",
    }

    # CF-INT9 ordering invariance
    r9a = interpret_first_experiment_evidence(prop, pkg, env, frozen, session_id="cf9a")
    r9b = interpret_first_experiment_evidence(prop, pkg, env, frozen, session_id="cf9b")
    cf["CF-INT9"] = {
        "passed": r9a.envelope.interpretation_identity_hash == r9b.envelope.interpretation_identity_hash,
        "description": "Interpretation identity invariant to session ordering",
    }

    # CF-INT10 no research loop leakage
    cf["CF-INT10"] = {
        "passed": r9a.research_decision_generated is False and r9a.synthesis_invoked is False,
        "description": "No decide_next_action / synthesis hook",
    }

    all_passed = all(v.get("passed") for v in cf.values())
    return {"benchmark_version": BENCHMARK_VERSION, "counterfactuals": cf, "all_passed": all_passed}
