"""Write V2 artifacts only under data/multifamily_discovery_v2/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from modules.multifamily_discovery_v2.contracts import V2_ARTIFACT_ROOT


def artifact_root(base: Optional[Path] = None) -> Path:
    root = Path(base) if base is not None else V2_ARTIFACT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    (root / "experiments").mkdir(exist_ok=True)
    return root


def write_json(name: str, payload: Dict[str, Any], *, base: Optional[Path] = None) -> Path:
    root = artifact_root(base)
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def write_text(name: str, text: str, *, base: Optional[Path] = None) -> Path:
    root = artifact_root(base)
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
