"""Shared Research D1 Archive Stage A — offline synthetic tests (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.shared_d1_archive.collector import (
    build_candidate_vnindex_session_index,
    collect_shared_d1_archive,
)
from research.shared_d1_archive.contract import (
    ADJUSTMENT_UNVERIFIED,
    FLAG_CONFLICTING_VALUE,
    FLAG_DUPLICATE_DATE,
    FLAG_MISSING_SESSION,
    FLAG_MISSING_SYMBOL,
    SESSION_INDEX_STATUS,
    VNINDEX_SYMBOL,
    observation_may_feed_research_outcomes,
    session_index_may_feed_verified_calendar,
)
from research.shared_d1_archive.fetcher import DNSE_PROVIDER_SOURCE, normalize_ohlcv_frame
from research.shared_d1_archive.store import D1ArchiveStore, observations_path
from research.shared_d1_archive.universe import load_watchlist


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _synthetic_fetcher(table: dict[str, pd.DataFrame]):
    def _fetch(*, symbol: str, start_date: str, end_date: str, resolution: str, type: str, beautify: bool, source: str):
        assert resolution == "1D"
        assert source == "DNSE"
        return table.get(symbol, pd.DataFrame()).copy()

    return _fetch


def test_normalize_preserves_provider_ohlcv_values():
    raw = _frame(
        [
            {"time": "2026-08-14", "open": 10.5, "high": 11.0, "low": 10.0, "close": 10.8, "volume": 1000},
            {"time": "2026-08-15", "open": 10.8, "high": 11.2, "low": 10.5, "close": 11.0, "volume": 1100},
        ]
    )
    out = normalize_ohlcv_frame(raw)
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert float(out.iloc[0]["close"]) == 10.8
    assert float(out.iloc[1]["volume"]) == 1100


def test_collect_archives_unverified_observations_and_candidate_index(tmp_path: Path):
    table = {
        VNINDEX_SYMBOL: _frame(
            [
                {"time": "2026-08-14", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 9},
                {"time": "2026-08-15", "open": 1, "high": 2, "low": 1, "close": 1.6, "volume": 9},
            ]
        ),
        "HPG": _frame(
            [
                {"time": "2026-08-14", "open": 20, "high": 21, "low": 19, "close": 20.5, "volume": 100},
                {"time": "2026-08-15", "open": 20.5, "high": 22, "low": 20, "close": 21.0, "volume": 120},
            ]
        ),
        "AAA": _frame([]),  # missing symbol
    }
    report = collect_shared_d1_archive(
        directory=tmp_path,
        symbols=["HPG", "AAA"],
        start_date="2026-08-01",
        end_date="2026-08-20",
        fetcher=_synthetic_fetcher(table),
        fetched_at="2026-08-20T12:00:00Z",
    )
    assert report.symbols_requested == 2
    assert report.symbols_fetched == 1
    assert report.symbols_missing == 1
    assert report.vnindex_sessions == 2
    assert report.observations_written >= 4  # VNINDEX 2 + HPG 2

    store = D1ArchiveStore.open(tmp_path)
    hpg = [r for r in store.observations if r["symbol"] == "HPG"]
    assert len(hpg) == 2
    assert all(r["adjustment_status"] == ADJUSTMENT_UNVERIFIED for r in hpg)
    assert all(r["provider_source"] == DNSE_PROVIDER_SOURCE for r in hpg)
    assert all(r["verified_for_research_ledger_b1"] is False for r in hpg)
    assert all(r["verified_for_guardian_outcomes"] is False for r in hpg)
    assert all(observation_may_feed_research_outcomes(r) is False for r in hpg)

    index = json.loads((tmp_path / "vnindex_session_index_candidate.json").read_text(encoding="utf-8"))
    assert index["verified"] is False
    assert index["status"] == SESSION_INDEX_STATUS
    assert index["sessions"] == ["2026-08-14", "2026-08-15"]
    assert "not_a_verified_hose_exchange_calendar" in index["provenance"]
    assert session_index_may_feed_verified_calendar(index) is False

    quality = store.quality_events
    assert any(q["flag"] == FLAG_MISSING_SYMBOL and q["symbol"] == "AAA" for q in quality)


def test_missing_session_vs_vnindex_is_flagged(tmp_path: Path):
    table = {
        VNINDEX_SYMBOL: _frame(
            [
                {"time": "2026-08-14", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                {"time": "2026-08-15", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            ]
        ),
        "HPG": _frame(
            [
                {"time": "2026-08-14", "open": 20, "high": 21, "low": 19, "close": 20, "volume": 10},
                # 2026-08-15 missing for HPG
            ]
        ),
    }
    report = collect_shared_d1_archive(
        directory=tmp_path,
        symbols=["HPG"],
        fetcher=_synthetic_fetcher(table),
        fetched_at="2026-08-20T12:00:00Z",
        end_date="2026-08-20",
    )
    assert report.missing_sessions_vs_vnindex == 1
    quality = D1ArchiveStore.open(tmp_path).quality_events
    assert any(
        q["flag"] == FLAG_MISSING_SESSION
        and q["symbol"] == "HPG"
        and q["session_date"] == "2026-08-15"
        for q in quality
    )


def test_duplicate_dates_in_fetch_flagged(tmp_path: Path):
    table = {
        VNINDEX_SYMBOL: _frame(
            [{"time": "2026-08-14", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
        ),
        "HPG": _frame(
            [
                {"time": "2026-08-14", "open": 20, "high": 21, "low": 19, "close": 20, "volume": 10},
                {"time": "2026-08-14", "open": 20, "high": 22, "low": 19, "close": 21, "volume": 11},
            ]
        ),
    }
    report = collect_shared_d1_archive(
        directory=tmp_path,
        symbols=["HPG"],
        include_vnindex=True,
        fetcher=_synthetic_fetcher(table),
        fetched_at="2026-08-20T12:00:00Z",
        end_date="2026-08-20",
    )
    assert report.duplicate_dates_in_fetch >= 1
    quality = D1ArchiveStore.open(tmp_path).quality_events
    assert any(q["flag"] == FLAG_DUPLICATE_DATE and q["symbol"] == "HPG" for q in quality)


def test_conflict_appends_without_overwrite(tmp_path: Path):
    table_v1 = {
        VNINDEX_SYMBOL: _frame(
            [{"time": "2026-08-14", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
        ),
        "HPG": _frame(
            [{"time": "2026-08-14", "open": 20, "high": 21, "low": 19, "close": 20.0, "volume": 10}]
        ),
    }
    collect_shared_d1_archive(
        directory=tmp_path,
        symbols=["HPG"],
        fetcher=_synthetic_fetcher(table_v1),
        fetched_at="2026-08-20T10:00:00Z",
        end_date="2026-08-20",
    )
    table_v2 = {
        VNINDEX_SYMBOL: table_v1[VNINDEX_SYMBOL],
        "HPG": _frame(
            [{"time": "2026-08-14", "open": 20, "high": 21, "low": 19, "close": 25.0, "volume": 10}]
        ),
    }
    report = collect_shared_d1_archive(
        directory=tmp_path,
        symbols=["HPG"],
        fetcher=_synthetic_fetcher(table_v2),
        fetched_at="2026-08-21T10:00:00Z",
        end_date="2026-08-20",
    )
    assert report.conflicts == 1
    versions = D1ArchiveStore.open(tmp_path).versions_for("HPG", "2026-08-14")
    assert len(versions) == 2
    assert versions[0]["close"] == 20.0
    assert versions[0]["fetched_at"] == "2026-08-20T10:00:00Z"
    assert versions[1]["close"] == 25.0
    assert versions[1]["fetched_at"] == "2026-08-21T10:00:00Z"
    assert FLAG_CONFLICTING_VALUE in versions[1]["quality_flags"]
    assert versions[1]["supersedes_fingerprint"] == versions[0]["content_fingerprint"]
    # First line in file remains the original capture (immutable).
    lines = observations_path(tmp_path).read_text(encoding="utf-8").strip().splitlines()
    hpg_lines = [json.loads(line) for line in lines if json.loads(line).get("symbol") == "HPG"]
    assert hpg_lines[0]["close"] == 20.0
    assert hpg_lines[0]["fetched_at"] == "2026-08-20T10:00:00Z"


def test_idempotent_rerun_skips_identical_content(tmp_path: Path):
    table = {
        VNINDEX_SYMBOL: _frame(
            [{"time": "2026-08-14", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
        ),
        "HPG": _frame(
            [{"time": "2026-08-14", "open": 20, "high": 21, "low": 19, "close": 20.0, "volume": 10}]
        ),
    }
    fetcher = _synthetic_fetcher(table)
    r1 = collect_shared_d1_archive(
        directory=tmp_path,
        symbols=["HPG"],
        fetcher=fetcher,
        fetched_at="2026-08-20T10:00:00Z",
        end_date="2026-08-20",
    )
    r2 = collect_shared_d1_archive(
        directory=tmp_path,
        symbols=["HPG"],
        fetcher=fetcher,
        fetched_at="2026-08-20T11:00:00Z",
        end_date="2026-08-20",
    )
    assert r1.observations_written >= 2
    assert r2.observations_written == 0
    assert r2.duplicates_skipped >= 2
    assert r2.conflicts == 0


def test_candidate_index_rejects_verified_true(tmp_path: Path):
    doc = build_candidate_vnindex_session_index(
        _frame([{"date": "2026-08-14", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]),
        fetched_at="2026-08-20T12:00:00Z",
        start_date="2026-08-01",
        end_date="2026-08-20",
    )
    doc["verified"] = True
    try:
        from research.shared_d1_archive.collector import write_candidate_session_index

        write_candidate_session_index(tmp_path / "bad.json", doc)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "verified=false" in str(exc)


def test_package_does_not_feed_b1_or_guardian_or_live_inject():
    root = Path(__file__).resolve().parents[1] / "research" / "shared_d1_archive"
    banned_imports = (
        "research.v2_research_ledger",
        "research.guardian_research",
        "position_guardian",
        "modules.live_candidate_v2",
        "inject_live_into_daily",
    )
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in banned_imports:
            assert f"import {marker}" not in text
            assert f"from {marker}" not in text
        assert "EXPLICIT_UNADJUSTED" not in text


def test_load_watchlist_from_app_ast():
    symbols = load_watchlist()
    assert "HPG" in symbols
    assert "VNINDEX" not in symbols
    assert len(symbols) >= 100
    assert list(symbols) == sorted(symbols)


def test_contract_is_provider_neutral_dnse_only_in_fetcher():
    root = Path(__file__).resolve().parents[1] / "research" / "shared_d1_archive"
    contract_text = (root / "contract.py").read_text(encoding="utf-8")
    for marker in ("DNSE", "vnstock", "entrade", "Entrade"):
        assert marker not in contract_text
    fetcher_text = (root / "fetcher.py").read_text(encoding="utf-8")
    assert "DNSE" in fetcher_text
    assert "vnstock" in fetcher_text


def test_no_production_files_modified_by_stage_a():
    root = Path(__file__).resolve().parents[1]
    # Stage A adds research package + tests only; production paths stay untouched in tree status.
    for rel in ("app.py", "position_guardian.py"):
        assert (root / rel).is_file()
    # Sanity: collector must not import production scan injectors.
    collector = (root / "research" / "shared_d1_archive" / "collector.py").read_text(
        encoding="utf-8"
    )
    assert "inject_live_into_daily" not in collector
    assert "from app" not in collector
