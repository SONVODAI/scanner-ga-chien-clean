"""Tracked symbols from the production WATCHLIST literal. app.py is not executed."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_WATCHLIST = re.compile(
    r"^WATCHLIST = sorted\(list\(set\(\[(.*?)\]\)\)\)",
    re.M | re.S,
)


def load_tracked_symbols(app_path: Path | None = None) -> tuple[str, ...]:
    path = app_path or (_REPO / "app.py")
    text = path.read_text(encoding="utf-8")
    match = _WATCHLIST.search(text)
    if match is None:
        raise ValueError("WATCHLIST literal not found")
    raw = ast.literal_eval("[" + match.group(1) + "]")
    symbols = tuple(sorted({str(item).strip().upper() for item in raw if str(item).strip()}))
    if not symbols:
        raise ValueError("WATCHLIST is empty")
    return symbols
