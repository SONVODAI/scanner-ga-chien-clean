"""Post-close finalize consumes the handoff and does not rescan it."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import pandas as pd

from modules.post_close_finalize import (
    BEFORE_CANONICAL_WINDOW,
    NO_VALID_HANDOFF,
    SAME_DAY_WINDOW_CLOSED,
    run_post_close_finalize,
)
from modules.regime_alpha_forward_eval import finalize_forward_shadow_snapshot
from modules.session_handoff import SCHEMA_VERSION
from tests.test_learning_t0_capture import T0_FREEZE_FILE, _sample_scan
from tests.test_regime_alpha_forward_finalize import _sample_bundle

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _handoff(trade_date: str = "2026-09-22", captured_at: str = "2026-09-22T14:49:12+07:00") -> dict:
    board = _sample_scan(trade_date=trade_date).to_csv(index=False)
    elite = pd.DataFrame([{"MÃ": "AAA", "GIÁ": 10, "KẾT LUẬN": "BUY ELITE"}]).to_csv(index=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "trade_date": trade_date,
        "captured_at": captured_at,
        "trading_today": True,
        "trading_reason": "",
        "market": {
            "market_real": 7,
            "market_live": 6,
            "market_forecast": 5,
            "market_forecast_text": "mid",
            "market_confidence": 70,
            "breadth": 0.4,
            "market_status": "ok",
            "market_action": "watch",
            "market_regime": "TRUNG",
            "market_regime_note": "",
        },
        "frames": {
            "buy_elite": elite,
            "learning_board": board,
            "recommendations": "symbol\nAAA\n",
            "leader_brain": "symbol,leader_score\nAAA,10\n",
            "pattern_library": "pattern_id\np\n",
            "leader_session_snapshot": f"session_date,symbol\n{trade_date},AAA\n",
        },
    }


def _close_scan():
    return {
        "scan_df": pd.DataFrame([{"symbol": "FROM_CLOSE_SCAN", "price": 1, "group": "X"}]),
        "market_real": 8,
        "market_live": 8,
        "market_forecast": 4,
        "market_forecast_text": "close",
        "market_confidence": 90,
        "market_status": "close",
        "market_action": "flat",
        "market_regime": "TRUNG",
        "market_regime_note": "",
        "breadth": 0.2,
        "trading_today": True,
        "trading_reason": "",
    }


def test_missing_handoff_does_not_feed_scan_into_the_three(tmp_path):
    calls = []

    def close_scan():
        calls.append("close_scan")
        return _close_scan()

    def forbid(*_args, **_kwargs):
        raise AssertionError("handoff writer ran without a handoff")

    with mock.patch("modules.post_close_finalize._finalize_forward", forbid), \
         mock.patch("modules.post_close_finalize._finalize_buy_elite", forbid), \
         mock.patch("modules.post_close_finalize._finalize_learning", forbid), \
         mock.patch("modules.post_close_finalize._run_close_writers", lambda *a, **k: calls.append("close_writers") or ({"status": "CAPTURED"}, {"status": "FROZEN"})):
        early = run_post_close_finalize(
            now=datetime(2026, 9, 22, 14, 0, tzinfo=VN),
            close_scan=close_scan,
            mature=False,
        )
        late = run_post_close_finalize(
            now=datetime(2026, 9, 22, 18, 30, tzinfo=VN),
            close_scan=close_scan,
            mature=False,
        )
    assert early["steps"]["forward_shadow"]["status"] == NO_VALID_HANDOFF
    assert early["steps"]["buy_elite"]["status"] == NO_VALID_HANDOFF
    assert early["steps"]["earning_learning"]["status"] == NO_VALID_HANDOFF
    assert early["steps"]["market_t0"]["status"] == BEFORE_CANONICAL_WINDOW
    assert early["close_scan_calls"] == 0
    assert late["steps"]["forward_shadow"]["status"] == NO_VALID_HANDOFF
    assert late["close_scan_calls"] == 1
    assert calls == ["close_scan", "close_writers"]


def test_invalid_handoff_is_not_reconstructed_from_the_close_scan():
    bad = _handoff()
    bad["schema_version"] = "nope"
    calls = []

    def close_scan():
        calls.append("close_scan")
        return _close_scan()

    report = run_post_close_finalize(
        now=datetime(2026, 9, 22, 12, 0, tzinfo=VN),
        handoff=bad,
        close_scan=close_scan,
        mature=False,
    )
    assert report["steps"]["buy_elite"]["status"] == NO_VALID_HANDOFF
    assert report["steps"]["earning_learning"]["status"] == NO_VALID_HANDOFF
    assert report["steps"]["forward_shadow"]["status"] == NO_VALID_HANDOFF
    assert calls == []


def test_handoff_writers_run_before_close_scan_and_do_not_see_it(monkeypatch):
    seen = {}

    def forward(handoff, ledger_path=None):
        seen["forward_board"] = handoff["frames"]["learning_board"]
        return {"ok": True, "status": "FROZEN", "new_rows": 1, "source": "session_handoff_v1"}

    def buy_elite(handoff):
        seen["buy_elite"] = handoff["frames"]["buy_elite"]
        return {"status": "APPENDED", "source": "session_handoff_v1", "session_date": handoff["trade_date"]}

    def learning(handoff, data_dir=None):
        seen["learning"] = handoff["frames"]["learning_board"]
        return {"status": "UPDATED", "source": "session_handoff_v1"}

    def close_writers(payload, **kwargs):
        seen["close_symbol"] = payload["scan_df"]["symbol"].iloc[0]
        return {"status": "CAPTURED", "source": "close_scan"}, {"status": "FROZEN", "source": "close_scan"}

    monkeypatch.setattr("modules.post_close_finalize._finalize_forward", forward)
    monkeypatch.setattr("modules.post_close_finalize._finalize_buy_elite", buy_elite)
    monkeypatch.setattr("modules.post_close_finalize._finalize_learning", learning)
    monkeypatch.setattr("modules.post_close_finalize._run_close_writers", close_writers)
    report = run_post_close_finalize(
        now=datetime(2026, 9, 22, 18, 30, tzinfo=VN),
        handoff=_handoff(),
        close_scan=_close_scan,
        mature=False,
    )
    assert "FROM_CLOSE_SCAN" not in seen["forward_board"]
    assert "FROM_CLOSE_SCAN" not in seen["buy_elite"]
    assert "FROM_CLOSE_SCAN" not in seen["learning"]
    assert seen["close_symbol"] == "FROM_CLOSE_SCAN"
    assert report["steps"]["forward_shadow"]["source"] == "session_handoff_v1"
    assert report["steps"]["market_t0"]["source"] == "close_scan"


def test_after_midnight_keeps_session_handoff_and_closes_market_window(monkeypatch):
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_forward",
        lambda *a, **k: {"ok": True, "status": "FROZEN", "source": "session_handoff_v1"},
    )
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_buy_elite",
        lambda *a, **k: {"status": "APPENDED", "source": "session_handoff_v1", "session_date": "2026-09-22"},
    )
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_learning",
        lambda *a, **k: {"status": "UPDATED", "source": "session_handoff_v1"},
    )
    calls = []
    report = run_post_close_finalize(
        now=datetime(2026, 9, 23, 18, 30, tzinfo=VN),
        session_date="2026-09-22",
        handoff=_handoff(),
        close_scan=lambda: calls.append("scan") or _close_scan(),
        mature=False,
    )
    assert report["steps"]["forward_shadow"]["status"] == "FROZEN"
    assert report["steps"]["market_t0"]["status"] == SAME_DAY_WINDOW_CLOSED
    assert report["steps"]["sweetspot"]["status"] == SAME_DAY_WINDOW_CLOSED
    assert calls == []


def test_replaying_handoff_does_not_add_forward_or_t0_rows(tmp_path):
    rec, brain, exp, shadow = _sample_bundle("2026-09-22")
    ledger_path = tmp_path / "ledger.csv"
    history = pd.DataFrame([{"session_date": "2026-09-22", "symbol": "AAA"}])
    with mock.patch("modules.regime_alpha_shadow.build_shadow_with_recall", return_value=shadow), \
         mock.patch("leader_memory._build_experience_frame", return_value=exp), \
         mock.patch("leader_memory._safe_read_csv", side_effect=AssertionError("disk read")), \
         mock.patch("leader_memory.load_pattern_library", side_effect=AssertionError("disk patterns")), \
         mock.patch("leader_memory.load_recommendations", side_effect=AssertionError("disk recs")):
        first = finalize_forward_shadow_snapshot(
            session_date="2026-09-22",
            trading_today=True,
            market_real=7.0,
            recommendations=rec,
            brain_df=brain,
            patterns_df=pd.DataFrame([{"pattern_id": "p1", "feature_signature": "demo"}]),
            history_df=history,
            ledger_path=ledger_path,
        )
        second = finalize_forward_shadow_snapshot(
            session_date="2026-09-22",
            trading_today=True,
            market_real=7.0,
            recommendations=rec,
            brain_df=brain,
            patterns_df=pd.DataFrame([{"pattern_id": "p1", "feature_signature": "demo"}]),
            history_df=history,
            ledger_path=ledger_path,
        )
    assert first["ok"] is True
    assert second["new_rows"] == 0
    assert first["frozen_rows"] == second["frozen_rows"]

    data_dir = tmp_path / "earning_learning"
    data_dir.mkdir()
    board = _sample_scan(trade_date="2026-09-22")
    from modules.earning_learning import update_learning

    first_learn = update_learning(
        earning_board_df=board,
        market_context={"market_real": 7, "market_live": 6, "market_forecast": 5, "market_regime": "mid"},
        trading_today=True,
        data_dir=data_dir,
        strict=True,
    )
    second_learn = update_learning(
        earning_board_df=board,
        market_context={"market_real": 7, "market_live": 6, "market_forecast": 5, "market_regime": "mid"},
        trading_today=True,
        data_dir=data_dir,
        strict=True,
    )
    freeze = pd.read_csv(data_dir / T0_FREEZE_FILE)
    assert first_learn.get("t0_freeze_added", 0) > 0
    assert second_learn.get("t0_freeze_added", 0) == 0
    assert len(freeze) == first_learn.get("t0_freeze_added")


def test_workflow_cron_permissions_and_secret_names():
    text = Path(__file__).resolve().parents[1].joinpath(".github/workflows/post-close-research.yml").read_text(encoding="utf-8")
    assert 'cron: "30 11 * * 1-5"' in text
    assert 'cron: "30 13 * * 1-5"' in text
    assert "contents: write" in text
    assert "secrets.GITHUB_TOKEN" in text
    assert "vars.POST_CLOSE_RESEARCH_ENABLED == 'true'" in text
    assert "POST_CLOSE_RESEARCH_ENABLED: ${{ vars.POST_CLOSE_RESEARCH_ENABLED }}" in text
    assert "VNSTOCK_API_KEY" not in text
    assert "python -m modules.post_close_finalize" in text
