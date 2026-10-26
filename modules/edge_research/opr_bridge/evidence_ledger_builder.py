"""
Phase 3I.13 — Generic evidence ledger builder from authoritative lifecycle artifacts.

Generic lifecycle normalization (A) only — no proposition-specific branching.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash


def proposition_spec_from_record(proposition: Dict[str, Any]) -> Dict[str, Any]:
    """Derive synthesis proposition spec from structured PropositionRecord fields."""
    exec_req = proposition.get("execution_requirements") or {}
    draft = proposition.get("experiment_spec_draft") or {}
    tool = draft.get("tool_name") or exec_req.get("tool_name", "")

    if tool == "partition_group_compare" or exec_req.get("partition_column") or draft.get("inputs", {}).get("partition_column"):
        ptype = "partition_contrast"
    elif "context" in str(proposition.get("canonical_proposition_core", "")).lower():
        ptype = "context_modulation"
    else:
        ptype = "partition_contrast"

    return {
        "proposition_id": proposition["proposition_id"],
        "proposition_hash": proposition_content_hash(proposition),
        "proposition_type": ptype,
    }


def _feature_semantics(experiment_spec: Dict[str, Any], proposition: Dict[str, Any]) -> str:
    inputs = experiment_spec.get("inputs") or {}
    if inputs.get("partition_column") or (proposition.get("execution_requirements") or {}).get("partition_column"):
        return "continuous_partition"
    if inputs.get("context_field") or inputs.get("modulator_field"):
        return "context_modulation"
    return "structured_contrast"


def _outcome_semantics(experiment_spec: Dict[str, Any], proposition: Dict[str, Any]) -> str:
    scope = experiment_spec.get("research_scope") or {}
    outcome_spec = scope.get("outcome_spec") or {}
    field = outcome_spec.get("field") or (proposition.get("outcome") or {}).get("field")
    if field:
        return "forward_outcome"
    return "forward_outcome"


def _horizon(experiment_spec: Dict[str, Any], proposition: Dict[str, Any]) -> str:
    scope = experiment_spec.get("research_scope") or {}
    h = scope.get("observation_horizon")
    if h is not None:
        return f"H{h}" if isinstance(h, int) else str(h)
    oh = proposition.get("observation_horizon")
    if oh is not None:
        return f"H{oh}" if isinstance(oh, int) else str(oh)
    outcome = (proposition.get("outcome") or {}).get("field", "")
    if outcome.startswith("t") and outcome[1:].isdigit():
        return outcome.upper().replace("_RETURN", "")
    return "H1"


def _population_semantics(population_spec: Dict[str, Any]) -> str:
    kind = population_spec.get("kind", "unknown")
    if kind == "all":
        return "full_universe"
    if kind == "filter":
        field = population_spec.get("field", "")
        op = population_spec.get("operator", "")
        if field == "trade_date":
            if op == "in":
                return "filtered_date_cohort"
            if op == "not_in" or op == "!=":
                return "holdout_exclude_dates"
        return f"filtered_{field or 'cohort'}"
    if kind == "and" or kind == "or":
        return "composite_population"
    return f"population_{kind}"


def _cohort_episode_scope(population_spec: Dict[str, Any]) -> str:
    """Canonical scope identity from population_spec structure (not prose)."""
    canonical = json.dumps(population_spec, sort_keys=True, default=str)
    scope_hash = stable_hash({"population_spec": population_spec})[:16]
    kind = population_spec.get("kind", "unknown")
    if kind == "all":
        return "all_episodes"
    if kind == "filter" and population_spec.get("field") == "trade_date":
        values = population_spec.get("values") or []
        return f"filter_trade_date_{len(values)}dates_{scope_hash}"
    return f"{kind}_{scope_hash}"


def _uncertainty_axis(
    population_spec: Dict[str, Any],
    *,
    falsification_intent: bool,
    population_semantics: str,
) -> str:
    if falsification_intent and population_semantics.startswith("holdout"):
        return "episode_robustness"
    if falsification_intent:
        return "counterexample_exposure"
    if population_spec.get("kind") == "all":
        return "directional_effect_full_universe"
    if population_spec.get("kind") == "filter":
        field = population_spec.get("field", "")
        if field == "trade_date":
            return "episode_robustness"
        return "population_robustness"
    return "directional_effect_full_universe"


def _effect_direction(epu: Dict[str, Any], proposition: Dict[str, Any]) -> str:
    direction = (proposition.get("explanatory_relation") or {}).get("contrast_direction", "positive")
    ec = epu.get("evidence_class", "")
    if ec == "DISCONFIRMING":
        return "negative" if direction == "positive" else "positive"
    if ec in ("CONTRADICTORY",):
        return "contradictory"
    if ec in ("NON_INFORMATIVE", "INVALID"):
        return "unknown"
    return str(direction)


def _effect_magnitude(epu: Dict[str, Any]) -> str:
    metrics = epu.get("metrics_used") or {}
    if metrics.get("falsify_strength") == "STRONG":
        return "strong"
    spread = metrics.get("quintile_mean_spread")
    if spread is None:
        spread = metrics.get("outcome_spread")
    if spread is None:
        return "unknown"
    try:
        s = float(spread)
    except (TypeError, ValueError):
        return "unknown"
    if epu.get("evidence_class") == "DISCONFIRMING" and s >= 0.5:
        return "strong"
    if s >= 0.5:
        return "strong"
    if s > 0:
        return "weak"
    return "none"


def _validity(epu: Dict[str, Any], interpretation: Optional[Dict[str, Any]]) -> str:
    if epu.get("evidence_class") == "INVALID":
        return "INVALID"
    if interpretation is not None and not interpretation.get("validity_passed", True):
        return "INVALID"
    return "VALID"


def _falsification_intent(lineage_metadata: Optional[Dict[str, Any]]) -> bool:
    if not lineage_metadata:
        return False
    if lineage_metadata.get("falsification_refs"):
        return True
    if lineage_metadata.get("evidence_independence_class") == "INDEPENDENT_FALSIFICATION":
        return True
    if lineage_metadata.get("falsification_intent"):
        return True
    return False


def _estimate_overlap_from_samples(current_n: int, prior_ns: List[int], same_measurement: bool) -> float:
    if not prior_ns or current_n <= 0:
        return 0.0
    if not same_measurement:
        return 0.3
    max_prior = max(prior_ns)
    denom = max(current_n, max_prior)
    if denom <= 0:
        return 0.0
    return round(min(current_n, max_prior) / denom, 4)


def build_evidence_spec_from_lifecycle_event(
    *,
    proposition: Dict[str, Any],
    epistemic_update: Dict[str, Any],
    experiment_spec: Dict[str, Any],
    experiment_ref: str,
    tool_result_hash: str,
    interpretation: Optional[Dict[str, Any]] = None,
    lineage_metadata: Optional[Dict[str, Any]] = None,
    prior_sample_sizes: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Build one normalized evidence spec from authoritative lifecycle artifacts."""
    prop_hash = proposition_content_hash(proposition)
    spec_obj = ExperimentSpec.from_dict({**experiment_spec, "tool_version": experiment_spec.get("tool_version", "v1")})
    exp_hash = compute_experiment_content_hash(spec_obj)

    scope = experiment_spec.get("research_scope") or {}
    pop_spec = scope.get("population_spec") or {"kind": "all"}
    pop_sem = _population_semantics(pop_spec)
    falsify = _falsification_intent(lineage_metadata)
    feature_sem = _feature_semantics(experiment_spec, proposition)
    outcome_sem = _outcome_semantics(experiment_spec, proposition)

    metrics = epistemic_update.get("metrics_used") or {}
    sample_size = int(metrics.get("sample_size", 0))

    prior_ns = prior_sample_sizes or []
    same_measurement = True  # same proposition experiment family
    overlap = _estimate_overlap_from_samples(sample_size, prior_ns, same_measurement)

    provenance = {
        "epistemic_update_id": epistemic_update.get("update_id", ""),
        "tool_result_hash": tool_result_hash,
        "experiment_content_hash": exp_hash,
    }
    if lineage_metadata:
        for key in ("falsification_refs", "candidate_id", "package_hash"):
            if key in lineage_metadata:
                provenance[key] = str(lineage_metadata[key])

    return {
        "evidence_id": epistemic_update["update_id"],
        "experiment_id": experiment_ref,
        "experiment_content_hash": exp_hash,
        "epistemic_update_ref": epistemic_update["update_id"],
        "evidence_class": epistemic_update["evidence_class"],
        "validity": _validity(epistemic_update, interpretation),
        "feature_semantics": feature_sem,
        "population_semantics": pop_sem,
        "outcome_semantics": outcome_sem,
        "horizon": _horizon(experiment_spec, proposition),
        "cohort_episode_scope": _cohort_episode_scope(pop_spec),
        "data_cutoff": experiment_spec.get("data_cutoff_date", ""),
        "sample_size": sample_size,
        "effect_direction": _effect_direction(epistemic_update, proposition),
        "effect_magnitude": _effect_magnitude(epistemic_update),
        "measurement_tool": experiment_spec.get("tool_name", "unknown"),
        "uncertainty_axis_tested": _uncertainty_axis(
            pop_spec, falsification_intent=falsify, population_semantics=pop_sem
        ),
        "falsification_intent": falsify,
        "cohort_overlap_ratio": overlap,
        "provenance_refs": provenance,
        "proposition_id": proposition["proposition_id"],
        "proposition_hash": prop_hash,
        "experiment_spec": {
            "research_scope": scope,
            "data_cutoff_date": experiment_spec.get("data_cutoff_date", ""),
            "tool_name": experiment_spec.get("tool_name", "unknown"),
        },
    }


def build_ledger_specs_from_events(
    proposition: Dict[str, Any],
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build ordered evidence specs from lifecycle evidence events.

    Each event dict must contain:
      epistemic_update, experiment_spec, experiment_ref, tool_result_hash
    Optional: interpretation, lineage_metadata
    """
    specs: List[Dict[str, Any]] = []
    prior_samples: List[int] = []
    for event in events:
        spec = build_evidence_spec_from_lifecycle_event(
            proposition=proposition,
            epistemic_update=event["epistemic_update"],
            experiment_spec=event["experiment_spec"],
            experiment_ref=event["experiment_ref"],
            tool_result_hash=event["tool_result_hash"],
            interpretation=event.get("interpretation"),
            lineage_metadata=event.get("lineage_metadata"),
            prior_sample_sizes=prior_samples,
        )
        specs.append(spec)
        n = spec.get("sample_size", 0)
        if n:
            prior_samples.append(n)
    return specs
