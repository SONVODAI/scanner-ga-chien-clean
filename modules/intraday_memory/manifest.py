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

# final_status values (NO_TRADING_DAY reserved for future scheduler/orchestration).
STATUS_SUCCESS = "SUCCESS"
STATUS_PARTIAL = "PARTIAL"
STATUS_NOT_READY = "NOT_READY"
STATUS_FAILED = "FAILED"
STATUS_NO_TRADING_DAY = "NO_TRADING_DAY"

TIER_GUEST = "guest"
TIER_COMMUNITY = "community"

FINAL_STATUSES = frozenset(
    {
        STATUS_SUCCESS,
        STATUS_PARTIAL,
        STATUS_NOT_READY,
        STATUS_FAILED,
        STATUS_NO_TRADING_DAY,
    }
)


def compute_final_status(
    *,
    universe_count: int,
    symbols_failed: dict[str, str],
    bars_valid: int,
    bars_fetched: int,
    per_symbol_summary: list[dict[str, Any]],
) -> str:
    """
    Derive run-level status from collector evidence.

    NO_TRADING_DAY is intentionally never assigned here; the future VPS
    scheduler/orchestration layer may set it when calendar evidence exists.
    """
    if universe_count <= 0:
        return STATUS_FAILED

    failed_count = len(symbols_failed)
    empty_count = sum(1 for s in per_symbol_summary if s.get("status") == "empty")

    if failed_count >= universe_count:
        return STATUS_FAILED

    if bars_valid == 0:
        if failed_count == 0 and (bars_fetched == 0 or empty_count > 0):
            return STATUS_NOT_READY
        return STATUS_FAILED

    if failed_count > 0 or empty_count > 0:
        return STATUS_PARTIAL

    unusable = any(s.get("status") == "unusable" for s in per_symbol_summary)
    if unusable:
        return STATUS_PARTIAL

    return STATUS_SUCCESS


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
    final_status: str = ""
    tier: str = ""
    requests_per_minute: int = 0
    duration_sec: float = 0.0
    per_symbol_summary: list[dict[str, Any]] = field(default_factory=list)

    def finish(self) -> None:
        self.finished_at = datetime.now(VN_TZ)

    def finalize_observability(
        self,
        *,
        tier: str,
        requests_per_minute: int,
        per_symbol_summary: list[dict[str, Any]] | None = None,
    ) -> None:
        """Compute duration, tier, throttle, status, and compact symbol summary."""
        if self.finished_at is None:
            self.finish()

        self.tier = tier
        self.requests_per_minute = requests_per_minute
        self.per_symbol_summary = list(per_symbol_summary or [])
        self.duration_sec = max(
            0.0,
            (self.finished_at - self.started_at).total_seconds(),
        )
        self.final_status = compute_final_status(
            universe_count=self.universe_count,
            symbols_failed=self.symbols_failed,
            bars_valid=self.bars_valid,
            bars_fetched=self.bars_fetched,
            per_symbol_summary=self.per_symbol_summary,
        )

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
        if self.finished_at is None:
            self.finish()
        lines = [
            f"Run {self.run_id} | mode={self.mode} | status={self.final_status or 'PENDING'}",
            f"  tier={self.tier or 'unknown'} rpm={self.requests_per_minute} "
            f"duration={self.duration_sec:.1f}s",
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
        if self.per_symbol_summary:
            lines.append(f"  per_symbol_summary entries={len(self.per_symbol_summary)}")
        return "\n".join(lines)


def symbol_summary_entry(
    symbol: str,
    *,
    status: str,
    reason: str = "",
    bars_fetched: int = 0,
    bars_valid: int = 0,
    bars_rejected: int = 0,
) -> dict[str, Any]:
    """Compact per-symbol issue record for manifest observability."""
    return {
        "symbol": symbol,
        "status": status,
        "reason": reason,
        "bars_fetched": bars_fetched,
        "bars_valid": bars_valid,
        "bars_rejected": bars_rejected,
    }
