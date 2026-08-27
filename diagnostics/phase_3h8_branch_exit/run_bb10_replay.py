#!/usr/bin/env python3
"""
Phase 3H.8 — BB10 offline counterfactual exit-valuation replay.

Replays frozen BB10 planning/allocation evidence through branch marginal state
and exit valuation. Does NOT execute BB11 or mutate BB10 artifacts.
"""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
BB10_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_10" / "artifacts"
OUT_DIR = Path(__file__).resolve().parent / "artifacts"

sys.path.insert(0, str(REPO))

from modules.edge_research.exit_valuation_negative_control_tokens import (  # noqa: E402
    FORBIDDEN_EXIT_TOKENS,
)
from modules.edge_research.research_assessment import ResearchAssessment  # noqa: E402
from modules.edge_research.research_branch_marginal_state import (  # noqa: E402
    RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
    build_branch_marginal_state,
    record_revalued_erv_snapshot,
)
from modules.edge_research.research_exit_valuation import (  # noqa: E402
    RESEARCH_EXIT_VALUATION_VERSION,
    compute_research_exit_value,
    evaluate_exit_vs_experiment,
    validate_no_forbidden_exit_patterns,
)
from modules.edge_research.research_frontier import ResearchFrontier, evaluate_global_stop  # noqa: E402
from modules.edge_research.research_realized_information_gain import (  # noqa: E402
    RESEARCH_REALIZED_INFORMATION_GAIN_VERSION,
    RealizedGainLevel,
    record_realized_information_gain,
    RealizedInformationGain,
)

PHASE = "phase_3h8_branch_exit"
FROZEN_BB10 = "22b1d0e4e"
FROZEN_3H6 = "b28cf8ae6"
FROZEN_3H7 = "6125150b7"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO)
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _load(name: str) -> Any:
    return json.loads((BB10_ARTIFACTS / name).read_text(encoding="utf-8"))


def _gain_level_from_bb10(class_name: str) -> str:
    mapping = {
        "HIGH_INFORMATION_GAIN": RealizedGainLevel.HIGH.value,
        "MODERATE_INFORMATION_GAIN": RealizedGainLevel.MEDIUM.value,
        "LOW_INFORMATION_GAIN": RealizedGainLevel.LOW.value,
        "REDUNDANT": RealizedGainLevel.ZERO.value,
        "ZERO_INFORMATION_GAIN": RealizedGainLevel.ZERO.value,
    }
    return mapping.get(class_name, RealizedGainLevel.UNRESOLVED.value)


def _assessment_from_planning(entry: Dict[str, Any]) -> ResearchAssessment:
    a = entry.get("assessment") or {}
    return ResearchAssessment(
        source_experiment_node_id=entry.get("experiment_node_id", ""),
        tool_name=a.get("tool_name", ""),
        tool_status=a.get("tool_status", "OK"),
        empirical_findings=tuple(a.get("empirical_findings") or []),
        unresolved_uncertainties=tuple(a.get("unresolved_uncertainties") or []),
        contradictions=tuple(a.get("contradictions") or []),
        concentration_concerns=tuple(a.get("concentration_concerns") or []),
        replication_concerns=tuple(a.get("replication_concerns") or []),
        fragility_evidence=tuple(a.get("fragility_evidence") or []),
        context_dependence=tuple(a.get("context_dependence") or []),
        horizon_dependence=tuple(a.get("horizon_dependence") or []),
        information_gaps=tuple(a.get("information_gaps") or []),
        possible_falsification_targets=tuple(a.get("possible_falsification_targets") or []),
        descriptive_strength=a.get("descriptive_strength", "NO_CLEAR_DIFFERENCE"),
        interpretation_confidence=a.get("interpretation_confidence", "HIGH"),
        additional_investigation_warranted=bool(a.get("additional_investigation_warranted")),
        interesting=bool(a.get("interesting")),
        validated=bool(a.get("validated")),
        actionable=bool(a.get("actionable")),
        branch_tools_attempted=tuple(a.get("branch_tools_attempted") or []),
        branch_observation_codes=tuple(a.get("branch_observation_codes") or []),
        observation_kind=a.get("observation_kind", ""),
        conditional_candidate=bool(a.get("conditional_candidate")),
    )


class ReplayGraph:
    """Minimal graph shell for offline replay."""

    def __init__(self) -> None:
        from modules.edge_research.research_graph import ResearchGraph

        self._inner = ResearchGraph.create_session(
            session_id="bb10-exit-replay",
            data_cutoff_date="2026-08-17",
            experiment_budget=12,
        )
        self._inner.session.panel_preflight = {"eligible_explanatory": list("abcdefgh")}

    @property
    def session(self) -> Any:
        return self._inner.session

    def get_portfolio_state(self) -> Any:
        return self._inner.get_portfolio_state()

    def persist_portfolio_state(self) -> None:
        self._inner.persist_portfolio_state()

    def get_frontier(self) -> ResearchFrontier:
        return self._inner.get_frontier()

    def get_frame_registry(self) -> Any:
        return self._inner.get_frame_registry()

    def get_node(self, node_id: str) -> Any:
        return self._inner.get_node(node_id) if node_id in self._inner.nodes else None

    def get_search_accounting(self) -> Any:
        return self._inner.get_search_accounting()


def _best_global_experiment_erv(alloc: Dict[str, Any]) -> float:
    ga = alloc.get("global_allocation") or {}
    opps = ga.get("all_opportunities") or []
    best = float("-inf")
    for o in opps:
        if not o.get("comparable", True):
            continue
        intent = (o.get("action_candidate") or {}).get("intent", "")
        if intent in ("STOP", "STOP_SESSION", "ABANDON"):
            continue
        val = float(o.get("expected_research_value", float("-inf")))
        if val > best:
            best = val
    if best == float("-inf"):
        return float(alloc.get("selected_erv", 0))
    return best


def _historical_best_frontier(alloc: Dict[str, Any]) -> float:
    ga = alloc.get("global_allocation") or {}
    best = 0.0
    for o in ga.get("all_opportunities") or []:
        if o.get("source") == "FRONTIER":
            best = max(best, float(o.get("historical_planner_score", 0)))
    return best


def replay_bb10() -> Dict[str, Any]:
    planning = _load("05_planning_decision_diary.json")
    allocation = _load("08_global_allocation_diary.json")
    info_gain = _load("14_information_gain_analysis.json")
    gain_by_exp = {
        e["experiment"]: _gain_level_from_bb10(e.get("information_gain_class", ""))
        for e in info_gain.get("experiments", [])
    }

    graph = ReplayGraph()
    branch_root = "obs-b08a47b141fd"
    transitions: List[Dict[str, Any]] = []
    late_audit: Dict[str, Any] = {}
    selection_changes = 0
    stop_wins = 0
    stop_competed = 0
    early_unchanged = 0

    for idx, alloc in enumerate(allocation):
        decision_index = alloc.get("decision_index", idx + 1)
        plan = planning[idx] if idx < len(planning) else {}
        assessment = _assessment_from_planning(plan)
        branch_root = alloc.get("branch_before") or branch_root
        exp_count = idx + 1

        portfolio = graph.get_portfolio_state()
        branch_rec = portfolio.get_branch(branch_root)
        branch_rec.experiments_on_branch = exp_count
        portfolio.sequence_counter = decision_index
        graph.persist_portfolio_state()

        triggering = alloc.get("triggering_experiment_node_id", "")
        if triggering and triggering in gain_by_exp:
            record_realized_information_gain(
                graph,
                RealizedInformationGain(
                    version=RESEARCH_REALIZED_INFORMATION_GAIN_VERSION,
                    experiment_node_id=triggering,
                    branch_root_id=branch_root,
                    gain_level=gain_by_exp[triggering],
                    gaps_resolved=(),
                    gaps_narrowed=(),
                    falsification_resolved=(),
                    new_observations=(),
                    uncertainties_unchanged=(),
                    component_explanations={"replay": "from BB10 information gain analysis"},
                ),
            )

        marginal = build_branch_marginal_state(
            graph=graph,
            assessment=assessment,
            branch_root_id=branch_root,
            experiment_node_id=triggering,
            planning_sequence=decision_index,
        )

        best_exp_erv = _best_global_experiment_erv(alloc)
        best_local = float(alloc.get("best_local_erv", 0))
        best_frontier = float(alloc.get("best_frontier_erv", 0))
        best_deferred = float(alloc.get("best_deferred_erv", 0))
        best_revisit = max(best_frontier, best_deferred) if alloc.get("selected_source") == "REVISIT" else 0.0
        if alloc.get("selected_source") == "REVISIT":
            best_revisit = float(alloc.get("selected_erv", 0))

        remaining = int(alloc.get("budget_remaining", 12 - decision_index))
        hist_frontier = _historical_best_frontier(alloc)

        exit_val = compute_research_exit_value(
            marginal_state=marginal,
            best_experiment_erv=best_exp_erv,
            best_local_erv=best_local,
            best_frontier_erv=best_frontier,
            best_revisit_erv=best_revisit,
            best_deferred_erv=best_deferred,
            historical_best_frontier_score=hist_frontier,
            remaining_budget=remaining,
            experiment_budget=12,
            features_touched=2,
            eligible_feature_count=8,
        )

        stop_would_win = evaluate_exit_vs_experiment(exit_val, best_exp_erv)
        pre_selected = alloc.get("selected_action_id", "")
        pre_source = alloc.get("selected_source", "LOCAL")
        post_selected = "STOP_SESSION" if stop_would_win else pre_selected
        post_source = "EXIT_VALUATION" if stop_would_win else pre_source
        changed = stop_would_win

        if exit_val.exit_value != float("-inf"):
            stop_competed += 1
        if stop_would_win:
            stop_wins += 1
        if changed:
            selection_changes += 1
        elif decision_index <= 7:
            early_unchanged += 1

        should_hist_stop, hist_reason = evaluate_global_stop(
            remaining_budget=remaining,
            frontier=graph.get_frontier(),
            features_touched=8,
            eligible_feature_count=8,
        )
        should_curr_stop, curr_reason = evaluate_global_stop(
            remaining_budget=remaining,
            frontier=graph.get_frontier(),
            features_touched=8,
            eligible_feature_count=8,
            current_best_revalued_score=best_exp_erv,
        )

        record_revalued_erv_snapshot(
            graph,
            branch_root_id=branch_root,
            selected_erv=float(alloc.get("selected_erv", 0)),
            planning_sequence=decision_index,
        )

        row = {
            "decision_index": decision_index,
            "triggering_experiment_node_id": triggering,
            "branch_root_id": branch_root,
            "branch_marginal_state": marginal.marginal_state,
            "branch_marginal_reason": marginal.marginal_state_reason,
            "pre_3h8_selected_action_id": pre_selected,
            "pre_3h8_selected_source": pre_source,
            "pre_3h8_selected_erv": float(alloc.get("selected_erv", 0)),
            "best_experiment_erv": best_exp_erv,
            "best_local_erv": best_local,
            "best_frontier_erv": best_frontier,
            "best_revisit_erv": best_revisit,
            "best_deferred_erv": best_deferred,
            "historical_best_frontier_score": hist_frontier,
            "exit_value": exit_val.exit_value,
            "exit_value_components": exit_val.components,
            "stop_competed": exit_val.exit_value != float("-inf"),
            "stop_would_win": stop_would_win,
            "post_3h8_selected_action": post_selected,
            "post_3h8_selected_source": post_source,
            "selection_changed_by_exit_valuation": changed,
            "scientific_reason": marginal.marginal_state_reason,
            "global_stop_historical_only": should_hist_stop,
            "global_stop_historical_code": hist_reason.code,
            "global_stop_current_revalued": should_curr_stop,
            "global_stop_current_code": curr_reason.code,
        }
        transitions.append(row)

        if decision_index in (8, 9, 10, 11):
            late_audit[f"T{decision_index}"] = row

    return {
        "replay_version": "bb10_exit_valuation_replay_v1",
        "replayed_at": _utc_now(),
        "frozen_bb10_commit": FROZEN_BB10,
        "frozen_3h6_commit": FROZEN_3H6,
        "frozen_3h7_commit": FROZEN_3H7,
        "implementation_commit": _git_head(),
        "transitions_replayed": len(transitions),
        "stop_competed_count": stop_competed,
        "stop_would_win_count": stop_wins,
        "selection_changes": selection_changes,
        "early_productive_decisions_unchanged": early_unchanged,
        "late_transition_audit": late_audit,
        "transitions": transitions,
        "bb11_not_run": True,
        "interpretation": (
            "Offline replay applies 3H.8 exit valuation to frozen BB10 ERV snapshots. "
            "Outcomes are diagnostic only — not acceptance criteria."
        ),
    }


def _negative_control_audit() -> Dict[str, Any]:
    modules = [
        REPO / "modules/edge_research/research_exit_valuation.py",
        REPO / "modules/edge_research/research_branch_marginal_state.py",
        REPO / "modules/edge_research/research_global_allocator.py",
    ]
    hits: Dict[str, List[str]] = {}
    for path in modules:
        src = path.read_text(encoding="utf-8")
        found = validate_no_forbidden_exit_patterns(src)
        if found:
            hits[str(path.relative_to(REPO))] = found
    return {
        "forbidden_tokens_checked": sorted(FORBIDDEN_EXIT_TOKENS),
        "implementation_hits": hits,
        "scanner_vocabulary_file": "modules/edge_research/exit_valuation_negative_control_tokens.py",
        "passed": not hits,
    }


def _invariant_audit() -> Dict[str, Any]:
    from modules.edge_research.research_information_value import RESEARCH_INFORMATION_VALUE_VERSION

    iv_src = (REPO / "modules/edge_research/research_information_value.py").read_text()
    planner_src = (REPO / "modules/edge_research/research_planner.py").read_text()
    return {
        "information_value_version": RESEARCH_INFORMATION_VALUE_VERSION,
        "planner_module": "research_planner.py",
        "stop_session_score_unchanged": "_stop_session_score" in planner_src and "-100" in planner_src,
        "iv_formulas_unchanged_marker": "research_information_value_v1" in iv_src,
        "exit_valuation_version": RESEARCH_EXIT_VALUATION_VERSION,
        "branch_marginal_version": RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
        "bb11_not_run": True,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not BB10_ARTIFACTS.exists():
        print(json.dumps({"error": "BB10 artifacts not found", "path": str(BB10_ARTIFACTS)}))
        sys.exit(1)

    replay = replay_bb10()
    neg = _negative_control_audit()
    inv = _invariant_audit()

    artifacts = {
        "00_implementation_manifest.json": {
            "phase": PHASE,
            "implementation_commit": _git_head(),
            "frozen_bb10": FROZEN_BB10,
            "frozen_3h6": FROZEN_3H6,
            "frozen_3h7": FROZEN_3H7,
            "created_at": _utc_now(),
            "bb11_not_run": True,
        },
        "01_branch_marginal_model.json": {
            "version": RESEARCH_BRANCH_MARGINAL_STATE_VERSION,
            "states": [
                "PRODUCTIVE",
                "DIMINISHING",
                "LOW_MARGINAL_VALUE",
                "EXHAUSTION_EVIDENCE",
                "INSUFFICIENT_EVIDENCE",
            ],
            "inputs": [
                "experiments_on_branch",
                "realized_information_gain_history",
                "recent_revalued_opportunity_history",
                "unresolved_uncertainty_codes",
                "redundancy_evidence",
                "frame_saturation",
            ],
            "no_branch_depth_threshold": True,
        },
        "02_exit_valuation_contract.json": {
            "version": RESEARCH_EXIT_VALUATION_VERSION,
            "competing_states": ["LOW_MARGINAL_VALUE", "EXHAUSTION_EVIDENCE"],
            "comparison": "exit_value > best_experiment_erv",
            "no_sign_shortcut": True,
            "no_fixed_stop_score": True,
        },
        "03_stop_competition_contract.json": {
            "architecture": "global_allocator compares revalued experiments vs exit_value",
            "stop_session_selected_when": "exit_value > best_experiment_erv",
            "historical_frontier_not_controlling_when": "current_best_revalued_score provided",
        },
        "04_bb10_exit_replay.json": replay,
        "05_bb10_late_transition_audit.json": replay["late_transition_audit"],
        "06_pre_post_selection_comparison.json": {
            "transitions": [
                {
                    "decision_index": t["decision_index"],
                    "pre": t["pre_3h8_selected_action_id"],
                    "post": t["post_3h8_selected_action"],
                    "changed": t["selection_changed_by_exit_valuation"],
                    "stop_would_win": t["stop_would_win"],
                }
                for t in replay["transitions"]
            ],
            "selection_changes": replay["selection_changes"],
            "early_unchanged": replay["early_productive_decisions_unchanged"],
        },
        "07_negative_control_audit.json": neg,
        "08_invariant_audit.json": inv,
        "09_post_run_freeze_manifest.json": {
            "phase": PHASE,
            "frozen_at": _utc_now(),
            "implementation_commit": _git_head(),
            "bb11_not_run": True,
            "replay_summary": {
                "stop_would_win_count": replay["stop_would_win_count"],
                "selection_changes": replay["selection_changes"],
            },
        },
    }

    for name, payload in artifacts.items():
        (OUT_DIR / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(replay, indent=2))


if __name__ == "__main__":
    main()
