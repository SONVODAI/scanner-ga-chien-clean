"""Cloud → VPS Dynamic Watchlist bus (GitHub Contents, exact snapshot bytes).

Does not reconstruct clocks. Does not invent Candidate rows on fetch failure.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from modules.live_candidate.watchlist import persist_research_watchlist
from modules.live_shadow_transport.contract import (
    EMPTY_WATCHLIST_TEXT,
    GITHUB_WATCHLIST_PATH,
    WATCHLIST_PUBLISH_STATUS_NAME,
    WATCHLIST_TRANSPORT_ERROR,
)

Writer = Callable[[str, str, str], str]
Fetcher = Callable[[], "WatchlistFetchResult"]

DEFAULT_OWNER = "SONVODAI"
DEFAULT_REPO = "scanner-ga-chien-clean"
GITHUB_API = "https://api.github.com"


class WatchlistTransportError(RuntimeError):
    """Published watchlist could not be fetched or written."""


@dataclass
class WatchlistPublishResult:
    ok: bool
    status: str
    detail: str = ""
    path: str = GITHUB_WATCHLIST_PATH
    bytes_len: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "detail": self.detail,
            "path": self.path,
            "bytes": self.bytes_len,
        }


@dataclass
class WatchlistFetchResult:
    ok: bool
    rows: list[dict[str, Any]]
    raw_text: str = ""
    error: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "n": len(self.rows),
            "error": self.error,
        }


def parse_watchlist_text(text: str) -> list[dict[str, Any]]:
    """Parse published JSON without rewriting timestamps or inventing rows."""
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        rows = data.get("rows")
        if isinstance(rows, list):
            return rows
    raise WatchlistTransportError("watchlist JSON is not a list")


def publish_watchlist_bytes(
    text: str,
    writer: Writer,
    *,
    path: str = GITHUB_WATCHLIST_PATH,
    message: str = "live candidate: publish dynamic watchlist snapshot",
) -> WatchlistPublishResult:
    """Publish the exact snapshot text. Writer may not mutate clocks."""
    try:
        status = writer(path, text, message)
    except Exception as exc:  # noqa: BLE001 — transport failure must stay explicit
        return WatchlistPublishResult(
            ok=False,
            status=WATCHLIST_TRANSPORT_ERROR,
            detail=str(exc),
            path=path,
            bytes_len=len(text.encode("utf-8")),
        )
    if status == "GITHUB_OK":
        return WatchlistPublishResult(
            ok=True,
            status="GITHUB_OK",
            detail="",
            path=path,
            bytes_len=len(text.encode("utf-8")),
        )
    return WatchlistPublishResult(
        ok=False,
        status=WATCHLIST_TRANSPORT_ERROR,
        detail=str(status or "github write failed"),
        path=path,
        bytes_len=len(text.encode("utf-8")),
    )


def write_publish_status(out_dir: Path, result: WatchlistPublishResult) -> Path:
    path = Path(out_dir) / WATCHLIST_PUBLISH_STATUS_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def persist_and_publish_research_watchlist(
    history: Any,
    *,
    observed_at: datetime,
    out_dir: Path | None = None,
    publisher: Optional[Writer] = None,
    skip_if_unchanged: bool = True,
) -> tuple[Path, WatchlistPublishResult]:
    """Persist locally (including canonical []), then publish the same bytes.

    An empty universe is a present `[]` document, never a missing GitHub object.
    Unchanged remote bytes are not rewritten (avoids commit spam).
    """
    path = persist_research_watchlist(history, observed_at=observed_at, out_dir=out_dir)
    text = path.read_text(encoding="utf-8")
    if publisher is None:
        result = WatchlistPublishResult(
            ok=False,
            status=WATCHLIST_TRANSPORT_ERROR,
            detail="no github publisher configured",
            bytes_len=len(text.encode("utf-8")),
        )
    elif skip_if_unchanged and _remote_watchlist_matches(text):
        result = WatchlistPublishResult(
            ok=True,
            status="GITHUB_OK",
            detail="unchanged",
            bytes_len=len(text.encode("utf-8")),
        )
    else:
        result = publish_watchlist_bytes(text, publisher)
    write_publish_status(path.parent, result)
    return path, result


def _normalize_watchlist_text(text: str) -> str:
    rows = parse_watchlist_text(text)
    if not rows:
        return EMPTY_WATCHLIST_TEXT
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def _remote_watchlist_matches(text: str) -> bool:
    """True when GitHub already has the same snapshot (empty or non-empty)."""
    try:
        current = fetch_github_watchlist_text()
    except WatchlistTransportError:
        return False
    except Exception:
        return False
    try:
        return _normalize_watchlist_text(current) == _normalize_watchlist_text(text)
    except Exception:
        return False


def fetch_github_watchlist_text(
    *,
    token: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    path: str = GITHUB_WATCHLIST_PATH,
    opener: Any = None,
) -> str:
    """GET exact file bytes via GitHub Contents API (raw accept). No clock rewrite."""
    tok = (token if token is not None else os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    own = (owner or os.environ.get("GITHUB_REPO_OWNER") or DEFAULT_OWNER).strip()
    rpo = (repo or os.environ.get("GITHUB_REPO_NAME") or DEFAULT_REPO).strip()
    url = f"{GITHUB_API}/repos/{own}/{rpo}/contents/{path}"
    headers = {
        "User-Agent": "mrbot-live-shadow-transport/1.0",
        "Accept": "application/vnd.github.raw",
    }
    if tok:
        headers["Authorization"] = f"token {tok}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise WatchlistTransportError(f"github HTTP {exc.code}") from exc
    except Exception as exc:  # noqa: BLE001
        raise WatchlistTransportError(f"github fetch failed: {exc}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WatchlistTransportError("github watchlist is not utf-8") from exc


def fetch_published_watchlist(
    *,
    fetcher: Fetcher | None = None,
    **kwargs: Any,
) -> WatchlistFetchResult:
    """Fetch the published snapshot. On failure: explicit error, empty rows, no stale fallback."""
    if fetcher is not None:
        result = fetcher()
        if not result.ok:
            return WatchlistFetchResult(ok=False, rows=[], raw_text="", error=result.error or WATCHLIST_TRANSPORT_ERROR)
        return result
    try:
        text = fetch_github_watchlist_text(**kwargs)
        rows = parse_watchlist_text(text)
    except WatchlistTransportError as exc:
        return WatchlistFetchResult(ok=False, rows=[], raw_text="", error=str(exc))
    except Exception as exc:  # noqa: BLE001 — never invent Candidate state
        return WatchlistFetchResult(ok=False, rows=[], raw_text="", error=str(exc))
    return WatchlistFetchResult(ok=True, rows=rows, raw_text=text, error=None)
