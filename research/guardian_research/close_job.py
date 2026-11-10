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
from research.guardian_research.session_authority import (
    WITNESS_SOURCE,
    assess_seal_window,
    probe_vnindex,
)

INPUTS = ("price", "ema9", "ma20", "obv", "obv_ema9")


def run_guardian_close(
    *,
    now: datetime | None = None,
    root: Path | None = None,
    close_scan=None,
    symbols: tuple[str, ...] | None = None,
    witness: dict | None = None,
) -> dict:
    """Seal the VNINDEX bar session. The job clock does not name that session."""
    if os.environ.get(ENABLE_ENV) != "true":
        return _public("disabled", "ENABLE_FLAG_OFF")
    from modules.intraday_execution_boundary import VN_TZ, as_vn
    from research.guardian_research.panel import default_root

    local_now = as_vn(now or datetime.now(VN_TZ))
    root_path = Path(root) if root is not None else default_root()
    # Probe + window + existing-seal check happen before any watchlist scan so
    # same-evening backup slots do not rescan or rewrite an immutable T0.
    search_end = local_now.strftime("%Y-%m-%d")
    accepted, witness_error = _accept_bar(witness if witness is not None else probe_vnindex(search_end))
    if witness_error:
        return _public("refused", witness_error)
    session = accepted["bar_session"]
    window_ok, window_reason = assess_seal_window(local_now, session)
    if not window_ok:
        return _public("refused", window_reason, session=session)
    existing = _existing_seal_without_scan(root_path, session)
    if existing is not None:
        return existing
    if close_scan is None:
        from modules.close_session_scan import build_close_scan_inputs

        payload = build_close_scan_inputs(now=local_now, retain_research=False)
    else:
        payload = close_scan()
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        reason = "CLOSE_SCAN_NOT_READY"
        if isinstance(payload, dict) and payload.get("status"):
            reason = str(payload.get("status"))
        return _public("refused", reason, error=_error_text(payload), session=session)
    payload = dict(payload)
    # Bar session names the seal. Clock-day trading_today may already be false
    # after ICT midnight; the accepted VNINDEX bar is the trading-day witness.
    payload["trade_date"] = session
    payload["session_witness"] = accepted
    from research.guardian_research.universe import load_tracked_symbols

    tracked = tuple(symbols) if symbols is not None else load_tracked_symbols()
    blocker = _input_blocker(payload, tracked)
    if blocker:
        return _public("refused", blocker, session=session)
    from research.guardian_research.pipeline import capture_from_close_payload

    result = capture_from_close_payload(
        payload,
        now=local_now,
        root=root_path,
        symbols=tracked,
    )
    document = result.get("document") if isinstance(result.get("document"), dict) else {}
    return _public(
        str(result.get("status") or "refused"),
        str(result.get("reason") or ""),
        path=result.get("path"),
        remote=result.get("remote"),
        session=document.get("session") or session,
        tracked_count=document.get("tracked_count"),
        content_sha256=document.get("content_sha256"),
        counts=document.get("counts"),
    )


def _existing_seal_without_scan(root: Path, session: str) -> dict | None:
    """Return an unchanged public result when a sealed T0 already exists.

    Backup schedules must not rescan or rewrite. Remote is preferred; a local
    sealed file is also treated as immutable and may only be re-published.
    """
    from research.guardian_research.pipeline import publish_snapshot, read_remote_snapshot
    from research.guardian_research.snapshot import read_snapshot

    remote, remote_state = read_remote_snapshot(root, session)
    if remote_state == "unverified":
        return _public("refused", "REMOTE_UNVERIFIED", session=session)
    local_path = Path(root) / "sessions" / f"{session}.json"
    local_document = None
    if local_path.exists():
        try:
            local_document = read_snapshot(local_path)
        except (OSError, ValueError, json.JSONDecodeError):
            local_document = None
    document = None
    if remote_state == "present" and isinstance(remote, dict) and remote.get("session") == session:
        document = remote
        remote_result = "unchanged"
    elif isinstance(local_document, dict) and local_document.get("session") == session:
        document = local_document
        if remote_state == "absent":
            remote_result = publish_snapshot(root, session)
        else:
            remote_result = "disabled"
    else:
        return None
    path = local_path if local_path.exists() else None
    return _public(
        "unchanged",
        "ok",
        path=path,
        remote=remote_result,
        session=session,
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
    sessions = []
    for symbol in tracked:
        item = seen[symbol]
        if any(finite_number(item.get(column)) is None for column in INPUTS):
            return "INCOMPLETE_INPUT"
        sessions.append(_session_text(item.get("date")))
    if len(set(sessions)) != 1:
        return "MIXED_SESSION"
    if sessions[0] != session:
        return "STALE_MARKET_DATA"
    if finite_number(payload.get("market_real")) is None:
        return "MARKET_CONTEXT_ABSENT"
    return None


def _accept_bar(witness) -> tuple[dict | None, str | None]:
    """Accept the downloaded VNINDEX bar date. A clock label is not a session."""
    if not isinstance(witness, dict) or witness.get("source") != WITNESS_SOURCE:
        return None, "SESSION_EVIDENCE_ABSENT"
    if witness.get("probe_error") == "ADAPTER_UNAVAILABLE":
        return None, "WITNESS_ADAPTER_UNAVAILABLE"
    if witness.get("probe_error"):
        return None, "SESSION_EVIDENCE_ABSENT"
    bar = str(witness.get("bar_session") or "")
    try:
        datetime.strptime(bar, "%Y-%m-%d")
    except ValueError:
        return None, "SESSION_EVIDENCE_ABSENT"
    return {
        "source": WITNESS_SOURCE,
        "bar_session": bar,
        "probe_error": None,
        "provenance": "research.guardian_research.session_authority.probe_vnindex",
    }, None


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
    try:
        from research.guardian_research.outcomes import refresh_outcomes

        result["outcomes"] = refresh_outcomes()
    except Exception as exc:
        result["outcomes"] = {"status": "skipped", "reason": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, default=str))
    if result.get("status") in {"disabled", "created", "unchanged"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
