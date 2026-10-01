"""
FC-1 maturity enforcement helpers.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence

import pandas as pd

from modules.forecast_research.fc1.labels import label_available_at_prediction


def filter_train_labels(
    labels: pd.DataFrame,
    *,
    prediction_date: str,
    horizon: int,
) -> pd.DataFrame:
    """
    Return label rows legally usable when forecasting at prediction_date for horizon.

    Rules:
    - same horizon
    - trade_date < prediction_date
    - mature_trade_date < prediction_date
    """
    if labels.empty:
        return labels.copy()
    td = str(prediction_date)[:10]
    df = labels.copy()
    df["trade_date"] = df["trade_date"].astype(str).str[:10]
    df["mature_trade_date"] = df["mature_trade_date"].astype(str).str[:10]
    df["horizon"] = pd.to_numeric(df["horizon"], errors="coerce")
    out = df[
        (df["horizon"] == int(horizon))
        & (df["trade_date"] < td)
        & (df["mature_trade_date"] < td)
    ].copy()
    # Fail closed: drop any row failing availability helper
    keep = [
        label_available_at_prediction(
            mature_trade_date=str(r["mature_trade_date"]),
            prediction_date=td,
        )
        for _, r in out.iterrows()
    ]
    return out.loc[keep].reset_index(drop=True)


def assert_train_precedes_prediction(
    train_dates: Sequence[str],
    prediction_date: str,
    mature_dates: Sequence[str],
) -> None:
    td = str(prediction_date)[:10]
    for d in train_dates:
        if str(d)[:10] >= td:
            raise AssertionError(f"train date {d} does not precede prediction {td}")
    for m in mature_dates:
        if str(m)[:10] >= td:
            raise AssertionError(f"mature date {m} not strictly before prediction {td}")


def maturity_cutoff_description(prediction_date: str, horizon: int) -> str:
    return (
        f"For prediction_date={prediction_date} horizon=T{horizon}: "
        f"train labels require trade_date < {prediction_date} AND "
        f"mature_trade_date < {prediction_date}."
    )
