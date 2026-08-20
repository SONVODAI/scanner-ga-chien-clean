"""P1b Edge Research VPS artifact server tests — CASE 1 through CASE 10."""

from __future__ import annotations

import io
import json
import shutil
import socket
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SOURCE = REPO_ROOT / "data" / "edge_research"
TEST_TOKEN = "test-artifact-token-placeholder"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(method: str, url: str, token: str | None = None, data: bytes | None = None) -> tuple[int, bytes]:
    headers = {"User-Agent": "test"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/gzip"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@pytest.fixture
def reference_copy(tmp_path) -> Path:
    if not REFERENCE_SOURCE.exists():
        pytest.skip("reference data/edge_research unavailable")
    dest = tmp_path / "reference_edge_research"
    shutil.copytree(REFERENCE_SOURCE, dest)
    return dest


@pytest.fixture
def artifact_server(tmp_path):
    from modules.edge_research.artifact_server import ArtifactServer, ArtifactServerConfig

    storage = tmp_path / "durable_root"
    port = _free_port()
    config = ArtifactServerConfig(
        storage_root=storage,
        token=TEST_TOKEN,
        host="127.0.0.1",
        port=port,
        max_upload_bytes=50 * 1024 * 1024,
    )
    server = ArtifactServer(config)
    server.start(blocking=False)
    base_url = server.base_url
    yield base_url, config, storage
    server.stop()


def _bundle_tar_from_working(working_dir: Path) -> bytes:
    from modules.edge_research.durable import stage_bundle_from_working_dir

    staging = working_dir.parent / "bundle_staging"
    stage_bundle_from_working_dir(working_dir, staging)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(staging / "manifest.json", arcname="manifest.json")
        for path in sorted((staging / "artifacts").iterdir()):
            tar.add(path, arcname=f"artifacts/{path.name}")
    return buf.getvalue()


# CASE 1 — authorized PUT succeeds
def test_case1_authorized_put(artifact_server, reference_copy):
    base_url, _, storage = artifact_server
    tar_bytes = _bundle_tar_from_working(reference_copy)
    status, body = _request("PUT", f"{base_url}/current/bundle.tar.gz", TEST_TOKEN, tar_bytes)
    assert status == 200
    assert json.loads(body)["ok"] is True
    assert (storage / "current" / "bundle.tar.gz").exists()


# CASE 2 — authorized GET returns identical bundle
def test_case2_authorized_get(artifact_server, reference_copy):
    base_url, _, _ = artifact_server
    tar_bytes = _bundle_tar_from_working(reference_copy)
    _request("PUT", f"{base_url}/current/bundle.tar.gz", TEST_TOKEN, tar_bytes)
    status, body = _request("GET", f"{base_url}/current/bundle.tar.gz", TEST_TOKEN)
    assert status == 200
    assert body == tar_bytes


# CASE 3 — missing/wrong token rejected
def test_case3_unauthorized_rejected(artifact_server, reference_copy):
    base_url, _, _ = artifact_server
    tar_bytes = _bundle_tar_from_working(reference_copy)
    status, _ = _request("PUT", f"{base_url}/current/bundle.tar.gz", None, tar_bytes)
    assert status == 401
    status, _ = _request("GET", f"{base_url}/current/bundle.tar.gz", "wrong-token")
    assert status == 401


# CASE 4 — malformed upload rejected
def test_case4_malformed_upload_rejected(artifact_server):
    base_url, _, storage = artifact_server
    status, _ = _request("PUT", f"{base_url}/current/bundle.tar.gz", TEST_TOKEN, b"not-a-valid-gzip")
    assert status == 400
    assert not (storage / "current" / "bundle.tar.gz").exists()


# CASE 5 — oversized upload rejected
def test_case5_oversized_upload_rejected(tmp_path):
    from modules.edge_research.artifact_server import ArtifactServer, ArtifactServerConfig

    storage = tmp_path / "durable_root"
    port = _free_port()
    config = ArtifactServerConfig(
        storage_root=storage,
        token=TEST_TOKEN,
        host="127.0.0.1",
        port=port,
        max_upload_bytes=1024,
    )
    server = ArtifactServer(config)
    server.start(blocking=False)
    try:
        status, _ = _request(
            "PUT",
            f"{server.base_url}/current/bundle.tar.gz",
            TEST_TOKEN,
            b"x" * 2048,
        )
        assert status == 413
    finally:
        server.stop()


# CASE 6 — failed replacement preserves previous bundle
def test_case6_failed_replace_preserves_previous(artifact_server, reference_copy):
    base_url, _, storage = artifact_server
    good = _bundle_tar_from_working(reference_copy)
    _request("PUT", f"{base_url}/current/bundle.tar.gz", TEST_TOKEN, good)
    before = (storage / "current" / "bundle.tar.gz").read_bytes()
    status, _ = _request("PUT", f"{base_url}/current/bundle.tar.gz", TEST_TOKEN, b"bad")
    assert status == 400
    after = (storage / "current" / "bundle.tar.gz").read_bytes()
    assert after == before == good


# CASE 7 — no arbitrary filesystem path access
def test_case7_no_arbitrary_path_access(artifact_server):
    base_url, _, _ = artifact_server
    for path in ("/etc/passwd", "/../../../etc/passwd", "/current/other", "/artifacts"):
        status, _ = _request("GET", f"{base_url}{path}", TEST_TOKEN)
        assert status == 404


# CASE 8 — camera paths not accessible; traversal tar rejected
def test_case8_camera_isolation_and_tar_traversal(artifact_server, reference_copy, tmp_path):
    base_url, config, _ = artifact_server
    camera_root = tmp_path / "intraday_memory"
    camera_root.mkdir()
    secret = camera_root / "secret.parquet"
    secret.write_bytes(b"camera-data")

    tar_bytes = _bundle_tar_from_working(reference_copy)
    _request("PUT", f"{base_url}/current/bundle.tar.gz", TEST_TOKEN, tar_bytes)
    assert secret.read_bytes() == b"camera-data"

    # crafted traversal tar
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="../intraday_memory/pwned")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"evil"))
    status, _ = _request("PUT", f"{base_url}/current/bundle.tar.gz", TEST_TOKEN, buf.getvalue())
    assert status == 400
    assert not (tmp_path / "intraday_memory" / "pwned").exists()
    assert config.storage_root.is_relative_to(tmp_path) or "edge_research" in str(config.storage_root)


# CASE 9 — full HTTP client round trip restore 20/0/3/17
def test_case9_http_client_round_trip(artifact_server, reference_copy, tmp_path, monkeypatch):
    base_url, _, _ = artifact_server
    working = tmp_path / "working"
    shutil.copytree(reference_copy, working)
    empty = tmp_path / "empty"
    empty.mkdir()

    monkeypatch.setenv("EDGE_RESEARCH_DURABLE_BACKEND", "http")
    monkeypatch.setenv("EDGE_RESEARCH_DURABLE_URL", base_url)
    monkeypatch.setenv("EDGE_RESEARCH_DURABLE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(working))

    from modules.edge_research.durable import stage_bundle_from_working_dir, resolve_durable_backend
    from modules.edge_research.persistence import publish_durable, try_restore_durable, summarize_restored_cohort

    staging = tmp_path / "stage"
    stage_bundle_from_working_dir(working, staging)
    backend = resolve_durable_backend()
    pub = backend.publish_bundle(staging)
    assert pub.ok

    shutil.rmtree(working)
    working.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(working))
    st = try_restore_durable(working)
    assert st.last_result == "restored"
    summary = summarize_restored_cohort(working)
    assert summary["cohort_size"] == 20
    assert summary["robustness_pass"] == 0
    assert summary["robustness_fragile"] == 3
    assert summary["robustness_reject"] == 17


# CASE 10 — service restart persistence
def test_case10_service_restart_persistence(artifact_server, reference_copy):
    base_url, config, storage = artifact_server
    tar_bytes = _bundle_tar_from_working(reference_copy)
    _request("PUT", f"{base_url}/current/bundle.tar.gz", TEST_TOKEN, tar_bytes)

    from modules.edge_research.artifact_server import ArtifactServer, ArtifactServerConfig

    # stop implicit via fixture end not yet — simulate restart with new server instance
    port2 = _free_port()
    config2 = ArtifactServerConfig(
        storage_root=storage,
        token=TEST_TOKEN,
        host="127.0.0.1",
        port=port2,
        max_upload_bytes=50 * 1024 * 1024,
    )
    server2 = ArtifactServer(config2)
    server2.start(blocking=False)
    try:
        status, body = _request("GET", f"{server2.base_url}/current/bundle.tar.gz", TEST_TOKEN)
        assert status == 200
        assert body == tar_bytes
    finally:
        server2.stop()


def test_health_unauthenticated(artifact_server):
    base_url, _, _ = artifact_server
    status, body = _request("GET", f"{base_url}/health", None)
    assert status == 200
    assert json.loads(body)["ok"] is True
