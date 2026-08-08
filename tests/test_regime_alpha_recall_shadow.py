"""N3.7 recall shadow integration tests."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from leader_memory import RECOMMENDATION_COLUMNS, _build_recommendations
from modules.regime_alpha import (
    RECALL_LEVEL_EXACT,
    RECALL_LEVEL_GLOBAL,
    RECALL_LEVEL_NO_EVIDENCE,
    compute_recall_evidence,
    filter_recall_learning_pool,
    load_recall_index,
)
from modules.regime_alpha_shadow import (
    build_shadow_with_recall,
    summarize_shadow_comparison,
)
from modules.regime_recall_index import rebuild_recall_index


class TestRecallEvidence(unittest.TestCase):
    DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "earning_learning"

    @classmethod
    def setUpClass(cls):
        if not (cls.DATA_DIR / "regime_recall_index.csv").exists():
            rebuild_recall_index(cls.DATA_DIR, write=True)
        cls.recall = load_recall_index(cls.DATA_DIR)

    def test_learning_pool_size(self):
        pool = filter_recall_learning_pool(self.recall)
        self.assertEqual(len(pool), 1420)
        self.assertTrue((pool["recall_level"] == RECALL_LEVEL_GLOBAL).all())

    def test_exact_has_zero_matured_evidence(self):
        pool = filter_recall_learning_pool(self.recall)
        exact = pool[pool["recall_level"] == RECALL_LEVEL_EXACT]
        self.assertEqual(len(exact), 0)

    def test_global_recall_evidence(self):
        pool = filter_recall_learning_pool(self.recall)
        dna_counts = pool.groupby("stock_pattern_key").size()
        top_dna = str(dna_counts[dna_counts >= 10].idxmax())
        evidence = compute_recall_evidence(
            "6-8|40-60|6-8",
            top_dna,
            recall_index=self.recall,
        )
        self.assertEqual(evidence.recall_level, RECALL_LEVEL_GLOBAL)
        self.assertGreaterEqual(evidence.recall_t3_samples, 10)
        self.assertGreater(evidence.recall_confidence, 0.0)

    def test_no_evidence_for_unknown_dna(self):
        evidence = compute_recall_evidence(
            "6-8|40-60|6-8",
            "UNKNOWN_DNA_KEY",
            recall_index=self.recall,
        )
        self.assertEqual(evidence.recall_level, RECALL_LEVEL_NO_EVIDENCE)
        self.assertEqual(evidence.recall_confidence, 0.0)


class TestShadowComparison(unittest.TestCase):
    DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "earning_learning"

    def _sample_candidates(self):
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
                },
            ]
        )
        patterns = pd.DataFrame(
            [{"pattern_id": "p1", "feature_signature": "x", "pattern_score": 70}]
        )
        config = {"max_recommendation_rows": 100}
        recall = load_recall_index(self.DATA_DIR)
        pool = filter_recall_learning_pool(recall)
        dna_stats = (
            pool.groupby("stock_pattern_key")
            .agg(n=("t3_return_pct", "count"), mean_t3=("t3_return_pct", "mean"))
            .reset_index()
        )
        dna_stats = dna_stats[dna_stats["n"] >= 10]
        weak_dna = str(dna_stats.sort_values("mean_t3").iloc[0]["stock_pattern_key"])
        strong_dna = str(dna_stats.sort_values("mean_t3").iloc[-1]["stock_pattern_key"])

        exp = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": weak_dna,
                    "ExperienceAdjustment": 0,
                },
                {
                    "symbol": "BBB",
                    "market_context_key": "6-8|40-60|6-8",
                    "stock_pattern_key": strong_dna,
                    "ExperienceAdjustment": 0,
                },
            ]
        )
        rec = _build_recommendations(
            brain, patterns, config, experience_df=exp, market_real=7.0
        )
        return rec, brain, exp, recall

    def test_baseline_and_shadow_can_differ(self):
        rec, brain, exp, recall = self._sample_candidates()
        shadow = build_shadow_with_recall(
            rec,
            brain,
            exp,
            session_date="2026-08-08",
            recall_index=recall,
        )
        self.assertEqual(len(shadow), 2)
        self.assertNotEqual(
            shadow["BaselineRank"].tolist(),
            shadow["ShadowExperienceRank"].tolist(),
        )
        summary = summarize_shadow_comparison(shadow, recall_index=recall)
        self.assertEqual(summary.global_count, 2)
        self.assertEqual(summary.exact_count, 0)
        self.assertGreater(summary.promoted + summary.demoted, 0)

    def test_production_columns_unchanged(self):
        rec, brain, exp, _ = self._sample_candidates()
        before = rec.copy()
        _ = build_shadow_with_recall(
            rec, brain, exp, session_date="2026-08-08"
        )
        pd.testing.assert_frame_equal(before, rec)
        self.assertListEqual(list(rec.columns), list(RECOMMENDATION_COLUMNS))

    def test_recall_index_unmodified_on_shadow_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in ("regime_recall_index.csv",):
                src = self.DATA_DIR / name
                (tmp_path / name).write_bytes(src.read_bytes())
            mtime_before = (tmp_path / name).stat().st_mtime
            recall = load_recall_index(tmp_path)
            rec, brain, exp, _ = self._sample_candidates()
            build_shadow_with_recall(
                rec,
                brain,
                exp,
                session_date="2026-08-08",
                recall_index=recall,
            )
            self.assertEqual(
                (tmp_path / name).stat().st_mtime,
                mtime_before,
            )


class TestCompileImport(unittest.TestCase):
    def test_compile_and_import(self):
        import py_compile

        base = Path(__file__).resolve().parents[1]
        py_compile.compile(str(base / "modules" / "regime_alpha.py"), doraise=True)
        py_compile.compile(str(base / "modules" / "regime_alpha_shadow.py"), doraise=True)
        import modules.regime_alpha as ra
        import modules.regime_alpha_shadow as sh

        self.assertIn("compute_recall_evidence", ra.__all__)
        self.assertIn("build_shadow_with_recall", sh.__all__)


if __name__ == "__main__":
    unittest.main()
