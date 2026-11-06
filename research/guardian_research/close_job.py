"""Guardian-only close. This does not finalize the Research Ledger.

Sealing stays off unless ``GUARDIAN_RESEARCH_SNAPSHOT_ENABLED`` is true.
The ledger finalizer and its authority gate are separate and are not called.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from research.guardian_research.collector import ENABLE_ENV
from research.guardian_research.indicators import finite_number

INPUTS = ("price", "ema9", "ma20", "obv", "obv_ema9")


def run_guardian_close(
    *,
    now: datetime | None = None,
    root: Path | None = None,
    close_scan=None,
    symbols: tuple[str, ...] | None = None,
) -> dict:
    """Seal today's close scan. A disabled flag does not scan or write."""
    if os.environ.get(ENABLE_ENV) != "true":
        return _public("disabled", "ENABLE_FLAG_OFF")
    from modules.intraday_execution_boundary import VN_TZ, as_vn

    local_now = as_vn(now or datetime.now(VN_TZ))
    if close_scan is None:
        from modules.close_session_scan import build_close_scan_inputs

        payload = build_close_scan_inputs(now=local_now, retain_research=False)
    else:
        payload = close_scan()
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        reason = "CLOSE_SCAN_NOT_READY"
        if isinstance(payload, dict) and payload.get("status"):
            reason = str(payload.get("status"))
        return _public("refused", reason, error=_error_text(payload))
    from research.guardian_research.universe import load_tracked_symbols

    tracked = tuple(symbols) if symbols is not None else load_tracked_symbols()
    blocker = _input_blocker(payload, tracked)
    if blocker:
        return _public("refused", blocker)
    from research.guardian_research.panel import default_root
    from research.guardian_research.pipeline import capture_from_close_payload

    result = capture_from_close_payload(
        payload,
        now=local_now,
        root=Path(root) if root is not None else default_root(),
        symbols=tracked,
    )
    document = result.get("document") if isinstance(result.get("document"), dict) else {}
    return _public(
        str(result.get("status") or "refused"),
        str(result.get("reason") or ""),
        path=result.get("path"),
        remote=result.get("remote"),
        session=document.get("session") or payload.get("trade_date"),
        tracked_count=document.get("tracked_count"),
        content_sha256=document.get("content_sha256"),
        counts=document.get("counts"),
    )


def _input_blocker(payload: dict, tracked: tuple[str, ...]) -> str | None:
    """Refuse a scan that is not one complete post-close session."""
    if payload.get("source") != "close_scan":
        return "CLOSE_SCAN_NOT_READY"
    if "observed_at" not in payload:
        return "OBSERVATION_TIMESTAMP_NOT_INDEPENDENT"
    coverage = payload.get("scan_coverage")
    if not isinstance(coverage, dict):
        return "SCAN_COVERAGE_ABSENT"
    requested = [str(symbol).strip().upper() for symbol in coverage.get("requested") or []]
    if len(requested) != len(set(requested)) or set(requested) != set(tracked):
        return "UNIVERSE_INCOMPLETE"
    errors = [str(symbol).strip().upper() for symbol in coverage.get("errors") or [] if str(symbol).strip()]
    absent = [str(symbol).strip().upper() for symbol in coverage.get("absent") or [] if str(symbol).strip()]
    if errors or absent:
        return "PARTIAL_SCAN"
    frame = payload.get("scan_df")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return "SCAN_ABSENT"
    session = str(payload.get("trade_date") or "")
    seen: dict[str, object] = {}
    for _, item in frame.iterrows():
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol:
            seen[symbol] = item
    if any(symbol not in seen for symbol in tracked):
        return "PARTIAL_SCAN"
    for symbol in tracked:
        item = seen[symbol]
        if _session_text(item.get("date")) != session:
            return "STALE_MARKET_DATA"
        if any(finite_number(item.get(column)) is None for column in INPUTS):
            return "INCOMPLETE_INPUT"
    if finite_number(payload.get("market_real")) is None:
        return "MARKET_CONTEXT_ABSENT"
    return None


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


def _error_text(payload) -> str | None:
    if not isinstance(payload, dict) or not payload.get("error"):
        return None
    return str(payload.get("error"))


def _public(status: str, reason: str, **extra) -> dict:
    result = {"status": status, "reason": reason, "path": None}
    for key, value in extra.items():
        if value is not None:
            result[key] = value
    if result.get("path") is not None:
        result["path"] = str(result["path"])
    return result


def main(argv: list[str] | None = None) -> int:
    """Explicit command. The ledger finalizer is not registered here."""
    del argv
    result = run_guardian_close()
    print(json.dumps(result, ensure_ascii=False, default=str))
    if result.get("status") in {"disabled", "created", "unchanged"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
