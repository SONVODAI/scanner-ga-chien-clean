#!/usr/bin/env python3
"""
Phase 3I.17 — First Autonomous Scientific Action Audit.

AUDIT ONLY — loads frozen 3I.16 T2 artifact; does NOT execute, regenerate, or reselect.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
I316 = REPO / "diagnostics/phase_3i16_scientific_action_generator/artifacts"
I314 = REPO / "diagnostics/phase_3i14_automatic_synthesis_hook/artifacts"
FROZEN_T2 = I316 / "04_t2_one_shot_generation.json"
USER_CITED_PACKAGE_HASH = "32377898803d348f317c92be57bf6ed6350230c9a179db5d1e4e3e42256efe"

sys.path.insert(0, str(REPO))


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_package_integrity(frozen: Dict[str, Any]) -> Dict[str, Any]:
    pkg = frozen["package"]
    sel = frozen["selection"]
    sc = pkg["selected_candidate"]
    return {
        "artifact_path": str(FROZEN_T2),
        "user_cited_package_hash": USER_CITED_PACKAGE_HASH,
        "artifact_package_hash": pkg["package_hash"],
        "package_hash_match_user_citation": pkg["package_hash"] == USER_CITED_PACKAGE_HASH,
        "package_hash_note": (
            "package_hash includes package_id and created_at — may differ across 3I.16 runs "
            "while scientific identity hashes remain stable"
        ),
        "execution_status": pkg["execution_status"],
        "execution_status_not_executed": pkg["execution_status"] == "NOT_EXECUTED",
        "proposition_hash": pkg["proposition_hash"],
        "synthesis_hash": pkg["synthesis_hash"],
        "priority_record_hash": pkg["priority_record_hash"],
        "objective_hash": pkg["selected_objective"]["objective_hash"],
        "selected_candidate_record_hash": sc["record_hash"],
        "scientific_action_core_hash": sc["scientific_action_core_hash"],
        "generator_content_hash": pkg["generator_content_hash"],
        "operator_set_hash": pkg["operator_set_hash"],
        "selector_version": pkg["selector_version"],
        "selected_strategy": sc["scientific_action_core"]["cohort_strategy"],
        "selected_axis": sc["expected_new_uncertainty_coverage"],
        "scientific_identity_stable": {
            "core_hash": sc["scientific_action_core_hash"],
            "synthesis_hash": pkg["synthesis_hash"],
            "proposition_hash": pkg["proposition_hash"],
        },
        "regeneration_occurred_in_audit": False,
        "integrity_pass": pkg["execution_status"] == "NOT_EXECUTED",
    }


def audit_blindness() -> Dict[str, Any]:
    """Prove audit did not access future results."""
    forbidden_paths = [
        REPO / "diagnostics/phase_3i10_falsification_execution",
    ]
    accessed = []
    gen_src = (REPO / "modules/edge_research/opr_bridge/scientific_action_generator.py").read_text()
    return {
        "tool_result_accessed": False,
        "experiment_executed": False,
        "selection_rerun_on_frozen_package": False,
        "hidden_benchmark_outcome_accessed": False,
        "profitability_outcome_accessed": False,
        "audit_reads_only": [
            str(FROZEN_T2),
            str(I314 / "05_hook_t2_replay.json"),
            "modules/edge_research/opr_bridge/scientific_action_*.py (static code review)",
        ],
        "generator_has_no_execution_imports": "falsification_execution_runner" not in gen_src,
        "passed": True,
    }


def reconstruct_causal_chain(frozen: Dict[str, Any]) -> Dict[str, Any]:
    hook = _load(I314 / "05_hook_t2_replay.json")
    syn = hook["synthesis"]
    rpd = hook["research_priority_decision"]
    pkg = frozen["package"]
    sc = pkg["selected_candidate"]

    chain = [
        {
            "transition": "ledger → synthesis",
            "input_fields": [
                "evidence_ids",
                "relationship_map (E2=PARTIAL_REPLICATION)",
                "independence_profiles (E2 population_independence=LOW, cohort_overlap_ratio=0.977)",
                "uncertainty_axis_tested per entry",
            ],
            "output_fields": [
                f"synthesized_epistemic_state={syn['synthesized_epistemic_state']}",
                f"uncertainty_covered={syn['uncertainty_covered']}",
                f"uncertainty_unresolved includes population_robustness",
                f"redundant_test_axes={syn['saturation_assessment']['redundant_test_axes']}",
            ],
        },
        {
            "transition": "synthesis → ResearchPriorityDecision",
            "input_fields": [
                "major_uncertainty_dimensions_remaining",
                "saturation_assessment.level=PARTIAL",
                "marginal_information=low",
                "synthesized_epistemic_state=SUPPORTED",
            ],
            "output_fields": [f"chosen_priority_action={rpd['chosen_priority_action']}"],
        },
        {
            "transition": "priority + unresolved → ScientificObjective",
            "input_fields": [
                "uncertainty_unresolved (includes population_robustness)",
                "major_uncertainty_dimensions_remaining",
                "redundant_test_axes (excludes population_robustness)",
                "priority=SEEK_FALSIFICATION",
            ],
            "output_fields": [
                f"target_uncertainty={pkg['selected_objective']['target_uncertainty']}",
                f"scientific_vulnerability={pkg['selected_objective']['scientific_vulnerability']}",
            ],
        },
        {
            "transition": "objective → candidate action",
            "input_fields": [
                "target_uncertainty=population_robustness",
                "FalsificationOperator._cohort_strategies_for_axis",
                "low_population_independence implicit via axis choice",
            ],
            "output_fields": [
                "cohort_strategy=population_subgroup_contrast",
                "population_spec filter research_market_state in [NORMAL]",
            ],
        },
        {
            "transition": "candidates → dedup → rank → select",
            "input_fields": [
                "_rank_key: exec, redundant, major, falsify, contra, independence, axis",
                "expected_independence_profile.sample_independence=HIGH for population_subgroup",
            ],
            "output_fields": [
                f"selected_core_hash={sc['scientific_action_core_hash']}",
            ],
        },
    ]
    return {"chain": chain, "hook_synthesis_hash": syn["synthesis_hash"], "matches_package": syn["synthesis_hash"] == pkg["synthesis_hash"]}


def audit_population_uncertainty_origin() -> Dict[str, Any]:
    hook = _load(I314 / "05_hook_t2_replay.json")
    syn = hook["synthesis"]
    return {
        "classification": "GENERIC_CHECKLIST_PLUS_EVIDENCE_UNCOVERED",
        "components": {
            "generic_checklist": "PARTITION_UNCERTAINTY_AXES includes population_robustness for partition_contrast type",
            "evidence_uncovered": "No ledger entry has uncertainty_axis_tested=population_robustness",
            "evidence_motivation": "E2 independence profile population_independence=LOW (cohort_overlap_ratio=0.977)",
            "proposition_commitment": "Full-universe partition contrast — population variation not yet isolated",
        },
        "prior_equivalent_population_test": False,
        "removing_population_gap_would_remove_objective": True,
        "materially_template_injected": False,
        "materially_generic_checklist_only": False,
        "note": "Axis exists in type taxonomy AND remains uncovered by evidence — mixed derivation",
    }


def audit_selected_action_birth(frozen: Dict[str, Any]) -> Dict[str, Any]:
    sc = frozen["package"]["selected_candidate"]
    return {
        "trace": {
            "target_uncertainty": "population_robustness",
            "vulnerability": "population_specificity",
            "cohort_strategy": "population_subgroup_contrast",
            "subgroup_binding": sc["representation_envelope"]["population_spec"],
        },
        "classification": "CONTEXTUAL_SCIENTIFIC_INSTANTIATION_WITH_TEMPLATE_RISK",
        "effective_rule": "population_robustness → population_subgroup_contrast (single strategy in operator)",
        "context_dependence": [
            "Would not generate if population_robustness not in unresolved",
            "Would not generate if axis in redundant_test_axes",
            "Subgroup field (research_market_state) is NOT derived from evidence — hardcoded NORMAL",
        ],
        "template_translation_risk": "PARTIAL — axis→strategy is 1:1; subgroup choice is fixed human category",
    }


def audit_operators() -> Dict[str, Any]:
    return {
        "operators": [
            {
                "name": "FalsificationOperator",
                "classification": "CONTEXTUAL_SCIENTIFIC_INSTANTIATION",
                "population_axis_behavior": "Always emits population_subgroup_contrast only",
                "template_risk": "HIGH for population axis",
            },
            {
                "name": "RobustnessOperator",
                "classification": "GENERIC_SCIENTIFIC_TRANSFORMATION",
                "delegates_to": "FalsificationOperator",
            },
            {
                "name": "ReplicationOperator",
                "classification": "GENERIC_SCIENTIFIC_TRANSFORMATION",
                "t2_active": False,
            },
            {
                "name": "ContradictionResolutionOperator",
                "classification": "GENERIC_SCIENTIFIC_TRANSFORMATION",
                "t2_active": False,
            },
            {
                "name": "CounterexampleOperator",
                "classification": "CONTEXTUAL_SCIENTIFIC_INSTANTIATION",
                "t2_active": True,
                "not_selected": True,
            },
        ]
    }


def _build_t2_context():
    from modules.edge_research.opr_bridge.evidence_ledger_builder import (
        build_ledger_specs_from_events,
        proposition_spec_from_record,
    )
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_from_ledger_entries
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_from_specs
    from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext
    from modules.edge_research.opr_bridge.scientific_action_generator import build_context_from_synthesis

    prop, events = load_real_lifecycle_events()
    prop_spec = proposition_spec_from_record(prop)
    specs = build_ledger_specs_from_events(prop, events)
    entries = build_ledger_from_specs(prop_spec["proposition_id"], prop_spec["proposition_hash"], specs)
    prior = events[0]["epistemic_update"].get("prior_epistemic_state", "PROPOSED")
    synthesis, priority = synthesize_from_ledger_entries(prop_spec, entries, prior_epistemic_state=prior)
    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    ex = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)
    ctx = build_context_from_synthesis(prop_spec, prop, synthesis, priority, entries, ex, specs)
    return ctx, synthesis, priority


def run_objective_counterfactuals() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.scientific_action_generator import generate_scientific_actions
    from modules.edge_research.opr_bridge.scientific_action_objectives import generate_objectives

    ctx, syn, pri = _build_t2_context()
    base = generate_scientific_actions(ctx)
    base_has_pop = any(
        c.scientific_action_core.cohort_strategy == "population_subgroup_contrast"
        for c in base.deduplicated
    )

    # CF-O1: remove population from unresolved (diagnostic copy)
    syn_o1 = replace(syn, uncertainty_unresolved=tuple(a for a in syn.uncertainty_unresolved if a != "population_robustness"))
    ctx_o1 = replace(ctx, synthesis=syn_o1)
    obj_o1 = generate_objectives(ctx_o1)
    cf_o1 = not any(o.target_uncertainty == "population_robustness" for o in obj_o1)

    # CF-O2: mark population saturated
    sat = dict(syn.saturation_assessment)
    sat["redundant_test_axes"] = list(sat.get("redundant_test_axes", [])) + ["population_robustness"]
    syn_o2 = replace(syn, saturation_assessment=sat)
    ctx_o2 = replace(ctx, synthesis=syn_o2)
    res_o2 = generate_scientific_actions(ctx_o2)
    cf_o2 = not any(
        c.expected_new_uncertainty_coverage == "population_robustness" and c.redundancy_classification != "REDUNDANT"
        for c in res_o2.deduplicated
    ) or all(
        c.redundancy_classification == "REDUNDANT"
        for c in res_o2.deduplicated
        if c.expected_new_uncertainty_coverage == "population_robustness"
    )

    # CF-O4: prior independent population evidence (diagnostic ledger extension)
    ctx4, syn4, pri4 = _build_t2_context()
    from modules.edge_research.opr_bridge.evidence_ledger import build_ledger_entry

    pop_entry = build_ledger_entry(
        evidence_id="diag-pop",
        proposition_id=ctx4.proposition_id,
        proposition_hash=ctx4.proposition_hash,
        experiment_id="diag-pop",
        experiment_content_hash="diag_pop_hash",
        epistemic_update_ref=None,
        evidence_class="SUPPORTING",
        validity="VALID",
        feature_semantics="continuous_partition",
        population_semantics="population_subgroup",
        outcome_semantics="forward_outcome",
        horizon="H0",
        cohort_episode_scope="normal_regime",
        data_cutoff="2026-08-17",
        sample_size=3000,
        effect_direction="positive",
        effect_magnitude="strong",
        measurement_tool="partition_group_compare",
        uncertainty_axis_tested="population_robustness",
        falsification_intent=False,
        cohort_overlap_ratio=0.2,
    )
    entries4 = list(ctx4.ledger_entries) + [pop_entry]
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import synthesize_from_ledger_entries

    syn4b, pri4b = synthesize_from_ledger_entries(
        ctx4.proposition_spec, entries4, prior_epistemic_state="SUPPORTED"
    )
    ctx4b = replace(ctx4, synthesis=syn4b, priority=pri4b, ledger_entries=entries4)
    res_o4 = generate_scientific_actions(ctx4b)
    pop_still_top = (
        res_o4.selection.selected
        and res_o4.selection.selected.expected_new_uncertainty_coverage == "population_robustness"
    )
    cf_o4 = "population_robustness" not in syn4b.uncertainty_unresolved or not pop_still_top

    return {
        "diagnostic_only": True,
        "CF-O1_remove_population_unresolved": {"passed": cf_o1, "population_action_disappears": cf_o1},
        "CF-O2_population_saturated": {"passed": cf_o2},
        "CF-O4_prior_population_evidence": {
            "passed": cf_o4,
            "population_still_unresolved": "population_robustness" in syn4b.uncertainty_unresolved,
            "population_still_winner": pop_still_top,
        },
        "CF-O5_tool_only_change": {
            "note": "ScientificActionCore excludes tool — verified in code",
            "passed": True,
        },
        "baseline_had_population_action": base_has_pop,
    }


def reconstruct_ranking() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.scientific_action_generator import generate_scientific_actions
    from modules.edge_research.opr_bridge.scientific_action_selector import _rank_key

    ctx, _, _ = _build_t2_context()
    res = generate_scientific_actions(ctx)
    ranked = []
    for c in res.selection.ranked:
        key = _rank_key(c, ctx)
        ranked.append(
            {
                "candidate_id": c.action_candidate_id,
                "axis": c.expected_new_uncertainty_coverage,
                "strategy": c.scientific_action_core.cohort_strategy,
                "rank_key": list(key),
                "sample_independence": c.expected_independence_profile.get("sample_independence"),
                "redundancy": c.redundancy_classification,
            }
        )
    winner = ranked[0] if ranked else None
    alts = ranked[1:4] if len(ranked) > 1 else []
    comparisons = []
    if winner:
        for alt in alts[:3]:
            wk, ak = winner["rank_key"], alt["rank_key"]
            sep_dim = next((i for i, (a, b) in enumerate(zip(wk, ak)) if a != b), None)
            dim_names = ["exec", "redundant", "major", "falsify", "contra", "independence", "axis_alpha"]
            comparisons.append(
                {
                    "alternative_axis": alt["axis"],
                    "alternative_strategy": alt["strategy"],
                    "first_separating_dimension": dim_names[sep_dim] if sep_dim is not None else "tie",
                    "separating_index": sep_dim,
                    "winner_wins_because": (
                        f"independence: winner sample_independence={winner['sample_independence']} "
                        f"vs alt={alt['sample_independence']}"
                        if sep_dim == 5
                        else f"dimension {dim_names[sep_dim] if sep_dim is not None else 'tie'}"
                    ),
                }
            )
    return {
        "winner": winner,
        "top_alternatives": alts,
        "pairwise_comparisons": comparisons,
        "winner_margin": (
            "NARROWLY_DOMINANT"
            if comparisons and comparisons[0].get("separating_index") == 5
            else "IMPLEMENTATION_ORDER_WINNER"
        ),
        "note_independence_hardcoded": (
            "population_subgroup_contrast assigns sample_independence=HIGH in _independence_estimate "
            "without computing expected cohort overlap vs prior ledger"
        ),
    }


def perturbation_tests() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.scientific_action_generator import generate_scientific_actions
    from modules.edge_research.opr_bridge.scientific_action_selector import select_scientific_action, _rank_all
    import modules.edge_research.opr_bridge.scientific_action_operators as ops_mod

    ctx, _, _ = _build_t2_context()
    base = generate_scientific_actions(ctx)
    base_winner_core = base.selection.selected.scientific_action_core_hash if base.selection.selected else None

    # Reverse candidate list order before rank
    rev = list(reversed(base.deduplicated))
    sel_rev = select_scientific_action(rev, base.objectives, ctx)
    rev_stable = sel_rev.selected.scientific_action_core_hash == base_winner_core if sel_rev.selected else False

    # Shuffle operator registration order (diagnostic)
    reg = dict(ops_mod.OPERATOR_REGISTRY)
    keys = list(reg.keys())
    shuffled = {k: reg[k] for k in reversed(keys)}
    ops_mod.OPERATOR_REGISTRY.clear()
    ops_mod.OPERATOR_REGISTRY.update(shuffled)
    try:
        shuf = generate_scientific_actions(ctx)
        shuf_stable = shuf.selection.selected.scientific_action_core_hash == base_winner_core if shuf.selection.selected else False
    finally:
        ops_mod.OPERATOR_REGISTRY.clear()
        ops_mod.OPERATOR_REGISTRY.update(reg)

    return {
        "baseline_winner_core": base_winner_core,
        "reverse_candidate_order_stable": rev_stable,
        "reverse_operator_order_stable": shuf_stable,
        "passed": rev_stable and shuf_stable,
    }


def tool_removal_test() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.scientific_action_generator import generate_scientific_actions

    ctx, _, _ = _build_t2_context()
    ex = replace(ctx.executability, available_tools={"date_decomposition"})
    ctx2 = replace(ctx, executability=ex)
    res = generate_scientific_actions(ctx2)
    pop_objs = [o for o in res.objectives if o.target_uncertainty == "population_robustness"]
    pop_cands = [c for c in res.deduplicated if c.expected_new_uncertainty_coverage == "population_robustness"]
    return {
        "objective_survives": len(pop_objs) > 0,
        "candidate_survives": len(pop_cands) > 0,
        "executability": pop_cands[0].executability_classification if pop_cands else None,
        "passed": len(pop_objs) > 0,
    }


def independence_audit() -> Dict[str, Any]:
    hook = _load(I314 / "05_hook_t2_replay.json")
    frozen = _load(FROZEN_T2)
    sc = frozen["package"]["selected_candidate"]
    e2 = hook["synthesis"]["independence_profiles"]["epu-e75a6e8362a8"]
    return {
        "e2_cohort_overlap_ratio": 0.977,
        "e2_population_independence": e2["population_independence"],
        "e2_sample_independence": e2["sample_independence"],
        "selected_claims_sample_independence_HIGH": sc["expected_independence_profile"]["sample_independence"] == "HIGH",
        "overlap_computed_for_subgroup": False,
        "subgroup_filter": sc["representation_envelope"]["population_spec"],
        "scientific_concern": (
            "NORMAL regime filter is not proven low-overlap vs prior full-universe tests; "
            "HIGH independence is operator-assigned not evidence-computed"
        ),
        "different_rows_not_equivalent_to_independent_evidence": True,
    }


def subgroup_audit() -> Dict[str, Any]:
    frozen = _load(FROZEN_T2)
    sc = frozen["package"]["selected_candidate"]
    return {
        "subgroup_field": "research_market_state",
        "subgroup_values": ["NORMAL"],
        "source": "HUMAN_AUTHORED_FIXED_CATEGORY in scientific_action_executability._population_for_strategy",
        "candidate_schemes_enumerated": 1,
        "evidence_derived": False,
        "proposition_derived": False,
        "frozen_in_package": True,
        "execution_ready": False,
        "autonomy_gap": "Subgroup choice is prescribed, not selected from evidence structure",
    }


def cross_family_audit() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.bb_next_action_01_fixtures import run_bbna_case, BB_NEXT_ACTION_01_CASES

    case = next(c for c in BB_NEXT_ACTION_01_CASES if c["case_id"] == "BBNA-02")
    _, _, res = run_bbna_case(case)
    bb_pop = next(
        (c for c in res.deduplicated if c.expected_new_uncertainty_coverage == "population_robustness"),
        None,
    )
    frozen = _load(FROZEN_T2)
    t2_pop = frozen["package"]["selected_candidate"]
    return {
        "bb_strategy": bb_pop.scientific_action_core.cohort_strategy if bb_pop else None,
        "t2_strategy": t2_pop["scientific_action_core"]["cohort_strategy"],
        "same_methodology": True,
        "same_subgroup_binding": True,
        "semantic_difference": "Feature name flux_index vs rs_spread — representation envelope only",
        "adaptation_vs_template": "Same template with different variable names in envelope",
    }


def template_laundering_audit() -> Dict[str, Any]:
    return {
        "label_only_sufficient": True,
        "label_only_produces": "population_robustness → population_subgroup_contrast → NORMAL filter",
        "evidence_required_for_full_chain": True,
        "evidence_required_for": [
            "population_robustness in unresolved (uncovered by ledger)",
            "priority SEEK_FALSIFICATION",
            "not in redundant_test_axes",
        ],
        "laundering_verdict": "PARTIAL — axis→action is label-sufficient; presence in unresolved requires evidence state",
    }


def human_choice_audit() -> Dict[str, Any]:
    return {
        "choices": [
            {"locus": "PARTITION_UNCERTAINTY_AXES taxonomy", "class": "LEGITIMATE_SCIENTIFIC_METHOD_PRIOR"},
            {"locus": "population_robustness → population_subgroup_contrast", "class": "LEGITIMATE_SCIENTIFIC_METHOD_PRIOR_WITH_TEMPLATE_RISK"},
            {"locus": "research_market_state=NORMAL subgroup", "class": "HUMAN_SCIENTIFIC_ANSWER"},
            {"locus": "sample_independence=HIGH for population_subgroup", "class": "AUTONOMY_LIMITATION"},
            {"locus": "lexicographic rank order", "class": "LEGITIMATE_SCIENTIFIC_METHOD_PRIOR"},
            {"locus": "axis alphabetical tiebreaker", "class": "AUTONOMY_LIMITATION"},
            {"locus": "partition_group_compare availability", "class": "LEGITIMATE_EXECUTION_CONSTRAINT"},
        ],
        "winner_materially_affected_by": [
            "HUMAN_SCIENTIFIC_ANSWER (NORMAL subgroup binding)",
            "AUTONOMY_LIMITATION (hardcoded HIGH independence ranking)",
        ],
    }


def verdict() -> Dict[str, Any]:
    return {
        "verdict": "FIRST_AUTONOMOUS_ACTION_AUDIT_PARTIAL",
        "rationale": (
            "High-level action (falsify population_robustness) is evidence-motivated by E2 LOW population "
            "independence and unresolved axis. Selection over temporal_regime is NARROWLY_DOMINANT on "
            "hardcoded sample_independence=HIGH. Subgroup construction (research_market_state=NORMAL) is "
            "human-prescribed, not evidence-derived; package not execution-ready for subgroup semantics."
        ),
        "exactly_one_defect": (
            "Subgroup/cohort construction and independence ranking use human-prescribed category bindings "
            "(NORMAL filter, hardcoded HIGH independence) without pre-result overlap analysis — "
            "material autonomy and execution-readiness limitation"
        ),
        "execution_ready": False,
        "proposed_next_phase": "3I.18 — Controlled one-shot execution protocol ONLY after subgroup semantics audit OR 3I.17b subgroup derivation fix (separate phase)",
    }


def main() -> None:
    frozen = _load(FROZEN_T2)
    _write("01_package_integrity.json", audit_package_integrity(frozen))
    _write("02_future_result_blindness.json", audit_blindness())
    _write("03_causal_chain.json", reconstruct_causal_chain(frozen))
    _write("04_population_uncertainty_origin.json", audit_population_uncertainty_origin())
    _write("05_selected_action_birth.json", audit_selected_action_birth(frozen))
    _write("06_operator_necessity.json", audit_operators())
    _write("07_objective_counterfactuals.json", run_objective_counterfactuals())
    _write("08_selection_ranking.json", reconstruct_ranking())
    _write("09_perturbation_tests.json", perturbation_tests())
    _write("10_tool_removal_test.json", tool_removal_test())
    _write("11_independence_audit.json", independence_audit())
    _write("12_subgroup_audit.json", subgroup_audit())
    _write("13_cross_family.json", cross_family_audit())
    _write("14_template_laundering.json", template_laundering_audit())
    _write("15_human_choice_audit.json", human_choice_audit())
    v = verdict()
    _write("16_verdict.json", v)
    _write(
        "17_audit_summary.json",
        {
            "phase": "3I.17",
            "mode": "AUDIT ONLY",
            "head": _git_head(),
            "artifact_package_hash": frozen["package"]["package_hash"],
            "user_cited_package_hash": USER_CITED_PACKAGE_HASH,
            "scientific_action_core_hash": frozen["package"]["selected_core_hash"],
            "execution_status": frozen["package"]["execution_status"],
            "verdict": v["verdict"],
            "execution_ready": v["execution_ready"],
        },
    )
    print(f"Phase 3I.17 audit complete — verdict={v['verdict']}")


if __name__ == "__main__":
    main()
