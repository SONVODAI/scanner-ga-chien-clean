"""Forward measurement stays outside the sealed snapshot and does not fill prices."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.guardian_research.backfill import seal_reconstructed_session
from research.guardian_research.forward import measure_snapshot
from research.guardian_research.performance import read_performance_view
from research.guardian_research.scan_archive import ArchiveRejected
from research.guardian_research.snapshot import SnapshotExists, build_snapshot, write_snapshot

ROOT = Path(__file__).resolve().parents[1]


def _observation(price: float, ema9: float, ma20: float) -> dict:
    return {
        "kind": "scan_row",
        "input_session": "2026-10-30",
        "reference_price_provenance": "production_scan.price",
        "quality": "production_scan_row",
        "source": "production_scan",
        "live_injected": False,
        "price": price,
        "ema9": ema9,
        "ma20": ma20,
        "obv": 10,
        "obv_ema9": 12,
    }


def _store() -> dict:
    return {
        "trading_sessions": ["2026-10-30", "2026-11-02"],
        "rows": [
            {"symbol": "HPG", "session": "2026-10-30", "close": 100, "clock": "14:45"},
            {"symbol": "HPG", "session": "2026-11-02", "close": 110, "clock": "14:45"},
            {"symbol": "SSI", "session": "2026-10-30", "close": 50, "clock": "14:45"},
            {"symbol": "SSI", "session": "2026-11-02", "close": 40, "clock": "14:45"},
        ],
        "discontinuities": [],
    }


def _snapshot() -> dict:
    return build_snapshot(
        "2026-10-30",
        observations={
            "HPG": _observation(90, 100, 110),
            "SSI": _observation(120, 100, 90),
        },
        market={"market_real": 3.0, "market_real_provenance": "test"},
        symbols=("F88", "HPG", "SSI"),
    )


def test_missing_forward_prices_stay_blank_and_the_snapshot_is_unchanged():
    document = _snapshot()
    original = document["content_sha256"]
    view = measure_snapshot(document, _store())
    assert document["content_sha256"] == original
    assert all(row["forward"]["status"] == "UNVERIFIED" for row in document["rows"])
    by_symbol = {row["symbol"]: row for row in view["rows"]}
    assert by_symbol["F88"]["horizons"]["T+1"]["return_pct"] is None
    assert by_symbol["F88"]["classification"] == "UNAVAILABLE"
    assert by_symbol["HPG"]["horizons"]["T+1"]["return_pct"] == 10
    assert by_symbol["HPG"]["horizons"]["T+5"]["return_pct"] is None
    assert by_symbol["HPG"]["horizons"]["T+5"]["status"] == "NOT_YET_OBSERVED"
    sell = view["classifications"]["SELL"]["horizons"]["T+1"]
    assert sell["primary"] == 1
    assert view["missed_rally"]["horizons"]["T+1"]["sample"] == 1
    assert view["missed_rally"]["horizons"]["T+1"]["above_3pct"] == 1
    assert view["subsequent_drawdown"]["worst_drawdown_pct"] is None
    assert view["subsequent_drawdown"]["reason"] == "INTRADAY_PATH_ABSENT"
    assert view["input_assessment"]["position_inputs_required"] is False
    assert view["input_assessment"]["holdings_invented"] is False
    assert view["official_pnl"] is False


def test_backfill_is_labeled_and_a_different_seal_is_refused(tmp_path: Path):
    archive = ROOT / "data" / "earning_money_snapshots.csv"
    if not archive.is_file():
        pytest.skip("persisted scan is not in this worktree")
    try:
        first = seal_reconstructed_session(ROOT, "2026-10-30", tmp_path)
    except ArchiveRejected as exc:
        if exc.reason == "STALE_ARCHIVE":
            pytest.skip("the stored scan was saved after the next calendar day")
        raise
    document = first["document"]
    assert document["observation_origin"] == "BACKFILLED"
    assert document["reconstruction"]["saved_at"] == "2026-10-31T00:27:55+07:00"
    assert document["counts"]["HOLD"] == 16
    assert document["counts"]["WATCH"] == 73
    assert document["counts"]["SELL"] == 54
    assert document["counts"]["UNAVAILABLE"] == 0
    assert document["tracked_count"] == 143
    assert all(row["position_inputs_used"] is False for row in document["rows"])
    again = seal_reconstructed_session(ROOT, "2026-10-30", tmp_path)
    assert again["document"]["content_sha256"] == document["content_sha256"]
    changed = json.loads(json.dumps(document))
    changed["reconstruction"] = {"source": "other", "saved_at": "other", "label": "other"}
    from research.guardian_research.snapshot import _digest

    changed["content_sha256"] = _digest({key: value for key, value in changed.items() if key != "content_sha256"})
    with pytest.raises(SnapshotExists):
        write_snapshot(tmp_path, changed)


def test_bundled_view_matches_a_backfilled_measurement(tmp_path: Path):
    bundled = read_performance_view()
    store_path = ROOT / "data" / "approximate_returns" / "reference_store.json"
    archive = ROOT / "data" / "earning_money_snapshots.csv"
    if bundled is None or not store_path.is_file() or not archive.is_file():
        pytest.skip("bundled guardian view is not built")
    try:
        sealed = seal_reconstructed_session(ROOT, "2026-10-30", tmp_path)
    except ArchiveRejected as exc:
        if exc.reason == "STALE_ARCHIVE":
            pytest.skip("the stored scan was saved after the next calendar day")
        raise
    store = json.loads(store_path.read_text(encoding="utf-8"))
    measured = measure_snapshot(sealed["document"], store)
    assert bundled["content_sha256"] == measured["content_sha256"]
    assert bundled["observation_origin"] == "BACKFILLED"
    assert bundled["classifications"]["SELL"]["horizons"]["T+5"]["average_return_pct"] is None
    assert bundled["portfolio_decision"] is False
