"""
FC-1 forward labels — 142-stock equal-weight universe opportunity.

Labels are constructed separately from T0 features.
Primary source: earning_learning outcomes.csv (per-symbol matured returns).
Optional attach: forecast_outcomes MFE/MAE / VNI when date×horizon match.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from modules.forecast_research.fc1.contract import (
    BROAD_FAVORABLE_SHARE,
    FAVORABLE_MEDIAN_THRESHOLD,
    FC1_LABEL_SCHEMA_VERSION,
    FC1_VERSION,
    HORIZONS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _norm_date(s: Any) -> str:
    return str(s)[:10]


def _session_index(dates: List[str], trade_date: str) -> Optional[int]:
    td = _norm_date(trade_date)
    try:
        return dates.index(td)
    except ValueError:
        return None


def trading_session_calendar(*frames: pd.DataFrame, date_cols: Optional[List[str]] = None) -> List[str]:
    """Union of trading dates from board-like frames, sorted."""
    date_cols = date_cols or ["trade_date", "snapshot_date", "entry_date"]
    dates: set[str] = set()
    for df in frames:
        if df is None or df.empty:
            continue
        for c in date_cols:
            if c in df.columns:
                dates |= set(df[c].astype(str).str[:10])
    return sorted(d for d in dates if d and d != "nan" and d.lower() != "nat")


def mature_trade_date_for(
    trade_date: str,
    horizon: int,
    session_dates: List[str],
) -> Optional[str]:
    """Return the session date on which horizon h matures, or None if not yet mature in calendar."""
    i0 = _session_index(session_dates, trade_date)
    if i0 is None:
        return None
    j = i0 + int(horizon)
    if j >= len(session_dates):
        return None
    return session_dates[j]


def label_available_at_prediction(
    *,
    mature_trade_date: str,
    prediction_date: str,
) -> bool:
    """
    A label may enter the training set for prediction at t only if it matured
    strictly before t (information boundary).
    """
    return _norm_date(mature_trade_date) < _norm_date(prediction_date)


def aggregate_universe_opportunity(
    outcomes: pd.DataFrame,
    *,
    entry_date: str,
    horizon: int,
) -> Optional[Dict[str, Any]]:
    if outcomes.empty:
        return None
    df = outcomes.copy()
    df["entry_date"] = df["entry_date"].astype(str).str[:10]
    df["horizon"] = pd.to_numeric(df["horizon"], errors="coerce").astype("Int64")
    sub = df[(df["entry_date"] == _norm_date(entry_date)) & (df["horizon"] == int(horizon))]
    if sub.empty:
        return None
    rets = pd.to_numeric(sub["return_pct"], errors="coerce").dropna()
    if rets.empty:
        return None
    return {
        "xs_mean_return": float(rets.mean()),
        "xs_median_return": float(rets.median()),
        "xs_positive_share": float((rets > 0).mean()),
        "xs_gt_3pct_share": float((rets > 3.0).mean()),
        "xs_gt_5pct_share": float((rets > 5.0).mean()),
        "xs_lt_minus3pct_share": float((rets < -3.0).mean()),
        "n_symbols": int(len(rets)),
    }


def build_labels(
    *,
    pit: pd.DataFrame,
    outcomes_path: Optional[Path] = None,
    forecast_outcomes_path: Optional[Path] = None,
    ems_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    root = repo_root or REPO_ROOT
    outcomes_path = outcomes_path or (root / "data" / "earning_learning" / "outcomes.csv")
    forecast_outcomes_path = forecast_outcomes_path or (
        root / "data" / "forecast_research" / "forecast_outcomes.csv"
    )
    ems_path = ems_path or (root / "data" / "earning_money_snapshots.csv")

    outcomes = pd.read_csv(outcomes_path, low_memory=False) if outcomes_path.exists() else pd.DataFrame()
    fout = (
        pd.read_csv(forecast_outcomes_path, low_memory=False)
        if forecast_outcomes_path.exists()
        else pd.DataFrame()
    )
    ems = pd.read_csv(ems_path, low_memory=False) if ems_path.exists() else pd.DataFrame()

    session_dates = trading_session_calendar(pit, outcomes, ems)
    # Prefer EMS calendar for maturity alignment when available
    if not ems.empty and "snapshot_date" in ems.columns:
        ems_dates = sorted(set(ems["snapshot_date"].astype(str).str[:10]))
        if len(ems_dates) >= 5:
            session_dates = ems_dates

    rows: List[Dict[str, Any]] = []
    for td in pit["trade_date"].astype(str).str[:10].tolist():
        for h in HORIZONS:
            mtd = mature_trade_date_for(td, h, session_dates)
            agg = aggregate_universe_opportunity(outcomes, entry_date=td, horizon=h)
            if agg is None:
                continue
            if mtd is None:
                # Outcome rows exist in artifact but calendar cannot prove maturity path —
                # still record mature_trade_date from outcomes target_date max if present.
                sub = outcomes[
                    (outcomes["entry_date"].astype(str).str[:10] == td)
                    & (pd.to_numeric(outcomes["horizon"], errors="coerce") == h)
                ]
                if "target_date" in sub.columns and not sub.empty:
                    mtd = _norm_date(pd.to_datetime(sub["target_date"]).max())
                else:
                    continue

            row: Dict[str, Any] = {
                "trade_date": td,
                "horizon": int(h),
                "mature_trade_date": mtd,
                "fc1_version": FC1_VERSION,
                "label_schema_version": FC1_LABEL_SCHEMA_VERSION,
                **agg,
                "universe_mfe": float("nan"),
                "universe_mae": float("nan"),
                "vni_return": float("nan"),
                "mfe_mae_source": None,
            }
            # Optional FM outcomes attach (same date/horizon only)
            if not fout.empty:
                hit = fout[
                    (fout["trade_date"].astype(str).str[:10] == td)
                    & (pd.to_numeric(fout["horizon"], errors="coerce") == h)
                ]
                if not hit.empty:
                    r = hit.iloc[-1]
                    row["universe_mfe"] = pd.to_numeric(r.get("mfe"), errors="coerce")
                    row["universe_mae"] = pd.to_numeric(r.get("mae"), errors="coerce")
                    row["vni_return"] = pd.to_numeric(r.get("vni_return"), errors="coerce")
                    row["mfe_mae_source"] = "forecast_outcomes"
                    # Prefer FM mature date when present
                    if pd.notna(r.get("mature_trade_date")):
                        row["mature_trade_date"] = _norm_date(r.get("mature_trade_date"))

            med = row["xs_median_return"]
            pos = row["xs_positive_share"]
            row["favorable_median"] = int(med > FAVORABLE_MEDIAN_THRESHOLD) if pd.notna(med) else None
            row["broad_favorable"] = int(pos >= BROAD_FAVORABLE_SHARE) if pd.notna(pos) else None
            rows.append(row)

    labels = pd.DataFrame(rows)
    meta = {
        "fc1_version": FC1_VERSION,
        "label_schema_version": FC1_LABEL_SCHEMA_VERSION,
        "n_rows": int(len(labels)),
        "session_dates_n": len(session_dates),
        "by_horizon": {},
    }
    if not labels.empty:
        for h in HORIZONS:
            sub = labels[labels["horizon"] == h]
            meta["by_horizon"][str(h)] = {
                "n": int(len(sub)),
                "date_min": str(sub["trade_date"].min()) if len(sub) else None,
                "date_max": str(sub["trade_date"].max()) if len(sub) else None,
            }
    return labels, meta
