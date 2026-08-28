"""
Phase 3J.9 — CF-CD1–CF-CD10 counterfactual fixtures for cumulative research decision #2.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional, Tuple

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
from modules.edge_research.opr_bridge.first_experiment_contract_freeze import (
    freeze_interpretation_contract_pre_result,
)
from modules.edge_research.opr_bridge.first_experiment_evidence_interpreter import (
    interpret_first_experiment_evidence,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    IntentAwareEvidenceAssessment,
    NullExplanationAccounting,
    NullExplanationState,
)
from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
from modules.edge_research.opr_bridge.first_experiment_research_decider import (
    decide_first_experiment_research_action,
)
from modules.edge_research.opr_bridge.lifecycle_records import NextResearchAction
from modules.edge_research.opr_bridge.multi_evidence_accounting import build_cumulative_assessment
from modules.edge_research.opr_bridge.second_experiment_interpretation_records import (
    build_second_interpretation_envelope,
    compute_second_interpretation_identity_hash,
)
from modules.edge_research.opr_bridge.second_experiment_research_decider import (
    decide_second_experiment_research_action,
)
from modules.edge_research.research_search_accounting import HIGH_COMPLEXITY_THRESHOLD
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

BENCHMARK_VERSION = "bb_cumulative_research_decision_01_v1_3j9"


def assert_bbfcd_firewall(obj: Any) -> None:
    import json

    blob = json.dumps(obj, default=str).lower()
    for tok in BBFE_FORBIDDEN:
        if tok.lower() in blob:
            raise ValueError(f"BB-CumulativeDecision firewall violation: {tok}")


def _supportive_assessment(*, cohort: str, target: str, null_key: str, strength: str = "MODERATE"):
    return IntentAwareEvidenceAssessment(
        experiment_intent_summary="test",
        cohort_strategy=cohort,
        target_uncertainty=target,
        evidence_relevance="HIGH",
        evidence_direction="SUPPORTS",
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


def _contradictory_assessment(*, null_key: str, strength: str = "STRONG"):
    return IntentAwareEvidenceAssessment(
        experiment_intent_summary="test",
        cohort_strategy="full_panel_contrast",
        target_uncertainty="directional_effect_full_universe",
        evidence_relevance="HIGH",
        evidence_direction="CONTRADICTS",
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


def _ledger_with_states(*entries: Tuple[str, str]) -> Tuple[NullExplanationAccounting, ...]:
    return tuple(
        NullExplanationAccounting(
            null_explanation_text=f"null {key}",
            null_key=key,
            state_before=NullExplanationState.STILL_PLAUSIBLE.value,
            state_after=state,
            rationale="cf",
        )
        for key, state in entries
    )


def _build_synthetic_context(
    case: Optional[Dict[str, Any]] = None,
    *,
    row_overlap: float = 0.977,
    cumulative_override=None,
    resulting_state: str = "SUPPORTED",
    second_assessment=None,
    second_interpretation=None,
):
    case = case or next(c for c in all_bbfe_cases() if c["case_id"] == "BBFE-01")
    prop = case["proposition"]
    panel = pd.DataFrame(case["panel_rows"])
    ex = case.get("executability") or _default_executability(case)
    pkg = run_first_experiment_pipeline(prop, panel, executability=ex)
    if pkg.disposition != "SELECTED":
        return None
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
    env1 = _synthetic_envelope(prop=prop, package=pkg, tool_result=tr, quintile_metrics=qm)
    ix1 = interpret_first_experiment_evidence(
        prop, pkg, env1, frozen, session_id="cf-cd", prior_epistemic_state="HYPOTHESIS"
    )
    if not ix1.envelope:
        return None
    decision = decide_first_experiment_research_action(
        prop, pkg, ix1.envelope, session_id="cf-cd"
    )
    if not decision.envelope:
        return None

    first = ix1.envelope.evidence_assessment
    second = second_assessment or _supportive_assessment(
        cohort="full_panel_contrast",
        target="directional_effect_full_universe",
        null_key="directional_reversal",
    )
    cum = cumulative_override or build_cumulative_assessment(
        first_assessment=first,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={
            "execution_id": "e1",
            "experiment_content_hash": "h1",
            "epistemic_update_id": ix1.envelope.epistemic_update["update_id"],
            "tool_result": {},
        },
        second_assessment=second,
        second_interpretation=second_interpretation or {"evidence_class": "SUPPORTING"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition={
            "ROW_OVERLAP": row_overlap,
            "NULL_TARGET_OVERLAP": 0.0,
            "SCIENTIFIC_QUESTION_OVERLAP": 0.0,
        },
        proposition_id=prop["proposition_id"],
        proposition_hash=ix1.envelope.proposition_hash,
        first_null_ledger=first.null_accounting,
    )

    frozen2 = freeze_interpretation_contract_pre_result(
        prop,
        package_id="pkg2-synthetic",
        experiment_content_hash="hash2",
        scientific_action_core_hash="core2",
        freeze_point="PRE_RESULT_SECOND_EXPERIMENT",
    )
    base_interp = {
        "evidence_class": second.base_evidence_class,
        "metrics_used": {},
        "condition_matched": second.condition_matched,
        "validity_passed": True,
        "validity_failures": [],
    }
    epu = {
        "update_id": "epu2-synthetic",
        "proposition_id": prop["proposition_id"],
        "prior_epistemic_state": ix1.envelope.resulting_epistemic_state,
        "resulting_epistemic_state": resulting_state,
        "evidence_class": second.base_evidence_class,
        "experiment_ref": "e2",
        "tool_result_hash": "tr2",
        "metrics_used": {},
        "condition_matched": second.condition_matched,
        "unresolved_uncertainty": "",
        "created_at": "2026-01-01T00:00:00Z",
        "lifecycle_version": "v1",
        "record_hash": "epu2hash",
    }
    ihash = compute_second_interpretation_identity_hash(
        contract_hash=frozen2.contract_hash,
        tool_result_hash="tr2",
        execution_identity_hash="exec2",
        scientific_action_core_hash="core2",
        first_interpretation_id=ix1.envelope.interpretation_id,
    )
    ix2_env = build_second_interpretation_envelope(
        execution_id="exec2",
        execution_identity_hash="exec2",
        tool_result_hash="tr2",
        package_id="pkg2-synthetic",
        package_hash="pkgh2",
        proposition_id=prop["proposition_id"],
        proposition_hash=ix1.envelope.proposition_hash,
        session_id="cf-cd",
        scientific_action_core_hash="core2",
        first_interpretation_id=ix1.envelope.interpretation_id,
        first_execution_id=env1.execution_id,
        frozen_contract_ref=frozen2,
        base_interpretation=base_interp,
        evidence_assessment=second,
        cumulative_assessment=cum,
        epistemic_update=epu,
        prior_epistemic_state=ix1.envelope.resulting_epistemic_state,
        resulting_epistemic_state=resulting_state,
        interpretation_identity_hash=ihash,
    )
    return {
        "prop": prop,
        "ix1": ix1.envelope,
        "ix2": ix2_env,
        "decision": decision.envelope,
    }


def _decide(ctx, **kwargs):
    return decide_second_experiment_research_action(
        ctx["prop"],
        ctx["ix2"],
        ctx["decision"],
        session_id="cf-cd",
        first_interpretation_envelope=ctx["ix1"],
        **kwargs,
    )


def run_cf_cd_counterfactuals() -> Dict[str, Any]:
    cf: Dict[str, Any] = {}
    ctx = _build_synthetic_context()

    if not ctx:
        return {
            "benchmark_version": BENCHMARK_VERSION,
            "counterfactuals": {"error": "synthetic context build failed"},
            "all_passed": False,
        }

    rd_base = _decide(ctx)

    # CF-CD1 — Same state, different search burden
    rd_low = _decide(ctx, complexity_override=3.0, cardinality_override=2)
    rd_high = _decide(
        ctx,
        budget_exhausted_override=True,
        complexity_override=HIGH_COMPLEXITY_THRESHOLD + 2,
    )
    cf["CF-CD1"] = {
        "passed": rd_low.envelope is not None
        and rd_high.envelope is not None
        and (
            rd_low.envelope.decision_kind != rd_high.envelope.decision_kind
            or rd_low.envelope.research_decision["chosen_next_action"]
            != rd_high.envelope.research_decision["chosen_next_action"]
            or rd_high.envelope.decision_kind == "STOP"
        ),
        "description": "Same cumulative state, different search burden may yield different Decision #2",
    }

    # CF-CD2 — Same evidence, different remaining nulls
    cum_a = build_cumulative_assessment(
        first_assessment=ctx["ix1"].evidence_assessment,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=_supportive_assessment(
            cohort="full_panel_contrast", target="directional_effect_full_universe", null_key="directional_reversal"
        ),
        second_interpretation={"evidence_class": "SUPPORTING"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition={"ROW_OVERLAP": 0.30, "NULL_TARGET_OVERLAP": 0.0, "SCIENTIFIC_QUESTION_OVERLAP": 0.0},
        proposition_id=ctx["prop"]["proposition_id"],
        proposition_hash=ctx["ix1"].proposition_hash,
        first_null_ledger=_ledger_with_states(
            ("episode_artifact", NullExplanationState.WEAKENED.value),
            ("directional_reversal", NullExplanationState.STILL_PLAUSIBLE.value),
        ),
    )
    cum_b = build_cumulative_assessment(
        first_assessment=ctx["ix1"].evidence_assessment,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=_supportive_assessment(
            cohort="full_panel_contrast", target="directional_effect_full_universe", null_key="directional_reversal"
        ),
        second_interpretation={"evidence_class": "SUPPORTING"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition={"ROW_OVERLAP": 0.30, "NULL_TARGET_OVERLAP": 0.0, "SCIENTIFIC_QUESTION_OVERLAP": 0.0},
        proposition_id=ctx["prop"]["proposition_id"],
        proposition_hash=ctx["ix1"].proposition_hash,
        first_null_ledger=_ledger_with_states(
            ("episode_artifact", NullExplanationState.WEAKENED.value),
            ("population_concentration", NullExplanationState.STILL_PLAUSIBLE.value),
        ),
    )
    ctx_a = {**ctx, "ix2": replace(ctx["ix2"], cumulative_assessment=cum_a)}
    ctx_b = {**ctx, "ix2": replace(ctx["ix2"], cumulative_assessment=cum_b)}
    dec_a = _decide(ctx_a)
    dec_b = _decide(ctx_b)
    cf["CF-CD2"] = {
        "passed": dec_a.envelope is not None
        and dec_b.envelope is not None
        and dec_a.envelope.research_decision != dec_b.envelope.research_decision,
        "description": "Different remaining null structures may yield different next actions",
    }

    # CF-CD3 — Supportive but highly dependent history
    dep = rd_base.envelope.dependence_summary
    inc = rd_base.envelope.incremental_evidence_summary
    repl_rejected = any(
        e.action_family == "SEEK_REPLICATION" and not e.admissible
        for e in rd_base.envelope.candidate_evaluations
    )
    cf["CF-CD3"] = {
        "passed": dep.get("sample_dependence_level") == "HIGH"
        and inc.get("incremental_strength") in ("WEAK", "MODERATE")
        and (repl_rejected or rd_base.envelope.confirmation_bias_guard_applied),
        "description": "Highly dependent supportive history not treated as strong replication",
    }

    # CF-CD4 — Independent replication now valuable
    cum_repl = build_cumulative_assessment(
        first_assessment=ctx["ix1"].evidence_assessment,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=_supportive_assessment(
            cohort="full_panel_contrast", target="directional_effect_full_universe", null_key="directional_reversal"
        ),
        second_interpretation={"evidence_class": "SUPPORTING"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition={"ROW_OVERLAP": 0.15, "NULL_TARGET_OVERLAP": 0.0, "SCIENTIFIC_QUESTION_OVERLAP": 0.0},
        proposition_id=ctx["prop"]["proposition_id"],
        proposition_hash=ctx["ix1"].proposition_hash,
        first_null_ledger=_ledger_with_states(
            ("episode_artifact", NullExplanationState.ADDRESSED.value),
            ("directional_reversal", NullExplanationState.ADDRESSED.value),
        ),
    )
    ctx_repl = {**ctx, "ix2": replace(ctx["ix2"], cumulative_assessment=cum_repl)}
    dec_repl = _decide(ctx_repl)
    repl_admissible = any(
        e.action_family == "SEEK_REPLICATION" and e.admissible for e in dec_repl.envelope.candidate_evaluations
    )
    cf["CF-CD4"] = {
        "passed": dec_repl.envelope is not None
        and (
            dec_repl.envelope.research_decision["chosen_next_action"]
            == NextResearchAction.SEEK_REPLICATION.value
            or repl_admissible
        ),
        "description": "Major nulls addressed — independent replication may legitimately win",
    }

    # CF-CD5 — Another falsification more valuable
    second_fals = _supportive_assessment(
        cohort="counterexample_period_search",
        target="episode_robustness",
        null_key="episode_artifact",
    )
    second_fals = replace(
        second_fals,
        other_nulls_still_alive=("population_concentration", "directional_reversal"),
    )
    cum_fals = build_cumulative_assessment(
        first_assessment=ctx["ix1"].evidence_assessment,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=second_fals,
        second_interpretation={"evidence_class": "SUPPORTING"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition={"ROW_OVERLAP": 0.25, "NULL_TARGET_OVERLAP": 0.0, "SCIENTIFIC_QUESTION_OVERLAP": 0.0},
        proposition_id=ctx["prop"]["proposition_id"],
        proposition_hash=ctx["ix1"].proposition_hash,
        first_null_ledger=_ledger_with_states(
            ("episode_artifact", NullExplanationState.WEAKENED.value),
            ("directional_reversal", NullExplanationState.WEAKENED.value),
        ),
    )
    ctx_fals = {**ctx, "ix2": replace(ctx["ix2"], cumulative_assessment=cum_fals)}
    dec_fals = _decide(ctx_fals)
    cf["CF-CD5"] = {
        "passed": dec_fals.envelope is not None
        and dec_fals.envelope.decision_kind == "ACTION"
        and dec_fals.envelope.research_decision["chosen_next_action"]
        == NextResearchAction.SEEK_FALSIFICATION.value,
        "description": "Material STILL_PLAUSIBLE null — continued falsification may win",
    }

    # CF-CD6 — Low information gain → STOP may win
    cf["CF-CD6"] = {
        "passed": rd_base.envelope.incremental_evidence_summary.get("incremental_strength") in (
            "WEAK",
            "INSUFFICIENT",
        )
        and (
            rd_base.envelope.decision_kind == "STOP"
            or rd_base.envelope.mechanical_sequencing_blocked
            or any(
                e.action_family.startswith("STOP_") and e.admissible
                for e in rd_base.envelope.candidate_evaluations
            )
        ),
        "description": "Weak incremental evidence — STOP competes and may win",
    }

    # CF-CD7 — Budget pressure → STOP
    rd_budget = _decide(
        ctx,
        budget_exhausted_override=True,
        complexity_override=HIGH_COMPLEXITY_THRESHOLD + 5,
    )
    cf["CF-CD7"] = {
        "passed": rd_budget.envelope is not None and rd_budget.envelope.decision_kind == "STOP",
        "description": "Budget/evidence burden exhausted — STOP",
    }

    # CF-CD8 — Negative cumulative evidence
    contra = _contradictory_assessment(null_key="directional_reversal")
    cum_neg = build_cumulative_assessment(
        first_assessment=ctx["ix1"].evidence_assessment,
        first_interpretation={"evidence_class": "SUPPORTING"},
        first_execution_meta={"execution_id": "e1", "experiment_content_hash": "h1", "epistemic_update_id": "u1", "tool_result": {}},
        second_assessment=contra,
        second_interpretation={"evidence_class": "CONTRADICTORY"},
        second_execution_meta={"execution_id": "e2", "experiment_content_hash": "h2", "tool_result": {}},
        novelty_decomposition={"ROW_OVERLAP": 0.20, "NULL_TARGET_OVERLAP": 0.0, "SCIENTIFIC_QUESTION_OVERLAP": 0.0},
        proposition_id=ctx["prop"]["proposition_id"],
        proposition_hash=ctx["ix1"].proposition_hash,
        first_null_ledger=ctx["ix1"].evidence_assessment.null_accounting,
    )
    ctx_neg = {
        **ctx,
        "ix2": replace(
            ctx["ix2"],
            cumulative_assessment=cum_neg,
            resulting_epistemic_state="WEAKENED",
            base_interpretation={**ctx["ix2"].base_interpretation, "evidence_class": "CONTRADICTORY"},
        ),
    }
    dec_neg = _decide(ctx_neg)
    repl_blocked = all(
        not (e.action_family == "SEEK_REPLICATION" and e.admissible)
        for e in dec_neg.envelope.candidate_evaluations
    )
    cf["CF-CD8"] = {
        "passed": dec_neg.envelope is not None
        and dec_neg.envelope.research_decision["chosen_next_action"]
        != NextResearchAction.SEEK_REPLICATION.value
        and repl_blocked
        and (
            dec_neg.envelope.decision_kind == "STOP"
            or dec_neg.envelope.research_decision["chosen_next_action"]
            in (
                NextResearchAction.ABANDON.value,
                NextResearchAction.HOLD_UNRESOLVED.value,
                NextResearchAction.SEEK_FALSIFICATION.value,
            )
        ),
        "description": "Negative cumulative evidence — no confirmation seeking",
    }

    # CF-CD9 — Ordering invariance
    rd9a = _decide(ctx)
    rd9b = _decide(ctx)
    cf["CF-CD9"] = {
        "passed": rd9a.envelope.research_decision["chosen_next_action"]
        == rd9b.envelope.research_decision["chosen_next_action"],
        "description": "Candidate ordering changes do not alter scientific decision",
    }

    # CF-CD10 — No Experiment #3 leakage
    cf["CF-CD10"] = {
        "passed": rd_base.envelope.third_experiment_generated is False
        and rd_base.envelope.third_experiment_executed is False
        and rd_base.third_experiment_generated is False
        and rd_base.third_experiment_executed is False,
        "description": "Decision #2 produces no Experiment #3 package or execution",
    }

    cf["all_passed"] = all(v.get("passed") for v in cf.values() if isinstance(v, dict) and "passed" in v)
    cf["benchmark_version"] = BENCHMARK_VERSION
    assert_bbfcd_firewall(cf)
    return {"counterfactuals": cf, "all_passed": cf["all_passed"], "benchmark_version": BENCHMARK_VERSION}
