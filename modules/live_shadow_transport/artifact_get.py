"""Cloud GET of isolated live-shadow artifacts via the existing durable URL + bearer.

Read-only. Never PUT. Never Camera. Never Interpreter.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from modules.live_shadow_transport.contract import (
    ARTIFACT_EVIDENCE_PATH,
    ARTIFACT_STATUS_PATH,
    EVIDENCE_TRANSPORT_ERROR,
)

try:
    from modules.edge_research.durable import _secret_or_env
except Exception:  # pragma: no cover — tests without Streamlit still have the module
    def _secret_or_env(name: str, default: Optional[str] = None) -> Optional[str]:
        value = os.getenv(name, default)
        if value in (None, ""):
            return None
        return str(value).strip()


class EvidenceTransportError(RuntimeError):
    """Remote live-shadow GET failed. Do not invent P×V."""


def remote_artifact_configured() -> bool:
    return bool((_secret_or_env("EDGE_RESEARCH_DURABLE_URL") or "").strip())


def get_live_shadow_bytes(
    rel_path: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
    opener: Callable[..., Any] | None = None,
    timeout: int = 20,
) -> bytes:
    base = (base_url if base_url is not None else (_secret_or_env("EDGE_RESEARCH_DURABLE_URL") or "")).rstrip("/")
    tok = token if token is not None else (_secret_or_env("EDGE_RESEARCH_DURABLE_TOKEN") or "")
    if not base:
        raise EvidenceTransportError("EDGE_RESEARCH_DURABLE_URL missing")
    if rel_path not in {ARTIFACT_EVIDENCE_PATH, ARTIFACT_STATUS_PATH}:
        raise EvidenceTransportError("disallowed live-shadow path")
    url = f"{base}{rel_path}"
    headers = {"User-Agent": "mrbot-live-shadow-ui/1.0"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise EvidenceTransportError(f"artifact HTTP {exc.code}") from exc
    except Exception as exc:  # noqa: BLE001
        raise EvidenceTransportError(f"artifact GET failed: {exc}") from exc


def get_live_evidence_text(**kwargs: Any) -> str:
    raw = get_live_shadow_bytes(ARTIFACT_EVIDENCE_PATH, **kwargs)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceTransportError("live_evidence.jsonl is not utf-8") from exc


def get_live_status_text(**kwargs: Any) -> str:
    raw = get_live_shadow_bytes(ARTIFACT_STATUS_PATH, **kwargs)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceTransportError("live_shadow_status.json is not utf-8") from exc


def transport_error_payload(detail: str = "") -> dict[str, Any]:
    return {
        "error": EVIDENCE_TRANSPORT_ERROR,
        "detail": detail,
        "alert_eligible": False,
    }
