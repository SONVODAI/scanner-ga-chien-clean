"""Verify a research-ledger delivery before the panel displays it.

This module reads a local directory of board.json, source_clock.json and
manifest.json. It does not open a network connection, and it does not compute
horizon returns.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATA_FRESH = "DATA_FRESH"
SOURCE_STALE = "SOURCE_STALE"
MISSING_SOURCE = "MISSING_SOURCE"
DELIVERY_UNAVAILABLE = "DELIVERY_UNAVAILABLE"
MAX_BOARD_BYTES = 32 * 1024 * 1024
MANIFEST_SCHEMA = "v2_research_publisher_manifest.v1"
CLOCK_SCHEMA = "v2_research_ledger_source_clock.v1"
BOARD_NAME = "board.json"
CLOCK_NAME = "source_clock.json"
MANIFEST_NAME = "manifest.json"

# Design names for a later GET-only host map. This module does not register them.
RESEARCH_BOARD_PATH = "/current/research_ledger/board.json"
RESEARCH_CLOCK_PATH = "/current/research_ledger/source_clock.json"
RESEARCH_MANIFEST_PATH = "/current/research_ledger/manifest.json"


@dataclass(frozen=True)
class DeliveryDiagnostics:
    """Read-only identity of one accepted delivery. It does not select trades."""

    generation_id: str
    as_of: str
    published_at: str
    rows: int
    source_health: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DeliveryView:
    state: str
    reason: str
    board: dict[str, Any] | None = None
    rows: int = 0
    diagnostics: DeliveryDiagnostics | None = None


def load_delivery(directory: Path) -> DeliveryView:
    """Accept one consistent trio, or refuse it without a partial board."""
    root = Path(directory)
    board_path = root / BOARD_NAME
    clock_path = root / CLOCK_NAME
    manifest_path = root / MANIFEST_NAME
    if not board_path.is_file() or not clock_path.is_file() or not manifest_path.is_file():
        return DeliveryView(DELIVERY_UNAVAILABLE, "incomplete")
    try:
        board_bytes = board_path.read_bytes()
        clock_bytes = clock_path.read_bytes()
        manifest_bytes = manifest_path.read_bytes()
    except OSError:
        return DeliveryView(DELIVERY_UNAVAILABLE, "unreadable")
    if len(board_bytes) > MAX_BOARD_BYTES or not board_bytes.endswith(b"\n"):
        return DeliveryView(DELIVERY_UNAVAILABLE, "board_bounds")
    try:
        board = json.loads(board_bytes)
        clock = json.loads(clock_bytes)
        manifest = json.loads(manifest_bytes)
    except (json.JSONDecodeError, UnicodeError):
        return DeliveryView(DELIVERY_UNAVAILABLE, "corrupt")
    if not isinstance(board, dict) or not isinstance(clock, dict) or not isinstance(manifest, dict):
        return DeliveryView(DELIVERY_UNAVAILABLE, "corrupt")
    if manifest.get("schema") != MANIFEST_SCHEMA or clock.get("schema") != CLOCK_SCHEMA:
        return DeliveryView(DELIVERY_UNAVAILABLE, "schema")
    if manifest.get("final_buy_enabled") is not False:
        return DeliveryView(DELIVERY_UNAVAILABLE, "final_buy")
    digest = hashlib.sha256(board_bytes).hexdigest()
    clock_digest = hashlib.sha256(clock_bytes).hexdigest()
    if manifest.get("board_sha256") != digest or manifest.get("generation_id") != digest:
        return DeliveryView(DELIVERY_UNAVAILABLE, "board_checksum")
    if manifest.get("clock_sha256") != clock_digest:
        return DeliveryView(DELIVERY_UNAVAILABLE, "clock_checksum")
    if int(manifest.get("board_bytes") or -1) != len(board_bytes):
        return DeliveryView(DELIVERY_UNAVAILABLE, "board_size")
    rows = board.get("rows")
    if not isinstance(rows, list):
        return DeliveryView(DELIVERY_UNAVAILABLE, "rows")
    if manifest.get("rows") != len(rows):
        return DeliveryView(DELIVERY_UNAVAILABLE, "row_count")
    coverage = board.get("coverage") if isinstance(board.get("coverage"), dict) else {}
    if coverage.get("rows") not in (None, len(rows)):
        return DeliveryView(DELIVERY_UNAVAILABLE, "row_count")
    return DeliveryView(
        _state(board),
        "ok",
        board,
        len(rows),
        _diagnostics(board, manifest, len(rows)),
    )


def _diagnostics(board: dict[str, Any], manifest: dict[str, Any], rows: int) -> DeliveryDiagnostics:
    health = manifest.get("source_health") if isinstance(manifest.get("source_health"), dict) else {}
    if not health:
        fresh = board.get("freshness") if isinstance(board.get("freshness"), dict) else {}
        nested = fresh.get("source_health") if isinstance(fresh.get("source_health"), dict) else {}
        health = nested
    pairs: list[tuple[str, str]] = []
    for name in sorted(health):
        item = health[name]
        status = item.get("status") if isinstance(item, dict) else ""
        pairs.append((str(name), str(status or "")))
    return DeliveryDiagnostics(
        generation_id=str(manifest.get("generation_id") or ""),
        as_of=str(board.get("as_of") or ""),
        published_at=str(manifest.get("published_at") or ""),
        rows=rows,
        source_health=tuple(pairs),
    )


def _state(board: dict[str, Any]) -> str:
    fresh = board.get("freshness") if isinstance(board.get("freshness"), dict) else {}
    reasons = [str(item) for item in (fresh.get("reasons") or [])]
    if any(item == SOURCE_STALE or item.startswith(f"{SOURCE_STALE}:") for item in reasons):
        return SOURCE_STALE
    health = fresh.get("source_health") if isinstance(fresh.get("source_health"), dict) else {}
    missing_health = any(
        isinstance(item, dict) and item.get("status") == "MISSING" for item in health.values()
    )
    if any(item == MISSING_SOURCE or item.startswith(f"{MISSING_SOURCE}:") for item in reasons) or missing_health:
        return MISSING_SOURCE
    return DATA_FRESH
