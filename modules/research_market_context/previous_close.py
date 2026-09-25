"""Canonical previous-close archive. Research only.

previous close = close of the latest D1 bar whose date is strictly < session_date.

The D1 frame is the one the production scan already downloaded. This module
does not call a market-data provider and does not apply the KBS thousands
multiplier. Integer VND is ``round(value, 0)`` of that D1 close.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from modules.live_candidate.calendar import as_vn
from modules.research_market_context.contract import (
    PRICE_UNIT_INTEGER_VND,
    SOURCE_VNSTOCK_D1,
    STALE_GAP_DAYS,
    previous_close_date_eligible,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "research" / "market_context_history"
PREVIOUS_CLOSE_NAME = "previous_close.jsonl"
ENV_DIR = "MRBOT_MARKET_CONTEXT_DIR"

STATUS_OK = "ok"
STATUS_STALE = "stale"
STATUS_MISSING = "missing"


def context_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_DIR, "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_DIR


def previous_close_path(directory: Path | None = None) -> Path:
    return context_dir(directory) / PREVIOUS_CLOSE_NAME


def integer_vnd_from_d1(value: object) -> int | None:
    """D1 close -> integer VND. Never multiplies by 1000."""
    try:
        if value is None or pd.isna(value):
            return None
        rounded = round(float(value), 0)
    except (TypeError, ValueError):
        return None
    if rounded != rounded or rounded <= 0:
        return None
    return int(rounded)


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return as_vn(value).date() if value.tzinfo is not None else value.date()
    if isinstance(value, date):
        return value
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def _last_d1(daily_bars: pd.DataFrame | None) -> tuple[date | None, int | None]:
    if daily_bars is None or not isinstance(daily_bars, pd.DataFrame) or daily_bars.empty:
        return None, None
    if "date" not in daily_bars.columns or "close" not in daily_bars.columns:
        return None, None
    frame = daily_bars.copy()
    frame["_d"] = frame["date"].map(_as_date)
    frame = frame.dropna(subset=["_d"]).sort_values("_d")
    if frame.empty:
        return None, None
    last = frame.iloc[-1]
    return last["_d"], integer_vnd_from_d1(last["close"])


def select_canonical_previous_close(
    daily_bars: pd.DataFrame | None,
    *,
    session_date: date,
) -> dict[str, Any]:
    """Pick the prior bar. A same-day row is never the canonical close."""
    last_date, last_close = _last_d1(daily_bars)
    chosen_date: date | None = None
    chosen_close: int | None = None
    if daily_bars is not None and isinstance(daily_bars, pd.DataFrame) and not daily_bars.empty:
        if "date" in daily_bars.columns and "close" in daily_bars.columns:
            frame = daily_bars.copy()
            frame["_d"] = frame["date"].map(_as_date)
            prior = frame[frame["_d"].map(lambda d: isinstance(d, date) and d < session_date)]
            prior = prior.dropna(subset=["_d"]).sort_values("_d")
            if not prior.empty:
                row = prior.iloc[-1]
                bar_date = row["_d"]
                if isinstance(bar_date, date) and previous_close_date_eligible(bar_date, session_date):
                    chosen_date = bar_date
                    chosen_close = integer_vnd_from_d1(row["close"])

    if chosen_date is None or chosen_close is None:
        status = STATUS_MISSING
        chosen_date = None
        chosen_close = None
    elif (session_date - chosen_date).days > STALE_GAP_DAYS:
        status = STATUS_STALE
    else:
        status = STATUS_OK

    return {
        "previous_close": chosen_close,
        "previous_close_date": chosen_date.isoformat() if chosen_date else None,
        "price_unit": PRICE_UNIT_INTEGER_VND,
        "source": SOURCE_VNSTOCK_D1,
        "status": status,
        "last_d1_date": last_date.isoformat() if last_date else None,
        "last_d1_close_before_injection": last_close,
    }


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _key(session_date: str, symbol: str) -> tuple[str, str]:
    return session_date, symbol.strip().upper()


def archive_previous_close(
    *,
    symbol: str,
    daily_bars: pd.DataFrame | None,
    session_date: date,
    captured_at: datetime | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Insert one canonical row per (session_date, symbol). First row wins."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")
    selected = select_canonical_previous_close(daily_bars, session_date=session_date)
    if selected["previous_close_date"] is not None:
        prior = date.fromisoformat(selected["previous_close_date"])
        if not previous_close_date_eligible(prior, session_date):
            raise RuntimeError("refusing same-day or future previous_close_date")
    now = as_vn(captured_at or datetime.now())
    row = {
        "session_date": session_date.isoformat(),
        "symbol": sym,
        "previous_close": selected["previous_close"],
        "previous_close_date": selected["previous_close_date"],
        "price_unit": PRICE_UNIT_INTEGER_VND,
        "source": SOURCE_VNSTOCK_D1,
        "captured_at": now.isoformat(),
        "status": selected["status"],
        "last_d1_date": selected["last_d1_date"],
        "last_d1_close_before_injection": selected["last_d1_close_before_injection"],
    }
    if row["status"] == STATUS_MISSING:
        return {"ok": True, "written": False, "reason": "missing", "row": row}
    dest = Path(path) if path is not None else previous_close_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_rows(dest)
    want = _key(row["session_date"], row["symbol"])
    for prior_row in existing:
        if _key(str(prior_row.get("session_date") or ""), str(prior_row.get("symbol") or "")) == want:
            return {"ok": True, "written": False, "reason": "duplicate", "row": prior_row}
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return {"ok": True, "written": True, "reason": "appended", "row": row}


def try_archive_previous_close(
    *,
    symbol: str,
    daily_bars: pd.DataFrame | None,
    session_date: date,
    captured_at: datetime | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Fail-open. Disk, parse, and logic errors stay inside this function."""
    try:
        return archive_previous_close(
            symbol=symbol,
            daily_bars=daily_bars,
            session_date=session_date,
            captured_at=captured_at,
            path=path,
        )
    except Exception as exc:  # noqa: BLE001 — research retention must not stop the scan
        return {"ok": False, "written": False, "reason": "write_failed", "error": type(exc).__name__}


def load_previous_close(path: Path) -> list[dict[str, Any]]:
    return _read_rows(path)
