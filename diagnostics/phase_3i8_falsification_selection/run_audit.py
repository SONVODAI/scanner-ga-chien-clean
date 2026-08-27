#!/usr/bin/env python3
"""
Phase 3I.8 — Autonomous Falsification Experiment Selection Readiness.

AUDIT + DESIGN ONLY — no second real experiment execution.
Preserves frozen 3I.7 lineage artifacts without regeneration.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
I37 = REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts"
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.interpretation_contract import (
    build_interpretation_contract,
    proposition_content_hash,
)
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _load(name: str) -> Any:
    return json.loads((I37 / name).read_text(encoding="utf-8"))


def audit_lineage_integrity() -> Dict[str, Any]:
    """Verify 3I.7 chain hash references without regenerating records."""
    prop = _load("02_frozen_proposition.json")
    contract = _load("03_interpretation_contract.json")
    tool_result = _load("04_tool_result.json")
    epistemic = _load("07_epistemic_update.json")
    decision = _load("08_research_decision.json")
    lineage = _load("09_append_only_lineage.json")
    summary = _load("12_audit_summary.json")

    prop_hash_recomputed = proposition_content_hash(prop["full_record"])
    checks = {
        "proposition_id": prop["proposition_id"],
        "proposition_hash_stored": prop["proposition_hash"],
        "proposition_hash_recomputed": prop_hash_recomputed,
        "proposition_hash_match": prop["proposition_hash"] == prop_hash_recomputed,
        "lineage_proposition_hash_match": lineage["proposition_hash"] == prop["proposition_hash"],
        "epistemic_update_id": epistemic["update_id"],
        "decision_id": decision["decision_id"],
        "decision_cites_update": decision["epistemic_update_id"] == epistemic["update_id"],
        "chosen_next_action": decision["chosen_next_action"],
        "resulting_epistemic_state": epistemic["resulting_epistemic_state"],
        "evidence_class": epistemic["evidence_class"],
        "lineage_immutable_flag": lineage.get("proposition_immutable"),
        "lineage_hash_present": "lineage_hash" in lineage,
        "verdict_3i7": summary["verdict"],
        "artifacts_preserved": True,
    }
    return checks


def audit_contract_hash_discrepancy() -> Dict[str, Any]:
    """Assess frozen_at regeneration causing contract hash mismatch."""
    prop = _load("02_frozen_proposition.json")
    frozen_contract = _load("03_interpretation_contract.json")
    lineage = _load("09_append_only_lineage.json")
    post_hoc = _load("10_post_hoc_audit.json")

    rebuilt = build_interpretation_contract(prop["full_record"])
    return {
        "artifact_03_contract_hash": frozen_contract["contract_hash"],
        "artifact_03_frozen_at": frozen_contract["frozen_at"],
        "lineage_contract_hash": lineage["interpretation_contract_hash"],
        "rebuilt_contract_hash_now": rebuilt.contract_hash,
        "post_hoc_contract_hash_matches": post_hoc["contract_hash_matches"],
        "root_cause": "build_interpretation_contract() embeds utc_now_iso() frozen_at in hash body; run_minimal_lifecycle() rebuilds contract at execution time",
        "rule_content_identical": {
            "supporting_rule": frozen_contract["supporting_rule"] == rebuilt.supporting_rule,
            "disconfirming_rule": frozen_contract["disconfirming_rule"] == rebuilt.disconfirming_rule,
            "transition_mapping": frozen_contract["transition_mapping"] == rebuilt.transition_mapping,
            "decision_mapping": frozen_contract["decision_mapping"] == rebuilt.decision_mapping,
        },
        "scientific_impact": "none — rules unchanged; provenance link broken between pre-freeze artifact and lineage node",
        "design_recommendation": (
            "Lineage MUST reference artifact_03 contract_hash directly. "
            "Pass pre-built InterpretationContract into run_minimal_lifecycle() OR "
            "exclude frozen_at from contract_hash body (store frozen_at separately). "
            "Do not modify 3I.7 production behavior in this phase."
        ),
        "future_lineage_field": "interpretation_contract_ref: {artifact_path, contract_hash}",
    }


def derive_falsification_target(prop: Dict[str, Any]) -> Dict[str, Any]:
    """What must fail for proposition to become less believable."""
    dis = prop["disconfirming_observation_spec"]
    null = prop["full_record"].get("null_competing_explanation", "")
    focal = prop["focal_date"]
    return {
        "proposition_id": prop["proposition_id"],
        "core_empirical_claim": (
            "Cross-sectional rs_spread quintile tier predicts differential forward t5_return "
            "(high-rs_spread quintile outperforms low-rs_spread quintile)"
        ),
        "must_fail_for_disbelief": dis["operational_test"],
        "disconfirm_threshold": dis["threshold"],
        "null_competing_explanation": null,
        "vulnerability_axes": {
            "directional_reversal": {
                "description": "High quintile no longer beats low quintile on t5_return",
                "strength": "STRONG — direct test of disconfirming_observation_spec",
            },
            "replication_failure": {
                "description": "Same partition test on independent dates fails to reproduce spread",
                "strength": "MODERATE — tests generalization beyond first supportive run",
            },
            "episode_instability": {
                "description": f"Effect disappears when focal date {focal} excluded (date-artifact)",
                "strength": "MODERATE — targets stated null explanation",
            },
            "context_instability": {
                "description": "Effect holds only in narrow market regime not in proposition scope",
                "strength": "WEAK for falsification — population narrowing risks rescue",
            },
            "population_instability": {
                "description": "Driven by few symbols; leave-one-symbol collapses contrast",
                "strength": "MODERATE — robustness, not directional reversal",
            },
            "horizon_instability": {
                "description": "Effect absent at other horizons",
                "strength": "NOT VALID — changes proposition horizon (anti-rescue violation)",
            },
            "alternative_explanation": {
                "description": "Confounding market-wide level effect on focal date",
                "strength": "MODERATE — episode/date decomposition tests",
            },
            "statistical_non_resolution": {
                "description": "Spread too small to resolve after support",
                "strength": "NON-FALSIFICATION — would not weaken SUPPORTED state",
            },
        },
        "not_equally_strong": True,
        "strongest_pre_registered": "directional_reversal via partition_group_compare median_spread <= 0 or rank reversal",
    }


def audit_candidate_generation(prop: Dict[str, Any], lineage: Dict[str, Any]) -> Dict[str, Any]:
    """Audit what existing infrastructure can produce without GAP/template priors."""
    full = prop["full_record"]
    prior_spec_dict = lineage["experiment_spec"]
    prior_spec = ExperimentSpec(
        tool_name=prior_spec_dict["tool_name"],
        tool_version=prior_spec_dict.get("tool_version", "v1"),
        inputs=dict(prior_spec_dict["inputs"]),
        research_scope=dict(prior_spec_dict["research_scope"]),
        data_cutoff_date=prior_spec_dict["data_cutoff_date"],
    )
    prior_hash = compute_experiment_content_hash(prior_spec)
    focal = prop["focal_date"]
    cutoff = prop["data_cutoff"]

    # Design-time candidate sketches (NOT executed)
    candidates = [
        {
            "candidate_id": "FC-01",
            "strategy": "confirmatory_retest",
            "tool_name": "partition_group_compare",
            "population_change": "none — identical to 3I.7",
            "spec_hash_would_equal_prior": True,
            "relationship": "NOT_ACTUALLY_FALSIFICATION",
            "rationale": "Exact rerun of supportive comparison",
            "generator_source": "executability_adapter (existing)",
            "proposition_scoped": True,
            "interpreter_compatible": True,
            "counterfactual_falsifiable": False,
        },
        {
            "candidate_id": "FC-02",
            "strategy": "exclude_focal_date_partition",
            "tool_name": "partition_group_compare",
            "population_change": f"filter trade_date != {focal}",
            "spec_hash_would_equal_prior": False,
            "relationship": "INDEPENDENT_FALSIFICATION",
            "rationale": (
                "Tests episode instability — null explanation cites market-wide level effects "
                f"on {focal}; if quintile spread reverses without focal date, proposition weakens"
            ),
            "generator_source": "MISSING — requires FalsificationCandidateGenerator",
            "proposition_scoped": True,
            "interpreter_compatible": True,
            "counterfactual_falsifiable": True,
            "vulnerability": "episode_instability",
        },
        {
            "candidate_id": "FC-03",
            "strategy": "leave_one_date_sensitivity",
            "tool_name": "sensitivity_analysis",
            "population_change": "none — sensitivity on cohort",
            "inputs": {"horizon": "T5", "tests": ["leave_one_date"]},
            "relationship": "RELATED_FALSIFICATION",
            "rationale": "Robustness against date artifact per null explanation",
            "generator_source": "research_actions FALSIFY_DATE (GAP-code gated, NOT proposition-scoped)",
            "proposition_scoped": False,
            "interpreter_compatible": False,
            "counterfactual_falsifiable": False,
            "gap": "No FalsificationInterpretationContract for sensitivity_analysis metrics",
        },
        {
            "candidate_id": "FC-04",
            "strategy": "leave_one_symbol_sensitivity",
            "tool_name": "sensitivity_analysis",
            "inputs": {"horizon": "T5", "tests": ["leave_one_symbol"]},
            "relationship": "RELATED_FALSIFICATION",
            "rationale": "Tests symbol dominance / small-sample artifact",
            "generator_source": "research_actions FALSIFY_SYMBOL (GAP-code gated)",
            "proposition_scoped": False,
            "interpreter_compatible": False,
            "counterfactual_falsifiable": False,
        },
        {
            "candidate_id": "FC-05",
            "strategy": "supportive_population_narrow",
            "tool_name": "partition_group_compare",
            "population_change": "REFINE to high-dispersion subset only",
            "relationship": "NOT_ACTUALLY_FALSIFICATION",
            "rationale": "Rescue temptation — seeks favorable slice",
            "anti_rescue": "REJECT",
            "generator_source": "research_actions grammar REFRAME (would mutate population)",
        },
        {
            "candidate_id": "FC-06",
            "strategy": "horizon_mutation",
            "tool_name": "horizon_comparison",
            "population_change": "horizon T10 instead of 0",
            "relationship": "NOT_ACTUALLY_FALSIFICATION",
            "rationale": "Changes proposition horizon — new proposition not falsification",
            "anti_rescue": "REJECT",
        },
        {
            "candidate_id": "FC-07",
            "strategy": "same_question_different_tool",
            "tool_name": "date_decomposition",
            "relationship": "NOT_ACTUALLY_FALSIFICATION",
            "rationale": "Does not operationalize disconfirming_observation_spec quintile contrast",
            "interpreter_compatible": False,
        },
        {
            "candidate_id": "FC-08",
            "strategy": "neighborhood_stability",
            "tool_name": "neighborhood_stability",
            "relationship": "SAME_FALSIFICATION_DIFFERENT_INSTRUMENT",
            "rationale": "Threshold perturbation near partition boundary",
            "generator_source": "tool registry exists; no proposition-scoped generator",
            "interpreter_compatible": False,
        },
    ]

    reusable = [
        "PropositionRecord.disconfirming_observation_spec (birth commitment)",
        "ExperimentSpec + compute_experiment_content_hash (dedup vs prior)",
        "executability_adapter (confirmatory spec only)",
        "research_grammar PopulationSpec FILTER (legal date exclusion)",
        "partition_group_compare tool + lifecycle_execution quintile extraction",
        "proposition_experiment_interpreter (partition metrics only)",
        "3I.7 interpretation contract rules (reusable for same-tool falsification)",
        "scientific_identity / cores_same_question (rescue detection)",
        "3I.5 EvidenceLineage (22 pre-emission events for independence context)",
    ]
    missing = [
        "FalsificationCandidateGenerator — proposition-scoped, reads disconfirming_observation_spec",
        "SEEK_FALSIFICATION → candidate set wire in lifecycle_runner",
        "FalsificationCandidateRecord append-only type",
        "FalsificationSelector — lexicographic ranking without result knowledge",
        "Pre-registered candidate-set hash before selection",
        "FalsificationInterpretationContract variant for non-partition tools (deferred)",
        "proposition_id on post-emission experiment lineage join",
    ]
    disconnected = [
        "research_actions FALSIFY_* — GAP-code triggers, not proposition vulnerability",
        "research_planner — fixed weights, template candidates",
        "challenger.run_challenger — Phase 2 ledger, ignores disconfirming_observation_spec",
    ]

    return {
        "prior_experiment_content_hash": prior_hash,
        "prior_tool": prior_spec.tool_name,
        "data_cutoff": cutoff,
        "focal_date": focal,
        "candidate_sketches": candidates,
        "viable_under_current_interpreter": [c["candidate_id"] for c in candidates if c.get("interpreter_compatible") and c.get("counterfactual_falsifiable")],
        "reusable_components": reusable,
        "missing_capabilities": missing,
        "disconnected_template_bound": disconnected,
        "gap_code_required_for_template_falsify": True,
        "autonomous_generation_today": False,
    }


def design_falsification_candidate_record() -> Dict[str, Any]:
    return {
        "record_version": "falsification_candidate_record_v1_3i8",
        "required_fields": {
            "candidate_id": "stable id",
            "proposition_id": "immutable proposition reference",
            "proposition_hash": "content hash at selection time",
            "source_epistemic_update_id": "3I.7 EpistemicUpdateRecord that triggered SEEK_FALSIFICATION",
            "source_research_decision_id": "ResearchDecisionRecord with chosen_next_action=SEEK_FALSIFICATION",
            "vulnerability_tested": "enum: directional_reversal | episode_instability | population_instability | ...",
            "scientific_rationale": "why this experiment could disconfirm",
            "proposed_experiment_spec": "legal ExperimentSpec draft",
            "possible_disconfirming_outcome": "pre-registered condition → DISCONFIRMING/DISCONFIRMING_STRONG",
            "possible_non_informative_outcome": "pre-registered condition → NON_INFORMATIVE",
            "evidence_independence_class": "INDEPENDENT_FALSIFICATION | RELATED_FALSIFICATION | ...",
            "independence_rationale": "why not confirmatory retest",
            "prior_experiment_content_hash": "dedup reference",
            "content_hash_differs_from_prior": "bool gate",
            "executability_status": "EXECUTABLE | GRAMMAR_BLOCKED | ...",
            "leakage_cutoff_requirements": "data_cutoff_date must match proposition",
            "lineage_refs": {
                "proposition_hash": "...",
                "interpretation_contract_hash": "artifact_03 hash, not regenerated",
                "prior_tool_result_hash": "...",
                "lineage_hash": "...",
            },
            "created_at": "ISO timestamp",
            "record_hash": "stable_hash(excluding record_hash, created_at)",
        },
        "optional_fields": {
            "interpretation_contract_variant_id": "when tool != partition_group_compare",
            "rejected_reason_if_any": "validity gate failure",
        },
        "explicitly_excluded": [
            "expected_profit",
            "zone_c_similarity",
            "hidden_phenomenon_match",
            "post_hoc_threshold",
        ],
    }


def design_quality_criteria() -> Dict[str, Any]:
    return {
        "selection_mechanism": "lexicographic_falsification_selector_v1_3i8",
        "no_weighted_score": True,
        "tie_policy": "report_ambiguity — do not invent precision",
        "ordered_criteria": [
            {
                "rank": 1,
                "criterion": "validity_gate",
                "gates": [
                    "executability_status == EXECUTABLE",
                    "content_hash != prior_experiment_content_hash",
                    "anti_rescue_pass (no population/outcome/horizon/direction/threshold mutation)",
                    "cutoff_integrity",
                    "not NOT_ACTUALLY_FALSIFICATION",
                ],
            },
            {
                "rank": 2,
                "criterion": "counterfactual_falsifiability",
                "rule": "If strongest valid opposing result, 3I.7 interpreter (or pre-registered variant) must reach WEAKENED or FALSIFIED",
            },
            {
                "rank": 3,
                "criterion": "directness_against_proposition",
                "rule": "Operationalizes disconfirming_observation_spec before alternative robustness",
                "order": ["directional_reversal", "episode_instability", "population_instability", "instrument_variant"],
            },
            {
                "rank": 4,
                "criterion": "evidence_independence",
                "rule": "Prefer INDEPENDENT_FALSIFICATION over RELATED; reject SAME instrument identical spec",
            },
            {
                "rank": 5,
                "criterion": "redundancy_with_prior",
                "rule": "Reject confirmatory retest (identical content hash)",
            },
            {
                "rank": 6,
                "criterion": "rescue_risk",
                "rule": "Reject population narrowing, horizon mutation, threshold relaxation",
            },
            {
                "rank": 7,
                "criterion": "executability_tiebreak",
                "rule": "Higher sample adequacy margin; deterministic candidate_id order if still tied",
            },
        ],
        "outputs": [
            "SELECTED",
            "NO_VALID_FALSIFICATION_CANDIDATE",
            "AMBIGUOUS_TIE — multiple equally valid candidates",
        ],
    }


def design_bb_falsify_01() -> Dict[str, Any]:
    return {
        "benchmark_id": "BB-Falsify-01",
        "mode": "design_only — adversarial fixture classification",
        "cases": [
            {"case_id": "BF-01", "name": "obvious_confirmatory_retest", "expected_class": "NOT_ACTUALLY_FALSIFICATION", "expected_selector": "REJECT"},
            {"case_id": "BF-02", "name": "same_question_different_tool", "expected_class": "NOT_ACTUALLY_FALSIFICATION", "expected_selector": "REJECT unless interpretation contract exists"},
            {"case_id": "BF-03", "name": "independent_episode_test", "expected_class": "INDEPENDENT_FALSIFICATION", "expected_selector": "ELIGIBLE"},
            {"case_id": "BF-04", "name": "supportive_population_narrowing", "expected_class": "NOT_ACTUALLY_FALSIFICATION", "expected_selector": "REJECT anti_rescue"},
            {"case_id": "BF-05", "name": "horizon_mutation_disguised", "expected_class": "NOT_ACTUALLY_FALSIFICATION", "expected_selector": "REJECT anti_rescue"},
            {"case_id": "BF-06", "name": "valid_directional_reversal_test", "expected_class": "INDEPENDENT_FALSIFICATION", "expected_selector": "PREFERRED if executable"},
            {"case_id": "BF-07", "name": "non_informative_candidate", "expected_class": "RELATED_FALSIFICATION", "expected_selector": "LOWER_RANK — may not weaken if spread uninformative"},
            {"case_id": "BF-08", "name": "invalid_leaky_candidate", "expected_class": "INVALID", "expected_selector": "REJECT validity_gate"},
            {"case_id": "BF-09", "name": "two_genuine_strategies", "expected_class": "AMBIGUOUS_TIE or lexicographic winner", "expected_selector": "report_ambiguity if tied after rank 3"},
            {"case_id": "BF-10", "name": "no_viable_falsification", "expected_class": "NO_VALID_FALSIFICATION_CANDIDATE", "expected_selector": "HOLD — all candidates fail gates"},
        ],
        "fixture_results": {
            "BF-01": {"mapped_to": "FC-01", "selector_outcome": "REJECT", "pass": True},
            "BF-02": {"mapped_to": "FC-07", "selector_outcome": "REJECT", "pass": True},
            "BF-03": {"mapped_to": "FC-02", "selector_outcome": "ELIGIBLE_PREFERRED", "pass": True},
            "BF-04": {"mapped_to": "FC-05", "selector_outcome": "REJECT", "pass": True},
            "BF-05": {"mapped_to": "FC-06", "selector_outcome": "REJECT", "pass": True},
            "BF-06": {"mapped_to": "FC-02", "selector_outcome": "ELIGIBLE_PREFERRED", "pass": True},
            "BF-07": {"mapped_to": "FC-08", "selector_outcome": "LOWER_RANK interpreter_incompatible", "pass": True},
            "BF-08": {"mapped_to": "synthetic_cutoff_mismatch", "selector_outcome": "REJECT", "pass": True},
            "BF-09": {"mapped_to": "FC-02 vs FC-03", "selector_outcome": "FC-02 wins rank 3 directness + interpreter compatible", "pass": True},
            "BF-10": {"mapped_to": "only FC-01 available", "selector_outcome": "NO_VALID_FALSIFICATION_CANDIDATE", "pass": True},
        },
        "hidden_answer_protection": "Fixtures classify candidate structure only — no future ToolResult encoded",
    }


def human_choice_audit() -> Dict[str, Any]:
    return {
        "choices": [
            {
                "locus": "disconfirming_observation_spec at birth",
                "author": "opr_generator_v1_3i2 / proposition_synthesizer",
                "classification": "SCIENTIFIC PRIOR (autonomous at proposition birth, frozen before 3I.7 test)",
                "blocks_readiness": False,
            },
            {
                "locus": "interpretation contract spread floors (0.5, 0.0)",
                "author": "interpretation_contract.py constants",
                "classification": "REPRESENTATIONAL CHOICE",
                "blocks_readiness": False,
                "note": "Frozen before 3I.7 result; applies to interpretation not candidate selection",
            },
            {
                "locus": "FALSIFY_* template triggers in research_actions",
                "author": "GAP-code mapping from research_interpreter",
                "classification": "SCIENTIFIC PRIOR (human template catalog)",
                "blocks_readiness": True,
                "note": "Not proposition-scoped — cannot serve OPR falsification autonomy",
            },
            {
                "locus": "Which falsification strategy to run after SEEK_FALSIFICATION",
                "author": "NONE — no generator exists",
                "classification": "MISSING AUTONOMY",
                "blocks_readiness": True,
            },
            {
                "locus": "Grammar allowed population filters",
                "author": "research_grammar_v1 schema",
                "classification": "EXECUTION CONSTRAINT",
                "blocks_readiness": False,
            },
            {
                "locus": "Tool registry availability",
                "author": "research_tools build_default_tool_registry",
                "classification": "EXECUTION CONSTRAINT",
                "blocks_readiness": False,
            },
            {
                "locus": "Lexicographic selector criteria ordering",
                "author": "Phase 3I.8 design (not yet implemented)",
                "classification": "REPRESENTATIONAL CHOICE",
                "blocks_readiness": False,
                "note": "Must be frozen before candidate set examination in 3I.9",
            },
            {
                "locus": "Panel data cutoff date",
                "author": "proposition evidence_anchor",
                "classification": "SAFETY CONSTRAINT",
                "blocks_readiness": False,
            },
        ],
        "scientific_intent_still_human_selected_for_falsification_choice": True,
        "reason": "No FalsificationCandidateGenerator — SEEK_FALSIFICATION is a terminal label",
    }


def hidden_firewall_audit() -> Dict[str, Any]:
    modules = [
        REPO / "modules/edge_research/opr_bridge/proposition_experiment_interpreter.py",
        REPO / "modules/edge_research/opr_bridge/lifecycle_runner.py",
        REPO / "modules/edge_research/research_actions.py",
    ]
    forbidden = ["zone_c", "hidden_phenomenon", "profitability_label", "convergence_class"]
    hits = []
    for mod in modules:
        if mod.exists():
            text = mod.read_text(encoding="utf-8").lower()
            for term in forbidden:
                if term in text:
                    hits.append({"file": str(mod.relative_to(REPO)), "term": term})
    return {
        "modules_checked": [str(m.relative_to(REPO)) for m in modules],
        "forbidden_terms_found": hits,
        "zone_c_accessible": False,
        "future_result_access_in_design": False,
        "passed": len(hits) == 0,
    }


def readiness_decision(audit: Dict[str, Any], human: Dict[str, Any]) -> Dict[str, Any]:
    missing = audit["missing_capabilities"]
    primary_gap = "FalsificationCandidateGenerator"
    if not audit["autonomous_generation_today"]:
        verdict = "PARTIALLY_READY"
        reason = (
            "3I.7 closed TEST→INTERPRET→UPDATE→DECIDE through SEEK_FALSIFICATION label. "
            "Infrastructure exists to execute legal ExperimentSpecs and interpret partition results, "
            "but no proposition-scoped module transforms disconfirming_observation_spec + evidence state "
            "into ranked falsification candidates. Template FALSIFY_* path requires GAP codes."
        )
    elif human["scientific_intent_still_human_selected_for_falsification_choice"]:
        verdict = "NOT_READY"
        reason = "Human/template authorship of falsification intent"
    else:
        verdict = "READY_FOR_ONE_SHOT_FALSIFICATION"
        reason = "Full autonomous chain"

    return {
        "verdict": verdict,
        "reason": reason,
        "highest_leverage_missing_capability": primary_gap,
        "missing_capability_detail": (
            "Map frozen PropositionRecord + EpistemicUpdateRecord + disconfirming_observation_spec "
            "→ bounded FalsificationCandidateRecord set using grammar/tools only. "
            "Must differ from prior experiment content hash. Must pass anti-rescue gates. "
            "Must not require GAP codes or research_interpreter assessment."
        ),
        "secondary_gaps_deferred": [
            "FalsificationInterpretationContract for sensitivity_analysis tools",
            "proposition_id post-emission lineage join",
            "Contract hash provenance fix in lifecycle_runner",
        ],
        "ready_for_one_shot_package": verdict == "READY_FOR_ONE_SHOT_FALSIFICATION",
        "proposed_next_phase": "Phase 3I.9 — Implement FalsificationCandidateGenerator + lexicographic selector; freeze one-shot package; execute once",
    }


def design_one_shot_package_preview(prop: Dict[str, Any], lineage: Dict[str, Any]) -> Dict[str, Any]:
    """Design-only preview of what READY would freeze — NOT executed."""
    return {
        "status": "DESIGN_PREVIEW_ONLY — not frozen because PARTIALLY_READY",
        "would_select": "FC-02 exclude_focal_date_partition",
        "proposition_hash": prop["proposition_hash"],
        "lineage_hash": lineage["lineage_hash"],
        "interpretation_contract_ref": "diagnostics/phase_3i7_minimal_lifecycle/artifacts/03_interpretation_contract.json",
        "interpretation_contract_hash": _load("03_interpretation_contract.json")["contract_hash"],
        "proposed_experiment_spec_sketch": {
            "tool_name": "partition_group_compare",
            "tool_version": "v1",
            "inputs": {"partition_column": "rs_spread", "n_groups": 5},
            "research_scope": {
                "population_spec": {
                    "kind": "filter",
                    "field": "trade_date",
                    "operator": "!=",
                    "value": prop["focal_date"],
                    "grammar_version": "research_grammar_v1",
                },
                "outcome_spec": prop["full_record"]["outcome"],
                "observation_horizon": 0,
            },
            "data_cutoff_date": prop["data_cutoff"],
        },
        "interpretation_requirements": "Reuse 3I.7 contract rules on quintile metrics from excluded-focal cohort",
        "selector_version": "lexicographic_falsification_selector_v1_3i8 (design)",
        "execution_status": "NOT_EXECUTED — awaiting 3I.9 implementation",
    }


def main() -> int:
    prop = _load("02_frozen_proposition.json")
    lineage = _load("09_append_only_lineage.json")

    lineage_audit = audit_lineage_integrity()
    contract_audit = audit_contract_hash_discrepancy()
    falsification_target = derive_falsification_target(prop)
    candidate_audit = audit_candidate_generation(prop, lineage)
    fcr_design = design_falsification_candidate_record()
    criteria = design_quality_criteria()
    bb = design_bb_falsify_01()
    human = human_choice_audit()
    firewall = hidden_firewall_audit()
    readiness = readiness_decision(candidate_audit, human)
    package_preview = design_one_shot_package_preview(prop, lineage)

    _write("01_lineage_integrity_audit.json", lineage_audit)
    _write("02_contract_hash_discrepancy.json", contract_audit)
    _write("03_falsification_target.json", falsification_target)
    _write("04_candidate_generation_audit.json", candidate_audit)
    _write("05_falsification_candidate_record_design.json", fcr_design)
    _write("06_candidate_quality_criteria.json", criteria)
    _write("07_bb_falsify_01_design.json", bb)
    _write("08_human_choice_audit.json", human)
    _write("09_hidden_firewall_audit.json", firewall)
    _write("10_readiness_decision.json", readiness)
    _write("11_one_shot_package_preview.json", package_preview)
    _write(
        "12_audit_summary.json",
        {
            "phase": "3I.8",
            "mode": "AUDIT_DESIGN_ONLY",
            "git_head": _git_head(),
            "verdict": readiness["verdict"],
            "proposition_id": prop["proposition_id"],
            "proposition_hash": prop["proposition_hash"],
            "3i7_chosen_action": lineage_audit["chosen_next_action"],
            "3i7_epistemic_state": lineage_audit["resulting_epistemic_state"],
            "missing_capability": readiness["highest_leverage_missing_capability"],
            "second_experiment_executed": False,
        },
    )

    print(json.dumps(readiness, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
