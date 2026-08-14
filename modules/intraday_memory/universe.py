"""
Production universe loader.

Derives the 142-symbol WATCHLIST from app.py via static parsing.
Does NOT import or execute Streamlit / app.py runtime.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

WATCHLIST_PATTERN = re.compile(
    r"WATCHLIST\s*=\s*sorted\s*\(\s*list\s*\(\s*set\s*\(\s*\[(.*?)\]\s*\)\s*\)\s*\)",
    re.DOTALL,
)


def _extract_via_regex(source: str) -> list[str]:
    match = WATCHLIST_PATTERN.search(source)
    if not match:
        raise ValueError("WATCHLIST block not found in app.py")
    symbols = re.findall(r'"([A-Z0-9]+)"', match.group(1))
    if not symbols:
        raise ValueError("No symbols parsed from WATCHLIST")
    return sorted(set(symbols))


def _extract_via_ast(source: str) -> list[str]:
    """Fallback: walk AST for WATCHLIST assignment."""
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "WATCHLIST":
                value = ast.literal_eval(node.value)
                if isinstance(value, list):
                    return sorted(set(str(s).upper() for s in value))
    raise ValueError("WATCHLIST assignment not found via AST")


@lru_cache(maxsize=4)
def load_production_universe(app_py_path: str | Path | None = None) -> tuple[str, ...]:
    """
    Return production symbols from app.py WATCHLIST.

    Cached by path. Raises ValueError if parsing fails.
    """
    path = Path(app_py_path) if app_py_path else Path(__file__).resolve().parents[2] / "app.py"
    if not path.exists():
        raise FileNotFoundError(f"app.py not found: {path}")

    source = path.read_text(encoding="utf-8")
    try:
        symbols = _extract_via_regex(source)
    except ValueError:
        symbols = _extract_via_ast(source)

    return tuple(sorted(set(symbols)))


def universe_count(app_py_path: str | Path | None = None) -> int:
    return len(load_production_universe(app_py_path))
