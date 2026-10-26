"""
Phase 3J.6 — Second-experiment candidate generation (decision-faithful, history-aware).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.cohort_overlap_estimator import PanelMetadataIndex
from modules.edge_research.opr_bridge.first_experiment_birth_evidence import (
    build_birth_evidence_fingerprint,
    measure_birth_overlap,
)
from modules.edge_research.opr_bridge.first_experiment_candidates import (
    FirstExperimentContext,
    _action_ctx_adapter,
    _contrast_relation,
    _detect_rescue_risk_local,
    _feature_field,
    _make_core,
    _outcome_field,
    _population_all,
)
from modules.edge_research.opr_bridge.first_experiment_execution_overlap import (
    FirstExperimentCohortFingerprint,
    measure_first_experiment_overlap,
)
from modules.edge_research.opr_bridge.first_experiment_execution_records import FirstExperimentExecutionEnvelope
from modules.edge_research.opr_bridge.first_experiment_records import InitialExperimentPackage
from modules.edge_research.opr_bridge.falsification_candidate_generator import (
    _check_anti_rescue,
    _holdout_dates_from_panel,
    _population_holdout_spec,
)
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.scientific_action_executability import bind_experiment_spec
from modules.edge_research.opr_bridge.scientific_action_records import RescueRiskClass
from modules.edge_research.opr_bridge.second_experiment_objective import SecondExperimentObjectiveRecord
from modules.edge_research.opr_bridge.second_experiment_records import (
    SecondExperimentCandidateRecord,
    build_candidate_record,
)
from modules.edge_research.research_grammar import GRAMMAR_VERSION
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash

NULL_COHORT_STRATEGIES: Dict[str, List[Dict[str, Any]]] = {
    "directional_reversal": [
        {
            "cohort_strategy": "full_panel_contrast",
            "target_uncertainty": "directional_effect_full_universe",
            "population": "all",
            "falsification_capable": True,
            "strategy_key": "full_panel_directional_falsify",
        },
    ],
    "episode_artifact": [
        {
            "cohort_strategy": "counterexample_period_search",
            "target_uncertainty": "episode_robustness",
            "population": "holdout",
            "falsification_capable": True,
            "strategy_key": "counterexample_holdout",
        },
        {
            "cohort_strategy": "episode_holdout_excluding_motivating",
            "target_uncertainty": "episode_robustness",
            "population": "holdout",
            "falsification_capable": True,
            "strategy_key": "episode_holdout",
        },
    ],
    "population_concentration": [
        {
            "cohort_strategy": "full_panel_contrast",
            "target_uncertainty": "population_generalization",
            "population": "all",
            "falsification_capable": True,
            "strategy_key": "full_panel_generalization",
        },
    ],
    "context_instability": [
        {
            "cohort_strategy": "regime_partition_contrast",
            "target_uncertainty": "context_stability",
            "population": "all",
            "falsification_capable": True,
            "strategy_key": "regime_contrast",
        },
    ],
}

WRONG_NULL_COHORT = {
    "directional_reversal": ("counterexample_period_search", "episode_holdout_excluding_motivating"),
    "episode_artifact": ("full_panel_contrast",),
}


def _population_for_strategy(
    ctx: FirstExperimentContext,
    spec: Dict[str, Any],
    panel_df: Optional[pd.DataFrame],
) -> Optional[Dict[str, Any]]:
    if spec["population"] == "all":
        return _population_all()
    if spec["population"] == "holdout":
        if panel_df is None:
            return None
        holdout = _holdout_dates_from_panel(
            panel_df,
            cutoff=ctx.executability.data_cutoff,
            motivating_dates=ctx.motivating_dates,
        )
        if not holdout:
            return None
        return _population_holdout_spec(holdout)
    return _population_all()


def _falsification_capability(
    *,
    falsification_capable: bool,
    exec_status: str,
    overlap_first: float,
    content_differs: bool,
) -> str:
    if not falsification_capable:
        return "NOT_FALSIFICATION_CAPABLE"
    if exec_status != "EXECUTABLE":
        return "NOT_EXECUTABLE"
    if overlap_first >= 0.95 and not content_differs:
        return "CONFIRMATION_ONLY"
    return "FALSIFICATION_CAPABLE"


def generate_second_experiment_candidates(
    prop: Dict[str, Any],
    objective: SecondExperimentObjectiveRecord,
    *,
    first_package: InitialExperimentPackage,
    first_execution: FirstExperimentExecutionEnvelope,
    first_fp: FirstExperimentCohortFingerprint,
    panel: PanelMetadataIndex,
    executability: ExecutabilityContext,
    panel_df: Optional[pd.DataFrame] = None,
    include_wrong_null_audit: bool = False,
) -> List[SecondExperimentCandidateRecord]:
    """
    Generate candidates faithful to frozen decision target null.
    Does NOT rerun decide_next_action.
    """
    ctx = FirstExperimentContext(
        proposition_record=prop,
        executability=executability,
        panel=panel,
        birth_fingerprint=build_birth_evidence_fingerprint(prop, panel),
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

    first_cohort = first_fp.cohort_strategy
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
            "outcome_spec": {"field": _outcome_field(ctx), "kind": "compare", "operator": ">", "value": 0.0, "grammar_version": GRAMMAR_VERSION},
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
        first_overlap, first_indep = measure_first_experiment_overlap(
            candidate_population_spec=pop,
            panel=panel,
            first_fp=first_fp,
        )

        content_hash = ""
        content_differs = True
        if bound_spec:
            content_hash = compute_experiment_content_hash(ExperimentSpec.from_dict(bound_spec))
            content_differs = content_hash != first_fp.experiment_content_hash

        if first_overlap >= 0.90 and cohort == first_cohort:
            rejection.append("replicates_first_experiment_cohort")
            decision_fidelity = decision_fidelity and False
        if content_hash and content_hash == first_fp.experiment_content_hash:
            rejection.append("identical_experiment_content_hash_to_first")
        if cohort == first_cohort and pop == first_fp.population_spec:
            rejection.append("syntactic_replication_of_first_experiment")
        if birth_overlap >= 0.85 and cohort == "full_panel_contrast" and objective.target_null_key == "directional_reversal":
            rejection.append("high_birth_overlap_confirmatory_risk")

        fals_cap = _falsification_capability(
            falsification_capable=spec["falsification_capable"],
            exec_status=exec_status,
            overlap_first=first_overlap,
            content_differs=content_differs,
        )
        if objective.selected_action == "SEEK_FALSIFICATION" and fals_cap == "CONFIRMATION_ONLY":
            rejection.append("confirmation_only_under_seek_falsification")
        if objective.selected_action == "SEEK_FALSIFICATION" and fals_cap == "NOT_FALSIFICATION_CAPABLE":
            rejection.append("non_falsification_under_seek_falsification")

        redundancy = "LOW"
        if first_overlap >= 0.85:
            redundancy = "HIGH_FIRST_EXPERIMENT_OVERLAP"
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
                scientific_identity=core.to_canonical_dict(),
                target_null_key=objective.target_null_key if not audit_wrong else (audit_wrong or objective.target_null_key),
                target_uncertainty=spec["target_uncertainty"],
                scientific_objective=sci_obj,
                falsification_rationale=fals_rationale,
                informative_observation="Directional quintile spread or survival on independent cohort",
                cannot_establish="Cannot establish unrelated nulls outside design scope",
                primary_classification=primary,
                falsification_capable=spec["falsification_capable"],
                birth_evidence_overlap_fraction=birth_overlap,
                first_experiment_overlap_fraction=first_overlap,
                birth_independence_profile=birth_indep,
                first_experiment_independence_profile=first_indep,
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


def _null_rationale(null_key: str, cohort: str) -> Tuple[str, str]:
    if null_key == "directional_reversal":
        return (
            "Does high-rs_spread quintile outperform low on full panel?",
            "Direction reversal on full cross-section would falsify directional commitment",
        )
    if null_key == "episode_artifact":
        return (
            "Does effect survive excluding motivating episode dates?",
            "Absence on holdout cohort supports episode artifact null",
        )
    return (f"Test null {null_key}", f"Discriminate {null_key} via {cohort}")


def deduplicate_second_experiment_candidates(
    candidates: List[SecondExperimentCandidateRecord],
) -> List[SecondExperimentCandidateRecord]:
    best: Dict[str, SecondExperimentCandidateRecord] = {}
    for c in candidates:
        key = c.scientific_action_core_hash
        if key not in best or (c.primary_classification == "ADMISSIBLE" and best[key].primary_classification != "ADMISSIBLE"):
            best[key] = c
    return list(best.values())
