"""
Durable backend abstraction for Edge Research bundles (P1).

Streamlit Cloud cannot mount VPS filesystem paths directly. Backends:
- local: directory on accessible filesystem (dev, VPS-hosted Streamlit, synced mount)
- http:  remote artifact service (operator must deploy; env-configured URL + token)
- none/disabled: no durable persistence (legacy behavior)

No secrets in source. Camera/intraday_memory untouched.
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from modules.edge_research.bundle import (
    MANIFEST_FILENAME,
    BundleValidationError,
    validate_bundle_dir,
    write_bundle_to_dir,
)

try:
    import streamlit as st
except Exception:  # pragma: no cover - allow tests/import outside Streamlit
    st = None  # type: ignore[assignment]


def _secret_or_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Resolve config from Streamlit secrets first, then environment (earning_learning pattern)."""
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


class DurableBackendError(RuntimeError):
    """Durable persistence operation failed."""


class DurableBackendNotConfigured(DurableBackendError):
    """Backend type requested but required env configuration missing."""


@dataclass
class DurablePublishResult:
    ok: bool
    backend: str
    message: str
    manifest: Optional[Dict[str, Any]] = None


@dataclass
class DurableLoadResult:
    ok: bool
    backend: str
    message: str
    bundle_dir: Optional[Path] = None
    manifest: Optional[Dict[str, Any]] = None


class DurableBackend(ABC):
    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def load_bundle(self, staging_dir: Path) -> DurableLoadResult:
        ...

    @abstractmethod
    def publish_bundle(self, bundle_dir: Path) -> DurablePublishResult:
        ...


class DisabledDurableBackend(DurableBackend):
    name = "none"

    def is_configured(self) -> bool:
        return False

    def load_bundle(self, staging_dir: Path) -> DurableLoadResult:
        return DurableLoadResult(False, self.name, "durable backend disabled")

    def publish_bundle(self, bundle_dir: Path) -> DurablePublishResult:
        return DurablePublishResult(False, self.name, "durable backend disabled")


class LocalDirectoryDurableBackend(DurableBackend):
    """
    Stores bundle under {root}/current/ with atomic staging publish.

    Reachable when root is on the same machine or a mounted volume visible
    to the Streamlit process. NOT automatically reachable from Streamlit Cloud
    unless operator mounts/syncs external storage into the container.
    """

    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.current_dir = self.root / "current"
        self.staging_root = self.root / "staging"

    def is_configured(self) -> bool:
        return bool(str(self.root))

    def load_bundle(self, staging_dir: Path) -> DurableLoadResult:
        if not self.current_dir.exists():
            return DurableLoadResult(False, self.name, "no durable bundle published yet")
        validation = validate_bundle_dir(self.current_dir)
        if not validation.ok:
            return DurableLoadResult(
                False,
                self.name,
                f"durable bundle invalid: {'; '.join(validation.errors)}",
            )
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        shutil.copytree(self.current_dir, staging_dir)
        return DurableLoadResult(
            True,
            self.name,
            "loaded durable bundle",
            bundle_dir=staging_dir,
            manifest=validation.manifest,
        )

    def publish_bundle(self, bundle_dir: Path) -> DurablePublishResult:
        validation = validate_bundle_dir(bundle_dir)
        if not validation.ok:
            return DurablePublishResult(
                False,
                self.name,
                f"refusing to publish invalid bundle: {'; '.join(validation.errors)}",
            )

        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.root.mkdir(parents=True, exist_ok=True)
        stage_name = f"publish_{uuid4().hex[:12]}"
        stage_target = self.staging_root / stage_name

        try:
            if stage_target.exists():
                shutil.rmtree(stage_target)
            shutil.copytree(bundle_dir, stage_target)
            reval = validate_bundle_dir(stage_target)
            if not reval.ok:
                raise BundleValidationError("; ".join(reval.errors))

            previous = self.current_dir.with_name("previous")
            if self.current_dir.exists():
                if previous.exists():
                    shutil.rmtree(previous)
                self.current_dir.rename(previous)
            stage_target.rename(self.current_dir)
            if previous.exists():
                shutil.rmtree(previous, ignore_errors=True)
        except Exception as exc:
            if stage_target.exists():
                shutil.rmtree(stage_target, ignore_errors=True)
            if not self.current_dir.exists() and (self.root / "previous").exists():
                (self.root / "previous").rename(self.current_dir)
            return DurablePublishResult(False, self.name, f"publish failed: {exc}")

        return DurablePublishResult(
            True,
            self.name,
            "published durable bundle",
            manifest=validation.manifest,
        )


class HttpArtifactDurableBackend(DurableBackend):
    """
    HTTP GET/PUT artifact service for cross-host durability (e.g. VPS service
    reachable from Streamlit Cloud).

    Requires operator deployment:
      EDGE_RESEARCH_DURABLE_URL=https://vps.example/edge-research-artifacts
      EDGE_RESEARCH_DURABLE_TOKEN=<secret in Streamlit secrets only>

    Expected API (operator implements):
      GET  {url}/bundle.tar.gz  or GET {url}/manifest.json + artifact files
    Minimal stub: GET/PUT {url}/bundle.json body = tar bytes or manifest index

    This implementation uses a simple tarball upload/download contract:
      GET  {url}/current/bundle.tar.gz
      PUT  {url}/current/bundle.tar.gz  (Authorization: Bearer token)

    Operator must deploy the matching artifact server separately.
    """

    name = "http"

    def __init__(self, base_url: str, token: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token or ""

    def is_configured(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> Dict[str, str]:
        headers = {"User-Agent": "mrbot-edge-research/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def load_bundle(self, staging_dir: Path) -> DurableLoadResult:
        import tarfile
        import io

        url = f"{self.base_url}/current/bundle.tar.gz"
        try:
            req = urllib.request.Request(url, headers=self._headers(), method="GET")
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return DurableLoadResult(False, self.name, "no remote bundle (404)")
            return DurableLoadResult(False, self.name, f"HTTP load failed: {exc.code}")
        except Exception as exc:
            return DurableLoadResult(False, self.name, f"HTTP load failed: {exc}")

        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(staging_dir, filter="data")
            else:
                members = tar.getmembers()
                for member in members:
                    if member.name.startswith("/") or ".." in member.name.split("/"):
                        shutil.rmtree(staging_dir, ignore_errors=True)
                        return DurableLoadResult(
                            False,
                            self.name,
                            "remote bundle contains disallowed paths",
                        )
                tar.extractall(staging_dir, members=members)
        validation = validate_bundle_dir(staging_dir)
        if not validation.ok:
            shutil.rmtree(staging_dir, ignore_errors=True)
            return DurableLoadResult(
                False,
                self.name,
                f"remote bundle invalid: {'; '.join(validation.errors)}",
            )
        return DurableLoadResult(
            True,
            self.name,
            "loaded remote bundle",
            bundle_dir=staging_dir,
            manifest=validation.manifest,
        )

    def publish_bundle(self, bundle_dir: Path) -> DurablePublishResult:
        import tarfile
        import io

        validation = validate_bundle_dir(bundle_dir)
        if not validation.ok:
            return DurablePublishResult(
                False,
                self.name,
                f"refusing to publish invalid bundle: {'; '.join(validation.errors)}",
            )

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(bundle_dir / MANIFEST_FILENAME, arcname=MANIFEST_FILENAME)
            artifacts = bundle_dir / "artifacts"
            for path in sorted(artifacts.iterdir()):
                tar.add(path, arcname=f"artifacts/{path.name}")
        buf.seek(0)

        url = f"{self.base_url}/current/bundle.tar.gz"
        try:
            req = urllib.request.Request(
                url,
                data=buf.read(),
                headers={**self._headers(), "Content-Type": "application/gzip"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=120):
                pass
        except Exception as exc:
            return DurablePublishResult(False, self.name, f"HTTP publish failed: {exc}")

        return DurablePublishResult(
            True,
            self.name,
            "published remote bundle",
            manifest=validation.manifest,
        )


def resolve_durable_backend() -> DurableBackend:
    """
    Environment-driven durable backend selection.

    EDGE_RESEARCH_DURABLE_BACKEND:
      - local (default when EDGE_RESEARCH_DURABLE_PATH set)
      - http
      - none / unset

    EDGE_RESEARCH_DURABLE_PATH: root directory for local backend
    EDGE_RESEARCH_DURABLE_URL: base URL for http backend
    EDGE_RESEARCH_DURABLE_TOKEN: bearer token (Streamlit secrets / env only)

    BACKEND, URL, and TOKEN resolve via Streamlit secrets when available, else os.environ.
    """
    backend_type = (_secret_or_env("EDGE_RESEARCH_DURABLE_BACKEND") or "").lower()
    durable_path = (os.environ.get("EDGE_RESEARCH_DURABLE_PATH") or "").strip()
    durable_url = _secret_or_env("EDGE_RESEARCH_DURABLE_URL") or ""
    durable_token = _secret_or_env("EDGE_RESEARCH_DURABLE_TOKEN") or ""

    if backend_type in ("none", "disabled", "off"):
        return DisabledDurableBackend()

    if backend_type == "http" or (not backend_type and durable_url):
        if not durable_url:
            raise DurableBackendNotConfigured(
                "EDGE_RESEARCH_DURABLE_BACKEND=http requires EDGE_RESEARCH_DURABLE_URL"
            )
        return HttpArtifactDurableBackend(durable_url, token=durable_token or None)

    if backend_type in ("local", "") and durable_path:
        return LocalDirectoryDurableBackend(Path(durable_path))

    if backend_type == "local" and not durable_path:
        raise DurableBackendNotConfigured(
            "EDGE_RESEARCH_DURABLE_BACKEND=local requires EDGE_RESEARCH_DURABLE_PATH"
        )

    return DisabledDurableBackend()


def stage_bundle_from_working_dir(working_dir: Path, staging_dir: Path) -> Dict[str, Any]:
    """Build validated bundle in staging directory."""
    return write_bundle_to_dir(working_dir, staging_dir)
