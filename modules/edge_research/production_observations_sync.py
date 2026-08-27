"""
Durable sync for autonomous production_observations (Streamlit Cloud read path).

Separate from Challenger discovery/challenger bundles. Fail-safe: never raises
into research pipeline. Does not mutate frozen evidence semantics.
"""

from __future__ import annotations

import io
import os
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from modules.edge_research.durable import _secret_or_env, resolve_durable_backend
from modules.edge_research.storage import resolve_data_dir, resolve_production_runs_root

PRODUCTION_OBS_OBJECT = "production_observations.tar.gz"
INCLUDE_RELATIVE_PREFIXES = (
    "daily_run_index.json",
    "daily_runs/",
    "daily_manifests/",
    "daily_voices/",
)


def _headers(token: str) -> Dict[str, str]:
    headers = {"User-Agent": "mrbot-edge-research-prodobs/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _should_include(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    for prefix in INCLUDE_RELATIVE_PREFIXES:
        if prefix.endswith("/"):
            if rel.startswith(prefix):
                return True
        elif rel == prefix:
            return True
    return False


def pack_production_observations(prod_root: Path) -> Optional[bytes]:
    if not prod_root.exists():
        return None
    buf = io.BytesIO()
    added = 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(prod_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(prod_root).as_posix()
            if not _should_include(rel):
                continue
            tar.add(path, arcname=f"production_observations/{rel}")
            added += 1
    if added == 0:
        return None
    return buf.getvalue()


def unpack_production_observations(blob: bytes, edge_root: Path) -> Path:
    dest = resolve_production_runs_root(edge_root)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        members = []
        for member in tar.getmembers():
            name = member.name.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError("disallowed path in production_observations bundle")
            if not (
                name == "production_observations"
                or name.startswith("production_observations/")
            ):
                raise ValueError(f"unexpected member: {name}")
            members.append(member)
        staging = Path(tempfile.mkdtemp(prefix="prodobs_"))
        try:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(staging, members=members, filter="data")
            else:
                tar.extractall(staging, members=members)
            src = staging / "production_observations"
            if not src.exists():
                raise ValueError("bundle missing production_observations/")
            # Overlay into canonical root (non-destructive for unknown files).
            for path in src.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(src)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return dest


def publish_production_observations_durable(
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Publish production_observations sidecar. Fail-safe dict result."""
    try:
        edge_root = resolve_data_dir(data_dir)
        prod_root = resolve_production_runs_root(edge_root)
        blob = pack_production_observations(prod_root)
        if not blob:
            return {"ok": False, "skipped": True, "reason": "nothing_to_publish"}

        backend = resolve_durable_backend()
        if backend.name == "none":
            return {"ok": False, "skipped": True, "reason": "durable_backend_disabled"}

        if backend.name == "local":
            storage = Path(os.environ.get("EDGE_RESEARCH_DURABLE_PATH") or "")
            if not storage:
                return {"ok": False, "skipped": True, "reason": "local_path_missing"}
            current = storage / "current"
            current.mkdir(parents=True, exist_ok=True)
            (current / PRODUCTION_OBS_OBJECT).write_bytes(blob)
            return {"ok": True, "backend": "local", "bytes": len(blob)}

        if backend.name == "http":
            base = (os.environ.get("EDGE_RESEARCH_DURABLE_URL") or "").strip().rstrip("/")
            # Prefer Streamlit secrets when available.
            base = (_secret_or_env("EDGE_RESEARCH_DURABLE_URL") or base).rstrip("/")
            token = _secret_or_env("EDGE_RESEARCH_DURABLE_TOKEN") or ""
            if not base:
                return {"ok": False, "skipped": True, "reason": "http_url_missing"}
            url = f"{base}/current/{PRODUCTION_OBS_OBJECT}"
            req = urllib.request.Request(
                url,
                data=blob,
                headers={**_headers(token), "Content-Type": "application/gzip"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                _ = resp.read()
            return {"ok": True, "backend": "http", "bytes": len(blob), "url": url}

        return {"ok": False, "skipped": True, "reason": f"unsupported_backend:{backend.name}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def try_restore_production_observations_durable(
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Restore production_observations sidecar into working edge data dir."""
    try:
        edge_root = resolve_data_dir(data_dir)
        backend = resolve_durable_backend()
        if backend.name == "none":
            return {"ok": False, "skipped": True, "reason": "durable_backend_disabled"}

        blob: Optional[bytes] = None
        if backend.name == "local":
            storage = Path(os.environ.get("EDGE_RESEARCH_DURABLE_PATH") or "")
            path = storage / "current" / PRODUCTION_OBS_OBJECT
            if not path.exists():
                return {"ok": False, "skipped": True, "reason": "local_sidecar_missing"}
            blob = path.read_bytes()
        elif backend.name == "http":
            base = (_secret_or_env("EDGE_RESEARCH_DURABLE_URL") or "").rstrip("/")
            token = _secret_or_env("EDGE_RESEARCH_DURABLE_TOKEN") or ""
            if not base:
                return {"ok": False, "skipped": True, "reason": "http_url_missing"}
            url = f"{base}/current/{PRODUCTION_OBS_OBJECT}"
            req = urllib.request.Request(url, headers=_headers(token), method="GET")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    blob = resp.read()
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return {"ok": False, "skipped": True, "reason": "remote_sidecar_404"}
                return {"ok": False, "error": f"HTTP:{exc.code}"}
        else:
            return {"ok": False, "skipped": True, "reason": f"unsupported_backend:{backend.name}"}

        if not blob:
            return {"ok": False, "skipped": True, "reason": "empty_blob"}
        dest = unpack_production_observations(blob, edge_root)
        return {"ok": True, "path": str(dest), "bytes": len(blob)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
