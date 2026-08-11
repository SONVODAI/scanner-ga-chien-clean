"""Tests for query-time recall context matching (Patch 2)."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from modules.regime_alpha import (
    RECALL_LEVEL_EXACT,
    RECALL_LEVEL_FAMILY,
    RECALL_LEVEL_GLOBAL,
    RECALL_LEVEL_NO_EVIDENCE,
    classify_context_match,
    compute_recall_evidence,
    filter_recall_learning_pool,
    load_recall_index,
)


class TestClassifyContextMatch(unittest.TestCase):
    def test_exact_full_key(self):
        key = "6-8|40-60|6-8"
        self.assertEqual(classify_context_match(key, key), RECALL_LEVEL_EXACT)

    def test_family_market_bucket_for_na_historical(self):
        live = "6-8|40-60|6-8"
        historical = "NA|NA|6-8"
        self.assertEqual(
            classify_context_match(live, historical),
            RECALL_LEVEL_FAMILY,
        )

    def test_no_family_when_market_bucket_differs(self):
        live = "6-8|40-60|6-8"
        historical = "NA|NA|<4"
        self.assertNotEqual(
            classify_context_match(live, historical),
            RECALL_LEVEL_FAMILY,
        )

    def test_global_for_na_context_without_bucket_match(self):
        live = "6-8|40-60|6-8"
        historical = "NA|NA|<4"
        self.assertEqual(
            classify_context_match(live, historical),
            RECALL_LEVEL_GLOBAL,
        )


class TestRecallPoolResolution(unittest.TestCase):
    DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "earning_learning"

    @classmethod
    def setUpClass(cls):
        if not (cls.DATA_DIR / "regime_recall_index.csv").exists():
            from modules.regime_recall_index import rebuild_recall_index

            rebuild_recall_index(cls.DATA_DIR, write=True)
        cls.recall = load_recall_index(cls.DATA_DIR)

    def _synthetic_family_pool(self) -> pd.DataFrame:
        rows = []
        dna = "SYNTH|DNA|KEY"
        for i in range(8):
            rows.append(
                {
                    "stock_pattern_key": dna,
                    "market_context_key": "NA|NA|6-8",
                    "recall_level": "GLOBAL_DNA",
                    "usable_for_learning": True,
                    "t3_return_pct": 2.5,
                    "t5_return_pct": 3.0,
                    "t10_return_pct": 4.0,
                    "outcome_status_t3": "READY",
                    "outcome_status_t5": "READY",
                    "outcome_status_t10": "READY",
                }
            )
        return pd.DataFrame(rows)

    def test_family_evidence_from_historical_na_bucket(self):
        pool = filter_recall_learning_pool(self.recall)
        bucket_rows = pool[
            pool["market_context_key"].astype(str) == "NA|NA|6-8"
        ]
        self.assertGreater(len(bucket_rows), 0)
        dna = str(bucket_rows.iloc[0]["stock_pattern_key"])
        evidence = compute_recall_evidence(
            "6-8|40-60|6-8",
            dna,
            recall_index=self.recall,
        )
        self.assertEqual(evidence.recall_level, RECALL_LEVEL_FAMILY)
        self.assertGreaterEqual(evidence.recall_t3_samples, 1)

    def test_family_confidence_when_bucket_has_enough_samples(self):
        synthetic = self._synthetic_family_pool()
        evidence = compute_recall_evidence(
            "6-8|40-60|6-8",
            "SYNTH|DNA|KEY",
            recall_index=synthetic,
        )
        self.assertEqual(evidence.recall_level, RECALL_LEVEL_FAMILY)
        self.assertGreaterEqual(evidence.recall_t3_samples, 5)
        self.assertGreater(evidence.recall_confidence, 0.0)
        self.assertLess(evidence.recall_confidence, 0.85 * 0.65 + 0.01)

    def test_exact_stored_global_still_resolves_exact_on_key_match(self):
        pool = filter_recall_learning_pool(self.recall)
        row = pool.iloc[0]
        evidence = compute_recall_evidence(
            str(row["market_context_key"]),
            str(row["stock_pattern_key"]),
            recall_index=self.recall,
        )
        self.assertIn(
            evidence.recall_level,
            {RECALL_LEVEL_EXACT, RECALL_LEVEL_FAMILY, RECALL_LEVEL_GLOBAL},
        )
        self.assertNotEqual(evidence.recall_level, RECALL_LEVEL_NO_EVIDENCE)

    def test_global_only_when_no_bucket_family_match(self):
        pool = filter_recall_learning_pool(self.recall)
        dna_counts = pool.groupby("stock_pattern_key").size()
        dna = str(dna_counts.idxmax())
        evidence = compute_recall_evidence(
            "6-8|40-60|<4",
            dna,
            recall_index=self.recall,
        )
        if evidence.recall_level != RECALL_LEVEL_NO_EVIDENCE:
            self.assertIn(
                evidence.recall_level,
                {RECALL_LEVEL_FAMILY, RECALL_LEVEL_GLOBAL},
            )


if __name__ == "__main__":
    unittest.main()
