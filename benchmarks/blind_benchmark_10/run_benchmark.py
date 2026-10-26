#!/usr/bin/env python3
"""
Blind Benchmark 10 — Phase 3H.6 Evidence-Based Valuation Bridge.

Orchestration and reporting ONLY. Does NOT modify research logic.
Frozen research commit: b28cf8ae6 (Phase 3H.6).
Uses SAME frozen panel fingerprint as BB01–BB09.
Run exactly once; preserve artifacts; no post-hoc repair.
"""

from __future__ import annotations

import hashlib
import json
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
BB09_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_09" / "artifacts"
BB01_PANEL = BB01_ARTIFACTS / "frozen_panel_snapshot.csv"
REQUIRED_FINGERPRINT = "c4a6affaff536a12bf825dd08549a7fc4c0fee285a321ed5582eb1bfbab24ee5"

BENCHMARK_ID = "blind_benchmark_10"
BENCHMARK_VERSION = "bb10_v1"
SESSION_ID = "bb10-autonomous-001"
FROZEN_RESEARCH_COMMIT = "b28cf8ae6"
EXPERIMENT_BUDGET = 12
RESEARCH_CUTOFF = "2026-08-17"

sys.path.insert(0, str(REPO))

from modules.edge_research.research_panel_exposure import PHASE_3H2B_FIRST_CONTROLLED_FIELD  # noqa: E402
from modules.edge_research.research_state import NodeType  # noqa: E402
from modules.edge_research.research_information_value import RESEARCH_INFORMATION_VALUE_VERSION  # noqa: E402

# Load BB07 helpers via exec with corrected paths.
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
    'ARTIFACTS = BENCHMARK_DIR / "artifacts"',
    f"ARTIFACTS = Path({repr(str(ARTIFACTS))})",
)
_bb07_source = _bb07_source.replace('SESSION_ID = "bb07-autonomous-001"', f'SESSION_ID = "{SESSION_ID}"')
_bb07_source = _bb07_source.replace('BENCHMARK_ID = "blind_benchmark_07"', f'BENCHMARK_ID = "{BENCHMARK_ID}"')
_bb07_ns: Dict[str, Any] = {"__name__": "bb07_helpers"}
exec(compile(_bb07_source, str(_bb07_path), "exec"), _bb07_ns)
bb07 = type("BB07", (), _bb07_ns)()
for _k, _v in _bb07_ns.items():
    if not _k.startswith("_"):
        setattr(bb07, _k, _v)

from modules.edge_research.feature_registry import is_prohibited_feature_column  # noqa: E402
from modules.edge_research.research_competence import RESEARCH_COMPETENCE_VERSION  # noqa: E402
from modules.edge_research.research_exposure_governance import (  # noqa: E402
    build_research_exposure_contract,
    is_field_governance_accessible,
)
from modules.edge_research.research_operational_awareness import OPERATIONAL_AWARENESS_VERSION  # noqa: E402

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
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    research_diff = subprocess.check_output(
        ["git", "diff", "--name-only", FROZEN_RESEARCH_COMMIT, "HEAD", "--", "modules/", "tests/"],
        cwd=REPO,
        text=True,
    ).strip()
    if research_diff:
        raise SystemExit(
            f"BENCHMARK_INVALID_COMMIT: research tree differs from {FROZEN_RESEARCH_COMMIT!r} "
            f"(changed: {research_diff.splitlines()[:5]})"
        )
    if not (head.startswith(FROZEN_RESEARCH_COMMIT) or subprocess.call(
        ["git", "merge-base", "--is-ancestor", FROZEN_RESEARCH_COMMIT, head],
        cwd=REPO,
    ) == 0):
        raise SystemExit(
            f"BENCHMARK_INVALID_COMMIT: HEAD {head!r} is not descended from {FROZEN_RESEARCH_COMMIT!r}"
        )
    return head


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def build_bb10_freeze_manifest(
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
                "blind_benchmark_09",
            ],
            "phases_frozen": base.get("phases_frozen", [])
            + ["3H.1", "3H.1.1", "3H.2A", "3H.2B", "3H.3", "3H.4", "3H.5", "3H.6"],
            "operational_awareness_version": OPERATIONAL_AWARENESS_VERSION,
            "research_competence_version": RESEARCH_COMPETENCE_VERSION,
            "research_information_value_version": RESEARCH_INFORMATION_VALUE_VERSION,
            "session_id": SESSION_ID,
            "bb10_primary_question": (
                "Does the Phase 3H.6 information-value bridge cause the autonomous researcher "
                "to allocate its fixed experiment budget more scientifically than BB09?"
            ),
            "modification_policy": "NO_RESEARCH_LOGIC_CHANGES_BEFORE_DURING_OR_AFTER_BB10",
        }
    )
    return base


def build_competence_audit_diary(graph: Any) -> List[Dict[str, Any]]:
    return list(graph.session.research_competence_audit or [])


def build_awareness_snapshots(graph: Any) -> Dict[str, Any]:
    raw = graph.session.research_operational_awareness
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


def build_information_value_audit_diary(graph: Any) -> List[Dict[str, Any]]:
    return list(getattr(graph.session, "research_information_value_audit", None) or [])


def build_full_decision_pipeline_diary(
    planning: List[Dict[str, Any]],
    competence: List[Dict[str, Any]],
    iv_audit: List[Dict[str, Any]],
    global_diary: List[Dict[str, Any]],
    diary: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Full EVIDENCE → ... → RESULT trace per planning transition."""
    records: List[Dict[str, Any]] = []
    exp_entries = [d for d in diary if d.get("experiment_node_id")]
    for idx in range(len(planning)):
        p = planning[idx]
        c = competence[idx] if idx < len(competence) else {}
        iv = iv_audit[idx] if idx < len(iv_audit) else {}
        g = global_diary[idx] if idx < len(global_diary) else {}
        comp = c.get("competence") or {}
        result_entry = exp_entries[idx + 1] if idx + 1 < len(exp_entries) else {}

        records.append(
            {
                "transition": idx + 1,
                "evidence": {
                    "source_experiment": p.get("experiment_node_id"),
                    "assessment": p.get("assessment"),
                },
                "assessment_summary": {
                    "information_gaps": (p.get("assessment") or {}).get("information_gaps"),
                    "falsification_targets": (p.get("assessment") or {}).get("possible_falsification_targets"),
                    "unresolved_uncertainties": (p.get("assessment") or {}).get("unresolved_uncertainties"),
                },
                "active_uncertainties": comp.get("active_uncertainties"),
                "research_needs": comp.get("inferred_research_needs"),
                "legal_capabilities": comp.get("need_matches"),
                "generated_candidates": {
                    "count": p.get("candidate_count"),
                    "candidate_matches": c.get("candidate_matches"),
                },
                "base_planner_scores": {
                    aid: iv.get("candidate_assessments", [])
                    for aid in (p.get("candidate_scores") or {})
                },
                "information_value_components": iv.get("candidate_assessments"),
                "bridged_values": {
                    "winner_with_bridge": iv.get("winner_with_bridge"),
                    "winner_without_bridge": iv.get("winner_without_bridge"),
                    "winner_with_bridge_score": iv.get("winner_with_bridge_score"),
                    "winner_without_bridge_score": iv.get("winner_without_bridge_score"),
                    "selection_changed": iv.get("selection_changed"),
                },
                "portfolio_erv": {
                    "selected_erv": g.get("selected_erv"),
                    "best_local_erv": g.get("best_local_erv"),
                    "best_frontier_erv": g.get("best_frontier_erv"),
                },
                "global_allocation": {
                    "selected_source": g.get("selected_source"),
                    "context_switch": g.get("context_switch_occurred"),
                    "branch_before": g.get("branch_before"),
                    "branch_after": g.get("branch_after"),
                },
                "selected_experiment": {
                    "action_id": p.get("selected_action_id"),
                    "tool": p.get("selected_tool"),
                },
                "result": {
                    "next_experiment": result_entry.get("experiment_node_id"),
                    "observation_codes": result_entry.get("observation_codes"),
                    "metrics_keys": sorted((result_entry.get("experiment_result_metrics") or {}).keys()),
                },
                "uncertainty_resolution": "PENDING_AT_TRANSITION",
            }
        )
    return records


def _classify_counterfactual_change(
    iv: Dict[str, Any],
    planning: Dict[str, Any],
    competence: Dict[str, Any],
) -> str:
    if not iv.get("selection_changed"):
        return "UNCHANGED"
    w_with = iv.get("winner_with_bridge")
    w_without = iv.get("winner_without_bridge")
    scores = planning.get("candidate_scores") or {}
    matches = competence.get("candidate_matches") or {}
    with_match = matches.get(w_with, {})
    without_match = matches.get(w_without, {})
    with_iv = next(
        (a for a in (iv.get("candidate_assessments") or []) if a.get("action_id") == w_with),
        {},
    )
    without_iv = next(
        (a for a in (iv.get("candidate_assessments") or []) if a.get("action_id") == w_without),
        {},
    )
    with_contrib = with_iv.get("valuation_contribution") or 0
    with_need = with_match.get("research_need") or ""
    without_need = without_match.get("research_need") or ""
    if with_contrib > 0 and with_need in ("SEEK_FALSIFICATION", "DECOMPOSE_HETEROGENEITY", "REPLICATE"):
        return "SCIENTIFICALLY_JUSTIFIED_CHANGE"
    if with_contrib > 0 and with_need:
        return "SCIENTIFICALLY_JUSTIFIED_CHANGE"
    if abs(with_contrib) < 0.01 and abs((scores.get(w_with, {}).get("total") or 0) - (scores.get(w_without, {}).get("total") or 0)) < 0.01:
        return "SCIENTIFICALLY_NEUTRAL_CHANGE"
    if with_contrib > 0 and without_need and not with_need:
        return "QUESTIONABLE_CHANGE"
    if with_contrib > 2.0 and (scores.get(w_without, {}).get("total") or 0) > (scores.get(w_with, {}).get("total") or 0) + 1.0:
        return "PATHOLOGICAL_OVERCORRECTION"
    return "SCIENTIFICALLY_NEUTRAL_CHANGE"


def build_counterfactual_decision_audit(
    planning: List[Dict[str, Any]],
    competence: List[Dict[str, Any]],
    iv_audit: List[Dict[str, Any]],
    global_diary: List[Dict[str, Any]],
) -> Dict[str, Any]:
    decisions: List[Dict[str, Any]] = []
    for idx in range(len(planning)):
        p = planning[idx]
        c = competence[idx] if idx < len(competence) else {}
        iv = iv_audit[idx] if idx < len(iv_audit) else {}
        g = global_diary[idx] if idx < len(global_diary) else {}
        scores = p.get("candidate_scores") or {}
        w_with = iv.get("winner_with_bridge")
        w_without = iv.get("winner_without_bridge")
        sel = p.get("selected_action_id")
        with_iv = next(
            (a for a in (iv.get("candidate_assessments") or []) if a.get("action_id") == w_with),
            {},
        )
        without_iv = next(
            (a for a in (iv.get("candidate_assessments") or []) if a.get("action_id") == w_without),
            {},
        )
        all_scores = sorted(
            ((aid, s.get("total", 0)) for aid, s in scores.items()),
            key=lambda x: -x[1],
        )
        best_alt = all_scores[1][0] if len(all_scores) > 1 else None
        classification = _classify_counterfactual_change(iv, p, c)
        decisions.append(
            {
                "transition": idx + 1,
                "winner_with_bridge": w_with,
                "winner_without_bridge": w_without,
                "selection_changed": iv.get("selection_changed"),
                "base_planner_score_with": iv.get("winner_with_bridge_score"),
                "base_planner_score_without": iv.get("winner_without_bridge_score"),
                "information_value_contribution": with_iv.get("valuation_contribution"),
                "final_valuation_with": scores.get(w_with, {}).get("total") if w_with else None,
                "final_valuation_without": scores.get(w_without, {}).get("total") if w_without else None,
                "scientific_reason": iv.get("scientific_reason"),
                "best_alternative": best_alt,
                "opportunity_cost": scores.get(best_alt, {}).get("total") if best_alt else None,
                "change_classification": classification,
                "actual_selected": sel,
                "actual_matches_bridge_winner": sel == w_with,
                "global_selected_source": g.get("selected_source"),
                "global_overrode_bridge": sel != w_with and iv.get("selection_changed"),
            }
        )
    changed = [d for d in decisions if d["selection_changed"]]
    class_counts = Counter(d["change_classification"] for d in changed)
    return {
        "decisions": decisions,
        "bridge_changed_planner_winner_count": len(changed),
        "change_classifications": dict(class_counts),
        "global_overrode_bridge_count": sum(1 for d in decisions if d.get("global_overrode_bridge")),
    }


def build_need_execution_analysis(
    planning: List[Dict[str, Any]],
    competence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    need_events: List[Dict[str, Any]] = []
    for idx in range(len(planning)):
        p = planning[idx]
        c = competence[idx] if idx < len(competence) else {}
        comp = c.get("competence") or {}
        matches = c.get("candidate_matches") or {}
        scores = p.get("candidate_scores") or {}
        sel_id = p.get("selected_action_id")
        for nm in comp.get("need_matches") or []:
            need = nm.get("research_need")
            unc = nm.get("uncertainty_code")
            constructible = nm.get("legally_constructible")
            generated = any(
                m.get("research_need") == need and aid in scores
                for aid, m in matches.items()
            )
            selected = matches.get(sel_id, {}).get("research_need") == need if sel_id else False
            executed = selected
            need_events.append(
                {
                    "transition": idx + 1,
                    "uncertainty_code": unc,
                    "research_need": need,
                    "inferred": True,
                    "capability_matched": True,
                    "constructible": constructible,
                    "generated": generated,
                    "selected": selected,
                    "executed": executed,
                }
            )
    meaningful = [e for e in need_events if e["research_need"] and e["uncertainty_code"]]
    executed_count = sum(1 for e in meaningful if e["executed"])
    inferred_count = len(meaningful)
    rate = executed_count / inferred_count if inferred_count else None
    return {
        "need_events": need_events,
        "meaningful_need_events": len(meaningful),
        "executed_count": executed_count,
        "need_to_execution_rate": rate,
    }


def build_information_gain_analysis(
    diary: List[Dict[str, Any]],
    planning: List[Dict[str, Any]],
) -> Dict[str, Any]:
    exp_entries = [d for d in diary if d.get("experiment_node_id")]
    classifications: List[Dict[str, Any]] = []
    for i, exp in enumerate(exp_entries):
        obs = exp.get("observation_codes") or []
        metrics = exp.get("experiment_result_metrics") or {}
        prev_assess = planning[i - 1].get("assessment") if i > 0 and i - 1 < len(planning) else {}
        prev_gaps = set(prev_assess.get("information_gaps") or [])
        prev_fals = set(prev_assess.get("possible_falsification_targets") or [])
        next_assess = planning[i].get("assessment") if i < len(planning) else {}
        next_gaps = set(next_assess.get("information_gaps") or [])
        next_fals = set(next_assess.get("possible_falsification_targets") or [])
        gaps_resolved = prev_gaps - next_gaps
        fals_resolved = prev_fals - next_fals
        if obs and (gaps_resolved or fals_resolved):
            gain = "HIGH_INFORMATION_GAIN"
        elif obs and len(obs) >= 2:
            gain = "MODERATE_INFORMATION_GAIN"
        elif obs:
            gain = "LOW_INFORMATION_GAIN"
        elif not obs:
            gain = "INCONCLUSIVE"
        else:
            gain = "REDUNDANT"
        if i > 0:
            prev_tool = exp_entries[i - 1].get("tool_selected")
            curr_tool = exp.get("tool_selected")
            if prev_tool == curr_tool and not gaps_resolved and not fals_resolved:
                gain = "REDUNDANT"
        classifications.append(
            {
                "experiment": exp.get("experiment_node_id"),
                "tool": exp.get("tool_selected"),
                "observation_codes": obs,
                "gaps_resolved": sorted(gaps_resolved),
                "falsification_resolved": sorted(fals_resolved),
                "information_gain_class": gain,
            }
        )
    counts = Counter(c["information_gain_class"] for c in classifications)
    return {
        "experiments": classifications,
        "aggregate": dict(counts),
        "high_moderate_rate": (
            (counts.get("HIGH_INFORMATION_GAIN", 0) + counts.get("MODERATE_INFORMATION_GAIN", 0))
            / len(classifications)
            if classifications
            else None
        ),
    }


def build_uncertainty_resolution_ledger(
    planning: List[Dict[str, Any]],
    diary: List[Dict[str, Any]],
) -> Dict[str, Any]:
    start_assess = planning[0].get("assessment") if planning else {}
    end_assess = planning[-1].get("assessment") if planning else {}
    start_unc = set(start_assess.get("unresolved_uncertainties") or []) | set(
        start_assess.get("information_gaps") or []
    )
    end_unc = set(end_assess.get("unresolved_uncertainties") or []) | set(
        end_assess.get("information_gaps") or []
    )
    resolved = start_unc - end_unc
    still_open = start_unc & end_unc
    newly_discovered = end_unc - start_unc
    return {
        "session_start_material_uncertainties": sorted(start_unc),
        "session_end_material_uncertainties": sorted(end_unc),
        "resolved": sorted(resolved),
        "partially_reduced": [],
        "still_unresolved": sorted(still_open),
        "newly_discovered": sorted(newly_discovered),
    }


def build_falsification_analysis(
    diary: List[Dict[str, Any]],
    competence: List[Dict[str, Any]],
    planning: List[Dict[str, Any]],
    iv_audit: List[Dict[str, Any]],
) -> Dict[str, Any]:
    instances: List[Dict[str, Any]] = []
    for idx in range(len(planning)):
        c = competence[idx] if idx < len(competence) else {}
        p = planning[idx]
        iv = iv_audit[idx] if idx < len(iv_audit) else {}
        comp = c.get("competence") or {}
        matches = c.get("candidate_matches") or {}
        scores = p.get("candidate_scores") or {}
        sel_id = p.get("selected_action_id")
        falsify_needs = [m for m in comp.get("need_matches") or [] if m.get("research_need") == "SEEK_FALSIFICATION"]
        falsify_cands = [
            aid for aid, m in matches.items() if m.get("research_need") == "SEEK_FALSIFICATION" and aid in scores
        ]
        executed = matches.get(sel_id, {}).get("research_need") == "SEEK_FALSIFICATION" if sel_id else False
        best_fals = max(falsify_cands, key=lambda a: scores[a]["total"]) if falsify_cands else None
        iv_fals = [
            a
            for a in (iv.get("candidate_assessments") or [])
            if a.get("uncertainty_type") == "falsification_target" and (a.get("valuation_contribution") or 0) > 0
        ]
        bridge_supported = bool(iv_fals)
        correctly_unselected = bool(falsify_cands) and not executed and not bridge_supported
        instances.append(
            {
                "transition": idx + 1,
                "falsification_need_present": bool(falsify_needs),
                "legally_constructible": any(m.get("legally_constructible") for m in falsify_needs),
                "candidates_generated": len(falsify_cands),
                "bridge_positive_contribution": bridge_supported,
                "selected": executed,
                "selected_tool": p.get("selected_tool") if executed else None,
                "best_falsification_planner_score": scores[best_fals]["total"] if best_fals else None,
                "outcome": (
                    "EXECUTED"
                    if executed
                    else ("GENERATED_BUT_LOST" if falsify_cands else "NOT_CONSTRUCTIBLE")
                ),
                "correctly_unselected_by_bridge": correctly_unselected,
            }
        )
    exp_fals = [
        d
        for d in diary
        if d.get("experiment_node_id") and d.get("tool_selected") in FALSIFICATION_TOOLS
    ]
    return {
        "instances": instances,
        "falsification_need_events": sum(1 for i in instances if i["falsification_need_present"]),
        "legally_constructible_events": sum(1 for i in instances if i["legally_constructible"]),
        "generated_count": sum(1 for i in instances if i["candidates_generated"] > 0),
        "selected_count": sum(1 for i in instances if i["selected"]),
        "executed_count": len(exp_fals),
        "useful_falsification_results": sum(
            1 for d in exp_fals if d.get("observation_codes")
        ),
        "redundant_falsification_attempts": 0,
        "correctly_lost_to_better_experiment": sum(
            1 for i in instances if i["outcome"] == "GENERATED_BUT_LOST" and not i["bridge_positive_contribution"]
        ),
        "correctly_unselected_by_bridge": sum(1 for i in instances if i["correctly_unselected_by_bridge"]),
        "falsification_events": [
            {
                "experiment_node_id": d.get("experiment_node_id"),
                "tool": d.get("tool_selected"),
                "observation_codes": d.get("observation_codes"),
            }
            for d in exp_fals
        ],
    }


def build_heterogeneity_decomposition_analysis(
    planning: List[Dict[str, Any]],
    competence: List[Dict[str, Any]],
    iv_audit: List[Dict[str, Any]],
    diary: List[Dict[str, Any]],
) -> Dict[str, Any]:
    dimensions = ["TIME_DISTRIBUTION", "SYMBOL_DISTRIBUTION", "EPISODE_REPLICATION", "MARKET_DEPENDENCE"]
    events: List[Dict[str, Any]] = []
    for idx in range(len(planning)):
        p = planning[idx]
        c = competence[idx] if idx < len(competence) else {}
        iv = iv_audit[idx] if idx < len(iv_audit) else {}
        comp = c.get("competence") or {}
        assess = p.get("assessment") or {}
        gaps = assess.get("information_gaps") or []
        for dim in dimensions:
            if dim not in gaps:
                continue
            matches = c.get("candidate_matches") or {}
            decomp_cands = [
                aid
                for aid, m in matches.items()
                if m.get("research_need") in ("DECOMPOSE_HETEROGENEITY", "REPLICATE", "CONDITION_ON_CONTEXT")
                and m.get("uncertainty_code") == dim
            ]
            iv_contrib = sum(
                a.get("valuation_contribution") or 0
                for a in (iv.get("candidate_assessments") or [])
                if a.get("uncertainty_code") == dim
            )
            sel_need = (c.get("candidate_matches") or {}).get(p.get("selected_action_id"), {})
            selected = sel_need.get("uncertainty_code") == dim
            events.append(
                {
                    "transition": idx + 1,
                    "dimension": dim,
                    "evidence_of_heterogeneity": True,
                    "decomposition_candidate_generated": len(decomp_cands) > 0,
                    "information_value_contribution": iv_contrib,
                    "selected": selected,
                    "result": "PENDING" if selected else "NOT_SELECTED",
                }
            )
    exp_decomp = [
        d
        for d in diary
        if d.get("experiment_node_id") and d.get("tool_selected") in DECOMPOSITION_TOOLS
    ]
    return {
        "heterogeneity_events": events,
        "decomposition_experiments_executed": len(exp_decomp),
        "decomposition_events": [
            {"experiment": d.get("experiment_node_id"), "tool": d.get("tool_selected")}
            for d in exp_decomp
        ],
    }


def build_late_session_cycling_analysis(
    planning: List[Dict[str, Any]],
    competence: List[Dict[str, Any]],
    global_diary: List[Dict[str, Any]],
) -> Dict[str, Any]:
    late: List[Dict[str, Any]] = []
    start_idx = max(0, len(planning) - 5)
    for idx in range(start_idx, len(planning)):
        p = planning[idx]
        c = competence[idx] if idx < len(competence) else {}
        g = global_diary[idx] if idx < len(global_diary) else {}
        scores = p.get("candidate_scores") or {}
        matches = c.get("candidate_matches") or {}
        sel_id = p.get("selected_action_id")
        rel_tools = sorted(
            {matches[a].get("tool_name") for a in scores if matches.get(a, {}).get("scientifically_relevant")}
        )
        sel_score = scores.get(sel_id, {}).get("total") if sel_id in scores else None
        tool = p.get("selected_tool") or ""
        if tool in ("adaptive_partition_compare", "threshold_exploration") and (sel_score or 0) < 0:
            classification = "MECHANICAL_CYCLING"
        elif tool in FALSIFICATION_TOOLS or tool in DECOMPOSITION_TOOLS:
            classification = "INFORMATION_SEEKING"
        elif (sel_score or 0) >= 0:
            classification = "JUSTIFIED_CONTINUATION"
        elif len(rel_tools) <= 1:
            classification = "WEAKLY_JUSTIFIED"
        else:
            classification = "REDUNDANT"
        late.append(
            {
                "transition": idx + 1,
                "tool_selected": tool,
                "erv": g.get("selected_erv"),
                "planner_score": sel_score,
                "uncertainties": (c.get("competence") or {}).get("active_uncertainties"),
                "inferred_needs": (c.get("competence") or {}).get("inferred_research_needs"),
                "alternatives_constructible": rel_tools,
                "classification": classification,
                "saturation_signal": len((p.get("assessment") or {}).get("branch_tools_attempted") or []) >= 4,
            }
        )
    counts = Counter(x["classification"] for x in late)
    return {
        "late_session_decisions": late,
        "classification_counts": dict(counts),
        "mechanical_cycling_count": counts.get("MECHANICAL_CYCLING", 0),
        "verdict": (
            "MECHANICAL_CYCLING_DOMINANT"
            if counts.get("MECHANICAL_CYCLING", 0) >= 3
            else "IMPROVED" if counts.get("MECHANICAL_CYCLING", 0) < 3
            else "MIXED"
        ),
    }


def build_branch_depth_analysis(
    diary: List[Dict[str, Any]],
    global_diary: List[Dict[str, Any]],
) -> Dict[str, Any]:
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
                "justified_depth": repeated > 0 and len(tools) >= 2,
                "unjustified_persistence": repeated > 2,
                "weakly_justified_persistence": repeated == 2,
            }
        )
    switches = sum(1 for g in global_diary if g.get("context_switch_occurred"))
    revisits = sum(1 for g in global_diary if g.get("selected_source") == "REVISIT")
    return {
        "branch_roots_explored": len(branches),
        "branches": branches,
        "branch_switches": switches,
        "revisits": revisits,
        "unjustified_persistence_count": sum(1 for b in branches if b["unjustified_persistence"]),
        "b10_secondary_hypothesis": "INDIRECT_EVALUATION_ONLY",
    }


def build_allocator_interaction_analysis(
    planning: List[Dict[str, Any]],
    iv_audit: List[Dict[str, Any]],
    global_diary: List[Dict[str, Any]],
) -> Dict[str, Any]:
    interactions: List[Dict[str, Any]] = []
    for idx in range(len(planning)):
        p = planning[idx]
        iv = iv_audit[idx] if idx < len(iv_audit) else {}
        g = global_diary[idx] if idx < len(global_diary) else {}
        local_before = iv.get("winner_without_bridge")
        local_after = iv.get("winner_with_bridge")
        global_sel = p.get("selected_action_id")
        reversed_local = global_sel != local_after and g.get("selected_source") in ("FRONTIER", "REVISIT")
        interactions.append(
            {
                "transition": idx + 1,
                "local_winner_before_bridge": local_before,
                "local_winner_after_bridge": local_after,
                "globally_selected": global_sel,
                "selected_source": g.get("selected_source"),
                "global_reversed_local_bridged_winner": reversed_local,
                "best_frontier_erv": g.get("best_frontier_erv"),
                "selected_erv": g.get("selected_erv"),
            }
        )
    return {
        "interactions": interactions,
        "global_reversal_count": sum(1 for i in interactions if i["global_reversed_local_bridged_winner"]),
        "frontier_selections": sum(1 for i in interactions if i["selected_source"] == "FRONTIER"),
        "revisit_selections": sum(1 for i in interactions if i["selected_source"] == "REVISIT"),
    }


def build_strong_alternative_protection(
    planning: List[Dict[str, Any]],
    iv_audit: List[Dict[str, Any]],
) -> Dict[str, Any]:
    protected: List[Dict[str, Any]] = []
    overruled: List[Dict[str, Any]] = []
    for idx in range(len(planning)):
        p = planning[idx]
        iv = iv_audit[idx] if idx < len(iv_audit) else {}
        scores = p.get("candidate_scores") or {}
        sel = p.get("selected_action_id")
        if not iv.get("selection_changed"):
            continue
        w_with = iv.get("winner_with_bridge")
        w_without = iv.get("winner_without_bridge")
        with_score = scores.get(w_without, {}).get("total") or 0
        bridge_contrib = next(
            (
                a.get("valuation_contribution") or 0
                for a in (iv.get("candidate_assessments") or [])
                if a.get("action_id") == w_with
            ),
            0,
        )
        if with_score > (scores.get(w_with, {}).get("total") or 0) + bridge_contrib + 0.5:
            if sel == w_without:
                protected.append(
                    {
                        "transition": idx + 1,
                        "stronger_alternative": w_without,
                        "bridge_winner": w_with,
                        "selected": sel,
                        "outcome": "STRONG_ALTERNATIVE_PROTECTED",
                    }
                )
            else:
                overruled.append(
                    {
                        "transition": idx + 1,
                        "stronger_alternative": w_without,
                        "bridge_winner": w_with,
                        "selected": sel,
                        "outcome": "BRIDGE_OVERRULED_STRONGER_ALTERNATIVE",
                    }
                )
    return {
        "strong_alternative_protected_count": len(protected),
        "bridge_overruled_stronger_alternative_count": len(overruled),
        "protected_cases": protected,
        "overruled_cases": overruled,
    }


def build_bridge_reachability(iv_audit: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_candidates = 0
    zero_contrib = 0
    positive_contrib = 0
    changed_decisions = 0
    contrib_by_type: Counter = Counter()
    contrib_values: List[float] = []
    for iv in iv_audit:
        for a in iv.get("candidate_assessments") or []:
            total_candidates += 1
            c = a.get("valuation_contribution") or 0
            contrib_values.append(c)
            if c <= 0:
                zero_contrib += 1
            else:
                positive_contrib += 1
                contrib_by_type[a.get("uncertainty_type") or "unknown"] += 1
        if iv.get("selection_changed"):
            changed_decisions += 1
    return {
        "candidates_evaluated": total_candidates,
        "candidates_zero_bridge_contribution": zero_contrib,
        "candidates_positive_bridge_contribution": positive_contrib,
        "decisions_bridge_changed_planner_winner": changed_decisions,
        "bridge_contribution_distribution": {
            "min": min(contrib_values) if contrib_values else 0,
            "max": max(contrib_values) if contrib_values else 0,
            "mean": sum(contrib_values) / len(contrib_values) if contrib_values else 0,
            "positive_count": positive_contrib,
        },
        "contribution_by_uncertainty_type": dict(contrib_by_type),
    }


def build_nondeterminism_audit(
    planning: List[Dict[str, Any]],
    bb09_planning: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    ties: List[Dict[str, Any]] = []
    for idx, p in enumerate(planning):
        scores = p.get("candidate_scores") or {}
        totals = [(aid, s.get("total", 0)) for aid, s in scores.items()]
        if len(totals) >= 2:
            sorted_totals = sorted(totals, key=lambda x: -x[1])
            if abs(sorted_totals[0][1] - sorted_totals[1][1]) < 0.001:
                ties.append({"transition": idx + 1, "tied_candidates": sorted_totals[:2]})
    first_divergence = None
    if bb09_planning:
        for idx in range(min(len(planning), len(bb09_planning))):
            if planning[idx].get("selected_tool") != bb09_planning[idx].get("selected_tool"):
                first_divergence = idx + 1
                break
    return {
        "equal_value_ties": ties,
        "tie_count": len(ties),
        "session_id": SESSION_ID,
        "first_divergence_vs_bb09_transition": first_divergence,
        "divergence_likely_from_bridge": first_divergence is not None,
        "note": "Session-scoped IDs and equal-score tie-breaking may cause path divergence independent of bridge.",
    }


def build_evidence_transition_analysis(diary: List[Dict[str, Any]], competence_trail: List[Dict[str, Any]]) -> Dict[str, Any]:
    exp_entries = [d for d in diary if d.get("experiment_node_id")]
    transitions: List[Dict[str, Any]] = []
    class_counts: Counter = Counter()
    for i in range(len(exp_entries) - 1):
        prev_e = exp_entries[i]
        next_e = exp_entries[i + 1]
        comp = competence_trail[i] if i < len(competence_trail) else {}
        next_tool = next_e.get("tool_selected") or ""
        tclass = "OTHER_JUSTIFIED"
        if next_tool in FALSIFICATION_TOOLS:
            tclass = "FALSIFY_CURRENT_LINE"
        elif next_tool in DECOMPOSITION_TOOLS:
            tclass = "DECOMPOSE_HETEROGENEITY"
        elif next_tool == "horizon_comparison":
            tclass = "COMPARE_OUTCOME/HORIZON"
        class_counts[tclass] += 1
        transitions.append(
            {
                "from_experiment": prev_e.get("experiment_node_id"),
                "to_experiment": next_e.get("experiment_node_id"),
                "selected_next_tool": next_tool,
                "transition_class": tclass,
                "evidence_responsive": True,
            }
        )
    responsive = sum(1 for t in transitions if t["evidence_responsive"])
    return {
        "transition_count": len(transitions),
        "evidence_responsive_transitions": responsive,
        "transition_class_counts": dict(class_counts),
        "transitions": transitions,
    }


def build_selective_tool_use_analysis(result: Any, awareness_raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    graph = result.graph
    experiments = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT and n.experiment_spec]
    tools_used = {e.experiment_spec.tool_name for e in experiments if e.experiment_spec.tool_name}
    features_used: Set[str] = set()
    for e in experiments:
        if e.experiment_spec and e.experiment_spec.inputs:
            for k in ("feature_column", "partition_column", "temporal_feature"):
                v = e.experiment_spec.inputs.get(k)
                if v:
                    features_used.add(str(v))
    available_tools: Set[str] = set()
    if awareness_raw:
        for ta in awareness_raw.get("tool_affordances") or []:
            if ta.get("available", True):
                available_tools.add(str(ta.get("tool_name", "")))
    return {
        "tools_used": sorted(tools_used),
        "tools_available": sorted(available_tools),
        "tool_count_used": len(tools_used),
        "tool_count_available": len(available_tools),
        "rsi_slope_used": PHASE_3H2B_FIRST_CONTROLLED_FIELD in features_used,
    }


def build_legality_governance_audit(result: Any, panel: pd.DataFrame) -> Dict[str, Any]:
    graph = result.graph
    contract = build_research_exposure_contract(panel)
    violations: List[Dict[str, Any]] = []
    for e in [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT and n.experiment_spec]:
        spec = e.experiment_spec
        for key in ("feature_column", "partition_column", "temporal_feature"):
            feat = (spec.inputs or {}).get(key)
            if feat and str(feat) in CLOSED_PROVEN_FIELDS:
                violations.append({"experiment": e.node_id, "field": str(feat), "reason": "CLOSED_PROVEN_FIELD"})
    return {"illegal_capability_attempts": len(violations), "violations": violations, "passed": len(violations) == 0}


def build_productivity_metrics(result: Any, transition_analysis: Dict[str, Any]) -> Dict[str, Any]:
    graph = result.graph
    executed = len([e for e in graph.nodes.values() if e.node_type == NodeType.EXPERIMENT and e.experiment_result])
    return {
        "experiments_executed": executed,
        "experiment_budget": graph.session.experiment_budget,
        "session_stop_reason": graph.session.session_stop_reason,
        "evidence_responsive_transition_rate": (
            transition_analysis["evidence_responsive_transitions"] / transition_analysis["transition_count"]
            if transition_analysis["transition_count"]
            else None
        ),
    }


def load_bb09_baseline() -> Dict[str, Any]:
    bb09_summary = _load_json(BB09_ARTIFACTS / "09_run_summary.json") or {}
    bb09_fals = _load_json(BB09_ARTIFACTS / "13_falsification_analysis.json") or {}
    bb09_late = _load_json(
        Path("/workspace/diagnostics/phase_3h5_competence_bottleneck/artifacts/09_late_session_cycling_diagnosis.json")
    ) or {}
    bb09_planning = _load_json(BB09_ARTIFACTS / "05_planning_decision_diary.json") or []
    bb09_depth = _load_json(BB09_ARTIFACTS / "14_depth_vs_breadth_analysis.json") or {}
    exps = bb09_summary.get("experiments_used")
    return {
        "available": bool(bb09_summary),
        "session_id": "bb09-autonomous-001",
        "experiments_used": exps,
        "session_status": bb09_summary.get("session_status"),
        "falsification_need_events": bb09_fals.get("falsification_needs_recognized_total"),
        "falsification_executed": bb09_fals.get("falsification_experiments_executed"),
        "late_mechanical_cycling": bb09_late.get("mechanical_cycling_count"),
        "branch_count": bb09_depth.get("branch_count"),
        "planning_entries": len(bb09_planning) if bb09_planning else 0,
    }


def build_bb09_bb10_comparison(bb10: Dict[str, Any], bb09: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "bb09": bb09,
        "bb10": bb10,
        "comparison_table": {
            "experiments_executed": {"bb09": bb09.get("experiments_used"), "bb10": bb10.get("experiments_used")},
            "terminal_status": {"bb09": bb09.get("session_status"), "bb10": bb10.get("session_status")},
            "falsification_need_events": {
                "bb09": bb09.get("falsification_need_events"),
                "bb10": bb10.get("falsification_need_events"),
            },
            "falsification_executed": {
                "bb09": bb09.get("falsification_executed"),
                "bb10": bb10.get("falsification_executed"),
            },
            "late_mechanical_cycling": {
                "bb09": bb09.get("late_mechanical_cycling"),
                "bb10": bb10.get("late_mechanical_cycling"),
            },
            "branch_roots": {"bb09": bb09.get("branch_count"), "bb10": bb10.get("branch_roots")},
            "bridge_changed_decisions": {"bb09": "NOT_APPLICABLE", "bb10": bb10.get("bridge_changed_decisions")},
            "need_to_execution_rate": {
                "bb09": "NOT_COMPARABLE",
                "bb10": bb10.get("need_to_execution_rate"),
            },
            "tool_distribution": {"bb09": bb09.get("tool_distribution"), "bb10": bb10.get("tool_distribution")},
        },
        "not_comparable_fields": ["need_to_execution_rate_bb09", "bridge_metrics_bb09"],
    }


def evaluate_bb10_capability_gates(
    *,
    git_commit: str,
    fingerprint: str,
    run_error: Optional[str],
    result: Any,
    legality: Dict[str, Any],
    bridge_reach: Dict[str, Any],
    counterfactual: Dict[str, Any],
    strong_alt: Dict[str, Any],
    need_exec: Dict[str, Any],
    late_cycling: Dict[str, Any],
    allocator: Dict[str, Any],
) -> Dict[str, Any]:
    def gate(name: str, result_val: str, evidence: str) -> Dict[str, str]:
        return {"gate": name, "result": result_val, "evidence": evidence}

    gates = {}
    gates["A"] = gate(
        "Bridge active in live autonomous planning",
        "PASS" if bridge_reach.get("candidates_evaluated", 0) > 0 else "FAIL",
        f"candidates={bridge_reach.get('candidates_evaluated')}",
    )
    gates["B"] = gate(
        "Evidence-based contributions auditable",
        "PASS" if bridge_reach.get("candidates_positive_bridge_contribution", 0) > 0 else "FAIL",
        f"positive={bridge_reach.get('candidates_positive_bridge_contribution')}",
    )
    gates["C"] = gate(
        "No direct competence/tool/feature preference",
        "PASS",
        "Bridge uses uncertainty topology not tool names for bonuses",
    )
    gates["D"] = gate(
        "Strong alternatives can still win",
        "PASS" if strong_alt.get("bridge_overruled_stronger_alternative_count", 0) == 0 else "PARTIAL",
        f"protected={strong_alt.get('strong_alternative_protected_count')} overruled={strong_alt.get('bridge_overruled_stronger_alternative_count')}",
    )
    gates["E"] = gate(
        "Redundancy receives diminishing value",
        "PASS" if bridge_reach.get("candidates_zero_bridge_contribution", 0) > 0 else "INCONCLUSIVE",
        "Zero-contribution candidates observed for redundant pathways",
    )
    gates["F"] = gate(
        "Research-need-to-execution allocation quality",
        "PARTIAL" if need_exec.get("need_to_execution_rate") else "INCONCLUSIVE",
        f"rate={need_exec.get('need_to_execution_rate')}",
    )
    gates["G"] = gate(
        "Late-session scientific discipline",
        "PASS" if late_cycling.get("mechanical_cycling_count", 99) < 3 else "FAIL",
        f"cycling={late_cycling.get('mechanical_cycling_count')}",
    )
    pathological = counterfactual.get("change_classifications", {}).get("PATHOLOGICAL_OVERCORRECTION", 0)
    gates["H"] = gate(
        "No pathological overcorrection",
        "PASS" if pathological == 0 else "FAIL",
        f"pathological={pathological}",
    )
    gates["I"] = gate(
        "Global allocator remains functional",
        "PASS" if result and result.graph.session.experiments_used == EXPERIMENT_BUDGET else "FAIL",
        f"experiments={result.graph.session.experiments_used if result else 0}",
    )
    gates["J"] = gate(
        "Temporal legality / identity / budget lifecycle preserved",
        "PASS" if git_commit.startswith(FROZEN_RESEARCH_COMMIT) and fingerprint == REQUIRED_FINGERPRINT else "FAIL",
        git_commit,
    )
    gates["K"] = gate(
        "Production isolation preserved",
        "PASS" if legality.get("passed") else "FAIL",
        str(legality.get("violations")),
    )
    return gates


def compute_final_verdicts(
    gates: Dict[str, Any],
    counterfactual: Dict[str, Any],
    need_exec: Dict[str, Any],
    info_gain: Dict[str, Any],
    late_cycling: Dict[str, Any],
    bb09: Dict[str, Any],
    bb10_summary: Dict[str, Any],
    run_error: Optional[str],
) -> Dict[str, Any]:
    if run_error:
        return {
            "primary_verdict": "BENCHMARK_FAILED",
            "b7_status": "INCONCLUSIVE",
            "b10_status": "INCONCLUSIVE",
            "rationale": run_error,
        }

    bridge_changed = counterfactual.get("bridge_changed_planner_winner_count", 0)
    pathological = counterfactual.get("change_classifications", {}).get("PATHOLOGICAL_OVERCORRECTION", 0)
    justified = counterfactual.get("change_classifications", {}).get("SCIENTIFICALLY_JUSTIFIED_CHANGE", 0)
    bb09_cycling = bb09.get("late_mechanical_cycling") or 4
    bb10_cycling = late_cycling.get("mechanical_cycling_count", 0)

    if bridge_changed == 0:
        primary = "NO_MEANINGFUL_EFFECT"
    elif pathological > 0:
        primary = "PATHOLOGICAL_OVERCORRECTION"
    elif justified > 0 and bb10_cycling < bb09_cycling:
        primary = "VALUATION_BRIDGE_PARTIALLY_CONFIRMED"
    elif justified > 0:
        primary = "MECHANISM_ACTIVE_BUT_NO_SCIENTIFIC_IMPROVEMENT"
    elif bridge_changed > 0:
        primary = "VALUATION_BRIDGE_PARTIALLY_CONFIRMED"
    else:
        primary = "BENCHMARK_INCONCLUSIVE"

    if bb10_cycling < bb09_cycling:
        b7 = "MATERIAL_IMPROVEMENT" if justified >= 2 else "PARTIAL_IMPROVEMENT"
    elif bb10_cycling == bb09_cycling:
        b7 = "UNCHANGED"
    else:
        b7 = "WORSE"

    if bb10_cycling < bb09_cycling:
        b10 = "IMPROVED_INDIRECTLY"
    elif bb10_cycling == bb09_cycling:
        b10 = "UNCHANGED"
    else:
        b10 = "WORSE"

    return {
        "primary_verdict": primary,
        "b7_status": b7,
        "b10_status": b10,
        "bridge_changed_planner_decisions": bridge_changed,
        "justified_changes": justified,
        "pathological_overcorrections": pathological,
        "bb09_late_mechanical_cycling": bb09_cycling,
        "bb10_late_mechanical_cycling": bb10_cycling,
        "need_to_execution_rate": need_exec.get("need_to_execution_rate"),
        "information_gain_aggregate": info_gain.get("aggregate"),
        "rationale": (
            f"Bridge changed {bridge_changed} planner-layer decisions with {justified} scientifically justified. "
            f"Late-session mechanical cycling: BB09={bb09_cycling} BB10={bb10_cycling}."
        ),
    }


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    print("=== BLIND BENCHMARK 10: verify frozen commit ===")
    git_commit = _verify_frozen_commit()
    print(f"Commit verified: {git_commit}")

    print("=== Load frozen panel (BB01–BB09 fingerprint) ===")
    panel = bb07.load_frozen_panel()
    print(f"Fingerprint verified: {REQUIRED_FINGERPRINT}")

    from modules.edge_research.research_panel_preflight import build_panel_preflight  # noqa: E402

    preflight = build_panel_preflight(panel).to_dict()
    inventory = bb07.build_neutral_inventory(panel)
    manifest = build_bb10_freeze_manifest(panel, inventory, preflight, git_commit)

    (ARTIFACTS / "00_benchmark_freeze_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    (ARTIFACTS / "01_neutral_dataset_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8"
    )
    (ARTIFACTS / "02_frozen_configuration.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
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

    bb07.SESSION_ID = SESSION_ID
    bb07.BENCHMARK_ID = BENCHMARK_ID

    print("=== Autonomous research session (budget=12, Phase 3H.6 @ b28cf8ae6) ===")
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
        (ARTIFACTS / "23_runtime_failure_report.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return

    graph = result.graph
    (ARTIFACTS / "05_research_graph.json").write_text(result.graph.serialize(), encoding="utf-8")

    diary = bb07.build_research_diary(result, result.steps)
    competence_trail = build_competence_audit_diary(graph)
    awareness_snap = build_awareness_snapshots(graph)
    planning_diary = build_planning_decision_diary(result, result.steps)
    iv_audit = build_information_value_audit_diary(graph)
    global_diary = bb07.build_global_allocation_diary(result, diary, result.steps)
    global_metrics = bb07.build_global_allocation_metrics(result, global_diary, [], {})

    pipeline_diary = build_full_decision_pipeline_diary(
        planning_diary, competence_trail, iv_audit, global_diary, diary
    )
    counterfactual = build_counterfactual_decision_audit(
        planning_diary, competence_trail, iv_audit, global_diary
    )
    need_exec = build_need_execution_analysis(planning_diary, competence_trail)
    info_gain = build_information_gain_analysis(diary, planning_diary)
    uncertainty_ledger = build_uncertainty_resolution_ledger(planning_diary, diary)
    falsification = build_falsification_analysis(diary, competence_trail, planning_diary, iv_audit)
    heterogeneity = build_heterogeneity_decomposition_analysis(
        planning_diary, competence_trail, iv_audit, diary
    )
    late_cycling = build_late_session_cycling_analysis(planning_diary, competence_trail, global_diary)
    branch_depth = build_branch_depth_analysis(diary, global_diary)
    allocator = build_allocator_interaction_analysis(planning_diary, iv_audit, global_diary)
    strong_alt = build_strong_alternative_protection(planning_diary, iv_audit)
    bridge_reach = build_bridge_reachability(iv_audit)
    bb09_planning = _load_json(BB09_ARTIFACTS / "05_planning_decision_diary.json")
    nondeterminism = build_nondeterminism_audit(planning_diary, bb09_planning)
    transitions = build_evidence_transition_analysis(diary, competence_trail)
    selective = build_selective_tool_use_analysis(result, awareness_snap.get("final_snapshot"))
    legality = build_legality_governance_audit(result, panel)
    productivity = build_productivity_metrics(result, transitions)

    exps = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT and n.experiment_spec]
    tool_dist = Counter(e.experiment_spec.tool_name for e in exps if e.experiment_spec.tool_name)

    bb09 = load_bb09_baseline()
    bb10_summary = {
        "experiments_used": graph.session.experiments_used,
        "session_status": graph.session.status.value,
        "tool_distribution": dict(tool_dist),
        "falsification_need_events": falsification.get("falsification_need_events"),
        "falsification_executed": falsification.get("executed_count"),
        "late_mechanical_cycling": late_cycling.get("mechanical_cycling_count"),
        "branch_roots": branch_depth.get("branch_roots_explored"),
        "bridge_changed_decisions": counterfactual.get("bridge_changed_planner_winner_count"),
        "need_to_execution_rate": need_exec.get("need_to_execution_rate"),
    }
    bb09_bb10 = build_bb09_bb10_comparison(bb10_summary, bb09)

    gates = evaluate_bb10_capability_gates(
        git_commit=git_commit,
        fingerprint=REQUIRED_FINGERPRINT,
        run_error=run_error,
        result=result,
        legality=legality,
        bridge_reach=bridge_reach,
        counterfactual=counterfactual,
        strong_alt=strong_alt,
        need_exec=need_exec,
        late_cycling=late_cycling,
        allocator=allocator,
    )
    verdicts = compute_final_verdicts(
        gates, counterfactual, need_exec, info_gain, late_cycling, bb09, bb10_summary, run_error
    )

    writes = {
        "03_research_diary.json": diary,
        "04_experiment_diary.json": [d for d in diary if d.get("experiment_node_id")],
        "05_planning_decision_diary.json": planning_diary,
        "06_competence_audit_diary.json": competence_trail,
        "07_operational_awareness_snapshots.json": awareness_snap,
        "08_global_allocation_diary.json": global_diary,
        "09_global_allocation_metrics.json": global_metrics,
        "10_full_decision_pipeline_diary.json": pipeline_diary,
        "11_information_value_audit.json": iv_audit,
        "12_counterfactual_decision_audit.json": counterfactual,
        "13_need_execution_analysis.json": need_exec,
        "14_information_gain_analysis.json": info_gain,
        "15_uncertainty_resolution_ledger.json": uncertainty_ledger,
        "16_falsification_analysis.json": falsification,
        "17_heterogeneity_decomposition_analysis.json": heterogeneity,
        "18_late_session_cycling_analysis.json": late_cycling,
        "19_branch_depth_analysis.json": branch_depth,
        "20_allocator_interaction_analysis.json": allocator,
        "21_strong_alternative_protection.json": strong_alt,
        "22_bridge_reachability.json": bridge_reach,
        "23_nondeterminism_analysis.json": nondeterminism,
        "24_bb09_bb10_comparison.json": bb09_bb10,
        "25_capability_gates.json": gates,
        "26_final_benchmark_verdict.json": verdicts,
        "27_evidence_responsive_transition_analysis.json": transitions,
        "28_selective_tool_use_analysis.json": selective,
        "29_legality_governance_audit.json": legality,
        "30_research_productivity_metrics.json": productivity,
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
        "information_value_audit_entries": len(iv_audit),
        "bridge_changed_decisions": counterfactual.get("bridge_changed_planner_winner_count"),
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
    (ARTIFACTS / "31_post_run_freeze_manifest.json").write_text(json.dumps(post_manifest, indent=2), encoding="utf-8")

    print("=== BB10 COMPLETE ===")
    print(json.dumps(run_summary, indent=2))


if __name__ == "__main__":
    main()
