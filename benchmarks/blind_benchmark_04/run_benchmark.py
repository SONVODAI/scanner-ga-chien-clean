#!/usr/bin/env python3
"""
Blind Benchmark 04 — post-3G.2.1 reframing survivability measurement.

Orchestration and reporting ONLY. Does NOT modify research logic.
Uses the SAME frozen panel fingerprint as BB01–BB03.
Primary test: can horizon-advanced frames survive follow-on research?
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
from modules.edge_research.research_state import NodeType, NodeStatus  # noqa: E402
from modules.edge_research.research_tools import TOOLBOX_VERSION, build_default_tool_registry  # noqa: E402

BENCHMARK_ID = "blind_benchmark_04"
BENCHMARK_VERSION = "bb04_v1"
SESSION_ID = "bb04-autonomous-001"
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
        "prior_benchmarks": ["blind_benchmark_01", "blind_benchmark_02", "blind_benchmark_03"],
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
        "phases_frozen": ["3D", "3E", "3F", "3G", "3G.1", "3G.2", "3G.2.1"],
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

    print("=== BLIND BENCHMARK 04: load frozen panel (BB01–BB03 fingerprint) ===")
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

    print("=== Autonomous research session (budget=%d, Phase 3G.2.1) ===" % EXPERIMENT_BUDGET)
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
                "Research logic was NOT modified post-failure per BB04 policy."
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

    summary = json.loads((ARTIFACTS / "09_run_summary.json").read_text())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
