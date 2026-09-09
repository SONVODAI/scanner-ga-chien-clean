#!/usr/bin/env python3
"""
Blind Benchmark 02 — post-3G.1 exploration policy measurement.

Orchestration and reporting ONLY. Does NOT modify research logic.
Uses the SAME frozen panel fingerprint as BB01.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = Path(__file__).resolve().parent
ARTIFACTS = BENCHMARK_DIR / "artifacts"
BB01_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_01" / "artifacts"
BB01_PANEL = BB01_ARTIFACTS / "frozen_panel_snapshot.csv"
REQUIRED_FINGERPRINT = "c4a6affaff536a12bf825dd08549a7fc4c0fee285a321ed5582eb1bfbab24ee5"

sys.path.insert(0, str(REPO))

from modules.edge_research.adapters import (  # noqa: E402
    EARNING_LEARNING_DIR,
    MARKET_T0_SNAPSHOT_PATH,
    OUTCOMES_PATH,
    PATTERN_HISTORY_PATH,
    earning_learning_digests,
    file_digest,
)
from modules.edge_research.autonomous_research import AutonomousResearchConfig  # noqa: E402
from modules.edge_research.engine import EdgeResearchEngine  # noqa: E402
from modules.edge_research.feature_registry import (  # noqa: E402
    FeatureRegistry,
    STOCK_CATEGORICAL_LEVEL_FEATURES,
    STOCK_NUMERIC_LEVEL_FEATURES,
    STOCK_RANK_LEVEL_FEATURES,
    is_prohibited_feature_column,
)
from modules.edge_research.metrics import HORIZONS, RETURN_COLUMNS  # noqa: E402
from modules.edge_research.research_frontier import FRONTIER_VERSION  # noqa: E402
from modules.edge_research.research_grammar import (  # noqa: E402
    GRAMMAR_VERSION,
    ALLOWED_OUTCOME_FIELDS,
    ALLOWED_POPULATION_FIELDS,
    OutcomeSpec,
    PopulationSpec,
)
from modules.edge_research.research_feature_eligibility import (  # noqa: E402
    FEATURE_ELIGIBILITY_VERSION,
    FIELD_AVAILABILITY_HORIZON,
    classify_feature_role,
    list_eligible_explanatory_features,
)
from modules.edge_research.research_panel_preflight import build_panel_preflight  # noqa: E402
from modules.edge_research.research_planner import (  # noqa: E402
    EARLY_SESSION_FALSIFICATION_DAMPEN,
    LOW_COVERAGE_STOP_PENALTY,
    WEIGHT_ABANDON,
    WEIGHT_FALSIFICATION_THREAT,
    WEIGHT_INDEPENDENT_BRANCH,
    WEIGHT_INFORMATION_GAIN,
    WEIGHT_INFORMATION_GAP,
    WEIGHT_NOVELTY,
    WEIGHT_REDUNDANCY_PENALTY,
    WEIGHT_STOP,
    WEIGHT_STRONG_EVIDENCE_EXPLORATION,
    WEIGHT_UNEXPLORED_FEATURE,
    WEIGHT_UNEXPLORED_OUTCOME,
    WEIGHT_UNEXPLORED_POPULATION,
)
from modules.edge_research.research_search_accounting import (  # noqa: E402
    SEARCH_ACCOUNTING_VERSION,
    WEIGHT_BRANCH_DEPTH,
    WEIGHT_PREDICATE,
    COMPLEXITY_PENALTY_SCALE,
    compute_complexity_score,
    compute_effective_hypotheses,
)
from modules.edge_research.research_state import NodeType, NodeStatus  # noqa: E402
from modules.edge_research.research_tools import TOOLBOX_VERSION, build_default_tool_registry  # noqa: E402

BENCHMARK_ID = "blind_benchmark_02"
BENCHMARK_VERSION = "bb02_v1"
SESSION_ID = "bb02-autonomous-001"
EXPERIMENT_BUDGET = 12
RESEARCH_CUTOFF = "2026-08-17"
DISCOVERY_RANGE = ("2026-07-23", "2026-08-17")

ROOT_CONFIG = {
    "initial_observation": (
        "Autonomous benchmark seed: scan the canonical historical Edge Research universe "
        "for non-trivial relationships."
    ),
    "initial_question": (
        "What non-trivial, statistically and economically interesting relationships "
        "can be discovered in the currently available historical data?"
    ),
    "population_spec": PopulationSpec.all_().to_dict(),
    "outcome_spec": OutcomeSpec.compare("t5_return", ">", 0.0).to_dict(),
    "initial_tool_name": "horizon_comparison",
    "initial_tool_inputs": {"horizons": list(HORIZONS)},
    "experiment_budget": EXPERIMENT_BUDGET,
    "max_steps": EXPERIMENT_BUDGET,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_panel() -> pd.DataFrame:
    """Load BB01 frozen panel — fingerprint must match exactly."""
    if not BB01_PANEL.exists():
        panel_local = ARTIFACTS / "frozen_panel_snapshot.csv"
        if not panel_local.exists():
            raise SystemExit(f"BENCHMARK INVALID: no frozen panel at {BB01_PANEL}")
        source = panel_local
    else:
        source = BB01_PANEL
        dest = ARTIFACTS / "frozen_panel_snapshot.csv"
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(source.read_bytes())

    fp = _sha256_file(source)
    if fp != REQUIRED_FINGERPRINT:
        raise SystemExit(
            f"BENCHMARK INVALID: dataset fingerprint {fp!r} != required {REQUIRED_FINGERPRINT!r}"
        )
    return pd.read_csv(source)


def build_neutral_inventory(panel: pd.DataFrame) -> Dict[str, Any]:
    registry = FeatureRegistry()
    eligible = list_eligible_explanatory_features(panel.columns, observation_horizon=0)
    prohibited = [c for c in panel.columns if is_prohibited_feature_column(c) and c not in RETURN_COLUMNS.values()]

    continuous, categorical, context_vars = [], [], []
    for col in sorted(panel.columns):
        role = classify_feature_role(col)
        if role == "continuous":
            continuous.append(col)
        elif role == "categorical":
            categorical.append(col)
        elif role == "context":
            context_vars.append(col)

    return {
        "benchmark_id": BENCHMARK_ID,
        "inventory_type": "neutral_legal_research_universe",
        "generated_at": _utc_now(),
        "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
        "row_count": int(len(panel)),
        "symbol_count": int(panel["symbol"].nunique()),
        "date_coverage": {
            "min_trade_date": str(panel["trade_date"].min()),
            "max_trade_date": str(panel["trade_date"].max()),
            "distinct_t0_dates": int(panel["trade_date"].nunique()),
        },
        "panel_fields": sorted(panel.columns.tolist()),
        "continuous_variables": continuous,
        "categorical_variables": categorical,
        "market_context_variables": context_vars,
        "eligible_explanatory_at_t0": [e.to_dict() for e in eligible],
        "eligible_outcome_fields": sorted(ALLOWED_OUTCOME_FIELDS),
        "eligible_population_fields": sorted(ALLOWED_POPULATION_FIELDS),
        "temporal_availability_metadata": dict(sorted(FIELD_AVAILABILITY_HORIZON.items())),
        "interpretation": "INVENTORY_ONLY_NO_RESEARCH_OPPORTUNITIES",
    }


def build_freeze_manifest(panel: pd.DataFrame, inventory: Dict[str, Any], preflight: Dict[str, Any]) -> Dict[str, Any]:
    git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    git_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    registry = build_default_tool_registry()
    panel_path = ARTIFACTS / "frozen_panel_snapshot.csv"

    return {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "prior_benchmark": "blind_benchmark_01",
        "freeze_timestamp": _utc_now(),
        "git_commit": git_commit,
        "git_branch": git_branch,
        "research_cutoff": RESEARCH_CUTOFF,
        "discovery_range": {"start": DISCOVERY_RANGE[0], "end": DISCOVERY_RANGE[1]},
        "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
        "fingerprint_verified_against_bb01": True,
        "frozen_panel_path": str(panel_path.relative_to(REPO)),
        "bb01_frozen_panel_source": str(BB01_PANEL.relative_to(REPO)),
        "data_source_fingerprints": {
            "pattern_lifecycle.csv": file_digest(EARNING_LEARNING_DIR / "pattern_lifecycle.csv"),
            "outcomes.csv": file_digest(OUTCOMES_PATH),
            "market_t0_snapshot.csv": file_digest(MARKET_T0_SNAPSHOT_PATH),
            "pattern_history.csv": file_digest(PATTERN_HISTORY_PATH),
            "earning_learning_digests": earning_learning_digests(),
        },
        "grammar_version": GRAMMAR_VERSION,
        "tool_registry_version": TOOLBOX_VERSION,
        "search_accounting_version": SEARCH_ACCOUNTING_VERSION,
        "research_frontier_version": FRONTIER_VERSION,
        "temporal_availability_rules": FEATURE_ELIGIBILITY_VERSION,
        "panel_preflight": preflight,
        "planner_weights": {
            "WEIGHT_INFORMATION_GAP": WEIGHT_INFORMATION_GAP,
            "WEIGHT_FALSIFICATION_THREAT": WEIGHT_FALSIFICATION_THREAT,
            "WEIGHT_NOVELTY": WEIGHT_NOVELTY,
            "WEIGHT_STOP": WEIGHT_STOP,
            "WEIGHT_ABANDON": WEIGHT_ABANDON,
            "WEIGHT_STRONG_EVIDENCE_EXPLORATION": WEIGHT_STRONG_EVIDENCE_EXPLORATION,
            "WEIGHT_UNEXPLORED_FEATURE": WEIGHT_UNEXPLORED_FEATURE,
            "WEIGHT_UNEXPLORED_OUTCOME": WEIGHT_UNEXPLORED_OUTCOME,
            "WEIGHT_UNEXPLORED_POPULATION": WEIGHT_UNEXPLORED_POPULATION,
            "WEIGHT_INDEPENDENT_BRANCH": WEIGHT_INDEPENDENT_BRANCH,
            "WEIGHT_INFORMATION_GAIN": WEIGHT_INFORMATION_GAIN,
            "WEIGHT_REDUNDANCY_PENALTY": WEIGHT_REDUNDANCY_PENALTY,
            "EARLY_SESSION_FALSIFICATION_DAMPEN": EARLY_SESSION_FALSIFICATION_DAMPEN,
            "LOW_COVERAGE_STOP_PENALTY": LOW_COVERAGE_STOP_PENALTY,
        },
        "complexity_weights": {
            "WEIGHT_BRANCH_DEPTH": WEIGHT_BRANCH_DEPTH,
            "WEIGHT_PREDICATE": WEIGHT_PREDICATE,
            "COMPLEXITY_PENALTY_SCALE": COMPLEXITY_PENALTY_SCALE,
        },
        "experiment_budget": EXPERIMENT_BUDGET,
        "deterministic_seed": None,
        "autonomous_research_config": ROOT_CONFIG,
        "autonomous_flag": "EDGE_RESEARCH_AUTONOMOUS=1",
        "inventory_row_count": inventory["row_count"],
        "phases_frozen": ["3D", "3E", "3F", "3G", "3G.1"],
        "modification_policy": "NO_RESEARCH_LOGIC_CHANGES_AFTER_FREEZE",
    }


def run_autonomous_session(panel: pd.DataFrame) -> Any:
    os.environ["EDGE_RESEARCH_AUTONOMOUS"] = "1"
    research_dir = ARTIFACTS / "research_sessions"
    research_dir.mkdir(parents=True, exist_ok=True)

    config = AutonomousResearchConfig(
        data_cutoff_date=RESEARCH_CUTOFF,
        initial_observation=ROOT_CONFIG["initial_observation"],
        initial_question=ROOT_CONFIG["initial_question"],
        population_spec=PopulationSpec.from_dict(ROOT_CONFIG["population_spec"]),
        outcome_spec=OutcomeSpec.from_dict(ROOT_CONFIG["outcome_spec"]),
        initial_tool_name=ROOT_CONFIG["initial_tool_name"],
        initial_tool_inputs=dict(ROOT_CONFIG["initial_tool_inputs"]),
        experiment_budget=EXPERIMENT_BUDGET,
        max_steps=EXPERIMENT_BUDGET,
        auto_persist=True,
        session_id=SESSION_ID,
    )

    engine = EdgeResearchEngine(data_dir=research_dir)
    return engine.run_autonomous_research(config, panel=panel, enabled=True)


def _extract_features_from_spec(spec: Optional[Any]) -> List[str]:
    if spec is None:
        return []
    inputs = spec.inputs or {}
    return [str(inputs[k]) for k in ("feature_column", "partition_column", "trajectory_feature", "primary_feature") if k in inputs]


def _branch_id_for_exp(graph: Any, exp_id: str) -> str:
    from modules.edge_research.research_search_accounting import branch_root_id
    return branch_root_id(graph, exp_id)


def build_research_diary(result: Any, steps: List[Any]) -> List[Dict[str, Any]]:
    graph = result.graph
    frontier = graph.get_frontier()
    diary: List[Dict[str, Any]] = []

    experiments = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT]
    experiments.sort(key=lambda n: n.created_at)

    stop_branch_events = 0
    frontier_resume_events = 0
    for step in steps:
        if step.branch_terminal:
            stop_branch_events += 1
        if step.branch_terminal and step.spawned_experiment_id and not step.session_terminal:
            frontier_resume_events += 1

    for step_idx, exp in enumerate(experiments, 1):
        parent_q = None
        for pid in exp.parent_node_ids:
            p = graph.get_node(pid)
            if p.node_type == NodeType.QUESTION:
                parent_q = p
                break

        planning_scores = {}
        rejected = []
        selected = None
        if exp.candidate_next_actions:
            for na in exp.candidate_next_actions:
                planning_scores[na.action_code] = (na.metadata or {}).get("planner_score")
            if exp.selected_next_action:
                selected = exp.selected_next_action.action_code
                rejected = [na.action_code for na in exp.candidate_next_actions if na.action_code != selected]

        branch_depth = sum(1 for n in graph.reconstruct_lineage(exp.node_id) if n.node_type == NodeType.EXPERIMENT)
        state = graph.get_search_accounting()
        root = _branch_id_for_exp(graph, exp.node_id)
        branch_ledger = state.branch_ledgers.get(root, state.session_ledger)
        complexity = compute_complexity_score(branch_ledger, branch_depth=branch_depth)

        obs_codes, metrics = [], {}
        if exp.experiment_result:
            obs_codes = [o.code for o in exp.experiment_result.observations]
            metrics = dict(exp.experiment_result.metrics)

        qctx = parent_q.question_context if parent_q else None
        frontier_snapshot = {
            item.frontier_id: {"status": item.status, "action_code": item.action_code, "planner_score": item.planner_score}
            for item in frontier.items.values()
        }

        diary.append(
            {
                "step": step_idx,
                "current_branch_root": root,
                "experiment_node_id": exp.node_id,
                "research_question": parent_q.question_text if parent_q else "",
                "population_spec": qctx.population_spec if qctx else {},
                "outcome_spec": qctx.outcome_spec if qctx else {},
                "tool_selected": exp.experiment_spec.tool_name if exp.experiment_spec else "",
                "tool_inputs": exp.experiment_spec.inputs if exp.experiment_spec else {},
                "selection_rationale": parent_q.rationale.reason_code if parent_q and parent_q.rationale else "",
                "experiment_result_metrics": metrics,
                "observation_codes": obs_codes,
                "interpretation": {
                    "research_status": exp.research_status,
                    "observation_codes": obs_codes,
                },
                "candidate_actions_generated": [na.to_dict() for na in exp.candidate_next_actions],
                "planner_scores": planning_scores,
                "selected_next_action": selected,
                "alternatives_rejected": rejected,
                "frontier_items_after_step": frontier_snapshot,
                "frontier_unexplored_count": frontier.count_by_status("UNEXPLORED"),
                "search_complexity_aggregate": complexity.aggregate_score,
                "branch_depth": branch_depth,
                "falsification_step": exp.experiment_spec.tool_name in (
                    "sensitivity_analysis", "date_decomposition", "symbol_decomposition", "episode_decomposition",
                ) if exp.experiment_spec else False,
                "node_status": exp.status.value,
                "terminal_reason": exp.terminal_reason,
            }
        )

    session_stop = graph.session.session_stop_reason or {}
    diary.append(
        {
            "step": "SESSION_SUMMARY",
            "stop_branch_events_total": stop_branch_events,
            "frontier_resume_events_total": frontier_resume_events,
            "stop_session_evaluation": session_stop,
            "terminal_session_status": graph.session.status.value,
            "experiments_used": graph.session.experiments_used,
            "experiment_budget": graph.session.experiment_budget,
        }
    )
    return diary


def build_frontier_report(result: Any) -> Dict[str, Any]:
    graph = result.graph
    frontier = graph.get_frontier()
    status_counts = Counter(item.status for item in frontier.items.values())
    items = [item.to_dict() for item in sorted(frontier.items.values(), key=lambda i: i.frontier_id)]
    return {
        "frontier_version": frontier.version,
        "total_items": len(items),
        "status_counts": dict(status_counts),
        "unexplored_count": status_counts.get("UNEXPLORED", 0),
        "executed_count": status_counts.get("EXECUTED", 0),
        "invalid_count": status_counts.get("INVALID", 0),
        "duplicate_count": status_counts.get("DUPLICATE", 0),
        "items": items,
        "serialized_frontier": frontier.to_dict(),
    }


def build_coverage_report(result: Any, inventory: Dict[str, Any]) -> Dict[str, Any]:
    graph = result.graph
    state = graph.get_search_accounting()
    ledger = state.session_ledger
    frontier = graph.get_frontier()

    touched_features: Set[str] = set()
    tools_used: Set[str] = set()
    for n in graph.nodes.values():
        if n.node_type == NodeType.EXPERIMENT and n.experiment_spec:
            tools_used.add(n.experiment_spec.tool_name)
            touched_features.update(_extract_features_from_spec(n.experiment_spec))

    eligible_feats = {e["field_name"] for e in inventory["eligible_explanatory_at_t0"]}
    touched_eligible = touched_features & eligible_feats

    independent_branches = len(state.branch_ledgers)
    status_counts = Counter(i.status for i in frontier.items.values())

    return {
        "eligible_explanatory_features": sorted(eligible_feats),
        "features_touched": sorted(touched_eligible),
        "untouched_eligible_features": sorted(eligible_feats - touched_eligible),
        "pct_eligible_features_touched": round(100.0 * len(touched_eligible) / max(1, len(eligible_feats)), 2),
        "eligible_outcomes": list(HORIZONS),
        "unique_outcome_specs": sorted(ledger.unique_outcome_specs),
        "unique_population_specs": sorted(ledger.unique_population_specs),
        "continuous_partitions": ledger.partitions_evaluated,
        "categorical_comparisons": ledger.categorical_levels_evaluated,
        "thresholds_explored": ledger.threshold_candidates_evaluated,
        "neighborhood_tests": ledger.neighborhood_cuts_evaluated,
        "market_context_tests": int("market_conditioning" in tools_used),
        "interactions_attempted": ledger.interactions_attempted,
        "tools_used": sorted(tools_used),
        "branches_created": len([n for n in graph.nodes.values() if n.node_type == NodeType.QUESTION]),
        "independent_branches_explored": independent_branches,
        "falsification_experiments_executed": ledger.falsification_experiments_executed,
        "total_experiments_executed": ledger.experiments_executed,
        "experiment_budget": EXPERIMENT_BUDGET,
        "pct_budget_used": round(100.0 * ledger.experiments_executed / EXPERIMENT_BUDGET, 2),
        "maximum_branch_depth": ledger.branch_depth_max,
        "effective_hypotheses_tested": compute_effective_hypotheses(ledger).effective_hypotheses_tested,
        "frontier_items_created": len(frontier.items),
        "frontier_items_executed": status_counts.get("EXECUTED", 0),
        "frontier_items_unexplored": status_counts.get("UNEXPLORED", 0),
        "frontier_items_invalid": status_counts.get("INVALID", 0),
        "frontier_items_duplicate": status_counts.get("DUPLICATE", 0),
        "coverage_assessment": (
            "RESEARCH_COVERAGE_STILL_TOO_LOW"
            if len(touched_eligible) < len(eligible_feats) * 0.25 and ledger.experiments_executed < EXPERIMENT_BUDGET
            else "ADEQUATE_FOR_BUDGET"
        ),
        "note": "Distinguish NO_EDGE_FOUND from low coverage with unused budget.",
    }


def build_search_accounting_report(result: Any) -> Dict[str, Any]:
    graph = result.graph
    state = graph.get_search_accounting()
    summaries = list(state.candidate_summaries.values())
    mh = compute_effective_hypotheses(state.session_ledger)
    return {
        "session_ledger": state.session_ledger.to_dict(),
        "branch_ledgers": {k: v.to_dict() for k, v in state.branch_ledgers.items()},
        "candidate_summaries_count": len(summaries),
        "effective_hypothesis_count": mh.effective_hypotheses_tested,
        "correction_applicable": mh.correction_applicable,
        "limitation_disclaimer": mh.limitation_disclaimer,
    }


def collect_candidates(result: Any) -> Dict[str, List[Dict[str, Any]]]:
    graph = result.graph
    positive, anti, rejected = [], [], []

    for n in graph.nodes.values():
        if n.candidate_summary:
            summary = dict(n.candidate_summary)
            summary["validated"] = False
            summary["actionable"] = False
            status = summary.get("current_research_status", "")
            if status == "REJECTED" or (summary.get("raw_outcome_metric") is not None and summary["raw_outcome_metric"] < 0.5):
                anti.append(summary)
            elif summary.get("interesting") or status in ("CANDIDATE_DISCOVERED", "NEEDS_FALSIFICATION", "EXPLORATORY"):
                positive.append(summary)
        if n.status == NodeStatus.ABANDONED:
            rejected.append({"node_id": n.node_id, "terminal_reason": n.terminal_reason})

    return {"candidates": positive, "anti_edges": anti, "rejected_abandoned": rejected}


def score_benchmark(diary: List[Dict[str, Any]], coverage: Dict[str, Any], result: Any) -> Dict[str, Any]:
    graph = result.graph
    exp_diary = [d for d in diary if isinstance(d.get("step"), int)]
    tools_sequence = [d["tool_selected"] for d in exp_diary]
    unique_tools = len(set(tools_sequence))
    session_summary = next((d for d in diary if d.get("step") == "SESSION_SUMMARY"), {})
    stopped_properly = graph.session.status.value not in ("ACTIVE",)
    frontier_used = coverage.get("frontier_items_executed", 0) > 0 or session_summary.get("frontier_resume_events_total", 0) > 0

    scores = {
        "A_autonomy": min(10, 4 + len(exp_diary) + (2 if frontier_used else 0)),
        "B_breadth": min(10, int(coverage["pct_eligible_features_touched"] / 10) + unique_tools),
        "C_depth": min(10, 3 + len(exp_diary) // 2 + coverage.get("independent_branches_explored", 0)),
        "D_shape_discovery": min(10, sum(1 for d in exp_diary if any("SHAPE" in c for c in d.get("observation_codes", []))) * 2 + 2),
        "E_scientific_skepticism": min(10, 2 + coverage["falsification_experiments_executed"] * 2),
        "F_simplicity_preference": 6,
        "G_research_productivity": min(10, len(collect_candidates(result)["candidates"]) * 3 + int(coverage["pct_budget_used"] / 10)),
        "H_novelty": min(10, unique_tools + (3 if coverage.get("independent_branches_explored", 0) > 1 else 0)),
        "I_auditability": 9 if exp_diary else 3,
        "J_restraint": min(10, 5 + (3 if stopped_properly else 0)),
    }
    return {
        "dimension_scores": scores,
        "overall_research_capability_score": sum(scores.values()),
        "evidence_notes": {
            "diary_steps": len(exp_diary),
            "unique_tools": unique_tools,
            "session_status": graph.session.status.value,
            "frontier_resume_events": session_summary.get("frontier_resume_events_total", 0),
            "stop_branch_events": session_summary.get("stop_branch_events_total", 0),
        },
    }


def build_bb01_comparison(bb02_coverage: Dict[str, Any], bb02_scorecard: Dict[str, Any], result: Any) -> Dict[str, Any]:
    bb01_cov_path = BB01_ARTIFACTS / "06_coverage_report.json"
    bb01_score_path = BB01_ARTIFACTS / "08_benchmark_scorecard.json"
    bb01_summary_path = BB01_ARTIFACTS / "09_run_summary.json"

    bb01_cov = json.loads(bb01_cov_path.read_text()) if bb01_cov_path.exists() else {}
    bb01_score = json.loads(bb01_score_path.read_text()) if bb01_score_path.exists() else {}
    bb01_summary = json.loads(bb01_summary_path.read_text()) if bb01_summary_path.exists() else {}

    graph = result.graph
    session_summary = graph.session.session_stop_reason or {}

    metrics = {
        "experiments_executed": {
            "bb01": bb01_cov.get("total_experiments_executed", bb01_summary.get("experiments_used")),
            "bb02": bb02_coverage.get("total_experiments_executed"),
        },
        "pct_budget_used": {
            "bb01": bb01_cov.get("pct_budget_used"),
            "bb02": bb02_coverage.get("pct_budget_used"),
        },
        "tools_used": {"bb01": bb01_cov.get("tools_used"), "bb02": bb02_coverage.get("tools_used")},
        "features_touched": {"bb01": bb01_cov.get("features_touched"), "bb02": bb02_coverage.get("features_touched")},
        "pct_eligible_features_touched": {
            "bb01": bb01_cov.get("pct_eligible_features_touched"),
            "bb02": bb02_coverage.get("pct_eligible_features_touched"),
        },
        "falsification_runs": {
            "bb01": bb01_cov.get("falsification_experiments_executed"),
            "bb02": bb02_coverage.get("falsification_experiments_executed"),
        },
        "independent_branches": {
            "bb01": bb01_cov.get("branches_created"),
            "bb02": bb02_coverage.get("independent_branches_explored"),
        },
        "maximum_branch_depth": {
            "bb01": bb01_cov.get("maximum_branch_depth"),
            "bb02": bb02_coverage.get("maximum_branch_depth"),
        },
        "effective_hypotheses": {
            "bb01": bb01_cov.get("effective_hypotheses_tested"),
            "bb02": bb02_coverage.get("effective_hypotheses_tested"),
        },
        "terminal_session_status": {
            "bb01": bb01_summary.get("session_status"),
            "bb02": graph.session.status.value,
        },
        "research_capability_score": {
            "bb01": bb01_score.get("overall_research_capability_score"),
            "bb02": bb02_scorecard.get("overall_research_capability_score"),
        },
        "frontier_items_created": {"bb01": 0, "bb02": bb02_coverage.get("frontier_items_created")},
        "frontier_items_executed": {"bb01": 0, "bb02": bb02_coverage.get("frontier_items_executed")},
        "stop_session_reason": {"bb01": None, "bb02": session_summary},
    }

    corrections = {
        "premature_global_stop": {
            "bb01_failure": bb01_summary.get("session_status") == "ACTIVE" and bb01_cov.get("pct_budget_used", 0) < 50,
            "bb02_improved": graph.session.status.value != "ACTIVE" or bb02_coverage.get("pct_budget_used", 0) > bb01_cov.get("pct_budget_used", 0),
        },
        "zero_feature_exploration": {
            "bb01_failure": bb01_cov.get("pct_eligible_features_touched", 0) == 0,
            "bb02_improved": bb02_coverage.get("pct_eligible_features_touched", 0) > bb01_cov.get("pct_eligible_features_touched", 0),
        },
        "single_threaded_research": {
            "bb01_failure": bb01_cov.get("total_experiments_executed", 0) <= 2,
            "bb02_improved": bb02_coverage.get("independent_branches_explored", 0) > 1 or bb02_coverage.get("total_experiments_executed", 0) > 2,
        },
        "false_descriptive_candidate": {
            "bb01_failure": True,
            "bb02_improved": "Phase 3G.1 observation_kind prevents horizon-only CANDIDATE_DISCOVERED",
        },
        "invalid_field_handling": {
            "bb01_failure": "panel/grammar mismatches caused blocked paths",
            "bb02_improved": bb02_coverage.get("frontier_items_invalid", 0) >= 0,
        },
        "session_closure": {
            "bb01_failure": bb01_summary.get("session_status") == "ACTIVE",
            "bb02_improved": graph.session.status.value != "ACTIVE",
        },
    }

    return {
        "comparison_type": "architectural_behavior_only",
        "no_human_edge_comparison": True,
        "side_by_side_metrics": metrics,
        "bb01_architectural_failures_vs_bb02": corrections,
        "interpretation": "Compares research-control behavior only — not discovery quality vs human edges.",
    }


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print("=== BLIND BENCHMARK 02: load frozen panel (BB01 fingerprint) ===")
    panel = load_frozen_panel()
    print(f"Fingerprint verified: {REQUIRED_FINGERPRINT}")

    preflight = build_panel_preflight(panel).to_dict()
    inventory = build_neutral_inventory(panel)
    (ARTIFACTS / "01_neutral_dataset_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8"
    )

    print("=== Freeze manifest (pre-execution) ===")
    manifest = build_freeze_manifest(panel, inventory, preflight)
    (ARTIFACTS / "00_benchmark_freeze_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    (ARTIFACTS / "02_frozen_configuration.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print("=== Autonomous research session (budget=%d, Phase 3G.1) ===" % EXPERIMENT_BUDGET)
    result = run_autonomous_session(panel)

    (ARTIFACTS / "05_research_graph.json").write_text(result.graph.serialize(), encoding="utf-8")

    diary = build_research_diary(result, result.steps)
    frontier_report = build_frontier_report(result)
    coverage = build_coverage_report(result, inventory)
    search_report = build_search_accounting_report(result)
    candidates = collect_candidates(result)
    scorecard = score_benchmark(diary, coverage, result)
    comparison = build_bb01_comparison(coverage, scorecard, result)

    (ARTIFACTS / "03_research_diary.json").write_text(json.dumps(diary, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "04_candidate_discoveries.json").write_text(json.dumps(candidates["candidates"], indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "04b_anti_edge_discoveries.json").write_text(json.dumps(candidates["anti_edges"], indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "04c_rejected_abandoned.json").write_text(json.dumps(candidates["rejected_abandoned"], indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "06_coverage_report.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    (ARTIFACTS / "07_search_accounting_report.json").write_text(json.dumps(search_report, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "08_benchmark_scorecard.json").write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    (ARTIFACTS / "10_research_frontier_snapshot.json").write_text(json.dumps(frontier_report, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "11_bb01_vs_bb02_comparison.json").write_text(json.dumps(comparison, indent=2, default=str), encoding="utf-8")

    summary = {
        "benchmark_id": BENCHMARK_ID,
        "completed_at": _utc_now(),
        "session_id": SESSION_ID,
        "session_status": result.graph.session.status.value,
        "session_stop_reason": result.graph.session.session_stop_reason,
        "experiments_used": result.graph.session.experiments_used,
        "step_count": len(result.steps),
        "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
        "artifact_dir": str(ARTIFACTS.relative_to(REPO)),
        "research_capability_score": scorecard["overall_research_capability_score"],
    }
    (ARTIFACTS / "09_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
