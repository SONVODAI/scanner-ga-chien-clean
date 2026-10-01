#!/usr/bin/env python3
"""
Phase 3I.6 AUDIT + DESIGN ONLY — lifecycle readiness audit.

Read-only inspection of merged research stack + 3I branch references.
Does NOT implement lifecycle engine.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _file_exists(rel: str) -> bool:
    return (REPO / rel).exists()


def _branch_file(branch: str, rel: str) -> bool:
    try:
        subprocess.check_output(
            ["git", "show", f"origin/{branch}:{rel}"],
            cwd=REPO,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def audit_infrastructure() -> Dict[str, Any]:
    merged = {
        "research_state_ExperimentSpec": _file_exists("modules/edge_research/research_state.py"),
        "research_tools_execution": _file_exists("modules/edge_research/research_tools.py"),
        "research_assessment": _file_exists("modules/edge_research/research_assessment.py"),
        "research_interpreter": _file_exists("modules/edge_research/research_interpreter.py"),
        "research_graph": _file_exists("modules/edge_research/research_graph.py"),
        "research_planner": _file_exists("modules/edge_research/research_planner.py"),
        "research_controller": _file_exists("modules/edge_research/research_controller.py"),
        "research_actions_templates": _file_exists("modules/edge_research/research_actions.py"),
        "challenger": _file_exists("modules/edge_research/challenger.py"),
        "hypothesis_derive_scientific_status": _file_exists("modules/edge_research/hypothesis.py"),
    }
    opr_branch = "cursor/phase-3i5-observation-prioritization-aad2"
    opr = {
        "proposition_record": _branch_file(opr_branch, "modules/edge_research/opr_bridge/proposition_record.py"),
        "prioritized_pipeline": _branch_file(opr_branch, "modules/edge_research/opr_bridge/prioritized_pipeline.py"),
        "executability_adapter": _branch_file(opr_branch, "modules/edge_research/opr_bridge/executability_adapter.py"),
        "scientific_identity": _branch_file(opr_branch, "modules/edge_research/opr_bridge/scientific_identity.py"),
        "research_proposition_core": _branch_file(opr_branch, "modules/edge_research/research_proposition_core.py"),
    }
    design_3i1 = _branch_file(
        "cursor/phase-3i1-opr-bridge-contract-aad2",
        "diagnostics/phase_3i1_opr_bridge_contract/artifacts/12_evidence_responsive_lineage.json",
    )
    return {
        "merged_research_stack": merged,
        "opr_branch_present": opr,
        "opr_on_main": _file_exists("modules/edge_research/opr_bridge/proposition_record.py"),
        "design_artifact_12_evidence_lineage": design_3i1,
    }


def reusable_vs_missing() -> Dict[str, Any]:
    return {
        "reusable": [
            {
                "component": "PropositionRecord v1",
                "location": "opr_bridge/proposition_record.py (3I branch)",
                "reuse": "Birth record, falsification spec, epistemic enum at birth",
            },
            {
                "component": "EvidenceLineage (3I.5)",
                "location": "prioritized_pipeline.py",
                "reuse": "Pre-emission append-only evidence aggregation",
            },
            {
                "component": "ExperimentSpec + execute_research_experiment",
                "location": "research_state.py, research_tools.py",
                "reuse": "Run partition_group_compare and other bounded tools",
            },
            {
                "component": "executability_adapter",
                "location": "opr_bridge/executability_adapter.py",
                "reuse": "PropositionRecord → ExperimentSpec syntax bridge",
            },
            {
                "component": "ResearchGraph",
                "location": "research_graph.py",
                "reuse": "Append-only experiment nodes, lineage, ABANDON/RESOLVED",
            },
            {
                "component": "ResearchAssessment",
                "location": "research_assessment.py",
                "reuse": "Branch-level interpretation — partial model for experiment reading",
            },
            {
                "component": "scientific_identity / cores_same_question",
                "location": "scientific_identity.py, research_proposition_core.py",
                "reuse": "Fork detection, dedup, mutation vs rescue boundary",
            },
            {
                "component": "3I.1 artifact 12",
                "location": "12_evidence_responsive_lineage.json",
                "reuse": "Transition vocabulary design precedent",
            },
        ],
        "disconnected_or_template_bound": [
            {
                "component": "research_actions.generate_action_candidates",
                "issue": "24+ frozen question templates + GAP code mapping — not proposition-scoped",
            },
            {
                "component": "research_planner.plan_next_action",
                "issue": "Fixed weights on template candidates — not evidence-class-driven",
            },
            {
                "component": "challenger.run_challenger",
                "issue": "Phase 2 candidates only; ignores disconfirming_observation_spec",
            },
            {
                "component": "derive_scientific_status",
                "issue": "Discovery pipeline enum — not PropositionRecord epistemic lifecycle",
            },
            {
                "component": "ResearchAssessment.validated/actionable",
                "issue": "Hard-coded False — never wired to belief update",
            },
            {
                "component": "OPR → research_controller",
                "issue": "No integration path; siloed pipelines",
            },
        ],
        "missing": [
            {
                "capability": "PropositionExperimentInterpreter",
                "description": "Compare ToolResult to falsifiable_expectation + disconfirming_observation_spec → evidence class",
            },
            {
                "capability": "EpistemicUpdateRecord",
                "description": "Append-only state transition with evidence refs",
            },
            {
                "capability": "ResearchDecisionRecord",
                "description": "Contract in artifact 04 — not implemented",
            },
            {
                "capability": "LifecycleDecisionEngine",
                "description": "Evidence → next action without template menu",
            },
            {
                "capability": "Proposition-scoped graph join",
                "description": "proposition_id on QUESTION/EXPERIMENT nodes",
            },
            {
                "capability": "Post-emission evidence lineage",
                "description": "Bridge 3I.5 pre-emission lineage to experiment results",
            },
            {
                "capability": "FORK_NEW_EXPLANATION generator",
                "description": "Design only — evidence-motivated fork with new birth certificate",
            },
        ],
    }


def readiness_gate(audit: Dict[str, Any], gap: Dict[str, Any]) -> Dict[str, Any]:
    execution_ok = audit["merged_research_stack"]["research_tools_execution"]
    birth_ok = audit["opr_branch_present"]["proposition_record"] or audit["opr_on_main"]
    design_ok = audit["design_artifact_12_evidence_lineage"]
    one_missing = gap["missing"][0]["capability"]

    if execution_ok and birth_ok and design_ok:
        verdict = "PARTIALLY_READY"
        prerequisite = one_missing  # PropositionExperimentInterpreter
        minimal_3i7 = {
            "scope": "One frozen autonomous proposition → one partition_group_compare result → one evidence interpretation → one ResearchDecisionRecord → append-only lineage",
            "frozen_inputs": "3I.3/3I.5 representative proposition (2026-08-02)",
            "no_general_autonomy": True,
        }
    else:
        verdict = "NOT_READY"
        prerequisite = "Merge OPR foundation to main" if not birth_ok else "Research execution stack"
        minimal_3i7 = None

    return {
        "verdict": verdict,
        "single_prerequisite": prerequisite,
        "minimal_3i7_boundary": minimal_3i7,
        "rationale": (
            "Execution and birth infrastructure exist; design contracts pre-registered in 3I.1/3I.6. "
            "Exactly one bridge missing: experiment-result interpretation against proposition falsification spec."
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    audit = audit_infrastructure()
    gap = reusable_vs_missing()
    readiness = readiness_gate(audit, gap)

    _write = lambda name, payload: (OUT / name).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    _write("06_infrastructure_audit.json", audit)
    _write("07_reusable_vs_missing.json", gap)
    _write("08_readiness_gate.json", readiness)

    summary = {
        "phase": "3I.6",
        "mode": "AUDIT_DESIGN_ONLY",
        "git_head": _git_head(),
        "capability_chain_current": "OBSERVE → WONDER → PROPOSE → PRIORITIZE",
        "capability_chain_target": "→ TEST → INTERPRET → UPDATE → DECIDE",
        "readiness_verdict": readiness["verdict"],
        "single_prerequisite": readiness["single_prerequisite"],
        "can_change_mind_today": False,
        "smallest_missing_mechanism": "PropositionExperimentInterpreter",
    }
    _write("09_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
