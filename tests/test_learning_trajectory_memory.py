"""Tests for Evolution Trajectory Memory research layer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from modules.learning_insight_candidates import (
    build_learning_insight_candidates,
    compute_insight_candidate_score,
)
from modules.learning_trajectory_memory import (
    TRAJECTORY_EVIDENCE_INSUFFICIENT,
    TRAJECTORY_EVIDENCE_NONE,
    TRAJECTORY_EVIDENCE_QUALIFIED,
    build_trajectory_features_from_history,
    build_trajectory_knowledge,
    build_trajectory_observation_rows,
    classify_behavior_class,
    compute_trajectory_evidence,
    freeze_trajectory_t0_ledger,
    load_trajectory_forward_ledger,
    lookup_trajectory_knowledge_row,
    rebuild_trajectory_knowledge,
    run_trajectory_validation_report,
    TrajectoryFeatures,
)
from modules.regime_alpha_forward_eval import EVAL_MODE_FORWARD_FROZEN


def _sample_history() -> pd.DataFrame:
    rows = []
    groups = ["THEO DÕI", "THEO DÕI", "TÍCH LŨY", "TÍCH LŨY", "MUA EARLY"]
    for i, g in enumerate(groups):
        rows.append(
            {
                "date": f"2026-07-{15 + i}",
                "symbol": "AAA",
                "group": g,
                "rank": {"THEO DÕI": 0, "TÍCH LŨY": 1, "MUA EARLY": 2}[g],
                "score": 50 + i,
            }
        )
    return pd.DataFrame(rows)


class TestTrajectoryFeatures(unittest.TestCase):
    def test_features_use_only_past_history(self):
        hist = _sample_history()
        features = build_trajectory_features_from_history(hist, t0_date="2026-07-18")
        self.assertIsNotNone(features)
        assert features is not None
        self.assertEqual(features.t0_group, "TÍCH LŨY")
        self.assertIn("ACCUM", features.trajectory_pattern)
        self.assertGreaterEqual(features.transition_count, 1)

    def test_no_future_row_in_features(self):
        hist = _sample_history()
        features = build_trajectory_features_from_history(hist, t0_date="2026-07-17")
        self.assertIsNotNone(features)
        assert features is not None
        self.assertEqual(features.t0_group, "TÍCH LŨY")

    def test_behavior_classes(self):
        ranks = [0, 0, 1, 2, 2]
        groups = ["THEO DÕI", "THEO DÕI", "TÍCH LŨY", "MUA EARLY", "MUA EARLY"]
        behavior = classify_behavior_class(ranks, groups)
        self.assertIn(behavior, {"SETUP_ENTRY", "CLIMB", "MIXED", "CHURN", "STABLE"})


class TestTrajectoryKnowledge(unittest.TestCase):
    def test_knowledge_respects_sample_gate(self):
        obs = pd.DataFrame(
            [
                {
                    "TrajectoryPattern": "EARLY_SETUP_ENTRY",
                    "TrajectoryContext": "NA|NA|<4",
                    "trade_date": "2026-07-23",
                    "t3_return_pct": 1.0,
                    "t5_return_pct": 2.0,
                    "t10_return_pct": 3.0,
                    "t3_is_win": True,
                    "t5_is_win": True,
                    "t10_is_win": True,
                }
            ]
            * 10
        )
        knowledge = build_trajectory_knowledge(obs)
        self.assertEqual(len(knowledge), 1)
        self.assertEqual(
            knowledge.iloc[0]["TrajectoryEvidenceStatus"],
            TRAJECTORY_EVIDENCE_INSUFFICIENT,
        )

    def test_qualified_when_enough_samples(self):
        obs = pd.DataFrame(
            [
                {
                    "TrajectoryPattern": "WATCH_STABLE",
                    "TrajectoryContext": "NA|NA|<4",
                    "trade_date": "2026-07-23",
                    "t3_return_pct": 1.0,
                    "t5_return_pct": 2.0,
                    "t10_return_pct": 3.0,
                    "t3_is_win": True,
                    "t5_is_win": True,
                    "t10_is_win": False,
                }
            ]
            * 20
        )
        knowledge = build_trajectory_knowledge(obs)
        self.assertEqual(
            knowledge.iloc[0]["TrajectoryEvidenceStatus"],
            TRAJECTORY_EVIDENCE_QUALIFIED,
        )
        row, mode = lookup_trajectory_knowledge_row(
            {("WATCH_STABLE", "NA|NA|<4"): knowledge.iloc[0]},
            "WATCH_STABLE",
            "NA|NA|<4",
        )
        self.assertIsNotNone(row)
        self.assertEqual(mode, "EXACT_CONTEXT")

    def test_compute_trajectory_evidence_neutral_without_row(self):
        feat = TrajectoryFeatures(
            trajectory_pattern="EARLY_CHURN",
            path_last_3="WATCH>EARLY",
            path_last_5="WATCH>ACCUM>EARLY",
            path_last_10="WATCH>ACCUM>EARLY",
            transition_count=2,
            upward_transitions=2,
            downward_transitions=0,
            sessions_in_current_group=1,
            unique_groups_window=3,
            behavior_class="CHURN",
            progression_speed=0.5,
            t0_group="MUA EARLY",
            terminal_bucket="EARLY",
        )
        result = compute_trajectory_evidence(
            features=feat,
            trajectory_context="NA|NA|<4",
            knowledge_row=None,
        )
        self.assertEqual(result.trajectory_score, 50.0)
        self.assertEqual(result.trajectory_evidence_status, TRAJECTORY_EVIDENCE_NONE)


class TestTrajectoryIndependence(unittest.TestCase):
    def test_insight_score_unchanged_by_trajectory(self):
        pattern_row = {
            "samples": 20,
            "win_rate_pct": 68.0,
            "win_rate_lower_bound_pct": 60.0,
            "pattern_key": "DNA_A",
            "market_context_key": "6-8|40-60|6-8",
        }
        insight = compute_insight_candidate_score(
            pattern_row=pattern_row,
            continuation_row=None,
            context_match_mode="FAMILY_CONTEXT",
        )
        self.assertGreater(insight.insight_candidate_score, 50.0)

    def test_insight_exposes_separate_trajectory_fields(self):
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
        brain = pd.DataFrame([{"symbol": "AAA", "leader_score": 80}])
        with mock.patch(
            "modules.learning_insight_candidates.get_pattern_knowledge",
            return_value=pd.DataFrame(),
        ), mock.patch(
            "modules.learning_insight_candidates.get_continuation_knowledge",
            return_value=pd.DataFrame(),
        ), mock.patch(
            "modules.learning_insight_candidates.load_evolution_history",
            return_value=_sample_history(),
        ), mock.patch(
            "modules.learning_insight_candidates.load_trajectory_knowledge",
            return_value=pd.DataFrame(),
        ):
            insight = build_learning_insight_candidates(
                rec,
                brain,
                session_date="2026-07-19",
                market_real=7.0,
                market_forecast=7.0,
                breadth=50.0,
            )
        self.assertIn("TrajectoryPattern", insight.columns)
        self.assertIn("TrajectoryScore", insight.columns)
        self.assertIn("TrajectoryEvidenceStatus", insight.columns)
        self.assertNotIn("ShadowFinalScore", insight.columns)


class TestTrajectoryForwardLedger(unittest.TestCase):
    def test_forward_frozen_rows_are_immutable(self):
        row = pd.DataFrame(
            [
                {
                    "session_date": "2026-08-08",
                    "symbol": "AAA",
                    "TrajectoryPattern": "EARLY_SETUP_ENTRY",
                    "TrajectoryContext": "NA|NA|<4",
                    "path_last_3": "ACCUM>EARLY",
                    "path_last_5": "WATCH>ACCUM>EARLY",
                    "path_last_10": "WATCH>ACCUM>EARLY",
                    "transition_count": 2,
                    "upward_transitions": 2,
                    "downward_transitions": 0,
                    "sessions_in_current_group": 1,
                    "unique_groups_window": 3,
                    "behavior_class": "SETUP_ENTRY",
                    "progression_speed": 0.5,
                    "TrajectoryScore": 55.0,
                    "TrajectoryEvidenceStatus": TRAJECTORY_EVIDENCE_QUALIFIED,
                    "TrajectoryReason": "test",
                    "TrajectorySamplesT5": 20,
                    "TrajectoryWinRateT5": 65.0,
                }
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trajectory_ledger.csv"
            freeze_trajectory_t0_ledger(row, ledger_path=path)
            updated = row.copy()
            updated.loc[0, "TrajectoryScore"] = 99.0
            freeze_trajectory_t0_ledger(updated, ledger_path=path)
            ledger = load_trajectory_forward_ledger(
                evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
                ledger_path=path,
            )
            self.assertEqual(len(ledger), 1)
            self.assertEqual(float(ledger.iloc[0]["TrajectoryScore"]), 55.0)


class TestTrajectoryValidation(unittest.TestCase):
    def test_validation_report_shape(self):
        obs = pd.DataFrame(
            [
                {
                    "TrajectoryPattern": "WATCH_STABLE",
                    "TrajectoryContext": "NA|NA|<4",
                    "trade_date": "2026-07-23",
                    "t3_return_pct": 1.0,
                    "t5_return_pct": 2.0,
                    "t10_return_pct": 3.0,
                    "t3_is_win": True,
                    "t5_is_win": True,
                    "t10_is_win": True,
                    "stock_pattern_key": "DNA_A",
                    "market_regime": "Forecast rủi ro",
                }
            ]
            * 25
        )
        report = run_trajectory_validation_report(obs, build_trajectory_knowledge(obs))
        self.assertIn("horizon_stats", report)
        self.assertIn("double_counting_audit", report)
        self.assertFalse(report["double_counting_audit"]["uses_persistence_field"])


class TestRealDataSmoke(unittest.TestCase):
    def test_rebuild_on_real_data_if_present(self):
        from modules.learning_trajectory_memory import EVOLUTION_HISTORY_FILE

        if not EVOLUTION_HISTORY_FILE.exists():
            self.skipTest("group_evolution_history.csv not present")
        knowledge = rebuild_trajectory_knowledge()
        self.assertIsInstance(knowledge, pd.DataFrame)
        obs = build_trajectory_observation_rows()
        self.assertGreater(len(obs), 0)
        report = run_trajectory_validation_report(obs, knowledge)
        self.assertGreater(report["observation_rows"], 0)


if __name__ == "__main__":
    unittest.main()
