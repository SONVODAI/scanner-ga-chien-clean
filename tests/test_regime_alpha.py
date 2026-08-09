"""Deterministic unit tests for modules.regime_alpha (Level 4 N2)."""

from __future__ import annotations

import math
import unittest
from datetime import date, timedelta

import pandas as pd

from modules.regime_alpha import (
    NEUTRAL_RAS,
    compute_alpha_confidence,
    compute_final_recommendation_score,
    compute_horizon_ev,
    compute_regime_alpha_score,
    compute_technical_prior,
    resolve_context_match,
    shrink_toward_neutral,
)


def _pattern_row(
    *,
    ctx="6-8|40-60|6-8",
    stock="DNA_TEST",
    horizon=5,
    samples=20,
    wlb=65.0,
    win_rate=70.0,
    median=5.0,
    avg_dd=-3.0,
    worst=-2.0,
    last_seen="2026-08-01",
):
    return {
        "market_context_key": ctx,
        "stock_pattern_key": stock,
        "pattern_key": "pk",
        "horizon": horizon,
        "samples": samples,
        "win_rate_lower_bound_pct": wlb,
        "win_rate_pct": win_rate,
        "median_return_pct": median,
        "avg_max_drawdown_pct": avg_dd,
        "worst_return_pct": worst,
        "last_seen": last_seen,
    }


def _continuation_row(
    *,
    ctx="6-8|40-60|6-8",
    stock="DNA_TEST",
    samples_t10=10,
    continuation_score=65.0,
    t3_to_t10_lower_bound_pct=60.0,
):
    return {
        "market_context_key": ctx,
        "stock_pattern_key": stock,
        "pattern_key": "pk",
        "samples_t10": samples_t10,
        "continuation_score": continuation_score,
        "t3_to_t10_lower_bound_pct": t3_to_t10_lower_bound_pct,
    }


class TestHorizonEv(unittest.TestCase):
    def test_strong_positive_outcome_above_neutral(self):
        ev = compute_horizon_ev(_pattern_row(wlb=72, median=6.0, worst=-1.0))
        self.assertIsNotNone(ev)
        self.assertGreater(ev, NEUTRAL_RAS)

    def test_strong_negative_outcome_below_neutral(self):
        ev = compute_horizon_ev(
            _pattern_row(wlb=25, median=-4.0, avg_dd=-12.0, worst=-10.0)
        )
        self.assertIsNotNone(ev)
        self.assertLess(ev, NEUTRAL_RAS)

    def test_median_return_differentiates_same_win_rate(self):
        high_med = compute_horizon_ev(_pattern_row(wlb=60, median=5.0))
        low_med = compute_horizon_ev(_pattern_row(wlb=60, median=0.2))
        self.assertGreater(high_med, low_med)

    def test_high_win_rate_negative_median_penalized(self):
        ev = compute_horizon_ev(_pattern_row(wlb=70, median=-2.0, worst=-6.0))
        self.assertLess(ev, NEUTRAL_RAS)

    def test_missing_row_returns_none_not_bad(self):
        self.assertIsNone(compute_horizon_ev(None))

    def test_zero_samples_returns_none(self):
        self.assertIsNone(compute_horizon_ev(_pattern_row(samples=0)))

    def test_zero_median_return_is_valid(self):
        ev_zero = compute_horizon_ev(_pattern_row(median=0.0))
        ev_missing = compute_horizon_ev(
            {k: v for k, v in _pattern_row().items() if k != "median_return_pct"}
        )
        self.assertIsNotNone(ev_zero)
        self.assertIsNone(ev_missing)

    def test_extreme_return_winsorized(self):
        ev_clip = compute_horizon_ev(_pattern_row(median=50.0))
        ev_normal = compute_horizon_ev(_pattern_row(median=5.0))
        self.assertLess(ev_clip, 100.0)
        self.assertGreater(ev_normal, NEUTRAL_RAS)


class TestHorizonRenormalization(unittest.TestCase):
    def test_single_available_horizon_uses_full_weight(self):
        pk = pd.DataFrame([_pattern_row(horizon=5)])
        result = compute_regime_alpha_score(
            "6-8|40-60|6-8", "DNA_TEST", pattern_knowledge=pk
        )
        ev5 = compute_horizon_ev(_pattern_row(horizon=5))
        self.assertAlmostEqual(result.raw_ras_before_discount, ev5, places=4)

    def test_missing_horizon_does_not_penalize(self):
        pk = pd.DataFrame([_pattern_row(horizon=5)])
        full = compute_regime_alpha_score(
            "6-8|40-60|6-8", "DNA_TEST", pattern_knowledge=pk
        )
        pk_three = pd.DataFrame(
            [
                _pattern_row(horizon=3, median=0.2, wlb=40),
                _pattern_row(horizon=5, median=5.0, wlb=70),
                _pattern_row(horizon=10, median=0.2, wlb=40),
            ]
        )
        mixed = compute_regime_alpha_score(
            "6-8|40-60|6-8", "DNA_TEST", pattern_knowledge=pk_three
        )
        self.assertGreater(full.regime_alpha_score, mixed.regime_alpha_score)


class TestAlphaConfidence(unittest.TestCase):
    def test_n0_zero_authority(self):
        self.assertEqual(compute_alpha_confidence(0, "EXACT"), 0.0)

    def test_n3_zero_authority(self):
        self.assertEqual(compute_alpha_confidence(3, "EXACT"), 0.0)

    def test_n5_still_zero_sample_weight(self):
        self.assertEqual(compute_alpha_confidence(5, "EXACT"), 0.0)

    def test_n10_partial_authority(self):
        c10 = compute_alpha_confidence(10, "EXACT", last_seen=date.today())
        self.assertGreater(c10, 0.0)
        self.assertLess(c10, 0.5)

    def test_n20_high_but_capped(self):
        c20 = compute_alpha_confidence(20, "EXACT", last_seen=date.today())
        c100 = compute_alpha_confidence(100, "EXACT", last_seen=date.today())
        self.assertLessEqual(c20, 0.85)
        self.assertLessEqual(c100, 0.85)
        self.assertAlmostEqual(c20, c100, places=6)

    def test_none_level_zero(self):
        self.assertEqual(compute_alpha_confidence(100, "NONE"), 0.0)

    def test_context_authority_order(self):
        today = date.today()
        c_exact = compute_alpha_confidence(20, "EXACT", last_seen=today)
        c_family = compute_alpha_confidence(20, "FAMILY", last_seen=today)
        c_global = compute_alpha_confidence(20, "GLOBAL_DNA", last_seen=today)
        self.assertGreater(c_exact, c_family)
        self.assertGreater(c_family, c_global)


class TestContextFallback(unittest.TestCase):
    def test_exact_wins_over_family(self):
        pk = pd.DataFrame(
            [
                _pattern_row(ctx="6-8|40-60|6-8", median=5.0, samples=8),
                _pattern_row(
                    ctx="6-8|30-50|6-8",
                    median=0.5,
                    samples=100,
                    wlb=55,
                ),
            ]
        )
        match = resolve_context_match(
            "6-8|40-60|6-8", "DNA_TEST", pattern_knowledge=pk
        )
        self.assertEqual(match.level, "EXACT")

    def test_family_does_not_cross_forecast_family(self):
        pk = pd.DataFrame(
            [
                _pattern_row(ctx="4-6|20-40|4-6", median=8.0, samples=50, wlb=70),
            ]
        )
        match = resolve_context_match(
            "8-10|60-80|8-10", "DNA_TEST", pattern_knowledge=pk
        )
        self.assertNotEqual(match.level, "FAMILY")

    def test_global_na_context(self):
        pk = pd.DataFrame(
            [_pattern_row(ctx="NA|NA|<4", median=3.0, samples=30, wlb=60)]
        )
        match = resolve_context_match(
            "6-8|40-60|6-8", "DNA_TEST", pattern_knowledge=pk
        )
        self.assertEqual(match.level, "GLOBAL_DNA")

    def test_none_neutral(self):
        result = compute_regime_alpha_score(
            "6-8|40-60|6-8", "UNKNOWN_DNA", pattern_knowledge=pd.DataFrame()
        )
        self.assertEqual(result.regime_alpha_score, NEUTRAL_RAS)
        self.assertEqual(result.regime_alpha_confidence, 0.0)
        self.assertEqual(result.context_match_level, "NONE")

    def test_discount_shrinks_toward_50_not_zero(self):
        raw = 80.0
        discounted = shrink_toward_neutral(raw, 0.75)
        self.assertAlmostEqual(discounted, 72.5)
        self.assertGreater(discounted, NEUTRAL_RAS)

    def test_regime_difference_same_dna(self):
        pk = pd.DataFrame(
            [
                _pattern_row(
                    ctx="4-6|20-40|4-6", median=6.0, wlb=72, samples=25, horizon=5
                ),
                _pattern_row(
                    ctx="8-10|60-80|8-10",
                    median=-3.0,
                    wlb=28,
                    samples=25,
                    horizon=5,
                ),
            ]
        )
        weak = compute_regime_alpha_score(
            "4-6|20-40|4-6", "DNA_TEST", pattern_knowledge=pk
        )
        strong = compute_regime_alpha_score(
            "8-10|60-80|8-10", "DNA_TEST", pattern_knowledge=pk
        )
        self.assertGreater(weak.regime_alpha_score, NEUTRAL_RAS)
        self.assertLess(strong.regime_alpha_score, NEUTRAL_RAS)
        self.assertGreater(
            weak.regime_alpha_score - strong.regime_alpha_score, 10.0
        )


class TestDeterminism(unittest.TestCase):
    def test_identical_inputs_identical_outputs(self):
        pk = pd.DataFrame([_pattern_row(), _pattern_row(horizon=3, median=1.0)])
        ck = pd.DataFrame([_continuation_row()])
        a = compute_regime_alpha_score(
            "6-8|40-60|6-8",
            "DNA_TEST",
            pattern_knowledge=pk,
            continuation_knowledge=ck,
            as_of=date(2026, 8, 8),
        )
        b = compute_regime_alpha_score(
            "6-8|40-60|6-8",
            "DNA_TEST",
            pattern_knowledge=pk,
            continuation_knowledge=ck,
            as_of=date(2026, 8, 8),
        )
        self.assertEqual(a, b)


class TestTechnicalPrior(unittest.TestCase):
    def test_leader_dominates_prior(self):
        high = compute_technical_prior({"leader_score": 85, "current_rsi14": 48})
        low = compute_technical_prior({"leader_score": 55, "current_rsi14": 48})
        self.assertGreater(high, low)


class TestCounterfactualCalculations(unittest.TestCase):
    """Design counterfactuals as pure score math (not wired to admission)."""

    def test_scenario_a_b_outranks_a_when_close_technicals(self):
        tp_a, tp_b = 72.0, 70.0
        ras_a, ras_b = 35.0, 72.0
        w = 0.75
        final_a = (1 - w) * tp_a + w * ras_a
        final_b = (1 - w) * tp_b + w * ras_b
        self.assertGreater(final_b, final_a)

    def test_scenario_b_reject_rule_ras_floor(self):
        ras = 38.0
        w = 0.55
        self.assertLessEqual(ras, 42.0)
        self.assertGreaterEqual(w, 0.50)

    def test_scenario_c_admit_moderate_technical(self):
        tp, ras, w = 55.0, 68.0, 0.60
        final_score = compute_final_recommendation_score(ras, tp, w)
        self.assertGreater(final_score, 52.0)
        self.assertGreater(ras, 58.0)

    def test_scenario_d_regime_only_change(self):
        tp = 70.0
        w = 0.70
        final_weak = compute_final_recommendation_score(74.0, tp, w)
        final_strong = compute_final_recommendation_score(38.0, tp, w)
        self.assertGreater(final_weak - final_strong, 15.0)


class TestNoSafetyLogic(unittest.TestCase):
    def test_module_has_no_safety_gate_exports(self):
        import modules.regime_alpha as ra

        for name in dir(ra):
            if name.startswith("_"):
                continue
            self.assertNotIn("safety", name.lower())
            self.assertNotIn("hard_bad", name.lower())
            self.assertNotIn("block", name.lower())


class TestRealKnowledgeRowsReadOnly(unittest.TestCase):
    """Optional integration with on-disk knowledge (read-only)."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.pk = pd.read_csv(
                "data/earning_learning/pattern_knowledge.csv", low_memory=False
            )
        except FileNotFoundError:
            cls.pk = pd.DataFrame()

    def test_global_na_row_produces_ras(self):
        if self.pk.empty:
            self.skipTest("pattern_knowledge.csv not available")
        na_rows = self.pk[
            self.pk["market_context_key"].astype(str).str.startswith("NA|NA")
        ]
        if na_rows.empty:
            self.skipTest("no NA context rows")
        row = na_rows.iloc[0]
        stock = str(row["stock_pattern_key"])
        result = compute_regime_alpha_score(
            "6-8|40-60|6-8", stock, pattern_knowledge=self.pk
        )
        self.assertIn(result.context_match_level, {"GLOBAL_DNA", "EXACT", "FAMILY", "NONE"})
        self.assertGreaterEqual(result.regime_alpha_score, 0.0)
        self.assertLessEqual(result.regime_alpha_score, 100.0)


if __name__ == "__main__":
    unittest.main()
