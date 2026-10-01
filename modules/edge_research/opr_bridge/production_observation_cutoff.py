"""
Phase 3K.0 — Observation cutoff and temporal provenance validation.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.production_observation_records import (
    DataAvailabilityStatus,
    ObservationCutoff,
    compute_observation_identity,
    new_observation_id,
)
from modules.edge_research.opr_bridge.production_trigger import compute_evidence_cutoff_hash
from modules.edge_research.research_tools import apply_research_cutoff

CUTOFF_VERSION = "production_observation_cutoff_v1_3k0"
DEFAULT_TIMEZONE = "UTC"


def compute_panel_hash(panel: pd.DataFrame) -> str:
    if panel.empty:
        return stable_hash({"empty": True})
    cols = sorted(str(c) for c in panel.columns)
    sample = panel.sort_values(["trade_date", "symbol"] if "symbol" in panel.columns else ["trade_date"])
    head = sample.head(100).to_dict(orient="records")
    tail = sample.tail(100).to_dict(orient="records")
    return stable_hash(
        {
            "row_count": len(panel),
            "columns": cols,
            "head": head,
            "tail": tail,
        }
    )


def compute_dataset_identities(panel: pd.DataFrame) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    identities = ["pattern_lifecycle", "market_t0_snapshot", "outcomes"]
    hashes = [compute_panel_hash(panel)]
    return tuple(identities), tuple(hashes)


def compute_universe_identity(panel: pd.DataFrame) -> Tuple[str, str]:
    if panel.empty or "symbol" not in panel.columns:
        identity = "EMPTY_UNIVERSE"
    else:
        symbols = sorted(panel["symbol"].astype(str).unique().tolist())
        identity = stable_hash({"symbols": symbols[:500], "count": len(symbols)})
    return identity, stable_hash({"universe_identity": identity})


def compute_market_context_identity(panel: pd.DataFrame, trade_date: str) -> Tuple[str, str]:
    if panel.empty:
        return "NO_CONTEXT", stable_hash({"empty": True})
    sub = panel[panel["trade_date"].astype(str) == str(trade_date)]
    if sub.empty:
        sub = panel.sort_values("trade_date").tail(1)
    ctx = {}
    for col in ("market_real", "market_forecast", "breadth_score", "research_market_state"):
        if col in sub.columns and not sub[col].isna().all():
            ctx[col] = str(sub[col].iloc[0])
    identity = stable_hash(ctx) if ctx else "UNKNOWN_CONTEXT"
    return identity, stable_hash({"market_context": ctx})


def get_code_identity(repo_root: Optional[Path] = None) -> str:
    root = repo_root or Path(__file__).resolve().parents[3]
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        return head
    except Exception:
        return "unknown"


def compute_policy_hash_bundle(policy_hashes: Dict[str, str]) -> str:
    return stable_hash({"policy_hashes": policy_hashes})


def truncate_panel_at_cutoff(
    panel: pd.DataFrame,
    data_cutoff_date: str,
    *,
    horizons: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Return cutoff-safe panel; fail-closed diagnostics included."""
    truncated, diag = apply_research_cutoff(
        panel,
        data_cutoff_date,
        horizons=horizons or ["T3", "T5", "T10"],
    )
    if panel.empty:
        diag["temporal_provenance_established"] = False
        diag["failure_reason"] = "empty_source_panel"
        return truncated, diag

    work = panel.copy()
    work["_trade_date_dt"] = pd.to_datetime(work["trade_date"], errors="coerce")
    cutoff = pd.Timestamp(data_cutoff_date)
    future_rows = int((work["_trade_date_dt"] > cutoff).sum())
    diag["future_t0_rows_in_source"] = future_rows
    diag["max_source_trade_date"] = str(work["_trade_date_dt"].max().date()) if work["_trade_date_dt"].notna().any() else None

    if truncated.empty:
        diag["temporal_provenance_established"] = False
        diag["failure_reason"] = "no_rows_at_or_before_cutoff"
        return truncated, diag

    trunc = truncated.copy()
    trunc["_trade_date_dt"] = pd.to_datetime(trunc["trade_date"], errors="coerce")
    max_visible = trunc["_trade_date_dt"].max()
    diag["max_researcher_visible_trade_date"] = str(max_visible.date()) if pd.notna(max_visible) else None
    diag["temporal_provenance_established"] = pd.notna(max_visible) and max_visible <= cutoff
    if not diag["temporal_provenance_established"]:
        diag["failure_reason"] = "max_visible_trade_date_exceeds_cutoff"
    return truncated, diag


def validate_temporal_provenance(
    panel: pd.DataFrame,
    data_cutoff_date: str,
    cutoff_diagnostics: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Fail closed if temporal provenance cannot be established."""
    errors: List[str] = []
    if not cutoff_diagnostics.get("temporal_provenance_established"):
        errors.append(cutoff_diagnostics.get("failure_reason") or "temporal_provenance_not_established")

    if panel.empty:
        errors.append("cutoff_panel_empty")
        return False, errors

    work = panel.copy()
    work["_trade_date_dt"] = pd.to_datetime(work["trade_date"], errors="coerce")
    cutoff = pd.Timestamp(data_cutoff_date)
    if (work["_trade_date_dt"] > cutoff).any():
        errors.append("future_trade_date_rows_present_in_research_panel")

    for h in ("T3", "T5", "T10"):
        target_col = {"T3": "t3_target_date", "T5": "t5_target_date", "T10": "t10_target_date"}.get(h, "")
        ret_col = {"T3": "t3_return_pct", "T5": "t5_return_pct", "T10": "t10_return_pct"}.get(h, "")
        if target_col in work.columns and ret_col in work.columns:
            tgt = pd.to_datetime(work[target_col], errors="coerce")
            leak = work[ret_col].notna() & (tgt > cutoff)
            if leak.any():
                errors.append(f"future_outcome_leak_{h}")

    return len(errors) == 0, errors


def build_observation_cutoff(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    policy_hashes: Dict[str, str],
    focal_dates: Optional[List[str]] = None,
    data_availability_status: str = DataAvailabilityStatus.EOD_FINAL.value,
    timezone: str = DEFAULT_TIMEZONE,
    repo_root: Optional[Path] = None,
    observation_mode: str = "PRODUCTION_SHADOW",
) -> Tuple[ObservationCutoff, Dict[str, Any]]:
    truncated, diag = truncate_panel_at_cutoff(panel, data_cutoff_date)
    ok, errors = validate_temporal_provenance(truncated, data_cutoff_date, diag)
    if not ok:
        raise ValueError(f"temporal_provenance_failed:{';'.join(errors)}")

    focal = focal_dates or sorted(truncated["trade_date"].astype(str).unique().tolist()) if not truncated.empty else []
    evidence_hash = compute_evidence_cutoff_hash(truncated, data_cutoff_date, focal)
    panel_hash = compute_panel_hash(truncated)
    policy_bundle = compute_policy_hash_bundle(policy_hashes)
    identity = compute_observation_identity(
        data_cutoff_date=data_cutoff_date,
        evidence_cutoff_hash=evidence_hash,
        policy_hash_bundle=policy_bundle,
        panel_hash=panel_hash,
        observation_mode=observation_mode,
    )
    observation_id = new_observation_id(identity)

    dataset_ids, dataset_hashes = compute_dataset_identities(truncated)
    universe_id, universe_hash = compute_universe_identity(truncated)
    trade_date = data_cutoff_date
    ctx_id, ctx_hash = compute_market_context_identity(truncated, trade_date)

    max_ts = diag.get("max_researcher_visible_trade_date") or data_cutoff_date
    temporal_hash = stable_hash(
        {
            "observation_id": observation_id,
            "data_cutoff_date": data_cutoff_date,
            "max_visible": max_ts,
            "evidence_cutoff_hash": evidence_hash,
        }
    )

    cutoff = ObservationCutoff(
        observation_id=observation_id,
        trade_date=trade_date,
        cutoff_timestamp=utc_now_iso(),
        timezone=timezone,
        data_availability_status=data_availability_status,
        market_data_max_timestamp=f"{max_ts}T23:59:59Z",
        dataset_identities=dataset_ids,
        dataset_hashes=dataset_hashes,
        universe_identity=universe_id,
        universe_hash=universe_hash,
        market_context_identity=ctx_id,
        market_context_hash=ctx_hash,
        research_policy_hashes=dict(policy_hashes),
        code_identity=get_code_identity(repo_root),
        panel_row_count=len(truncated),
        panel_max_trade_date=str(max_ts),
        temporal_provenance_hash=temporal_hash,
    )
    meta = {
        "identity_hash": identity,
        "evidence_cutoff_hash": evidence_hash,
        "panel_hash": panel_hash,
        "policy_hash_bundle": policy_bundle,
        "cutoff_diagnostics": diag,
    }
    return cutoff, meta
