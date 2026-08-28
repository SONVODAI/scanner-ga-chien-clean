"""Phase B — Future Recognition & LIVE_FORWARD capability tests."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.contracts import (
    ASSESSMENT_NO_QUALIFIED_MATCH,
    ASSESSMENT_QUALIFIED_MATCH_FOUND,
    ASSESSMENT_UNABLE_TO_ASSESS,
    CONTEXT_COMPATIBLE,
    CONTEXT_INCOMPATIBLE,
    CONTEXT_UNKNOWN,
    EDGE_MEMORY_STATUS_ACTIVE,
    FEATURE_BUCKET_CONFIG_VERSION,
    FORWARD_OUTCOME_PENDING,
    OOS_STATUS_FAIL,
    OOS_STATUS_PASS,
    OOS_STATUS_PENDING,
    REASON_NO_ACTIVE_EDGE_AVAILABLE,
)
from modules.edge_research.discovery import ConditionClause
from modules.edge_research.freeze import persist_frozen_spec
from modules.edge_research.hypothesis import FrozenHypothesisSpec, spec_hash_from_dict
from modules.edge_research.oos_eval import OOSEvaluation, clauses_from_frozen_spec
from modules.edge_research.storage import ensure_storage, read_ledger
from tests.test_edge_research_phase_a_qualification import (
    _minimal_spec,
    _planted_panel,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EARNING_DIR = REPO_ROOT / "data" / "earning_learning"
FUTURE_DATE = "2026-01-15"
COMPATIBLE_MARKET = {
    "research_market_state": "STRESS",
    "research_market_transition": "STRESS -> STRESS",
}
INCOMPATIBLE_MARKET = {
    "research_market_state": "MATURE",
    "research_market_transition": "MATURE -> MATURE",
}
UNKNOWN_MARKET = {
    "research_market_state": "UNKNOWN",
    "research_market_transition": "UNKNOWN",
}


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


def _pass_eval(spec: FrozenHypothesisSpec) -> OOSEvaluation:
    return OOSEvaluation(
        hypothesis_id=spec.hypothesis_id,
        edge_id=spec.edge_id,
        result=OOS_STATUS_PASS,
        reason="fixture_oos_pass",
        evaluated_at="2024-06-01T00:00:00Z",
        spec_hash=spec.spec_hash,
        best_horizon=spec.best_horizon,
        candidate_n=24,
        baseline_n=60,
        incremental_median=1.25,
        incremental_mean=1.10,
        incremental_win_rate=0.62,
        market_episode_count=3,
    )


def _activate(spec: FrozenHypothesisSpec, data_dir: Path) -> FrozenHypothesisSpec:
    from modules.edge_research.edge_memory import promote_oos_pass_to_memory

    persist_frozen_spec(spec, data_dir)
    promote_oos_pass_to_memory(spec, _pass_eval(spec), data_dir=data_dir)
    return spec


def _write_memory_status(spec: FrozenHypothesisSpec, data_dir: Path, status: str) -> None:
    persist_frozen_spec(spec, data_dir)
    mem = read_ledger("edge_memory.csv", data_dir)
    row = {col: "" for col in mem.columns}
    row.update(
        {
            "edge_id": spec.edge_id,
            "hypothesis_id": spec.hypothesis_id,
            "status": status,
            "spec_path": f"frozen_specs/{spec.hypothesis_id}.json",
            "spec_hash": spec.spec_hash,
            "market_state": spec.market_state,
            "market_transition": spec.market_transition,
            "condition_key": spec.condition_key,
            "condition_text": spec.condition_text,
            "best_horizon": spec.best_horizon,
            "feature_clauses_json": json.dumps(list(spec.feature_clauses), ensure_ascii=False),
            "oos_result": status,
            "forward_matches": 0,
        }
    )
    mem = pd.concat([mem, pd.DataFrame([row])], ignore_index=True)
    mem.to_csv(data_dir / "edge_memory.csv", index=False)


def _values_for_clauses(clauses, *, satisfy: bool) -> dict[str, float]:
    vals = {"rs5": -1.0, "rs10": -1.0, "rsi14": 50.0, "rs_spread": 0.0}
    for clause in clauses:
        if clause.feature == "rs_spread":
            continue
        if clause.operator == "<=":
            target = float(clause.threshold_hi) - (0.75 if satisfy else -5.0)
        elif clause.operator == ">":
            target = float(clause.threshold_lo) + (0.75 if satisfy else -5.0)
        else:
            lo = float(clause.threshold_lo if clause.threshold_lo is not None else -20)
            hi = float(clause.threshold_hi if clause.threshold_hi is not None else 20)
            target = (lo + hi) / 2.0 if satisfy else hi + 8.0
        vals[clause.feature] = target
    vals["rs_spread"] = vals["rs5"] - vals["rs10"]
    for clause in clauses:
        if clause.feature != "rs_spread":
            continue
        if clause.operator == "<=":
            target = float(clause.threshold_hi) - (0.75 if satisfy else -6.0)
        elif clause.operator == ">":
            target = float(clause.threshold_lo) + (0.75 if satisfy else -6.0)
        else:
            lo = float(clause.threshold_lo if clause.threshold_lo is not None else -8)
            hi = float(clause.threshold_hi if clause.threshold_hi is not None else 8)
            target = (lo + hi) / 2.0 if satisfy else hi + 6.0
        vals["rs_spread"] = target
        vals["rs5"] = vals["rs10"] + target
    return vals


def _t0_row(symbol: str, *, clauses, satisfy: bool = True, drop: str | None = None, **extra) -> dict:
    vals = _values_for_clauses(clauses, satisfy=satisfy)
    row = {
        "observation_id": f"{FUTURE_DATE}|{symbol}",
        "trade_date": FUTURE_DATE,
        "symbol": symbol,
        "rs5": vals["rs5"],
        "rs10": vals["rs10"],
        "rsi14": vals["rsi14"],
        "rs_spread": vals["rs_spread"],
        "market_real": 4.0,
        "t3_return": 9.9,
        "t5_return": 12.1,
        "t10_return": 15.0,
    }
    row.update(extra)
    if drop:
        row.pop(drop, None)
    return row


def _freeze_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _run_fr(data_dir: Path, freeze: pd.DataFrame | None, market, **kwargs):
    from modules.edge_research.future_recognition import run_future_recognition

    freeze_df = kwargs.pop("freeze_df", freeze)
    return run_future_recognition(
        trade_date=kwargs.pop("trade_date", FUTURE_DATE),
        data_dir=data_dir,
        freeze_df=freeze_df,
        market_context=market,
        **kwargs,
    )


def _rsi_spec(**overrides) -> FrozenHypothesisSpec:
    kwargs = dict(
        condition_key="STRESS -> STRESS|rsi14:rsi14_le_40",
        condition_text="RSI14<=40",
        market_transition="STRESS -> STRESS",
        market_state="STRESS",
        feature_clauses=(
            {
                "feature": "rsi14",
                "operator": "<=",
                "threshold_lo": None,
                "threshold_hi": 40.0,
                "bucket_id": "rsi14_le_40",
            },
        ),
        best_horizon="T3",
        discovery_run_id="disc-rsi",
        discovery_evidence={"incremental_median": 1.8},
        challenger_status="PASS",
        guardrails_summary={"multiple_testing_survives": True},
        data_cutoff_date="2024-04-01",
        guardrails_config_version="guardrails_v1",
        freeze_timestamp="2024-04-01T00:00:00Z",
        edge_id="EDGE-000002",
        baseline_type="SAME_TRANSITION",
        discovery_start_date="2024-01-02",
        discovery_end_date="2024-04-01",
        holdout_applied=True,
        oos_mode="HOLDOUT_SPLIT",
        embargo_trading_sessions=10,
    )
    kwargs.update(overrides)
    from modules.edge_research.hypothesis import build_frozen_hypothesis_spec

    return build_frozen_hypothesis_spec(**kwargs)


# ---------------------------------------------------------------------------
# 1–4 ACTIVE-only consumption
# ---------------------------------------------------------------------------
def test_matcher_loads_active_edges_only(edge_data_dir):
    from modules.edge_research.future_recognition import load_interpretable_active_edges

    ensure_storage(edge_data_dir)
    active = _activate(_minimal_spec(), edge_data_dir)
    _write_memory_status(_rsi_spec(), edge_data_dir, "CANDIDATE")
    loaded = load_interpretable_active_edges(edge_data_dir)
    ids = {e.memory_row.get("edge_id") for e in loaded}
    assert active.edge_id in ids
    assert "EDGE-000002" not in ids
    assert all(str(e.memory_row.get("status")).upper() == EDGE_MEMORY_STATUS_ACTIVE for e in loaded)


def test_challenger_pass_non_active_cannot_match(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _minimal_spec()
    persist_frozen_spec(spec, edge_data_dir)
    _write_memory_status(spec, edge_data_dir, "READY_FOR_OOS")
    clauses = clauses_from_frozen_spec(spec)
    freeze = _freeze_df(
        [
            _t0_row("NEW1", clauses=clauses, satisfy=True),
            _t0_row("FILL", clauses=clauses, satisfy=False),
        ]
    )
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert result["reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE
    assert result["qualified_match_count"] == 0
    ledger = read_ledger("edge_forward_ledger.csv", edge_data_dir)
    assert ledger.empty or len(ledger) == 0


def test_oos_pending_cannot_match(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _minimal_spec()
    _write_memory_status(spec, edge_data_dir, OOS_STATUS_PENDING)
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert result["qualified_match_count"] == 0


def test_oos_fail_cannot_match(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _minimal_spec()
    _write_memory_status(spec, edge_data_dir, OOS_STATUS_FAIL)
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert result["qualified_match_count"] == 0


# ---------------------------------------------------------------------------
# 5–6 spec integrity
# ---------------------------------------------------------------------------
def test_frozen_spec_hash_mismatch_unable(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    path = edge_data_dir / "frozen_specs" / f"{spec.hypothesis_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["feature_clauses"][0]["threshold_hi"] = -99.0
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert result["reason"] == "ACTIVE_EDGE_SPEC_UNINTERPRETABLE"
    assert result["qualified_match_count"] == 0


def test_config_schema_incompatibility_is_explicit(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    path = edge_data_dir / "frozen_specs" / f"{spec.hypothesis_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["feature_bucket_config_version"] = "feature_buckets_v9"
    payload.pop("spec_hash", None)
    new_hash = spec_hash_from_dict(payload)
    payload["spec_hash"] = new_hash
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    mem = read_ledger("edge_memory.csv", edge_data_dir)
    mem.loc[mem["hypothesis_id"] == spec.hypothesis_id, "spec_hash"] = new_hash
    mem.to_csv(edge_data_dir / "edge_memory.csv", index=False)
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert result["reason"] == "ACTIVE_EDGE_SPEC_UNINTERPRETABLE"
    assert "feature_bucket_config_incompatible" in str(result.get("failure_detail") or "")
    assert FEATURE_BUCKET_CONFIG_VERSION != "feature_buckets_v9"


# ---------------------------------------------------------------------------
# 7–9 market context
# ---------------------------------------------------------------------------
def test_compatible_transition_permits_evaluation(edge_data_dir):
    from modules.edge_research.future_recognition import evaluate_market_context

    spec = _minimal_spec()
    verdict, reason = evaluate_market_context(spec, "STRESS -> STRESS", "STRESS")
    assert verdict == CONTEXT_COMPATIBLE
    assert "COMPATIBLE" in reason


def test_incompatible_transition_produces_no_birth(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    freeze = _freeze_df(
        [
            _t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True),
            _t0_row("FILL", clauses=clauses_from_frozen_spec(spec), satisfy=False),
        ]
    )
    result = _run_fr(edge_data_dir, freeze, INCOMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert result["edges_context_incompatible"] >= 1
    assert result["qualified_match_count"] == 0
    ledger = read_ledger("edge_forward_ledger.csv", edge_data_dir)
    assert len(ledger) == 0


def test_unknown_context_does_not_guess(edge_data_dir):
    from modules.edge_research.future_recognition import evaluate_market_context

    spec = _minimal_spec()
    verdict, reason = evaluate_market_context(spec, "UNKNOWN", "UNKNOWN")
    assert verdict == CONTEXT_UNKNOWN
    ensure_storage(edge_data_dir)
    _activate(spec, edge_data_dir)
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    result = _run_fr(edge_data_dir, freeze, UNKNOWN_MARKET)
    assert result["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert result["reason"] == "MARKET_CONTEXT_UNKNOWN"
    assert result["qualified_match_count"] == 0


# ---------------------------------------------------------------------------
# 10–11 PIT universe
# ---------------------------------------------------------------------------
def test_pit_t0_universe_is_used(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    clauses = clauses_from_frozen_spec(spec)
    freeze = _freeze_df(
        [
            _t0_row("NEW1", clauses=clauses, satisfy=True),
            _t0_row("AAA", clauses=clauses, satisfy=False),
            _t0_row("BBB", clauses=clauses, satisfy=False),
        ]
    )
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["universe_count"] == 3
    assert result["universe_hash"]
    assert result["t0_source_status"] == "OK"
    assert result["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND
    assert {m["symbol"] for m in result["matches"]} == {"NEW1"}


def test_lifecycle_outcome_gated_panel_is_not_universe(edge_data_dir, monkeypatch):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)

    def _boom(*_a, **_k):
        raise AssertionError("pattern_lifecycle must not be the future universe")

    monkeypatch.setattr("modules.edge_research.adapters.load_lifecycle", _boom)
    src = inspect.getsource(importlib.import_module("modules.edge_research.t0_universe"))
    assert "pattern_lifecycle.csv" not in src.split("def load_session_universe")[1].split("def systemic")[0]
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND


# ---------------------------------------------------------------------------
# 12–17 matching semantics
# ---------------------------------------------------------------------------
def test_exact_clauses_reproduce_discovery_semantics(edge_data_dir):
    from modules.edge_research.discovery import apply_condition

    spec = _minimal_spec()
    clauses = clauses_from_frozen_spec(spec)
    freeze = _freeze_df(
        [
            _t0_row("IN", clauses=clauses, satisfy=True),
            _t0_row("OUT", clauses=clauses, satisfy=False),
        ]
    )
    matched = apply_condition(freeze, list(clauses))
    assert set(matched["symbol"].astype(str)) == {"IN"}
    for _, row in freeze.iterrows():
        expected = all(c.matches(row) for c in clauses)
        assert (row["symbol"] == "IN") == expected


def test_missing_required_feature_on_symbol_prevents_match(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    clauses = clauses_from_frozen_spec(spec)
    missing = _t0_row("MISS", clauses=clauses, satisfy=True, drop=clauses[0].feature)
    keep = _t0_row("KEEP", clauses=clauses, satisfy=False)
    freeze = _freeze_df([missing, keep])
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert result["qualified_match_count"] == 0


def test_many_stocks_may_match_one_edge(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    clauses = clauses_from_frozen_spec(spec)
    freeze = _freeze_df(
        [
            _t0_row("NEW1", clauses=clauses, satisfy=True),
            _t0_row("NEW2", clauses=clauses, satisfy=True),
            _t0_row("OUT", clauses=clauses, satisfy=False),
        ]
    )
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND
    assert {m["symbol"] for m in result["matches"]} == {"NEW1", "NEW2"}
    assert len(result["matches"]) == 2


def test_one_stock_may_match_multiple_active_edges(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec_a = _activate(_minimal_spec(), edge_data_dir)
    spec_b = _activate(_rsi_spec(), edge_data_dir)
    clauses_a = clauses_from_frozen_spec(spec_a)
    clauses_b = clauses_from_frozen_spec(spec_b)
    # Build a row that satisfies BOTH independent frozen clause sets.
    dual = _t0_row("NEW1", clauses=clauses_a, satisfy=True)
    rsi_vals = _values_for_clauses(clauses_b, satisfy=True)
    dual["rsi14"] = rsi_vals["rsi14"]
    freeze = _freeze_df([dual, _t0_row("OUT", clauses=clauses_a, satisfy=False)])
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND
    pairs = {(m["symbol"], m["edge_id"]) for m in result["matches"]}
    assert ("NEW1", spec_a.edge_id) in pairs
    assert ("NEW1", spec_b.edge_id) in pairs
    assert len(pairs) == 2
    ledger = read_ledger("edge_forward_ledger.csv", edge_data_dir)
    assert len(ledger) == 2


# ---------------------------------------------------------------------------
# 18–20 birth contract
# ---------------------------------------------------------------------------
def test_birth_immutable_first_write_wins_and_no_future_outcome(edge_data_dir):
    from modules.edge_research.forward_ledger import persist_births

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    first = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    ledger = read_ledger("edge_forward_ledger.csv", edge_data_dir)
    assert len(ledger) == 1
    original_reason = str(ledger.iloc[0]["selection_reason"])
    original_id = str(ledger.iloc[0]["ledger_id"])
    assert str(ledger.iloc[0]["outcome_status"]) == FORWARD_OUTCOME_PENDING
    for col in ("t3_return", "t5_return", "t10_return", "forward_return"):
        assert col not in ledger.columns or pd.isna(ledger.iloc[0].get(col)) or str(ledger.iloc[0].get(col)) in ("", "nan")
    persist_births(
        [
            {
                "hypothesis_id": spec.hypothesis_id,
                "t0_trade_date": FUTURE_DATE,
                "symbol": "NEW1",
                "selection_reason": "TAMPERED",
                "outcome_status": "HIT",
                "t5_return": 99.0,
            }
        ],
        data_dir=edge_data_dir,
    )
    ledger2 = read_ledger("edge_forward_ledger.csv", edge_data_dir)
    assert len(ledger2) == 1
    assert str(ledger2.iloc[0]["selection_reason"]) == original_reason
    assert str(ledger2.iloc[0]["ledger_id"]) == original_id
    assert str(ledger2.iloc[0]["outcome_status"]) == FORWARD_OUTCOME_PENDING
    second = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    assert second["duplicate_skip_count"] >= 1
    assert second["new_birth_count"] == 0
    assert len(read_ledger("edge_forward_ledger.csv", edge_data_dir)) == 1
    assert first["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND


# ---------------------------------------------------------------------------
# 21–25 assessment states
# ---------------------------------------------------------------------------
def test_qualified_no_match_unable_and_zero_active_states(edge_data_dir, tmp_path):
    ensure_storage(edge_data_dir)
    freeze_ok = _freeze_df(
        [
            {
                "observation_id": f"{FUTURE_DATE}|ZZZ",
                "trade_date": FUTURE_DATE,
                "symbol": "ZZZ",
                "rs5": 1.0,
                "rs10": 1.0,
                "rsi14": 50.0,
                "rs_spread": 0.0,
                "market_real": 4.0,
            }
        ]
    )
    none = _run_fr(edge_data_dir, freeze_ok, COMPATIBLE_MARKET)
    assert none["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert none["reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE

    spec = _activate(_minimal_spec(), edge_data_dir)
    freeze_match = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    found = _run_fr(edge_data_dir, freeze_match, COMPATIBLE_MARKET)
    assert found["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND

    freeze_nomatch = _freeze_df([_t0_row("OUT", clauses=clauses_from_frozen_spec(spec), satisfy=False)])
    empty = _run_fr(edge_data_dir, freeze_nomatch, COMPATIBLE_MARKET)
    assert empty["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert empty["reason"] == "NO_STOCK_SATISFIES_ACTIVE_EDGE_IN_COMPATIBLE_CONTEXT"

    missing = _run_fr(
        edge_data_dir,
        freeze_ok,
        COMPATIBLE_MARKET,
        freeze_df=None,
        freeze_path=tmp_path / "no_such_t0.csv",
        trade_date=FUTURE_DATE,
    )
    assert missing["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert missing["reason"] in {"T0_UNIVERSE_UNAVAILABLE", "T0_FREEZE_DATE_UNAVAILABLE"}


def test_matcher_exception_is_unable_and_does_not_corrupt_t0(edge_data_dir, tmp_path):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    freeze_path = tmp_path / "t0_observation_freeze.csv"
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    freeze.to_csv(freeze_path, index=False)
    before = _digest(freeze_path)
    prod_before = _digest(EARNING_DIR / "t0_observation_freeze.csv")
    result = _run_fr(
        edge_data_dir,
        freeze,
        COMPATIBLE_MARKET,
        freeze_path=freeze_path,
        raise_internal=RuntimeError("injected matcher failure"),
    )
    assert result["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert result["reason"] == "MATCHER_EXCEPTION"
    assert "injected matcher failure" in str(result.get("failure_detail") or "")
    assert _digest(freeze_path) == before
    assert _digest(EARNING_DIR / "t0_observation_freeze.csv") == prod_before
    assert len(read_ledger("edge_forward_ledger.csv", edge_data_dir)) == 0


# ---------------------------------------------------------------------------
# 27–28 sidecar + restore
# ---------------------------------------------------------------------------
def test_derived_sidecar_rebuild_and_restart_preserves_births(edge_data_dir, tmp_path):
    from modules.edge_research.forward_ledger import (
        load_session_matches,
        read_latest_assessment,
        rebuild_daily_sidecar,
    )

    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    freeze = _freeze_df([_t0_row("NEW1", clauses=clauses_from_frozen_spec(spec), satisfy=True)])
    result = _run_fr(edge_data_dir, freeze, COMPATIBLE_MARKET)
    sidecar = edge_data_dir / "daily_edge_matches" / f"{FUTURE_DATE}.json"
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    sidecar.unlink()
    rebuilt = rebuild_daily_sidecar(FUTURE_DATE, result, data_dir=edge_data_dir)
    payload2 = json.loads(rebuilt.read_text(encoding="utf-8"))
    assert payload2["canonical_source"] == "edge_forward_ledger.csv"
    assert payload2["qualified_match_count"] == payload["qualified_match_count"]
    assert {m["symbol"] for m in payload2["matches"]} == {"NEW1"}

    restored = tmp_path / "restored"
    shutil.copytree(edge_data_dir, restored)
    ledger = load_session_matches(FUTURE_DATE, data_dir=restored)
    assert len(ledger) == 1
    assert str(ledger.iloc[0]["symbol"]) == "NEW1"
    latest = read_latest_assessment(restored)
    assert latest.get("assessment_state") == ASSESSMENT_QUALIFIED_MATCH_FOUND
    rerun = _run_fr(restored, freeze, COMPATIBLE_MARKET)
    assert rerun["new_birth_count"] == 0
    assert len(read_ledger("edge_forward_ledger.csv", restored)) == 1


def test_bundle_optional_artifacts_include_phase_b():
    from modules.edge_research.bundle import OPTIONAL_ARTIFACT_NAMES

    assert "edge_forward_ledger.csv" in OPTIONAL_ARTIFACT_NAMES
    assert "edge_session_assessments.csv" in OPTIONAL_ARTIFACT_NAMES
    assert "latest_future_recognition.json" in OPTIONAL_ARTIFACT_NAMES


# ---------------------------------------------------------------------------
# 29–30 no BUY / no human edge rule
# ---------------------------------------------------------------------------
def test_no_buy_execution_coupling_and_no_human_edge_rule():
    names = ("future_recognition", "forward_ledger", "t0_universe")
    forbidden_buy = (
        "apply_learning_experience",
        "build_buy_elite_decision_engine",
        "build_final_decision",
        "place_order",
        "BUY ELITE",
    )
    for name in names:
        src = inspect.getsource(importlib.import_module(f"modules.edge_research.{name}"))
        for tok in forbidden_buy:
            assert tok not in src
        assert "RESEARCH MATCH — NOT AUTOMATIC BUY" in inspect.getsource(
            importlib.import_module("modules.edge_research.forward_ledger")
        )
        assert "NEW1" not in src
        assert "TCB" not in src
        assert '"S000"' not in src
        assert "STRESS -> EARLY_RECOVERY" not in src or "expected" in src
    engine_src = inspect.getsource(importlib.import_module("modules.edge_research.engine"))
    for tok in ("future_matcher", "FutureMatcher", "match_active_edges", "scan_universe_for_edges", "create_live_forward_from_edge"):
        assert tok not in engine_src
    app_src = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert "run_edge_research_eod_cycle(" not in app_src
    orch = (REPO_ROOT / "modules/edge_research/opr_bridge/production_daily_run_orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert "run_closed_loop_edge_after_daily" in orch
    eod_src = inspect.getsource(importlib.import_module("modules.edge_research.eod_cycle").run_edge_research_eod_cycle)
    assert "run_qualification_cycle" in eod_src
    assert "run_continuous_learning" in eod_src
    assert "run_future_recognition" in eod_src
    assert eod_src.index("run_qualification_cycle") < eod_src.index("run_continuous_learning")
    assert eod_src.index("run_continuous_learning") < eod_src.index("run_future_recognition")


def test_ui_distinguishes_three_assessment_states():
    from modules.edge_research.future_recognition import format_future_recognition_operator_text
    from modules.edge_research.ui import render_edge_research_panel

    found = format_future_recognition_operator_text(
        {
            "assessment_state": ASSESSMENT_QUALIFIED_MATCH_FOUND,
            "trade_date": FUTURE_DATE,
            "matches": [
                {
                    "symbol": "NEW1",
                    "edge_id": "EDGE-000001",
                    "context_verdict": "COMPATIBLE",
                    "context_reason": "expected:STRESS -> STRESS current:STRESS -> STRESS verdict:COMPATIBLE",
                    "condition_text": "RS10<=-10",
                    "best_horizon": "T5",
                    "oos_evidence": {"oos_candidate_n": 24, "oos_incremental_median": 1.25, "episode_count": 3},
                    "research_label": "RESEARCH MATCH — NOT AUTOMATIC BUY",
                    "selection_reason": "RESEARCH MATCH EDGE-000001 because market compatible",
                }
            ],
        }
    )
    assert "QUALIFIED MATCH FOUND" in found
    assert "NEW1" in found
    assert "EDGE-000001" in found
    assert "LIVE_FORWARD" in found
    assert "RESEARCH MATCH" in found
    assert "BUY ELITE" not in found

    none = format_future_recognition_operator_text(
        {
            "assessment_state": ASSESSMENT_NO_QUALIFIED_MATCH,
            "reason": REASON_NO_ACTIVE_EDGE_AVAILABLE,
            "active_edge_count": 0,
            "edges_context_compatible": 0,
            "universe_count": 10,
            "qualified_match_count": 0,
        }
    )
    assert "NO QUALIFIED MATCH" in none
    assert "NO_ACTIVE_EDGE_AVAILABLE" in none
    assert "no opportunities today" not in none.lower()

    unable = format_future_recognition_operator_text(
        {
            "assessment_state": ASSESSMENT_UNABLE_TO_ASSESS,
            "reason": "T0_UNIVERSE_UNAVAILABLE",
            "failure_detail": "canonical T0 freeze missing or empty",
        }
    )
    assert "UNABLE TO ASSESS" in unable
    assert "NOT 'no opportunities today.'" in unable
    src = inspect.getsource(render_edge_research_panel)
    assert "FUTURE RECOGNITION" in src
    assert "run_future_recognition" not in src


# ---------------------------------------------------------------------------
# 19 mandatory blind NEW1 acceptance
# ---------------------------------------------------------------------------
def test_blind_new1_acceptance_from_discovery_active_edge(edge_data_dir):
    from modules.edge_research.challenger import run_challenger
    from modules.edge_research.discovery import run_discovery
    from modules.edge_research.edge_memory import count_active_edges, promote_oos_pass_to_memory
    from modules.edge_research.freeze import freeze_eligible_candidates, load_frozen_spec
    from modules.edge_research.future_recognition import format_future_recognition_operator_text
    from modules.edge_research.oos_eval import evaluate_frozen_hypothesis_oos
    from modules.edge_research.storage import (
        append_candidates,
        update_ledger_robustness,
        write_challenger_run,
        write_discovery_run,
    )

    ensure_storage(edge_data_dir)
    panel = _planted_panel(n_sessions=180, symbols=20, seed=11)
    cohort_symbols = set(panel["symbol"].astype(str).str.upper())
    result = run_discovery(panel, apply_chronological_holdout=True, max_candidates=20)
    assert result.promoted_candidates >= 1
    append_candidates(result.candidates, edge_data_dir, discovery_run_id=result.run_id)
    write_discovery_run(result.to_dict(), data_dir=edge_data_dir)
    search_end = result.discovery_end_date
    challenger_panel = panel[pd.to_datetime(panel["trade_date"]) <= pd.Timestamp(search_end)].copy()
    ledger = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    chal = run_challenger(challenger_panel, ledger, discovery_run_id=result.run_id, force=True)
    write_challenger_run(chal.to_dict(), data_dir=edge_data_dir)
    update_ledger_robustness(chal.results, chal.run_id, data_dir=edge_data_dir)
    freeze = freeze_eligible_candidates(data_dir=edge_data_dir, panel=challenger_panel)
    assert freeze.frozen_count >= 1
    spec = freeze.frozen[0].spec
    assert spec is not None
    pos = evaluate_frozen_hypothesis_oos(spec, panel)
    assert pos.result == OOS_STATUS_PASS, pos.to_dict()
    promote_oos_pass_to_memory(spec, pos, data_dir=edge_data_dir)
    assert count_active_edges(edge_data_dir) == 1

    clauses = clauses_from_frozen_spec(spec)
    assert "NEW1" not in cohort_symbols
    future_rows = [
        _t0_row("NEW1", clauses=clauses, satisfy=True),
        _t0_row("S000", clauses=clauses, satisfy=False),
        _t0_row("FILL1", clauses=clauses, satisfy=False),
        _t0_row("FILL2", clauses=clauses, satisfy=False),
        _t0_row("FILL3", clauses=clauses, satisfy=False),
    ]
    freeze_df = _freeze_df(future_rows)
    market = {
        "research_market_state": spec.market_state,
        "research_market_transition": spec.market_transition,
    }
    assessment = _run_fr(edge_data_dir, freeze_df, market)
    assert assessment["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND
    assert assessment["qualified_match_count"] == 1
    match = assessment["matches"][0]
    assert match["symbol"] == "NEW1"
    assert match["edge_id"] == spec.edge_id
    assert match["context_verdict"] == CONTEXT_COMPATIBLE
    assert match["live_forward_status"] == FORWARD_OUTCOME_PENDING
    assert "RESEARCH MATCH" in match["research_label"]
    births = read_ledger("edge_forward_ledger.csv", edge_data_dir)
    assert len(births) == 1
    assert str(births.iloc[0]["symbol"]) == "NEW1"
    assert str(births.iloc[0]["hypothesis_id"]) == spec.hypothesis_id
    assert str(births.iloc[0]["outcome_status"]) == FORWARD_OUTCOME_PENDING
    for col in ("t3_return", "t5_return", "t10_return"):
        assert col not in births.columns or str(births.iloc[0].get(col) or "") in ("", "nan")
    surface = format_future_recognition_operator_text(assessment)
    assert "NEW1" in surface
    assert spec.edge_id in surface
    assert "LIVE_FORWARD" in surface
    sidecar = json.loads((edge_data_dir / "daily_edge_matches" / f"{FUTURE_DATE}.json").read_text())
    assert sidecar["matches"][0]["symbol"] == "NEW1"
    rerun = _run_fr(edge_data_dir, freeze_df, market)
    assert rerun["new_birth_count"] == 0
    assert len(read_ledger("edge_forward_ledger.csv", edge_data_dir)) == 1
    fr_src = inspect.getsource(importlib.import_module("modules.edge_research.future_recognition"))
    assert "NEW1" not in fr_src
    assert load_frozen_spec(spec.hypothesis_id, edge_data_dir) is not None


def test_negative_controls_a_through_j(edge_data_dir, tmp_path):
    """A–J negative controls from the Phase B contract."""
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    clauses = clauses_from_frozen_spec(spec)
    new1 = _freeze_df(
        [
            _t0_row("NEW1", clauses=clauses, satisfy=True),
            _t0_row("OUT", clauses=clauses, satisfy=False),
        ]
    )

    # A. incompatible market
    a = _run_fr(edge_data_dir, new1, INCOMPATIBLE_MARKET)
    assert a["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert a["qualified_match_count"] == 0

    # B. compatible + outside clauses
    b = _run_fr(
        edge_data_dir,
        _freeze_df([_t0_row("OUT", clauses=clauses, satisfy=False)]),
        COMPATIBLE_MARKET,
    )
    assert b["qualified_match_count"] == 0
    assert b["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH

    # C. missing critical feature
    c = _run_fr(
        edge_data_dir,
        _freeze_df(
            [
                _t0_row("MISS", clauses=clauses, satisfy=True, drop=clauses[0].feature),
                _t0_row("KEEP", clauses=clauses, satisfy=False),
            ]
        ),
        COMPATIBLE_MARKET,
    )
    assert c["qualified_match_count"] == 0

    # D. no ACTIVE edges
    empty_dir = tmp_path / "no_active"
    ensure_storage(empty_dir)
    d = _run_fr(empty_dir, new1, COMPATIBLE_MARKET)
    assert d["assessment_state"] == ASSESSMENT_NO_QUALIFIED_MATCH
    assert d["reason"] == REASON_NO_ACTIVE_EDGE_AVAILABLE

    # E. missing T0
    e = _run_fr(
        edge_data_dir,
        new1,
        COMPATIBLE_MARKET,
        freeze_df=None,
        freeze_path=tmp_path / "missing_freeze.csv",
    )
    assert e["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS

    # F. UNKNOWN market
    f = _run_fr(edge_data_dir, new1, UNKNOWN_MARKET)
    assert f["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert f["reason"] == "MARKET_CONTEXT_UNKNOWN"

    # G. hash mismatch
    path = edge_data_dir / "frozen_specs" / f"{spec.hypothesis_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["best_horizon"] = "T99"
    path.write_text(json.dumps(payload), encoding="utf-8")
    g = _run_fr(edge_data_dir, new1, COMPATIBLE_MARKET)
    assert g["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert g["qualified_match_count"] == 0

    # restore original frozen spec for remaining controls
    path.write_text(spec.serialize(), encoding="utf-8")

    # H. duplicate rerun
    h1 = _run_fr(edge_data_dir, new1, COMPATIBLE_MARKET)
    n_after = len(read_ledger("edge_forward_ledger.csv", edge_data_dir))
    h2 = _run_fr(edge_data_dir, new1, COMPATIBLE_MARKET)
    assert h1["assessment_state"] == ASSESSMENT_QUALIFIED_MATCH_FOUND
    assert h2["new_birth_count"] == 0
    assert len(read_ledger("edge_forward_ledger.csv", edge_data_dir)) == n_after

    # I. one symbol × two ACTIVE edges — isolated dir so prior births don't collide
    two_dir = tmp_path / "two_edges"
    ensure_storage(two_dir)
    a_spec = _activate(_minimal_spec(), two_dir)
    b_spec = _activate(_rsi_spec(), two_dir)
    dual = _t0_row("NEW1", clauses=clauses_from_frozen_spec(a_spec), satisfy=True)
    dual["rsi14"] = _values_for_clauses(clauses_from_frozen_spec(b_spec), satisfy=True)["rsi14"]
    i = _run_fr(two_dir, _freeze_df([dual]), COMPATIBLE_MARKET)
    assert i["qualified_match_count"] == 2
    assert len(read_ledger("edge_forward_ledger.csv", two_dir)) == 2

    # J. matcher exception does not corrupt T0
    freeze_path = tmp_path / "t0_j.csv"
    new1.to_csv(freeze_path, index=False)
    before = _digest(freeze_path)
    j = _run_fr(
        edge_data_dir,
        new1,
        COMPATIBLE_MARKET,
        freeze_path=freeze_path,
        raise_internal=ValueError("boom"),
    )
    assert j["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert j["reason"] == "MATCHER_EXCEPTION"
    assert _digest(freeze_path) == before


def test_systemic_missing_features_unable(edge_data_dir):
    ensure_storage(edge_data_dir)
    spec = _activate(_minimal_spec(), edge_data_dir)
    feat = clauses_from_frozen_spec(spec)[0].feature
    rows = []
    for i, sym in enumerate(["A", "B", "C", "D"]):
        row = _t0_row(sym, clauses=clauses_from_frozen_spec(spec), satisfy=True)
        row.pop(feat, None)
        rows.append(row)
    result = _run_fr(edge_data_dir, _freeze_df(rows), COMPATIBLE_MARKET)
    assert result["assessment_state"] == ASSESSMENT_UNABLE_TO_ASSESS
    assert result["reason"] == "FEATURE_CONTRACT_UNAVAILABLE"


def test_eod_hook_isolated_from_qualification_cycle():
    from modules.edge_research.engine import EdgeResearchEngine

    src = inspect.getsource(EdgeResearchEngine.run_qualification_cycle)
    assert "run_future_recognition" not in src
    src_fr = inspect.getsource(EdgeResearchEngine.run_future_recognition)
    assert "update_learning" not in src_fr
    assert "mature_forward" not in src_fr
