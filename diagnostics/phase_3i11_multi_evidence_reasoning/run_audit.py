#!/usr/bin/env python3
"""
Phase 3I.11 — Multi-Evidence Epistemic Reasoning Readiness.

AUDIT + DESIGN ONLY — no multi-evidence engine implementation, no new experiments.
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
I39 = REPO / "diagnostics/phase_3i9_falsification_selection/artifacts"
I310 = REPO / "diagnostics/phase_3i10_falsification_execution/artifacts"

sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.interpretation_contract import proposition_content_hash
from modules.edge_research.research_state import ExperimentSpec, compute_experiment_content_hash


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


def audit_lineage_integrity() -> Dict[str, Any]:
    prop_wrap = _load(I37 / "02_frozen_proposition.json")
    prop = prop_wrap["full_record"]
    e1_update = _load(I37 / "07_epistemic_update.json")
    e1_decision = _load(I37 / "08_research_decision.json")
    lineage_37 = _load(I37 / "09_append_only_lineage.json")
    package = _load(I39 / "09_one_shot_package.json")
    candidate = _load(I39 / "07_real_candidate_set.json")["candidates"][0]
    e2_update = _load(I310 / "05_epistemic_update.json")
    e2_decision = _load(I310 / "06_research_decision.json")

    prop_hash = proposition_content_hash(prop)
    spec1 = lineage_37["experiment_spec"]
    spec1_hash = compute_experiment_content_hash(ExperimentSpec.from_dict({**spec1, "tool_version": spec1.get("tool_version", "v1")}))

    chain = [
        {"node": "PropositionRecord", "id": prop["proposition_id"], "hash": prop_hash},
        {"node": "ExperimentSpec_1", "ref": "lifecycle_real_001", "hash": spec1_hash},
        {"node": "EpistemicUpdate_1", "id": e1_update["update_id"], "class": e1_update["evidence_class"], "state": e1_update["resulting_epistemic_state"]},
        {"node": "ResearchDecision_1", "id": e1_decision["decision_id"], "action": e1_decision["chosen_next_action"]},
        {"node": "FalsificationCandidate", "id": candidate["candidate_id"]},
        {"node": "OneShotPackage", "hash": package["package_hash"], "status": package["execution_status"]},
        {"node": "ExperimentSpec_2", "hash": package["selected_experiment_content_hash"]},
        {"node": "EpistemicUpdate_2", "id": e2_update["update_id"], "class": e2_update["evidence_class"], "state": e2_update["resulting_epistemic_state"]},
        {"node": "ResearchDecision_2", "id": e2_decision["decision_id"], "action": e2_decision["chosen_next_action"]},
    ]

    return {
        "proposition_hash": prop_hash,
        "proposition_hash_recomputed_match": prop_hash == prop_wrap["proposition_hash"],
        "lineage_37_hash": lineage_37["lineage_hash"],
        "package_hash": package["package_hash"],
        "evidence_events": 2,
        "chain": chain,
        "history_summary": "HYPOTHESIS→SUPPORTED→SEEK_FALSIFICATION→holdout SUPPORTING→SUPPORTED→SEEK_FALSIFICATION",
        "passed": prop_hash == prop_wrap["proposition_hash"],
    }


def audit_resolve_cohort_fix() -> Dict[str, Any]:
    return {
        "change_summary": "resolve_cohort now applies research_scope.population_spec via apply_population_spec",
        "commit_phase": "3I.10",
        "questions": {
            "A_execution_correctness_only": {
                "answer": True,
                "rationale": (
                    "Frozen 3I.9 ExperimentSpec already encoded holdout population_spec; "
                    "3I.9 executability checks used apply_population_spec but tool execution path ignored it. "
                    "Fix honors pre-frozen spec — no new scientific choice."
                ),
            },
            "B_new_scientific_choice_after_result": {
                "answer": False,
                "rationale": "Patch landed before accepted 3I.10 artifacts; candidate/package frozen in 3I.9 pre-result.",
            },
            "C_holdout_cohort_preserved": {
                "answer": True,
                "rationale": "43 holdout dates excluding 2026-08-02 unchanged; post-fix cohort n=5964 vs pre-fix erroneous n=6106.",
            },
            "D_changed_selection_or_interpretation": {
                "answer": False,
                "rationale": "Selection frozen in 3I.9; interpretation contract artifact 03 unchanged.",
            },
            "E_toolresult_unavailable_before_fix": {
                "answer": "Partial — execution ran but cohort was wrong without filter; not absence of ToolResult.",
                "note": "Pre-fix path would have duplicated full-panel cohort (PROCESS_CONTAMINATION risk); fixed before final verdict artifacts.",
            },
        },
        "classification": "EXECUTION_CORRECTNESS_ONLY",
        "contamination_in_accepted_run": False,
        "historical_note": (
            "Early 3I.10 development run without filter produced metrics identical to Evidence 1; "
            "not used as accepted AUTONOMOUS_FALSIFICATION_PASS artifacts."
        ),
        "metric_evidence": {
            "evidence_1_sample_size": 6106,
            "evidence_2_sample_size_correct": 5964,
            "evidence_2_spread": 2.0887694594595527,
            "evidence_1_spread": 2.351875539446755,
        },
    }


def design_evidence_ledger() -> Dict[str, Any]:
    return {
        "record_version": "evidence_ledger_entry_v1_3i11",
        "principle": "Raw append-only EpistemicUpdateRecords remain authoritative; ledger entries index them.",
        "required_fields_per_event": [
            "ledger_entry_id",
            "proposition_id",
            "epistemic_update_id",
            "experiment_content_hash",
            "tool_result_hash",
            "evidence_class",
            "relationship_to_proposition",
            "relationship_to_prior_evidence",
            "population_spec",
            "outcome_spec",
            "observation_horizon",
            "feature_semantics",
            "cohort_episode_scope",
            "data_cutoff",
            "sample_size",
            "effect_direction",
            "effect_magnitude",
            "validity_status",
            "independence_profile",
            "contradiction_status",
            "information_contribution",
            "provenance_hashes",
        ],
        "no_scalar_confidence": True,
        "authoritative_source": "EpistemicUpdateRecord + ExperimentSpec + ToolResult refs",
    }


def design_evidence_relationship_taxonomy() -> Dict[str, Any]:
    return {
        "taxonomy_version": "evidence_relationship_v1_3i11",
        "classes": {
            "EXACT_REPLICATION": "Identical experiment content hash",
            "REPRESENTATION_REPLICATION": "Same scientific question, different instrument only",
            "PARTIAL_REPLICATION": "Overlapping cohort/measurement with subset change",
            "INDEPENDENT_REPLICATION": "New independent sample/episode with same proposition semantics",
            "INDEPENDENT_FALSIFICATION": "Test designed to disconfirm; independent cohort",
            "RELATED_EVIDENCE": "Same proposition, overlapping uncertainty dimension",
            "CONTRADICTORY_EVIDENCE": "Valid opposing directional implications",
            "NON_INFORMATIVE": "Valid but non-resolving",
            "INVALID": "Failed validity gate",
        },
        "independence_not_from": ["tool_change_alone", "date_label_alone", "representation_change_alone"],
        "reuse": ["3H research_line_relationship", "3I.9 evidence_independence_class", "compute_experiment_content_hash"],
    }


def design_independence_profile() -> Dict[str, Any]:
    return {
        "record_version": "evidence_independence_profile_v1_3i11",
        "dimensions": {
            "sample_independence": "distinct row cohort vs prior experiment",
            "episode_independence": "distinct trade_date sets / motivating episode exclusion",
            "population_independence": "distinct population_spec semantics",
            "temporal_independence": "non-overlapping time windows",
            "measurement_independence": "distinct outcome/feature/metric formulation",
            "methodological_independence": "distinct tool operationalizing different test",
            "semantic_independence": "distinct uncertainty dimension tested (3H cores)",
        },
        "not_interchangeable": True,
        "aggregate_rule": "Report per-dimension; no single yes/no unless all relevant dimensions pass",
    }


def design_multi_evidence_state() -> Dict[str, Any]:
    return {
        "existing_states_sufficient": True,
        "recommended_additions": [],
        "note": "Prefer CONFLICTED + rich ledger over new states like DOUBLY_SUPPORTED",
        "missing_state": "HOLD_PROVISIONALLY is a ResearchPriorityDecision not epistemic state",
        "current_vocabulary": [
            "PROPOSED", "UNDER_TEST", "SUPPORTED", "WEAKENED", "CONFLICTED",
            "FALSIFIED", "UNRESOLVED", "ABANDONED", "INSUFFICIENT_EVIDENCE",
        ],
    }


def design_prior_state_reasoning() -> Dict[str, Any]:
    return {
        "current_limitation": "3I.7 transition_mapping is evidence-absolute (evidence_class → resulting_state)",
        "design": "prior_state_conditioned_transition_table",
        "examples": {
            "SUPPORTED + independent SUPPORTING": {
                "requires": ["independence_profile episode_or_sample high", "same uncertainty dimension or new"],
                "possible_outcomes": ["SUPPORTED unchanged", "CONFLICTED if contradicts hidden conflict"],
                "not": "auto-upgrade confidence",
            },
            "SUPPORTED + independent DISCONFIRMING": {
                "requires": ["valid disconfirming evidence", "independence from prior support cohort"],
                "possible_outcomes": ["WEAKENED", "CONFLICTED", "FALSIFIED if strong"],
            },
            "SUPPORTED + strong CONTRADICTORY": {"outcome": "CONFLICTED"},
            "WEAKENED + independent SUPPORTING": {"outcome": "SUPPORTED or CONFLICTED — depends on conflict structure"},
            "CONFLICTED + additional contradiction": {"outcome": "CONFLICTED persists; seek resolution experiment"},
            "UNRESOLVED + informative": {"outcome": "state per evidence class"},
            "FALSIFIED + later SUPPORTING": {"outcome": "FALSIFIED preserved; flag anomaly, no auto-resurrection"},
        },
        "preregister_before_synthesis": True,
    }


def design_unresolved_uncertainty() -> Dict[str, Any]:
    return {
        "record_version": "unresolved_uncertainty_v1_3i11",
        "dimensions_examples": [
            "episode_robustness", "temporal_robustness", "population_robustness",
            "horizon_robustness", "effect_stability", "concentration_dominance",
            "alternative_explanations", "measurement_robustness", "regime_dependence",
            "statistical_resolution",
        ],
        "derivation": "From proposition canonical core + disconfirming_observation_spec + ledger coverage map",
        "representation": "Set of uncovered dimensions with executability hints — not scalar",
    }


def design_information_contribution() -> Dict[str, Any]:
    return {
        "mechanism": "lexicographic_marginal_information_v1_3i11",
        "ordered_checks": [
            "covers_new_uncertainty_dimension",
            "increases_independence_on_untested_dimension",
            "resolves_existing_contradiction",
            "robustness_gain_non_redundant",
            "falsification_opportunity_unexhausted",
            "evidence_saturation_not_reached",
        ],
        "rejects": ["experiment_count", "majority_vote", "N_confirmations_rule"],
    }


def design_saturation() -> Dict[str, Any]:
    return {
        "record_version": "evidence_saturation_assessment_v1_3i11",
        "forbidden_rules": ["after_2_supports_stop", "after_3_tests_stop"],
        "derived_from": [
            "uncertainty_dimension_coverage_complete",
            "diminishing_independence_between_new_experiments",
            "no_unresolved_contradictions",
            "no_executable_high_value_falsification_remaining",
            "marginal_information_below_threshold",
        ],
        "outputs": ["NOT_SATURATED", "PARTIALLY_SATURATED", "SATURATED_FOR_CURRENT_UNCERTAINTY"],
        "allows_silence": True,
    }


def design_falsification_sufficiency() -> Dict[str, Any]:
    return {
        "problem": "3I.7 decision_mapping always SEEK_FALSIFICATION on SUPPORTING regardless of ledger",
        "valid_next_actions": [
            "SEEK_FALSIFICATION", "SEEK_REPLICATION", "SEEK_CONTRADICTION_RESOLUTION",
            "HOLD_PROVISIONALLY", "HOLD_UNRESOLVED", "ABANDON",
        ],
        "hold_provisionally_definition": (
            "Evidence sufficient to preserve proposition as research-usable; "
            "marginal experiment value lower than other frontier questions. NOT proven true."
        ),
        "falsification_no_longer_highest_value_when": [
            "episode_robustness dimension covered by independent holdout",
            "remaining falsification axes redundant with ledger",
            "saturation assessment SATURATED_FOR_CURRENT_UNCERTAINTY",
            "no executable counterexample axis with marginal information",
        ],
    }


def design_research_priority() -> Dict[str, Any]:
    return {
        "distinction": "epistemic_uncertainty vs research_priority",
        "existing_infrastructure": {
            "research_frontier": "modules/edge_research/research_frontier.py — unexplored action queue",
            "research_portfolio_intelligence": "branch scoring — not proposition-scoped",
            "research_information_value": "template candidates — not OPR ledger",
        },
        "integration_deferred": True,
        "future_join_key": "proposition_id",
    }


def design_proposed_records() -> Dict[str, Any]:
    return {
        "EvidenceLedgerEntry": "Index EpistemicUpdateRecord + experiment metadata; no duplicate metrics",
        "EvidenceSynthesisRecord": {
            "immutable_snapshot": True,
            "contains": [
                "evidence_considered", "relationships", "independence_structure",
                "contradictions", "uncertainty_coverage", "saturation_assessment",
                "resulting_epistemic_state", "synthesis_hash",
            ],
        },
        "ResearchPriorityDecision": {
            "separate_from": "ResearchDecisionRecord (single-evidence)",
            "contains": ["epistemic_state", "saturation", "marginal_information", "chosen_priority_action", "frontier_rationale"],
        },
    }


def design_bb_epistemic_01() -> Dict[str, Any]:
    cases = [
        ("BE-01", "one_support_only", "SUPPORTED", "SEEK_FALSIFICATION or replication"),
        ("BE-02", "two_correlated_supports", "SUPPORTED", "NOT auto-strengthen; saturation partial"),
        ("BE-03", "two_independent_supports", "SUPPORTED", "may HOLD_PROVISIONALLY if dimensions covered"),
        ("BE-04", "support_weak_disconfirm", "WEAKENED or CONFLICTED", "SEEK_REPLICATION"),
        ("BE-05", "support_strong_independent_disconfirm", "WEAKENED/FALSIFIED", "ABANDON or conflict resolution"),
        ("BE-06", "representation_only_support", "SUPPORTED unchanged info", "reject redundancy"),
        ("BE-07", "conflicting_independent", "CONFLICTED", "SEEK_CONTRADICTION_RESOLUTION"),
        ("BE-08", "invalid_disconfirmation", "prior unchanged", "HOLD"),
        ("BE-09", "non_informative_repetition", "UNRESOLVED/SUPPORTED", "different axis or HOLD"),
        ("BE-10", "supports_major_dimension_untouched", "SUPPORTED", "SEEK_FALSIFICATION on untouched axis"),
        ("BE-11", "saturation_no_contradiction", "SUPPORTED", "HOLD_PROVISIONALLY"),
        ("BE-12", "unresolved_contradiction", "CONFLICTED", "SEEK_CONTRADICTION_RESOLUTION"),
        ("BE-13", "no_executable_high_info", "prior state", "HOLD_PROVISIONALLY or HOLD_UNRESOLVED"),
        ("BE-14", "falsified_then_support", "FALSIFIED preserved", "anomaly flag, no resurrection"),
        ("BE-15", "narrow_after_contradiction_temptation", "FALSIFIED/CONFLICTED", "reject rescue; FORK deferred"),
    ]
    return {
        "benchmark_id": "BB-Epistemic-01",
        "mode": "design_only",
        "abstract_features_required": True,
        "cases": [{"id": c[0], "name": c[1], "expected_state_hint": c[2], "expected_action_hint": c[3]} for c in cases],
        "fixture_results": "Deferred to 3I.12 implementation on abstract ledgers",
    }


def diagnostic_current_proposition(e1: Dict, e2: Dict, candidate: Dict) -> Dict[str, Any]:
    n1 = e1["metrics_used"]["sample_size"]
    n2 = e2["metrics_used"]["sample_size"]
    overlap_estimate = 1.0 - (n1 - n2) / n1 if n1 else 0

    return {
        "evidence_1": {
            "ref": e1["experiment_ref"],
            "class": e1["evidence_class"],
            "scope": "full_panel_all_dates",
            "sample_size": n1,
            "spread": e1["metrics_used"]["quintile_mean_spread"],
        },
        "evidence_2": {
            "ref": e2["experiment_ref"],
            "class": e2["evidence_class"],
            "scope": "holdout_exclude_2026-08-02",
            "sample_size": n2,
            "spread": e2["metrics_used"]["quintile_mean_spread"],
            "candidate_class": candidate["evidence_independence_class"],
        },
        "relationship_e1_to_e2": "PARTIAL_REPLICATION with episode_independence attempt — high cohort overlap (~97.7% rows)",
        "independence_assessment": {
            "episode_independence": "partial — one motivating date excluded",
            "sample_independence": "low — 5964/6106 shared structure",
            "measurement_independence": "none — same partition/quintile/outcome",
            "semantic_independence": "low — same uncertainty dimension (directional spread)",
        },
        "uncertainty_dimensions_covered": [
            "directional_effect_full_market",
            "directional_effect_holdout_without_focal_date",
        ],
        "uncertainty_dimensions_untouched": [
            "temporal_regime_robustness",
            "symbol_concentration",
            "horizon_variation",
            "population_subsets",
            "counterexample_conditions",
            "alternative_explanation_resolution",
            "measurement_formulation_change",
        ],
        "seek_falsification_still_justified": "On untouched axes yes; generic holdout repeat NO",
        "another_generic_holdout_redundant": True,
        "better_next_axis": "counterexample search, symbol/date decomposition, regime slice — not another date-exclusion holdout",
        "hold_provisionally_justified_yet": False,
        "hold_provisionally_reason": (
            "Two correlated supports on same measurement; major uncertainty dimensions remain open; "
            "not saturation — marginal value remains on non-redundant axes."
        ),
        "note": "Diagnostic from frozen design principles — not tuned to desired answer",
    }


def readiness_decision() -> Dict[str, Any]:
    return {
        "verdict": "PARTIALLY_READY",
        "reason": (
            "Ledger fragments exist (2 EpistemicUpdateRecords, lineage) but no EvidenceSynthesisEngine "
            "to reason over accumulated evidence, prior-state-conditioned transitions, saturation, or research priority."
        ),
        "highest_leverage_missing_capability": "EvidenceSynthesisEngine",
        "capability_detail": (
            "Synthesize append-only evidence ledger into: relationship taxonomy, independence profiles, "
            "contradiction structure, uncertainty coverage, saturation assessment, prior-state-conditioned "
            "epistemic state, and ResearchPriorityDecision — without vote counting or N-confirmation rules."
        ),
        "minimal_3i12_boundary": (
            "Implement EvidenceSynthesisEngine on abstract BB-Epistemic-01 fixtures only; "
            "prior-state-conditioned transition table frozen before real proposition application; "
            "then apply once diagnostically to prop-efb650d9bd5c451f ledger."
        ),
        "proposed_next_phase": "Phase 3I.12 — Minimal Evidence Synthesis Engine (abstract fixtures first)",
    }


def main() -> int:
    lineage = audit_lineage_integrity()
    cohort_fix = audit_resolve_cohort_fix()
    e1 = _load(I37 / "07_epistemic_update.json")
    e2 = _load(I310 / "05_epistemic_update.json")
    candidate = _load(I39 / "07_real_candidate_set.json")["candidates"][0]

    _write("01_lineage_integrity.json", lineage)
    _write("02_resolve_cohort_fix_audit.json", cohort_fix)
    _write("03_evidence_ledger_design.json", design_evidence_ledger())
    _write("04_evidence_relationship_taxonomy.json", design_evidence_relationship_taxonomy())
    _write("05_independence_profile_design.json", design_independence_profile())
    _write("06_multi_evidence_state_design.json", design_multi_evidence_state())
    _write("07_prior_state_reasoning_design.json", design_prior_state_reasoning())
    _write("08_unresolved_uncertainty_design.json", design_unresolved_uncertainty())
    _write("09_information_contribution_design.json", design_information_contribution())
    _write("10_saturation_design.json", design_saturation())
    _write("11_falsification_sufficiency_design.json", design_falsification_sufficiency())
    _write("12_research_priority_design.json", design_research_priority())
    _write("13_proposed_records_design.json", design_proposed_records())
    _write("14_bb_epistemic_01_design.json", design_bb_epistemic_01())
    _write("15_current_proposition_diagnostic.json", diagnostic_current_proposition(e1, e2, candidate))
    _write("16_readiness_decision.json", readiness_decision())
    _write("17_audit_summary.json", {
        "phase": "3I.11",
        "mode": "AUDIT_DESIGN_ONLY",
        "git_head": _git_head(),
        "verdict": readiness_decision()["verdict"],
        "missing_capability": readiness_decision()["highest_leverage_missing_capability"],
        "resolve_cohort_classification": cohort_fix["classification"],
        "lineage_passed": lineage["passed"],
        "new_experiment_executed": False,
    })

    print(json.dumps(readiness_decision(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
