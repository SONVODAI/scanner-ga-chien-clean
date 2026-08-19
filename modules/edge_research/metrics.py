"""
Outcome profile metrics for Edge Research discovery (Phase 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

import numpy as np
import pandas as pd

HORIZONS: Sequence[str] = ("T3", "T5", "T10")
RETURN_COLUMNS = {"T3": "t3_return", "T5": "t5_return", "T10": "t10_return"}


@dataclass(frozen=True)
class HorizonProfile:
    horizon: str
    n: int
    mean_return: Optional[float]
    median_return: Optional[float]
    win_rate_gt_0: Optional[float]
    rate_ge_3pct: Optional[float]
    rate_ge_5pct: Optional[float]
    rate_le_minus_3pct: Optional[float]
    rate_le_minus_5pct: Optional[float]

    def to_dict(self, prefix: str = "") -> Dict[str, Any]:
        p = f"{prefix}_" if prefix else ""
        return {
            f"{p}n": self.n,
            f"{p}mean": self.mean_return,
            f"{p}median": self.median_return,
            f"{p}win_rate": self.win_rate_gt_0,
            f"{p}rate_ge_3": self.rate_ge_3pct,
            f"{p}rate_ge_5": self.rate_ge_5pct,
            f"{p}rate_le_minus_3": self.rate_le_minus_3pct,
            f"{p}rate_le_minus_5": self.rate_le_minus_5pct,
        }


def _rate(series: pd.Series, predicate) -> Optional[float]:
    if series.empty:
        return None
    return float(predicate(series).sum() / len(series) * 100.0)


def compute_horizon_profile(returns: pd.Series, horizon: str) -> HorizonProfile:
    """Compute outcome profile for one horizon from matured return labels."""
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    n = int(len(clean))
    if n == 0:
        return HorizonProfile(
            horizon=horizon,
            n=0,
            mean_return=None,
            median_return=None,
            win_rate_gt_0=None,
            rate_ge_3pct=None,
            rate_ge_5pct=None,
            rate_le_minus_3pct=None,
            rate_le_minus_5pct=None,
        )
    return HorizonProfile(
        horizon=horizon,
        n=n,
        mean_return=float(clean.mean()),
        median_return=float(clean.median()),
        win_rate_gt_0=_rate(clean, lambda s: s > 0),
        rate_ge_3pct=_rate(clean, lambda s: s >= 3),
        rate_ge_5pct=_rate(clean, lambda s: s >= 5),
        rate_le_minus_3pct=_rate(clean, lambda s: s <= -3),
        rate_le_minus_5pct=_rate(clean, lambda s: s <= -5),
    )


def compute_incremental_metrics(
    candidate: HorizonProfile,
    baseline: HorizonProfile,
) -> Dict[str, Optional[float]]:
    """Incremental edge vs same-state baseline."""

    def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b is None:
            return None
        return float(a - b)

    return {
        "incremental_mean": _delta(candidate.mean_return, baseline.mean_return),
        "incremental_median": _delta(candidate.median_return, baseline.median_return),
        "incremental_win_rate": _delta(candidate.win_rate_gt_0, baseline.win_rate_gt_0),
        "downside_delta_3": _delta(candidate.rate_le_minus_3pct, baseline.rate_le_minus_3pct),
        "downside_delta_5": _delta(candidate.rate_le_minus_5pct, baseline.rate_le_minus_5pct),
    }


def has_positive_incremental_evidence(metrics: Dict[str, Optional[float]]) -> bool:
    """Transparent promotion guard — all core incremental signals must be positive."""
    im = metrics.get("incremental_median")
    imean = metrics.get("incremental_mean")
    iwr = metrics.get("incremental_win_rate")
    dd3 = metrics.get("downside_delta_3")
    dd5 = metrics.get("downside_delta_5")
    if im is None or imean is None or iwr is None:
        return False
    if im <= 0 or imean <= 0 or iwr <= 0:
        return False
    if dd3 is not None and dd3 > 5:
        return False
    if dd5 is not None and dd5 > 3:
        return False
    return True


def select_best_horizon(
    candidate_profiles: Dict[str, HorizonProfile],
    baseline_profiles: Dict[str, HorizonProfile],
) -> Optional[str]:
    """
    Deterministic best-horizon selection.

    Lexicographic over horizons T5, T3, T10 (T5 preferred on ties):
    1. incremental median > 0
    2. incremental mean > 0
    3. incremental win rate > 0
    4. lower downside delta (prefer less negative)
    5. higher candidate N
    """
    order = ("T5", "T3", "T10")
    ranked: list[tuple] = []
    horizon_pref = {"T5": 3, "T3": 2, "T10": 1}
    for h in order:
        cp = candidate_profiles.get(h)
        bp = baseline_profiles.get(h)
        if cp is None or bp is None or cp.n == 0:
            continue
        inc = compute_incremental_metrics(cp, bp)
        if not has_positive_incremental_evidence(inc):
            continue
        ranked.append(
            (
                inc.get("incremental_median") or -999,
                inc.get("incremental_mean") or -999,
                inc.get("incremental_win_rate") or -999,
                -(inc.get("downside_delta_3") or 0),
                cp.n,
                horizon_pref.get(h, 0),
            )
        )
    if not ranked:
        return None
    ranked.sort(reverse=True)
    # Recover horizon from preference score
    pref_to_h = {v: k for k, v in horizon_pref.items()}
    return pref_to_h.get(ranked[0][-1], "T5")
