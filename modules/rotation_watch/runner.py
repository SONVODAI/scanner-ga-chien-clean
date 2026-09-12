"""Rotation Watch sidecar. Intended for /opt/mrbot-camera-venv (vnstock 4.x).

Never writes Candidate / Edge / Learning / Camera parquet.
One provider failure isolates to that symbol.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from modules.live_candidate.calendar import as_vn
from modules.rotation_watch.artifact import board_from_rows, write_board, write_status
from modules.rotation_watch.config import default_watchlist_path, load_watchlist
from modules.rotation_watch.constants import ARTIFACT_STALE_AFTER_SEC, ST_DATA_UNCERTAIN
from modules.rotation_watch.publish import publish_rotation_artifacts, resolve_rotation_store
from modules.rotation_watch.data import SymbolSnapshot, fetch_symbol_snapshot
from modules.rotation_watch.engine import RotationRow, evaluate_row
from modules.rotation_watch.pxv import RotationPxV, interpret_completed_bars
from modules.rotation_watch.session import session_phase
from modules.rotation_watch.state import apply_transitions, default_state_path

BAR_MINUTES = 5
DEFAULT_RPM = 18


def seconds_until_next_completed_bar(now: datetime) -> float:
    """Sleep target: next 5m slot close (bar_ts + 5m)."""
    now = as_vn(now)
    minute = (now.minute // BAR_MINUTES) * BAR_MINUTES
    slot = now.replace(minute=minute, second=0, microsecond=0)
    nxt = slot + timedelta(minutes=BAR_MINUTES)
    wait = (nxt - now).total_seconds()
    return max(1.0, wait)


def _row_to_artifact(row: RotationRow, *, observed_at: str, source: str, source_label: str) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "current_price": row.current_price,
        "lower_zone": row.lower_zone,
        "upper_zone": row.upper_zone,
        "range_position_pct": row.range_position_pct,
        "location": row.location,
        "last_session_state": row.rotation_state,
        "last_session_action": row.suggested_action,
        "rotation_state": row.rotation_state,
        "suggested_action": row.suggested_action,
        "raw_pxv": row.raw_pxv,
        "published_pxv": row.published_pxv,
        "pxv_why": row.pxv_why,
        "published_why": row.published_why,
        "evidence_why": row.pxv_why,
        "rotation_evidence": list(row.rotation_evidence),
        "last_bar_ts": row.last_bar_ts,
        "observed_at": observed_at,
        "source": source,
        "source_id": source,
        "data_source": source,
        "data_source_label": source_label,
        "freshness": row.freshness,
        "freshness_reason": row.freshness_reason,
        "entry_price": row.entry_price,
        "pnl_pct": row.pnl_pct,
        "previous_state": row.previous_state,
        "current_state": row.rotation_state,
        "first_entered_at": row.first_entered_at,
        "latest_transition_at": row.latest_transition_at,
        "t25_checkpoint": row.t25_checkpoint,
        "has_position": row.has_position,
        "note": row.note,
        "enabled": row.enabled,
    }


def run_cycle(
    *,
    now: datetime,
    provider: Any | None = None,
    watchlist_path: Path | None = None,
    injected: dict[str, list[dict[str, Any]]] | None = None,
    board_path: Path | None = None,
    status_path: Path | None = None,
    state_path: Path | None = None,
    store_dir: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    now = as_vn(now)
    observed = now.isoformat()
    rows_cfg = load_watchlist(watchlist_path)
    path = str(watchlist_path or default_watchlist_path())
    symbol_status: list[dict[str, Any]] = []
    evaluated: list[RotationRow] = []

    for cfg in rows_cfg:
        try:
            if injected is not None:
                snap = fetch_symbol_snapshot(
                    cfg.symbol, now, injected_records=injected.get(cfg.symbol, [])
                )
            else:
                snap = fetch_symbol_snapshot(cfg.symbol, now, provider=provider)
            pxv = interpret_completed_bars(snap.completed, now=now) if snap.completed else RotationPxV()
            ev = evaluate_row(cfg, snap, pxv, now=now)
            evaluated.append(ev)
            symbol_status.append(
                {
                    "symbol": cfg.symbol,
                    "ok": ev.rotation_state != ST_DATA_UNCERTAIN or snap.is_usable,
                    "freshness": ev.freshness,
                    "error": snap.error,
                }
            )
        except Exception as exc:
            symbol_status.append(
                {
                    "symbol": cfg.symbol,
                    "ok": False,
                    "freshness": "PROVIDER_ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            snap = SymbolSnapshot(
                symbol=cfg.symbol,
                source="unavailable",
                source_label="symbol fetch failed — isolated",
                session_date=None,
                expected_session=now.date(),
                freshness_label="PROVIDER_ERROR",
                freshness_reason=f"{type(exc).__name__}: {exc}",
                is_usable=False,
                error=str(exc),
            )
            evaluated.append(evaluate_row(cfg, snap, RotationPxV(), now=now))

    if persist and evaluated:
        persisted = apply_transitions(evaluated, now=now, path=state_path or default_state_path())
        by_sym = {p["symbol"]: p for p in persisted}
        for item in evaluated:
            rec = by_sym.get(item.symbol) or {}
            item.previous_state = str(rec.get("previous_state") or "")
            item.first_entered_at = str(rec.get("first_entered_at") or "")
            item.latest_transition_at = str(rec.get("latest_transition_at") or "")

    art_rows = [
        _row_to_artifact(
            ev,
            observed_at=observed,
            source=ev.data_source,
            source_label=ev.data_source_label,
        )
        for ev in evaluated
    ]
    runner_meta = {
        "n_symbols": len(rows_cfg),
        "n_ok": sum(1 for s in symbol_status if s.get("ok")),
        "n_failed": sum(1 for s in symbol_status if not s.get("ok")),
        "rpm": DEFAULT_RPM,
        "stale_after_sec": ARTIFACT_STALE_AFTER_SEC,
        "symbols": symbol_status,
        "session_phase": session_phase(now),
    }
    board = board_from_rows(
        art_rows,
        now=now,
        watchlist_path=path,
        empty_message="" if art_rows else "Chưa có mã enabled trong data/rotation_watch/watchlist.csv",
        runner=runner_meta,
    )
    written_board = write_board(board, board_path)
    status = {
        "schema": "rotation_watch_status.v1",
        "observed_at": observed,
        "session_phase": session_phase(now),
        "alert_eligible": False,
        "n_symbols": len(rows_cfg),
        "symbols": symbol_status,
    }
    write_status(status, status_path)
    dest = resolve_rotation_store(store_dir)
    if dest is not None:
        status["publish"] = publish_rotation_artifacts(written_board.parent, dest)
    return status
