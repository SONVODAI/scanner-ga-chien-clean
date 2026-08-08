"""N3.7B immutable forward-evaluation ledger tests."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from leader_memory import RECOMMENDATION_COLUMNS, _build_recommendations
from modules.regime_alpha_forward_eval import (
    EVAL_MODE_FORWARD_FROZEN,
    EVAL_MODE_RECONSTRUCTED_AUDIT,
    IMMUTABLE_T0_FIELDS,
    LEDGER_COLUMNS,
    OUTCOME_COLUMNS,
    classify_movement_class,
    evaluate_forward_scorecard,
    evaluate_regime_scorecard,
    freeze_t0_ledger,
    load_forward_ledger,
    load_forward_outcomes,
    make_snapshot_id,
    mature_forward_outcomes,
)
from modules.regime_alpha_shadow import build_shadow_with_recall, persist_shadow_audit


def _sample_shadow(rec: pd.DataFrame, brain: pd.DataFrame, exp: pd.DataFrame, session: str):
    return build_shadow_with_recall(
        rec, brain, exp, session_date=session, recall_index=pd.DataFrame()
    )


class TestForwardLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.ledger_path = self.tmp_path / "ledger.csv"
        self.outcomes_path = self.tmp_path / "outcomes.csv"

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
        self.shadow = _sample_shadow(rec, brain, exp, "2026-08-10")
        self.shadow.loc[self.shadow["symbol"] == "AAA", "RecallConfidence"] = 0.175
        self.shadow.loc[self.shadow["symbol"] == "AAA", "RecallAlpha"] = 55.0
        self.shadow.loc[self.shadow["symbol"] == "AAA", "ScoreDelta"] = 2.5
        self.shadow.loc[self.shadow["symbol"] == "AAA", "ShadowExperienceScore"] = (
            self.shadow.loc[self.shadow["symbol"] == "AAA", "BaselineScore"] + 2.5
        )
        self.shadow["movement_class"] = self.shadow.apply(classify_movement_class, axis=1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_idempotent_t0_persistence(self):
        first = freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        second = freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)

    def test_b_t0_immutable_when_outcomes_change(self):
        freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        before = load_forward_ledger(ledger_path=self.ledger_path).copy()

        lifecycle = pd.DataFrame(
            [
                {
                    "observation_id": "obs-aaa",
                    "symbol": "AAA",
                    "trade_date": "2026-08-10",
                    "t3_return_pct": 1.5,
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

        changed_shadow = self.shadow.copy()
        changed_shadow.loc[
            changed_shadow["symbol"] == "AAA", "BaselineScore"
        ] = 999.0
        changed_shadow.loc[
            changed_shadow["symbol"] == "AAA", "RecallAlpha"
        ] = 999.0
        freeze_t0_ledger(
            changed_shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        after = load_forward_ledger(ledger_path=self.ledger_path)
        aaa_before = before[before["symbol"] == "AAA"].iloc[0]
        aaa_after = after[after["symbol"] == "AAA"].iloc[0]
        self.assertEqual(float(aaa_before["BaselineScore"]), float(aaa_after["BaselineScore"]))
        self.assertEqual(float(aaa_before["RecallAlpha"]), float(aaa_after["RecallAlpha"]))

    def test_c_mature_t3_only(self):
        freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        lifecycle = pd.DataFrame(
            [
                {
                    "observation_id": "obs-aaa",
                    "symbol": "AAA",
                    "trade_date": "2026-08-10",
                    "t3_return_pct": 2.0,
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
        row = out[out["symbol"] == "AAA"].iloc[0]
        self.assertEqual(row["outcome_status_t3"], "READY")
        self.assertEqual(float(row["ActualT3Return"]), 2.0)
        self.assertEqual(row["outcome_status_t5"], "PENDING")
        self.assertEqual(row["outcome_status_t10"], "PENDING")

    def test_d_mature_t5_later_preserves_t3(self):
        freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        lifecycle_t3 = pd.DataFrame(
            [
                {
                    "observation_id": "obs-aaa",
                    "symbol": "AAA",
                    "trade_date": "2026-08-10",
                    "t3_return_pct": 2.0,
                    "t5_return_pct": None,
                    "t10_return_pct": None,
                }
            ]
        )
        mature_forward_outcomes(
            ledger_path=self.ledger_path,
            outcomes_path=self.outcomes_path,
            lifecycle=lifecycle_t3,
        )
        lifecycle_t5 = pd.DataFrame(
            [
                {
                    "observation_id": "obs-aaa",
                    "symbol": "AAA",
                    "trade_date": "2026-08-10",
                    "t3_return_pct": 2.0,
                    "t5_return_pct": 3.5,
                    "t10_return_pct": None,
                }
            ]
        )
        mature_forward_outcomes(
            ledger_path=self.ledger_path,
            outcomes_path=self.outcomes_path,
            lifecycle=lifecycle_t5,
        )
        out = load_forward_outcomes(self.outcomes_path)
        row = out[out["symbol"] == "AAA"].iloc[0]
        self.assertEqual(float(row["ActualT3Return"]), 2.0)
        self.assertEqual(row["outcome_status_t5"], "READY")
        self.assertEqual(float(row["ActualT5Return"]), 3.5)
        self.assertEqual(row["outcome_status_t10"], "PENDING")

    def test_e_mature_t10_later_preserves_t3_t5(self):
        freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        lifecycle = pd.DataFrame(
            [
                {
                    "observation_id": "obs-aaa",
                    "symbol": "AAA",
                    "trade_date": "2026-08-10",
                    "t3_return_pct": 2.0,
                    "t5_return_pct": 3.5,
                    "t10_return_pct": 4.0,
                }
            ]
        )
        mature_forward_outcomes(
            ledger_path=self.ledger_path,
            outcomes_path=self.outcomes_path,
            lifecycle=pd.DataFrame(
                [
                    {
                        "observation_id": "obs-aaa",
                        "symbol": "AAA",
                        "trade_date": "2026-08-10",
                        "t3_return_pct": 2.0,
                        "t5_return_pct": None,
                        "t10_return_pct": None,
                    }
                ]
            ),
        )
        mature_forward_outcomes(
            ledger_path=self.ledger_path,
            outcomes_path=self.outcomes_path,
            lifecycle=pd.DataFrame(
                [
                    {
                        "observation_id": "obs-aaa",
                        "symbol": "AAA",
                        "trade_date": "2026-08-10",
                        "t3_return_pct": 2.0,
                        "t5_return_pct": 3.5,
                        "t10_return_pct": None,
                    }
                ]
            ),
        )
        mature_forward_outcomes(
            ledger_path=self.ledger_path,
            outcomes_path=self.outcomes_path,
            lifecycle=lifecycle,
        )
        out = load_forward_outcomes(self.outcomes_path)
        row = out[out["symbol"] == "AAA"].iloc[0]
        self.assertEqual(float(row["ActualT3Return"]), 2.0)
        self.assertEqual(float(row["ActualT5Return"]), 3.5)
        self.assertEqual(float(row["ActualT10Return"]), 4.0)

    def test_f_no_duplicate_t0_identities(self):
        freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        ledger = load_forward_ledger(ledger_path=self.ledger_path)
        keys = list(zip(ledger["session_date"], ledger["symbol"]))
        self.assertEqual(len(keys), len(set(keys)))

    def test_g_no_duplicate_outcome_identities(self):
        freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        lifecycle = pd.DataFrame(
            [
                {
                    "observation_id": "obs-aaa",
                    "symbol": "AAA",
                    "trade_date": "2026-08-10",
                    "t3_return_pct": 1.0,
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
        mature_forward_outcomes(
            ledger_path=self.ledger_path,
            outcomes_path=self.outcomes_path,
            lifecycle=lifecycle,
        )
        out = load_forward_outcomes(self.outcomes_path)
        self.assertEqual(out["snapshot_id"].nunique(), len(out))

    def test_snapshot_id_deterministic(self):
        sid1 = make_snapshot_id("2026-08-10", "AAA")
        sid2 = make_snapshot_id("2026-08-10", "AAA")
        self.assertEqual(sid1, sid2)
        self.assertNotEqual(sid1, make_snapshot_id("2026-08-10", "BBB"))

    def test_reconstructed_audit_separate_from_forward(self):
        freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        audit = self.shadow.copy()
        audit.loc[audit["symbol"] == "AAA", "BaselineScore"] = 777.0
        freeze_t0_ledger(
            audit,
            evaluation_mode=EVAL_MODE_RECONSTRUCTED_AUDIT,
            ledger_path=self.ledger_path,
        )
        ledger = pd.read_csv(self.ledger_path, encoding="utf-8-sig")
        forward = ledger[ledger["evaluation_mode"] == EVAL_MODE_FORWARD_FROZEN]
        recon = ledger[ledger["evaluation_mode"] == EVAL_MODE_RECONSTRUCTED_AUDIT]
        self.assertEqual(len(forward), 2)
        self.assertEqual(len(recon), 2)
        self.assertNotEqual(
            float(forward[forward["symbol"] == "AAA"]["BaselineScore"].iloc[0]),
            777.0,
        )

    def test_corporate_action_flag(self):
        freeze_t0_ledger(
            self.shadow,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        lifecycle = pd.DataFrame(
            [
                {
                    "observation_id": "obs-aaa",
                    "symbol": "AAA",
                    "trade_date": "2026-08-10",
                    "t3_return_pct": 30.0,
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
        flag = out[out["symbol"] == "AAA"]["corporate_action_flag"].iloc[0]
        self.assertIn("SUSPECT", str(flag))


class TestScorecardReader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.ledger_path = self.tmp_path / "ledger.csv"
        self.outcomes_path = self.tmp_path / "outcomes.csv"

        rows = []
        for i, sym in enumerate(["S1", "S2", "S3", "S4", "S5"], start=1):
            rows.append(
                {
                    "session_date": "2026-08-10",
                    "rank": i,
                    "symbol": sym,
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 80 - i,
                    "market_context_key": "NA|NA|6-8",
                    "stock_pattern_key": f"DNA_{sym}",
                    "TechnicalPrior": 60.0,
                    "BaselineScore": 40.0 - i * 0.1,
                    "BaselineRank": i,
                    "ShadowExperienceScore": 40.0 - i * 0.2,
                    "ShadowExperienceRank": i,
                    "ScoreDelta": 0.0,
                    "RankDelta": 0,
                    "ShadowMovement": "UNCHANGED",
                    "RecallSource": "RECALL_INDEX",
                    "RecallLevel": "GLOBAL_DNA",
                    "RecallSamples": 10,
                    "RecallT3Samples": 10,
                    "RecallT5Samples": 10,
                    "RecallT10Samples": 10,
                    "RecallMeanT3": 1.0,
                    "RecallMeanT5": 1.0,
                    "RecallMeanT10": 1.0,
                    "RecallWinRateT3": 60.0,
                    "RecallWinRateT5": 60.0,
                    "RecallWinRateT10": 60.0,
                    "RecallConfidence": 0.0,
                    "RecallAlpha": 50.0,
                    "RecallMatchedDNA": f"DNA_{sym}",
                    "RecallMatchedContext": "NA|NA|6-8",
                    "ShadowReason": "test",
                    "updated_at": "2026-08-10",
                    "snapshot_id": make_snapshot_id("2026-08-10", sym),
                    "frozen_at": "2026-08-10T12:00:00+00:00",
                    "ledger_version": "1.0.0",
                    "evaluation_mode": EVAL_MODE_FORWARD_FROZEN,
                    "movement_class": "UNCHANGED",
                    "observation_id": "",
                }
            )
        ledger = pd.DataFrame(rows, columns=list(LEDGER_COLUMNS))
        ledger.to_csv(self.ledger_path, index=False, encoding="utf-8-sig")

        outcomes = []
        for i, sym in enumerate(["S1", "S2", "S3", "S4", "S5"], start=1):
            outcomes.append(
                {
                    "session_date": "2026-08-10",
                    "symbol": sym,
                    "snapshot_id": make_snapshot_id("2026-08-10", sym),
                    "observation_id": "",
                    "ActualT3Return": float(i),
                    "ActualT5Return": float(i),
                    "ActualT10Return": float(i),
                    "outcome_status_t3": "READY",
                    "outcome_status_t5": "READY",
                    "outcome_status_t10": "READY",
                    "matured_at_t3": "2026-08-13",
                    "matured_at_t5": "2026-08-15",
                    "matured_at_t10": "2026-08-20",
                    "corporate_action_flag": "",
                    "outcome_version": "1.0.0",
                }
            )
        pd.DataFrame(outcomes, columns=list(OUTCOME_COLUMNS)).to_csv(
            self.outcomes_path, index=False, encoding="utf-8-sig"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_scorecard_top_n_and_lift(self):
        card = evaluate_forward_scorecard(
            ledger_path=self.ledger_path,
            outcomes_path=self.outcomes_path,
        )
        self.assertEqual(card.candidates, 5)
        self.assertIsNotNone(card.baseline_top5.mean_t3)
        self.assertIsNotNone(card.shadow_top5.mean_t3)
        self.assertIsNotNone(card.learning_lift_top10_mean_t3)

    def test_regime_scorecard_global_label(self):
        result = evaluate_regime_scorecard(
            market_context_key="NA|NA|6-8",
            ledger_path=self.ledger_path,
            outcomes_path=self.outcomes_path,
        )
        self.assertIn("CONTEXT_FREE_PRIOR", result["regime_label"])


class TestProductionImmutability(unittest.TestCase):
    DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "earning_learning"

    def test_production_columns_unchanged(self):
        rec, brain, exp = self._sample()
        before = rec.copy()
        shadow = build_shadow_with_recall(rec, brain, exp, session_date="2026-08-10")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.csv"
            outcomes = Path(tmp) / "outcomes.csv"
            freeze_t0_ledger(
                shadow,
                evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
                ledger_path=ledger,
            )
        pd.testing.assert_frame_equal(before, rec)
        self.assertListEqual(list(rec.columns), list(RECOMMENDATION_COLUMNS))

    def test_source_files_not_modified_by_persist(self):
        targets = [
            "observations.csv",
            "pattern_lifecycle.csv",
            "pattern_knowledge.csv",
            "continuation_knowledge.csv",
            "regime_recall_index.csv",
        ]
        before = {}
        for name in targets:
            path = self.DATA_DIR / name
            if path.exists():
                h = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
                before[name] = h

        rec, brain, exp = self._sample()
        shadow = build_shadow_with_recall(rec, brain, exp, session_date="2026-08-10")
        with tempfile.TemporaryDirectory() as tmp:
            from modules.regime_alpha_forward_eval import LEDGER_FILE, OUTCOMES_FILE
            import modules.regime_alpha_forward_eval as fe

            old_ledger = fe.LEDGER_FILE
            old_outcomes = fe.OUTCOMES_FILE
            fe.LEDGER_FILE = Path(tmp) / "ledger.csv"
            fe.OUTCOMES_FILE = Path(tmp) / "outcomes.csv"
            try:
                persist_shadow_audit(
                    shadow,
                    evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
                    freeze_ledger=True,
                    mature_outcomes=True,
                )
            finally:
                fe.LEDGER_FILE = old_ledger
                fe.OUTCOMES_FILE = old_outcomes

        for name, h in before.items():
            path = self.DATA_DIR / name
            after = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            self.assertEqual(h, after, msg=f"{name} changed")

    def _sample(self):
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
                }
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
                }
            ]
        )
        rec = _build_recommendations(
            brain, patterns, {"max_recommendation_rows": 100}, experience_df=exp
        )
        return rec, brain, exp


class TestImmutableFieldList(unittest.TestCase):
    def test_immutable_fields_present_in_ledger_schema(self):
        for field in IMMUTABLE_T0_FIELDS:
            self.assertIn(field, LEDGER_COLUMNS)


if __name__ == "__main__":
    unittest.main()
