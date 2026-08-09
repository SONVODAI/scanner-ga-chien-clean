"""N3.7 shadow integration tests — production must remain unchanged."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from final_decision_engine import build_final_decision
from leader_memory import RECOMMENDATION_COLUMNS, _build_recommendations
from modules.regime_alpha import RECALL_LEVEL_NO_EVIDENCE
from modules.regime_alpha_shadow import (
    SHADOW_COLUMNS,
    SHADOW_SNAPSHOT_FILE,
    _apply_shadow_experience_rerank,
    build_shadow_with_recall,
    persist_shadow_audit,
)


def _brain_row(
    symbol="AAA",
    recommendation="THEO DÕI MUA",
    leader_score=75.0,
    confidence_score=40.0,
    **extra,
):
    base = {
        "symbol": symbol,
        "recommendation": recommendation,
        "leader_score": leader_score,
        "confidence_score": confidence_score,
        "leader_level": "LEADER",
        "current_group": "CP MẠNH",
        "current_price": 10.0,
        "current_rs5": 1.2,
        "current_rs10": 1.1,
        "current_rsi14": 58.0,
        "current_obv_status": "UP",
        "winrate_t5_pct": 60.0,
        "avg_return_t5_pct": 2.0,
        "persistence_20_pct": 55.0,
        "feature_signature": "sig1",
    }
    base.update(extra)
    return base


def _empty_recall_index() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "stock_pattern_key",
            "market_context_key",
            "recall_level",
            "usable_for_learning",
            "t3_return_pct",
            "t5_return_pct",
            "t10_return_pct",
            "outcome_status_t3",
            "outcome_status_t5",
            "outcome_status_t10",
        ]
    )


class TestProductionUnchanged(unittest.TestCase):
    def _sample_production_inputs(self):
        brain = pd.DataFrame(
            [
                _brain_row("AAA", leader_score=80, recommendation="ƯU TIÊN CAO"),
                _brain_row("BBB", leader_score=70, recommendation="THEO DÕI MUA"),
            ]
        )
        patterns = pd.DataFrame(
            [{"pattern_id": "p1", "feature_signature": "sig1", "pattern_score": 70}]
        )
        config = {"max_recommendation_rows": 100}
        exp = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "ExperienceAdjustment": 2.0,
                    "LearningStatus": "READY_FOR_CONNECTION",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": "DNA_A",
                },
                {
                    "symbol": "BBB",
                    "ExperienceAdjustment": -1.0,
                    "LearningStatus": "READY_FOR_CONNECTION",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": "DNA_B",
                },
            ]
        )
        return brain, patterns, config, exp

    def test_production_columns_and_order_unchanged_by_shadow(self):
        brain, patterns, config, exp = self._sample_production_inputs()
        rec_before = _build_recommendations(
            brain, patterns, config, experience_df=exp, market_real=7.0
        )
        rec_after = _build_recommendations(
            brain, patterns, config, experience_df=exp, market_real=7.0
        )
        _ = build_shadow_with_recall(
            rec_after,
            brain,
            exp,
            session_date="2026-08-08",
            recall_index=_empty_recall_index(),
            market_real=7.0,
            market_forecast=7.0,
        )
        self.assertListEqual(list(rec_before.columns), list(RECOMMENDATION_COLUMNS))
        pd.testing.assert_frame_equal(rec_before, rec_after)

    def test_production_rec_not_mutated_by_shadow(self):
        brain, patterns, config, exp = self._sample_production_inputs()
        rec = _build_recommendations(
            brain, patterns, config, experience_df=exp, market_real=7.0
        )
        rec_before = rec.copy(deep=True)
        _ = build_shadow_with_recall(
            rec,
            brain,
            exp,
            session_date="2026-08-08",
            recall_index=_empty_recall_index(),
            market_real=7.0,
            market_forecast=7.0,
        )
        pd.testing.assert_frame_equal(rec, rec_before)


class TestShadowRerank(unittest.TestCase):
    def test_shadow_rank_follows_shadow_experience_score(self):
        rec = pd.DataFrame(
            [
                {
                    "rank": 1,
                    "symbol": "AAA",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 90,
                    "confidence_score": 50,
                    "pattern_match_score": 60,
                    "updated_at": "2026-08-08",
                },
                {
                    "rank": 2,
                    "symbol": "BBB",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 80,
                    "confidence_score": 50,
                    "pattern_match_score": 60,
                    "updated_at": "2026-08-08",
                },
                {
                    "rank": 3,
                    "symbol": "CCC",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 70,
                    "confidence_score": 50,
                    "pattern_match_score": 60,
                    "updated_at": "2026-08-08",
                },
            ]
        )
        brain = pd.DataFrame([_brain_row("AAA"), _brain_row("BBB"), _brain_row("CCC")])
        exp = pd.DataFrame(
            [
                {"symbol": "AAA", "market_context_key": "k", "stock_pattern_key": "DNA_A"},
                {"symbol": "BBB", "market_context_key": "k", "stock_pattern_key": "DNA_B"},
                {"symbol": "CCC", "market_context_key": "k", "stock_pattern_key": "DNA_C"},
            ]
        )

        def _fake_recall(market_context_key, stock_pattern_key, recall_index=None, **kwargs):
            _ = market_context_key, recall_index, kwargs
            mapping = {
                "DNA_A": mock.Mock(
                    recall_source="RECALL_INDEX",
                    recall_level=RECALL_LEVEL_NO_EVIDENCE,
                    recall_samples=0,
                    recall_t3_samples=0,
                    recall_t5_samples=0,
                    recall_t10_samples=0,
                    recall_mean_t3=None,
                    recall_mean_t5=None,
                    recall_mean_t10=None,
                    recall_win_rate_t3=None,
                    recall_win_rate_t5=None,
                    recall_win_rate_t10=None,
                    recall_confidence=0.0,
                    recall_alpha=50.0,
                    recall_matched_dna=stock_pattern_key,
                    recall_matched_context="",
                ),
                "DNA_B": mock.Mock(
                    recall_source="RECALL_INDEX",
                    recall_level="EXACT_CONTEXT",
                    recall_samples=20,
                    recall_t3_samples=20,
                    recall_t5_samples=20,
                    recall_t10_samples=20,
                    recall_mean_t3=5.0,
                    recall_mean_t5=5.0,
                    recall_mean_t10=5.0,
                    recall_win_rate_t3=70.0,
                    recall_win_rate_t5=70.0,
                    recall_win_rate_t10=70.0,
                    recall_confidence=0.8,
                    recall_alpha=85.0,
                    recall_matched_dna=stock_pattern_key,
                    recall_matched_context="k",
                ),
                "DNA_C": mock.Mock(
                    recall_source="RECALL_INDEX",
                    recall_level="FAMILY_CONTEXT",
                    recall_samples=15,
                    recall_t3_samples=15,
                    recall_t5_samples=15,
                    recall_t10_samples=15,
                    recall_mean_t3=3.0,
                    recall_mean_t5=3.0,
                    recall_mean_t10=3.0,
                    recall_win_rate_t3=60.0,
                    recall_win_rate_t5=60.0,
                    recall_win_rate_t10=60.0,
                    recall_confidence=0.5,
                    recall_alpha=70.0,
                    recall_matched_dna=stock_pattern_key,
                    recall_matched_context="k",
                ),
            }
            return mapping[stock_pattern_key]

        with mock.patch(
            "modules.regime_alpha_shadow.compute_recall_evidence",
            side_effect=_fake_recall,
        ):
            shadow = build_shadow_with_recall(
                rec,
                brain,
                exp,
                session_date="2026-08-08",
                recall_index=_empty_recall_index(),
                market_real=7.0,
                market_forecast=7.0,
            )

        self.assertEqual(int(shadow.iloc[0]["ShadowExperienceRank"]), 1)
        self.assertEqual(shadow.iloc[0]["symbol"], "BBB")
        self.assertEqual(int(shadow.loc[shadow["symbol"] == "AAA", "ProductionRank"].iloc[0]), 1)
        self.assertFalse(
            (shadow["ShadowExperienceRank"] == shadow["BaselineRank"]).all()
        )
        scores = shadow.sort_values("ShadowExperienceRank")["ShadowExperienceScore"].tolist()
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue((shadow["ShadowRank"] == shadow["ShadowExperienceRank"]).all())

    def test_csv_sorted_by_shadow_experience_rank(self):
        df = pd.DataFrame(
            [
                {
                    "session_date": "2026-08-08",
                    "rank": 2,
                    "ProductionRank": 2,
                    "ShadowRank": 2,
                    "symbol": "BBB",
                    "recommendation": "X",
                    "leader_score": 80,
                    "market_context_key": "k",
                    "stock_pattern_key": "DNA_B",
                    "TechnicalPrior": 70,
                    "BaselineScore": 70,
                    "BaselineRank": 2,
                    "ShadowExperienceScore": 80,
                    "ShadowExperienceRank": 2,
                    "ScoreDelta": 10,
                    "RankDelta": 0,
                    "ShadowMovement": "UNCHANGED",
                    "RecallSource": "RECALL_INDEX",
                    "RecallLevel": RECALL_LEVEL_NO_EVIDENCE,
                    "RecallSamples": 0,
                    "RecallT3Samples": 0,
                    "RecallT5Samples": 0,
                    "RecallT10Samples": 0,
                    "RecallMeanT3": None,
                    "RecallMeanT5": None,
                    "RecallMeanT10": None,
                    "RecallWinRateT3": None,
                    "RecallWinRateT5": None,
                    "RecallWinRateT10": None,
                    "RecallConfidence": 0.0,
                    "RecallAlpha": 50.0,
                    "RecallMatchedDNA": "DNA_B",
                    "RecallMatchedContext": "",
                    "ShadowReason": "test",
                    "updated_at": "2026-08-08",
                },
                {
                    "session_date": "2026-08-08",
                    "rank": 1,
                    "ProductionRank": 1,
                    "ShadowRank": 1,
                    "symbol": "AAA",
                    "recommendation": "X",
                    "leader_score": 90,
                    "market_context_key": "k",
                    "stock_pattern_key": "DNA_A",
                    "TechnicalPrior": 75,
                    "BaselineScore": 90,
                    "BaselineRank": 1,
                    "ShadowExperienceScore": 90,
                    "ShadowExperienceRank": 1,
                    "ScoreDelta": 0,
                    "RankDelta": 0,
                    "ShadowMovement": "UNCHANGED",
                    "RecallSource": "RECALL_INDEX",
                    "RecallLevel": RECALL_LEVEL_NO_EVIDENCE,
                    "RecallSamples": 0,
                    "RecallT3Samples": 0,
                    "RecallT5Samples": 0,
                    "RecallT10Samples": 0,
                    "RecallMeanT3": None,
                    "RecallMeanT5": None,
                    "RecallMeanT10": None,
                    "RecallWinRateT3": None,
                    "RecallWinRateT5": None,
                    "RecallWinRateT10": None,
                    "RecallConfidence": 0.0,
                    "RecallAlpha": 50.0,
                    "RecallMatchedDNA": "DNA_A",
                    "RecallMatchedContext": "",
                    "ShadowReason": "test",
                    "updated_at": "2026-08-08",
                },
            ]
        )
        out = _apply_shadow_experience_rerank(df.sort_values("BaselineRank"))
        self.assertListEqual(list(out["ShadowExperienceRank"]), [1, 2])
        self.assertListEqual(list(out["symbol"]), ["AAA", "BBB"])


class TestBuyEliteFinalDecisionUntouched(unittest.TestCase):
    def test_final_decision_output_unchanged_after_shadow_build(self):
        buy_elite = pd.DataFrame(
            [
                {
                    "MÃ": "AAA",
                    "KẾT LUẬN": "MUA ELITE",
                    "EliteScore": 88,
                    "EliteScoreBase": 85,
                    "WinProb": 72,
                    "ĐỘ TIN CẬY": "CAO",
                    "ĐỒNG THUẬN": "4/5",
                    "NHÓM": "CP MẠNH",
                    "GIÁ": 10.0,
                }
            ]
        )
        before_df, before_note = build_final_decision(buy_elite)
        rec = pd.DataFrame(
            [
                {
                    "rank": 1,
                    "symbol": "AAA",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 80,
                    "updated_at": "2026-08-08",
                }
            ]
        )
        brain = pd.DataFrame([_brain_row("AAA")])
        exp = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": "DNA_A",
                }
            ]
        )
        _ = build_shadow_with_recall(
            rec,
            brain,
            exp,
            session_date="2026-08-08",
            recall_index=_empty_recall_index(),
            market_real=7.0,
            market_forecast=7.0,
        )
        after_df, after_note = build_final_decision(buy_elite)
        pd.testing.assert_frame_equal(before_df, after_df)
        self.assertEqual(before_note, after_note)

    def test_app_has_no_shadow_in_buy_elite_path(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        text = app_path.read_text(encoding="utf-8")
        self.assertIn("render_shadow_observation_board", text)
        self.assertNotIn("build_shadow_with_recall", text.split("build_buy_elite_decision_engine")[0])


class TestShadowPersistenceIsolation(unittest.TestCase):
    def test_shadow_persist_writes_snapshot_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "ai_recommendation_shadow.csv"
            with mock.patch("modules.regime_alpha_shadow.SHADOW_SNAPSHOT_FILE", snap):
                shadow_df = pd.DataFrame(
                    [
                        {
                            "session_date": "2026-08-08",
                            "rank": 1,
                            "ProductionRank": 1,
                            "ShadowRank": 1,
                            "symbol": "AAA",
                            "recommendation": "THEO DÕI MUA",
                            "leader_score": 75,
                            "market_context_key": "6-8|40-60|6-8",
                            "stock_pattern_key": "DNA_A",
                            "TechnicalPrior": 70.0,
                            "BaselineScore": 70.0,
                            "BaselineRank": 1,
                            "ShadowExperienceScore": 70.0,
                            "ShadowExperienceRank": 1,
                            "ScoreDelta": 0.0,
                            "RankDelta": 0,
                            "ShadowMovement": "UNCHANGED",
                            "RecallSource": "RECALL_INDEX",
                            "RecallLevel": RECALL_LEVEL_NO_EVIDENCE,
                            "RecallSamples": 0,
                            "RecallT3Samples": 0,
                            "RecallT5Samples": 0,
                            "RecallT10Samples": 0,
                            "RecallMeanT3": None,
                            "RecallMeanT5": None,
                            "RecallMeanT10": None,
                            "RecallWinRateT3": None,
                            "RecallWinRateT5": None,
                            "RecallWinRateT10": None,
                            "RecallConfidence": 0.0,
                            "RecallAlpha": 50.0,
                            "RecallMatchedDNA": "DNA_A",
                            "RecallMatchedContext": "",
                            "ShadowReason": "test",
                            "updated_at": "2026-08-08",
                        }
                    ]
                )
                persist_shadow_audit(shadow_df, freeze_ledger=False)
            self.assertTrue(snap.exists())
            loaded = pd.read_csv(snap, encoding="utf-8-sig")
            self.assertIn("ProductionRank", loaded.columns)
            self.assertIn("ShadowRank", loaded.columns)


class TestCompileImport(unittest.TestCase):
    def test_compile_and_import(self):
        import py_compile

        base = Path(__file__).resolve().parents[1]
        py_compile.compile(str(base / "modules" / "regime_alpha_shadow.py"), doraise=True)
        import modules.regime_alpha_shadow as sh

        self.assertIn("build_shadow_with_recall", sh.__all__)
        self.assertIn("ProductionRank", sh.SHADOW_COLUMNS)


if __name__ == "__main__":
    unittest.main()
