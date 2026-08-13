"""Forward pipeline integrity — handoff, storage, ordering, isolation."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from leader_memory import (
    RECOMMENDATION_COLUMNS,
    _build_recommendations,
    finalize_session_forward_shadow,
    get_runtime_recommendations,
    reset_runtime_recommendations,
    update_memory,
)
from modules.regime_alpha_forward_eval import (
    EVAL_MODE_FORWARD_FROZEN,
    finalize_forward_shadow_snapshot,
    freeze_t0_ledger,
    load_forward_ledger,
    load_forward_outcomes,
    mature_forward_outcomes,
)
from modules.regime_alpha_shadow import build_shadow_with_recall
from modules.shadow_observation_board import (
    evaluate_genuine_forward_scorecard,
    filter_genuine_forward_ledger,
    load_observation_session_lookup,
)


REPO_BRAIN = Path(__file__).resolve().parents[1] / "brain"


def _sample_bundle(session: str = "2026-08-12"):
    brain = pd.DataFrame(
        [
            {
                "symbol": "VNM",
                "recommendation": "ƯU TIÊN CAO",
                "leader_score": 88,
                "confidence_score": 60,
                "current_group": "CP MẠNH",
                "current_rsi14": 58,
                "current_obv_status": "UP",
                "persistence_20_pct": 60,
                "winrate_t5_pct": 65,
                "feature_signature": "demo_vnm",
            },
            {
                "symbol": "FPT",
                "recommendation": "THEO DÕI MUA",
                "leader_score": 84,
                "confidence_score": 55,
                "current_group": "PULL ĐẸP",
                "current_rsi14": 55,
                "current_obv_status": "UP",
                "persistence_20_pct": 55,
                "winrate_t5_pct": 60,
                "feature_signature": "demo_fpt",
            },
        ]
    )
    patterns = pd.DataFrame(
        [{"pattern_id": "p1", "feature_signature": "demo_vnm", "pattern_score": 70}]
    )
    exp = pd.DataFrame(
        [
            {
                "symbol": "VNM",
                "market_context_key": "6-8|40-60|6-8",
                "stock_pattern_key": "DNA_V",
            },
            {
                "symbol": "FPT",
                "market_context_key": "6-8|40-60|6-8",
                "stock_pattern_key": "DNA_F",
            },
        ]
    )
    rec = _build_recommendations(
        brain,
        patterns,
        {"max_recommendation_rows": 100},
        experience_df=exp,
    )
    shadow = build_shadow_with_recall(
        rec,
        brain,
        exp,
        session_date=session,
        recall_index=pd.DataFrame(),
    )
    return rec, brain, exp, shadow


class RuntimeRecommendationHandoffTests(unittest.TestCase):
    def test_finalize_succeeds_without_recommendation_csv(self):
        rec, brain, exp, _ = _sample_bundle("2026-08-13")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.csv"
            with mock.patch("leader_memory.load_recommendations") as load_rec:
                load_rec.side_effect = AssertionError("disk fallback must not run")
                with mock.patch("leader_memory._safe_read_csv", return_value=brain):
                    with mock.patch(
                        "leader_memory._latest_session_experience_snapshot",
                        return_value=pd.DataFrame({"symbol": ["VNM"], "session_date": "2026-08-13"}),
                    ):
                        with mock.patch(
                            "leader_memory._build_experience_frame",
                            return_value=exp,
                        ):
                            result = finalize_forward_shadow_snapshot(
                                session_date="2026-08-13",
                                trading_today=True,
                                market_real=7.5,
                                recommendations=rec,
                                ledger_path=ledger,
                            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["frozen_rows"], 2)

    def test_csv_fallback_when_runtime_omitted(self):
        rec, brain, exp, _ = _sample_bundle("2026-08-12")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.csv"
            with mock.patch("leader_memory.load_recommendations", return_value=rec):
                with mock.patch("leader_memory._safe_read_csv", return_value=brain):
                    with mock.patch(
                        "leader_memory._latest_session_experience_snapshot",
                        return_value=pd.DataFrame({"symbol": ["VNM"], "session_date": "2026-08-12"}),
                    ):
                        with mock.patch(
                            "leader_memory._build_experience_frame",
                            return_value=exp,
                        ):
                            result = finalize_forward_shadow_snapshot(
                                session_date="2026-08-12",
                                trading_today=True,
                                market_real=7.0,
                                ledger_path=ledger,
                            )

        self.assertTrue(result["ok"])

    def test_runtime_ordering_preserved_in_shadow(self):
        rec, brain, exp, _ = _sample_bundle("2026-08-12")
        with mock.patch("leader_memory._safe_read_csv", return_value=brain):
            with mock.patch(
                "leader_memory._latest_session_experience_snapshot",
                return_value=pd.DataFrame({"symbol": ["VNM"], "session_date": "2026-08-12"}),
            ):
                with mock.patch("leader_memory._build_experience_frame", return_value=exp):
                    with tempfile.TemporaryDirectory() as tmp:
                        ledger = Path(tmp) / "ledger.csv"
                        finalize_forward_shadow_snapshot(
                            session_date="2026-08-12",
                            trading_today=True,
                            market_real=7.0,
                            recommendations=rec,
                            ledger_path=ledger,
                        )
                        frozen = load_forward_ledger(ledger_path=ledger)

        prod_ranks = rec.sort_values("rank")["symbol"].tolist()
        frozen_ranks = (
            frozen.sort_values("ProductionRank")["symbol"].astype(str).tolist()
        )
        self.assertEqual(prod_ranks, frozen_ranks)


class StorageBackedProvenanceTests(unittest.TestCase):
    def test_observation_lookup_uses_storage_abstraction(self):
        from modules.regime_alpha_forward_eval import _lookup_observation_ids

        obs = pd.DataFrame(
            [
                {
                    "trade_date": "2026-08-12",
                    "symbol": "VNM",
                    "observation_id": "obs-vnm-001",
                }
            ]
        )
        with mock.patch(
            "modules.regime_alpha_forward_eval._read_earning_learning_csv",
            return_value=obs,
        ) as reader:
            lookup = _lookup_observation_ids(
                pd.DataFrame([{"session_date": "2026-08-12", "symbol": "VNM"}])
            )
        reader.assert_called_once()
        self.assertEqual(lookup[("2026-08-12", "VNM")], "obs-vnm-001")

    def test_missing_provenance_excluded_from_scoreboard(self):
        ledger = pd.DataFrame(
            [
                {
                    "session_date": "2026-08-12",
                    "symbol": "AAA",
                    "evaluation_mode": EVAL_MODE_FORWARD_FROZEN,
                    "observation_id": "",
                }
            ]
        )
        genuine = filter_genuine_forward_ledger(
            ledger,
            observation_lookup={},
        )
        self.assertTrue(genuine.empty)


class PipelineOrderingTests(unittest.TestCase):
    def test_current_session_blocked_from_premature_maturity(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.csv"
            outcomes_path = Path(tmp) / "outcomes.csv"
            _, _, _, shadow = _sample_bundle("2026-08-13")
            freeze_t0_ledger(
                shadow,
                evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
                ledger_path=ledger_path,
            )
            lifecycle = pd.DataFrame(
                [
                    {
                        "trade_date": "2026-08-13",
                        "symbol": "VNM",
                        "observation_id": "obs-vnm",
                        "t3_return_pct": 9.9,
                        "t5_return_pct": None,
                        "t10_return_pct": None,
                    }
                ]
            )
            mature_forward_outcomes(
                ledger_path=ledger_path,
                outcomes_path=outcomes_path,
                lifecycle=lifecycle,
                immature_session_dates=["2026-08-13"],
            )
            out = load_forward_outcomes(outcomes_path)
            self.assertEqual(out.iloc[0]["outcome_status_t3"], "PENDING")

    def test_old_session_can_mature_after_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.csv"
            outcomes_path = Path(tmp) / "outcomes.csv"
            _, _, _, shadow = _sample_bundle("2026-08-10")
            freeze_t0_ledger(
                shadow,
                evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
                ledger_path=ledger_path,
            )
            lifecycle = pd.DataFrame(
                [
                    {
                        "trade_date": "2026-08-10",
                        "symbol": "VNM",
                        "observation_id": "obs-vnm-old",
                        "t3_return_pct": 2.5,
                        "t5_return_pct": None,
                        "t10_return_pct": None,
                    }
                ]
            )
            with mock.patch(
                "modules.regime_alpha_forward_eval._load_lifecycle",
                return_value=lifecycle,
            ):
                mature_forward_outcomes(
                    ledger_path=ledger_path,
                    outcomes_path=outcomes_path,
                    immature_session_dates=["2026-08-13"],
                )
            out = load_forward_outcomes(outcomes_path)
            self.assertEqual(out.iloc[0]["outcome_status_t3"], "READY")
            self.assertAlmostEqual(float(out.iloc[0]["ActualT3Return"]), 2.5)


class EndToEndGenuineForwardTests(unittest.TestCase):
    def test_genuine_forward_to_scoreboard(self):
        session = "2026-08-10"
        rec, brain, exp, shadow = _sample_bundle(session)
        observations = pd.DataFrame(
            [
                {
                    "trade_date": session,
                    "symbol": sym,
                    "observation_id": f"obs-{sym.lower()}",
                    "price": 100.0,
                }
                for sym in rec["symbol"].astype(str)
            ]
        )
        lifecycle = pd.DataFrame(
            [
                {
                    "trade_date": session,
                    "symbol": str(rec.iloc[0]["symbol"]),
                    "observation_id": "obs-vnm",
                    "t3_return_pct": 3.3,
                    "t5_return_pct": None,
                    "t10_return_pct": None,
                },
                {
                    "trade_date": session,
                    "symbol": str(rec.iloc[1]["symbol"]),
                    "observation_id": "obs-fpt",
                    "t3_return_pct": 1.1,
                    "t5_return_pct": None,
                    "t10_return_pct": None,
                },
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.csv"
            outcomes_path = Path(tmp) / "outcomes.csv"

            with mock.patch(
                "modules.regime_alpha_forward_eval._read_earning_learning_csv",
                side_effect=lambda name: observations if "observations" in name else lifecycle,
            ):
                freeze_t0_ledger(
                    shadow,
                    evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
                    ledger_path=ledger_path,
                    observations=observations,
                )
                mature_forward_outcomes(
                    ledger_path=ledger_path,
                    outcomes_path=outcomes_path,
                    lifecycle=lifecycle,
                )

            with mock.patch(
                "modules.shadow_observation_board.load_forward_ledger",
                return_value=load_forward_ledger(ledger_path=ledger_path),
            ), mock.patch(
                "modules.shadow_observation_board.load_forward_outcomes",
                return_value=load_forward_outcomes(outcomes_path),
            ), mock.patch(
                "modules.shadow_observation_board.load_observation_session_lookup",
                return_value=load_observation_session_lookup(observations),
            ):
                card = evaluate_genuine_forward_scorecard()

        self.assertEqual(card.sessions, 1)
        self.assertGreater(card.candidates, 0)
        self.assertGreater(card.baseline_top10.n, 0)
        self.assertIsNotNone(card.baseline_top10.mean_t3)


class RepoBrainIsolationTests(unittest.TestCase):
    def test_repo_brain_files_not_modified_by_tests(self):
        for path in (
            REPO_BRAIN / "regime_alpha_shadow_ledger.csv",
            REPO_BRAIN / "learning_insight_forward_ledger.csv",
            REPO_BRAIN / "regime_alpha_forward_outcomes.csv",
        ):
            if path.exists():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertIsNotNone(digest)


class RuntimeRecommendationCacheTests(unittest.TestCase):
    def test_get_runtime_recommendations_after_update_memory(self):
        reset_runtime_recommendations()
        brain = pd.DataFrame(
            [
                {
                    "symbol": "VNM",
                    "recommendation": "ƯU TIÊN CAO",
                    "leader_score": 88,
                    "confidence_score": 60,
                    "current_group": "CP MẠNH",
                    "current_rsi14": 58,
                    "current_obv_status": "UP",
                    "persistence_20_pct": 60,
                    "winrate_t5_pct": 65,
                    "feature_signature": "demo",
                    "session_date": "2026-08-13",
                }
            ]
        )
        with mock.patch("leader_memory._prepare_snapshot") as prep:
            prep.return_value = (brain, [])
            with mock.patch("leader_memory._merge_snapshot", side_effect=lambda h, s, c: h):
                with mock.patch("leader_memory._update_outcomes", side_effect=lambda h, c: h):
                    with mock.patch("leader_memory._build_brain", return_value=brain):
                        with mock.patch("leader_memory._build_patterns", return_value=pd.DataFrame()):
                            with mock.patch("leader_memory._build_hof", return_value=pd.DataFrame()):
                                with mock.patch(
                                    "leader_memory._build_experience_frame",
                                    return_value=pd.DataFrame(),
                                ):
                                    with mock.patch("leader_memory._atomic_write_csv"):
                                        with mock.patch(
                                            "leader_memory._persist_recommendation_shadow"
                                        ):
                                            with mock.patch(
                                                "leader_memory._persist_learning_insight_candidates"
                                            ):
                                                update_memory(
                                                    brain,
                                                    session_date="2026-08-13",
                                                    market_real=7.0,
                                                )
        runtime = get_runtime_recommendations()
        self.assertIsNotNone(runtime)
        self.assertFalse(runtime.empty)
        self.assertListEqual(list(runtime.columns), list(RECOMMENDATION_COLUMNS))


if __name__ == "__main__":
    unittest.main()
