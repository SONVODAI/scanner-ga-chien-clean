"""Candidate episode semantics. Does not change Elite scores or conclusions.

Episode key: (session_date, symbol).

- actionable → actionable (same session): keep first_seen, update updated_ts
- actionable → non-actionable (same session): keep first_seen, status HELD
- non-actionable → actionable (same session, no first_seen yet): stamp now
- non-actionable → actionable (same session, first_seen already set): keep it
- same symbol next session: new episode, new first_seen

Never invent or backfill first_seen for historical rows that lack it.
Never use session open, bar time, or EOD as a synthetic first_seen.
"""

from __future__ import annotations

ACTIONABLE_CONCLUSIONS = frozenset(
    {
        "BUY ELITE",
        "MUA NHỎ / ƯU TIÊN",
    }
)

FIRST_SEEN_COL = "candidate_first_seen_ts"
UPDATED_COL = "candidate_updated_ts"
SOURCE = "buy_elite_learning_history"

STATUS_ACTIVE = "ACTIVE"
STATUS_HELD = "HELD"


def is_actionable(conclusion: object) -> bool:
    return str(conclusion or "").strip() in ACTIONABLE_CONCLUSIONS


def has_legal_first_seen(value: object) -> bool:
    s = str(value or "").strip()
    return bool(s) and s.lower() not in {"nan", "none", "nat"}
