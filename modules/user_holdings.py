"""User-owned current holdings. Not a market artifact and not keyed by trade_date.

Durable store:
  1. GitHub Contents API (same GITHUB_TOKEN the app already uses for evolution)
  2. Local data/user_holdings/portfolio_symbols.txt
  3. Legacy cwd portfolio_symbols.txt

Writes only when the user-owned text actually changes.
Rotation / Camera / Candidate / Edge / Learning / BUY ELITE must not import this.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Callable, Optional

DEFAULT_LOCAL_PATH = Path("data") / "user_holdings" / "portfolio_symbols.txt"
LEGACY_LOCAL_PATH = Path("portfolio_symbols.txt")
REMOTE_PATH = "data/user_holdings/portfolio_symbols.txt"
ENV_PATH = "MRBOT_USER_HOLDINGS_FILE"

DEFAULT_GITHUB_OWNER = "SONVODAI"
DEFAULT_GITHUB_REPO = "scanner-ga-chien-clean"


def local_holdings_path() -> Path:
    raw = os.environ.get(ENV_PATH, "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_LOCAL_PATH


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
    github_reader: Optional[Callable[[], Optional[str]]] = None,
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
    github_writer: Optional[Callable[[str], str]] = None,
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
    github_writer: Optional[Callable[[str], str]] = None,
) -> tuple[str, bool, str]:
    """Persist only when the user-owned text actually changed. Empty is a valid clear."""
    if edited == previous:
        return previous, False, "UNCHANGED"
    status = save_holdings_text(edited, github_writer=github_writer)
    return edited, True, status
