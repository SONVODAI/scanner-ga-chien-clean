"""
Phase 3J.13 — History-aware follow-on experiment candidate generation (Experiment #N).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.cohort_overlap_estimator import PanelMetadataIndex
from modules.edge_research.opr_bridge.first_experiment_birth_evidence import measure_birth_overlap
from modules.edge_research.opr_bridge.first_experiment_candidates import (
    FirstExperimentContext,
    _action_ctx_adapter,
    _detect_rescue_risk_local,
    _feature_field,
    _make_core,
    _outcome_field,
    _population_all,
)
from modules.edge_research.opr_bridge.first_experiment_records import InitialExperimentPackage
from modules.edge_research.opr_bridge.falsification_candidate_generator import (
    _check_anti_rescue,
    _holdout_dates_from_panel,
    _population_holdout_spec,
)
from modules.edge_research.opr_bridge.follow_on_experiment_history_context import (
    FollowOnHistoryContext,
    measure_max_prior_overlap,
)
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.scientific_action_executability import bind_experiment_spec
from modules.edge_research.opr_bridge.scientific_action_records import RescueRiskClass
from modules.edge_research.opr_bridge.second_experiment_candidates import (
    NULL_COHORT_STRATEGIES,
    WRONG_NULL_COHORT,
    _falsification_capability,
    _null_rationale,
    _population_for_strategy,
)
from modules.edge_research.opr_bridge.second_experiment_novelty_audit import decompose_novelty
from modules.edge_research.opr_bridge.second_experiment_objective import SecondExperimentObjectiveRecord
from modules.edge_research.opr_bridge.second_experiment_records import (
    SecondExperimentCandidateRecord,
    build_candidate_record,
)
from modules.edge_research.research_grammar import GRAMMAR_VERSION
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

GENERATOR_VERSION = "follow_on_experiment_generator_v1_3j13"

SEARCH_BURDEN_SILENCE_THRESHOLD = 18.0


def _null_cycling_detected(
    *,
    null_key: str,
    cohort: str,
    uncertainty: str,
    history_ctx: FollowOnHistoryContext,
) -> bool:
    for nk, c, tu in history_ctx.tested_null_cohort_pairs:
        if nk == null_key and c == cohort and tu == uncertainty:
            return True
    if history_ctx.tested_null_keys.count(null_key) >= 2:
        return True
    return False


def _worst_novelty_vs_history(
    *,
    bound_spec: Optional[Dict[str, Any]],
    core_identity: Dict[str, str],
    target_null: str,
    target_uncertainty: str,
    row_overlap: float,
    history_ctx: FollowOnHistoryContext,
) -> Tuple[float, float, str]:
    """Return (max_null_target_overlap, max_scientific_question_overlap, coarse_redundancy)."""
    max_null = 0.0
    max_q = 0.0
    coarse = "LOW"
    if not bound_spec:
        return max_null, max_q, coarse

    for pf in history_ctx.prior_fingerprints:
        prior_spec = {
            "tool_name": pf.tool_name,
            "inputs": {},
            "research_scope": {
                "population_spec": dict(pf.population_spec),
                "outcome_spec": {"field": _outcome_field_from_prop({}), "kind": "compare"},
                "observation_horizon": 0,
            },
        }
        dec = decompose_novelty(
            first_spec=prior_spec,
            first_identity=pf.scientific_identity,
            first_target_null=pf.target_null_key,
            first_target_uncertainty=pf.target_uncertainty,
            second_spec=bound_spec,
            second_identity=core_identity,
            second_target_null=target_null,
            second_target_uncertainty=target_uncertainty,
            row_overlap_fraction=row_overlap,
        )
        max_null = max(max_null, dec.null_target_overlap)
        max_q = max(max_q, dec.scientific_question_overlap)
        if dec.coarse_redundancy_interpretation == "SCIENTIFIC_REDUNDANCY":
            coarse = "SCIENTIFIC_REDUNDANCY"
        elif dec.coarse_redundancy_interpretation == "HIGH_FIRST_EXPERIMENT_OVERLAP" and coarse == "LOW":
            coarse = dec.coarse_redundancy_interpretation

    return max_null, max_q, coarse


def _outcome_field_from_prop(prop: Dict[str, Any]) -> str:
    return "t5_return"


def generate_follow_on_experiment_candidates(
    prop: Dict[str, Any],
    objective: SecondExperimentObjectiveRecord,
    *,
    history_ctx: FollowOnHistoryContext,
    panel: PanelMetadataIndex,
    executability: ExecutabilityContext,
    panel_df: Optional[pd.DataFrame] = None,
    include_wrong_null_audit: bool = False,
    first_package: Optional[InitialExperimentPackage] = None,
) -> List[SecondExperimentCandidateRecord]:
    """
    Generate Experiment #N candidates from frozen decision + complete research history.
    Does NOT use ordinal-2-specific overlap-only-vs-first assumptions.
    """
    ctx = FirstExperimentContext(
        proposition_record=prop,
        executability=executability,
        panel=panel,
        birth_fingerprint=history_ctx.birth_evidence,
    )
    prop_hash = proposition_content_hash(prop)
    strategies = list(NULL_COHORT_STRATEGIES.get(objective.target_null_key, []))

    if include_wrong_null_audit:
        for wrong_null, wrong_strats in WRONG_NULL_COHORT.items():
            if wrong_null != objective.target_null_key:
                for ws in wrong_strats:
                    if ws == "full_panel_contrast":
                        strategies.append(
                            {
                                "cohort_strategy": "full_panel_contrast",
                                "target_uncertainty": "directional_effect_full_universe",
                                "population": "all",
                                "falsification_capable": True,
                                "strategy_key": f"audit_wrong_null_{wrong_null}",
                                "_audit_wrong_null": wrong_null,
                            }
                        )

    candidates: List[SecondExperimentCandidateRecord] = []

    for spec in strategies:
        cohort = spec["cohort_strategy"]
        pop = _population_for_strategy(ctx, spec, panel_df)
        if pop is None:
            continue

        core = _make_core(
            ctx,
            target_uncertainty=spec["target_uncertainty"],
            cohort_strategy=cohort,
            information_gain="falsify" if spec["falsification_capable"] else "inform",
        )

        audit_wrong = spec.get("_audit_wrong_null")
        rejection: List[str] = []
        decision_fidelity = True

        if audit_wrong:
            decision_fidelity = False
            rejection.append(f"decision_substitution_wrong_null_{audit_wrong}")
        elif cohort in WRONG_NULL_COHORT.get(objective.target_null_key, ()):
            decision_fidelity = False
            rejection.append("targets_wrong_null_for_frozen_decision")

        scope = {
            "population_spec": pop,
            "outcome_spec": {
                "field": _outcome_field(ctx),
                "kind": "compare",
                "operator": ">",
                "value": 0.0,
                "grammar_version": GRAMMAR_VERSION,
            },
            "observation_horizon": int(prop.get("observation_horizon", 0)),
        }
        rescue = _detect_rescue_risk_local(prop, pop, scope)
        if rescue == RescueRiskClass.PASS.value:
            anti_ok, anti_detail = _check_anti_rescue(prop, scope)
            if not anti_ok:
                rescue = anti_detail

        actx = _action_ctx_adapter(ctx)
        bound_spec, envelope, exec_class, exec_detail = bind_experiment_spec(
            actx,
            core=core,
            rescue_risk=rescue if rescue != RescueRiskClass.PASS.value else RescueRiskClass.PASS.value,
            population_spec_override=pop,
        )
        exec_map = {
            "SCIENTIFICALLY_VALID_EXECUTABLE": "EXECUTABLE",
            "SCIENTIFICALLY_VALID_NOT_EXECUTABLE": "NOT_EXECUTABLE",
            "RESCUE_RISK": "RESCUE_REJECTED",
            "INVALID": "INVALID",
        }
        exec_status = exec_map.get(exec_class, exec_class)

        birth_overlap, birth_indep = measure_birth_overlap(
            candidate_population_spec=pop,
            candidate_contrast_relation=core.contrast_relation,
            candidate_feature=_feature_field(ctx),
            panel=panel,
            birth=ctx.birth_fingerprint,
        )
        prior_overlap, prior_indep, worst_ord = measure_max_prior_overlap(
            candidate_population_spec=pop,
            panel=panel,
            prior_fingerprints=history_ctx.prior_fingerprints,
        )

        content_hash = ""
        content_differs = True
        if bound_spec:
            content_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(bound_spec))
            content_differs = content_hash not in history_ctx.content_hashes

        core_identity = core.to_canonical_dict()
        target_null = objective.target_null_key if not audit_wrong else (audit_wrong or objective.target_null_key)

        if content_hash and content_hash in history_ctx.content_hashes:
            rejection.append("identical_experiment_content_hash_to_prior")
        if core.core_hash in history_ctx.core_hashes:
            rejection.append("representation_alias_core_hash_match")
        if core.core_hash in history_ctx.rejected_core_hashes:
            rejection.append("previously_rejected_core_hash")

        if _null_cycling_detected(
            null_key=target_null,
            cohort=cohort,
            uncertainty=spec["target_uncertainty"],
            history_ctx=history_ctx,
        ):
            rejection.append("null_cycling_detected")

        for pf in history_ctx.prior_fingerprints:
            if prior_overlap >= 0.90 and cohort == pf.cohort_strategy and pop == pf.population_spec:
                rejection.append(f"replicates_prior_experiment_cohort:ordinal_{pf.ordinal}")
                decision_fidelity = decision_fidelity and False
            if (
                prior_overlap >= 0.85
                and target_null == pf.target_null_key
                and cohort == pf.cohort_strategy
            ):
                rejection.append(f"semantic_redundancy_vs_prior:ordinal_{pf.ordinal}")

        if birth_overlap >= 0.85 and cohort == "full_panel_contrast" and objective.target_null_key == "directional_reversal":
            rejection.append("high_birth_overlap_confirmatory_risk")

        fals_cap = _falsification_capability(
            falsification_capable=spec["falsification_capable"],
            exec_status=exec_status,
            overlap_first=prior_overlap,
            content_differs=content_differs,
        )

        if objective.selected_action == "SEEK_FALSIFICATION" and fals_cap == "CONFIRMATION_ONLY":
            rejection.append("confirmation_only_under_seek_falsification")
        if objective.selected_action == "SEEK_FALSIFICATION" and fals_cap == "NOT_FALSIFICATION_CAPABLE":
            rejection.append("non_falsification_under_seek_falsification")

        if objective.selected_action == "SEEK_REPLICATION":
            indep_level = prior_indep.get("sample_independence", "UNKNOWN")
            if indep_level in ("LOW", "NONE") or prior_overlap >= 0.85:
                rejection.append("fake_replication_insufficient_independence")
            if not content_differs and prior_overlap >= 0.50:
                rejection.append("fake_replication_representation_alias")

        max_null_ov, max_q_ov, coarse_red = _worst_novelty_vs_history(
            bound_spec=bound_spec,
            core_identity=core_identity,
            target_null=target_null,
            target_uncertainty=spec["target_uncertainty"],
            row_overlap=prior_overlap,
            history_ctx=history_ctx,
        )
        if max_null_ov >= 1.0 and max_q_ov >= 1.0 and prior_overlap >= 0.85:
            rejection.append("scientific_question_redundant_vs_history")
        if coarse_red == "SCIENTIFIC_REDUNDANCY":
            rejection.append("full_history_scientific_redundancy")

        if history_ctx.search_burden_score >= SEARCH_BURDEN_SILENCE_THRESHOLD and prior_overlap >= 0.75:
            rejection.append("search_burden_low_incremental_information")

        redundancy = "LOW"
        if coarse_red == "SCIENTIFIC_REDUNDANCY" or (max_null_ov >= 1.0 and max_q_ov >= 1.0):
            redundancy = "HIGH_SCIENTIFIC_REDUNDANCY"
        elif prior_overlap >= 0.85:
            redundancy = "HIGH_PRIOR_EXPERIMENT_OVERLAP"
        elif birth_overlap >= 0.85:
            redundancy = "HIGH_BIRTH_OVERLAP"

        primary = "ADMISSIBLE" if not rejection and exec_status == "EXECUTABLE" and decision_fidelity else "INADMISSIBLE"
        if exec_status != "EXECUTABLE" and not rejection:
            rejection.append(f"not_executable:{exec_detail[:80]}")

        sci_obj, fals_rationale = _null_rationale(objective.target_null_key, cohort)
        candidates.append(
            build_candidate_record(
                proposition_id=prop["proposition_id"],
                proposition_hash=prop_hash,
                objective_id=objective.objective_id,
                scientific_action_core_hash=core.core_hash,
                scientific_identity=core_identity,
                target_null_key=target_null,
                target_uncertainty=spec["target_uncertainty"],
                scientific_objective=sci_obj,
                falsification_rationale=fals_rationale,
                informative_observation=(
                    f"Discriminates {target_null} via {cohort} "
                    f"(max_prior_overlap={prior_overlap:.2f} vs ord{worst_ord or '?'})"
                ),
                cannot_establish="Cannot establish unrelated nulls outside frozen decision scope",
                primary_classification=primary,
                falsification_capable=spec["falsification_capable"],
                birth_evidence_overlap_fraction=birth_overlap,
                first_experiment_overlap_fraction=prior_overlap,
                birth_independence_profile=birth_indep,
                first_experiment_independence_profile={
                    **prior_indep,
                    "worst_prior_ordinal": str(worst_ord),
                    "history_aware": "true",
                },
                redundancy_assessment=redundancy,
                falsification_capability=fals_cap,
                executability_status=exec_status,
                executability_detail=exec_detail,
                experiment_spec=bound_spec,
                representation_envelope=envelope,
                experiment_content_hash=content_hash,
                content_hash_differs_from_first=content_differs,
                decision_fidelity_ok=decision_fidelity and not rejection,
                rejection_reasons=tuple(rejection),
            )
        )

    return candidates


def deduplicate_follow_on_experiment_candidates(
    candidates: List[SecondExperimentCandidateRecord],
) -> List[SecondExperimentCandidateRecord]:
    best: Dict[str, SecondExperimentCandidateRecord] = {}
    for c in candidates:
        key = c.scientific_action_core_hash
        if key not in best or (
            c.primary_classification == "ADMISSIBLE" and best[key].primary_classification != "ADMISSIBLE"
        ):
            best[key] = c
    return list(best.values())
