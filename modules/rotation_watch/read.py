"""Read-only Rotation artifact loader. No KBS, no P×V recompute, no Candidate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.rotation_watch.artifact import default_board_path, load_json
from modules.rotation_watch.constants import SCHEMA_BOARD


def load_board_artifact(path: Path | None = None) -> dict[str, Any] | None:
    data = load_json(path or default_board_path())
    if data is None:
        return None
    if data.get("schema") not in {SCHEMA_BOARD, None} and "rows" not in data:
        return None
    return data
