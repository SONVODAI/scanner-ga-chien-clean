"""N3.7D T0 feature capture — leader_history snapshot persistence tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from leader_memory import (
    CANONICAL_T0_DNA_FIELDS,
    HISTORY_COLUMNS,
    _build_experience_frame,
    _cache_t0_snapshot,
    _ensure_columns,
    _load_config,
    _overlay_t0_fields,
    _prepare_snapshot,
    _resolve_experience_t0_snapshot,
    reset_t0_snapshot_cache,
)


def _sample_scan_row() -> dict:
    return {
        "symbol": "BVH",
        "group": "MUA BREAK",
        "price": 100.0,
        "rs5": 11.31,
        "rs10": 17.37,
        "rsi14": 64.35,
        "ema9_ma20_slope": 4.53,
        "obv_status": "🟢",
        "volume": 1000.0,
        "vol_ma20": 338.0,
        "evolution_health_group": "🌱 ĐANG HỒI",
        "rs_spread": -6.06,
        "volume_ratio20": 2.959,
        "green_2_confirm": "",
        "early_dry_green2": "",
        "pull_label": "PULL VỪA",
        "dryup_ok": False,
        "total_score": 80,
    }


class TestT0SnapshotPersistence(unittest.TestCase):
    def setUp(self):
        reset_t0_snapshot_cache()

    def test_prepare_snapshot_retains_canonical_fields(self):
        scan = pd.DataFrame([_sample_scan_row()])
        snap, _ = _prepare_snapshot(scan, "2026-08-08", 7.0, 6.0, None, _load_config())
        self.assertIn("health_group", snap.columns)
        self.assertIn("rs_spread", snap.columns)
        row = snap.iloc[0]
        self.assertEqual(row["health_group"], "🌱 ĐANG HỒI")
        self.assertAlmostEqual(float(row["ema9_ma20_slope"]), 4.53, places=2)
        self.assertAlmostEqual(float(row["volume_ratio"]), 2.959, places=2)
        self.assertEqual(row["obv_status"], "🟢")

    def test_valid_values_survive_persistence_shape(self):
        scan = pd.DataFrame([_sample_scan_row()])
        snap, _ = _prepare_snapshot(scan, "2026-08-08", 7.0, 6.0, None, _load_config())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leader_history.csv"
            snap.to_csv(path, index=False)
            loaded = pd.read_csv(path)
            old_shape = _ensure_columns(loaded, HISTORY_COLUMNS)
            self.assertEqual(old_shape.iloc[0]["health_group"], "🌱 ĐANG HỒI")
            self.assertAlmostEqual(
                float(old_shape.iloc[0]["rs_spread"]), -6.06, places=2
            )

    def test_old_snapshots_without_new_columns_load_safely(self):
        legacy_cols = [c for c in HISTORY_COLUMNS if c not in {"health_group", "rs_spread"}]
        legacy = pd.DataFrame(
            [{
                "session_date": "2026-01-01",
                "snapshot_time": "2026-01-01 09:00:00",
                "symbol": "AAA",
                "price": 10.0,
                "group": "🔴 YẾU",
                "sector": "",
                "rs5": 1.0,
                "rs10": 2.0,
                "rsi14": 50.0,
                "obv": 0.0,
                "obv_status": "",
                "total_score": 40.0,
                "trend_score": 0.0,
                "buy_score": 0.0,
                "source_persistence": 0.0,
                "evolution": 0.0,
                "recent_change": 0.0,
                "ema9_ma20_slope": np.nan,
                "dist_from_ema9_pct": np.nan,
                "volume": np.nan,
                "vol_ma20": np.nan,
                "volume_ratio": np.nan,
                "market_real": 7.0,
                "market_forecast": 6.0,
                "market_regime": "",
                "storm": False,
                "early": False,
                "pullback": False,
                "green2": False,
                "dryup": False,
                "action": "",
                "reason": "",
                "feature_signature": "x",
                "schema_version": "1",
                "engine_version": "1",
            }]
        )
        loaded = _ensure_columns(legacy, HISTORY_COLUMNS)
        self.assertIn("health_group", loaded.columns)
        self.assertIn("rs_spread", loaded.columns)
        self.assertTrue(pd.isna(loaded.iloc[0]["health_group"]))

    def test_in_memory_t0_takes_priority_over_persisted(self):
        persisted = _ensure_columns(
            pd.DataFrame(
                [{
                    "session_date": "2026-08-08",
                    "snapshot_time": "t",
                    "symbol": "BVH",
                    "price": 100.0,
                    "group": "🌱 ĐANG HỒI",
                    "sector": "",
                    "health_group": "",
                    "rs5": 11.31,
                    "rs10": 17.37,
                    "rs_spread": np.nan,
                    "rsi14": 64.35,
                    "obv": 0.0,
                    "obv_status": "",
                    "total_score": 80.0,
                    "trend_score": 0.0,
                    "buy_score": 0.0,
                    "source_persistence": 0.0,
                    "evolution": 0.0,
                    "recent_change": 0.0,
                    "ema9_ma20_slope": np.nan,
                    "dist_from_ema9_pct": np.nan,
                    "volume": np.nan,
                    "vol_ma20": np.nan,
                    "volume_ratio": np.nan,
                    "market_real": 7.0,
                    "market_forecast": 6.0,
                    "market_regime": "",
                    "storm": False,
                    "early": False,
                    "pullback": False,
                    "green2": False,
                    "dryup": False,
                    "action": "",
                    "reason": "",
                    "feature_signature": "x",
                    "schema_version": "1",
                    "engine_version": "1",
                }]
            ),
            HISTORY_COLUMNS,
        )
        live, _ = _prepare_snapshot(
            pd.DataFrame([_sample_scan_row()]),
            "2026-08-08",
            7.0,
            6.0,
            None,
            _load_config(),
        )
        _cache_t0_snapshot(live, "2026-08-08")
        resolved = _resolve_experience_t0_snapshot(
            snapshot=live,
            history=pd.concat([persisted], ignore_index=True),
            session_date="2026-08-08",
        )
        row = resolved[resolved["symbol"] == "BVH"].iloc[0]
        self.assertEqual(row["health_group"], "🌱 ĐANG HỒI")
        self.assertAlmostEqual(float(row["ema9_ma20_slope"]), 4.53, places=2)
        self.assertEqual(row["obv_status"], "🟢")

    def test_overlay_never_replaces_valid_with_nan(self):
        base = pd.DataFrame([{"symbol": "X", "ema9_ma20_slope": 1.5, "health_group": "A"}])
        overlay = pd.DataFrame([{"symbol": "X", "ema9_ma20_slope": np.nan, "health_group": ""}])
        merged = _overlay_t0_fields(base, overlay, overlay_wins=True)
        self.assertAlmostEqual(float(merged.iloc[0]["ema9_ma20_slope"]), 1.5)
        self.assertEqual(merged.iloc[0]["health_group"], "A")

    def test_no_outcome_fields_in_dna_frame(self):
        scan = pd.DataFrame([_sample_scan_row()])
        snap, _ = _prepare_snapshot(scan, "2026-08-08", 7.0, 6.0, None, _load_config())
        exp = _build_experience_frame(
            snap,
            market_real=7.0,
            market_forecast=6.0,
            breadth=50.0,
            session_date="2026-08-08",
        )
        forbidden = [
            c for c in exp.columns
            if c.startswith(("return_t", "price_t", "win_t", "evaluated_t", "max_gain_t"))
        ]
        self.assertEqual(forbidden, [])

    def test_canonical_field_list_matches_pattern_columns(self):
        self.assertIn("health_group", CANONICAL_T0_DNA_FIELDS)
        self.assertIn("rs_spread", CANONICAL_T0_DNA_FIELDS)
        self.assertIn("volume_ratio", CANONICAL_T0_DNA_FIELDS)


if __name__ == "__main__":
    unittest.main()
