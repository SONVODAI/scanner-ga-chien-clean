"""
Run manifest for collector observability.

Every collection run produces a machine-readable summary so we can answer:
"Did yesterday's camera actually record the market correctly?"
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.intraday_memory.timezone_policy import VN_TZ


@dataclass
class RunManifest:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(VN_TZ))
    finished_at: datetime | None = None
    mode: str = ""
    requested_session: str | None = None
    requested_range: str | None = None
    universe_count: int = 0
    symbols_success: list[str] = field(default_factory=list)
    symbols_failed: dict[str, str] = field(default_factory=dict)
    bars_fetched: int = 0
    bars_valid: int = 0
    bars_rejected: int = 0
    bars_new: int = 0
    bars_existing: int = 0
    bars_changed: int = 0
    duplicate_count: int = 0
    provider: str = "KBS"
    collector_version: str = ""
    storage_root: str = ""

    def finish(self) -> None:
        self.finished_at = datetime.now(VN_TZ)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("started_at", "finished_at"):
            val = data.get(key)
            if isinstance(val, datetime):
                data[key] = val.isoformat()
        return data

    def save(self, manifests_dir: Path) -> Path:
        manifests_dir.mkdir(parents=True, exist_ok=True)
        path = manifests_dir / f"{self.run_id}.json"
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def summary_text(self) -> str:
        self.finish() if self.finished_at is None else None
        lines = [
            f"Run {self.run_id} | mode={self.mode}",
            f"  universe={self.universe_count} success={len(self.symbols_success)} "
            f"failed={len(self.symbols_failed)}",
            f"  bars: fetched={self.bars_fetched} valid={self.bars_valid} "
            f"rejected={self.bars_rejected} new={self.bars_new} "
            f"existing={self.bars_existing} changed={self.bars_changed}",
        ]
        if self.symbols_failed:
            lines.append("  failures:")
            for sym, reason in sorted(self.symbols_failed.items()):
                lines.append(f"    {sym}: {reason}")
        return "\n".join(lines)
