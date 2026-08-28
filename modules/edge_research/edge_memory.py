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
            active = existing[existing["status"].astype(str).str.upper() == EDGE_MEMORY_STATUS_ACTIVE]
            if not active.empty:
                # Idempotent: already ACTIVE for this hypothesis.
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
