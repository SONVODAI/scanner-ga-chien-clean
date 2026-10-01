"""
FC-1 metrics — always report N; never overclaim tiny samples.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from modules.forecast_research.fc1.contract import MIN_CALIBRATION_N, MIN_SPEARMAN_N


def _finite_pairs(y_true: Sequence[float], y_pred: Sequence[float]):
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    m = np.isfinite(yt) & np.isfinite(yp)
    return yt[m], yp[m]


def binary_metrics(y_true: Sequence[float], y_prob: Sequence[float]) -> Dict[str, Any]:
    yt, yp = _finite_pairs(y_true, y_prob)
    n = int(len(yt))
    out: Dict[str, Any] = {"n": n}
    if n == 0:
        out["status"] = "NO_DATA"
        return out
    base = float(yt.mean())
    # Hard classify at 0.5 for hit rate
    yhat = (yp >= 0.5).astype(float)
    hit = float((yhat == yt).mean())
    brier = float(np.mean((yp - yt) ** 2))
    # Lift vs always-predict base rate (Brier of base rate)
    brier_base = float(np.mean((base - yt) ** 2)) if n else float("nan")
    out.update(
        {
            "base_rate": base,
            "hit_rate": hit,
            "brier": brier,
            "brier_base_rate": brier_base,
            "brier_lift": float(brier_base - brier) if np.isfinite(brier_base) else float("nan"),
        }
    )
    if n >= MIN_CALIBRATION_N:
        # Simple 5-bin calibration table
        bins = np.linspace(0, 1, 6)
        table = []
        for i in range(len(bins) - 1):
            lo, hi = bins[i], bins[i + 1]
            m = (yp >= lo) & (yp < hi if i < len(bins) - 2 else yp <= hi)
            if m.sum() == 0:
                continue
            table.append(
                {
                    "bin": f"{lo:.1f}-{hi:.1f}",
                    "n": int(m.sum()),
                    "mean_prob": float(yp[m].mean()),
                    "mean_outcome": float(yt[m].mean()),
                }
            )
        out["calibration_table"] = table
    else:
        out["calibration_table"] = None
        out["calibration_note"] = f"n<{MIN_CALIBRATION_N}"
    return out


def continuous_metrics(y_true: Sequence[float], y_pred: Sequence[float]) -> Dict[str, Any]:
    yt, yp = _finite_pairs(y_true, y_pred)
    n = int(len(yt))
    out: Dict[str, Any] = {"n": n}
    if n == 0:
        out["status"] = "NO_DATA"
        return out
    err = yp - yt
    out["mae"] = float(np.mean(np.abs(err)))
    out["median_ae"] = float(np.median(np.abs(err)))
    if n >= MIN_SPEARMAN_N:
        # Spearman via rank correlation
        rt = pd.Series(yt).rank().to_numpy()
        rp = pd.Series(yp).rank().to_numpy()
        if np.std(rt) > 0 and np.std(rp) > 0:
            out["spearman"] = float(np.corrcoef(rt, rp)[0, 1])
        else:
            out["spearman"] = float("nan")
    else:
        out["spearman"] = None
        out["spearman_note"] = f"n<{MIN_SPEARMAN_N}"
    return out


def downside_discrimination(
    y_downside_share: Sequence[float],
    y_prob_favorable: Sequence[float],
) -> Dict[str, Any]:
    """
    Higher predicted favorable probability should associate with lower downside share.
    Report Spearman (negatively signed expectation) with N.
    """
    yd, yp = _finite_pairs(y_downside_share, y_prob_favorable)
    n = int(len(yd))
    out: Dict[str, Any] = {"n": n}
    if n < MIN_SPEARMAN_N:
        out["spearman_pred_vs_downside"] = None
        out["note"] = f"n<{MIN_SPEARMAN_N}"
        return out
    rd = pd.Series(yd).rank().to_numpy()
    rp = pd.Series(yp).rank().to_numpy()
    if np.std(rd) == 0 or np.std(rp) == 0:
        out["spearman_pred_vs_downside"] = float("nan")
    else:
        out["spearman_pred_vs_downside"] = float(np.corrcoef(rp, rd)[0, 1])
    return out
