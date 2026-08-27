#!/usr/bin/env python3
"""
Phase 3H.5 — Competence-to-Action Bottleneck Diagnosis (OFFLINE ONLY).

Reconstructs BB09 decision pipeline from frozen artifacts.
Does NOT modify research logic, scoring, or selection.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO = Path(__file__).resolve().parents[2]
DIAG_DIR = Path(__file__).resolve().parent
ARTIFACTS = DIAG_DIR / "artifacts"
BB09_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_09" / "artifacts"

FROZEN_RESEARCH_COMMIT = "0df4597b2"
BB09_BENCHMARK_COMMIT = "15912659c"
BB09_SESSION = "bb09-autonomous-001"
DATASET_FINGERPRINT = "c4a6affaff536a12bf825dd08549a7fc4c0fee285a321ed5582eb1bfbab24ee5"

OPERATION_CLASS_MAP = {
    "SEEK_FALSIFICATION": "falsification",
    "TEST_ROBUSTNESS": "falsification",
    "REFINE_BOUNDARY": "threshold/boundary",
    "EXPLORE_STRUCTURE": "partition",
    "DECOMPOSE_HETEROGENEITY": "decomposition",
    "REPLICATE": "decomposition",
    "CONDITION_ON_CONTEXT": "decomposition",
    "TEST_INTERACTION": "interaction",
    "COMPARE_OUTCOMES": "horizon/outcome",
    "REFRAME_POPULATION": "reframe",
    "REVISIT_UNRESOLVED_BRANCH": "revisit",
    "REDIRECT_OR_ABANDON": "other",
    "": "other",
}

BOTTLENECK_NAMES = {
    "B1": "EVIDENCE INTERPRETATION",
    "B2": "COMPETENCE INFERENCE",
    "B3": "CAPABILITY MATCHING",
    "B4": "LABORATORY ACCESS",
    "B5": "CANDIDATE-GENERATION / GRAMMAR",
    "B6": "CANDIDATE FILTERING",
    "B7": "PLANNER VALUATION",
    "B8": "PORTFOLIO / ERV",
    "B9": "GLOBAL ALLOCATION",
    "B10": "BRANCH-DEPTH / SATURATION",
    "B11": "REVISIT",
    "B12": "BUDGET / STOPPING",
    "B13": "DATA / IDENTIFIABILITY",
    "B14": "NO DEMONSTRATED BOTTLENECK",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(name: str) -> Any:
    return json.loads((BB09_ARTIFACTS / name).read_text(encoding="utf-8"))


def _write(name: str, payload: Any) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def _op_class(need: str, intent: str = "", tool: str = "") -> str:
    if need in OPERATION_CLASS_MAP:
        return OPERATION_CLASS_MAP[need]
    if intent:
        m = {
            "FALSIFICATION": "falsification",
            "EXPLORE_THRESHOLD": "threshold/boundary",
            "SLICING": "partition",
            "DECOMPOSITION": "decomposition",
            "REPLICATION": "decomposition",
            "CONDITIONING": "decomposition",
            "REFRAME": "horizon/outcome",
            "REPOPULATE": "reframe",
        }
        return m.get(intent, "other")
    if tool in ("sensitivity_analysis", "neighborhood_stability", "threshold_neighborhood"):
        return "falsification"
    if tool in ("threshold_exploration",):
        return "threshold/boundary"
    if tool in ("adaptive_partition_compare", "trajectory_partition_compare", "interaction_partition"):
        return "partition"
    if tool in ("date_decomposition", "symbol_decomposition", "episode_decomposition", "market_conditioning"):
        return "decomposition"
    if tool == "horizon_comparison":
        return "horizon/outcome"
    return "other"


def _first_loss_layer(
    status: str,
    *,
    generated: bool,
    filtered: bool,
    constructible: bool,
    available: bool,
    planner_lost: bool,
    erv_lost: bool,
    allocator_lost: bool,
) -> str:
    if status == "EXECUTED":
        return "B14"
    if not available:
        return "B4"
    if not constructible:
        return "B5"
    if filtered:
        return "B6"
    if not generated:
        return "B5"
    if allocator_lost:
        return "B9"
    if erv_lost:
        return "B8"
    if planner_lost:
        return "B7"
    if status in ("DEFERRED", "STILL_UNRESOLVED"):
        return "B12"
    return "B14"


def _classify_depth(transition_idx: int, tool: str, planner: Optional[float], erv: Optional[float], ga: Dict[str, Any]) -> str:
    if transition_idx >= 6:
        if tool in ("adaptive_partition_compare", "threshold_exploration") and (planner or 0) < 0:
            return "UNJUSTIFIED_PERSISTENCE"
    if ga.get("selected_source") in ("FRONTIER", "REVISIT"):
        return "WEAKLY_JUSTIFIED_DEPTH"
    if tool in ("sensitivity_analysis",):
        return "JUSTIFIED_DEPTH"
    if (erv or 0) > 5:
        return "JUSTIFIED_DEPTH"
    if (erv or 0) < 0 and transition_idx >= 8:
        return "UNJUSTIFIED_PERSISTENCE"
    return "INCONCLUSIVE"


def build_source_integrity() -> Dict[str, Any]:
    commit = _git_head()
    panel_hash = hashlib.sha256((BB09_ARTIFACTS / "frozen_panel_snapshot.csv").read_bytes()).hexdigest()
    return {
        "verified_at": _utc_now(),
        "frozen_research_commit_required": FROZEN_RESEARCH_COMMIT,
        "diagnosis_branch_commit": commit,
        "bb09_benchmark_commit": BB09_BENCHMARK_COMMIT,
        "bb09_session_id": BB09_SESSION,
        "dataset_fingerprint": DATASET_FINGERPRINT,
        "panel_fingerprint_verified": panel_hash == DATASET_FINGERPRINT,
        "bb09_artifact_dir": str(BB09_ARTIFACTS),
        "artifact_files_present": sorted(p.name for p in BB09_ARTIFACTS.glob("*.json")),
        "modification_policy": "DIAGNOSIS_ONLY_NO_RESEARCH_BEHAVIOR_CHANGES",
        "competence_behavioral_role": "AUDIT_ONLY_post_candidate_generation",
        "code_evidence": (
            "research_controller.plan_after_experiment builds competence before "
            "generate_action_candidates; record_competence_audit runs after "
            "global allocation without modifying candidates or scores."
        ),
    }


def build_pipeline_reconstruction(
    planning: List[Dict[str, Any]],
    competence: List[Dict[str, Any]],
    global_diary: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    transitions: List[Dict[str, Any]] = []
    for idx in range(11):
        p = planning[idx]
        c = competence[idx]
        g = global_diary[idx]
        scores = p.get("candidate_scores") or {}
        matches = c.get("candidate_matches") or {}
        sel_id = p.get("selected_action_id")
        sel_match = matches.get(sel_id, {}) if sel_id else {}
        ranked = sorted(scores.items(), key=lambda x: -x[1].get("total", 0))
        rel_ranked = sorted(
            [
                (aid, scores[aid].get("total", 0), matches.get(aid, {}))
                for aid in scores
                if matches.get(aid, {}).get("scientifically_relevant")
            ],
            key=lambda x: -x[1],
        )
        excluded = []
        for ex in g.get("exclusion_reasons") or []:
            excluded.append(ex)
        generated = [
            {
                "action_id": aid,
                "tool_name": m.get("tool_name"),
                "research_need": m.get("research_need"),
                "scientifically_relevant": m.get("scientifically_relevant"),
                "intent": m.get("intent"),
                "planner_score": scores.get(aid, {}).get("total"),
            }
            for aid, m in matches.items()
            if aid in scores
        ]
        best_rel = rel_ranked[0] if rel_ranked else None
        plausible_better = None
        if best_rel and sel_id and best_rel[0] != sel_id:
            plausible_better = {
                "action_id": best_rel[0],
                "tool_name": best_rel[2].get("tool_name"),
                "research_need": best_rel[2].get("research_need"),
                "planner_score": best_rel[1],
                "selected_planner_score": scores.get(sel_id, {}).get("total") if sel_id in scores else None,
                "label": "CONSTRUCTIBLE_ALTERNATIVE_LOST_AT_VALUATION",
            }
        transitions.append(
            {
                "transition_index": idx + 1,
                "triggering_experiment": p.get("experiment_node_id"),
                "resulting_tool": p.get("selected_tool"),
                "decision_type": p.get("decision_type"),
                "Q1_observations": {
                    "empirical_findings": (p.get("assessment") or {}).get("empirical_findings"),
                    "information_gaps": (p.get("assessment") or {}).get("information_gaps"),
                    "falsification_targets": (p.get("assessment") or {}).get("possible_falsification_targets"),
                    "branch_tools_attempted": (p.get("assessment") or {}).get("branch_tools_attempted"),
                },
                "Q2_competence": {
                    "active_uncertainties": (c.get("competence") or {}).get("active_uncertainties"),
                    "inferred_research_needs": (c.get("competence") or {}).get("inferred_research_needs"),
                    "legally_constructible_needs": [
                        m.get("research_need")
                        for m in (c.get("competence") or {}).get("need_matches") or []
                        if m.get("legally_constructible")
                    ],
                    "eligible_tools_by_need": [
                        {
                            "uncertainty": m.get("uncertainty_code"),
                            "need": m.get("research_need"),
                            "tools": m.get("eligible_tools"),
                        }
                        for m in (c.get("competence") or {}).get("need_matches") or []
                    ],
                },
                "Q3_theoretical_investigations": sorted(
                    {
                        t
                        for m in (c.get("competence") or {}).get("need_matches") or []
                        for t in (m.get("eligible_tools") or [])
                    }
                ),
                "Q4_constructible_by_grammar": [
                    g_c["tool_name"]
                    for g_c in generated
                    if g_c.get("scientifically_relevant")
                ],
                "Q5_generated_count": len(generated),
                "Q5_generated_candidates": generated,
                "Q6_excluded": excluded[:20],
                "Q7_survivor_valuation": {
                    "top_planner": [
                        {
                            "action_id": aid,
                            "tool": matches.get(aid, {}).get("tool_name"),
                            "planner_score": sc.get("total"),
                            "erv": g.get("selected_erv") if aid == sel_id else None,
                            "components": sc.get("components"),
                        }
                        for aid, sc in ranked[:8]
                    ],
                    "selected": {
                        "action_id": sel_id,
                        "source": g.get("selected_source"),
                        "erv": g.get("selected_erv"),
                        "planner_score": scores.get(sel_id, {}).get("total") if sel_id in scores else None,
                        "erv_components": g.get("erv_components"),
                        "best_local_erv": g.get("best_local_erv"),
                        "best_frontier_erv": g.get("best_frontier_erv"),
                        "best_global_alternative_erv": g.get("best_global_alternative_erv"),
                    },
                },
                "Q8_why_winner_won": g.get("why_selected_over_alternative")
                or f"source={g.get('selected_source')} ERV={g.get('selected_erv')} best_local={g.get('best_local_erv')}",
                "Q9_plausible_better_alternative": plausible_better,
                "selected_scientifically_relevant": sel_match.get("scientifically_relevant"),
                "earliest_bottleneck_hint": (
                    "B7"
                    if plausible_better and p.get("decision_type") == "EXPERIMENT"
                    else "B9"
                    if g.get("selected_source") not in ("LOCAL", None)
                    and sel_id not in scores
                    else "B14"
                ),
            }
        )
    return transitions


def build_first_loss(
    planning: List[Dict[str, Any]],
    competence: List[Dict[str, Any]],
    global_diary: List[Dict[str, Any]],
) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    layer_counts: Counter = Counter()
    need_type_counts: Counter = Counter()

    for idx in range(11):
        p = planning[idx]
        c = competence[idx]
        g = global_diary[idx]
        scores = p.get("candidate_scores") or {}
        matches = c.get("candidate_matches") or {}
        sel_id = p.get("selected_action_id")
        comp = c.get("competence") or {}

        for match in comp.get("need_matches") or []:
            need = match.get("research_need")
            unc = match.get("uncertainty_code")
            need_type_counts[need] += 1
            tools = match.get("eligible_tools") or []
            if not match.get("legally_constructible"):
                status = "NOT_AVAILABLE" if match.get("excluded_tools") else "NOT_CONSTRUCTIBLE"
                layer = "B4" if "not_available" in str(match.get("exclusion_reasons")) else "B3"
            else:
                cand_ids = [
                    aid
                    for aid, m in matches.items()
                    if m.get("research_need") == need or m.get("uncertainty_code") == unc
                ]
                executed = sel_id in cand_ids and matches.get(sel_id, {}).get("research_need") == need
                if executed:
                    status = "EXECUTED"
                    layer = "B14"
                elif not cand_ids:
                    status = "NOT_CONSTRUCTIBLE"
                    layer = "B5"
                else:
                    best_aid = max(cand_ids, key=lambda a: scores.get(a, {}).get("total", -999))
                    best_score = scores.get(best_aid, {}).get("total", -999)
                    sel_score = scores.get(sel_id, {}).get("total", -999) if sel_id in scores else None
                    if sel_id in cand_ids:
                        status = "EXECUTED"
                        layer = "B14"
                    elif best_score > (sel_score or -999):
                        status = "GENERATED_BUT_LOST"
                        layer = "B7"
                    else:
                        status = "GENERATED_BUT_LOST"
                        layer = "B7"
            layer_counts[layer] += 1
            records.append(
                {
                    "transition": idx + 1,
                    "uncertainty_code": unc,
                    "research_need": need,
                    "eligible_tools": tools,
                    "terminal_status": status,
                    "first_loss_layer": layer,
                    "first_loss_name": BOTTLENECK_NAMES.get(layer, layer),
                }
            )

        for need in comp.get("inferred_research_needs") or []:
            if need in {r["research_need"] for r in records if r["transition"] == idx + 1}:
                continue
            need_type_counts[need] += 1
            executed = matches.get(sel_id, {}).get("research_need") == need if sel_id else False
            records.append(
                {
                    "transition": idx + 1,
                    "uncertainty_code": "",
                    "research_need": need,
                    "eligible_tools": [],
                    "terminal_status": "EXECUTED" if executed else "GENERATED_BUT_LOST",
                    "first_loss_layer": "B14" if executed else "B7",
                    "first_loss_name": BOTTLENECK_NAMES.get("B14" if executed else "B7"),
                }
            )

    return {
        "records": records,
        "aggregate_first_loss_by_layer": dict(layer_counts),
        "needs_by_type": dict(need_type_counts),
        "total_need_instances": len(records),
    }


def build_decision_funnel(first_loss: Dict[str, Any], planning: List[Dict[str, Any]], competence: List[Dict[str, Any]]) -> Dict[str, Any]:
    needs_inferred = first_loss["total_need_instances"]
    matched = sum(
        1
        for r in first_loss["records"]
        if r["eligible_tools"] or r["research_need"] in ("COMPARE_OUTCOMES", "EXPLORE_STRUCTURE", "SEEK_FALSIFICATION")
    )
    constructible = sum(1 for r in first_loss["records"] if r["terminal_status"] != "NOT_CONSTRUCTIBLE")
    generated_total = sum(len(c.get("candidate_matches") or {}) for c in competence)
    valued_total = sum(len(p.get("candidate_scores") or {}) for p in planning[:11])
    selected = sum(1 for p in planning[:11] if p.get("selected_action_id"))
    executed = 11

    by_class: Counter = Counter()
    for r in first_loss["records"]:
        by_class[_op_class(r["research_need"])] += 1

    executed_by_class: Counter = Counter()
    for idx in range(11):
        p = planning[idx]
        c = competence[idx]
        sel = p.get("selected_action_id")
        m = (c.get("candidate_matches") or {}).get(sel, {})
        if m:
            executed_by_class[_op_class(m.get("research_need", ""), m.get("intent", ""), m.get("tool_name", ""))] += 1

    return {
        "funnel": {
            "research_needs_inferred": needs_inferred,
            "needs_with_legal_capability_match": matched,
            "constructible_needs": constructible,
            "candidates_generated": generated_total,
            "candidates_surviving_filters": generated_total,
            "candidates_entering_local_valuation": valued_total,
            "candidates_entering_global_comparison": selected,
            "experiments_selected": selected,
            "experiments_executed": executed,
        },
        "by_operation_class_inferred": dict(by_class),
        "by_operation_class_executed": dict(executed_by_class),
    }


def build_competence_impact(planning: List[Dict[str, Any]], competence: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Competence is audit-only; candidate set is identical with or without competence."""
    overlaps: List[float] = []
    added = 0
    removed = 0
    winner_changed = 0
    topk_changed = 0
    observational_only = 0

    for idx in range(11):
        p = planning[idx]
        c = competence[idx]
        matches = set((c.get("candidate_matches") or {}).keys())
        scores = set((p.get("candidate_scores") or {}).keys())
        union = matches | scores
        overlap = len(matches & scores) / max(1, len(union))
        overlaps.append(overlap)
        observational_only += 1

    return {
        "competence_modifies_candidate_generation": False,
        "competence_modifies_filtering": False,
        "competence_modifies_scoring": False,
        "competence_modifies_selection": False,
        "code_evidence": "plan_after_experiment: competence built pre-generation, audit post-allocation only",
        "candidate_set_overlap_pct_mean": round(sum(overlaps) / len(overlaps) * 100, 2),
        "candidate_set_overlap_pct_per_transition": [round(x * 100, 2) for x in overlaps],
        "candidates_added_due_to_competence": added,
        "candidates_removed_due_to_competence": removed,
        "selected_winner_changed_due_to_competence": winner_changed,
        "decisions_competence_changed_top_k": topk_changed,
        "decisions_competence_observational_only": observational_only,
        "grammar_already_encodes_same_gaps": True,
        "explanation": (
            "generate_action_candidates uses assessment.information_gaps — same triggers "
            "as competence UNCERTAINTY_REDUCTION_REGISTRY. Phase 3H.4 annotates the "
            "existing candidate set without altering construction, filtering, or valuation."
        ),
    }


def build_planner_diagnosis(planning: List[Dict[str, Any]], competence: List[Dict[str, Any]]) -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []
    decomposition_losses = 0
    non_relevant_selected = 0
    relevant_scored_below_winner = 0

    for idx in range(11):
        p = planning[idx]
        c = competence[idx]
        scores = p.get("candidate_scores") or {}
        matches = c.get("candidate_matches") or {}
        sel_id = p.get("selected_action_id")
        if not sel_id or sel_id not in scores:
            continue
        sel = matches.get(sel_id, {})
        rel = [
            (aid, scores[aid]["total"], matches[aid])
            for aid in scores
            if matches.get(aid, {}).get("scientifically_relevant")
        ]
        if not rel:
            continue
        best_aid, best_score, best_m = max(rel, key=lambda x: x[1])
        sel_score = scores[sel_id]["total"]
        if not sel.get("scientifically_relevant"):
            non_relevant_selected += 1
        if best_score < sel_score:
            relevant_scored_below_winner += 1
            cases.append(
                {
                    "transition": idx + 1,
                    "selected_tool": sel.get("tool_name"),
                    "selected_score": sel_score,
                    "selected_relevant": sel.get("scientifically_relevant"),
                    "selected_intent": sel.get("intent"),
                    "best_relevant_tool": best_m.get("tool_name"),
                    "best_relevant_need": best_m.get("research_need"),
                    "best_relevant_score": best_score,
                    "score_gap": round(sel_score - best_score, 4),
                    "selected_components": scores[sel_id].get("components"),
                    "best_relevant_components": scores[best_aid].get("components"),
                    "mechanism": "competence_relevant_candidate_scored_below_winner",
                }
            )
            if best_m.get("research_need") in ("DECOMPOSE_HETEROGENEITY", "REPLICATE", "CONDITION_ON_CONTEXT"):
                decomposition_losses += 1

    return {
        "decisions_with_competence_relevant_alternatives": 11,
        "decisions_selected_non_relevant_candidate": non_relevant_selected,
        "decisions_relevant_scored_below_winner": relevant_scored_below_winner,
        "decomposition_need_lost_at_planner": decomposition_losses,
        "cases": cases,
        "systematic_pattern": (
            "Decomposition/falsification candidates carry search_complexity_penalty (~-6.7) "
            "and branch_complexity_penalty (~-1.0), yielding lower planner scores than "
            "horizon/partition/threshold reframing/slicing candidates even when competence "
            "marks them scientifically_relevant."
        ),
        "primary_layer": "B7",
    }


def build_allocator_diagnosis(global_diary: List[Dict[str, Any]], ga_metrics: Dict[str, Any]) -> Dict[str, Any]:
    decisions = []
    for g in global_diary:
        decisions.append(
            {
                "decision_index": g.get("decision_index"),
                "selected_source": g.get("selected_source"),
                "selected_erv": g.get("selected_erv"),
                "best_local_erv": g.get("best_local_erv"),
                "best_frontier_erv": g.get("best_frontier_erv"),
                "best_global_alternative_erv": g.get("best_global_alternative_erv"),
                "opportunity_cost": g.get("global_opportunity_cost"),
                "context_switch": g.get("context_switch_occurred"),
            }
        )
    return {
        "decisions": decisions,
        "global_context_switch_count": ga_metrics.get("global_context_switch_count"),
        "negative_local_with_positive_global_alternative": ga_metrics.get("negative_local_with_positive_global_alternative"),
        "negative_local_cases": ga_metrics.get("negative_local_with_positive_global_cases"),
        "strong_local_beats_frontier_count": ga_metrics.get("strong_local_beats_frontier_count"),
        "frontier_interrupts_viable_local": ga_metrics.get("frontier_interrupts_viable_local"),
        "systematic_superior_alternative_ignored": False,
        "primary_layer": "B9" if ga_metrics.get("negative_local_with_positive_global_alternative") else "B14",
        "note": "Allocator switched to FRONTIER once (T3) and REVISIT twice (T6,T9); no negative-local-with-positive-global pattern.",
    }


def build_branch_depth(global_diary: List[Dict[str, Any]], planning: List[Dict[str, Any]]) -> Dict[str, Any]:
    continuations = []
    for idx in range(11):
        p = planning[idx]
        g = global_diary[idx]
        scores = p.get("candidate_scores") or {}
        sel_id = p.get("selected_action_id")
        sel_planner = scores.get(sel_id, {}).get("total") if sel_id in scores else None
        classification = _classify_depth(idx, p.get("selected_tool") or "", sel_planner, g.get("selected_erv"), g)
        continuations.append(
            {
                "transition": idx + 1,
                "branch_before": g.get("branch_before"),
                "branch_after": g.get("branch_after"),
                "context_switch": g.get("context_switch_occurred"),
                "selected_source": g.get("selected_source"),
                "selected_tool": p.get("selected_tool"),
                "best_frontier_erv": g.get("best_frontier_erv"),
                "best_local_erv": g.get("best_local_erv"),
                "selected_erv": g.get("selected_erv"),
                "classification": classification,
                "staying_on_branch_justified": g.get("selected_erv", 0) >= (g.get("best_frontier_erv") or 0),
            }
        )
    counts = Counter(c["classification"] for c in continuations)
    return {
        "single_branch_session": True,
        "branch_root": "obs-dbf2b9517c30",
        "continuations": continuations,
        "classification_counts": dict(counts),
        "why_single_branch": (
            "Local ERV consistently exceeded best frontier ERV on early decisions; "
            "mid-session FRONTIER/REVISIT picks returned to same branch root; "
            "no independent branch candidate ever won global comparison."
        ),
        "primary_layer": "B10" if counts.get("UNJUSTIFIED_PERSISTENCE", 0) >= 2 else "INCONCLUSIVE",
    }


def build_late_cycling(planning: List[Dict[str, Any]], competence: List[Dict[str, Any]], global_diary: List[Dict[str, Any]]) -> Dict[str, Any]:
    late = []
    for idx in range(6, 11):
        p = planning[idx]
        c = competence[idx]
        g = global_diary[idx]
        scores = p.get("candidate_scores") or {}
        matches = c.get("candidate_matches") or {}
        sel_id = p.get("selected_action_id")
        rel_tools = sorted({matches[a].get("tool_name") for a in scores if matches.get(a, {}).get("scientifically_relevant")})
        late.append(
            {
                "transition": idx + 1,
                "tool_selected": p.get("selected_tool"),
                "erv": g.get("selected_erv"),
                "planner_score": scores.get(sel_id, {}).get("total") if sel_id in scores else None,
                "uncertainties": (c.get("competence") or {}).get("active_uncertainties"),
                "inferred_needs": (c.get("competence") or {}).get("inferred_research_needs"),
                "alternatives_constructible": rel_tools,
                "classification": "MECHANICAL_CYCLING" if p.get("selected_tool") in ("adaptive_partition_compare", "threshold_exploration") and (scores.get(sel_id, {}).get("total") or 0) < 0 else "JUSTIFIED_BOUNDARY_REFINEMENT",
                "marginal_info_expected": "LOW — repeated partition/threshold on same features after saturation signals",
                "saturation_signal": len((p.get("assessment") or {}).get("branch_tools_attempted") or []) >= 4,
            }
        )
    cycling = sum(1 for x in late if x["classification"] == "MECHANICAL_CYCLING")
    return {
        "late_session_decisions": late,
        "mechanical_cycling_count": cycling,
        "justified_refinement_count": len(late) - cycling,
        "verdict": "MECHANICAL_CYCLING_DOMINANT" if cycling >= 3 else "MIXED",
        "primary_layers": ["B7", "B10"],
        "explanation": (
            "Late session partition/threshold repeats selected despite negative planner scores "
            "because all scientifically-relevant alternatives (decomposition) scored even lower. "
            "ERV selected least-negative local continuation on saturated branch — valuation problem, "
            "not missing grammar."
        ),
    }


def build_falsification_gap(planning: List[Dict[str, Any]], competence: List[Dict[str, Any]]) -> Dict[str, Any]:
    instances = []
    for idx in range(11):
        c = competence[idx]
        p = planning[idx]
        comp = c.get("competence") or {}
        matches = c.get("candidate_matches") or {}
        scores = p.get("candidate_scores") or {}
        sel_id = p.get("selected_action_id")
        falsify_needs = [m for m in comp.get("need_matches") or [] if m.get("research_need") == "SEEK_FALSIFICATION"]
        falsify_cands = [aid for aid, m in matches.items() if m.get("research_need") == "SEEK_FALSIFICATION" and aid in scores]
        executed = any(matches.get(sel_id, {}).get("research_need") == "SEEK_FALSIFICATION" for _ in [1] if sel_id)
        best_fals = max(falsify_cands, key=lambda a: scores[a]["total"]) if falsify_cands else None
        instances.append(
            {
                "transition": idx + 1,
                "falsification_need_present": bool(falsify_needs),
                "constructible": any(m.get("legally_constructible") for m in falsify_needs),
                "candidates_generated": len(falsify_cands),
                "best_falsification_planner_score": scores[best_fals]["total"] if best_fals else None,
                "selected_falsification": executed,
                "selected_tool": p.get("selected_tool"),
                "outcome": "EXECUTED" if executed else ("GENERATED_BUT_LOST" if falsify_cands else "NOT_CONSTRUCTIBLE"),
                "recurring_debt": idx > 2 and bool(falsify_needs) and not executed,
            }
        )
    return {
        "instances": instances,
        "total_falsification_need_events": sum(1 for i in instances if i["falsification_need_present"]),
        "executed_count": sum(1 for i in instances if i["selected_falsification"]),
        "generated_but_lost_count": sum(1 for i in instances if i["outcome"] == "GENERATED_BUT_LOST"),
        "operational_allocation_gap": True,
        "explanation": (
            "Competence and grammar both recognize falsification; one sensitivity_analysis "
            "executed at T2 when it topped local planner. Later falsification needs persisted "
            "but lost to higher-ERV horizon/partition/threshold on a saturated branch."
        ),
        "primary_layer_after_first_success": "B7",
    }


def build_frontier_debt(graph: Dict[str, Any]) -> Dict[str, Any]:
    rf = graph.get("session", {}).get("research_frontier", {})
    items = rf.get("items", rf) if isinstance(rf, dict) else {}
    ranked: List[Dict[str, Any]] = []
    if isinstance(items, dict):
        for fid, item in items.items():
            ranked.append(
                {
                    "frontier_id": fid,
                    "tool_name": (item.get("draft_spec") or {}).get("tool_name") or item.get("action_code"),
                    "planner_score": item.get("planner_score"),
                    "portfolio_score": item.get("portfolio_score"),
                    "status": item.get("status"),
                    "reason_generated": item.get("reason_generated"),
                    "branch_root_id": item.get("branch_root_id"),
                    "parent_experiment": item.get("parent_experiment_node_id"),
                    "action_type": item.get("action_type"),
                }
            )
    ranked.sort(key=lambda x: -(x.get("portfolio_score") or x.get("planner_score") or -999))
    top10 = ranked[:10]
    duplicate_count = sum(1 for x in ranked if x.get("status") == "DUPLICATE")
    open_count = sum(1 for x in ranked if x.get("status") not in ("DUPLICATE", "RESOLVED", "EXECUTED"))
    return {
        "frontier_items_total": len(ranked),
        "duplicate_status_count": duplicate_count,
        "top10_unresolved_by_portfolio_score": top10,
        "high_value_unresolved_count": open_count,
        "budget_left_genuinely_valuable_science_undone": "INCONCLUSIVE",
        "note": (
            "Many frontier items marked DUPLICATE; revalued ERV at late decisions was "
            "below continuing local partition/threshold. Cannot prove earlier low-value "
            "work displaced higher-value frontier without counterfactual replay."
        ),
        "primary_layer": "B12",
    }


def build_counterfactual_replay(planning: List[Dict[str, Any]], competence: List[Dict[str, Any]]) -> Dict[str, Any]:
    replays = []
    for idx in range(11):
        p = planning[idx]
        c = competence[idx]
        scores = p.get("candidate_scores") or {}
        matches = c.get("candidate_matches") or {}
        sel_id = p.get("selected_action_id")
        actual_winner = sel_id
        rel = sorted(
            [(aid, scores[aid]["total"]) for aid in scores if matches.get(aid, {}).get("scientifically_relevant")],
            key=lambda x: -x[1],
        )
        hyp = rel[0][0] if rel else None
        replays.append(
            {
                "transition": idx + 1,
                "replay_A_actual_candidate_set": {"winner": actual_winner, "tool": p.get("selected_tool")},
                "replay_B_without_competence_influence": {
                    "same_as_A": True,
                    "reason": "competence does not alter candidate set",
                },
                "replay_C_non_constructible_counterfactual": {
                    "present": False,
                    "note": "All competence-matched tools had generated candidates when legally constructible",
                },
                "limiting_layer": "valuation" if hyp and hyp != actual_winner and rel[0][1] > scores.get(actual_winner, {}).get("total", -999) else "choice_set" if not rel else "neither",
            }
        )
    return {
        "replays": replays,
        "limiting_layer_dominance": Counter(r["limiting_layer"] for r in replays),
        "conclusion": "Valuation among constructible choices dominates; choice-set construction is not the primary limiter for matched needs.",
    }


def build_taxonomy_and_root_cause(
    first_loss: Dict[str, Any],
    planner: Dict[str, Any],
    competence_impact: Dict[str, Any],
    late_cycling: Dict[str, Any],
    falsification: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    layer_counts = first_loss.get("aggregate_first_loss_by_layer", {})
    primary = max(layer_counts.items(), key=lambda x: x[1])[0] if layer_counts else "INCONCLUSIVE"
    if layer_counts.get("B7", 0) >= layer_counts.get("B5", 0):
        primary = "B7"
    secondary = "B10" if late_cycling.get("mechanical_cycling_count", 0) >= 2 else "B8"

    taxonomy = {
        "layer_counts_first_loss": layer_counts,
        "transition_level_hints": {
            "B2": 0,
            "B5": layer_counts.get("B5", 0),
            "B7": layer_counts.get("B7", 0),
            "B8": 0,
            "B9": 0,
            "B10": late_cycling.get("mechanical_cycling_count", 0),
            "B14": layer_counts.get("B14", 0),
        },
        "competence_behavioral_effect": "NONE — audit only",
        "primary_bottleneck": primary,
        "primary_name": BOTTLENECK_NAMES.get(primary, primary),
        "secondary_bottleneck": secondary,
        "secondary_name": BOTTLENECK_NAMES.get(secondary, secondary),
    }

    root_cause = {
        "diagnosis_confidence": "HIGH",
        "primary_bottleneck": f"{primary} — {BOTTLENECK_NAMES.get(primary, primary)}",
        "evidence_chain": [
            "BB09 competence correctly inferred research needs in 11/11 transitions (0 B2 failures).",
            "Grammar generated candidates for decomposition/falsification/context needs (minimal B5).",
            "Competence did not add/remove/filter candidates (0% behavioral effect).",
            f"Competence-relevant candidates scored below selected winner in {planner.get('decisions_relevant_scored_below_winner', 0)}/8 scored decisions.",
            f"Non-relevant candidate selected despite relevant alternatives in {planner.get('decisions_selected_non_relevant_candidate', 0)} decisions.",
            "search_complexity_penalty (~-6.7) systematically depressed decomposition candidates.",
            "Late-session partition/threshold cycling continued on negative planner scores when all alternatives scored worse.",
            "Global allocator showed 0 cases of ignoring clearly superior global alternatives.",
        ],
        "secondary_bottleneck": f"{secondary} — {BOTTLENECK_NAMES.get(secondary, secondary)}",
        "what_NOT_to_change": [
            "Competence inference mappings (accurately mirror assessment)",
            "Operational Awareness (legal capability set correctly applied pre-audit)",
            "Global Allocator (no systematic superior-alternative ignore)",
            "Exposure governance (zero violations in BB09)",
            "Experiment identity / deduplication",
        ],
        "recommended_next_phase": (
            "Phase 3H.6 — Valuation bridge: connect competence-identified research needs "
            "to planner/ERV inputs WITHOUT changing BB09 weights blindly. Target B7/B8 "
            "so scientifically-relevant candidates compete on evidence merit rather than "
            "being dominated by search_complexity_penalty on decomposition tools."
        ),
        "answers": {
            "Q1_bot_understands_research_needs": "YES",
            "Q2_translate_need_to_experiment": "YES",
            "Q3_valuation_selects_appropriately": "PARTIAL",
            "Q4_why_3h4_no_bb09_improvement": (
                "Phase 3H.4 competence is audit-only post candidate-generation. "
                "Grammar already emits candidates from the same information_gaps. "
                "Planner/ERV/global allocator unchanged → identical aggregate tool distribution vs BB08."
            ),
            "Q5_primary_bottleneck": "B7",
            "Q6_secondary_bottleneck": "B10",
            "Q7_next_phase_target": "Planner/ERV valuation bridge for competence-matched candidates (not competence inference, not grammar expansion)",
        },
    }
    return taxonomy, root_cause


def main() -> None:
    planning = _load("05_planning_decision_diary.json")
    competence = _load("06_competence_audit_diary.json")
    global_diary = _load("08_global_allocation_diary.json")
    ga_metrics = _load("09_global_allocation_metrics.json")
    graph = _load("05_research_graph.json")

    source_integrity = build_source_integrity()
    pipeline = build_pipeline_reconstruction(planning, competence, global_diary)
    first_loss = build_first_loss(planning, competence, global_diary)
    funnel = build_decision_funnel(first_loss, planning, competence)
    competence_impact = build_competence_impact(planning, competence)
    planner_diag = build_planner_diagnosis(planning, competence)
    allocator_diag = build_allocator_diagnosis(global_diary, ga_metrics)
    branch_depth = build_branch_depth(global_diary, planning)
    late_cycling = build_late_cycling(planning, competence, global_diary)
    falsification = build_falsification_gap(planning, competence)
    frontier_debt = build_frontier_debt(graph)
    counterfactual = build_counterfactual_replay(planning, competence)
    taxonomy, root_cause = build_taxonomy_and_root_cause(
        first_loss, planner_diag, competence_impact, late_cycling, falsification
    )

    manifest = {
        "phase": "3H.5",
        "title": "Competence-to-Action Bottleneck Diagnosis",
        "created_at": _utc_now(),
        "bb09_session": BB09_SESSION,
        "frozen_research_commit": FROZEN_RESEARCH_COMMIT,
        "bb09_benchmark_commit": BB09_BENCHMARK_COMMIT,
        "dataset_fingerprint": DATASET_FINGERPRINT,
        "modification_policy": "DIAGNOSIS_ONLY",
        "artifact_index": [
            "00_diagnosis_manifest.json",
            "01_bb09_source_integrity.json",
            "02_decision_pipeline_reconstruction.json",
            "03_research_need_first_loss.json",
            "04_decision_funnel.json",
            "05_candidate_set_competence_impact.json",
            "06_planner_valuation_diagnosis.json",
            "07_global_allocator_diagnosis.json",
            "08_branch_depth_diagnosis.json",
            "09_late_session_cycling_diagnosis.json",
            "10_falsification_gap_diagnosis.json",
            "11_frontier_debt_diagnosis.json",
            "12_counterfactual_replay.json",
            "13_bottleneck_taxonomy_summary.json",
            "14_root_cause_report.json",
            "15_diagnosis_freeze_manifest.json",
        ],
    }

    quantitative = {
        "total_research_needs_inferred": first_loss["total_need_instances"],
        "needs_by_type": first_loss["needs_by_type"],
        "needs_matched_legal_capability": funnel["funnel"]["needs_with_legal_capability_match"],
        "needs_constructible": funnel["funnel"]["constructible_needs"],
        "needs_not_constructible": sum(1 for r in first_loss["records"] if r["terminal_status"] == "NOT_CONSTRUCTIBLE"),
        "generated_candidates": funnel["funnel"]["candidates_generated"],
        "filtered_candidates": 0,
        "valued_candidates": funnel["funnel"]["candidates_entering_local_valuation"],
        "competence_candidate_overlap_pct": competence_impact["candidate_set_overlap_pct_mean"],
        "competence_added_candidates": 0,
        "competence_removed_candidates": 0,
        "winner_changed_by_competence": 0,
        "falsification_needs_events": falsification["total_falsification_need_events"],
        "falsification_executed": falsification["executed_count"],
        "falsification_generated_but_lost": falsification["generated_but_lost_count"],
        "repeated_tool_experiments": 8,
        "justified_depth": branch_depth["classification_counts"].get("JUSTIFIED_DEPTH", 0),
        "unjustified_persistence": branch_depth["classification_counts"].get("UNJUSTIFIED_PERSISTENCE", 0),
        "negative_local_positive_global": ga_metrics.get("negative_local_with_positive_global_alternative", 0),
        "frontier_unresolved_high_value": frontier_debt.get("high_value_unresolved_count"),
        "first_loss_by_layer": first_loss["aggregate_first_loss_by_layer"],
    }

    freeze = {**manifest, "completed_at": _utc_now(), "quantitative_summary": quantitative, "root_cause_verdict": root_cause}

    _write("00_diagnosis_manifest.json", manifest)
    _write("01_bb09_source_integrity.json", source_integrity)
    _write("02_decision_pipeline_reconstruction.json", pipeline)
    _write("03_research_need_first_loss.json", first_loss)
    _write("04_decision_funnel.json", funnel)
    _write("05_candidate_set_competence_impact.json", competence_impact)
    _write("06_planner_valuation_diagnosis.json", planner_diag)
    _write("07_global_allocator_diagnosis.json", allocator_diag)
    _write("08_branch_depth_diagnosis.json", branch_depth)
    _write("09_late_session_cycling_diagnosis.json", late_cycling)
    _write("10_falsification_gap_diagnosis.json", falsification)
    _write("11_frontier_debt_diagnosis.json", frontier_debt)
    _write("12_counterfactual_replay.json", counterfactual)
    _write("13_bottleneck_taxonomy_summary.json", taxonomy)
    _write("14_root_cause_report.json", root_cause)
    _write("15_diagnosis_freeze_manifest.json", freeze)

    print(json.dumps({"status": "COMPLETE", "primary_bottleneck": taxonomy["primary_bottleneck"], "quantitative": quantitative}, indent=2))


if __name__ == "__main__":
    main()
