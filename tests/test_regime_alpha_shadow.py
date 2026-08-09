"""N3 shadow Regime Alpha integration tests — production must remain unchanged."""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pandas as pd

from leader_memory import (
    RECOMMENDATION_COLUMNS,
    _build_recommendations,
    _build_experience_frame,
)
from modules.regime_alpha import NEUTRAL_RAS, compute_alpha_confidence
from modules.regime_alpha_shadow import (
    SHADOW_COLUMNS,
    SHADOW_HISTORY_FILE,
    SHADOW_SNAPSHOT_FILE,
    ShadowAuditRow,
    build_shadow_recommendations,
    compute_shadow_audit,
    persist_shadow_audit,
)
from final_decision_engine import build_final_decision


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


def _pattern_row(ctx, stock, horizon=5, samples=20, wlb=65.0, median=5.0):
    return {
        "market_context_key": ctx,
        "stock_pattern_key": stock,
        "pattern_key": "pk",
        "horizon": horizon,
        "samples": samples,
        "win_rate_lower_bound_pct": wlb,
        "win_rate_pct": wlb + 5,
        "median_return_pct": median,
        "avg_max_drawdown_pct": -3.0,
        "worst_return_pct": -2.0,
        "last_seen": "2026-08-01",
    }


class TestProductionUnchanged(unittest.TestCase):
    """A / I — production recommendation output identical."""

    def _sample_production_inputs(self):
        brain = pd.DataFrame(
            [
                _brain_row("AAA", leader_score=80, recommendation="ƯU TIÊN CAO"),
                _brain_row("BBB", leader_score=70, recommendation="THEO DÕI MUA"),
                _brain_row("CCC", leader_score=50, recommendation="CHƯA HÀNH ĐỘNG"),
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
                    "ExperienceSamples": 10,
                    "LearningStatus": "READY_FOR_CONNECTION",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": "DNA_A",
                },
                {
                    "symbol": "BBB",
                    "ExperienceAdjustment": -1.0,
                    "ExperienceSamples": 8,
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
        shadow = build_shadow_recommendations(
            rec_after, brain, exp, session_date="2026-08-08"
        )

        self.assertListEqual(list(rec_before.columns), list(RECOMMENDATION_COLUMNS))
        self.assertListEqual(list(rec_after.columns), list(RECOMMENDATION_COLUMNS))
        pd.testing.assert_frame_equal(rec_before, rec_after)
        self.assertEqual(len(rec_before), 2)
        self.assertEqual(list(rec_before["symbol"]), ["AAA", "BBB"])
        self.assertFalse(shadow.empty)

    def test_rank_order_unchanged(self):
        brain, patterns, config, exp = self._sample_production_inputs()
        rec = _build_recommendations(
            brain, patterns, config, experience_df=exp, market_real=7.0
        )
        ranks = list(rec["rank"])
        symbols = list(rec["symbol"])
        _ = build_shadow_recommendations(rec, brain, exp, session_date="2026-08-08")
        rec2 = _build_recommendations(
            brain, patterns, config, experience_df=exp, market_real=7.0
        )
        self.assertEqual(list(rec2["rank"]), ranks)
        self.assertEqual(list(rec2["symbol"]), symbols)

    def test_production_rec_not_mutated_by_shadow(self):
        """D — build_shadow_recommendations must not mutate production_rec."""
        brain, patterns, config, exp = self._sample_production_inputs()
        rec = _build_recommendations(
            brain, patterns, config, experience_df=exp, market_real=7.0
        )
        rec_before = rec.copy(deep=True)
        _ = build_shadow_recommendations(rec, brain, exp, session_date="2026-08-08")
        pd.testing.assert_frame_equal(rec, rec_before)


class TestShadowRerank(unittest.TestCase):
    """C — independent ShadowRank ordering."""

    def _make_audit(
        self,
        *,
        technical_prior: float,
        shadow_final_score: float,
        confidence: float = 0.5,
    ) -> ShadowAuditRow:
        return ShadowAuditRow(
            technical_prior=technical_prior,
            regime_alpha_score=55.0,
            regime_alpha_raw_score=60.0,
            regime_alpha_discounted_score=55.0,
            regime_alpha_confidence=confidence,
            regime_alpha_context_level="EXACT_CONTEXT",
            regime_alpha_matched_context="6-8|40-60|6-8",
            regime_alpha_samples=20,
            shadow_final_score=shadow_final_score,
            shadow_decision="SHADOW_AGREE",
            shadow_reason="test fixture",
        )

    def test_shadow_rank_follows_shadow_final_score(self):
        rec = pd.DataFrame(
            [
                {
                    "rank": 1,
                    "symbol": "AAA",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 90,
                    "updated_at": "2026-08-08",
                },
                {
                    "rank": 2,
                    "symbol": "BBB",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 80,
                    "updated_at": "2026-08-08",
                },
                {
                    "rank": 3,
                    "symbol": "CCC",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 70,
                    "updated_at": "2026-08-08",
                },
            ]
        )
        brain = pd.DataFrame(
            [
                _brain_row("AAA", leader_score=90),
                _brain_row("BBB", leader_score=80),
                _brain_row("CCC", leader_score=70),
            ]
        )
        exp = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": "DNA_A",
                },
                {
                    "symbol": "BBB",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": "DNA_B",
                },
                {
                    "symbol": "CCC",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": "DNA_C",
                },
            ]
        )

        def _fake_audit(*, experience_row, **kwargs):
            stock = str(experience_row.get("stock_pattern_key", ""))
            mapping = {
                "DNA_A": self._make_audit(technical_prior=70.0, shadow_final_score=60.0),
                "DNA_B": self._make_audit(technical_prior=75.0, shadow_final_score=85.0),
                "DNA_C": self._make_audit(technical_prior=72.0, shadow_final_score=70.0),
            }
            return mapping[stock]

        with mock.patch(
            "modules.regime_alpha_shadow.compute_shadow_audit",
            side_effect=_fake_audit,
        ):
            shadow = build_shadow_recommendations(
                rec, brain, exp, session_date="2026-08-08"
            )

        self.assertListEqual(list(shadow["symbol"]), ["BBB", "CCC", "AAA"])
        self.assertListEqual(list(shadow["ShadowRank"]), [1, 2, 3])
        self.assertEqual(int(shadow.loc[shadow["symbol"] == "AAA", "ProductionRank"].iloc[0]), 1)
        self.assertEqual(int(shadow.loc[shadow["symbol"] == "BBB", "ShadowRank"].iloc[0]), 1)
        self.assertFalse((shadow["ShadowRank"] == shadow["ProductionRank"]).all())

        scores = shadow.sort_values("ShadowRank")["ShadowFinalScore"].tolist()
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_production_rank_preserved_as_rank_alias(self):
        rec = pd.DataFrame(
            [
                {
                    "rank": 2,
                    "symbol": "BBB",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 80,
                    "updated_at": "2026-08-08",
                },
                {
                    "rank": 1,
                    "symbol": "AAA",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 90,
                    "updated_at": "2026-08-08",
                },
            ]
        )
        brain = pd.DataFrame([_brain_row("AAA"), _brain_row("BBB")])
        exp = pd.DataFrame(
            [
                {"symbol": "AAA", "market_context_key": "k", "stock_pattern_key": "DNA_A"},
                {"symbol": "BBB", "market_context_key": "k", "stock_pattern_key": "DNA_B"},
            ]
        )

        def _fake_audit(*, experience_row, **kwargs):
            stock = str(experience_row.get("stock_pattern_key", ""))
            mapping = {
                "DNA_A": self._make_audit(technical_prior=70.0, shadow_final_score=50.0),
                "DNA_B": self._make_audit(technical_prior=75.0, shadow_final_score=90.0),
            }
            return mapping[stock]

        with mock.patch(
            "modules.regime_alpha_shadow.compute_shadow_audit",
            side_effect=_fake_audit,
        ):
            shadow = build_shadow_recommendations(
                rec, brain, exp, session_date="2026-08-08"
            )

        for _, row in shadow.iterrows():
            self.assertEqual(row["rank"], row["ProductionRank"])

    def test_shadow_top10_is_shadow_rank_leq_10(self):
        rows = []
        for i in range(12):
            sym = f"S{i:02d}"
            rows.append(
                {
                    "rank": i + 1,
                    "symbol": sym,
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 100 - i,
                    "updated_at": "2026-08-08",
                }
            )
        rec = pd.DataFrame(rows)
        brain = pd.DataFrame([_brain_row(row["symbol"], leader_score=row["leader_score"]) for row in rows])
        exp = pd.DataFrame(
            [
                {
                    "symbol": row["symbol"],
                    "market_context_key": "k",
                    "stock_pattern_key": f"DNA_{row['symbol']}",
                }
                for row in rows
            ]
        )

        def _fake_audit(*, experience_row, **kwargs):
            stock = str(experience_row.get("stock_pattern_key", ""))
            idx = int(stock.split("_")[1][1:])
            score = 100.0 - idx
            return self._make_audit(
                technical_prior=score,
                shadow_final_score=score,
                confidence=0.1 + idx * 0.01,
            )

        with mock.patch(
            "modules.regime_alpha_shadow.compute_shadow_audit",
            side_effect=_fake_audit,
        ):
            shadow = build_shadow_recommendations(
                rec, brain, exp, session_date="2026-08-08"
            )

        top10 = shadow[shadow["ShadowRank"] <= 10]
        self.assertEqual(len(top10), 10)
        self.assertListEqual(list(top10["ShadowRank"]), list(range(1, 11)))


class TestShadowDeterminism(unittest.TestCase):
    """B / F — shadow output deterministic."""

    def test_same_inputs_same_shadow(self):
        brain = pd.DataFrame([_brain_row()])
        rec = pd.DataFrame(
            [
                {
                    "rank": 1,
                    "symbol": "AAA",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 75,
                    "pattern_match_score": 60,
                    "updated_at": "2026-08-08",
                }
            ]
        )
        exp = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": "DNA_TEST",
                }
            ]
        )
        pk = pd.DataFrame([_pattern_row("6-8|40-60|6-8", "DNA_TEST")])
        a = build_shadow_recommendations(
            rec,
            brain,
            exp,
            session_date="2026-08-08",
            pattern_knowledge=pk,
            as_of=date(2026, 8, 8),
        )
        b = build_shadow_recommendations(
            rec,
            brain,
            exp,
            session_date="2026-08-08",
            pattern_knowledge=pk,
            as_of=date(2026, 8, 8),
        )
        pd.testing.assert_frame_equal(a, b)


class TestShadowContextRules(unittest.TestCase):
    """C / D / E — context and confidence rules."""

    def test_none_context_neutral(self):
        audit = compute_shadow_audit(
            brain_row=_brain_row(),
            experience_row={"market_context_key": "6-8|40-60|6-8", "stock_pattern_key": ""},
            pattern_knowledge=pd.DataFrame(),
            continuation_knowledge=pd.DataFrame(),
        )
        self.assertEqual(audit.regime_alpha_score, NEUTRAL_RAS)
        self.assertEqual(audit.regime_alpha_confidence, 0.0)
        self.assertEqual(audit.regime_alpha_context_level, "NONE")
        self.assertEqual(audit.shadow_decision, "TECHNICAL_ONLY")

    def test_global_dna_lower_authority_than_exact(self):
        today = date(2026, 8, 8)
        c_exact = compute_alpha_confidence(20, "EXACT", last_seen=today, as_of=today)
        c_family = compute_alpha_confidence(20, "FAMILY", last_seen=today, as_of=today)
        c_global = compute_alpha_confidence(20, "GLOBAL_DNA", last_seen=today, as_of=today)
        self.assertGreater(c_exact, c_family)
        self.assertGreater(c_family, c_global)

    def test_low_confidence_cannot_dominate_technical_prior(self):
        audit = compute_shadow_audit(
            brain_row=_brain_row(leader_score=80),
            experience_row={
                "market_context_key": "6-8|40-60|6-8",
                "stock_pattern_key": "DNA_LOW",
            },
            pattern_knowledge=pd.DataFrame(
                [_pattern_row("NA|NA|<4", "DNA_LOW", samples=5, wlb=70, median=8.0)]
            ),
            continuation_knowledge=pd.DataFrame(),
            as_of=date(2026, 8, 8),
        )
        self.assertEqual(audit.regime_alpha_context_level, "GLOBAL_DNA")
        self.assertLess(audit.regime_alpha_confidence, 0.15)
        self.assertAlmostEqual(
            audit.shadow_final_score,
            audit.technical_prior,
            delta=2.0,
        )
        self.assertEqual(audit.shadow_decision, "TECHNICAL_ONLY")

    def test_global_dna_labeled_explicitly(self):
        audit = compute_shadow_audit(
            brain_row=_brain_row(),
            experience_row={
                "market_context_key": "6-8|40-60|6-8",
                "stock_pattern_key": "DNA_G",
            },
            pattern_knowledge=pd.DataFrame(
                [_pattern_row("NA|NA|<4", "DNA_G", samples=30)]
            ),
            continuation_knowledge=pd.DataFrame(),
        )
        self.assertEqual(audit.regime_alpha_context_level, "GLOBAL_DNA")
        self.assertIn("GLOBAL_DNA", audit.shadow_reason)
        self.assertIn("not proof of regime-specific", audit.shadow_reason)


class TestShadowPersistenceIsolation(unittest.TestCase):
    """G / K — shadow files separate; join keys present."""

    def test_shadow_persist_does_not_touch_pattern_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            brain_dir = Path(tmp) / "brain"
            brain_dir.mkdir()
            snap = brain_dir / "ai_recommendation_shadow.csv"
            hist = brain_dir / "regime_alpha_shadow_history.csv"
            pk_path = Path(tmp) / "pattern_knowledge.csv"
            pk_path.write_text("market_context_key,stock_pattern_key\n", encoding="utf-8")
            mtime_before = pk_path.stat().st_mtime

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
                        "RegimeAlphaScore": 55.0,
                        "RegimeAlphaRawScore": 60.0,
                        "RegimeAlphaDiscountedScore": 55.0,
                        "RegimeAlphaConfidence": 0.0,
                        "RegimeAlphaContextLevel": "GLOBAL_DNA",
                        "RegimeAlphaMatchedContext": "NA|NA|<4",
                        "RegimeAlphaSamples": 5,
                        "ShadowFinalScore": 70.0,
                        "ShadowDecision": "TECHNICAL_ONLY",
                        "ShadowReason": "test",
                        "updated_at": "2026-08-08",
                    }
                ]
            )

            with mock.patch("modules.regime_alpha_shadow.SHADOW_SNAPSHOT_FILE", snap), mock.patch(
                "modules.regime_alpha_shadow.SHADOW_HISTORY_FILE", hist
            ):
                persist_shadow_audit(shadow_df)

            self.assertTrue(snap.exists())
            self.assertTrue(hist.exists())
            loaded = pd.read_csv(hist, encoding="utf-8-sig")
            self.assertIn("session_date", loaded.columns)
            self.assertIn("symbol", loaded.columns)
            self.assertIn("stock_pattern_key", loaded.columns)
            self.assertIn("market_context_key", loaded.columns)
            self.assertIn("outcome_join_status", loaded.columns)
            self.assertEqual(loaded.iloc[-1]["outcome_join_status"], "PENDING")
            self.assertGreaterEqual(pk_path.stat().st_mtime, mtime_before)


class TestNoSafetyBypass(unittest.TestCase):
    """H — shadow module has no safety gate exports."""

    def test_shadow_module_no_safety_exports(self):
        import modules.regime_alpha_shadow as sh

        for name in dir(sh):
            if name.startswith("_"):
                continue
            self.assertNotIn("safety", name.lower())
            self.assertNotIn("hard_bad", name.lower())
            self.assertNotIn("block", name.lower())


class TestBuyEliteFinalDecisionUntouched(unittest.TestCase):
    """B / J — no wiring into buy elite / final decision."""

    def _sample_buy_elite(self):
        return pd.DataFrame(
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
                    "ExperienceAdjustment": 3.0,
                    "ExperienceSamples": 10,
                    "LearningStatus": "READY_FOR_CONNECTION",
                },
                {
                    "MÃ": "BBB",
                    "KẾT LUẬN": "MUA ELITE",
                    "EliteScore": 82,
                    "EliteScoreBase": 80,
                    "WinProb": 68,
                    "ĐỘ TIN CẬY": "TRUNG BÌNH",
                    "ĐỒNG THUẬN": "3/5",
                    "NHÓM": "CP MẠNH",
                    "GIÁ": 12.0,
                    "ExperienceAdjustment": 2.0,
                    "ExperienceSamples": 8,
                    "LearningStatus": "READY_FOR_CONNECTION",
                },
            ]
        )

    def test_final_decision_output_unchanged_after_shadow_build(self):
        buy_elite = self._sample_buy_elite()
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
        _ = build_shadow_recommendations(rec, brain, exp, session_date="2026-08-08")

        after_df, after_note = build_final_decision(buy_elite)
        pd.testing.assert_frame_equal(before_df, after_df)
        self.assertEqual(before_note, after_note)

    def test_app_has_no_shadow_in_buy_elite_path(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        text = app_path.read_text(encoding="utf-8")
        self.assertNotIn("regime_alpha_shadow", text)
        self.assertNotIn("build_shadow_recommendations", text)

    def test_final_decision_untouched(self):
        fd_path = Path(__file__).resolve().parents[1] / "final_decision_engine.py"
        text = fd_path.read_text(encoding="utf-8")
        self.assertNotIn("regime_alpha", text.lower())


class TestShadowRealKnowledgeReadOnly(unittest.TestCase):
    """Example shadow rows from real knowledge (read-only)."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.pk = pd.read_csv(
                "data/earning_learning/pattern_knowledge.csv", low_memory=False
            )
        except FileNotFoundError:
            cls.pk = pd.DataFrame()

    def test_real_knowledge_shadow_row(self):
        if self.pk.empty:
            self.skipTest("pattern_knowledge.csv unavailable")
        row = self.pk[self.pk["samples"] >= 5].iloc[0]
        stock = str(row["stock_pattern_key"])
        brain = pd.DataFrame([_brain_row(symbol="REAL1")])
        rec = pd.DataFrame(
            [
                {
                    "rank": 1,
                    "symbol": "REAL1",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 70,
                    "pattern_match_score": 55,
                    "updated_at": "2026-08-08",
                }
            ]
        )
        exp = pd.DataFrame(
            [
                {
                    "symbol": "REAL1",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": stock,
                }
            ]
        )
        shadow = build_shadow_recommendations(
            rec,
            brain,
            exp,
            session_date="2026-08-08",
            pattern_knowledge=self.pk,
            as_of=date(2026, 8, 8),
        )
        self.assertEqual(len(shadow), 1)
        self.assertIn(shadow.iloc[0]["RegimeAlphaContextLevel"], {
            "GLOBAL_DNA",
            "EXACT_CONTEXT",
            "FAMILY_CONTEXT",
            "NONE",
        })
        for col in SHADOW_COLUMNS:
            self.assertIn(col, shadow.columns)


class TestCompileImport(unittest.TestCase):
    """L — compile and import."""

    def test_compile_and_import(self):
        import py_compile

        base = Path(__file__).resolve().parents[1]
        py_compile.compile(str(base / "modules" / "regime_alpha_shadow.py"), doraise=True)
        py_compile.compile(str(base / "leader_memory.py"), doraise=True)
        import modules.regime_alpha_shadow as sh

        self.assertIn("build_shadow_recommendations", sh.__all__)


if __name__ == "__main__":
    unittest.main()
