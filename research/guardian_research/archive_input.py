"""Dry-run one persisted scan through the accepted collector. Never writes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from research.guardian_research.collector import collect
from research.guardian_research.scan_archive import ArchiveRejected, load_persisted_scan
from research.guardian_research.session_authority import probe_vnindex
from research.guardian_research.universe import load_tracked_symbols


def dry_run_persisted_session(
    project_root: Path,
    session: str,
    now: datetime,
    snapshot_root: Path,
    witness: dict | None = None,
    symbols: tuple[str, ...] | None = None,
) -> dict:
    """Validate archive, witness, classification, and hash without sealing."""
    tracked = tuple(symbols) if symbols is not None else load_tracked_symbols()
    resolved = probe_vnindex(session) if witness is None else witness
    try:
        loaded = load_persisted_scan(project_root, session, tracked)
    except ArchiveRejected as exc:
        return _view(session, _refused(exc.reason), resolved, None)
    result = collect(
        loaded["scan_df"],
        now=now,
        session=session,
        root=snapshot_root,
        witness=resolved,
        market_real=loaded["market_real"],
        coverage=loaded["coverage"],
        symbols=tracked,
        dry_run=True,
    )
    return _view(session, result, resolved, loaded["provenance"])


def _view(session: str, result: dict, witness: dict, provenance: dict | None) -> dict:
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "session": session,
        "path": None,
        "document": result.get("document"),
        "tracked_count": result.get("tracked_count") or (provenance or {}).get("rows"),
        "witness_bar_session": witness.get("bar_session") or None,
        "witness_error": witness.get("probe_error"),
        "archive_rows": None if provenance is None else provenance.get("rows"),
        "archive_saved_at": None if provenance is None else provenance.get("saved_at"),
        "market_real_source": None if provenance is None else provenance.get("market_real_source"),
    }


def _refused(reason: str) -> dict:
    return {"status": "refused", "reason": reason, "document": None, "tracked_count": None}
