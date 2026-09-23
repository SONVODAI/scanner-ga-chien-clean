"""Rotation-only state persistence. Never writes Candidate / Edge / Learning artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.live_candidate.calendar import as_vn
from modules.rotation_watch.config import default_watch_dir
from modules.rotation_watch.constants import SCHEMA_STATE, ST_BUY_READY, STATE_NAME

# Future alert hooks look at these pairs only. V1 records them; no Telegram.
ALERTABLE_TRANSITIONS = frozenset(
    {
        ("LOWER_ZONE", "BUY_READY"),
        ("WATCH", "BUY_READY"),
        ("HOLD", "BUY_READY"),
        ("UPPER_ZONE", "SELL_READY"),
        ("HOLD", "SELL_READY"),
        ("WATCH", "SELL_READY"),
        ("UPPER_ZONE", "TREND_HOLD"),
        ("HOLD", "TREND_HOLD"),
        ("WATCH", "TREND_HOLD"),
        ("LOWER_ZONE", "RISK"),
        ("HOLD", "RISK"),
        ("BUY_READY", "RISK"),
    }
)


def default_state_path() -> Path:
    return default_watch_dir() / STATE_NAME


def load_state(path: Path | None = None) -> dict[str, Any]:
    src = path or default_state_path()
    if not src.exists():
        return {"schema": SCHEMA_STATE, "updated_at": "", "symbols": {}}
    data = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"schema": SCHEMA_STATE, "updated_at": "", "symbols": {}}
    data.setdefault("schema", SCHEMA_STATE)
    data.setdefault("symbols", {})
    return data


def save_state(payload: dict[str, Any], path: Path | None = None) -> Path:
    dest = path or default_state_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _nonempty_text(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return ""


def capture_buy_ready(row: Any, symbol: str, stamp: str) -> dict[str, Any]:
    """Fields already present on this cycle. Missing values are omitted, not guessed."""
    record: dict[str, Any] = {
        "symbol": symbol,
        "last_buy_ready_at": stamp,
    }
    price = _row_value(row, "current_price")
    if price is not None and price != "":
        record["price"] = price
    location = _nonempty_text(_row_value(row, "location"))
    if location:
        record["location"] = location
    published = _nonempty_text(_row_value(row, "published_pxv"))
    if published:
        record["published_pxv"] = published
    reason = _nonempty_text(_row_value(row, "pxv_why")) or _nonempty_text(
        _row_value(row, "published_why")
    )
    if reason:
        record["reason"] = reason
    return record


def backfill_buy_ready(symbol: str, transitions: list[Any]) -> dict[str, Any] | None:
    """Latest retained transition into BUY_READY. Timestamp only — old rows have no price/P×V."""
    latest_at = ""
    for item in transitions:
        if not isinstance(item, dict):
            continue
        if item.get("to") != ST_BUY_READY:
            continue
        at = _nonempty_text(item.get("at"))
        if at and at > latest_at:
            latest_at = at
    if not latest_at:
        return None
    return {"symbol": symbol, "last_buy_ready_at": latest_at}


def _kept_buy_ready(rec: dict[str, Any]) -> dict[str, Any] | None:
    raw = rec.get("last_buy_ready")
    if not isinstance(raw, dict):
        return None
    if not _nonempty_text(raw.get("last_buy_ready_at")):
        return None
    return dict(raw)


def copy_persisted_fields(row: Any, rec: dict[str, Any]) -> None:
    row.previous_state = str(rec.get("previous_state") or "")
    row.first_entered_at = str(rec.get("first_entered_at") or "")
    row.latest_transition_at = str(rec.get("latest_transition_at") or "")
    raw = rec.get("last_buy_ready")
    row.last_buy_ready = dict(raw) if isinstance(raw, dict) else {}


def apply_transitions(
    rows: list[Any],
    *,
    now: datetime,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    now = as_vn(now)
    stamp = now.isoformat()
    payload = load_state(path)
    symbols = payload.setdefault("symbols", {})
    out: list[dict[str, Any]] = []
    for row in rows:
        symbol = getattr(row, "symbol", None) or row.get("symbol")
        current = getattr(row, "rotation_state", None) or row.get("rotation_state")
        rec = symbols.get(symbol) or {}
        previous = rec.get("current_state") or ""
        first = rec.get("first_entered_at") or stamp
        latest = rec.get("latest_transition_at") or stamp
        transitions = list(rec.get("transitions") or [])
        last_buy_ready = _kept_buy_ready(rec)
        entered_buy_ready = current == ST_BUY_READY and previous != current
        if previous != current:
            if previous:
                transitions.append(
                    {
                        "from": previous,
                        "to": current,
                        "at": stamp,
                        "alert_worthy": (previous, current) in ALERTABLE_TRANSITIONS,
                    }
                )
                latest = stamp
                first = stamp
            else:
                first = stamp
                latest = stamp
            transitions = transitions[-50:]
        # last_buy_ready survives later states and calendar days. The 50-transition
        # cap does not apply to it. A newer entry into BUY_READY replaces it.
        # If the field is absent, backfill only the latest retained to==BUY_READY
        # timestamp — price/location/P×V are not reconstructed.
        if entered_buy_ready:
            last_buy_ready = capture_buy_ready(row, symbol, stamp)
        elif last_buy_ready is None:
            last_buy_ready = backfill_buy_ready(symbol, transitions)
        symbols[symbol] = {
            "previous_state": previous,
            "current_state": current,
            "first_entered_at": first,
            "latest_transition_at": latest,
            "transitions": transitions,
        }
        if last_buy_ready:
            symbols[symbol]["last_buy_ready"] = last_buy_ready
        out.append(symbols[symbol] | {"symbol": symbol})
    payload["updated_at"] = stamp
    payload["schema"] = SCHEMA_STATE
    save_state(payload, path)
    return out
