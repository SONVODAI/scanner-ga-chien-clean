"""Tests for expanded shadow candidate universe (Patch 3)."""

from __future__ import annotations

import unittest

import pandas as pd

from leader_memory import RECOMMENDATION_COLUMNS, _build_recommendations
from modules.regime_alpha_shadow import build_shadow_candidate_universe


class TestShadowUniverseExpansion(unittest.TestCase):
    def _sample_data(self):
        brain = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "recommendation": "ƯU TIÊN CAO",
                    "leader_score": 90,
                    "confidence_score": 55,
                    "feature_signature": "sig1",
                },
                {
                    "symbol": "BBB",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 85,
                    "confidence_score": 50,
                    "feature_signature": "sig1",
                },
                {
                    "symbol": "CCC",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 95,
                    "confidence_score": 60,
                    "feature_signature": "sig1",
                },
                {
                    "symbol": "DDD",
                    "recommendation": "TRÁNH / CHỜ PHỤC HỒI",
                    "leader_score": 99,
                    "confidence_score": 60,
                    "feature_signature": "sig1",
                },
            ]
        )
        patterns = pd.DataFrame(
            [{"pattern_id": "p1", "feature_signature": "sig1", "pattern_score": 70}]
        )
        config = {"max_recommendation_rows": 2}
        rec = _build_recommendations(
            brain, patterns, config, market_real=7.0
        )
        return brain, patterns, rec

    def test_universe_includes_outside_production_cap(self):
        brain, patterns, rec = self._sample_data()
        self.assertEqual(len(rec), 2)
        universe = build_shadow_candidate_universe(
            brain, patterns, rec, max_candidates=250
        )
        symbols = universe["symbol"].astype(str).str.upper().tolist()
        self.assertIn("AAA", symbols)
        self.assertIn("BBB", symbols)
        self.assertIn("CCC", symbols)
        self.assertNotIn("DDD", symbols)
        self.assertGreater(len(universe), len(rec))

    def test_production_row_preserved_for_overlap(self):
        brain, patterns, rec = self._sample_data()
        universe = build_shadow_candidate_universe(brain, patterns, rec)
        aaa_prod = rec[rec["symbol"].astype(str).str.upper() == "AAA"].iloc[0]
        aaa_uni = universe[universe["symbol"].astype(str).str.upper() == "AAA"].iloc[0]
        self.assertEqual(int(aaa_uni["rank"]), int(aaa_prod["rank"]))


if __name__ == "__main__":
    unittest.main()
