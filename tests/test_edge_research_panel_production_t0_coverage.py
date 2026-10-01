"""Regression: research panel must include current EOD T0 without outcome maturity."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.edge_research.adapters import (
    build_research_panel,
    load_lifecycle,
    load_observations,
    load_production_t0_stock_frame,
    load_t0_observation_freeze,
)


def test_production_t0_panel_covers_observation_dates_beyond_lifecycle() -> None:
    obs = load_observations()
    lc = load_lifecycle()
    assert not obs.empty
    obs_dates = set(pd.to_datetime(obs["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").dropna())
    lc_dates = set(pd.to_datetime(lc["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").dropna())
    ahead = sorted(obs_dates - lc_dates)
    assert ahead, "fixture expects observations ahead of outcome-gated lifecycle"

    legacy = build_research_panel(source="pattern_lifecycle")
    legacy_dates = set(pd.to_datetime(legacy["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").dropna())
    assert max(legacy_dates) == max(lc_dates)

    panel = build_research_panel()  # default production_t0
    panel_dates = set(pd.to_datetime(panel["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").dropna())
    assert max(panel_dates) == max(obs_dates)
    for d in ahead:
        assert d in panel_dates
        n = int((panel["trade_date"].astype(str) == d).sum())
        assert n >= 100, f"{d} underpopulated: {n}"


def test_missing_eod_dates_safe_in_panel_with_core_fields() -> None:
    panel = build_research_panel()
    freeze = load_t0_observation_freeze()
    freeze_dates = set(pd.to_datetime(freeze["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").dropna())
    for d in ("2026-08-20", "2026-08-21", "2026-08-24"):
        if d not in freeze_dates:
            continue
        sub = panel[panel["trade_date"].astype(str) == d]
        assert len(sub) >= 100
        assert sub["symbol"].nunique() >= 100
        for col in ("close", "rsi14", "rs5", "rs10", "rs_spread"):
            assert col in sub.columns
            assert sub[col].notna().mean() > 0.9


def test_freeze_overlay_preferred_over_observation_duplicate() -> None:
    frame = load_production_t0_stock_frame()
    assert not frame.empty
    # No duplicate symbol/date after overlay
    keys = frame.assign(
        trade_date=pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    )
    dup = keys.duplicated(subset=["trade_date", "symbol"]).sum()
    assert dup == 0


def test_legacy_lifecycle_source_still_available() -> None:
    panel = build_research_panel(source="pattern_lifecycle")
    assert not panel.empty
    lc = load_lifecycle()
    assert pd.to_datetime(panel["trade_date"]).max() == pd.to_datetime(lc["trade_date"]).max()
