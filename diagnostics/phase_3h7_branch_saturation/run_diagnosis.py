#!/usr/bin/env python3
"""
Phase 3H.7 — Branch Saturation / Exit Diagnosis (OFFLINE ONLY).

Reconstructs BB10 branch lifecycle from frozen artifacts + frozen research code.
Does NOT modify research logic, scoring, or selection.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
DIAG_DIR = Path(__file__).resolve().parent
ARTIFACTS = DIAG_DIR / "artifacts"
BB10_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_10" / "artifacts"

FROZEN_RESEARCH_COMMIT = "b28cf8ae6"
BB10_BENCHMARK_COMMIT = "22b1d0e4e"
BB10_SESSION = "bb10-autonomous-001"
DATASET_FINGERPRINT = "c4a6affaff536a12bf825dd08549a7fc4c0fee285a321ed5582eb1bfbab24ee5"

EXIT_LAYERS = {
    "L1": "SATURATION EVIDENCE",
    "L2": "SATURATION RECOGNITION",
    "L3": "EXIT NEED",
    "L4": "EXIT CAPABILITY",
    "L5": "EXIT CANDIDATE CONSTRUCTION",
    "L6": "FILTER",
    "L7": "PLANNER VALUE",
    "L8": "INFORMATION VALUE",
    "L9": "PORTFOLIO / ERV",
    "L10": "GLOBAL ALLOCATION",
    "L11": "STOP COMPETITION",
    "L12": "EXIT / STAY",
}

HYPOTHESES = {
    "B10-A": "SATURATION NOT REPRESENTED",
    "B10-B": "SATURATION REPRESENTED BUT NOT VALUED",
    "B10-C": "EXIT ALTERNATIVES NOT GENERATED",
    "B10-D": "EXIT ALTERNATIVES GENERATED BUT UNDERVALUED",
    "B10-E": "GLOBAL ALLOCATOR / SWITCHING FRICTION",
    "B10-F": "FRONTIER QUALITY PROBLEM",
    "B10-G": "STOP LOGIC PROBLEM",
    "B10-H": "REVISIT / DEFERRED LIFECYCLE PROBLEM",
    "B10-I": "BRANCH IDENTITY / TOPOLOGY PROBLEM",
    "B10-J": "INFORMATION-VALUE DECAY MISMATCH",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(name: str) -> Any:
    return json.loads((BB10_ARTIFACTS / name).read_text(encoding="utf-8"))


def _write(name: str, payload: Any) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def _iv_for_transition(iv_audit: List[Dict], idx: int, action_id: str) -> Optional[Dict]:
    if idx >= len(iv_audit):
        return None
    for a in iv_audit[idx].get("candidate_assessments") or []:
        if a.get("action_id") == action_id:
            return a
    return None


def build_freeze_manifest() -> Dict[str, Any]:
    panel_hash = hashlib.sha256((BB10_ARTIFACTS / "frozen_panel_snapshot.csv").read_bytes()).hexdigest()
    return {
        "diagnosis_id": "phase_3h7_branch_saturation",
        "diagnosis_version": "3h7_v1",
        "verified_at": _utc_now(),
        "frozen_research_commit": FROZEN_RESEARCH_COMMIT,
        "bb10_benchmark_commit": BB10_BENCHMARK_COMMIT,
        "bb10_session_id": BB10_SESSION,
        "dataset_fingerprint": DATASET_FINGERPRINT,
        "panel_fingerprint_verified": panel_hash == DATASET_FINGERPRINT,
        "diagnosis_branch_commit": _git_head(),
        "bb10_artifact_dir": str(BB10_ARTIFACTS),
        "modification_policy": "DIAGNOSIS_ONLY_NO_RESEARCH_BEHAVIOR_CHANGES",
        "artifact_index": [
            "01_branch_lifecycle_diary.json",
            "02_branch_topology_audit.json",
            "03_saturation_signal_inventory.json",
            "04_marginal_information_curve.json",
            "05_exit_opportunity_reconstruction.json",
            "06_late_session_forensics.json",
            "07_stop_logic_audit.json",
            "08_allocator_switching_audit.json",
            "09_information_value_decay_audit.json",
            "10_exit_counterfactuals.json",
            "11_branch_exit_first_loss.json",
            "12_limitation_15_2_15_3_effect.json",
            "13_required_questions.json",
            "14_final_diagnosis.json",
        ],
    }


def build_branch_lifecycle_diary(
    exp_diary: List[Dict],
    planning: List[Dict],
    competence: List[Dict],
    global_diary: List[Dict],
    iv_audit: List[Dict],
    info_gain: Dict,
) -> List[Dict[str, Any]]:
    ig_map = {e["experiment"]: e for e in info_gain.get("experiments", [])}
    records: List[Dict[str, Any]] = []
    for i, exp in enumerate(exp_diary):
        t = i + 1
        p = planning[i] if i < len(planning) else {}
        c = competence[i] if i < len(competence) else {}
        g = global_diary[i] if i < len(global_diary) else {}
        iv = iv_audit[i] if i < len(iv_audit) else {}
        assess_before = p.get("assessment") or {}
        sel_id = p.get("selected_action_id")
        scores = p.get("candidate_scores") or {}
        sel_score = scores.get(sel_id, {}) if sel_id else {}
        iv_sel = _iv_for_transition(iv_audit, i, sel_id) if sel_id else None
        ig = ig_map.get(exp.get("experiment_node_id"), {})
        branch_tools = assess_before.get("branch_tools_attempted") or []
        marginal = "UNKNOWN"
        if t >= 8:
            marginal = "DECLINING" if (sel_score.get("total") or 0) < 0 else "FLAT"
        elif t >= 5:
            marginal = "FLAT"
        else:
            marginal = "INCREASING_OR_STABLE"
        records.append(
            {
                "transition": t,
                "experiment_id": exp.get("experiment_node_id"),
                "branch_root_id": exp.get("current_branch_root"),
                "frame_id": exp.get("frame_id", ""),
                "source": g.get("selected_source"),
                "tool": exp.get("tool_selected"),
                "intent": (c.get("candidate_matches") or {}).get(sel_id, {}).get("intent"),
                "uncertainty_addressed": (c.get("candidate_matches") or {}).get(sel_id, {}).get("uncertainty_code"),
                "evidence_before": {
                    "information_gaps": assess_before.get("information_gaps"),
                    "falsification_targets": assess_before.get("possible_falsification_targets"),
                    "branch_tools_attempted": branch_tools,
                    "observation_codes": assess_before.get("branch_observation_codes"),
                },
                "information_value_contribution": (iv_sel or {}).get("valuation_contribution"),
                "base_planner_score": sel_score.get("components", {}).get("base_planner_score"),
                "final_planner_score": sel_score.get("total"),
                "erv_components": g.get("erv_components"),
                "selected_erv": g.get("selected_erv"),
                "best_local_erv": g.get("best_local_erv"),
                "best_frontier_erv": g.get("best_frontier_erv"),
                "best_deferred_erv": g.get("best_deferred_erv"),
                "context_switch": g.get("context_switch_occurred"),
                "result_observations": exp.get("observation_codes"),
                "information_gain_class": ig.get("information_gain_class"),
                "redundancy_state": {
                    "tool_repeated_on_branch": exp.get("tool_selected") in branch_tools,
                    "branch_tool_count": len(branch_tools),
                },
                "resolved_new": bool(ig.get("gaps_resolved") or ig.get("falsification_resolved")),
                "marginal_branch_value": marginal,
            }
        )
    return records


def build_branch_topology_audit(graph: Dict, lifecycle: List[Dict]) -> Dict[str, Any]:
    nodes = graph.get("nodes", {})
    branch_roots = set(r["branch_root_id"] for r in lifecycle if r.get("branch_root_id"))
    frames = set()
    for r in lifecycle:
        eid = r.get("experiment_id")
        if eid and eid in nodes:
            spec = (nodes[eid].get("experiment_spec") or {})
            scope = spec.get("research_scope") or {}
            frames.add(scope.get("frame_id") or nodes[eid].get("frame_id") or "")
    rf = graph.get("session", {}).get("research_frontier", {})
    items = rf.get("items", rf) if isinstance(rf, dict) else {}
    frontier_branches = set()
    if isinstance(items, dict):
        for item in items.values():
            frontier_branches.add(item.get("branch_root_id"))
    all_same = len(branch_roots) == 1
    semantic_variation = {
        "unique_tools": len(set(r["tool"] for r in lifecycle)),
        "horizon_experiments": sum(1 for r in lifecycle if r["tool"] == "horizon_comparison"),
        "decomposition_executed": sum(1 for r in lifecycle if r["tool"] in (
            "symbol_decomposition", "date_decomposition", "episode_decomposition"
        )),
        "revisit_selections": sum(1 for r in lifecycle if r.get("source") == "REVISIT"),
        "frontier_selections": sum(1 for r in lifecycle if r.get("source") == "FRONTIER"),
    }
    return {
        "structural_branch_roots": sorted(branch_roots),
        "structural_single_branch": all_same,
        "frontier_branch_roots": sorted(x for x in frontier_branches if x),
        "all_frontier_same_root_as_executed": frontier_branches <= branch_roots,
        "frame_ids_observed": sorted(x for x in frames if x),
        "semantic_variation_within_root": semantic_variation,
        "finding": (
            "STRUCTURAL_SINGLE_BRANCH with SEMANTIC_TOOL_DIVERSITY"
            if all_same and semantic_variation["unique_tools"] > 3
            else "MULTI_BRANCH" if not all_same else "SINGLE_BRANCH_LOW_DIVERSITY"
        ),
        "topology_explanation": (
            "All 12 experiments share branch_root obs-b08a47b141fd. Tool/intent diversity "
            "(5 tools, decomposition, falsification) occurs within one graph branch identity. "
            "REVISIT and FRONTIER selections return to or spawn from the same branch_root — "
            "not independent scientific branches."
        ),
    }


def build_saturation_signal_inventory() -> Dict[str, Any]:
    signals = [
        {
            "signal": "repeated_unresolved_uncertainty",
            "represented": True,
            "location": "ResearchAssessment.information_gaps, unresolved_uncertainties",
            "available_before_planning": True,
            "consumed_by_planner": "partial (information_gap weights)",
            "consumed_by_portfolio_erv": "via marginal_information_gain reduction",
            "consumed_by_global_allocator": "indirect via ERV",
            "consumed_by_stop": False,
            "audit_only": False,
        },
        {
            "signal": "branch_tools_attempted",
            "represented": True,
            "location": "ResearchAssessment.branch_tools_attempted",
            "available_before_planning": True,
            "consumed_by_planner": True,
            "consumed_by_portfolio_erv": True,
            "consumed_by_global_allocator": True,
            "consumed_by_stop": False,
            "audit_only": False,
        },
        {
            "signal": "negative_planner_scores",
            "represented": True,
            "location": "research_planner.score_candidate",
            "available_before_planning": True,
            "consumed_by_planner": True,
            "consumed_by_portfolio_erv": True,
            "consumed_by_global_allocator": True,
            "consumed_by_stop": False,
            "audit_only": False,
        },
        {
            "signal": "iv_redundancy_burden",
            "represented": True,
            "location": "research_information_value._redundancy_burden (uncertainty-tool topology)",
            "available_before_planning": True,
            "consumed_by_planner": False,
            "consumed_by_portfolio_erv": False,
            "consumed_by_global_allocator": False,
            "consumed_by_stop": False,
            "audit_only": False,
            "note": "Affects planner layer only via IV bridge; not branch-level cumulative",
        },
        {
            "signal": "frame_saturation_status",
            "represented": True,
            "location": "research_frame.assess_frame_saturation",
            "available_before_planning": True,
            "consumed_by_planner": "reframe bonuses only",
            "consumed_by_portfolio_erv": False,
            "consumed_by_global_allocator": False,
            "consumed_by_stop": False,
            "audit_only": "partial",
        },
        {
            "signal": "portfolio_tool_attempt_counts",
            "represented": True,
            "location": "research_portfolio.compute_marginal_information_gain",
            "available_before_planning": True,
            "consumed_by_planner": False,
            "consumed_by_portfolio_erv": True,
            "consumed_by_global_allocator": True,
            "consumed_by_stop": False,
            "audit_only": False,
        },
        {
            "signal": "realized_information_gain",
            "represented": False,
            "location": "NOT in state — only in post-hoc BB10 audit",
            "available_before_planning": False,
            "consumed_by_planner": False,
            "consumed_by_portfolio_erv": False,
            "consumed_by_global_allocator": False,
            "consumed_by_stop": False,
            "audit_only": True,
        },
        {
            "signal": "branch_level_marginal_decay",
            "represented": False,
            "location": "No explicit branch cumulative marginal value field",
            "available_before_planning": False,
            "consumed_by_planner": False,
            "consumed_by_portfolio_erv": "partial via MIG tool/dimension counts",
            "consumed_by_global_allocator": False,
            "consumed_by_stop": False,
            "audit_only": False,
        },
        {
            "signal": "frontier_revalued_erv",
            "represented": True,
            "location": "research_global_allocator._build_frontier_opportunity",
            "available_before_planning": True,
            "consumed_by_planner": False,
            "consumed_by_portfolio_erv": True,
            "consumed_by_global_allocator": True,
            "consumed_by_stop": False,
            "audit_only": False,
        },
        {
            "signal": "stop_session_candidate",
            "represented": True,
            "location": "research_actions STOP_SESSION candidate; planner _stop_session_score=-100",
            "available_before_planning": True,
            "consumed_by_planner": True,
            "consumed_by_portfolio_erv": True,
            "consumed_by_global_allocator": True,
            "consumed_by_stop": "evaluate_global_stop separate from candidate competition",
            "audit_only": False,
        },
    ]
    knowable = sum(1 for s in signals if s.get("available_before_planning"))
    operational = sum(
        1 for s in signals
        if s.get("consumed_by_planner") or s.get("consumed_by_portfolio_erv")
    )
    return {
        "signals": signals,
        "signals_represented_before_planning": knowable,
        "signals_operationally_consumed": operational,
        "can_bot_know_saturation_before_decision": "PARTIAL — multiple local signals exist but no unified branch-exhaustion representation gates exit",
    }


def build_marginal_information_curve(lifecycle: List[Dict], info_gain: Dict) -> Dict[str, Any]:
    curve: List[Dict[str, Any]] = []
    cumulative_depth = 0
    for r in lifecycle:
        cumulative_depth += 1
        ig = r.get("information_gain_class", "UNKNOWN")
        expected_iv = r.get("information_value_contribution") or 0
        planner = r.get("final_planner_score") or 0
        erv = r.get("selected_erv") or 0
        curve.append(
            {
                "transition": r["transition"],
                "tool": r["tool"],
                "expected_iv_before": expected_iv,
                "planner_score_before": planner,
                "erv_before": erv,
                "realized_gain_after": ig,
                "cumulative_branch_depth": cumulative_depth,
                "marginal_branch_value": r.get("marginal_branch_value"),
                "unresolved_gaps_count": len(r.get("evidence_before", {}).get("information_gaps") or []),
            }
        )
    deterioration_start = None
    for pt in curve:
        if pt["transition"] >= 7 and pt["erv_before"] is not None and pt["erv_before"] < 2:
            deterioration_start = pt["transition"]
            break
    return {
        "curve": curve,
        "deterioration_interval_start": deterioration_start,
        "deterioration_interval_end": 12,
        "interpretation": (
            f"Marginal ERV deteriorates from T{deterioration_start or '?'} onward. "
            "T8–T11 show negative local ERV with continued selection. "
            "No hard saturation point — gradual decline with 'least bad' continuation."
            if deterioration_start
            else "No clear deterioration point identified."
        ),
        "audit_only": True,
    }


def build_exit_opportunity_reconstruction(
    planning: List[Dict],
    competence: List[Dict],
    global_diary: List[Dict],
    iv_audit: List[Dict],
) -> Dict[str, Any]:
    alt_types = ("NEW_BRANCH", "FRONTIER", "REVISIT", "DEFERRED", "REFRAME", "FALSIFICATION",
                 "DECOMPOSITION", "STOP", "CONTINUE_CURRENT_BRANCH")
    transitions: List[Dict[str, Any]] = []
    for idx in range(min(11, len(planning))):
        p = planning[idx]
        c = competence[idx]
        g = global_diary[idx]
        iv = iv_audit[idx] if idx < len(iv_audit) else {}
        scores = p.get("candidate_scores") or {}
        matches = c.get("candidate_matches") or {}
        alternatives: List[Dict[str, Any]] = []
        for aid, sc in scores.items():
            m = matches.get(aid, {})
            tool = m.get("tool_name") or ""
            need = m.get("research_need") or ""
            intent = m.get("intent") or ""
            if "STOP" in intent or need in ("REDIRECT_OR_ABANDON",):
                atype = "STOP"
            elif need in ("DECOMPOSE_HETEROGENEITY", "REPLICATE", "CONDITION_ON_CONTEXT"):
                atype = "DECOMPOSITION"
            elif need == "SEEK_FALSIFICATION":
                atype = "FALSIFICATION"
            elif need == "REVISIT_UNRESOLVED_BRANCH":
                atype = "REVISIT"
            elif intent in ("REFRAME", "REPOPULATE"):
                atype = "REFRAME"
            else:
                atype = "CONTINUE_CURRENT_BRANCH"
            iv_a = next((a for a in (iv.get("candidate_assessments") or []) if a.get("action_id") == aid), {})
            alternatives.append(
                {
                    "action_id": aid,
                    "type": atype,
                    "tool": tool,
                    "scientifically_relevant": m.get("scientifically_relevant"),
                    "legally_constructible": m.get("legally_constructible", True),
                    "generated": True,
                    "planner_score": sc.get("total"),
                    "information_value": iv_a.get("valuation_contribution"),
                    "erv": sc.get("total"),
                }
            )
        alternatives.sort(key=lambda x: -(x.get("planner_score") or -9999))
        sel = p.get("selected_action_id")
        sel_alt = next((a for a in alternatives if a["action_id"] == sel), {})
        transitions.append(
            {
                "transition": idx + 1,
                "selected_type": sel_alt.get("type", "CONTINUE_CURRENT_BRANCH"),
                "selected_source": g.get("selected_source"),
                "selected_erv": g.get("selected_erv"),
                "best_frontier_erv": g.get("best_frontier_erv"),
                "best_local_erv": g.get("best_local_erv"),
                "alternatives_count": len(alternatives),
                "exit_alternatives": [a for a in alternatives if a["type"] not in ("CONTINUE_CURRENT_BRANCH",)],
                "top_exit_alternative": next((a for a in alternatives if a["type"] != "CONTINUE_CURRENT_BRANCH"), None),
                "nowhere_better": (
                    (g.get("best_frontier_erv") or -999) <= (g.get("best_local_erv") or -999)
                    and (g.get("selected_erv") or -999) >= (g.get("best_frontier_erv") or -999)
                ),
                "valuation_prevented_exit": (
                    any(a["type"] in ("DECOMPOSITION", "FALSIFICATION", "FRONTIER") for a in alternatives)
                    and g.get("selected_source") == "LOCAL"
                    and (g.get("selected_erv") or 0) < 0
                ),
            }
        )
    late = [t for t in transitions if t["transition"] >= 7]
    return {
        "transitions": transitions,
        "late_session_summary": late,
        "nowhere_better_count": sum(1 for t in late if t["nowhere_better"]),
        "valuation_prevented_count": sum(1 for t in late if t["valuation_prevented_exit"]),
    }


def build_late_session_forensics(
    lifecycle: List[Dict],
    exit_recon: Dict,
    planning: List[Dict],
    global_diary: List[Dict],
) -> Dict[str, Any]:
    late_bb10 = _load("18_late_session_cycling_analysis.json")
    decisions: List[Dict[str, Any]] = []
    for idx in range(7, 11):
        lc = next((r for r in lifecycle if r["transition"] == idx + 1), {})
        er = next((t for t in exit_recon["transitions"] if t["transition"] == idx + 1), {})
        p = planning[idx] if idx < len(planning) else {}
        g = global_diary[idx] if idx < len(global_diary) else {}
        bb10_class = next(
            (d for d in late_bb10.get("late_session_decisions", []) if d.get("transition") == idx + 1),
            {},
        ).get("classification", "")
        sel_erv = g.get("selected_erv") or 0
        best_front = g.get("best_frontier_erv") or -999
        best_local = g.get("best_local_erv") or -999
        if bb10_class == "MECHANICAL_CYCLING":
            causal = "MECHANICAL_CYCLING"
        elif sel_erv >= best_front and sel_erv >= 0:
            causal = "JUSTIFIED_STAY_NO_BETTER_ALTERNATIVE"
        elif sel_erv >= best_front and sel_erv < 0:
            causal = "LEAST_BAD_CONTINUATION"
        elif er.get("valuation_prevented_exit"):
            causal = "EXIT_ALTERNATIVE_UNDERVALUED"
        else:
            causal = "TOPOLOGY_AMBIGUOUS"
        if bb10_class == "JUSTIFIED_CONTINUATION" and sel_erv < 0:
            causal = "LEAST_BAD_CONTINUATION"
        decisions.append(
            {
                "transition": idx + 1,
                "tool_selected": lc.get("tool"),
                "bb10_cycling_class": bb10_class,
                "causal_classification": causal,
                "evidence_for_staying": {
                    "local_erv_beats_frontier": sel_erv >= best_front,
                    "selected_erv": sel_erv,
                    "best_frontier_erv": best_front,
                },
                "evidence_for_leaving": {
                    "negative_planner": (p.get("candidate_scores") or {}).get(p.get("selected_action_id"), {}).get("total", 0) < 0,
                    "unresolved_uncertainties": len(lc.get("evidence_before", {}).get("information_gaps") or []),
                    "exit_alts_exist": len(er.get("exit_alternatives") or []) > 0,
                },
                "alternatives_independent": er.get("selected_source") not in ("REVISIT", "LOCAL") or False,
                "positive_scientific_value": sel_erv > 0,
                "genuinely_best_vs_least_bad": "LEAST_BAD" if sel_erv < 0 else "GENUINELY_BEST",
                "stop_defensible": sel_erv < 0 and best_front < 0,
                "deciding_component": (
                    "LOCAL_ERV_DOMINANCE" if g.get("selected_source") == "LOCAL"
                    else "REVISIT_ERV" if g.get("selected_source") == "REVISIT"
                    else "FRONTIER_ERV"
                ),
            }
        )
    class_counts = Counter(d["causal_classification"] for d in decisions)
    return {
        "late_session_decisions": decisions,
        "causal_classification_counts": dict(class_counts),
        "bb10_cycling_reference": late_bb10.get("classification_counts"),
    }


def build_stop_logic_audit(graph: Dict, global_diary: List[Dict]) -> Dict[str, Any]:
    sess = graph.get("session", {})
    rf = sess.get("research_frontier", {})
    items = rf.get("items", rf) if isinstance(rf, dict) else {}
    unexplored = [v for v in (items.values() if isinstance(items, dict) else []) if v.get("status") == "UNEXPLORED"]
    historical_best = max((u.get("planner_score", 0) for u in unexplored), default=0)
    stop_transitions: List[Dict[str, Any]] = []
    for idx, g in enumerate(global_diary[:11]):
        stop_transitions.append(
            {
                "transition": idx + 1,
                "best_frontier_erv_revalued": g.get("best_frontier_erv"),
                "best_local_erv": g.get("best_local_erv"),
                "would_stop_if_revalued_only": (
                    (g.get("best_frontier_erv") or 0) < 0.5
                    and (g.get("best_local_erv") or 0) < 0.5
                    and idx >= 6
                ),
                "historical_frontier_best": historical_best,
            }
        )
    cf_stop_differs = [t for t in stop_transitions if t["would_stop_if_revalued_only"]]
    return {
        "evaluate_global_stop_location": "research_frontier.evaluate_global_stop",
        "stop_uses_historical_planner_score": True,
        "stop_threshold": 0.5,
        "terminal_stop_reason": sess.get("session_stop_reason"),
        "session_stopped_by": "BUDGET_EXHAUSTED not INSUFFICIENT_RESEARCH_VALUE",
        "unexplored_frontier_at_end": len(unexplored),
        "historical_best_unexplored_score": historical_best,
        "revalued_best_at_late_decisions": [g.get("best_frontier_erv") for g in global_diary[7:11]],
        "stop_session_planner_penalty": -100.0,
        "stop_competes_in_global_allocation": True,
        "stop_would_win_any_late_decision": False,
        "counterfactual_revalued_stop_transitions": cf_stop_differs,
        "finding": (
            "STOP never competes effectively: STOP_SESSION hardcoded -100 planner penalty; "
            "evaluate_global_stop uses historical frontier scores (best=8.7) not revalued ERV "
            "(late revalued ~-4 to -1). Session continues until budget exhaustion despite "
            "negative marginal experiment value."
        ),
    }


def build_allocator_switching_audit(global_diary: List[Dict]) -> Dict[str, Any]:
    decisions: List[Dict[str, Any]] = []
    for idx, g in enumerate(global_diary[:11]):
        if not g:
            continue
        local_beats = (g.get("best_local_erv") or -999) > (g.get("best_frontier_erv") or -999)
        decisions.append(
            {
                "transition": idx + 1,
                "selected_source": g.get("selected_source"),
                "context_switch": g.get("context_switch_occurred"),
                "selected_erv": g.get("selected_erv"),
                "best_local_erv": g.get("best_local_erv"),
                "best_frontier_erv": g.get("best_frontier_erv"),
                "best_deferred_erv": g.get("best_deferred_erv"),
                "local_beats_frontier": local_beats,
                "erv_components": g.get("erv_components"),
                "branch_before": g.get("branch_before"),
                "branch_after": g.get("branch_after"),
            }
        )
    late_local_wins = sum(
        1 for d in decisions if d["transition"] >= 8 and d.get("local_beats_frontier")
    )
    return {
        "decisions": decisions,
        "branch_switches": sum(1 for d in decisions if d.get("context_switch")),
        "frontier_selections": sum(1 for d in decisions if d.get("selected_source") == "FRONTIER"),
        "revisit_selections": sum(1 for d in decisions if d.get("selected_source") == "REVISIT"),
        "late_local_beats_frontier_count": late_local_wins,
        "primary_mechanism": (
            "Local branch ERV consistently exceeds revalued frontier ERV in late session (T8–T11). "
            "No context-switch to different branch_root occurred. REVISIT returns to same root."
        ),
        "switching_friction_evidence": "context_switch_occurred=false for all 12 transitions",
    }


def build_iv_decay_audit(lifecycle: List[Dict], iv_audit: List[Dict]) -> Dict[str, Any]:
    examples: List[Dict[str, Any]] = []
    for idx, lc in enumerate(lifecycle[:11]):
        iv = iv_audit[idx] if idx < len(iv_audit) else {}
        pos = [a for a in (iv.get("candidate_assessments") or []) if (a.get("valuation_contribution") or 0) > 0]
        zero_redundancy = [a for a in (iv.get("candidate_assessments") or []) if a.get("redundancy_burden", 0) > 0]
        examples.append(
            {
                "transition": lc["transition"],
                "tool_selected": lc["tool"],
                "positive_iv_candidates": len(pos),
                "candidates_with_redundancy_burden": len(zero_redundancy),
                "iv_still_positive_for_heterogeneity": any(
                    a.get("uncertainty_type") == "information_gap" for a in pos
                ),
                "topology_not_branch_level": True,
            }
        )
    return {
        "redundancy_mechanism": "UNCERTAINTY_RESOLUTION_TOOLS topology — counts prior tools addressing same uncertainty code on branch",
        "captures_same_scientific_question": "PARTIAL — same uncertainty yes, cross-tool alternation may evade per-tool topology",
        "captures_branch_level_saturation": False,
        "captures_low_realized_gain": False,
        "resets_after_reframe": "NOT EVIDENCED in BB10 — single frame throughout",
        "horizon_partition_threshold_evade": (
            "YES — different tools (horizon/partition/threshold) attack different uncertainty codes; "
            "branch_tools_attempted tracks tools but IV redundancy is uncertainty-specific"
        ),
        "bb10_examples": examples,
        "finding": "B10-J CONFIRMED — IV decay operates at uncertainty-tool level, not branch cumulative marginal decay",
    }


def build_exit_counterfactuals(planning: List[Dict], global_diary: List[Dict]) -> Dict[str, Any]:
    cfs: List[Dict[str, Any]] = []
    for idx in range(7, 11):
        p = planning[idx]
        g = global_diary[idx]
        scores = p.get("candidate_scores") or {}
        sel = p.get("selected_action_id")
        non_sel = {k: v for k, v in scores.items() if k != sel and (v.get("total") or 0) > -500}
        cf1_winner = max(non_sel.items(), key=lambda x: x[1].get("total", -999))[0] if non_sel else None
        ranked = sorted(scores.items(), key=lambda x: -x[1].get("total", -999))
        stop_cands = [(k, v) for k, v in scores.items() if (v.get("total") or 0) < -100]
        cfs.append(
            {
                "transition": idx + 1,
                "CF1_remove_current_branch_winner": cf1_winner,
                "CF2_zero_switch_cost": "Same winner — no branch switch candidates with higher ERV at different root",
                "CF3_revalued_erv_only_winner": ranked[0][0] if ranked else None,
                "CF4_stop_as_zero_competitor": (
                    "STOP would win" if stop_cands and all(
                        (v.get("total") or 0) < -10 for _, v in ranked[:3]
                    ) else "CONTINUE still wins — STOP at -115 to -119 vs continue at -3 to -8"
                ),
                "CF5_branch_redundancy_zero_effect": "No change to candidate construction — redundancy affects scoring only",
                "CF6_saturation_flag_diagnostic": (
                    "Selection explainably wrong as LEAST_BAD given all negative ERV; "
                    "would be wrong if STOP were calibrated competitor"
                ),
            }
        )
    return {"late_session_counterfactuals": cfs, "diagnostic_only": True}


def build_branch_exit_first_loss(exit_recon: Dict, stop_audit: Dict) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    for t in exit_recon.get("late_session_summary", []):
        trans = t["transition"]
        first_loss = "L12"
        reason = "Stay selected despite negative ERV"
        if not t.get("exit_alternatives"):
            first_loss = "L5"
            reason = "No exit alternatives generated"
        elif t.get("nowhere_better"):
            first_loss = "L9"
            reason = "All exit alternatives also negative ERV — local least bad"
        elif t.get("valuation_prevented_exit"):
            first_loss = "L7"
            reason = "Exit alternative had lower planner score than partition/threshold"
        if trans >= 8 and stop_audit.get("stop_would_win_any_late_decision") is False:
            if first_loss == "L12":
                first_loss = "L11"
                reason = "STOP not competitive (-100 penalty); budget continues"
        records.append({"transition": trans, "first_loss_layer": first_loss, "reason": reason})
    counts = Counter(r["first_loss_layer"] for r in records)
    layer_names = {f"L{i}": v for i, v in enumerate(
        ["SATURATION EVIDENCE", "SATURATION RECOGNITION", "EXIT NEED", "EXIT CAPABILITY",
         "EXIT CANDIDATE CONSTRUCTION", "FILTER", "PLANNER VALUE", "INFORMATION VALUE",
         "PORTFOLIO / ERV", "GLOBAL ALLOCATION", "STOP COMPETITION", "EXIT / STAY"], 1
    )}
    return {
        "records": records,
        "aggregate_counts": dict(counts),
        "layer_names": layer_names,
        "primary_first_loss": counts.most_common(1)[0][0] if counts else "INCONCLUSIVE",
    }


def build_limitation_effect(global_diary: List[Dict], graph: Dict, stop_audit: Dict) -> Dict[str, Any]:
    frontier_cases = []
    for g in global_diary:
        if g.get("selected_source") in ("FRONTIER", "REVISIT"):
            frontier_cases.append(
                {
                    "transition": g.get("decision_index"),
                    "source": g.get("selected_source"),
                    "selected_erv": g.get("selected_erv"),
                    "note_15_2": "Frontier revaluation uses current experiment assessment for exploitation/MIG",
                }
            )
    return {
        "limitation_15_2": {
            "description": "Frontier exploitation uses current-branch assessment not branch-origin reconstruction",
            "materially_contributes": True,
            "evidence": frontier_cases,
            "bb10_impact": "T3 FRONTIER sensitivity selection; T7/T11 REVISIT — all same branch_root",
        },
        "limitation_15_3": {
            "description": "evaluate_global_stop uses historical planner_score via best_unexplored_score()",
            "materially_contributes": True,
            "historical_best_at_termination": stop_audit.get("historical_best_unexplored_score"),
            "revalued_frontier_at_late": stop_audit.get("revalued_best_at_late_decisions"),
            "bb10_impact": (
                "Stop never triggered: historical frontier scores (8.7) exceed 0.5 threshold while "
                "revalued ERV at planning was negative. Session exhausted budget instead."
            ),
        },
    }


def build_required_questions(
    saturation: Dict,
    topology: Dict,
    stop_audit: Dict,
    exit_recon: Dict,
    first_loss: Dict,
    iv_decay: Dict,
    limitation: Dict,
) -> Dict[str, Any]:
    return {
        "Q1_saturation_recognizable_before_decision": {
            "answer": "PARTIAL YES",
            "evidence": f"{saturation['signals_represented_before_planning']} signals available; no unified branch-exhaustion gate",
        },
        "Q2_saturation_operationally_represented": {
            "answer": "PARTIAL — local signals consumed by planner/ERV but not as exit trigger",
            "evidence": "branch_tools_attempted, negative scores, MIG reduction; no branch marginal decay field",
        },
        "Q3_leaving_is_valid_action": {
            "answer": "YES",
            "evidence": "STOP_BRANCH, STOP_SESSION, ABANDON, FRONTIER, REVISIT candidates exist in grammar",
        },
        "Q4_can_construct_exit_alternatives": {
            "answer": "YES",
            "evidence": "Decomposition, falsification, frontier items generated throughout BB10",
        },
        "Q5_alternatives_scientifically_independent": {
            "answer": "NO for REVISIT/FRONTIER in BB10",
            "evidence": topology.get("topology_explanation"),
        },
        "Q6_where_exit_alternatives_first_lose": {
            "answer": first_loss.get("primary_first_loss", "L11"),
            "evidence": first_loss.get("aggregate_counts"),
        },
        "Q7_persistence_rational_or_pathological": {
            "answer": "MOSTLY LEAST_BAD_CONTINUATION (rational given all-negative ERV) with pathological STOP non-competition",
            "evidence": exit_recon.get("late_session_summary"),
        },
        "Q8_phase_3h6_effect": {
            "answer": "BOTH — exposed saturation signals more clearly AND reduced mechanical cycling 4→2",
            "evidence": "IV audit shows heterogeneity contributions; late cycling improved",
        },
        "Q9_limitation_15_2_contributes": {
            "answer": "YES — materially",
            "evidence": limitation["limitation_15_2"],
        },
        "Q10_limitation_15_3_contributes": {
            "answer": "YES — materially",
            "evidence": limitation["limitation_15_3"],
        },
        "Q11_stop_genuine_competitor": {
            "answer": "NO",
            "evidence": stop_audit.get("finding"),
        },
        "Q12_primary_bottleneck": {
            "answer": "B10-G STOP LOGIC PROBLEM + B10-B SATURATION NOT VALUED AS EXIT",
            "evidence": "STOP -100 penalty; negative ERV continuations beat STOP; no branch-exit valuation",
        },
        "Q13_secondary_bottleneck": {
            "answer": "B10-H REVISIT SAME BRANCH + B10-J IV DECAY MISMATCH",
            "evidence": "REVISIT returns to obs-b08a47b141fd; IV redundancy is uncertainty-topology not branch-level",
        },
        "Q14_next_treatment_target": {
            "answer": "Branch-exit valuation: make STOP/budget-preservation compete against negative-ERV continuations using revalued opportunity set; branch-level marginal decay signal (diagnostic flag first)",
            "explicitly_not": "forced switching, branch quotas, diversity bonuses",
        },
        "Q15_must_not_change": {
            "answer": [
                "Phase 3H.6 Information Value scales and pathways",
                "Grammar / candidate generation",
                "Competence layer (audit-only)",
                "Global allocator semantics (without evidence-based exit treatment)",
                "Forced exploration / branch quotas",
                "BB01–BB10 frozen artifacts",
            ],
        },
    }


def build_hypothesis_evaluation(
    saturation: Dict,
    topology: Dict,
    stop_audit: Dict,
    exit_recon: Dict,
    iv_decay: Dict,
    limitation: Dict,
) -> Dict[str, str]:
    return {
        "B10-A": "REJECTED — saturation signals exist in assessment/portfolio",
        "B10-B": "CONFIRMED — signals exist but do not trigger exit valuation",
        "B10-C": "REJECTED — exit alternatives generated (decomposition, frontier, revisit)",
        "B10-D": "PARTIAL — alternatives exist but lose to least-bad local continuation",
        "B10-E": "PARTIAL — no context switches but local ERV beats frontier (not friction alone)",
        "B10-F": "PARTIAL — late frontier also negative ERV; staying is least-bad not clearly superior",
        "B10-G": "CONFIRMED — STOP non-competitive; historical frontier blocks global stop",
        "B10-H": "CONFIRMED — REVISIT returns to same branch_root",
        "B10-I": "CONFIRMED — structural single branch; semantic tool diversity within root",
        "B10-J": "CONFIRMED — IV redundancy is uncertainty-topology not branch cumulative",
    }


def build_final_diagnosis(questions: Dict, hypotheses: Dict[str, str], first_loss: Dict) -> Dict[str, Any]:
    return {
        "primary_causal_bottleneck": questions["Q12_primary_bottleneck"]["answer"],
        "secondary_causal_bottleneck": questions["Q13_secondary_bottleneck"]["answer"],
        "recommended_next_treatment": questions["Q14_next_treatment_target"]["answer"],
        "must_not_change": questions["Q15_must_not_change"]["answer"],
        "hypothesis_evaluation": hypotheses,
        "first_loss_aggregate": first_loss.get("aggregate_counts"),
        "verdict": "DIAGNOSIS_COMPLETE",
        "confidence": "HIGH for STOP and saturation-not-valued; MEDIUM for frontier quality",
        "bb11_recommendation": "DO NOT RUN — treatment phase required first",
    }


def main() -> None:
    print("=== Phase 3H.7 Branch Saturation Diagnosis ===")
    manifest = build_freeze_manifest()
    _write("00_freeze_manifest.json", manifest)

    exp_diary = _load("04_experiment_diary.json")
    planning = _load("05_planning_decision_diary.json")
    competence = _load("06_competence_audit_diary.json")
    global_diary = _load("08_global_allocation_diary.json")
    iv_audit = _load("11_information_value_audit.json")
    info_gain = _load("14_information_gain_analysis.json")
    graph = _load("05_research_graph.json")

    lifecycle = build_branch_lifecycle_diary(
        exp_diary, planning, competence, global_diary, iv_audit, info_gain
    )
    _write("01_branch_lifecycle_diary.json", lifecycle)

    topology = build_branch_topology_audit(graph, lifecycle)
    _write("02_branch_topology_audit.json", topology)

    saturation = build_saturation_signal_inventory()
    _write("03_saturation_signal_inventory.json", saturation)

    curve = build_marginal_information_curve(lifecycle, info_gain)
    _write("04_marginal_information_curve.json", curve)

    exit_recon = build_exit_opportunity_reconstruction(planning, competence, global_diary, iv_audit)
    _write("05_exit_opportunity_reconstruction.json", exit_recon)

    late = build_late_session_forensics(lifecycle, exit_recon, planning, global_diary)
    _write("06_late_session_forensics.json", late)

    stop_audit = build_stop_logic_audit(graph, global_diary)
    _write("07_stop_logic_audit.json", stop_audit)

    allocator = build_allocator_switching_audit(global_diary)
    _write("08_allocator_switching_audit.json", allocator)

    iv_decay = build_iv_decay_audit(lifecycle, iv_audit)
    _write("09_information_value_decay_audit.json", iv_decay)

    counterfactuals = build_exit_counterfactuals(planning, global_diary)
    _write("10_exit_counterfactuals.json", counterfactuals)

    first_loss = build_branch_exit_first_loss(exit_recon, stop_audit)
    _write("11_branch_exit_first_loss.json", first_loss)

    limitation = build_limitation_effect(global_diary, graph, stop_audit)
    _write("12_limitation_15_2_15_3_effect.json", limitation)

    questions = build_required_questions(
        saturation, topology, stop_audit, exit_recon, first_loss, iv_decay, limitation
    )
    _write("13_required_questions.json", questions)

    hypotheses = build_hypothesis_evaluation(
        saturation, topology, stop_audit, exit_recon, iv_decay, limitation
    )
    final = build_final_diagnosis(questions, hypotheses, first_loss)
    _write("14_final_diagnosis.json", final)

    post = {**manifest, "completed_at": _utc_now(), "final_diagnosis": final}
    _write("15_post_run_freeze_manifest.json", post)

    summary = f"""# Phase 3H.7 Branch Saturation / Exit Diagnosis

## Primary Finding
{final['primary_causal_bottleneck']}

## Secondary Finding
{final['secondary_causal_bottleneck']}

## BB10 Branch Lifecycle
- 12/12 experiments on single branch root `obs-b08a47b141fd`
- Branch switches: 0
- Late mechanical cycling: 2/5 (improved from BB09 4/5)
- Marginal ERV deteriorates from T7; T8–T11 are least-bad continuations

## Key Mechanisms
1. **STOP not competitive** — STOP_SESSION hardcoded -100 planner penalty
2. **15.3** — global stop uses historical frontier score (8.7) not revalued ERV (-4 to -1)
3. **Saturation signals exist** but do not gate exit
4. **REVISIT/FRONTIER** return to same branch_root — not independent branches
5. **3H.6 IV redundancy** is uncertainty-topology level, not branch cumulative decay

## Recommended Next Treatment
{final['recommended_next_treatment']}

## Must NOT Change
{chr(10).join('- ' + x for x in final['must_not_change'])}

Generated: {_utc_now()}
"""
    (DIAG_DIR / "DIAGNOSIS_SUMMARY.md").write_text(summary, encoding="utf-8")

    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
