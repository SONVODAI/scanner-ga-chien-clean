"""
Leakage-safe T0 feature matrix builder for Edge Research.

Constructs symbol × trade_date feature rows using ONLY information available
at or before T0. Forward T3/T5/T10 outcomes remain separate labels.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.edge_research.adapters import load_lifecycle
from modules.edge_research.feature_registry import (
    CANONICAL_STOCK_HISTORY_SOURCE,
    FeatureKind,
    FeatureRegistry,
    FeatureSpec,
    LEGACY_SEARCH_FEATURES,
    STOCK_CATEGORICAL_LEVEL_FEATURES,
    STOCK_NUMERIC_LEVEL_FEATURES,
    STOCK_RANK_LEVEL_FEATURES,
    is_prohibited_feature_column,
    validate_feature_columns,
)

FEATURE_MATRIX_KEY_COLUMNS: Tuple[str, str] = ("trade_date", "symbol")
DEFAULT_LAG_WINDOWS: Tuple[int, ...] = (1, 2, 3)
SLOPE_WINDOW = 3
ACCEL_WINDOW = 2

_LEVEL_SOURCE_MAP: Dict[str, str] = {
    "close": "price",
}


def _normalize_trade_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")


def _trailing_slope(values: Sequence[object]) -> Optional[float]:
    pts: List[Tuple[int, float]] = []
    for idx, raw in enumerate(values):
        if raw is None or (isinstance(raw, float) and np.isnan(raw)):
            continue
        try:
            pts.append((idx, float(raw)))
        except (TypeError, ValueError):
            continue
    if len(pts) < 2:
        return None
    xs = np.array([p[0] for p in pts], dtype=float)
    ys = np.array([p[1] for p in pts], dtype=float)
    if len(pts) == 2:
        dx = xs[1] - xs[0]
        if dx == 0:
            return None
        return float((ys[1] - ys[0]) / dx)
    coeff = np.polyfit(xs, ys, 1)
    return float(coeff[0])


def load_canonical_stock_history(
    lifecycle: Optional[pd.DataFrame] = None,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load deduplicated symbol × trade_date history from pattern_lifecycle.csv.

    Uses the same canonical source as build_research_panel(). Outcome columns
    are excluded from the returned frame.
    """
    df = lifecycle.copy() if lifecycle is not None else load_lifecycle()
    if df.empty:
        return pd.DataFrame(columns=list(FEATURE_MATRIX_KEY_COLUMNS))

    validate_feature_columns(
        list(STOCK_NUMERIC_LEVEL_FEATURES)
        + list(STOCK_CATEGORICAL_LEVEL_FEATURES)
        + list(STOCK_RANK_LEVEL_FEATURES)
        + list(_LEVEL_SOURCE_MAP.values())
    )

    date_col = "trade_date" if "trade_date" in df.columns else "entry_date"
    out = df.copy()
    out["trade_date"] = _normalize_trade_date(out[date_col])
    out["symbol"] = out["symbol"].astype(str)
    out = out.dropna(subset=["trade_date", "symbol"])

    if start:
        out = out[out["trade_date"] >= start]
    if end:
        out = out[out["trade_date"] <= end]

    out = out.sort_values(["symbol", "trade_date"], kind="mergesort")
    out = out.drop_duplicates(subset=list(FEATURE_MATRIX_KEY_COLUMNS), keep="last")
    return out.reset_index(drop=True)


def _extract_level_column(frame: pd.DataFrame, feature: str) -> pd.Series:
    source = _LEVEL_SOURCE_MAP.get(feature, feature)
    if source not in frame.columns:
        if feature in STOCK_CATEGORICAL_LEVEL_FEATURES:
            return pd.Series("UNKNOWN", index=frame.index, dtype="string")
        return pd.Series(np.nan, index=frame.index, dtype=float)
    if feature in STOCK_CATEGORICAL_LEVEL_FEATURES:
        return frame[source].astype("string").fillna("UNKNOWN")
    return pd.to_numeric(frame[source], errors="coerce")


def _shift_by_symbol(work: pd.DataFrame, series: pd.Series, lag: int) -> pd.Series:
    shifted_parts: List[pd.Series] = []
    for _, grp in work.groupby("symbol", sort=False):
        shifted_parts.append(series.loc[grp.index].shift(lag))
    return pd.concat(shifted_parts).sort_index()


def _register_level_specs(
    registry: FeatureRegistry,
    feature: str,
    *,
    kind: FeatureKind,
    search_eligible: bool,
) -> None:
    registry.register(
        FeatureSpec(
            name=feature,
            kind=kind,
            source_column=_LEVEL_SOURCE_MAP.get(feature, feature),
            temporal=False,
            search_eligible=search_eligible,
            description=f"T0 {kind.value} from {CANONICAL_STOCK_HISTORY_SOURCE}",
        )
    )


def _register_temporal_specs(
    registry: FeatureRegistry,
    base_feature: str,
    *,
    kind: FeatureKind,
    suffix: str,
    lag: Optional[int] = None,
) -> None:
    name = f"{base_feature}_{suffix}"
    registry.register(
        FeatureSpec(
            name=name,
            kind=kind,
            source_column=base_feature,
            temporal=True,
            search_eligible=False,
            description=(
                f"Temporal {kind.value} for {base_feature}"
                + (f" lag={lag}" if lag is not None else "")
            ),
        )
    )


def build_t0_feature_matrix(
    history: Optional[pd.DataFrame] = None,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    lag_windows: Sequence[int] = DEFAULT_LAG_WINDOWS,
    registry: Optional[FeatureRegistry] = None,
) -> pd.DataFrame:
    """
    Build deterministic leakage-safe feature rows for symbol × trade_date.

    Uses only data available at or before each trade_date for the same symbol.
    Missing prior history remains missing — no future backfill.
    """
    hist = load_canonical_stock_history(history, start=start, end=end)
    reg = registry if registry is not None else FeatureRegistry()

    if hist.empty:
        return pd.DataFrame(columns=list(FEATURE_MATRIX_KEY_COLUMNS))

    work = hist.sort_values(["symbol", "trade_date"], kind="mergesort").reset_index(drop=True)

    out = pd.DataFrame(
        {
            "trade_date": work["trade_date"],
            "symbol": work["symbol"],
        }
    )

    for feature in STOCK_NUMERIC_LEVEL_FEATURES:
        current = _extract_level_column(work, feature)
        out[feature] = current
        _register_level_specs(
            reg,
            feature,
            kind=FeatureKind.NUMERIC_LEVEL,
            search_eligible=feature in LEGACY_SEARCH_FEATURES,
        )

        for lag in lag_windows:
            lag_col = f"{feature}_lag_{lag}"
            out[lag_col] = _shift_by_symbol(work, current, lag)
            _register_temporal_specs(
                reg,
                feature,
                kind=FeatureKind.NUMERIC_LAG,
                suffix=f"lag_{lag}",
                lag=lag,
            )

            delta_col = f"{feature}_delta_{lag}"
            out[delta_col] = out[feature] - out[lag_col]
            _register_temporal_specs(
                reg,
                feature,
                kind=FeatureKind.NUMERIC_DELTA,
                suffix=f"delta_{lag}",
                lag=lag,
            )

        slope_col = f"{feature}_slope_{SLOPE_WINDOW}"
        slope_values: List[Optional[float]] = []
        for _, grp in work.groupby("symbol", sort=False):
            levels = _extract_level_column(grp, feature)
            for pos in range(len(grp)):
                window = levels.iloc[max(0, pos - SLOPE_WINDOW) : pos + 1].tolist()
                slope_values.append(_trailing_slope(window))
        out[slope_col] = slope_values
        _register_temporal_specs(
            reg,
            feature,
            kind=FeatureKind.NUMERIC_SLOPE,
            suffix=f"slope_{SLOPE_WINDOW}",
        )

        accel_col = f"{feature}_accel_{ACCEL_WINDOW}"
        lag1 = f"{feature}_lag_1"
        lag2 = f"{feature}_lag_2"
        if lag1 in out.columns and lag2 in out.columns:
            prior_delta = out[lag1] - out[lag2]
            current_delta = out[feature] - out[lag1]
            out[accel_col] = current_delta - prior_delta
        else:
            out[accel_col] = np.nan
        _register_temporal_specs(
            reg,
            feature,
            kind=FeatureKind.NUMERIC_ACCEL,
            suffix=f"accel_{ACCEL_WINDOW}",
        )

    for feature in STOCK_CATEGORICAL_LEVEL_FEATURES:
        current = _extract_level_column(work, feature).astype(str)
        out[feature] = current
        _register_level_specs(
            reg,
            feature,
            kind=FeatureKind.CATEGORICAL_LEVEL,
            search_eligible=False,
        )

        prior_col = f"{feature}_prior"
        out[prior_col] = _shift_by_symbol(work, current, 1)
        _register_temporal_specs(
            reg,
            feature,
            kind=FeatureKind.CATEGORICAL_PRIOR,
            suffix="prior",
            lag=1,
        )

        transition_col = f"{feature}_transition"
        out[transition_col] = out[prior_col].astype(str) + " -> " + out[feature].astype(str)
        out.loc[out[prior_col].isna(), transition_col] = np.nan
        _register_temporal_specs(
            reg,
            feature,
            kind=FeatureKind.CATEGORICAL_TRANSITION,
            suffix="transition",
        )

    for feature in STOCK_RANK_LEVEL_FEATURES:
        current = _extract_level_column(work, feature)
        out[feature] = current
        _register_level_specs(
            reg,
            feature,
            kind=FeatureKind.RANK_LEVEL,
            search_eligible=False,
        )

        lag1_col = f"{feature}_lag_1"
        out[lag1_col] = _shift_by_symbol(work, current, 1)
        _register_temporal_specs(
            reg,
            feature,
            kind=FeatureKind.RANK_LAG,
            suffix="lag_1",
            lag=1,
        )

        delta_col = f"{feature}_delta_1"
        out[delta_col] = out[feature] - out[lag1_col]
        _register_temporal_specs(
            reg,
            feature,
            kind=FeatureKind.RANK_DELTA,
            suffix="delta_1",
            lag=1,
        )

    out.attrs["feature_registry"] = reg
    out.attrs["canonical_source"] = CANONICAL_STOCK_HISTORY_SOURCE

    prohibited_in_output = [c for c in out.columns if is_prohibited_feature_column(c)]
    if prohibited_in_output:
        raise ValueError(
            "Feature matrix contains prohibited columns: "
            + ", ".join(sorted(prohibited_in_output))
        )

    return out


def get_matrix_registry(matrix: pd.DataFrame) -> FeatureRegistry:
    reg = matrix.attrs.get("feature_registry")
    if isinstance(reg, FeatureRegistry):
        return reg
    return FeatureRegistry()
