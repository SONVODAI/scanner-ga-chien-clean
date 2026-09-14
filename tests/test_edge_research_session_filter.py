"""Research canonical series excludes weekend ghost dates; EOD policy unchanged."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.adapters import (
    PATTERN_HISTORY_PATH,
    _exclude_non_trading_session_dates,
    build_canonical_market_series,
    load_raw_market_snapshots,
)
from modules.edge_research.contracts import SNAPSHOT_POLICY_VERSION
from modules.edge_research.market_state import (
    RawMarketSnapshot,
    derive_research_market_state,
    enrich_date_with_market_research,
    select_canonical_market_snapshot,
)
from modules.regime_alpha_forward_eval import is_trading_session_valid
from modules.regime_recall_index import _is_weekend

REPO = Path(__file__).resolve().parents[1]
T0_PATH = REPO / "data" / "earning_learning" / "market_t0_snapshot.csv"

GHOST_SAT = "2026-09-12"
GHOST_SUN = "2026-09-13"
FIXTURE_DATES = {
    "T0": "2026-09-14",
    "T-1": "2026-09-11",
    "T-2": "2026-09-10",
    "T-3": "2026-09-09",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    ph = tmp_path / "pattern_history.csv"
    t0 = tmp_path / "market_t0_snapshot.csv"
    be = tmp_path / "buy_elite_learning_history.csv"
    ph.write_text(
        "date,time,market_real,market_forecast,breadth_score\n"
        "2026-09-11,15:05:31,3.4,0.0,19.0\n"
        "2026-09-12,10:00:00,3.4,0.0,19.0\n"
        "2026-09-13,10:00:00,3.4,0.0,19.0\n"
        "2026-09-14,15:03:00,2.8,0.0,18.0\n"
        "2026-09-14,15:19:00,2.5,0.0,18.0\n"
        "2026-09-14,15:22:00,2.4,0.0,18.0\n",
        encoding="utf-8",
    )
    t0.write_text(
        "trade_date,time,market_real,market_forecast,breadth_score,session_slot\n"
        "2026-09-09,15:49:55,5.1,0.4,32.0,AFTER_CLOSE\n"
        "2026-09-10,15:36:24,4.5,0.2,34.0,AFTER_CLOSE\n"
        "2026-09-11,21:05:31,3.4,0.0,19.0,AFTER_CLOSE\n"
        "2026-09-14,15:41:38,2.4,0.0,18.0,AFTER_CLOSE\n",
        encoding="utf-8",
    )
    be.write_text("date,time,market_real,market_forecast\n", encoding="utf-8")
    return ph, t0, be


@pytest.fixture
def research_fixture_paths(tmp_path, monkeypatch):
    ph, t0, be = _write_fixture_sources(tmp_path)
    import modules.edge_research.adapters as adapters

    monkeypatch.setattr(adapters, "PATTERN_HISTORY_PATH", ph)
    monkeypatch.setattr(adapters, "MARKET_T0_SNAPSHOT_PATH", t0)
    monkeypatch.setattr(adapters, "BUY_ELITE_HISTORY_PATH", be)
    return ph, t0, be


def _lags_for_date(series: pd.DataFrame, date: str) -> dict[str, str]:
    ordered = series.sort_values("date").reset_index(drop=True)
    idx_list = ordered.index[ordered["date"] == date].tolist()
    assert idx_list, f"{date} missing from canonical series: {ordered['date'].tolist()}"
    idx = int(idx_list[0])
    return {
        "T0": str(ordered.iloc[idx]["date"]),
        "T-1": str(ordered.iloc[idx - 1]["date"]),
        "T-2": str(ordered.iloc[idx - 2]["date"]),
        "T-3": str(ordered.iloc[idx - 3]["date"]),
    }


def test_weekend_filter_uses_existing_trading_session_weekend_guard():
    assert _is_weekend("2026-09-12") is True
    assert _is_weekend("2026-09-13") is True
    assert _is_weekend("2026-09-11") is False
    assert _is_weekend("2026-09-14") is False
    valid, reason = is_trading_session_valid("2026-09-13")
    assert valid is False
    assert reason == "weekend_session"
    filtered = _exclude_non_trading_session_dates(
        pd.DataFrame({"date": ["2026-09-11", GHOST_SAT, GHOST_SUN, "2026-09-14"]})
    )
    assert filtered["date"].tolist() == ["2026-09-11", "2026-09-14"]


def test_canonical_series_excludes_known_weekend_ghost_dates(research_fixture_paths):
    series = build_canonical_market_series(start="2026-09-09", end="2026-09-14")
    dates = set(series["date"].astype(str))
    assert GHOST_SAT not in dates
    assert GHOST_SUN not in dates
    snap_dates = {s.date for s in load_raw_market_snapshots(start="2026-09-09", end="2026-09-14")}
    assert GHOST_SAT not in snap_dates
    assert GHOST_SUN not in snap_dates


def test_2026_09_14_no_longer_uses_weekend_as_tminus1_or_tminus2(research_fixture_paths):
    series = build_canonical_market_series(start="2026-09-09", end="2026-09-14")
    lags = _lags_for_date(series, FIXTURE_DATES["T0"])
    assert lags["T-1"] != GHOST_SUN
    assert lags["T-2"] != GHOST_SAT
    assert lags["T-1"] != GHOST_SAT
    assert lags["T-2"] != GHOST_SUN


def test_2026_09_14_eligible_session_chronology_restored(research_fixture_paths):
    series = build_canonical_market_series(start="2026-09-09", end="2026-09-14")
    lags = _lags_for_date(series, FIXTURE_DATES["T0"])
    assert lags == FIXTURE_DATES
    fields = enrich_date_with_market_research(
        FIXTURE_DATES["T0"],
        series.sort_values("date").reset_index(drop=True),
        pd.DataFrame(),
        {},
    )
    assert fields["mr_t_minus_1"] == pytest.approx(3.4)
    assert fields["mr_t_minus_2"] == pytest.approx(4.5)
    assert fields["mr_t_minus_3"] == pytest.approx(5.1)


def test_filtering_does_not_mutate_historical_source_csv(research_fixture_paths):
    ph, t0, be = research_fixture_paths
    before = {path: _digest(path) for path in (ph, t0, be)}
    load_raw_market_snapshots(start="2026-09-09", end="2026-09-14")
    build_canonical_market_series(start="2026-09-09", end="2026-09-14")
    after = {path: _digest(path) for path in (ph, t0, be)}
    assert before == after


def test_repo_pattern_history_csv_untouched_by_canonical_filter():
    assert PATTERN_HISTORY_PATH.exists()
    before = _digest(PATTERN_HISTORY_PATH)
    t0_before = _digest(T0_PATH) if T0_PATH.exists() else None
    series = build_canonical_market_series(start="2026-09-09", end="2026-09-14")
    assert _digest(PATTERN_HISTORY_PATH) == before
    if t0_before is not None:
        assert _digest(T0_PATH) == t0_before
    dates = set(series["date"].astype(str))
    assert GHOST_SAT not in dates
    assert GHOST_SUN not in dates
    lags = _lags_for_date(series, FIXTURE_DATES["T0"])
    assert lags == FIXTURE_DATES


def test_eod_ambiguity_policy_unchanged():
    assert SNAPSHOT_POLICY_VERSION == "canonical_market_t0_v2_eod_preferred"
    snaps = [
        RawMarketSnapshot("2026-07-23", "16:00:00", 0.6, 0.0, session_slot="AFTER_CLOSE"),
        RawMarketSnapshot("2026-07-23", "18:00:00", 1.1, 0.0, session_slot="AFTER_CLOSE"),
    ]
    canon = select_canonical_market_snapshot(snaps)
    assert canon.policy_version == SNAPSHOT_POLICY_VERSION
    assert canon.ambiguous is True
    assert canon.market_real == pytest.approx(1.1)
    assert canon.selected_tier == "eod"
    assert derive_research_market_state("LOW", "IMPROVING", ambiguous=True) == "UNKNOWN"


def test_multiple_post_1500_values_ambiguous_unknown():
    snaps = [
        RawMarketSnapshot("2026-09-14", "15:03:00", 2.8),
        RawMarketSnapshot("2026-09-14", "15:19:00", 2.5),
        RawMarketSnapshot("2026-09-14", "15:39:00", 2.4),
        RawMarketSnapshot("2026-09-14", "15:41:38", 2.4, session_slot="AFTER_CLOSE"),
    ]
    canon = select_canonical_market_snapshot(snaps)
    assert canon.ambiguous is True
    assert canon.market_real == pytest.approx(2.4)
    assert canon.selected_tier == "eod"
    assert 2.8 in canon.distinct_market_real_values
    assert 2.5 in canon.distinct_market_real_values
    assert 2.4 in canon.distinct_market_real_values
    assert derive_research_market_state("LOW", "DETERIORATING", ambiguous=True) == "UNKNOWN"


def test_fixture_canonical_eod_on_2026_09_14_stays_ambiguous(research_fixture_paths):
    series = build_canonical_market_series(start="2026-09-14", end="2026-09-14")
    row = series.iloc[0]
    assert str(row["date"]) == "2026-09-14"
    assert bool(row["ambiguous"]) is True
    assert float(row["market_real"]) == pytest.approx(2.4)
    assert row["snapshot_tier"] == "eod"
