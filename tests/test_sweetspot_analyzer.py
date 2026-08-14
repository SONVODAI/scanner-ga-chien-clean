"""Unit tests for read-only RS/RSI sweetspot analyzer."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from modules.sweetspot_analyzer import (
    MIN_RANK_N,
    RS5_RS10_BIN_EDGES,
    RSI14_BIN_EDGES,
    analyze_sweetspots,
    bucket_values,
    combined_statistics,
    data_coverage,
    evidence_label,
    filter_window,
    rank_top_sweetspots,
    single_factor_statistics,
)


def _sample_lifecycle() -> pd.DataFrame:
    rows = []
    rs5_vals = [-12, -7, -2, 3, 8, 16]
    rs10_vals = [-12, -7, -2, 3, 8, 16]
    rsi_vals = [28, 33, 38, 43, 48, 53, 58, 65, 75]
    idx = 0
    for day in ["2026-08-01", "2026-08-02", "2026-08-03"]:
        for rs5 in rs5_vals:
            for rs10 in rs10_vals:
                for rsi in rsi_vals[:3]:
                    idx += 1
                    t3 = float((idx % 5) - 2)
                    t5 = float((idx % 7) - 3) if idx % 4 != 0 else np.nan
                    t10 = float((idx % 9) - 4) if idx % 5 != 0 else np.nan
                    rows.append(
                        {
                            "observation_id": f"obs-{idx:04d}",
                            "symbol": f"SYM{idx % 11}",
                            "trade_date": day,
                            "entry_date": day,
                            "rs5": rs5,
                            "rs10": rs10,
                            "rsi14": rsi,
                            "t3_return_pct": t3,
                            "t5_return_pct": t5,
                            "t10_return_pct": t10,
                        }
                    )
    return pd.DataFrame(rows)


class BucketBoundaryTests(unittest.TestCase):
    def test_rs5_bucket_boundaries(self):
        values = pd.Series([-10.0, -9.999, -5.0, 0.0, 15.0, 15.0001])
        labels = bucket_values(values, RS5_RS10_BIN_EDGES)
        self.assertEqual(labels.iloc[0], "-10 → -5")
        self.assertEqual(labels.iloc[1], "-10 → -5")
        self.assertEqual(labels.iloc[2], "-5 → 0")
        self.assertEqual(labels.iloc[3], "0 → 5")
        self.assertEqual(labels.iloc[4], "10 → 15")
        self.assertEqual(labels.iloc[5], "> 15")

    def test_rsi14_bucket_boundaries(self):
        values = pd.Series([29.9, 30.0, 34.999, 70.0, 70.01])
        labels = bucket_values(values, RSI14_BIN_EDGES)
        self.assertEqual(labels.iloc[0], "< 30")
        self.assertEqual(labels.iloc[1], "30 → 35")
        self.assertEqual(labels.iloc[2], "30 → 35")
        self.assertEqual(labels.iloc[3], "60 → 70")
        self.assertEqual(labels.iloc[4], "> 70")


class HorizonHandlingTests(unittest.TestCase):
    def test_missing_horizon_excluded_independently(self):
        df = pd.DataFrame(
            [
                {
                    "trade_date": "2026-08-01",
                    "rs5": 0,
                    "rs10": 0,
                    "rsi14": 40,
                    "t3_return_pct": 1.0,
                    "t5_return_pct": np.nan,
                    "t10_return_pct": 2.0,
                }
            ]
        )
        coverage = data_coverage(df)
        self.assertEqual(coverage["T3"], 1)
        self.assertEqual(coverage["T5"], 0)
        self.assertEqual(coverage["T10"], 1)

    def test_win_definition(self):
        df = pd.DataFrame(
            [
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": 0, "rsi14": 40, "t3_return_pct": 0.0},
                {"trade_date": "2026-08-01", "rs5": 1, "rs10": 1, "rsi14": 41, "t3_return_pct": 0.01},
                {"trade_date": "2026-08-01", "rs5": 2, "rs10": 2, "rsi14": 42, "t3_return_pct": -1.0},
            ]
        )
        combo = combined_statistics(df)["T3"]
        total_n = int(combo["N"].sum())
        total_wins = int(combo["Wins"].sum())
        self.assertEqual(total_n, 3)
        self.assertEqual(total_wins, 1)

    def test_n_and_winrate_calculation(self):
        df = pd.DataFrame(
            [
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": 0, "rsi14": 40, "t3_return_pct": 2.0},
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": 0, "rsi14": 40, "t3_return_pct": 4.0},
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": 0, "rsi14": 40, "t3_return_pct": -1.0},
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": 0, "rsi14": 40, "t3_return_pct": 3.0},
            ]
        )
        combo = combined_statistics(df)["T3"]
        self.assertEqual(len(combo), 1)
        row = combo.iloc[0]
        self.assertEqual(row["N"], 4)
        self.assertEqual(row["Wins"], 3)
        self.assertAlmostEqual(row["Winrate"], 75.0)
        self.assertAlmostEqual(row["Avg Return"], 2.0)
        self.assertAlmostEqual(row["Median Return"], 2.5)


class CombinedGroupingTests(unittest.TestCase):
    def test_combined_rs5_rs10_rsi_grouping(self):
        df = pd.DataFrame(
            [
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": -2, "rsi14": 40, "t3_return_pct": 1.0},
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": -2, "rsi14": 40, "t3_return_pct": 2.0},
                {"trade_date": "2026-08-01", "rs5": 5, "rs10": 5, "rsi14": 55, "t3_return_pct": -1.0},
            ]
        )
        combo = combined_statistics(df)["T3"]
        self.assertEqual(len(combo), 2)
        keys = set(zip(combo["RS5 Range"], combo["RS10 Range"], combo["RSI14 Range"]))
        self.assertIn(("0 → 5", "-5 → 0", "40 → 45"), keys)
        self.assertIn(("5 → 10", "5 → 10", "55 → 60"), keys)


class RankingTests(unittest.TestCase):
    def test_n_below_20_excluded_from_top_ranking(self):
        frame = pd.DataFrame(
            [
                {
                    "RS5 Range": "0 → 5",
                    "RS10 Range": "-5 → 0",
                    "RSI14 Range": "40 → 45",
                    "N": 19,
                    "Winrate": 99.0,
                    "Avg Return": 10.0,
                    "Median Return": 10.0,
                    "Evidence": "INSUFFICIENT",
                },
                {
                    "RS5 Range": "0 → 5",
                    "RS10 Range": "0 → 5",
                    "RSI14 Range": "45 → 50",
                    "N": 25,
                    "Winrate": 60.0,
                    "Avg Return": 2.0,
                    "Median Return": 1.5,
                    "Evidence": "EARLY",
                },
            ]
        )
        top = rank_top_sweetspots(frame, top_n=5)
        self.assertEqual(len(top), 1)
        self.assertEqual(top.iloc[0]["N"], 25)

    def test_ranking_prefers_winrate_then_returns(self):
        frame = pd.DataFrame(
            [
                {
                    "RS5 Range": "A",
                    "RS10 Range": "A",
                    "RSI14 Range": "A",
                    "N": 30,
                    "Winrate": 55.0,
                    "Avg Return": 5.0,
                    "Median Return": 4.0,
                    "Evidence": "EARLY",
                },
                {
                    "RS5 Range": "B",
                    "RS10 Range": "B",
                    "RSI14 Range": "B",
                    "N": 30,
                    "Winrate": 70.0,
                    "Avg Return": 1.0,
                    "Median Return": 1.0,
                    "Evidence": "EARLY",
                },
            ]
        )
        top = rank_top_sweetspots(frame, top_n=1)
        self.assertEqual(top.iloc[0]["RS5 Range"], "B")


class WindowTests(unittest.TestCase):
    def test_recent_20_unique_t0_dates(self):
        rows = []
        for i in range(25):
            rows.append(
                {
                    "trade_date": f"2026-07-{i + 1:02d}",
                    "rs5": 0,
                    "rs10": 0,
                    "rsi14": 40,
                    "t3_return_pct": 1.0,
                }
            )
        df = pd.DataFrame(rows)
        recent = filter_window(df, "recent_20")
        unique_dates = pd.to_datetime(recent["trade_date"]).dt.strftime("%Y-%m-%d").nunique()
        self.assertEqual(unique_dates, 20)
        self.assertEqual(recent["trade_date"].min(), "2026-07-06")
        self.assertEqual(recent["trade_date"].max(), "2026-07-25")

    def test_recent_uses_all_when_fewer_than_20_dates(self):
        df = pd.DataFrame(
            [
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": 0, "rsi14": 40, "t3_return_pct": 1.0},
                {"trade_date": "2026-08-02", "rs5": 0, "rs10": 0, "rsi14": 40, "t3_return_pct": 1.0},
            ]
        )
        recent = filter_window(df, "recent_20")
        self.assertEqual(len(recent), 2)


class IntegrityTests(unittest.TestCase):
    def test_input_dataframe_not_mutated(self):
        df = _sample_lifecycle()
        before = df.copy(deep=True)
        result = analyze_sweetspots(df, window="all", top_n=5)
        pd.testing.assert_frame_equal(df, before)
        self.assertTrue(result["source_unchanged"])

    def test_evidence_labels(self):
        self.assertEqual(evidence_label(10), "INSUFFICIENT")
        self.assertEqual(evidence_label(20), "EARLY")
        self.assertEqual(evidence_label(50), "MODERATE")
        self.assertEqual(evidence_label(100), "STRONGER EVIDENCE")

    def test_no_hardcoded_sweetspot_priority(self):
        df = pd.DataFrame(
            [
                {"trade_date": "2026-08-01", "rs5": 12, "rs10": 12, "rsi14": 65, "t3_return_pct": 9.0},
                {"trade_date": "2026-08-01", "rs5": 12, "rs10": 12, "rsi14": 65, "t3_return_pct": 8.0},
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": -2, "rsi14": 40, "t3_return_pct": -2.0},
                {"trade_date": "2026-08-01", "rs5": 0, "rs10": -2, "rsi14": 40, "t3_return_pct": -3.0},
            ]
        )
        # inflate N for non-traditional region
        extra = []
        for i in range(22):
            extra.append(
                {
                    "trade_date": "2026-08-02",
                    "rs5": 12,
                    "rs10": 12,
                    "rsi14": 65,
                    "t3_return_pct": 5.0,
                }
            )
        df = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)
        top = analyze_sweetspots(df, top_n=1)["top_sweetspots"]["T3"]
        self.assertFalse(top.empty)
        self.assertEqual(top.iloc[0]["RS5 Range"], "10 → 15")


class SingleFactorTests(unittest.TestCase):
    def test_single_factor_outputs_per_horizon(self):
        df = _sample_lifecycle()
        singles = single_factor_statistics(df)
        for horizon in ("T3", "T5", "T10"):
            self.assertIn(horizon, singles)
            self.assertFalse(singles[horizon].empty)
            self.assertIn("Factor", singles[horizon].columns)


if __name__ == "__main__":
    unittest.main()
