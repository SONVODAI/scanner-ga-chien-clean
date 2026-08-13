"""N3.7C canonical forward snapshot freeze tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from leader_memory import RECOMMENDATION_COLUMNS, _build_recommendations, _persist_recommendation_shadow
from modules.regime_alpha_forward_eval import (
    EVAL_MODE_FORWARD_FROZEN,
    finalize_forward_shadow_snapshot,
    freeze_t0_ledger,
    is_trading_session_valid,
    load_forward_ledger,
    load_forward_outcomes,
    mature_forward_outcomes,
)
from modules.regime_alpha_shadow import build_shadow_with_recall, persist_shadow_audit


def _sample_bundle(session: str = "2026-08-11"):
    brain = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "recommendation": "ƯU TIÊN CAO",
                "leader_score": 80,
                "confidence_score": 55,
                "current_rsi14": 58,
                "current_obv_status": "UP",
                "persistence_20_pct": 60,
                "winrate_t5_pct": 65,
                "current_group": "CP MẠNH",
                "feature_signature": "demo",
            },
            {
                "symbol": "BBB",
                "recommendation": "THEO DÕI MUA",
                "leader_score": 79,
                "confidence_score": 50,
                "current_rsi14": 55,
                "current_obv_status": "UP",
                "persistence_20_pct": 55,
                "winrate_t5_pct": 60,
                "current_group": "PULL ĐẸP",
                "feature_signature": "demo",
            },
        ]
    )
    patterns = pd.DataFrame(
        [{"pattern_id": "p1", "feature_signature": "demo", "pattern_score": 70}]
    )
    exp = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "market_context_key": "6-8|40-60|6-8",
                "stock_pattern_key": "DNA_A",
                "ExperienceAdjustment": 0,
            },
            {
                "symbol": "BBB",
                "market_context_key": "6-8|40-60|6-8",
                "stock_pattern_key": "DNA_B",
                "ExperienceAdjustment": 0,
            },
        ]
    )
    rec = _build_recommendations(
        brain, patterns, {"max_recommendation_rows": 100}, experience_df=exp
    )
    shadow = build_shadow_with_recall(
        rec, brain, exp, session_date=session, recall_index=pd.DataFrame()
    )
    return rec, brain, exp, shadow


class TestLiveVsFrozenSeparation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.ledger_path = self.tmp_path / "ledger.csv"
        self.outcomes_path = self.tmp_path / "outcomes.csv"
        self.snapshot_path = self.tmp_path / "live_shadow.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_intraday_persist_does_not_freeze(self):
        _, _, _, shadow = _sample_bundle()
        persist_shadow_audit(
            shadow,
            freeze_ledger=False,
            mature_outcomes=False,
        )
        ledger = load_forward_ledger(ledger_path=self.ledger_path)
        self.assertEqual(len(ledger), 0)

    def test_b_intraday_rank_change_still_no_freeze(self):
        _, _, _, shadow1 = _sample_bundle()
        persist_shadow_audit(shadow1, freeze_ledger=False)
        self.assertEqual(len(load_forward_ledger(ledger_path=self.ledger_path)), 0)

        shadow2 = shadow1.copy()
        shadow2.loc[shadow2["symbol"] == "AAA", "BaselineScore"] = 99.0
        persist_shadow_audit(shadow2, freeze_ledger=False)
        self.assertEqual(len(load_forward_ledger(ledger_path=self.ledger_path)), 0)

    def test_c_canonical_finalization_freezes_once(self):
        _, _, _, shadow = _sample_bundle("2026-08-11")
        freeze_t0_ledger(
            shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        ledger = load_forward_ledger(ledger_path=self.ledger_path)
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger["session_date"].nunique(), 1)

    def test_d_post_finalization_immutable(self):
        _, _, _, shadow = _sample_bundle("2026-08-11")
        freeze_t0_ledger(
            shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        before = load_forward_ledger(ledger_path=self.ledger_path)
        changed = shadow.copy()
        changed.loc[changed["symbol"] == "AAA", "RecallAlpha"] = 999.0
        freeze_t0_ledger(
            changed,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        after = load_forward_ledger(ledger_path=self.ledger_path)
        self.assertEqual(
            float(before[before["symbol"] == "AAA"]["RecallAlpha"].iloc[0]),
            float(after[after["symbol"] == "AAA"]["RecallAlpha"].iloc[0]),
        )

    def test_e_repeated_finalization_no_duplicates(self):
        _, _, _, shadow = _sample_bundle("2026-08-11")
        freeze_t0_ledger(shadow, ledger_path=self.ledger_path)
        freeze_t0_ledger(shadow, ledger_path=self.ledger_path)
        ledger = load_forward_ledger(ledger_path=self.ledger_path)
        self.assertEqual(len(ledger), 2)

    def test_f_weekend_skips_forward_freeze(self):
        valid, reason = is_trading_session_valid(
            "2026-08-08",
            market_real=7.0,
            trading_today=True,
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "weekend_session")

    def test_g_outcome_maturation_after_finalize(self):
        _, _, _, shadow = _sample_bundle("2026-08-11")
        freeze_t0_ledger(shadow, ledger_path=self.ledger_path)
        lifecycle = pd.DataFrame(
            [
                {
                    "observation_id": "obs-aaa",
                    "symbol": "AAA",
                    "trade_date": "2026-08-11",
                    "t3_return_pct": 1.2,
                    "t5_return_pct": None,
                    "t10_return_pct": None,
                }
            ]
        )
        mature_forward_outcomes(
            ledger_path=self.ledger_path,
            outcomes_path=self.outcomes_path,
            lifecycle=lifecycle,
        )
        out = load_forward_outcomes(self.outcomes_path)
        self.assertEqual(out.loc[out["symbol"] == "AAA", "outcome_status_t3"].iloc[0], "READY")
        self.assertEqual(out.loc[out["symbol"] == "AAA", "outcome_status_t5"].iloc[0], "PENDING")


class TestFinalizeIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @mock.patch("modules.regime_alpha_shadow.build_shadow_with_recall")
    @mock.patch("leader_memory.load_recommendations")
    @mock.patch("leader_memory._safe_read_csv")
    @mock.patch("leader_memory._build_experience_frame")
    @mock.patch("leader_memory._latest_session_experience_snapshot")
    def test_finalize_reads_persisted_state(
        self,
        mock_snapshot,
        mock_experience,
        mock_read_csv,
        mock_load_rec,
        mock_build_shadow,
    ):
        rec, brain, exp, shadow = _sample_bundle("2026-08-12")
        mock_load_rec.return_value = rec
        mock_read_csv.return_value = brain
        mock_snapshot.return_value = pd.DataFrame({"symbol": ["AAA"], "session_date": "2026-08-12"})
        mock_experience.return_value = exp
        mock_build_shadow.return_value = shadow

        ledger_path = self.tmp_path / "ledger.csv"
        result = finalize_forward_shadow_snapshot(
            session_date="2026-08-12",
            trading_today=True,
            market_real=7.0,
            ledger_path=ledger_path,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["frozen_rows"], 2)

    @mock.patch("modules.regime_alpha_forward_eval.mature_forward_outcomes")
    @mock.patch("modules.regime_alpha_shadow.build_shadow_with_recall")
    @mock.patch("leader_memory.load_recommendations")
    @mock.patch("leader_memory._safe_read_csv")
    @mock.patch("leader_memory._build_experience_frame")
    @mock.patch("leader_memory._latest_session_experience_snapshot")
    def test_finalize_prefers_runtime_recommendations(
        self,
        mock_snapshot,
        mock_experience,
        mock_read_csv,
        mock_load_rec,
        mock_build_shadow,
        mock_mature,
    ):
        rec, brain, exp, shadow = _sample_bundle("2026-08-12")
        mock_load_rec.side_effect = AssertionError("disk fallback should not run")
        mock_read_csv.return_value = brain
        mock_snapshot.return_value = pd.DataFrame({"symbol": ["AAA"], "session_date": "2026-08-12"})
        mock_experience.return_value = exp
        mock_build_shadow.return_value = shadow

        ledger_path = self.tmp_path / "ledger.csv"
        result = finalize_forward_shadow_snapshot(
            session_date="2026-08-12",
            trading_today=True,
            market_real=7.0,
            recommendations=rec,
            ledger_path=ledger_path,
        )

        self.assertTrue(result["ok"])
        mock_mature.assert_not_called()

    def test_non_trading_day_finalize_skipped(self):
        ledger_path = self.tmp_path / "ledger.csv"
        result = finalize_forward_shadow_snapshot(
            session_date="2026-08-09",
            trading_today=False,
            market_real=7.0,
            ledger_path=ledger_path,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(len(load_forward_ledger(ledger_path=ledger_path)), 0)


class TestProductionUnchanged(unittest.TestCase):
    def test_persist_recommendation_shadow_does_not_freeze(self):
        rec, brain, exp, _ = _sample_bundle()
        before = rec.copy()
        import modules.regime_alpha_forward_eval as fe

        old_ledger = Path(tempfile.mkdtemp()) / "ledger.csv"
        fe.LEDGER_FILE = old_ledger
        try:
            _persist_recommendation_shadow(rec, brain, exp, session_date="2026-08-11")
        finally:
            pass
        pd.testing.assert_frame_equal(before, rec)
        self.assertListEqual(list(rec.columns), list(RECOMMENDATION_COLUMNS))
        self.assertFalse(old_ledger.exists())


if __name__ == "__main__":
    unittest.main()
