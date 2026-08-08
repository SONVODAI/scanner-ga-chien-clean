"""Tests for modules.regime_recall_index (N3.6)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from modules.regime_recall_index import (
    RECALL_LEVEL_EXACT,
    RECALL_LEVEL_GLOBAL,
    RECALL_LEVEL_UNUSABLE,
    build_recall_index,
    classify_recall_level,
    ensure_recall_index,
    load_recall_index,
    rebuild_recall_index,
    reset_recall_index_runtime_cache,
    summarize_recall_index,
    validate_against_decision_archive,
)


class TestRecallClassification(unittest.TestCase):
    def test_exact_context(self):
        level = classify_recall_level(
            market_score_t0=7.0,
            market_forecast_t0=5.0,
            breadth_t0=50.0,
            market_context_key="6-8|40-60|6-8",
            is_weekend=False,
        )
        self.assertEqual(level, RECALL_LEVEL_EXACT)

    def test_global_dna(self):
        level = classify_recall_level(
            market_score_t0=7.0,
            market_forecast_t0=float("nan"),
            breadth_t0=float("nan"),
            market_context_key="NA|NA|6-8",
            is_weekend=False,
        )
        self.assertEqual(level, RECALL_LEVEL_GLOBAL)

    def test_unusable_weekend(self):
        level = classify_recall_level(
            market_score_t0=7.0,
            market_forecast_t0=5.0,
            breadth_t0=50.0,
            market_context_key="6-8|40-60|6-8",
            is_weekend=True,
        )
        self.assertEqual(level, RECALL_LEVEL_UNUSABLE)

    def test_unusable_missing_market_score(self):
        level = classify_recall_level(
            market_score_t0=float("nan"),
            market_forecast_t0=5.0,
            breadth_t0=50.0,
            market_context_key="NA|NA|NA",
            is_weekend=False,
        )
        self.assertEqual(level, RECALL_LEVEL_UNUSABLE)


class TestRecallIndexIntegration(unittest.TestCase):
    DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "earning_learning"

    @classmethod
    def setUpClass(cls):
        if not (cls.DATA_DIR / "observations.csv").exists():
            raise unittest.SkipTest("historical observations not available")

    def test_rebuild_population_counts(self):
        index_df, summary, _ = rebuild_recall_index(self.DATA_DIR, write=False)
        self.assertEqual(summary.total_index_rows, 2272)
        self.assertEqual(summary.duplicate_observation_ids, 0)
        self.assertEqual(summary.by_level.get(RECALL_LEVEL_GLOBAL, 0), 1562)
        self.assertEqual(summary.by_level.get(RECALL_LEVEL_EXACT, 0), 142)
        self.assertEqual(summary.by_level.get(RECALL_LEVEL_UNUSABLE, 0), 568)
        self.assertEqual(summary.weekend_rows, 568)
        self.assertEqual(
            summary.t3_ready_by_level.get(RECALL_LEVEL_GLOBAL, 0),
            1420,
        )
        exact = index_df[index_df["recall_level"] == RECALL_LEVEL_EXACT]
        self.assertEqual(len(exact), 142)
        self.assertTrue((exact["outcome_status_t3"] == "PENDING").all())

    def test_archive_key_match_rate(self):
        index_df, summary, diagnostics = rebuild_recall_index(
            self.DATA_DIR, write=False
        )
        self.assertEqual(diagnostics["archive_key_match_rate"], 1.0)
        archive = pd.read_csv(
            self.DATA_DIR / "decision_archive.csv",
            encoding="utf-8-sig",
            low_memory=False,
        )
        rate = validate_against_decision_archive(index_df, archive)
        self.assertEqual(rate, 1.0)

    def test_idempotent_rebuild(self):
        first, _, _ = rebuild_recall_index(self.DATA_DIR, write=False)
        second, _, _ = rebuild_recall_index(self.DATA_DIR, write=False)
        cols = [c for c in first.columns if c != "rebuilt_at"]
        pd.testing.assert_frame_equal(
            first[cols].sort_values("observation_id").reset_index(drop=True),
            second[cols].sort_values("observation_id").reset_index(drop=True),
        )

    def test_outcomes_are_labels_only(self):
        index_df, _, _ = rebuild_recall_index(self.DATA_DIR, write=False)
        pending_exact = index_df[
            (index_df["recall_level"] == RECALL_LEVEL_EXACT)
            & (index_df["outcome_status_t3"] == "PENDING")
        ]
        self.assertEqual(len(pending_exact), 142)
        self.assertTrue(
            pending_exact["market_context_key"]
            .astype(str)
            .str.contains(r"^\d|<", regex=True)
            .all()
        )

    def test_global_group_counts(self):
        index_df, summary, _ = rebuild_recall_index(self.DATA_DIR, write=False)
        self.assertGreaterEqual(summary.groups_n5_by_level[RECALL_LEVEL_GLOBAL], 50)
        self.assertGreaterEqual(summary.groups_n10_by_level[RECALL_LEVEL_GLOBAL], 29)
        self.assertGreaterEqual(summary.groups_n20_by_level[RECALL_LEVEL_GLOBAL], 12)

    def test_write_derived_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in (
                "observations.csv",
                "pattern_lifecycle.csv",
                "outcomes.csv",
                "decision_archive.csv",
            ):
                src = self.DATA_DIR / name
                if src.exists():
                    (tmp_path / name).write_bytes(src.read_bytes())

            obs_mtime_before = (tmp_path / "observations.csv").stat().st_mtime
            rebuild_recall_index(tmp_path, write=True)
            self.assertTrue((tmp_path / "regime_recall_index.csv").exists())
            self.assertEqual(
                (tmp_path / "observations.csv").stat().st_mtime,
                obs_mtime_before,
            )


class TestRecallIndexRuntimeActivation(unittest.TestCase):
    DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "earning_learning"

    def setUp(self):
        reset_recall_index_runtime_cache()

    def test_auto_rebuild_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in (
                "observations.csv",
                "pattern_lifecycle.csv",
                "outcomes.csv",
                "decision_archive.csv",
            ):
                src = self.DATA_DIR / name
                if src.exists():
                    (tmp_path / name).write_bytes(src.read_bytes())

            recall = ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
            self.assertEqual(len(recall), 2272)
            self.assertTrue((tmp_path / "regime_recall_index.csv").exists())

    def test_load_uses_cache_without_second_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in (
                "observations.csv",
                "pattern_lifecycle.csv",
                "outcomes.csv",
                "decision_archive.csv",
            ):
                src = self.DATA_DIR / name
                if src.exists():
                    (tmp_path / name).write_bytes(src.read_bytes())

            first = ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
            path = tmp_path / "regime_recall_index.csv"
            mtime = path.stat().st_mtime
            second = load_recall_index(tmp_path)
            self.assertEqual(len(first), len(second))
            self.assertEqual(path.stat().st_mtime, mtime)

    def test_missing_sources_degrades_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            recall = ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
            self.assertTrue(recall.empty)
            # Second call with still-missing sources must remain empty but not poison retry.
            recall2 = ensure_recall_index(tmp_path, write=True, auto_rebuild=True)
            self.assertTrue(recall2.empty)


class TestCompileImport(unittest.TestCase):
    def test_compile_and_import(self):
        import py_compile

        base = Path(__file__).resolve().parents[1]
        py_compile.compile(str(base / "modules" / "regime_recall_index.py"), doraise=True)
        import modules.regime_recall_index as rri

        self.assertIn("rebuild_recall_index", rri.__all__)
        self.assertIn("ensure_recall_index", rri.__all__)


if __name__ == "__main__":
    unittest.main()
