"""Read-only historical BOT Candidate reconstruction.

Source (Slice 1, exclusive):
  buy_elite_learning_history.csv

Kept conclusions (actionable decision-engine outputs only):
  BUY ELITE
  MUA NHỎ / ƯU TIÊN

Excluded (not treated as Candidates — would silently become a scanner):
  WATCHLIST
  WATCHLIST - MARKET YẾU
  CHƯA ĐỦ ĐỒNG THUẬN
  pattern_history.csv groups (MUA EARLY / PULL …) — these are scan labels,
  not Candidate events.

Limitations:
  - One row per (symbol, date); last file order wins.
  - `conclusion` / `group` / scores are pass-through context only.
  - Dates with no Camera session are skipped later (not invented).
  - If the CSV is missing, the event list is empty — no synthetic Candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from modules.intraday_pxv_v1.constants import ACTIONABLE_CONCLUSIONS
from modules.intraday_pxv_v1.paths import elite_history_path

CANDIDATE_SOURCE = "buy_elite_learning_history.csv"
CANDIDATE_FILTER = "conclusion in {BUY ELITE, MUA NHỎ / ƯU TIÊN}"


@dataclass(frozen=True)
class CandidateEvent:
    symbol: str
    session: date
    candidate_reason: str
    candidate_ts: str
    bot_context: str
    source: str = CANDIDATE_SOURCE


def load_candidate_events(
    path: Path | None = None,
    *,
    sessions: Iterable[date] | None = None,
) -> list[CandidateEvent]:
    src = path or elite_history_path()
    if not src.exists():
        return []

    df = pd.read_csv(src, low_memory=False)
    if df.empty or "symbol" not in df.columns or "date" not in df.columns:
        return []
    if "conclusion" not in df.columns:
        return []

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "symbol"])
    df["symbol"] = df["symbol"].astype(str).str.upper()
    df["conclusion"] = df["conclusion"].astype(str)
    df = df[df["conclusion"].isin(ACTIONABLE_CONCLUSIONS)]
    if sessions is not None:
        allowed = {d.isoformat() for d in sessions}
        df = df[df["date"].dt.strftime("%Y-%m-%d").isin(allowed)]
    df = df.sort_values(["date", "symbol"])
    df = df.drop_duplicates(["symbol", "date"], keep="last")

    events: list[CandidateEvent] = []
    for _, row in df.iterrows():
        sess = row["date"].date() if hasattr(row["date"], "date") else date.fromisoformat(str(row["date"])[:10])
        reason = str(row.get("conclusion", "")).strip()
        ts = str(row.get("time", "") or "")
        group = str(row.get("group", "") or "")
        events.append(
            CandidateEvent(
                symbol=str(row["symbol"]),
                session=sess,
                candidate_reason=reason,
                candidate_ts=f"{sess.isoformat()} {ts}".strip(),
                bot_context=group,
            )
        )
    return events


def thesis_is_long(reason: str) -> bool:
    """BUY ELITE / MUA NHỎ are long-biased decision outputs."""
    return str(reason) in ACTIONABLE_CONCLUSIONS
