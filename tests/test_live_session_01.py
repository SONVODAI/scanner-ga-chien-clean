"""LIVE SESSION 01 preflight + read-only validator. Never starts KBS."""
from __future__ import annotations

import inspect
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.live_candidate_pxv_ui.read import default_shadow_dir, default_watchlist_path
from modules.live_camera_shadow.feed import (
    default_shadow_dir as feed_shadow,
    default_watchlist_path as feed_watch,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def test_ui_and_feed_share_exact_paths():
    assert default_watchlist_path().resolve() == feed_watch().resolve()
    assert default_shadow_dir().resolve() == feed_shadow().resolve()


def test_preflight_does_not_start_session():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "preflight_live_session_01",
        Path("scripts/preflight_live_session_01.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = inspect.getsource(mod)
    assert "--live" not in src or "Never starts KBS" in (mod.__doc__ or "")
    assert "run_cycle" not in src
    payload = mod.run_preflight(now=_ts("2026-08-14T10:00:00"))
    assert payload["session_started"] is False
    assert payload["production_unchanged"] is True


def test_validator_not_started_is_valid_pre_session():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_live_session_01",
        Path("scripts/validate_live_session_01.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.analyze(
        watchlist=[],
        evidence=[],
        status={},
        now=_ts("2026-08-14T10:00:00"),
    )
    assert report["session_status"] == "NOT_STARTED"
    assert report["verdict"]["PRODUCTION_UNCHANGED"] == "YES"
    assert report["verdict"]["CANDIDATE_LIVE_HANDOFF_WORKED"] == "NO"
    assert report["verdict"]["CAMERA_5M_LIVE_WORKED"] == "NO"
    assert "not started" in report["blocker"].lower()


def test_validator_neutral_only_session_can_pass():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_live_session_01",
        Path("scripts/validate_live_session_01.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.analyze(
        watchlist=[
            {
                "symbol": "HPG",
                "candidate_reason": "BUY ELITE",
                "candidate_first_seen_ts": "2026-08-14T10:05:00+07:00",
                "eligible_from": "2026-08-14T10:05:00+07:00",
            }
        ],
        evidence=[
            {
                "symbol": "HPG",
                "bar_ts": "2026-08-14T10:15:00+07:00",
                "observed_at": "2026-08-14T10:21:00+07:00",
                "raw_evidence": "NEUTRAL",
                "published_evidence": "NEUTRAL",
                "chronology_legal": True,
                "alert_eligible": False,
            }
        ],
        status={"observed_at": "2026-08-14T10:21:00+07:00", "alert_eligible": False, "symbols": [{"symbol": "HPG", "status": "OK"}]},
        now=_ts("2026-08-14T10:22:00"),
    )
    assert report["session_status"] == "OBSERVED"
    assert report["counts"]["candidates"] == 1
    assert report["counts"]["legal_completed_bars"] == 1
    assert report["counts"]["raw"]["NEUTRAL"] == 1
    assert report["verdict"]["CANDIDATE_LIVE_HANDOFF_WORKED"] == "YES"
    assert report["verdict"]["CAMERA_5M_LIVE_WORKED"] == "YES"
    assert report["verdict"]["PXV_LIVE_INTERPRETATION_WORKED"] == "YES"
    assert report["verdict"]["CHRONOLOGY_CLEAN"] == "YES"
    assert report["latency_sec"]["after_bar_close_median"] == 60.0


def test_validator_empty_candidate_is_valid():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_live_session_01",
        Path("scripts/validate_live_session_01.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.analyze(
        watchlist=[],
        evidence=[],
        status={"observed_at": "2026-08-14T10:20:00+07:00", "alert_eligible": False, "symbols": []},
        now=_ts("2026-08-14T10:21:00"),
    )
    assert report["verdict"]["CANDIDATE_LIVE_HANDOFF_WORKED"] == "YES"
    assert report["counts"]["candidates"] == 0
    assert report["verdict"]["CHRONOLOGY_CLEAN"] == "YES"


def test_validator_illegal_bar_fails_chronology():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_live_session_01",
        Path("scripts/validate_live_session_01.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.analyze(
        watchlist=[{"symbol": "HPG", "candidate_first_seen_ts": "2026-08-14T13:37:00+07:00", "eligible_from": "2026-08-14T13:37:00+07:00"}],
        evidence=[{
            "symbol": "HPG",
            "bar_ts": "2026-08-14T13:35:00+07:00",
            "observed_at": "2026-08-14T13:42:00+07:00",
            "raw_evidence": "STRENGTHEN",
            "published_evidence": "STRENGTHEN",
            "chronology_legal": False,
            "alert_eligible": False,
        }],
        status={"observed_at": "2026-08-14T13:42:00+07:00", "alert_eligible": False, "symbols": []},
        now=_ts("2026-08-14T13:43:00"),
    )
    assert report["verdict"]["CHRONOLOGY_CLEAN"] == "NO"
    assert report["counts"]["illegal_evidence_rows"] == 1


def test_validator_source_does_not_call_provider():
    text = Path("scripts/validate_live_session_01.py").read_text(encoding="utf-8")
    for tok in ("KBSProvider", "fetch_session", "upsert_session", "IntradayCollector"):
        assert tok not in text
    assert "Never calls Camera/provider" in text
    op = Path("scripts/live_session_01_operator.sh").read_text(encoding="utf-8")
    assert 'preflight|start|health|stop|validate' in op
    assert "Does not start unless you pass" in op
