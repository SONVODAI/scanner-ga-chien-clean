"""N3.7D — canonical live/historical DNA alignment + recall cache recovery."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from modules.earning_learning import (
    _add_pattern_columns,
    _decision_rows_for_pattern_keys,
    enrich_decision_frame_for_pattern_keys,
)
from modules.regime_recall_index import (
    ensure_recall_index,
    rebuild_recall_index,
    reset_recall_index_runtime_cache,
)


def _historical_key(row: dict) -> str:
    return str(_add_pattern_columns(pd.DataFrame([row]))["stock_pattern_key"].iloc[0])


def _live_key(row: dict, *, market_real=7.0, market_forecast=6.0, breadth=50.0, brain=None) -> str:
    frame = pd.DataFrame([row])
    keyed = _decision_rows_for_pattern_keys(
        frame,
        market_real=market_real,
        market_forecast=market_forecast,
        breadth=breadth,
        brain_df=brain,
    )
    return str(keyed["stock_pattern_key"].iloc[0])


class TestCanonicalDnaParity(unittest.TestCase):
    def test_full_populated_features_match(self):
        features = {
            "symbol": "TEST",
            "health_group": "🌱 ĐANG HỒI",
            "rsi14": 58.0,
            "rs5": 12.0,
            "rs10": 10.0,
            "rs_spread": 2.0,
            "ema9_ma20_slope": 0.15,
            "volume": 1000.0,
            "vol_ma20": 800.0,
            "volume_ratio20": 1.25,
            "obv_status": "🟢",
            "green2": False,
            "early": False,
            "pull": False,
            "dryup": False,
            "leader_score": 75.0,
            "market_score": 7.0,
            "market_forecast": 6.0,
            "breadth": 50.0,
        }
        hist = _historical_key(features)
        live_row = {
            "symbol": "TEST",
            "group": "🌱 ĐANG HỒI",
            "rsi14": 58.0,
            "rs5": 12.0,
            "rs10": 10.0,
            "leader_score": 75.0,
            "ema9_ma20_slope": 0.15,
            "volume": 1000.0,
            "vol_ma20": 800.0,
            "obv_status": "🟢",
            "green2": False,
            "early": False,
            "pullback": False,
            "dryup": False,
        }
        brain = pd.DataFrame(
            [{"symbol": "TEST", "current_group": "🌱 ĐANG HỒI"}]
        )
        live = _live_key(live_row, brain=brain)
        self.assertEqual(hist, live)

    def test_legitimate_missing_field_stays_na(self):
        features = {
            "symbol": "MISS",
            "health_group": "🟡 TRUNG TÍNH",
            "rsi14": 52.0,
            "rs5": 3.0,
            "rs10": 2.0,
            "rs_spread": 1.0,
            "ema9_ma20_slope": np.nan,
            "volume_ratio20": 1.1,
            "obv_status": "NEUTRAL",
            "green2": False,
            "early": False,
            "pull": False,
            "dryup": False,
            "leader_score": np.nan,
            "market_score": 7.0,
            "market_forecast": 6.0,
            "breadth": 50.0,
        }
        hist = _historical_key(features)
        live = _live_key(
            {
                "symbol": "MISS",
                "group": "🟡 TRUNG TÍNH",
                "rsi14": 52.0,
                "rs5": 3.0,
                "rs10": 2.0,
                "volume_ratio": 1.1,
                "obv_status": "NEUTRAL",
                "green2": False,
                "early": False,
                "pullback": False,
                "dryup": False,
            }
        )
        self.assertEqual(hist, live)
        self.assertIn("|NA|", hist)

    def test_recovering_neutral_case(self):
        features = {
            "symbol": "REC",
            "health_group": "🌱 ĐANG HỒI",
            "rsi14": 56.0,
            "rs5": 8.0,
            "rs10": 5.0,
            "rs_spread": 3.0,
            "ema9_ma20_slope": 0.05,
            "volume_ratio20": 0.85,
            "obv_status": "NEUTRAL",
            "green2": False,
            "early": True,
            "pull": False,
            "dryup": False,
            "leader_score": 55.0,
            "market_score": 5.0,
            "market_forecast": 5.0,
            "breadth": 35.0,
        }
        hist = _historical_key(features)
        live = _live_key(
            {
                "symbol": "REC",
                "group": "🌱 ĐANG HỒI",
                "rsi14": 56.0,
                "rs5": 8.0,
                "rs10": 5.0,
                "ema9_ma20_slope": 0.05,
                "volume": 850.0,
                "vol_ma20": 1000.0,
                "obv_status": "NEUTRAL",
                "green2": False,
                "early": True,
                "pullback": False,
                "dryup": False,
                "leader_score": 55.0,
            },
            market_real=5.0,
            market_forecast=5.0,
            breadth=35.0,
            brain=pd.DataFrame([{"symbol": "REC"}]),
        )
        self.assertEqual(hist, live)
        self.assertTrue(hist.startswith("RECOVERING|"))

    def test_strong_leader_case(self):
        features = {
            "symbol": "LEAD",
            "health_group": "🌱 ĐANG HỒI",
            "rsi14": 68.0,
            "rs5": 15.0,
            "rs10": 12.0,
            "rs_spread": 3.0,
            "ema9_ma20_slope": 0.25,
            "volume_ratio20": 1.4,
            "obv_status": "POSITIVE",
            "green2": True,
            "early": False,
            "pull": True,
            "dryup": False,
            "leader_score": 88.0,
            "market_score": 8.0,
            "market_forecast": 7.0,
            "breadth": 65.0,
        }
        hist = _historical_key(features)
        live = _live_key(
            {
                "symbol": "LEAD",
                "group": "🌱 ĐANG HỒI",
                "rsi14": 68.0,
                "rs5": 15.0,
                "rs10": 12.0,
                "ema9_ma20_slope": 0.25,
                "volume_ratio": 1.4,
                "obv_status": "POSITIVE",
                "green2": True,
                "early": False,
                "pullback": True,
                "dryup": False,
                "leader_score": 88.0,
            },
            market_real=8.0,
            market_forecast=7.0,
            breadth=65.0,
            brain=pd.DataFrame([{"symbol": "LEAD"}]),
        )
        self.assertEqual(hist, live)
        self.assertIn(">=85", hist)

    def test_enrich_maps_group_health_and_brain(self):
        raw = pd.DataFrame(
            [
                {
                    "symbol": "ENR",
                    "group": "⚠️ YẾU DẦN",
                    "rsi14": 48.0,
                    "rs10": -1.0,
                    "pullback": True,
                }
            ]
        )
        brain = pd.DataFrame(
            [
                {
                    "symbol": "ENR",
                    "current_rs5": 1.0,
                    "current_rs10": -1.0,
                    "current_obv_status": "🔴",
                }
            ]
        )
        enriched = enrich_decision_frame_for_pattern_keys(raw, brain_df=brain)
        self.assertEqual(enriched.loc[0, "health_group"], "⚠️ YẾU DẦN")
        self.assertEqual(enriched.loc[0, "pull"], True)
        self.assertAlmostEqual(float(enriched.loc[0, "rs5"]), 1.0)


class TestRecallIndexCacheRecovery(unittest.TestCase):
    DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "earning_learning"

    def setUp(self):
        reset_recall_index_runtime_cache()

    def _copy_sources(self, tmp_path: Path) -> None:
        for name in (
            "observations.csv",
            "pattern_lifecycle.csv",
            "outcomes.csv",
            "decision_archive.csv",
        ):
            src = self.DATA_DIR / name
            if src.exists():
                (tmp_path / name).write_bytes(src.read_bytes())

    @unittest.skipUnless(
        (Path(__file__).resolve().parents[1] / "data" / "earning_learning" / "observations.csv").exists(),
        "historical observations not available",
    )
    def test_missing_sources_then_available_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
            self.assertTrue(first.empty)

            self._copy_sources(tmp_path)
            second = ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
            self.assertEqual(len(second), 2414)

    @unittest.skipUnless(
        (Path(__file__).resolve().parents[1] / "data" / "earning_learning" / "observations.csv").exists(),
        "historical observations not available",
    )
    def test_successful_result_remains_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._copy_sources(tmp_path)
            first = ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
            self.assertEqual(len(first), 2414)

            with mock.patch(
                "modules.regime_recall_index.rebuild_recall_index",
                wraps=rebuild_recall_index,
            ) as mocked:
                second = ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
                mocked.assert_not_called()
            self.assertEqual(len(second), 2414)

    @unittest.skipUnless(
        (Path(__file__).resolve().parents[1] / "data" / "earning_learning" / "observations.csv").exists(),
        "historical observations not available",
    )
    def test_repeated_reruns_do_not_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._copy_sources(tmp_path)
            ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
            path = tmp_path / "regime_recall_index.csv"
            mtime = path.stat().st_mtime

            with mock.patch(
                "modules.regime_recall_index.rebuild_recall_index",
                wraps=rebuild_recall_index,
            ) as mocked:
                for _ in range(5):
                    ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
                mocked.assert_not_called()
            self.assertEqual(path.stat().st_mtime, mtime)

    def test_missing_sources_first_call_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            recall = ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
            self.assertTrue(recall.empty)


if __name__ == "__main__":
    unittest.main()
