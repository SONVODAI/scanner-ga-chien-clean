"""Intraday Guardian labels for the tracked universe.

Uses the same scan-row lookup and ``generate_signal`` call as
``position_guardian.build_position_table``. Writes nothing and does not
read a sealed T0 snapshot.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from position_guardian import _scan_rows_by_symbol, generate_signal
from research.guardian_research.classify import classification_version
from research.guardian_research.contract import CLASS_UNAVAILABLE, PRODUCTION_TO_RESEARCH
from research.guardian_research.indicators import finite_number
from research.guardian_research.universe import load_tracked_symbols

LIVE_SCHEMA = "guardian_research_live.v1"
_FIELDS = ("price", "ema9", "ma20", "obv", "obv_ema9")


def evaluate_live(scan_df, *, symbols: tuple[str, ...] | None = None, evaluated_at=None) -> dict:
    """Classify the current scan. The returned document is not a T0 snapshot."""
    tracked = tuple(symbols) if symbols is not None else load_tracked_symbols()
    found = _scan_rows_by_symbol(scan_df)
    dates = [_session_text(item.get("date")) for item in found.values()]
    dated = {value for value in dates if value}
    scan_session = next(iter(dated)) if len(dated) == 1 else None
    mixed = len(dated) > 1
    rows = [
        _one(symbol, found.get(symbol), scan_session=scan_session, mixed=mixed)
        for symbol in tracked
    ]
    return {
        "schema": LIVE_SCHEMA,
        "portfolio_decision": False,
        "classification_version": classification_version(),
        "scan_session": scan_session,
        "mixed_session": mixed,
        "evaluated_at": _clock(evaluated_at),
        "tracked_count": len(tracked),
        "fresh_count": sum(row["freshness"] == "FRESH" for row in rows),
        "stale_count": sum(row["freshness"] == "STALE" for row in rows),
        "undated_count": sum(row["freshness"] == "UNDATED" for row in rows),
        "incomplete_count": sum(row["freshness"] == "INCOMPLETE" for row in rows),
        "missing_count": sum(row["freshness"] == "MISSING" for row in rows),
        "live_adjusted_count": sum(row["live_adjusted"] is True for row in rows),
        "quoted_count": sum(bool(row.get("quote_observed_at")) for row in rows),
        "rows": rows,
    }


def live_board(document: dict) -> pd.DataFrame:
    """Display frame. HOLD, WATCH, SELL, then marked rows."""
    order = {"HOLD": 0, "WATCH": 1, "SELL": 2, "UNAVAILABLE": 3}
    records = []
    for row in document.get("rows") or []:
        inputs = row.get("inputs") or {}
        records.append(
            {
                "Classification": row.get("classification"),
                "Symbol": row.get("symbol"),
                "Price": inputs.get("price") if isinstance(inputs, dict) else None,
                "Score": row.get("score"),
                "Freshness": row.get("freshness"),
                "Live": "YES" if row.get("live_adjusted") is True else "",
                "Quote": row.get("quote_observed_at") or "",
                "Reason": row.get("reason"),
                "Input session": row.get("input_session"),
            }
        )
    frame = pd.DataFrame(
        records,
        columns=[
            "Classification",
            "Symbol",
            "Price",
            "Score",
            "Freshness",
            "Live",
            "Quote",
            "Reason",
            "Input session",
        ],
    )
    if frame.empty:
        return frame
    frame["_class"] = frame["Classification"].map(lambda value: order.get(value, len(order)))
    frame["_src"] = range(len(frame))
    return frame.sort_values(["_class", "_src"], kind="stable").drop(columns=["_class", "_src"]).reset_index(drop=True)


def _one(symbol: str, item, *, scan_session: str | None, mixed: bool) -> dict:
    if item is None:
        return _marked(symbol, "MISSING", "SYMBOL_ABSENT", None)
    values = {name: finite_number(item.get(name)) for name in _FIELDS}
    input_session = _session_text(item.get("date"))
    live_adjusted = _live_flag(item)
    quote = _quote_time(item) if live_adjusted else None
    # Same row Position Guardian passes in. Do not rebuild the inputs.
    signal, reason, score = generate_signal(item)
    research = PRODUCTION_TO_RESEARCH.get(signal)
    freshness = _freshness(input_session, scan_session, mixed)
    if research is None:
        return _marked(symbol, freshness, "UNMAPPED_PRODUCTION_SIGNAL", input_session, values)
    return {
        "symbol": symbol,
        "classification": research,
        "production_signal": signal,
        "reason": reason,
        "score": int(score),
        "freshness": freshness,
        "input_session": input_session,
        "inputs": values,
        "live_adjusted": live_adjusted,
        "quote_observed_at": quote,
        "portfolio_decision": False,
    }


def _marked(symbol: str, freshness: str, reason: str, input_session, values=None) -> dict:
    return {
        "symbol": symbol,
        "classification": CLASS_UNAVAILABLE,
        "production_signal": None,
        "reason": reason,
        "score": None,
        "freshness": freshness,
        "input_session": input_session,
        "inputs": values,
        "live_adjusted": False,
        "quote_observed_at": None,
        "portfolio_decision": False,
    }


def _live_flag(item) -> bool:
    index = getattr(item, "index", None)
    if index is None or "is_live_adjusted" not in index:
        return False
    value = item["is_live_adjusted"]
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _quote_time(item) -> str | None:
    """Return the scan's own live quote timestamp. Never invent one."""
    index = getattr(item, "index", None)
    if index is None or "live_ts" not in index:
        return None
    value = item["live_ts"]
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nat", "none", "nan"}:
        return None
    return text


def _freshness(input_session: str | None, scan_session: str | None, mixed: bool) -> str:
    if mixed or (input_session and scan_session and input_session != scan_session):
        return "STALE"
    if input_session is None:
        return "UNDATED"
    return "FRESH"


def _session_text(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return str(value.isoformat())[:10]
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def _clock(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
