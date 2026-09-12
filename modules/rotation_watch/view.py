"""View-model for the read-only Rotation Watch panel."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from modules.live_candidate.calendar import as_vn
from modules.rotation_watch.constants import (
    ACT_WAIT,
    FRESH_MISSING,
    ST_DATA_UNCERTAIN,
)
from modules.rotation_watch.read import load_panel_sources
from modules.rotation_watch.session import apply_actionability, session_phase


def _uncertain_row(symbol: str, reason: str, *, now: datetime) -> dict[str, Any]:
    return apply_actionability(
        {
            "symbol": symbol or "—",
            "current_price": None,
            "lower_zone": "",
            "upper_zone": "",
            "range_position_pct": None,
            "last_session_state": ST_DATA_UNCERTAIN,
            "last_session_action": ACT_WAIT,
            "rotation_state": ST_DATA_UNCERTAIN,
            "suggested_action": ACT_WAIT,
            "raw_pxv": "",
            "published_pxv": "",
            "pxv_why": "",
            "published_why": "",
            "rotation_evidence": [f"DATA_UNCERTAIN: {reason}"],
            "last_bar_ts": "",
            "freshness": FRESH_MISSING,
            "freshness_reason": reason,
            "data_source": "unavailable",
            "data_source_label": "Rotation artifact missing or unusable — no Yahoo/KBS fallback",
            "entry_price": None,
            "pnl_pct": None,
        },
        now,
    )


def build_panel(
    *,
    now: datetime,
    artifact_path: Path | None = None,
    sources: dict[str, Any] | None = None,
    source_mode: str | None = None,
    board_fetcher=None,
    status_fetcher=None,
) -> dict[str, Any]:
    now = as_vn(now)
    transport: dict[str, Any] = {}
    if sources is not None:
        raw = sources
    else:
        packed = load_panel_sources(
            artifact_path=artifact_path,
            source_mode=source_mode,
            board_fetcher=board_fetcher,
            status_fetcher=status_fetcher,
        )
        raw = packed.get("board")
        transport = dict(packed.get("transport") or {})
    phase = session_phase(now)
    if raw is None:
        reason = "Rotation artifact missing"
        if transport.get("error"):
            reason = str(transport.get("detail") or transport.get("error") or reason)
        return {
            "empty": False,
            "empty_message": "",
            "observed_at": "",
            "session_phase": phase,
            "alert_eligible": False,
            "transport": transport,
            "rows": [_uncertain_row("", reason, now=now)],
        }

    observed = raw.get("observed_at")
    observed_dt = None
    if observed:
        try:
            observed_dt = as_vn(datetime.fromisoformat(str(observed)))
        except ValueError:
            observed_dt = None

    rows = []
    for row in raw.get("rows") or []:
        rows.append(apply_actionability(row, now, artifact_observed_at=observed_dt))

    if raw.get("empty") and not rows:
        return {
            "empty": True,
            "empty_message": raw.get("empty_message") or "Chưa có mã Rotation Watch.",
            "observed_at": raw.get("observed_at") or "",
            "session_phase": phase,
            "alert_eligible": False,
            "transport": transport,
            "rows": [],
        }

    return {
        "empty": False,
        "empty_message": "",
        "observed_at": raw.get("observed_at") or "",
        "session_phase": phase,
        "alert_eligible": False,
        "watchlist_path": raw.get("watchlist_path") or "",
        "transport": transport,
        "rows": rows,
    }


def display_table(panel: dict[str, Any]) -> Any:
    import pandas as pd

    records = []
    for row in panel.get("rows") or []:
        records.append(
            {
                "Symbol": row.get("symbol"),
                "Current Price": row.get("current_price"),
                "Location": row.get("location"),
                "Lower Zone": row.get("lower_zone"),
                "Upper Zone": row.get("upper_zone"),
                "Range Position %": row.get("range_position_pct"),
                "Last-session State": row.get("last_session_state") or row.get("rotation_state"),
                "Last-session Action": row.get("last_session_action"),
                "Suggested Action": row.get("suggested_action"),
                "Session": row.get("session_phase"),
                "Raw P×V": row.get("raw_pxv"),
                "Published P×V": row.get("published_pxv"),
                "P×V evidence / why": row.get("pxv_why") or row.get("evidence_why"),
                "Last completed 5m bar": row.get("last_bar_ts"),
                "Data Freshness": row.get("freshness"),
                "Entry Price": row.get("entry_price"),
                "P/L %": row.get("pnl_pct"),
                "Rotation evidence": " · ".join(row.get("rotation_evidence") or []),
                "Action gate": row.get("action_gate_reason") or "",
            }
        )
    return pd.DataFrame(records)
