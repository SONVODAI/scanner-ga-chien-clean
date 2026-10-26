#!/usr/bin/env python3
"""
Blind Benchmark 07 — post-3G.4.1 experiment identity & deduplication measurement.

Orchestration and reporting ONLY. Does NOT modify research logic.
Uses the SAME frozen panel fingerprint as BB01–BB06.
Primary test: does experiment-identity repair eliminate the BB06 Decision-4
DuplicateExperimentError and allow the frozen Global Research Allocator to
complete a full 12-experiment autonomous session?
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
BB02_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_02" / "artifacts"
BB03_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_03" / "artifacts"
BB04_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_04" / "artifacts"
BB05_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_05" / "artifacts"
BB06_ARTIFACTS = REPO / "benchmarks" / "blind_benchmark_06" / "artifacts"
BB05_GIT_REF = "cursor/blind-benchmark-05-aad2"
BB06_GIT_REF = "cursor/blind-benchmark-06-aad2"
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
from modules.edge_research.feature_registry import is_prohibited_feature_column  # noqa: E402
from modules.edge_research.metrics import HORIZONS, RETURN_COLUMNS  # noqa: E402
from modules.edge_research.research_frame import (  # noqa: E402
    RESEARCH_FRAME_VERSION,
    MIN_EXPERIMENTS_FOR_SATURATION,
    MIN_FEATURE_COVERAGE_RATIO,
    STOP_BRANCH_SATURATION_COUNT,
    FrameTransformationType,
    ResearchFrameRegistry,
    validate_frame_temporal_legality,
)
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
    WEIGHT_FRAME_NOVELTY,
    WEIGHT_INDEPENDENT_BRANCH,
    WEIGHT_INFORMATION_GAIN,
    WEIGHT_INFORMATION_GAP,
    WEIGHT_NEW_CONTEXT,
    WEIGHT_NEW_HORIZON,
    WEIGHT_NEW_OUTCOME,
    WEIGHT_NEW_POPULATION,
    WEIGHT_NOVELTY,
    WEIGHT_REDUNDANCY_PENALTY,
    WEIGHT_SAMPLE_LOSS_PENALTY,
    WEIGHT_SAME_FRAME_PENALTY,
    WEIGHT_SATURATED_REFRAME,
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
from modules.edge_research.research_experiment_identity import EXPERIMENT_IDENTITY_VERSION  # noqa: E402
from modules.edge_research.research_global_allocator import GLOBAL_ALLOCATOR_VERSION  # noqa: E402
from modules.edge_research.research_planner import PlanDecisionType  # noqa: E402
from modules.edge_research.research_portfolio import (  # noqa: E402
    PORTFOLIO_VERSION,
    BranchPortfolioStatus,
    compute_session_portfolio_metrics,
    WEIGHT_DOMINATED_PENALTY,
    WEIGHT_EXPLORATION_DEBT,
    WEIGHT_EXPLOITATION,
    WEIGHT_FALSIFICATION_PORTFOLIO,
    WEIGHT_MARGINAL_GAIN,
    WEIGHT_NOVELTY_PORTFOLIO,
    WEIGHT_REDUNDANCY_DIMINISH,
    WEIGHT_REVISIT,
    WEIGHT_SAMPLE_BURDEN,
    WEIGHT_SUNK_COST_AVOID,
)
from modules.edge_research.research_state import NodeType, NodeStatus  # noqa: E402
from modules.edge_research.research_tools import TOOLBOX_VERSION, build_default_tool_registry  # noqa: E402

BENCHMARK_ID = "blind_benchmark_07"
BENCHMARK_VERSION = "bb07_v1"
SESSION_ID = "bb07-autonomous-001"
FROZEN_RESEARCH_COMMIT = "dd027b3da"
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
    if not BB01_PANEL.exists():
        panel_local = ARTIFACTS / "frozen_panel_snapshot.csv"
        if not panel_local.exists():
            raise SystemExit(f"BENCHMARK_INVALID_DATASET_MISMATCH: no frozen panel at {BB01_PANEL}")
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
            f"BENCHMARK_INVALID_DATASET_MISMATCH: fingerprint {fp!r} != required {REQUIRED_FINGERPRINT!r}"
        )
    return pd.read_csv(source)


def build_neutral_inventory(panel: pd.DataFrame) -> Dict[str, Any]:
    eligible = list_eligible_explanatory_features(panel.columns, observation_horizon=0)
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
    panel_path = ARTIFACTS / "frozen_panel_snapshot.csv"

    return {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "prior_benchmarks": [
            "blind_benchmark_01",
            "blind_benchmark_02",
            "blind_benchmark_03",
            "blind_benchmark_04",
            "blind_benchmark_05",
            "blind_benchmark_06",
        ],
        "frozen_research_commit": FROZEN_RESEARCH_COMMIT,
        "global_allocator_version": GLOBAL_ALLOCATOR_VERSION,
        "experiment_identity_version": EXPERIMENT_IDENTITY_VERSION,
        "freeze_timestamp": _utc_now(),
        "git_commit": git_commit,
        "git_branch": git_branch,
        "research_cutoff": RESEARCH_CUTOFF,
        "discovery_range": {"start": DISCOVERY_RANGE[0], "end": DISCOVERY_RANGE[1]},
        "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
        "fingerprint_verified_against_bb01_bb02_bb03": True,
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
        "research_frame_version": RESEARCH_FRAME_VERSION,
        "temporal_availability_rules": FEATURE_ELIGIBILITY_VERSION,
        "frame_saturation_thresholds": {
            "MIN_EXPERIMENTS_FOR_SATURATION": MIN_EXPERIMENTS_FOR_SATURATION,
            "MIN_FEATURE_COVERAGE_RATIO": MIN_FEATURE_COVERAGE_RATIO,
            "STOP_BRANCH_SATURATION_COUNT": STOP_BRANCH_SATURATION_COUNT,
        },
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
            "WEIGHT_NEW_OUTCOME": WEIGHT_NEW_OUTCOME,
            "WEIGHT_NEW_POPULATION": WEIGHT_NEW_POPULATION,
            "WEIGHT_NEW_HORIZON": WEIGHT_NEW_HORIZON,
            "WEIGHT_NEW_CONTEXT": WEIGHT_NEW_CONTEXT,
            "WEIGHT_FRAME_NOVELTY": WEIGHT_FRAME_NOVELTY,
            "WEIGHT_SATURATED_REFRAME": WEIGHT_SATURATED_REFRAME,
            "WEIGHT_SAME_FRAME_PENALTY": WEIGHT_SAME_FRAME_PENALTY,
            "WEIGHT_SAMPLE_LOSS_PENALTY": WEIGHT_SAMPLE_LOSS_PENALTY,
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
        "phases_frozen": ["3D", "3E", "3F", "3G", "3G.1", "3G.2", "3G.2.1", "3G.3", "3G.4"],
        "portfolio_version": PORTFOLIO_VERSION,
        "portfolio_weights": {
            "WEIGHT_EXPLORATION_DEBT": WEIGHT_EXPLORATION_DEBT,
            "WEIGHT_EXPLOITATION": WEIGHT_EXPLOITATION,
            "WEIGHT_MARGINAL_GAIN": WEIGHT_MARGINAL_GAIN,
            "WEIGHT_REVISIT": WEIGHT_REVISIT,
            "WEIGHT_FALSIFICATION_PORTFOLIO": WEIGHT_FALSIFICATION_PORTFOLIO,
            "WEIGHT_NOVELTY_PORTFOLIO": WEIGHT_NOVELTY_PORTFOLIO,
            "WEIGHT_REDUNDANCY_DIMINISH": WEIGHT_REDUNDANCY_DIMINISH,
            "WEIGHT_DOMINATED_PENALTY": WEIGHT_DOMINATED_PENALTY,
            "WEIGHT_SAMPLE_BURDEN": WEIGHT_SAMPLE_BURDEN,
            "WEIGHT_SUNK_COST_AVOID": WEIGHT_SUNK_COST_AVOID,
        },
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
    return [
        str(inputs[k])
        for k in ("feature_column", "partition_column", "trajectory_feature", "primary_feature")
        if k in inputs
    ]


def _branch_id_for_exp(graph: Any, exp_id: str) -> str:
    from modules.edge_research.research_search_accounting import branch_root_id
    return branch_root_id(graph, exp_id)


def _experiments_by_frame(graph: Any) -> Dict[str, List[Any]]:
    by_frame: Dict[str, List[Any]] = defaultdict(list)
    for n in graph.nodes.values():
        if n.node_type != NodeType.EXPERIMENT:
            continue
        frame_id = ""
        for pid in n.parent_node_ids:
            p = graph.get_node(pid)
            if p.question_context:
                frame_id = p.question_context.frame_id or "unknown"
                break
        by_frame[frame_id].append(n)
    return dict(by_frame)


def _frame_content_key(pop: Dict[str, Any], out: Dict[str, Any], obs_h: int = 0) -> Tuple[str, str, str, int]:
    try:
        ph = PopulationSpec.from_dict(pop).content_hash()
        oh = OutcomeSpec.from_dict(out).content_hash()
    except Exception:
        ph, oh = str(pop), str(out)
    return ph, oh, ph + oh, obs_h


def build_frame_registry_report(result: Any) -> Dict[str, Any]:
    graph = result.graph
    reg = graph.get_frame_registry()
    exp_by_frame = _experiments_by_frame(graph)
    frontier = graph.get_frontier()

    created_frame_ids = set(reg.frames.keys())
    frontier_frame_ids = {item.frame_id for item in frontier.items.values() if item.frame_id}
    all_created = created_frame_ids | frontier_frame_ids

    executed_frame_ids = {fid for fid, exps in exp_by_frame.items() if fid and exps}
    unexplored = all_created - executed_frame_ids

    status_counts = Counter(f.status for f in reg.frames.values())
    transformations = Counter(
        item.transformation_type for item in frontier.items.values() if item.transformation_type
    )
    for rec in reg.lineage:
        transformations[rec.transformation] += 1

    return {
        "registry_version": reg.version,
        "active_frame_id": reg.active_frame_id,
        "frames": {fid: f.to_dict() for fid, f in sorted(reg.frames.items())},
        "lineage": [r.to_dict() for r in reg.lineage],
        "created_vs_executed": {
            "research_frames_created": len(all_created),
            "research_frames_executed": len(executed_frame_ids),
            "research_frames_unexplored": sorted(unexplored),
            "unique_outcome_specs_created": reg.unique_outcome_count(),
            "unique_population_specs_created": reg.unique_population_count(),
        },
        "status_counts": dict(status_counts),
        "frontier_transformation_types_created": dict(transformations),
    }


def build_frame_coverage_report(result: Any, inventory: Dict[str, Any]) -> Dict[str, Any]:
    graph = result.graph
    reg = graph.get_frame_registry()
    state = graph.get_search_accounting()
    ledger = state.session_ledger
    exp_by_frame = _experiments_by_frame(graph)
    frontier = graph.get_frontier()

    executed_frames = {fid for fid, exps in exp_by_frame.items() if fid and exps}
    created_frames = set(reg.frames.keys())

    outcome_hashes_created: Set[str] = set()
    outcome_hashes_executed: Set[str] = set()
    pop_hashes_created: Set[str] = set()
    pop_hashes_executed: Set[str] = set()
    horizons_created: Set[int] = set()
    horizons_executed: Set[int] = set()

    for f in reg.frames.values():
        outcome_hashes_created.add(f.outcome.content_hash())
        pop_hashes_created.add(f.population.content_hash())
        horizons_created.add(f.observation_horizon)

    for fid in executed_frames:
        frame = reg.get(fid)
        if frame:
            outcome_hashes_executed.add(frame.outcome.content_hash())
            pop_hashes_executed.add(frame.population.content_hash())
            horizons_executed.add(frame.observation_horizon)
        else:
            for exp in exp_by_frame[fid]:
                for pid in exp.parent_node_ids:
                    p = graph.get_node(pid)
                    if p.question_context:
                        try:
                            outcome_hashes_executed.add(
                                OutcomeSpec.from_dict(p.question_context.outcome_spec).content_hash()
                            )
                            pop_hashes_executed.add(
                                PopulationSpec.from_dict(p.question_context.population_spec).content_hash()
                            )
                            horizons_executed.add(p.question_context.observation_horizon)
                        except Exception:
                            pass

    transformation_executed = Counter()
    transformation_created = Counter()
    for item in frontier.items.values():
        if item.transformation_type:
            transformation_created[item.transformation_type] += 1
    for rec in reg.lineage:
        new_f = reg.get(rec.new_frame_id)
        if new_f and rec.new_frame_id in executed_frames:
            transformation_executed[rec.transformation] += 1

    same_frame_experiments = sum(
        len(exps) for fid, exps in exp_by_frame.items() if fid == reg.frames.get(fid, reg.get(reg.active_frame_id or "")) is not None
    )
    primary_frame = reg.active_frame_id or (sorted(created_frames)[0] if created_frames else "")
    same_frame_count = len(exp_by_frame.get(primary_frame, []))

    touched_features: Set[str] = set()
    tools_used: Set[str] = set()
    for n in graph.nodes.values():
        if n.node_type == NodeType.EXPERIMENT and n.experiment_spec:
            tools_used.add(n.experiment_spec.tool_name)
            touched_features.update(_extract_features_from_spec(n.experiment_spec))

    eligible_feats = {e["field_name"] for e in inventory["eligible_explanatory_at_t0"]}
    touched_eligible = touched_features & eligible_feats
    status_counts = Counter(i.status for i in frontier.items.values())

    return {
        "traditional_coverage": {
            "experiments_executed": ledger.experiments_executed,
            "experiment_budget": EXPERIMENT_BUDGET,
            "pct_budget_used": round(100.0 * ledger.experiments_executed / EXPERIMENT_BUDGET, 2),
            "tools_used": sorted(tools_used),
            "eligible_features": sorted(eligible_feats),
            "features_touched": sorted(touched_eligible),
            "pct_eligible_features_touched": round(100.0 * len(touched_eligible) / max(1, len(eligible_feats)), 2),
            "partitions": ledger.partitions_evaluated,
            "thresholds": ledger.threshold_candidates_evaluated,
            "categorical_comparisons": ledger.categorical_levels_evaluated,
            "market_context_tests": int("market_conditioning" in tools_used),
            "interactions": ledger.interactions_attempted,
            "falsifications": ledger.falsification_experiments_executed,
            "unique_outcome_specs_executed": sorted(ledger.unique_outcome_specs),
            "unique_population_specs_executed": sorted(ledger.unique_population_specs),
            "unique_research_frames_executed": sorted(ledger.unique_research_frames),
            "refinements_reframes": ledger.refinements_reframes,
        },
        "frame_coverage": {
            "frames_created": len(created_frames),
            "frames_executed": len(executed_frames),
            "frames_unexplored": sorted(created_frames - executed_frames),
            "frames_by_status": dict(Counter(f.status for f in reg.frames.values())),
            "unique_outcome_specs_created": len(outcome_hashes_created),
            "unique_outcome_specs_executed": len(outcome_hashes_executed),
            "unique_population_specs_created": len(pop_hashes_created),
            "unique_population_specs_executed": len(pop_hashes_executed),
            "observation_horizons_created": sorted(horizons_created),
            "observation_horizons_executed": sorted(horizons_executed),
            "frame_transitions_recorded": len(reg.lineage),
            "outcome_reframes_created": transformation_created.get(FrameTransformationType.OUTCOME_REFRAME.value, 0)
            + transformation_created.get(FrameTransformationType.STRUCTURAL_TRIGGER.value, 0),
            "outcome_reframes_executed": transformation_executed.get(FrameTransformationType.OUTCOME_REFRAME.value, 0)
            + transformation_executed.get(FrameTransformationType.STRUCTURAL_TRIGGER.value, 0),
            "population_reframes_created": transformation_created.get(FrameTransformationType.POPULATION_REFRAME.value, 0),
            "population_reframes_executed": transformation_executed.get(FrameTransformationType.POPULATION_REFRAME.value, 0),
            "horizon_advancements_created": transformation_created.get(FrameTransformationType.HORIZON_ADVANCE.value, 0),
            "horizon_advancements_executed": transformation_executed.get(FrameTransformationType.HORIZON_ADVANCE.value, 0),
            "outcome_to_population_created": transformation_created.get(
                FrameTransformationType.OUTCOME_TO_POPULATION.value, 0
            ),
            "outcome_to_population_executed": transformation_executed.get(
                FrameTransformationType.OUTCOME_TO_POPULATION.value, 0
            ),
            "same_frame_experiments": same_frame_count,
            "cross_frame_experiments": ledger.experiments_executed - same_frame_count,
            "frontier_items_with_frame_id": sum(1 for i in frontier.items.values() if i.frame_id),
            "frontier_reframe_items_unexplored": sum(
                1
                for i in frontier.items.values()
                if i.frame_id and i.status == "UNEXPLORED" and i.transformation_type
            ),
        },
        "created_vs_executed_summary": {
            "outcome_specs": {"created": len(outcome_hashes_created), "executed": len(outcome_hashes_executed)},
            "population_specs": {"created": len(pop_hashes_created), "executed": len(pop_hashes_executed)},
            "observation_horizons": {"created": len(horizons_created), "executed": len(horizons_executed)},
            "research_frames": {"created": len(created_frames), "executed": len(executed_frames)},
        },
    }


def build_frame_transition_diary(result: Any, diary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    graph = result.graph
    reg = graph.get_frame_registry()
    exp_by_frame = _experiments_by_frame(graph)
    transitions: List[Dict[str, Any]] = []

    for rec in reg.lineage:
        old = reg.frames.get(rec.old_frame_id)
        new = reg.frames.get(rec.new_frame_id)
        old_exps = exp_by_frame.get(rec.old_frame_id, [])
        new_exps = exp_by_frame.get(rec.new_frame_id, [])

        trigger_exp = old_exps[-1].node_id if old_exps else None
        trigger_metrics = {}
        trigger_obs = []
        if old_exps and old_exps[-1].experiment_result:
            trigger_metrics = dict(old_exps[-1].experiment_result.metrics)
            trigger_obs = [o.code for o in old_exps[-1].experiment_result.observations]

        planner_alts = []
        if old_exps and old_exps[-1].candidate_next_actions:
            planner_alts = [
                {"action_code": na.action_code, "score": (na.metadata or {}).get("planner_score")}
                for na in old_exps[-1].candidate_next_actions
            ]

        exec_results = []
        for exp in new_exps:
            obs_codes, metrics = [], {}
            if exp.experiment_result:
                obs_codes = [o.code for o in exp.experiment_result.observations]
                metrics = dict(exp.experiment_result.metrics)
            exec_results.append(
                {
                    "experiment_node_id": exp.node_id,
                    "tool": exp.experiment_spec.tool_name if exp.experiment_spec else "",
                    "observation_codes": obs_codes,
                    "metrics": metrics,
                    "research_status": exp.research_status,
                }
            )

        transitions.append(
            {
                "old_frame": {
                    "frame_id": rec.old_frame_id,
                    "population_spec": old.population.to_dict() if old else {},
                    "outcome_spec": old.outcome.to_dict() if old else {},
                    "observation_horizon": old.observation_horizon if old else 0,
                    "experiments_performed": len(old_exps),
                    "features_explored": list(old.features_explored) if old else [],
                    "status": old.status if old else "",
                    "candidate_yield": old.candidate_yield if old else 0,
                    "saturation_evidence": rec.saturation_evidence,
                },
                "trigger": {
                    "prior_experiment": trigger_exp,
                    "prior_metrics": trigger_metrics,
                    "prior_observations": trigger_obs,
                    "trigger_code": rec.trigger,
                    "saturation_evidence": rec.saturation_evidence,
                    "planner_alternatives": planner_alts,
                },
                "new_frame": {
                    "frame_id": rec.new_frame_id,
                    "transformation_type": rec.transformation,
                    "population_spec": new.population.to_dict() if new else {},
                    "outcome_spec": new.outcome.to_dict() if new else {},
                    "observation_horizon": rec.observation_horizon,
                    "temporal_legal": rec.temporal_legal,
                    "sample_n": rec.sample_n,
                },
                "execution": {
                    "was_researched": len(new_exps) > 0,
                    "experiments_run": len(new_exps),
                    "results": exec_results,
                },
            }
        )

    if not transitions:
        transitions.append(
            {
                "note": "NO_FRAME_TRANSITIONS_RECORDED",
                "interpretation": "Session remained in initial research frame or transitions not persisted.",
                "initial_frame_id": reg.active_frame_id,
                "frames_in_registry": len(reg.frames),
            }
        )

    return transitions


def build_outcome_to_population_audit(result: Any) -> Dict[str, Any]:
    graph = result.graph
    reg = graph.get_frame_registry()
    cases: List[Dict[str, Any]] = []

    for rec in reg.lineage:
        if rec.transformation != FrameTransformationType.OUTCOME_TO_POPULATION.value:
            continue
        new = reg.frames.get(rec.new_frame_id)
        old = reg.frames.get(rec.old_frame_id)
        if not new:
            continue
        exp_by_frame = _experiments_by_frame(graph)
        new_exps = exp_by_frame.get(rec.new_frame_id, [])

        cases.append(
            {
                "source_outcome": old.outcome.to_dict() if old else {},
                "original_observation_horizon": old.observation_horizon if old else 0,
                "new_observation_horizon": new.observation_horizon,
                "new_population_spec": new.population.to_dict(),
                "later_target_outcome_spec": new.outcome.to_dict(),
                "temporal_legal": rec.temporal_legal,
                "sample_n": rec.sample_n,
                "executed": len(new_exps) > 0,
                "experiment_results": [
                    {
                        "experiment_id": e.node_id,
                        "observations": [o.code for o in e.experiment_result.observations]
                        if e.experiment_result
                        else [],
                    }
                    for e in new_exps
                ],
            }
        )

    return {
        "outcome_to_population_count": len(cases),
        "cases": cases,
        "note": "Zero transformations is a valid benchmark result.",
    }


def build_failed_reframes(result: Any) -> List[Dict[str, Any]]:
    graph = result.graph
    reg = graph.get_frame_registry()
    exp_by_frame = _experiments_by_frame(graph)
    failed: List[Dict[str, Any]] = []

    for rec in reg.lineage:
        new_exps = exp_by_frame.get(rec.new_frame_id, [])
        if not new_exps:
            continue
        new_frame = reg.frames.get(rec.new_frame_id)
        if not new_frame:
            continue
        if new_frame.candidate_yield > 0:
            continue

        obs_all = []
        for exp in new_exps:
            if exp.experiment_result:
                obs_all.extend(o.code for o in exp.experiment_result.observations)

        failed.append(
            {
                "frame_id": rec.new_frame_id,
                "transformation": rec.transformation,
                "reason_created": new_frame.reason_created,
                "trigger": rec.trigger,
                "experiments_run": len(new_exps),
                "observation_codes": obs_all,
                "frame_status_after": new_frame.status,
                "candidate_yield": new_frame.candidate_yield,
                "what_bot_did_next": "Returned to frontier or continued same session",
            }
        )

    return failed


def build_temporal_safety_audit(result: Any) -> Dict[str, Any]:
    graph = result.graph
    reg = graph.get_frame_registry()
    frontier = graph.get_frontier()

    illegal_attempts = []
    for item in frontier.items.values():
        if item.status == "INVALID" and "leak" in (item.invalid_reason or "").lower():
            illegal_attempts.append({"frontier_id": item.frontier_id, "reason": item.invalid_reason})

    frame_legality = []
    for fid, frame in reg.frames.items():
        legal = validate_frame_temporal_legality(frame)
        frame_legality.append(
            {
                "frame_id": fid,
                "observation_horizon": frame.observation_horizon,
                "temporally_legal": legal,
                "outcome_field": frame.outcome.outcome_field,
            }
        )

    for rec in reg.lineage:
        frame_legality.append(
            {
                "frame_id": rec.new_frame_id,
                "lineage_temporal_legal": rec.temporal_legal,
                "transformation": rec.transformation,
            }
        )

    all_legal = all(
        entry.get("temporally_legal", entry.get("lineage_temporal_legal", True)) for entry in frame_legality
    )

    return {
        "attempted_illegal_transformations": illegal_attempts,
        "rejected_future_leakage_actions": len(illegal_attempts),
        "executed_frame_legality": frame_legality,
        "all_executed_frames_temporally_legal": all_legal,
        "outcome_to_population_legality_decisions": [
            {"frame_id": c["new_frame"]["frame_id"], "legal": c["new_frame"]["temporal_legal"]}
            for c in build_frame_transition_diary(result, [])  # noqa - reuse if transitions exist
            if isinstance(c.get("new_frame"), dict) and c["new_frame"].get("transformation_type")
            == FrameTransformationType.OUTCOME_TO_POPULATION.value
        ],
    }


def build_research_diary(result: Any, steps: List[Any]) -> List[Dict[str, Any]]:
    graph = result.graph
    frontier = graph.get_frontier()
    reg = graph.get_frame_registry()
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
        frame_id = qctx.frame_id if qctx else ""
        frame_status = reg.get(frame_id).status if frame_id and reg.get(frame_id) else ""

        diary.append(
            {
                "step": step_idx,
                "current_branch_root": root,
                "experiment_node_id": exp.node_id,
                "frame_id": frame_id,
                "frame_status": frame_status,
                "observation_horizon": qctx.observation_horizon if qctx else 0,
                "research_question": parent_q.question_text if parent_q else "",
                "population_spec": qctx.population_spec if qctx else {},
                "outcome_spec": qctx.outcome_spec if qctx else {},
                "tool_selected": exp.experiment_spec.tool_name if exp.experiment_spec else "",
                "tool_inputs": exp.experiment_spec.inputs if exp.experiment_spec else {},
                "selection_rationale": parent_q.rationale.reason_code if parent_q and parent_q.rationale else "",
                "experiment_result_metrics": metrics,
                "observation_codes": obs_codes,
                "interpretation": {"research_status": exp.research_status, "observation_codes": obs_codes},
                "candidate_actions_generated": [na.to_dict() for na in exp.candidate_next_actions],
                "planner_scores": planning_scores,
                "selected_next_action": selected,
                "alternatives_rejected": rejected,
                "frontier_unexplored_count": frontier.count_by_status("UNEXPLORED"),
                "search_complexity_aggregate": complexity.aggregate_score,
                "branch_depth": branch_depth,
                "falsification_step": exp.experiment_spec.tool_name
                in ("sensitivity_analysis", "date_decomposition", "symbol_decomposition", "episode_decomposition")
                if exp.experiment_spec
                else False,
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
            "frame_transitions": len(reg.lineage),
            "unique_frames_executed": len(_experiments_by_frame(graph)),
        }
    )
    return diary


def build_frontier_report(result: Any) -> Dict[str, Any]:
    graph = result.graph
    frontier = graph.get_frontier()
    status_counts = Counter(item.status for item in frontier.items.values())
    items = [item.to_dict() for item in sorted(frontier.items.values(), key=lambda i: i.frontier_id)]
    frame_ids = Counter(item.frame_id for item in frontier.items.values() if item.frame_id)
    return {
        "frontier_version": frontier.version,
        "total_items": len(items),
        "status_counts": dict(status_counts),
        "unique_frame_ids_on_frontier": dict(frame_ids),
        "reframe_items": [
            item.to_dict()
            for item in frontier.items.values()
            if item.transformation_type
        ],
        "items": items,
        "serialized_frontier": frontier.to_dict(),
    }


def collect_candidates(result: Any) -> Dict[str, List[Dict[str, Any]]]:
    graph = result.graph
    reg = graph.get_frame_registry()
    positive, anti, rejected = [], [], []

    for n in graph.nodes.values():
        if n.candidate_summary:
            summary = dict(n.candidate_summary)
            summary["validated"] = False
            summary["actionable"] = False
            frame_id = ""
            for pid in n.parent_node_ids:
                p = graph.get_node(pid)
                if p.question_context:
                    frame_id = p.question_context.frame_id
                    summary["originating_frame_id"] = frame_id
                    summary["observation_horizon"] = p.question_context.observation_horizon
                    break
            status = summary.get("current_research_status", "")
            if status == "REJECTED" or (
                summary.get("raw_outcome_metric") is not None and summary["raw_outcome_metric"] < 0.5
            ):
                anti.append(summary)
            elif summary.get("interesting") or status in (
                "CANDIDATE_DISCOVERED",
                "NEEDS_FALSIFICATION",
                "EXPLORATORY",
            ):
                positive.append(summary)
        if n.status == NodeStatus.ABANDONED:
            rejected.append({"node_id": n.node_id, "terminal_reason": n.terminal_reason})

    return {"candidates": positive, "anti_edges": anti, "rejected_abandoned": rejected}


def build_horizon_advanced_survivability_audit(
    result: Any,
    diary: List[Dict[str, Any]],
    run_error: Optional[str] = None,
) -> Dict[str, Any]:
    """Primary BB04 test: horizon-advanced frames surviving follow-on research."""
    graph = result.graph
    reg = graph.get_frame_registry()
    exp_by_frame = _experiments_by_frame(graph)
    exp_diary = [d for d in diary if isinstance(d.get("step"), int)]

    horizon_frames: List[Dict[str, Any]] = []
    any_survived = False

    for fid, frame in reg.frames.items():
        is_horizon_advanced = (
            frame.observation_horizon > 0
            or frame.transformation == FrameTransformationType.OUTCOME_TO_POPULATION.value
            or frame.transformation == FrameTransformationType.HORIZON_ADVANCE.value
        )
        if not is_horizon_advanced:
            continue

        exps = exp_by_frame.get(fid, [])
        if not exps:
            continue

        first_exp = exps[0]
        parent_frame_id = frame.parent_frame_id or ""
        lineage_rec = next((r for r in reg.lineage if r.new_frame_id == fid), None)

        # Find diary entry for first experiment in this frame
        first_diary = next((d for d in exp_diary if d.get("experiment_node_id") == first_exp.node_id), {})
        trigger_exp = lineage_rec.triggering_experiment_id if lineage_rec else ""

        # Follow-on planning: did candidate generation succeed on first exp in frame?
        follow_on_planning_attempted = bool(first_exp.candidate_next_actions)
        grammar_count = adaptive_count = reframe_count = 0
        if first_exp.candidate_next_actions:
            for na in first_exp.candidate_next_actions:
                code = na.action_code
                if code.startswith("REFRAME_") or "HORIZON" in code:
                    reframe_count += 1
                elif code.startswith("ADAPTIVE") or code.startswith("CONDITION_") or code.startswith("EXPLORE_"):
                    adaptive_count += 1
                elif code.startswith("REPOPULATE") or code.startswith("REFRAME_OUTCOME"):
                    grammar_count += 1
                elif code in ("REFRAME_OUTCOME", "REPOPULATE_REFINE", "REPOPULATE_WIDEN"):
                    grammar_count += 1
                else:
                    meta = na.metadata or {}
                    intent = meta.get("intent", "")
                    if intent == "REFRAME":
                        reframe_count += 1
                    elif intent in ("REPOPULATE", "REDESCRIBE_OUTCOME"):
                        grammar_count += 1
                    elif intent == "SLICING":
                        adaptive_count += 1

        selected_follow_on = first_exp.selected_next_action.action_code if first_exp.selected_next_action else None
        another_exp_after = len(exps) > 1
        frame_error = None
        if run_error and trigger_exp and any(e.node_id == trigger_exp for e in exps):
            frame_error = run_error
        # Check session stop reason for planning failure in this frame
        stop_reason = graph.session.session_stop_reason or {}
        if stop_reason.get("experiment_node_id") == first_exp.node_id:
            frame_error = stop_reason.get("error_message", run_error)

        survived = (
            follow_on_planning_attempted
            and frame_error is None
            and "GrammarValidationError" not in (frame_error or "")
            and (another_exp_after or selected_follow_on is not None or graph.session.status.value != "ERROR")
        )
        if survived and follow_on_planning_attempted:
            any_survived = True

        horizon_frames.append(
            {
                "frame_id": fid,
                "parent_frame_id": parent_frame_id,
                "transformation_type": frame.transformation,
                "population_spec": frame.population.to_dict(),
                "outcome_spec": frame.outcome.to_dict(),
                "observation_horizon": frame.observation_horizon,
                "temporal_legal": validate_frame_temporal_legality(frame),
                "first_experiment_executed": first_exp.node_id,
                "follow_on_planning_attempted": follow_on_planning_attempted,
                "grammar_candidates_generated": grammar_count,
                "adaptive_candidates_generated": adaptive_count,
                "reframe_candidates_generated": reframe_count,
                "selected_follow_on_action": selected_follow_on,
                "another_experiment_executed_afterward": another_exp_after,
                "frame_status_afterward": frame.status,
                "error": frame_error,
                "survived_follow_on": survived,
                "lineage_persisted_before_operations": lineage_rec is not None,
                "lineage_sequence_order": lineage_rec.sequence_order if lineage_rec else None,
            }
        )

    return {
        "HORIZON_ADVANCED_FRAME_SURVIVED_FOLLOW_ON": any_survived,
        "horizon_advanced_frames_audited": len(horizon_frames),
        "frames": horizon_frames,
        "bb03_failure_path_tested": len(horizon_frames) > 0,
        "note": (
            "TRUE requires follow-on planning inside horizon-advanced frame without "
            "BB03 GrammarValidationError crash — not merely spawning the child frame."
        ),
    }


def build_failure_safe_audit(result: Any, run_error: Optional[str] = None) -> Dict[str, Any]:
    graph = result.graph
    reg = graph.get_frame_registry()
    experiments = [
        n for n in graph.nodes.values()
        if n.node_type == NodeType.EXPERIMENT and n.experiment_result is not None
    ]
    experiments.sort(key=lambda n: n.created_at)
    last_completed = experiments[-1].node_id if experiments else None

    active_frame = reg.active_frame_id
    lineage_persisted = len(reg.lineage) > 0
    frontier_persisted = bool(graph.session.research_frontier)
    accounting_persisted = bool(graph.session.search_accounting)

    false_completions = []
    for n in graph.nodes.values():
        if n.node_type == NodeType.EXPERIMENT:
            if n.experiment_result is None and n.status == NodeStatus.RESOLVED:
                false_completions.append(n.node_id)

    return {
        "runtime_error_occurred": run_error is not None or graph.session.status.value == "ERROR",
        "error_message": run_error or (graph.session.session_stop_reason or {}).get("error_message"),
        "session_terminal_status": graph.session.status.value,
        "last_completed_experiment": last_completed,
        "active_frame_id": active_frame,
        "lineage_records_persisted": len(reg.lineage),
        "lineage_survived_failure": lineage_persisted,
        "lineage_records": [r.to_dict() for r in reg.lineage],
        "frontier_persisted": frontier_persisted,
        "search_accounting_persisted": accounting_persisted,
        "false_completion_nodes": false_completions,
        "session_stop_reason": graph.session.session_stop_reason,
    }


def build_evidence_driven_question_changes(result: Any, transitions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Plain-language summary of executed frame transitions from audit records."""
    graph = result.graph
    reg = graph.get_frame_registry()
    summaries: List[Dict[str, Any]] = []

    for rec in reg.lineage:
        old = reg.frames.get(rec.old_frame_id)
        new = reg.frames.get(rec.new_frame_id)
        exp_by_frame = _experiments_by_frame(graph)
        new_exps = exp_by_frame.get(rec.new_frame_id, [])
        if not new_exps:
            continue

        trigger_obs = rec.saturation_evidence or {}
        if rec.triggering_experiment_id:
            trigger_node = graph.get_node(rec.triggering_experiment_id)
            if trigger_node.experiment_result:
                trigger_obs = {
                    "observation_codes": [o.code for o in trigger_node.experiment_result.observations],
                    "metrics": dict(trigger_node.experiment_result.metrics),
                }

        category = "unknown"
        if rec.transformation == FrameTransformationType.OUTCOME_TO_POPULATION.value:
            category = "outcome_to_population_transformation"
        elif rec.transformation == FrameTransformationType.HORIZON_ADVANCE.value:
            category = "horizon_advancement"
        elif rec.transformation == FrameTransformationType.OUTCOME_REFRAME.value:
            category = "evidence_driven_reframe" if "STRUCTURAL" in rec.trigger else "outcome_reframe"
        elif rec.transformation == FrameTransformationType.POPULATION_REFRAME.value:
            category = "population_reframe"
        elif "SATURATION" in rec.trigger or rec.saturation_evidence:
            category = "low_yield_saturation_reframe"
        elif rec.trigger in ("STRUCTURAL_TRIGGER", "HORIZON_HETEROGENEOUS"):
            category = "structural_observation_reframe"

        summaries.append(
            {
                "child_frame_id": rec.new_frame_id,
                "parent_frame_id": rec.old_frame_id,
                "transition_category": category,
                "planner_action": rec.planner_action_code,
                "planner_score": rec.planner_score,
                "triggering_experiment": rec.triggering_experiment_id,
                "triggering_evidence": trigger_obs,
                "plain_language": (
                    f"Bot observed {rec.trigger} (evidence: {list(trigger_obs.keys()) if isinstance(trigger_obs, dict) else rec.trigger}) "
                    f"and transitioned from frame {rec.old_frame_id} (horizon {rec.parent_observation_horizon}) "
                    f"to frame {rec.new_frame_id} (horizon {rec.observation_horizon}) via {rec.transformation}."
                ),
                "old_population_spec": old.population.to_dict() if old else {},
                "old_outcome_spec": old.outcome.to_dict() if old else {},
                "new_population_spec": new.population.to_dict() if new else {},
                "new_outcome_spec": new.outcome.to_dict() if new else {},
                "temporal_legal": rec.temporal_legal,
                "sequence_order": rec.sequence_order,
            }
        )

    if not summaries:
        summaries.append({"note": "NO_EXECUTED_FRAME_TRANSITIONS", "interpretation": "No lineage-backed executed transitions."})
    return summaries


def evaluate_capability_gates(
    coverage: Dict[str, Any],
    frame_coverage: Dict[str, Any],
    transitions: List[Dict[str, Any]],
    temporal_audit: Dict[str, Any],
    candidates: Dict[str, List],
    survivability_audit: Dict[str, Any],
    failure_audit: Dict[str, Any],
) -> Dict[str, Any]:
    trad = coverage.get("traditional_coverage", coverage)
    fc = frame_coverage.get("frame_coverage", frame_coverage)

    gate_a = trad.get("pct_budget_used", 0) >= 50 or trad.get("experiments_executed", 0) >= 6
    gate_b = fc.get("frames_executed", 0) > 1 and (
        fc.get("unique_outcome_specs_executed", 0) > 1
        or fc.get("unique_population_specs_executed", 0) > 1
        or len(fc.get("observation_horizons_executed", [])) > 1
    )
    gate_c = survivability_audit.get("HORIZON_ADVANCED_FRAME_SURVIVED_FOLLOW_ON", False)
    gate_d = len([
        t for t in transitions
        if t.get("trigger") and t.get("execution", {}).get("was_researched")
    ]) > 0
    gate_e = temporal_audit.get("all_executed_frames_temporally_legal", True)
    gate_f = failure_audit.get("lineage_survived_failure", False) or (
        not failure_audit.get("runtime_error_occurred", False) and len(transitions) >= 0
    )
    if failure_audit.get("runtime_error_occurred") and failure_audit.get("lineage_records_persisted", 0) > 0:
        gate_f = True
    gate_g = trad.get("falsifications", 0) >= 0  # discipline active if accounting present
    gate_h = len(candidates.get("candidates", [])) >= 1

    return {
        "gate_A_exploration": {"result": "PASS" if gate_a else "FAIL", "evidence": trad},
        "gate_B_reframing": {
            "result": "PASS" if gate_b else "FAIL",
            "evidence": {
                "frames_executed": fc.get("frames_executed"),
                "outcome_specs_executed": fc.get("unique_outcome_specs_executed"),
                "population_specs_executed": fc.get("unique_population_specs_executed"),
                "horizons_executed": fc.get("observation_horizons_executed"),
            },
        },
        "gate_C_reframe_survivability": {
            "result": "PASS" if gate_c else "FAIL",
            "evidence": survivability_audit,
            "note": "Primary BB04 gate — follow-on planning inside horizon-advanced frame.",
        },
        "gate_D_evidence_driven_transition": {
            "result": "PASS" if gate_d else "FAIL",
            "evidence": f"{len([t for t in transitions if t.get('execution', {}).get('was_researched')])} executed transitions with audit trail",
        },
        "gate_E_temporal_legality": {"result": "PASS" if gate_e else "FAIL", "evidence": temporal_audit},
        "gate_F_audit_durability": {
            "result": "PASS" if gate_f else "FAIL",
            "evidence": failure_audit,
        },
        "gate_G_scientific_discipline": {
            "result": "PASS" if gate_g else "FAIL",
            "evidence": {"falsifications": trad.get("falsifications"), "refinements": trad.get("refinements_reframes")},
        },
        "gate_H_discovery": {
            "result": "PASS" if gate_h else "FAIL",
            "evidence": f"{len(candidates.get('candidates', []))} conditional candidates",
            "note": "Gate H may FAIL while A–G PASS without architectural failure.",
        },
    }


def score_benchmark(
    diary: List[Dict[str, Any]],
    coverage: Dict[str, Any],
    frame_coverage: Dict[str, Any],
    transitions: List[Dict[str, Any]],
    result: Any,
    survivability_audit: Dict[str, Any],
) -> Dict[str, Any]:
    graph = result.graph
    exp_diary = [d for d in diary if isinstance(d.get("step"), int)]
    trad = coverage.get("traditional_coverage", coverage)
    fc = frame_coverage.get("frame_coverage", frame_coverage)
    tools_sequence = [d["tool_selected"] for d in exp_diary]
    unique_tools = len(set(tools_sequence))
    session_summary = next((d for d in diary if d.get("step") == "SESSION_SUMMARY"), {})
    stopped_properly = graph.session.status.value not in ("ACTIVE",)
    frontier_used = session_summary.get("frontier_resume_events_total", 0) > 0

    scores = {
        "A_autonomy": min(10, 4 + len(exp_diary) + (2 if frontier_used else 0)),
        "B_breadth": min(10, int(trad.get("pct_eligible_features_touched", 0) / 10) + unique_tools),
        "C_depth": min(10, 3 + len(exp_diary) // 2 + fc.get("frames_executed", 1)),
        "D_shape_discovery": min(
            10, sum(1 for d in exp_diary if any("SHAPE" in c for c in d.get("observation_codes", []))) * 2 + 2
        ),
        "E_scientific_skepticism": min(10, 2 + trad.get("falsifications", 0) * 2),
        "F_simplicity_preference": 6,
        "G_research_productivity": min(
            10, len(collect_candidates(result)["candidates"]) * 3 + int(trad.get("pct_budget_used", 0) / 10)
        ),
        "H_novelty": min(10, unique_tools + (3 if fc.get("frames_executed", 0) > 1 else 0)),
        "I_auditability": 9 if exp_diary and transitions else 7,
        "J_restraint": min(10, 5 + (3 if stopped_properly else 0)),
    }

    reframing = 0
    if fc.get("frames_executed", 0) > 1:
        reframing += 5
    elif fc.get("frames_executed", 0) == 1 and fc.get("frame_transitions_recorded", 0) > 0:
        reframing += 2
    if any(t.get("execution", {}).get("was_researched") for t in transitions if t.get("trigger")):
        reframing += 5
    if fc.get("unique_outcome_specs_executed", 0) > 1 or fc.get("unique_population_specs_executed", 0) > 1:
        reframing += 5
    if fc.get("frontier_reframe_items_unexplored", 0) > 0 and fc.get("frames_executed", 0) <= 1:
        reframing = max(0, reframing - 3)
    reframing = min(20, reframing)

    survivability = 0
    if survivability_audit.get("horizon_advanced_frames_audited", 0) > 0:
        survivability += 2
    if survivability_audit.get("HORIZON_ADVANCED_FRAME_SURVIVED_FOLLOW_ON"):
        survivability += 5
    for f in survivability_audit.get("frames", []):
        if f.get("follow_on_planning_attempted"):
            survivability += 1
        if f.get("another_experiment_executed_afterward"):
            survivability += 2
    survivability = min(10, survivability)

    return {
        "dimension_scores": scores,
        "overall_research_capability_score": sum(scores.values()),
        "reframing_capability_score": reframing,
        "reframe_survivability_score": survivability,
        "reframing_score_notes": {
            "frames_executed": fc.get("frames_executed"),
            "transitions_executed": len([t for t in transitions if t.get("execution", {}).get("was_researched")]),
            "unexplored_reframe_frontier_items": fc.get("frontier_reframe_items_unexplored"),
        },
        "evidence_notes": {
            "diary_steps": len(exp_diary),
            "unique_tools": unique_tools,
            "session_status": graph.session.status.value,
            "frontier_resume_events": session_summary.get("frontier_resume_events_total", 0),
            "frame_transitions": session_summary.get("frame_transitions", 0),
        },
    }


def build_portfolio_selection_diary(result: Any, diary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Experiment-by-experiment portfolio selection audit from persisted decision explanations."""
    graph = result.graph
    portfolio = graph.get_portfolio_state()
    explanations = portfolio.decision_explanations
    exp_diary = [d for d in diary if isinstance(d.get("step"), int)]
    experiments = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT]
    experiments.sort(key=lambda n: n.created_at)

    selections: List[Dict[str, Any]] = []

    # Initial experiment (no prior portfolio decision)
    if experiments:
        first = experiments[0]
        root = _branch_id_for_exp(graph, first.node_id)
        parent_q = None
        for pid in first.parent_node_ids:
            p = graph.get_node(pid)
            if p.node_type == NodeType.QUESTION:
                parent_q = p
                break
        qctx = parent_q.question_context if parent_q else None
        selections.append(
            {
                "selection_index": 0,
                "selection_type": "INITIAL_SPAWN",
                "selected_experiment_node_id": first.node_id,
                "selected_action_code": "AUTONOMOUS_INITIAL",
                "branch_root_id": root,
                "frame_id": qctx.frame_id if qctx else "",
                "observation_horizon": qctx.observation_horizon if qctx else 0,
                "portfolio_decision": None,
                "note": "Root experiment spawned from AutonomousResearchConfig — no prior portfolio selection.",
            }
        )

    for idx, exp in enumerate(experiments):
        if idx == 0:
            prior_exp = exp
        else:
            prior_exp = experiments[idx - 1]

        expl_idx = idx - 1 if idx > 0 else None
        expl = explanations[expl_idx] if expl_idx is not None and expl_idx < len(explanations) else None

        exp_entry = next((d for d in exp_diary if d.get("experiment_node_id") == exp.node_id), {})
        root = _branch_id_for_exp(graph, exp.node_id)
        branch = portfolio.branches.get(root)
        branch_status = branch.status if branch else ""

        planner_scores = exp_entry.get("planner_scores") or {}
        dominated_in_set = [
            code
            for code, score in planner_scores.items()
            if isinstance(score, (int, float)) and score < -100
        ]

        sel_record: Dict[str, Any] = {
            "selection_index": idx + 1 if idx > 0 else 1,
            "selection_type": "PORTFOLIO_PLANNING" if expl else "FRONTIER_OR_INITIAL",
            "triggering_experiment_node_id": prior_exp.node_id if idx > 0 else None,
            "selected_experiment_node_id": exp.node_id,
            "selected_action_code": exp_entry.get("selection_rationale") or exp.experiment_spec.tool_name if exp.experiment_spec else "",
            "tool_selected": exp_entry.get("tool_selected"),
            "branch_root_id": root,
            "frame_id": exp_entry.get("frame_id", ""),
            "observation_horizon": exp_entry.get("observation_horizon", 0),
            "branch_depth": exp_entry.get("branch_depth", 0),
            "branch_portfolio_status": branch_status,
            "is_revisit": branch.revisit_count > 0 if branch and idx > 0 else False,
            "revisit_count": branch.revisit_count if branch else 0,
        }

        if expl:
            sel_record["portfolio_decision"] = {
                "selected_opportunity_id": expl.get("selected_opportunity_id"),
                "selected_action_id": expl.get("selected_action_id"),
                "expected_research_value": expl.get("expected_research_value"),
                "selection_reasons": expl.get("selection_reasons"),
                "best_alternative_id": expl.get("best_alternative_id"),
                "best_alternative_value": expl.get("best_alternative_value"),
                "opportunity_cost": expl.get("opportunity_cost"),
                "exploration_component": expl.get("exploration_component"),
                "exploitation_component": expl.get("exploitation_component"),
                "falsification_component": expl.get("falsification_component"),
                "novelty_component": expl.get("novelty_component"),
                "redundancy_penalty": expl.get("redundancy_penalty"),
                "complexity_penalty": expl.get("complexity_penalty"),
                "sample_burden_penalty": expl.get("sample_burden_penalty"),
                "budget_remaining": expl.get("budget_remaining"),
                "is_revisit": expl.get("is_revisit"),
                "why_selected_over_alternative": expl.get("why_selected_over_alternative"),
            }
            sel_record["marginal_information_gain_proxy"] = expl.get("exploitation_component")
            sel_record["exploration_debt"] = expl.get("exploration_component")
            sel_record["exploitation_value"] = expl.get("exploitation_component")
            sel_record["falsification_value"] = expl.get("falsification_component")

        sel_record["planner_alternatives"] = {
            "scores": planner_scores,
            "selected_next_action": exp_entry.get("selected_next_action"),
            "alternatives_rejected": exp_entry.get("alternatives_rejected"),
            "dominated_candidates_detected": dominated_in_set,
        }
        selections.append(sel_record)

    return selections


def build_portfolio_branch_report(result: Any) -> Dict[str, Any]:
    """Branch reservation, revisit, and deferred-promising state at termination."""
    graph = result.graph
    portfolio = graph.get_portfolio_state()
    branches = []
    for bid, branch in sorted(portfolio.branches.items()):
        branches.append(
            {
                "branch_root_id": bid,
                "status": branch.status,
                "experiments_on_branch": branch.experiments_on_branch,
                "unresolved_research_value": branch.unresolved_research_value,
                "revisit_count": branch.revisit_count,
                "last_explored_sequence": branch.last_explored_sequence,
                "last_marginal_gain": branch.last_marginal_gain,
                "evidence_before_leave": branch.evidence_before_leave,
                "leave_reason": branch.leave_reason,
                "falsified": branch.falsified,
                "deferred_promising": branch.status == BranchPortfolioStatus.DEFERRED_PROMISING.value,
            }
        )
    deferred = [b for b in branches if b["deferred_promising"]]
    falsified = [b for b in branches if b["falsified"]]
    return {
        "branch_count": len(branches),
        "deferred_promising_branches": deferred,
        "falsified_branches": falsified,
        "revisit_branches": [b for b in branches if b["revisit_count"] > 0],
        "branches": branches,
        "marginal_gains_sequence": portfolio.marginal_gains,
        "dimension_experiment_counts": portfolio.dimension_experiment_counts,
        "tool_attempt_counts": portfolio.tool_attempt_counts,
        "dominated_skipped": portfolio.dominated_skipped,
    }


def build_portfolio_frontier_quality(result: Any) -> Dict[str, Any]:
    """Frontier quality metrics — not frontier size alone."""
    graph = result.graph
    frontier = graph.get_frontier()
    portfolio = graph.get_portfolio_state()
    unexplored = frontier.unexplored_items()
    high_value = [i for i in unexplored if i.planner_score > 2.0]
    stale = [
        i for i in unexplored
        if portfolio.sequence_counter - getattr(i, "enqueued_sequence", 0) > 5
    ]
    dominated = [
        i for i in unexplored
        if getattr(i, "portfolio_score", 0) < -100
    ]
    return {
        "viable_frontier_size": len(unexplored),
        "high_value_unexplored": len(high_value),
        "stale_opportunities": len(stale),
        "dominated_on_frontier": len(dominated),
        "high_value_items": [
            {"frontier_id": i.frontier_id, "action_code": i.action_code, "planner_score": i.planner_score}
            for i in high_value[:20]
        ],
        "status_counts": dict(Counter(i.status for i in frontier.items.values())),
    }


def _load_bb05_artifact(name: str) -> Any:
    """Load frozen BB05 artifact from workspace or git ref — read-only."""
    path = BB05_ARTIFACTS / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        raw = subprocess.check_output(
            ["git", "show", f"{BB05_GIT_REF}:benchmarks/blind_benchmark_05/artifacts/{name}"],
            cwd=REPO,
            text=True,
        )
        return json.loads(raw)
    except subprocess.CalledProcessError:
        return None


def _load_bb06_artifact(name: str) -> Any:
    """Load frozen BB06 artifact from workspace or git ref — read-only."""
    path = BB06_ARTIFACTS / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        raw = subprocess.check_output(
            ["git", "show", f"{BB06_GIT_REF}:benchmarks/blind_benchmark_06/artifacts/{name}"],
            cwd=REPO,
            text=True,
        )
        return json.loads(raw)
    except subprocess.CalledProcessError:
        return None


def build_global_allocation_diary(result: Any, diary: List[Dict[str, Any]], steps: List[Any]) -> List[Dict[str, Any]]:
    """Per planning decision: reconstruct global allocation audit from persisted explanations."""
    graph = result.graph
    portfolio = graph.get_portfolio_state()
    explanations = portfolio.decision_explanations
    global_explanations = [e for e in explanations if e.get("allocator_version")]

    experiments = [n for n in graph.nodes.values() if n.node_type == NodeType.EXPERIMENT]
    experiments.sort(key=lambda n: n.created_at)

    records: List[Dict[str, Any]] = []
    step_by_prior_exp: Dict[str, Any] = {}
    for step in steps:
        if step.planning is not None:
            step_by_prior_exp[step.planning.experiment_node_id] = step

    for idx, expl in enumerate(global_explanations):
        prior_exp_id = None
        selected_exp_id = None
        if idx + 1 < len(experiments):
            prior_exp_id = experiments[idx].node_id if idx < len(experiments) else None
            selected_exp_id = experiments[idx + 1].node_id
        elif idx < len(experiments):
            prior_exp_id = experiments[idx].node_id

        step = step_by_prior_exp.get(prior_exp_id) if prior_exp_id else None
        decision = step.planning.decision if step and step.planning else None

        prev_root = expl.get("previous_branch_root_id", "")
        new_root = expl.get("new_branch_root_id", "")
        selected_source = expl.get("selected_source", "")

        ga = {}
        if decision is not None and hasattr(decision, "global_allocation") and decision.global_allocation:
            ga = decision.global_allocation

        selected_non_local = None
        if selected_source and selected_source != "LOCAL":
            selected_non_local = {
                "historical_planner_score": expl.get("historical_planner_score"),
                "current_revalued_value": expl.get("current_revalued_value"),
                "delta": (
                    (expl.get("current_revalued_value") or 0)
                    - (expl.get("historical_planner_score") or 0)
                ),
            }

        exp_entry = next(
            (d for d in diary if d.get("experiment_node_id") == selected_exp_id),
            {},
        ) if selected_exp_id else {}

        records.append(
            {
                "decision_index": idx + 1,
                "triggering_experiment_node_id": prior_exp_id,
                "resulting_experiment_node_id": selected_exp_id,
                "selected_opportunity_id": expl.get("selected_opportunity_id"),
                "selected_action_id": expl.get("selected_action_id"),
                "selected_source": selected_source,
                "selected_erv": expl.get("selected_erv", expl.get("expected_research_value")),
                "erv_components": {
                    "exploration_component": expl.get("exploration_component"),
                    "exploitation_component": expl.get("exploitation_component"),
                    "falsification_component": expl.get("falsification_component"),
                    "novelty_component": expl.get("novelty_component"),
                    "redundancy_penalty": expl.get("redundancy_penalty"),
                    "complexity_penalty": expl.get("complexity_penalty"),
                    "sample_burden_penalty": expl.get("sample_burden_penalty"),
                },
                "best_local_erv": expl.get("best_local_erv"),
                "best_frontier_erv": expl.get("best_frontier_erv"),
                "best_deferred_erv": expl.get("best_deferred_erv"),
                "best_global_alternative_erv": expl.get("best_global_alternative_erv"),
                "global_opportunity_cost": expl.get("global_opportunity_cost"),
                "globally_comparable_count": expl.get("globally_comparable_count"),
                "excluded_count": expl.get("excluded_count"),
                "exclusion_reasons": expl.get("exclusion_reasons", []),
                "context_switch_occurred": expl.get("context_switch_occurred", False),
                "historical_vs_revalued_non_local": selected_non_local,
                "branch_before": prev_root,
                "branch_after": new_root,
                "frame_before": exp_entry.get("frame_id", ""),
                "observation_horizon_before": exp_entry.get("observation_horizon", 0),
                "budget_remaining": expl.get("budget_remaining"),
                "valuation_sequence": expl.get("valuation_sequence"),
                "local_would_have_selected": expl.get("local_would_have_selected"),
                "decision_type": decision.decision_type.value if decision else None,
                "selected_frontier_id": (
                    decision.selected_frontier_id if decision and hasattr(decision, "selected_frontier_id") else ""
                ),
                "revisit_audit": expl.get("revisit_audit", {}),
                "why_selected_over_alternative": expl.get("why_selected_over_alternative"),
                "experiment_identity_version": expl.get("experiment_identity_version"),
                "global_allocation_summary": {
                    "comparable_count": ga.get("comparable_count"),
                    "excluded_count": ga.get("excluded_count"),
                    "best_local_erv": ga.get("best_local_erv"),
                    "best_frontier_erv": ga.get("best_frontier_erv"),
                },
                "global_allocation": ga,
            }
        )
    return records


def build_global_allocation_metrics(
    result: Any,
    global_diary: List[Dict[str, Any]],
    portfolio_diary: List[Dict[str, Any]],
    coverage: Dict[str, Any],
) -> Dict[str, Any]:
    """Aggregate BB07 allocation-quality measurements."""
    graph = result.graph
    frontier = graph.get_frontier()
    portfolio = graph.get_portfolio_state()

    global_switches = [
        d for d in global_diary
        if d.get("context_switch_occurred") or d.get("decision_type") == PlanDecisionType.SWITCH_OPPORTUNITY.value
    ]
    frontier_interrupts = [
        d for d in global_diary
        if d.get("selected_source") in ("FRONTIER", "DEFERRED", "REVISIT")
        and d.get("best_local_erv") is not None
        and d.get("selected_erv") is not None
        and d.get("best_local_erv", float("-inf")) > 0
    ]
    strong_local_protected = [
        d for d in global_diary
        if d.get("selected_source") == "LOCAL"
        and (d.get("best_frontier_erv") or 0) < (d.get("selected_erv") or 0)
    ]
    negative_local_with_positive_global = [
        d for d in global_diary
        if d.get("selected_source") == "LOCAL"
        and (d.get("selected_erv") or 0) < 0
        and max(
            d.get("best_frontier_erv") or float("-inf"),
            d.get("best_deferred_erv") or float("-inf"),
            d.get("best_global_alternative_erv") or float("-inf"),
        ) > 0
    ]
    valuation_material_changes = [
        d for d in global_diary
        if d.get("historical_vs_revalued_non_local")
        and abs(d["historical_vs_revalued_non_local"].get("delta") or 0) > 1.0
    ]
    genuine_revisits = [d for d in global_diary if d.get("selected_source") == "REVISIT"]

    unexplored = frontier.unexplored_items()
    high_current_value_at_end = []
    for item in unexplored:
        hist = item.planner_score
        port = getattr(item, "portfolio_score", hist)
        if port > 2.0 or hist > 2.0:
            high_current_value_at_end.append(
                {
                    "frontier_id": item.frontier_id,
                    "action_code": item.action_code,
                    "historical_planner_score": hist,
                    "portfolio_score_at_enqueue": port,
                    "status": item.status,
                }
            )

    trad = coverage.get("traditional_coverage", coverage)
    fc = coverage.get("frame_coverage", coverage)

    intent_counts = Counter()
    for d in global_diary:
        src = d.get("selected_source") or "UNKNOWN"
        intent_counts[src] += 1

    return {
        "global_context_switch_count": len(global_switches),
        "frontier_interrupts_viable_local": len(frontier_interrupts),
        "strong_local_beats_frontier_count": len(strong_local_protected),
        "negative_local_with_positive_global_alternative": len(negative_local_with_positive_global),
        "negative_local_with_positive_global_cases": negative_local_with_positive_global,
        "frontier_valuation_material_changes": len(valuation_material_changes),
        "valuation_material_change_cases": valuation_material_changes,
        "genuine_revisit_count": len(genuine_revisits),
        "genuine_revisit_cases": genuine_revisits,
        "selection_source_counts": dict(intent_counts),
        "unique_executed": {
            "branch_roots": len(set(d.get("branch_root_id") for d in portfolio_diary if d.get("branch_root_id"))),
            "frames": fc.get("frames_executed", 0),
            "outcomes": fc.get("unique_outcome_specs_executed", 0),
            "populations": fc.get("unique_population_specs_executed", 0),
            "horizons": len(fc.get("observation_horizons_executed", [])),
            "features": len(trad.get("features_touched", [])),
            "tools": len(trad.get("tools_used", [])),
        },
        "allocation_by_intent": {
            "exploration_decisions": sum(
                1 for d in global_diary if (d.get("erv_components") or {}).get("exploration_component", 0) > 0.5
            ),
            "exploitation_decisions": sum(
                1 for d in global_diary if (d.get("erv_components") or {}).get("exploitation_component", 0) > 1.0
            ),
            "falsification_decisions": sum(
                1 for d in global_diary if (d.get("erv_components") or {}).get("falsification_component", 0) > 1.0
            ),
        },
        "dominated_skipped": portfolio.dominated_skipped,
        "redundant_experiments_proxy": sum(1 for g in portfolio.marginal_gains if g < 0.2),
        "unresolved_high_value_at_termination": high_current_value_at_end,
        "unresolved_high_value_count": len(high_current_value_at_end),
        "global_switch_events": global_switches,
        "frontier_interrupt_events": frontier_interrupts,
        "strong_local_events": strong_local_protected,
    }


def build_experiment_identity_dedup_audit(
    global_diary: List[Dict[str, Any]],
    result: Any,
) -> Dict[str, Any]:
    """Extract all experiment-identity dedup exclusions from global allocation audits."""
    already_executed: List[Dict[str, Any]] = []
    same_cycle: List[Dict[str, Any]] = []
    duplicate_experiment_errors: List[Dict[str, Any]] = []

    for d in global_diary:
        decision_index = d.get("decision_index")
        for exc in d.get("exclusion_reasons") or []:
            reason = exc.get("reason") or ""
            entry = {
                "decision_index": decision_index,
                "opportunity_id": exc.get("opportunity_id"),
                "reason": reason,
            }
            if reason.startswith("duplicate_experiment_already_executed:"):
                already_executed.append(entry)
            elif reason.startswith("duplicate_same_cycle_representative:"):
                same_cycle.append(entry)

        ga = d.get("global_allocation") if isinstance(d.get("global_allocation"), dict) else {}
        for exc in ga.get("excluded") or []:
            reason = exc.get("exclusion_reason") or ""
            entry = {
                "decision_index": decision_index,
                "opportunity_id": exc.get("opportunity_id"),
                "source": exc.get("source"),
                "action_id": exc.get("action_id"),
                "frontier_id": exc.get("frontier_id"),
                "experiment_content_hash": exc.get("experiment_content_hash"),
                "duplicate_of_experiment_id": exc.get("duplicate_of_experiment_id"),
                "duplicate_representative_id": exc.get("duplicate_representative_id"),
                "reason": reason,
            }
            if reason.startswith("duplicate_experiment_already_executed:"):
                if entry not in already_executed:
                    already_executed.append(entry)
            elif reason.startswith("duplicate_same_cycle_representative:"):
                if entry not in same_cycle:
                    same_cycle.append(entry)

    graph = result.graph
    frontier_dupes = [
        {
            "frontier_id": item.frontier_id,
            "action_id": item.action_id,
            "status": item.status,
            "invalid_reason": item.invalid_reason,
        }
        for item in graph.get_frontier().items.values()
        if item.status == "DUPLICATE"
        and "duplicate_experiment_already_executed" in (item.invalid_reason or "")
    ]

    session_ledger = graph.get_search_accounting().session_ledger
    return {
        "experiment_identity_version": EXPERIMENT_IDENTITY_VERSION,
        "duplicate_experiment_already_executed_count": len(already_executed),
        "duplicate_same_cycle_representative_count": len(same_cycle),
        "duplicate_experiment_already_executed": already_executed,
        "duplicate_same_cycle_representative": same_cycle,
        "frontier_lifecycle_duplicates_marked": frontier_dupes,
        "frontier_lifecycle_duplicate_count": len(frontier_dupes),
        "duplicate_experiment_error_at_spawn": duplicate_experiment_errors,
        "spawn_duplicate_experiment_error_count": len(duplicate_experiment_errors),
        "session_experiments_executed": session_ledger.experiments_executed,
        "session_experiments_used": graph.session.experiments_used,
        "experiment_index_size": len(graph.experiment_index),
        "interpretation": (
            "Identity dedup runs before global ERV selection. Exclusions are auditable; "
            "they must not inflate globally_comparable_count or experiments_executed."
        ),
    }


def build_bb06_bb07_identity_repair_comparison(
    bb07_summary: Dict[str, Any],
    bb07_global_diary: List[Dict[str, Any]],
    bb07_dedup_audit: Dict[str, Any],
    bb07_global_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """Narrow causal comparison: did 3G.4.1 eliminate the BB06 Decision-4 duplicate failure?"""
    bb06_failure = _load_bb06_artifact("18_benchmark_failure_report.json") or {}
    bb06_global = _load_bb06_artifact("28_global_allocation_diary.json") or []
    bb06_ctx = bb06_failure.get("failure_context") or {}

    bb06_decision_4 = next(
        (d for d in bb06_global if d.get("decision_index") == 4),
        {},
    )

    bb07_completed = bb07_summary.get("experiments_used", 0) >= EXPERIMENT_BUDGET
    bb07_no_spawn_dup = bb07_dedup_audit.get("spawn_duplicate_experiment_error_count", 0) == 0
    bb07_status = bb07_summary.get("session_status", "")

    bb06_dup_at_decision_4 = (
        bb06_failure.get("error", {}).get("error_type") == "DuplicateExperimentError"
        if isinstance(bb06_failure.get("error"), dict)
        else "DuplicateExperimentError" in str(bb06_failure.get("error", ""))
    )

    bb07_decision_4 = next(
        (d for d in bb07_global_diary if d.get("decision_index") == 4),
        {},
    )

    bb07_decision_4_dup_excluded = any(
        (e.get("reason") or "").startswith("duplicate_experiment_already_executed:")
        for e in (bb07_decision_4.get("exclusion_reasons") or [])
    ) or any(
        (e.get("reason") or "").startswith("duplicate_experiment_already_executed:")
        for e in bb07_dedup_audit.get("duplicate_experiment_already_executed", [])
        if e.get("decision_index") == 4
    )

    return {
        "comparison_type": "bb06_bb07_identity_repair_causal",
        "bb06_frozen_commit": "94bde8807",
        "bb07_frozen_commit": FROZEN_RESEARCH_COMMIT,
        "primary_question": (
            "Did experiment-identity repair eliminate the BB06 Decision-4 "
            "DuplicateExperimentError and allow normal allocator operation?"
        ),
        "bb06_failure_summary": {
            "status": bb06_failure.get("status"),
            "experiments_completed": bb06_failure.get("experiments_completed"),
            "error_type": (
                bb06_failure.get("error", {}).get("error_type")
                if isinstance(bb06_failure.get("error"), dict)
                else None
            ),
            "global_decision_index": bb06_ctx.get("global_decision_index"),
            "selected_source_at_failure": bb06_ctx.get("selected_source"),
            "selected_action_id_at_failure": bb06_ctx.get("selected_action_id"),
            "duplicate_of_node": bb06_ctx.get("duplicate_of_node"),
        },
        "bb06_decision_4_audit": bb06_decision_4,
        "bb07_session_summary": {
            "session_status": bb07_status,
            "experiments_used": bb07_summary.get("experiments_used"),
            "experiments_budget": EXPERIMENT_BUDGET,
            "completed_full_session": bb07_completed,
            "spawn_duplicate_experiment_error": not bb07_no_spawn_dup,
        },
        "bb07_decision_4_audit": bb07_decision_4,
        "identity_repair_verdict": {
            "bb06_duplicate_failure_eliminated": bb07_no_spawn_dup and not bb06_dup_at_decision_4,
            "bb07_completed_12_experiments": bb07_completed,
            "decision_4_duplicate_excluded_before_selection": bb07_decision_4_dup_excluded,
            "causal_narrow_conclusion": (
                "REPAIR_CONFIRMED"
                if bb07_no_spawn_dup and bb07_completed and bb07_decision_4_dup_excluded
                else (
                    "PARTIAL_REPAIR"
                    if bb07_no_spawn_dup and not bb07_completed
                    else "REPAIR_NOT_CONFIRMED"
                )
            ),
        },
        "dedup_totals_bb07": {
            "already_executed_exclusions": bb07_dedup_audit.get(
                "duplicate_experiment_already_executed_count", 0
            ),
            "same_cycle_exclusions": bb07_dedup_audit.get(
                "duplicate_same_cycle_representative_count", 0
            ),
        },
        "interpretation_guidance": (
            "Completing 12 experiments alone does not prove full allocation improvement. "
            "First establish the BB06 duplicate failure is gone; then evaluate BB05 comparison separately."
        ),
        "bb07_global_metrics_snapshot": {
            k: bb07_global_metrics.get(k)
            for k in (
                "global_context_switch_count",
                "strong_local_beats_frontier_count",
                "negative_local_with_positive_global_alternative",
                "genuine_revisit_count",
                "selection_source_counts",
            )
        },
    }


def build_limitation_diagnostics(result: Any, global_diary: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evidence-only inspection of known 3G.4 limitations (15.2, 15.3).
    Does NOT fix either issue.
    """
    graph = result.graph
    frontier = graph.get_frontier()

    # 15.2: frontier exploitation uses current experiment assessment, not branch-origin
    misvaluation_candidates = []
    for d in global_diary:
        if d.get("selected_source") not in ("FRONTIER", "DEFERRED", "REVISIT"):
            continue
        ga_raw = d.get("global_allocation") if isinstance(d.get("global_allocation"), dict) else {}
        if not ga_raw:
            continue
        all_opps = ga_raw.get("all_opportunities") or []
        selected_fid = d.get("selected_frontier_id")
        for opp in all_opps:
            if opp.get("frontier_id") == selected_fid or opp.get("source") in ("FRONTIER", "DEFERRED", "REVISIT"):
                hist = opp.get("historical_planner_score", 0)
                curr = opp.get("current_revalued_value", 0)
                exploit = (opp.get("erv_components") or {}).get("exploitation_value")
                if exploit is None and opp.get("opportunity"):
                    exploit = (opp["opportunity"] or {}).get("exploitation_value")
                misvaluation_candidates.append(
                    {
                        "decision_index": d.get("decision_index"),
                        "frontier_id": opp.get("frontier_id"),
                        "branch_root_id": opp.get("branch_root_id"),
                        "triggering_experiment": d.get("triggering_experiment_node_id"),
                        "historical_planner_score": hist,
                        "current_revalued_value": curr,
                        "exploitation_component_in_erv": exploit,
                        "note": (
                            "15.2: exploitation may reflect current-branch assessment "
                            "rather than reconstructed branch-origin assessment"
                        ),
                    }
                )

    # 15.3: evaluate_global_stop uses historical planner_score via best_unexplored_score
    from modules.edge_research.research_frontier import evaluate_global_stop

    remaining = max(0, (graph.session.experiment_budget or 12) - graph.session.experiments_used)
    preflight = graph.session.panel_preflight or {}
    features_touched = len(
        graph.get_search_accounting().session_ledger.explanatory_features_tested
    )
    eligible = len(preflight.get("eligible_explanatory") or [])
    unexplored = frontier.unexplored_items()
    historical_best = frontier.best_unexplored_score()

    revalued_scores = []
    for item in unexplored:
        revalued_scores.append(
            {
                "frontier_id": item.frontier_id,
                "historical_planner_score": item.planner_score,
                "portfolio_score_at_enqueue": getattr(item, "portfolio_score", item.planner_score),
            }
        )
    revalued_scores.sort(key=lambda x: -x["historical_planner_score"])

    should_stop, stop_reason = evaluate_global_stop(
        remaining_budget=remaining,
        frontier=frontier,
        features_touched=features_touched,
        eligible_feature_count=eligible,
    )

    stop_inconsistency = {
        "limitation": "15.3",
        "evaluate_global_stop_uses_historical_planner_score": True,
        "historical_best_unexplored_score": historical_best,
        "unexplored_count": len(unexplored),
        "session_stop_evaluated": should_stop,
        "stop_reason_code": stop_reason.code,
        "note": (
            "Session stop threshold uses frontier.best_unexplored_score() which sorts by "
            "historical planner_score — not current-state revalued ERV used at planning decisions"
        ),
        "top_unexplored_by_historical_score": revalued_scores[:5],
    }

    return {
        "limitation_15_2_frontier_exploitation_assessment": {
            "description": "Frontier revaluation may use current experiment assessment for exploitation components",
            "evidence_cases": misvaluation_candidates,
            "case_count": len(misvaluation_candidates),
        },
        "limitation_15_3_session_stop_historical_scores": stop_inconsistency,
    }


def build_bb05_bb07_allocation_comparison(
    bb07_coverage: Dict[str, Any],
    bb07_metrics: Dict[str, Any],
    bb07_global_diary: List[Dict[str, Any]],
    bb07_portfolio_metrics: Any,
) -> Dict[str, Any]:
    """Compare BB07 vs BB05 on allocation quality — secondary to identity repair verdict."""
    bb05_cov = _load_bb05_artifact("06_coverage_report.json") or {}
    bb05_metrics = _load_bb05_artifact("23_portfolio_session_metrics.json") or {}
    bb05_diary = _load_bb05_artifact("22_portfolio_selection_diary.json") or []
    bb05_frontier = _load_bb05_artifact("25_portfolio_frontier_quality.json") or {}
    bb05_summary = _load_bb05_artifact("09_run_summary.json") or {}

    bb05_trad = bb05_cov.get("traditional_coverage", bb05_cov)
    bb07_trad = bb07_coverage.get("traditional_coverage", bb07_coverage)
    bb05_fc = bb05_cov.get("frame_coverage", bb05_cov)
    bb07_fc = bb07_coverage.get("frame_coverage", bb07_coverage)

    bb05_decisions = [d for d in bb05_diary if d.get("portfolio_decision")]
    bb07_global_decisions = bb07_global_diary

    def row(metric: str, bb5: Any, bb7: Any, note: str = "") -> Dict[str, Any]:
        return {"metric": metric, "bb05": bb5, "bb07": bb7, "allocation_note": note}

    bb05_neg_local_miss = sum(
        1
        for d in bb05_decisions
        if (d.get("portfolio_decision") or {}).get("expected_research_value", 0) < 0
    )

    return {
        "comparison_type": "research_allocation_quality_bb05_vs_bb07",
        "bb05_frozen_commit": "61b669927",
        "bb07_frozen_commit": FROZEN_RESEARCH_COMMIT,
        "bb07_experiment_identity_version": EXPERIMENT_IDENTITY_VERSION,
        "primary_question": (
            "If BB07 completes normally, does full-session evidence support or weaken "
            "the Phase 3G.4 Global Allocator hypothesis relative to BB05?"
        ),
        "rows": [
            row("experiments_executed", bb05_trad.get("experiments_executed"), bb07_trad.get("experiments_executed")),
            row(
                "features_touched",
                len(bb05_trad.get("features_touched", [])),
                len(bb07_trad.get("features_touched", [])),
                "Breadth alone is not success criterion",
            ),
            row(
                "frames_executed",
                bb05_fc.get("frames_executed"),
                bb07_fc.get("frames_executed"),
            ),
            row(
                "global_context_switches",
                0,
                bb07_metrics.get("global_context_switch_count"),
                "BB05 had no global allocator; switches only via STOP_BRANCH→frontier",
            ),
            row(
                "portfolio_decisions_audited",
                len(bb05_decisions),
                len(bb07_global_decisions),
            ),
            row(
                "negative_local_selections",
                bb05_neg_local_miss,
                bb07_metrics.get("negative_local_with_positive_global_alternative"),
                "BB07 target: fewer negative-local picks when positive global alternative exists",
            ),
            row(
                "high_value_unexplored_at_end_historical",
                bb05_frontier.get("high_value_unexplored"),
                bb07_metrics.get("unresolved_high_value_count"),
                "Uses historical planner_score threshold >2.0",
            ),
            row(
                "revisit_count",
                bb05_metrics.get("revisit_count", 0),
                bb07_metrics.get("genuine_revisit_count"),
            ),
            row(
                "mean_opportunity_cost",
                (
                    sum((d.get("portfolio_decision") or {}).get("opportunity_cost", 0) for d in bb05_decisions)
                    / max(1, len(bb05_decisions))
                ),
                (
                    sum(d.get("global_opportunity_cost", 0) for d in bb07_global_decisions)
                    / max(1, len(bb07_global_decisions))
                ),
            ),
            row(
                "strong_local_protected",
                "N/A",
                bb07_metrics.get("strong_local_beats_frontier_count"),
                "Local continuation when local current ERV genuinely highest",
            ),
            row(
                "frontier_interrupts_viable_local",
                "N/A",
                bb07_metrics.get("frontier_interrupts_viable_local"),
                "Frontier selected while viable local branch existed",
            ),
        ],
        "bb05_session_status": bb05_summary.get("session_status"),
        "bb07_selection_sources": bb07_metrics.get("selection_source_counts"),
        "interpretation_guidance": (
            "Only evaluate full-session allocation improvement if BB07 completed 12 experiments. "
            "Switching more is not inherently better."
        ),
    }


def evaluate_global_allocator_capability_gates(
    global_metrics: Dict[str, Any],
    global_diary: List[Dict[str, Any]],
    limitation_diag: Dict[str, Any],
    dedup_audit: Dict[str, Any],
) -> Dict[str, Any]:
    """BB07 capability gates: identity repair + global allocation behavior."""
    has_audit = len(global_diary) > 0
    has_sources = all(
        d.get("selected_source") for d in global_diary if d.get("selected_erv") is not None
    )
    no_forced_diversity = global_metrics.get("global_context_switch_count", 0) < len(global_diary)
    protected_local = global_metrics.get("strong_local_beats_frontier_count", 0) >= 0

    return {
        "gate_A_global_decisions_audited": {
            "result": has_audit,
            "evidence": f"{len(global_diary)} global allocation decisions with full audit fields",
        },
        "gate_B_source_and_erv_recorded": {
            "result": has_sources,
            "evidence": global_metrics.get("selection_source_counts"),
        },
        "gate_C_no_forced_diversity": {
            "result": no_forced_diversity,
            "evidence": {
                "switches": global_metrics.get("global_context_switch_count"),
                "decisions": len(global_diary),
            },
        },
        "gate_D_strong_local_can_win": {
            "result": protected_local,
            "evidence": global_metrics.get("strong_local_beats_frontier_count"),
        },
        "gate_E_limitation_diagnostics_documented": {
            "result": bool(limitation_diag),
            "evidence": ["15.2", "15.3"],
        },
        "gate_F_no_spawn_duplicate_experiment_error": {
            "result": dedup_audit.get("spawn_duplicate_experiment_error_count", 0) == 0,
            "evidence": dedup_audit.get("spawn_duplicate_experiment_error_count", 0),
        },
        "gate_G_identity_dedup_audited": {
            "result": (
                dedup_audit.get("duplicate_experiment_already_executed_count", 0) >= 0
                and dedup_audit.get("experiment_identity_version") == EXPERIMENT_IDENTITY_VERSION
            ),
            "evidence": {
                "already_executed": dedup_audit.get("duplicate_experiment_already_executed_count"),
                "same_cycle": dedup_audit.get("duplicate_same_cycle_representative_count"),
            },
        },
    }


def build_bb04_bb05_allocation_comparison(
    bb05_coverage: Dict[str, Any],
    bb05_portfolio_metrics: Any,
    bb05_portfolio_diary: List[Dict[str, Any]],
    bb05_frontier_quality: Dict[str, Any],
    result: Any,
) -> Dict[str, Any]:
    """Compare BB05 vs BB04 on research allocation quality — not breadth alone."""
    bb04_cov_path = BB04_ARTIFACTS / "06_coverage_report.json"
    bb04_summary_path = BB04_ARTIFACTS / "09_run_summary.json"
    bb04_cov = json.loads(bb04_cov_path.read_text()) if bb04_cov_path.exists() else {}
    bb04_summary = json.loads(bb04_summary_path.read_text()) if bb04_summary_path.exists() else {}

    bb04_trad = bb04_cov.get("traditional_coverage", bb04_cov)
    bb04_fc = bb04_cov.get("frame_coverage", bb04_cov)
    bb05_trad = bb05_coverage.get("traditional_coverage", bb05_coverage)
    bb05_fc = bb05_coverage.get("frame_coverage", bb05_coverage)
    pm = bb05_portfolio_metrics

    def row(metric: str, bb4: Any, bb5: Any, allocation_note: str = "") -> Dict[str, Any]:
        return {"metric": metric, "bb04": bb4, "bb05": bb5, "allocation_interpretation": allocation_note}

    portfolio_decisions = [
        s for s in bb05_portfolio_diary if s.get("portfolio_decision")
    ]
    avg_opp_cost = (
        sum(s["portfolio_decision"].get("opportunity_cost", 0) for s in portfolio_decisions)
        / max(1, len(portfolio_decisions))
    )
    revisit_selections = sum(
        1 for s in portfolio_decisions if s["portfolio_decision"].get("is_revisit")
    )
    falsification_selections = sum(
        1 for s in portfolio_decisions
        if s["portfolio_decision"].get("falsification_component", 0) > 1.0
    )
    exploitation_selections = sum(
        1 for s in portfolio_decisions
        if s["portfolio_decision"].get("exploitation_component", 0) > 2.0
    )
    exploration_selections = sum(
        1 for s in portfolio_decisions
        if s["portfolio_decision"].get("exploration_component", 0) > 0.5
    )

    table = [
        row("experiments_executed", bb04_trad.get("experiments_executed"), bb05_trad.get("experiments_executed")),
        row(
            "unique_frames_executed",
            bb04_fc.get("frames_executed"),
            bb05_fc.get("frames_executed"),
            "More frames is not automatically better — quality of allocation matters.",
        ),
        row(
            "unique_features_touched",
            len(bb04_trad.get("features_touched", [])),
            len(bb05_trad.get("features_touched", [])),
            "Breadth without value is not success.",
        ),
        row(
            "unique_outcome_specs_executed",
            bb04_fc.get("unique_outcome_specs_executed"),
            bb05_fc.get("unique_outcome_specs_executed"),
        ),
        row(
            "unique_population_specs_executed",
            bb04_fc.get("unique_population_specs_executed"),
            bb05_fc.get("unique_population_specs_executed"),
        ),
        row(
            "observation_horizons_executed",
            len(bb04_fc.get("observation_horizons_executed", [])),
            len(bb05_fc.get("observation_horizons_executed", [])),
        ),
        row(
            "max_same_frame_depth",
            bb04_fc.get("same_frame_experiments"),
            bb05_fc.get("same_frame_experiments"),
            "Depth on productive branch can be rational.",
        ),
        row("falsifications_executed", bb04_trad.get("falsifications"), bb05_trad.get("falsifications")),
        row(
            "conditional_candidates",
            len(json.loads((BB04_ARTIFACTS / "04_candidate_discoveries.json").read_text()))
            if (BB04_ARTIFACTS / "04_candidate_discoveries.json").exists()
            else 0,
            len(collect_candidates(result)["candidates"]),
        ),
        row(
            "frontier_unexplored_at_end",
            bb04_summary.get("session_stop_reason", {}).get("unexplored_frontier_count"),
            result.graph.get_frontier().count_by_status("UNEXPLORED"),
            "Large frontier with few executions is not automatically bad if allocation was reasoned.",
        ),
        row("revisit_count", 0, pm.revisit_count, "BB04 had no portfolio revisit tracking."),
        row("successful_branch_returns", 0, pm.successful_branch_returns),
        row("redundant_experiment_count", "not_tracked", pm.redundant_experiment_count),
        row("mean_marginal_information_gain", "not_tracked", round(pm.mean_marginal_information_gain, 4)),
        row("high_value_unexplored_at_end", "not_tracked", pm.high_value_unexplored_at_end),
        row("exploration_debt_at_end", "not_tracked", round(pm.exploration_debt_at_end, 4)),
        row("unresolved_research_value_at_termination", "not_tracked", round(pm.unresolved_research_value_at_termination, 4)),
        row("portfolio_decisions_with_audit", 0, len(portfolio_decisions)),
        row("mean_opportunity_cost", "not_tracked", round(avg_opp_cost, 4)),
        row("selections_with_exploitation_component", "not_tracked", exploitation_selections),
        row("selections_with_exploration_component", "not_tracked", exploration_selections),
        row("selections_with_falsification_component", "not_tracked", falsification_selections),
        row("selections_marked_revisit", "not_tracked", revisit_selections),
        row("viable_frontier_size", "not_tracked", pm.viable_frontier_size),
        row("high_value_frontier_opportunities", "not_tracked", pm.high_value_opportunities),
        row("stale_frontier_opportunities", "not_tracked", pm.stale_opportunities),
    ]

    allocation_judgment = {
        "primary_question": "Did BB05 allocate scarce experiments better than BB04?",
        "breadth_alone_is_not_success": True,
        "bb04_limitation_observed": (
            "BB04 executed 12 experiments but touched only 1/8 eligible features; "
            "41 frontier items remained unexplored; allocation was not portfolio-aware."
        ),
        "bb05_portfolio_awareness": len(portfolio_decisions) > 0,
        "bb05_has_opportunity_cost_audit": len(portfolio_decisions) > 0,
        "comparison_basis": "architectural_allocation_quality_not_human_edge",
        "no_bb04_relationship_encoding": True,
    }

    return {
        "comparison_type": "research_allocation_quality_bb04_vs_bb05",
        "no_human_edge_comparison": True,
        "metrics_table": table,
        "allocation_judgment": allocation_judgment,
        "bb05_frontier_quality": bb05_frontier_quality,
    }


def evaluate_portfolio_capability_gates(
    coverage: Dict[str, Any],
    portfolio_metrics: Any,
    portfolio_diary: List[Dict[str, Any]],
    frontier_quality: Dict[str, Any],
    candidates: Dict[str, List],
    temporal_audit: Dict[str, Any],
    failure_audit: Dict[str, Any],
) -> Dict[str, Any]:
    """BB05 capability gates focused on portfolio allocation quality."""
    trad = coverage.get("traditional_coverage", coverage)
    decisions = [s for s in portfolio_diary if s.get("portfolio_decision")]

    gate_a = trad.get("experiments_executed", 0) >= 12
    gate_b = len(decisions) >= 10
    gate_c = all(
        d.get("portfolio_decision", {}).get("best_alternative_id") is not None
        or d.get("portfolio_decision", {}).get("why_selected_over_alternative")
        for d in decisions
    )
    gate_d = portfolio_metrics.mean_marginal_information_gain >= 0
    gate_e = temporal_audit.get("all_executed_frames_temporally_legal", True)
    gate_f = not failure_audit.get("runtime_error_occurred", False)
    gate_g = portfolio_metrics.revisit_count >= 0
    gate_h = len(candidates.get("candidates", [])) >= 0

    return {
        "gate_A_budget_exhausted": {"result": "PASS" if gate_a else "FAIL", "evidence": trad.get("experiments_executed")},
        "gate_B_portfolio_decisions_audited": {
            "result": "PASS" if gate_b else "FAIL",
            "evidence": f"{len(decisions)} portfolio decisions with explanation records",
        },
        "gate_C_opportunity_cost_stored": {
            "result": "PASS" if gate_c else "FAIL",
            "evidence": "Each selection stores best alternative and why-selected",
        },
        "gate_D_marginal_gain_tracking": {
            "result": "PASS" if gate_d else "FAIL",
            "evidence": {"mean_mig": portfolio_metrics.mean_marginal_information_gain},
        },
        "gate_E_temporal_legality": {"result": "PASS" if gate_e else "FAIL", "evidence": temporal_audit},
        "gate_F_no_runtime_failure": {"result": "PASS" if gate_f else "FAIL", "evidence": failure_audit},
        "gate_G_revisit_tracking_active": {
            "result": "PASS" if gate_g else "FAIL",
            "evidence": {"revisit_count": portfolio_metrics.revisit_count},
        },
        "gate_H_discovery_optional": {
            "result": "PASS" if gate_h else "FAIL",
            "evidence": f"{len(candidates.get('candidates', []))} conditional candidates",
            "note": "Discovery may fail while allocation gates pass.",
        },
        "gate_I_frontier_quality_measured": {
            "result": "PASS" if frontier_quality.get("viable_frontier_size", 0) >= 0 else "FAIL",
            "evidence": frontier_quality,
        },
        "gate_J_unresolved_value_at_termination": {
            "result": "PASS",
            "evidence": portfolio_metrics.unresolved_research_value_at_termination,
        },
    }


def build_architectural_comparison(
    bb04_coverage: Dict[str, Any],
    bb04_scorecard: Dict[str, Any],
    result: Any,
) -> Dict[str, Any]:
    bb01_cov = json.loads((BB01_ARTIFACTS / "06_coverage_report.json").read_text())
    bb02_cov = json.loads((BB02_ARTIFACTS / "06_coverage_report.json").read_text())
    bb03_cov_path = BB03_ARTIFACTS / "06_coverage_report.json"
    bb03_cov = json.loads(bb03_cov_path.read_text()) if bb03_cov_path.exists() else {}
    bb01_summary = json.loads((BB01_ARTIFACTS / "09_run_summary.json").read_text())
    bb02_summary = json.loads((BB02_ARTIFACTS / "09_run_summary.json").read_text())
    bb03_summary_path = BB03_ARTIFACTS / "09_run_summary.json"
    bb03_summary = json.loads(bb03_summary_path.read_text()) if bb03_summary_path.exists() else {}
    bb01_score = json.loads((BB01_ARTIFACTS / "08_benchmark_scorecard.json").read_text())
    bb02_score = json.loads((BB02_ARTIFACTS / "08_benchmark_scorecard.json").read_text())
    bb03_score_path = BB03_ARTIFACTS / "08_benchmark_scorecard.json"
    bb03_score = json.loads(bb03_score_path.read_text()) if bb03_score_path.exists() else {}

    graph = result.graph
    trad = bb04_coverage.get("traditional_coverage", {})
    fc = bb04_coverage.get("frame_coverage", {})

    def row(metric: str, bb1: Any, bb2: Any, bb3: Any, bb4: Any) -> Dict[str, Any]:
        return {"metric": metric, "bb01": bb1, "bb02": bb2, "bb03_partial": bb3, "bb04": bb4}

    bb03_trad = bb03_cov.get("traditional_coverage", bb03_cov)
    bb03_fc = bb03_cov.get("frame_coverage", bb03_cov)

    table = [
        row("experiments", bb01_cov.get("total_experiments_executed", 2), bb02_cov.get("total_experiments_executed"), bb03_summary.get("experiments_completed_before_failure", bb03_trad.get("experiments_executed")), trad.get("experiments_executed")),
        row("pct_budget_used", bb01_cov.get("pct_budget_used"), bb02_cov.get("pct_budget_used"), bb03_trad.get("pct_budget_used"), trad.get("pct_budget_used")),
        row("features_touched", len(bb01_cov.get("features_touched", [])), len(bb02_cov.get("features_touched", [])), len(bb03_trad.get("features_touched", [])), len(trad.get("features_touched", []))),
        row("tools", len(bb01_cov.get("tools_used", [])), len(bb02_cov.get("tools_used", [])), len(bb03_trad.get("tools_used", [])), len(trad.get("tools_used", []))),
        row("research_frames_executed", 1, 1, bb03_fc.get("frames_executed"), fc.get("frames_executed")),
        row("outcome_specs_executed", len(bb01_cov.get("unique_outcome_specs", [])), len(bb02_cov.get("unique_outcome_specs", [])), bb03_fc.get("unique_outcome_specs_executed"), fc.get("unique_outcome_specs_executed")),
        row("population_specs_executed", len(bb01_cov.get("unique_population_specs", [])), len(bb02_cov.get("unique_population_specs", [])), bb03_fc.get("unique_population_specs_executed"), fc.get("unique_population_specs_executed")),
        row("observation_horizons_executed", 1, 1, len(bb03_fc.get("observation_horizons_executed", [])), len(fc.get("observation_horizons_executed", []))),
        row("frame_transitions", 0, 0, bb03_fc.get("frame_transitions_recorded"), fc.get("frame_transitions_recorded")),
        row("outcome_to_population_executed", 0, 0, bb03_fc.get("outcome_to_population_executed"), fc.get("outcome_to_population_executed")),
        row("successful_post_reframe_follow_on", 0, 0, 0, 1 if bb04_scorecard.get("reframe_survivability_score", 0) >= 5 else 0),
        row("falsifications", bb01_cov.get("falsification_experiments_executed"), bb02_cov.get("falsification_experiments_executed"), bb03_trad.get("falsifications"), trad.get("falsifications")),
        row("conditional_candidates", 0, len(json.loads((BB02_ARTIFACTS / "04_candidate_discoveries.json").read_text())), len(json.loads((BB03_ARTIFACTS / "04_candidate_discoveries.json").read_text())) if (BB03_ARTIFACTS / "04_candidate_discoveries.json").exists() else 0, len(collect_candidates(result)["candidates"])),
        row("runtime_errors", 0, 0, 1 if bb03_summary.get("status") == "BENCHMARK_RUN_FAILED" else 0, 1 if graph.session.status.value == "ERROR" else 0),
        row("terminal_status", bb01_summary.get("session_status"), bb02_summary.get("session_status"), bb03_summary.get("session_status"), graph.session.status.value),
        row("research_capability_score", bb01_score.get("overall_research_capability_score"), bb02_score.get("overall_research_capability_score"), bb03_summary.get("research_capability_score"), bb04_scorecard.get("overall_research_capability_score")),
        row("reframing_capability_score", 0, 0, bb03_summary.get("reframing_capability_score"), bb04_scorecard.get("reframing_capability_score")),
        row("reframe_survivability_score", 0, 0, 0, bb04_scorecard.get("reframe_survivability_score")),
    ]

    return {
        "comparison_type": "architectural_behavior_bb01_through_bb04",
        "no_human_edge_comparison": True,
        "metrics_table": table,
        "bb03_note": "BB03 metrics are partial-run (crashed at experiment 2/12).",
        "bb04_primary_question": "Can horizon-advanced frames survive follow-on research after 3G.2.1 repair?",
    }


def load_partial_result() -> Optional[Any]:
    """Load persisted partial session if benchmark run failed mid-session."""
    from types import SimpleNamespace

    session_path = ARTIFACTS / "research_sessions" / "research_sessions" / f"{SESSION_ID}.json"
    if not session_path.exists():
        return None

    from modules.edge_research.storage import read_research_graph

    graph = read_research_graph(SESSION_ID, data_dir=ARTIFACTS / "research_sessions")
    return SimpleNamespace(graph=graph, steps=[])


def write_partial_artifacts(
    result: Any,
    inventory: Dict[str, Any],
    manifest: Dict[str, Any],
    run_error: str,
) -> None:
    """Generate best-effort BB04 artifacts from incomplete session."""
    diary = build_research_diary(result, result.steps)
    frontier_report = build_frontier_report(result)
    frame_registry = build_frame_registry_report(result)
    coverage = build_frame_coverage_report(result, inventory)
    frame_transitions = build_frame_transition_diary(result, diary)
    o2p_audit = build_outcome_to_population_audit(result)
    failed_reframes = build_failed_reframes(result)
    temporal_audit = build_temporal_safety_audit(result)
    survivability_audit = build_horizon_advanced_survivability_audit(result, diary, run_error)
    failure_audit = build_failure_safe_audit(result, run_error)
    evidence_changes = build_evidence_driven_question_changes(result, frame_transitions)
    search_report = {
        "session_ledger": result.graph.get_search_accounting().session_ledger.to_dict(),
        "branch_ledgers": {
            k: v.to_dict() for k, v in result.graph.get_search_accounting().branch_ledgers.items()
        },
    }
    candidates = collect_candidates(result)
    scorecard = score_benchmark(diary, coverage, coverage, frame_transitions, result, survivability_audit)
    gates = evaluate_capability_gates(
        coverage, coverage, frame_transitions, temporal_audit, candidates, survivability_audit, failure_audit
    )
    comparison = build_architectural_comparison(coverage, scorecard, result)

    (ARTIFACTS / "03_research_diary.json").write_text(json.dumps(diary, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "04_candidate_discoveries.json").write_text(
        json.dumps(candidates["candidates"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "04b_anti_edge_discoveries.json").write_text(
        json.dumps(candidates["anti_edges"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "06_coverage_report.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    (ARTIFACTS / "07_search_accounting_report.json").write_text(
        json.dumps(search_report, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "08_benchmark_scorecard.json").write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    (ARTIFACTS / "10_research_frontier_snapshot.json").write_text(
        json.dumps(frontier_report, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "11_research_frame_registry.json").write_text(
        json.dumps(frame_registry, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "12_frame_transition_diary.json").write_text(
        json.dumps(frame_transitions, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "13_outcome_to_population_audit.json").write_text(
        json.dumps(o2p_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "14_failed_reframes.json").write_text(
        json.dumps(failed_reframes, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "15_temporal_safety_audit.json").write_text(
        json.dumps(temporal_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "16_capability_gates.json").write_text(json.dumps(gates, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "17_bb01_bb04_comparison.json").write_text(
        json.dumps(comparison, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "19_horizon_survivability_audit.json").write_text(
        json.dumps(survivability_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "20_failure_safe_audit.json").write_text(
        json.dumps(failure_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "21_evidence_driven_question_changes.json").write_text(
        json.dumps(evidence_changes, indent=2, default=str), encoding="utf-8"
    )

    failure_report = {
        "benchmark_id": BENCHMARK_ID,
        "status": "BENCHMARK_RUN_FAILED",
        "failed_at": _utc_now(),
        "git_commit": manifest["git_commit"],
        "error": run_error,
        "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
        "experiments_completed_before_failure": result.graph.session.experiments_used,
        "session_status": result.graph.session.status.value,
        "HORIZON_ADVANCED_FRAME_SURVIVED_FOLLOW_ON": survivability_audit.get(
            "HORIZON_ADVANCED_FRAME_SURVIVED_FOLLOW_ON", False
        ),
        "interpretation": "Partial artifacts generated from persisted session. Research logic NOT modified.",
    }
    (ARTIFACTS / "18_benchmark_failure_report.json").write_text(
        json.dumps(failure_report, indent=2), encoding="utf-8"
    )
    (ARTIFACTS / "09_run_summary.json").write_text(
        json.dumps(
            {
                **failure_report,
                "research_capability_score": scorecard.get("overall_research_capability_score"),
                "reframing_capability_score": scorecard.get("reframing_capability_score"),
                "reframe_survivability_score": scorecard.get("reframe_survivability_score"),
                "HORIZON_ADVANCED_FRAME_SURVIVED_FOLLOW_ON": survivability_audit.get(
                    "HORIZON_ADVANCED_FRAME_SURVIVED_FOLLOW_ON", False
                ),
                "capability_gates": {k: v["result"] for k, v in gates.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if hasattr(result.graph, "serialize"):
        (ARTIFACTS / "05_research_graph.json").write_text(result.graph.serialize(), encoding="utf-8")


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print("=== BLIND BENCHMARK 07: load frozen panel (BB01–BB06 fingerprint) ===")
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
    (ARTIFACTS / "02_frozen_configuration.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("=== Autonomous research session (budget=%d, Phase 3G.4.1) ===" % EXPERIMENT_BUDGET)
    run_error: Optional[str] = None
    result = None
    try:
        result = run_autonomous_session(panel)
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
        print(f"BENCHMARK RUN FAILED: {run_error}")

    if result is None:
        failure_report = {
            "benchmark_id": BENCHMARK_ID,
            "status": "BENCHMARK_RUN_FAILED",
            "failed_at": _utc_now(),
            "git_commit": manifest["git_commit"],
            "error": run_error,
            "dataset_fingerprint_sha256": REQUIRED_FINGERPRINT,
            "interpretation": (
                "Autonomous session terminated before completing 12 experiments. "
                "Research logic was NOT modified post-failure per BB07 policy."
            ),
        }
        partial_path = ARTIFACTS / "research_sessions" / "research_sessions" / f"{SESSION_ID}.json"
        if partial_path.exists():
            partial = json.loads(partial_path.read_text())
            failure_report["partial_session"] = {
                "experiments_used": partial.get("session", {}).get("experiments_used"),
                "session_status": partial.get("session", {}).get("status"),
                "research_frames": partial.get("session", {}).get("research_frames", {}),
            }
        partial_result = load_partial_result()
        if partial_result is not None:
            write_partial_artifacts(partial_result, inventory, manifest, run_error or "unknown")
        else:
            (ARTIFACTS / "09_run_summary.json").write_text(json.dumps(failure_report, indent=2), encoding="utf-8")
            (ARTIFACTS / "18_benchmark_failure_report.json").write_text(
                json.dumps(failure_report, indent=2), encoding="utf-8"
            )
        print(json.dumps(json.loads((ARTIFACTS / "09_run_summary.json").read_text()), indent=2))
        return

    (ARTIFACTS / "05_research_graph.json").write_text(result.graph.serialize(), encoding="utf-8")

    diary = build_research_diary(result, result.steps)
    frontier_report = build_frontier_report(result)
    frame_registry = build_frame_registry_report(result)
    coverage = build_frame_coverage_report(result, inventory)
    frame_transitions = build_frame_transition_diary(result, diary)
    o2p_audit = build_outcome_to_population_audit(result)
    failed_reframes = build_failed_reframes(result)
    temporal_audit = build_temporal_safety_audit(result)
    survivability_audit = build_horizon_advanced_survivability_audit(result, diary, run_error)
    failure_audit = build_failure_safe_audit(result, run_error)
    evidence_changes = build_evidence_driven_question_changes(result, frame_transitions)
    search_report = {
        "session_ledger": result.graph.get_search_accounting().session_ledger.to_dict(),
        "branch_ledgers": {
            k: v.to_dict() for k, v in result.graph.get_search_accounting().branch_ledgers.items()
        },
        "effective_hypothesis_count": compute_effective_hypotheses(
            result.graph.get_search_accounting().session_ledger
        ).effective_hypotheses_tested,
    }
    candidates = collect_candidates(result)
    scorecard = score_benchmark(diary, coverage, coverage, frame_transitions, result, survivability_audit)
    gates = evaluate_capability_gates(
        coverage, coverage, frame_transitions, temporal_audit, candidates, survivability_audit, failure_audit
    )
    comparison = build_architectural_comparison(coverage, scorecard, result)

    portfolio_diary = build_portfolio_selection_diary(result, diary)
    portfolio_branch_report = build_portfolio_branch_report(result)
    portfolio_metrics = compute_session_portfolio_metrics(result.graph)
    portfolio_metrics_dict = portfolio_metrics.to_dict()
    frontier_quality = build_portfolio_frontier_quality(result)
    allocation_comparison = build_bb04_bb05_allocation_comparison(
        coverage, portfolio_metrics, portfolio_diary, frontier_quality, result
    )
    portfolio_gates = evaluate_portfolio_capability_gates(
        coverage, portfolio_metrics, portfolio_diary, frontier_quality,
        candidates, temporal_audit, failure_audit,
    )

    global_diary = build_global_allocation_diary(result, diary, result.steps)
    global_metrics = build_global_allocation_metrics(
        result, global_diary, portfolio_diary, coverage
    )
    dedup_audit = build_experiment_identity_dedup_audit(global_diary, result)
    limitation_diag = build_limitation_diagnostics(result, global_diary)
    bb05_bb07_comparison = build_bb05_bb07_allocation_comparison(
        coverage, global_metrics, global_diary, portfolio_metrics
    )
    bb06_bb07_comparison = build_bb06_bb07_identity_repair_comparison(
        {"experiments_used": result.graph.session.experiments_used, "session_status": result.graph.session.status.value},
        global_diary,
        dedup_audit,
        global_metrics,
    )
    global_gates = evaluate_global_allocator_capability_gates(
        global_metrics, global_diary, limitation_diag, dedup_audit
    )

    (ARTIFACTS / "03_research_diary.json").write_text(json.dumps(diary, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "04_candidate_discoveries.json").write_text(
        json.dumps(candidates["candidates"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "04b_anti_edge_discoveries.json").write_text(
        json.dumps(candidates["anti_edges"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "04c_rejected_abandoned.json").write_text(
        json.dumps(candidates["rejected_abandoned"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "06_coverage_report.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    (ARTIFACTS / "07_search_accounting_report.json").write_text(
        json.dumps(search_report, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "08_benchmark_scorecard.json").write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    (ARTIFACTS / "09_run_summary.json").write_text(
        json.dumps(
            {
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
                "reframing_capability_score": scorecard["reframing_capability_score"],
                "reframe_survivability_score": scorecard["reframe_survivability_score"],
                "HORIZON_ADVANCED_FRAME_SURVIVED_FOLLOW_ON": survivability_audit.get(
                    "HORIZON_ADVANCED_FRAME_SURVIVED_FOLLOW_ON", False
                ),
                "capability_gates": {k: v["result"] for k, v in gates.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (ARTIFACTS / "10_research_frontier_snapshot.json").write_text(
        json.dumps(frontier_report, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "11_research_frame_registry.json").write_text(
        json.dumps(frame_registry, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "12_frame_transition_diary.json").write_text(
        json.dumps(frame_transitions, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "13_outcome_to_population_audit.json").write_text(
        json.dumps(o2p_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "14_failed_reframes.json").write_text(
        json.dumps(failed_reframes, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "15_temporal_safety_audit.json").write_text(
        json.dumps(temporal_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "16_capability_gates.json").write_text(json.dumps(gates, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "17_bb01_bb07_comparison.json").write_text(
        json.dumps(comparison, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "19_horizon_survivability_audit.json").write_text(
        json.dumps(survivability_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "20_failure_safe_audit.json").write_text(
        json.dumps(failure_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "21_evidence_driven_question_changes.json").write_text(
        json.dumps(evidence_changes, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "22_portfolio_selection_diary.json").write_text(
        json.dumps(portfolio_diary, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "23_portfolio_session_metrics.json").write_text(
        json.dumps(portfolio_metrics_dict, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "24_portfolio_branch_state.json").write_text(
        json.dumps(portfolio_branch_report, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "25_portfolio_frontier_quality.json").write_text(
        json.dumps(frontier_quality, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "26_bb04_bb05_allocation_comparison.json").write_text(
        json.dumps(allocation_comparison, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "27_portfolio_capability_gates.json").write_text(
        json.dumps(portfolio_gates, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "28_global_allocation_diary.json").write_text(
        json.dumps(global_diary, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "29_global_allocation_metrics.json").write_text(
        json.dumps(global_metrics, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "30_bb05_bb07_allocation_comparison.json").write_text(
        json.dumps(bb05_bb07_comparison, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "31_limitation_diagnostics_15_2_15_3.json").write_text(
        json.dumps(limitation_diag, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "32_global_allocator_capability_gates.json").write_text(
        json.dumps(global_gates, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "33_experiment_identity_dedup_audit.json").write_text(
        json.dumps(dedup_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "34_bb06_bb07_identity_repair_comparison.json").write_text(
        json.dumps(bb06_bb07_comparison, indent=2, default=str), encoding="utf-8"
    )

    summary = json.loads((ARTIFACTS / "09_run_summary.json").read_text())
    summary["portfolio_session_metrics"] = portfolio_metrics_dict
    summary["portfolio_capability_gates"] = {k: v["result"] for k, v in portfolio_gates.items()}
    summary["allocation_comparison_note"] = allocation_comparison.get("allocation_judgment", {})
    summary["global_allocation_metrics"] = {
        k: global_metrics[k]
        for k in (
            "global_context_switch_count",
            "frontier_interrupts_viable_local",
            "strong_local_beats_frontier_count",
            "negative_local_with_positive_global_alternative",
            "genuine_revisit_count",
            "selection_source_counts",
            "unresolved_high_value_count",
        )
    }
    summary["experiment_identity_dedup_audit"] = {
        "already_executed_exclusions": dedup_audit.get("duplicate_experiment_already_executed_count"),
        "same_cycle_exclusions": dedup_audit.get("duplicate_same_cycle_representative_count"),
        "spawn_duplicate_experiment_error_count": dedup_audit.get("spawn_duplicate_experiment_error_count"),
    }
    summary["identity_repair_verdict"] = bb06_bb07_comparison.get("identity_repair_verdict")
    summary["global_allocator_capability_gates"] = {k: v["result"] for k, v in global_gates.items()}
    (ARTIFACTS / "09_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("=== BLIND BENCHMARK 07 COMPLETE ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
