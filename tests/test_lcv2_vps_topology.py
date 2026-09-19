"""Real VPS topology: collect parquet is authoritative; no phantom Camera service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M,
)
from modules.live_candidate_v2_action.observe_store import observe_from_collected_session
from modules.live_candidate_v2_camera.github_bus import STATUS_NOT_FOUND, V2FetchResult
from modules.live_candidate_v2_camera.observe import pxv_implies_buy

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
SESSION = "2026-09-18"
NOW = datetime.fromisoformat("2026-09-19T10:05:00").replace(tzinfo=VN)


def test_no_phantom_live_camera_shadow_unit():
    systemd = REPO / "deploy" / "systemd"
    names = {p.name for p in systemd.glob("*")}
    assert "mrbot-live-camera-shadow.service" not in names
    assert "mrbot-v2-shadow-observe.service" in names
    assert "mrbot-v2-shadow-observe.timer" in names
    assert "mrbot-intraday-collect.service" in names
    assert "mrbot-intraday-collect.timer" in names
    updater = (REPO / "scripts" / "vps_update_live_shadow_v2.sh").read_text(encoding="utf-8")
    assert "systemctl restart \"$PHANTOM_SERVICE\"" not in updater
    assert "systemctl start \"$PHANTOM_SERVICE\"" not in updater
    assert "PHANTOM_SERVICE=\"mrbot-live-camera-shadow.service\"" in updater
    assert "mrbot-v2-shadow-observe" in updater
    assert "COLLECT_UNITS_UNTOUCHED=YES" in updater
    assert "run_rotation_watch" not in updater
    collect = (systemd / "mrbot-intraday-collect.service").read_text(encoding="utf-8")
    assert "modules.intraday_memory.runner collect" in collect
    observe = (systemd / "mrbot-v2-shadow-observe.service").read_text(encoding="utf-8")
    assert "run_v2_shadow_observe_store.py" in observe
    assert "--live" not in observe
    assert "/opt/mrbot-camera" not in observe or "WorkingDirectory=/opt/mrbot-live-shadow" in observe


def test_observe_store_source_has_no_kbs():
    src = (REPO / "modules" / "live_candidate_v2_action" / "observe_store.py").read_text(encoding="utf-8")
    assert "KBSProvider" not in src
    assert "intraday_memory.provider" not in src
    assert "intraday_memory.collector" not in src
    assert "load_session" in src


def test_observe_stale_sidecar_fail_closed_no_fabricated_rows(tmp_path, monkeypatch):
    def _missing():
        return V2FetchResult(ok=False, status=STATUS_NOT_FOUND, error="404")

    monkeypatch.setattr(
        "modules.live_candidate_v2_action.observe_store.load_session",
        lambda root, session: (_ for _ in ()).throw(AssertionError("must not load parquet when sidecar fails")),
    )
    payload = observe_from_collected_session(
        session="2026-09-19",
        now=NOW,
        camera_root=tmp_path / "camera",
        out_dir=tmp_path / "out",
        shadow_store_dir=tmp_path / "store",
        sidecar_fetcher=_missing,
    )
    assert payload["rows"] == []
    assert payload["kbs_polled"] is False
    assert payload["candidate_is_buy"] is False
    assert payload["pxv_implies_buy"] is False
    assert payload["alert_eligible"] is False
    assert payload["waiting"] == WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M
    assert (tmp_path / "store" / "v2_action_state.json").exists()


def test_observe_from_parquet_does_not_poll_or_flip_permissions(tmp_path):
    def _ok():
        from tests.test_lcv2_vps_shadow_observe import _sidecar

        return V2FetchResult(ok=True, status="OK_ROWS", document=_sidecar(session=SESSION), n_rows=1)

    frame = pd.DataFrame(
        [
            {
                "symbol": "HPG",
                "timestamp": datetime.fromisoformat("2026-09-18T09:15:00").replace(tzinfo=VN),
                "session_date": SESSION,
                "open": 27100,
                "high": 27200,
                "low": 27000,
                "close": 27150,
                "volume": 1000,
                "source": "vnstock4_kbs",
                "collected_at": NOW,
                "quality_flag": "ok",
            }
        ]
    )
    import modules.live_candidate_v2_action.observe_store as obs

    orig = obs.load_session
    obs.load_session = lambda root, session: frame  # type: ignore[assignment]
    try:
        payload = observe_from_collected_session(
            session=SESSION,
            now=datetime.fromisoformat("2026-09-18T16:00:00").replace(tzinfo=VN),
            camera_root=tmp_path / "camera",
            out_dir=tmp_path / "out",
            shadow_store_dir=tmp_path / "store",
            sidecar_fetcher=_ok,
        )
    finally:
        obs.load_session = orig  # type: ignore[assignment]
    assert payload["kbs_polled"] is False
    assert payload["candidate_is_buy"] is False
    assert pxv_implies_buy("STRENGTHEN") is False
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False
    assert payload.get("collector") == "mrbot-intraday-collect"
    rows = payload.get("rows") or []
    assert rows
    assert rows[0]["symbol"] == "HPG"
    assert rows[0]["shadow_action"] != "WAIT" or rows[0].get("action_reason") != "NO_OBSERVATION_CAP"


def test_permissions_remain_false():
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False
    assert pxv_implies_buy("STRENGTHEN") is False
