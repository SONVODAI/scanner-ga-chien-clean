"""Publish one verified research trio onto the serving store.

The publisher directory and the directory Streamlit reads are different.
This module copies a trio only after nomination identities are preserved.
It stages a temporary manifest stamp, validates schema, row count and
checksums, then asks the exporter to switch the serving pointer. A refusal
or a failed switch leaves the previous pointer in place.

Unattributed action rows stay unattributed. History JSONL is not opened.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from research.v2_research_ledger.export_delivery import (
    BOARD_NAME,
    CLOCK_NAME,
    MANIFEST_NAME,
    REFUSED,
    ExportResult,
    current_target,
    export_once,
)

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
NOMINATION_SOURCES = frozenset({"brain_a_scan_setup", "market_aware_sweetspot"})
UNATTRIBUTED_SOURCE = "unattributed"
UNATTRIBUTED_COHORT = "action_unattributed"
NOMINATION_COHORT = "nomination"

SERVING_POINTER_NOT_UPDATED = "serving_pointer_not_updated"
ALIGNED = "aligned"


def diagnose_generations(publisher_generation: str, serving_generation: str) -> dict[str, str]:
    """Explain whether the serving pointer matches the publisher generation."""
    publisher = str(publisher_generation or "")
    serving = str(serving_generation or "")
    if publisher and publisher == serving:
        reason = ALIGNED
    elif not serving:
        reason = "serving_pointer_missing"
    elif not publisher:
        reason = "publisher_generation_missing"
    else:
        reason = SERVING_POINTER_NOT_UPDATED
    return {
        "publisher_generation": publisher,
        "serving_generation": serving,
        "reason": reason,
    }


def publish_serving(
    source: Path,
    store: Path,
    *,
    published_at: datetime | None = None,
    replace: Any = None,
) -> ExportResult:
    """Validate, stage, and switch the serving pointer, or leave it unchanged."""
    root = Path(store)
    incoming = _read_board(Path(source) / BOARD_NAME)
    if isinstance(incoming, ExportResult):
        return incoming
    previous = _serving_board(root)
    if isinstance(previous, ExportResult):
        return previous
    refusal = _preservation_reason(previous, incoming)
    if refusal:
        return ExportResult(REFUSED, refusal)
    stamp = _stamp(published_at)
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "trio"
        staged.mkdir()
        try:
            _stage_trio(Path(source), root, staged, published_at=stamp)
        except (OSError, json.JSONDecodeError, UnicodeError, ValueError):
            return ExportResult(REFUSED, "corrupt")
        if replace is None:
            return export_once(staged, root)
        return export_once(staged, root, replace=replace)


def _stamp(moment: datetime | None) -> str:
    if moment is None:
        moment = datetime.now(ICT)
    if moment.tzinfo is None:
        raise ValueError("published_at requires a timezone")
    return moment.isoformat()


def _read_board(path: Path) -> dict[str, Any] | ExportResult:
    if not path.is_file():
        return ExportResult(REFUSED, "missing")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return ExportResult(REFUSED, "corrupt")
    if not isinstance(loaded, dict) or not isinstance(loaded.get("rows"), list):
        return ExportResult(REFUSED, "corrupt")
    return loaded


def _serving_board(store: Path) -> dict[str, Any] | None | ExportResult:
    if not store.exists():
        return None
    ident = current_target(store)
    if not ident:
        link = store / "current"
        if link.exists() or link.is_symlink():
            return ExportResult(REFUSED, "current_broken")
        return None
    path = store / "generations" / ident / BOARD_NAME
    loaded = _read_board(path)
    if isinstance(loaded, ExportResult):
        return ExportResult(REFUSED, "current_broken")
    return loaded


def _preservation_reason(
    previous: dict[str, Any] | None,
    incoming: dict[str, Any],
) -> str:
    nxt = _nominations(incoming)
    if isinstance(nxt, str):
        return nxt
    for row in incoming["rows"]:
        if not isinstance(row, dict):
            return "corrupt"
        if _promoted(row):
            return "unattributed_promoted"
    if previous is None:
        return ""
    kept = _nominations(previous)
    if isinstance(kept, str):
        return "current_broken"
    if len(nxt) < len(kept):
        return "nomination_rows_decreased"
    for ident, prior in kept.items():
        if ident not in nxt:
            return "nomination_missing"
        if nxt[ident]["t0_date"] != prior["t0_date"]:
            return "t0_changed"
        if nxt[ident]["source"] != prior["source"]:
            return "source_changed"
        if nxt[ident]["symbol"] != prior["symbol"]:
            return "symbol_changed"
    return ""


def _promoted(row: dict[str, Any]) -> bool:
    cohort = str(row.get("cohort") or "")
    source = str(row.get("source") or "")
    if cohort == UNATTRIBUTED_COHORT and source != UNATTRIBUTED_SOURCE:
        return True
    if cohort == NOMINATION_COHORT and source == UNATTRIBUTED_SOURCE:
        return True
    if cohort == UNATTRIBUTED_COHORT and source in NOMINATION_SOURCES:
        return True
    return False


def _nominations(board: dict[str, Any]) -> dict[str, dict[str, str]] | str:
    found: dict[str, dict[str, str]] = {}
    for row in board["rows"]:
        if not isinstance(row, dict) or not _is_nomination(row):
            continue
        ident = str(row.get("row_id") or "")
        if not ident:
            return "nomination_missing"
        if ident in found:
            return "nomination_duplicate"
        found[ident] = {
            "source": str(row.get("source") or ""),
            "t0_date": str(row.get("t0_date") or ""),
            "symbol": str(row.get("symbol") or ""),
        }
    return found


def _is_nomination(row: dict[str, Any]) -> bool:
    cohort = str(row.get("cohort") or "")
    source = str(row.get("source") or "")
    if cohort == UNATTRIBUTED_COHORT:
        return False
    if cohort == NOMINATION_COHORT:
        return True
    return source in NOMINATION_SOURCES


def _stage_trio(source: Path, store: Path, dest: Path, *, published_at: str) -> None:
    board_bytes = (source / BOARD_NAME).read_bytes()
    clock_bytes = (source / CLOCK_NAME).read_bytes()
    (dest / BOARD_NAME).write_bytes(board_bytes)
    (dest / CLOCK_NAME).write_bytes(clock_bytes)
    digest = hashlib.sha256(board_bytes).hexdigest()
    existing = store / "generations" / digest / MANIFEST_NAME
    if existing.is_file():
        try:
            prior = json.loads(existing.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            prior = None
        if isinstance(prior, dict) and prior.get("board_sha256") == digest and prior.get("published_at"):
            (dest / MANIFEST_NAME).write_bytes(existing.read_bytes())
            return
    manifest_path = source / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest")
    if not manifest.get("published_at"):
        manifest["published_at"] = published_at
    payload = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    (dest / MANIFEST_NAME).write_bytes(payload)
