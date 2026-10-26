"""
FC-1 simple baselines for walk-forward bake-off.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from modules.forecast_research.fc1.contract import (
    INSUFFICIENT_EVIDENCE,
    MIN_TRAIN_REGRESSION,
    MIN_TRAIN_UNCONDITIONAL,
)


def _y_bin(train: pd.DataFrame, target: str) -> pd.Series:
    return pd.to_numeric(train[target], errors="coerce")


def _y_cont(train: pd.DataFrame, target: str) -> pd.Series:
    return pd.to_numeric(train[target], errors="coerce")


def _lin_pred(x_train: np.ndarray, y_train: np.ndarray, x_pred: float) -> float:
    """Simple OLS with intercept; falls back to mean if degenerate."""
    mask = np.isfinite(x_train) & np.isfinite(y_train)
    x = x_train[mask]
    y = y_train[mask]
    if len(x) < 2 or np.unique(x).size < 2:
        return float(np.nanmean(y)) if len(y) else float("nan")
    X = np.column_stack([np.ones(len(x)), x])
    try:
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        return float(beta[0] + beta[1] * x_pred)
    except Exception:
        return float(np.nanmean(y))


def _lin_pred_multi(X_train: np.ndarray, y_train: np.ndarray, x_pred: np.ndarray) -> float:
    mask = np.isfinite(X_train).all(axis=1) & np.isfinite(y_train)
    X = X_train[mask]
    y = y_train[mask]
    if len(X) < X.shape[1] + 1:
        return float(np.nanmean(y)) if len(y) else float("nan")
    Xd = np.column_stack([np.ones(len(X)), X])
    try:
        beta, _, _, _ = np.linalg.lstsq(Xd, y, rcond=None)
        return float(beta[0] + float(np.dot(beta[1:], x_pred)))
    except Exception:
        return float(np.nanmean(y))


def _clip01(p: float) -> float:
    if not np.isfinite(p):
        return float("nan")
    return float(min(1.0, max(0.0, p)))


def predict_baseline(
    name: str,
    *,
    train_labels: pd.DataFrame,
    train_pit: pd.DataFrame,
    pred_row: pd.Series,
    binary_target: str = "favorable_median",
    continuous_target: str = "xs_median_return",
) -> Dict[str, Any]:
    """
    Return prediction dict with binary_prob and continuous_pred.
    Marks INSUFFICIENT_EVIDENCE when train N is too small for the method.
    """
    merged = train_labels.merge(
        train_pit,
        on="trade_date",
        how="inner",
        suffixes=("", "_pit"),
    )
    n = int(len(merged))
    out: Dict[str, Any] = {
        "baseline": name,
        "train_n": n,
        "status": "OK",
        "binary_prob": float("nan"),
        "continuous_pred": float("nan"),
    }

    yb = _y_bin(merged, binary_target) if binary_target in merged.columns else pd.Series(dtype=float)
    yc = _y_cont(merged, continuous_target) if continuous_target in merged.columns else pd.Series(dtype=float)

    if name == "unconditional":
        if n < MIN_TRAIN_UNCONDITIONAL:
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        out["binary_prob"] = float(yb.mean()) if yb.notna().any() else float("nan")
        out["continuous_pred"] = float(yc.median()) if yc.notna().any() else float("nan")
        return out

    if name == "persistence":
        if n < 1:
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        last = merged.sort_values("trade_date").iloc[-1]
        out["binary_prob"] = float(last.get(binary_target)) if pd.notna(last.get(binary_target)) else float("nan")
        out["continuous_pred"] = (
            float(last.get(continuous_target)) if pd.notna(last.get(continuous_target)) else float("nan")
        )
        return out

    def _single(feature: str, min_n: int = MIN_TRAIN_REGRESSION) -> Dict[str, Any]:
        if n < min_n or feature not in merged.columns:
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        x = pd.to_numeric(merged[feature], errors="coerce").to_numpy(dtype=float)
        xp = pd.to_numeric(pred_row.get(feature), errors="coerce")
        if pd.isna(xp):
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        # Continuous OLS
        out["continuous_pred"] = _lin_pred(x, yc.to_numpy(dtype=float), float(xp))
        # Binary: map continuous score through logistic-ish clip of linear prob approx
        # Use linear probability model clipped to [0,1]
        out["binary_prob"] = _clip01(_lin_pred(x, yb.to_numpy(dtype=float), float(xp)))
        return out

    if name == "real_only":
        return _single("market_real")
    if name == "live_only":
        return _single("market_live")
    if name == "breadth_only":
        # Prefer breadth_score; fall back to rsi50_share
        feat = "breadth_score" if pred_row.get("breadth_score") is not None and pd.notna(pred_row.get("breadth_score")) else "rsi50_share"
        if feat not in merged.columns or merged[feat].notna().sum() < MIN_TRAIN_REGRESSION:
            feat = "rsi50_share"
        return _single(feat)
    if name == "legacy_fc_only":
        return _single("market_forecast")
    if name == "composition_early_share":
        return _single("share_MUA_EARLY")

    if name == "real_live":
        if n < MIN_TRAIN_REGRESSION:
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        cols = ["market_real", "market_live"]
        if any(c not in merged.columns for c in cols):
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        X = merged[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        xp = np.array(
            [
                float(pd.to_numeric(pred_row.get("market_real"), errors="coerce")),
                float(pd.to_numeric(pred_row.get("market_live"), errors="coerce")),
            ],
            dtype=float,
        )
        if not np.isfinite(xp).all():
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        out["continuous_pred"] = _lin_pred_multi(X, yc.to_numpy(dtype=float), xp)
        out["binary_prob"] = _clip01(_lin_pred_multi(X, yb.to_numpy(dtype=float), xp))
        return out

    if name == "regime_pit":
        if n < MIN_TRAIN_UNCONDITIONAL or "regime_pit" not in merged.columns:
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        reg = pred_row.get("regime_pit")
        if reg is None or (isinstance(reg, float) and np.isnan(reg)):
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        sub = merged[merged["regime_pit"] == reg]
        if len(sub) < MIN_TRAIN_UNCONDITIONAL:
            out["status"] = INSUFFICIENT_EVIDENCE
            return out
        out["binary_prob"] = float(pd.to_numeric(sub[binary_target], errors="coerce").mean())
        out["continuous_pred"] = float(pd.to_numeric(sub[continuous_target], errors="coerce").median())
        out["train_n"] = int(len(sub))
        return out

    out["status"] = INSUFFICIENT_EVIDENCE
    out["error"] = f"unknown_baseline:{name}"
    return out


BASELINE_NAMES = (
    "unconditional",
    "persistence",
    "real_only",
    "live_only",
    "real_live",
    "breadth_only",
    "legacy_fc_only",
    "regime_pit",
    "composition_early_share",
)
