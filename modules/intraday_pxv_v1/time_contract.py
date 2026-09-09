"""LIVE Candidate time contract.

A Candidate MUST NEVER be visible to Intraday P×V before it legally existed.

A) candidate_first_seen_ts — first moment BOT made that Candidate available.
   Immutable for the (symbol, session) episode. Never overwritten by a later save.
B) candidate_updated_ts — later re-evaluation / last write.
C) session_date — which cash session owns the episode.

Historical `buy_elite_learning_history.csv` `time` is a learning-cycle save clock
with last-wins. That is earliest_proven_ts only. It is NOT first_seen and MUST NOT
be used as proof the Candidate existed earlier.

Session rule:
  - first created after cash close (14:45 VN) → no same-day 5m interpretation.
    LIVE: eligible from next trading session open (do not invent D+1 historical rows).
  - first created during the owned session → interpret only asof >= gate_ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

import pandas as pd

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.constants import (
    PROVENANCE_FIRST_SEEN,
    PROVENANCE_MISSING,
    PROVENANCE_SAVE_CLOCK,
    SESSION_PM_END,
)


def cash_session_end(session: date) -> datetime:
    """Last regular cash 5m print (14:45 VN), inclusive."""
    return datetime.combine(session, time(*SESSION_PM_END), tzinfo=VN_TZ)


def _has_clock_component(raw: str) -> bool:
    s = str(raw or "").strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return False
    if "T" in s:
        return True
    parts = s.split()
    if len(parts) >= 2 and ":" in parts[1]:
        return True
    if s.count(":") >= 1 and not s[:10].replace("-", "").isdigit():
        return True
    # "2026-08-14" / "2026-08-14 00:00:00" invented midnight — reject date-only
    if len(parts) == 1 and len(s) <= 10:
        return False
    if len(parts) >= 2 and parts[1].startswith("00:00"):
        return False
    return ":" in s


def parse_legal_ts(raw: Any) -> datetime | None:
    """Parse a VN-local timestamp. Date-only / midnight-invented values are illegal."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    if not _has_clock_component(s):
        return None
    try:
        ts = pd.Timestamp(s)
    except Exception:
        return None
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize(VN_TZ)
    else:
        ts = ts.tz_convert(VN_TZ)
    if ts.hour == 0 and ts.minute == 0 and ts.second == 0 and "00:00" in s:
        return None
    return ts.to_pydatetime()


@dataclass(frozen=True)
class LegalExistence:
    session: date
    first_seen_ts: datetime | None
    updated_ts: datetime | None
    earliest_proven_ts: datetime | None
    gate_ts: datetime | None
    provenance: str
    same_day_intraday_eligible: bool
    next_session_open_eligible: bool

    @property
    def usable(self) -> bool:
        return self.gate_ts is not None and self.same_day_intraday_eligible


def resolve_legal_existence(candidate: Any) -> LegalExistence:
    """Resolve the legal existence clock. Prefer immutable first_seen. Never invent."""
    session = candidate.session
    first = parse_legal_ts(getattr(candidate, "candidate_first_seen_ts", "") or "")
    updated = parse_legal_ts(getattr(candidate, "candidate_updated_ts", "") or "")
    save_clock = parse_legal_ts(getattr(candidate, "candidate_ts", "") or "")

    if first is not None:
        gate = first
        provenance = PROVENANCE_FIRST_SEEN
        proven = first
    elif save_clock is not None:
        gate = save_clock
        provenance = PROVENANCE_SAVE_CLOCK
        proven = save_clock
        # Save clock is last-wins. Do not promote it to first_seen.
        first = None
    else:
        return LegalExistence(
            session=session,
            first_seen_ts=None,
            updated_ts=updated,
            earliest_proven_ts=None,
            gate_ts=None,
            provenance=PROVENANCE_MISSING,
            same_day_intraday_eligible=False,
            next_session_open_eligible=False,
        )

    close = cash_session_end(session)
    after_close = gate > close
    # This owned session's 5m bars are legal iff existence is at or before cash close.
    # A prior-day first_seen is legal for today's bars (LIVE next-open carry).
    same_day = not after_close
    next_open = after_close

    return LegalExistence(
        session=session,
        first_seen_ts=first if provenance == PROVENANCE_FIRST_SEEN else None,
        updated_ts=updated or save_clock,
        earliest_proven_ts=proven,
        gate_ts=gate,
        provenance=provenance,
        same_day_intraday_eligible=same_day,
        next_session_open_eligible=next_open,
    )


def asof_allowed(asof: datetime, legal: LegalExistence) -> bool:
    if not legal.usable or legal.gate_ts is None:
        return False
    ts = pd.Timestamp(asof)
    if ts.tzinfo is None:
        ts = ts.tz_localize(VN_TZ)
    else:
        ts = ts.tz_convert(VN_TZ)
    return ts >= pd.Timestamp(legal.gate_ts)
