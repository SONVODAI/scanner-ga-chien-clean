"""Atomic, idempotent fusion artifact persistence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from modules.actionable_research.contracts import FUSION_SCHEMA_VERSION, FUSION_VERSION
from modules.actionable_research.paths import FusionPaths, read_json, utc_now_iso


def _stable_dump(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def payload_identity_hash(payload: Dict[str, Any]) -> str:
    """Hash of scientific/presentation content excluding generated_at / write stamps."""
    clone = json.loads(_stable_dump(payload))
    clone.pop("generated_at", None)
    clone.pop("written_at", None)
    clone.pop("write_generation", None)
    if isinstance(clone.get("session"), dict):
        clone["session"].pop("generated_at", None)
        clone["session"].pop("written_at", None)
    records = clone.get("records")
    if isinstance(records, list):
        for rec in records:
            if isinstance(rec, dict):
                rec.pop("generated_at", None)
    observations = clone.get("observations")
    if isinstance(observations, list):
        for rec in observations:
            if isinstance(rec, dict):
                rec.pop("generated_at", None)
    return hashlib.sha256(_stable_dump(clone).encode("utf-8")).hexdigest()


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def observation_id(rec: Dict[str, Any]) -> str:
    identity = {
        "trade_date": rec.get("trade_date"),
        "symbol": rec.get("symbol"),
        "edge_status": rec.get("edge_status"),
        "matched_edge_ids": rec.get("matched_edge_ids"),
        "money_flow_status": rec.get("money_flow_status"),
        "money_flow_direction": rec.get("money_flow_direction"),
        "foreign_flow_status": rec.get("foreign_flow_status"),
        "observation_relation": rec.get("observation_relation"),
        "camera_cutoff_timestamp": rec.get("camera_cutoff_timestamp"),
    }
    return hashlib.sha256(_stable_dump(identity).encode("utf-8")).hexdigest()[:16]


def persist_observation_ledger(
    payload: Dict[str, Any],
    *,
    paths: FusionPaths,
    replay: bool = False,
) -> None:
    """
    First-write-wins ledger of noteworthy observations only.

    Frozen T0 context is kept so later T3/T5/T10 outcomes can be joined.
    Does not birth LIVE_FORWARD scientific edges. Replay does not duplicate rows.
    """
    trade_date = str(payload.get("trade_date") or "")[:10]
    observations = list(payload.get("observations") or [])
    daily_obs = {
        "trade_date": trade_date,
        "speak_policy": payload.get("speak_policy"),
        "authority": payload.get("authority"),
        "scan": payload.get("scan") or {},
        "observations": observations,
        "outcome_horizon_slots": ["T3", "T5", "T10"],
        "outcome_status": "PENDING",
    }
    atomic_write_json(paths.daily_observations_path(trade_date), daily_obs)

    ledger_path = paths.observation_ledger_path()
    existing_ids = set()
    if ledger_path.exists() and ledger_path.stat().st_size > 0:
        with ledger_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    oid = str(row.get("observation_id") or "")
                    if oid:
                        existing_ids.add(oid)

    if replay:
        return

    new_lines = []
    for rec in observations:
        if not isinstance(rec, dict):
            continue
        oid = observation_id(rec)
        if oid in existing_ids:
            continue
        row = {
            "observation_id": oid,
            "trade_date": rec.get("trade_date") or trade_date,
            "symbol": rec.get("symbol"),
            "authority": "RESEARCH ONLY",
            "observation_relation": rec.get("observation_relation"),
            "edge_status": rec.get("edge_status"),
            "matched_edge_ids": rec.get("matched_edge_ids"),
            "money_flow_status": rec.get("money_flow_status"),
            "money_flow_direction": rec.get("money_flow_direction"),
            "foreign_flow_status": rec.get("foreign_flow_status"),
            "market_state": rec.get("market_state"),
            "market_transition": rec.get("market_transition"),
            "stock_state": rec.get("stock_state"),
            "camera_cutoff_timestamp": rec.get("camera_cutoff_timestamp"),
            "evidence_summary": rec.get("evidence_summary"),
            "reasons": rec.get("reasons"),
            "outcome_status": "PENDING",
            "t3_return_pct": None,
            "t5_return_pct": None,
            "t10_return_pct": None,
            "generated_at": rec.get("generated_at") or payload.get("generated_at"),
        }
        new_lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))
        existing_ids.add(oid)

    if not new_lines:
        return
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        for line in new_lines:
            fh.write(line + "\n")


def persist_fusion_artifact(
    payload: Dict[str, Any],
    *,
    paths: FusionPaths,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Write daily + latest + history. Same-date replay with the same identity
    overwrites in place (no duplicate records / no extra index rows).
    """
    trade_date = str(payload.get("trade_date") or "")[:10]
    if not trade_date:
        raise ValueError("fusion payload missing trade_date")

    generated_at = utc_now_iso(now)
    identity = payload_identity_hash(payload)
    session_status = str(payload.get("session_status") or "")
    cutoff = str(payload.get("camera_cutoff_timestamp") or payload.get("cutoff_timestamp") or "")

    existing = read_json(paths.daily_path(trade_date))
    replay = False
    if existing and str(existing.get("content_hash") or "") == identity:
        replay = True
        generated_at = str(existing.get("generated_at") or generated_at)
        write_generation = int(existing.get("write_generation") or 1)
    else:
        write_generation = int((existing or {}).get("write_generation") or 0) + 1

    out = dict(payload)
    out["generated_at"] = generated_at
    out["written_at"] = utc_now_iso(now)
    out["content_hash"] = identity
    out["write_generation"] = write_generation
    out["idempotent_replay"] = replay
    out["fusion_version"] = FUSION_VERSION
    out["schema_version"] = FUSION_SCHEMA_VERSION
    for rec in list(out.get("records") or []) + list(out.get("observations") or []):
        if isinstance(rec, dict):
            rec["generated_at"] = generated_at

    persist_observation_ledger(out, paths=paths, replay=replay)

    daily_path = paths.daily_path(trade_date)
    atomic_write_json(daily_path, out)

    history_name = f"{trade_date}__{cutoff.replace(':', '').replace('+', '_') or 'nocutoff'}.json"
    atomic_write_json(paths.history_dir() / history_name, out)

    latest = {
        "trade_date": trade_date,
        "session_status": session_status,
        "daily_path": str(daily_path),
        "content_hash": identity,
        "generated_at": generated_at,
        "camera_cutoff_timestamp": cutoff,
        "authority": out.get("authority") or "RESEARCH ONLY",
        "notable_count": out.get("notable_count"),
        "scanned_count": (out.get("scan") or {}).get("scanned_count"),
        "speak_policy": out.get("speak_policy"),
        "fusion_version": FUSION_VERSION,
        "idempotent_replay": replay,
        "artifact": out,
    }
    atomic_write_json(paths.latest_path(), latest)

    index = read_json(paths.index_path()) or {"runs": {}}
    runs = index.setdefault("runs", {})
    # One canonical row per trade_date (not per replay).
    runs[trade_date] = {
        "trade_date": trade_date,
        "session_status": session_status,
        "content_hash": identity,
        "generated_at": generated_at,
        "write_generation": write_generation,
        "idempotent_replay": replay,
        "daily_path": str(daily_path),
        "camera_cutoff_timestamp": cutoff,
        "record_count": len(out.get("observations") or out.get("records") or []),
        "scanned_count": (out.get("scan") or {}).get("scanned_count"),
        "notable_count": out.get("notable_count"),
    }
    index["updated_at"] = generated_at
    atomic_write_json(paths.index_path(), index)
    return out
