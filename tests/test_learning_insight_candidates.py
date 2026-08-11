"""Tests for Learning Insight Candidates research engine (Patch 5)."""

from __future__ import annotations

import unittest
from unittest import mock

import pandas as pd

from modules.learning_insight_candidates import (
    compute_insight_candidate_score,
    build_learning_insight_candidates,
)
from modules.regime_alpha_shadow import build_shadow_with_recall


class TestInsightCandidateScore(unittest.TestCase):
    def test_independent_from_shadow_score(self):
        pattern_row = {
            "samples": 20,
            "win_rate_pct": 68.0,
            "win_rate_lower_bound_pct": 60.0,
            "pattern_key": "CTX[6-8|40-60|6-8]::DNA[TEST]",
            "market_context_key": "6-8|40-60|6-8",
        }
        continuation_row = {
            "samples_t10": 15,
            "continuation_score": 72.0,
            "t3_to_t5_rate_pct": 65.0,
            "t3_to_t10_rate_pct": 58.0,
            "market_context_key": "6-8|40-60|6-8",
        }
        insight = compute_insight_candidate_score(
            pattern_row=pattern_row,
            continuation_row=continuation_row,
            context_match_mode="FAMILY_CONTEXT",
        )
        self.assertGreater(insight.insight_candidate_score, 50.0)
        self.assertEqual(insight.context_match_mode, "FAMILY_CONTEXT")
        self.assertGreater(insight.experience_samples, 0)

    def test_insight_build_does_not_use_shadow_final_score(self):
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
        with mock.patch(
            "modules.learning_insight_candidates.get_pattern_knowledge",
            return_value=pd.DataFrame(),
        ), mock.patch(
            "modules.learning_insight_candidates.get_continuation_knowledge",
            return_value=pd.DataFrame(),
        ):
            insight = build_learning_insight_candidates(
                rec,
                brain,
                session_date="2026-08-08",
                market_real=7.0,
                market_forecast=7.0,
                breadth=50.0,
            )
            shadow = build_shadow_with_recall(
                rec,
                brain,
                None,
                session_date="2026-08-08",
                recall_index=pd.DataFrame(),
                market_real=7.0,
                market_forecast=7.0,
            )
        self.assertIn("InsightCandidateScore", insight.columns)
        self.assertNotIn("ShadowFinalScore", insight.columns)
        self.assertIn("ShadowFinalScore", shadow.columns)


if __name__ == "__main__":
    unittest.main()
