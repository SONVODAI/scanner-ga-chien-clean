"""
Empirical surprise detection for cross-sectional dispersion anomalies.

Determines whether dispersion is noteworthy relative to historical self-baseline.
Does NOT use OBS_* or GAP_* labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from modules.edge_research.opr_bridge.constants import (
    MIN_DATES_FOR_BASELINE,
    MIN_QUINTILE_COUNT,
    QUINTILE_SPREAD_THRESHOLD,
    SURPRISE_ZSCORE_THRESHOLD,
)
from modules.edge_research.opr_bridge.evidence_ingest import DispersionEvidencePayload


@dataclass(frozen=True)
class SurpriseAssessment:
    """Empirical reason observation is noteworthy — reconstructable from evidence."""

    is_surprising: bool
    reason_code: str
    zscore_vs_baseline: float
    baseline_mean: float
    baseline_std: float
    focal_dispersion: float
    quintile_spread: float
    monotonicity_break: bool
    surprise_basis_text: str
    reference_type: str

    def to_dict(self) -> dict:
        return {
            "is_surprising": self.is_surprising,
            "reason_code": self.reason_code,
            "zscore_vs_baseline": self.zscore_vs_baseline,
            "baseline_mean": self.baseline_mean,
            "baseline_std": self.baseline_std,
            "focal_dispersion": self.focal_dispersion,
            "quintile_spread": self.quintile_spread,
            "monotonicity_break": self.monotonicity_break,
            "surprise_basis_text": self.surprise_basis_text,
            "reference_type": self.reference_type,
        }


def assess_dispersion_surprise(evidence: DispersionEvidencePayload) -> SurpriseAssessment:
    """
    Compare focal dispersion and quintile structure against historical self-baseline.
    """
    hist = list(evidence.historical_dispersion_series)
    focal = evidence.cross_sectional_dispersion
    spread = evidence.quintile_return_spread
    mono_break = evidence.monotonicity_score < 1.0

    if len(hist) < MIN_DATES_FOR_BASELINE:
        return SurpriseAssessment(
            is_surprising=False,
            reason_code="INSUFFICIENT_BASELINE",
            zscore_vs_baseline=0.0,
            baseline_mean=float(np.mean(hist)) if hist else 0.0,
            baseline_std=float(np.std(hist)) if hist else 0.0,
            focal_dispersion=focal,
            quintile_spread=spread,
            monotonicity_break=mono_break,
            surprise_basis_text=(
                f"Only {len(hist)} historical dates available; "
                f"minimum {MIN_DATES_FOR_BASELINE} required for baseline."
            ),
            reference_type="historical_self_baseline",
        )

    baseline_mean = float(np.mean(hist))
    baseline_std = float(np.std(hist))
    if baseline_std <= 1e-9:
        zscore = 0.0
    else:
        zscore = (focal - baseline_mean) / baseline_std

    reasons: List[str] = []
    surprising = False

    if abs(zscore) >= SURPRISE_ZSCORE_THRESHOLD:
        surprising = True
        direction = "elevated" if zscore > 0 else "depressed"
        reasons.append(
            f"Cross-sectional {evidence.dispersion_feature} dispersion ({focal:.4f}) is "
            f"{direction} vs {len(hist)}-date baseline (mean={baseline_mean:.4f}, "
            f"std={baseline_std:.4f}, z={zscore:.2f})."
        )

    if spread >= QUINTILE_SPREAD_THRESHOLD and len(evidence.quintile_slices) >= MIN_QUINTILE_COUNT:
        surprising = True
        reasons.append(
            f"Quintile spread of {evidence.outcome_field} across {evidence.dispersion_feature} "
            f"tiers is {spread:.4f} (threshold={QUINTILE_SPREAD_THRESHOLD})."
        )

    if mono_break and spread >= QUINTILE_SPREAD_THRESHOLD * 0.5:
        surprising = True
        means = [q.mean_outcome for q in evidence.quintile_slices]
        reasons.append(
            f"Quintile outcome means break monotonicity: {[round(m, 4) for m in means]}."
        )

    if not surprising:
        return SurpriseAssessment(
            is_surprising=False,
            reason_code="NOT_SURPRISING",
            zscore_vs_baseline=zscore,
            baseline_mean=baseline_mean,
            baseline_std=baseline_std,
            focal_dispersion=focal,
            quintile_spread=spread,
            monotonicity_break=mono_break,
            surprise_basis_text=(
                f"Dispersion z={zscore:.2f} below threshold {SURPRISE_ZSCORE_THRESHOLD}; "
                f"quintile spread {spread:.4f} below {QUINTILE_SPREAD_THRESHOLD}."
            ),
            reference_type="historical_self_baseline",
        )

    reason_code = "DISPERSION_ANOMALY"
    if mono_break:
        reason_code = "DISPERSION_ANOMALY_WITH_MONOTONICITY_BREAK"

    return SurpriseAssessment(
        is_surprising=True,
        reason_code=reason_code,
        zscore_vs_baseline=zscore,
        baseline_mean=baseline_mean,
        baseline_std=baseline_std,
        focal_dispersion=focal,
        quintile_spread=spread,
        monotonicity_break=mono_break,
        surprise_basis_text=" ".join(reasons),
        reference_type="historical_self_baseline",
    )
