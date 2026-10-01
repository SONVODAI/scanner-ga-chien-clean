"""Scheduler installer / acceptance contracts — no research execution."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.production_scheduler_acceptance import (
    ACCEPT_SCRIPT,
    INSTALL_SCRIPT,
    SERVICE_UNIT,
    TIMER_UNIT,
    run_scheduler_acceptance_static_audit,
    validate_accept_script,
    validate_install_script,
    validate_service_unit,
    validate_timer_unit,
)


def test_service_execstart_is_live_forward_research_venv():
    result = validate_service_unit()
    assert result["ok"], result["errors"]
    assert "/opt/mrbot-research-venv/bin/python" in result["exec_start"]
    assert "--mode LIVE_FORWARD" in result["exec_start"]
    assert "streamlit" not in result["exec_start"].lower()


def test_timer_not_labeled_disabled_only():
    result = validate_timer_unit()
    assert result["ok"], result["errors"]
    text = TIMER_UNIT.read_text(encoding="utf-8")
    assert "DISABLED" not in text or "install only" not in text.lower()


def test_installer_daemon_reload_and_genesis_gated_enable():
    result = validate_install_script()
    assert result["ok"], result["errors"]
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "daemon-reload" in text
    assert "--enable-when-genesis" in text
    assert "--require-active" in text
    assert "Timer NOT enabled. Operator must run DAY_0_SMOKE" not in text


def test_installer_require_active_cannot_pass_without_enable_path():
    """Simulate a regressive installer that leaves timer disabled after require-active."""
    bad = """#!/usr/bin/env bash
echo "Installed units"
echo "Timer NOT enabled. Operator must run DAY_0_SMOKE and create genesis first."
echo "To enable later: systemctl enable mrbot-daily-research.timer"
# intentionally omits systemd reload and genesis-gated activation
"""
    result = validate_install_script(bad)
    assert result["ok"] is False
    assert "missing_daemon_reload" in result["errors"]
    assert "missing_enable_when_genesis_flag" in result["errors"]
    assert "missing_require_active_flag" in result["errors"]
    assert "stale_day0_smoke_gate_message" in result["errors"]
    assert "missing_enable_now_timer" in result["errors"]


def test_accept_script_fail_closed_and_no_research_run():
    result = validate_accept_script()
    assert result["ok"], result["errors"]
    mode = ACCEPT_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR


def test_full_static_audit_pass():
    audit = run_scheduler_acceptance_static_audit()
    assert audit["ok"] is True, audit
