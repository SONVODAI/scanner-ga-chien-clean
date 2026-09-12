"""KBS 5m fetch + session-aware freshness for Rotation Watch.

Reuses Camera KBSProvider and live_camera_shadow completed/stale helpers.
Never reads Candidate live_evidence.jsonl. Never writes Camera parquet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.live_candidate.calendar import as_vn
from modules.live_camera_shadow.bars import (
    classify_stale,
    completed_to_overlay,
    validate_live_records,
)
from modules.rotation_watch.constants import (
    FRESH_INVALID,
    FRESH_LIVE,
    FRESH_LUNCH_HOLD,
    FRESH_MISSING,
    FRESH_PROVIDER_ERROR,
    FRESH_SESSION_CLOSED,
    FRESH_STALE,
    FRESH_UNFINISHED_ONLY,
    FRESH_WRONG_SESSION,
    SOURCE_INJECTED,
    SOURCE_KBS,
    SOURCE_LABEL_INJECTED,
    SOURCE_LABEL_KBS,
    SOURCE_UNAVAILABLE,
)

SESSION_OPEN = time(9, 15)
LUNCH_START = time(11, 30)
LUNCH_END = time(13, 0)
SESSION_END = time(14, 50)
LAST_AM_OK = time(11, 15)
LAST_PM_OK = time(14, 30)


def previous_weekday(day: date) -> date:
    cur = day - timedelta(days=1)
    while cur.weekday() >= 5:
        cur -= timedelta(days=1)
    return cur


def expected_session_date(now: datetime) -> date:
    now = as_vn(now)
    day = now.date()
    if day.weekday() >= 5:
        return previous_weekday(day)
    if now.timetz().replace(tzinfo=None) < SESSION_OPEN:
        return previous_weekday(day)
    return day


@dataclass
class SymbolSnapshot:
    symbol: str
    source: str
    source_label: str
    session_date: date | None
    expected_session: date
    completed: list[dict[str, Any]] = field(default_factory=list)
    latest_bar_ts: datetime | None = None
    latest_close_vnd: int | None = None
    freshness_label: str = FRESH_MISSING
    freshness_reason: str = ""
    is_usable: bool = False
    error: str | None = None

    @property
    def overlay(self) -> Any:
        return completed_to_overlay(self.completed)


def _iso(ts: datetime | None) -> str:
    if ts is None:
        return ""
    return as_vn(ts).isoformat()


def classify_rotation_freshness(
    *,
    latest_completed: datetime | None,
    now: datetime,
    expected_session: date,
    bar_session: date | None,
    had_records: bool,
    had_unfinished_only: bool,
) -> tuple[str, str, bool]:
    """Session-aware freshness. Fail closed on stale / wrong session / missing."""
    now = as_vn(now)
    if latest_completed is None:
        if had_unfinished_only:
            return FRESH_UNFINISHED_ONLY, "only unfinished 5m bar(s); no completed bar", False
        if had_records:
            return FRESH_INVALID, "records present but no valid completed bar", False
        return FRESH_MISSING, "no intraday bars for expected session", False

    latest = as_vn(latest_completed)
    if bar_session is None:
        return FRESH_INVALID, "latest bar session_date missing", False
    if bar_session != expected_session:
        return (
            FRESH_WRONG_SESSION,
            f"bar session {bar_session.isoformat()} != expected {expected_session.isoformat()}",
            False,
        )

    clock = now.timetz().replace(tzinfo=None)
    latest_clock = latest.timetz().replace(tzinfo=None)

    if now.date() == expected_session and LUNCH_START <= clock < LUNCH_END:
        if latest_clock >= LAST_AM_OK:
            return FRESH_LUNCH_HOLD, "lunch hold; last AM completed bar accepted", True
        return FRESH_STALE, "lunch but last completed bar is not the AM close", False

    if now.date() == expected_session and clock >= SESSION_END:
        return FRESH_SESSION_CLOSED, "expected session closed; using last completed 5m bar", True

    if now.date() != expected_session and bar_session == expected_session:
        return FRESH_SESSION_CLOSED, "outside live session; last completed session bars", True

    if classify_stale(latest, now):
        return FRESH_STALE, "latest completed 5m bar older than 15+5 minutes", False
    return FRESH_LIVE, "latest completed 5m bar is live", True


def _snapshot_from_records(
    symbol: str,
    records: list[dict[str, Any]],
    *,
    now: datetime,
    expected_session: date,
    source: str,
    source_label: str,
    error: str | None = None,
) -> SymbolSnapshot:
    completed, other = validate_live_records(
        symbol,
        records,
        session_date=expected_session,
        observed_at=now,
    )
    unfinished_only = bool(other) and not completed and any(
        str(item.get("reason") or "") == "UNFINISHED" for item in other
    )
    latest = completed[-1] if completed else None
    latest_ts = latest["bar_ts"] if latest else None
    bar_session = latest.get("session_date") if latest else None
    label, reason, usable = classify_rotation_freshness(
        latest_completed=latest_ts,
        now=now,
        expected_session=expected_session,
        bar_session=bar_session,
        had_records=bool(records),
        had_unfinished_only=unfinished_only,
    )
    if error:
        usable = False
        if label in {FRESH_MISSING, FRESH_INVALID, FRESH_UNFINISHED_ONLY}:
            label = FRESH_PROVIDER_ERROR
            reason = error
    return SymbolSnapshot(
        symbol=symbol,
        source=source,
        source_label=source_label,
        session_date=bar_session,
        expected_session=expected_session,
        completed=completed,
        latest_bar_ts=latest_ts,
        latest_close_vnd=int(latest["close"]) if latest else None,
        freshness_label=label,
        freshness_reason=reason,
        is_usable=usable,
        error=error,
    )


def fetch_symbol_snapshot(
    symbol: str,
    now: datetime,
    *,
    provider: Any | None = None,
    injected_records: list[dict[str, Any]] | None = None,
    expected_session: date | None = None,
) -> SymbolSnapshot:
    now = as_vn(now)
    session = expected_session or expected_session_date(now)
    symbol = str(symbol).strip().upper()

    if injected_records is not None:
        return _snapshot_from_records(
            symbol,
            injected_records,
            now=now,
            expected_session=session,
            source=SOURCE_INJECTED,
            source_label=SOURCE_LABEL_INJECTED,
        )

    if provider is None:
        try:
            from modules.intraday_memory.provider import KBSProvider

            provider = KBSProvider()
        except Exception as exc:
            return SymbolSnapshot(
                symbol=symbol,
                source=SOURCE_UNAVAILABLE,
                source_label="KBS/vnstock4 unavailable — no daily/Yahoo substitute",
                session_date=None,
                expected_session=session,
                freshness_label=FRESH_PROVIDER_ERROR,
                freshness_reason=f"{type(exc).__name__}: {exc}",
                is_usable=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    try:
        records = provider.fetch_session(symbol, session)
    except Exception as exc:
        return SymbolSnapshot(
            symbol=symbol,
            source=SOURCE_KBS,
            source_label=SOURCE_LABEL_KBS,
            session_date=None,
            expected_session=session,
            freshness_label=FRESH_PROVIDER_ERROR,
            freshness_reason=f"KBS fetch failed: {type(exc).__name__}: {exc}",
            is_usable=False,
            error=f"{type(exc).__name__}: {exc}",
        )

    return _snapshot_from_records(
        symbol,
        list(records or []),
        now=now,
        expected_session=session,
        source=SOURCE_KBS,
        source_label=SOURCE_LABEL_KBS,
    )


def fetch_snapshots(
    symbols: Iterable[str],
    now: datetime,
    *,
    provider: Any | None = None,
    injected: dict[str, list[dict[str, Any]]] | None = None,
    expected_session: date | None = None,
) -> dict[str, SymbolSnapshot]:
    out: dict[str, SymbolSnapshot] = {}
    for symbol in symbols:
        key = str(symbol).strip().upper()
        recs = None if injected is None else injected.get(key, [])
        out[key] = fetch_symbol_snapshot(
            key,
            now,
            provider=provider,
            injected_records=recs if injected is not None else None,
            expected_session=expected_session,
        )
    return out
