#!/usr/bin/env python3
"""
Blind Benchmark 11 — Phase 3H.8 Evidence-Based Branch Exit Valuation.

Orchestration and reporting ONLY. Does NOT modify research logic.
Frozen research commit: 5c62fc334 (Phase 3H.8).
Uses SAME frozen panel fingerprint as BB01–BB10.
Run exactly once; preserve artifacts; no post-hoc repair.
"""

from __future__ import annotations

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
BB10_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_10" / "artifacts"
BB01_PANEL = BB01_ARTIFACTS / "frozen_panel_snapshot.csv"
REQUIRED_FINGERPRINT = "c4a6affaff536a12bf825dd08549a7fc4c0fee285a321ed5582eb1bfbab24ee5"

BENCHMARK_ID = "blind_benchmark_11"
BENCHMARK_VERSION = "bb11_v1"
SESSION_ID = "bb11-autonomous-001"
FROZEN_RESEARCH_COMMIT = "5c62fc334"
EXPERIMENT_BUDGET = 12
RESEARCH_CUTOFF = "2026-08-17"

sys.path.insert(0, str(REPO))

from modules.edge_research.exit_valuation_negative_control_tokens import (  # noqa: E402
    FORBIDDEN_EXIT_TOKENS,
)
from modules.edge_research.research_branch_marginal_state import (  # noqa: E402
    RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
)
from modules.edge_research.research_competence import RESEARCH_COMPETENCE_VERSION  # noqa: E402
from modules.edge_research.research_exit_valuation import (  # noqa: E402
    RESEARCH_EXIT_VALUATION_VERSION,
    validate_no_forbidden_exit_patterns,
)
from modules.edge_research.research_information_value import RESEARCH_INFORMATION_VALUE_VERSION  # noqa: E402
from modules.edge_research.research_operational_awareness import OPERATIONAL_AWARENESS_VERSION  # noqa: E402
from modules.edge_research.research_realized_information_gain import (  # noqa: E402
    RESEARCH_REALIZED_INFORMATION_GAIN_VERSION,
)
from modules.edge_research.research_state import NodeType  # noqa: E402

# Load BB07 helpers via exec with corrected paths (same pattern as BB10).
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
from modules.edge_research.research_panel_exposure import PHASE_3H2B_FIRST_CONTROLLED_FIELD  # noqa: E402

CLOSED_PROVEN_FIELDS = frozenset(
    {"health_score", "health_group", "obv_status", "health_rank", "group_rank", "volume_ratio20"}
)
FALSIFICATION_TOOLS = frozenset(
    {"sensitivity_analysis", "neighborhood_stability", "threshold_neighborhood"}
)
DECOMPOSITION_TOOLS = frozenset(
    {"date_decomposition", "symbol_decomposition", "episode_decomposition"}
)
MECHANICAL_TOOLS = frozenset({"adaptive_partition_compare", "threshold_exploration"})

STOP_QUALITY = frozenset(
    {"JUSTIFIED_STOP", "PREMATURE_STOP", "DEFENSIBLE_STOP", "MISVALUED_STOP", "INCONCLUSIVE"}
)
CONTINUE_QUALITY = frozenset(
    {
        "JUSTIFIED_CONTINUE",
        "DEFENSIBLE_CONTINUE",
        "UNJUSTIFIED_PERSISTENCE",
        "MECHANICAL_CYCLING",
        "INCONCLUSIVE",
    }
)
INTERVENTION_QUALITY = frozenset(
    {"BENEFICIAL_INTERVENTION", "HARMFUL_INTERVENTION", "DEFENSIBLE_BUT_UNPROVEN", "INCONCLUSIVE"}
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str, sort_keys=False), encoding="utf-8")


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
    if not (
        head.startswith(FROZEN_RESEARCH_COMMIT)
        or subprocess.call(
            ["git", "merge-base", "--is-ancestor", FROZEN_RESEARCH_COMMIT, head],
            cwd=REPO,
        )
        == 0
    ):
        raise SystemExit(
            f"BENCHMARK_INVALID_COMMIT: HEAD {head!r} is not descended from {FROZEN_RESEARCH_COMMIT!r}"
        )
    return head


def build_bb11_freeze_manifest(
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
                "blind_benchmark_10",
            ],
            "phases_frozen": base.get("phases_frozen", [])
            + [
                "3H.1",
                "3H.1.1",
                "3H.2A",
                "3H.2B",
                "3H.3",
                "3H.4",
                "3H.5",
                "3H.6",
                "3H.7",
                "3H.8",
            ],
            "operational_awareness_version": OPERATIONAL_AWARENESS_VERSION,
            "research_competence_version": RESEARCH_COMPETENCE_VERSION,
            "research_information_value_version": RESEARCH_INFORMATION_VALUE_VERSION,
            "research_exit_valuation_version": RESEARCH_EXIT_VALUATION_VERSION,
            "research_branch_marginal_state_version": RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
            "research_realized_information_gain_version": RESEARCH_REALIZED_INFORMATION_GAIN_VERSION,
            "session_id": SESSION_ID,
            "bb11_primary_question": (
                "Does Phase 3H.8 evidence-based branch exit valuation improve late-session "
                "scientific discipline versus BB10 while preserving allocator integrity?"
            ),
            "modification_policy": "NO_RESEARCH_LOGIC_CHANGES_BEFORE_DURING_OR_AFTER_BB11",
        }
    )
    return base


def build_run_configuration(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "session_id": SESSION_ID,
        "experiment_budget": EXPERIMENT_BUDGET,
        "research_cutoff": RESEARCH_CUTOFF,
        "frozen_research_commit": FROZEN_RESEARCH_COMMIT,
        "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
        "autonomous_research_config": manifest.get("autonomous_research_config"),
        "phase_versions": {
            "research_exit_valuation": RESEARCH_EXIT_VALUATION_VERSION,
            "research_branch_marginal_state": RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
            "research_realized_information_gain": RESEARCH_REALIZED_INFORMATION_GAIN_VERSION,
            "research_information_value": RESEARCH_INFORMATION_VALUE_VERSION,
            "research_competence": RESEARCH_COMPETENCE_VERSION,
            "operational_awareness": OPERATIONAL_AWARENESS_VERSION,
        },
        "modification_policy": manifest.get("modification_policy"),
        "configured_at": _utc_now(),
    }


def extract_session_trails(graph: Any) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "research_exit_decision_audit": list(
            getattr(graph.session, "research_exit_decision_audit", None) or []
        ),
        "research_branch_marginal_audit": list(
            getattr(graph.session, "research_branch_marginal_audit", None) or []
        ),
        "research_realized_information_gain_history": list(
            getattr(graph.session, "research_realized_information_gain_history", None) or []
        ),
        "research_information_value_audit": list(
            getattr(graph.session, "research_information_value_audit", None) or []
        ),
        "research_revalued_erv_history": list(
            getattr(graph.session, "research_revalued_erv_history", None) or []
        ),
    }


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


def build_search_accounting_report(result: Any) -> Dict[str, Any]:
    graph = result.graph
    state = graph.get_search_accounting()
    return {
        "search_accounting_version": state.version,
        "session_ledger": state.session_ledger.to_dict(),
        "branch_ledgers": {k: v.to_dict() for k, v in state.branch_ledgers.items()},
        "effective_hypotheses": state.session_ledger.effective_hypotheses,
        "experiments_executed": state.session_ledger.experiments_executed,
    }


def build_capability_awareness_audit(
    competence_trail: List[Dict[str, Any]],
    awareness: Dict[str, Any],
    planning: List[Dict[str, Any]],
) -> Dict[str, Any]:
    need_events = 0
    matched_events = 0
    for entry in competence_trail:
        comp = entry.get("competence") or {}
        for nm in comp.get("need_matches") or []:
            need_events += 1
            if nm.get("legally_constructible"):
                matched_events += 1
    return {
        "operational_awareness_version": OPERATIONAL_AWARENESS_VERSION,
        "research_competence_version": RESEARCH_COMPETENCE_VERSION,
        "competence_audit_entries": len(competence_trail),
        "planning_decisions": len(planning),
        "need_match_events": need_events,
        "legally_constructible_need_matches": matched_events,
        "awareness_final_snapshot": awareness.get("final_snapshot"),
        "awareness_audit_trail_length": len(awareness.get("audit_trail_events") or []),
        "tools_afforded": [
            ta.get("tool_name")
            for ta in ((awareness.get("final_snapshot") or {}).get("tool_affordances") or [])
        ],
    }


def build_realized_information_gain_audit(
    rig_history: List[Dict[str, Any]],
    branch_marginal: List[Dict[str, Any]],
) -> Dict[str, Any]:
    level_counts = Counter(e.get("gain_level") for e in rig_history)
    by_branch: Dict[str, List[str]] = defaultdict(list)
    for e in rig_history:
        by_branch[e.get("branch_root_id", "unknown")].append(e.get("gain_level", "UNRESOLVED"))
    marginal_levels = Counter(
        lvl
        for m in branch_marginal
        for lvl in (m.get("realized_information_gain_history") or [])
    )
    return {
        "realized_information_gain_version": RESEARCH_REALIZED_INFORMATION_GAIN_VERSION,
        "history_entries": rig_history,
        "gain_level_counts": dict(level_counts),
        "by_branch_gain_levels": {k: v for k, v in by_branch.items()},
        "branch_marginal_realized_levels": dict(marginal_levels),
        "high_or_medium_count": level_counts.get("HIGH", 0) + level_counts.get("MEDIUM", 0),
        "zero_or_unresolved_count": level_counts.get("ZERO", 0) + level_counts.get("UNRESOLVED", 0),
    }


def build_branch_marginal_state_audit(branch_marginal: List[Dict[str, Any]]) -> Dict[str, Any]:
    state_counts = Counter(m.get("marginal_state") for m in branch_marginal)
    return {
        "research_branch_marginal_state_version": RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
        "entries": branch_marginal,
        "marginal_state_counts": dict(state_counts),
        "competing_exit_state_events": sum(
            1
            for m in branch_marginal
            if m.get("marginal_state") in ("LOW_MARGINAL_VALUE", "EXHAUSTION_EVIDENCE")
        ),
    }


def _recent_gain_levels(
    rig_history: List[Dict[str, Any]], branch_root: str, limit: int = 3
) -> List[str]:
    levels = [
        e.get("gain_level", "UNRESOLVED")
        for e in rig_history
        if e.get("branch_root_id") == branch_root
    ]
    return levels[-limit:]


def classify_stop_quality(
    exit_entry: Dict[str, Any],
    planning_entry: Optional[Dict[str, Any]],
    rig_history: List[Dict[str, Any]],
) -> str:
    if not exit_entry.get("stop_won"):
        return "INCONCLUSIVE"
    marginal = exit_entry.get("branch_marginal_state", "")
    best_erv = float(exit_entry.get("best_experiment_erv") or 0)
    exit_val = exit_entry.get("exit_value")
    if exit_val in (None, float("-inf")):
        return "INCONCLUSIVE"
    recent = _recent_gain_levels(rig_history, exit_entry.get("current_branch_root_id", ""))
    high_recent = sum(1 for g in recent if g == "HIGH")
    if best_erv > 2.0 and marginal != "EXHAUSTION_EVIDENCE":
        return "PREMATURE_STOP"
    if marginal in ("LOW_MARGINAL_VALUE", "EXHAUSTION_EVIDENCE") and best_erv <= float(exit_val):
        if high_recent == 0:
            return "JUSTIFIED_STOP"
        return "DEFENSIBLE_STOP"
    if marginal == "PRODUCTIVE" and high_recent >= 2:
        return "PREMATURE_STOP"
    if exit_entry.get("stop_competed") and not exit_entry.get("selection_changed_by_exit_valuation"):
        return "MISVALUED_STOP"
    if marginal in ("LOW_MARGINAL_VALUE", "EXHAUSTION_EVIDENCE"):
        return "DEFENSIBLE_STOP"
    return "INCONCLUSIVE"


def classify_continue_quality(
    exit_entry: Dict[str, Any],
    planning_entry: Optional[Dict[str, Any]],
    rig_history: List[Dict[str, Any]],
) -> str:
    if exit_entry.get("stop_won"):
        return "INCONCLUSIVE"
    tool = (planning_entry or {}).get("selected_tool") or ""
    scores = (planning_entry or {}).get("candidate_scores") or {}
    sel_id = (planning_entry or {}).get("selected_action_id")
    sel_score = (scores.get(sel_id) or {}).get("total") if sel_id else None
    marginal = exit_entry.get("branch_marginal_state", "")
    recent = _recent_gain_levels(rig_history, exit_entry.get("current_branch_root_id", ""))
    zero_recent = sum(1 for g in recent if g in ("ZERO", "UNRESOLVED", "LOW"))

    if tool in MECHANICAL_TOOLS and (sel_score or 0) < 0:
        return "MECHANICAL_CYCLING"
    if marginal in ("EXHAUSTION_EVIDENCE", "LOW_MARGINAL_VALUE") and zero_recent >= 2 and (sel_score or 0) < 0:
        return "UNJUSTIFIED_PERSISTENCE"
    if (sel_score or 0) >= 0 or marginal == "PRODUCTIVE":
        return "JUSTIFIED_CONTINUE"
    if marginal in ("DIMINISHING", "INSUFFICIENT_EVIDENCE"):
        return "DEFENSIBLE_CONTINUE"
    if zero_recent >= 2 and (sel_score or 0) < 0:
        return "UNJUSTIFIED_PERSISTENCE"
    return "INCONCLUSIVE"


def classify_3h8_intervention(
    exit_entry: Dict[str, Any],
    planning_entry: Optional[Dict[str, Any]],
    rig_history: List[Dict[str, Any]],
) -> str:
    if not exit_entry.get("selection_changed_by_exit_valuation"):
        return "INCONCLUSIVE"
    stop_quality = classify_stop_quality(exit_entry, planning_entry, rig_history)
    if stop_quality == "JUSTIFIED_STOP":
        return "BENEFICIAL_INTERVENTION"
    if stop_quality == "PREMATURE_STOP":
        return "HARMFUL_INTERVENTION"
    if stop_quality in ("DEFENSIBLE_STOP", "MISVALUED_STOP"):
        return "DEFENSIBLE_BUT_UNPROVEN"
    return "INCONCLUSIVE"


def build_exit_valuation_diary(
    exit_audit: List[Dict[str, Any]],
    global_diary: List[Dict[str, Any]],
    revalued_erv: List[Dict[str, Any]],
    branch_marginal: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Full per-transition reconstruction from exit decision audit + global allocation diary."""
    records: List[Dict[str, Any]] = []
    marginal_by_seq = {m.get("planning_sequence"): m for m in branch_marginal}
    revalued_by_seq = {r.get("planning_sequence"): r for r in revalued_erv}
    for idx, exit_entry in enumerate(exit_audit):
        seq = exit_entry.get("planning_sequence", idx + 1)
        global_entry = global_diary[idx] if idx < len(global_diary) else {}
        marginal_entry = marginal_by_seq.get(seq) or (branch_marginal[idx] if idx < len(branch_marginal) else {})
        revalued_entry = revalued_by_seq.get(seq) or {}
        records.append(
            {
                "transition": idx + 1,
                "planning_sequence": seq,
                "branch_root_id": exit_entry.get("current_branch_root_id"),
                "branch_marginal_state": exit_entry.get("branch_marginal_state"),
                "branch_marginal_reason": exit_entry.get("branch_marginal_reason"),
                "exit_valuation": {
                    "exit_value": exit_entry.get("exit_value"),
                    "exit_value_components": exit_entry.get("exit_value_components"),
                    "best_experiment_erv": exit_entry.get("best_experiment_erv"),
                    "best_experiment_source": exit_entry.get("best_experiment_source"),
                    "best_experiment_action_id": exit_entry.get("best_experiment_action_id"),
                    "best_local_erv": exit_entry.get("best_local_erv"),
                    "best_frontier_erv": exit_entry.get("best_frontier_erv"),
                    "best_revisit_erv": exit_entry.get("best_revisit_erv"),
                    "best_deferred_erv": exit_entry.get("best_deferred_erv"),
                    "historical_best_frontier_score": exit_entry.get("historical_best_frontier_score"),
                    "remaining_budget": exit_entry.get("remaining_budget"),
                },
                "decision": {
                    "selected_action": exit_entry.get("selected_action"),
                    "stop_competed": exit_entry.get("stop_competed"),
                    "stop_won": exit_entry.get("stop_won"),
                    "why_selected": exit_entry.get("why_selected"),
                    "runner_up": exit_entry.get("runner_up"),
                    "runner_up_value": exit_entry.get("runner_up_value"),
                    "opportunity_cost": exit_entry.get("opportunity_cost"),
                    "would_pre_3h8_have_continued": exit_entry.get("would_pre_3h8_have_continued"),
                    "selection_changed_by_exit_valuation": exit_entry.get(
                        "selection_changed_by_exit_valuation"
                    ),
                    "alternative_branch_roots": exit_entry.get("alternative_branch_roots"),
                    "same_structural_branch_notes": exit_entry.get("same_structural_branch_notes"),
                },
                "global_allocation": {
                    "decision_index": global_entry.get("decision_index"),
                    "triggering_experiment_node_id": global_entry.get("triggering_experiment_node_id"),
                    "resulting_experiment_node_id": global_entry.get("resulting_experiment_node_id"),
                    "selected_source": global_entry.get("selected_source"),
                    "selected_erv": global_entry.get("selected_erv"),
                    "best_local_erv": global_entry.get("best_local_erv"),
                    "best_frontier_erv": global_entry.get("best_frontier_erv"),
                    "context_switch_occurred": global_entry.get("context_switch_occurred"),
                    "branch_before": global_entry.get("branch_before"),
                    "branch_after": global_entry.get("branch_after"),
                    "budget_remaining": global_entry.get("budget_remaining"),
                    "global_allocation": global_entry.get("global_allocation"),
                },
                "branch_marginal_snapshot": marginal_entry,
                "revalued_erv_snapshot": revalued_entry,
            }
        )
    return records


def build_stop_continue_quality_classification(
    exit_audit: List[Dict[str, Any]],
    planning: List[Dict[str, Any]],
    rig_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    decisions: List[Dict[str, Any]] = []
    stop_counts: Counter = Counter()
    continue_counts: Counter = Counter()
    for idx, exit_entry in enumerate(exit_audit):
        plan = planning[idx] if idx < len(planning) else None
        if exit_entry.get("stop_won"):
            quality = classify_stop_quality(exit_entry, plan, rig_history)
            stop_counts[quality] += 1
        else:
            quality = classify_continue_quality(exit_entry, plan, rig_history)
            continue_counts[quality] += 1
        decisions.append(
            {
                "transition": idx + 1,
                "planning_sequence": exit_entry.get("planning_sequence"),
                "stop_won": exit_entry.get("stop_won"),
                "stop_competed": exit_entry.get("stop_competed"),
                "decision_quality": quality,
                "decision_family": "STOP" if exit_entry.get("stop_won") else "CONTINUE",
                "branch_marginal_state": exit_entry.get("branch_marginal_state"),
                "selected_tool": (plan or {}).get("selected_tool"),
                "best_experiment_erv": exit_entry.get("best_experiment_erv"),
                "exit_value": exit_entry.get("exit_value"),
            }
        )
    return {
        "stop_quality_labels": sorted(STOP_QUALITY),
        "continue_quality_labels": sorted(CONTINUE_QUALITY),
        "decisions": decisions,
        "stop_quality_counts": dict(stop_counts),
        "continue_quality_counts": dict(continue_counts),
        "stop_won_count": sum(1 for e in exit_audit if e.get("stop_won")),
        "stop_competed_count": sum(1 for e in exit_audit if e.get("stop_competed")),
    }


def build_phase_3h8_counterfactual_interventions(
    exit_audit: List[Dict[str, Any]],
    planning: List[Dict[str, Any]],
    rig_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    interventions: List[Dict[str, Any]] = []
    class_counts: Counter = Counter()
    for idx, exit_entry in enumerate(exit_audit):
        plan = planning[idx] if idx < len(planning) else None
        classification = classify_3h8_intervention(exit_entry, plan, rig_history)
        if exit_entry.get("selection_changed_by_exit_valuation"):
            class_counts[classification] += 1
        interventions.append(
            {
                "transition": idx + 1,
                "planning_sequence": exit_entry.get("planning_sequence"),
                "selection_changed_by_exit_valuation": exit_entry.get(
                    "selection_changed_by_exit_valuation"
                ),
                "would_pre_3h8_have_continued": exit_entry.get("would_pre_3h8_have_continued"),
                "stop_won": exit_entry.get("stop_won"),
                "pre_3h8_action": exit_entry.get("best_experiment_action_id"),
                "post_3h8_action": exit_entry.get("selected_action"),
                "exit_value": exit_entry.get("exit_value"),
                "best_experiment_erv": exit_entry.get("best_experiment_erv"),
                "branch_marginal_state": exit_entry.get("branch_marginal_state"),
                "intervention_classification": classification,
            }
        )
    changed = [i for i in interventions if i["selection_changed_by_exit_valuation"]]
    return {
        "intervention_labels": sorted(INTERVENTION_QUALITY),
        "interventions": interventions,
        "selection_changed_count": len(changed),
        "intervention_class_counts": dict(class_counts),
        "beneficial_count": class_counts.get("BENEFICIAL_INTERVENTION", 0),
        "harmful_count": class_counts.get("HARMFUL_INTERVENTION", 0),
    }


def build_remaining_opportunity_audit(result: Any, global_diary: List[Dict[str, Any]]) -> Dict[str, Any]:
    graph = result.graph
    frontier = graph.get_frontier()
    portfolio = graph.get_portfolio_state()
    unexplored = [
        item.to_dict()
        for item in frontier.items.values()
        if item.status in ("UNEXPLORED", "DEFERRED", "ACTIVE")
    ]
    last_global = global_diary[-1] if global_diary else {}
    return {
        "session_experiments_used": graph.session.experiments_used,
        "experiment_budget": graph.session.experiment_budget,
        "budget_remaining_at_end": last_global.get("budget_remaining"),
        "frontier_unexplored_count": sum(1 for i in unexplored if i.get("status") == "UNEXPLORED"),
        "frontier_deferred_count": sum(1 for i in unexplored if i.get("status") == "DEFERRED"),
        "frontier_active_count": sum(1 for i in unexplored if i.get("status") == "ACTIVE"),
        "best_frontier_erv_at_end": last_global.get("best_frontier_erv"),
        "best_local_erv_at_end": last_global.get("best_local_erv"),
        "global_opportunity_cost_at_end": last_global.get("global_opportunity_cost"),
        "remaining_opportunities": unexplored[:50],
        "portfolio_branch_count": len(portfolio.branches),
        "session_stop_reason": graph.session.session_stop_reason,
    }


def build_candidate_anti_edge_findings(result: Any) -> Dict[str, Any]:
    candidates = bb07.collect_candidates(result)
    return {
        "candidate_discoveries": candidates.get("candidates", []),
        "anti_edge_findings": candidates.get("anti_edges", []),
        "rejected_abandoned": candidates.get("rejected_abandoned", []),
        "candidate_count": len(candidates.get("candidates", [])),
        "anti_edge_count": len(candidates.get("anti_edges", [])),
    }


def build_legality_governance_audit(result: Any, panel: pd.DataFrame) -> Dict[str, Any]:
    graph = result.graph
    violations: List[Dict[str, Any]] = []
    for e in [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT and n.experiment_spec]:
        spec = e.experiment_spec
        for key in ("feature_column", "partition_column", "temporal_feature"):
            feat = (spec.inputs or {}).get(key)
            if feat and str(feat) in CLOSED_PROVEN_FIELDS:
                violations.append({"experiment": e.node_id, "field": str(feat), "reason": "CLOSED_PROVEN_FIELD"})
            if feat and is_prohibited_feature_column(str(feat)):
                violations.append({"experiment": e.node_id, "field": str(feat), "reason": "PROHIBITED_FEATURE"})
    return {"illegal_capability_attempts": len(violations), "violations": violations, "passed": len(violations) == 0}


def build_negative_control_audit() -> Dict[str, Any]:
    hits: Dict[str, List[str]] = {}
    modules_to_scan = [
        REPO / "modules" / "edge_research" / "research_exit_valuation.py",
        REPO / "modules" / "edge_research" / "research_branch_marginal_state.py",
        REPO / "modules" / "edge_research" / "research_controller.py",
        REPO / "modules" / "edge_research" / "research_global_allocator.py",
    ]
    for mod_path in modules_to_scan:
        if not mod_path.exists():
            continue
        source = mod_path.read_text(encoding="utf-8")
        found = validate_no_forbidden_exit_patterns(source)
        if found:
            hits[str(mod_path.relative_to(REPO))] = found
    orchestration_hits = validate_no_forbidden_exit_patterns(Path(__file__).read_text(encoding="utf-8"))
    if orchestration_hits:
        hits[str(Path(__file__).relative_to(REPO))] = orchestration_hits
    return {
        "forbidden_tokens_checked": sorted(FORBIDDEN_EXIT_TOKENS),
        "scanner_vocabulary_file": "modules/edge_research/exit_valuation_negative_control_tokens.py",
        "implementation_hits": hits,
        "passed": len(hits) == 0,
        "scanned_at": _utc_now(),
    }


def load_bb10_baseline() -> Dict[str, Any]:
    bb10_summary = _load_json(BB10_ARTIFACTS / "09_run_summary.json") or {}
    bb10_late = _load_json(BB10_ARTIFACTS / "18_late_session_cycling_analysis.json") or {}
    bb10_iv = _load_json(BB10_ARTIFACTS / "11_information_value_audit.json") or []
    bb10_global = _load_json(BB10_ARTIFACTS / "08_global_allocation_diary.json") or []
    bb10_counter = _load_json(BB10_ARTIFACTS / "12_counterfactual_decision_audit.json") or {}
    exps = [n for n in (_load_json(BB10_ARTIFACTS / "05_research_graph.json") or {}).get("nodes", {}).values()]
    tool_dist: Counter = Counter()
    for node in exps:
        spec = node.get("experiment_spec") or {}
        tool = spec.get("tool_name")
        if tool:
            tool_dist[tool] += 1
    return {
        "available": bool(bb10_summary),
        "session_id": "bb10-autonomous-001",
        "experiments_used": bb10_summary.get("experiments_used"),
        "session_status": bb10_summary.get("session_status"),
        "late_mechanical_cycling": bb10_late.get("mechanical_cycling_count"),
        "bridge_changed_decisions": bb10_counter.get("bridge_changed_planner_winner_count"),
        "information_value_audit_entries": len(bb10_iv) if bb10_iv else 0,
        "global_allocation_decisions": len(bb10_global) if bb10_global else 0,
        "tool_distribution": dict(tool_dist),
        "exit_valuation_active": False,
        "stop_competed_count": 0,
        "selection_changed_by_exit_count": 0,
    }


def build_bb10_bb11_scientific_comparison(
    bb11: Dict[str, Any],
    bb10: Dict[str, Any],
    stop_continue: Dict[str, Any],
    interventions: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "bb10": bb10,
        "bb11": bb11,
        "comparison_table": {
            "experiments_executed": {"bb10": bb10.get("experiments_used"), "bb11": bb11.get("experiments_used")},
            "terminal_status": {"bb10": bb10.get("session_status"), "bb11": bb11.get("session_status")},
            "late_mechanical_cycling": {
                "bb10": bb10.get("late_mechanical_cycling"),
                "bb11": bb11.get("late_mechanical_cycling"),
            },
            "bridge_changed_decisions": {
                "bb10": bb10.get("bridge_changed_decisions"),
                "bb11": bb11.get("bridge_changed_decisions"),
            },
            "exit_valuation_active": {"bb10": False, "bb11": bb11.get("exit_valuation_active")},
            "stop_competed_count": {
                "bb10": bb10.get("stop_competed_count"),
                "bb11": bb11.get("stop_competed_count"),
            },
            "exit_selection_changes": {
                "bb10": bb10.get("selection_changed_by_exit_count"),
                "bb11": bb11.get("selection_changed_by_exit_count"),
            },
            "justified_stops_bb11": stop_continue.get("stop_quality_counts", {}).get("JUSTIFIED_STOP", 0),
            "premature_stops_bb11": stop_continue.get("stop_quality_counts", {}).get("PREMATURE_STOP", 0),
            "mechanical_cycling_bb11": stop_continue.get("continue_quality_counts", {}).get(
                "MECHANICAL_CYCLING", 0
            ),
            "beneficial_interventions_bb11": interventions.get("beneficial_count", 0),
            "harmful_interventions_bb11": interventions.get("harmful_count", 0),
            "tool_distribution": {"bb10": bb10.get("tool_distribution"), "bb11": bb11.get("tool_distribution")},
        },
        "not_comparable_fields": [
            "exit_valuation_bb10",
            "branch_marginal_state_bb10",
            "realized_information_gain_bb10",
        ],
        "primary_question": (
            "Does Phase 3H.8 exit valuation reduce late-session mechanical persistence "
            "without pathological early termination?"
        ),
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
        sel_id = p.get("selected_action_id")
        sel_score = scores.get(sel_id, {}).get("total") if sel_id in scores else None
        tool = p.get("selected_tool") or ""
        if tool in MECHANICAL_TOOLS and (sel_score or 0) < 0:
            classification = "MECHANICAL_CYCLING"
        elif tool in FALSIFICATION_TOOLS or tool in DECOMPOSITION_TOOLS:
            classification = "INFORMATION_SEEKING"
        elif (sel_score or 0) >= 0:
            classification = "JUSTIFIED_CONTINUATION"
        else:
            classification = "REDUNDANT"
        late.append(
            {
                "transition": idx + 1,
                "tool_selected": tool,
                "erv": g.get("selected_erv"),
                "planner_score": sel_score,
                "uncertainties": (c.get("competence") or {}).get("active_uncertainties"),
                "classification": classification,
            }
        )
    counts = Counter(x["classification"] for x in late)
    return {
        "late_session_decisions": late,
        "classification_counts": dict(counts),
        "mechanical_cycling_count": counts.get("MECHANICAL_CYCLING", 0),
    }


def evaluate_bb11_capability_gates(
    *,
    git_commit: str,
    fingerprint: str,
    run_error: Optional[str],
    result: Any,
    trails: Dict[str, List[Dict[str, Any]]],
    legality: Dict[str, Any],
    negative_control: Dict[str, Any],
    stop_continue: Dict[str, Any],
    interventions: Dict[str, Any],
    dedup_audit: Dict[str, Any],
    late_cycling: Dict[str, Any],
    bb10: Dict[str, Any],
) -> Dict[str, Any]:
    def gate(name: str, result_val: str, evidence: str) -> Dict[str, str]:
        return {"gate": name, "result": result_val, "evidence": evidence}

    exit_audit = trails["research_exit_decision_audit"]
    marginal = trails["research_branch_marginal_audit"]
    rig = trails["research_realized_information_gain_history"]
    iv = trails["research_information_value_audit"]

    gates: Dict[str, Dict[str, str]] = {}
    gates["A"] = gate(
        "Exit valuation active in live autonomous planning",
        "PASS" if len(exit_audit) > 0 else "FAIL",
        f"exit_audit_entries={len(exit_audit)}",
    )
    gates["B"] = gate(
        "Branch marginal state auditable at each decision",
        "PASS" if len(marginal) > 0 else "FAIL",
        f"marginal_audit_entries={len(marginal)}",
    )
    gates["C"] = gate(
        "Realized information gain history recorded",
        "PASS" if len(rig) >= result.graph.session.experiments_used - 1 else "PARTIAL",
        f"rig_entries={len(rig)} experiments={result.graph.session.experiments_used}",
    )
    stop_competed = sum(1 for e in exit_audit if e.get("stop_competed"))
    gates["D"] = gate(
        "STOP competes on same revalued basis as experiments",
        "PASS" if stop_competed > 0 else "INCONCLUSIVE",
        f"stop_competed={stop_competed}",
    )
    gates["E"] = gate(
        "No forbidden exit shortcut patterns in implementation",
        "PASS" if negative_control.get("passed") else "FAIL",
        str(negative_control.get("implementation_hits")),
    )
    gates["F"] = gate(
        "Information-value bridge remains active",
        "PASS" if len(iv) > 0 else "FAIL",
        f"iv_audit_entries={len(iv)}",
    )
    harmful = interventions.get("harmful_count", 0)
    premature = stop_continue.get("stop_quality_counts", {}).get("PREMATURE_STOP", 0)
    gates["G"] = gate(
        "Strong positive experiments can win over STOP",
        "PASS" if harmful == 0 and premature == 0 else "PARTIAL" if harmful == 0 else "FAIL",
        f"harmful={harmful} premature={premature}",
    )
    gates["H"] = gate(
        "No dominant pathological premature stops",
        "PASS" if premature <= 1 else "FAIL",
        f"premature_stops={premature}",
    )
    gates["I"] = gate(
        "Global allocator lifecycle preserved",
        "PASS"
        if result.graph.session.experiments_used == EXPERIMENT_BUDGET
        or result.graph.session.session_stop_reason
        else "FAIL",
        f"experiments={result.graph.session.experiments_used} stop_reason={result.graph.session.session_stop_reason}",
    )
    gates["J"] = gate(
        "Temporal legality / fingerprint / frozen commit preserved",
        "PASS" if git_commit.startswith(FROZEN_RESEARCH_COMMIT) and fingerprint == REQUIRED_FINGERPRINT else "FAIL",
        git_commit,
    )
    gates["K"] = gate(
        "Production isolation preserved",
        "PASS" if legality.get("passed") else "FAIL",
        str(legality.get("violations")),
    )
    gates["L"] = gate(
        "Experiment identity dedup remains functional",
        "PASS"
        if dedup_audit.get("spawn_duplicate_experiment_error_count", 0) == 0
        else "FAIL",
        f"spawn_dup_errors={dedup_audit.get('spawn_duplicate_experiment_error_count')}",
    )
    bb10_cycling = bb10.get("late_mechanical_cycling") or 99
    bb11_cycling = late_cycling.get("mechanical_cycling_count", 99)
    improved = bb11_cycling < bb10_cycling
    gates["M"] = gate(
        "Late-session scientific discipline vs BB10",
        "PASS" if improved else "PARTIAL" if bb11_cycling == bb10_cycling else "FAIL",
        f"bb10_cycling={bb10_cycling} bb11_cycling={bb11_cycling}",
    )
    if run_error:
        for k in gates:
            if gates[k]["result"] == "PASS":
                gates[k]["result"] = "INCONCLUSIVE"
    return gates


def build_session_summary(
    result: Any,
    git_commit: str,
    trails: Dict[str, List[Dict[str, Any]]],
    stop_continue: Dict[str, Any],
    interventions: Dict[str, Any],
    late_cycling: Dict[str, Any],
    gates: Dict[str, Any],
) -> Dict[str, Any]:
    graph = result.graph
    exps = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT and n.experiment_spec]
    tool_dist = Counter(e.experiment_spec.tool_name for e in exps if e.experiment_spec.tool_name)
    exit_audit = trails["research_exit_decision_audit"]
    return {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "completed_at": _utc_now(),
        "session_id": SESSION_ID,
        "frozen_research_commit": FROZEN_RESEARCH_COMMIT,
        "git_commit": git_commit,
        "session_status": graph.session.status.value,
        "session_stop_reason": graph.session.session_stop_reason,
        "experiments_used": graph.session.experiments_used,
        "experiment_budget": graph.session.experiment_budget,
        "step_count": graph.session.experiments_used,
        "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
        "tool_distribution": dict(tool_dist),
        "exit_valuation_audit_entries": len(exit_audit),
        "stop_competed_count": sum(1 for e in exit_audit if e.get("stop_competed")),
        "stop_won_count": sum(1 for e in exit_audit if e.get("stop_won")),
        "selection_changed_by_exit_count": sum(
            1 for e in exit_audit if e.get("selection_changed_by_exit_valuation")
        ),
        "branch_marginal_audit_entries": len(trails["research_branch_marginal_audit"]),
        "realized_gain_history_entries": len(trails["research_realized_information_gain_history"]),
        "information_value_audit_entries": len(trails["research_information_value_audit"]),
        "late_mechanical_cycling": late_cycling.get("mechanical_cycling_count"),
        "stop_quality_counts": stop_continue.get("stop_quality_counts"),
        "continue_quality_counts": stop_continue.get("continue_quality_counts"),
        "intervention_class_counts": interventions.get("intervention_class_counts"),
        "capability_gates": {k: v["result"] for k, v in gates.items()},
    }


def build_bb11_report(
    summary: Dict[str, Any],
    comparison: Dict[str, Any],
    stop_continue: Dict[str, Any],
    interventions: Dict[str, Any],
    gates: Dict[str, Any],
    run_error: Optional[str],
) -> str:
    lines = [
        "# Blind Benchmark 11 Report",
        "",
        f"Session: `{SESSION_ID}` | Frozen commit: `{FROZEN_RESEARCH_COMMIT}` | Completed: {summary.get('completed_at', _utc_now())}",
        "",
        "## FACT",
        "",
    ]
    if run_error:
        lines.extend(
            [
                f"- Benchmark run **failed**: `{run_error}`",
                f"- Partial experiments used: {summary.get('experiments_used', 0)}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"- Autonomous session completed with status `{summary.get('session_status')}` "
                f"({summary.get('experiments_used')}/{summary.get('experiment_budget')} experiments).",
                f"- Exit valuation audit entries: {summary.get('exit_valuation_audit_entries')}.",
                f"- STOP competed {summary.get('stop_competed_count')} times; STOP won {summary.get('stop_won_count')} times.",
                f"- Exit valuation changed selection {summary.get('selection_changed_by_exit_count')} times.",
                f"- Branch marginal audit entries: {summary.get('branch_marginal_audit_entries')}.",
                f"- Realized information gain history entries: {summary.get('realized_gain_history_entries')}.",
                f"- Dataset fingerprint verified: `{REQUIRED_FINGERPRINT[:16]}…`.",
                "",
            ]
        )

    lines.extend(
        [
            "## MEASUREMENT",
            "",
            "### Stop / Continue Quality",
            "",
            f"- Stop quality counts: `{stop_continue.get('stop_quality_counts')}`",
            f"- Continue quality counts: `{stop_continue.get('continue_quality_counts')}`",
            "",
            "### Phase 3H.8 Interventions",
            "",
            f"- Selection changed by exit valuation: {interventions.get('selection_changed_count')}",
            f"- Intervention classes: `{interventions.get('intervention_class_counts')}`",
            "",
            "### BB10 vs BB11",
            "",
        ]
    )
    table = comparison.get("comparison_table", {})
    for metric, vals in table.items():
        if isinstance(vals, dict) and "bb10" in vals and "bb11" in vals:
            lines.append(f"- {metric}: BB10={vals['bb10']} | BB11={vals['bb11']}")
    lines.extend(
        [
            "",
            "### Capability Gates (A–M)",
            "",
        ]
    )
    for gate_id in sorted(gates.keys()):
        g = gates[gate_id]
        lines.append(f"- Gate {gate_id}: **{g['result']}** — {g['gate']} ({g['evidence']})")

    lines.extend(
        [
            "",
            "## INFERENCE",
            "",
        ]
    )
    premature = stop_continue.get("stop_quality_counts", {}).get("PREMATURE_STOP", 0)
    beneficial = interventions.get("beneficial_count", 0)
    harmful = interventions.get("harmful_count", 0)
    mech_bb10 = comparison.get("comparison_table", {}).get("late_mechanical_cycling", {}).get("bb10")
    mech_bb11 = comparison.get("comparison_table", {}).get("late_mechanical_cycling", {}).get("bb11")
    if run_error:
        lines.append(
            "- Run failure prevents scientific inference; artifacts document the failure state only."
        )
    elif beneficial > 0 and harmful == 0 and (mech_bb11 or 0) <= (mech_bb10 or 99):
        lines.append(
            "- Phase 3H.8 exit valuation appears to intervene beneficially on at least one late transition "
            "without recorded harmful overrides."
        )
    elif harmful > 0:
        lines.append(
            "- At least one exit-valuation intervention is classified harmful; late-session discipline gains "
            "must be weighed against potential premature termination."
        )
    else:
        lines.append(
            "- Exit valuation machinery is active and auditable; causal improvement over BB10 is not yet established."
        )
    if premature > 0:
        lines.append(f"- {premature} PREMATURE_STOP classification(s) warrant manual review.")

    lines.extend(
        [
            "",
            "## LIMITATION",
            "",
            "- Single autonomous session (`experiment_budget=12`); no multi-seed replication.",
            "- BB10 baseline lacks live exit-valuation trails; several comparison fields are explicitly not comparable.",
            "- Stop/continue quality labels are orchestration-layer heuristics, not ground-truth human labels.",
            "- Orchestration script does not modify research modules; all inference is observational.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    print("=== BLIND BENCHMARK 11: verify frozen commit ===")
    git_commit = _verify_frozen_commit()
    print(f"Commit verified: {git_commit}")

    print("=== Load frozen panel (BB01–BB10 fingerprint) ===")
    panel = bb07.load_frozen_panel()
    print(f"Fingerprint verified: {REQUIRED_FINGERPRINT}")

    from modules.edge_research.research_panel_preflight import build_panel_preflight  # noqa: E402

    preflight = build_panel_preflight(panel).to_dict()
    inventory = bb07.build_neutral_inventory(panel)
    manifest = build_bb11_freeze_manifest(panel, inventory, preflight, git_commit)
    run_config = build_run_configuration(manifest)

    _write_json(ARTIFACTS / "00_benchmark_freeze_manifest.json", manifest)
    _write_json(ARTIFACTS / "01_run_configuration.json", run_config)

    bb07.SESSION_ID = SESSION_ID
    bb07.BENCHMARK_ID = BENCHMARK_ID

    print("=== Autonomous research session (budget=12, Phase 3H.8 @ 5c62fc334) ===")
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
        _write_json(ARTIFACTS / "02_session_summary.json", failure)
        _write_json(ARTIFACTS / "20_failure_report.json", failure)
        post_manifest = {
            **manifest,
            "completed_at": _utc_now(),
            "run_error": run_error,
            "status": "BENCHMARK_RUN_FAILED",
        }
        _write_json(ARTIFACTS / "21_post_run_freeze_manifest.json", post_manifest)
        (ARTIFACTS / "BB11_REPORT.md").write_text(
            build_bb11_report(failure, {}, {}, {}, {}, run_error),
            encoding="utf-8",
        )
        print(json.dumps(failure, indent=2))
        return

    graph = result.graph
    (ARTIFACTS / "05_research_graph.json").write_text(result.graph.serialize(), encoding="utf-8")

    diary = bb07.build_research_diary(result, result.steps)
    planning = build_planning_decision_diary(result, result.steps)
    competence = build_competence_audit_diary(graph)
    awareness = build_awareness_snapshots(graph)
    trails = extract_session_trails(graph)
    global_diary = bb07.build_global_allocation_diary(result, diary, result.steps)
    global_metrics = bb07.build_global_allocation_metrics(result, global_diary, [], {})
    frame_report = bb07.build_frame_registry_report(result)
    search_report = build_search_accounting_report(result)
    capability_audit = build_capability_awareness_audit(competence, awareness, planning)
    rig_audit = build_realized_information_gain_audit(
        trails["research_realized_information_gain_history"],
        trails["research_branch_marginal_audit"],
    )
    marginal_audit = build_branch_marginal_state_audit(trails["research_branch_marginal_audit"])
    exit_diary = build_exit_valuation_diary(
        trails["research_exit_decision_audit"],
        global_diary,
        trails["research_revalued_erv_history"],
        trails["research_branch_marginal_audit"],
    )
    stop_continue = build_stop_continue_quality_classification(
        trails["research_exit_decision_audit"], planning, trails["research_realized_information_gain_history"]
    )
    interventions = build_phase_3h8_counterfactual_interventions(
        trails["research_exit_decision_audit"], planning, trails["research_realized_information_gain_history"]
    )
    dedup_audit = bb07.build_experiment_identity_dedup_audit(global_diary, result)
    remaining = build_remaining_opportunity_audit(result, global_diary)
    candidates = build_candidate_anti_edge_findings(result)
    legality = build_legality_governance_audit(result, panel)
    negative_control = build_negative_control_audit()
    late_cycling = build_late_session_cycling_analysis(planning, competence, global_diary)
    bb10 = load_bb10_baseline()

    exps = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT and n.experiment_spec]
    tool_dist = Counter(e.experiment_spec.tool_name for e in exps if e.experiment_spec.tool_name)
    iv_counter = _load_json(BB10_ARTIFACTS / "12_counterfactual_decision_audit.json") or {}
    bb11_baseline = {
        "session_id": SESSION_ID,
        "experiments_used": graph.session.experiments_used,
        "session_status": graph.session.status.value,
        "late_mechanical_cycling": late_cycling.get("mechanical_cycling_count"),
        "bridge_changed_decisions": sum(
            1
            for iv in trails["research_information_value_audit"]
            if iv.get("selection_changed")
        ),
        "exit_valuation_active": len(trails["research_exit_decision_audit"]) > 0,
        "stop_competed_count": sum(1 for e in trails["research_exit_decision_audit"] if e.get("stop_competed")),
        "selection_changed_by_exit_count": sum(
            1 for e in trails["research_exit_decision_audit"] if e.get("selection_changed_by_exit_valuation")
        ),
        "tool_distribution": dict(tool_dist),
    }
    comparison = build_bb10_bb11_scientific_comparison(bb11_baseline, bb10, stop_continue, interventions)
    gates = evaluate_bb11_capability_gates(
        git_commit=git_commit,
        fingerprint=REQUIRED_FINGERPRINT,
        run_error=run_error,
        result=result,
        trails=trails,
        legality=legality,
        negative_control=negative_control,
        stop_continue=stop_continue,
        interventions=interventions,
        dedup_audit=dedup_audit,
        late_cycling=late_cycling,
        bb10=bb10,
    )
    summary = build_session_summary(
        result, git_commit, trails, stop_continue, interventions, late_cycling, gates
    )

    writes = {
        "02_session_summary.json": summary,
        "03_experiment_diary.json": [d for d in diary if d.get("experiment_node_id")],
        "04_research_frames.json": frame_report,
        "05_search_accounting.json": search_report,
        "06_capability_awareness_audit.json": capability_audit,
        "07_information_value_audit.json": trails["research_information_value_audit"],
        "08_realized_information_gain_audit.json": rig_audit,
        "09_branch_marginal_state_audit.json": marginal_audit,
        "10_exit_valuation_diary.json": exit_diary,
        "11_global_allocation_diary.json": global_diary,
        "12_stop_continue_quality_classification.json": stop_continue,
        "13_phase_3h8_counterfactual_interventions.json": interventions,
        "14_bb10_bb11_scientific_comparison.json": comparison,
        "15_experiment_identity_audit.json": dedup_audit,
        "16_remaining_opportunity_audit.json": remaining,
        "17_candidate_anti_edge_findings.json": candidates,
        "18_capability_gates.json": gates,
        "19_negative_control_audit.json": negative_control,
    }
    for fname, payload in writes.items():
        _write_json(ARTIFACTS / fname, payload)

    report = build_bb11_report(summary, comparison, stop_continue, interventions, gates, run_error)
    (ARTIFACTS / "BB11_REPORT.md").write_text(report, encoding="utf-8")

    artifact_index = sorted(writes.keys()) + [
        "00_benchmark_freeze_manifest.json",
        "01_run_configuration.json",
        "05_research_graph.json",
        "BB11_REPORT.md",
    ]
    post_manifest = {
        **manifest,
        "completed_at": _utc_now(),
        "run_error": run_error,
        "experiments_used": graph.session.experiments_used,
        "session_status": graph.session.status.value,
        "capability_gates": {k: v["result"] for k, v in gates.items()},
        "artifact_index": artifact_index,
    }
    _write_json(ARTIFACTS / "21_post_run_freeze_manifest.json", post_manifest)

    print("=== BB11 COMPLETE ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
