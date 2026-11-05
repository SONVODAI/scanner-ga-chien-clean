"""One immutable Guardian Research snapshot per trading session."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

from research.guardian_research.classify import (
    classification_version,
    evaluate_symbol,
    normalize_market_context,
)
from research.guardian_research.contract import (
    CLASS_UNAVAILABLE,
    CLASSIFICATIONS,
    FORWARD_CALENDAR,
    FORWARD_HORIZONS,
    FORWARD_OUTCOMES,
    FORWARD_PENDING,
    FORWARD_REASON,
    FORWARD_UNVERIFIED,
    SCHEMA,
    unverified_forward,
)
from research.guardian_research.universe import load_tracked_symbols


class SnapshotExists(FileExistsError):
    """A session snapshot is already stored and cannot be replaced."""


def build_snapshot(
    session: str,
    observations: dict | None = None,
    market: dict | None = None,
    symbols: tuple[str, ...] | None = None,
    priors: list[dict] | None = None,
) -> dict:
    day = date.fromisoformat(session)
    tracked = tuple(symbols) if symbols is not None else load_tracked_symbols()
    supplied = {str(key).strip().upper(): value for key, value in (observations or {}).items()}
    context = normalize_market_context(market)
    version = classification_version()
    rows = [
        _with_market(evaluate_symbol(symbol, day.isoformat(), supplied.get(symbol)), context)
        for symbol in tracked
    ]
    _annotate_history(rows, priors or [], version)
    document = {
        "schema": SCHEMA,
        "session": day.isoformat(),
        "classification_version": version,
        "classification_scope": "market_technical",
        "portfolio_decision": False,
        "tracked_count": len(tracked),
        "market": context,
        "counts": _counts(rows),
        "rows": rows,
    }
    document["content_sha256"] = _digest(document)
    return document


def label_observation_origin(document: dict, origin: str, *, reconstruction: dict) -> dict:
    """Copy a snapshot and record whether it was sealed at the time or reconstructed."""
    if origin not in {"BACKFILLED", "CONTEMPORANEOUS", "DELAYED"}:
        raise ValueError("unknown observation origin")
    if not isinstance(reconstruction, dict):
        raise ValueError("reconstruction record required")
    body = {key: value for key, value in document.items() if key != "content_sha256"}
    body["observation_origin"] = origin
    body["reconstruction"] = reconstruction
    body["content_sha256"] = _digest(body)
    _require_document(body)
    return body


def write_snapshot(root: Path, document: dict) -> Path:
    """Create the session file. An identical retry returns the existing file."""
    _require_document(document)
    dest = Path(root) / "sessions" / (document["session"] + ".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            existing = read_snapshot(dest)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SnapshotExists(document["session"]) from exc
        if existing.get("content_sha256") == document["content_sha256"]:
            return dest
        raise SnapshotExists(document["session"])
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SnapshotExists(document["session"]) from exc
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    return dest


def read_snapshot(path: Path) -> dict:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    _require_document(document)
    return document


def _with_market(row: dict, context: dict) -> dict:
    stored = dict(row)
    stored["market_real"] = context.get("market_real")
    stored["market_real_provenance"] = context.get("market_real_provenance")
    stored["market_real_status"] = context.get("market_real_status")
    stored["market_context_used_by_classification"] = False
    return stored


def load_prior_snapshots(root: Path, session: str) -> list[dict]:
    folder = Path(root) / "sessions"
    if not folder.is_dir():
        return []
    priors = []
    for path in sorted(folder.glob("*.json")):
        if path.stem >= session:
            continue
        try:
            priors.append(read_snapshot(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return priors


def _annotate_history(rows: list[dict], priors: list[dict], version: str) -> None:
    history: dict[str, list[dict]] = {}
    for prior in sorted(priors, key=lambda item: str(item.get("session") or "")):
        if prior.get("schema") != SCHEMA:
            continue
        for earlier in prior.get("rows") or []:
            symbol = str(earlier.get("symbol") or "")
            if symbol:
                history.setdefault(symbol, []).append(earlier)
    for row in rows:
        past = history.get(row["symbol"], [])
        previous = past[-1] if past else None
        row["previous_classification"] = previous.get("classification") if previous else None
        row["previous_session"] = previous.get("session") if previous else None
        row["forward"] = unverified_forward()
        current = row["classification"]
        if current == CLASS_UNAVAILABLE:
            row["transition"] = "UNAVAILABLE"
            row["state_age_sessions"] = None
            continue
        if previous is None:
            row["transition"] = "INITIAL"
            row["state_age_sessions"] = 1
            continue
        same_label = previous.get("classification") == current
        same_version = previous.get("classification_version") == version
        if same_label and same_version:
            age = 1
            for earlier in reversed(past):
                if (
                    earlier.get("classification") == current
                    and earlier.get("classification_version") == version
                ):
                    age += 1
                else:
                    break
            row["transition"] = "UNCHANGED"
            row["state_age_sessions"] = age
        elif same_label:
            row["transition"] = "VERSION_BREAK"
            row["state_age_sessions"] = 1
        else:
            row["transition"] = "CHANGED"
            row["state_age_sessions"] = 1


def _counts(rows: list[dict]) -> dict:
    counts = {name: 0 for name in sorted(CLASSIFICATIONS)}
    for row in rows:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    return counts


def _digest(document: dict) -> str:
    body = {key: value for key, value in document.items() if key != "content_sha256"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_document(document: dict) -> None:
    if document.get("schema") != SCHEMA:
        raise ValueError("unexpected snapshot schema")
    if document.get("portfolio_decision") is not False:
        raise ValueError("snapshot must not be a portfolio decision")
    date.fromisoformat(document["session"])
    expected = _digest(document)
    if document.get("content_sha256") != expected:
        raise ValueError("snapshot hash mismatch")
    for row in document["rows"]:
        if row["classification"] not in CLASSIFICATIONS:
            raise ValueError("unknown classification")
        if row.get("portfolio_decision") is not False:
            raise ValueError("row must not be a portfolio decision")
        if row["session"] != document["session"]:
            raise ValueError("row session mismatch")
        forward = row.get("forward")
        if not isinstance(forward, dict) or forward.get("status") != FORWARD_UNVERIFIED:
            raise ValueError("forward outcome must stay unverified")
        if forward.get("reason") != FORWARD_REASON or forward.get("calendar") != FORWARD_CALENDAR:
            raise ValueError("forward measurement is not ready")
        horizons = forward.get("horizons")
        if not isinstance(horizons, dict):
            raise ValueError("forward horizons missing")
        for horizon in FORWARD_HORIZONS:
            item = horizons.get(f"T+{horizon}")
            if not isinstance(item, dict) or item.get("status") != FORWARD_PENDING:
                raise ValueError("forward horizon must stay pending")
            if any(item.get(name) is not None for name in FORWARD_OUTCOMES):
                raise ValueError("forward outcome must stay empty")
