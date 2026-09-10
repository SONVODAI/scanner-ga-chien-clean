"""LIVE / STALE / STOPPED from observed_at age. Never rewrite clocks."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from modules.live_candidate.calendar import as_vn
from modules.live_shadow_transport.contract import (
    RUNNER_LIVE,
    RUNNER_STALE,
    RUNNER_STALE_AFTER_SEC,
    RUNNER_STOPPED,
)


def parse_observed_at(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return as_vn(value)
    try:
        import pandas as pd

        ts = pd.to_datetime(value, errors="coerce")
        if ts is None or pd.isna(ts):
            return None
        return as_vn(ts.to_pydatetime())
    except Exception:
        return None


def classify_freshness(
    observed_at: Any,
    now: datetime,
    *,
    stale_after_sec: int = RUNNER_STALE_AFTER_SEC,
) -> dict[str, Any]:
    now = as_vn(now)
    observed = parse_observed_at(observed_at)
    if observed is None:
        return {
            "label": RUNNER_STOPPED,
            "age_sec": None,
            "is_live": False,
            "is_stale": True,
        }
    age = (now - observed).total_seconds()
    if age > stale_after_sec:
        return {
            "label": RUNNER_STALE,
            "age_sec": age,
            "is_live": False,
            "is_stale": True,
        }
    return {
        "label": RUNNER_LIVE,
        "age_sec": age,
        "is_live": True,
        "is_stale": False,
    }
