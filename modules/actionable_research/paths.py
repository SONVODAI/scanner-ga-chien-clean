"""Path resolution and tiny I/O helpers. Fusion never writes scientific stores."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from modules.actionable_research.contracts import (
    DEFAULT_ARTIFACT_DIRNAME,
    DEFAULT_DAILY_SUBDIR,
    DEFAULT_HISTORY_SUBDIR,
    INDEX_FILENAME,
    LATEST_FILENAME,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def utc_now_iso(now: Optional[datetime] = None) -> str:
    dt = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    return Path(raw) if raw else default


@dataclass
class FusionPaths:
    repo_root: Path = field(default_factory=lambda: REPO_ROOT)
    artifact_root: Optional[Path] = None
    earning_learning_dir: Optional[Path] = None
    edge_data_dir: Optional[Path] = None
    camera_root: Optional[Path] = None
    foreign_history_root: Optional[Path] = None
    app_py_path: Optional[Path] = None

    def resolved_repo(self) -> Path:
        return Path(self.repo_root)

    def artifacts(self) -> Path:
        if self.artifact_root is not None:
            return Path(self.artifact_root)
        return _path_from_env(
            "MRBOT_ACTIONABLE_RESEARCH_DIR",
            self.resolved_repo() / "data" / DEFAULT_ARTIFACT_DIRNAME,
        )

    def daily_dir(self) -> Path:
        return self.artifacts() / DEFAULT_DAILY_SUBDIR

    def history_dir(self) -> Path:
        return self.artifacts() / DEFAULT_HISTORY_SUBDIR

    def latest_path(self) -> Path:
        return self.artifacts() / LATEST_FILENAME

    def index_path(self) -> Path:
        return self.artifacts() / INDEX_FILENAME

    def daily_path(self, trade_date: str) -> Path:
        return self.daily_dir() / f"{trade_date}.json"

    def earning_learning(self) -> Path:
        if self.earning_learning_dir is not None:
            return Path(self.earning_learning_dir)
        return self.resolved_repo() / "data" / "earning_learning"

    def t0_freeze_path(self) -> Path:
        return self.earning_learning() / "t0_observation_freeze.csv"

    def market_daily_t0_path(self) -> Path:
        return self.earning_learning() / "market_daily_t0.csv"

    def market_t0_snapshot_path(self) -> Path:
        return self.earning_learning() / "market_t0_snapshot.csv"

    def sweetspot_observer_ledger_path(self) -> Path:
        return self.earning_learning() / "market_aware_sweetspot_observer_ledger.csv"

    def edge_root(self) -> Path:
        if self.edge_data_dir is not None:
            return Path(self.edge_data_dir)
        env = os.environ.get("EDGE_RESEARCH_DATA_DIR", "").strip()
        if env:
            return Path(env)
        return self.resolved_repo() / "data" / "edge_research"

    def edge_memory_path(self) -> Path:
        return self.edge_root() / "edge_memory.csv"

    def latest_recognition_path(self) -> Path:
        return self.edge_root() / "latest_future_recognition.json"

    def daily_edge_matches_path(self, trade_date: str) -> Path:
        return self.edge_root() / "daily_edge_matches" / f"{trade_date}.json"

    def camera_data_root(self) -> Path:
        if self.camera_root is not None:
            return Path(self.camera_root)
        return _path_from_env(
            "MRBOT_INTRADAY_DATA_ROOT",
            self.resolved_repo() / "intraday_memory",
        )

    def foreign_root(self) -> Path:
        if self.foreign_history_root is not None:
            return Path(self.foreign_history_root)
        return self.resolved_repo() / "data" / "foreign_flow_history"

    def app_py(self) -> Path:
        if self.app_py_path is not None:
            return Path(self.app_py_path)
        env = os.environ.get("MRBOT_APP_PY_PATH", "").strip()
        if env:
            return Path(env)
        return self.resolved_repo() / "app.py"


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
