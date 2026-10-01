"""
Phase 3I.13 — Abstract lifecycle integration fixtures.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _abstract_prop(prop_id: str = "prop-abstract-int-A") -> Dict[str, Any]:
    return {
        "proposition_id": prop_id,
        "record_version": "proposition_record_v1",
        "generator_version": "opr_generator_v1_test",
        "epistemic_status": "HYPOTHESIS",
        "observation_horizon": 3,
        "explanatory_relation": {"contrast_direction": "positive", "feature_or_contrast": "flux_index"},
        "outcome": {"field": "delta_yield"},
        "execution_requirements": {"partition_column": "flux_index", "min_sample": 50},
        "experiment_spec_draft": {
            "tool_name": "partition_group_compare",
            "inputs": {"partition_column": "flux_index", "n_groups": 5},
        },
        "observation_provenance": {
            "evidence_anchor": {"data_cutoff_date": "2019-06-01"},
            "empirical_artifacts": [],
            "structural_context": {},
            "surprise_basis": "abstract",
            "evidence_hash": "abstract",
        },
        "motivating_observation": "abstract",
        "surprise_or_uncertainty": "abstract",
        "scientific_question": "Does flux_index predict delta_yield?",
        "canonical_proposition_core": "flux_index contrast",
        "population_context": "abstract universe",
        "falsifiable_expectation": "positive spread",
        "null_competing_explanation": "noise",
        "disconfirming_observation_spec": {
            "description": "reverse",
            "operational_test": "spread",
            "threshold": "0",
            "alternative_interpretation": "noise",
        },
        "evidence_required": [],
        "confidence": "LOW",
        "birth_certificate": {"answers": [{"question_id": "q1", "passed": True, "answer": "yes"}]},
    }


def _base_spec(pop_kind: str = "all", *, filter_values: List[str] | None = None) -> Dict[str, Any]:
    pop: Dict[str, Any] = {"kind": pop_kind, "grammar_version": "research_grammar_v1"}
    if pop_kind == "filter":
        pop["field"] = "trade_date"
        pop["operator"] = "in"
        pop["values"] = filter_values or ["2019-01-01", "2019-01-02"]
    return {
        "tool_name": "tier_compare",
        "tool_version": "v1",
        "inputs": {"partition_column": "flux_index", "n_groups": 5},
        "research_scope": {
            "population_spec": pop,
            "outcome_spec": {"kind": "compare", "field": "delta_yield", "operator": ">", "value": 0},
            "observation_horizon": 3,
        },
        "data_cutoff_date": "2019-06-01",
    }


def _epu(
    eid: str,
    cls: str,
    *,
    prior: str = "HYPOTHESIS",
    sample: int = 500,
    spread: float = 2.0,
    ref: str = "exp-001",
) -> Dict[str, Any]:
    return {
        "update_id": eid,
        "proposition_id": "prop-abstract-int-A",
        "prior_epistemic_state": prior,
        "resulting_epistemic_state": "SUPPORTED" if cls == "SUPPORTING" else prior,
        "evidence_class": cls,
        "experiment_ref": ref,
        "tool_result_hash": f"hash-{eid}",
        "metrics_used": {
            "sample_size": sample,
            "quintile_mean_spread": spread,
            "contrast_direction": "positive",
        },
        "condition_matched": "test",
        "unresolved_uncertainty": "abstract",
        "record_hash": f"epu-hash-{eid}",
    }


def _event(epu: Dict[str, Any], spec: Dict[str, Any], **meta) -> Dict[str, Any]:
    return {
        "epistemic_update": epu,
        "experiment_spec": spec,
        "experiment_ref": epu["experiment_ref"],
        "tool_result_hash": epu["tool_result_hash"],
        **meta,
    }


ABSTRACT_INTEGRATION_FIXTURES: List[Dict[str, Any]] = [
    {
        "fixture_id": "INT-A",
        "name": "single_support",
        "proposition": _abstract_prop(),
        "events": [_event(_epu("epu-a1", "SUPPORTING"), _base_spec())],
        "expected_state": "SUPPORTED",
    },
    {
        "fixture_id": "INT-B",
        "name": "correlated_support_pair",
        "proposition": _abstract_prop(),
        "events": [
            _event(_epu("epu-b1", "SUPPORTING", sample=500), _base_spec()),
            _event(
                _epu("epu-b2", "SUPPORTING", prior="SUPPORTED", sample=490, ref="exp-002"),
                _base_spec(),  # same spec → high correlation / exact replication
            ),
        ],
        "expect_relationship_in": ("PARTIAL_REPLICATION", "EXACT_REPLICATION", "RELATED_EVIDENCE"),
    },
    {
        "fixture_id": "INT-C",
        "name": "independent_support_pair",
        "proposition": _abstract_prop(),
        "events": [
            _event(_epu("epu-c1", "SUPPORTING", sample=500), _base_spec()),
            _event(
                _epu("epu-c2", "SUPPORTING", prior="SUPPORTED", sample=200, ref="exp-002"),
                _base_spec("filter", filter_values=["2019-03-01", "2019-03-02", "2019-03-03"]),
            ),
        ],
    },
    {
        "fixture_id": "INT-D",
        "name": "support_independent_contradiction",
        "proposition": _abstract_prop(),
        "events": [
            _event(_epu("epu-d1", "SUPPORTING", sample=500, spread=2.0), _base_spec()),
            _event(
                _epu("epu-d2", "DISCONFIRMING", prior="SUPPORTED", sample=180, spread=1.5, ref="exp-002"),
                _base_spec("filter", filter_values=["2019-04-01", "2019-04-02"]),
            ),
        ],
        "expected_state_in": ("CONFLICTED", "FALSIFIED", "WEAKENED"),
    },
    {
        "fixture_id": "INT-E",
        "name": "invalid_second_evidence",
        "proposition": _abstract_prop(),
        "events": [
            _event(_epu("epu-e1", "SUPPORTING"), _base_spec()),
            _event(
                _epu("epu-e2", "INVALID", prior="SUPPORTED", ref="exp-002"),
                _base_spec(),
                interpretation={"validity_passed": False},
            ),
        ],
        "expected_state": "SUPPORTED",
    },
    {
        "fixture_id": "INT-F",
        "name": "non_informative_second",
        "proposition": _abstract_prop(),
        "events": [
            _event(_epu("epu-f1", "SUPPORTING"), _base_spec()),
            _event(_epu("epu-f2", "NON_INFORMATIVE", prior="SUPPORTED", ref="exp-002"), _base_spec()),
        ],
        "expected_state": "SUPPORTED",
    },
    {
        "fixture_id": "INT-G",
        "name": "saturated_body",
        "proposition": _abstract_prop(),
        "events": [],  # filled dynamically in test from BB BE-11 pattern
        "skip_direct": True,
    },
    {
        "fixture_id": "INT-H",
        "name": "falsified_later_support",
        "proposition": _abstract_prop(),
        "events": [
            _event(_epu("epu-h1", "DISCONFIRMING", prior="FALSIFIED", spread=2.0), _base_spec()),
            _event(_epu("epu-h2", "SUPPORTING", prior="FALSIFIED", ref="exp-002"), _base_spec("filter")),
        ],
        "expected_state": "FALSIFIED",
    },
]
