#!/usr/bin/env python3
"""
Phase 3J.1 — Autonomous First-Experiment Selection Readiness Audit.

AUDIT + DESIGN ONLY. No experiments. No ToolResult. No deployment.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"

sys.path.insert(0, str(REPO))


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def audit_mechanism_inventory() -> Dict[str, Any]:
    """Classify existing components for first-experiment-at-birth applicability."""
    mechanisms = [
        {
            "component": "executability_adapter.adapt_executability",
            "location": "opr_bridge/executability_adapter.py",
            "when": "At proposition emission (pipeline.py L126)",
            "classification": "TOOL_BINDING_ONLY",
            "notes": "Hardcodes partition_group_compare; single candidate; no comparison",
        },
        {
            "component": "proposition_synthesizer.experiment_spec expectations",
            "location": "opr_bridge/proposition_synthesizer.py",
            "when": "At proposition birth",
            "classification": "SCIENTIFIC_OBJECTIVE_DERIVED (partial)",
            "notes": "falsifiable_expectation + disconfirming_observation_spec derived from contrast; tool named in BC_Q8",
        },
        {
            "component": "scientific_action_generator",
            "location": "opr_bridge/scientific_action_generator.py",
            "when": "Post-synthesis only",
            "classification": "NOT_APPLICABLE_AT_PROPOSITION_BIRTH",
            "notes": "Requires EvidenceSynthesisRecord + ResearchPriorityDecision",
        },
        {
            "component": "falsification_candidate_generator",
            "location": "opr_bridge/falsification_candidate_generator.py",
            "when": "Post-first-experiment + SEEK_FALSIFICATION",
            "classification": "NOT_APPLICABLE_AT_PROPOSITION_BIRTH",
            "notes": "Requires epistemic_update, research_decision, prior_tool_result_hash",
        },
        {
            "component": "derive_proposition_vulnerabilities",
            "location": "falsification_candidate_generator.py",
            "when": "Callable at birth (unused for first experiment)",
            "classification": "SCIENTIFIC_OBJECTIVE_DERIVED (partial)",
            "notes": "Vulnerabilities from disconfirm spec; not wired to first-experiment selection",
        },
        {
            "component": "research_actions.generate_action_candidates",
            "location": "research_actions.py",
            "when": "Post-experiment legacy planner",
            "classification": "LEGACY_PRIOR",
            "notes": "GAP → 24 templates; blocked under OPR authority",
        },
        {
            "component": "research_planner.plan_next_action",
            "location": "research_planner.py",
            "when": "Post-experiment",
            "classification": "LEGACY_PRIOR",
            "notes": "Weighted template ranking; not proposition-birth",
        },
        {
            "component": "lifecycle_runner.run_minimal_lifecycle",
            "location": "lifecycle_runner.py",
            "when": "Manual/diagnostic with pre-selected spec",
            "classification": "EXECUTION_UTILITY",
            "notes": "Executes given spec; does not select first experiment",
        },
        {
            "component": "production_orchestrator STOP_PROPOSITION_PERSISTED",
            "location": "production_orchestrator.py",
            "when": "3J.0 production birth",
            "classification": "NOT_APPLICABLE_AT_PROPOSITION_BIRTH",
            "notes": "Explicit stop before any experiment selection",
        },
        {
            "component": "cohort_overlap_estimator",
            "location": "cohort_overlap_estimator.py",
            "when": "3I.17b post-synthesis actions",
            "classification": "EXECUTION_UTILITY (reusable)",
            "notes": "Can quantify birth-evidence overlap if wired at birth",
        },
    ]
    return {"mechanisms": mechanisms, "count": len(mechanisms)}


def design_initial_experiment_objective_record() -> Dict[str, Any]:
    """Minimum general record design — not implemented in production."""
    return {
        "record_version": "initial_experiment_objective_v1_design_3j1",
        "purpose": "State what uncertainty the first experiment should reduce, derived from proposition commitments",
        "required_fields": {
            "objective_id": "stable id",
            "proposition_id": "parent proposition",
            "proposition_hash": "immutable commitment anchor",
            "target_uncertainty": "derived from falsifiable_expectation / disconfirming_observation_spec / canonical core",
            "scientific_vulnerability": "e.g. directional_reversal, episode_artifact, population_specificity",
            "why_first": "Why this uncertainty ranks first before any evidence",
            "outcome_branches": {
                "more_credible": "pre-result description",
                "less_credible": "pre-result description",
                "unresolved": "pre-result description",
            },
            "forbidden_rescue_mutations": "from proposition commitments",
            "provenance": "fields used for derivation — no tool names required",
        },
        "derivation_sources_at_birth": [
            "falsifiable_expectation",
            "disconfirming_observation_spec",
            "null_competing_explanation",
            "canonical_proposition_core",
            "observation_provenance.structural_context",
        ],
        "capability_gap": "No production module derives InitialExperimentObjectiveRecord at STOP_PROPOSITION_PERSISTED",
    }


def design_selection_policy() -> Dict[str, Any]:
    """Lexicographic pre-result selection policy — design only."""
    return {
        "policy_version": "first_experiment_selector_lex_v1_design_3j1",
        "ordering": [
            "1. Reject NON_EXECUTABLE, RESCUE_MUTATION, NEW_PROPOSITION_REQUIRED",
            "2. Reject REDUNDANT_WITH_BIRTH_EVIDENCE (overlap thresholds)",
            "3. Reject CONFIRMATORY_ONLY when FALSIFICATION_CAPABLE available",
            "4. Reject REPRESENTATION_ONLY duplicates",
            "5. Prefer higher birth-evidence independence (lexicographic dimensions)",
            "6. Prefer directness to central proposition commitment",
            "7. Prefer falsification-capable outcome branches",
            "8. Executability tie-break only — tools last",
        ],
        "valid_non_selection_outcomes": [
            "AMBIGUOUS_FIRST_EXPERIMENT",
            "NO_HIGH_INFORMATION_FIRST_EXPERIMENT",
        ],
        "capability_gap": "No FirstExperimentSelector module exists",
    }


def run_real_proposition_diagnostic() -> Dict[str, Any]:
    """Apply audit to frozen T2 proposition — NOT executed."""
    import pandas as pd
    from modules.edge_research.opr_bridge.executability_adapter import adapt_executability
    from modules.edge_research.opr_bridge.falsification_candidate_generator import (
        collect_motivating_episode_dates,
        derive_proposition_vulnerabilities,
    )
    from modules.edge_research.opr_bridge.lifecycle_runner import load_proposition_record
    from modules.edge_research.opr_bridge.proposition_record import ExecutabilityStatus

    prop_wrap = json.loads(
        (REPO / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json").read_text()
    )
    prop = prop_wrap["full_record"]
    panel_path = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
    panel = pd.read_csv(panel_path) if panel_path.exists() else None

    record = load_proposition_record(prop)
    exec_result = adapt_executability(record, panel) if panel is not None else None

    vulnerabilities = derive_proposition_vulnerabilities(prop)
    motivating_dates = collect_motivating_episode_dates(prop)

    candidates = []
    if exec_result and exec_result.experiment_spec:
        candidates.append(
            {
                "candidate_id": "birth-executability-default",
                "source": "executability_adapter",
                "experiment_spec": exec_result.to_dict().get("experiment_spec"),
                "classification": "REDUNDANT_WITH_BIRTH_EVIDENCE",
                "classification_rationale": (
                    "Same partition_column rs_spread, same outcome t5_return, full-panel quintile "
                    f"recompute includes motivating focal_date {motivating_dates} — duplicates birth quintile contrast"
                ),
                "independence_from_birth": "LOW",
                "falsification_capable": True,
                "confirmatory_only": True,
            }
        )

    # Sketch what falsification generator would produce IF called at birth (it cannot — missing inputs)
    sketch_strategies = [
        "episode_holdout_excluding_motivating",
        "directional_reversal_partition",
    ]
    for sk in sketch_strategies:
        candidates.append(
            {
                "candidate_id": f"sketch-fc-{sk}",
                "source": "falsification_generator_sketch_NOT_INVOKED",
                "classification": "FALSIFICATION_CAPABLE if independent",
                "note": "Generator requires epistemic_update — not invokable at birth today",
            }
        )

    selected = None
    selection_reason = (
        "No selector exists. Default executability_adapter candidate would win by being the only "
        "invokable path — human/tool prior (partition_group_compare hardcoded), not scientific dominance."
    )

    package = {
        "package_id": "iefp-design-preview-not-executed",
        "execution_status": "NOT_EXECUTED",
        "proposition_id": prop["proposition_id"],
        "proposition_hash": prop_wrap["proposition_hash"],
        "scientific_vulnerability_primary": vulnerabilities[0].kind.value if vulnerabilities else None,
        "objectives_sketch": [
            {
                "target_uncertainty": "directional_effect_full_universe",
                "derived_from": "falsifiable_expectation + disconfirming_observation_spec",
            },
            {
                "target_uncertainty": "episode_robustness",
                "derived_from": "null_competing_explanation episode artifact",
            },
        ],
        "candidates": candidates,
        "selected_candidate": selected,
        "selection_reason": selection_reason,
        "human_choice_material": True,
        "human_choice_reason": "executability_adapter hardcodes single tool; no comparative selection",
    }

    return {
        "proposition_id": prop["proposition_id"],
        "motivating_dates": list(motivating_dates),
        "vulnerabilities": [{"kind": v.kind.value, "description": v.description} for v in vulnerabilities],
        "executability_status": exec_result.status.value if exec_result else "NO_PANEL",
        "initial_experiment_package": package,
    }


def run_counterfactual_audit() -> Dict[str, Any]:
    """CF-FE1 through CF-FE8 — conceptual against current mechanism inventory."""
    cf = {
        "CF-FE1": {
            "description": "Remove motivating evidence → rationale changes",
            "current_capability": "NOT_DEMONSTRATED",
            "passed": False,
            "reason": "No first-experiment objective derivation module",
        },
        "CF-FE2": {
            "description": "Increase birth overlap → independence falls",
            "current_capability": "PARTIAL",
            "passed": False,
            "reason": "cohort_overlap_estimator exists but not wired at proposition birth",
        },
        "CF-FE3": {
            "description": "Resolve central uncertainty → experiment disappears",
            "current_capability": "NOT_DEMONSTRATED",
            "passed": False,
            "reason": "No objective lifecycle at birth",
        },
        "CF-FE4": {
            "description": "Rename/reorder tools → scientific winner unchanged",
            "current_capability": "NOT_APPLICABLE",
            "passed": False,
            "reason": "Only one candidate path — no selection invariance test possible",
        },
        "CF-FE5": {
            "description": "Representation change only → identity unchanged",
            "current_capability": "PARTIAL",
            "passed": False,
            "reason": "scientific_action_core dedup exists for post-synthesis actions, not first experiment",
        },
        "CF-FE6": {
            "description": "Redundant cohort → alternate or silence",
            "current_capability": "NOT_DEMONSTRATED",
            "passed": False,
            "reason": "No first-experiment selector",
        },
        "CF-FE7": {
            "description": "Best candidate non-executable → no silent inferior substitution",
            "current_capability": "NOT_DEMONSTRATED",
            "passed": False,
            "reason": "No selector policy at birth",
        },
        "CF-FE8": {
            "description": "Rescue mutation → reject",
            "current_capability": "PARTIAL",
            "passed": True,
            "reason": "Anti-rescue in falsification generator + scientific_action_operators — but post-synthesis only",
        },
    }
    cf["all_passed"] = all(v["passed"] for v in cf.values() if isinstance(v, dict))
    return cf


def run_bbfe_design_audit() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.bb_first_experiment_01_design import all_bbfe_cases, assert_bbfe_firewall

    cases = all_bbfe_cases()
    firewall = [assert_bbfe_firewall(c) for c in cases]
    return {
        "benchmark": "BB-FirstExperiment-01",
        "version": "design_pre_registered",
        "case_count": len(cases),
        "firewall_passed": all(f["passed"] for f in firewall),
        "implementation_status": "NOT_IMPLEMENTED — design only for 3J.1",
        "expected_current_pass_rate": "0/20 against existing birth-time mechanisms",
        "cases": [{"case_id": c["case_id"], "family": c["family"], "scenario": c["scenario"]} for c in cases],
    }


def production_relationship_audit() -> Dict[str, Any]:
    return {
        "current_3j0_flow": [
            "production evidence",
            "→ detect_production_opportunity",
            "→ STOP_PROPOSITION_PERSISTED",
            "→ persist OprProductionSessionRecord",
            "→ STOP (no experiment)",
        ],
        "required_future_insertion": "[future first-experiment selector] between STOP_PROPOSITION_PERSISTED and InitialExperimentPackage",
        "wired_in_3j1": False,
        "stop_after_package": True,
    }


def legacy_firewall_audit() -> Dict[str, Any]:
    return {
        "legacy_can_choose_first_experiment": True,
        "path": "bootstrap_research_graph → human seed question → template experiment",
        "opr_blocks_legacy_when_active": True,
        "first_experiment_via_template_map": "Would be TEMPLATE_TRANSLATION if OPR not active",
        "verdict": "Legacy cannot silently choose when OPR authority active, but no OPR first-experiment selector exists either",
    }


def compute_verdicts(audit: Dict[str, Any]) -> Dict[str, str]:
    return {
        "FIRST_EXPERIMENT_OBJECTIVE_READINESS": "PARTIALLY_READY",
        "FIRST_EXPERIMENT_CANDIDATE_GENERATION_READINESS": "NOT_READY",
        "FIRST_EXPERIMENT_SELECTION_READINESS": "NOT_READY",
        "BIRTH_EVIDENCE_INDEPENDENCE_READINESS": "NOT_READY",
        "OVERALL": "NOT_READY",
    }


def main() -> int:
    from modules.edge_research.opr_bridge.evidence_synthesis_engine import engine_content_hash

    audit = {
        "phase": "3J.1",
        "mode": "AUDIT_DESIGN_ONLY",
        "git_head": _git_head(),
        "frozen_hashes": {
            "evidence_synthesis_engine": engine_content_hash(),
            "note": "3J.0 integration hash unchanged — no scientific modules modified",
        },
        "mechanism_inventory": audit_mechanism_inventory(),
        "initial_experiment_objective_design": design_initial_experiment_objective_record(),
        "selection_policy_design": design_selection_policy(),
        "real_proposition_diagnostic": run_real_proposition_diagnostic(),
        "counterfactuals": run_counterfactual_audit(),
        "bb_first_experiment_01": run_bbfe_design_audit(),
        "production_relationship": production_relationship_audit(),
        "legacy_firewall": legacy_firewall_audit(),
    }
    audit["verdicts"] = compute_verdicts(audit)

    _write("01_mechanism_inventory.json", audit["mechanism_inventory"])
    _write("02_initial_experiment_objective_design.json", audit["initial_experiment_objective_design"])
    _write("03_selection_policy_design.json", audit["selection_policy_design"])
    _write("04_real_proposition_diagnostic.json", audit["real_proposition_diagnostic"])
    _write("05_counterfactuals.json", audit["counterfactuals"])
    _write("06_bb_first_experiment_01_design.json", audit["bb_first_experiment_01"])
    _write("07_production_relationship.json", audit["production_relationship"])
    _write("08_legacy_firewall.json", audit["legacy_firewall"])
    _write("09_audit_summary.json", audit)

    print(json.dumps(audit["verdicts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
