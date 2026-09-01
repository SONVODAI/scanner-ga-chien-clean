"""
Production integration for Actionable Research Fusion.

Called AFTER closed-loop A→C→B on the existing daily orchestrator.
Never a second scheduler. Never mutates scientific edge truth.
Camera collect/reconcile must not own Fusion.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from modules.actionable_research.engine import fuse_session
from modules.actionable_research.paths import FusionPaths

logger = logging.getLogger(__name__)


def _flatten_receipt_fields(result: Dict[str, Any], *, paths: FusionPaths, td: str) -> Dict[str, Any]:
    scan = result.get("scan") or {}
    status = str(result.get("session_status") or "UNKNOWN")
    return {
        "ran_fusion": True,
        "ran": True,
        "status": status,
        "trade_date": td,
        "session_status": status,
        "authority": result.get("authority"),
        "universe_evaluated": result.get("universe_count") or scan.get("scanned_count") or 0,
        "noteworthy_count": result.get("notable_count"),
        "notable_count": result.get("notable_count"),
        "record_count": result.get("record_count") or len(result.get("records") or []),
        "artifact_path": str(paths.daily_path(td)),
        "artifact_daily_path": str(paths.daily_path(td)),
        "observation_births": result.get("observation_births") or 0,
        "observation_duplicate_skips": result.get("observation_duplicate_skips") or 0,
        "missing_camera_count": scan.get("camera_unknown_count"),
        "missing_foreign_count": scan.get("foreign_unknown_count"),
        "generated_at": result.get("generated_at"),
        "idempotent_replay": result.get("idempotent_replay"),
        "headline_vi": result.get("headline_vi"),
        "scientific_writes": result.get("scientific_writes") or [],
        "observation_maturity": result.get("observation_maturity") or {},
        "result": result,
    }


def run_actionable_research_after_daily(
    *,
    target_trade_date: str,
    daily_result: Optional[Dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    camera_root: Optional[Path] = None,
    artifact_root: Optional[Path] = None,
    cutoff: Optional[datetime | str] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """
    Nested payload for the existing daily pipeline.

    Failures stay on this payload. Does not change daily run_disposition.
    Does not write edge_memory / edge_forward_ledger / LIVE_FORWARD births.
    """
    td = str(target_trade_date or "")[:10]
    root = Path(repo_root) if repo_root else FusionPaths().resolved_repo()
    app_py = root / "app.py"
    paths = FusionPaths(
        repo_root=root,
        edge_data_dir=Path(data_dir) if data_dir else None,
        camera_root=Path(camera_root) if camera_root else None,
        artifact_root=Path(artifact_root) if artifact_root else (root / "data" / "actionable_research"),
        app_py_path=app_py if app_py.exists() else None,
    )
    try:
        result = fuse_session(
            td,
            paths=paths,
            cutoff=cutoff,
            daily_result=daily_result,
            persist=persist,
        )
        return _flatten_receipt_fields(result, paths=paths, td=td)
    except Exception as exc:  # noqa: BLE001
        logger.exception("actionable research fusion failed")
        return {
            "ran_fusion": False,
            "ran": False,
            "status": "FAILED",
            "trade_date": td,
            "session_status": "FAILED",
            "authority": "RESEARCH ONLY",
            "universe_evaluated": 0,
            "noteworthy_count": None,
            "artifact_path": None,
            "observation_births": 0,
            "observation_duplicate_skips": 0,
            "missing_camera_count": None,
            "missing_foreign_count": None,
            "generated_at": None,
            "failure_detail": f"{type(exc).__name__}: {exc}",
            "scientific_writes": [],
        }


def maybe_run_fusion_after_camera(
    session_date: date | str,
    *,
    camera_root: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    stage: str = "camera",
) -> Dict[str, Any]:
    """
    Intentionally a no-op on the current-production lineage.

    Fusion is owned by the daily orchestrator after A→C→B so Camera collect
    cannot birth T0 observations before scientific recognition.
    """
    td = session_date.isoformat() if isinstance(session_date, date) else str(session_date)[:10]
    logger.info("fusion after %s skipped: owned by daily A→C→B orchestrator", stage)
    return {
        "ran_fusion": False,
        "ran": False,
        "status": "SKIPPED",
        "trade_date": td,
        "session_status": "SKIPPED_OWNED_BY_DAILY_ORCHESTRATOR",
        "stage": stage,
        "scientific_writes": [],
    }


def attach_fusion_to_daily_result(
    daily_result: Dict[str, Any],
    *,
    target_trade_date: str,
    repo_root: Optional[Path] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Non-mutating clone + nested actionable_research payload."""
    out = dict(daily_result)
    out["actionable_research"] = run_actionable_research_after_daily(
        target_trade_date=target_trade_date,
        daily_result=daily_result,
        repo_root=repo_root,
        data_dir=data_dir,
    )
    return out
