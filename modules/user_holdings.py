"""User-owned current holdings. Not a market artifact and not keyed by trade_date.

Durable store:
  1. data/user_holdings/positions.json  (user_holdings.v1)
  2. GitHub Contents API (same GITHUB_TOKEN as evolution)
  3. Legacy portfolio_symbols.txt (read-only fallback; never overwritten with JSON)

Writes only when the user-owned canonical JSON actually changes.
Rotation / Camera / Candidate / Edge / Learning / BUY ELITE must not import this.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

SCHEMA = "user_holdings.v1"

DEFAULT_LOCAL_PATH = Path("data") / "user_holdings" / "portfolio_symbols.txt"
DEFAULT_JSON_PATH = Path("data") / "user_holdings" / "positions.json"
LEGACY_LOCAL_PATH = Path("portfolio_symbols.txt")
REMOTE_PATH = "data/user_holdings/portfolio_symbols.txt"
REMOTE_JSON_PATH = "data/user_holdings/positions.json"
ENV_PATH = "MRBOT_USER_HOLDINGS_FILE"
ENV_JSON_PATH = "MRBOT_USER_HOLDINGS_JSON"

DEFAULT_GITHUB_OWNER = "SONVODAI"
DEFAULT_GITHUB_REPO = "scanner-ga-chien-clean"

GithubReader = Callable[[], Optional[str]]
GithubWriter = Callable[[str], str]


def local_holdings_path() -> Path:
    raw = os.environ.get(ENV_PATH, "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_LOCAL_PATH


def local_positions_path() -> Path:
    raw = os.environ.get(ENV_JSON_PATH, "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_JSON_PATH


def _secret_or_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value:
        return str(value).strip()
    try:
        import streamlit as st

        secret = st.secrets.get(name, None)
        if secret:
            return str(secret).strip()
    except Exception:
        pass
    return default


def _github_token() -> Optional[str]:
    return _secret_or_env("GITHUB_TOKEN")


def _github_read(path: str = REMOTE_PATH) -> Optional[str]:
    token = _github_token()
    if not token:
        return None
    try:
        import requests
    except Exception:
        return None
    owner = _secret_or_env("GITHUB_REPO_OWNER", DEFAULT_GITHUB_OWNER)
    repo = _secret_or_env("GITHUB_REPO_NAME", DEFAULT_GITHUB_REPO)
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    try:
        resp = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=10)
        if resp.status_code == 200:
            content = resp.json().get("content", "")
            return base64.b64decode(content).decode("utf-8")
    except Exception:
        return None
    return None


def _github_write(text: str, path: str = REMOTE_PATH) -> str:
    token = _github_token()
    if not token:
        return "LOCAL_ONLY"
    try:
        import requests
    except Exception:
        return "GITHUB_ERROR"
    owner = _secret_or_env("GITHUB_REPO_OWNER", DEFAULT_GITHUB_OWNER)
    repo = _secret_or_env("GITHUB_REPO_NAME", DEFAULT_GITHUB_REPO)
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {"Authorization": f"token {token}"}
    try:
        encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
        sha = None
        get_r = requests.get(url, headers=headers, timeout=10)
        if get_r.status_code == 200:
            sha = get_r.json().get("sha")
        payload = {
            "message": "Update user holdings (manual)",
            "content": encoded,
        }
        if sha:
            payload["sha"] = sha
        put_r = requests.put(url, headers=headers, json=payload, timeout=15)
        if put_r.status_code in {200, 201}:
            return "GITHUB_OK"
        return f"GITHUB_FAIL_{put_r.status_code}"
    except Exception:
        return "GITHUB_ERROR"


def _read_path(path: Path) -> Optional[str]:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except OSError:
        return None
    return None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_holdings_text(
    *,
    github_reader: Optional[GithubReader] = None,
) -> str:
    """GitHub first (survives Streamlit Cloud restart), then local, then legacy."""
    reader = github_reader if github_reader is not None else _github_read
    try:
        remote = reader()
    except Exception:
        remote = None
    if remote is not None:
        return remote

    current = _read_path(local_holdings_path())
    if current is not None:
        return current
    legacy = _read_path(LEGACY_LOCAL_PATH)
    if legacy is not None:
        return legacy
    return ""


def save_holdings_text(
    text: str,
    *,
    github_writer: Optional[GithubWriter] = None,
) -> str:
    payload = text if text is not None else ""
    _atomic_write(local_holdings_path(), payload)
    try:
        _atomic_write(LEGACY_LOCAL_PATH, payload)
    except OSError:
        pass
    writer = github_writer if github_writer is not None else _github_write
    try:
        return writer(payload)
    except Exception:
        return "LOCAL_ONLY"


def persist_if_changed(
    edited: str,
    previous: str,
    *,
    github_writer: Optional[GithubWriter] = None,
) -> tuple[str, bool, str]:
    """Persist only when the user-owned text actually changed. Empty is a valid clear."""
    if edited == previous:
        return previous, False, "UNCHANGED"
    status = save_holdings_text(edited, github_writer=github_writer)
    return edited, True, status


def parse_legacy_symbols(text: str | None) -> list[str]:
    if text is None:
        return []
    blob = str(text).upper().replace("\n", ",")
    symbols: list[str] = []
    for item in blob.split(","):
        item = item.strip()
        if not item or item in symbols:
            continue
        symbols.append(item)
    return symbols


def _optional_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        if hasattr(value, "item"):
            value = value.item()
    except Exception:
        pass
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return None
    except Exception:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _optional_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def normalize_position(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        symbol = raw.strip().upper()
        if not symbol:
            return None
        return {"symbol": symbol, "entry_price": None, "entry_date": None}
    if not isinstance(raw, dict):
        return None
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    return {
        "symbol": symbol,
        "entry_price": _optional_price(raw.get("entry_price")),
        "entry_date": _optional_date(raw.get("entry_date")),
    }


def normalize_positions(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    by_symbol: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in rows:
        item = normalize_position(raw)
        if item is None:
            continue
        symbol = item["symbol"]
        if symbol not in by_symbol:
            order.append(symbol)
        by_symbol[symbol] = item
    return [by_symbol[symbol] for symbol in order]


def positions_from_legacy_text(text: str | None) -> list[dict[str, Any]]:
    return [
        {"symbol": symbol, "entry_price": None, "entry_date": None}
        for symbol in parse_legacy_symbols(text)
    ]


def parse_positions_document(text: str | None) -> list[dict[str, Any]] | None:
    if text is None or not str(text).strip():
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema") != SCHEMA:
        return None
    if "positions" not in data or not isinstance(data["positions"], list):
        return None
    return normalize_positions(data["positions"])


def canonical_positions_text(positions: list[dict[str, Any]]) -> str:
    normalized = normalize_positions(positions)
    payload = {
        "schema": SCHEMA,
        "positions": [
            {
                "symbol": item["symbol"],
                "entry_price": item["entry_price"],
                "entry_date": item["entry_date"],
            }
            for item in normalized
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _read_json_text(
    *,
    json_github_reader: Optional[GithubReader] = None,
) -> Optional[str]:
    reader = json_github_reader
    if reader is None:
        reader = lambda: _github_read(REMOTE_JSON_PATH)
    try:
        remote = reader()
    except Exception:
        remote = None
    if remote is not None:
        return remote
    return _read_path(local_positions_path())


def load_positions(
    *,
    json_github_reader: Optional[GithubReader] = None,
    legacy_github_reader: Optional[GithubReader] = None,
) -> list[dict[str, Any]]:
    """Prefer valid positions.json; otherwise migrate legacy symbols in memory."""
    parsed = parse_positions_document(
        _read_json_text(json_github_reader=json_github_reader)
    )
    if parsed is not None:
        return parsed
    return positions_from_legacy_text(
        load_holdings_text(github_reader=legacy_github_reader)
    )


def save_positions(
    positions: list[dict[str, Any]],
    *,
    github_writer: Optional[GithubWriter] = None,
) -> str:
    payload = canonical_positions_text(positions)
    _atomic_write(local_positions_path(), payload)
    writer = github_writer
    if writer is None:
        writer = lambda text: _github_write(text, REMOTE_JSON_PATH)
    try:
        return writer(payload)
    except Exception:
        return "LOCAL_ONLY"


def persist_positions_if_changed(
    edited: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    *,
    github_writer: Optional[GithubWriter] = None,
) -> tuple[list[dict[str, Any]], bool, str]:
    """Persist only when canonical JSON differs. Empty list is an explicit clear."""
    new_text = canonical_positions_text(edited)
    old_text = canonical_positions_text(previous)
    if new_text == old_text:
        return normalize_positions(previous), False, "UNCHANGED"
    status = save_positions(edited, github_writer=github_writer)
    return normalize_positions(edited), True, status


def pnl_pct(current_price: Any, entry_price: Any) -> float | None:
    current = _optional_price(current_price)
    entry = _optional_price(entry_price)
    if current is None or entry is None or entry == 0:
        return None
    return (current / entry - 1.0) * 100.0


def holding_days(entry_date: Any, today: date | None = None) -> int | None:
    parsed = _optional_date(entry_date)
    if parsed is None:
        return None
    day = today or date.today()
    return (day - date.fromisoformat(parsed)).days
