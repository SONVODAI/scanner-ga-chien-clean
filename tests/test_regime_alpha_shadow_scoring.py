"""Tests for ShadowFinalScore / pure baseline scoring (Patch 1)."""

from __future__ import annotations

import unittest
from unittest import mock

import pandas as pd

from modules.regime_alpha import (
    RECALL_LEVEL_NO_EVIDENCE,
    RecallEvidenceResult,
    compute_pure_baseline_score,
    compute_shadow_final_score,
)
from modules.regime_alpha_shadow import build_shadow_with_recall


class TestPureBaseline(unittest.TestCase):
    def test_pure_baseline_excludes_experience(self):
        row = {
            "leader_score": 80,
            "confidence_score": 50,
            "pattern_match_score": 60,
            "_experience_rank_adj": 8.0,
        }
        pure = compute_pure_baseline_score(row)
        self.assertEqual(pure, round(80 * 0.55 + 50 * 0.20 + 60 * 0.25, 4))

    def test_shadow_final_includes_pattern_adjustment(self):
        pattern_row = {
            "samples": 20,
            "win_rate_pct": 70.0,
            "win_rate_lower_bound_pct": 62.0,
        }
        result = compute_shadow_final_score(
            70.0,
            RecallEvidenceResult(),
            pattern_row=pattern_row,
        )
        self.assertGreater(result.shadow_final_score, result.pure_baseline_score)
        self.assertGreater(result.pattern_adjustment, 0.0)


class TestShadowBuildPureBaseline(unittest.TestCase):
    def test_baseline_score_is_pure_in_shadow_output(self):
        rec = pd.DataFrame(
            [
                {
                    "rank": 1,
                    "symbol": "AAA",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 80,
                    "confidence_score": 50,
                    "pattern_match_score": 60,
                    "updated_at": "2026-08-08",
                }
            ]
        )
        brain = pd.DataFrame([{"symbol": "AAA", "leader_score": 80}])
        exp = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "ExperienceAdjustment": 8.0,
                    "market_context_key": "k",
                    "stock_pattern_key": "DNA_A",
                }
            ]
        )

        with mock.patch(
            "modules.regime_alpha_shadow.compute_recall_evidence",
            return_value=RecallEvidenceResult(),
        ):
            shadow = build_shadow_with_recall(
                rec,
                brain,
                exp,
                session_date="2026-08-08",
                recall_index=pd.DataFrame(),
                market_real=7.0,
                market_forecast=7.0,
            )

        pure = compute_pure_baseline_score(rec.iloc[0])
        self.assertEqual(float(shadow.iloc[0]["BaselineScore"]), pure)
        self.assertEqual(float(shadow.iloc[0]["PureBaselineScore"]), pure)
        self.assertEqual(
            float(shadow.iloc[0]["ShadowFinalScore"]),
            float(shadow.iloc[0]["ShadowExperienceScore"]),
        )


if __name__ == "__main__":
    unittest.main()
