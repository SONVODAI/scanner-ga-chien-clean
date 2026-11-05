"""Fail-closed VN exchange-session calendar for Research Ledger Stage B1.

Accepts only an explicitly verified session-date index with provenance.
Does not infer holidays from missing symbol prices or weekday arithmetic.
Does not download or fabricate calendars.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class SessionCalendarError(ValueError):
    """Calendar missing, unverified, or insufficient for the requested offset."""


def _text(value: object) -> str:
    return str(value or "").strip()


def _parse_day(value: object) -> date | None:
    text = _text(value)
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _normalize_sessions(raw: Iterable[object]) -> tuple[date, ...]:
    days: list[date] = []
    seen: set[date] = set()
    for item in raw:
        day = item if isinstance(item, date) else _parse_day(item)
        if day is None or day in seen:
            continue
        seen.add(day)
        days.append(day)
    days.sort()
    return tuple(days)


@dataclass(frozen=True)
class VerifiedSessionCalendar:
    """Explicitly verified exchange sessions. Fail closed when coverage is short."""

    sessions: tuple[date, ...]
    source: str
    provenance: str
    verified_through: date
    schema: str = "v2_research_session_calendar.v1"

    def __post_init__(self) -> None:
        if not _text(self.source) or not _text(self.provenance):
            raise SessionCalendarError("verified calendar requires source and provenance")
        if not self.sessions:
            raise SessionCalendarError("verified calendar requires at least one session date")
        if self.sessions != tuple(sorted(set(self.sessions))):
            raise SessionCalendarError("sessions must be unique and sorted ascending")
        # verified_through must not claim coverage past the last listed session
        if self.verified_through > self.sessions[-1]:
            raise SessionCalendarError(
                "verified_through cannot exceed the last listed exchange session"
            )

    @property
    def first_session(self) -> date:
        return self.sessions[0]

    @property
    def last_session(self) -> date:
        return self.sessions[-1]

    def metadata(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source": self.source,
            "provenance": self.provenance,
            "verified_through": self.verified_through.isoformat(),
            "first_session": self.first_session.isoformat(),
            "last_session": self.last_session.isoformat(),
            "n_sessions": len(self.sessions),
        }

    def contains(self, day: date | str) -> bool:
        parsed = day if isinstance(day, date) else _parse_day(day)
        return parsed in self.sessions if parsed is not None else False

    def covers_through(self, day: date | str) -> bool:
        parsed = day if isinstance(day, date) else _parse_day(day)
        if parsed is None:
            return False
        return self.last_session >= parsed and self.verified_through >= parsed

    def index_of(self, day: date | str) -> int | None:
        parsed = day if isinstance(day, date) else _parse_day(day)
        if parsed is None:
            return None
        try:
            return self.sessions.index(parsed)
        except ValueError:
            return None

    def offset(self, origin: date | str, n: int) -> date | None:
        """Return the exchange session ``n`` sessions after ``origin``.

        ``n=0`` is ``origin`` when present. Negative offsets are rejected.
        Returns ``None`` when origin is absent or coverage does not reach T+n
        (never invents a weekday or holiday).
        """
        if int(n) < 0:
            raise SessionCalendarError("session offset must be non-negative")
        idx = self.index_of(origin)
        if idx is None:
            return None
        target_idx = idx + int(n)
        if target_idx >= len(self.sessions):
            return None
        target = self.sessions[target_idx]
        if not self.covers_through(target):
            return None
        return target


def build_verified_session_calendar(
    sessions: Sequence[object],
    *,
    source: str,
    provenance: str,
    verified_through: date | str,
) -> VerifiedSessionCalendar:
    """Construct a fail-closed calendar from an explicit verified index."""
    through = (
        verified_through
        if isinstance(verified_through, date)
        else _parse_day(verified_through)
    )
    if through is None:
        raise SessionCalendarError("verified_through must be a date")
    normalized = _normalize_sessions(sessions)
    return VerifiedSessionCalendar(
        sessions=normalized,
        source=_text(source),
        provenance=_text(provenance),
        verified_through=through,
    )


def load_verified_session_calendar(path: Path) -> VerifiedSessionCalendar:
    """Load a verified calendar document. Refuses incomplete / unmarked files."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise SessionCalendarError("calendar document must be a JSON object")
    schema = _text(raw.get("schema"))
    if schema and schema != "v2_research_session_calendar.v1":
        raise SessionCalendarError(f"unsupported calendar schema {schema}")
    verified = raw.get("verified")
    if verified is not True:
        raise SessionCalendarError("calendar document must set verified=true")
    source = _text(raw.get("source"))
    provenance = _text(raw.get("provenance"))
    sessions = raw.get("sessions")
    if not isinstance(sessions, list):
        raise SessionCalendarError("calendar document requires sessions list")
    through = raw.get("verified_through") or (sessions[-1] if sessions else None)
    return build_verified_session_calendar(
        sessions,
        source=source,
        provenance=provenance,
        verified_through=through,
    )
