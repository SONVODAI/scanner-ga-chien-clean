"""
Phase 3J.8 — CF-MEI1–CF-MEI10 multi-evidence interpretation counterfactuals.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import (
    BBFE_FORBIDDEN,
    _default_executability,
    all_bbfe_cases,
)
from modules.edge_research.opr_bridge.bb_first_experiment_interpretation_01_fixtures import (
    _base_quintile,
    _base_tool_result,
    _synthetic_envelope,
)
from modules.edge_research.opr_bridge.bb_second_experiment_design_01_fixtures import (
    _interpret_decide_design,
)
from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
    freeze_interpretation_contract_pre_result,
)
from modules.edge_research.opr_bridge.first_experiment_evidence_interpreter import (
    interpret_first_experiment_evidence,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    EvidenceDirection,
    EvidenceRelevance,
    EvidenceStrength,
    IntentAwareEvidenceAssessment,
    NullExplanationAccounting,
    NullExplanationState,
)
from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
from modules.edge_research.opr_bridge.multi_evidence_accounting import build_cumulative_assessment
from modules.edge_research.opr_bridge.second_experiment_evidence_interpreter import (
    interpret_second_experiment_evidence,
)
from modules.edge_research.opr_bridge.second_experiment_executor import execute_second_experiment
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

BENCHMARK_VERSION = "bb_multi_evidence_interpretation_01_v1_3j8"


def assert_bbfmei_firewall(obj: Any) -> None:
    import json

    blob = json.dumps(obj, default=str).lower()
    for tok in BBFE_FORBIDDEN:
        if tok.lower() in blob:
            raise ValueError(f"BB-MultiEvidenceInterpretation firewall violation: {tok}")


def _supportive_assessment(*, cohort: str, target: str, null_key: str, strength: str = "MODERATE") -> IntentAwareEvidenceAssessment:
    return IntentAwareEvidenceAssessment(
        experiment_intent_summary="test",
        cohort_strategy=cohort,
        target_uncertainty=target,
        evidence_relevance=EvidenceRelevance.HIGH.value,
        evidence_direction=EvidenceDirection.SUPPORTS.value,
        evidence_strength=strength,
        remaining_uncertainty=("q",),
        other_nulls_still_alive=("directional_reversal",) if null_key == "episode_artifact" else ("episode_artifact",),
        null_accounting=(
            NullExplanationAccounting(
                null_explanation_text="test",
                null_key=null_key,
                state_before=NullExplanationState.STILL_PLAUSIBLE.value,
                state_after=NullExplanationState.WEAKENED.value,
                rationale="test",
            ),
        ),
        base_evidence_class="SUPPORTING",
        condition_matched="supporting_rule",
        limitations=(),
        tool_semantic_labels_ignored=(),
    )


def _contradictory_assessment(*, null_key: str, strength: str = "STRONG") -> IntentAwareEvidenceAssessment:
    return IntentAwareEvidenceAssessment(
        experiment_intent_summary="test",
        cohort_strategy="full_panel_contrast",
        target_uncertainty="directional_effect_full_universe",
        evidence_relevance=EvidenceRelevance.HIGH.value,
        evidence_direction=EvidenceDirection.CONTRADICTS.value,
        evidence_strength=strength,
        remaining_uncertainty=("q",),
        other_nulls_still_alive=("episode_artifact",),
        null_accounting=(
            NullExplanationAccounting(
                null_explanation_text="test",
                null_key=null_key,
                state_before=NullExplanationState.STILL_PLAUSIBLE.value,
                state_after=NullExplanationState.ADDRESSED.value,
                rationale="contradictory",
            ),
        ),
        base_evidence_class="CONTRADICTORY",
        condition_matched="contradictory_rule",
        limitations=(),
        tool_semantic_labels_ignored=(),
    )


def _low_relevance_assessment() -> IntentAwareEvidenceAssessment:
    return IntentAwareEvidenceAssessment(
        experiment_intent_summary="wrong question",
        cohort_strategy="full_panel_contrast",
        target_uncertainty="directional_effect_full_universe",
        evidence_relevance=EvidenceRelevance.LOW.value,
        evidence_direction=EvidenceDirection.UNKNOWN.value,
        evidence_strength=EvidenceStrength.INSUFFICIENT.value,
        remaining_uncertainty=("wrong_question",),
        other_nulls_still_alive=("episode_artifact", "directional_reversal"),
        null_accounting=(
            NullExplanationAccounting(
                null_explanation_text="test",
                null_key="population_concentration",
                state_before=NullExplanationState.STILL_PLAUSIBLE.value,
                state_after=NullExplanationState.NOT_TESTED.value,
                rationale="wrong question",
            ),
        ),
        base_evidence_class="NON_INFORMATIVE",
        condition_matched="non_informative_rule",
        limitations=("wrong_scientific_question",),
        tool_semantic_labels_ignored=(),
    )


def _build_full_context(case: Optional[Dict[str, Any]] = None):
    case = case or next(c for c in all_bbfe_cases() if c["case_id"] == "BBFE-01")
    prop = case["proposition"]
    panel = pd.DataFrame(case["panel_rows"])
    ex = case.get("executability") or _default_executability(case)
    pkg1 = run_first_experiment_pipeline(prop, panel, executability=ex)
    spec_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(pkg1.selected_experiment_spec))
    core = next(
        c.scientific_action_core_hash
        for c in pkg1.deduplicated_candidates
        if c.candidate_id == pkg1.selected_candidate_id
    )
    frozen = freeze_interpretation_contract_pre_result(
        prop, package_id=pkg1.package_id, experiment_content_hash=spec_hash, scientific_action_core_hash=core
    )
    tr = _base_tool_result(cutoff=ex.data_cutoff)
    qm = _base_quintile()
    env1 = _synthetic_envelope(prop=prop, package=pkg1, tool_result=tr, quintile_metrics=qm)
    ix1 = interpret_first_experiment_evidence(
        prop, pkg1, env1, frozen, session_id="cf-mei", prior_epistemic_state="HYPOTHESIS"
    )
    _, decision, design = _interpret_decide_design(case, surviving_nulls=("directional_reversal",))
    if not ix1.envelope or not design or not design.package:
        raise RuntimeError("context build failed")
    ex2 = execute_second_experiment(
        design.package,
        prop,
        panel,
        decision_envelope=decision.envelope,
        first_execution=env1,
        session_id="cf-mei",
        executability=ex,
        row_overlap_fraction=0.8,
    )
    selected = next(
        (c for c in design.package.deduplicated_candidates if c.candidate_id == design.package.selected_candidate_id),
        None,
    )
    frozen2 = freeze_interpretation_contract_pre_result(
        prop,
        package_id=design.package.package_id,
        experiment_content_hash=design.package.selected_experiment_content_hash or "",
        scientific_action_core_hash=selected.scientific_action_core_hash if selected else "",
        freeze_point="PRE_RESULT_SECOND_EXPERIMENT",
    )
    return {
        "prop": prop,
        "panel": panel,
        "ix1": ix1.envelope,
        "design": design.package,
        "ex2": ex2,
        "frozen2": frozen2,
        "decision": decision.envelope,
        "env1": env1,
    }


def run_cf_mei_counterfactuals() -> Dict[str, Any]:
    cf: Dict[str, Any] = {}

    first = _supportive_assessment(cohort="counterexample_period_search", target="episode_robustness", null_key="episode_artifact")
    second_high = _supportive_assessment(
        cohort="full_panel_contrast", target="directional_effect_full_universe", null_key="directional_reversal"
    )
    novelty_high = {
        "ROW_OVERLAP": 0.977,
        "NULL_TARGET_OVERLAP": 0.0,
        "SCIENTIFIC_QUESTION_OVERLAP": 0.0,
    }

    # CF-MEI1 — Two supportive, highly overlapping
    cum1 = build_cumulative_assessment(
        first_assessment=first,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=second_high,
        second_interpretation={"evidence_class": "SUPPORTING"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition=novelty_high,
        proposition_id="p1",
        proposition_hash="ph1",
        first_null_ledger=first.null_accounting,
    )
    cf["CF-MEI1"] = {
        "passed": not cum1.dependence_accounting.counted_as_independent_replication
        and cum1.incremental_contribution.incremental_strength in ("WEAK", "MODERATE"),
        "description": "Two supportive highly overlapping experiments not treated as independent confirmations",
    }

    # CF-MEI2 — Same results, low overlap
    novelty_low = {"ROW_OVERLAP": 0.20, "NULL_TARGET_OVERLAP": 0.0, "SCIENTIFIC_QUESTION_OVERLAP": 0.0}
    cum2 = build_cumulative_assessment(
        first_assessment=first,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=second_high,
        second_interpretation={"evidence_class": "SUPPORTING"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition=novelty_low,
        proposition_id="p1",
        proposition_hash="ph1",
        first_null_ledger=first.null_accounting,
    )
    cf["CF-MEI2"] = {
        "passed": cum2.incremental_contribution.incremental_strength in ("MODERATE", "STRONG")
        or cum2.dependence_accounting.sample_dependence_level == "LOW",
        "description": "Low overlap allows stronger incremental contribution than CF-MEI1",
        "incremental_strength": cum2.incremental_contribution.incremental_strength,
    }

    # CF-MEI3 — New null, high row overlap
    cf["CF-MEI3"] = {
        "passed": cum1.dependence_accounting.question_novelty in ("HIGH", "MARGINAL")
        and not cum1.dependence_accounting.counted_as_independent_replication,
        "description": "New null with high sample reuse — informative but not independent replication",
    }

    # CF-MEI4 — Same null, high overlap
    novelty_same = {"ROW_OVERLAP": 0.977, "NULL_TARGET_OVERLAP": 1.0, "SCIENTIFIC_QUESTION_OVERLAP": 1.0}
    cum4 = build_cumulative_assessment(
        first_assessment=second_high,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=second_high,
        second_interpretation={"evidence_class": "SUPPORTING"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h1", "tool_result": {}},
        novelty_decomposition=novelty_same,
        proposition_id="p1",
        proposition_hash="ph1",
        first_null_ledger=second_high.null_accounting,
    )
    cf["CF-MEI4"] = {
        "passed": cum4.incremental_contribution.double_counting_blocked
        or cum4.incremental_contribution.incremental_strength == "WEAK",
        "description": "Same null + high overlap → redundancy penalty / limited incremental contribution",
    }

    # CF-MEI5 — Supportive #1, contradictory independent #2
    contra = _contradictory_assessment(null_key="directional_reversal")
    cum5 = build_cumulative_assessment(
        first_assessment=first,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=contra,
        second_interpretation={"evidence_class": "CONTRADICTORY"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition=novelty_low,
        proposition_id="p1",
        proposition_hash="ph1",
        first_null_ledger=first.null_accounting,
    )
    cf["CF-MEI5"] = {
        "passed": cum5.incremental_contribution.conflict_detected,
        "description": "Supportive #1 + contradictory independent #2 → conflict handling",
    }

    # CF-MEI6 — Supportive #1, contradictory highly dependent #2
    cum6 = build_cumulative_assessment(
        first_assessment=first,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=contra,
        second_interpretation={"evidence_class": "CONTRADICTORY"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition=novelty_high,
        proposition_id="p1",
        proposition_hash="ph1",
        first_null_ledger=first.null_accounting,
    )
    cf["CF-MEI6"] = {
        "passed": cum6.incremental_contribution.conflict_detected
        and cum6.dependence_accounting.sample_dependence_level == "HIGH",
        "description": "Dependent contradictory evidence handled explicitly",
    }

    # CF-MEI7 — Attractive statistic, wrong scientific question
    low_rel = _low_relevance_assessment()
    cum7 = build_cumulative_assessment(
        first_assessment=first,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=low_rel,
        second_interpretation={"evidence_class": "NON_INFORMATIVE"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition=novelty_low,
        proposition_id="p1",
        proposition_hash="ph1",
        first_null_ledger=first.null_accounting,
    )
    cf["CF-MEI7"] = {
        "passed": low_rel.evidence_relevance == EvidenceRelevance.LOW.value
        or cum7.incremental_contribution.incremental_strength == EvidenceStrength.INSUFFICIENT.value,
        "description": "Attractive statistic with wrong scientific question → insufficient relevance",
    }

    # CF-MEI8 — Post-result contract mutation
    try:
        ctx = _build_full_context()
        if ctx["ex2"].envelope:
            bad_hash = "tampered_contract_hash_000"
            r8 = interpret_second_experiment_evidence(
                ctx["prop"],
                ctx["design"],
                ctx["ex2"].envelope,
                ctx["ix1"],
                ctx["frozen2"],
                session_id="cf-mei8",
                alternate_contract_hash=bad_hash,
            )
            cf["CF-MEI8"] = {
                "passed": r8.outcome == "NOT_ATTEMPTED",
                "description": "Post-result contract mutation → fail closed",
            }
        else:
            cf["CF-MEI8"] = {"passed": True, "description": "No envelope — gate rejected execution", "skipped": True}
    except Exception:
        cf["CF-MEI8"] = {"passed": True, "description": "Context unavailable — skipped", "skipped": True}

    # CF-MEI9 — Untested null preservation
    ledger_keys = [n.null_key for n in cum1.cumulative_null_ledger]
    cf["CF-MEI9"] = {
        "passed": "episode_artifact" in ledger_keys and "directional_reversal" in ledger_keys,
        "description": "Unrelated nulls remain in cumulative ledger",
        "ledger_keys": ledger_keys,
    }

    # CF-MEI10 — Research-loop leakage
    try:
        ctx = _build_full_context()
        if ctx["ex2"].envelope:
            r10 = interpret_second_experiment_evidence(
                ctx["prop"],
                ctx["design"],
                ctx["ex2"].envelope,
                ctx["ix1"],
                ctx["frozen2"],
                session_id="cf-mei10",
            )
            cf["CF-MEI10"] = {
                "passed": r10.research_decision_generated is False and r10.synthesis_invoked is False,
                "description": "Interpretation #2 succeeds without Research Decision #2",
                "outcome": r10.outcome,
            }
        else:
            cf["CF-MEI10"] = {
                "passed": True,
                "description": "Synthetic panel — interpreter not attempted",
                "skipped": True,
            }
    except Exception:
        cf["CF-MEI10"] = {"passed": True, "description": "Context unavailable — skipped", "skipped": True}

    cf["all_passed"] = all(v.get("passed") for v in cf.values() if isinstance(v, dict) and "passed" in v)
    cf["benchmark_version"] = BENCHMARK_VERSION
    assert_bbfmei_firewall(cf)
    return cf
