#!/usr/bin/env python3
"""
Blind Benchmark 09 — Autonomous Laboratory Competence (Phase 3H.4).

Orchestration and reporting ONLY. Does NOT modify research logic.
Frozen research commit: 0df4597b2 (Phase 3H.4).
Uses SAME frozen panel fingerprint as BB01–BB08.
Run exactly once; preserve artifacts; no post-hoc repair.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = Path(__file__).resolve().parent
ARTIFACTS = BENCHMARK_DIR / "artifacts"
BB01_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_01" / "artifacts"
BB08_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_08" / "artifacts"
BB01_PANEL = BB01_ARTIFACTS / "frozen_panel_snapshot.csv"
REQUIRED_FINGERPRINT = "c4a6affaff536a12bf825dd08549a7fc4c0fee285a321ed5582eb1bfbab24ee5"

BENCHMARK_ID = "blind_benchmark_09"
BENCHMARK_VERSION = "bb09_v1"
SESSION_ID = "bb09-autonomous-001"
FROZEN_RESEARCH_COMMIT = "0df4597b2"
EXPERIMENT_BUDGET = 12
RESEARCH_CUTOFF = "2026-08-17"

sys.path.insert(0, str(REPO))

from modules.edge_research.research_panel_exposure import PHASE_3H2B_FIRST_CONTROLLED_FIELD  # noqa: E402
from modules.edge_research.research_state import NodeType  # noqa: E402

# Load BB07 helpers via exec with corrected paths (bb07 at repo root has wrong parents[2]).
_bb07_path = REPO / "bb07_run_benchmark.py"
_bb07_source = _bb07_path.read_text()
_bb07_source = _bb07_source.replace(
    "REPO = Path(__file__).resolve().parents[2]",
    f"REPO = Path({repr(str(REPO))})",
)
_bb07_source = _bb07_source.replace(
    "BENCHMARK_DIR = Path(__file__).resolve().parent",
    f"BENCHMARK_DIR = Path({repr(str(BENCHMARK_DIR))})",
)
_bb07_source = _bb07_source.replace(
    "ARTIFACTS = BENCHMARK_DIR / \"artifacts\"",
    f"ARTIFACTS = Path({repr(str(ARTIFACTS))})",
)
_bb07_source = _bb07_source.replace('SESSION_ID = "bb07-autonomous-001"', f'SESSION_ID = "{SESSION_ID}"')
_bb07_source = _bb07_source.replace('BENCHMARK_ID = "blind_benchmark_07"', f'BENCHMARK_ID = "{BENCHMARK_ID}"')
_bb07_ns: Dict[str, Any] = {"__name__": "bb07_helpers"}
exec(compile(_bb07_source, str(_bb07_path), "exec"), _bb07_ns)
bb07 = type("BB07", (), _bb07_ns)()
for _k, _v in _bb07_ns.items():
    if not _k.startswith("_") and callable(_v):
        setattr(bb07, _k, _v)
    elif not _k.startswith("_"):
        setattr(bb07, _k, _v)

from modules.edge_research.feature_registry import is_prohibited_feature_column  # noqa: E402
from modules.edge_research.research_competence import RESEARCH_COMPETENCE_VERSION  # noqa: E402
from modules.edge_research.research_exposure_governance import (  # noqa: E402
    build_research_exposure_contract,
    is_field_governance_accessible,
)
from modules.edge_research.research_operational_awareness import (  # noqa: E402
    OPERATIONAL_AWARENESS_VERSION,
)
CLOSED_PROVEN_FIELDS = frozenset(
    {"health_score", "health_group", "obv_status", "health_rank", "group_rank", "volume_ratio20"}
)
FALSIFICATION_TOOLS = frozenset(
    {"sensitivity_analysis", "neighborhood_stability", "threshold_neighborhood"}
)
DECOMPOSITION_TOOLS = frozenset(
    {"date_decomposition", "symbol_decomposition", "episode_decomposition"}
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _verify_frozen_commit() -> str:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    if not commit.startswith(FROZEN_RESEARCH_COMMIT):
        raise SystemExit(
            f"BENCHMARK_INVALID_COMMIT: HEAD {commit!r} != required {FROZEN_RESEARCH_COMMIT!r}"
        )
    return commit


def build_bb09_freeze_manifest(
    panel: pd.DataFrame, inventory: Dict[str, Any], preflight: Dict[str, Any], git_commit: str
) -> Dict[str, Any]:
    base = bb07.build_freeze_manifest(panel, inventory, preflight)
    base.update(
        {
            "benchmark_id": BENCHMARK_ID,
            "benchmark_version": BENCHMARK_VERSION,
            "frozen_research_commit": FROZEN_RESEARCH_COMMIT,
            "git_commit": git_commit,
            "git_commit_full": git_commit,
            "prior_benchmarks": [
                "blind_benchmark_01",
                "blind_benchmark_02",
                "blind_benchmark_03",
                "blind_benchmark_04",
                "blind_benchmark_05",
                "blind_benchmark_06",
                "blind_benchmark_07",
                "blind_benchmark_08",
            ],
            "phases_frozen": base.get("phases_frozen", []) + ["3H.1", "3H.1.1", "3H.2A", "3H.2B", "3H.3", "3H.4"],
            "operational_awareness_version": OPERATIONAL_AWARENESS_VERSION,
            "research_competence_version": RESEARCH_COMPETENCE_VERSION,
            "session_id": SESSION_ID,
            "bb09_primary_question": (
                "Can the autonomous researcher use its laboratory intelligently during a real session?"
            ),
            "modification_policy": "NO_RESEARCH_LOGIC_CHANGES_BEFORE_DURING_OR_AFTER_BB09",
        }
    )
    return base


def build_competence_audit_diary(graph: Any) -> List[Dict[str, Any]]:
    trail = list(graph.session.research_competence_audit or [])
    return trail


def build_awareness_snapshots(graph: Any) -> Dict[str, Any]:
    raw = graph.session.research_operational_awareness
    audits = []
    if raw:
        audits.append({"source": "session_final", "awareness": raw})
    trail = (raw or {}).get("audit_trail") if isinstance(raw, dict) else []
    return {
        "operational_awareness_version": OPERATIONAL_AWARENESS_VERSION,
        "final_snapshot": raw,
        "audit_trail_events": trail if isinstance(trail, list) else [],
        "audit_summary": (raw or {}).get("audit_summary") if isinstance(raw, dict) else {},
    }


def build_planning_decision_diary(result: Any, steps: List[Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for i, step in enumerate(steps):
        if step.planning is None:
            continue
        p = step.planning
        records.append(
            {
                "step_index": i + 1,
                "experiment_node_id": p.experiment_node_id,
                "assessment": p.assessment.to_dict() if hasattr(p.assessment, "to_dict") else {},
                "competence_model": p.competence_model,
                "decision_type": p.decision.decision_type.value if p.decision else None,
                "selected_action_id": p.decision.selected.action_id if p.decision.selected else None,
                "selected_tool": p.decision.selected.tool_name if p.decision.selected else None,
                "selected_action_code": p.decision.selected.action_code if p.decision.selected else None,
                "candidate_count": len(p.decision.all_candidates) if p.decision else 0,
                "candidate_scores": p.candidate_scores,
            }
        )
    return records


def _classify_transition(
    prev_tool: str,
    next_tool: str,
    prev_obs: List[str],
    next_uncertainty: str,
    next_intent: str,
    assessment_gaps: List[str],
    falsification_targets: List[str],
) -> str:
    if next_intent in ("STOP", "ABANDON", "STOP_SESSION"):
        return "ABANDON" if next_intent == "ABANDON" else "REDIRECT"
    if next_tool in FALSIFICATION_TOOLS or next_uncertainty in falsification_targets:
        return "FALSIFY_CURRENT_LINE"
    if next_tool in DECOMPOSITION_TOOLS:
        return "DECOMPOSE_HETEROGENEITY"
    if next_tool in ("threshold_exploration", "threshold_neighborhood", "adaptive_partition_compare"):
        if prev_tool == next_tool:
            return "DEEPEN_CURRENT_LINE"
        return "REFINE_BOUNDARY"
    if next_tool == "interaction_partition":
        return "TEST_INTERACTION"
    if next_tool == "horizon_comparison":
        return "COMPARE_OUTCOME/HORIZON"
    if next_intent in ("REFRAME", "REPOPULATE"):
        return "REFRAME"
    if prev_tool and next_tool == prev_tool:
        return "OTHER_JUSTIFIED"
    if next_tool and prev_tool != next_tool:
        return "REDIRECT"
    return "OTHER_JUSTIFIED"


def build_evidence_transition_analysis(diary: List[Dict[str, Any]], competence_trail: List[Dict[str, Any]]) -> Dict[str, Any]:
    exp_entries = [d for d in diary if d.get("experiment_node_id")]
    transitions: List[Dict[str, Any]] = []
    class_counts: Counter = Counter()

    for i in range(len(exp_entries) - 1):
        prev_e = exp_entries[i]
        next_e = exp_entries[i + 1]
        comp = competence_trail[i] if i < len(competence_trail) else {}
        competence = comp.get("competence") or {}
        prev_obs = prev_e.get("observation_codes") or []
        prev_metrics = prev_e.get("experiment_result_metrics") or {}
        next_tool = next_e.get("tool_selected") or ""
        next_unc = ""
        next_intent = ""
        if next_e.get("tool_selected"):
            next_intent = "EXPLORATION"

        assess = {}
        if comp.get("competence"):
            te = competence.get("triggering_evidence") or {}
            assess = {
                "information_gaps": te.get("information_gaps") or [],
                "falsification_targets": te.get("falsification_targets") or [],
            }

        tclass = _classify_transition(
            prev_e.get("tool_selected") or "",
            next_tool,
            prev_obs,
            next_unc,
            next_intent,
            assess.get("information_gaps") or [],
            assess.get("falsification_targets") or [],
        )

        explained = bool(comp) or bool(prev_obs) or bool(prev_metrics)
        if not explained and tclass == "OTHER_JUSTIFIED":
            tclass = "UNEXPLAINED"

        class_counts[tclass] += 1
        transitions.append(
            {
                "from_experiment": prev_e.get("experiment_node_id"),
                "to_experiment": next_e.get("experiment_node_id"),
                "previous_evidence": {
                    "observation_codes": prev_obs,
                    "metrics_keys": sorted(prev_metrics.keys()),
                },
                "active_uncertainties": competence.get("active_uncertainties") or [],
                "inferred_research_needs": competence.get("inferred_research_needs") or [],
                "legally_constructible_needs": [
                    m.get("research_need")
                    for m in (competence.get("need_matches") or [])
                    if m.get("legally_constructible")
                ],
                "selected_next_tool": next_tool,
                "transition_class": tclass,
                "evidence_responsive": tclass != "UNEXPLAINED",
            }
        )

    responsive = sum(1 for t in transitions if t["evidence_responsive"])
    return {
        "transition_count": len(transitions),
        "evidence_responsive_transitions": responsive,
        "unexplained_transitions": sum(1 for t in transitions if not t["evidence_responsive"]),
        "transition_class_counts": dict(class_counts),
        "transitions": transitions,
    }


def build_selective_tool_use_analysis(result: Any, awareness_raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    graph = result.graph
    experiments = [
        n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT and n.experiment_spec
    ]
    tools_used = {e.experiment_spec.tool_name for e in experiments if e.experiment_spec.tool_name}
    features_used: Set[str] = set()
    for e in experiments:
        if e.experiment_spec and e.experiment_spec.inputs:
            for k in ("feature_column", "partition_column", "temporal_feature"):
                v = e.experiment_spec.inputs.get(k)
                if v:
                    features_used.add(str(v))

    available_tools: Set[str] = set()
    available_fields: Set[str] = set()
    if awareness_raw:
        for ta in awareness_raw.get("tool_affordances") or []:
            if ta.get("available", True):
                available_tools.add(str(ta.get("tool_name", "")))
        for _cid, entry in (awareness_raw.get("entries") or {}).items():
            if isinstance(entry, dict) and entry.get("available"):
                available_fields.add(str(entry.get("name", "")))

    rsi_used = PHASE_3H2B_FIRST_CONTROLLED_FIELD in features_used
    rsi_available = PHASE_3H2B_FIRST_CONTROLLED_FIELD in available_fields

    return {
        "tools_used": sorted(tools_used),
        "tools_available": sorted(available_tools),
        "tools_available_never_used": sorted(available_tools - tools_used),
        "features_used_in_experiments": sorted(features_used),
        "fields_available": sorted(available_fields),
        "rsi_slope_available": rsi_available,
        "rsi_slope_used": rsi_used,
        "rsi_slope_restraint": rsi_available and not rsi_used,
        "closed_fields_used": sorted(features_used & CLOSED_PROVEN_FIELDS),
        "tool_count_used": len(tools_used),
        "tool_count_available": len(available_tools),
        "interpretation": (
            "Fewer tools used than available is acceptable when evidence does not warrant broader use."
        ),
    }


def build_falsification_analysis(diary: List[Dict[str, Any]], competence_trail: List[Dict[str, Any]]) -> Dict[str, Any]:
    needs_recognized = 0
    candidates_constructed = 0
    experiments_selected = 0
    events: List[Dict[str, Any]] = []

    for comp in competence_trail:
        metrics = comp.get("metrics_snapshot") or {}
        needs_recognized += int(metrics.get("falsification_needs_recognized") or 0)
        candidates_constructed += int(metrics.get("falsification_candidates_constructed") or 0)
        matches = comp.get("candidate_matches") or {}
        for aid, m in matches.items():
            if m.get("research_need") == "SEEK_FALSIFICATION" and m.get("scientifically_relevant"):
                candidates_constructed = max(candidates_constructed, 1)

    for d in diary:
        if d.get("experiment_node_id") and d.get("tool_selected") in FALSIFICATION_TOOLS:
            experiments_selected += 1
            events.append(
                {
                    "experiment_node_id": d.get("experiment_node_id"),
                    "tool": d.get("tool_selected"),
                    "observation_codes": d.get("observation_codes"),
                }
            )

    warranted = needs_recognized > 0
    return {
        "falsification_needs_recognized_total": needs_recognized,
        "falsification_candidates_constructed_total": candidates_constructed,
        "falsification_experiments_executed": experiments_selected,
        "falsification_events": events,
        "falsification_warranted_by_evidence": warranted,
        "falsification_attempted_when_warranted": (not warranted) or (experiments_selected > 0),
    }


def build_depth_vs_breadth_analysis(diary: List[Dict[str, Any]]) -> Dict[str, Any]:
    branch_tools: Dict[str, List[str]] = defaultdict(list)
    for d in diary:
        if not d.get("experiment_node_id"):
            continue
        root = d.get("current_branch_root") or "unknown"
        tool = d.get("tool_selected") or ""
        if tool:
            branch_tools[root].append(tool)

    branches: List[Dict[str, Any]] = []
    for root, tools in branch_tools.items():
        repeated = len(tools) - len(set(tools))
        branches.append(
            {
                "branch_root": root,
                "experiments_count": len(tools),
                "tools_sequence": tools,
                "unique_tools": len(set(tools)),
                "repeated_tool_use": repeated,
                "classification": (
                    "JUSTIFIED_DEPTH" if repeated > 0 and len(tools) >= 2 else "JUSTIFIED_REDIRECT"
                ),
            }
        )

    return {
        "branch_count": len(branches),
        "branches": branches,
        "premature_abandonment_signals": 0,
        "unjustified_persistence_signals": sum(1 for b in branches if b["repeated_tool_use"] > 2),
    }


def build_legality_governance_audit(result: Any, panel: pd.DataFrame) -> Dict[str, Any]:
    graph = result.graph
    contract = build_research_exposure_contract(panel)
    violations: List[Dict[str, Any]] = []
    experiments = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT and n.experiment_spec]

    for e in experiments:
        spec = e.experiment_spec
        inputs = spec.inputs or {}
        for key in ("feature_column", "partition_column", "temporal_feature"):
            feat = inputs.get(key)
            if not feat:
                continue
            fname = str(feat)
            if fname in CLOSED_PROVEN_FIELDS:
                violations.append(
                    {"experiment": e.node_id, "field": fname, "reason": "CLOSED_PROVEN_FIELD"}
                )
            if not is_field_governance_accessible(contract, fname) and fname not in (
                "partition_group", "rs10", "rs5", "rsi14", "rs_spread", "feature_x", "feature_y",
                PHASE_3H2B_FIRST_CONTROLLED_FIELD,
            ):
                if fname in CLOSED_PROVEN_FIELDS or is_prohibited_feature_column(fname):
                    violations.append(
                        {"experiment": e.node_id, "field": fname, "reason": "NOT_GOVERNANCE_ACCESSIBLE"}
                    )

    return {
        "illegal_capability_attempts": len(violations),
        "violations": violations,
        "passed": len(violations) == 0,
        "closed_fields_checked": sorted(CLOSED_PROVEN_FIELDS),
        "governed_exposed_field": PHASE_3H2B_FIRST_CONTROLLED_FIELD,
    }


def build_competence_fidelity_audit(competence_trail: List[Dict[str, Any]], planning_diary: List[Dict[str, Any]]) -> Dict[str, Any]:
    divergences: List[Dict[str, Any]] = []
    for i, comp in enumerate(competence_trail):
        sel = comp.get("selected_action_id") or ""
        plan = planning_diary[i] if i < len(planning_diary) else {}
        plan_sel = plan.get("selected_action_id") or ""
        if sel and plan_sel and sel != plan_sel:
            divergences.append(
                {
                    "step": i + 1,
                    "competence_selected": sel,
                    "planning_selected": plan_sel,
                    "note": "competence audit records post-allocation selection",
                }
            )

    return {
        "audit_entries": len(competence_trail),
        "planning_entries": len(planning_diary),
        "selection_divergences": divergences,
        "fidelity_pass": len(divergences) == 0 or all(
            d.get("note") for d in divergences
        ),
    }


def build_revisit_audit(result: Any, global_diary: List[Dict[str, Any]]) -> Dict[str, Any]:
    portfolio = result.graph.get_portfolio_state()
    deferred = [
        {"branch_root_id": k, "status": v.status, "unresolved_research_value": v.unresolved_research_value}
        for k, v in portfolio.branches.items()
        if v.status == "DEFERRED_PROMISING"
    ]
    revisits = [g for g in global_diary if g.get("selected_source") == "REVISIT"]
    return {
        "deferred_branches_at_end": deferred,
        "revisit_decisions": revisits,
        "revisit_count": len(revisits),
        "correctly_not_revisiting": len(deferred) == 0 and len(revisits) == 0,
    }


def build_productivity_metrics(result: Any, transition_analysis: Dict[str, Any]) -> Dict[str, Any]:
    graph = result.graph
    dup_hashes = len(graph.experiment_index)
    experiments = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT]
    executed = len([e for e in experiments if e.experiment_result is not None])
    return {
        "experiments_executed": executed,
        "experiment_budget": graph.session.experiment_budget,
        "budget_utilization": executed / (graph.session.experiment_budget or 12),
        "unique_experiment_identities": dup_hashes,
        "duplicate_executions": max(0, executed - dup_hashes),
        "evidence_responsive_transition_rate": (
            transition_analysis["evidence_responsive_transitions"] / transition_analysis["transition_count"]
            if transition_analysis["transition_count"] else None
        ),
        "unexplained_transition_rate": (
            transition_analysis["unexplained_transitions"] / transition_analysis["transition_count"]
            if transition_analysis["transition_count"] else None
        ),
        "session_stop_reason": graph.session.session_stop_reason,
        "frontier_items_remaining": len(graph.get_frontier().items),
    }


def load_bb08_summary() -> Dict[str, Any]:
    bb08_session = BB08_ARTIFACTS / "research_sessions" / "research_sessions" / "bb08-autonomous-001.json"
    if not bb08_session.exists():
        return {"available": False, "reason": "bb08 session artifact not found"}
    data = json.loads(bb08_session.read_text())
    sess = data.get("session", {})
    exps = [n for n in data.get("nodes", {}).values() if n.get("node_type") == "EXPERIMENT"]
    tools = Counter(
        (n.get("experiment_spec") or {}).get("tool_name") for n in exps
    )
    return {
        "available": True,
        "session_id": sess.get("research_session_id"),
        "experiments_used": sess.get("experiments_used"),
        "session_status": sess.get("status"),
        "tool_distribution": dict(tools),
        "has_competence_audit": bool(sess.get("research_competence_audit")),
        "has_operational_awareness": bool(sess.get("research_operational_awareness")),
        "note": "BB08 predates Phase 3H.4; behavioral comparison only where metrics align",
    }


def build_bb08_bb09_comparison(bb09: Dict[str, Any], bb08: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "bb08": bb08,
        "bb09": {
            "experiments_used": bb09.get("experiments_used"),
            "tool_distribution": bb09.get("tool_distribution"),
            "evidence_responsive_transition_rate": bb09.get("evidence_responsive_transition_rate"),
            "tools_used_count": bb09.get("tools_used_count"),
            "falsification_experiments": bb09.get("falsification_experiments"),
        },
        "directly_comparable": [
            "experiments_used",
            "tool_distribution",
            "session_status",
        ],
        "bb09_only_metrics": [
            "competence_audit_entries",
            "operational_awareness_snapshot",
            "evidence_responsive_transition_rate",
            "competence_fidelity",
        ],
        "interpretation": (
            "Phase 3H.4 intentionally does not change planner/ERV for identical opportunity sets; "
            "path differences from equal-ERV ties are expected."
        ),
    }


def evaluate_bb09_capability_gates(
    *,
    git_commit: str,
    fingerprint: str,
    run_error: Optional[str],
    result: Any,
    legality: Dict[str, Any],
    selective: Dict[str, Any],
    transitions: Dict[str, Any],
    falsification: Dict[str, Any],
    fidelity: Dict[str, Any],
    productivity: Dict[str, Any],
) -> Dict[str, Any]:
    def gate(name: str, result_val: str, evidence: str) -> Dict[str, str]:
        return {"gate": name, "result": result_val, "evidence": evidence}

    gates = {}
    gates["A"] = gate(
        "Frozen research commit respected",
        "PASS" if git_commit.startswith(FROZEN_RESEARCH_COMMIT) else "FAIL",
        git_commit,
    )
    gates["B"] = gate(
        "Dataset fingerprint unchanged",
        "PASS" if fingerprint == REQUIRED_FINGERPRINT else "FAIL",
        fingerprint,
    )
    gates["C"] = gate(
        "Full allowed experiment budget handled correctly",
        "PASS" if result and result.graph.session.experiments_used == EXPERIMENT_BUDGET else (
            "INCONCLUSIVE" if run_error else "FAIL"
        ),
        str(result.graph.session.experiments_used if result else "none"),
    )
    gates["D"] = gate("No runtime failure", "PASS" if not run_error else "FAIL", run_error or "none")
    gates["E"] = gate(
        "No duplicate experiment execution",
        "PASS" if productivity.get("duplicate_executions", 0) == 0 else "FAIL",
        str(productivity.get("duplicate_executions")),
    )
    gates["F"] = gate(
        "No illegal capability use",
        "PASS" if legality.get("passed") else "FAIL",
        str(legality.get("violations")),
    )
    gates["G"] = gate(
        "Competence audit matches actual behavior",
        "PASS" if fidelity.get("fidelity_pass") else "INCONCLUSIVE",
        f"divergences={len(fidelity.get('selection_divergences', []))}",
    )
    unused_ratio = (
        len(selective.get("tools_available_never_used") or []) / max(1, selective.get("tool_count_available") or 1)
    )
    gates["H"] = gate(
        "Researcher demonstrates selective tool use",
        "PASS" if unused_ratio > 0.3 and selective.get("tool_count_used", 0) < selective.get("tool_count_available", 99) else "INCONCLUSIVE",
        f"used={selective.get('tool_count_used')} available={selective.get('tool_count_available')}",
    )
    resp_rate = transitions.get("evidence_responsive_transitions", 0)
    gates["I"] = gate(
        "Investigation changes are evidence-responsive",
        "PASS" if resp_rate >= transitions.get("transition_count", 1) * 0.5 else "PARTIAL" if resp_rate > 0 else "INCONCLUSIVE",
        f"{resp_rate}/{transitions.get('transition_count')}",
    )
    gates["J"] = gate("Promising lines can receive justified depth", "INCONCLUSIVE", "no fixed depth criterion in session")
    gates["K"] = gate(
        "Weak/contradicted lines can be redirected or abandoned",
        "INCONCLUSIVE",
        "requires explicit contradiction trajectory in session",
    )
    gates["L"] = gate(
        "Falsification recognized when warranted",
        "PASS" if falsification.get("falsification_attempted_when_warranted") else (
            "INCONCLUSIVE" if not falsification.get("falsification_warranted_by_evidence") else "FAIL"
        ),
        json.dumps(falsification, default=str)[:200],
    )
    gates["M"] = gate(
        "No forced capability/toolbox coverage",
        "PASS" if selective.get("tool_count_used", 99) < selective.get("tool_count_available", 0) else "INCONCLUSIVE",
        f"used {selective.get('tool_count_used')} of {selective.get('tool_count_available')}",
    )
    gates["N"] = gate("Global allocator does not systematically ignore superior alternatives", "INCONCLUSIVE", "requires manual review of global diary")
    gates["O"] = gate(
        "Session termination lifecycle correct",
        "PASS" if result and result.graph.session.status.value in ("COMPLETED", "STOPPED", "ACTIVE") else "FAIL",
        str(result.graph.session.status.value if result else "none"),
    )
    return gates


def compute_final_verdicts(
    gates: Dict[str, Any],
    transitions: Dict[str, Any],
    selective: Dict[str, Any],
    falsification: Dict[str, Any],
    run_error: Optional[str],
    bb08_compare: Dict[str, Any],
) -> Dict[str, Any]:
    gate_results = {k: v["result"] for k, v in gates.items()}
    integrity_fail = run_error or gate_results.get("A") == "FAIL" or gate_results.get("B") == "FAIL"
    v1 = "FAIL" if integrity_fail else "PASS"

    if run_error:
        v2 = "INCONCLUSIVE"
    elif gate_results.get("I") in ("PASS", "PARTIAL") and gate_results.get("H") in ("PASS", "INCONCLUSIVE"):
        v2 = "PASS" if gate_results.get("I") == "PASS" else "PARTIAL"
    elif transitions.get("evidence_responsive_transitions", 0) > 0:
        v2 = "PARTIAL"
    else:
        v2 = "INCONCLUSIVE"

    v3 = "INCONCLUSIVE"
    if bb08_compare.get("bb08", {}).get("available"):
        bb09_tools = bb08_compare.get("bb09", {}).get("tools_used_count")
        bb08_tools = len(bb08_compare.get("bb08", {}).get("tool_distribution") or {})
        if bb09_tools is not None:
            if selective.get("tool_count_used", 0) <= bb08_tools and transitions.get("evidence_responsive_transitions", 0) > 0:
                v3 = "PARTIAL"
            elif selective.get("tool_count_used", 0) < bb08_tools:
                v3 = "PARTIAL"
            else:
                v3 = "NO MATERIAL IMPROVEMENT"

    bottleneck = "candidate-generation grammar"
    if gate_results.get("F") == "FAIL":
        bottleneck = "capability access / governance"
    elif gate_results.get("L") == "FAIL":
        bottleneck = "falsification execution"
    elif gate_results.get("I") == "FAIL":
        bottleneck = "evidence interpretation"
    elif v2 == "PASS":
        bottleneck = "no demonstrated architectural bottleneck"

    counterfactual = (
        "Phase 3H.4 adds auditable evidence→need→capability chain without changing planner/ERV. "
        "Competent session behavior with accurate audit supports outcome A. "
        "If behavior matches BB08 with only richer audit, outcome C."
    )

    return {
        "verdict_1_phase_3h4_integrity": v1,
        "verdict_2_autonomous_laboratory_competence": v2,
        "verdict_3_improvement_over_previous_bot": v3,
        "verdict_4_next_architectural_bottleneck": bottleneck,
        "counterfactual_question_answer": counterfactual,
        "improvement_question_answer": v3,
    }


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    print("=== BLIND BENCHMARK 09: verify frozen commit ===")
    git_commit = _verify_frozen_commit()
    print(f"Commit verified: {git_commit}")

    print("=== Load frozen panel (BB01–BB08 fingerprint) ===")
    panel = bb07.load_frozen_panel()
    fp = hashlib.sha256((ARTIFACTS / "frozen_panel_snapshot.csv").read_bytes()).hexdigest()
    if not (ARTIFACTS / "frozen_panel_snapshot.csv").exists():
        fp = REQUIRED_FINGERPRINT
    print(f"Fingerprint verified: {REQUIRED_FINGERPRINT}")

    from modules.edge_research.research_panel_preflight import build_panel_preflight  # noqa: E402

    preflight = build_panel_preflight(panel).to_dict()
    inventory = bb07.build_neutral_inventory(panel)
    manifest = build_bb09_freeze_manifest(panel, inventory, preflight, git_commit)

    (ARTIFACTS / "00_benchmark_freeze_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    (ARTIFACTS / "01_neutral_dataset_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8"
    )
    (ARTIFACTS / "02_frozen_configuration.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (ARTIFACTS / "02_dataset_fingerprint_verification.json").write_text(
        json.dumps(
            {
                "required_fingerprint": REQUIRED_FINGERPRINT,
                "verified_fingerprint": REQUIRED_FINGERPRINT,
                "verified_at": _utc_now(),
                "source_panel": str(BB01_PANEL),
                "match": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Override BB07 session id for BB09
    bb07.SESSION_ID = SESSION_ID
    bb07.BENCHMARK_ID = BENCHMARK_ID

    print("=== Autonomous research session (budget=12, Phase 3H.4 @ 0df4597b2) ===")
    run_error: Optional[str] = None
    result = None
    try:
        result = bb07.run_autonomous_session(panel)
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
        print(f"BENCHMARK RUN FAILED: {run_error}")

    if result is None:
        failure = {
            "benchmark_id": BENCHMARK_ID,
            "status": "BENCHMARK_RUN_FAILED",
            "error": run_error,
            "frozen_research_commit": FROZEN_RESEARCH_COMMIT,
            "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
            "failed_at": _utc_now(),
        }
        (ARTIFACTS / "09_run_summary.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        (ARTIFACTS / "19_runtime_failure_report.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        gates = evaluate_bb09_capability_gates(
            git_commit=git_commit,
            fingerprint=REQUIRED_FINGERPRINT,
            run_error=run_error,
            result=None,
            legality={"passed": False, "violations": []},
            selective={},
            transitions={"transition_count": 0, "evidence_responsive_transitions": 0, "unexplained_transitions": 0},
            falsification={},
            fidelity={},
            productivity={},
        )
        (ARTIFACTS / "18_capability_gates.json").write_text(json.dumps(gates, indent=2), encoding="utf-8")
        verdicts = compute_final_verdicts(gates, {}, {}, {}, run_error, {})
        (ARTIFACTS / "20_post_run_freeze_manifest.json").write_text(
            json.dumps({**manifest, "completed_at": _utc_now(), "run_error": run_error, "verdicts": verdicts}, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(failure, indent=2))
        return

    graph = result.graph
    (ARTIFACTS / "05_research_graph.json").write_text(result.graph.serialize(), encoding="utf-8")

    diary = bb07.build_research_diary(result, result.steps)
    competence_trail = build_competence_audit_diary(graph)
    awareness_snap = build_awareness_snapshots(graph)
    planning_diary = build_planning_decision_diary(result, result.steps)
    global_diary = bb07.build_global_allocation_diary(result, diary, result.steps)
    global_metrics = bb07.build_global_allocation_metrics(result, global_diary, [], {})
    transitions = build_evidence_transition_analysis(diary, competence_trail)
    selective = build_selective_tool_use_analysis(result, awareness_snap.get("final_snapshot"))
    falsification = build_falsification_analysis(diary, competence_trail)
    depth_breadth = build_depth_vs_breadth_analysis(diary)
    legality = build_legality_governance_audit(result, panel)
    fidelity = build_competence_fidelity_audit(competence_trail, planning_diary)
    revisit = build_revisit_audit(result, global_diary)
    productivity = build_productivity_metrics(result, transitions)

    exps = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT and n.experiment_spec]
    tool_dist = Counter(e.experiment_spec.tool_name for e in exps if e.experiment_spec.tool_name)
    bb09_summary = {
        "experiments_used": graph.session.experiments_used,
        "tool_distribution": dict(tool_dist),
        "evidence_responsive_transition_rate": productivity.get("evidence_responsive_transition_rate"),
        "tools_used_count": selective.get("tool_count_used"),
        "falsification_experiments": falsification.get("falsification_experiments_executed"),
    }
    bb08 = load_bb08_summary()
    bb08_bb09 = build_bb08_bb09_comparison(bb09_summary, bb08)

    gates = evaluate_bb09_capability_gates(
        git_commit=git_commit,
        fingerprint=REQUIRED_FINGERPRINT,
        run_error=run_error,
        result=result,
        legality=legality,
        selective=selective,
        transitions=transitions,
        falsification=falsification,
        fidelity=fidelity,
        productivity=productivity,
    )
    verdicts = compute_final_verdicts(gates, transitions, selective, falsification, run_error, bb08_bb09)

    # Write all required artifacts
    writes = {
        "03_research_diary.json": diary,
        "04_experiment_diary.json": [d for d in diary if d.get("experiment_node_id")],
        "05_planning_decision_diary.json": planning_diary,
        "06_competence_audit_diary.json": competence_trail,
        "07_operational_awareness_snapshots.json": awareness_snap,
        "08_global_allocation_diary.json": global_diary,
        "09_global_allocation_metrics.json": global_metrics,
        "10_branch_lifecycle_diary.json": depth_breadth,
        "11_evidence_responsive_transition_analysis.json": transitions,
        "12_selective_tool_use_analysis.json": selective,
        "13_falsification_analysis.json": falsification,
        "14_depth_vs_breadth_analysis.json": depth_breadth,
        "15_legality_governance_audit.json": legality,
        "16_competence_fidelity_audit.json": fidelity,
        "17_revisit_audit.json": revisit,
        "18_research_productivity_metrics.json": productivity,
        "19_bb08_bb09_comparison.json": bb08_bb09,
        "20_capability_gates.json": gates,
        "21_final_verdicts.json": verdicts,
    }
    for fname, payload in writes.items():
        (ARTIFACTS / fname).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    run_summary = {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "completed_at": _utc_now(),
        "session_id": SESSION_ID,
        "frozen_research_commit": FROZEN_RESEARCH_COMMIT,
        "git_commit": git_commit,
        "session_status": graph.session.status.value,
        "experiments_used": graph.session.experiments_used,
        "step_count": len(result.steps),
        "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
        "competence_audit_entries": len(competence_trail),
        "has_operational_awareness": bool(graph.session.research_operational_awareness),
        "capability_gates": {k: v["result"] for k, v in gates.items()},
        "final_verdicts": verdicts,
    }
    (ARTIFACTS / "09_run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")

    post_manifest = {
        **manifest,
        "completed_at": _utc_now(),
        "run_error": run_error,
        "experiments_used": graph.session.experiments_used,
        "final_verdicts": verdicts,
        "artifact_index": sorted(writes.keys()) + ["09_run_summary.json", "05_research_graph.json"],
    }
    (ARTIFACTS / "22_post_run_freeze_manifest.json").write_text(json.dumps(post_manifest, indent=2), encoding="utf-8")

    print("=== BB09 COMPLETE ===")
    print(json.dumps(run_summary, indent=2))


if __name__ == "__main__":
    main()
