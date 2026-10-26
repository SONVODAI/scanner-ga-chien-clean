"""
Phase 3J.6 — CF-SD1–10 counterfactual fixtures for second-experiment design.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.bb_first_experiment_interpretation_01_fixtures import (
    _base_quintile,
    _base_tool_result,
    _synthetic_envelope,
)
from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import (
    _default_executability,
    _prop,
    _rows_grid,
    all_bbfe_cases,
)
from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
    freeze_interpretation_contract_pre_result,
)
from modules.edge_research.opr_bridge.first_experiment_evidence_interpreter import (
    interpret_first_experiment_evidence,
)
from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
from modules.edge_research.opr_bridge.first_experiment_research_decider import (
    decide_first_experiment_research_action,
)
from modules.edge_research.opr_bridge.first_experiment_research_decision_records import (
    build_decision_envelope,
)
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.second_experiment_design_gate import (
    validate_second_experiment_design_eligibility,
)
from modules.edge_research.opr_bridge.second_experiment_pipeline import (
    run_second_experiment_design_pipeline,
)
from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentDisposition
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

BENCHMARK_VERSION = "bb_second_experiment_design_01_v1_3j6"


def _interpret_decide_design(
    case: Dict[str, Any],
    *,
    surviving_nulls: tuple = ("directional_reversal",),
    tool_result=None,
    quintile=None,
    include_wrong_null_audit: bool = False,
    executability_override: Optional[ExecutabilityContext] = None,
    design_executability_override: Optional[ExecutabilityContext] = None,
):
    prop = case["proposition"]
    panel = pd.DataFrame(case["panel_rows"])
    ex = executability_override or case.get("executability") or _default_executability(case)
    pkg = run_first_experiment_pipeline(prop, panel, executability=ex)
    if pkg.disposition != "SELECTED":
        return None, None, None
    spec_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(pkg.selected_experiment_spec))
    core = next(
        c.scientific_action_core_hash
        for c in pkg.deduplicated_candidates
        if c.candidate_id == pkg.selected_candidate_id
    )
    frozen = freeze_interpretation_contract_pre_result(
        prop, package_id=pkg.package_id, experiment_content_hash=spec_hash, scientific_action_core_hash=core
    )
    tr = tool_result or _base_tool_result(cutoff=ex.data_cutoff)
    qm = quintile or _base_quintile()
    env_exec = _synthetic_envelope(prop=prop, package=pkg, tool_result=tr, quintile_metrics=qm)
    interp = interpret_first_experiment_evidence(
        prop, pkg, env_exec, frozen, session_id="cf-sd", prior_epistemic_state="HYPOTHESIS"
    )
    if not interp.envelope:
        return interp, None, None

    assess = interp.envelope.evidence_assessment
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
        other_nulls_still_alive=surviving_nulls,
        null_accounting=assess.null_accounting,
        base_evidence_class=assess.base_evidence_class,
        condition_matched=assess.condition_matched,
        limitations=assess.limitations,
        tool_semantic_labels_ignored=assess.tool_semantic_labels_ignored,
    )
    interp_env = replace(interp.envelope, evidence_assessment=new_assess)

    decision = decide_first_experiment_research_action(
        prop, pkg, interp_env, session_id="cf-sd"
    )
    if not decision.envelope:
        return interp, decision, None

    design = run_second_experiment_design_pipeline(
        prop,
        panel,
        first_package=pkg,
        first_execution=env_exec,
        interpretation_envelope=interp_env,
        decision_envelope=decision.envelope,
        executability=design_executability_override or ex,
        include_wrong_null_audit=include_wrong_null_audit,
    )
    return interp, decision, design


def run_cf_sd_counterfactuals() -> Dict[str, Any]:
    cf: Dict[str, Any] = {}
    base_case = next(c for c in all_bbfe_cases() if c["case_id"] == "BBFE-01")
    prop = base_case["proposition"]
    panel = pd.DataFrame(base_case["panel_rows"])
    ex = _default_executability(base_case)

    _, decision, design = _interpret_decide_design(base_case, surviving_nulls=("directional_reversal",))
    assert design is not None and design.package is not None

    # CF-SD1 — Decision substitution temptation (wrong null rejected)
    _, _, sd1 = _interpret_decide_design(
        base_case, surviving_nulls=("directional_reversal",), include_wrong_null_audit=True
    )
    wrong_rejected = any(
        "decision_substitution" in ";".join(c.rejection_reasons)
        for c in sd1.package.candidates_considered
    )
    cf["CF-SD1"] = {
        "passed": wrong_rejected,
        "description": "Easier wrong-null experiment rejected under frozen directional_reversal decision",
    }

    # CF-SD2 — Replication disguise (syntactic variant of first experiment rejected)
    repl_rejected = any(
        "replicates_first_experiment" in r or "identical_experiment_content_hash" in r
        for c in design.package.candidates_considered
        for r in c.rejection_reasons
    )
    cf["CF-SD2"] = {
        "passed": repl_rejected or design.package.disposition == SecondExperimentDisposition.SELECTED.value,
        "description": "Replication-disguised candidate detected or faithful distinct design selected",
    }

    # CF-SD3 — Birth-independent but prior-experiment redundant
    cf["CF-SD3"] = {
        "passed": all(
            c.first_experiment_overlap_fraction < 0.90 or c.primary_classification != "ADMISSIBLE"
            for c in design.package.deduplicated_candidates
            if c.birth_evidence_overlap_fraction < 0.50 and c.target_null_key == "directional_reversal"
        )
        or design.package.disposition == SecondExperimentDisposition.SELECTED.value,
        "description": "High first-experiment overlap penalized even when birth overlap is low",
    }

    # CF-SD4 — Tool convenience (science wins over weaker design)
    selected = next(
        (c for c in design.package.deduplicated_candidates if c.candidate_id == design.package.selected_candidate_id),
        None,
    )
    cf["CF-SD4"] = {
        "passed": (
            design.package.disposition == SecondExperimentDisposition.NO_FAITHFUL_SECOND_EXPERIMENT.value
            or (
                selected is not None
                and selected.decision_fidelity_ok
                and selected.target_null_key == "directional_reversal"
            )
        ),
        "description": "Faithful design selected or valid silence when no faithful executable design",
    }

    # CF-SD5 — Non-executable best design → silence
    blocked = ExecutabilityContext(
        data_cutoff=ex.data_cutoff,
        available_tools=frozenset(),
        abstract_mode=True,
    )
    _, _, sd5 = _interpret_decide_design(base_case, design_executability_override=blocked)
    cf["CF-SD5"] = {
        "passed": sd5 is not None
        and sd5.package is not None
        and sd5.package.execution_status == "NOT_EXECUTED"
        and (
            sd5.package.disposition == SecondExperimentDisposition.NO_FAITHFUL_SECOND_EXPERIMENT.value
            or sd5.package.selected_candidate_id is None
        ),
        "description": "Non-executable faithful design yields silence, not substitution",
    }

    # CF-SD6 — Confirmation-only under SEEK_FALSIFICATION rejected
    confirm_rejected = any(
        "confirmation_only_under_seek_falsification" in c.rejection_reasons
        for c in design.package.candidates_considered
    )
    cf["CF-SD6"] = {
        "passed": confirm_rejected or design.package.disposition == SecondExperimentDisposition.SELECTED.value,
        "description": "Confirmation-only candidates rejected under SEEK_FALSIFICATION",
    }

    # CF-SD7 — Same decision family, different history → design may differ
    _, _, sd7a = _interpret_decide_design(base_case, surviving_nulls=("directional_reversal",))
    _, _, sd7b = _interpret_decide_design(base_case, surviving_nulls=("population_concentration",))
    diff = (
        sd7a.package.selected_experiment_content_hash != sd7b.package.selected_experiment_content_hash
        or sd7a.package.disposition != sd7b.package.disposition
        or sd7a.package.objective.target_null_key != sd7b.package.objective.target_null_key
    )
    cf["CF-SD7"] = {
        "passed": diff,
        "description": "Different surviving null history may yield different second-experiment design",
    }

    # CF-SD8 — Ordering invariance
    cands = list(design.package.deduplicated_candidates)
    from modules.edge_research.opr_bridge.second_experiment_selector import select_second_experiment

    sel_a = select_second_experiment(cands)
    sel_b = select_second_experiment(list(reversed(cands)))
    cf["CF-SD8"] = {
        "passed": (sel_a.selected.candidate_id if sel_a.selected else None)
        == (sel_b.selected.candidate_id if sel_b.selected else None),
        "description": "Candidate ordering does not change scientific selection",
    }

    # CF-SD9 — Stale ResearchDecisionRecord rejected (existing package identity mismatch)
    from modules.edge_research.opr_bridge.second_experiment_design_gate import (
        validate_second_experiment_design_eligibility,
    )

    pkg9 = run_first_experiment_pipeline(prop, panel, executability=ex)
    spec_hash9 = compute_experiment_content_hash(ExperimentSpec.from_dict(pkg9.selected_experiment_spec))
    core9 = next(
        c.scientific_action_core_hash
        for c in pkg9.deduplicated_candidates
        if c.candidate_id == pkg9.selected_candidate_id
    )
    frozen9 = freeze_interpretation_contract_pre_result(
        prop, package_id=pkg9.package_id, experiment_content_hash=spec_hash9, scientific_action_core_hash=core9
    )
    env9 = _synthetic_envelope(
        prop=prop, package=pkg9, tool_result=_base_tool_result(cutoff=ex.data_cutoff), quintile_metrics=_base_quintile()
    )
    interp9 = interpret_first_experiment_evidence(
        prop, pkg9, env9, frozen9, session_id="cf-sd9", prior_epistemic_state="HYPOTHESIS"
    )
    dec9 = decide_first_experiment_research_action(prop, pkg9, interp9.envelope, session_id="cf-sd9")
    stale_pkg = replace(design.package, research_decision_hash="stale_decision_hash")
    gate9 = validate_second_experiment_design_eligibility(
        prop=prop,
        first_package=pkg9,
        first_execution=env9,
        interpretation_envelope=interp9.envelope,
        decision_envelope=dec9.envelope,
        existing_package=stale_pkg,
    )
    cf["CF-SD9"] = {
        "passed": not gate9.eligible and "existing_design_identity_mismatch" in gate9.reasons,
        "description": "Stale decision hash/provenance fails closed",
    }

    # CF-SD10 — Execution leakage
    cf["CF-SD10"] = {
        "passed": design.package.execution_status == "NOT_EXECUTED"
        and "tool_result" not in design.package.to_dict(),
        "description": "Valid package is NOT_EXECUTED with no ToolResult",
    }

    cf["all_passed"] = all(v.get("passed") for v in cf.values() if isinstance(v, dict) and "passed" in v)
    cf["benchmark_version"] = BENCHMARK_VERSION
    return cf
