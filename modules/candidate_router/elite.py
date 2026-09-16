"""BUY ELITE → NominatedCandidate adapter.

Wraps the existing research watchlist builder so Slice 1 output stays
semantically equivalent to the Elite-only watchlist. Does not stamp
first_seen, does not read CSV mtime, and does not change Elite conclusions.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from modules.candidate_router.contract import SRC_BUY_ELITE, NominatedCandidate
from modules.live_candidate.watchlist import build_research_watchlist


def nominations_from_buy_elite_history(
    history: pd.DataFrame | None,
    *,
    now: datetime,
) -> tuple[NominatedCandidate, ...]:
    """Map legally visible Elite episodes. History is read-only."""
    wl = build_research_watchlist(history, now=now)
    if wl is None or wl.empty:
        return ()
    out: list[NominatedCandidate] = []
    for row in wl.to_dict(orient="records"):
        symbol = str(row.get("symbol") or "").strip().upper()
        reason = str(row.get("candidate_reason") or "")
        status = str(row.get("status") or "")
        source = str(row.get("source") or SRC_BUY_ELITE)
        out.append(
            NominatedCandidate(
                symbol=symbol,
                source=source,
                candidate_first_seen_ts=str(row.get("candidate_first_seen_ts") or ""),
                candidate_updated_ts=str(row.get("candidate_updated_ts") or ""),
                eligible_from=str(row.get("eligible_from") or ""),
                session=str(row.get("session") or ""),
                status=status,
                candidate_reason=reason,
                source_state=status,
                source_action="",
                source_reason=reason,
            )
        )
    return tuple(out)
