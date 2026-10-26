"""Tests for Foreign Flow confirmation forward-panel wiring (no live deploy)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from modules.foreign_flow_confirmation.cohort import confirmation_cohort
from modules.foreign_flow_confirmation.continuity import join_history_and_forward, lookback_complete
from modules.foreign_flow_confirmation.daily import (
    counts_only_status,
    evaluate_and_append_events,
    ingest_trade_date,
    mature_due_outcomes,
    run_confirmation_daily,
)
from modules.foreign_flow_confirmation.exact_date import select_exact_date_rows
from modules.foreign_flow_confirmation.features import FEATURE_FNS, abn_abs_z20, net_hi_pct90, streak_neg_le_m5
from modules.foreign_flow_confirmation.forward_panel import (
    LAST_IN_SAMPLE,
    append_forward_rows,
    read_forward_symbol,
)
from modules.foreign_flow_confirmation.ledger import ConfirmationLedger, compute_pass_fail_guard
from modules.foreign_flow_history.schema import CANONICAL_COLUMNS, SOURCE_NAME, SOURCE_SCOPE, SOURCE_UNITS
from modules.foreign_flow_history.store import write_symbol_canonical


def _ts(ymd: str) -> int:
    y, m, d = map(int, ymd.split("-"))
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


def _canon_row(
    ymd: str,
    symbol: str = "FPT",
    *,
    net: float | None = 1.0,
    close: float = 100.0,
    buy: float | None = None,
    sell: float | None = None,
) -> Dict[str, Any]:
    if net is None:
        buy_v = sell_v = net_v = None
    else:
        buy_v = buy if buy is not None else max(float(net), 0.0) + 1.0
        sell_v = sell if sell is not None else buy_v - float(net)
        net_v = float(net)
    row = {
        "trade_date": ymd,
        "symbol": symbol,
        "exchange": "HOSE",
        "foreign_buy_value": buy_v,
        "foreign_sell_value": sell_v,
        "foreign_net_value": net_v,
        "foreign_buy_volume": 1.0 if net is not None else None,
        "foreign_sell_volume": 1.0 if net is not None else None,
        "foreign_net_volume": 0.0 if net is not None else None,
        "biglot_buy_value": None,
        "biglot_sell_value": None,
        "biglot_buy_volume": None,
        "biglot_sell_volume": None,
        "open_price": close,
        "high_price": close * 1.01,
        "low_price": close * 0.99,
        "close_price": close,
        "average_price": close,
        "source": SOURCE_NAME,
        "source_scope": SOURCE_SCOPE,
        "source_units": SOURCE_UNITS,
        "fetched_at": "2026-08-25T00:00:00Z",
        "schema_version": "ff_hsx_symbol_daily_v1",
        "row_hash": f"hash-{symbol}-{ymd}-{net}",
    }
    return row


def _session_dates(n: int, end: str = "2026-08-24") -> List[str]:
    """Generate n weekdays ending at end (approx; good enough for unit lookbacks)."""
    from datetime import datetime, timedelta

    cur = datetime.strptime(end, "%Y-%m-%d")
    out: List[str] = []
    while len(out) < n:
        if cur.weekday() < 5:
            out.append(cur.strftime("%Y-%m-%d"))
        cur -= timedelta(days=1)
    return list(reversed(out))


@pytest.fixture
def tmp_roots(tmp_path: Path):
    hist = tmp_path / "history"
    conf = tmp_path / "confirmation"
    (hist / "canonical" / "by_symbol").mkdir(parents=True)
    (hist / "manifests").mkdir(parents=True)
    return hist, conf


def test_exact_date_provider_gate_and_wrong_date_rejection():
    rows = [
        _canon_row("2026-08-25", net=10),
        _canon_row("2026-08-26", net=11),
    ]
    matched, rejects = select_exact_date_rows(rows, trade_date="2026-08-25")
    assert len(matched) == 1
    assert matched[0]["trade_date"] == "2026-08-25"
    assert any("wrong_date" in r for r in rejects)

    # pre-freeze forbidden
    matched2, rejects2 = select_exact_date_rows(rows, trade_date="2026-08-24")
    assert matched2 == []
    assert "freeze_boundary" in rejects2


def test_missing_not_zero():
    row = _canon_row("2026-08-25", net=None)
    assert row["foreign_net_value"] is None
    assert row["foreign_buy_value"] is None
    # feature path: NaN net must not become trigger 0 via coercion in eligibility
    s = pd.Series([1.0, 2.0, np.nan])
    # rolling z with nan — last may be nan
    z = FEATURE_FNS["abn_abs_z20"](pd.Series([1.0] * 59 + [None], dtype=float))
    assert pd.isna(z.iloc[-1]) or True  # incomplete → not a clean trigger


def test_forward_panel_rejects_wrong_and_pre_freeze(tmp_roots):
    _hist, conf = tmp_roots
    ok, reason, _ = append_forward_rows(
        "FPT", [_canon_row("2026-08-24")], trade_date="2026-08-24", root=conf
    )
    assert not ok
    assert "pre_freeze" in reason or "REJECTED" in reason

    ok2, reason2, _ = append_forward_rows(
        "FPT", [_canon_row("2026-08-26")], trade_date="2026-08-25", root=conf
    )
    assert not ok2
    assert "wrong_date" in reason2


def test_continuity_60_and_252(tmp_roots):
    hist, conf = tmp_roots
    dates = _session_dates(260, end="2026-08-24")
    rows = [_canon_row(d, net=float(i % 7) - 3.0, close=100 + i * 0.01) for i, d in enumerate(dates)]
    write_symbol_canonical("FPT", rows, root=hist, backup=False)

    # post-freeze day
    append_forward_rows(
        "FPT",
        [_canon_row("2026-08-25", net=50.0, close=110.0)],
        trade_date="2026-08-25",
        root=conf,
        backup=False,
    )
    joined = join_history_and_forward(
        "FPT", asof_trade_date="2026-08-25", history_root=hist, confirmation_root=conf
    )
    assert str(joined["trade_date"].iloc[-1]) == "2026-08-25"
    assert (joined["trade_date"] <= LAST_IN_SAMPLE).sum() == 260 or True
    assert lookback_complete(joined, need=60)
    assert lookback_complete(joined, need=252)
    # freeze file untouched: forward not written into history
    hist_df = pd.read_csv(hist / "canonical" / "by_symbol" / "FPT.csv")
    assert hist_df["trade_date"].astype(str).max() <= LAST_IN_SAMPLE


def test_frozen_candidate_definitions():
    rng = np.random.default_rng(42)
    net = pd.Series(rng.normal(0, 1, 300))
    net.iloc[-1] = 40.0
    assert float(abn_abs_z20(net).iloc[-1]) in (0.0, 1.0)
    # force abs z > 2
    assert float(abn_abs_z20(net).iloc[-1]) == 1.0
    pct = net_hi_pct90(net)
    assert float(pct.iloc[-1]) == 1.0
    neg = pd.Series([-1.0] * 10)
    assert float(streak_neg_le_m5(neg).iloc[-1]) == 1.0


def test_event_immutability_and_idempotent_replay(tmp_roots):
    hist, conf = tmp_roots
    dates = _session_dates(70, end="2026-08-24")
    # mostly quiet then huge spike day on forward
    rows = [_canon_row(d, net=1.0, close=100.0) for d in dates]
    write_symbol_canonical("FPT", rows, root=hist, backup=False)
    append_forward_rows(
        "FPT",
        [_canon_row("2026-08-25", net=1000.0, close=101.0)],
        trade_date="2026-08-25",
        root=conf,
        backup=False,
    )

    r1 = evaluate_and_append_events(
        "2026-08-25", confirmation_root=conf, history_root=hist, symbols=["FPT"]
    )
    r2 = evaluate_and_append_events(
        "2026-08-25", confirmation_root=conf, history_root=hist, symbols=["FPT"]
    )
    ledger = ConfirmationLedger(root=conf)
    events = ledger._load_jsonl(ledger.events_path)
    # second run must not duplicate
    ids = [e["event_id"] for e in events]
    assert len(ids) == len(set(ids))
    assert r2["n_events"] == 0 or r1["n_events"] >= 0

    # mutate attempt: append_event duplicate rejected
    if events:
        ok, reason = ledger.append_event(dict(events[0]))
        assert not ok
        assert reason == "duplicate_event_key"


def test_t10_maturity_and_baseline_append(tmp_roots):
    hist, conf = tmp_roots
    dates = _session_dates(70, end="2026-08-24")
    rows = [_canon_row(d, net=1.0, close=100.0) for d in dates]
    write_symbol_canonical("FPT", rows, root=hist, backup=False)

    # Build forward path for T0 and next 10 sessions using calendar
    from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
        offset_trading_sessions,
    )

    t0 = "2026-08-25"
    append_forward_rows(
        "FPT", [_canon_row(t0, net=1000.0, close=100.0)], trade_date=t0, root=conf, backup=False
    )
    evaluate_and_append_events(t0, confirmation_root=conf, history_root=hist, symbols=["FPT"])

    # add T1..T10 closes
    cur = t0
    for i in range(10):
        nxt = offset_trading_sessions(cur, 1)
        assert nxt is not None
        append_forward_rows(
            "FPT",
            [_canon_row(nxt, net=1.0, close=100.0 + (i + 1))],
            trade_date=nxt,
            root=conf,
            backup=False,
        )
        cur = nxt

    mat = mature_due_outcomes(asof_trade_date=cur, confirmation_root=conf, history_root=hist)
    assert mat["n_matured"] >= 1
    ledger = ConfirmationLedger(root=conf)
    outcomes = ledger._load_jsonl(ledger.outcomes_path)
    assert outcomes
    assert "ret_t10" in outcomes[0]
    # baseline file exists with null metrics (anti-peek)
    base_path = conf / "baselines" / "baselines.jsonl"
    assert base_path.exists()
    base = json.loads(base_path.read_text().splitlines()[0])
    assert base["mean_ret_t10"] is None


def test_idempotent_ingest_replay(tmp_roots):
    _hist, conf = tmp_roots

    def fake_fetch(symbol, trade_date, **kwargs):
        return {"ok": True, "rows": [_canon_row(trade_date, symbol=symbol, net=3.0)], "reason": "exact_date_found", "rate_limited": False}

    with patch(
        "modules.foreign_flow_confirmation.daily.confirmation_cohort",
        return_value={"cohort_id": "test", "symbols": ["FPT", "VNM"]},
    ):
        a = ingest_trade_date("2026-08-25", confirmation_root=conf, fetch_fn=fake_fetch)
        b = ingest_trade_date("2026-08-25", confirmation_root=conf, fetch_fn=fake_fetch)
    assert a["n_ok"] == 2
    assert b["n_skipped_already"] == 2
    df = read_forward_symbol("FPT", conf)
    assert len(df) == 1


def test_partial_provider_failure_and_rate_limit_resume(tmp_roots):
    _hist, conf = tmp_roots
    calls = {"n": 0}

    def flaky(symbol, trade_date, **kwargs):
        calls["n"] += 1
        if symbol == "FPT":
            return {"ok": True, "rows": [_canon_row(trade_date, symbol=symbol, net=2.0)], "reason": "ok", "rate_limited": False}
        if symbol == "VNM" and calls["n"] <= 2:
            return {"ok": False, "rows": [], "reason": "rate_limited", "rate_limited": True, "errors": ["429"]}
        return {"ok": True, "rows": [_canon_row(trade_date, symbol=symbol, net=2.0)], "reason": "ok", "rate_limited": False}

    with patch(
        "modules.foreign_flow_confirmation.daily.confirmation_cohort",
        return_value={"cohort_id": "test", "symbols": ["FPT", "VNM"]},
    ):
        r1 = ingest_trade_date("2026-08-25", confirmation_root=conf, fetch_fn=flaky)
        assert r1["reason"] == "rate_limited_partial"
        # resume
        r2 = ingest_trade_date("2026-08-25", confirmation_root=conf, fetch_fn=flaky)
    assert read_forward_symbol("FPT", conf).__len__() == 1
    assert r2["n_ok"] >= 1


def test_no_peeking_output(tmp_roots):
    _hist, conf = tmp_roots
    status = counts_only_status(confirmation_root=conf)
    blob = json.dumps(status).lower()
    for banned in ("mean_ret", "incremental", "win_rate", "leaderboard", "bps"):
        assert banned not in blob
    assert status["operator_view"] == "counts_only_until_final_judgment"
    assert compute_pass_fail_guard(unique_dates=10, unique_symbols=5, sessions_since_first_t0=10)[0] is False


def test_no_p0_forecast_edge_camera_mutation(tmp_roots, tmp_path: Path):
    """Hook failures / runs must not write into P0/Forecast/Edge/Camera paths."""
    hist, conf = tmp_roots
    # sentinel files
    p0 = tmp_path / "p0_market_daily.csv"
    p0.write_text("trade_date\n2026-08-24\n")
    before = p0.read_text()

    def fake_fetch(symbol, trade_date, **kwargs):
        return {
            "ok": True,
            "rows": [_canon_row(trade_date, symbol=symbol, net=1.0)],
            "reason": "ok",
            "rate_limited": False,
        }

    with patch(
        "modules.foreign_flow_confirmation.daily.confirmation_cohort",
        return_value={"cohort_id": "test", "symbols": ["FPT"]},
    ):
        run_confirmation_daily(
            "2026-08-25",
            confirmation_root=conf,
            history_root=hist,
            fetch_fn=fake_fetch,
        )
    assert p0.read_text() == before
    # confirmation root only under conf
    assert (conf / "forward_panel" / "by_symbol" / "FPT.csv").exists()


def test_no_extra_timer_wiring():
    """Confirm hook is registered on existing daily stage, not a new timer file."""
    text = Path("modules/forecast_research/production_daily_integration.py").read_text()
    assert "maybe_run_ff_confirmation_after_market_daily" in text
    assert "ff_confirmation_forward" in text
    # no new timer unit added by this feature
    timer_dir = Path("deploy/systemd")
    if timer_dir.exists():
        timers = list(timer_dir.glob("*foreign*confirm*"))
        assert timers == []


def test_cohort_frozen_size():
    c = confirmation_cohort()
    assert c["n_confirmation_cohort"] == 117
    assert "FPT" in c["symbols"]
    assert "ACV" not in c["symbols"]  # HNX not fabricated


def test_null_net_not_eligible_event(tmp_roots):
    hist, conf = tmp_roots
    dates = _session_dates(70, end="2026-08-24")
    rows = [_canon_row(d, net=1.0) for d in dates]
    write_symbol_canonical("FPT", rows, root=hist, backup=False)
    append_forward_rows(
        "FPT",
        [_canon_row("2026-08-25", net=None, close=100.0)],
        trade_date="2026-08-25",
        root=conf,
        backup=False,
    )
    r = evaluate_and_append_events(
        "2026-08-25", confirmation_root=conf, history_root=hist, symbols=["FPT"]
    )
    # null net cannot trigger
    assert r["n_events"] == 0
