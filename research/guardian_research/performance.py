"""Read a finished Guardian performance view. It does not classify or score prices."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "guardian_research_performance.v1"
PRICE_BASIS = "APPROX_LAST_5M_CLOSE"
BUNDLED_VIEW = Path(__file__).resolve().parent / "performance_view.json"


def read_performance_view(path: Path | None = None) -> dict | None:
    target = Path(path) if path is not None else BUNDLED_VIEW
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        return None
    if document.get("official_pnl") is not False or document.get("portfolio_decision") is not False:
        return None
    if document.get("price_basis") != PRICE_BASIS:
        return None
    if document.get("content_sha256") != _digest(document):
        return None
    return document


def _digest(document: dict) -> str:
    body = {key: value for key, value in document.items() if key != "content_sha256"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
