"""Guardian Research Stage A — exact generate_signal reuse, immutable T0 store."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.guardian_research.collector import (
    classify_scan_row,
    collect_guardian_t0,
    load_guardian_classifier,
)
from research.guardian_research.contract import (
    CLASSIFICATION_FN,
    STATUS_MISSING,
    STATUS_VALID,
)
from research.guardian_research.store import GuardianT0Store


def _scan_row(symbol: str, **overrides):
    base = {
        "symbol": symbol,
        "price": 26.0,
        "ema9": 25.0,
        "ma20": 24.0,
        "obv": 1000.0,
        "obv_ema9": 900.0,
    }
    base.update(overrides)
    return base


def test_classification_parity_with_position_guardian():
    pg = load_guardian_classifier()
    cases = [
        _scan_row("AAA", price=26.0, ema9=25.0, ma20=24.0, obv=1000, obv_ema9=900),
        _scan_row("BBB", price=24.0, ema9=25.0, ma20=24.0, obv=1000, obv_ema9=900),
        _scan_row("CCC", price=24.0, ema9=23.0, ma20=24.0, obv=1100, obv_ema9=900),
        _scan_row("DDD", price=24.0, ema9=23.0, ma20=24.0, obv=800, obv_ema9=900),
    ]
    for raw in cases:
        series = pd.Series(raw)
        expected = pg.generate_signal(series)
        got = classify_scan_row(series, pg=pg)
        assert got["status"] == STATUS_VALID
        assert got["signal"] == expected[0]
        assert got["reason"] == expected[1]
        assert got["sell_score"] == expected[2]
        assert got["signal"] in (pg.SIGNAL_HOLD, pg.SIGNAL_WARNING, pg.SIGNAL_SELL)


def test_daily_snapshot_covers_full_tracked_universe(tmp_path: Path):
    """Every supplied tracked symbol gets a row, including MISSING gaps."""
    pg = load_guardian_classifier()
    tracked = ["AAA", "bbb", "CCC", "DDD", "AAA", "", "  "]  # dup + blanks
    scan_df = pd.DataFrame(
        [
            _scan_row("AAA"),
            _scan_row("CCC", price=24.0, ema9=25.0, ma20=24.0),  # WARNING
            # BBB absent; DDD incomplete
            {"symbol": "DDD", "price": 1.0, "ema9": 1.0},
            # Extra scan symbol outside tracked universe — must not be required
            _scan_row("ZZZ"),
        ]
    )
    store = GuardianT0Store.open(tmp_path / "universe.jsonl")
    report = collect_guardian_t0(
        scan_df,
        tracked_symbols=tracked,
        session_date="2026-08-14",
        store=store,
        market_real=4.5,
        source_provenance="universe_coverage",
        pg=pg,
    )
    expected = ["AAA", "BBB", "CCC", "DDD"]
    assert report.symbols_considered == 4
    assert report.written == 4
    assert report.valid == 2
    assert report.missing == 2
    session_rows = [r for r in store.rows if r["session_date"] == "2026-08-14"]
    assert sorted(r["symbol"] for r in session_rows) == expected
    assert len(session_rows) == len(expected)
    assert "ZZZ" not in {r["symbol"] for r in session_rows}
    by_sym = {r["symbol"]: r for r in session_rows}
    assert by_sym["AAA"]["status"] == STATUS_VALID
    assert by_sym["AAA"]["signal"] == pg.SIGNAL_HOLD
    assert by_sym["CCC"]["signal"] == pg.SIGNAL_WARNING
    assert by_sym["BBB"]["status"] == STATUS_MISSING
    assert by_sym["DDD"]["status"] == STATUS_MISSING
    assert by_sym["BBB"]["signal"] != pg.SIGNAL_HOLD
    assert by_sym["DDD"]["signal"] != pg.SIGNAL_HOLD


def test_missing_or_incomplete_never_fabricates_hold(tmp_path: Path):
    pg = load_guardian_classifier()
    scan_df = pd.DataFrame(
        [
            _scan_row("HAS"),
            # Incomplete: missing ma20 / obv fields → must not become HOLD.
            {"symbol": "INC", "price": 10.0, "ema9": 9.0},
        ]
    )
    store = GuardianT0Store.open(tmp_path / "guardian_t0_snapshots.jsonl")
    report = collect_guardian_t0(
        scan_df,
        tracked_symbols=["HAS", "INC", "ABSENT"],
        session_date="2026-08-14",
        store=store,
        market_real=7.0,
        market_context_source="test_fixture",
        source_provenance="unit_test_scan",
        captured_at="2026-08-14T10:00:00Z",
        pg=pg,
    )
    assert report.written == 3
    assert report.valid == 1
    assert report.missing == 2

    by_sym = {r["symbol"]: r for r in store.rows}
    assert by_sym["HAS"]["status"] == STATUS_VALID
    assert by_sym["HAS"]["signal"] == pg.SIGNAL_HOLD
    assert by_sym["HAS"]["market_real"] == 7.0

    for symbol in ("INC", "ABSENT"):
        row = by_sym[symbol]
        assert row["status"] == STATUS_MISSING
        assert row["signal"] == "—"
        assert row["reason"] == "—"
        assert row["sell_score"] is None
        assert row["price"] is None
        # Must not equal production HOLD label.
        assert row["signal"] != pg.SIGNAL_HOLD


def test_duplicate_rerun_preserves_historical_immutability(tmp_path: Path):
    pg = load_guardian_classifier()
    path = tmp_path / "guardian_t0_snapshots.jsonl"
    store = GuardianT0Store.open(path)
    first_scan = pd.DataFrame([_scan_row("HPG", price=100.0, ema9=99.0, ma20=98.0)])
    r1 = collect_guardian_t0(
        first_scan,
        tracked_symbols=["HPG"],
        session_date="2026-08-14",
        store=store,
        market_real=5.0,
        source_provenance="scan_v1",
        captured_at="2026-08-14T10:00:00Z",
        pg=pg,
    )
    assert r1.written == 1
    original = dict(store.get("2026-08-14", "HPG"))

    # Rerun with different price / market_real must not rewrite T0.
    second_scan = pd.DataFrame(
        [_scan_row("HPG", price=50.0, ema9=60.0, ma20=70.0, obv=1.0, obv_ema9=2.0)]
    )
    r2 = collect_guardian_t0(
        second_scan,
        tracked_symbols=["HPG"],
        session_date="2026-08-14",
        store=store,
        market_real=9.9,
        source_provenance="scan_v2_should_not_overwrite",
        captured_at="2026-08-14T18:00:00Z",
        pg=pg,
    )
    assert r2.written == 0
    assert r2.duplicates_skipped == 1
    assert store.get("2026-08-14", "HPG") == original
    assert original["price"] == 100.0
    assert original["market_real"] == 5.0
    assert original["source_provenance"] == "scan_v1"
    assert original["classification_fn"] == CLASSIFICATION_FN

    # New session may append without touching prior day.
    r3 = collect_guardian_t0(
        second_scan,
        tracked_symbols=["HPG"],
        session_date="2026-08-17",
        store=store,
        market_real=6.0,
        source_provenance="scan_next_session",
        captured_at="2026-08-17T10:00:00Z",
        pg=pg,
    )
    assert r3.written == 1
    assert store.get("2026-08-14", "HPG")["price"] == 100.0
    assert store.get("2026-08-17", "HPG")["price"] == 50.0

    # File has exactly two lines; first line still the original payload.
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["price"] == 100.0
    assert json.loads(lines[0])["session_date"] == "2026-08-14"


def test_no_holdings_or_production_guardian_writes():
    root = Path(__file__).resolve().parents[1]
    package = root / "research" / "guardian_research"
    for path in package.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for forbidden in (
            "modules.user_holdings",
            "load_positions",
            "entry_price",
            "pnl_pct",
            "holding_days",
            "build_position_table",
            "render_guardian",
            "modules.live_candidate_v2",
            "research.v2_research_ledger",
            "publish_serving",
        ):
            assert forbidden not in text, f"{path.name} must not reference {forbidden}"


def test_labels_preserved_verbatim_in_store(tmp_path: Path):
    pg = load_guardian_classifier()
    scan_df = pd.DataFrame(
        [
            _scan_row("HOLD1", price=26.0, ema9=25.0, ma20=24.0),
            _scan_row("WARN1", price=24.0, ema9=25.0, ma20=24.0),
            _scan_row("SELL1", price=24.0, ema9=23.0, ma20=24.0, obv=800, obv_ema9=900),
        ]
    )
    store = GuardianT0Store.open(tmp_path / "t0.jsonl")
    collect_guardian_t0(
        scan_df,
        tracked_symbols=["HOLD1", "WARN1", "SELL1"],
        session_date="2026-08-14",
        store=store,
        pg=pg,
        source_provenance="label_parity",
    )
    by_sym = {r["symbol"]: r for r in store.rows}
    assert by_sym["HOLD1"]["signal"] == pg.SIGNAL_HOLD
    assert by_sym["WARN1"]["signal"] == pg.SIGNAL_WARNING
    assert by_sym["SELL1"]["signal"] == pg.SIGNAL_SELL
    assert by_sym["SELL1"]["reason"] == "EMA9 dưới MA20 + OBV xác nhận"
    assert by_sym["SELL1"]["sell_score"] == 80
