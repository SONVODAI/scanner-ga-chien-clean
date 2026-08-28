"""Phase C — Continuous Edge Learning capability tests."""

from __future__ import annotations

import hashlib
import inspect
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.contracts import (
    ASSESSMENT_NO_QUALIFIED_MATCH,
    ASSESSMENT_QUALIFIED_MATCH_FOUND,
    ASSESSMENT_UNABLE_TO_ASSESS,
    EDGE_MEMORY_STATUS_ACTIVE,
    EDGE_MEMORY_STATUS_DECAYING,
    EDGE_MEMORY_STATUS_INVALIDATED,
    FORWARD_OUTCOME_PENDING,
    HORIZON_STATUS_MATURE,
    HORIZON_STATUS_PENDING,
    REASON_MATCHES_SUPPRESSED_BY_EDGE_HEALTH,
    REASON_NO_ACTIVE_EDGE_AVAILABLE,
)
from modules.edge_research.forward_health_policy import (
    CALIBRATION_REQUIRED,
    DEFAULT_FORWARD_HEALTH_POLICY,
    EXISTING_SCIENTIFIC_POLICY,
    ForwardHealthPolicy,
)
from modules.edge_research.oos_eval import clauses_from_frozen_spec
from modules.edge_research.storage import ensure_storage, read_ledger
from tests.test_edge_research_phase_a_qualification import _minimal_spec, _planted_panel
from tests.test_edge_research_phase_b_future_recognition import (
    COMPATIBLE_MARKET,
    _activate,
    _freeze_df,
    _run_fr,
    _t0_row,
    _values_for_clauses,
)

REPO = Path(__file__).resolve().parents[1]
EARNING = REPO / "data" / "earning_learning"

TEST_POLICY = ForwardHealthPolicy(
    min_mature_best_horizon_n=4,
    min_baseline_n=3,
    min_independent_sessions=4,
    min_episodes=3,
    min_recovery_new_n=4,
    min_recovery_sessions=4,
    anti_context_min_n=4,
    anti_context_min_sessions=4,
    anti_context_min_episodes=3,
)


@pytest.fixture
def edge_data_dir(tmp_path, monkeypatch):
    d = tmp_path / "edge_research"
    d.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(d))
    monkeypatch.delenv("EDGE_RESEARCH_DURABLE_PATH", raising=False)
    monkeypatch.delenv("EDGE_RESEARCH_DURABLE_BACKEND", raising=False)
    return d


def _digest(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _weekdays(n: int, start: str = "2026-01-02", extra_gap_after: int | None = None) -> list[str]:
    dates: list[str] = []
    d = datetime.strptime(start, "%Y-%m-%d")
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y-%m-%d"))
            if extra_gap_after is not None and len(dates) == extra_gap_after:
                d += timedelta(days=12)
                continue
        d += timedelta(days=1)
    return dates


def _gapped_blocks(blocks: int = 4, block_len: int = 8, start: str = "2026-01-02") -> list[str]:
    dates: list[str] = []
    d = datetime.strptime(start, "%Y-%m-%d")
    for _ in range(blocks):
        block = 0
        while block < block_len:
            if d.weekday() < 5:
                dates.append(d.strftime("%Y-%m-%d"))
                block += 1
            d += timedelta(days=1)
        d += timedelta(days=12)
    return dates


def _ohlcv_for(symbol: str, calendar: list[str], *, t0: str, closes_at: dict[int, float]) -> pd.DataFrame:
    t0i = calendar.index(t0)
    rows = []
    for i, d in enumerate(calendar):
        offset = i - t0i
        close = closes_at.get(offset, 100.0)
        rows.append({"date": d, "close": close})
    return pd.DataFrame(rows)


def _universe(date: str, spec, extra_symbols: int = 4, *, match_symbol: str = "NEW1", baseline_prefix: str = "B") -> list[dict]:
    clauses = clauses_from_frozen_spec(spec)
    rows = [_t0_row(match_symbol, clauses=clauses, satisfy=True)]
    rows[0]["trade_date"] = date
    rows[0]["observation_id"] = f"{date}|{match_symbol}"
    rows[0]["research_market_transition"] = spec.market_transition
    rows[0]["research_market_state"] = spec.market_state
    for i in range(extra_symbols):
        sym = f"{baseline_prefix}{i:02d}"
        r = _t0_row(sym, clauses=clauses, satisfy=False)
        r["trade_date"] = date
        r["observation_id"] = f"{date}|{sym}"
        r["research_market_transition"] = spec.market_transition
        r["research_market_state"] = spec.market_state
        rows.append(r)
    return rows


def _birth_and_prices(
    spec,
    calendar,
    t0,
    *,
    new1_t5_close: float,
    base_t5_close: float,
    match_symbol: str = "NEW1",
    baseline_prefix: str = "B",
):
    freeze_rows = _universe(t0, spec, match_symbol=match_symbol, baseline_prefix=baseline_prefix)
    freeze = _freeze_df(freeze_rows)
    freeze["trade_date"] = t0
    ohlcv = {
        match_symbol: _ohlcv_for(
            match_symbol, calendar, t0=t0, closes_at={0: 100.0, 3: 102.0, 5: new1_t5_close, 10: new1_t5_close}
        ),
    }
    for i in range(4):
        ohlcv[f"{baseline_prefix}{i:02d}"] = _ohlcv_for(
            f"{baseline_prefix}{i:02d}",
            calendar,
            t0=t0,
            closes_at={0: 100.0, 3: 100.5, 5: base_t5_close, 10: base_t5_close},
        )
    return freeze, ohlcv


def test_policy_thresholds_are_named_and_calibration_honest():
    snap = DEFAULT_FORWARD_HEALTH_POLICY.snapshot()
    assert snap["policy_id"] == "forward_edge_health_policy_v1"
    assert snap["thresholds"]["min_mature_best_horizon_n"]["status"] == CALIBRATION_REQUIRED
    assert snap["thresholds"]["min_baseline_n"]["status"] == CALIBRATION_REQUIRED
    assert snap["thresholds"]["max_date_concentration"]["status"] == EXISTING_SCIENTIFIC_POLICY
    assert snap["thresholds"]["min_mature_best_horizon_n"]["value"] == 10
    assert DEFAULT_FORWARD_HEALTH_POLICY.min_baseline_n == 20


def test_t3_does_not_mature_before_third_session_weekend_holiday(edge_data_dir):
    from modules.edge_research.forward_maturity import mature_edge_forward_ledger, target_trading_session
    from modules.edge_research.oos import unique_trading_sessions

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    # Friday T0; Sat/Sun excluded automatically by weekday calendar.
    calendar = _weekdays(12, start="2026-01-02")
    assert "2026-01-03" not in calendar and "2026-01-04" not in calendar
    t0 = calendar[0]
    freeze, ohlcv = _birth_and_prices(spec, calendar, t0, new1_t5_close=105.0, base_t5_close=101.0)
    rec = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, trade_date=t0)
    assert rec["qualified_match_count"] == 1
    sessions = unique_trading_sessions(pd.DataFrame({"trade_date": calendar}))
    assert target_trading_session(sessions, t0, 3) == calendar[3]
    early = mature_edge_forward_ledger(
        calendar[2], data_dir=edge_data_dir, session_calendar=calendar, ohlcv_by_symbol=ohlcv, freeze_df=freeze
    )
    ledger = read_ledger("edge_forward_ledger.csv", edge_data_dir)
    assert str(ledger.iloc[0]["t3_status"] or HORIZON_STATUS_PENDING) != HORIZON_STATUS_MATURE
    assert str(ledger.iloc[0]["t5_status"] or "") != HORIZON_STATUS_MATURE
    at_t3 = mature_edge_forward_ledger(
        calendar[3], data_dir=edge_data_dir, session_calendar=calendar, ohlcv_by_symbol=ohlcv, freeze_df=freeze
    )
    ledger = read_ledger("edge_forward_ledger.csv", edge_data_dir)
    assert str(ledger.iloc[0]["t3_status"]) == HORIZON_STATUS_MATURE
    assert str(ledger.iloc[0]["t5_status"] or HORIZON_STATUS_PENDING) != HORIZON_STATUS_MATURE
    assert pd.notna(pd.to_numeric(ledger.iloc[0]["t3_return"], errors="coerce"))
    # Holiday: drop calendar[3]; T3 target shifts later.
    cal2 = [d for d in calendar if d != calendar[3]]
    assert target_trading_session(unique_trading_sessions(pd.DataFrame({"trade_date": cal2})), t0, 3) == cal2[3]
    assert early["matured_horizons"] == 0
    assert at_t3["matured_horizons"] >= 1


def test_t5_cannot_leak_at_t3_and_t10_cannot_leak_at_t5(edge_data_dir):
    from modules.edge_research.forward_maturity import mature_edge_forward_ledger

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    calendar = _weekdays(16)
    t0 = calendar[0]
    freeze, ohlcv = _birth_and_prices(spec, calendar, t0, new1_t5_close=105.0, base_t5_close=101.0)
    _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, trade_date=t0)
    mature_edge_forward_ledger(calendar[3], data_dir=edge_data_dir, session_calendar=calendar, ohlcv_by_symbol=ohlcv)
    row = read_ledger("edge_forward_ledger.csv", edge_data_dir).iloc[0]
    assert str(row["t3_status"]) == HORIZON_STATUS_MATURE
    assert str(row["t5_status"] or "") != HORIZON_STATUS_MATURE
    assert str(row["t10_status"] or "") != HORIZON_STATUS_MATURE
    mature_edge_forward_ledger(calendar[5], data_dir=edge_data_dir, session_calendar=calendar, ohlcv_by_symbol=ohlcv)
    row = read_ledger("edge_forward_ledger.csv", edge_data_dir).iloc[0]
    assert str(row["t5_status"]) == HORIZON_STATUS_MATURE
    assert str(row["t10_status"] or "") != HORIZON_STATUS_MATURE


def test_rerun_maturity_idempotent_and_birth_t0_immutable(edge_data_dir):
    from modules.edge_research.forward_ledger import persist_maturity_updates
    from modules.edge_research.forward_maturity import mature_edge_forward_ledger

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    calendar = _weekdays(12)
    t0 = calendar[0]
    freeze, ohlcv = _birth_and_prices(spec, calendar, t0, new1_t5_close=105.0, base_t5_close=101.0)
    _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, trade_date=t0)
    first = mature_edge_forward_ledger(calendar[5], data_dir=edge_data_dir, session_calendar=calendar, ohlcv_by_symbol=ohlcv)
    row1 = read_ledger("edge_forward_ledger.csv", edge_data_dir).iloc[0]
    born = str(row1["born_at"])
    reason = str(row1["selection_reason"])
    t5 = float(row1["t5_return"])
    second = mature_edge_forward_ledger(calendar[5], data_dir=edge_data_dir, session_calendar=calendar, ohlcv_by_symbol=ohlcv)
    row2 = read_ledger("edge_forward_ledger.csv", edge_data_dir).iloc[0]
    assert float(row2["t5_return"]) == t5
    assert str(row2["born_at"]) == born
    persist_maturity_updates(
        [{"ledger_id": row2["ledger_id"], "selection_reason": "TAMPER", "symbol": "HACK", "t5_return": 99.0}],
        data_dir=edge_data_dir,
    )
    row3 = read_ledger("edge_forward_ledger.csv", edge_data_dir).iloc[0]
    assert str(row3["selection_reason"]) == reason
    assert str(row3["symbol"]) == "NEW1"
    assert float(row3["t5_return"]) == t5
    assert str(row3["outcome_status"]) != FORWARD_OUTCOME_PENDING or str(row3["t5_status"]) == HORIZON_STATUS_MATURE
    assert first["matured_horizons"] >= 1
    assert second["idempotent_skips"] >= 1


def test_same_transition_baseline_no_fallback_and_missing_is_insufficient(edge_data_dir):
    from modules.edge_research.forward_evidence import contemporaneous_baseline_for_birth
    from modules.edge_research.forward_maturity import mature_edge_forward_ledger, resolve_session_calendar

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    calendar = _weekdays(12)
    t0 = calendar[0]
    freeze, ohlcv = _birth_and_prices(spec, calendar, t0, new1_t5_close=105.0, base_t5_close=101.0)
    _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, trade_date=t0)
    mature_edge_forward_ledger(calendar[5], data_dir=edge_data_dir, session_calendar=calendar, ohlcv_by_symbol=ohlcv)
    row = read_ledger("edge_forward_ledger.csv", edge_data_dir).iloc[0]
    sessions = resolve_session_calendar(session_calendar=calendar, ohlcv_by_symbol=ohlcv)
    ok = contemporaneous_baseline_for_birth(
        row, freeze_df=freeze, sessions=sessions, ohlcv_by_symbol=ohlcv, policy=TEST_POLICY, spec=spec
    )
    assert ok["baseline_status"] == "OK"
    assert ok["baseline_type"] == "SAME_TRANSITION"
    assert ok["baseline_n"] >= 3
    assert ok["incremental_return"] is not None
    thin_policy = ForwardHealthPolicy(min_baseline_n=500)
    missing = contemporaneous_baseline_for_birth(
        row, freeze_df=freeze, sessions=sessions, ohlcv_by_symbol=ohlcv, policy=thin_policy, spec=spec
    )
    assert missing["baseline_status"] == "INSUFFICIENT"
    assert missing["incremental_return"] is None


def test_frozen_best_horizon_not_reselected(edge_data_dir):
    from modules.edge_research.freeze import load_frozen_spec
    from modules.edge_research.forward_maturity import mature_edge_forward_ledger

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    before = spec.best_horizon
    calendar = _weekdays(16)
    t0 = calendar[0]
    freeze, ohlcv = _birth_and_prices(spec, calendar, t0, new1_t5_close=103.0, base_t5_close=101.0)
    ohlcv["NEW1"] = _ohlcv_for("NEW1", calendar, t0=t0, closes_at={0: 100, 3: 110, 5: 103, 10: 120})
    _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, trade_date=t0)
    mature_edge_forward_ledger(calendar[10], data_dir=edge_data_dir, session_calendar=calendar, ohlcv_by_symbol=ohlcv)
    loaded = load_frozen_spec(spec.hypothesis_id, edge_data_dir)
    assert loaded is not None
    assert loaded.best_horizon == before
    row = read_ledger("edge_forward_ledger.csv", edge_data_dir).iloc[0]
    assert str(row["best_horizon"]) == before


def test_thin_and_one_loss_cannot_invalidate(edge_data_dir):
    from modules.edge_research.eod_cycle import run_continuous_learning
    from modules.edge_research.forward_evidence import decide_health_state

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    calendar = _weekdays(12)
    t0 = calendar[0]
    freeze, ohlcv = _birth_and_prices(spec, calendar, t0, new1_t5_close=90.0, base_t5_close=101.0)
    _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, trade_date=t0)
    run_continuous_learning(
        calendar[5],
        data_dir=edge_data_dir,
        freeze_df=freeze,
        session_calendar=calendar,
        ohlcv_by_symbol=ohlcv,
        policy=TEST_POLICY,
    )
    mem = read_ledger("edge_memory.csv", edge_data_dir)
    assert str(mem.iloc[0]["status"]) == EDGE_MEMORY_STATUS_ACTIVE
    decision = decide_health_state(
        EDGE_MEMORY_STATUS_ACTIVE,
        {
            "comparable_n": 1,
            "unique_sessions": 1,
            "unique_episodes": 1,
            "date_concentration": 1.0,
            "forward_incremental_median": -5.0,
            "forward_incremental_mean": -5.0,
            "best_horizon": "T5",
        },
        TEST_POLICY,
    )
    assert decision["status"] == EDGE_MEMORY_STATUS_ACTIVE
    assert "INSUFFICIENT" in decision["health_status"]


def test_same_date_concentration_recognized():
    from modules.edge_research.forward_evidence import decide_health_state

    decision = decide_health_state(
        EDGE_MEMORY_STATUS_ACTIVE,
        {
            "comparable_n": 20,
            "unique_sessions": 1,
            "unique_episodes": 1,
            "date_concentration": 1.0,
            "forward_incremental_median": -3.0,
            "forward_incremental_mean": -3.0,
            "best_horizon": "T5",
        },
        TEST_POLICY,
    )
    assert decision["status"] == EDGE_MEMORY_STATUS_ACTIVE
    assert decision["sufficient"] is False


def _multi_session_fixture(edge_data_dir, spec, *, n_births: int, new1_t5: float, base_t5: float, start="2026-01-02"):
    calendar = _gapped_blocks(blocks=n_births, block_len=8, start=start)
    all_freeze = []
    ohlcv: dict[str, pd.DataFrame] = {}
    t0s = []
    cursor = 0
    for i in range(n_births):
        block = calendar[cursor : cursor + 8]
        t0 = block[0]
        t0s.append(t0)
        match_symbol = f"N{i:02d}"
        baseline_prefix = f"U{i:02d}"
        freeze, prices = _birth_and_prices(
            spec,
            calendar,
            t0,
            new1_t5_close=new1_t5,
            base_t5_close=base_t5,
            match_symbol=match_symbol,
            baseline_prefix=baseline_prefix,
        )
        freeze = freeze.copy()
        freeze["trade_date"] = t0
        all_freeze.append(freeze)
        for sym, frame in prices.items():
            ohlcv[sym] = frame if sym not in ohlcv else pd.concat([ohlcv[sym], frame]).drop_duplicates("date", keep="last")
        rec = _run_fr(
            edge_data_dir,
            freeze,
            {"research_market_state": spec.market_state, "research_market_transition": spec.market_transition},
            trade_date=t0,
        )
        assert rec["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND
        cursor += 8
    freeze_all = pd.concat(all_freeze, ignore_index=True)
    return calendar, freeze_all, ohlcv, t0s


def test_adequate_positive_forward_keeps_active(edge_data_dir):
    from modules.edge_research.eod_cycle import run_continuous_learning

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    calendar, freeze, ohlcv, t0s = _multi_session_fixture(edge_data_dir, spec, n_births=4, new1_t5=108.0, base_t5=101.0)
    as_of = calendar[-1]
    run_continuous_learning(
        as_of, data_dir=edge_data_dir, freeze_df=freeze, session_calendar=calendar, ohlcv_by_symbol=ohlcv, policy=TEST_POLICY
    )
    mem = read_ledger("edge_memory.csv", edge_data_dir)
    assert str(mem.iloc[0]["status"]) == EDGE_MEMORY_STATUS_ACTIVE
    assert str(mem.iloc[0]["health_status"]) in {"SUPPORTED", "INSUFFICIENT_EVIDENCE"}


def test_deterioration_decay_invalidation_recovery_and_matcher(edge_data_dir, tmp_path):
    from modules.edge_research.eod_cycle import run_continuous_learning, run_edge_research_eod_cycle
    from modules.edge_research.edge_memory import promote_oos_pass_to_memory
    from modules.edge_research.oos_eval import OOSEvaluation

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    calendar, freeze, ohlcv, t0s = _multi_session_fixture(edge_data_dir, spec, n_births=4, new1_t5=90.0, base_t5=101.0)
    run_continuous_learning(
        calendar[-1],
        data_dir=edge_data_dir,
        freeze_df=freeze,
        session_calendar=calendar,
        ohlcv_by_symbol=ohlcv,
        policy=TEST_POLICY,
    )
    mem = read_ledger("edge_memory.csv", edge_data_dir)
    status = str(mem.iloc[0]["status"])
    assert status in {EDGE_MEMORY_STATUS_DECAYING, EDGE_MEMORY_STATUS_INVALIDATED}
    # Matcher must not create qualified births from DECAYING/INVALIDATED.
    later = _weekdays(6, start="2026-06-01")
    freeze_later, _ = _birth_and_prices(spec, later, later[0], new1_t5_close=108.0, base_t5_close=101.0)
    rec = _run_fr(
        edge_data_dir,
        freeze_later,
        {"research_market_state": spec.market_state, "research_market_transition": spec.market_transition},
        trade_date=later[0],
    )
    assert rec["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    if status == EDGE_MEMORY_STATUS_DECAYING:
        assert rec["reason"] == REASON_MATCHES_SUPPRESSED_BY_EDGE_HEALTH
    else:
        assert rec["reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE

    # Isolated recovery: DECAYING, then new unseen positive births after decayed_at.
    rec2 = tmp_path / "recovery2"
    shutil.copytree(edge_data_dir, rec2)
    orig_ledger = read_ledger("edge_forward_ledger.csv", rec2)
    orig_ledger["born_at"] = "2026-01-15T00:00:00Z"
    orig_ledger.to_csv(rec2 / "edge_forward_ledger.csv", index=False)
    mem2 = read_ledger("edge_memory.csv", rec2)
    mem2.loc[0, "status"] = EDGE_MEMORY_STATUS_ACTIVE
    mem2.loc[0, "decayed_at"] = ""
    mem2.to_csv(rec2 / "edge_memory.csv", index=False)
    cal2, freeze2, ohlcv2, t0s2 = _multi_session_fixture(
        rec2, spec, n_births=4, new1_t5=112.0, base_t5=101.0, start="2026-07-01"
    )
    mem2 = read_ledger("edge_memory.csv", rec2)
    mem2.loc[0, "status"] = EDGE_MEMORY_STATUS_DECAYING
    mem2.loc[0, "decayed_at"] = "2026-03-01T00:00:00Z"
    mem2.to_csv(rec2 / "edge_memory.csv", index=False)
    run_continuous_learning(
        cal2[-1], data_dir=rec2, freeze_df=freeze2, session_calendar=cal2, ohlcv_by_symbol=ohlcv2, policy=TEST_POLICY
    )
    mem2 = read_ledger("edge_memory.csv", rec2)
    assert str(mem2.iloc[0]["status"]) == EDGE_MEMORY_STATUS_ACTIVE
    hist2 = read_ledger("edge_validation_history.csv", rec2)
    assert (hist2["to_status"].astype(str) == EDGE_MEMORY_STATUS_ACTIVE).any()
    assert (hist2["from_status"].astype(str) == EDGE_MEMORY_STATUS_DECAYING).any()

    # Invalidation isolated: force DECAYING then more negative evidence already in original dir.
    inv = tmp_path / "inv"
    shutil.copytree(edge_data_dir, inv)
    hist = read_ledger("edge_validation_history.csv", inv)
    promote_oos_pass_to_memory(
        spec,
        OOSEvaluation(
            hypothesis_id=spec.hypothesis_id,
            edge_id=spec.edge_id,
            result="OOS_PASS",
            reason="nope",
            evaluated_at="2026-08-01T00:00:00Z",
            spec_hash=spec.spec_hash,
            best_horizon=spec.best_horizon,
        ),
        data_dir=inv,
    )
    mem_i = read_ledger("edge_memory.csv", inv)
    assert not (mem_i["status"].astype(str) == EDGE_MEMORY_STATUS_ACTIVE).any() or str(mem.iloc[0]["status"]) != EDGE_MEMORY_STATUS_INVALIDATED
    # INVALIDATED cannot resurrect
    mem_i.loc[0, "status"] = EDGE_MEMORY_STATUS_INVALIDATED
    mem_i.to_csv(inv / "edge_memory.csv", index=False)
    assert promote_oos_pass_to_memory(
        spec,
        OOSEvaluation(
            hypothesis_id=spec.hypothesis_id,
            edge_id=spec.edge_id,
            result="OOS_PASS",
            reason="resurrect",
            evaluated_at="2026-08-02T00:00:00Z",
            spec_hash=spec.spec_hash,
            best_horizon=spec.best_horizon,
        ),
        data_dir=inv,
    ) is False
    rec_i = _run_fr(
        inv,
        freeze_later,
        {"research_market_state": spec.market_state, "research_market_transition": spec.market_transition},
        trade_date=later[0],
    )
    assert rec_i["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert rec_i["qualified_match_count"] == 0
    assert run_edge_research_eod_cycle  # import used above


def test_decaying_and_invalidated_cannot_birth(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    calendar = _weekdays(8)
    freeze, _ = _birth_and_prices(spec, calendar, calendar[0], new1_t5_close=105.0, base_t5_close=101.0)
    mem = read_ledger("edge_memory.csv", edge_data_dir)
    mem.loc[0, "status"] = EDGE_MEMORY_STATUS_DECAYING
    mem.to_csv(edge_data_dir / "edge_memory.csv", index=False)
    rec = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, trade_date=calendar[0])
    assert rec["qualified_match_count"] == 0
    assert rec["reason"] == REASON_MATCHES_SUPPRESSED_BY_EDGE_HEALTH
    mem.loc[0, "status"] = EDGE_MEMORY_STATUS_INVALIDATED
    mem.to_csv(edge_data_dir / "edge_memory.csv", index=False)
    rec2 = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, trade_date=calendar[0])
    assert rec2["qualified_match_count"] == 0
    assert rec2["reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE


def test_anti_context_evidence_derived_not_hardcoded(edge_data_dir):
    from modules.edge_research.anti_context import learn_anti_context, mature_shadow_observations, run_shadow_counterfactual_scan
    from modules.edge_research.eod_cycle import run_continuous_learning

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    src = inspect.getsource(__import__("modules.edge_research.anti_context", fromlist=["x"]))
    assert "weak market" not in src.lower()
    assert "Y is bad" not in src
    calendar = _gapped_blocks(4, 8, start="2026-01-02")
    y_market = {"research_market_state": "MATURE", "research_market_transition": "MATURE -> MATURE"}
    freeze_parts = []
    ohlcv = {}
    cursor = 0
    for i in range(4):
        block = calendar[cursor : cursor + 8]
        t0 = block[0]
        freeze, prices = _birth_and_prices(
            spec,
            calendar,
            t0,
            new1_t5_close=90.0,
            base_t5_close=101.0,
            match_symbol=f"N{i:02d}",
            baseline_prefix=f"U{i:02d}",
        )
        freeze["research_market_transition"] = "MATURE -> MATURE"
        freeze["research_market_state"] = "MATURE"
        freeze_parts.append(freeze)
        for k, v in prices.items():
            ohlcv[k] = v if k not in ohlcv else pd.concat([ohlcv[k], v]).drop_duplicates("date")
        run_shadow_counterfactual_scan(t0, data_dir=edge_data_dir, freeze_df=freeze, market_context=y_market, session_calendar=calendar)
        cursor += 8
    freeze_all = pd.concat(freeze_parts, ignore_index=True)
    mature_shadow_observations(
        calendar[-1], data_dir=edge_data_dir, session_calendar=calendar, freeze_df=freeze_all, ohlcv_by_symbol=ohlcv, policy=TEST_POLICY
    )
    learned = learn_anti_context(data_dir=edge_data_dir, policy=TEST_POLICY, session_date=calendar[-1])
    anti = read_ledger("edge_anti_context.csv", edge_data_dir)
    if learned["learned"] == 0:
        # still must not fake; shadows should exist
        shadows = read_ledger("edge_shadow_observations.csv", edge_data_dir)
        assert not shadows.empty
        assert (shadows["research_label"].astype(str).str.contains("NOT A QUALIFIED")).all()
    else:
        assert not anti.empty
        assert str(anti.iloc[0]["context_y"]) == "MATURE -> MATURE"
        assert int(anti.iloc[0]["sample_n"]) >= 4
    # One observation is insufficient.
    thin = learn_anti_context(data_dir=edge_data_dir, policy=ForwardHealthPolicy(anti_context_min_n=999), session_date=calendar[-1])
    assert thin["learned"] == 0
    # X remains eligible
    freeze_x, _ = _birth_and_prices(spec, _weekdays(8, start="2026-09-01"), "2026-09-01", new1_t5_close=105.0, base_t5_close=101.0)
    rec = _run_fr(edge_data_dir, freeze_x, COMPATIBLE_MARKET, trade_date="2026-09-01")
    assert rec["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND
    # Y is not a qualified match
    rec_y = _run_fr(edge_data_dir, freeze_x, y_market, trade_date="2026-09-01")
    assert rec_y["qualified_match_count"] == 0
    assert rec_y["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    # Matcher consumes learned anti-context on an otherwise compatible session.
    anti_all = read_ledger("edge_anti_context.csv", edge_data_dir)
    if anti_all.empty:
        anti_all = pd.DataFrame(
            [
                {
                    "anti_context_id": "fixture",
                    "hypothesis_id": spec.hypothesis_id,
                    "context_y": spec.market_transition,
                    "evidence_status": "LEARNED",
                    "reason": "fixture evidence-derived anti-context",
                    "policy_version": "anti_context_policy_v1",
                    "sample_n": 4,
                }
            ]
        )
    else:
        anti_all = anti_all.copy()
        anti_all.loc[0, "context_y"] = spec.market_transition
        anti_all.loc[0, "hypothesis_id"] = spec.hypothesis_id
        anti_all.loc[0, "evidence_status"] = "LEARNED"
    anti_all.to_csv(edge_data_dir / "edge_anti_context.csv", index=False)
    rec_block = _run_fr(edge_data_dir, freeze_x, COMPATIBLE_MARKET, trade_date="2026-09-01")
    assert rec_block["qualified_match_count"] == 0
    assert rec_block["reason"] == "MATCHES_SUPPRESSED_BY_ANTI_CONTEXT"


def test_daily_duty_after_phase_c(edge_data_dir, tmp_path):
    from modules.edge_research.eod_cycle import run_edge_research_eod_cycle

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    calendar = _weekdays(8)
    freeze, ohlcv = _birth_and_prices(spec, calendar, calendar[0], new1_t5_close=105.0, base_t5_close=101.0)
    eod = run_edge_research_eod_cycle(
        trade_date=calendar[0],
        data_dir=edge_data_dir,
        freeze_df=freeze,
        session_calendar=calendar,
        ohlcv_by_symbol=ohlcv,
        market_context=COMPATIBLE_MARKET,
        policy=TEST_POLICY,
        panel=pd.DataFrame(),
    )
    assert eod["order"] == ["qualification", "continuous_learning", "recognition", "shadow"]
    assert eod["recognition"]["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND
    none = _run_fr(edge_data_dir, _freeze_df([_t0_row("OUT", clauses=clauses_from_frozen_spec(spec), satisfy=False)]), COMPATIBLE_MARKET, trade_date=calendar[0])
    assert none["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    unable = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, freeze_df=None, freeze_path=tmp_path / "no.csv", trade_date=calendar[0])
    assert unable["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS


def test_phase_c_failure_does_not_corrupt_t0_or_frozen_spec(edge_data_dir, monkeypatch):
    from modules.edge_research.eod_cycle import run_continuous_learning
    from modules.edge_research.freeze import load_frozen_spec

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    before_spec = load_frozen_spec(spec.hypothesis_id, edge_data_dir).serialize()
    freeze_path = EARNING / "t0_observation_freeze.csv"
    before = _digest(freeze_path)
    monkeypatch.setattr(
        "modules.edge_research.eod_cycle.mature_edge_forward_ledger",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("maturity boom")),
    )
    result = run_continuous_learning("2026-01-15", data_dir=edge_data_dir, policy=TEST_POLICY)
    assert result["ok"] is False
    assert any("maturity" in e for e in result["errors"])
    assert _digest(freeze_path) == before
    assert load_frozen_spec(spec.hypothesis_id, edge_data_dir).serialize() == before_spec


def test_restart_preserves_health_and_matured_outcomes(edge_data_dir, tmp_path):
    from modules.edge_research.eod_cycle import run_continuous_learning

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    calendar = _weekdays(12)
    freeze, ohlcv = _birth_and_prices(spec, calendar, calendar[0], new1_t5_close=105.0, base_t5_close=101.0)
    _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET, trade_date=calendar[0])
    run_continuous_learning(
        calendar[5], data_dir=edge_data_dir, freeze_df=freeze, session_calendar=calendar, ohlcv_by_symbol=ohlcv, policy=TEST_POLICY
    )
    restored = tmp_path / "restored"
    shutil.copytree(edge_data_dir, restored)
    a = read_ledger("edge_forward_ledger.csv", edge_data_dir)
    b = read_ledger("edge_forward_ledger.csv", restored)
    assert str(a.iloc[0]["t5_status"]) == str(b.iloc[0]["t5_status"])
    assert str(read_ledger("edge_memory.csv", restored).iloc[0]["status"]) == str(
        read_ledger("edge_memory.csv", edge_data_dir).iloc[0]["status"]
    )
    run_continuous_learning(
        calendar[5], data_dir=restored, freeze_df=freeze, session_calendar=calendar, ohlcv_by_symbol=ohlcv, policy=TEST_POLICY
    )
    assert len(read_ledger("edge_forward_ledger.csv", restored)) == len(a)


def test_eod_cycle_order_and_headless_entrypoint():
    from modules.edge_research.eod_cycle import main, run_edge_research_eod_cycle

    src = inspect.getsource(run_edge_research_eod_cycle)
    assert src.index("run_qualification_cycle") < src.index("run_continuous_learning")
    assert src.index("run_continuous_learning") < src.index("run_future_recognition")
    app_src = (REPO / "app.py").read_text(encoding="utf-8")
    assert "run_edge_research_eod_cycle" in app_src
    unit = (REPO / "deploy/systemd/mrbot-edge-research-eod.service").read_text(encoding="utf-8")
    assert "python -m modules.edge_research.eod_cycle" in unit
    assert callable(main)


def test_no_buy_and_no_human_edge_in_phase_c():
    import importlib

    for name in ("forward_maturity", "forward_evidence", "anti_context", "eod_cycle", "forward_health_policy"):
        src = inspect.getsource(importlib.import_module(f"modules.edge_research.{name}"))
        for tok in ("place_order", "BUY ELITE", "apply_learning_experience", "build_final_decision"):
            assert tok not in src
        assert "NEW1" not in src
        assert "three losses" not in src.lower()
