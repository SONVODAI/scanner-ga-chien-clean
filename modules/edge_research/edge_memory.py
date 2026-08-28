"""
Durable ACTIVE edge memory (Phase A).

The ONLY route to status=ACTIVE is OOS_PASS. FRAGILE, REJECT, READY_FOR_OOS,
OOS_PENDING, OOS_FAIL, and OOS_INCONCLUSIVE never write ACTIVE rows.

Phase B Future Matcher is not implemented here. Forward counters are initialized
to zero and must not be faked.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.contracts import (
    EDGE_MEMORY_STATUS_ACTIVE,
    EDGE_MEMORY_STATUS_DECAYING,
    EDGE_MEMORY_STATUS_INVALIDATED,
    FROZEN_SPECS_DIRNAME,
    OOS_STATUS_PASS,
)
from modules.edge_research.hypothesis import FrozenHypothesisSpec
from modules.edge_research.oos_eval import OOSEvaluation
from modules.edge_research.storage import ensure_storage, read_ledger, resolve_data_dir


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def count_active_edges(data_dir: Optional[Path] = None) -> int:
    memory = read_ledger("edge_memory.csv", data_dir=data_dir)
    if memory.empty or "status" not in memory.columns:
        return 0
    status = memory["status"].astype(str).str.upper()
    return int((status == EDGE_MEMORY_STATUS_ACTIVE).sum())


def load_active_memory(data_dir: Optional[Path] = None) -> pd.DataFrame:
    memory = read_ledger("edge_memory.csv", data_dir=data_dir)
    if memory.empty or "status" not in memory.columns:
        return memory
    return memory[memory["status"].astype(str).str.upper() == EDGE_MEMORY_STATUS_ACTIVE].copy()


def _active_row(spec: FrozenHypothesisSpec, evaluation: OOSEvaluation, activated_at: str) -> Dict[str, Any]:
    return {
        "edge_id": spec.edge_id,
        "hypothesis_id": spec.hypothesis_id,
        "status": EDGE_MEMORY_STATUS_ACTIVE,
        "confirmed_at": activated_at,
        "decayed_at": "",
        "notes": "ACTIVE via OOS_PASS only; not a buy signal; Future Matcher not implemented in Phase A",
        "spec_path": f"{FROZEN_SPECS_DIRNAME}/{spec.hypothesis_id}.json",
        "spec_hash": spec.spec_hash,
        "market_state": spec.market_state,
        "market_transition": spec.market_transition,
        "baseline_type": spec.baseline_type,
        "feature_clauses_json": json.dumps(list(spec.feature_clauses), ensure_ascii=False),
        "condition_key": spec.condition_key,
        "condition_text": spec.condition_text,
        "best_horizon": spec.best_horizon,
        "feature_bucket_config_version": spec.feature_bucket_config_version,
        "market_state_config_version": spec.market_state_config_version,
        "activated_at": activated_at,
        "oos_result": evaluation.result,
        "oos_candidate_n": evaluation.candidate_n,
        "oos_baseline_n": evaluation.baseline_n,
        "oos_incremental_median": evaluation.incremental_median,
        "oos_incremental_mean": evaluation.incremental_mean,
        "oos_incremental_win_rate": evaluation.incremental_win_rate,
        "oos_evaluated_at": evaluation.evaluated_at,
        "episode_count": evaluation.market_episode_count,
        "concentration_notes": evaluation.concentration_json,
        "forward_matches": 0,
        "forward_matured": 0,
        "forward_hits": 0,
    }


def promote_oos_pass_to_memory(
    spec: FrozenHypothesisSpec,
    evaluation: OOSEvaluation,
    *,
    data_dir: Optional[Path] = None,
    activated_at: Optional[str] = None,
) -> bool:
    """
    Promote exactly one ACTIVE row for an OOS_PASS frozen hypothesis.

    Returns True if a row was written (or already existed identically).
    Returns False if evaluation is not OOS_PASS (no write).
    """
    if evaluation.result != OOS_STATUS_PASS:
        return False
    if evaluation.spec_hash and spec.spec_hash and evaluation.spec_hash != spec.spec_hash:
        raise ValueError("OOS evaluation spec_hash does not match frozen spec; refusing promotion")

    root = ensure_storage(data_dir)
    memory = read_ledger("edge_memory.csv", data_dir=root)
    ts = activated_at or evaluation.evaluated_at or _iso_now()

    if not memory.empty and "hypothesis_id" in memory.columns:
        existing = memory[memory["hypothesis_id"].astype(str) == spec.hypothesis_id]
        if not existing.empty:
            statuses = existing["status"].astype(str).str.upper()
            if (statuses == EDGE_MEMORY_STATUS_INVALIDATED).any():
                # INVALIDATED identity remains dead. No OOS/historical resurrection.
                return False
            if (statuses == EDGE_MEMORY_STATUS_DECAYING).any():
                # Recovery is forward-evidence only, never historical OOS rewrite.
                return True
            if (statuses == EDGE_MEMORY_STATUS_ACTIVE).any():
                return True

    row = _active_row(spec, evaluation, ts)
    memory = pd.concat([memory, pd.DataFrame([row])], ignore_index=True)
    memory.to_csv(root / "edge_memory.csv", index=False)
    return True


def promote_evaluations(
    evaluations: List[OOSEvaluation],
    specs_by_id: Dict[str, FrozenHypothesisSpec],
    *,
    data_dir: Optional[Path] = None,
) -> int:
    """Promote all OOS_PASS evaluations. Non-PASS never write ACTIVE rows."""
    written = 0
    for ev in evaluations:
        spec = specs_by_id.get(ev.hypothesis_id)
        if spec is None:
            continue
        if promote_oos_pass_to_memory(spec, ev, data_dir=data_dir):
            if ev.result == OOS_STATUS_PASS:
                written += 1
    return written


def load_memory_by_status(status: str, data_dir: Optional[Path] = None) -> pd.DataFrame:
    memory = read_ledger("edge_memory.csv", data_dir=data_dir)
    if memory.empty or "status" not in memory.columns:
        return memory
    return memory[memory["status"].astype(str).str.upper() == str(status).upper()].copy()


def apply_memory_health_update(
    hypothesis_id: str,
    *,
    decision: Dict[str, Any],
    evidence: Dict[str, Any],
    policy: Any,
    evaluated_at: str,
    data_dir: Optional[Path] = None,
) -> None:
    """Update current reusable state / summarized forward evidence. Never rewrite OOS/spec identity."""
    root = ensure_storage(data_dir)
    memory = read_ledger("edge_memory.csv", data_dir=root)
    if memory.empty or "hypothesis_id" not in memory.columns:
        return
    mask = memory["hypothesis_id"].astype(str) == str(hypothesis_id)
    if not mask.any():
        return
    idx = memory.index[mask][0]
    prev = str(memory.at[idx, "status"] or "")
    new_status = str(decision.get("status") or prev)
    frozen_identity = (
        "edge_id",
        "hypothesis_id",
        "spec_path",
        "spec_hash",
        "market_state",
        "market_transition",
        "baseline_type",
        "feature_clauses_json",
        "condition_key",
        "condition_text",
        "best_horizon",
        "feature_bucket_config_version",
        "market_state_config_version",
        "oos_result",
        "oos_candidate_n",
        "oos_baseline_n",
        "oos_incremental_median",
        "oos_incremental_mean",
        "oos_incremental_win_rate",
        "oos_evaluated_at",
        "confirmed_at",
        "activated_at",
    )
    _ = frozen_identity  # documented; we simply never assign those keys below
    memory.at[idx, "status"] = new_status
    memory.at[idx, "health_status"] = decision.get("health_status") or ""
    memory.at[idx, "health_reason"] = decision.get("reason") or ""
    memory.at[idx, "health_policy_version"] = getattr(policy, "policy_id", "")
    memory.at[idx, "last_health_evaluated_at"] = evaluated_at
    memory.at[idx, "forward_matured"] = evidence.get("mature_best_horizon") or 0
    memory.at[idx, "forward_hits"] = evidence.get("comparable_n") or 0
    memory.at[idx, "forward_incremental_median"] = evidence.get("forward_incremental_median")
    memory.at[idx, "forward_incremental_mean"] = evidence.get("forward_incremental_mean")
    memory.at[idx, "forward_unique_sessions"] = evidence.get("unique_sessions")
    memory.at[idx, "forward_unique_episodes"] = evidence.get("unique_episodes")
    memory.at[idx, "forward_evidence_json"] = json.dumps(evidence, default=str)
    if new_status != prev:
        memory.at[idx, "last_state_change_at"] = evaluated_at
        memory.at[idx, "last_state_change_from"] = prev
        memory.at[idx, "last_state_change_to"] = new_status
        if new_status == EDGE_MEMORY_STATUS_DECAYING:
            memory.at[idx, "decayed_at"] = evaluated_at
        if new_status == EDGE_MEMORY_STATUS_ACTIVE and prev == EDGE_MEMORY_STATUS_DECAYING:
            memory.at[idx, "decayed_at"] = ""
    memory.to_csv(root / "edge_memory.csv", index=False)
