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
    CHALLENGER_RUN_COLUMNS,
    DISCOVERY_RUN_COLUMNS,
    EDGE_EPISODE_REGISTRY_COLUMNS,
    EDGE_FORWARD_LEDGER_COLUMNS,
    EDGE_HYPOTHESIS_LEDGER_COLUMNS,
    EDGE_MEMORY_COLUMNS,
    EDGE_ROBUSTNESS_HISTORY_COLUMNS,
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
    "edge_robustness_history.csv": EDGE_ROBUSTNESS_HISTORY_COLUMNS,
    "challenger_runs.csv": CHALLENGER_RUN_COLUMNS,
}

# Challenger persistence schema — explicit dtypes before categorical assignment.
HYPOTHESIS_LEDGER_STRING_COLUMNS: Tuple[str, ...] = (
    "robustness_status",
    "robustness_run_id",
    "fragility_flags",
    "rejection_reasons",
    "main_fragility_flag",
)

HYPOTHESIS_LEDGER_NULLABLE_INT_COLUMNS: Tuple[str, ...] = (
    "observed_episodes",
    "positive_episodes",
    "negative_episodes",
    "mixed_episodes",
    "date_count",
    "unique_symbol_count",
)

ROBUSTNESS_HISTORY_STRING_COLUMNS: Tuple[str, ...] = (
    "run_id",
    "edge_id",
    "timestamp",
    "test_name",
    "test_version",
    "result",
    "reason",
)

EPISODE_REGISTRY_STRING_COLUMNS: Tuple[str, ...] = (
    "episode_id",
    "episode_version",
    "start_date",
    "end_date",
    "start_state",
    "end_state",
    "transition_sequence",
    "candidate_edge_id",
    "candidate_best_horizon",
    "episode_result",
)

CHALLENGER_RUN_STRING_COLUMNS: Tuple[str, ...] = (
    "run_id",
    "timestamp",
    "robustness_config_version",
    "episode_config_version",
    "discovery_run_id",
    "candidate_ledger_hash",
    "ledger_hash",
    "report_status",
    "superseded_by",
    "superseded_reason",
    "dataset_start",
    "dataset_end",
)


def _coerce_string_columns(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = df[col].astype("string")
    return df


def _coerce_nullable_int_columns(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df


def normalize_hypothesis_ledger_dtypes(ledger: pd.DataFrame) -> pd.DataFrame:
    """Ensure challenger-written columns accept categorical strings after CSV reload."""
    if ledger.empty:
        return ledger
    ledger = ledger.copy()
    _coerce_string_columns(ledger, HYPOTHESIS_LEDGER_STRING_COLUMNS)
    _coerce_nullable_int_columns(ledger, HYPOTHESIS_LEDGER_NULLABLE_INT_COLUMNS)
    return ledger


def normalize_robustness_history_dtypes(ledger: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        return ledger
    ledger = ledger.copy()
    return _coerce_string_columns(ledger, ROBUSTNESS_HISTORY_STRING_COLUMNS)


def normalize_episode_registry_dtypes(ledger: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        return ledger
    ledger = ledger.copy()
    return _coerce_string_columns(ledger, EPISODE_REGISTRY_STRING_COLUMNS)


def normalize_challenger_run_dtypes(ledger: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        return ledger
    ledger = ledger.copy()
    return _coerce_string_columns(ledger, CHALLENGER_RUN_STRING_COLUMNS)

STATUS_FILE = "engine_status.json"
DISCOVERY_RUN_FILE = "latest_discovery_run.json"
CHALLENGER_RUN_FILE = "latest_challenger_run.json"
PANEL_CACHE_FILE = "research_panel_cache.csv"
RESEARCH_SESSIONS_DIR = "research_sessions"


def resolve_data_dir(explicit: Optional[Path] = None) -> Path:
    env = os.environ.get("EDGE_RESEARCH_DATA_DIR")
    if explicit is not None:
        return Path(explicit)
    if env:
        return Path(env)
    return DEFAULT_DATA_DIR


def resolve_production_runs_root(data_dir: Optional[Path] = None) -> Path:
    """
    Canonical root for production daily runs, assessments, voices, manifests.

    Accepts either the edge data dir (``data/edge_research``) or an already-canonical
    ``.../production_observations`` path. Never double-nests.
    """
    root = resolve_data_dir(data_dir)
    if root.name == "production_observations":
        return root
    return root / "production_observations"


def ensure_storage(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / RESEARCH_SESSIONS_DIR).mkdir(parents=True, exist_ok=True)
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
    expected_cols = LEDGER_FILES.get(name, ())
    if not path.exists():
        return pd.DataFrame(columns=list(expected_cols))
    df = pd.read_csv(path)
    for col in expected_cols:
        if col not in df.columns:
            df[col] = pd.NA
    if name == "edge_hypothesis_ledger.csv":
        df = normalize_hypothesis_ledger_dtypes(df)
    elif name == "edge_robustness_history.csv":
        df = normalize_robustness_history_dtypes(df)
    elif name == "edge_episode_registry.csv":
        df = normalize_episode_registry_dtypes(df)
    elif name == "challenger_runs.csv":
        df = normalize_challenger_run_dtypes(df)
    return df


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


def ledger_row_condition_key(row: pd.Series) -> str:
    """Canonical condition key matching discovery cohort identifiers."""
    from modules.edge_research.discovery import canonical_condition_key
    from modules.edge_research.robustness import reconstruct_clauses_from_ledger_row

    transition = str(row.get("market_transition", ""))
    clauses = reconstruct_clauses_from_ledger_row(row)
    if not clauses:
        return f"{transition}|{row.get('condition_text', '')}"
    return f"{transition}|{canonical_condition_key(clauses)}"


def load_existing_condition_keys(data_dir: Optional[Path] = None) -> set[str]:
    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir=data_dir)
    if ledger.empty:
        return set()
    keys = set()
    for _, row in ledger.iterrows():
        keys.add(ledger_row_condition_key(row))
        keys.add(f"{row.get('market_transition', '')}|{row.get('condition_text', '')}")
    return keys


def append_candidates(
    candidates: Sequence[Any],
    data_dir: Optional[Path] = None,
    existing_keys: Optional[set[str]] = None,
    discovery_run_id: Optional[str] = None,
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
        guardrails = getattr(cand, "guardrails", {}) or {}
        row = {
            "edge_id": edge_id,
            "created_at": created,
            "discovery_run_id": discovery_run_id or "",
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
            "notes": json.dumps({"guardrails": guardrails}, ensure_ascii=False) if guardrails else "",
        }
        new_rows.append(row)

    if not new_rows:
        return 0
    ledger = pd.concat([ledger, pd.DataFrame(new_rows)], ignore_index=True)
    ledger = normalize_hypothesis_ledger_dtypes(ledger)
    ledger.to_csv(root / "edge_hypothesis_ledger.csv", index=False)
    return len(new_rows)


def read_top_candidates(data_dir: Optional[Path] = None, limit: int = 10) -> List[Dict[str, Any]]:
    ledger = resolve_discovery_cohort(data_dir=data_dir)
    if ledger.empty:
        return []
    df = ledger[ledger["status"] == "CANDIDATE"].copy()
    if df.empty:
        df = ledger.copy()
    if "incremental_median" in df.columns:
        df = df.sort_values("incremental_median", ascending=False, na_position="last")
    return df.head(limit).to_dict(orient="records")


def resolve_discovery_cohort(
    data_dir: Optional[Path] = None,
    discovery_run_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    Return hypothesis ledger rows for one discovery cohort.

    Prefers explicit discovery_run_id linkage. Falls back to the latest persisted
    discovery run's condition_key set without combining multiple runs.
    """
    root = resolve_data_dir(data_dir)
    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir=root)
    if ledger.empty:
        return ledger

    discovery = read_discovery_run(root)
    run_id = discovery_run_id or str(discovery.get("run_id", "") or "")
    if not run_id:
        return ledger

    explicit = ledger[ledger.get("discovery_run_id", pd.Series(dtype=str)).astype(str) == run_id]
    if not explicit.empty:
        return explicit.reset_index(drop=True)

    expected_keys = {
        str(c.get("condition_key", ""))
        for c in discovery.get("candidates", [])
        if c.get("condition_key")
    }
    if not expected_keys:
        # Latest run exists but no embedded keys — use most recent created_at batch.
        latest_ts = ledger["created_at"].dropna().astype(str).max()
        if latest_ts:
            return ledger[ledger["created_at"].astype(str) == latest_ts].reset_index(drop=True)
        return ledger

    ledger = ledger.copy()
    ledger["_condition_key"] = ledger.apply(ledger_row_condition_key, axis=1)
    matched = ledger[ledger["_condition_key"].isin(expected_keys)].copy()
    if matched.empty:
        return pd.DataFrame(columns=ledger.columns)

    # One row per condition_key — prefer latest created_at when duplicates exist.
    matched = matched.sort_values(["created_at", "edge_id"], ascending=[False, False])
    matched = matched.drop_duplicates(subset=["_condition_key"], keep="first")
    return matched.drop(columns=["_condition_key"]).reset_index(drop=True)


def cohort_ledger_hash(cohort: pd.DataFrame) -> str:
    from modules.edge_research.challenger import _ledger_hash

    return _ledger_hash(cohort)


def supersede_challenger_runs(
    superseded_by: str,
    *,
    reason: str,
    data_dir: Optional[Path] = None,
    exclude_run_id: Optional[str] = None,
) -> None:
    root = resolve_data_dir(data_dir)
    path = root / "challenger_runs.csv"
    if not path.exists():
        return
    ledger = read_ledger("challenger_runs.csv", data_dir=root)
    if ledger.empty:
        return
    active = ledger.get("report_status", pd.Series(dtype=str)).fillna("ACTIVE") == "ACTIVE"
    mask = active
    if exclude_run_id:
        mask &= ledger["run_id"].astype(str) != str(exclude_run_id)
    if not mask.any():
        return
    for col in ("report_status", "superseded_by", "superseded_reason"):
        if col in ledger.columns:
            ledger[col] = ledger[col].astype(object)
    ledger.loc[mask, "report_status"] = "SUPERSEDED"
    ledger.loc[mask, "superseded_by"] = superseded_by
    ledger.loc[mask, "superseded_reason"] = reason
    ledger.to_csv(path, index=False)


def write_challenger_run(payload: Dict[str, Any], data_dir: Optional[Path] = None) -> Path:
    root = ensure_storage(data_dir)
    path = root / CHALLENGER_RUN_FILE
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    row = {
        "run_id": payload.get("run_id"),
        "timestamp": payload.get("timestamp"),
        "robustness_config_version": payload.get("robustness_config_version"),
        "episode_config_version": payload.get("episode_config_version"),
        "discovery_run_id": payload.get("discovery_run_id"),
        "candidate_ledger_hash": payload.get("candidate_ledger_hash"),
        "ledger_hash": payload.get("ledger_hash"),
        "report_status": payload.get("report_status", "ACTIVE"),
        "superseded_by": payload.get("superseded_by", ""),
        "superseded_reason": payload.get("superseded_reason", ""),
        "dataset_start": payload.get("dataset_start"),
        "dataset_end": payload.get("dataset_end"),
        "candidates_entering": payload.get("candidates_entering", payload.get("candidates_entered")),
        "candidates_entered": payload.get("candidates_entered"),
        "robustness_pass": payload.get("robustness_pass"),
        "robustness_fragile": payload.get("robustness_fragile"),
        "robustness_reject": payload.get("robustness_reject"),
        "episodes_segmented": payload.get("episodes_segmented"),
        "episodes_unknown": payload.get("episodes_unknown", 0),
    }
    ledger = read_ledger("challenger_runs.csv", data_dir=root)
    ledger = pd.concat([ledger, pd.DataFrame([row])], ignore_index=True)
    ledger = normalize_challenger_run_dtypes(ledger)
    ledger.to_csv(root / "challenger_runs.csv", index=False)
    return path


def read_challenger_run(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = resolve_data_dir(data_dir)
    path = root / CHALLENGER_RUN_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def append_robustness_history(
    run_id: str,
    edge_id: str,
    timestamp: str,
    test_records: List[Dict[str, Any]],
    data_dir: Optional[Path] = None,
) -> None:
    root = ensure_storage(data_dir)
    ledger = read_ledger("edge_robustness_history.csv", data_dir=root)
    rows = []
    for rec in test_records:
        rows.append(
            {
                "run_id": run_id,
                "edge_id": edge_id,
                "timestamp": timestamp,
                "test_name": rec.get("test_name", ""),
                "test_version": rec.get("test_version", "robustness_v1"),
                "pre_n": rec.get("pre_n", ""),
                "post_n": rec.get("post_n", ""),
                "pre_incremental_median": rec.get("pre_incremental_median", ""),
                "post_incremental_median": rec.get("post_incremental_median", ""),
                "pre_incremental_mean": rec.get("pre_incremental_mean", ""),
                "post_incremental_mean": rec.get("post_incremental_mean", ""),
                "pre_incremental_wr": rec.get("pre_incremental_wr", ""),
                "post_incremental_wr": rec.get("post_incremental_wr", ""),
                "result": rec.get("result", ""),
                "reason": rec.get("reason", ""),
            }
        )
    if rows:
        new_rows = normalize_robustness_history_dtypes(pd.DataFrame(rows))
        ledger = pd.concat([ledger, new_rows], ignore_index=True)
        ledger = normalize_robustness_history_dtypes(ledger)
        ledger.to_csv(root / "edge_robustness_history.csv", index=False)


def update_ledger_robustness(
    results: List[Any],
    run_id: str,
    data_dir: Optional[Path] = None,
) -> None:
    root = ensure_storage(data_dir)
    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir=root)
    if ledger.empty:
        return
    ledger = normalize_hypothesis_ledger_dtypes(ledger)
    for res in results:
        eid = res.edge_id
        mask = ledger["edge_id"] == eid
        if not mask.any():
            continue
        ledger.loc[mask, "robustness_status"] = res.robustness_status
        ledger.loc[mask, "robustness_run_id"] = run_id
        ledger.loc[mask, "observed_episodes"] = res.observed_episodes
        ledger.loc[mask, "positive_episodes"] = res.positive_episodes
        ledger.loc[mask, "negative_episodes"] = res.negative_episodes
        ledger.loc[mask, "mixed_episodes"] = res.mixed_episodes
        ledger.loc[mask, "date_count"] = res.date_count
        ledger.loc[mask, "unique_symbol_count"] = res.unique_symbol_count
        ledger.loc[mask, "fragility_flags"] = "|".join(res.fragility_flags)
        ledger.loc[mask, "rejection_reasons"] = "|".join(res.rejection_reasons)
        ledger.loc[mask, "main_fragility_flag"] = res.main_fragility_flag
    ledger.to_csv(root / "edge_hypothesis_ledger.csv", index=False)


def write_episode_registry(
    run_result: Any,
    panel: pd.DataFrame,
    data_dir: Optional[Path] = None,
) -> None:
    from modules.edge_research.episodes import segment_market_episodes

    root = ensure_storage(data_dir)
    episodes = segment_market_episodes(panel)
    rows = []
    for ep in episodes:
        rows.append(
            {
                "episode_id": ep.episode_id,
                "episode_version": ep.episode_version,
                "start_date": ep.start_date,
                "end_date": ep.end_date,
                "start_state": ep.start_state,
                "end_state": ep.end_state,
                "transition_sequence": ep.transition_sequence,
                "min_market_real": ep.min_market_real,
                "max_market_real": ep.max_market_real,
                "number_of_trading_dates": ep.number_of_trading_dates,
                "candidate_edge_id": "",
                "candidate_observations_in_episode": "",
                "candidate_best_horizon": "",
                "candidate_incremental_median": "",
                "candidate_incremental_mean": "",
                "candidate_incremental_wr": "",
                "episode_result": "",
            }
        )
    for res in run_result.results:
        for detail in res.episode_summary.get("episode_details", []):
            rows.append(
                {
                    "episode_id": detail.get("episode_id"),
                    "episode_version": "episode_v1",
                    "start_date": detail.get("start_date"),
                    "end_date": detail.get("end_date"),
                    "start_state": "",
                    "end_state": "",
                    "transition_sequence": "",
                    "min_market_real": "",
                    "max_market_real": "",
                    "number_of_trading_dates": "",
                    "candidate_edge_id": res.edge_id,
                    "candidate_observations_in_episode": detail.get("observations"),
                    "candidate_best_horizon": res.best_horizon,
                    "candidate_incremental_median": "",
                    "candidate_incremental_mean": "",
                    "candidate_incremental_wr": "",
                    "episode_result": detail.get("episode_result"),
                }
            )
    if rows:
        ledger = read_ledger("edge_episode_registry.csv", data_dir=root)
        new_rows = normalize_episode_registry_dtypes(pd.DataFrame(rows))
        ledger = pd.concat([ledger, new_rows], ignore_index=True)
        ledger = normalize_episode_registry_dtypes(ledger)
        ledger.to_csv(root / "edge_episode_registry.csv", index=False)


def get_challenger_ledger_hash(data_dir: Optional[Path] = None) -> str:
    cohort = resolve_discovery_cohort(data_dir=data_dir)
    return cohort_ledger_hash(cohort)


def research_session_path(session_id: str, data_dir: Optional[Path] = None) -> Path:
    root = ensure_storage(data_dir)
    safe_id = session_id.replace("/", "_").replace("\\", "_")
    return root / RESEARCH_SESSIONS_DIR / f"{safe_id}.json"


def write_research_graph(graph: Any, data_dir: Optional[Path] = None) -> Path:
    """
    Atomically persist a ResearchGraph snapshot to research_sessions/.

    Separate from edge_hypothesis_ledger.csv — research memory only.
    """
    from modules.edge_research.research_graph import ResearchGraph

    if not isinstance(graph, ResearchGraph):
        raise TypeError("graph must be a ResearchGraph instance")
    graph.validate()
    path = research_session_path(graph.session.research_session_id, data_dir=data_dir)
    tmp = path.with_suffix(".json.tmp")
    payload = graph.serialize()
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_research_graph(
    session_id: str,
    data_dir: Optional[Path] = None,
) -> Any:
    from modules.edge_research.research_graph import ResearchGraph

    path = research_session_path(session_id, data_dir=data_dir)
    if not path.exists():
        raise FileNotFoundError(f"Research session not found: {session_id}")
    return ResearchGraph.deserialize(path.read_text(encoding="utf-8"))


def list_research_session_ids(data_dir: Optional[Path] = None) -> List[str]:
    root = ensure_storage(data_dir)
    sessions_dir = root / RESEARCH_SESSIONS_DIR
    if not sessions_dir.exists():
        return []
    return sorted(p.stem for p in sessions_dir.glob("*.json") if p.is_file())
