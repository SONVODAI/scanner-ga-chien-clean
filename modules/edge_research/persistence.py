"""
Edge Research durable persistence orchestration (P1 + P2).

Save/restore contracts between working storage and durable backend.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from modules.edge_research.bundle import (
    BundleValidationError,
    compare_state_fingerprints,
    fingerprint_working_state,
    is_publishable_state,
    restore_bundle_to_working_dir,
    validate_bundle_dir,
)
from modules.edge_research.durable import (
    DurableBackend,
    DurableBackendNotConfigured,
    DisabledDurableBackend,
    resolve_durable_backend,
    stage_bundle_from_working_dir,
)
from modules.edge_research.storage import (
    ensure_storage,
    read_challenger_run,
    read_discovery_run,
    resolve_data_dir,
    resolve_discovery_cohort,
)

PERSISTENCE_STATUS_FILE = "durable_persistence_status.json"


@dataclass
class PersistenceStatus:
    last_operation: str = "none"
    last_result: str = "none"
    message: str = ""
    backend: str = "none"
    discovery_run_id: str = ""
    challenger_run_id: str = ""
    cohort_size: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "last_operation": self.last_operation,
            "last_result": self.last_result,
            "message": self.message,
            "backend": self.backend,
            "discovery_run_id": self.discovery_run_id,
            "challenger_run_id": self.challenger_run_id,
            "cohort_size": self.cohort_size,
            "details": self.details,
        }


def _status_path(data_dir: Path) -> Path:
    return data_dir / PERSISTENCE_STATUS_FILE


def read_persistence_status(data_dir: Optional[Path] = None) -> PersistenceStatus:
    root = resolve_data_dir(data_dir)
    path = _status_path(root)
    if not path.exists():
        return PersistenceStatus()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PersistenceStatus(
            last_operation=str(raw.get("last_operation", "none")),
            last_result=str(raw.get("last_result", "none")),
            message=str(raw.get("message", "")),
            backend=str(raw.get("backend", "none")),
            discovery_run_id=str(raw.get("discovery_run_id", "")),
            challenger_run_id=str(raw.get("challenger_run_id", "")),
            cohort_size=int(raw.get("cohort_size", 0) or 0),
            details=dict(raw.get("details", {}) or {}),
        )
    except Exception:
        return PersistenceStatus(last_result="error", message="status file unreadable")


def write_persistence_status(status: PersistenceStatus, data_dir: Optional[Path] = None) -> None:
    root = resolve_data_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    _status_path(root).write_text(
        json.dumps(status.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _get_backend() -> DurableBackend:
    try:
        return resolve_durable_backend()
    except DurableBackendNotConfigured:
        return DisabledDurableBackend()


def try_restore_durable(data_dir: Optional[Path] = None) -> PersistenceStatus:
    """
    Restore contract:
    1. Ensure working storage exists.
    2. Load durable bundle if configured.
    3. Apply conflict policy — never overwrite newer valid local state.
    4. Restore canonical artifacts when durable wins.
    """
    root = ensure_storage(data_dir)
    backend = _get_backend()
    if not backend.is_configured():
        st = PersistenceStatus(
            last_operation="restore",
            last_result="skipped",
            message="durable backend not configured",
            backend=backend.name,
        )
        write_persistence_status(st, root)
        return st

    local_fp = fingerprint_working_state(root)
    local_has_cohort = bool(local_fp.discovery_run_id) and local_fp.cohort_size > 0

    staging = root / ".durable_staging" / f"restore_{uuid4().hex[:8]}"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        load_result = backend.load_bundle(staging)
        if not load_result.ok:
            st = PersistenceStatus(
                last_operation="restore",
                last_result="skipped",
                message=load_result.message,
                backend=backend.name,
                cohort_size=local_fp.cohort_size,
                details={"local_has_cohort": local_has_cohort},
            )
            write_persistence_status(st, root)
            return st

        bundle_dir = load_result.bundle_dir or staging
        validation = validate_bundle_dir(bundle_dir)
        if not validation.ok:
            st = PersistenceStatus(
                last_operation="restore",
                last_result="rejected",
                message="; ".join(validation.errors),
                backend=backend.name,
            )
            write_persistence_status(st, root)
            return st

        manifest = validation.manifest or {}
        durable_fp = fingerprint_working_state(root)
        # Fingerprint durable from manifest without applying yet.
        durable_fp = type(local_fp)(
            discovery_run_id=str(manifest.get("discovery_run_id", "") or ""),
            discovery_timestamp=str(manifest.get("discovery_timestamp", "") or ""),
            challenger_run_id=str(manifest.get("challenger_run_id", "") or ""),
            challenger_timestamp=str(manifest.get("challenger_timestamp", "") or ""),
            cohort_size=int(manifest.get("cohort_size", 0) or 0),
            cohort_hash=str(manifest.get("cohort_hash", "") or ""),
            state_sequence=int(manifest.get("state_sequence", 0) or 0),
        )

        if local_has_cohort:
            winner = compare_state_fingerprints(local_fp, durable_fp)
            if winner in ("local", "equal"):
                st = PersistenceStatus(
                    last_operation="restore",
                    last_result="skipped",
                    message=f"keeping newer/equal local state ({winner})",
                    backend=backend.name,
                    discovery_run_id=local_fp.discovery_run_id,
                    challenger_run_id=local_fp.challenger_run_id,
                    cohort_size=local_fp.cohort_size,
                    details={"conflict_winner": winner},
                )
                write_persistence_status(st, root)
                return st

        restore_bundle_to_working_dir(bundle_dir, root)
        restored_fp = fingerprint_working_state(root)
        st = PersistenceStatus(
            last_operation="restore",
            last_result="restored",
            message="restored canonical research bundle from durable backend",
            backend=backend.name,
            discovery_run_id=restored_fp.discovery_run_id,
            challenger_run_id=restored_fp.challenger_run_id,
            cohort_size=restored_fp.cohort_size,
            details={
                "robustness_pass": manifest.get("robustness_pass"),
                "robustness_fragile": manifest.get("robustness_fragile"),
                "robustness_reject": manifest.get("robustness_reject"),
            },
        )
        write_persistence_status(st, root)
        return st
    except BundleValidationError as exc:
        st = PersistenceStatus(
            last_operation="restore",
            last_result="rejected",
            message=str(exc),
            backend=backend.name,
        )
        write_persistence_status(st, root)
        return st
    finally:
        shutil.rmtree(staging.parent, ignore_errors=True)


def publish_durable(data_dir: Optional[Path] = None) -> PersistenceStatus:
    """
    Save contract after successful Discovery/Challenger local persistence:
    build bundle → validate → atomic publish to durable backend.
    """
    root = resolve_data_dir(data_dir)
    backend = _get_backend()
    if not backend.is_configured():
        st = PersistenceStatus(
            last_operation="publish",
            last_result="skipped",
            message="durable backend not configured",
            backend=backend.name,
        )
        write_persistence_status(st, root)
        return st

    if not is_publishable_state(root):
        st = PersistenceStatus(
            last_operation="publish",
            last_result="skipped",
            message="working storage has no publishable discovery cohort",
            backend=backend.name,
        )
        write_persistence_status(st, root)
        return st

    staging = root / ".durable_staging" / f"publish_{uuid4().hex[:8]}"
    try:
        manifest = stage_bundle_from_working_dir(root, staging)
        pub = backend.publish_bundle(staging)
        fp = fingerprint_working_state(root)
        st = PersistenceStatus(
            last_operation="publish",
            last_result="published" if pub.ok else "failed",
            message=pub.message,
            backend=backend.name,
            discovery_run_id=fp.discovery_run_id,
            challenger_run_id=fp.challenger_run_id,
            cohort_size=fp.cohort_size,
            details={
                "robustness_pass": manifest.get("robustness_pass"),
                "robustness_fragile": manifest.get("robustness_fragile"),
                "robustness_reject": manifest.get("robustness_reject"),
            },
        )
        write_persistence_status(st, root)
        return st
    except BundleValidationError as exc:
        st = PersistenceStatus(
            last_operation="publish",
            last_result="failed",
            message=str(exc),
            backend=backend.name,
        )
        write_persistence_status(st, root)
        return st
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def migrate_working_dir_to_durable(
    source_data_dir: Path,
    durable_root: Path,
) -> PersistenceStatus:
    """One-time migration helper: copy working artifacts → durable local backend."""
    from modules.edge_research.durable import LocalDirectoryDurableBackend

    backend = LocalDirectoryDurableBackend(durable_root)
    staging = source_data_dir / ".durable_staging" / f"migrate_{uuid4().hex[:8]}"
    try:
        manifest = stage_bundle_from_working_dir(source_data_dir, staging)
        pub = backend.publish_bundle(staging)
        return PersistenceStatus(
            last_operation="migrate",
            last_result="published" if pub.ok else "failed",
            message=pub.message,
            backend=backend.name,
            discovery_run_id=str(manifest.get("discovery_run_id", "")),
            challenger_run_id=str(manifest.get("challenger_run_id", "")),
            cohort_size=int(manifest.get("cohort_size", 0) or 0),
            details={
                "robustness_pass": manifest.get("robustness_pass"),
                "robustness_fragile": manifest.get("robustness_fragile"),
                "robustness_reject": manifest.get("robustness_reject"),
            },
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def summarize_restored_cohort(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Diagnostic summary after restore — no UI dependency."""
    root = resolve_data_dir(data_dir)
    discovery = read_discovery_run(root)
    challenger = read_challenger_run(root)
    cohort = resolve_discovery_cohort(root)
    counts: Dict[str, int] = {}
    if not cohort.empty and "robustness_status" in cohort.columns:
        for val, cnt in cohort["robustness_status"].value_counts(dropna=False).items():
            counts[str(val)] = int(cnt)
    return {
        "cohort_size": len(cohort),
        "discovery_run_id": discovery.get("run_id"),
        "challenger_run_id": challenger.get("run_id"),
        "robustness_pass": challenger.get("robustness_pass"),
        "robustness_fragile": challenger.get("robustness_fragile"),
        "robustness_reject": challenger.get("robustness_reject"),
        "cohort_robustness_counts": counts,
        "has_valid_cohort": not cohort.empty and bool(discovery.get("run_id")),
    }
