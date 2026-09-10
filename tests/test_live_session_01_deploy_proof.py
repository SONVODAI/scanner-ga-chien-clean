"""Deploy-proof script is read-only and never starts LIVE SESSION 01."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = Path("scripts/proof_live_session_01_deploy.py")
    spec = importlib.util.spec_from_file_location("proof_live_session_01_deploy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_proof_never_starts_session():
    src = Path("scripts/proof_live_session_01_deploy.py").read_text(encoding="utf-8")
    assert "--live" not in src
    assert "never starts" in src.lower()
    report = _load().run_proof()
    assert report["session_started"] is False
    assert report["verdict"]["E_LIVE_RUNNER_STILL_STOPPED"] == "YES"
    assert report["verdict"]["F_READY_TO_START_LIVE_SESSION_01"] == "NO"
    assert report["source"]["vnstock_0292"] is True
    assert report["source"]["ui_no_kbs"] is True
    assert report["source"]["alert_eligible_false"] is True
    assert report["source"]["empty_candidate_ui"] is True
    assert report["source"]["no_telegram_in_runner"] is True
    assert report["source"]["no_orders_in_runner"] is True
    # Names only — values must not appear in the proof payload.
    for name, state in report["secrets_present"].items():
        assert state in {"PRESENT", "ABSENT"}
        assert name not in ("ghp_", "sk-", "Bearer")


def test_overlay_script_refuses_prod_checkout():
    src = Path("scripts/vps_overlay_live_shadow_artifacts.sh").read_text(encoding="utf-8")
    assert "git checkout" not in src
    assert "does NOT switch /opt/mrbot-camera" in src
    assert "/opt/mrbot-camera" in src
    assert "NOT STARTED" in src
    assert "intraday_memory" in src
    assert "mrbot-edge-artifacts.service" in src
    rb = Path("scripts/vps_rollback_live_shadow_artifacts.sh").read_text(encoding="utf-8")
    assert "not written" in rb
    assert "systemctl restart" in rb
