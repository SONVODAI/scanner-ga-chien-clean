"""Read production WATCHLIST without executing the Streamlit app."""

from __future__ import annotations

import ast
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def app_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "app.py"


def _extract_string_list(node: ast.AST) -> list[str] | None:
    """Pull string elements from list/set/tuple or nested Call(list/set/sorted)."""
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out: list[str] = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
            else:
                return None
        return out
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else None
        if name in {"list", "set", "sorted", "tuple"} and node.args:
            return _extract_string_list(node.args[0])
    return None


def load_watchlist(path: Path | None = None) -> tuple[str, ...]:
    """Parse the ``WATCHLIST`` assignment from ``app.py`` (read-only AST)."""
    source_path = Path(path) if path is not None else app_path()
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "WATCHLIST":
                items = _extract_string_list(node.value)
                if items is None:
                    raise ValueError("WATCHLIST assignment is not a parseable string collection")
                symbols = sorted({item.strip().upper() for item in items if item.strip()})
                return tuple(symbols)
    raise ValueError(f"WATCHLIST not found in {source_path}")
