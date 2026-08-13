"""T0 data-preservation patch tests (observations + immutable freeze)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from modules.earning_learning import (
    OBSERVATIONS_FILE,
    T0_FREEZE_FILE,
    _adapt_board,
    _build_outcomes,
    _hash_payload,
    update_learning,
)
from modules.learning_t0_capture import (
    PATTERN_ALGORITHM_VERSION,
    append_t0_observation_freeze,
    build_learning_input_df,
)


def _sample_scan(*, trade_date: str = "2026-08-12") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "trade_date": trade_date,
                "price": 10.0,
                "rsi14": 55.0,
                "group": "PULL ĐẸP",
                "total_score": 80.0,
                "O": 2.0,
                "V": 1.0,
                "volume": 1000.0,
                "vol_ma20": 500.0,
            },
            {
                "symbol": "BBB",
                "trade_date": trade_date,
                "price": 20.0,
                "rsi14": 60.0,
                "group": "PULL VỪA",
                "total_score": 70.0,
                "O": 1.0,
                "V": 0.0,
                "volume": 800.0,
                "vol_ma20": 400.0,
            },
        ]
    )


def _storm_scores() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "AAA", "storm_score": 12.5},
            {"symbol": "BBB", "storm_score": 8.0},
        ]
    )


def _evo_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "AAA", "EvoFinal": 22.0},
            {"symbol": "BBB", "EvoFinal": 18.5},
        ]
    )


def _leader_brain() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "AAA", "leader_score": 75.0},
            {"symbol": "BBB", "leader_score": 62.0},
        ]
    )


def _market_context(*, real: float = 9.0, live: float = 7.0) -> dict:
    return {
        "market_real": real,
        "market_score": real,
        "market_live": live,
        "market_forecast": 6.5,
        "market_regime": "NEUTRAL",
        "breadth": 45.0,
    }


def _learning_input(scan_df: pd.DataFrame | None = None) -> pd.DataFrame:
    scan = scan_df if scan_df is not None else _sample_scan()
    return build_learning_input_df(
        scan,
        storm_scores=_storm_scores(),
        evo_table=_evo_table(),
        leader_brain=_leader_brain(),
    )


class BuildLearningInputTests(unittest.TestCase):
    def test_h_no_symbol_duplication_on_merge(self):
        merged = _learning_input()
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged["symbol"].nunique(), 2)

    def test_h_rejects_duplicate_scan_symbols(self):
        scan = _sample_scan()
        dup = pd.concat([scan, scan.iloc[[0]]], ignore_index=True)
        with self.assertRaises(ValueError):
            build_learning_input_df(
                dup,
                storm_scores=_storm_scores(),
                evo_table=_evo_table(),
                leader_brain=_leader_brain(),
            )

    def test_c_storm_score_from_raw_engine(self):
        merged = _learning_input()
        expected = _storm_scores().set_index("symbol")["storm_score"]
        for symbol in ("AAA", "BBB"):
            self.assertAlmostEqual(
                float(merged.loc[merged["symbol"] == symbol, "storm_score"].iloc[0]),
                float(expected[symbol]),
            )

    def test_d_evolution_score_equals_evofinal(self):
        merged = _learning_input()
        expected = _evo_table().set_index("symbol")["EvoFinal"]
        for symbol in ("AAA", "BBB"):
            self.assertAlmostEqual(
                float(merged.loc[merged["symbol"] == symbol, "evolution_score"].iloc[0]),
                float(expected[symbol]),
            )

    def test_e_leader_score_from_brain(self):
        merged = _learning_input()
        expected = _leader_brain().set_index("symbol")["leader_score"]
        for symbol in ("AAA", "BBB"):
            self.assertAlmostEqual(
                float(merged.loc[merged["symbol"] == symbol, "leader_score"].iloc[0]),
                float(expected[symbol]),
            )


class MarketContextTests(unittest.TestCase):
    def test_f_market_real_and_live_distinct(self):
        ctx = _market_context(real=9.0, live=7.0)
        canonical = _adapt_board(_learning_input(), market_context=ctx)
        self.assertTrue((canonical["market_real"] == 9.0).all())
        self.assertTrue((canonical["market_live"] == 7.0).all())
        self.assertTrue((canonical["market_score"] == 9.0).all())
        self.assertFalse(
            (canonical["market_real"] == canonical["market_live"]).all()
        )


def _read_t0_freeze(data_dir: Path) -> pd.DataFrame:
    path = data_dir / T0_FREEZE_FILE
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


class T0FreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "earning_learning"
        self.data_dir.mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run_learning(
        self,
        scan_df: pd.DataFrame,
        *,
        trading_today: bool = True,
    ) -> dict:
        return update_learning(
            earning_board_df=_learning_input(scan_df),
            market_context=_market_context(),
            data_dir=self.data_dir,
            trading_today=trading_today,
            strict=True,
        )

    def test_a_first_capture_writes_durable_freeze_file(self):
        result = self._run_learning(_sample_scan())
        freeze_path = self.data_dir / T0_FREEZE_FILE
        self.assertTrue(freeze_path.exists())
        self.assertGreater(result.get("t0_freeze_added", 0), 0)
        freeze = _read_t0_freeze(self.data_dir)
        self.assertEqual(len(freeze), 2)

    def test_a_different_dates_create_distinct_freeze_rows(self):
        scan_a = _sample_scan(trade_date="2026-08-10")
        scan_b = _sample_scan(trade_date="2026-08-12")
        self._run_learning(scan_a)
        self._run_learning(scan_b)

        freeze = _read_t0_freeze(self.data_dir)
        aaa_rows = freeze[freeze["symbol"] == "AAA"]
        self.assertEqual(len(aaa_rows), 2)
        dates = set(aaa_rows["trade_date"].astype(str))
        self.assertEqual(dates, {"2026-08-10", "2026-08-12"})

    def test_b_same_day_rerun_observations_update_freeze_first_wins(self):
        scan_v1 = _sample_scan()
        scan_v2 = scan_v1.copy()
        scan_v2.loc[scan_v2["symbol"] == "AAA", "price"] = 11.0

        first_result = self._run_learning(scan_v1)
        self.assertGreater(first_result.get("t0_freeze_added", 0), 0)
        freeze_after_first = _read_t0_freeze(self.data_dir).copy()

        second_result = self._run_learning(scan_v2)
        self.assertEqual(second_result.get("t0_freeze_added", 0), 0)

        obs_path = self.data_dir / OBSERVATIONS_FILE
        observations = pd.read_csv(obs_path)
        aaa_obs = observations[observations["symbol"] == "AAA"].iloc[0]
        self.assertAlmostEqual(float(aaa_obs["price"]), 11.0)

        freeze = _read_t0_freeze(self.data_dir)
        aaa_freeze = freeze[freeze["symbol"] == "AAA"].iloc[0]
        self.assertAlmostEqual(float(aaa_freeze["price"]), 10.0)
        self.assertTrue(str(aaa_freeze.get("pattern_key_v2_frozen", "")).strip())
        self.assertEqual(
            str(aaa_freeze.get("pattern_algorithm_version", "")),
            PATTERN_ALGORITHM_VERSION,
        )
        pd.testing.assert_frame_equal(
            freeze.reset_index(drop=True),
            freeze_after_first.reset_index(drop=True),
            check_dtype=False,
        )

    def test_d_frozen_values_unchanged_after_same_day_observation_update(self):
        scan_v1 = _sample_scan()
        scan_v2 = scan_v1.copy()
        scan_v2.loc[scan_v2["symbol"] == "AAA", "price"] = 11.0
        scan_v2.loc[scan_v2["symbol"] == "AAA", "storm_score"] = 99.0

        self._run_learning(scan_v1)
        first_freeze = _read_t0_freeze(self.data_dir)
        self._run_learning(scan_v2)
        second_freeze = _read_t0_freeze(self.data_dir)

        pd.testing.assert_frame_equal(
            first_freeze.reset_index(drop=True),
            second_freeze.reset_index(drop=True),
            check_dtype=False,
        )

    def test_e_storage_read_append_write_preserves_existing_rows(self):
        scan_a = _sample_scan(trade_date="2026-08-10")
        scan_b = _sample_scan(trade_date="2026-08-12")
        self._run_learning(scan_a)
        after_first = _read_t0_freeze(self.data_dir)
        self._run_learning(scan_b)
        after_second = _read_t0_freeze(self.data_dir)

        self.assertGreater(len(after_second), len(after_first))
        merged_ids = set(after_first["observation_id"].astype(str))
        preserved = after_second[
            after_second["observation_id"].astype(str).isin(merged_ids)
        ]
        pd.testing.assert_frame_equal(
            after_first.sort_values("observation_id").reset_index(drop=True),
            preserved.sort_values("observation_id").reset_index(drop=True),
            check_dtype=False,
        )

    def test_g_non_trading_day_creates_no_new_rows(self):
        before_obs = self.data_dir / OBSERVATIONS_FILE
        before_exists = before_obs.exists()

        result = self._run_learning(_sample_scan(), trading_today=False)
        self.assertEqual(result.get("skipped_reason"), "NON_TRADING_SESSION")
        self.assertEqual(result.get("observations_added"), 0)
        self.assertFalse(before_obs.exists() if not before_exists else False)

        freeze = _read_t0_freeze(self.data_dir)
        self.assertTrue(freeze.empty)
        self.assertFalse((self.data_dir / T0_FREEZE_FILE).exists())

    def test_freeze_first_write_wins_by_observation_id(self):
        canonical = _adapt_board(_learning_input(), market_context=_market_context())
        oid = canonical.loc[canonical["symbol"] == "AAA", "observation_id"].iloc[0]

        first, added1 = append_t0_observation_freeze(pd.DataFrame(), canonical)
        self.assertEqual(added1, 2)

        changed = canonical.copy()
        changed.loc[changed["symbol"] == "AAA", "price"] = 99.0
        second, added2 = append_t0_observation_freeze(first, changed)
        self.assertEqual(added2, 0)

        frozen_aaa = second[second["observation_id"] == oid].iloc[0]
        self.assertAlmostEqual(float(frozen_aaa["price"]), 10.0)


class LifecycleRegressionTests(unittest.TestCase):
    def test_i_outcomes_still_build_from_observations(self):
        rows = []
        for offset, price in enumerate([10.0, 10.5, 11.0, 12.0, 13.0, 14.0]):
            rows.append(
                {
                    "symbol": "AAA",
                    "trade_date": f"2026-08-{10 + offset:02d}",
                    "price": price,
                    "rsi14": 55.0,
                    "group": "PULL ĐẸP",
                }
            )
        observations = _adapt_board(
            pd.DataFrame(rows),
            market_context=_market_context(),
        )
        outcomes = _build_outcomes(observations, horizons=(3, 5, 10))
        self.assertFalse(outcomes.empty)
        self.assertIn("return_pct", outcomes.columns)
        t3 = outcomes[outcomes["horizon"] == 3]
        self.assertFalse(t3.empty)
        self.assertAlmostEqual(float(t3.iloc[0]["return_pct"]), 20.0)


class StormRankingUnchangedTests(unittest.TestCase):
    def test_j_learning_input_preserves_ranking_source_columns(self):
        """Learning merge must not mutate scan columns used by ranking engines."""
        scan = _sample_scan()
        merged = _learning_input(scan)
        for col in ("total_score", "O", "V", "group", "price", "rsi14"):
            pd.testing.assert_series_equal(
                scan[col].reset_index(drop=True),
                merged[col].reset_index(drop=True),
                check_names=False,
            )


class T0CaptureDemo(unittest.TestCase):
    """Section 8 dry-run: print one fully populated observation row."""

    def test_demo_new_observation_row(self):
        canonical = _adapt_board(_learning_input(), market_context=_market_context())
        row = canonical[canonical["symbol"] == "AAA"].iloc[0]

        with_patterns, added = append_t0_observation_freeze(
            pd.DataFrame(),
            canonical,
        )
        freeze_row = with_patterns[with_patterns["symbol"] == "AAA"].iloc[0]

        demo_fields = [
            "symbol",
            "trade_date",
            "observation_id",
            "price",
            "rsi14",
            "group",
            "storm_score",
            "evolution_score",
            "leader_score",
            "market_real",
            "market_live",
            "market_forecast",
            "breadth",
            "market_regime",
            "pattern_key_v2_frozen",
            "pattern_algorithm_version",
        ]

        demo = {field: freeze_row.get(field, row.get(field)) for field in demo_fields}
        self.assertEqual(demo["symbol"], "AAA")
        self.assertEqual(demo["trade_date"], "2026-08-12")
        self.assertEqual(
            demo["observation_id"],
            _hash_payload((demo["trade_date"], demo["symbol"])),
        )
        self.assertAlmostEqual(float(demo["storm_score"]), 12.5)
        self.assertAlmostEqual(float(demo["evolution_score"]), 22.0)
        self.assertAlmostEqual(float(demo["leader_score"]), 75.0)
        self.assertAlmostEqual(float(demo["market_real"]), 9.0)
        self.assertAlmostEqual(float(demo["market_live"]), 7.0)
        self.assertNotEqual(float(demo["market_real"]), float(demo["market_live"]))
        self.assertTrue(str(demo["pattern_key_v2_frozen"]).strip())
        self.assertEqual(demo["pattern_algorithm_version"], PATTERN_ALGORITHM_VERSION)

        # First capture == immutable freeze row for same observation_id
        rerun_changed = canonical.copy()
        rerun_changed.loc[rerun_changed["symbol"] == "AAA", "price"] = 99.0
        frozen_after, _ = append_t0_observation_freeze(with_patterns, rerun_changed)
        first = frozen_after[
            frozen_after["observation_id"] == demo["observation_id"]
        ].iloc[0]
        for field in demo_fields:
            if field in {"pattern_key_v2_frozen", "pattern_algorithm_version"}:
                continue
            if pd.isna(demo[field]) and pd.isna(first[field]):
                continue
            self.assertEqual(str(demo[field]), str(first[field]))


if __name__ == "__main__":
    unittest.main()
