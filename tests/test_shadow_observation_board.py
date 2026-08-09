"""Read-only tests for shadow observation board display layer."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from modules.regime_alpha_forward_eval import (
    EVAL_MODE_FORWARD_FROZEN,
    EVAL_MODE_RECONSTRUCTED_AUDIT,
    classify_movement_class,
)
from modules.shadow_observation_board import (
    count_excluded_forward_rows,
    evaluate_genuine_forward_scorecard,
    filter_genuine_forward_ledger,
    format_recall_level_display,
    has_forward_observation_provenance,
    load_genuine_forward_joined,
    movement_class_counts,
    prepare_live_shadow_frame,
)


def _sample_shadow_row(symbol: str = "VNM", dna: str = "DNA_REAL") -> dict:
    return {
        "session_date": "2026-08-15",
        "rank": 1,
        "symbol": symbol,
        "recommendation": "ƯU TIÊN CAO",
        "leader_score": 80,
        "market_context_key": "6-8|40-60|6-8",
        "stock_pattern_key": dna,
        "TechnicalPrior": 75.0,
        "BaselineScore": 77.0,
        "BaselineRank": 1,
        "ShadowExperienceScore": 79.0,
        "ShadowExperienceRank": 1,
        "ScoreDelta": 2.0,
        "RankDelta": 0,
        "ShadowMovement": "UNCHANGED",
        "RecallSource": "GLOBAL",
        "RecallLevel": "GLOBAL_DNA",
        "RecallSamples": 20,
        "RecallT3Samples": 15,
        "RecallT5Samples": 10,
        "RecallT10Samples": 5,
        "RecallMeanT3": 2.5,
        "RecallMeanT5": 3.0,
        "RecallMeanT10": 4.0,
        "RecallWinRateT3": 60.0,
        "RecallWinRateT5": 55.0,
        "RecallWinRateT10": 50.0,
        "RecallConfidence": 0.15,
        "RecallAlpha": 58.0,
        "RecallMatchedDNA": dna,
        "RecallMatchedContext": "NA",
        "ShadowReason": "test",
        "updated_at": "2026-08-15",
    }


class TestProvenanceFilter(unittest.TestCase):
    def test_provenance_from_observation_id(self):
        row = {"session_date": "2026-08-15", "symbol": "AAA", "observation_id": "obs-1"}
        self.assertTrue(has_forward_observation_provenance(row, {}))

    def test_provenance_from_lookup_not_symbol_heuristic(self):
        lookup = {("2026-08-15", "AAA"): "obs-from-file"}
        row = {"session_date": "2026-08-15", "symbol": "AAA", "observation_id": ""}
        self.assertTrue(has_forward_observation_provenance(row, lookup))

    def test_missing_provenance_excludes_row(self):
        row = {"session_date": "2026-08-10", "symbol": "AAA", "observation_id": ""}
        self.assertFalse(has_forward_observation_provenance(row, {}))

    def test_filter_uses_mode_and_provenance_only(self):
        ledger = pd.DataFrame(
            [
                {
                    "session_date": "2026-08-10",
                    "symbol": "AAA",
                    "evaluation_mode": EVAL_MODE_FORWARD_FROZEN,
                    "observation_id": "",
                },
                {
                    "session_date": "2026-08-15",
                    "symbol": "VNM",
                    "evaluation_mode": EVAL_MODE_FORWARD_FROZEN,
                    "observation_id": "obs-vnm",
                },
                {
                    "session_date": "2026-08-15",
                    "symbol": "HPG",
                    "evaluation_mode": EVAL_MODE_RECONSTRUCTED_AUDIT,
                    "observation_id": "obs-hpg",
                },
            ]
        )
        filtered = filter_genuine_forward_ledger(ledger, observation_lookup={})
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]["symbol"], "VNM")

    def test_count_excluded_forward_rows(self):
        ledger = pd.DataFrame(
            [
                {
                    "evaluation_mode": EVAL_MODE_FORWARD_FROZEN,
                    "session_date": "2026-08-10",
                    "symbol": "AAA",
                    "observation_id": "",
                },
                {
                    "evaluation_mode": EVAL_MODE_RECONSTRUCTED_AUDIT,
                    "session_date": "2026-08-10",
                    "symbol": "HPG",
                    "observation_id": "obs-hpg",
                },
            ]
        )
        with mock.patch(
            "modules.shadow_observation_board.load_observation_session_lookup",
            return_value={},
        ):
            counts = count_excluded_forward_rows(ledger)
        self.assertEqual(counts["missing_provenance"], 1)
        self.assertEqual(counts["reconstructed_audit"], 1)


class TestDisplayHelpers(unittest.TestCase):
    def test_global_label(self):
        text = format_recall_level_display("GLOBAL_DNA")
        self.assertIn("CONTEXT_FREE_PRIOR", text)
        self.assertIn("GLOBAL_DNA", text)

    def test_movement_class_counts(self):
        df = pd.DataFrame(
            [
                {"RecallConfidence": 0.2, "ScoreDelta": 2.0, "ShadowMovement": "PROMOTED"},
                {"RecallConfidence": 0.2, "ScoreDelta": -2.0, "ShadowMovement": "DEMOTED"},
                {"RecallConfidence": 0, "ScoreDelta": 0, "ShadowMovement": "PROMOTED"},
            ]
        )
        df["movement_class"] = df.apply(classify_movement_class, axis=1)
        counts = movement_class_counts(df)
        self.assertEqual(counts["ACTIVE_PROMOTED"], 1)
        self.assertEqual(counts["ACTIVE_DEMOTED"], 1)
        self.assertEqual(counts["PASSIVE_MOVED"], 1)

    def test_prepare_live_adds_pending_outcomes(self):
        shadow = pd.DataFrame([_sample_shadow_row()])
        prepared = prepare_live_shadow_frame(shadow)
        self.assertEqual(prepared.iloc[0]["outcome_status_t3"], "PENDING")
        self.assertIn("RecallLevelDisplay", prepared.columns)


class TestReadOnlyScorecard(unittest.TestCase):
    def test_genuine_scorecard_requires_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ledger_path = tmp_path / "ledger.csv"
            outcomes_path = tmp_path / "outcomes.csv"

            rows = []
            for sym, oid in [("AAA", ""), ("VNM", "obs-vnm")]:
                row = _sample_shadow_row(sym, "REAL")
                row.update(
                    {
                        "snapshot_id": f"snap_{sym}",
                        "frozen_at": "2026-08-15T12:00:00+00:00",
                        "ledger_version": "1.0.0",
                        "evaluation_mode": EVAL_MODE_FORWARD_FROZEN,
                        "movement_class": "UNCHANGED",
                        "observation_id": oid,
                    }
                )
                rows.append(row)
            pd.DataFrame(rows).to_csv(ledger_path, index=False)
            pd.DataFrame(
                [
                    {
                        "session_date": "2026-08-15",
                        "symbol": "VNM",
                        "snapshot_id": "snap_VNM",
                        "observation_id": "obs-vnm",
                        "ActualT3Return": 5.0,
                        "ActualT5Return": pd.NA,
                        "ActualT10Return": pd.NA,
                        "outcome_status_t3": "READY",
                        "outcome_status_t5": "PENDING",
                        "outcome_status_t10": "PENDING",
                        "matured_at_t3": "2026-08-20",
                        "matured_at_t5": "",
                        "matured_at_t10": "",
                        "corporate_action_flag": "",
                        "outcome_version": "1.0.0",
                    }
                ]
            ).to_csv(outcomes_path, index=False)

            with mock.patch(
                "modules.shadow_observation_board.load_forward_ledger",
                return_value=pd.read_csv(ledger_path),
            ), mock.patch(
                "modules.shadow_observation_board.load_forward_outcomes",
                return_value=pd.read_csv(outcomes_path),
            ), mock.patch(
                "modules.shadow_observation_board.load_observation_session_lookup",
                return_value={},
            ):
                joined = load_genuine_forward_joined()
                self.assertEqual(len(joined), 1)
                self.assertEqual(joined.iloc[0]["symbol"], "VNM")
                card = evaluate_genuine_forward_scorecard()
                self.assertEqual(card.sessions, 1)
                self.assertEqual(card.candidates, 1)


class TestBoardDoesNotWrite(unittest.TestCase):
    _WATCH_FILES = (
        "brain/ai_recommendation.csv",
        "brain/ai_recommendation_shadow.csv",
        "brain/regime_alpha_shadow_ledger.csv",
        "brain/regime_alpha_forward_outcomes.csv",
        "data/earning_learning/regime_recall_index.csv",
        "data/earning_learning/observations.csv",
        "data/earning_learning/pattern_lifecycle.csv",
        "data/earning_learning/pattern_knowledge.csv",
        "data/earning_learning/continuation_knowledge.csv",
    )

    def test_render_does_not_touch_watched_files(self):
        import modules.shadow_observation_board as board

        before = {}
        for rel in self._WATCH_FILES:
            path = Path(rel)
            if path.exists():
                before[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

        mock_st = mock.MagicMock()
        mock_st.expander.return_value.__enter__ = lambda s: mock_st
        mock_st.expander.return_value.__exit__ = lambda s, *a: None

        with mock.patch.object(
            board, "load_shadow_recommendations", return_value=pd.DataFrame()
        ), mock.patch.object(
            board, "load_genuine_forward_joined", return_value=pd.DataFrame()
        ), mock.patch.object(
            board, "load_forward_ledger", return_value=pd.DataFrame()
        ), mock.patch.dict("sys.modules", {"streamlit": mock_st}):
            board.render_shadow_observation_board()

        for rel, digest in before.items():
            path = Path(rel)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, after, msg=rel)


if __name__ == "__main__":
    unittest.main()
