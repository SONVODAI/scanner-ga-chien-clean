"""Isolated paths for P×V V1. Never writes under Camera or production stores."""

from __future__ import annotations

import os
from pathlib import Path

from modules.intraday_pxv_v1.constants import OUTPUT_DIRNAME

REPO_ROOT = Path(__file__).resolve().parents[2]


def camera_data_root() -> Path:
    env = os.getenv("MRBOT_INTRADAY_DATA_ROOT", "").strip()
    if env:
        return Path(env)
    vps = Path("/var/lib/mrbot/intraday_memory")
    if vps.exists():
        return vps
    return REPO_ROOT / "intraday_memory"


def output_root(base: Path | None = None) -> Path:
    env = os.getenv("MRBOT_PXV_V1_OUT", "").strip()
    if env:
        return Path(env)
    return (base or REPO_ROOT) / "data" / OUTPUT_DIRNAME


def elite_history_path() -> Path:
    return REPO_ROOT / "buy_elite_learning_history.csv"


def lifecycle_path() -> Path:
    return REPO_ROOT / "data" / "earning_learning" / "pattern_lifecycle.csv"
