"""
End-to-end autonomous daily pipeline production-contract tests.

Proves: valid session → headless T0 → Edge panel → LIVE_FORWARD → SESSION_MARKET_VOICE
→ receipt PASS, without Streamlit. Cases 1–9 from the release contract.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.blind_research_examination_runner import (
    compute_research_policy_hashes,
)
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (
    run_production_daily_research,
)
from modules.edge_research.opr_bridge.production_live_forward_genesis import (
    build_genesis_record,
    genesis_exists,
    persist_genesis,
)
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    session_voice_path,
)
from modules.edge_research.opr_bridge.production_living_research_ui_read_model import (
    build_living_research_ui_read_model,
    resolve_production_data_dir,
)
from modules.edge_research.opr_bridge.production_panel_freshness import diagnose_panel_freshness
from modules.edge_research.storage import resolve_production_runs_root
from modules.production_daily_receipt import (
    OVERALL_PASS,
    OVERALL_SKIPPED,
    OVERALL_WAITING,
    build_daily_pipeline_receipt,
    receipt_path,
    write_receipt_from_run,
)
from modules.production_eod.headless_eod import run_headless_eod
from tests.test_headless_eod_zero_touch import EXPECTED_UNIVERSE, _run, _synth_scan, _vn


@pytest.fixture(autouse=True)
def _offline_hooks(monkeypatch):
    def _fake_p0(trade_date: str, *, data_dir=None):
        from modules.forecast_research.p0_daily import collect_p0_for_date

        return collect_p0_for_date(trade_date, data_dir=data_dir, collect_foreign=False)

    monkeypatch.setattr(
        "modules.forecast_research.p0_daily.maybe_collect_p0_after_market_daily",
        lambda trade_date, data_dir=None: _fake_p0(trade_date, data_dir=data_dir),
    )
    monkeypatch.setattr(
        "modules.foreign_flow_confirmation.daily.maybe_run_ff_confirmation_after_market_daily",
        lambda trade_date, **kwargs: {
            "ok": True,
            "written": False,
            "skipped": True,
            "reason": "test_stub_no_network",
            "trade_date": str(trade_date)[:10],
            "stage": "ff_confirmation_forward",
        },
    )


def _plant_live_forward_genesis(tmp: Path, edge_dir: Path, first_eligible: str) -> None:
    """Plant irreversible LIVE_FORWARD genesis once for fixture runtime."""
    if genesis_exists(edge_dir):
        return
    # Policy hashes must match orchestrator (computed from repo_root=tmp → empty
    # when opr_bridge sources are absent under the fixture tree). Use REPO hashes
    # and mirror the hashed modules so LIVE_FORWARD genesis gate passes.
    policy = compute_research_policy_hashes(REPO)
    src_root = REPO / "modules" / "edge_research" / "opr_bridge"
    dst_root = tmp / "modules" / "edge_research" / "opr_bridge"
    dst_root.mkdir(parents=True, exist_ok=True)
    for name in policy:
        src = src_root / name
        if src.exists():
            dst = dst_root / name
            if not dst.exists():
                dst.write_bytes(src.read_bytes())
    genesis = build_genesis_record(
        first_eligible_trade_date=first_eligible,
        code_commit="e2e-fixture",
        policy_hashes=policy,
        dataset_identities={"panel": "e2e_fixture"},
        deployment_identity="e2e_autonomous_daily_pipeline",
    )
    persist_genesis(genesis, data_dir=edge_dir)


def _plant_prior_sessions(tmp: Path, dates: list[str]) -> None:
    """Ensure panel has prior history so Edge research has context."""
    el = tmp / "data" / "earning_learning"
    el.mkdir(parents=True, exist_ok=True)
    rows = []
    for td in dates:
        for i in range(EXPECTED_UNIVERSE):
            rows.append(
                {
                    "observation_id": f"{td}-S{i:03d}",
                    "trade_date": td,
                    "symbol": f"S{i:03d}",
                    "price": 100 + i,
                    "rsi14": 50,
                    "rs5": 1.0,
                    "rs10": 0.5,
                    "rs_spread": 0.5,
                    "frozen_at": f"{td}T10:00:00+00:00",
                }
            )
    df = pd.DataFrame(rows)
    obs_path = el / "observations.csv"
    freeze_path = el / "t0_observation_freeze.csv"
    if obs_path.exists():
        df = pd.concat([pd.read_csv(obs_path), df], ignore_index=True)
    df.to_csv(obs_path, index=False)
    df.to_csv(freeze_path, index=False)


def _full_autonomous_day(tmp: Path, td: str, *, prior: list[str] | None = None) -> dict:
    """Headless EOD (no Streamlit) → panel → LIVE_FORWARD Edge → receipt."""
    if prior:
        _plant_prior_sessions(tmp, prior)
    with patch.dict("sys.modules", {"streamlit": None}):
        headless = _run(tmp, td, skip_forecast_memory=False)
    assert headless["ok"] is True
    assert headless["stage_disposition"] == "SUCCESS"

    panel = build_research_panel(repo_root=tmp)
    freshness = diagnose_panel_freshness(panel, td, headless_eod=headless)
    assert freshness["target_in_panel_sessions"] is True

    edge_dir = tmp / "data" / "edge_research"
    edge_dir.mkdir(parents=True, exist_ok=True)
    # Genesis first_eligible must be a VN trading session on/before target.
    _plant_live_forward_genesis(tmp, edge_dir, "2026-08-28")

    result = run_production_daily_research(
        panel,
        target_trade_date=td,
        run_mode="LIVE_FORWARD",
        data_dir=edge_dir,
        repo_root=tmp,
    )
    receipt = write_receipt_from_run(
        td,
        repo_root=tmp,
        edge_data_dir=edge_dir,
        headless_eod=headless,
        edge_result=result,
        panel_freshness=freshness,
        run_provenance={"recovery": False, "run_mode": "LIVE_FORWARD", "autonomy_evidence": "AUTONOMOUS_PRODUCTION"},
    )
    return {
        "headless": headless,
        "panel": panel,
        "freshness": freshness,
        "result": result,
        "receipt": receipt,
        "edge_dir": edge_dir,
    }


def test_case1_valid_session_zero_discovery_pass_with_voice(tmp_path: Path):
    td = "2026-09-10"
    prior = [f"2026-09-{d:02d}" for d in range(1, 10) if date(2026, 9, d).weekday() < 5]
    out = _full_autonomous_day(tmp_path, td, prior=prior)
    run = out["result"]["run"]
    assert run["run_disposition"] == "SUCCESS"
    # Zero discovery is allowed
    assert isinstance(run.get("observations_born"), (list, tuple))
    voice = session_voice_path(td, out["edge_dir"])
    assert voice.exists()
    payload = json.loads(voice.read_text())
    assert payload["observation_id"] == "SESSION_MARKET_VOICE"
    rec = out["receipt"]["receipt"]
    assert rec["overall"] == OVERALL_PASS
    assert rec["daily_market_voice"]["exists"] is True
    assert rec["automation"]["streamlit_required"] is False
    assert receipt_path(td, repo_root=tmp_path).exists()


def test_case2_valid_session_with_discovery_represented(tmp_path: Path):
    td = "2026-09-11"
    prior = [f"2026-09-{d:02d}" for d in range(1, 11) if date(2026, 9, d).weekday() < 5]
    out = _full_autonomous_day(tmp_path, td, prior=prior)
    run = out["result"]["run"]
    assert run["run_disposition"] == "SUCCESS"
    manifest = out["result"].get("manifest") or {}
    # Discovery may be 0 or >0 depending on Brain; both valid. Represented correctly:
    assert "discovery_count" in manifest
    assert manifest.get("bot_spoke_today") is True
    assert session_voice_path(td, out["edge_dir"]).exists()
    assert out["receipt"]["receipt"]["overall"] == OVERALL_PASS


def test_case3_missing_t0_waiting(tmp_path: Path):
    # Weekday missing from panel T0 (not a weekend — calendar skip is a different case).
    td = "2026-09-15"
    # Prior sessions only — target date absent from panel T0 sources.
    _plant_prior_sessions(tmp_path, [f"2026-09-{d:02d}" for d in range(1, 12) if date(2026, 9, d).weekday() < 5])
    panel = build_research_panel(repo_root=tmp_path)
    assert td not in set(panel["trade_date"].astype(str))
    edge_dir = tmp_path / "data" / "edge_research"
    edge_dir.mkdir(parents=True, exist_ok=True)
    _plant_live_forward_genesis(tmp_path, edge_dir, "2026-08-28")
    result = run_production_daily_research(
        panel,
        target_trade_date=td,
        run_mode="LIVE_FORWARD",
        data_dir=edge_dir,
        repo_root=tmp_path,
    )
    assert result["run"]["run_disposition"] == "WAITING_FOR_DATA"
    assert result["run"]["failure_or_skip_reason"] == "target_date_not_in_panel_sessions"
    freshness = diagnose_panel_freshness(panel, td, headless_eod={"stage_disposition": "SUCCESS", "ok": True})
    receipt = write_receipt_from_run(
        td,
        repo_root=tmp_path,
        edge_data_dir=edge_dir,
        headless_eod={"stage_disposition": "SUCCESS", "ok": True, "source_rows": 142},
        edge_result=result,
        panel_freshness=freshness,
        run_provenance={"recovery": False, "run_mode": "LIVE_FORWARD"},
    )
    rec = receipt["receipt"]
    assert rec["overall"] == OVERALL_WAITING
    assert rec["first_failed_stage"] in ("stock_t0", "edge_panel")
    assert not session_voice_path(td, edge_dir).exists()


def test_case4_genuine_non_trading_day_skipped(tmp_path: Path):
    td = "2026-09-13"  # Sunday
    headless = run_headless_eod(
        td,
        repo_root=tmp_path,
        scan_df=_synth_scan(EXPECTED_UNIVERSE, td),
        now=_vn(td, hour=19),
        trading_today=False,
        trading_reason="injected_non_trading",
        allow_before_close_for_tests=False,
        skip_forecast_memory=True,
    )
    assert headless["stage_disposition"] == "SKIPPED_NON_TRADING_DAY"
    panel = build_research_panel(repo_root=tmp_path)
    edge_dir = tmp_path / "data" / "edge_research"
    edge_dir.mkdir(parents=True, exist_ok=True)
    _plant_live_forward_genesis(tmp_path, edge_dir, "2026-08-28")
    # Edge calendar may also skip weekends
    result = run_production_daily_research(
        panel if not panel.empty else pd.DataFrame({"trade_date": ["2026-09-11"], "symbol": ["AAA"], "rs_spread": [1.0]}),
        target_trade_date=td,
        run_mode="LIVE_FORWARD",
        data_dir=edge_dir,
        repo_root=tmp_path,
    )
    assert result["run"]["run_disposition"] == "SKIPPED_NON_TRADING_DAY"
    receipt = write_receipt_from_run(
        td,
        repo_root=tmp_path,
        edge_data_dir=edge_dir,
        headless_eod=headless,
        edge_result=result,
        panel_freshness={"target_in_panel_sessions": False},
        run_provenance={"recovery": False, "run_mode": "LIVE_FORWARD"},
    )
    assert receipt["receipt"]["overall"] == OVERALL_SKIPPED


def test_case5_probe_failure_not_non_trading(tmp_path: Path):
    from modules.production_eod import headless_eod as he

    td = "2026-09-15"
    with patch.object(
        he,
        "resolve_trading_today",
        return_value=he.TradingDayProbeResult(
            trading_today=None,
            reason="TRADING_DAY_PROBE_FAILED:unavailable:no_vnindex_bars",
            probe_status=he.PROBE_FAILED,
        ),
    ):
        result = run_headless_eod(
            td,
            repo_root=tmp_path,
            scan_df=_synth_scan(EXPECTED_UNIVERSE, td),
            now=_vn(td, hour=19),
            trading_today=None,
            allow_before_close_for_tests=False,
            skip_forecast_memory=True,
        )
    assert result["stage_disposition"] == "TRADING_DAY_PROBE_FAILED"
    assert "SKIPPED_NON_TRADING" not in result["stage_disposition"]
    receipt = build_daily_pipeline_receipt(
        td,
        repo_root=tmp_path,
        headless_eod=result,
        edge_result={"run": {"run_disposition": "WAITING_FOR_DATA", "failure_or_skip_reason": "target_date_not_in_panel_sessions"}},
        panel_freshness={"target_in_panel_sessions": False},
        run_provenance={"recovery": False},
    )
    assert receipt["overall"] == "FAIL"
    assert receipt["first_failed_stage"] == "trading_day_probe"


def test_case6_frozen_observation_t_horizons_no_rewrite(tmp_path: Path):
    td_birth = "2026-09-08"
    td_assess = "2026-09-09"
    prior = [f"2026-09-{d:02d}" for d in range(1, 8) if date(2026, 9, d).weekday() < 5]
    out1 = _full_autonomous_day(tmp_path, td_birth, prior=prior)
    assert out1["result"]["run"]["run_disposition"] == "SUCCESS"
    births = list(out1["result"]["run"].get("observations_born") or [])
    # Second day reassessment (may or may not birth new)
    with patch.dict("sys.modules", {"streamlit": None}):
        headless2 = _run(tmp_path, td_assess)
    panel = build_research_panel(repo_root=tmp_path)
    edge_dir = out1["edge_dir"]
    result2 = run_production_daily_research(
        panel,
        target_trade_date=td_assess,
        run_mode="LIVE_FORWARD",
        data_dir=edge_dir,
        repo_root=tmp_path,
    )
    assert result2["run"]["run_disposition"] == "SUCCESS"
    # Prior birth records remain (idempotent index)
    from modules.edge_research.opr_bridge.production_observation_persistence import (
        load_observation_index,
        lookup_birth_record,
    )

    idx = load_observation_index(edge_dir)
    for oid in births:
        birth = lookup_birth_record(oid, data_dir=edge_dir)
        assert birth is not None
        assert birth.cutoff.trade_date == td_birth
    assert session_voice_path(td_assess, edge_dir).exists()
    assert oid in idx.get("observations", {}) if births else True


def test_case7_ui_backend_canonical_root_equal(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    prod = edge / "production_observations"
    prod.mkdir(parents=True)
    (prod / "daily_run_index.json").write_text(
        json.dumps({"runs": {"r1": {"run_id": "r1", "target_trade_date": "2026-09-10", "run_disposition": "SUCCESS", "run_mode": "LIVE_FORWARD"}}}),
        encoding="utf-8",
    )
    assert resolve_production_runs_root(edge) == prod
    assert resolve_production_data_dir(edge) == prod
    assert resolve_production_data_dir(prod) == prod
    rm = build_living_research_ui_read_model(data_dir=edge)
    assert rm["health"]["latest_successful_research_date"] == "2026-09-10"


def test_case8_foreign_flow_wired_counts_only_no_peek(tmp_path: Path):
    from modules.forecast_research.production_daily_integration import run_forecast_memory_daily_stage
    import inspect

    src = inspect.getsource(run_forecast_memory_daily_stage)
    assert "maybe_run_ff_confirmation_after_market_daily" in src
    # Receipt FF section must not contain performance peek fields
    receipt = build_daily_pipeline_receipt(
        "2026-09-10",
        repo_root=tmp_path,
        headless_eod={
            "stage_disposition": "SUCCESS",
            "artifacts": {
                "forecast_memory": {
                    "ff_confirmation_forward": {
                        "ok": True,
                        "written": False,
                        "skipped": True,
                        "reason": "test",
                        "stage": "ff_confirmation_forward",
                        "mean_ret": 1.23,  # poisoned — must not be copied
                        "win_rate": 0.9,
                    }
                }
            },
        },
        edge_result={"run": {"run_disposition": "WAITING_FOR_DATA", "failure_or_skip_reason": "x"}},
        panel_freshness={"target_in_panel_sessions": False},
    )
    ff = receipt["foreign_flow_confirmation"]
    blob = json.dumps(ff)
    assert "mean_ret" not in blob
    assert "win_rate" not in blob
    assert ff.get("anti_peeking") is True


def test_case9_idempotent_rerun_no_destructive_duplicate(tmp_path: Path):
    td = "2026-09-14"
    prior = [f"2026-09-{d:02d}" for d in range(1, 14) if date(2026, 9, d).weekday() < 5]
    out1 = _full_autonomous_day(tmp_path, td, prior=prior)
    assert out1["result"]["run"]["run_disposition"] == "SUCCESS"
    panel = build_research_panel(repo_root=tmp_path)
    result2 = run_production_daily_research(
        panel,
        target_trade_date=td,
        run_mode="LIVE_FORWARD",
        data_dir=out1["edge_dir"],
        repo_root=tmp_path,
    )
    assert result2.get("idempotent_replay") is True or result2["run"]["run_disposition"] == "SUCCESS"
    # EMS rows for date remain 142 (no duplicate destructive expansion beyond universe)
    ems = pd.read_csv(tmp_path / "data" / "earning_money_snapshots.csv")
    day = ems[ems["snapshot_date"].astype(str).str[:10] == td]
    assert len(day) == EXPECTED_UNIVERSE
    obs = pd.read_csv(tmp_path / "data" / "earning_learning" / "observations.csv")
    day_obs = obs[obs["trade_date"].astype(str).str[:10] == td]
    assert day_obs["symbol"].nunique() == len(day_obs) == EXPECTED_UNIVERSE


def test_receipt_fail_safe_does_not_raise(tmp_path: Path):
    # Even with empty/broken inputs, write_receipt_from_run must not raise.
    out = write_receipt_from_run(
        "2099-01-01",
        repo_root=tmp_path,
        headless_eod=None,
        edge_result=None,
    )
    assert "ok" in out
    assert out.get("receipt") is not None or out.get("error")
