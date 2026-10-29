"""Fetch the three research-ledger files over HTTPS and validate them.

The token is sent only as an Authorization header. It is not written into
URLs, error text, or the returned board. Redirects are not followed.
"""

from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlsplit

from research.v2_research_ledger.delivery_view import (
    BOARD_NAME,
    CLOCK_NAME,
    DELIVERY_UNAVAILABLE,
    MANIFEST_NAME,
    MAX_BOARD_BYTES,
    RESEARCH_BOARD_PATH,
    RESEARCH_CLOCK_PATH,
    RESEARCH_MANIFEST_PATH,
    DeliveryView,
    load_delivery,
)

TIMEOUT_SECONDS = 20
PATHS = {
    BOARD_NAME: RESEARCH_BOARD_PATH,
    CLOCK_NAME: RESEARCH_CLOCK_PATH,
    MANIFEST_NAME: RESEARCH_MANIFEST_PATH,
}


@dataclass(frozen=True)
class RemoteResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Opener = Callable[[str, Mapping[str, str], int], RemoteResponse]


def resolve_remote_config() -> tuple[str, str]:
    """Read the ledger URL and token from secrets or the environment."""
    return _setting("EDGE_RESEARCH_LEDGER_URL"), _setting("EDGE_RESEARCH_LEDGER_TOKEN")


def fetch_research_trio(
    base_url: str,
    token: str,
    *,
    opener: Opener | None = None,
    timeout: int = TIMEOUT_SECONDS,
) -> DeliveryView:
    """Download one consistent trio, or refuse it without a partial board."""
    if not str(token or "").strip():
        return DeliveryView(DELIVERY_UNAVAILABLE, "missing_secret")
    base = _base_url(base_url)
    if base is None:
        return DeliveryView(DELIVERY_UNAVAILABLE, "insecure_url")
    open_fn = opener or _urllib_open
    blobs: dict[str, bytes] = {}
    for name, rel_path in PATHS.items():
        url = base + rel_path
        if urlsplit(url).path != rel_path:
            return DeliveryView(DELIVERY_UNAVAILABLE, "insecure_url")
        try:
            response = open_fn(
                url,
                {"Authorization": f"Bearer {token}", "User-Agent": "mrbot-research-ledger/1.0"},
                timeout,
            )
        except TimeoutError:
            return DeliveryView(DELIVERY_UNAVAILABLE, "timeout")
        except Exception:
            return DeliveryView(DELIVERY_UNAVAILABLE, "transport")
        if response.status in {301, 302, 303, 307, 308}:
            return DeliveryView(DELIVERY_UNAVAILABLE, "redirect")
        if response.status == 401:
            return DeliveryView(DELIVERY_UNAVAILABLE, "unauthorized")
        if response.status == 403:
            return DeliveryView(DELIVERY_UNAVAILABLE, "forbidden")
        if response.status != 200:
            return DeliveryView(DELIVERY_UNAVAILABLE, "transport")
        accepted = _bounded(response, name)
        if isinstance(accepted, DeliveryView):
            return accepted
        blobs[name] = accepted
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, payload in blobs.items():
            (root / name).write_bytes(payload)
        return load_delivery(root)


def _base_url(value: str) -> str | None:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    if parsed.path not in {"", "/"}:
        return None
    return f"https://{parsed.netloc}"


def _bounded(response: RemoteResponse, name: str) -> bytes | DeliveryView:
    declared = response.headers.get("Content-Length") or response.headers.get("content-length")
    if declared not in (None, ""):
        try:
            size = int(str(declared))
        except ValueError:
            return DeliveryView(DELIVERY_UNAVAILABLE, "incomplete")
        if size > MAX_BOARD_BYTES:
            return DeliveryView(DELIVERY_UNAVAILABLE, "oversized")
        if len(response.body) != size:
            return DeliveryView(DELIVERY_UNAVAILABLE, "incomplete")
    if len(response.body) > MAX_BOARD_BYTES:
        return DeliveryView(DELIVERY_UNAVAILABLE, "oversized")
    if name == BOARD_NAME and not response.body.endswith(b"\n"):
        return DeliveryView(DELIVERY_UNAVAILABLE, "incomplete")
    return response.body


def _urllib_open(url: str, headers: Mapping[str, str], timeout: int) -> RemoteResponse:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length")
            if length not in (None, ""):
                size = int(length)
                if size > MAX_BOARD_BYTES:
                    return RemoteResponse(200, {"Content-Length": length}, b"")
                body = response.read(size)
            else:
                body = response.read(MAX_BOARD_BYTES + 1)
            header_map = {"Content-Length": length or ""}
            return RemoteResponse(getattr(response, "status", 200), header_map, body)
    except urllib.error.HTTPError as exc:
        return RemoteResponse(exc.code, {}, b"")
    except TimeoutError as exc:
        raise TimeoutError("timeout") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise TimeoutError("timeout") from exc
        raise


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def _setting(name: str) -> str:
    value = None
    try:
        import streamlit as st  # type: ignore

        value = st.secrets.get(name)
    except Exception:
        value = None
    if value in (None, ""):
        value = os.getenv(name)
    if value in (None, ""):
        return ""
    return str(value).strip()
