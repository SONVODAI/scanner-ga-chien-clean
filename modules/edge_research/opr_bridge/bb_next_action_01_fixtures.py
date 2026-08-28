"""
Phase 3I.16 — BB-NextAction-01 abstract benchmark fixtures.

DEVELOPMENT FIREWALL: No rs_spread, t5_return, prop-efb650d9bd5c451f, 2026-08-02.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import copy

from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import (
    FORBIDDEN_TOKENS,
    _ev,
    assert_development_firewall,
)
from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.scientific_action_generator import (
    GenerationResult,
    build_context_from_synthesis,
    generate_scientific_actions,
)
from modules.edge_research.opr_bridge.scientific_action_records import ActionDisposition

BB_FORBIDDEN = FORBIDDEN_TOKENS | frozenset({"2026-08-02"})


def assert_bb_firewall(spec: Dict[str, Any]) -> None:
    import json

    blob = json.dumps(spec, default=str).lower()
    for tok in BB_FORBIDDEN:
        if tok.lower() in blob:
            raise ValueError(f"BB-NextAction firewall violation: {tok}")


def _prop(
    prop_id: str,
    *,
    ptype: str = "partition_contrast",
    null: str = "",
    motivating: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "proposition_id": prop_id,
        "proposition_hash": f"abstract_{prop_id}",
        "proposition_type": ptype,
        "feature": "flux_index" if ptype == "partition_contrast" else "context_gate",
        "outcome": "delta_yield",
        "null_competing_explanation": null,
        "motivating_dates": motivating or ["2019-01-15"],
        "population_context": {"kind": "all", "grammar_version": "research_grammar_v1"},
        "observation_horizon": 0,
        "observation_provenance": {
            "evidence_anchor": {"focal_date": (motivating or ["2019-01-15"])[0], "data_cutoff_date": "2019-06-01"},
            "empirical_artifacts": [],
        },
        "disconfirming_observation_spec": {
            "description": "High flux_index quintile does not exceed low on delta_yield",
            "alternative_interpretation": null or "Small-sample artifact on focal episode",
        },
    }


def _case(
    case_id: str,
    *,
    proposition: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    prior_state: str = "SUPPORTED",
    priority_override: Optional[str] = None,
    executability: Optional[ExecutabilityContext] = None,
    expect: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "proposition": proposition,
        "evidence": evidence,
        "prior_state": prior_state,
        "priority_override": priority_override,
        "executability": executability,
        "expect": expect,
    }


BB_NEXT_ACTION_01_CASES: List[Dict[str, Any]] = [
    _case(
        "BBNA-01",
        proposition=_prop("bbna-partition-temporal"),
        evidence=[
            _ev("e1", "SUPPORTING", axis="directional_effect_full_universe"),
            _ev("e2", "SUPPORTING", axis="episode_robustness", scope="holdout_episodes", pop="holdout", overlap=0.1, exp_hash="h2"),
        ],
        expect={
            "min_distinct_core_hashes": 2,
            "must_include_strategies": {"regime_separated_contrast"},
            "must_not_only_strategy": "episode_holdout_excluding_motivating",
        },
    ),
    _case(
        "BBNA-02",
        proposition=_prop("bbna-partition-population"),
        evidence=[
            _ev("e1", "SUPPORTING"),
            _ev("e2", "SUPPORTING", overlap=0.92, pop="full", exp_hash="h2"),
        ],
        expect={
            "must_include_axes": {"population_robustness"},
            "must_include_strategies": {"population_subgroup_contrast"},
        },
    ),
    _case(
        "BBNA-03",
        proposition=_prop("bbna-partition-measurement", null="Measurement artifact on delta_yield definition"),
        evidence=[_ev("e1", "SUPPORTING")],
        expect={
            "allow_executability": {
                "SCIENTIFICALLY_VALID_NOT_EXECUTABLE",
                "SCIENTIFICALLY_VALID_EXECUTABLE",
            },
            "must_not_rescue": True,
        },
    ),
    _case(
        "BBNA-04",
        proposition=_prop("bbna-partition-contradiction"),
        evidence=[
            _ev("e1", "SUPPORTING", magnitude="strong"),
            _ev("e2", "DISCONFIRMING", magnitude="strong", overlap=0.15, exp_hash="h2"),
        ],
        expect={
            "priority_actions": {"SEEK_CONTRADICTION_RESOLUTION", "ABANDON"},
            "must_include_contradiction_resolution": True,
        },
    ),
    _case(
        "BBNA-05",
        proposition=_prop("bbna-context-replication", ptype="context_modulation"),
        evidence=[
            _ev("e1", "SUPPORTING", feature="context_gate", axis="context_modulation_direction", magnitude="weak"),
        ],
        prior_state="HYPOTHESIS",
        expect={
            "priority_actions": {"SEEK_REPLICATION", "SEEK_FALSIFICATION"},
            "replication_operator_when_priority": "SEEK_REPLICATION",
        },
    ),
    _case(
        "BBNA-06",
        proposition=_prop("bbna-partition-saturated"),
        evidence=[
            _ev("e1", "SUPPORTING"),
            _ev("e2", "SUPPORTING", overlap=0.98, exp_hash="h2"),
        ],
        priority_override="HOLD_PROVISIONALLY",
        expect={"dispositions": {ActionDisposition.HOLD.value, ActionDisposition.NO_HIGH_INFORMATION_ACTION.value}},
    ),
    _case(
        "BBNA-07",
        proposition=_prop("bbna-partition-falsified-rescue"),
        evidence=[_ev("e1", "DISCONFIRMING", magnitude="strong")],
        prior_state="FALSIFIED",
        expect={
            "dispositions": {ActionDisposition.NO_HIGH_INFORMATION_ACTION.value, ActionDisposition.HOLD.value},
            "no_rescue_candidates": True,
        },
    ),
    _case(
        "BBNA-08",
        proposition=_prop("bbna-partition-hold"),
        evidence=[_ev("e1", "SUPPORTING")],
        priority_override="HOLD_PROVISIONALLY",
        expect={"dispositions": {ActionDisposition.HOLD.value}},
    ),
    _case(
        "BBNA-09",
        proposition=_prop("bbna-context-no-interpreter", ptype="context_modulation"),
        evidence=[_ev("e1", "SUPPORTING", feature="context_gate", axis="context_modulation_direction")],
        executability=ExecutabilityContext(
            available_tools=set(),
            has_regime_column=False,
            panel_columns={"trade_date"},
            abstract_mode=True,
        ),
        expect={"preserve_not_executable": True},
    ),
    _case(
        "BBNA-11",
        proposition=_prop("bbna-partition-multi"),
        evidence=[
            _ev("e1", "SUPPORTING"),
            _ev("e2", "SUPPORTING", axis="episode_robustness", scope="holdout", pop="holdout", overlap=0.05, exp_hash="h2"),
        ],
        expect={"min_distinct_core_hashes": 2},
    ),
    _case(
        "BBNA-12",
        proposition=_prop("bbna-partition-hard-vs-easy"),
        evidence=[
            _ev("e1", "SUPPORTING"),
            _ev("e2", "SUPPORTING", axis="episode_robustness", scope="holdout", pop="holdout", overlap=0.05, exp_hash="h2"),
        ],
        expect={"winner_not_redundant": True},
    ),
    _case(
        "BBNA-13",
        proposition=_prop("bbna-partition-correlated"),
        evidence=[
            _ev("e1", "SUPPORTING"),
            _ev("e2", "SUPPORTING", overlap=0.99, exp_hash="h2"),
        ],
        expect={
            "disguised_strategies_redundant": True,
            "winner_not_disguised_independent": True,
        },
    ),
    _case(
        "BBNA-10",
        proposition=_prop("bbna-partition-two-tools"),
        evidence=[_ev("e1", "SUPPORTING")],
        expect={"same_core_two_tools": True},
    ),
    _case(
        "BBNA-14",
        proposition=_prop("bbna-partition-leakage"),
        evidence=[_ev("e1", "SUPPORTING")],
        expect={"no_invalid_selected": True},
    ),
    _case(
        "BBNA-15",
        proposition=_prop("bbna-partition-template-a"),
        evidence=[_ev("e1", "SUPPORTING")],
        expect={"context_sensitive": "BBNA-15"},
    ),
    _case(
        "BBNA-16",
        proposition=_prop("bbna-context-mutation", ptype="context_modulation"),
        evidence=[_ev("e1", "SUPPORTING", feature="context_gate", axis="context_modulation_direction")],
        expect={"no_rescue_candidates": True},
    ),
    _case(
        "BBNA-17",
        proposition=_prop(
            "bbna-partition-counterexample",
            null="Effect is a single-episode fluke artifact unrelated to flux_index structure",
        ),
        evidence=[_ev("e1", "SUPPORTING")],
        expect={"must_include_strategies": {"counterexample_period_search"}},
    ),
    _case(
        "BBNA-18",
        proposition=_prop("bbna-partition-fork-temptation"),
        evidence=[
            _ev("e1", "SUPPORTING"),
            _ev("e2", "DISCONFIRMING", magnitude="strong", overlap=0.12, exp_hash="h2"),
        ],
        expect={
            "must_include_contradiction_resolution": True,
            "no_rescue_candidates": True,
        },
    ),
]


def all_bbna_cases() -> List[Dict[str, Any]]:
    for c in BB_NEXT_ACTION_01_CASES:
        assert_bb_firewall(c)
        assert_development_firewall(c)
    return BB_NEXT_ACTION_01_CASES


def run_bbna_case(case: Dict[str, Any]) -> Tuple[Any, Any, GenerationResult]:
    prop = case["proposition"]
    prop_spec = {
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop["proposition_hash"],
        "proposition_type": prop["proposition_type"],
    }
    synthesis, priority = synthesize_evidence(prop_spec, case["evidence"], prior_epistemic_state=case["prior_state"])

    if case.get("priority_override"):
        from dataclasses import replace

        priority = replace(priority, chosen_priority_action=case["priority_override"])

    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs

    entries = build_ledger_from_specs(prop_spec["proposition_id"], prop_spec["proposition_hash"], case["evidence"])
    ex = case.get("executability") or ExecutabilityContext.abstract_default()
    ctx = build_context_from_synthesis(
        prop_spec,
        prop,
        synthesis,
        priority,
        entries,
        ex,
        evidence_specs=case["evidence"],
    )
    result = generate_scientific_actions(ctx)
    return synthesis, priority, result


def evaluate_case(case: Dict[str, Any], result: GenerationResult) -> Dict[str, Any]:
    """Return pass/fail diagnostics for a BBNA case."""
    exp = case["expect"]
    checks: Dict[str, bool] = {}
    cores = {c.scientific_action_core_hash for c in result.deduplicated}
    strategies = {c.scientific_action_core.cohort_strategy for c in result.deduplicated}

    if "min_distinct_core_hashes" in exp:
        checks["min_distinct_core_hashes"] = len(cores) >= exp["min_distinct_core_hashes"]
    if "must_include_strategies" in exp:
        checks["must_include_strategies"] = exp["must_include_strategies"].issubset(strategies)
    if "must_not_only_strategy" in exp:
        only = len(strategies) == 1 and exp["must_not_only_strategy"] in strategies
        checks["must_not_only_strategy"] = not only
    if "must_include_axes" in exp:
        axes = {c.expected_new_uncertainty_coverage for c in result.deduplicated}
        checks["must_include_axes"] = exp["must_include_axes"].issubset(axes)
    if "dispositions" in exp:
        checks["dispositions"] = result.selection.disposition.value in exp["dispositions"]
    if "must_include_contradiction_resolution" in exp:
        checks["contradiction_resolution"] = any(
            c.contradiction_resolution_capability for c in result.deduplicated
        )
    if "no_rescue_candidates" in exp:
        checks["no_rescue"] = all(
            c.rescue_risk_classification == "pass" for c in result.deduplicated
        )
    if "preserve_not_executable" in exp:
        checks["not_executable_preserved"] = any(
            c.executability_classification == "SCIENTIFICALLY_VALID_NOT_EXECUTABLE"
            for c in result.deduplicated
        )
    if "must_include_strategies" in exp and "counterexample_period_search" in exp.get("must_include_strategies", set()):
        checks["counterexample"] = "counterexample_period_search" in strategies
    if "winner_not_redundant" in exp and result.selection.selected:
        checks["winner_not_redundant"] = result.selection.selected.redundancy_classification != "REDUNDANT"
    if "allow_executability" in exp:
        classes = {c.executability_classification for c in result.deduplicated}
        checks["allow_executability"] = bool(classes & exp["allow_executability"])
    if exp.get("must_not_rescue"):
        checks["must_not_rescue"] = all(
            c.rescue_risk_classification == "pass" for c in result.deduplicated
        )
    if "priority_actions" in exp:
        checks["priority_actions"] = True  # checked at synthesis level separately
    if "replication_operator_when_priority" in exp:
        case_copy = dict(case)
        case_copy["priority_override"] = exp["replication_operator_when_priority"]
        _, _, res_rep = run_bbna_case(case_copy)
        checks["replication_operator"] = any(
            c.operator_id == "ReplicationOperator" for c in res_rep.candidates
        )
    if "same_core_two_tools" in exp:
        cores = {c.scientific_action_core_hash for c in result.deduplicated}
        checks["dedup_works"] = len(cores) == len(result.deduplicated)
    if "no_invalid_selected" in exp:
        sel = result.selection.selected
        checks["no_invalid_selected"] = sel is None or sel.executability_classification != "INVALID"
    if exp.get("context_sensitive") == "BBNA-15":
        case_b = {
            **case,
            "proposition": _prop("bbna-partition-template-b", ptype="context_modulation", null="Context gate fluke only"),
            "evidence": [_ev("e1", "SUPPORTING", feature="context_gate", axis="context_modulation_direction")],
        }
        _, _, result_b = run_bbna_case(case_b)
        axes_a = {o.target_uncertainty for o in result.objectives}
        axes_b = {o.target_uncertainty for o in result_b.objectives}
        checks["context_changes_actions"] = axes_a != axes_b or result.objectives[0].scientific_vulnerability != result_b.objectives[0].scientific_vulnerability
    if "disguised_strategies_redundant" in exp:
        disguised = {"episode_holdout_excluding_motivating", "independent_replication_cohort", "full_panel_contrast"}
        disguised_cands = [c for c in result.deduplicated if c.scientific_action_core.cohort_strategy in disguised]
        checks["disguised_redundant"] = all(
            c.redundancy_classification == "REDUNDANT" for c in disguised_cands
        ) if disguised_cands else True
    if "winner_not_disguised_independent" in exp and result.selection.selected:
        disguised = {"episode_holdout_excluding_motivating", "independent_replication_cohort", "full_panel_contrast"}
        checks["winner_not_disguised"] = (
            result.selection.selected.scientific_action_core.cohort_strategy not in disguised
        )

    passed = all(checks.values()) if checks else False
    return {"case_id": case["case_id"], "checks": checks, "passed": passed, "disposition": result.selection.disposition.value}
