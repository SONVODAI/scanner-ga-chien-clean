"""Session handoff keeps the actual capture clock and refuses a later substitute."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.earning_learning import GitHubConfig, GitHubLocalStorage
from modules.session_handoff import (
    capture_locked_session_handoff,
    capture_session_handoff,
    load_valid_handoff,
    validate_handoff,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]


def _storage(tmp_path: Path) -> GitHubLocalStorage:
    return GitHubLocalStorage(
        tmp_path,
        GitHubConfig(
            token=None,
            owner="SONVODAI",
            repo="scanner-ga-chien-clean",
            branch="main",
            remote_dir="data/session_handoff",
        ),
    )


def _capture(storage, hour: int, minute: int, second: int = 0):
    moment = datetime(2026, 9, 22, hour, minute, second, tzinfo=VN)
    return capture_session_handoff(
        trade_date="2026-09-22",
        trading_today=True,
        trading_reason="",
        market={
            "market_real": 7,
            "market_live": 6,
            "market_forecast": 5,
            "market_forecast_text": "test",
            "market_confidence": 80,
            "breadth": 0.4,
            "market_status": "ok",
            "market_action": "watch",
            "market_regime": "TRUNG",
            "market_regime_note": "",
        },
        buy_elite_df=pd.DataFrame([{"MÃ": "AAA"}]),
        learning_board=pd.DataFrame([{"symbol": "AAA", "storm_score": 1.0}]),
        recommendations=pd.DataFrame([{"symbol": "AAA"}]),
        leader_brain=pd.DataFrame([{"symbol": "AAA", "leader_score": 10}]),
        pattern_library=pd.DataFrame([{"pattern_id": "p"}]),
        leader_history=pd.DataFrame(
            [
                {"session_date": "2026-09-22", "symbol": "AAA"},
                {"session_date": "2026-09-21", "symbol": "BBB"},
            ]
        ),
        now=moment,
        storage=storage,
    )


def test_latest_actual_clock_wins_and_is_not_labeled_1450(tmp_path):
    storage = _storage(tmp_path)
    assert _capture(storage, 13, 30)["status"] == "WRITTEN"
    assert _capture(storage, 14, 20)["status"] == "WRITTEN"
    last = _capture(storage, 14, 49, 12)
    assert last["captured_at"] == "2026-09-22T14:49:12+07:00"
    older = _capture(storage, 13, 30)
    assert older["status"] == "KEPT_NEWER"
    text = (tmp_path / "2026-09-22.json").read_text(encoding="utf-8")
    assert "2026-09-22T14:49:12+07:00" in text
    assert "14:50" not in text
    payload = load_valid_handoff("2026-09-22", storage=storage)
    assert payload is not None
    assert payload["captured_at"] == "2026-09-22T14:49:12+07:00"
    assert "2026-09-21" not in payload["frames"]["leader_session_snapshot"]


def test_invalid_handoffs_are_rejected(tmp_path):
    storage = _storage(tmp_path)
    _capture(storage, 14, 49)
    payload = load_valid_handoff("2026-09-22", storage=storage)
    weekend = dict(payload)
    weekend["captured_at"] = "2026-09-26T10:00:00+07:00"
    weekend["trade_date"] = "2026-09-26"
    ok, reason = validate_handoff(weekend, path_trade_date="2026-09-26")
    assert ok is False
    assert reason == "captured_at_outside_lock"

    mismatch = dict(payload)
    mismatch["trade_date"] = "2026-09-21"
    ok, reason = validate_handoff(mismatch, path_trade_date="2026-09-22")
    assert ok is False
    assert reason == "trade_date_mismatch"

    broken = dict(payload)
    broken["schema_version"] = "other"
    ok, reason = validate_handoff(broken, path_trade_date="2026-09-22")
    assert ok is False
    assert reason == "bad_schema"
    assert load_valid_handoff("2026-09-23", storage=storage) is None


def test_capture_only_while_gate_is_locked(tmp_path):
    storage = _storage(tmp_path)
    skipped = capture_locked_session_handoff(
        trade_date="2026-09-22",
        trading_today=True,
        trading_reason="",
        market_real=1,
        market_live=1,
        market_forecast=1,
        market_forecast_text="",
        market_confidence=1,
        breadth=0,
        market_status="",
        market_action="",
        market_regime="",
        market_regime_note="",
        buy_elite_df=pd.DataFrame(),
        scan_df=pd.DataFrame(),
        storm_score_frame=pd.DataFrame(),
        evo_table=pd.DataFrame(),
        leader_brain=pd.DataFrame(),
        now=datetime(2026, 9, 22, 16, 0, tzinfo=VN),
        storage=storage,
    )
    assert skipped["status"] == "NOT_WRITTEN"
    assert skipped["reason"] == "not_locked"
    assert not (tmp_path / "2026-09-22.json").exists()


def test_failed_put_keeps_previous_object(tmp_path):
    storage = _storage(tmp_path)
    assert _capture(storage, 14, 49)["status"] == "WRITTEN"

    class Boom(GitHubLocalStorage):
        def write_text(self, filename, text, *, commit_message):
            raise RuntimeError("PUT failed")

    boom = Boom(
        tmp_path,
        GitHubConfig(
            token=None,
            owner="SONVODAI",
            repo="scanner-ga-chien-clean",
            branch="main",
            remote_dir="data/session_handoff",
        ),
    )
    try:
        capture_session_handoff(
            trade_date="2026-09-22",
            trading_today=True,
            trading_reason="",
            market={"market_real": 1},
            buy_elite_df=pd.DataFrame(),
            learning_board=pd.DataFrame(),
            recommendations=pd.DataFrame(),
            leader_brain=pd.DataFrame(),
            pattern_library=pd.DataFrame(),
            leader_history=pd.DataFrame(),
            now=datetime(2026, 9, 22, 14, 55, tzinfo=VN),
            storage=boom,
        )
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True
    text = (tmp_path / "2026-09-22.json").read_text(encoding="utf-8")
    assert "2026-09-22T14:49:00+07:00" in text


def test_handoff_module_does_not_recompute_or_research():
    src = (REPO / "modules" / "session_handoff.py").read_text(encoding="utf-8")
    for name in (
        "_compute_storm_score_frame(",
        "compute_storm_scores(",
        "update_learning(",
        "finalize_forward_shadow_snapshot(",
        "run_buy_elite_learning_cycle(",
        "capture_market_t0_snapshot(",
        "freeze_daily_observer_if_eligible(",
        "run_scan(",
    ):
        assert name not in src
