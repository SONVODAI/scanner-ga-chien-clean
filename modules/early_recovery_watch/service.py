"""Run one Early Recovery evaluation. Research only.

Market Real is the value passed by this run. It is not read back from
market_context.jsonl.
"""

from __future__ import annotations

import statistics
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from modules.early_recovery_watch.contract import (
    EMPTY_MESSAGE,
    OUTCOME_FIELDS,
    PANEL_TITLE,
)
from modules.early_recovery_watch.observe import (
    build_event,
    candidate_from_row,
    current_scan_boundary,
    health_label,
    health_kind,
    horizon_returns,
    later_session_prices,
    previous_observation,
    symbol_key,
)
from modules.early_recovery_watch.store import (
    TextMirror,
    append_new_records,
    events_path,
    load_merged_text,
    materialize,
    save_text,
    watch_dir,
)
from modules.research_evolution_ledger.ledger import ledger_path, load_evolution_ledger
from modules.research_market_context.contract import SOURCE_STREAMLIT_SCAN
from modules.research_market_context.market_context import scan_fingerprint


def _day(value: date | str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _current_rows(scan_df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if scan_df is None or not isinstance(scan_df, pd.DataFrame) or scan_df.empty:
        return []
    if "symbol" not in scan_df.columns:
        return []
    latest: dict[str, dict[str, Any]] = {}
    for record in scan_df.to_dict("records"):
        key = symbol_key(record.get("symbol"))
        if key:
            latest[key] = record
    return list(latest.values())


def _evolution_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return load_evolution_ledger(path)


def scorecard(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    def _side(field: str) -> dict[str, Any]:
        values = [event.get(field) for event in events if event.get(field) is not None]
        if not values:
            return {"n": 0, "winrate": None, "median": None}
        wins = sum(1 for value in values if float(value) > 0.0)
        return {
            "n": len(values),
            "winrate": wins / len(values),
            "median": float(statistics.median([float(value) for value in values])),
        }

    t3 = _side("t3_return_pct")
    t5 = _side("t5_return_pct")
    return {
        "events": len(events),
        "independent_signal_days": len({str(event.get("event_date") or "") for event in events if event.get("event_date")}),
        "mature_t3_n": t3["n"],
        "t3_winrate": t3["winrate"],
        "median_t3": t3["median"],
        "mature_t5_n": t5["n"],
        "t5_winrate": t5["winrate"],
        "median_t5": t5["median"],
    }


def _display_rows(
    events: list[Mapping[str, Any]],
    evolution_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered = sorted(
        events,
        key=lambda event: (str(event.get("event_date") or ""), str(event.get("symbol") or "")),
        reverse=True,
    )
    rows: list[dict[str, Any]] = []
    for event in ordered:
        sessions = later_session_prices(
            evolution_lines,
            event.get("symbol"),
            str(event.get("event_date") or ""),
        )
        previous = health_label(health_kind(event.get("previous_health")))
        current = health_label(health_kind(event.get("current_health")))
        rows.append(
            {
                "Mã": event.get("symbol"),
                "Giá T0": event.get("t0_price"),
                "Prev → Now": f"{previous} → {current}",
                "RS10": event.get("current_rs10"),
                "ΔRS10": event.get("delta_rs10"),
                "Vol": "Có" if event.get("vol_confirm") else "",
                "M.Real": event.get("market_real_t0"),
                "Regime": event.get("market_regime") or "",
                "Age": len(sessions),
                "T3": event.get("t3_return_pct"),
                "T5": event.get("t5_return_pct"),
                "T10": event.get("t10_return_pct"),
            }
        )
    return rows


def build_view(
    events: list[Mapping[str, Any]],
    evolution_lines: list[dict[str, Any]],
) -> dict[str, Any]:
    frozen = list(events)
    return {
        "visible": True,
        "title": PANEL_TITLE,
        "empty_message": "" if frozen else EMPTY_MESSAGE,
        "scorecard": scorecard(frozen),
        "rows": _display_rows(frozen, evolution_lines),
    }


def _outcome_updates(
    events: list[Mapping[str, Any]],
    evolution_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for event in events:
        sessions = later_session_prices(
            evolution_lines,
            event.get("symbol"),
            str(event.get("event_date") or ""),
        )
        returns = horizon_returns(
            [price for _, price in sessions],
            event.get("t0_price"),
        )
        changed = False
        for field in OUTCOME_FIELDS:
            if returns[field] is not None and returns[field] != event.get(field):
                changed = True
        if changed:
            updates.append({"event_id": event.get("event_id"), **returns})
    return updates


def run_watch(
    *,
    scan_df: pd.DataFrame | None,
    market_real: object,
    trade_date: date | str,
    source: str = SOURCE_STREAMLIT_SCAN,
    market_live: object = None,
    market_forecast: object = None,
    market_regime: object = None,
    breadth: object = None,
    market_status: object = None,
    market_action: object = None,
    evolution_path: Path | None = None,
    directory: Path | None = None,
    storage: TextMirror | None = None,
) -> dict[str, Any]:
    """Qualify this scan and append any new frozen events.

    The previous-line boundary is the captured_at of this scan's own ledger
    lines. A later wall clock must not turn that line into the previous one.
    """
    evo_path = Path(evolution_path) if evolution_path is not None else ledger_path()
    lines = _evolution_lines(evo_path)
    day = _day(trade_date)
    fingerprint = scan_fingerprint(scan_df if isinstance(scan_df, pd.DataFrame) else None)
    boundary = current_scan_boundary(
        lines,
        scan_fingerprint=fingerprint,
        trade_date=day,
        source=source,
    )
    dest = watch_dir(directory)
    dest.mkdir(parents=True, exist_ok=True)
    mirror = storage if storage is not None else _default_storage(dest)
    merged = load_merged_text(mirror, dest)
    existing = materialize(merged)
    existing_ids = {str(event.get("event_id") or "") for event in existing}

    fresh: list[dict[str, Any]] = []
    metadata: Mapping[str, Any] = {
        "market_live": market_live,
        "market_forecast": market_forecast,
        "market_regime": market_regime,
        "breadth": breadth,
        "market_status": market_status,
        "market_action": market_action,
    }
    if boundary is not None:
        for row in _current_rows(scan_df):
            previous = previous_observation(lines, row.get("symbol"), boundary)
            if previous is None:
                continue
            if not candidate_from_row(row, previous, market_real):
                continue
            event = build_event(
                symbol=row.get("symbol"),
                event_date=day,
                event_timestamp=boundary,
                current=row,
                previous=previous,
                market_real=float(market_real),
                scan_fingerprint=fingerprint,
                source=source,
                metadata=metadata,
            )
            if event["event_id"] in existing_ids or any(
                item["event_id"] == event["event_id"] for item in fresh
            ):
                continue
            fresh.append(event)

    combined = [*existing, *fresh]
    updates = _outcome_updates(combined, lines)
    final_text, appended = append_new_records(merged, fresh, updates)
    local_text = ""
    path = events_path(dest)
    if path.exists():
        local_text = path.read_text(encoding="utf-8")
    if appended or local_text != final_text:
        save_text(
            mirror,
            final_text,
            message="Early Recovery Watch forward events",
        )
    events = materialize(final_text)
    return {
        "events": events,
        "created": [event["event_id"] for event in fresh if event["event_id"] not in existing_ids],
        "appended": appended,
        "view": build_view(events, lines),
        "boundary": boundary.isoformat() if boundary is not None else None,
    }


def _default_storage(directory: Path) -> TextMirror:
    from modules.early_recovery_watch.store import build_storage

    return build_storage(directory)
