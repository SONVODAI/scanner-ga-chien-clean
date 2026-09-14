"""Pattern History write gate: skip non-trading days, persist on trading days."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import pattern_manager as pm

REPO = Path(__file__).resolve().parents[1]


def _learning_scan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "group": "MUA EARLY",
                "price": 10.0,
                "total_score": 80,
                "E": 1,
                "R": 1,
                "O": 1,
                "S": 1,
                "RS": 1,
                "V": 1,
                "rsi14": 55.0,
                "ema9_ma20_slope": 0.5,
                "dist_from_ema9_pct": 0.1,
                "obv_status": "🟢",
                "volume": 1000,
                "vol_ma20": 800,
                "green_2_confirm": False,
                "early_green2": False,
                "early_dry_green2": False,
                "warning": "",
            }
        ]
    )


@pytest.fixture
def isolated_pattern_file(tmp_path, monkeypatch):
    path = tmp_path / "pattern_history.csv"
    monkeypatch.setattr(pm, "PATTERN_FILE", str(path))
    monkeypatch.setattr(pm, "get_github_token", lambda: None)
    return path


def test_save_pattern_history_not_persisted_on_non_trading_day(isolated_pattern_file, monkeypatch):
    writes: list[pd.DataFrame] = []

    def _capture_write(df):
        writes.append(df)
        raise AssertionError("write_pattern_history must not run on a non-trading day")

    monkeypatch.setattr(pm, "write_pattern_history", _capture_write)
    before = isolated_pattern_file.read_bytes() if isolated_pattern_file.exists() else b""

    history, status = pm.save_pattern_history(
        None,
        _learning_scan(),
        3.4,
        0.0,
        allow_save=False,
        reason="VNINDEX weekend",
    )

    after = isolated_pattern_file.read_bytes() if isolated_pattern_file.exists() else b""
    assert writes == []
    assert before == after
    assert not isolated_pattern_file.exists()
    assert status.startswith("SKIP_NO_TRADING_SESSION")
    assert "VNINDEX weekend" in status
    assert history is not None


def test_save_pattern_history_persists_on_trading_day(isolated_pattern_file):
    assert not isolated_pattern_file.exists()
    history, status = pm.save_pattern_history(
        None,
        _learning_scan(),
        3.4,
        0.0,
        allow_save=True,
        reason="VNINDEX trading",
    )
    assert isolated_pattern_file.exists()
    assert status == "LOCAL_ONLY"
    assert not history.empty
    saved = pd.read_csv(isolated_pattern_file)
    assert "AAA" in set(saved["symbol"].astype(str).str.upper())
    assert float(saved["market_real"].iloc[0]) == pytest.approx(3.4)


def test_app_derives_trading_today_before_both_pattern_history_saves():
    src = (REPO / "app.py").read_text(encoding="utf-8")
    gate = src.index("trading_today, trading_reason = is_vnindex_trading_today()")
    first = src.index("save_pattern_history(")
    second = src.index("save_pattern_history(", first + 1)
    assert src.find("save_pattern_history(", second + 1) == -1
    assert gate < first < second

    first_block = src[first : src.index(")", first) + 1]
    second_block = src[second : src.index(")", second) + 1]
    assert "allow_save=trading_today" in first_block
    assert "reason=trading_reason" in first_block
    assert "allow_save=trading_today" in second_block
    assert "reason=trading_reason" in second_block
    assert "def is_vnindex_trading_today()" in src
