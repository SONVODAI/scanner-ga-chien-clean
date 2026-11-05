"""Shared Research D1 Archive Stage A collector.

Archives append-only UNVERIFIED observations for WATCHLIST + VNINDEX and
writes a candidate (not verified) VNINDEX session index. Does not feed
Research Ledger B1 or Guardian outcomes. Provider-specific fetch details
come from ``fetcher`` provenance, not the neutral contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from research.shared_d1_archive.contract import (
    ADJUSTMENT_UNVERIFIED,
    DEFAULT_START_DATE,
    FLAG_DUPLICATE_DATE,
    FLAG_EMPTY_FETCH,
    FLAG_INVALID_ROW,
    FLAG_MISSING_SESSION,
    FLAG_MISSING_SYMBOL,
    RECORD_OBSERVATION,
    RECORD_SESSION_INDEX,
    RESOLUTION,
    RUN_REPORT_FILENAME,
    SCHEMA_OBSERVATION,
    SCHEMA_RUN_REPORT,
    SCHEMA_SESSION_INDEX,
    SESSION_INDEX_FILENAME,
    SESSION_INDEX_STATUS,
    STOCK_TYPE,
    VNINDEX_SYMBOL,
    VNINDEX_TYPE,
)
from research.shared_d1_archive.fetcher import (
    D1Fetcher,
    default_fetch_provenance,
    fetch_symbol_d1,
    fetch_vnindex_d1,
    today_iso,
)
from research.shared_d1_archive.store import D1ArchiveStore, default_history_dir
from research.shared_d1_archive.universe import load_watchlist


def _utc_now_iso(now: datetime | None = None) -> str:
    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _append_jsonl_line(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
        handle.write("\n")


@dataclass
class CollectReport:
    symbols_requested: int = 0
    symbols_fetched: int = 0
    symbols_missing: int = 0
    observations_built: int = 0
    observations_written: int = 0
    duplicates_skipped: int = 0
    conflicts: int = 0
    duplicate_dates_in_fetch: int = 0
    invalid_rows: int = 0
    vnindex_sessions: int = 0
    missing_sessions_vs_vnindex: int = 0
    candidate_index_path: str | None = None
    notes: list[str] = field(default_factory=list)


def rows_from_ohlcv(
    symbol: str,
    frame: pd.DataFrame,
    *,
    fetched_at: str,
    start_date: str,
    end_date: str,
    instrument_type: str,
    provenance: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert a normalized OHLCV frame into observation + quality records."""
    observations: list[dict[str, Any]] = []
    quality: list[dict[str, Any]] = []
    seen_dates: dict[str, int] = {}
    provider = str(provenance.get("provider") or "")
    provider_source = str(provenance.get("provider_source") or "")
    fetch_fn = str(provenance.get("fetch_fn") or "")
    beautify = bool(provenance.get("beautify", True))
    unit_note = str(provenance.get("unit_note") or "as_returned_by_provider")

    for _, row in frame.iterrows():
        session = pd.Timestamp(row["date"]).date().isoformat()
        seen_dates[session] = seen_dates.get(session, 0) + 1
        open_v = row.get("open")
        high_v = row.get("high")
        low_v = row.get("low")
        close_v = row.get("close")
        volume_v = row.get("volume")
        if pd.isna(close_v):
            quality.append(
                {
                    "flag": FLAG_INVALID_ROW,
                    "symbol": symbol,
                    "session_date": session,
                    "detail": "close_missing",
                    "fetched_at": fetched_at,
                }
            )
            continue
        flags: list[str] = []
        if seen_dates[session] > 1:
            flags.append(FLAG_DUPLICATE_DATE)
        obs = {
            "schema": SCHEMA_OBSERVATION,
            "record_type": RECORD_OBSERVATION,
            "symbol": symbol,
            "session_date": session,
            "open": None if pd.isna(open_v) else float(open_v),
            "high": None if pd.isna(high_v) else float(high_v),
            "low": None if pd.isna(low_v) else float(low_v),
            "close": float(close_v),
            "volume": None if pd.isna(volume_v) else float(volume_v),
            "provider": provider,
            "provider_source": provider_source,
            "fetch_fn": fetch_fn,
            "fetched_at": fetched_at,
            "adjustment_status": ADJUSTMENT_UNVERIFIED,
            "beautify": beautify,
            "resolution": RESOLUTION,
            "instrument_type": instrument_type,
            "start_date_requested": start_date,
            "end_date_requested": end_date,
            "unit_note": unit_note,
            "quality_flags": flags,
            "verified_for_research_ledger_b1": False,
            "verified_for_guardian_outcomes": False,
        }
        observations.append(obs)

    for session, count in seen_dates.items():
        if count > 1:
            quality.append(
                {
                    "flag": FLAG_DUPLICATE_DATE,
                    "symbol": symbol,
                    "session_date": session,
                    "detail": f"fetch_returned_{count}_rows_for_date",
                    "fetched_at": fetched_at,
                }
            )
    return observations, quality


def build_candidate_vnindex_session_index(
    vnindex_frame: pd.DataFrame,
    *,
    fetched_at: str,
    start_date: str,
    end_date: str,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Candidate session dates from VNINDEX D1 — explicitly not verified."""
    meta = dict(provenance or default_fetch_provenance())
    sessions: list[str] = []
    if vnindex_frame is not None and not vnindex_frame.empty:
        for value in vnindex_frame["date"].tolist():
            day = pd.Timestamp(value).date().isoformat()
            if day not in sessions:
                sessions.append(day)
        sessions.sort()
    return {
        "schema": SCHEMA_SESSION_INDEX,
        "record_type": RECORD_SESSION_INDEX,
        "verified": False,
        "status": SESSION_INDEX_STATUS,
        "sessions": sessions,
        "n_sessions": len(sessions),
        "first_session": sessions[0] if sessions else None,
        "last_session": sessions[-1] if sessions else None,
        "source": meta.get("provider"),
        "provider_source": meta.get("provider_source"),
        "symbol": VNINDEX_SYMBOL,
        "provenance": (
            "candidate_only_from_vnindex_d1_dates;"
            "not_a_verified_hose_exchange_calendar;"
            "do_not_feed_research_ledger_b1_or_guardian_outcomes"
        ),
        "fetched_at": fetched_at,
        "start_date_requested": start_date,
        "end_date_requested": end_date,
        "adjustment_status": ADJUSTMENT_UNVERIFIED,
    }


def write_candidate_session_index(path: Path, document: Mapping[str, Any]) -> Path:
    """Write/replace the candidate index document (always verified=false)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if document.get("verified") is True:
        raise ValueError("candidate session index must keep verified=false")
    path.write_text(
        json.dumps(dict(document), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def collect_shared_d1_archive(
    *,
    directory: Path | None = None,
    symbols: Sequence[str] | None = None,
    include_vnindex: bool = True,
    start_date: str = DEFAULT_START_DATE,
    end_date: str | None = None,
    fetcher: D1Fetcher | Callable[..., pd.DataFrame] | None = None,
    fetched_at: str | None = None,
    watchlist_path: Path | None = None,
) -> CollectReport:
    """Fetch and archive raw D1 observations for the tracked universe + VNINDEX."""
    report = CollectReport()
    root = Path(directory) if directory is not None else default_history_dir()
    store = D1ArchiveStore.open(root)
    fetched = fetched_at or _utc_now_iso()
    end = end_date or today_iso()

    if symbols is None:
        universe = list(load_watchlist(watchlist_path))
    else:
        universe = [str(s).strip().upper() for s in symbols if str(s).strip()]
    report.symbols_requested = len(universe)

    all_observations: list[dict[str, Any]] = []
    pending_quality: list[dict[str, Any]] = []
    vnindex_sessions: set[str] = set()
    provenance = default_fetch_provenance(beautify=True)

    if include_vnindex:
        vn_frame = fetch_vnindex_d1(start_date=start_date, end_date=end, fetcher=fetcher)
        if vn_frame.empty:
            pending_quality.append(
                {
                    "flag": FLAG_EMPTY_FETCH,
                    "symbol": VNINDEX_SYMBOL,
                    "session_date": None,
                    "detail": "vnindex_fetch_empty",
                    "fetched_at": fetched,
                }
            )
            report.notes.append("VNINDEX fetch empty")
        else:
            obs, qual = rows_from_ohlcv(
                VNINDEX_SYMBOL,
                vn_frame,
                fetched_at=fetched,
                start_date=start_date,
                end_date=end,
                instrument_type=VNINDEX_TYPE,
                provenance=provenance,
            )
            all_observations.extend(obs)
            pending_quality.extend(qual)
            report.duplicate_dates_in_fetch += sum(
                1 for q in qual if q.get("flag") == FLAG_DUPLICATE_DATE
            )
            report.invalid_rows += sum(1 for q in qual if q.get("flag") == FLAG_INVALID_ROW)
            vnindex_sessions = {r["session_date"] for r in obs}
            report.vnindex_sessions = len(vnindex_sessions)
            index_doc = build_candidate_vnindex_session_index(
                vn_frame,
                fetched_at=fetched,
                start_date=start_date,
                end_date=end,
                provenance=provenance,
            )
            index_path = write_candidate_session_index(
                root / SESSION_INDEX_FILENAME,
                index_doc,
            )
            report.candidate_index_path = str(index_path)

    symbol_sessions: dict[str, set[str]] = {}
    for symbol in universe:
        frame = fetch_symbol_d1(
            symbol,
            start_date=start_date,
            end_date=end,
            instrument_type=STOCK_TYPE,
            beautify=True,
            fetcher=fetcher,
        )
        if frame.empty:
            report.symbols_missing += 1
            pending_quality.append(
                {
                    "flag": FLAG_MISSING_SYMBOL,
                    "symbol": symbol,
                    "session_date": None,
                    "detail": "empty_d1_fetch",
                    "fetched_at": fetched,
                }
            )
            continue
        report.symbols_fetched += 1
        obs, qual = rows_from_ohlcv(
            symbol,
            frame,
            fetched_at=fetched,
            start_date=start_date,
            end_date=end,
            instrument_type=STOCK_TYPE,
            provenance=provenance,
        )
        all_observations.extend(obs)
        pending_quality.extend(qual)
        report.duplicate_dates_in_fetch += sum(
            1 for q in qual if q.get("flag") == FLAG_DUPLICATE_DATE
        )
        report.invalid_rows += sum(1 for q in qual if q.get("flag") == FLAG_INVALID_ROW)
        symbol_sessions[symbol] = {r["session_date"] for r in obs}

    # Missing sessions relative to candidate VNINDEX index (gap ≠ holiday proof).
    if vnindex_sessions:
        for symbol, sessions in symbol_sessions.items():
            missing = sorted(vnindex_sessions - sessions)
            for session in missing:
                report.missing_sessions_vs_vnindex += 1
                pending_quality.append(
                    {
                        "flag": FLAG_MISSING_SESSION,
                        "symbol": symbol,
                        "session_date": session,
                        "detail": "absent_vs_vnindex_candidate_index",
                        "fetched_at": fetched,
                    }
                )

    report.observations_built = len(all_observations)
    counts = store.append_observations(all_observations, fetched_at=fetched)
    report.observations_written = counts["written"]
    report.duplicates_skipped = counts["duplicates_skipped"]
    report.conflicts = counts["conflicts"]

    if pending_quality:
        stamped = [
            {
                "schema": "shared_research_d1.quality.v1",
                "record_type": "d1_quality_event",
                **item,
            }
            for item in pending_quality
        ]
        store.append_quality_events(stamped)

    run_row = {
        "schema": SCHEMA_RUN_REPORT,
        "record_type": "d1_run_report",
        "fetched_at": fetched,
        "start_date": start_date,
        "end_date": end,
        "symbols_requested": report.symbols_requested,
        "symbols_fetched": report.symbols_fetched,
        "symbols_missing": report.symbols_missing,
        "observations_written": report.observations_written,
        "duplicates_skipped": report.duplicates_skipped,
        "conflicts": report.conflicts,
        "vnindex_sessions": report.vnindex_sessions,
        "missing_sessions_vs_vnindex": report.missing_sessions_vs_vnindex,
        "candidate_index_path": report.candidate_index_path,
        "feeds_research_ledger_b1": False,
        "feeds_guardian_outcomes": False,
    }
    _append_jsonl_line(root / RUN_REPORT_FILENAME, run_row)
    return report
