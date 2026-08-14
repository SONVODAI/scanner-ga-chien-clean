"""Tests for Market-Aware Sweetspot Observer V1."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from modules.market_aware_sweetspot_observer import (
    CONTEXT_MATCH_EXACT,
    CONTEXT_MATCH_FAMILY,
    CONTEXT_MATCH_INSUFFICIENT,
    OBSERVER_LEDGER_FILE,
    STATUS_INSUFFICIENT_CONTEXT,
    STATUS_NO_QUALIFIED,
    STATUS_OBSERVE,
    STATUS_ZERO_CANDIDATES,
    append_observer_ledger,
    compute_observer_snapshot,
    filter_lifecycle_as_of,
    filter_stock_candidate_rows,
    freeze_daily_observer_if_eligible,
    get_frozen_day,
    load_observer_ledger,
    mature_observer_outcomes,
    render_market_aware_sweetspot_observer_panel,
)
from modules.sweetspot_analyzer import MIN_RANK_N, analyze_sweetspots


def _lifecycle_row(
    trade_date: str,
    *,
    rs5: float = 0.0,
    rs10: float = -2.0,
    rsi14: float = 40.0,
    t3: float = 1.0,
    context_key: str = "4-6|40-60|6-8",
    symbol: str = "AAA",
) -> dict:
    return {
        "trade_date": trade_date,
        "symbol": symbol,
        "rs5": rs5,
        "rs10": rs10,
        "rsi14": rsi14,
        "t3_return_pct": t3,
        "t5_return_pct": t3,
        "t10_return_pct": t3,
        "market_context_key": context_key,
    }


def _board_row(
    symbol: str,
    *,
    rs5: float = 0.0,
    rs10: float = -2.0,
    rsi14: float = 40.0,
    price: float = 10.0,
) -> dict:
    return {
        "symbol": symbol,
        "price": price,
        "rs5": rs5,
        "rs10": rs10,
        "rsi14": rsi14,
    }


def _make_qualified_history(
    context_key: str = "6-8|40-60|6-8",
    *,
    n: int = MIN_RANK_N,
    start_date: str = "2026-08-01",
) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            _lifecycle_row(
                start_date,
                rs5=0.0,
                rs10=-2.0,
                rsi14=40.0,
                t3=2.0 if i % 2 == 0 else -1.0,
                context_key=context_key,
                symbol=f"S{i:02d}",
            )
        )
    return pd.DataFrame(rows)


class AsOfFilterTests(unittest.TestCase):
    def test_excludes_trade_date_equal_t0(self):
        df = pd.DataFrame(
            [
                _lifecycle_row("2026-08-09"),
                _lifecycle_row("2026-08-10"),
                _lifecycle_row("2026-08-11"),
            ]
        )
        out = filter_lifecycle_as_of(df, "2026-08-10")
        dates = set(out["trade_date"].astype(str))
        self.assertIn("2026-08-09", dates)
        self.assertNotIn("2026-08-10", dates)
        self.assertNotIn("2026-08-11", dates)

    def test_excludes_trade_date_after_t0(self):
        df = pd.DataFrame([_lifecycle_row("2026-08-12")])
        out = filter_lifecycle_as_of(df, "2026-08-10")
        self.assertTrue(out.empty)


class EvidenceCutoffTests(unittest.TestCase):
    def test_same_day_lifecycle_not_in_as_of_evidence(self):
        t0 = "2026-08-10"
        lifecycle = pd.concat(
            [
                _make_qualified_history("6-8|40-60|6-8", start_date="2026-08-09"),
                pd.DataFrame([_lifecycle_row(t0, t3=99.0, context_key="6-8|40-60|6-8")]),
            ],
            ignore_index=True,
        )
        board = pd.DataFrame([_board_row("AAA", rs5=0, rs10=-2, rsi14=40)])
        snap = compute_observer_snapshot(
            t0_date=t0,
            earning_board_df=board,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
            market_regime="🟡 TRUNG TÍNH",
        )
        self.assertEqual(snap["observer_status"], STATUS_OBSERVE)


class ImmutableLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self._testMethodName + "_data")
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self):
        ledger = self.tmp / OBSERVER_LEDGER_FILE
        if ledger.exists():
            ledger.unlink()
        if self.tmp.exists():
            self.tmp.rmdir()

    def test_first_write_wins_for_day(self):
        t0 = "2026-08-10"
        row1 = pd.DataFrame(
            [
                {
                    "observer_id": "abc",
                    "t0_date": t0,
                    "symbol": "AAA",
                    "observer_status": STATUS_OBSERVE,
                    "rs5_t0": 1.0,
                }
            ]
        )
        merged, added1 = append_observer_ledger(pd.DataFrame(), row1, t0_date=t0)
        self.assertEqual(added1, 1)

        row2 = row1.copy()
        row2["rs5_t0"] = 9.9
        merged2, added2 = append_observer_ledger(merged, row2, t0_date=t0)
        self.assertEqual(added2, 0)
        self.assertEqual(float(merged2.iloc[0]["rs5_t0"]), 1.0)

    def test_same_day_rerun_does_not_mutate_rs_fields(self):
        t0 = "2026-08-10"
        lifecycle = _make_qualified_history(start_date="2026-08-01")
        board1 = pd.DataFrame([_board_row("AAA", rs5=0, rs10=-2, rsi14=40)])
        snap1 = compute_observer_snapshot(
            t0_date=t0,
            earning_board_df=board1,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
        )
        merged, added1 = append_observer_ledger(
            pd.DataFrame(), pd.DataFrame(snap1["rows"]), t0_date=t0
        )
        self.assertEqual(added1, 1)

        board2 = pd.DataFrame([_board_row("AAA", rs5=99, rs10=99, rsi14=99)])
        snap2 = compute_observer_snapshot(
            t0_date=t0,
            earning_board_df=board2,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
        )
        merged2, added2 = append_observer_ledger(
            merged, pd.DataFrame(snap2["rows"]), t0_date=t0
        )
        self.assertEqual(added2, 0)
        frozen = get_frozen_day(merged2, t0)
        candidate = frozen[frozen["symbol"].astype(str).str.strip() == "AAA"].iloc[0]
        self.assertEqual(float(candidate["rs5_t0"]), 0.0)

    def test_same_day_rerun_does_not_change_candidate_membership(self):
        t0 = "2026-08-10"
        lifecycle = _make_qualified_history(start_date="2026-08-01")
        board = pd.DataFrame(
            [
                _board_row("AAA", rs5=0, rs10=-2, rsi14=40),
                _board_row("BBB", rs5=5, rs10=5, rsi14=55),
            ]
        )
        snap = compute_observer_snapshot(
            t0_date=t0,
            earning_board_df=board,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
        )
        merged, _ = append_observer_ledger(
            pd.DataFrame(), pd.DataFrame(snap["rows"]), t0_date=t0
        )
        symbols = {
            s
            for s in get_frozen_day(merged, t0)["symbol"].astype(str)
            if s.strip()
        }
        self.assertEqual(symbols, {"AAA"})

        board2 = pd.DataFrame([_board_row("BBB", rs5=0, rs10=-2, rsi14=40)])
        snap2 = compute_observer_snapshot(
            t0_date=t0,
            earning_board_df=board2,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
        )
        merged2, added = append_observer_ledger(
            merged, pd.DataFrame(snap2["rows"]), t0_date=t0
        )
        self.assertEqual(added, 0)
        self.assertEqual(
            set(get_frozen_day(merged2, t0)["symbol"].astype(str)),
            {"AAA"},
        )


class ZeroCandidatePersistenceTests(unittest.TestCase):
    def test_insufficient_context_persisted(self):
        lifecycle = pd.DataFrame(
            [_lifecycle_row("2026-08-01", t3=1.0, context_key="6-8|40-60|6-8")]
        )
        board = pd.DataFrame([_board_row("AAA")])
        snap = compute_observer_snapshot(
            t0_date="2026-08-10",
            earning_board_df=board,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
        )
        self.assertEqual(snap["observer_status"], STATUS_INSUFFICIENT_CONTEXT)
        self.assertEqual(len(snap["rows"]), 1)
        self.assertEqual(snap["rows"][0]["symbol"], "")

    def test_qualified_sweetspot_zero_candidates_persisted(self):
        lifecycle = _make_qualified_history(start_date="2026-08-01")
        board = pd.DataFrame([_board_row("ZZZ", rs5=12, rs10=12, rsi14=65)])
        snap = compute_observer_snapshot(
            t0_date="2026-08-10",
            earning_board_df=board,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
        )
        self.assertEqual(snap["observer_status"], STATUS_ZERO_CANDIDATES)
        self.assertEqual(snap["rows"][0]["observer_status"], STATUS_ZERO_CANDIDATES)
        self.assertEqual(snap["rows"][0]["symbol"], "")


class ContextMatchTests(unittest.TestCase):
    def test_exact_context_used_when_qualified(self):
        exact_key = "6-8|40-60|6-8"
        lifecycle = pd.concat(
            [
                _make_qualified_history(exact_key, start_date="2026-08-01"),
                _make_qualified_history("9-9|90-90|9-9", n=MIN_RANK_N, start_date="2026-08-02"),
            ],
            ignore_index=True,
        )
        lifecycle.loc[lifecycle["trade_date"] == "2026-08-02", "t3_return_pct"] = 50.0
        board = pd.DataFrame([_board_row("AAA", rs5=0, rs10=-2, rsi14=40)])
        snap = compute_observer_snapshot(
            t0_date="2026-08-10",
            earning_board_df=board,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
        )
        self.assertEqual(snap["context_match_level"], CONTEXT_MATCH_EXACT)

    def test_family_fallback_when_exact_insufficient(self):
        family_key = "6-8|20-40|6-8"
        lifecycle = _make_qualified_history(family_key, start_date="2026-08-01")
        board = pd.DataFrame([_board_row("AAA", rs5=0, rs10=-2, rsi14=40)])
        snap = compute_observer_snapshot(
            t0_date="2026-08-10",
            earning_board_df=board,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
        )
        self.assertEqual(snap["context_match_level"], CONTEXT_MATCH_FAMILY)

    def test_insufficient_context_when_family_too_small(self):
        lifecycle = pd.DataFrame(
            [_lifecycle_row("2026-08-01", context_key="1-1|1-1|1-1")]
        )
        board = pd.DataFrame([_board_row("AAA")])
        snap = compute_observer_snapshot(
            t0_date="2026-08-10",
            earning_board_df=board,
            lifecycle_df=lifecycle,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
        )
        self.assertEqual(snap["context_match_level"], CONTEXT_MATCH_INSUFFICIENT)
        self.assertEqual(snap["observer_status"], STATUS_INSUFFICIENT_CONTEXT)


class ProductionIsolationTests(unittest.TestCase):
    def test_existing_sweetspot_research_still_works(self):
        lifecycle = _make_qualified_history(start_date="2026-08-01")
        result = analyze_sweetspots(lifecycle, window="all", top_n=5)
        self.assertIn("top_sweetspots", result)
        self.assertTrue(result["source_unchanged"])

    def test_leader_memory_recommendation_paths_untouched(self):
        import leader_memory as lm

        self.assertTrue(hasattr(lm, "update_memory"))
        self.assertTrue(callable(lm.update_memory))


class UiFrozenReadTests(unittest.TestCase):
    def test_ui_reads_frozen_ledger_not_recompute(self):
        import sys
        from unittest.mock import MagicMock

        st_mock = MagicMock()
        st_mock.columns.return_value = [
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ]
        sys.modules["streamlit"] = st_mock

        t0 = "2026-08-10"
        ledger = pd.DataFrame(
            [
                {
                    "observer_id": "x",
                    "t0_date": t0,
                    "symbol": "AAA",
                    "observer_status": STATUS_OBSERVE,
                    "market_real_t0": 7.0,
                    "market_forecast_t0": 6.0,
                    "breadth_t0": 50.0,
                    "market_regime_t0": "🟡 TRUNG TÍNH",
                    "market_context_key": "6-8|40-60|6-8",
                    "context_match_level": CONTEXT_MATCH_EXACT,
                    "earning_universe_n": 142,
                    "price_t0": 10.0,
                    "rs5_t0": 0.0,
                    "rs10_t0": -2.0,
                    "rsi14_t0": 40.0,
                    "matched_sweetspot": "RS5=...",
                    "sweetspot_horizon": "T5",
                    "historical_sample_n": 25,
                    "historical_winrate": 60.0,
                    "historical_avg_return": 1.5,
                    "historical_median_return": 1.0,
                    "evidence_status": "MODERATE",
                    "t3_return_pct": np.nan,
                    "t5_return_pct": np.nan,
                    "t10_return_pct": np.nan,
                    "created_at": "2026-08-10T11:00:00Z",
                }
            ]
        )
        with mock.patch(
            "modules.market_aware_sweetspot_observer.load_observer_ledger",
            return_value=ledger,
        ), mock.patch(
            "modules.market_aware_sweetspot_observer.compute_observer_snapshot",
        ) as mock_compute:
            result = render_market_aware_sweetspot_observer_panel(t0_date=t0)
            mock_compute.assert_not_called()
            self.assertEqual(result["candidate_count"], 1)
            st_mock.dataframe.assert_called_once()


class FreezeIntegrationTests(unittest.TestCase):
    def test_freeze_writes_to_isolated_data_dir(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            lifecycle = _make_qualified_history(start_date="2026-08-01")
            board = pd.DataFrame([_board_row("AAA", rs5=0, rs10=-2, rsi14=40)])
            result = freeze_daily_observer_if_eligible(
                t0_date="2026-08-10",
                earning_board_df=board,
                market_real=7.0,
                market_forecast=6.0,
                breadth=50.0,
                market_regime="🟡 TRUNG TÍNH",
                lifecycle_df=lifecycle,
                data_dir=tmp,
                force=True,
            )
            self.assertEqual(result["added"], 1)
            ledger = load_observer_ledger(tmp)
            self.assertEqual(len(get_frozen_day(ledger, "2026-08-10")), 1)

    def test_mature_observer_outcomes_updates_returns_only(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            lifecycle = _make_qualified_history(start_date="2026-08-01")
            board = pd.DataFrame([_board_row("AAA", rs5=0, rs10=-2, rsi14=40)])
            freeze_daily_observer_if_eligible(
                t0_date="2026-08-10",
                earning_board_df=board,
                market_real=7.0,
                market_forecast=6.0,
                breadth=50.0,
                lifecycle_df=lifecycle,
                data_dir=tmp,
                force=True,
            )
            lifecycle.loc[0, "symbol"] = "AAA"
            lifecycle.loc[0, "trade_date"] = "2026-08-10"
            lifecycle.loc[0, "t3_return_pct"] = 3.3
            mature_observer_outcomes(
                lifecycle_df=lifecycle,
                data_dir=tmp,
                immature_session_dates=["2026-08-10"],
            )
            ledger = load_observer_ledger(tmp)
            row = get_frozen_day(ledger, "2026-08-10").iloc[0]
            self.assertTrue(pd.isna(row["t3_return_pct"]))

            mature_observer_outcomes(lifecycle_df=lifecycle, data_dir=tmp)
            ledger2 = load_observer_ledger(tmp)
            row2 = get_frozen_day(ledger2, "2026-08-10").iloc[0]
            self.assertEqual(float(row2["t3_return_pct"]), 3.3)
            self.assertEqual(float(row2["rs5_t0"]), 0.0)


class InsufficientUiRobustnessTests(unittest.TestCase):
    def test_insufficient_status_nan_fields_do_not_crash_render(self):
        import sys
        from unittest.mock import MagicMock, call

        st_mock = MagicMock()
        col_mocks = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        st_mock.columns.return_value = col_mocks
        sys.modules["streamlit"] = st_mock

        t0 = "2026-08-14"
        ledger = pd.DataFrame(
            [
                {
                    "observer_id": "status",
                    "t0_date": t0,
                    "symbol": "",
                    "observer_status": STATUS_INSUFFICIENT_CONTEXT,
                    "market_real_t0": 5.6,
                    "market_forecast_t0": 4.0,
                    "breadth_t0": 25.0,
                    "market_regime_t0": "🔴 MÙA ĐÔNG",
                    "market_context_key": "<4|20-40|4-6",
                    "context_match_level": CONTEXT_MATCH_INSUFFICIENT,
                    "earning_universe_n": 142,
                    "price_t0": np.nan,
                    "rs5_t0": np.nan,
                    "rs10_t0": np.nan,
                    "rsi14_t0": np.nan,
                    "matched_sweetspot": np.nan,
                    "sweetspot_horizon": np.nan,
                    "historical_sample_n": np.nan,
                    "historical_winrate": np.nan,
                    "historical_avg_return": np.nan,
                    "historical_median_return": np.nan,
                    "evidence_status": np.nan,
                    "t3_return_pct": np.nan,
                    "t5_return_pct": np.nan,
                    "t10_return_pct": np.nan,
                    "created_at": "2026-08-14T12:00:00Z",
                }
            ]
        )

        with mock.patch(
            "modules.market_aware_sweetspot_observer.load_observer_ledger",
            return_value=ledger,
        ):
            result = render_market_aware_sweetspot_observer_panel(t0_date=t0)

        self.assertTrue(result["ok"])
        self.assertEqual(result["candidate_count"], 0)
        horizon_calls = [
            c
            for c in st_mock.metric.call_args_list
            if c.args[0] == "Sweetspot Horizon"
        ]
        self.assertEqual(horizon_calls[0].args[1], "—")
        st_mock.warning.assert_called_once()
        st_mock.dataframe.assert_not_called()
        st_mock.caption.assert_any_call("No qualified candidates for this frozen T0.")

    def test_insufficient_status_with_nan_symbol_counts_zero_candidates(self):
        import sys
        from unittest.mock import MagicMock

        st_mock = MagicMock()
        st_mock.columns.return_value = [MagicMock()] * 4
        sys.modules["streamlit"] = st_mock

        t0 = "2026-08-14"
        ledger = pd.DataFrame(
            [
                {
                    "observer_id": "status",
                    "t0_date": t0,
                    "symbol": np.nan,
                    "observer_status": STATUS_INSUFFICIENT_CONTEXT,
                    "market_real_t0": 5.6,
                    "earning_universe_n": 142,
                }
            ]
        )
        with mock.patch(
            "modules.market_aware_sweetspot_observer.load_observer_ledger",
            return_value=ledger,
        ):
            result = render_market_aware_sweetspot_observer_panel(t0_date=t0)

        self.assertEqual(result["candidate_count"], 0)
        st_mock.dataframe.assert_not_called()

    def test_missing_historical_sample_n_safe_int(self):
        from modules.market_aware_sweetspot_observer import _safe_int

        self.assertEqual(_safe_int(np.nan), 0)
        self.assertEqual(_safe_int(None), 0)
        self.assertEqual(_safe_int(25), 25)

    def test_insufficient_status_row_immutable_on_rerun(self):
        t0 = "2026-08-14"
        row = {
            "observer_id": "s1",
            "t0_date": t0,
            "symbol": "",
            "observer_status": STATUS_INSUFFICIENT_CONTEXT,
            "market_real_t0": 5.6,
            "sweetspot_horizon": np.nan,
            "historical_sample_n": np.nan,
            "earning_universe_n": 142,
        }
        merged, added1 = append_observer_ledger(
            pd.DataFrame(), pd.DataFrame([row]), t0_date=t0
        )
        self.assertEqual(added1, 1)

        row2 = dict(row)
        row2["market_real_t0"] = 9.9
        merged2, added2 = append_observer_ledger(
            merged, pd.DataFrame([row2]), t0_date=t0
        )
        self.assertEqual(added2, 0)
        self.assertEqual(float(merged2.iloc[0]["market_real_t0"]), 5.6)


class CandidateFilterTests(unittest.TestCase):
    def _status_row(self, status: str, *, symbol: Any = "") -> dict:
        return {
            "observer_id": "status",
            "t0_date": "2026-08-14",
            "symbol": symbol,
            "observer_status": status,
        }

    def _observe_row(self, symbol: str) -> dict:
        return {
            "observer_id": symbol,
            "t0_date": "2026-08-14",
            "symbol": symbol,
            "observer_status": STATUS_OBSERVE,
        }

    def test_insufficient_status_row_is_not_candidate(self):
        day = pd.DataFrame([self._status_row(STATUS_INSUFFICIENT_CONTEXT, symbol=np.nan)])
        self.assertEqual(len(filter_stock_candidate_rows(day)), 0)

    def test_no_qualified_status_row_is_not_candidate(self):
        day = pd.DataFrame([self._status_row(STATUS_NO_QUALIFIED, symbol="")])
        self.assertEqual(len(filter_stock_candidate_rows(day)), 0)

    def test_zero_candidates_status_row_is_not_candidate(self):
        day = pd.DataFrame([self._status_row(STATUS_ZERO_CANDIDATES, symbol=None)])
        self.assertEqual(len(filter_stock_candidate_rows(day)), 0)

    def test_three_observe_rows_count_as_three_candidates(self):
        day = pd.DataFrame(
            [self._observe_row("AAA"), self._observe_row("BBB"), self._observe_row("CCC")]
        )
        self.assertEqual(len(filter_stock_candidate_rows(day)), 3)

    def test_status_row_plus_three_observe_rows_counts_three(self):
        day = pd.DataFrame(
            [
                self._status_row(STATUS_INSUFFICIENT_CONTEXT, symbol=np.nan),
                self._observe_row("AAA"),
                self._observe_row("BBB"),
                self._observe_row("CCC"),
            ]
        )
        filtered = filter_stock_candidate_rows(day)
        self.assertEqual(len(filtered), 3)
        self.assertSetEqual(set(filtered["symbol"]), {"AAA", "BBB", "CCC"})

    def test_filter_does_not_mutate_input_ledger(self):
        day = pd.DataFrame(
            [
                self._status_row(STATUS_INSUFFICIENT_CONTEXT, symbol=np.nan),
                self._observe_row("AAA"),
            ]
        )
        before = day.copy()
        _ = filter_stock_candidate_rows(day)
        pd.testing.assert_frame_equal(day, before)


if __name__ == "__main__":
    unittest.main()
