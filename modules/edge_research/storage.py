"""
Isolated persistence for Edge Research Engine V1.

ONLY writer to data/edge_research/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.contracts import (
    DISCOVERY_RUN_COLUMNS,
    EDGE_EPISODE_REGISTRY_COLUMNS,
    EDGE_FORWARD_LEDGER_COLUMNS,
    EDGE_HYPOTHESIS_LEDGER_COLUMNS,
    EDGE_MEMORY_COLUMNS,
    EDGE_VALIDATION_HISTORY_COLUMNS,
    ENGINE_VERSION,
)

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "edge_research"

LEDGER_FILES: Dict[str, Tuple[str, ...]] = {
    "edge_hypothesis_ledger.csv": EDGE_HYPOTHESIS_LEDGER_COLUMNS,
    "edge_episode_registry.csv": EDGE_EPISODE_REGISTRY_COLUMNS,
    "edge_validation_history.csv": EDGE_VALIDATION_HISTORY_COLUMNS,
    "edge_memory.csv": EDGE_MEMORY_COLUMNS,
    "edge_forward_ledger.csv": EDGE_FORWARD_LEDGER_COLUMNS,
    "discovery_runs.csv": DISCOVERY_RUN_COLUMNS,
}

STATUS_FILE = "engine_status.json"
DISCOVERY_RUN_FILE = "latest_discovery_run.json"
PANEL_CACHE_FILE = "research_panel_cache.csv"


def resolve_data_dir(explicit: Optional[Path] = None) -> Path:
    env = os.environ.get("EDGE_RESEARCH_DATA_DIR")
    if explicit is not None:
        return Path(explicit)
    if env:
        return Path(env)
    return DEFAULT_DATA_DIR


def ensure_storage(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    for filename, columns in LEDGER_FILES.items():
        path = root / filename
        if not path.exists():
            pd.DataFrame(columns=list(columns)).to_csv(path, index=False)
    status_path = root / STATUS_FILE
    if not status_path.exists():
        write_status(
            {
                "engine_version": ENGINE_VERSION,
                "phase": "discovery",
                "hypotheses": 0,
                "validated_edges": 0,
                "independent_episodes": 0,
                "last_research_event": "NONE",
            },
            data_dir=root,
        )
    return root


def write_status(payload: Dict[str, Any], data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / STATUS_FILE
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_status(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = resolve_data_dir(data_dir)
    path = root / STATUS_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_ledger(name: str, data_dir: Optional[Path] = None) -> pd.DataFrame:
    root = resolve_data_dir(data_dir)
    path = root / name
    if not path.exists():
        cols = LEDGER_FILES.get(name, ())
        return pd.DataFrame(columns=list(cols))
    return pd.read_csv(path)


def count_ledger_rows(name: str, data_dir: Optional[Path] = None) -> int:
    df = read_ledger(name, data_dir=data_dir)
    if df.empty:
        return 0
    return int(len(df.dropna(how="all")))


def write_panel_cache(df: pd.DataFrame, data_dir: Optional[Path] = None) -> Path:
    root = ensure_storage(data_dir)
    path = root / PANEL_CACHE_FILE
    df.to_csv(path, index=False)
    return path


def read_panel_cache(data_dir: Optional[Path] = None) -> pd.DataFrame:
    root = resolve_data_dir(data_dir)
    path = root / PANEL_CACHE_FILE
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def write_discovery_run(payload: Dict[str, Any], data_dir: Optional[Path] = None) -> Path:
    root = ensure_storage(data_dir)
    path = root / DISCOVERY_RUN_FILE
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    dq = payload.get("data_quality", {})
    row = {
        "run_id": payload.get("run_id"),
        "timestamp": payload.get("timestamp"),
        "research_version": payload.get("research_version"),
        "discovery_start_date": payload.get("discovery_start_date"),
        "discovery_end_date": payload.get("discovery_end_date"),
        "observation_count": dq.get("total_observations"),
        "eligible_observation_count": dq.get("eligible_observations"),
        "valid_market_state_count": dq.get("valid_market_state_count"),
        "unknown_market_state_count": dq.get("unknown_market_state_count"),
        "valid_t3_count": dq.get("valid_t3_count"),
        "valid_t5_count": dq.get("valid_t5_count"),
        "valid_t10_count": dq.get("valid_t10_count"),
        "distinct_states": dq.get("distinct_states"),
        "distinct_transitions": dq.get("distinct_transitions"),
        "market_contexts_analyzed": payload.get("market_contexts_analyzed"),
        "conditions_tested": payload.get("conditions_tested"),
        "rejected_insufficient_sample": payload.get("rejected_insufficient_sample"),
        "rejected_no_incremental_edge": payload.get("rejected_no_incremental_edge"),
        "promoted_candidates": payload.get("promoted_candidates"),
    }
    ledger = read_ledger("discovery_runs.csv", data_dir=root)
    ledger = pd.concat([ledger, pd.DataFrame([row])], ignore_index=True)
    ledger.to_csv(root / "discovery_runs.csv", index=False)
    return path


def read_discovery_run(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = resolve_data_dir(data_dir)
    path = root / DISCOVERY_RUN_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _next_edge_id(ledger: pd.DataFrame) -> str:
    if ledger.empty or "edge_id" not in ledger.columns:
        return "EDGE-000001"
    ids = ledger["edge_id"].dropna().astype(str)
    nums = []
    for eid in ids:
        if eid.startswith("EDGE-"):
            try:
                nums.append(int(eid.split("-")[1]))
            except ValueError:
                pass
    n = max(nums) + 1 if nums else 1
    return f"EDGE-{n:06d}"


def load_existing_condition_keys(data_dir: Optional[Path] = None) -> set[str]:
    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir=data_dir)
    if ledger.empty:
        return set()
    keys = set()
    for _, row in ledger.iterrows():
        transition = str(row.get("market_transition", ""))
        f1 = str(row.get("feature_1", ""))
        t1 = str(row.get("threshold_1", ""))
        f2 = row.get("feature_2", "")
        t2 = row.get("threshold_2", "")
        parts = [f"{f1}:{t1}"]
        if pd.notna(f2) and str(f2):
            parts.append(f"{f2}:{t2}")
        keys.add(f"{transition}|{'|'.join(sorted(parts))}")
    return keys


def append_candidates(
    candidates: Sequence[Any],
    data_dir: Optional[Path] = None,
    existing_keys: Optional[set[str]] = None,
) -> int:
    """Append new candidates to hypothesis ledger; returns count of new rows."""
    from datetime import datetime, timezone

    root = ensure_storage(data_dir)
    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir=root)
    keys = existing_keys or load_existing_condition_keys(root)
    new_rows: List[Dict[str, Any]] = []
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for cand in candidates:
        dedup_key = f"{cand.market_transition}|{cand.condition_text}"
        if dedup_key in keys or cand.condition_key in keys:
            continue
        keys.add(dedup_key)
        keys.add(cand.condition_key)
        edge_id = _next_edge_id(ledger if not new_rows else pd.concat([ledger, pd.DataFrame(new_rows)]))
        clauses = list(cand.clauses)
        f1 = clauses[0] if len(clauses) > 0 else None
        f2 = clauses[1] if len(clauses) > 1 else None
        cp = cand.profiles.get("candidate", {})
        bp = cand.profiles.get("baseline", {})
        inc = cand.incremental
        row = {
            "edge_id": edge_id,
            "created_at": created,
            "research_version": ENGINE_VERSION,
            "market_state": cand.market_state,
            "market_transition": cand.market_transition,
            "baseline_type": cand.baseline_type,
            "condition_text": cand.condition_text,
            "feature_1": f1.feature if f1 else "",
            "operator_1": f1.operator if f1 else "",
            "threshold_1": f1.threshold_hi if f1 and f1.threshold_hi is not None else (f1.threshold_lo if f1 else ""),
            "feature_2": f2.feature if f2 else "",
            "operator_2": f2.operator if f2 else "",
            "threshold_2": f2.threshold_hi if f2 and f2.threshold_hi is not None else (f2.threshold_lo if f2 else ""),
            "candidate_n": cand.candidate_n,
            "baseline_n": cand.baseline_n,
            "best_horizon": cand.best_horizon,
            "candidate_mean": cp.get("candidate_mean"),
            "baseline_mean": bp.get("baseline_mean"),
            "incremental_mean": inc.get("incremental_mean"),
            "candidate_median": cp.get("candidate_median"),
            "baseline_median": bp.get("baseline_median"),
            "incremental_median": inc.get("incremental_median"),
            "candidate_win_rate": cp.get("candidate_win_rate"),
            "baseline_win_rate": bp.get("baseline_win_rate"),
            "incremental_win_rate": inc.get("incremental_win_rate"),
            "candidate_downside_3": cp.get("candidate_rate_le_minus_3"),
            "baseline_downside_3": bp.get("baseline_rate_le_minus_3"),
            "candidate_downside_5": cp.get("candidate_rate_le_minus_5"),
            "baseline_downside_5": bp.get("baseline_rate_le_minus_5"),
            "status": cand.status,
            "discovery_start_date": cand.discovery_start_date,
            "discovery_end_date": cand.discovery_end_date,
            "oos_status": "NOT_TESTED",
            "notes": "",
        }
        new_rows.append(row)

    if not new_rows:
        return 0
    ledger = pd.concat([ledger, pd.DataFrame(new_rows)], ignore_index=True)
    ledger.to_csv(root / "edge_hypothesis_ledger.csv", index=False)
    return len(new_rows)


def read_top_candidates(data_dir: Optional[Path] = None, limit: int = 10) -> List[Dict[str, Any]]:
    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir=data_dir)
    if ledger.empty:
        return []
    df = ledger[ledger["status"] == "CANDIDATE"].copy()
    if df.empty:
        return []
    df = df.sort_values("incremental_median", ascending=False, na_position="last")
    return df.head(limit).to_dict(orient="records")
