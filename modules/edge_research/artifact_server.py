"""
Minimal HTTPS-ready WSGI artifact server for Edge Research durable bundles (P1b).

Serves only:
  GET  /current/bundle.tar.gz
  PUT  /current/bundle.tar.gz

Storage is isolated under a dedicated root (default /var/lib/mrbot/edge_research_durable).
No Camera/intraday_memory coupling. No arbitrary filesystem access.

Run locally:
  EDGE_RESEARCH_ARTIFACT_TOKEN=<secret> \\
  EDGE_RESEARCH_ARTIFACT_STORAGE=/tmp/edge_durable \\
  python -m modules.edge_research.artifact_server
"""

from __future__ import annotations

import hashlib
import hmac
import io
import os
import shutil
import tarfile
import threading
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple
from uuid import uuid4
from wsgiref.simple_server import WSGIServer, make_server

from modules.edge_research.bundle import (
    ARTIFACTS_DIRNAME,
    MANIFEST_FILENAME,
    BundleValidationError,
    validate_bundle_dir,
)

DEFAULT_STORAGE_ROOT = Path("/var/lib/mrbot/edge_research_durable")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
BUNDLE_OBJECT_NAME = "bundle.tar.gz"
PRODUCTION_OBS_OBJECT_NAME = "production_observations.tar.gz"
ALLOWED_METHODS = {"GET", "PUT"}
ALLOWED_PATH = "/current/bundle.tar.gz"
ALLOWED_PRODUCTION_OBS_PATH = "/current/production_observations.tar.gz"


@dataclass(frozen=True)
class ArtifactServerConfig:
    storage_root: Path
    token: str
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES

    @classmethod
    def from_env(cls) -> "ArtifactServerConfig":
        storage = os.environ.get("EDGE_RESEARCH_ARTIFACT_STORAGE", str(DEFAULT_STORAGE_ROOT))
        token = os.environ.get("EDGE_RESEARCH_ARTIFACT_TOKEN", "").strip()
        if not token:
            raise ValueError("EDGE_RESEARCH_ARTIFACT_TOKEN is required")
        host = os.environ.get("EDGE_RESEARCH_ARTIFACT_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
        port = int(os.environ.get("EDGE_RESEARCH_ARTIFACT_PORT", str(DEFAULT_PORT)))
        max_upload = int(
            os.environ.get("EDGE_RESEARCH_ARTIFACT_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES))
        )
        return cls(
            storage_root=Path(storage),
            token=token,
            host=host,
            port=port,
            max_upload_bytes=max_upload,
        )


def _json_response(start_response: Callable, status: int, payload: dict) -> List[bytes]:
    import json

    body = json.dumps(payload).encode("utf-8")
    headers = [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))),
    ]
    start_response(f"{status} {HTTPStatus(status).phrase}", headers)
    return [body]


def _bytes_response(start_response: Callable, status: int, body: bytes, content_type: str) -> List[bytes]:
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
    ]
    start_response(f"{status} {HTTPStatus(status).phrase}", headers)
    return [body]


def _authorize(environ: dict, token: str) -> bool:
    header = environ.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return False
    provided = header[7:].strip()
    if not provided:
        return False
    return hmac.compare_digest(provided, token)


def _safe_tar_members(members: Iterable[tarfile.TarInfo]) -> bool:
    allowed_prefixes = (f"{MANIFEST_FILENAME}", f"{ARTIFACTS_DIRNAME}/")
    for member in members:
        name = member.name.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            return False
        if not (name == MANIFEST_FILENAME or name.startswith(f"{ARTIFACTS_DIRNAME}/")):
            return False
    return True


def _extract_and_validate_bundle(tar_bytes: bytes, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
            members = tar.getmembers()
            if not _safe_tar_members(members):
                raise BundleValidationError("tar archive contains disallowed paths")
            for member in members:
                member.name = member.name.replace("\\", "/")
            if hasattr(tarfile, "data_filter"):
                tar.extractall(extract_dir, members=members, filter="data")
            else:
                tar.extractall(extract_dir, members=members)
    except BundleValidationError:
        raise
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise BundleValidationError(f"invalid tar archive: {exc}") from exc
    validation = validate_bundle_dir(extract_dir)
    if not validation.ok:
        raise BundleValidationError("; ".join(validation.errors))


def publish_bundle_bytes(config: ArtifactServerConfig, tar_bytes: bytes) -> None:
    """Atomic durable publish with rollback to previous bundle."""
    if len(tar_bytes) > config.max_upload_bytes:
        raise BundleValidationError("upload exceeds max size")
    if len(tar_bytes) == 0:
        raise BundleValidationError("empty upload")

    root = config.storage_root
    current_dir = root / "current"
    previous_dir = root / "previous"
    staging_root = root / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    current_dir.mkdir(parents=True, exist_ok=True)

    stage_id = uuid4().hex[:12]
    stage_dir = staging_root / stage_id
    stage_bundle = stage_dir / BUNDLE_OBJECT_NAME
    stage_extract = stage_dir / "extracted"

    try:
        stage_dir.mkdir(parents=True, exist_ok=False)
        stage_bundle.write_bytes(tar_bytes)
        _extract_and_validate_bundle(tar_bytes, stage_extract)

        promoted_previous = False
        if (current_dir / BUNDLE_OBJECT_NAME).exists():
            if previous_dir.exists():
                shutil.rmtree(previous_dir)
            current_dir.rename(previous_dir)
            promoted_previous = True
            current_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(stage_bundle, current_dir / BUNDLE_OBJECT_NAME)
    except Exception:
        if not (current_dir / BUNDLE_OBJECT_NAME).exists() and previous_dir.exists():
            if current_dir.exists():
                shutil.rmtree(current_dir, ignore_errors=True)
            previous_dir.rename(current_dir)
        raise
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
        if previous_dir.exists() and (current_dir / BUNDLE_OBJECT_NAME).exists():
            shutil.rmtree(previous_dir, ignore_errors=True)


def load_bundle_bytes(config: ArtifactServerConfig) -> bytes:
    path = config.storage_root / "current" / BUNDLE_OBJECT_NAME
    if not path.exists():
        raise FileNotFoundError("no bundle published")
    return path.read_bytes()


def publish_production_observations_bytes(config: ArtifactServerConfig, tar_bytes: bytes) -> None:
    """Atomic sidecar publish for autonomous production_observations (no Challenger validation)."""
    if len(tar_bytes) > config.max_upload_bytes:
        raise BundleValidationError("upload exceeds max size")
    if len(tar_bytes) == 0:
        raise BundleValidationError("empty upload")
    # Light path safety check only.
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = member.name.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise BundleValidationError("tar archive contains disallowed paths")
            if not (
                name == "production_observations"
                or name.startswith("production_observations/")
            ):
                raise BundleValidationError(f"unexpected member: {name}")

    current_dir = config.storage_root / "current"
    current_dir.mkdir(parents=True, exist_ok=True)
    tmp = current_dir / f".{PRODUCTION_OBS_OBJECT_NAME}.tmp"
    final = current_dir / PRODUCTION_OBS_OBJECT_NAME
    tmp.write_bytes(tar_bytes)
    os.replace(tmp, final)


def load_production_observations_bytes(config: ArtifactServerConfig) -> bytes:
    path = config.storage_root / "current" / PRODUCTION_OBS_OBJECT_NAME
    if not path.exists():
        raise FileNotFoundError("no production_observations sidecar published")
    return path.read_bytes()


def create_wsgi_app(config: ArtifactServerConfig):
    def app(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "") or ""

        if path == "/health" and method == "GET":
            return _json_response(start_response, 200, {"ok": True, "service": "edge_research_artifacts"})

        if path == ALLOWED_PRODUCTION_OBS_PATH and method in ALLOWED_METHODS:
            if not _authorize(environ, config.token):
                return _json_response(start_response, 401, {"error": "unauthorized"})
            if method == "GET":
                try:
                    body = load_production_observations_bytes(config)
                except FileNotFoundError:
                    return _json_response(start_response, 404, {"error": "production_observations_not_found"})
                return _bytes_response(start_response, 200, body, "application/gzip")
            try:
                length = int(environ.get("CONTENT_LENGTH") or "0")
            except ValueError:
                return _json_response(start_response, 400, {"error": "invalid_content_length"})
            if length <= 0:
                return _json_response(start_response, 400, {"error": "empty_body"})
            if length > config.max_upload_bytes:
                return _json_response(start_response, 413, {"error": "payload_too_large"})
            body = environ["wsgi.input"].read(length)
            if len(body) != length:
                return _json_response(start_response, 400, {"error": "incomplete_body"})
            try:
                publish_production_observations_bytes(config, body)
            except BundleValidationError as exc:
                return _json_response(start_response, 400, {"error": "invalid_sidecar", "detail": str(exc)})
            except Exception:
                return _json_response(start_response, 500, {"error": "publish_failed"})
            digest = hashlib.sha256(body).hexdigest()
            return _json_response(start_response, 200, {"ok": True, "sha256": digest, "kind": "production_observations"})

        if path != ALLOWED_PATH or method not in ALLOWED_METHODS:
            return _json_response(start_response, 404, {"error": "not_found"})

        if not _authorize(environ, config.token):
            return _json_response(start_response, 401, {"error": "unauthorized"})

        if method == "GET":
            try:
                body = load_bundle_bytes(config)
            except FileNotFoundError:
                return _json_response(start_response, 404, {"error": "bundle_not_found"})
            return _bytes_response(start_response, 200, body, "application/gzip")

        # PUT
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            return _json_response(start_response, 400, {"error": "invalid_content_length"})
        if length <= 0:
            return _json_response(start_response, 400, {"error": "empty_body"})
        if length > config.max_upload_bytes:
            return _json_response(start_response, 413, {"error": "payload_too_large"})

        body = environ["wsgi.input"].read(length)
        if len(body) != length:
            return _json_response(start_response, 400, {"error": "incomplete_body"})
        try:
            publish_bundle_bytes(config, body)
        except BundleValidationError as exc:
            return _json_response(start_response, 400, {"error": "invalid_bundle", "detail": str(exc)})
        except Exception:
            return _json_response(start_response, 500, {"error": "publish_failed"})
        digest = hashlib.sha256(body).hexdigest()
        return _json_response(start_response, 200, {"ok": True, "sha256": digest})

    return app


class ArtifactServer:
    """Thread-friendly WSGI server wrapper for tests and systemd ExecStart."""

    def __init__(self, config: ArtifactServerConfig) -> None:
        self.config = config
        self._httpd: Optional[WSGIServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    def start(self, blocking: bool = False) -> None:
        app = create_wsgi_app(self.config)
        self._httpd = make_server(self.config.host, self.config.port, app)
        if blocking:
            self._httpd.serve_forever()
        else:
            self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def main() -> None:
    config = ArtifactServerConfig.from_env()
    config.storage_root.mkdir(parents=True, exist_ok=True)
    server = ArtifactServer(config)
    print(f"Edge Research artifact server listening on {config.host}:{config.port}")
    server.start(blocking=True)


if __name__ == "__main__":
    main()
