"""Dynamic Watchlist → live poll universe. No extra ranking."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import pandas as pd

from modules.live_candidate.calendar import as_vn
from modules.live_camera_shadow.rate import LIVE_UNIVERSE_CAP

__all__ = ["LIVE_UNIVERSE_CAP", "eligible_watchlist_symbols"]


def _parse(raw: object) -> pd.Timestamp | None:
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Ho_Chi_Minh")
    else:
        ts = ts.tz_convert("Asia/Ho_Chi_Minh")
    return ts


def eligible_watchlist_symbols(
    watchlist: Iterable[dict[str, Any]] | pd.DataFrame,
    *,
    now: datetime,
    cap: int = LIVE_UNIVERSE_CAP,
) -> list[dict[str, Any]]:
    """Symbols with now >= eligible_from. Stable order: eligible_from, symbol."""
    if isinstance(watchlist, pd.DataFrame):
        rows = watchlist.to_dict(orient="records") if not watchlist.empty else []
    else:
        rows = list(watchlist or [])
    now_ts = pd.Timestamp(as_vn(now))
    eligible: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        elig = _parse(row.get("eligible_from"))
        rec = dict(row)
        rec["symbol"] = str(rec.get("symbol") or "").strip().upper()
        if not rec["symbol"] or elig is None:
            continue
        if now_ts >= elig:
            eligible.append(rec)
        else:
            rec["_skip"] = "NOT_YET_ELIGIBLE"
            skipped.append(rec)
    eligible.sort(key=lambda r: (str(r.get("eligible_from") or ""), r["symbol"]))
    return eligible[: max(0, cap)] + skipped
