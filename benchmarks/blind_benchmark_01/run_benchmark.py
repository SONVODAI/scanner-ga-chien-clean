#!/usr/bin/env python3
"""
Blind Benchmark 01 — orchestration and reporting ONLY.

Does NOT modify research logic. Uses frozen Phase 3D–3G architecture as-is.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = Path(__file__).resolve().parent
ARTIFACTS = BENCHMARK_DIR / "artifacts"
sys.path.insert(0, str(REPO))

# --- Phase 1: imports (read-only) ---
from modules.edge_research.adapters import (  # noqa: E402
    EARNING_LEARNING_DIR,
    MARKET_T0_SNAPSHOT_PATH,
    OUTCOMES_PATH,
    PATTERN_HISTORY_PATH,
    build_research_panel,
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
from modules.edge_research.research_planner import (  # noqa: E402
    WEIGHT_ABANDON,
    WEIGHT_FALSIFICATION_THREAT,
    WEIGHT_INFORMATION_GAP,
    WEIGHT_NOVELTY,
    WEIGHT_STOP,
    WEIGHT_STRONG_EVIDENCE_EXPLORATION,
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
from modules.edge_research.research_controller import DEFAULT_SESSION_EXPERIMENT_BUDGET  # noqa: E402

BENCHMARK_ID = "blind_benchmark_01"
BENCHMARK_VERSION = "bb01_v1"
SESSION_ID = "bb01-autonomous-001"

# --- Frozen BEFORE execution (declared in manifest, not tuned post-hoc) ---
EXPERIMENT_BUDGET = 12
RESEARCH_CUTOFF = "2026-08-17"  # max T0 date in canonical panel at inventory time
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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return _sha256_bytes(path.read_bytes())


def build_neutral_inventory(panel: pd.DataFrame) -> Dict[str, Any]:
    """Neutral inventory only — no research interpretation."""
    registry = FeatureRegistry()
    eligible = list_eligible_explanatory_features(panel.columns, observation_horizon=0)
    prohibited = [c for c in panel.columns if is_prohibited_feature_column(c) and c not in RETURN_COLUMNS.values()]

    continuous = []
    categorical = []
    context_vars = []
    for col in sorted(panel.columns):
        role = classify_feature_role(col)
        if role == "continuous":
            continuous.append(col)
        elif role == "categorical":
            categorical.append(col)
        elif role == "context":
            context_vars.append(col)

    missingness = {
        col: round(float(panel[col].isna().mean()), 4)
        for col in sorted(panel.columns)
    }

    return {
        "benchmark_id": BENCHMARK_ID,
        "inventory_type": "neutral_legal_research_universe",
        "generated_at": _utc_now(),
        "canonical_data_sources": {
            "pattern_lifecycle": str(EARNING_LEARNING_DIR / "pattern_lifecycle.csv"),
            "outcomes_csv": str(OUTCOMES_PATH),
            "market_t0_snapshot": str(MARKET_T0_SNAPSHOT_PATH),
            "pattern_history": str(PATTERN_HISTORY_PATH),
            "panel_builder": "modules.edge_research.adapters.build_research_panel",
            "engine_entry": "EdgeResearchEngine.build_panel",
        },
        "row_count": int(len(panel)),
        "symbol_count": int(panel["symbol"].nunique()),
        "date_coverage": {
            "min_trade_date": str(panel["trade_date"].min()),
            "max_trade_date": str(panel["trade_date"].max()),
            "distinct_t0_dates": int(panel["trade_date"].nunique()),
        },
        "forward_horizons": list(HORIZONS),
        "forward_outcome_columns": {h: RETURN_COLUMNS[h] for h in HORIZONS},
        "matured_outcome_counts": {
            RETURN_COLUMNS[h]: int(panel[RETURN_COLUMNS[h]].notna().sum())
            for h in HORIZONS
            if RETURN_COLUMNS[h] in panel.columns
        },
        "panel_field_count": int(len(panel.columns)),
        "panel_fields": sorted(panel.columns.tolist()),
        "feature_registry": {
            "numeric_level": list(STOCK_NUMERIC_LEVEL_FEATURES),
            "categorical_level": list(STOCK_CATEGORICAL_LEVEL_FEATURES),
            "rank_level": list(STOCK_RANK_LEVEL_FEATURES),
            "registry_metadata_count": len(registry.all_specs()),
        },
        "continuous_variables": continuous,
        "categorical_variables": categorical,
        "market_context_variables": context_vars,
        "eligible_explanatory_at_t0": [e.to_dict() for e in eligible],
        "eligible_outcome_fields": sorted(ALLOWED_OUTCOME_FIELDS),
        "eligible_population_fields": sorted(ALLOWED_POPULATION_FIELDS),
        "prohibited_leakage_variables_sample": prohibited[:50],
        "temporal_availability_metadata": dict(sorted(FIELD_AVAILABILITY_HORIZON.items())),
        "missingness_by_field": missingness,
        "interpretation": "INVENTORY_ONLY_NO_RESEARCH_OPPORTUNITIES",
    }


def build_freeze_manifest(panel: pd.DataFrame, inventory: Dict[str, Any]) -> Dict[str, Any]:
    import subprocess

    git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    git_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()

    panel_csv = ARTIFACTS / "frozen_panel_snapshot.csv"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    panel.to_csv(panel_csv, index=False)
    panel_fingerprint = _sha256_file(panel_csv)

    data_sources = {
        "pattern_lifecycle.csv": _sha256_file(EARNING_LEARNING_DIR / "pattern_lifecycle.csv"),
        "outcomes.csv": _sha256_file(OUTCOMES_PATH),
        "market_t0_snapshot.csv": _sha256_file(MARKET_T0_SNAPSHOT_PATH),
        "pattern_history.csv": _sha256_file(PATTERN_HISTORY_PATH),
        "earning_learning_digests": earning_learning_digests(),
    }

    registry = build_default_tool_registry()

    return {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "freeze_timestamp": _utc_now(),
        "git_commit": git_commit,
        "git_branch": git_branch,
        "research_cutoff": RESEARCH_CUTOFF,
        "discovery_range": {"start": DISCOVERY_RANGE[0], "end": DISCOVERY_RANGE[1]},
        "dataset_fingerprint_sha256": panel_fingerprint,
        "frozen_panel_path": str(panel_csv.relative_to(REPO)),
        "data_source_fingerprints": data_sources,
        "feature_registry_snapshot": {
            "numeric": list(STOCK_NUMERIC_LEVEL_FEATURES),
            "categorical": list(STOCK_CATEGORICAL_LEVEL_FEATURES),
            "rank": list(STOCK_RANK_LEVEL_FEATURES),
        },
        "grammar_version": GRAMMAR_VERSION,
        "tool_registry_version": TOOLBOX_VERSION,
        "tool_count": len(registry.list_tools()),
        "tools": [m.tool_name for m in registry.list_tools()],
        "planner_weights": {
            "WEIGHT_INFORMATION_GAP": WEIGHT_INFORMATION_GAP,
            "WEIGHT_FALSIFICATION_THREAT": WEIGHT_FALSIFICATION_THREAT,
            "WEIGHT_NOVELTY": WEIGHT_NOVELTY,
            "WEIGHT_STOP": WEIGHT_STOP,
            "WEIGHT_ABANDON": WEIGHT_ABANDON,
            "WEIGHT_STRONG_EVIDENCE_EXPLORATION": WEIGHT_STRONG_EVIDENCE_EXPLORATION,
        },
        "experiment_budget": EXPERIMENT_BUDGET,
        "deterministic_seed": None,
        "autonomous_research_config": ROOT_CONFIG,
        "temporal_availability_rules": FEATURE_ELIGIBILITY_VERSION,
        "search_accounting_version": SEARCH_ACCOUNTING_VERSION,
        "complexity_weights": {
            "WEIGHT_BRANCH_DEPTH": WEIGHT_BRANCH_DEPTH,
            "WEIGHT_PREDICATE": WEIGHT_PREDICATE,
            "COMPLEXITY_PENALTY_SCALE": COMPLEXITY_PENALTY_SCALE,
        },
        "autonomous_flag": "EDGE_RESEARCH_AUTONOMOUS=1",
        "inventory_row_count": inventory["row_count"],
        "phases_frozen": ["3D", "3E", "3F", "3G"],
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
    feats = []
    for k in ("feature_column", "partition_column", "trajectory_feature"):
        if k in inputs:
            feats.append(str(inputs[k]))
    return feats


def build_research_diary(result: Any) -> List[Dict[str, Any]]:
    graph = result.graph
    diary: List[Dict[str, Any]] = []
    step_idx = 0

    experiments = [
        n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT
    ]
    experiments.sort(key=lambda n: n.created_at)

    for exp in experiments:
        step_idx += 1
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
                score = (na.metadata or {}).get("planner_score")
                planning_scores[na.action_code] = score
            if exp.selected_next_action:
                selected = exp.selected_next_action.action_code
                rejected = [
                    na.action_code
                    for na in exp.candidate_next_actions
                    if na.action_code != selected
                ]

        branch_depth = sum(
            1
            for n in graph.reconstruct_lineage(exp.node_id)
            if n.node_type == NodeType.EXPERIMENT
        )

        state = graph.get_search_accounting()
        from modules.edge_research.research_search_accounting import branch_root_id

        root = branch_root_id(graph, exp.node_id)
        branch_ledger = state.branch_ledgers.get(root, state.session_ledger)
        complexity = compute_complexity_score(branch_ledger, branch_depth=branch_depth)

        obs_codes = []
        metrics = {}
        if exp.experiment_result:
            obs_codes = [o.code for o in exp.experiment_result.observations]
            metrics = dict(exp.experiment_result.metrics)

        qctx = parent_q.question_context if parent_q else None
        diary.append(
            {
                "step": step_idx,
                "experiment_node_id": exp.node_id,
                "initial_observation": (
                    graph.get_node(graph.session.root_node_ids[0]).trigger.description
                    if graph.session.root_node_ids
                    else ""
                ),
                "research_question": parent_q.question_text if parent_q else "",
                "population_spec": qctx.population_spec if qctx else {},
                "outcome_spec": qctx.outcome_spec if qctx else {},
                "explanatory_variables": _extract_features_from_spec(exp.experiment_spec),
                "tool_selected": exp.experiment_spec.tool_name if exp.experiment_spec else "",
                "tool_inputs": exp.experiment_spec.inputs if exp.experiment_spec else {},
                "selection_rationale": (
                    parent_q.rationale.reason_code if parent_q and parent_q.rationale else ""
                ),
                "triggering_parent": (
                    parent_q.rationale.prior_node_id if parent_q and parent_q.rationale else ""
                ),
                "triggering_evidence": (
                    dict(parent_q.rationale.evidence_summary)
                    if parent_q and parent_q.rationale
                    else {}
                ),
                "experiment_result_metrics": metrics,
                "observation_codes": obs_codes,
                "candidate_next_actions": [na.to_dict() for na in exp.candidate_next_actions],
                "planner_scores": planning_scores,
                "selected_next_action": selected,
                "alternatives_rejected": rejected,
                "search_complexity_aggregate": complexity.aggregate_score,
                "branch_depth": branch_depth,
                "falsification_step": exp.experiment_spec.tool_name in (
                    "date_decomposition",
                    "symbol_decomposition",
                    "sensitivity_analysis",
                    "episode_decomposition",
                )
                if exp.experiment_spec
                else False,
                "node_status": exp.status.value,
                "terminal_reason": exp.terminal_reason,
                "research_status": exp.research_status,
            }
        )
    return diary


def build_coverage_report(result: Any, inventory: Dict[str, Any]) -> Dict[str, Any]:
    graph = result.graph
    state = graph.get_search_accounting()
    ledger = state.session_ledger

    touched_features: set[str] = set()
    tools_used: set[str] = set()
    for n in graph.nodes.values():
        if n.node_type == NodeType.EXPERIMENT and n.experiment_spec:
            tools_used.add(n.experiment_spec.tool_name)
            touched_features.update(_extract_features_from_spec(n.experiment_spec))

    eligible_feats = {e["field_name"] for e in inventory["eligible_explanatory_at_t0"]}
    eligible_count = len(eligible_feats)
    touched_count = len(touched_features & eligible_feats)

    branches_created = len(
        [n for n in graph.nodes.values() if n.node_type == NodeType.QUESTION]
    )
    branches_abandoned = ledger.abandoned_branches

    unexplored_features = sorted(eligible_feats - touched_features)

    mh = compute_effective_hypotheses(ledger)

    return {
        "eligible_features_count": eligible_count,
        "features_touched": sorted(touched_features),
        "pct_eligible_features_touched": round(
            100.0 * touched_count / max(1, eligible_count), 2
        ),
        "eligible_outcome_primitives": list(HORIZONS),
        "unique_outcome_specs": sorted(ledger.unique_outcome_specs),
        "unique_population_specs": sorted(ledger.unique_population_specs),
        "continuous_variables_partitioned": sorted(
            f for f in touched_features if f in inventory.get("continuous_variables", [])
        ),
        "categorical_variables_compared": sorted(
            f for f in touched_features if f in inventory.get("categorical_variables", [])
        ),
        "thresholds_explored": ledger.threshold_candidates_evaluated,
        "neighborhood_cuts_tested": ledger.neighborhood_cuts_evaluated,
        "interactions_attempted": ledger.interactions_attempted,
        "market_context_tests": ledger.partitions_evaluated
        if "market_conditioning" in tools_used
        else int("market_conditioning" in tools_used),
        "tools_used": sorted(tools_used),
        "branches_created": branches_created,
        "branches_abandoned": branches_abandoned,
        "duplicate_experiments_blocked": ledger.duplicate_experiments_blocked,
        "falsification_experiments_executed": ledger.falsification_experiments_executed,
        "total_experiments_executed": ledger.experiments_executed,
        "experiment_budget": EXPERIMENT_BUDGET,
        "pct_budget_used": round(
            100.0 * ledger.experiments_executed / EXPERIMENT_BUDGET, 2
        ),
        "maximum_branch_depth": ledger.branch_depth_max,
        "effective_hypotheses_tested": mh.effective_hypotheses_tested,
        "unexplored_eligible_features": unexplored_features[:100],
        "unexplored_count": len(unexplored_features),
        "note": "Unexplored space is NOT evidence of no edge.",
    }


def build_search_accounting_report(result: Any) -> Dict[str, Any]:
    graph = result.graph
    state = graph.get_search_accounting()
    summaries = list(state.candidate_summaries.values())

    complexities = []
    ratios = []
    for s in summaries:
        cs = s.get("complexity_score") or {}
        if "aggregate_score" in cs:
            complexities.append(float(cs["aggregate_score"]))
        eb = s.get("evidence_burden") or {}
        if eb.get("evidence_to_search_ratio") is not None:
            ratios.append(float(eb["evidence_to_search_ratio"]))

    mh = compute_effective_hypotheses(state.session_ledger)

    return {
        "session_ledger": state.session_ledger.to_dict(),
        "branch_ledgers": {k: v.to_dict() for k, v in state.branch_ledgers.items()},
        "complexity_distribution": {
            "min": min(complexities) if complexities else None,
            "max": max(complexities) if complexities else None,
            "values": complexities,
        },
        "simplest_interesting_candidate": min(summaries, key=lambda s: (s.get("complexity_score") or {}).get("aggregate_score", 999), default=None),
        "most_complex_candidate": max(summaries, key=lambda s: (s.get("complexity_score") or {}).get("aggregate_score", 0), default=None),
        "evidence_to_search_ratios": ratios,
        "effective_hypothesis_count": mh.effective_hypotheses_tested,
        "correction_applicable": mh.correction_applicable,
        "correction_method": mh.correction_method,
        "limitation_disclaimer": mh.limitation_disclaimer,
        "confirmation_status_summary": {
            s.get("candidate_id"): s.get("confirmation_status") for s in summaries
        },
    }


def collect_candidates(result: Any) -> Dict[str, List[Dict[str, Any]]]:
    graph = result.graph
    positive: List[Dict[str, Any]] = []
    anti: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for n in graph.nodes.values():
        if n.candidate_summary:
            summary = dict(n.candidate_summary)
            summary["validated"] = False
            summary["actionable"] = False
            raw = summary.get("raw_outcome_metric")
            if raw is not None and raw < 0.5:
                anti.append(summary)
            else:
                positive.append(summary)
        if n.status == NodeStatus.ABANDONED and n.experiment_result:
            rejected.append(
                {
                    "node_id": n.node_id,
                    "terminal_reason": n.terminal_reason,
                    "observations": [o.code for o in n.experiment_result.observations],
                    "metrics": dict(n.experiment_result.metrics),
                }
            )

    return {"candidates": positive, "anti_edges": anti, "rejected_abandoned": rejected}


def score_benchmark(diary: List[Dict[str, Any]], coverage: Dict[str, Any], result: Any) -> Dict[str, Any]:
    graph = result.graph
    tools_sequence = [d["tool_selected"] for d in diary]
    unique_tools = len(set(tools_sequence))
    has_followup = len(diary) > 1
    has_falsification = coverage["falsification_experiments_executed"] > 0
    stopped = graph.session.status.value in ("NO_EDGE_FOUND", "COMPLETE") or any(
        d.get("selected_next_action", "").startswith("STOP") for d in diary
    )

    scores = {
        "A_autonomy": min(10, 4 + len(diary) + (2 if len(set(tools_sequence)) > 2 else 0)),
        "B_breadth": min(10, int(coverage["pct_eligible_features_touched"] / 10) + unique_tools),
        "C_depth": min(10, 3 + len(diary) // 2),
        "D_shape_discovery": min(
            10,
            sum(
                1
                for d in diary
                if any("SHAPE" in c for c in d.get("observation_codes", []))
            )
            * 2
            + 2,
        ),
        "E_scientific_skepticism": min(10, 2 + coverage["falsification_experiments_executed"] * 2),
        "F_simplicity_preference": 6,
        "G_research_productivity": min(10, len(collect_candidates(result)["candidates"]) * 3 + 2),
        "H_novelty": min(10, unique_tools + (3 if has_followup else 0)),
        "I_auditability": 9 if diary else 3,
        "J_restraint": min(10, 5 + (3 if stopped else 0)),
    }
    overall = sum(scores.values())
    return {"dimension_scores": scores, "overall_research_capability_score": overall, "evidence_notes": {
        "diary_steps": len(diary),
        "unique_tools": unique_tools,
        "has_falsification": has_falsification,
        "session_status": graph.session.status.value,
    }}


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print("=== BLIND BENCHMARK 01: building canonical panel ===")
    engine = EdgeResearchEngine()
    panel = engine.build_panel()

    print("=== Phase 3: neutral inventory ===")
    inventory = build_neutral_inventory(panel)
    inv_path = ARTIFACTS / "01_neutral_dataset_inventory.json"
    inv_path.write_text(json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8")

    print("=== Phase 4: freeze manifest ===")
    manifest = build_freeze_manifest(panel, inventory)
    manifest_path = ARTIFACTS / "00_benchmark_freeze_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print("=== Phase 6: autonomous research session (budget=%d) ===" % EXPERIMENT_BUDGET)
    result = run_autonomous_session(panel)

    graph_path = ARTIFACTS / "research_sessions" / f"{SESSION_ID}.json"
    if not graph_path.exists():
        graph_path = ARTIFACTS / "research_sessions" / f"{SESSION_ID}"
        if graph_path.is_dir():
            graph_path = graph_path / "graph.json"

    # Persist full graph
    full_graph_path = ARTIFACTS / "05_research_graph.json"
    full_graph_path.write_text(result.graph.serialize(), encoding="utf-8")

    diary = build_research_diary(result)
    coverage = build_coverage_report(result, inventory)
    search_report = build_search_accounting_report(result)
    candidates = collect_candidates(result)
    scorecard = score_benchmark(diary, coverage, result)

    (ARTIFACTS / "02_frozen_configuration.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (ARTIFACTS / "03_research_diary.json").write_text(
        json.dumps(diary, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "04_candidate_discoveries.json").write_text(
        json.dumps(candidates["candidates"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "04b_anti_edge_discoveries.json").write_text(
        json.dumps(candidates["anti_edges"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "04c_rejected_abandoned.json").write_text(
        json.dumps(candidates["rejected_abandoned"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "06_coverage_report.json").write_text(
        json.dumps(coverage, indent=2), encoding="utf-8"
    )
    (ARTIFACTS / "07_search_accounting_report.json").write_text(
        json.dumps(search_report, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "08_benchmark_scorecard.json").write_text(
        json.dumps(scorecard, indent=2), encoding="utf-8"
    )

    summary = {
        "benchmark_id": BENCHMARK_ID,
        "completed_at": _utc_now(),
        "session_id": SESSION_ID,
        "session_status": result.graph.session.status.value,
        "experiments_used": result.graph.session.experiments_used,
        "step_count": len(result.steps),
        "artifact_dir": str(ARTIFACTS.relative_to(REPO)),
    }
    (ARTIFACTS / "09_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
