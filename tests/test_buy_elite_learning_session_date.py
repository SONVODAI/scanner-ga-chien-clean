"""BUY ELITE append keeps session D when the job clock is the next morning."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from modules.buy_elite_learning import append_today_buy_elite_signals, run_buy_elite_learning_cycle
from modules.live_candidate.contract import FIRST_SEEN_COL

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _elite(n: int = 1) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "MÃ": f"S{i:02d}",
                "GIÁ": 10 + i,
                "KẾT LUẬN": "BUY ELITE",
                "EliteScore": 80,
            }
            for i in range(n)
        ]
    )


def test_session_date_survives_next_morning_clock(monkeypatch, tmp_path):
    monkeypatch.setattr("modules.buy_elite_learning.today_str", lambda: "2026-09-23")
    monkeypatch.setattr(
        "modules.buy_elite_learning.vn_now",
        lambda: datetime(2026, 9, 23, 8, 15, tzinfo=VN),
    )
    monkeypatch.setattr(
        "modules.live_shadow_transport.watchlist_bus.persist_and_publish_research_watchlist",
        lambda *args, **kwargs: None,
    )
    observed = datetime(2026, 9, 22, 14, 49, 12, tzinfo=VN)
    hist = append_today_buy_elite_signals(
        pd.DataFrame(),
        _elite(31),
        market_real=7,
        market_forecast=5,
        allow_save=True,
        session_date="2026-09-22",
        observed_at=observed,
    )
    assert len(hist) == 30
    assert set(hist["date"].astype(str)) == {"2026-09-22"}
    assert set(hist["time"].astype(str)) == {"14:49:12"}
    assert "2026-09-23" not in set(hist["date"].astype(str))
    first = hist.loc[hist["symbol"].astype(str) == "S00", FIRST_SEEN_COL].iloc[0]
    again = append_today_buy_elite_signals(
        hist,
        _elite(1),
        market_real=9,
        market_forecast=5,
        allow_save=True,
        session_date="2026-09-22",
        observed_at=datetime(2026, 9, 22, 14, 55, tzinfo=VN),
    )
    kept = again.loc[again["symbol"].astype(str) == "S00", FIRST_SEEN_COL].iloc[0]
    assert kept == first
    assert kept


def test_omitted_session_date_still_uses_today(monkeypatch):
    monkeypatch.setattr("modules.buy_elite_learning.today_str", lambda: "2026-09-22")
    monkeypatch.setattr(
        "modules.buy_elite_learning.vn_now",
        lambda: datetime(2026, 9, 22, 14, 20, tzinfo=VN),
    )
    monkeypatch.setattr(
        "modules.live_shadow_transport.watchlist_bus.persist_and_publish_research_watchlist",
        lambda *args, **kwargs: None,
    )
    hist = append_today_buy_elite_signals(
        pd.DataFrame(),
        _elite(1),
        market_real=7,
        market_forecast=5,
        allow_save=True,
    )
    assert hist["date"].iloc[0] == "2026-09-22"
    assert hist["time"].iloc[0] == "14:20:00"


def test_cycle_writes_session_date_not_job_date(monkeypatch, tmp_path):
    history = tmp_path / "history.csv"
    profile = tmp_path / "profile.json"
    monkeypatch.setattr("modules.buy_elite_learning.HISTORY_FILE", str(history))
    monkeypatch.setattr("modules.buy_elite_learning.PROFILE_FILE", str(profile))
    monkeypatch.setattr("modules.buy_elite_learning.today_str", lambda: "2026-09-23")
    monkeypatch.setattr(
        "modules.buy_elite_learning.vn_now",
        lambda: datetime(2026, 9, 23, 7, 0, tzinfo=VN),
    )
    monkeypatch.setattr("modules.buy_elite_learning._github_token", lambda: None)
    monkeypatch.setattr(
        "modules.live_shadow_transport.watchlist_bus.persist_and_publish_research_watchlist",
        lambda *args, **kwargs: None,
    )
    saved, _profile, _hist_status, _profile_status = run_buy_elite_learning_cycle(
        buy_elite_df=_elite(1),
        scan_df=pd.DataFrame([{"symbol": "S00", "price": 11}]),
        market_real=7,
        market_forecast=5,
        trading_today=True,
        session_date="2026-09-22",
        observed_at=datetime(2026, 9, 22, 14, 49, tzinfo=VN),
    )
    assert set(saved["date"].astype(str)) == {"2026-09-22"}
    assert "2026-09-23" not in history.read_text(encoding="utf-8")
