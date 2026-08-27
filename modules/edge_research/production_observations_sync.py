"""
Durable sync for autonomous production_observations (Streamlit Cloud read path).

VPS publish contract (authoritative on the research host):
  EDGE_RESEARCH_ARTIFACT_STORAGE / EDGE_RESEARCH_ARTIFACT_TOKEN(+HOST/PORT)
  — same contract as mrbot-edge-artifacts.service (/etc/mrbot/edge-artifacts.env).

Streamlit Cloud restore contract (consumer):
  EDGE_RESEARCH_DURABLE_URL + EDGE_RESEARCH_DURABLE_TOKEN
  — reverse-proxied base URL of the artifact service; object path is always
  /current/production_observations.tar.gz.

Fail-safe: never raises into the research pipeline. Does not mutate frozen
evidence semantics.
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
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.artifact_server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_STORAGE_ROOT,
    publish_production_observations_bytes,
    ArtifactServerConfig,
)
from modules.edge_research.durable import _secret_or_env, resolve_durable_backend
from modules.edge_research.storage import resolve_data_dir, resolve_production_runs_root

PRODUCTION_OBS_OBJECT = "production_observations.tar.gz"
ARTIFACT_ENV_FILE = Path("/etc/mrbot/edge-artifacts.env")
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


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Parse KEY=VALUE lines; ignores comments/blank lines. No shell expansion."""
    out: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            out[key] = value
    return out


def load_artifact_service_config() -> Dict[str, str]:
    """
    Resolve artifact-server settings for the VPS sidecar.

    Process environment wins; missing keys fall back to /etc/mrbot/edge-artifacts.env
    so the daily research oneshot can publish without duplicating DURABLE_* vars.
    """
    file_vals = _parse_env_file(ARTIFACT_ENV_FILE) if ARTIFACT_ENV_FILE.is_file() else {}
    keys = (
        "EDGE_RESEARCH_ARTIFACT_STORAGE",
        "EDGE_RESEARCH_ARTIFACT_TOKEN",
        "EDGE_RESEARCH_ARTIFACT_HOST",
        "EDGE_RESEARCH_ARTIFACT_PORT",
        "EDGE_RESEARCH_ARTIFACT_MAX_UPLOAD_BYTES",
    )
    resolved: Dict[str, str] = {}
    for key in keys:
        env_val = (os.environ.get(key) or "").strip()
        file_val = (file_vals.get(key) or "").strip()
        resolved[key] = env_val or file_val
    return resolved


def _artifact_storage_root(cfg: Dict[str, str]) -> Optional[Path]:
    raw = (cfg.get("EDGE_RESEARCH_ARTIFACT_STORAGE") or "").strip()
    if raw:
        return Path(raw)
    # Production default used by mrbot-edge-artifacts.service / install script.
    default = Path(DEFAULT_STORAGE_ROOT)
    if default.exists():
        return default
    return None


def _artifact_http_base(cfg: Dict[str, str]) -> Optional[str]:
    token = (cfg.get("EDGE_RESEARCH_ARTIFACT_TOKEN") or "").strip()
    if not token or token == "CHANGE_ME":
        return None
    host = (cfg.get("EDGE_RESEARCH_ARTIFACT_HOST") or DEFAULT_HOST).strip() or DEFAULT_HOST
    port_raw = (cfg.get("EDGE_RESEARCH_ARTIFACT_PORT") or str(DEFAULT_PORT)).strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = DEFAULT_PORT
    return f"http://{host}:{port}"


def resolve_production_observations_publish_backend() -> Tuple[str, Dict[str, Any]]:
    """
    Choose publish target for the autonomous sidecar.

    Returns (backend_name, params). backend_name == "none" means disabled.

    Priority (architecture, not symptom flag-flip):
      1. artifact_storage — write into the same root mrbot-edge-artifacts serves
      2. artifact_http    — PUT to the local artifact HTTP API
      3. durable local/http — legacy Challenger DURABLE_* client (Streamlit/dev)
    """
    cfg = load_artifact_service_config()
    storage = _artifact_storage_root(cfg)
    if storage is not None:
        return "artifact_storage", {"storage_root": storage, "cfg": cfg}

    http_base = _artifact_http_base(cfg)
    if http_base is not None:
        return "artifact_http", {
            "base_url": http_base,
            "token": cfg["EDGE_RESEARCH_ARTIFACT_TOKEN"],
        }

    backend = resolve_durable_backend()
    if backend.name == "none":
        return "none", {}
    if backend.name == "local":
        path = (os.environ.get("EDGE_RESEARCH_DURABLE_PATH") or "").strip()
        if not path:
            return "none", {}
        return "durable_local", {"storage_root": Path(path)}
    if backend.name == "http":
        base = (_secret_or_env("EDGE_RESEARCH_DURABLE_URL") or "").rstrip("/")
        token = _secret_or_env("EDGE_RESEARCH_DURABLE_TOKEN") or ""
        if not base:
            return "none", {}
        return "durable_http", {"base_url": base, "token": token}
    return "none", {}


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


def _put_http(url: str, token: str, blob: bytes) -> None:
    req = urllib.request.Request(
        url,
        data=blob,
        headers={**_headers(token), "Content-Type": "application/gzip"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        _ = resp.read()


def _get_http(url: str, token: str) -> bytes:
    req = urllib.request.Request(url, headers=_headers(token), method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


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

        backend, params = resolve_production_observations_publish_backend()
        if backend == "none":
            return {"ok": False, "skipped": True, "reason": "durable_backend_disabled"}

        if backend == "artifact_storage":
            storage_root: Path = params["storage_root"]
            max_upload = int(
                params["cfg"].get("EDGE_RESEARCH_ARTIFACT_MAX_UPLOAD_BYTES")
                or str(50 * 1024 * 1024)
            )
            # Token unused for local filesystem publish; reuse server helper for
            # identical layout/validation as mrbot-edge-artifacts.service.
            config = ArtifactServerConfig(
                storage_root=storage_root,
                token=(params["cfg"].get("EDGE_RESEARCH_ARTIFACT_TOKEN") or "local"),
                max_upload_bytes=max_upload,
            )
            publish_production_observations_bytes(config, blob)
            final = storage_root / "current" / PRODUCTION_OBS_OBJECT
            return {
                "ok": True,
                "backend": "artifact_storage",
                "bytes": len(blob),
                "path": str(final),
            }

        if backend in ("artifact_http", "durable_http"):
            base = str(params["base_url"]).rstrip("/")
            token = str(params.get("token") or "")
            url = f"{base}/current/{PRODUCTION_OBS_OBJECT}"
            _put_http(url, token, blob)
            return {"ok": True, "backend": backend, "bytes": len(blob), "url": url}

        if backend == "durable_local":
            storage_root = params["storage_root"]
            if not storage_root:
                return {"ok": False, "skipped": True, "reason": "local_path_missing"}
            current = storage_root / "current"
            current.mkdir(parents=True, exist_ok=True)
            (current / PRODUCTION_OBS_OBJECT).write_bytes(blob)
            return {"ok": True, "backend": "durable_local", "bytes": len(blob)}

        return {"ok": False, "skipped": True, "reason": f"unsupported_backend:{backend}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def try_restore_production_observations_durable(
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Restore production_observations sidecar into working edge data dir.

    Consumer priority:
      1. Streamlit DURABLE_* (Cloud / remote)
      2. Local artifact storage (VPS co-located Streamlit)
      3. Local artifact HTTP API
    """
    try:
        edge_root = resolve_data_dir(data_dir)
        blob: Optional[bytes] = None
        source = ""

        # 1) Explicit Streamlit / DURABLE client (preferred for Cloud).
        durable = resolve_durable_backend()
        if durable.name == "local":
            storage = Path(os.environ.get("EDGE_RESEARCH_DURABLE_PATH") or "")
            path = storage / "current" / PRODUCTION_OBS_OBJECT
            if path.exists():
                blob = path.read_bytes()
                source = "durable_local"
        elif durable.name == "http":
            base = (_secret_or_env("EDGE_RESEARCH_DURABLE_URL") or "").rstrip("/")
            token = _secret_or_env("EDGE_RESEARCH_DURABLE_TOKEN") or ""
            if base:
                url = f"{base}/current/{PRODUCTION_OBS_OBJECT}"
                try:
                    blob = _get_http(url, token)
                    source = "durable_http"
                except urllib.error.HTTPError as exc:
                    if exc.code == 404:
                        return {"ok": False, "skipped": True, "reason": "remote_sidecar_404"}
                    return {"ok": False, "error": f"HTTP:{exc.code}"}

        # 2/3) VPS artifact-server contract when DURABLE_* absent.
        if blob is None:
            cfg = load_artifact_service_config()
            storage = _artifact_storage_root(cfg)
            if storage is not None:
                path = storage / "current" / PRODUCTION_OBS_OBJECT
                if path.exists():
                    blob = path.read_bytes()
                    source = "artifact_storage"
            if blob is None:
                http_base = _artifact_http_base(cfg)
                if http_base is not None:
                    url = f"{http_base.rstrip('/')}/current/{PRODUCTION_OBS_OBJECT}"
                    try:
                        blob = _get_http(url, cfg["EDGE_RESEARCH_ARTIFACT_TOKEN"])
                        source = "artifact_http"
                    except urllib.error.HTTPError as exc:
                        if exc.code == 404:
                            return {"ok": False, "skipped": True, "reason": "remote_sidecar_404"}
                        return {"ok": False, "error": f"HTTP:{exc.code}"}

        if blob is None:
            return {"ok": False, "skipped": True, "reason": "durable_backend_disabled"}
        if not blob:
            return {"ok": False, "skipped": True, "reason": "empty_blob"}
        dest = unpack_production_observations(blob, edge_root)
        # Guard against accidental double nesting from bad extractors.
        nested = dest / "production_observations"
        if nested.is_dir() and not (dest / "daily_run_index.json").exists():
            return {
                "ok": False,
                "error": "double_nested_production_observations",
                "path": str(dest),
            }
        return {"ok": True, "path": str(dest), "bytes": len(blob), "source": source}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
