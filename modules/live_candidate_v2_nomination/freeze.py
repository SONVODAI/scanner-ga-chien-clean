"""Immutable first_seen + frozen refs at Brain A NOMINATION, not BUY ELITE.

Episode key: (session, symbol).
Once stamped for the active episode, later rescans must not rewrite
candidate_first_seen_ts, price_at_first_seen, ema9_at_first_seen, or
breakout_ref_at_first_seen.

Do not backfill earlier timestamps from later rows.
Do not stamp first_seen for rows that are not legally nominated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

import pandas as pd

from modules.live_candidate.calendar import as_vn, cash_session_end, next_trading_session_open
from modules.live_candidate.contract import has_legal_first_seen
from modules.live_candidate.watchlist import episode_window
from modules.live_candidate_v2_nomination.contract import (
    CHRONOLOGY_ELIGIBLE,
    CHRONOLOGY_NOT_YET_ELIGIBLE,
    FreezeRecord,
)


def _num(value: object) -> float | None:
    n = pd.to_numeric(value, errors="coerce")
    if pd.isna(n):
        return None
    return float(n)


def session_of(row: Mapping[str, Any], observed_at: datetime) -> str:
    raw = row.get("session") or row.get("date") or row.get("session_date")
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        return as_vn(observed_at).date().isoformat()
    return ts.date().isoformat()


def episode_key(session: str, symbol: str) -> tuple[str, str]:
    return str(session), str(symbol).strip().upper()


def freeze_from_row(row: Mapping[str, Any]) -> tuple[float | None, float | None, float | None]:
    price = _num(row.get("price") if "price" in row else row.get("Giá"))
    ema9 = _num(row.get("ema9"))
    brk = _num(row.get("breakout_ref"))
    return price, ema9, brk


def ledger_map(records: list[FreezeRecord] | tuple[FreezeRecord, ...] | None) -> dict[tuple[str, str], FreezeRecord]:
    out: dict[tuple[str, str], FreezeRecord] = {}
    for rec in records or ():
        if not has_legal_first_seen(rec.candidate_first_seen_ts):
            continue
        out[episode_key(rec.session, rec.symbol)] = rec
    return out


def stamp_or_reuse(
    row: Mapping[str, Any],
    *,
    symbol: str,
    session: str,
    observed_at: datetime,
    prior: Mapping[tuple[str, str], FreezeRecord],
) -> FreezeRecord:
    key = episode_key(session, symbol)
    existing = prior.get(key)
    if existing is not None and has_legal_first_seen(existing.candidate_first_seen_ts):
        return existing
    now_iso = as_vn(observed_at).isoformat()
    price, ema9, brk = freeze_from_row(row)
    return FreezeRecord(
        session=session,
        symbol=symbol,
        candidate_first_seen_ts=now_iso,
        price_at_first_seen=price,
        ema9_at_first_seen=ema9,
        breakout_ref_at_first_seen=brk,
    )


def eligible_from_for(session: str, first_seen_iso: str) -> str:
    first = pd.to_datetime(first_seen_iso, errors="coerce")
    if pd.isna(first):
        return first_seen_iso
    if first.tzinfo is None:
        first = first.tz_localize("Asia/Ho_Chi_Minh")
    else:
        first = first.tz_convert("Asia/Ho_Chi_Minh")
    session_date = pd.Timestamp(session).date()
    eligible, _until = episode_window(session_date, first.to_pydatetime())
    return eligible.isoformat()


def chronology_status_for(eligible_from_iso: str, now: datetime) -> str:
    elig = pd.to_datetime(eligible_from_iso, errors="coerce")
    if pd.isna(elig):
        return CHRONOLOGY_NOT_YET_ELIGIBLE
    if elig.tzinfo is None:
        elig = elig.tz_localize("Asia/Ho_Chi_Minh")
    else:
        elig = elig.tz_convert("Asia/Ho_Chi_Minh")
    now_ts = pd.Timestamp(as_vn(now))
    if now_ts < elig:
        return CHRONOLOGY_NOT_YET_ELIGIBLE
    return CHRONOLOGY_ELIGIBLE


def cash_close_iso(session: str) -> str:
    return cash_session_end(pd.Timestamp(session).date()).isoformat()


def next_open_iso(session: str) -> str:
    return next_trading_session_open(pd.Timestamp(session).date()).isoformat()
