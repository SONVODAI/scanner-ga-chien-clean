"""Phase A — Edge Qualification & Durable Memory capability tests."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.contracts import (
    BASELINE_TYPE_SAME_TRANSITION,
    EDGE_MEMORY_STATUS_ACTIVE,
    OOS_STATUS_FAIL,
    OOS_STATUS_INCONCLUSIVE,
    OOS_STATUS_PASS,
    ROBUSTNESS_FRAGILE,
    ROBUSTNESS_PASS,
    ROBUSTNESS_REJECT,
)
from modules.edge_research.hypothesis import (
    FrozenHypothesisSpec,
    build_frozen_hypothesis_spec,
)
from modules.edge_research.oos import (
    OOSLeakageError,
    assert_no_oos_leakage,
    chronological_research_split,
    first_oos_session_after_embargo,
    labels_overlap_embargo,
    unique_trading_sessions,
)
from modules.edge_research.oos_policy import (
    OOS_BASELINE_MIN_N,
    OOS_CANDIDATE_MIN_N,
    OOS_POLICY_ID,
    oos_policy_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EARNING_DIR = REPO_ROOT / "data" / "earning_learning"


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


def _weekday_sessions(n: int, start: str = "2024-01-02", gap_after: int | None = 40) -> list[str]:
    dates: list[str] = []
    d = datetime.strptime(start, "%Y-%m-%d")
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y-%m-%d"))
            if gap_after is not None and len(dates) == gap_after:
                d += timedelta(days=16)
                continue
        d += timedelta(days=1)
    return dates


def _planted_panel(
    n_sessions: int = 120,
    symbols: int = 16,
    seed: int = 7,
    start: str = "2024-01-02",
    gap_after: int | None = 40,
    oos_return_mode: str = "positive",
    discovery_fraction: float = 0.70,
) -> pd.DataFrame:
    """
    Synthetic research panel. Outcomes are planted statistically so generic
    Discovery can find an edge; the rule itself is NOT hardcoded into
    freeze/OOS/memory modules.
    """
    rng = np.random.default_rng(seed)
    sessions = _weekday_sessions(n_sessions, start=start, gap_after=gap_after)
    split_idx = max(1, int(len(sessions) * discovery_fraction))
    discovery_end = sessions[split_idx - 1]
    rows = []
    for di, date in enumerate(sessions):
        for s in range(symbols):
            u = float(rng.random())
            if u < 0.28:
                rs10 = float(rng.uniform(-18, -10.01))
            elif u < 0.50:
                rs10 = float(rng.uniform(-10, -5.01))
            else:
                rs10 = float(rng.uniform(-5, 8))
            rsi = float(rng.uniform(22, 55))
            rs5 = rs10 + float(rng.uniform(-1.5, 1.5))
            in_oos = date > discovery_end
            if rs10 <= -10:
                if oos_return_mode == "negative" and in_oos:
                    base = -2.5
                else:
                    base = 4.2
            elif rs10 <= -5:
                base = 2.0 if not (oos_return_mode == "negative" and in_oos) else -0.4
            else:
                base = -0.35 if not (oos_return_mode == "negative" and in_oos) else 1.6
            noise = float(rng.normal(0, 0.25))
            ret = base + noise
            rows.append(
                {
                    "trade_date": date,
                    "symbol": f"S{s:03d}",
                    "rs5": rs5,
                    "rs10": rs10,
                    "rsi14": rsi,
                    "rs_spread": rs5 - rs10,
                    "research_market_state": "STRESS",
                    "research_market_transition": "STRESS -> STRESS",
                    "market_real": 4.0,
                    "t3_return": ret,
                    "t5_return": ret + 0.15,
                    "t10_return": ret + 0.30,
                }
            )
    return pd.DataFrame(rows)


def _minimal_spec(**overrides) -> FrozenHypothesisSpec:
    kwargs = dict(
        condition_key="STRESS -> STRESS|rs10:rs10_le_-10",
        condition_text="RS10<=-10",
        market_transition="STRESS -> STRESS",
        market_state="STRESS",
        feature_clauses=(
            {
                "feature": "rs10",
                "operator": "<=",
                "threshold_lo": None,
                "threshold_hi": -10.0,
                "bucket_id": "rs10_le_-10",
            },
        ),
        best_horizon="T5",
        discovery_run_id="disc-test",
        discovery_evidence={"incremental_median": 2.0},
        challenger_status="PASS",
        guardrails_summary={"multiple_testing_survives": True},
        data_cutoff_date="2024-03-01",
        guardrails_config_version="guardrails_v1",
        freeze_timestamp="2024-03-01T00:00:00Z",
        edge_id="EDGE-000001",
        baseline_type=BASELINE_TYPE_SAME_TRANSITION,
        discovery_start_date="2024-01-02",
        discovery_end_date="2024-03-01",
        holdout_applied=True,
        oos_mode="HOLDOUT_SPLIT",
        embargo_trading_sessions=10,
    )
    kwargs.update(overrides)
    return build_frozen_hypothesis_spec(**kwargs)


def _oos_panel_for_spec(spec: FrozenHypothesisSpec, *, n_oos: int, mode: str, symbols: int = 20) -> pd.DataFrame:
    """Build a panel that includes cutoff + embargo sessions + OOS sessions."""
    rng = np.random.default_rng(21)
    cutoff = datetime.strptime(spec.data_cutoff_date, "%Y-%m-%d")
    # Walk backward to collect cutoff as a weekday.
    while cutoff.weekday() >= 5:
        cutoff -= timedelta(days=1)
    sessions = []
    d = cutoff - timedelta(days=1)
    # a few pre-cutoff sessions so cutoff is on the calendar
    pre = []
    while len(pre) < 3:
        if d.weekday() < 5:
            pre.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    sessions.extend(reversed(pre))
    sessions.append(cutoff.strftime("%Y-%m-%d"))
    d = cutoff + timedelta(days=1)
    while len(sessions) < 3 + 1 + spec.embargo_trading_sessions + n_oos:
        if d.weekday() < 5:
            sessions.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    oos_start_idx = 3 + spec.embargo_trading_sessions  # after cutoff index 3? pre=3, cutoff at index 3
    # sessions: 3 pre + cutoff + embargo + oos
    cutoff_idx = sessions.index(cutoff.strftime("%Y-%m-%d"))
    rows = []
    for date in sessions:
        is_oos = sessions.index(date) > cutoff_idx + spec.embargo_trading_sessions
        for s in range(symbols):
            u = float(rng.random())
            if u < 0.4:
                rs10 = float(rng.uniform(-16, -10.01))
            else:
                rs10 = float(rng.uniform(-4, 6))
            rs5 = rs10 + 0.5
            if rs10 <= -10:
                ret = -2.0 if (mode == "negative" and is_oos) else 3.5
            else:
                ret = -0.4 if not (mode == "negative" and is_oos) else 1.8
            rows.append(
                {
                    "trade_date": date,
                    "symbol": f"S{s:03d}",
                    "rs5": rs5,
                    "rs10": rs10,
                    "rsi14": 35.0,
                    "rs_spread": 0.5,
                    "research_market_state": "STRESS",
                    "research_market_transition": "STRESS -> STRESS",
                    "market_real": 4.0,
                    "t3_return": ret,
                    "t5_return": ret,
                    "t10_return": ret,
                }
            )
    df = pd.DataFrame(rows)
    if mode == "thin":
        # Keep cutoff/embargo calendar but almost no OOS candidate rows.
        oos_dates = sorted(df["trade_date"].unique())[cutoff_idx + spec.embargo_trading_sessions + 1 :]
        keep_oos = set(oos_dates[:1])
        mask = ~df["trade_date"].isin(oos_dates) | df["trade_date"].isin(keep_oos)
        df = df[mask]
        df = df[~((df["trade_date"].isin(keep_oos)) & (df["rs10"] <= -10)) | ~df["trade_date"].isin(keep_oos)]
    return df


# ---------------------------------------------------------------------------
# Frozen spec contract
# ---------------------------------------------------------------------------
def test_frozen_spec_deterministic_and_idempotent_identity():
    a = _minimal_spec()
    b = _minimal_spec()
    assert a.hypothesis_id == b.hypothesis_id
    assert a.spec_hash == b.spec_hash
    assert len(a.feature_clauses) == 1


def test_frozen_spec_material_change_new_identity():
    a = _minimal_spec()
    b = _minimal_spec(best_horizon="T10")
    c = _minimal_spec(market_transition="STRESS -> EARLY_RECOVERY")
    assert a.hypothesis_id != b.hypothesis_id
    assert a.hypothesis_id != c.hypothesis_id


def test_frozen_spec_all_clauses_not_just_two():
    clauses = [
        {"feature": "rs10", "operator": "<=", "threshold_hi": -10.0, "threshold_lo": None, "bucket_id": "rs10_le_-10"},
        {"feature": "rsi14", "operator": "<=", "threshold_hi": 30.0, "threshold_lo": None, "bucket_id": "rsi14_le_30"},
        {"feature": "rs5", "operator": ">", "threshold_lo": 5.0, "threshold_hi": None, "bucket_id": "rs5_gt_5"},
    ]
    spec = _minimal_spec(feature_clauses=clauses, condition_text="three")
    assert len(spec.feature_clauses) == 3
    roundtrip = FrozenHypothesisSpec.from_dict(json.loads(spec.serialize()))
    assert [c["feature"] for c in roundtrip.feature_clauses] == ["rs10", "rs5", "rsi14"] or len(roundtrip.feature_clauses) == 3


def test_rerun_freeze_is_idempotent(edge_data_dir):
    from modules.edge_research.freeze import persist_frozen_spec
    from modules.edge_research.storage import ensure_storage

    ensure_storage(edge_data_dir)
    spec = _minimal_spec()
    p1, reused1 = persist_frozen_spec(spec, edge_data_dir)
    p2, reused2 = persist_frozen_spec(spec, edge_data_dir)
    assert p1 == p2
    assert reused1 is False
    assert reused2 is True
    loaded = json.loads(p1.read_text())
    assert loaded["spec_hash"] == spec.spec_hash
    assert loaded["frozen_at"] == spec.frozen_at


def test_frozen_spec_cannot_silently_mutate(edge_data_dir):
    from modules.edge_research.freeze import persist_frozen_spec
    from modules.edge_research.storage import ensure_storage

    ensure_storage(edge_data_dir)
    spec = _minimal_spec()
    persist_frozen_spec(spec, edge_data_dir)
    payload = json.loads((edge_data_dir / "frozen_specs" / f"{spec.hypothesis_id}.json").read_text())
    payload["best_horizon"] = "T10"
    mutated = FrozenHypothesisSpec.from_dict(payload)
    assert mutated.best_horizon == "T10"
    assert mutated.canonical_identity_json() != spec.canonical_identity_json()
    # On-disk original remains the frozen contract.
    disk = FrozenHypothesisSpec.from_dict(
        json.loads((edge_data_dir / "frozen_specs" / f"{spec.hypothesis_id}.json").read_text())
    )
    assert disk.best_horizon == "T5"
    assert disk.spec_hash == spec.spec_hash


# ---------------------------------------------------------------------------
# Freeze eligibility
# ---------------------------------------------------------------------------
def test_fragile_and_reject_cannot_freeze():
    from modules.edge_research.freeze import classify_freeze_eligibility

    fragile = pd.Series(
        {
            "edge_id": "EDGE-000002",
            "robustness_status": ROBUSTNESS_FRAGILE,
            "scientific_status": "FRAGILE",
            "condition_text": "RS10<=-10",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10,
            "market_transition": "STRESS -> STRESS",
        }
    )
    reject = pd.Series(
        {
            "edge_id": "EDGE-000003",
            "robustness_status": ROBUSTNESS_REJECT,
            "scientific_status": "REJECTED",
            "condition_text": "RS10<=-10",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10,
            "market_transition": "STRESS -> STRESS",
        }
    )
    assert classify_freeze_eligibility(fragile).eligible is False
    assert classify_freeze_eligibility(reject).eligible is False


def test_reconstruction_mismatch_is_historical_only():
    from modules.edge_research.freeze import classify_freeze_eligibility

    row = pd.Series(
        {
            "edge_id": "EDGE-000009",
            "robustness_status": ROBUSTNESS_PASS,
            "scientific_status": "READY_FOR_OOS",
            "condition_text": "RS10<=-10 & RSI14<=30 & RS5>5",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10,
            "feature_2": "rsi14",
            "operator_2": "<=",
            "threshold_2": 30,
            "market_transition": "STRESS -> STRESS",
            "best_horizon": "T5",
        }
    )
    decision = classify_freeze_eligibility(row)
    assert decision.eligible is False
    assert "HISTORICAL" in decision.eligibility or "mismatch" in decision.reason


# ---------------------------------------------------------------------------
# Trading-session embargo
# ---------------------------------------------------------------------------
def test_embargo_uses_trading_sessions_not_calendar_days():
    # Friday cutoff; weekend must not count; holiday Wednesday missing.
    sessions = [
        "2026-08-03",  # Mon
        "2026-08-04",  # Tue
        "2026-08-06",  # Thu (Wed 5th missing — non-trading)
        "2026-08-07",  # Fri cutoff
        "2026-08-10",  # Mon
        "2026-08-11",  # Tue
        "2026-08-12",  # Wed
        "2026-08-13",  # Thu
    ]
    ts = [pd.Timestamp(s) for s in sessions]
    cutoff = "2026-08-07"
    oos = first_oos_session_after_embargo(ts, cutoff, embargo_trading_sessions=2)
    assert oos is not None
    assert oos.strftime("%Y-%m-%d") == "2026-08-12"
    # Calendar +2 from Friday is Sunday 08-09, which is not a session; session embargo waits until Wed.


def test_t10_overlap_rejected():
    sessions = _weekday_sessions(40, start="2026-01-05", gap_after=None)
    panel = pd.DataFrame(
        {
            "trade_date": sessions,
            "symbol": ["AAA"] * len(sessions),
            "t10_return": [1.0] * len(sessions),
        }
    )
    split = chronological_research_split(panel, discovery_fraction=0.5, embargo_trading_days=10)
    assert_no_oos_leakage(split)
    from modules.edge_research.oos import t10_label_terminal_session

    cal = [pd.Timestamp(s) for s in split.session_calendar]
    terminal = t10_label_terminal_session(cal, split.discovery_end_date, 10)
    oos_dates = set(pd.to_datetime(split.oos_panel["trade_date"]).dt.strftime("%Y-%m-%d"))
    if terminal is not None and not split.oos_panel.empty:
        assert terminal.strftime("%Y-%m-%d") not in oos_dates
    assert labels_overlap_embargo(
        split.discovery_end_date,
        split.discovery_end_date,
        target_horizon_days=10,
        session_dates=split.session_calendar,
    ) is True


def test_chronological_split_session_embargo_and_weekend():
    rows = []
    # Include a weekend in the calendar span but only weekday rows exist.
    for d in _weekday_sessions(25, start="2026-08-03", gap_after=None):
        rows.append({"trade_date": d, "symbol": "AAA", "rs5": 1.0})
    panel = pd.DataFrame(rows)
    split = chronological_research_split(panel, discovery_fraction=0.6, embargo_trading_days=3)
    assert_no_oos_leakage(split)
    disc = set(pd.to_datetime(split.discovery_panel["trade_date"]).dt.strftime("%Y-%m-%d"))
    oos = set(pd.to_datetime(split.oos_panel["trade_date"]).dt.strftime("%Y-%m-%d"))
    assert disc.isdisjoint(oos)
    assert "2026-08-08" not in disc and "2026-08-08" not in oos  # Saturday never a session
    assert "2026-08-09" not in disc and "2026-08-09" not in oos  # Sunday never a session


def test_historical_candidate_cannot_receive_fake_retrospective_oos(edge_data_dir):
    from modules.edge_research.freeze import persist_frozen_spec
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos
    from modules.edge_research.storage import ensure_storage

    ensure_storage(edge_data_dir)
    panel = _planted_panel(n_sessions=40, gap_after=None)
    last = sorted(panel["trade_date"].unique())[-1]
    spec = _minimal_spec(
        data_cutoff_date=str(last)[:10],
        discovery_end_date=str(last)[:10],
        holdout_applied=False,
        oos_mode="PROSPECTIVE_AFTER_FREEZE",
        freeze_timestamp="2026-01-01T00:00:00Z",
    )
    persist_frozen_spec(spec, edge_data_dir)
    ev = evaluate_frozen_hypothesis_oos(spec, panel)
    assert ev.result == OOS_STATUS_INCONCLUSIVE
    assert ev.reason == "no_unseen_sessions_after_embargo"


# ---------------------------------------------------------------------------
# OOS outcomes
# ---------------------------------------------------------------------------
def test_oos_insufficient_n_inconclusive(edge_data_dir):
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos

    spec = _minimal_spec()
    panel = _oos_panel_for_spec(spec, n_oos=2, mode="thin", symbols=3)
    ev = evaluate_frozen_hypothesis_oos(spec, panel)
    assert ev.result == OOS_STATUS_INCONCLUSIVE
    assert ev.policy["threshold_policy_version"] == OOS_POLICY_ID
    assert ev.candidate_n < OOS_CANDIDATE_MIN_N or ev.baseline_n < OOS_BASELINE_MIN_N or ev.reason


def test_oos_positive_incremental_pass():
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos

    spec = _minimal_spec()
    panel = _oos_panel_for_spec(spec, n_oos=40, mode="positive", symbols=20)
    ev = evaluate_frozen_hypothesis_oos(spec, panel)
    assert ev.result == OOS_STATUS_PASS
    assert ev.best_horizon == "T5"
    assert ev.incremental_median is not None and ev.incremental_median > 0
    assert ev.threshold_policy_version == OOS_POLICY_ID


def test_oos_negative_incremental_fail():
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos

    spec = _minimal_spec()
    panel = _oos_panel_for_spec(spec, n_oos=40, mode="negative", symbols=20)
    ev = evaluate_frozen_hypothesis_oos(spec, panel)
    assert ev.result == OOS_STATUS_FAIL
    assert ev.candidate_n >= OOS_CANDIDATE_MIN_N
    assert ev.baseline_n >= OOS_BASELINE_MIN_N


def test_oos_does_not_reselect_best_horizon():
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos

    spec = _minimal_spec(best_horizon="T3")
    panel = _oos_panel_for_spec(spec, n_oos=40, mode="positive", symbols=20)
    # Make T10 look better than T3 in OOS without allowing reselection.
    panel = panel.copy()
    panel["t10_return"] = panel["t10_return"] + 10.0
    ev = evaluate_frozen_hypothesis_oos(spec, panel)
    assert ev.best_horizon == "T3"
    assert ev.horizon_reselection_attempted is False
    assert ev.selected_horizon_if_allowed in (None, "T3", "T5", "T10")
    # Diagnostic may prefer T10 but must not change the frozen horizon used.
    if ev.selected_horizon_if_allowed:
        assert ev.best_horizon == "T3"


def test_oos_uses_same_context_baseline_and_absent_context_inconclusive():
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos

    spec = _minimal_spec()
    panel = _oos_panel_for_spec(spec, n_oos=40, mode="positive", symbols=20)
    ev = evaluate_frozen_hypothesis_oos(spec, panel)
    assert ev.baseline_type == BASELINE_TYPE_SAME_TRANSITION

    other = panel.copy()
    other["research_market_transition"] = "MATURE -> ROLLOVER"
    other["research_market_state"] = "ROLLOVER"
    ev2 = evaluate_frozen_hypothesis_oos(spec, other)
    assert ev2.result == OOS_STATUS_INCONCLUSIVE
    assert "context" in ev2.reason


def test_validation_history_append_only(edge_data_dir):
    from modules.edge_research.oos_eval import append_validation_history, evaluate_frozen_hypothesis_oos
    from modules.edge_research.storage import ensure_storage, read_ledger

    ensure_storage(edge_data_dir)
    spec = _minimal_spec()
    panel = _oos_panel_for_spec(spec, n_oos=8, mode="thin", symbols=8)
    ev1 = evaluate_frozen_hypothesis_oos(spec, panel)
    append_validation_history(ev1, data_dir=edge_data_dir)
    append_validation_history(ev1, data_dir=edge_data_dir)  # idempotent duplicate
    hist = read_ledger("edge_validation_history.csv", edge_data_dir)
    assert len(hist) == 1
    first_result = hist.iloc[0]["result"]

    panel2 = _oos_panel_for_spec(spec, n_oos=40, mode="positive", symbols=20)
    ev2 = evaluate_frozen_hypothesis_oos(spec, panel2)
    append_validation_history(ev2, data_dir=edge_data_dir)
    hist2 = read_ledger("edge_validation_history.csv", edge_data_dir)
    assert len(hist2) == 2
    assert hist2.iloc[0]["result"] == first_result
    assert set(hist2["result"].astype(str)) >= {ev1.result, ev2.result}


def test_oos_pass_promotes_exactly_one_active_and_fail_inconclusive_do_not(edge_data_dir):
    from modules.edge_research.edge_memory import count_active_edges, promote_oos_pass_to_memory
    from modules.edge_research.freeze import persist_frozen_spec
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos
    from modules.edge_research.storage import ensure_storage, read_ledger

    ensure_storage(edge_data_dir)
    spec = _minimal_spec()
    persist_frozen_spec(spec, edge_data_dir)

    fail_ev = evaluate_frozen_hypothesis_oos(spec, _oos_panel_for_spec(spec, n_oos=40, mode="negative"))
    assert fail_ev.result == OOS_STATUS_FAIL
    assert promote_oos_pass_to_memory(spec, fail_ev, data_dir=edge_data_dir) is False
    assert count_active_edges(edge_data_dir) == 0

    thin_ev = evaluate_frozen_hypothesis_oos(spec, _oos_panel_for_spec(spec, n_oos=2, mode="thin", symbols=3))
    assert thin_ev.result == OOS_STATUS_INCONCLUSIVE
    assert promote_oos_pass_to_memory(spec, thin_ev, data_dir=edge_data_dir) is False
    assert count_active_edges(edge_data_dir) == 0

    pass_ev = evaluate_frozen_hypothesis_oos(spec, _oos_panel_for_spec(spec, n_oos=40, mode="positive"))
    assert pass_ev.result == OOS_STATUS_PASS
    assert promote_oos_pass_to_memory(spec, pass_ev, data_dir=edge_data_dir) is True
    assert promote_oos_pass_to_memory(spec, pass_ev, data_dir=edge_data_dir) is True  # idempotent
    mem = read_ledger("edge_memory.csv", edge_data_dir)
    active = mem[mem["status"].astype(str) == EDGE_MEMORY_STATUS_ACTIVE]
    assert len(active) == 1
    assert str(active.iloc[0]["spec_hash"]) == spec.spec_hash
    assert str(active.iloc[0]["hypothesis_id"]) == spec.hypothesis_id


def test_restart_restore_preserves_active_and_frozen_identity(edge_data_dir, tmp_path):
    from modules.edge_research.edge_memory import count_active_edges, promote_oos_pass_to_memory
    from modules.edge_research.freeze import load_frozen_spec, persist_frozen_spec
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos
    from modules.edge_research.storage import ensure_storage, read_ledger

    ensure_storage(edge_data_dir)
    spec = _minimal_spec()
    persist_frozen_spec(spec, edge_data_dir)
    ev = evaluate_frozen_hypothesis_oos(spec, _oos_panel_for_spec(spec, n_oos=40, mode="positive"))
    promote_oos_pass_to_memory(spec, ev, data_dir=edge_data_dir)

    restored = tmp_path / "restored"
    shutil.copytree(edge_data_dir, restored)
    loaded = load_frozen_spec(spec.hypothesis_id, restored)
    assert loaded is not None
    assert loaded.spec_hash == spec.spec_hash
    assert loaded.canonical_identity_json() == spec.canonical_identity_json()
    assert count_active_edges(restored) == 1
    mem = read_ledger("edge_memory.csv", restored)
    assert str(mem.iloc[0]["spec_hash"]) == spec.spec_hash


def test_no_writes_to_earning_learning_canonical_truth(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.freeze import persist_frozen_spec
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos
    from modules.edge_research.edge_memory import promote_oos_pass_to_memory
    from modules.edge_research.storage import ensure_storage

    files = [
        "pattern_lifecycle.csv",
        "observations.csv",
        "outcomes.csv",
        "t0_observation_freeze.csv",
    ]
    before = {f: _digest(EARNING_DIR / f) for f in files}
    ensure_storage(edge_data_dir)
    spec = _minimal_spec()
    persist_frozen_spec(spec, edge_data_dir)
    ev = evaluate_frozen_hypothesis_oos(spec, _oos_panel_for_spec(spec, n_oos=40, mode="positive"))
    promote_oos_pass_to_memory(spec, ev, data_dir=edge_data_dir)
    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    engine.run_qualification_cycle(panel=_oos_panel_for_spec(spec, n_oos=10, mode="thin", symbols=4))
    after = {f: _digest(EARNING_DIR / f) for f in files}
    assert before == after


def test_no_future_matcher_or_live_forward_in_phase_a():
    forbidden_tokens = (
        "future_matcher",
        "FutureMatcher",
        "match_active_edges",
        "scan_universe_for_edges",
        "create_live_forward_from_edge",
    )
    for name in (
        "freeze",
        "oos_eval",
        "edge_memory",
        "engine",
        "migration",
        "oos_policy",
        "hypothesis",
    ):
        mod = importlib.import_module(f"modules.edge_research.{name}")
        src = inspect.getsource(mod)
        for tok in forbidden_tokens:
            assert tok not in src
        for forbidden in ("apply_learning_experience", "build_buy_elite_decision_engine", "build_final_decision"):
            assert forbidden not in src


def test_validated_edges_counts_only_active(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.storage import ensure_storage

    ensure_storage(edge_data_dir)
    # Schema-only / empty memory must not count as validated.
    pd.DataFrame(
        [
            {
                "edge_id": "EDGE-000001",
                "hypothesis_id": "dead",
                "status": "",
                "confirmed_at": "",
                "decayed_at": "",
                "notes": "schema-only",
            }
        ]
    ).to_csv(edge_data_dir / "edge_memory.csv", index=False)
    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    status = engine.get_foundation_status()
    assert status.validated_edges == 0


def test_oos_policy_is_named_and_conservative():
    snap = oos_policy_snapshot()
    assert snap["oos_candidate_min_n"] == 20
    assert snap["oos_baseline_min_n"] == 50
    assert "CALIBRATION_REQUIRED" in snap["calibration_status"]
    assert snap["insufficient_sample_result"] == "OOS_INCONCLUSIVE"


def test_existing_edge_migration_audit_categories(edge_data_dir):
    from modules.edge_research.migration import audit_existing_candidates
    from modules.edge_research.storage import ensure_storage

    ensure_storage(edge_data_dir)
    rows = [
        {
            "edge_id": "EDGE-000001",
            "robustness_status": ROBUSTNESS_PASS,
            "scientific_status": "READY_FOR_OOS",
            "condition_text": "RS10<=-10",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10,
            "feature_2": "",
            "operator_2": "",
            "threshold_2": "",
            "market_transition": "STRESS -> STRESS",
            "best_horizon": "T5",
            "status": "CANDIDATE",
        },
        {
            "edge_id": "EDGE-000002",
            "robustness_status": ROBUSTNESS_FRAGILE,
            "scientific_status": "FRAGILE",
            "condition_text": "RS10<=-10",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10,
            "market_transition": "STRESS -> STRESS",
            "best_horizon": "T5",
            "status": "CANDIDATE",
        },
        {
            "edge_id": "EDGE-000003",
            "robustness_status": ROBUSTNESS_REJECT,
            "scientific_status": "REJECTED",
            "condition_text": "RS10<=-10",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10,
            "market_transition": "STRESS -> STRESS",
            "best_horizon": "T5",
            "status": "CANDIDATE",
        },
        {
            "edge_id": "EDGE-000004",
            "robustness_status": "",
            "scientific_status": "",
            "condition_text": "RS10<=-10",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10,
            "market_transition": "STRESS -> STRESS",
            "best_horizon": "T5",
            "status": "CANDIDATE",
        },
        {
            "edge_id": "EDGE-000005",
            "robustness_status": ROBUSTNESS_PASS,
            "scientific_status": "READY_FOR_OOS",
            "condition_text": "RS10<=-10 & RSI14<=30 & RS5>5",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10,
            "feature_2": "rsi14",
            "operator_2": "<=",
            "threshold_2": 30,
            "market_transition": "STRESS -> STRESS",
            "best_horizon": "T5",
            "status": "CANDIDATE",
        },
    ]
    pd.DataFrame(rows).to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)
    report = audit_existing_candidates(edge_data_dir)
    assert report["auto_active"] == 0
    assert report["counts"]["pass_reconstructable_ready_for_oos"] == 1
    assert report["counts"]["fragile_remain_historical"] == 1
    assert report["counts"]["reject_remain_historical"] == 1
    assert report["counts"]["challenger_not_run"] == 1
    assert report["counts"]["reconstruction_mismatch_historical_only"] == 1
    assert (edge_data_dir / "migration" / "phase_a_existing_edge_audit.json").exists()


# ---------------------------------------------------------------------------
# Blind Phase A acceptance: Discovery-produced EDGE-X
# ---------------------------------------------------------------------------
def test_blind_phase_a_discovery_to_memory_branches(edge_data_dir, monkeypatch):
    from modules.edge_research.challenger import run_challenger
    from modules.edge_research.discovery import run_discovery
    from modules.edge_research.edge_memory import count_active_edges, promote_oos_pass_to_memory
    from modules.edge_research.freeze import freeze_eligible_candidates, load_frozen_spec, persist_frozen_spec
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos
    from modules.edge_research.storage import (
        append_candidates,
        ensure_storage,
        read_ledger,
        update_ledger_robustness,
        write_challenger_run,
        write_discovery_run,
    )

    ensure_storage(edge_data_dir)
    panel = _planted_panel(n_sessions=180, symbols=20, seed=11)
    result = run_discovery(panel, apply_chronological_holdout=True, max_candidates=20)
    assert result.holdout_applied is True
    assert result.promoted_candidates >= 1
    discovered_keys = {c.condition_key for c in result.candidates}
    discovered_texts = {c.condition_text for c in result.candidates}

    append_candidates(result.candidates, edge_data_dir, discovery_run_id=result.run_id)
    write_discovery_run(result.to_dict(), data_dir=edge_data_dir)

    search_end = result.discovery_end_date
    challenger_panel = panel[pd.to_datetime(panel["trade_date"]) <= pd.Timestamp(search_end)].copy()
    ledger = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    chal = run_challenger(challenger_panel, ledger, discovery_run_id=result.run_id, force=True)
    write_challenger_run(chal.to_dict(), data_dir=edge_data_dir)
    update_ledger_robustness(chal.results, chal.run_id, data_dir=edge_data_dir)

    freeze = freeze_eligible_candidates(data_dir=edge_data_dir, panel=challenger_panel)
    assert freeze.frozen_count >= 1, f"expected freezeable PASS candidate, got {freeze.to_dict()}"
    spec = freeze.frozen[0].spec
    assert spec is not None
    assert spec.condition_key in discovered_keys or spec.condition_text in discovered_texts
    frozen_json_before = spec.serialize()

    # Positive branch — unseen holdout of the same planted process.
    pos = evaluate_frozen_hypothesis_oos(spec, panel)
    assert pos.best_horizon == spec.best_horizon
    assert pos.horizon_reselection_attempted is False
    assert FrozenHypothesisSpec.from_dict(json.loads(frozen_json_before)).serialize() == frozen_json_before
    assert pos.result == OOS_STATUS_PASS, pos.to_dict()
    promote_oos_pass_to_memory(spec, pos, data_dir=edge_data_dir)
    assert count_active_edges(edge_data_dir) == 1
    mem = read_ledger("edge_memory.csv", edge_data_dir)
    assert str(mem.iloc[0]["spec_hash"]) == spec.spec_hash

    # Reload preserves ACTIVE identity.
    reloaded = load_frozen_spec(spec.hypothesis_id, edge_data_dir)
    assert reloaded is not None and reloaded.spec_hash == spec.spec_hash

    # Negative branch — same frozen H, isolated memory store.
    neg_dir = edge_data_dir.parent / "neg"
    ensure_storage(neg_dir)
    persist_frozen_spec(spec, neg_dir)
    neg_panel = _planted_panel(n_sessions=180, symbols=20, seed=11, oos_return_mode="negative")
    neg = evaluate_frozen_hypothesis_oos(spec, neg_panel)
    assert neg.result == OOS_STATUS_FAIL, neg.to_dict()
    promote_oos_pass_to_memory(spec, neg, data_dir=neg_dir)
    assert count_active_edges(neg_dir) == 0

    # Thin-data branch.
    thin_dir = edge_data_dir.parent / "thin"
    ensure_storage(thin_dir)
    persist_frozen_spec(spec, thin_dir)
    thin_panel = _oos_panel_for_spec(spec, n_oos=2, mode="thin", symbols=3)
    # Align cutoff calendar with frozen spec.
    thin = evaluate_frozen_hypothesis_oos(spec, thin_panel)
    assert thin.result == OOS_STATUS_INCONCLUSIVE
    promote_oos_pass_to_memory(spec, thin, data_dir=thin_dir)
    assert count_active_edges(thin_dir) == 0

    # OOS did not alter H.
    disk = load_frozen_spec(spec.hypothesis_id, edge_data_dir)
    assert disk is not None
    assert disk.serialize() == frozen_json_before or disk.spec_hash == spec.spec_hash
    assert disk.best_horizon == spec.best_horizon
    assert disk.feature_clauses == spec.feature_clauses
