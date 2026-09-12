"""Cloud GET of isolated Rotation artifacts via the existing durable URL + bearer.

Read-only. Never PUT. Never Camera. Never KBS. Never Candidate live-shadow parse.
Does not import or call the Candidate live-shadow GET client.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from modules.rotation_watch.constants import (
    ARTIFACT_BOARD_PATH,
    ARTIFACT_STATUS_PATH,
    TRANSPORT_ERROR,
)

try:
    import streamlit as st
except Exception:  # pragma: no cover — tests / sidecar import without Streamlit
    st = None  # type: ignore[assignment]


def _secret_or_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value: Any = None
    if st is not None:
        try:
            value = st.secrets.get(name)
        except Exception:
            value = None
    if value in (None, ""):
        value = os.getenv(name, default)
    if value in (None, ""):
        return None
    return str(value).strip()


class RotationTransportError(RuntimeError):
    """Remote Rotation GET failed. Do not invent board rows."""


class RotationArtifactNotFound(Exception):
    """Expected missing Rotation object (HTTP 404). Not a synthetic board."""


def remote_rotation_configured() -> bool:
    return bool((_secret_or_env("EDGE_RESEARCH_DURABLE_URL") or "").strip())


def get_rotation_bytes(
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
        raise RotationTransportError("EDGE_RESEARCH_DURABLE_URL missing")
    if rel_path not in {ARTIFACT_BOARD_PATH, ARTIFACT_STATUS_PATH}:
        raise RotationTransportError("disallowed rotation path")
    url = f"{base}{rel_path}"
    headers = {"User-Agent": "mrbot-rotation-watch-ui/1.0"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RotationArtifactNotFound(rel_path) from exc
        raise RotationTransportError(f"artifact HTTP {exc.code}") from exc
    except RotationArtifactNotFound:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RotationTransportError(f"artifact GET failed: {exc}") from exc


def get_rotation_board_text(**kwargs: Any) -> str:
    raw = get_rotation_bytes(ARTIFACT_BOARD_PATH, **kwargs)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RotationTransportError("board.json is not utf-8") from exc


def get_rotation_status_text(**kwargs: Any) -> str:
    raw = get_rotation_bytes(ARTIFACT_STATUS_PATH, **kwargs)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RotationTransportError("status.json is not utf-8") from exc


def transport_error_payload(detail: str = "") -> dict[str, Any]:
    return {
        "error": TRANSPORT_ERROR,
        "detail": detail,
        "alert_eligible": False,
    }
