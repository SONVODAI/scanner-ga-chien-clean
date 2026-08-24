"""Immutable persistence for Forecast T0 and outcome layers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.forecast_research.contract import (
    DEFAULT_DATA_DIR_NAME,
    OUTCOMES_FILE,
    STATUS_FILE,
    T0_FILE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_forecast_data_dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is not None:
        root = Path(data_dir)
    else:
        root = REPO_ROOT / "data" / DEFAULT_DATA_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def t0_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_forecast_data_dir(data_dir) / T0_FILE


def outcomes_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_forecast_data_dir(data_dir) / OUTCOMES_FILE


def status_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_forecast_data_dir(data_dir) / STATUS_FILE


def load_t0_table(data_dir: Optional[Path] = None) -> pd.DataFrame:
    path = t0_path(data_dir)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def load_outcomes_table(data_dir: Optional[Path] = None) -> pd.DataFrame:
    path = outcomes_path(data_dir)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def persist_t0_record(
    record: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """
    First-write-wins immutable T0 persist.
    Returns (written, reason).
    """
    path = t0_path(data_dir)
    existing = load_t0_table(data_dir)
    trade_date = str(record["trade_date"])[:10]
    if not existing.empty and "trade_date" in existing.columns:
        if (existing["trade_date"].astype(str).str[:10] == trade_date).any():
            return False, "ALREADY_FROZEN"
    row = pd.DataFrame([record])
    if existing.empty:
        out = row
    else:
        out = pd.concat([existing, row], ignore_index=True)
    out.to_csv(path, index=False)
    return True, "WRITTEN"


def persist_outcome_record(
    record: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Idempotent outcome persist keyed by (trade_date, horizon)."""
    path = outcomes_path(data_dir)
    existing = load_outcomes_table(data_dir)
    td = str(record["trade_date"])[:10]
    hz = int(record["horizon"])
    if not existing.empty:
        mask = (existing["trade_date"].astype(str).str[:10] == td) & (
            pd.to_numeric(existing["horizon"], errors="coerce") == hz
        )
        if mask.any():
            return False, "ALREADY_PRESENT"
    row = pd.DataFrame([record])
    out = row if existing.empty else pd.concat([existing, row], ignore_index=True)
    out.to_csv(path, index=False)
    return True, "WRITTEN"


def write_status(payload: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Path:
    path = status_path(data_dir)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
