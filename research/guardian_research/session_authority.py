"""Trading-session witness for Guardian Research.

A weekday clock is not enough. The witness is the latest VNINDEX daily bar
date, using the same comparison as ``app.is_vnindex_trading_today``. This
module does not import ``app`` and does not download the stock watchlist.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

WITNESS_SOURCE = "vnindex_daily_bar"
CANONICAL_CLOSE = time(18, 0)


def assess_session(now: datetime, session: str, witness: dict | None) -> tuple[bool, str]:
    """Accept one session only when the clock and the index bar agree."""
    from modules.intraday_execution_boundary import as_vn

    local = as_vn(now)
    if local.weekday() >= 5:
        return False, "WEEKEND"
    try:
        date.fromisoformat(session)
    except ValueError:
        return False, "SESSION_DATE_INVALID"
    if local.strftime("%Y-%m-%d") != session:
        return False, "CLOCK_SESSION_MISMATCH"
    if local.timetz().replace(tzinfo=None) < CANONICAL_CLOSE:
        return False, "BEFORE_CANONICAL_WINDOW"
    if not isinstance(witness, dict) or witness.get("source") != WITNESS_SOURCE:
        return False, "SESSION_EVIDENCE_ABSENT"
    if witness.get("probe_error") == "ADAPTER_UNAVAILABLE":
        return False, "WITNESS_ADAPTER_UNAVAILABLE"
    if witness.get("probe_error"):
        return False, "SESSION_EVIDENCE_ABSENT"
    bar_session = str(witness.get("bar_session") or "")
    if not bar_session:
        return False, "SESSION_EVIDENCE_ABSENT"
    if bar_session != session:
        return False, "NON_TRADING_SESSION"
    return True, "ok"


def probe_vnindex(session: str) -> dict:
    """Return the latest VNINDEX daily bar date. No prices are kept."""
    witness = {"source": WITNESS_SOURCE, "bar_session": "", "probe_error": None}
    try:
        date.fromisoformat(session)
    except ValueError:
        witness["probe_error"] = "SESSION_DATE_INVALID"
        return witness
    try:
        from vnstock import stock_historical_data
    except ImportError:
        # Missing verified daily adapter. This is not a confirmed non-trading day.
        witness["probe_error"] = "ADAPTER_UNAVAILABLE"
        return witness
    except Exception as exc:
        witness["probe_error"] = type(exc).__name__
        return witness
    start = (date.fromisoformat(session) - timedelta(days=10)).isoformat()
    last_seen = ""
    saw_frame = False
    for bar_type in ("index", "stock"):
        try:
            frame = stock_historical_data(
                symbol="VNINDEX",
                start_date=start,
                end_date=session,
                resolution="1D",
                type=bar_type,
                beautify=True,
            )
        except Exception:
            continue
        if frame is None or getattr(frame, "empty", True):
            continue
        column = next(
            (name for name in frame.columns if "date" in str(name).lower() or "time" in str(name).lower()),
            None,
        )
        if column is None:
            continue
        import pandas as pd

        dated = frame.copy()
        dated[column] = pd.to_datetime(dated[column], errors="coerce")
        dated = dated.dropna(subset=[column]).sort_values(column)
        if dated.empty:
            continue
        saw_frame = True
        last_seen = dated[column].iloc[-1].strftime("%Y-%m-%d")
        if last_seen == session:
            break
    if not last_seen:
        witness["probe_error"] = "NO_BAR" if not saw_frame else "BAR_DATE_ABSENT"
        return witness
    witness["bar_session"] = last_seen
    return witness
