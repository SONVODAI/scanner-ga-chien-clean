"""Rotation-only state persistence. Never writes Candidate / Edge / Learning artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.live_candidate.calendar import as_vn
from modules.rotation_watch.config import default_watch_dir
from modules.rotation_watch.constants import SCHEMA_STATE, STATE_NAME

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
        symbols[symbol] = {
            "previous_state": previous,
            "current_state": current,
            "first_entered_at": first,
            "latest_transition_at": latest,
            "transitions": transitions,
        }
        out.append(symbols[symbol] | {"symbol": symbol})
    payload["updated_at"] = stamp
    payload["schema"] = SCHEMA_STATE
    save_state(payload, path)
    return out
