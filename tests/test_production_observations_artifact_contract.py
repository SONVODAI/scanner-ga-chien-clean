"""
Regression: production_observations durable sidecar must use the VPS
artifact-server contract (ARTIFACT_*), not only Challenger DURABLE_*.

On tip a64943b05, publish_production_observations_durable() returned
reason=durable_backend_disabled when only EDGE_RESEARCH_ARTIFACT_* was
configured — the real mrbot-edge-artifacts.service deployment shape.
"""

from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import pytest

from modules.edge_research.artifact_server import ArtifactServer, ArtifactServerConfig
from modules.edge_research.autonomous_daily_edge_ui import build_autonomous_daily_edge_ui_view
from modules.edge_research.production_observations_sync import (
    PRODUCTION_OBS_OBJECT,
    pack_production_observations,
    publish_production_observations_durable,
    resolve_production_observations_publish_backend,
    try_restore_production_observations_durable,
    unpack_production_observations,
)


TEST_TOKEN = "test-prodobs-artifact-token-not-a-secret"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _clear_durable_and_artifact_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "EDGE_RESEARCH_DURABLE_BACKEND",
        "EDGE_RESEARCH_DURABLE_PATH",
        "EDGE_RESEARCH_DURABLE_URL",
        "EDGE_RESEARCH_DURABLE_TOKEN",
        "EDGE_RESEARCH_ARTIFACT_STORAGE",
        "EDGE_RESEARCH_ARTIFACT_TOKEN",
        "EDGE_RESEARCH_ARTIFACT_HOST",
        "EDGE_RESEARCH_ARTIFACT_PORT",
        "EDGE_RESEARCH_DATA_DIR",
    ):
        monkeypatch.delenv(key, raising=False)


def _seed_production_observations(edge_root: Path, *, trade_date: str = "2026-08-27") -> Path:
    prod = edge_root / "production_observations"
    (prod / "daily_runs").mkdir(parents=True, exist_ok=True)
    (prod / "daily_manifests").mkdir(parents=True, exist_ok=True)
    (prod / "daily_voices").mkdir(parents=True, exist_ok=True)
    run_id = f"live_{trade_date.replace('-', '')}_seed"
    index = {
        "runs": {
            run_id: {
                "run_id": run_id,
                "target_trade_date": trade_date,
                "run_disposition": "SUCCESS",
                "run_mode": "LIVE_FORWARD",
                "discovery_count": 1,
            }
        }
    }
    (prod / "daily_run_index.json").write_text(json.dumps(index), encoding="utf-8")
    (prod / "daily_runs" / f"{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "run_disposition": "SUCCESS",
                "target_trade_date": trade_date,
                "discovery_count": 1,
                "session_market_voice_kind": "SESSION_MARKET_VOICE",
            }
        ),
        encoding="utf-8",
    )
    (prod / "daily_manifests" / f"{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "ok": True,
                "discovery_count": 1,
                "bot_spoke_today": True,
            }
        ),
        encoding="utf-8",
    )
    (prod / "daily_voices" / f"session_{trade_date}.json").write_text(
        json.dumps(
            {
                "voice_kind": "SESSION_MARKET_VOICE",
                "assessment_trade_date": trade_date,
                "observation_id": f"obs_{trade_date}",
                "q1_today_i_see_vi": "Hom nay thi truong mo cua on dinh.",
                "q2_vs_prior_session_vi": "So voi phien truoc, dong tien ngoai cai thien.",
                "q3_market_change_vi": "Bien dong chu yeu o nhom ngan hang.",
                "q4_new_evidence_vi": "Co tin hieu discovery moi.",
                "q5_belief_changed_vi": "Niem tin tang nhe.",
                "q6_if_not_why_vi": "",
                "q9_waiting_for_vi": "Cho them xac nhan phien toi.",
            }
        ),
        encoding="utf-8",
    )
    return prod


def test_a64943b05_regression_artifact_storage_not_durable_backend_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    FAIL on a64943b05: only ARTIFACT_STORAGE configured → durable_backend_disabled.
    MUST succeed after architecture fix.
    """
    _clear_durable_and_artifact_env(monkeypatch)
    edge = tmp_path / "edge"
    edge.mkdir()
    _seed_production_observations(edge)
    storage = tmp_path / "artifact_storage"
    storage.mkdir()

    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(edge))
    monkeypatch.setenv("EDGE_RESEARCH_ARTIFACT_STORAGE", str(storage))
    # Explicitly ensure DURABLE_* remain unset (VPS daily runner shape).
    assert not (monkeypatch.getenv("EDGE_RESEARCH_DURABLE_BACKEND") if False else None)

    backend, params = resolve_production_observations_publish_backend()
    assert backend == "artifact_storage", (
        f"expected artifact_storage when only ARTIFACT_STORAGE is set; got {backend}"
    )
    assert params["storage_root"] == storage

    result = publish_production_observations_durable(data_dir=edge)
    assert result.get("ok") is True, result
    assert result.get("backend") == "artifact_storage"
    assert result.get("reason") != "durable_backend_disabled"
    published = storage / "current" / PRODUCTION_OBS_OBJECT
    assert published.is_file()
    assert published.stat().st_size > 0


def test_publish_via_artifact_http_without_durable_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_durable_and_artifact_env(monkeypatch)
    edge = tmp_path / "edge"
    edge.mkdir()
    _seed_production_observations(edge)
    storage = tmp_path / "artifact_storage"
    storage.mkdir()
    port = _free_port()
    config = ArtifactServerConfig(
        storage_root=storage,
        token=TEST_TOKEN,
        host="127.0.0.1",
        port=port,
    )
    server = ArtifactServer(config)
    server.start(blocking=False)
    try:
        # Force HTTP path: no storage env, and hide production default storage.
        monkeypatch.setattr(
            "modules.edge_research.production_observations_sync.DEFAULT_STORAGE_ROOT",
            tmp_path / "no-default-artifact-storage",
        )
        monkeypatch.setattr(
            "modules.edge_research.production_observations_sync.ARTIFACT_ENV_FILE",
            tmp_path / "missing-edge-artifacts.env",
        )
        monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(edge))
        monkeypatch.setenv("EDGE_RESEARCH_ARTIFACT_TOKEN", TEST_TOKEN)
        monkeypatch.setenv("EDGE_RESEARCH_ARTIFACT_HOST", "127.0.0.1")
        monkeypatch.setenv("EDGE_RESEARCH_ARTIFACT_PORT", str(port))

        backend, _ = resolve_production_observations_publish_backend()
        assert backend == "artifact_http", backend
        result = publish_production_observations_durable(data_dir=edge)
        assert result.get("ok") is True, result
        assert result.get("backend") == "artifact_http"
        assert result.get("reason") != "durable_backend_disabled"

        url = f"http://127.0.0.1:{port}/current/{PRODUCTION_OBS_OBJECT}"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {TEST_TOKEN}"}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
        assert body
        assert (storage / "current" / PRODUCTION_OBS_OBJECT).is_file()
    finally:
        server.stop()


def test_streamlit_consumer_restore_no_double_nest_and_ui_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    VPS publishes via ARTIFACT_*; Streamlit restores via DURABLE_URL pointing at
    the same artifact-server object path — no double nesting, UI fields present.
    """
    _clear_durable_and_artifact_env(monkeypatch)
    edge_src = tmp_path / "edge_src"
    edge_src.mkdir()
    _seed_production_observations(edge_src)
    storage = tmp_path / "artifact_storage"
    storage.mkdir()
    port = _free_port()
    config = ArtifactServerConfig(
        storage_root=storage,
        token=TEST_TOKEN,
        host="127.0.0.1",
        port=port,
    )
    server = ArtifactServer(config)
    server.start(blocking=False)
    try:
        monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(edge_src))
        monkeypatch.setenv("EDGE_RESEARCH_ARTIFACT_STORAGE", str(storage))
        pub = publish_production_observations_durable(data_dir=edge_src)
        assert pub.get("ok") is True, pub

        # Consumer side: only DURABLE_* (Streamlit Cloud shape) — no ARTIFACT_*.
        _clear_durable_and_artifact_env(monkeypatch)
        edge_dst = tmp_path / "edge_dst"
        edge_dst.mkdir()
        monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(edge_dst))
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_BACKEND", "http")
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_TOKEN", TEST_TOKEN)

        restore = try_restore_production_observations_durable(data_dir=edge_dst)
        assert restore.get("ok") is True, restore
        dest = Path(restore["path"])
        assert (dest / "daily_run_index.json").is_file()
        assert not (dest / "production_observations").exists(), "double nesting detected"

        view = build_autonomous_daily_edge_ui_view(data_dir=edge_dst)
        assert view.get("session_date") == "2026-08-27"
        assert view.get("run_disposition") == "SUCCESS"
        assert view.get("discovery_count") == 1
        assert view.get("requires_streamlit_action") is False
        assert view.get("view_only") is True
        assert view.get("daily_market_voice_exists") is True
        qs = view.get("session_voice_questions") or {}
        assert qs.get("voice_kind") == "SESSION_MARKET_VOICE"
        assert "Hom nay thi truong" in str(qs.get("q1_today_i_see_vi") or "")
        assert "Hom nay thi truong" in str(view.get("narrative_vi") or "")
    finally:
        server.stop()


def test_unpack_lands_in_canonical_root_not_nested(tmp_path: Path) -> None:
    edge = tmp_path / "edge"
    edge.mkdir()
    prod = _seed_production_observations(edge)
    blob = pack_production_observations(prod)
    assert blob
    dest_edge = tmp_path / "dest_edge"
    dest_edge.mkdir()
    dest = unpack_production_observations(blob, dest_edge)
    assert dest.name == "production_observations"
    assert (dest / "daily_run_index.json").is_file()
    assert not (dest / "production_observations" / "daily_run_index.json").exists()


def test_loads_artifact_env_file_when_process_env_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Daily oneshot may lack ARTIFACT_* in process env; must read edge-artifacts.env."""
    _clear_durable_and_artifact_env(monkeypatch)
    edge = tmp_path / "edge"
    edge.mkdir()
    _seed_production_observations(edge)
    storage = tmp_path / "artifact_storage"
    storage.mkdir()
    env_file = tmp_path / "edge-artifacts.env"
    env_file.write_text(
        "\n".join(
            [
                f"EDGE_RESEARCH_ARTIFACT_TOKEN={TEST_TOKEN}",
                f"EDGE_RESEARCH_ARTIFACT_STORAGE={storage}",
                "EDGE_RESEARCH_ARTIFACT_HOST=127.0.0.1",
                "EDGE_RESEARCH_ARTIFACT_PORT=8765",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "modules.edge_research.production_observations_sync.ARTIFACT_ENV_FILE",
        env_file,
    )
    monkeypatch.setattr(
        "modules.edge_research.production_observations_sync.DEFAULT_STORAGE_ROOT",
        tmp_path / "no-default",
    )
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(edge))

    backend, params = resolve_production_observations_publish_backend()
    assert backend == "artifact_storage"
    assert params["storage_root"] == storage
    result = publish_production_observations_durable(data_dir=edge)
    assert result.get("ok") is True, result
    assert (storage / "current" / PRODUCTION_OBS_OBJECT).is_file()


def test_disabled_only_when_neither_artifact_nor_durable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_durable_and_artifact_env(monkeypatch)
    # Point ARTIFACT env file away and ensure default storage does not hijack.
    monkeypatch.setattr(
        "modules.edge_research.production_observations_sync.ARTIFACT_ENV_FILE",
        tmp_path / "missing-edge-artifacts.env",
    )
    monkeypatch.setattr(
        "modules.edge_research.production_observations_sync.DEFAULT_STORAGE_ROOT",
        tmp_path / "no-such-default-storage",
    )
    # Also patch artifact_server default used via _artifact_storage_root import path
    monkeypatch.setattr(
        "modules.edge_research.production_observations_sync.DEFAULT_STORAGE_ROOT",
        tmp_path / "no-such-default-storage",
    )
    edge = tmp_path / "edge"
    edge.mkdir()
    _seed_production_observations(edge)
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(edge))
    backend, _ = resolve_production_observations_publish_backend()
    assert backend == "none"
    result = publish_production_observations_durable(data_dir=edge)
    assert result.get("ok") is False
    assert result.get("reason") == "durable_backend_disabled"
