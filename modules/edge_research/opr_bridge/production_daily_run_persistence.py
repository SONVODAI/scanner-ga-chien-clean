"""
Phase 3K.2 — Production daily run persistence (immutable after finalization).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.production_daily_run_records import (
    DAILY_RUN_VERSION,
    DailyManifest,
    ProductionDailyResearchRun,
    RunPhase,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    DEFAULT_SHADOW_AUTHORITY,
    ShadowAuthoritySemantics,
)
from modules.edge_research.storage import resolve_data_dir

RUN_PERSISTENCE_VERSION = "production_daily_run_persistence_v1_3k2"
RUNS_DIR = "daily_runs"
MANIFESTS_DIR = "daily_manifests"
PHASE_MARKERS_DIR = "run_phase_markers"
RUN_INDEX = "daily_run_index.json"
RUN_LEDGER = "daily_run_ledger.jsonl"
MANIFEST_LEDGER = "daily_manifest_ledger.jsonl"


def runs_root(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir) / "production_observations"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _subdir(name: str, data_dir: Optional[Path] = None) -> Path:
    path = runs_root(data_dir) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def run_path(run_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = run_id.replace("/", "_")
    return _subdir(RUNS_DIR, data_dir) / f"{safe}.json"


def manifest_path(run_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = run_id.replace("/", "_")
    return _subdir(MANIFESTS_DIR, data_dir) / f"{safe}.json"


def phase_marker_path(run_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = run_id.replace("/", "_")
    return _subdir(PHASE_MARKERS_DIR, data_dir) / f"{safe}.json"


def run_index_path(data_dir: Optional[Path] = None) -> Path:
    return runs_root(data_dir) / RUN_INDEX


def load_run_index(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = run_index_path(data_dir)
    if not path.exists():
        return {"version": RUN_PERSISTENCE_VERSION, "runs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_run_index(index: Dict[str, Any], data_dir: Optional[Path] = None) -> None:
    index["version"] = RUN_PERSISTENCE_VERSION
    _atomic_write(run_index_path(data_dir), json.dumps(index, indent=2, default=str))


def run_exists(run_id: str, data_dir: Optional[Path] = None) -> bool:
    return run_path(run_id, data_dir).exists()


def lookup_run(run_id: str, data_dir: Optional[Path] = None) -> Optional[ProductionDailyResearchRun]:
    path = run_path(run_id, data_dir)
    if not path.exists():
        return None
    return _run_from_dict(json.loads(path.read_text(encoding="utf-8")))


def lookup_run_for_date(
    target_trade_date: str,
    run_mode: str,
    *,
    data_dir: Optional[Path] = None,
) -> Optional[ProductionDailyResearchRun]:
    index = load_run_index(data_dir)
    for meta in index.get("runs", {}).values():
        if meta.get("target_trade_date") == target_trade_date and meta.get("run_mode") == run_mode:
            if meta.get("run_disposition") in ("SUCCESS", "SKIPPED_NON_TRADING_DAY", "WAITING_FOR_DATA"):
                return lookup_run(meta["run_id"], data_dir)
    return None


def lookup_prior_successful_run(
    target_trade_date: str,
    *,
    data_dir: Optional[Path] = None,
) -> Optional[str]:
    index = load_run_index(data_dir)
    candidates = [
        m for m in index.get("runs", {}).values()
        if m.get("run_disposition") == "SUCCESS" and m.get("target_trade_date", "") < target_trade_date
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.get("target_trade_date", ""))["run_id"]


def persist_run(
    run: ProductionDailyResearchRun,
    *,
    data_dir: Optional[Path] = None,
    allow_overwrite: bool = False,
) -> Path:
    if run_exists(run.run_id, data_dir) and not allow_overwrite:
        existing = lookup_run(run.run_id, data_dir)
        if existing and existing.frozen:
            return run_path(run.run_id, data_dir)
    path = run_path(run.run_id, data_dir)
    _atomic_write(path, json.dumps(run.to_dict(), indent=2, default=str))
    index = load_run_index(data_dir)
    index.setdefault("runs", {})[run.run_id] = {
        "run_id": run.run_id,
        "target_trade_date": run.target_trade_date,
        "run_mode": run.run_mode,
        "run_disposition": run.run_disposition,
        "run_identity_hash": run.run_identity_hash,
        "frozen": run.frozen,
        "counts_as_forward_evidence": run.counts_as_forward_evidence,
    }
    save_run_index(index, data_dir)
    if run.frozen:
        ledger = runs_root(data_dir) / RUN_LEDGER
        with ledger.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "run_id": run.run_id,
                "target_trade_date": run.target_trade_date,
                "run_disposition": run.run_disposition,
                "run_identity_hash": run.run_identity_hash,
            }, default=str) + "\n")
    return path


def persist_manifest(manifest: DailyManifest, *, data_dir: Optional[Path] = None) -> Path:
    path = manifest_path(manifest.run_id, data_dir)
    _atomic_write(path, json.dumps(manifest.to_dict(), indent=2, default=str))
    ledger = runs_root(data_dir) / MANIFEST_LEDGER
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"run_id": manifest.run_id, "trade_date": manifest.trade_date}, default=str) + "\n")
    return path


def persist_phase_marker(
    run_id: str,
    phase: str,
    *,
    data_dir: Optional[Path] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    path = phase_marker_path(run_id, data_dir)
    existing: Dict[str, Any] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing[phase] = {
        "phase": phase,
        "timestamp": utc_now_iso(),
        "extra": dict(extra or {}),
    }
    existing["latest_phase"] = phase
    _atomic_write(path, json.dumps(existing, indent=2, default=str))


def load_phase_marker(run_id: str, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = phase_marker_path(run_id, data_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def phase_completed(run_id: str, phase: str, *, data_dir: Optional[Path] = None) -> bool:
    markers = load_phase_marker(run_id, data_dir=data_dir)
    return phase in markers


def assert_run_immutable(
    run_id: str,
    *,
    attempted_mutation: Dict[str, Any],
    data_dir: Optional[Path] = None,
) -> bool:
    existing = lookup_run(run_id, data_dir)
    if existing is None or not existing.frozen:
        return True
    mutated = dict(existing.to_dict())
    mutated.update(attempted_mutation)
    new_hash = stable_hash({k: v for k, v in mutated.items() if k != "run_identity_hash"})
    return new_hash == existing.run_identity_hash


def reject_run_mode_conversion(
    run_id: str,
    proposed_mode: str,
    *,
    data_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    existing = lookup_run(run_id, data_dir)
    if existing is None:
        return True, "no_existing_run"
    if existing.frozen and existing.run_mode != proposed_mode:
        return False, f"mode_conversion_rejected:{existing.run_mode}->{proposed_mode}"
    return True, "ok"


def _shadow_from_dict(d: Optional[Dict[str, Any]]) -> ShadowAuthoritySemantics:
    d = d or {}
    return ShadowAuthoritySemantics(
        research_only=bool(d.get("research_only", True)),
        trading_authority=bool(d.get("trading_authority", False)),
        buy_signal=bool(d.get("buy_signal", False)),
        sell_signal=bool(d.get("sell_signal", False)),
        edge_active=bool(d.get("edge_active", False)),
    )


def _run_from_dict(payload: Dict[str, Any]) -> ProductionDailyResearchRun:
    return ProductionDailyResearchRun(
        run_id=payload["run_id"],
        target_trade_date=payload["target_trade_date"],
        run_mode=payload["run_mode"],
        run_started_at=payload["run_started_at"],
        run_completed_at=payload.get("run_completed_at"),
        cutoff=payload.get("cutoff"),
        source_dataset_identity=payload.get("source_dataset_identity", ""),
        source_dataset_hash=payload.get("source_dataset_hash", ""),
        source_max_trade_date=payload.get("source_max_trade_date"),
        researcher_visible_max_trade_date=payload.get("researcher_visible_max_trade_date"),
        market_context_identity=payload.get("market_context_identity"),
        market_context_hash=payload.get("market_context_hash"),
        prior_successful_run_id=payload.get("prior_successful_run_id"),
        policy_version_hashes=dict(payload.get("policy_version_hashes") or {}),
        observations_born=tuple(payload.get("observations_born") or []),
        observations_reassessed=tuple(payload.get("observations_reassessed") or []),
        forward_outcomes_released=tuple(payload.get("forward_outcomes_released") or []),
        daily_summary_id=payload.get("daily_summary_id"),
        run_disposition=payload.get("run_disposition", "FAILED_CLOSED"),
        failure_or_skip_reason=payload.get("failure_or_skip_reason"),
        counts_as_forward_evidence=bool(payload.get("counts_as_forward_evidence", False)),
        current_phase=payload.get("current_phase", RunPhase.STARTED.value),
        phase_history=tuple(payload.get("phase_history") or []),
        shadow_authority=_shadow_from_dict(payload.get("shadow_authority")),
        run_identity_hash=payload.get("run_identity_hash", ""),
        frozen=bool(payload.get("frozen", False)),
    )
