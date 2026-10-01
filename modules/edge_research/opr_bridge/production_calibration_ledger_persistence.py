"""
Phase 3K.3 — Forward evidence & calibration ledger persistence (append-only).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.production_calibration_records import (
    CalibrationSnapshot,
    ForwardCohortIdentity,
    ForwardEvidenceLedgerEntry,
    PreOutcomeStateSnapshot,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    DEFAULT_SHADOW_AUTHORITY,
    ShadowAuthoritySemantics,
)
from modules.edge_research.storage import resolve_data_dir

CALIBRATION_PERSISTENCE_VERSION = "calibration_persistence_v1_3k3"
LEDGER_DIR = "forward_evidence_ledger"
SNAPSHOTS_DIR = "calibration_snapshots"
CALIBRATION_INDEX = "calibration_ledger_index.json"
LEDGER_LEDGER = "forward_evidence_ledger.jsonl"
SNAPSHOT_LEDGER = "calibration_snapshot_ledger.jsonl"


def calibration_root(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir) / "production_observations"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _subdir(name: str, data_dir: Optional[Path] = None) -> Path:
    path = calibration_root(data_dir) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def ledger_entry_path(ledger_entry_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = ledger_entry_id.replace("/", "_")
    return _subdir(LEDGER_DIR, data_dir) / f"{safe}.json"


def snapshot_path(snapshot_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = snapshot_id.replace("/", "_")
    return _subdir(SNAPSHOTS_DIR, data_dir) / f"{safe}.json"


def load_calibration_index(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = calibration_root(data_dir) / CALIBRATION_INDEX
    if not path.exists():
        return {"version": CALIBRATION_PERSISTENCE_VERSION, "ledger_entries": {}, "snapshots": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_calibration_index(index: Dict[str, Any], data_dir: Optional[Path] = None) -> None:
    index["version"] = CALIBRATION_PERSISTENCE_VERSION
    _atomic_write(calibration_root(data_dir) / CALIBRATION_INDEX, json.dumps(index, indent=2, default=str))


def ledger_entry_exists(ledger_entry_id: str, data_dir: Optional[Path] = None) -> bool:
    return ledger_entry_path(ledger_entry_id, data_dir).exists()


def snapshot_exists(snapshot_id: str, data_dir: Optional[Path] = None) -> bool:
    return snapshot_path(snapshot_id, data_dir).exists()


def persist_ledger_entry(
    entry: ForwardEvidenceLedgerEntry,
    *,
    data_dir: Optional[Path] = None,
    allow_overwrite: bool = False,
) -> Path:
    if ledger_entry_exists(entry.ledger_entry_id, data_dir) and not allow_overwrite:
        return ledger_entry_path(entry.ledger_entry_id, data_dir)
    path = ledger_entry_path(entry.ledger_entry_id, data_dir)
    _atomic_write(path, json.dumps(entry.to_dict(), indent=2, default=str))
    ledger = calibration_root(data_dir) / LEDGER_LEDGER
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "ledger_entry_id": entry.ledger_entry_id,
            "observation_id": entry.observation_id,
            "horizon": entry.horizon,
            "identity_hash": entry.ledger_identity_hash,
        }, default=str) + "\n")
    index = load_calibration_index(data_dir)
    index.setdefault("ledger_entries", {})[entry.ledger_entry_id] = {
        "ledger_entry_id": entry.ledger_entry_id,
        "observation_id": entry.observation_id,
        "horizon": entry.horizon,
        "identity_hash": entry.ledger_identity_hash,
        "counts_as_forward_evidence": entry.counts_as_forward_evidence,
    }
    save_calibration_index(index, data_dir)
    return path


def persist_calibration_snapshot(
    snapshot: CalibrationSnapshot,
    *,
    data_dir: Optional[Path] = None,
    allow_overwrite: bool = False,
) -> Path:
    if snapshot_exists(snapshot.snapshot_id, data_dir) and not allow_overwrite:
        return snapshot_path(snapshot.snapshot_id, data_dir)
    path = snapshot_path(snapshot.snapshot_id, data_dir)
    _atomic_write(path, json.dumps(snapshot.to_dict(), indent=2, default=str))
    ledger = calibration_root(data_dir) / SNAPSHOT_LEDGER
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "snapshot_id": snapshot.snapshot_id,
            "as_of_trade_date": snapshot.as_of_trade_date,
            "provenance_hash": snapshot.provenance_hash,
        }, default=str) + "\n")
    index = load_calibration_index(data_dir)
    index.setdefault("snapshots", {})[snapshot.snapshot_id] = {
        "snapshot_id": snapshot.snapshot_id,
        "as_of_trade_date": snapshot.as_of_trade_date,
        "provenance_hash": snapshot.provenance_hash,
        "frozen": snapshot.frozen,
    }
    save_calibration_index(index, data_dir)
    return path


def lookup_ledger_entry(ledger_entry_id: str, data_dir: Optional[Path] = None) -> Optional[ForwardEvidenceLedgerEntry]:
    path = ledger_entry_path(ledger_entry_id, data_dir)
    if not path.exists():
        return None
    return _entry_from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_ledger_entries(*, data_dir: Optional[Path] = None, forward_only: bool = True) -> List[ForwardEvidenceLedgerEntry]:
    index = load_calibration_index(data_dir)
    rows = []
    for meta in index.get("ledger_entries", {}).values():
        if forward_only and not meta.get("counts_as_forward_evidence"):
            continue
        e = lookup_ledger_entry(meta["ledger_entry_id"], data_dir)
        if e:
            rows.append(e)
    return rows


def list_snapshots(*, data_dir: Optional[Path] = None) -> List[CalibrationSnapshot]:
    index = load_calibration_index(data_dir)
    rows = []
    for meta in index.get("snapshots", {}).values():
        path = snapshot_path(meta["snapshot_id"], data_dir)
        if path.exists():
            rows.append(_snapshot_from_dict(json.loads(path.read_text(encoding="utf-8"))))
    return sorted(rows, key=lambda s: s.as_of_trade_date)


def assert_snapshot_immutable(
    snapshot_id: str,
    *,
    attempted_mutation: Dict[str, Any],
    data_dir: Optional[Path] = None,
) -> bool:
    path = snapshot_path(snapshot_id, data_dir)
    if not path.exists():
        return True
    existing = json.loads(path.read_text(encoding="utf-8"))
    if not existing.get("frozen"):
        return True
    mutated = dict(existing)
    mutated.update(attempted_mutation)
    new_hash = stable_hash({k: v for k, v in mutated.items() if k != "provenance_hash"})
    old_hash = stable_hash({k: v for k, v in existing.items() if k != "provenance_hash"})
    return new_hash == old_hash


def _shadow_from_dict(d: Optional[Dict[str, Any]]) -> ShadowAuthoritySemantics:
    d = d or {}
    return ShadowAuthoritySemantics(
        research_only=bool(d.get("research_only", True)),
        trading_authority=bool(d.get("trading_authority", False)),
        buy_signal=bool(d.get("buy_signal", False)),
        sell_signal=bool(d.get("sell_signal", False)),
        edge_active=bool(d.get("edge_active", False)),
    )


def _pre_snapshot_from_dict(d: Dict[str, Any]) -> PreOutcomeStateSnapshot:
    return PreOutcomeStateSnapshot(
        snapshot_id=d["snapshot_id"],
        observation_id=d["observation_id"],
        horizon=d["horizon"],
        assessment_id=d.get("assessment_id"),
        assessment_trade_date=d["assessment_trade_date"],
        epistemic_state=d.get("epistemic_state"),
        evidence_strength=d.get("evidence_strength"),
        lifecycle_state=d.get("lifecycle_state"),
        surviving_nulls=tuple(d.get("surviving_nulls") or []),
        unresolved_uncertainties=tuple(d.get("unresolved_uncertainties") or []),
        market_context_hash=d.get("market_context_hash"),
        observation_age_trading_days=int(d.get("observation_age_trading_days", 0)),
        voice_assessment_id=d.get("voice_assessment_id"),
        snapshot_provenance_hash=d.get("snapshot_provenance_hash", ""),
    )


def _cohort_from_dict(d: Dict[str, Any]) -> ForwardCohortIdentity:
    return ForwardCohortIdentity(
        cohort_id=d["cohort_id"],
        birth_regime=d.get("birth_regime"),
        market_transition=d.get("market_transition"),
        hypothesis_family=d.get("hypothesis_family"),
        epistemic_state=d.get("epistemic_state"),
        evidence_strength_bucket=d.get("evidence_strength_bucket"),
        horizon=d["horizon"],
        observation_age_bucket=d.get("observation_age_bucket"),
        outcome_availability=d.get("outcome_availability", "RELEASED"),
        cohort_hash=d.get("cohort_hash", ""),
    )


def _entry_from_dict(payload: Dict[str, Any]) -> ForwardEvidenceLedgerEntry:
    return ForwardEvidenceLedgerEntry(
        ledger_entry_id=payload["ledger_entry_id"],
        observation_id=payload["observation_id"],
        horizon=payload["horizon"],
        birth_record_hash=payload["birth_record_hash"],
        outcome_record_id=payload["outcome_record_id"],
        run_id=payload["run_id"],
        run_mode=payload["run_mode"],
        pre_outcome_snapshot=_pre_snapshot_from_dict(payload["pre_outcome_snapshot"]),
        outcome_values=dict(payload.get("outcome_values") or {}),
        outcome_status=payload.get("outcome_status", "EVALUATED"),
        release_trade_date=payload["release_trade_date"],
        eligible_evaluation_date=payload["eligible_evaluation_date"],
        cohort_identity=_cohort_from_dict(payload["cohort_identity"]),
        provenance=dict(payload.get("provenance") or {}),
        counts_as_forward_evidence=bool(payload.get("counts_as_forward_evidence", False)),
        dependence_warning=payload.get("dependence_warning"),
        ledger_identity_hash=payload.get("ledger_identity_hash", ""),
        shadow_authority=_shadow_from_dict(payload.get("shadow_authority")),
    )


def _snapshot_from_dict(payload: Dict[str, Any]) -> CalibrationSnapshot:
    return CalibrationSnapshot(
        snapshot_id=payload["snapshot_id"],
        as_of_trade_date=payload["as_of_trade_date"],
        snapshot_timestamp=payload["snapshot_timestamp"],
        maturity_label=payload["maturity_label"],
        total_live_forward_observations=int(payload.get("total_live_forward_observations", 0)),
        eligible_n=int(payload.get("eligible_n", 0)),
        pending_n=int(payload.get("pending_n", 0)),
        missing_n=int(payload.get("missing_n", 0)),
        by_horizon=dict(payload.get("by_horizon") or {}),
        by_epistemic_state=dict(payload.get("by_epistemic_state") or {}),
        by_evidence_strength=dict(payload.get("by_evidence_strength") or {}),
        by_lifecycle_state=dict(payload.get("by_lifecycle_state") or {}),
        dependence_flags=tuple(payload.get("dependence_flags") or []),
        ledger_entry_ids=tuple(payload.get("ledger_entry_ids") or []),
        provenance_hash=payload.get("provenance_hash", ""),
        counts_as_forward_evidence=bool(payload.get("counts_as_forward_evidence", False)),
        frozen=bool(payload.get("frozen", True)),
    )
