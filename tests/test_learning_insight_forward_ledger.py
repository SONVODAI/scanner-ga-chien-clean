"""Immutable T0 forward ledger for Learning Insight Candidates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from modules.learning_insight_candidates import (
    INSIGHT_EVIDENCE_NONE,
    INSIGHT_EVIDENCE_QUALIFIED,
    build_learning_insight_candidates,
    classify_insight_evidence_status,
    compute_insight_candidate_score,
)
from modules.regime_alpha_forward_eval import (
    EVAL_MODE_FORWARD_FROZEN,
    INSIGHT_IMMUTABLE_T0_FIELDS,
    freeze_insight_t0_ledger,
    load_insight_forward_ledger,
)


def _qualified_pattern_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market_context_key": "6-8|40-60|6-8",
                "pattern_key": "DNA_A",
                "stock_pattern_key": "DNA_A",
                "samples": 20,
                "win_rate_pct": 68.0,
                "win_rate_lower_bound_pct": 60.0,
                "horizon": 5,
            }
        ]
    )


def _weak_pattern_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market_context_key": "6-8|40-60|6-8",
                "pattern_key": "DNA_A",
                "stock_pattern_key": "DNA_A",
                "samples": 2,
                "win_rate_pct": 90.0,
                "win_rate_lower_bound_pct": 85.0,
                "horizon": 5,
            }
        ]
    )


class TestInsightEvidenceStatus(unittest.TestCase):
    def test_qualified_when_effective_conf_positive(self):
        result = compute_insight_candidate_score(
            pattern_row={
                "samples": 20,
                "win_rate_pct": 68.0,
                "win_rate_lower_bound_pct": 60.0,
                "pattern_key": "DNA_A",
                "market_context_key": "6-8|40-60|6-8",
            },
            continuation_row={
                "samples_t10": 15,
                "continuation_score": 72.0,
                "market_context_key": "6-8|40-60|6-8",
            },
            context_match_mode="FAMILY_CONTEXT",
        )
        self.assertEqual(result.insight_evidence_status, INSIGHT_EVIDENCE_QUALIFIED)
        self.assertGreater(result.insight_candidate_score, 50.0)

    def test_insufficient_when_rows_exist_but_samples_low(self):
        status = classify_insight_evidence_status(
            effective_conf=0.0,
            pattern_row={"samples": 2},
            continuation_row=None,
            context_match_mode="GLOBAL_DNA",
        )
        self.assertEqual(status, "INSUFFICIENT_EVIDENCE")

    def test_no_evidence_when_no_rows(self):
        status = classify_insight_evidence_status(
            effective_conf=0.0,
            pattern_row=None,
            continuation_row=None,
            context_match_mode="NO_PATTERN_MATCH",
        )
        self.assertEqual(status, INSIGHT_EVIDENCE_NONE)

    def test_qualified_rank_only_for_qualified(self):
        rec = pd.DataFrame(
            [
                {
                    "rank": 1,
                    "symbol": "AAA",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 80,
                    "confidence_score": 50,
                    "pattern_match_score": 60,
                    "updated_at": "2026-08-08",
                },
                {
                    "rank": 2,
                    "symbol": "BBB",
                    "recommendation": "THEO DÕI MUA",
                    "leader_score": 70,
                    "confidence_score": 50,
                    "pattern_match_score": 60,
                    "updated_at": "2026-08-08",
                },
            ]
        )
        brain = pd.DataFrame(
            [
                {"symbol": "AAA", "leader_score": 80},
                {"symbol": "BBB", "leader_score": 70},
            ]
        )
        with mock.patch(
            "modules.learning_insight_candidates.get_pattern_knowledge",
            return_value=_qualified_pattern_df(),
        ), mock.patch(
            "modules.learning_insight_candidates.get_continuation_knowledge",
            return_value=pd.DataFrame(),
        ), mock.patch(
            "modules.learning_insight_candidates._decision_rows_for_pattern_keys",
            side_effect=lambda frame, **kwargs: pd.DataFrame(
                [
                    {
                        "symbol": str(frame.iloc[0]["symbol"]),
                        "stock_pattern_key": "DNA_A"
                        if str(frame.iloc[0]["symbol"]) == "AAA"
                        else "DNA_B",
                        "market_context_key": "6-8|40-60|6-8",
                    }
                ]
            ),
        ):
            insight = build_learning_insight_candidates(
                rec,
                brain,
                session_date="2026-08-08",
                market_real=7.0,
                market_forecast=7.0,
                breadth=50.0,
            )

        aaa = insight[insight["symbol"] == "AAA"].iloc[0]
        bbb = insight[insight["symbol"] == "BBB"].iloc[0]
        self.assertEqual(aaa["InsightEvidenceStatus"], INSIGHT_EVIDENCE_QUALIFIED)
        self.assertEqual(bbb["InsightEvidenceStatus"], INSIGHT_EVIDENCE_NONE)
        self.assertEqual(int(aaa["InsightQualifiedRank"]), 1)
        self.assertTrue(pd.isna(bbb["InsightQualifiedRank"]))


class TestInsightForwardLedgerImmutability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger_path = Path(self.tmp.name) / "insight_ledger.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def _build_live_insight(self, pattern_df: pd.DataFrame) -> pd.DataFrame:
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
            return_value=pattern_df,
        ), mock.patch(
            "modules.learning_insight_candidates.get_continuation_knowledge",
            return_value=pd.DataFrame(),
        ), mock.patch(
            "modules.learning_insight_candidates._decision_rows_for_pattern_keys",
            return_value=pd.DataFrame(
                [
                    {
                        "symbol": "AAA",
                        "stock_pattern_key": "DNA_A",
                        "market_context_key": "6-8|40-60|6-8",
                    }
                ]
            ),
        ):
            return build_learning_insight_candidates(
                rec,
                brain,
                session_date="2026-08-08",
                market_real=7.0,
                market_forecast=7.0,
                breadth=50.0,
            )

    def test_frozen_insight_unchanged_after_knowledge_update(self):
        live_v1 = self._build_live_insight(_weak_pattern_df())
        self.assertEqual(live_v1.iloc[0]["InsightEvidenceStatus"], "INSUFFICIENT_EVIDENCE")

        freeze_insight_t0_ledger(
            live_v1,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        frozen = load_insight_forward_ledger(ledger_path=self.ledger_path)
        self.assertEqual(len(frozen), 1)
        frozen_row = frozen.iloc[0]

        live_v2 = self._build_live_insight(_qualified_pattern_df())
        self.assertEqual(live_v2.iloc[0]["InsightEvidenceStatus"], INSIGHT_EVIDENCE_QUALIFIED)
        self.assertGreater(float(live_v2.iloc[0]["InsightCandidateScore"]), 50.0)

        freeze_insight_t0_ledger(
            live_v2,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        after = load_insight_forward_ledger(ledger_path=self.ledger_path)
        self.assertEqual(len(after), 1)

        row = after.iloc[0]
        for field in INSIGHT_IMMUTABLE_T0_FIELDS:
            if field in {"frozen_at"}:
                continue
            self.assertEqual(
                str(row.get(field)),
                str(frozen_row.get(field)),
                msg=f"T0 field {field} must remain immutable",
            )

    def test_forward_frozen_rows_not_overwritten_on_rerun(self):
        insight = self._build_live_insight(_qualified_pattern_df())
        freeze_insight_t0_ledger(
            insight,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        first = load_insight_forward_ledger(ledger_path=self.ledger_path).copy()

        mutated = insight.copy()
        mutated["InsightCandidateScore"] = 99.0
        mutated["InsightRank"] = 99
        freeze_insight_t0_ledger(
            mutated,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=self.ledger_path,
        )
        second = load_insight_forward_ledger(ledger_path=self.ledger_path)
        pd.testing.assert_frame_equal(first.reset_index(drop=True), second.reset_index(drop=True))


if __name__ == "__main__":
    unittest.main()
