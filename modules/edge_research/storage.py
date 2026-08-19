"""
Isolated persistence for Edge Research Engine V1.

ONLY writer to data/edge_research/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from modules.edge_research.contracts import (
    EDGE_EPISODE_REGISTRY_COLUMNS,
    EDGE_FORWARD_LEDGER_COLUMNS,
    EDGE_HYPOTHESIS_LEDGER_COLUMNS,
    EDGE_MEMORY_COLUMNS,
    EDGE_VALIDATION_HISTORY_COLUMNS,
    ENGINE_VERSION,
)

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "edge_research"

LEDGER_FILES: Dict[str, Tuple[str, ...]] = {
    "edge_hypothesis_ledger.csv": EDGE_HYPOTHESIS_LEDGER_COLUMNS,
    "edge_episode_registry.csv": EDGE_EPISODE_REGISTRY_COLUMNS,
    "edge_validation_history.csv": EDGE_VALIDATION_HISTORY_COLUMNS,
    "edge_memory.csv": EDGE_MEMORY_COLUMNS,
    "edge_forward_ledger.csv": EDGE_FORWARD_LEDGER_COLUMNS,
}

STATUS_FILE = "engine_status.json"
PANEL_CACHE_FILE = "research_panel_cache.csv"


def resolve_data_dir(explicit: Optional[Path] = None) -> Path:
    env = os.environ.get("EDGE_RESEARCH_DATA_DIR")
    if explicit is not None:
        return Path(explicit)
    if env:
        return Path(env)
    return DEFAULT_DATA_DIR


def ensure_storage(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    for filename, columns in LEDGER_FILES.items():
        path = root / filename
        if not path.exists():
            pd.DataFrame(columns=list(columns)).to_csv(path, index=False)
    status_path = root / STATUS_FILE
    if not status_path.exists():
        write_status(
            {
                "engine_version": ENGINE_VERSION,
                "phase": "foundation",
                "hypotheses": 0,
                "validated_edges": 0,
                "independent_episodes": 0,
                "last_research_event": "NONE",
            },
            data_dir=root,
        )
    return root


def write_status(payload: Dict[str, Any], data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / STATUS_FILE
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_status(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = resolve_data_dir(data_dir)
    path = root / STATUS_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_ledger(name: str, data_dir: Optional[Path] = None) -> pd.DataFrame:
    root = resolve_data_dir(data_dir)
    path = root / name
    if not path.exists():
        cols = LEDGER_FILES.get(name, ())
        return pd.DataFrame(columns=list(cols))
    return pd.read_csv(path)


def count_ledger_rows(name: str, data_dir: Optional[Path] = None) -> int:
    df = read_ledger(name, data_dir=data_dir)
    if df.empty:
        return 0
    return int(len(df.dropna(how="all")))


def write_panel_cache(df: pd.DataFrame, data_dir: Optional[Path] = None) -> Path:
    root = ensure_storage(data_dir)
    path = root / PANEL_CACHE_FILE
    df.to_csv(path, index=False)
    return path


def read_panel_cache(data_dir: Optional[Path] = None) -> pd.DataFrame:
    root = resolve_data_dir(data_dir)
    path = root / PANEL_CACHE_FILE
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
