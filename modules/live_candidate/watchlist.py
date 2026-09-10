"""Research-only Dynamic Watchlist snapshot. Candidate state, not P×V state."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from modules.live_candidate.calendar import as_vn, cash_session_end, next_trading_session_open
from modules.live_candidate.contract import (
    FIRST_SEEN_COL,
    SOURCE,
    STATUS_ACTIVE,
    STATUS_HELD,
    UPDATED_COL,
    has_legal_first_seen,
    is_actionable,
)
from modules.live_candidate.persist import _norm_date, _norm_symbol

WATCHLIST_NAME = "dynamic_watchlist.json"
# Present empty document. Absence of this file is not a valid empty universe.
CANONICAL_EMPTY_JSON = "[]\n"


def output_root(base: Path | None = None) -> Path:
    env = os.getenv("MRBOT_LIVE_CANDIDATE_OUT", "").strip()
    if env:
        return Path(env)
    return (base or Path(__file__).resolve().parents[2]) / "data" / "live_candidate"


def _parse_ts(raw: object) -> pd.Timestamp | None:
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Ho_Chi_Minh")
    else:
        ts = ts.tz_convert("Asia/Ho_Chi_Minh")
    return ts


def episode_window(session: date, first_seen: datetime) -> tuple[datetime, datetime]:
    close = cash_session_end(session)
    if first_seen <= close:
        return first_seen, next_trading_session_open(session)
    nxt_open = next_trading_session_open(session)
    carry_end = next_trading_session_open(nxt_open.date())
    return nxt_open, carry_end


def build_research_watchlist(
    history: pd.DataFrame | None,
    *,
    now: datetime,
) -> pd.DataFrame:
    """Candidates legally available at `now`. Never before eligible_from."""
    cols = [
        "session",
        "symbol",
        "candidate_first_seen_ts",
        "candidate_updated_ts",
        "candidate_reason",
        "source",
        "status",
        "eligible_from",
    ]
    if history is None or history.empty or FIRST_SEEN_COL not in history.columns:
        return pd.DataFrame(columns=cols)

    now_ts = pd.Timestamp(as_vn(now))
    rows: list[dict] = []
    work = history.copy()
    work["symbol"] = work["symbol"].map(_norm_symbol)
    work["date"] = work["date"].map(_norm_date)

    for _, row in work.iterrows():
        if not has_legal_first_seen(row.get(FIRST_SEEN_COL)):
            continue
        first = _parse_ts(row.get(FIRST_SEEN_COL))
        if first is None:
            continue
        session = pd.Timestamp(row.get("date")).date()
        eligible_from, visible_until = episode_window(session, first.to_pydatetime())
        elig = pd.Timestamp(eligible_from)
        until = pd.Timestamp(visible_until)
        if now_ts < elig or now_ts >= until:
            continue
        rows.append(
            {
                "session": session.isoformat(),
                "symbol": _norm_symbol(row.get("symbol")),
                "candidate_first_seen_ts": str(row.get(FIRST_SEEN_COL)),
                "candidate_updated_ts": str(row.get(UPDATED_COL) or ""),
                "candidate_reason": str(row.get("conclusion") or ""),
                "source": SOURCE,
                "status": STATUS_ACTIVE if is_actionable(row.get("conclusion")) else STATUS_HELD,
                "eligible_from": eligible_from.isoformat(),
            }
        )

    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows)
    out = out.sort_values(["symbol", "candidate_first_seen_ts"])
    out = out.drop_duplicates(subset=["symbol"], keep="last")
    return out.reset_index(drop=True)


def persist_research_watchlist(
    history: pd.DataFrame | None,
    *,
    observed_at: datetime,
    out_dir: Path | None = None,
) -> Path:
    root = out_dir or output_root()
    root.mkdir(parents=True, exist_ok=True)
    wl = build_research_watchlist(history, now=observed_at)
    path = root / WATCHLIST_NAME
    path.write_text(encode_watchlist_text(wl), encoding="utf-8")
    return path


def encode_watchlist_text(watchlist: pd.DataFrame | None) -> str:
    """Canonical GitHub/local bytes. Zero rows → '[]', never a missing file."""
    if watchlist is None or watchlist.empty:
        return CANONICAL_EMPTY_JSON
    payload = json.loads(watchlist.to_json(orient="records", force_ascii=False))
    if not payload:
        return CANONICAL_EMPTY_JSON
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
