"""Guardian-only T0 collector.

This entrypoint does not call the post-close finalizer or any forward-ledger
writer. Sealing stays off unless GUARDIAN_RESEARCH_SNAPSHOT_ENABLED is true.
A dry run validates and returns the document without creating a file.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from research.guardian_research.contract import FORWARD_REASON, FORWARD_UNVERIFIED
from research.guardian_research.indicators import finite_number
from research.guardian_research.pipeline import SCAN_COLUMNS, observations_from_scan
from research.guardian_research.session_authority import assess_session, probe_vnindex
from research.guardian_research.snapshot import (
    SnapshotExists,
    build_snapshot,
    load_prior_snapshots,
    write_snapshot,
)
from research.guardian_research.universe import load_tracked_symbols

ENABLE_ENV = "GUARDIAN_RESEARCH_SNAPSHOT_ENABLED"
MARKET_PROVENANCE = "caller.market_real"


def enabled() -> bool:
    return os.environ.get(ENABLE_ENV) == "true"


def collect(
    scan_df,
    *,
    now: datetime,
    session: str,
    root: Path,
    witness: dict | None,
    market_real=None,
    coverage: dict | None = None,
    symbols: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> dict:
    """Validate one session and optionally seal it. Dry runs never write."""
    if not dry_run and not enabled():
        return _refused("disabled", "ENABLE_FLAG_OFF")
    allowed, reason = assess_session(now, session, witness)
    if not allowed:
        return _refused("refused", reason)
    tracked = tuple(symbols) if symbols is not None else load_tracked_symbols()
    coverage_reason = _coverage_reason(coverage, tracked)
    if coverage_reason:
        return _refused("refused", coverage_reason)
    ready, ready_reason = _frame_ready(scan_df, session, tracked)
    if not ready:
        return _refused("refused", ready_reason)
    if finite_number(market_real) is None:
        return _refused("refused", "MARKET_CONTEXT_ABSENT")
    observations, info = observations_from_scan(scan_df, session)
    if not info["verified"]:
        return _refused("refused", str(info["reason"]))
    document = build_snapshot(
        session,
        observations=observations,
        market={"market_real": market_real, "market_real_provenance": MARKET_PROVENANCE},
        symbols=tracked,
        priors=load_prior_snapshots(root, session),
    )
    incomplete = [
        row["symbol"]
        for row in document["rows"]
        if row["classification"] == "UNAVAILABLE"
    ]
    if incomplete:
        return _refused("refused", "INCOMPLETE_INPUT")
    if any(row["forward"]["status"] != FORWARD_UNVERIFIED or row["forward"]["reason"] != FORWARD_REASON for row in document["rows"]):
        return _refused("refused", "FORWARD_NOT_ISOLATED")
    if dry_run:
        return {
            "status": "dry_run",
            "reason": "ok",
            "path": None,
            "document": document,
            "tracked_count": document["tracked_count"],
        }
    destination = Path(root) / "sessions" / f"{session}.json"
    existed = destination.exists()
    try:
        path = write_snapshot(root, document)
    except SnapshotExists:
        return _refused("conflict", "SNAPSHOT_CONFLICT")
    return {
        "status": "unchanged" if existed else "created",
        "reason": "ok",
        "path": path,
        "document": document,
        "tracked_count": document["tracked_count"],
    }


def _coverage_reason(coverage: dict | None, tracked: tuple[str, ...]) -> str | None:
    if not isinstance(coverage, dict):
        return "SCAN_COVERAGE_ABSENT"
    requested = [str(symbol).strip().upper() for symbol in coverage.get("requested") or []]
    if len(requested) != len(set(requested)) or set(requested) != set(tracked):
        return "UNIVERSE_INCOMPLETE"
    errors = [str(symbol).strip().upper() for symbol in coverage.get("errors") or [] if str(symbol).strip()]
    if errors:
        return "PARTIAL_SCAN"
    return None


def _frame_ready(scan_df, session: str, tracked: tuple[str, ...]) -> tuple[bool, str]:
    if scan_df is None or not isinstance(scan_df, pd.DataFrame) or scan_df.empty:
        return False, "SCAN_ABSENT"
    missing = [name for name in SCAN_COLUMNS if name not in scan_df.columns]
    if missing:
        return False, "SCAN_COLUMNS_ABSENT"
    seen: dict[str, str | None] = {}
    for _, item in scan_df.iterrows():
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol:
            seen[symbol] = _session_text(item.get("date"))
    stale = [symbol for symbol in tracked if symbol in seen and seen[symbol] not in (None, session)]
    if stale:
        return False, "STALE_MARKET_DATA"
    return True, "ok"


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
    if hasattr(value, "isoformat"):
        text = value.isoformat()
        return text[:10]
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def _refused(status: str, reason: str) -> dict:
    return {"status": status, "reason": reason, "path": None, "document": None}


def _option(args: list[str], name: str) -> str | None:
    if name not in args:
        return None
    index = args.index(name)
    if index + 1 >= len(args) or str(args[index + 1]).startswith("--"):
        return ""
    return str(args[index + 1])


def _public_result(result: dict) -> dict:
    """CLI view. The document stays in memory and is not printed."""
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "session": result.get("session"),
        "tracked_count": result.get("tracked_count"),
        "witness_bar_session": result.get("witness_bar_session"),
        "witness_error": result.get("witness_error"),
        "archive_rows": result.get("archive_rows"),
        "archive_saved_at": result.get("archive_saved_at"),
        "market_real_source": result.get("market_real_source"),
        "path": None,
    }


def main(argv: list[str] | None = None) -> int:
    """Explicit command. Scheduling is not registered here."""
    args = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in args
    if not dry_run and not enabled():
        print(json.dumps({"status": "disabled", "reason": "ENABLE_FLAG_OFF", "path": None}))
        return 0
    if not dry_run:
        print(json.dumps({
            "status": "refused",
            "reason": "SCAN_NOT_ATTACHED",
            "path": None,
        }))
        return 0
    from modules.intraday_execution_boundary import VN_TZ

    now = datetime.now(VN_TZ)
    archive_session = _option(args, "--session")
    if archive_session is not None:
        from research.guardian_research.archive_input import dry_run_persisted_session

        result = dry_run_persisted_session(
            project_root=Path(__file__).resolve().parents[2],
            session=archive_session,
            now=now,
            snapshot_root=Path("data") / "guardian_research",
        )
        print(json.dumps(_public_result(result), ensure_ascii=False))
        return 0
    session = now.strftime("%Y-%m-%d")
    witness = probe_vnindex(session)
    result = collect(
        None,
        now=now,
        session=session,
        root=Path("data") / "guardian_research",
        witness=witness,
        dry_run=True,
    )
    print(json.dumps({
        "status": result["status"],
        "reason": result["reason"],
        "session": session,
        "witness_bar_session": witness.get("bar_session") or None,
        "witness_error": witness.get("probe_error"),
        "path": None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
