"""Read-only stock-state adapter: canonical 142 universe + PIT freeze features."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from modules.actionable_research.contracts import PIT_FEATURE_KEYS
from modules.actionable_research.paths import FusionPaths
from modules.intraday_memory.universe import load_production_universe


def load_canonical_universe(paths: FusionPaths) -> Tuple[str, ...]:
    return load_production_universe(paths.app_py())


def _norm_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return str(value or "").strip()[:10]
    return str(ts.date())


def load_t0_freeze(paths: FusionPaths) -> pd.DataFrame:
    path = paths.t0_freeze_path()
    if not path.exists() or path.stat().st_size <= 0:
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return pd.DataFrame()
    if df.empty or "trade_date" not in df.columns or "symbol" not in df.columns:
        return df
    out = df.copy()
    out["trade_date"] = out["trade_date"].map(_norm_date)
    out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
    return out


def freeze_has_session(freeze: pd.DataFrame, trade_date: str) -> bool:
    if freeze is None or freeze.empty or "trade_date" not in freeze.columns:
        return False
    return bool((freeze["trade_date"].astype(str).str[:10] == str(trade_date)[:10]).any())


def session_stock_rows(
    trade_date: str,
    *,
    paths: FusionPaths,
    universe: Sequence[str],
    freeze: Optional[pd.DataFrame] = None,
) -> List[Dict[str, Any]]:
    """One row per canonical-universe symbol. Missing freeze → features UNKNOWN, not zero."""
    td = str(trade_date)[:10]
    freeze = freeze if freeze is not None else load_t0_freeze(paths)
    by_symbol: Dict[str, pd.Series] = {}
    freeze_ok = False
    if freeze is not None and not freeze.empty and "symbol" in freeze.columns:
        day = freeze[freeze["trade_date"].astype(str).str[:10] == td]
        freeze_ok = not day.empty
        for _, row in day.iterrows():
            by_symbol[str(row["symbol"]).upper()] = row

    records: List[Dict[str, Any]] = []
    for raw in universe:
        symbol = str(raw).upper().strip()
        row = by_symbol.get(symbol)
        features: Dict[str, Any] = {}
        labels: Dict[str, Any] = {}
        if row is not None:
            for key in PIT_FEATURE_KEYS:
                if key in row.index:
                    val = row[key]
                    features[key] = None if pd.isna(val) else _jsonable(val)
            labels = {
                "health_group": features.get("health_group"),
                "group": features.get("group"),
                "pattern_key": features.get("pattern_key_v2_frozen")
                or features.get("stock_pattern_key"),
            }
            source = "t0_observation_freeze.csv"
            source_status = "OK"
        elif freeze_ok:
            source = "t0_observation_freeze.csv"
            source_status = "SYMBOL_NOT_IN_FREEZE"
        elif freeze is None or freeze.empty:
            source = "t0_observation_freeze.csv"
            source_status = "FREEZE_UNAVAILABLE"
        else:
            source = "t0_observation_freeze.csv"
            source_status = "SESSION_NOT_IN_FREEZE"
        records.append(
            {
                "symbol": symbol,
                "stock_state": labels.get("pattern_key") or labels.get("health_group") or "UNKNOWN",
                "stock_pattern_labels": labels,
                "pit_features": features,
                "stock_state_source": source,
                "stock_state_source_status": source_status,
            }
        )
    return records


def _jsonable(val: Any) -> Any:
    if hasattr(val, "item"):
        try:
            return val.item()
        except Exception:
            return str(val)
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    return str(val)
