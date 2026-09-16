"""BUY ELITE → NominatedCandidate adapter.

Wraps the existing research watchlist builder so Slice 1 output stays
semantically equivalent to the Elite-only watchlist. Does not stamp
first_seen, does not read CSV mtime, and does not change Elite conclusions.

`group` / `setup` are copied from the Elite history row for the same episode.
They are never derived from candidate_reason / KẾT LUẬN.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from modules.candidate_router.contract import SRC_BUY_ELITE, NominatedCandidate, pass_through_meta
from modules.live_candidate.contract import FIRST_SEEN_COL
from modules.live_candidate.persist import _norm_date, _norm_symbol
from modules.live_candidate.watchlist import build_research_watchlist


def _history_meta_indexes(
    history: pd.DataFrame | None,
) -> tuple[dict[tuple[str, str, str], tuple[str, str]], dict[tuple[str, str], tuple[str, str]]]:
    """(symbol, session, first_seen) and (symbol, session) → (group, setup)."""
    exact: dict[tuple[str, str, str], tuple[str, str]] = {}
    episode: dict[tuple[str, str], tuple[str, str]] = {}
    if history is None or history.empty or "symbol" not in history.columns:
        return exact, episode
    has_group = "group" in history.columns or "NHÓM" in history.columns
    has_setup = "setup" in history.columns
    has_date = "date" in history.columns
    has_fs = FIRST_SEEN_COL in history.columns
    for _, row in history.iterrows():
        symbol = _norm_symbol(row.get("symbol"))
        session = _norm_date(row.get("date")) if has_date else ""
        if not symbol or not session:
            continue
        group = ""
        if has_group:
            group = pass_through_meta(row.get("group"))
            if not group:
                group = pass_through_meta(row.get("NHÓM"))
        setup = pass_through_meta(row.get("setup")) if has_setup else ""
        first = pass_through_meta(row.get(FIRST_SEEN_COL)) if has_fs else ""
        episode[(symbol, session)] = (group, setup)
        exact[(symbol, session, first)] = (group, setup)
    return exact, episode


def _lookup_meta(
    exact: dict[tuple[str, str, str], tuple[str, str]],
    episode: dict[tuple[str, str], tuple[str, str]],
    *,
    symbol: str,
    session: str,
    first_seen: str,
) -> tuple[str, str]:
    hit = exact.get((symbol, session, first_seen))
    if hit is not None:
        return hit
    return episode.get((symbol, session), ("", ""))


def nominations_from_buy_elite_history(
    history: pd.DataFrame | None,
    *,
    now: datetime,
) -> tuple[NominatedCandidate, ...]:
    """Map legally visible Elite episodes. History is read-only."""
    wl = build_research_watchlist(history, now=now)
    if wl is None or wl.empty:
        return ()
    exact, episode = _history_meta_indexes(history)
    out: list[NominatedCandidate] = []
    for row in wl.to_dict(orient="records"):
        symbol = str(row.get("symbol") or "").strip().upper()
        reason = str(row.get("candidate_reason") or "")
        status = str(row.get("status") or "")
        source = str(row.get("source") or SRC_BUY_ELITE)
        session = str(row.get("session") or "")
        first_seen = str(row.get("candidate_first_seen_ts") or "")
        group, setup = _lookup_meta(
            exact,
            episode,
            symbol=symbol,
            session=session,
            first_seen=first_seen,
        )
        out.append(
            NominatedCandidate(
                symbol=symbol,
                source=source,
                candidate_first_seen_ts=first_seen,
                candidate_updated_ts=str(row.get("candidate_updated_ts") or ""),
                eligible_from=str(row.get("eligible_from") or ""),
                session=session,
                status=status,
                candidate_reason=reason,
                source_state=status,
                source_action="",
                source_reason=reason,
                group=group,
                setup=setup,
            )
        )
    return tuple(out)
