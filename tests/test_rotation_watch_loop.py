"""Operational Rotation --loop guard + isolated systemd unit. No engine/UI change."""

from __future__ import annotations

from pathlib import Path

from modules.rotation_watch.runner import (
    LOOP_LOCK_NAME,
    acquire_loop_lock,
    release_loop_lock,
)

REPO = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = REPO / "deploy" / "systemd"
SERVICE = SYSTEMD_DIR / "mrbot-rotation-watch.service"
INSTALL = SYSTEMD_DIR / "install-rotation-watch.sh"
ENV_EXAMPLE = SYSTEMD_DIR / "mrbot-rotation-watch.env.example"
SCRIPT = REPO / "scripts" / "run_rotation_watch.py"

FORBIDDEN_TOUCH = (
    "mrbot-intraday-collect.service",
    "mrbot-intraday-reconcile.service",
    "systemctl restart mrbot-edge-artifacts",
    "systemctl restart mrbot-intraday",
    "git pull",
    "git reset",
    "git checkout",
    "live_evidence.jsonl",
    "yfinance",
    "intraday_memory/",
)


def test_loop_lock_is_exclusive(tmp_path):
    first = acquire_loop_lock(tmp_path)
    assert first is not None
    assert (tmp_path / LOOP_LOCK_NAME).exists()
    second = acquire_loop_lock(tmp_path)
    assert second is None
    release_loop_lock(first)
    third = acquire_loop_lock(tmp_path)
    assert third is not None
    release_loop_lock(third)


def test_systemd_unit_is_isolated_single_loop():
    text = SERVICE.read_text(encoding="utf-8")
    assert (
        "ExecStart=/opt/mrbot-camera-venv/bin/python "
        "/opt/mrbot-rotation-watch/scripts/run_rotation_watch.py --live --loop"
    ) in text
    assert "WorkingDirectory=/opt/mrbot-rotation-watch" in text
    assert "EnvironmentFile=-/etc/mrbot/rotation-watch.env" in text
    assert "Restart=on-failure" in text
    assert "Type=simple" in text
    assert "mrbot-intraday-collect" not in text
    assert "mrbot-edge-artifacts" not in text
    assert "intraday_memory" not in text
    assert "live_pxv_shadow" not in text


def test_env_example_stays_on_isolated_store():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "MRBOT_ROTATION_WATCH_STORE=/var/lib/mrbot/rotation_watch" in text
    assert "MRBOT_ROTATION_WATCH_DIR=/opt/mrbot-rotation-watch/data/rotation_watch" in text
    assert "/var/lib/mrbot/intraday_memory" not in text
    assert "/var/lib/mrbot/live_pxv_shadow" not in text
    assert "/var/lib/mrbot/edge_research_durable" not in text


def test_install_script_does_not_touch_camera_edge_or_watchlist():
    text = INSTALL.read_text(encoding="utf-8")
    assert "ROTATION_LOOP_CONFIRM=YES" in text
    assert "mrbot-rotation-watch.service" in text
    assert "watchlist.csv" not in text
    assert "data/rotation_watch/watchlist" not in text
    assert "Never run from a Cloud Agent" in text
    for banned in FORBIDDEN_TOUCH:
        assert banned not in text, banned
    assert "systemctl restart mrbot-intraday-collect" not in text
    assert "systemctl restart mrbot-edge-artifacts" not in text
    assert "expected exactly 1 Rotation --loop process" in text


def test_loop_script_uses_refresh_gate_and_lock():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "loop_may_refresh" in src
    assert "acquire_loop_lock" in src
    assert "rotation_watch_loop_already_running" in src
    assert "skip persist" in src or "loop_refresh" in src
    assert "KBSProvider" in src
    assert "yfinance" not in src
