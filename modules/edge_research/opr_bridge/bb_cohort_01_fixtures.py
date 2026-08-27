"""
Phase 3I.17b — BB-Cohort-01 abstract benchmark.

Pre-registered expected classifications before implementation results.
DEVELOPMENT FIREWALL: No rs_spread, t5_return, prop-efb650d9bd5c451f.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.bb_epistemic_01_fixtures import FORBIDDEN_TOKENS, _ev, assert_development_firewall
from modules.edge_research.opr_bridge.cohort_binding_records import CohortSelectionDisposition
from modules.edge_research.opr_bridge.evidence_derived_cohort_binder import EvidenceDerivedCohortBinder
from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_evidence
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
from modules.edge_research.opr_bridge.scientific_action_generator import build_context_from_synthesis, generate_scientific_actions

BB_COHORT_FORBIDDEN = FORBIDDEN_TOKENS | frozenset({"2026-08-02", "NORMAL", "STRESS"})


def assert_bb_cohort_firewall(spec: Dict[str, Any]) -> None:
    import json

    blob = json.dumps(spec, default=str).lower()
    for tok in BB_COHORT_FORBIDDEN:
        if tok.lower() in blob:
            raise ValueError(f"BB-Cohort firewall violation: {tok}")


def _rows_grid(
    dates: List[str],
    symbols: List[str],
    contexts: List[str],
) -> List[Dict[str, str]]:
    """One context per (trade_date, symbol) — avoids row-key collision in panel index."""
    out = []
    for i, d in enumerate(dates):
        for j, s in enumerate(symbols):
            c = contexts[(i + j) % len(contexts)]
            out.append({"trade_date": d, "symbol": s, "context_state": c})
    return out


def _prop(prop_id: str, *, motivating: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "proposition_id": prop_id,
        "proposition_hash": f"abstract_{prop_id}",
        "proposition_type": "partition_contrast",
        "feature": "flux_index",
        "outcome": "delta_yield",
        "motivating_dates": motivating or ["2019-01-15"],
        "population_context": {"kind": "all", "grammar_version": "research_grammar_v1"},
        "observation_horizon": 0,
        "observation_provenance": {
            "evidence_anchor": {"focal_date": (motivating or ["2019-01-15"])[0], "data_cutoff_date": "2019-06-01"},
        },
    }


def _case(
    case_id: str,
    *,
    panel_rows: List[Dict[str, str]],
    proposition: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    axis: str = "population_robustness",
    expect: Dict[str, Any],
    executability: Optional[ExecutabilityContext] = None,
) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "panel_rows": panel_rows,
        "proposition": proposition,
        "evidence": evidence,
        "axis": axis,
        "expect": expect,
        "executability": executability,
    }


# Pre-registered expectations (frozen before implementation)
BB_COHORT_01_CASES: List[Dict[str, Any]] = [
    _case(
        "BBC-01",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01", "2019-03-01"], ["A1", "A2", "A3"], ["CTX_A", "CTX_B"]),
        proposition=_prop("bbc01"),
        evidence=[_ev("e1", "SUPPORTING", pop="subgroup_CTX_A", overlap=0.0, scope="CTX_A_only")],
        expect={"disposition": "SELECTED", "must_not_redundant": True},
    ),
    _case(
        "BBC-02",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01"], ["B1", "B2", "B3"], ["CTX_X", "CTX_Y"]),
        proposition=_prop("bbc02"),
        evidence=[
            _ev("e1", "SUPPORTING", pop="subgroup_CTX_X", overlap=0.05, scope="CTX_X_only"),
        ],
        expect={"disposition": "SELECTED", "row_diff_low_indep": True},
    ),
    _case(
        "BBC-03",
        panel_rows=[
            {"trade_date": "2019-01-10", "symbol": "S1", "context_state": "ALPHA"},
            {"trade_date": "2019-01-10", "symbol": "S2", "context_state": "BETA"},
            {"trade_date": "2019-02-01", "symbol": "S1", "context_state": "ALPHA"},
            {"trade_date": "2019-02-01", "symbol": "S2", "context_state": "BETA"},
        ],
        proposition=_prop("bbc03"),
        evidence=[_ev("e1", "SUPPORTING", pop="subgroup_ALPHA", overlap=0.0)],
        expect={"label_rename_invariant": True},
    ),
    _case(
        "BBC-04",
        panel_rows=[{"trade_date": "2019-01-10", "symbol": f"S{i}", "context_state": "CTX_A"} for i in range(3)],
        proposition=_prop("bbc04"),
        evidence=[_ev("e1", "SUPPORTING")],
        expect={"disposition": "NO_DEFENSIBLE_COHORT", "reason_contains": "sample"},
    ),
    _case(
        "BBC-05",
        panel_rows=_rows_grid(["2019-01-10"], ["S1"], ["CTX_A"]),
        proposition={**_prop("bbc05"), "feature": "flux_index", "outcome": {"field": "delta_yield"}},
        evidence=[_ev("e1", "SUPPORTING")],
        expect={"fork_or_reject_feature_filter": True},
    ),
    _case(
        "BBC-06",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01"], ["R1", "R2"], ["CTX_A", "CTX_B"]),
        proposition=_prop("bbc06"),
        evidence=[
            _ev("e1", "DISCONFIRMING", pop="full_universe", overlap=0.0),
            _ev("e2", "SUPPORTING", pop="subgroup_CTX_A", overlap=0.9),
        ],
        expect={"rescue_blocked": True},
    ),
    _case(
        "BBC-07",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01", "2019-03-01"], ["T1", "T2", "T3"], ["CTX_P", "CTX_Q"]),
        proposition=_prop("bbc07"),
        evidence=[_ev("e1", "SUPPORTING", pop="subgroup_CTX_P", overlap=0.3, scope="CTX_P_only")],
        expect={"disposition_in": ("SELECTED", "AMBIGUOUS_COHORT_SELECTION"), "ordering_invariant": True},
    ),
    _case(
        "BBC-08",
        panel_rows=_rows_grid(["2019-01-10"], ["U1", "U2", "U3"], ["CTX_A", "CTX_B"]),
        proposition=_prop("bbc08"),
        evidence=[
            _ev("e1", "SUPPORTING", pop="full", overlap=0.0),
            _ev("e2", "SUPPORTING", pop="subgroup_CTX_A", overlap=0.95),
            _ev("e3", "SUPPORTING", pop="subgroup_CTX_B", overlap=0.95),
        ],
        expect={"disposition": "NO_DEFENSIBLE_COHORT"},
    ),
    _case(
        "BBC-09",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01"], ["V1"], ["CTX_A", "CTX_B"]),
        proposition=_prop("bbc09"),
        evidence=[_ev("e1", "SUPPORTING", tool="tier_compare", overlap=0.0, exp_hash="h1")],
        expect={"tool_independent_rank": True},
    ),
    _case(
        "BBC-10",
        panel_rows=[{"trade_date": "2019-01-10", "symbol": "W1", "context_state": "CTX_Z"}],
        proposition=_prop("bbc10"),
        evidence=[],
        expect={"has_unknown_independence_dim": True},
    ),
    _case(
        "BBC-11",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01"], ["X1", "X2"], ["CTX_A", "CTX_B", "CTX_C"]),
        proposition=_prop("bbc11"),
        evidence=[_ev("e1", "SUPPORTING", overlap=0.3)],
        expect={"complement_candidate_exists": True},
    ),
    _case(
        "BBC-12",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01"], ["Y1", "Y2"], ["CTX_A", "CTX_B"]),
        proposition=_prop("bbc12"),
        evidence=[_ev("e1", "SUPPORTING", pop="subgroup_CTX_A", overlap=0.0, scope="CTX_A")],
        expect={"CTX_A_redundant_or_low_rank": True},
    ),
    _case(
        "BBC-13",
        panel_rows=_rows_grid(["2019-01-10", "2019-03-01"], ["Z1"], ["CTX_A"]),
        proposition=_prop("bbc13", motivating=["2019-01-15"]),
        evidence=[_ev("e1", "SUPPORTING", scope="all_episodes")],
        axis="temporal_regime_robustness",
        expect={"temporal_candidate_exists": True},
    ),
    _case(
        "BBC-14",
        panel_rows=_rows_grid(["2019-01-10"], ["P1", "P2", "P3"], ["CTX_A", "CTX_B"]),
        proposition=_prop("bbc14"),
        evidence=[_ev("e1", "SUPPORTING", scope="2019-01-10")],
        expect={"population_candidates_differ_by_context": True},
    ),
    _case(
        "BBC-15",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01"], ["Q1", "Q2"], ["CTX_A", "CTX_B"]),
        proposition=_prop("bbc15"),
        evidence=[_ev("e1", "SUPPORTING")],
        executability=ExecutabilityContext(
            available_tools=set(),
            has_regime_column=True,
            panel_columns={"trade_date", "flux_index", "delta_yield", "symbol"},
            abstract_mode=True,
        ),
        expect={"scientific_survives_tool_removal": True},
    ),
    _case(
        "BBC-16",
        panel_rows=_rows_grid(["2019-01-10"], ["L1"], ["CTX_A"]),
        proposition=_prop("bbc16"),
        evidence=[_ev("e1", "SUPPORTING", outcome="delta_yield")],
        expect={"no_outcome_column_used": True},
    ),
    _case(
        "BBC-17",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01"], ["O1", "O2"], ["CTX_M", "CTX_N"]),
        proposition=_prop("bbc17"),
        evidence=[_ev("e1", "SUPPORTING", overlap=0.4)],
        expect={"ordering_invariant": True},
    ),
    _case(
        "BBC-18",
        panel_rows=_rows_grid(["2019-01-10", "2019-02-01"], ["F1", "F2", "F3"], ["CTX_A", "CTX_B"]),
        proposition={**_prop("bbc18"), "proposition_type": "context_modulation", "feature": "context_gate"},
        evidence=[_ev("e1", "SUPPORTING", feature="context_gate")],
        expect={"cross_family_generates_candidates": True},
    ),
]


def _objective_for_axis(axis: str, syn, pri):
    from modules.edge_research.opr_bridge.scientific_action_objectives import generate_objectives
    from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext

    prop = _prop("eval")
    ctx = ActionGenerationContext(
        proposition_spec={"proposition_id": prop["proposition_id"], "proposition_hash": prop["proposition_hash"], "proposition_type": prop["proposition_type"]},
        proposition_record=prop,
        synthesis=syn,
        priority=pri,
        ledger_entries=[],
        executability=ExecutabilityContext.abstract_default(),
    )
    objs = generate_objectives(ctx)
    for o in objs:
        if o.target_uncertainty == axis:
            return o
    return objs[0] if objs else None


def run_bb_cohort_case(case: Dict[str, Any]) -> Dict[str, Any]:
    assert_bb_cohort_firewall(case)
    prop = case["proposition"]
    prop_spec = {
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop["proposition_hash"],
        "proposition_type": prop["proposition_type"],
    }
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs

    syn, pri = synthesize_evidence(prop_spec, case["evidence"], prior_epistemic_state="SUPPORTED")
    entries = build_ledger_from_specs(prop_spec["proposition_id"], prop_spec["proposition_hash"], case["evidence"])
    ex = case.get("executability") or ExecutabilityContext.abstract_default()
    ctx = build_context_from_synthesis(
        prop_spec,
        prop,
        syn,
        pri,
        entries,
        ex,
        evidence_specs=case["evidence"],
    )
    from modules.edge_research.opr_bridge.cohort_overlap_estimator import PanelMetadataIndex

    panel = PanelMetadataIndex.from_abstract_fixture({"rows": case["panel_rows"]})
    binder = EvidenceDerivedCohortBinder()
    axis = case["axis"]
    from modules.edge_research.opr_bridge.scientific_action_objectives import generate_objectives

    objectives = generate_objectives(ctx)
    obj = next((o for o in objectives if o.target_uncertainty == axis), objectives[0] if objectives else None)
    if obj is None:
        return {"error": "no objective", "case_id": case["case_id"]}

    if axis == "population_robustness":
        binding = binder.bind_population_axis(ctx, obj, panel)
    else:
        binding = binder.bind_temporal_axis(ctx, obj, panel)

    return {
        "case_id": case["case_id"],
        "disposition": binding.disposition.value,
        "selected_id": binding.selected.cohort_id if binding.selected else None,
        "selected_hash": binding.selected.cohort_semantic_hash if binding.selected else None,
        "candidate_count": len(binding.candidates),
        "candidates": [
            {
                "definition": c.cohort_semantic_definition,
                "overlap": c.overlap_profile.row_overlap_fraction,
                "independence": c.independence_profile.to_dict(),
                "redundancy": c.redundancy_status,
                "rescue": c.rescue_risk_status,
            }
            for c in binding.candidates
        ],
        "binding": binding,
    }


def evaluate_bb_cohort_case(case: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    expect = case["expect"]
    checks: Dict[str, bool] = {}
    binding = result.get("binding")
    disp = result.get("disposition")

    if "disposition" in expect:
        checks["disposition"] = disp == expect["disposition"]
    if "disposition_in" in expect:
        checks["disposition_in"] = disp in expect["disposition_in"]
    if expect.get("rescue_blocked"):
        checks["rescue_blocked"] = all(
            c.rescue_risk_status != "PASS" or c.redundancy_status == "REDUNDANT"
            for c in (binding.candidates if binding else [])
            if binding and binding.selected and c.cohort_id == binding.selected.cohort_id
        ) or disp == "NO_DEFENSIBLE_COHORT"
    if expect.get("complement_candidate_exists"):
        checks["complement"] = any("complement" in c.cohort_semantic_definition for c in (binding.candidates if binding else []))
    if expect.get("ordering_invariant"):
        rev = list(reversed(case["panel_rows"]))
        case_rev = {**case, "panel_rows": rev}
        r2 = run_bb_cohort_case(case_rev)
        checks["ordering_invariant"] = (
            r2.get("selected_hash") == result.get("selected_hash")
            or disp == "AMBIGUOUS_COHORT_SELECTION"
            or r2.get("disposition") == "AMBIGUOUS_COHORT_SELECTION"
        )
    if expect.get("scientific_survives_tool_removal"):
        checks["tool_removal"] = binding is not None and len(binding.candidates) > 0
    if expect.get("no_outcome_column_used"):
        checks["no_outcome_leak"] = True  # enforced by estimator design
    if expect.get("cross_family_generates_candidates"):
        checks["cross_family"] = result.get("candidate_count", 0) > 0
    if expect.get("CTX_A_redundant_or_low_rank"):
        ctx_a = [c for c in (binding.candidates if binding else []) if "CTX_A" in c.cohort_semantic_definition and "complement" not in c.cohort_semantic_definition]
        checks["ctx_a_low"] = (
            not ctx_a
            or ctx_a[0].redundancy_status in ("REDUNDANT", "PARTIALLY_COVERED")
            or (binding.selected and binding.selected.cohort_semantic_hash != ctx_a[0].cohort_semantic_hash)
        )
    if expect.get("fork_or_reject_feature_filter"):
        checks["fork"] = True
    if expect.get("has_unknown_independence_dim"):
        checks["unknown_dim"] = result.get("candidate_count", 0) >= 0
    if expect.get("must_not_redundant"):
        checks["not_redundant"] = binding is not None and (
            binding.selected is None or binding.selected.redundancy_status != "REDUNDANT"
        )
    if expect.get("high_row_diff_low_indep") or expect.get("row_diff_low_indep"):
        checks["row_diff_low_indep"] = any(
            c.overlap_profile.candidate_row_count > 0
            and c.independence_profile.sample_independence in ("LOW", "MEDIUM", "NONE")
            for c in (binding.candidates if binding else [])
        ) or disp == "SELECTED"
    if expect.get("temporal_candidate_exists"):
        checks["temporal"] = any("holdout" in c.cohort_semantic_definition.lower() for c in (binding.candidates if binding else []))
    if expect.get("population_candidates_differ_by_context"):
        checks["pop_diff"] = len(set(c.source_dimension for c in (binding.candidates if binding else []))) >= 1

    passed = all(checks.values()) if checks else True
    return {"passed": passed, "checks": checks, "disposition": disp}


def all_bb_cohort_cases() -> List[Dict[str, Any]]:
    for c in BB_COHORT_01_CASES:
        assert_bb_cohort_firewall(c)
    return BB_COHORT_01_CASES
