"""Last valid 5-minute close for each confirmed trading session."""

from __future__ import annotations

import math
from datetime import time

import pandas as pd

from research.approximate_returns.contract import (
    DISCONTINUITY_THRESHOLD,
    PRICE_BASIS,
    PRICE_UNIT,
    SCHEMA_REFERENCE,
    SOURCE,
    TRUNCATION_CLOCK,
)


class ReferenceRejected(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def load_confirmed_sessions(document: dict) -> list[str]:
    sessions = [str(item) for item in document.get("sessions") or []]
    if sessions != sorted(set(sessions)):
        raise ReferenceRejected("SESSION_INDEX_INVALID")
    return sessions


def build_reference_store(frame: pd.DataFrame, sessions: list[str], *, as_of: str) -> dict:
    """One reference per symbol-session. Later bars and off-calendar bars are dropped."""
    calendar = _calendar(sessions, as_of)
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ReferenceRejected("BARS_ABSENT")
    required = {"symbol", "close"}
    if not required.issubset(frame.columns):
        raise ReferenceRejected("BAR_COLUMNS_ABSENT")
    if "session" not in frame.columns and "session_date" not in frame.columns:
        raise ReferenceRejected("BAR_COLUMNS_ABSENT")
    work = frame.copy()
    work["symbol"] = work["symbol"].astype(str).str.strip().str.upper()
    work["session"] = work["session" if "session" in work.columns else "session_date"].astype(str).str.slice(0, 10)
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    work["clock"] = _clocks(work)
    rejected_lookahead = int(work["session"].map(lambda day: _after(day, as_of)).sum())
    rejected_off_calendar = int((~work["session"].isin(calendar) & ~work["session"].map(lambda day: _after(day, as_of))).sum())
    kept = work[work["session"].isin(calendar) & work["close"].map(_positive)].copy()
    if kept.empty:
        raise ReferenceRejected("NO_REFERENCES")
    kept = kept.sort_values(["session", "symbol", "clock"]).groupby(["session", "symbol"], as_index=False).tail(1)
    rows = []
    for item in kept.itertuples(index=False):
        close = _price(item.close)
        clock = str(item.clock)
        if close is None:
            continue
        truncated = not clock or _minutes(clock) < _minutes(TRUNCATION_CLOCK)
        rows.append({
            "symbol": item.symbol,
            "session": item.session,
            "close": close,
            "clock": clock,
            "quality": "TRUNCATED" if truncated else "OK",
        })
    rows.sort(key=lambda row: (row["session"], row["symbol"]))
    discontinuities = _discontinuities(rows, calendar)
    return {
        "schema": SCHEMA_REFERENCE,
        "price_basis": PRICE_BASIS,
        "source": SOURCE,
        "price_unit": PRICE_UNIT,
        "truncation_clock": TRUNCATION_CLOCK,
        "discontinuity_threshold": DISCONTINUITY_THRESHOLD,
        "as_of": as_of,
        "trading_sessions": calendar,
        "rejected_lookahead": rejected_lookahead,
        "rejected_off_calendar": rejected_off_calendar,
        "rows": rows,
        "discontinuities": discontinuities,
    }


def index_store(store: dict) -> dict:
    prices = {}
    clocks = {}
    for row in store["rows"]:
        key = (row["symbol"], row["session"])
        prices[key] = row["close"]
        clocks[key] = row["clock"]
    flagged = {(item["symbol"], item["session"]) for item in store["discontinuities"]}
    sessions = list(store["trading_sessions"])
    return {
        "prices": prices,
        "clocks": clocks,
        "flagged": flagged,
        "sessions": sessions,
        "index": {day: position for position, day in enumerate(sessions)},
    }


def _calendar(sessions: list[str], as_of: str) -> list[str]:
    if sessions != sorted(set(sessions)):
        raise ReferenceRejected("SESSION_INDEX_INVALID")
    if as_of not in sessions or sessions[-1] != as_of:
        raise ReferenceRejected("CALENDAR_AFTER_AS_OF")
    return list(sessions)


def _clocks(frame: pd.DataFrame) -> pd.Series:
    if "clock" in frame.columns:
        return frame["clock"].map(_normalize_clock)
    if "timestamp" not in frame.columns:
        return pd.Series([""] * len(frame), index=frame.index)
    stamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    if getattr(stamps.dt, "tz", None) is not None:
        stamps = stamps.dt.tz_convert("Asia/Ho_Chi_Minh")
    return stamps.dt.strftime("%H:%M").fillna("")


def _normalize_clock(value) -> str:
    text = str(value or "").strip()
    if len(text) >= 5 and text[2] == ":":
        return text[:5]
    return ""


def _minutes(clock: str) -> int:
    hour, minute = clock.split(":")
    parsed = time(int(hour), int(minute))
    return parsed.hour * 60 + parsed.minute


def _positive(value) -> bool:
    return _price(value) is not None


def _price(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    if number.is_integer():
        return int(number)
    return number


def _after(day: str, as_of: str) -> bool:
    return len(day) == 10 and day > as_of


def _discontinuities(rows: list[dict], sessions: list[str]) -> list[dict]:
    by_symbol: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        by_symbol.setdefault(row["symbol"], []).append((row["session"], float(row["close"])))
    order = {day: position for position, day in enumerate(sessions)}
    found = []
    for symbol, pairs in by_symbol.items():
        pairs.sort(key=lambda item: order[item[0]])
        for (prior_day, prior_price), (day, price) in zip(pairs, pairs[1:]):
            if prior_price <= 0:
                continue
            change = price / prior_price - 1
            if abs(change) >= DISCONTINUITY_THRESHOLD:
                found.append({
                    "symbol": symbol,
                    "prior_session": prior_day,
                    "session": day,
                    "change_pct": round(change * 100, 4),
                })
    found.sort(key=lambda item: (item["session"], item["symbol"]))
    return found
