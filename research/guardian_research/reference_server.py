"""Loopback GET for one reference file. No other route and no upload."""

from __future__ import annotations

import hmac
import json
import os
from http import HTTPStatus
from pathlib import Path
from wsgiref.simple_server import make_server

from research.guardian_research.reference_export import PUBLISHED_PATH

ARCHIVE_ROOT = Path("/var/lib/mrbot/intraday_memory")
DEFAULT_ROOT = Path("/var/lib/mrbot/guardian_reference")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766


class ReferenceServerError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def create_app(root: Path, token: str):
    store_root = Path(root)

    def app(environ, start_response):
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = environ.get("PATH_INFO", "") or ""
        if path == "/health" and method == "GET":
            return _json(start_response, 200, {"ok": True, "service": "guardian_reference"})
        if path != PUBLISHED_PATH:
            return _json(start_response, 404, {"error": "not_found"})
        if method != "GET":
            return _json(start_response, 405, {"error": "method_not_allowed"})
        if not _authorized(environ, token):
            return _json(start_response, 401, {"error": "unauthorized"})
        body = _read_store(store_root)
        if body is None:
            return _json(start_response, 404, {"error": "guardian_reference_not_found"})
        start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
        return [body]

    return app


def serve(root: Path, token: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    _require_loopback(host)
    _require_isolated_root(root)
    if not str(token or "").strip():
        raise ReferenceServerError("TOKEN_ABSENT")
    httpd = make_server(host, port, create_app(root, token))
    return httpd


def _read_store(root: Path) -> bytes | None:
    try:
        resolved_root = Path(root).resolve()
        resolved = (resolved_root / "reference_store.json").resolve()
    except OSError:
        return None
    if resolved != resolved_root and resolved_root not in resolved.parents:
        return None
    if resolved.name != "reference_store.json" or not resolved.is_file():
        return None
    return resolved.read_bytes()


def _authorized(environ: dict, token: str) -> bool:
    header = str(environ.get("HTTP_AUTHORIZATION", ""))
    if not header.startswith("Bearer "):
        return False
    provided = header[7:].strip()
    if not provided:
        return False
    return hmac.compare_digest(provided, token)


def _require_loopback(host: str) -> None:
    if host != DEFAULT_HOST:
        raise ReferenceServerError("NON_LOOPBACK_BIND")


def _require_isolated_root(root: Path) -> None:
    try:
        resolved = Path(root).resolve()
        archive = ARCHIVE_ROOT.resolve()
    except OSError as exc:
        raise ReferenceServerError("ROOT_UNRESOLVED") from exc
    if resolved == archive or archive in resolved.parents or resolved in archive.parents:
        raise ReferenceServerError("ROOT_OVERLAPS_ARCHIVE")


def _json(start_response, status: int, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    start_response(
        f"{status} {HTTPStatus(status).phrase}",
        [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
    )
    return [body]


def main() -> int:
    root = Path(os.environ.get("GUARDIAN_REFERENCE_ROOT", str(DEFAULT_ROOT)))
    token = os.environ.get("EDGE_RESEARCH_ARTIFACT_TOKEN", "").strip()
    host = os.environ.get("GUARDIAN_REFERENCE_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    port = int(os.environ.get("GUARDIAN_REFERENCE_PORT", str(DEFAULT_PORT)))
    try:
        httpd = serve(root, token, host, port)
    except ReferenceServerError as exc:
        print(json.dumps({"status": "refused", "reason": exc.reason}))
        return 1
    print(json.dumps({"status": "listening", "host": host, "port": port}))
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
