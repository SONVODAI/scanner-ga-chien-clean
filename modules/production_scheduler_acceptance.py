"""
Autonomous daily scheduler acceptance — static contracts (no research execution).

Validates systemd unit text and installer script invariants so deploy/install
cannot claim readiness while leaving the timer disabled or systemd stale.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = REPO_ROOT / "deploy" / "systemd"
SERVICE_UNIT = SYSTEMD_DIR / "mrbot-daily-research.service"
TIMER_UNIT = SYSTEMD_DIR / "mrbot-daily-research.timer"
INSTALL_SCRIPT = SYSTEMD_DIR / "install-daily-research.sh"
ACCEPT_SCRIPT = SYSTEMD_DIR / "accept-autonomous-daily-scheduler.sh"

REQUIRED_PYTHON = "/opt/mrbot-research-venv/bin/python"
REQUIRED_MODULE = "modules.edge_research.opr_bridge.production_daily_run_entrypoint"
REQUIRED_MODE = "LIVE_FORWARD"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_service_unit(text: Optional[str] = None) -> Dict[str, Any]:
    raw = text if text is not None else _read(SERVICE_UNIT)
    errors: List[str] = []
    exec_lines = [ln for ln in raw.splitlines() if ln.strip().startswith("ExecStart=")]
    if len(exec_lines) != 1:
        errors.append(f"expected_one_ExecStart_got_{len(exec_lines)}")
        exec_line = ""
    else:
        exec_line = exec_lines[0].split("=", 1)[1].strip()
    if REQUIRED_PYTHON not in exec_line:
        errors.append("missing_research_venv_python")
    if REQUIRED_MODULE not in exec_line:
        errors.append("missing_production_entrypoint")
    if f"--mode {REQUIRED_MODE}" not in exec_line:
        errors.append("missing_live_forward_mode")
    if "--derive-vn-date" not in exec_line:
        errors.append("missing_derive_vn_date")
    if "--use-lock" not in exec_line:
        errors.append("missing_use_lock")
    if "streamlit" in exec_line.lower():
        errors.append("streamlit_forbidden_in_execstart")
    return {
        "ok": not errors,
        "exec_start": exec_line,
        "errors": errors,
    }


def validate_timer_unit(text: Optional[str] = None) -> Dict[str, Any]:
    raw = text if text is not None else _read(TIMER_UNIT)
    errors: List[str] = []
    if "DISABLED" in raw and "install only" in raw.lower():
        errors.append("timer_description_still_marks_disabled_only")
    if "OnCalendar=" not in raw:
        errors.append("missing_oncalendar")
    if "Asia/Ho_Chi_Minh" not in raw:
        errors.append("missing_vn_timezone")
    if "Unit=mrbot-daily-research.service" not in raw:
        errors.append("missing_service_unit_binding")
    # Exactly one timer identity — no second production research timer in this file.
    if raw.count("[Timer]") != 1:
        errors.append("unexpected_timer_section_count")
    return {"ok": not errors, "errors": errors}


def validate_install_script(text: Optional[str] = None) -> Dict[str, Any]:
    raw = text if text is not None else _read(INSTALL_SCRIPT)
    errors: List[str] = []
    if "daemon-reload" not in raw:
        errors.append("missing_daemon_reload")
    if "--enable-when-genesis" not in raw:
        errors.append("missing_enable_when_genesis_flag")
    if "--require-active" not in raw:
        errors.append("missing_require_active_flag")
    if "enable --now mrbot-daily-research.timer" not in raw:
        errors.append("missing_enable_now_timer")
    # Must not unconditionally claim timer left disabled without a genesis gate.
    if re.search(r"Timer NOT enabled\. Operator must run DAY_0_SMOKE", raw):
        errors.append("stale_day0_smoke_gate_message")
    # Enabling must be gated on genesis presence.
    if "live_forward_genesis.json" not in raw:
        errors.append("missing_genesis_path_check")
    if "ENABLE_WHEN_GENESIS" not in raw and "--enable-when-genesis" not in raw:
        errors.append("missing_enable_gate")
    return {"ok": not errors, "errors": errors}


def validate_accept_script(text: Optional[str] = None) -> Dict[str, Any]:
    raw = text if text is not None else _read(ACCEPT_SCRIPT)
    errors: List[str] = []
    for needle in (
        "AUTONOMOUS_SCHEDULER_ACCEPTANCE=PASS",
        "NEXT_REAL_SESSION_READY=YES",
        "--enable-when-genesis",
        "--require-active",
        "live_forward_genesis.json",
        "LIVE_FORWARD",
        "/opt/mrbot-research-venv/bin/python",
        "list-timers",
    ):
        if needle not in raw:
            errors.append(f"missing:{needle}")
    # Must not invoke research / recovery.
    forbidden = (
        "run_headless_eod(",
        "historical_recovery",
        "--recovery",
        "git reset --hard",
        "git clean",
        "checkout main",
        "streamlit run",
    )
    for needle in forbidden:
        if needle in raw:
            errors.append(f"forbidden:{needle}")
    return {"ok": not errors, "errors": errors}


def run_scheduler_acceptance_static_audit() -> Dict[str, Any]:
    service = validate_service_unit()
    timer = validate_timer_unit()
    install = validate_install_script()
    accept = validate_accept_script()
    ok = all(x["ok"] for x in (service, timer, install, accept))
    return {
        "ok": ok,
        "service": service,
        "timer": timer,
        "install_script": install,
        "accept_script": accept,
    }
