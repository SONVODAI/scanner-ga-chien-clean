"""
Raw empirical evidence ingestion for cross-sectional dispersion anomaly detection.

Operates on panel numeric columns only — no OBS_* or GAP_* labels as input.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from modules.edge_research.opr_bridge.constants import (
    DISPERSION_FEATURE,
    MIN_COHORT_N_PER_QUINTILE,
    MIN_SYMBOLS_PER_DATE,
    OUTCOME_FIELD,
)


@dataclass(frozen=True)
class QuintileSlice:
    quintile: int
    n: int
    mean_outcome: float
    mean_dispersion: float


@dataclass(frozen=True)
class DispersionEvidencePayload:
    """Raw/derived market evidence for one focal observation date."""

    focal_date: str
    data_cutoff_date: str
    dispersion_feature: str
    outcome_field: str
    cross_sectional_dispersion: float
    cross_sectional_n: int
    quintile_slices: Tuple[QuintileSlice, ...]
    quintile_return_spread: float
    monotonicity_score: float
    historical_dispersion_series: Tuple[float, ...]
    historical_dates: Tuple[str, ...]
    empirical_artifacts: Tuple[Dict[str, Any], ...]
    evidence_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "focal_date": self.focal_date,
            "data_cutoff_date": self.data_cutoff_date,
            "dispersion_feature": self.dispersion_feature,
            "outcome_field": self.outcome_field,
            "cross_sectional_dispersion": self.cross_sectional_dispersion,
            "cross_sectional_n": self.cross_sectional_n,
            "quintile_slices": [
                {
                    "quintile": q.quintile,
                    "n": q.n,
                    "mean_outcome": q.mean_outcome,
                    "mean_dispersion": q.mean_dispersion,
                }
                for q in self.quintile_slices
            ],
            "quintile_return_spread": self.quintile_return_spread,
            "monotonicity_score": self.monotonicity_score,
            "historical_dispersion_series": list(self.historical_dispersion_series),
            "historical_dates": list(self.historical_dates),
            "empirical_artifacts": list(self.empirical_artifacts),
            "evidence_hash": self.evidence_hash,
        }


def _content_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _daily_cross_sectional_std(panel: pd.DataFrame, feature: str) -> pd.Series:
    """Std of feature within each trade_date — empirical dispersion measure."""
    return panel.groupby("trade_date")[feature].std()


def _assign_quintiles(values: pd.Series, n_quintiles: int = 5) -> pd.Series:
    """Deterministic quintile assignment; duplicates dropped to rank."""
    ranked = values.rank(method="first")
    try:
        return pd.qcut(ranked, q=n_quintiles, labels=False, duplicates="drop")
    except ValueError:
        return pd.Series(index=values.index, dtype=float)


def _monotonicity_score(means: List[float]) -> float:
    """1.0 = perfectly monotonic increasing; 0.0 = maximally non-monotonic."""
    if len(means) < 2:
        return 1.0
    diffs = [means[i + 1] - means[i] for i in range(len(means) - 1)]
    if not diffs:
        return 1.0
    same_sign = all(d >= 0 for d in diffs) or all(d <= 0 for d in diffs)
    return 1.0 if same_sign else 0.0


def ingest_dispersion_evidence(
    panel: pd.DataFrame,
    *,
    focal_date: str,
    data_cutoff_date: str,
    dispersion_feature: str = DISPERSION_FEATURE,
    outcome_field: str = OUTCOME_FIELD,
    lookback_dates: Optional[int] = None,
) -> Optional[DispersionEvidencePayload]:
    """
    Build raw dispersion evidence for a focal date from panel rows.

    Returns None if insufficient empirical data.
    """
    required = {"trade_date", dispersion_feature, outcome_field}
    if not required.issubset(panel.columns):
        return None

    df = panel.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    cutoff = str(data_cutoff_date)
    df = df[df["trade_date"] <= cutoff]

    dates = sorted(df["trade_date"].unique())
    if focal_date not in dates:
        return None

    focal_idx = dates.index(focal_date)
    if lookback_dates is not None:
        start_idx = max(0, focal_idx - lookback_dates)
        hist_dates = dates[start_idx:focal_idx]
    else:
        hist_dates = dates[:focal_idx]

    daily_std = _daily_cross_sectional_std(df, dispersion_feature)
    focal_slice = df[df["trade_date"] == focal_date].dropna(subset=[dispersion_feature, outcome_field])
    if len(focal_slice) < MIN_SYMBOLS_PER_DATE:
        return None

    focal_dispersion = float(focal_slice[dispersion_feature].std())
    if np.isnan(focal_dispersion):
        return None

    focal_slice = focal_slice.copy()
    focal_slice["_q"] = _assign_quintiles(focal_slice[dispersion_feature])
    quintile_slices: List[QuintileSlice] = []
    for q in sorted(focal_slice["_q"].dropna().unique()):
        q_rows = focal_slice[focal_slice["_q"] == q]
        if len(q_rows) < MIN_COHORT_N_PER_QUINTILE:
            continue
        quintile_slices.append(
            QuintileSlice(
                quintile=int(q),
                n=len(q_rows),
                mean_outcome=float(q_rows[outcome_field].mean()),
                mean_dispersion=float(q_rows[dispersion_feature].mean()),
            )
        )

    if len(quintile_slices) < 2:
        return None

    quintile_slices.sort(key=lambda x: x.quintile)
    outcome_means = [q.mean_outcome for q in quintile_slices]
    spread = float(max(outcome_means) - min(outcome_means))
    mono = _monotonicity_score(outcome_means)

    hist_series = tuple(float(daily_std.get(d, float("nan"))) for d in hist_dates)
    hist_series_clean = tuple(v for v in hist_series if not np.isnan(v))

    artifacts: List[Dict[str, Any]] = [
        {"name": "cross_sectional_dispersion", "value": focal_dispersion, "date": focal_date},
        {"name": "cross_sectional_n", "value": len(focal_slice), "date": focal_date},
        {"name": "quintile_return_spread", "value": spread, "date": focal_date},
        {"name": "monotonicity_score", "value": mono, "date": focal_date},
    ]
    for q in quintile_slices:
        artifacts.append(
            {
                "name": f"quintile_{q.quintile}_mean_{outcome_field}",
                "value": q.mean_outcome,
                "n": q.n,
            }
        )

    payload_dict = {
        "focal_date": focal_date,
        "dispersion_feature": dispersion_feature,
        "outcome_field": outcome_field,
        "cross_sectional_dispersion": round(focal_dispersion, 6),
        "quintile_return_spread": round(spread, 6),
        "quintile_slices": [(q.quintile, round(q.mean_outcome, 6)) for q in quintile_slices],
    }
    evidence_hash = _content_hash(payload_dict)

    return DispersionEvidencePayload(
        focal_date=focal_date,
        data_cutoff_date=cutoff,
        dispersion_feature=dispersion_feature,
        outcome_field=outcome_field,
        cross_sectional_dispersion=focal_dispersion,
        cross_sectional_n=len(focal_slice),
        quintile_slices=tuple(quintile_slices),
        quintile_return_spread=spread,
        monotonicity_score=mono,
        historical_dispersion_series=hist_series_clean,
        historical_dates=tuple(hist_dates),
        empirical_artifacts=tuple(artifacts),
        evidence_hash=evidence_hash,
    )


def find_eligible_focal_dates(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    dispersion_feature: str = DISPERSION_FEATURE,
    outcome_field: str = OUTCOME_FIELD,
    min_symbols: int = MIN_SYMBOLS_PER_DATE,
) -> List[str]:
    """Dates with sufficient cross-section for dispersion computation."""
    df = panel.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    df = df[df["trade_date"] <= str(data_cutoff_date)]
    eligible = []
    for date, grp in df.groupby("trade_date"):
        sub = grp.dropna(subset=[dispersion_feature, outcome_field])
        if len(sub) >= min_symbols and sub[dispersion_feature].std() > 0:
            eligible.append(str(date))
    return sorted(eligible)
