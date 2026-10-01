"""
Production integration for Actionable Research Fusion.

Called after existing daily orchestration (closed-loop A→C→B when present)
and optionally after Camera reconcile. Never a second scheduler.
Never mutates scientific edge truth.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from modules.actionable_research.engine import fuse_session
from modules.actionable_research.paths import FusionPaths

logger = logging.getLogger(__name__)


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
    paths = FusionPaths(
        repo_root=Path(repo_root) if repo_root else FusionPaths().resolved_repo(),
        edge_data_dir=Path(data_dir) if data_dir else None,
        camera_root=Path(camera_root) if camera_root else None,
        artifact_root=Path(artifact_root) if artifact_root else None,
    )
    try:
        result = fuse_session(
            td,
            paths=paths,
            cutoff=cutoff,
            daily_result=daily_result,
            persist=persist,
        )
        return {
            "ran_fusion": True,
            "trade_date": td,
            "session_status": result.get("session_status"),
            "authority": result.get("authority"),
            "notable_count": result.get("notable_count"),
            "record_count": result.get("record_count") or len(result.get("records") or []),
            "idempotent_replay": result.get("idempotent_replay"),
            "headline_vi": result.get("headline_vi"),
            "scientific_writes": result.get("scientific_writes") or [],
            "artifact_daily_path": str(paths.daily_path(td)),
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("actionable research fusion failed")
        return {
            "ran_fusion": False,
            "trade_date": td,
            "session_status": "FAILED",
            "authority": "RESEARCH ONLY",
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
    """Fail-safe Camera post-step. Must never fail collect/reconcile."""
    td = session_date.isoformat() if isinstance(session_date, date) else str(session_date)[:10]
    try:
        return run_actionable_research_after_daily(
            target_trade_date=td,
            daily_result=None,
            repo_root=repo_root,
            camera_root=camera_root,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("fusion after %s skipped: %s", stage, exc)
        return {
            "ran_fusion": False,
            "trade_date": td,
            "session_status": "FAILED",
            "stage": stage,
            "failure_detail": f"{type(exc).__name__}: {exc}",
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
