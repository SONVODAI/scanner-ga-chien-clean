"""
Phase 3K.5A — Filesystem backup for irreplaceable LIVE_FORWARD scientific records.

Append-safe snapshot backup with integrity manifest. Scheduled activation NOT enabled.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.storage import resolve_data_dir

BACKUP_VERSION = "production_backup_v1_3k5a"
DEFAULT_RETENTION_COUNT = 7
BACKUP_SUBDIR = "live_forward_backups"

PROTECTED_RELATIVE_PATHS = (
    "live_forward_genesis.json",
    "observation_births",
    "daily_assessments",
    "forward_outcomes",
    "daily_runs",
    "daily_manifests",
    "forward_evidence_ledger",
    "calibration_snapshots",
    "daily_summaries",
)


@dataclass(frozen=True)
class BackupResult:
    success: bool
    backup_id: str
    backup_path: str
    file_count: int
    manifest_path: str
    errors: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "backup_id": self.backup_id,
            "backup_path": self.backup_path,
            "file_count": self.file_count,
            "manifest_path": self.manifest_path,
            "errors": list(self.errors),
            "version": BACKUP_VERSION,
        }


def production_observations_root(data_dir: Optional[Path] = None) -> Path:
    return resolve_data_dir(data_dir) / "production_observations"


def backup_root(data_dir: Optional[Path] = None) -> Path:
    root = production_observations_root(data_dir) / BACKUP_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_protected_files(obs_root: Path) -> List[Path]:
    files: List[Path] = []
    for rel in PROTECTED_RELATIVE_PATHS:
        target = obs_root / rel
        if not target.exists():
            continue
        if target.is_file():
            files.append(target)
        else:
            for p in sorted(target.rglob("*")):
                if p.is_file():
                    files.append(p)
    return files


def create_live_forward_backup(
    *,
    data_dir: Optional[Path] = None,
    backup_id: Optional[str] = None,
) -> BackupResult:
    """Snapshot-copy protected paths into timestamped backup directory."""
    obs_root = production_observations_root(data_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bid = backup_id or f"lfwd-bak-{ts}"
    dest = backup_root(data_dir) / bid
    errors: List[str] = []

    if dest.exists():
        return BackupResult(False, bid, str(dest), 0, "", ("backup_id_already_exists",))

    try:
        dest.mkdir(parents=True, exist_ok=False)
        manifest_entries: List[Dict[str, Any]] = []
        file_count = 0

        for src in _collect_protected_files(obs_root):
            rel = src.relative_to(obs_root)
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            file_count += 1
            manifest_entries.append({
                "relative_path": str(rel),
                "sha256": _sha256_file(out),
                "size_bytes": out.stat().st_size,
            })

        manifest = {
            "backup_id": bid,
            "created_at": utc_now_iso(),
            "version": BACKUP_VERSION,
            "source_root": str(obs_root),
            "file_count": file_count,
            "protected_paths": list(PROTECTED_RELATIVE_PATHS),
            "entries": manifest_entries,
            "manifest_hash": stable_hash({"entries": manifest_entries, "backup_id": bid}),
        }
        manifest_path = dest / "backup_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        latest_ptr = backup_root(data_dir) / "latest_backup.json"
        latest_ptr.write_text(json.dumps({"backup_id": bid, "path": str(dest), "created_at": manifest["created_at"]}, indent=2), encoding="utf-8")

        _enforce_retention(data_dir=data_dir)

        return BackupResult(True, bid, str(dest), file_count, str(manifest_path), ())
    except Exception as exc:
        errors.append(str(exc))
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return BackupResult(False, bid, str(dest), 0, "", tuple(errors))


def _enforce_retention(*, data_dir: Optional[Path] = None, keep: int = DEFAULT_RETENTION_COUNT) -> None:
    root = backup_root(data_dir)
    backups = sorted(
        [p for p in root.iterdir() if p.is_dir() and p.name.startswith("lfwd-bak-")],
        key=lambda p: p.name,
        reverse=True,
    )
    for old in backups[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def verify_backup_integrity(backup_path: Path) -> Tuple[bool, str, Dict[str, Any]]:
    """Restore verification — rejects corrupted backups."""
    manifest_path = backup_path / "backup_manifest.json"
    if not manifest_path.exists():
        return False, "manifest_missing", {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, "manifest_invalid_json", {}

    errors: List[str] = []
    for entry in manifest.get("entries", []):
        rel = entry.get("relative_path")
        expected = entry.get("sha256")
        fp = backup_path / rel
        if not fp.exists():
            errors.append(f"missing:{rel}")
            continue
        actual = _sha256_file(fp)
        if actual != expected:
            errors.append(f"checksum_mismatch:{rel}")

    recomputed = stable_hash({"entries": manifest.get("entries", []), "backup_id": manifest.get("backup_id")})
    if manifest.get("manifest_hash") and recomputed != manifest.get("manifest_hash"):
        errors.append("manifest_hash_mismatch")

    if errors:
        return False, errors[0], {"errors": errors, "backup_id": manifest.get("backup_id")}
    return True, "ok", manifest


def load_latest_backup_metadata(*, data_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    ptr = backup_root(data_dir) / "latest_backup.json"
    if not ptr.exists():
        return None
    try:
        meta = json.loads(ptr.read_text(encoding="utf-8"))
        bp = Path(meta.get("path", ""))
        ok, reason, manifest = verify_backup_integrity(bp)
        meta["integrity_ok"] = ok
        meta["integrity_reason"] = reason
        meta["file_count"] = manifest.get("file_count", 0)
        return meta
    except Exception:
        return {"integrity_ok": False, "integrity_reason": "latest_pointer_invalid"}
