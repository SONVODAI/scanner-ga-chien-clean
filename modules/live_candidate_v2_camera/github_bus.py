"""Slice 3B: isolated GitHub Contents transport for the V2 Camera sidecar.

Cloud local sidecar → GitHub Contents V2 path → fetch + validate.
Does not rebuild nominations. Does not retarget production watchlist.
Does not poll KBS. Does not start the runner.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from modules.live_candidate.contract import has_legal_first_seen
from modules.live_candidate_v2_camera.contract import (
    ENV_V2_GITHUB_PUBLISH,
    ENV_V2_GITHUB_PUBLISH_FALSY,
    ENV_V2_GITHUB_PUBLISH_TRUTHY,
    GITHUB_V2_SIDECAR_PATH,
    PRODUCTION_WATCHLIST_RELPATH,
    SCHEMA_ID,
)
from modules.live_shadow_transport.contract import GITHUB_WATCHLIST_PATH
from modules.live_shadow_transport.watchlist_bus import (
    DEFAULT_OWNER,
    DEFAULT_REPO,
    GITHUB_API,
    WatchlistTransportError,
    fetch_github_watchlist_text,
    publish_watchlist_bytes,
)

Writer = Callable[[str, str, str], str]

STATUS_GATE_OFF = "GATE_OFF"
STATUS_NOT_ELIGIBLE = "NOT_ELIGIBLE"
STATUS_PUBLISHED = "GITHUB_OK"
STATUS_OK_ROWS = "OK_ROWS"
STATUS_OK_EMPTY = "OK_EMPTY"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_TRANSPORT_ERROR = "TRANSPORT_ERROR"
STATUS_INVALID_DOCUMENT = "INVALID_DOCUMENT"
STATUS_LOAD_FAILED = "LOAD_FAILED"

PUBLISH_MESSAGE = "live candidate v2: publish camera sidecar snapshot"

SESSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Identity / chronology keys already emitted by Slice 1/2/3A sidecar rows.
# Transport checks presence/types only. Does not reinterpret nomination semantics.
ROW_REQUIRED_KEYS = (
    "symbol",
    "session",
    "candidate_first_seen_ts",
    "eligible_from",
    "source",
    "setup",
    "group",
    "observation_intent",
    "observation_reference",
    "price_at_first_seen",
    "ema9_at_first_seen",
    "breakout_ref_at_first_seen",
    "source_action",
    "source_reason",
    "elite_buy_grade",
    "provenance",
    "candidate_is_buy",
    "alert_eligible",
)

IMMUTABLE_ON_V2_TRANSPORT = (
    "candidate_first_seen_ts",
    "eligible_from",
    "setup",
    "group",
    "observation_intent",
    "observation_reference",
    "price_at_first_seen",
    "ema9_at_first_seen",
    "breakout_ref_at_first_seen",
    "source_action",
    "source_reason",
    "nomination_source",
    "elite_buy_grade",
    "market_real",
    "market_permission",
    "provenance",
    "candidate_is_buy",
    "alert_eligible",
)


class V2TransportError(RuntimeError):
    """V2 GitHub sidecar transport/validation failure. Not an empty universe."""


def v2_github_publish_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Default OFF. Independent of the Slice 3A local-sidecar gate."""
    raw = str((env or os.environ).get(ENV_V2_GITHUB_PUBLISH, "") or "").strip().lower()
    if raw in ENV_V2_GITHUB_PUBLISH_TRUTHY:
        return True
    if raw in ENV_V2_GITHUB_PUBLISH_FALSY:
        return False
    return False


def assert_v2_github_path(path: str) -> str:
    """Refuse production Elite watchlist. Only the dedicated V2 sidecar path."""
    rel = str(path or "").replace("\\", "/").lstrip("./")
    if rel in {GITHUB_WATCHLIST_PATH, PRODUCTION_WATCHLIST_RELPATH}:
        raise V2TransportError("refusing production dynamic_watchlist.json")
    if rel.endswith("dynamic_watchlist.json") or rel.endswith("/dynamic_watchlist.json"):
        raise V2TransportError("refusing production dynamic_watchlist.json")
    if rel != GITHUB_V2_SIDECAR_PATH:
        raise V2TransportError(f"V2 GitHub path must be {GITHUB_V2_SIDECAR_PATH}")
    return rel


def _is_false_flag(value: object) -> bool:
    return value is False


def _parse_generated_at(value: object) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_v2_sidecar_document(doc: object) -> str | None:
    """Return None if valid. Otherwise a reason. Does not rewrite fields."""
    if not isinstance(doc, dict):
        return "sidecar is not a JSON object"
    if doc.get("schema") != SCHEMA_ID:
        return "invalid or missing schema"
    session = str(doc.get("session") or "").strip()
    if not SESSION_RE.match(session):
        return "missing or invalid session"
    if not _parse_generated_at(doc.get("generated_at")):
        return "missing or invalid generated_at"
    rows = doc.get("rows")
    if not isinstance(rows, list):
        return "rows is not a list"
    ledger = doc.get("freeze_ledger")
    if not isinstance(ledger, list):
        return "freeze_ledger is not a list"
    if not _is_false_flag(doc.get("candidate_is_buy")):
        return "candidate_is_buy must be false"
    if not _is_false_flag(doc.get("alert_eligible")):
        return "alert_eligible must be false"
    for i, rec in enumerate(ledger):
        err = _validate_freeze_entry(rec, i)
        if err:
            return err
    for i, rec in enumerate(rows):
        err = _validate_row(rec, i)
        if err:
            return err
    return None


def _validate_freeze_entry(rec: object, index: int) -> str | None:
    if not isinstance(rec, Mapping):
        return f"freeze_ledger[{index}] is not an object"
    session = str(rec.get("session") or "").strip()
    symbol = str(rec.get("symbol") or "").strip().upper()
    first = rec.get("candidate_first_seen_ts")
    if not SESSION_RE.match(session):
        return f"freeze_ledger[{index}] missing session"
    if not symbol:
        return f"freeze_ledger[{index}] missing symbol"
    if not has_legal_first_seen(first):
        return f"freeze_ledger[{index}] missing candidate_first_seen_ts"
    return None


def _validate_row(rec: object, index: int) -> str | None:
    if not isinstance(rec, Mapping):
        return f"rows[{index}] is not an object"
    missing = [k for k in ROW_REQUIRED_KEYS if k not in rec]
    if missing:
        return f"rows[{index}] missing {missing[0]}"
    symbol = str(rec.get("symbol") or "").strip().upper()
    session = str(rec.get("session") or "").strip()
    if not symbol:
        return f"rows[{index}] missing symbol"
    if not SESSION_RE.match(session):
        return f"rows[{index}] missing session"
    if not has_legal_first_seen(rec.get("candidate_first_seen_ts")):
        return f"rows[{index}] missing candidate_first_seen_ts"
    if not has_legal_first_seen(rec.get("eligible_from")):
        return f"rows[{index}] missing eligible_from"
    if not _is_false_flag(rec.get("candidate_is_buy")):
        return f"rows[{index}] candidate_is_buy must be false"
    if not _is_false_flag(rec.get("alert_eligible")):
        return f"rows[{index}] alert_eligible must be false"
    if not isinstance(rec.get("provenance"), list):
        return f"rows[{index}] provenance must be a list"
    return None


@dataclass(frozen=True)
class V2PublishResult:
    ok: bool
    skipped: bool = False
    status: str = ""
    path: str = GITHUB_V2_SIDECAR_PATH
    bytes_len: int = 0
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "skipped": self.skipped,
            "status": self.status,
            "path": self.path,
            "bytes": self.bytes_len,
            "error": self.error,
        }


@dataclass(frozen=True)
class V2FetchResult:
    ok: bool
    status: str
    document: dict[str, Any] | None = None
    raw_text: str = ""
    n_rows: int = 0
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "n_rows": self.n_rows,
            "error": self.error or None,
        }


def load_local_v2_sidecar_text(path: Path) -> tuple[str, dict[str, Any]]:
    """Read exact local bytes. Missing/corrupt is a failure, not empty universe."""
    src = Path(path)
    if not src.exists():
        raise V2TransportError("local sidecar missing")
    try:
        text = src.read_text(encoding="utf-8")
    except OSError as exc:
        raise V2TransportError(f"unreadable local sidecar: {exc}") from exc
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise V2TransportError(f"corrupted sidecar JSON: {exc}") from exc
    reason = validate_v2_sidecar_document(doc)
    if reason:
        raise V2TransportError(reason)
    return text, doc


def v2_github_contents_writer(path: str, text: str, message: str) -> str:
    """GitHub Contents PUT for the pinned V2 path. Same token env as watchlist fetch."""
    dest = assert_v2_github_path(path)
    tok = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not tok:
        return "LOCAL_ONLY"
    own = (os.environ.get("GITHUB_REPO_OWNER") or DEFAULT_OWNER).strip()
    rpo = (os.environ.get("GITHUB_REPO_NAME") or DEFAULT_REPO).strip()
    url = f"{GITHUB_API}/repos/{own}/{rpo}/contents/{dest}"
    headers = {
        "User-Agent": "mrbot-live-candidate-v2-sidecar/1.0",
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {tok}",
    }
    sha = None
    req_get = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req_get, timeout=20) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
            if isinstance(meta, dict):
                sha = meta.get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            return f"GITHUB_FAIL_{exc.code}"
    except Exception:
        return "GITHUB_ERROR"
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
    }
    if sha:
        payload["sha"] = sha
    body = json.dumps(payload).encode("utf-8")
    req_put = urllib.request.Request(
        url,
        data=body,
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req_put, timeout=20) as resp:
            if getattr(resp, "status", 200) in (200, 201):
                return "GITHUB_OK"
            return f"GITHUB_FAIL_{getattr(resp, 'status', 'unknown')}"
    except urllib.error.HTTPError as exc:
        return f"GITHUB_FAIL_{exc.code}"
    except Exception:
        return "GITHUB_ERROR"


def publish_v2_sidecar_text(
    text: str,
    *,
    writer: Writer | None = None,
    env: Mapping[str, str] | None = None,
) -> V2PublishResult:
    """Publish exact sidecar bytes to the V2 GitHub path. Does not rebuild rows."""
    nbytes = len(text.encode("utf-8"))
    if not v2_github_publish_enabled(env):
        return V2PublishResult(
            ok=True,
            skipped=True,
            status=STATUS_GATE_OFF,
            bytes_len=nbytes,
        )
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return V2PublishResult(
            ok=False,
            status=STATUS_INVALID_DOCUMENT,
            bytes_len=nbytes,
            error=f"corrupted sidecar JSON: {exc}",
        )
    reason = validate_v2_sidecar_document(doc)
    if reason:
        return V2PublishResult(
            ok=False,
            status=STATUS_INVALID_DOCUMENT,
            bytes_len=nbytes,
            error=reason,
        )
    dest = GITHUB_V2_SIDECAR_PATH
    assert_v2_github_path(dest)
    put = writer if writer is not None else v2_github_contents_writer
    bus = publish_watchlist_bytes(text, put, path=dest, message=PUBLISH_MESSAGE)
    if bus.path != dest:
        return V2PublishResult(
            ok=False,
            status=STATUS_TRANSPORT_ERROR,
            path=str(bus.path),
            bytes_len=nbytes,
            error="writer retargeted production watchlist path",
        )
    if bus.ok:
        return V2PublishResult(
            ok=True,
            skipped=False,
            status=STATUS_PUBLISHED,
            path=dest,
            bytes_len=nbytes,
        )
    return V2PublishResult(
        ok=False,
        status=STATUS_TRANSPORT_ERROR,
        path=dest,
        bytes_len=nbytes,
        error=bus.detail or bus.status,
    )


def publish_v2_sidecar_file(
    path: Path | str,
    *,
    writer: Writer | None = None,
    env: Mapping[str, str] | None = None,
) -> V2PublishResult:
    """Publish a successfully loaded valid local sidecar. Never invents rows."""
    if not v2_github_publish_enabled(env):
        return V2PublishResult(ok=True, skipped=True, status=STATUS_GATE_OFF)
    try:
        text, _doc = load_local_v2_sidecar_text(Path(path))
    except V2TransportError as exc:
        return V2PublishResult(
            ok=False,
            skipped=False,
            status=STATUS_LOAD_FAILED,
            error=str(exc),
        )
    return publish_v2_sidecar_text(text, writer=writer, env=env)


def maybe_publish_v2_sidecar(
    *,
    local_ok: bool,
    local_skipped: bool,
    path: Path | str | None,
    writer: Writer | None = None,
    env: Mapping[str, str] | None = None,
) -> V2PublishResult:
    """Follow-on to Slice 3A. Publish only after a successful local write this cycle."""
    if not v2_github_publish_enabled(env):
        return V2PublishResult(ok=True, skipped=True, status=STATUS_GATE_OFF)
    if local_skipped or not local_ok or not path:
        return V2PublishResult(
            ok=True,
            skipped=True,
            status=STATUS_NOT_ELIGIBLE,
            error="no successful local V2 sidecar this cycle",
        )
    return publish_v2_sidecar_file(path, writer=writer, env=env)


def _fetch_status_from_transport_error(exc: BaseException) -> str:
    text = str(exc)
    if "HTTP 404" in text or text.endswith(" 404"):
        return STATUS_NOT_FOUND
    return STATUS_TRANSPORT_ERROR


def fetch_v2_sidecar(
    *,
    token: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    opener: Any = None,
    text_fetcher: Callable[..., str] | None = None,
) -> V2FetchResult:
    """Fetch + validate the V2 sidecar. Never treats 404/corrupt as empty universe."""
    dest = assert_v2_github_path(GITHUB_V2_SIDECAR_PATH)
    getter = text_fetcher or fetch_github_watchlist_text
    try:
        text = getter(
            token=token,
            owner=owner,
            repo=repo,
            path=dest,
            opener=opener,
        )
    except WatchlistTransportError as exc:
        status = _fetch_status_from_transport_error(exc)
        return V2FetchResult(ok=False, status=status, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — never invent Candidate state
        return V2FetchResult(ok=False, status=STATUS_TRANSPORT_ERROR, error=str(exc))
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return V2FetchResult(
            ok=False,
            status=STATUS_INVALID_DOCUMENT,
            raw_text=text,
            error=f"corrupted sidecar JSON: {exc}",
        )
    reason = validate_v2_sidecar_document(doc)
    if reason:
        return V2FetchResult(
            ok=False,
            status=STATUS_INVALID_DOCUMENT,
            raw_text=text,
            error=reason,
        )
    rows = doc["rows"]
    status = STATUS_OK_EMPTY if not rows else STATUS_OK_ROWS
    return V2FetchResult(
        ok=True,
        status=status,
        document=doc,
        raw_text=text,
        n_rows=len(rows),
    )
