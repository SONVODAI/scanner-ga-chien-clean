"""
Phase 3K.5B — WAITING_FOR_DATA same-day retry vs terminal idempotency.

Regression for production defect where a frozen early WAITING_FOR_DATA attempt
permanently blocked later timer cycles after source coverage advanced.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (  # noqa: E402
    run_production_daily_research,
)
from modules.edge_research.opr_bridge.production_daily_run_persistence import (  # noqa: E402
    lookup_run,
    lookup_run_for_date,
    load_run_index,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (  # noqa: E402
    BACKFILL_NON_FORWARD,
)
from modules.edge_research.opr_bridge.production_observation_persistence import (  # noqa: E402
    load_observation_index,
)
from modules.edge_research.opr_bridge.production_scheduling_contract import (  # noqa: E402
    build_scheduling_contract,
)


def _mini_panel(dates: list[str], *, symbols: int = 8) -> pd.DataFrame:
    rows = []
    for d in dates:
        for i in range(symbols):
            rows.append(
                {
                    "trade_date": d,
                    "symbol": f"S{i:03d}",
                    "rs_spread": float(i - symbols / 2),
                    "t3_return": 0.01 * (i % 3 - 1),
                    "t5_return": 0.01 * (i % 5 - 2),
                    "t10_return": 0.01 * (i % 7 - 3),
                }
            )
    return pd.DataFrame(rows)


def test_waiting_then_source_advance_creates_new_attempt_not_frozen_replay():
    early_dates = [f"2026-01-{d:02d}" for d in range(1, 11)]  # through 01-10
    target = "2026-01-15"
    full_dates = [f"2026-01-{d:02d}" for d in range(1, 16)]  # through 01-15

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        early = _mini_panel(early_dates)
        r1 = run_production_daily_research(
            early,
            target_trade_date=target,
            run_mode=BACKFILL_NON_FORWARD,
            data_dir=data_dir,
            repo_root=REPO,
        )
        assert r1["idempotent_replay"] is False
        assert r1["run"]["run_disposition"] == "WAITING_FOR_DATA"
        assert r1["run"]["frozen"] is True
        waiting_id = r1["run"]["run_id"]
        waiting_blob = lookup_run(waiting_id, data_dir=data_dir).to_dict()

        # Unchanged source → idempotent WAITING replay (18:35 == 20:05 still incomplete)
        r1b = run_production_daily_research(
            early,
            target_trade_date=target,
            run_mode=BACKFILL_NON_FORWARD,
            data_dir=data_dir,
            repo_root=REPO,
        )
        assert r1b["idempotent_replay"] is True
        assert r1b["idempotent_reason"] == "waiting_unchanged"
        assert r1b["run"]["run_id"] == waiting_id

        # Source advances to include target → new attempt, not frozen WAITING replay
        ready = _mini_panel(full_dates)
        r2 = run_production_daily_research(
            ready,
            target_trade_date=target,
            run_mode=BACKFILL_NON_FORWARD,
            data_dir=data_dir,
            repo_root=REPO,
        )
        assert r2["idempotent_replay"] is False
        assert r2["run"]["run_id"] != waiting_id
        assert r2["run"]["run_disposition"] == "SUCCESS"
        assert r2["run"]["frozen"] is True

        # Old WAITING audit record preserved byte-stable
        after = lookup_run(waiting_id, data_dir=data_dir).to_dict()
        assert after == waiting_blob
        assert after["run_disposition"] == "WAITING_FOR_DATA"

        # Authoritative date lookup prefers SUCCESS
        authoritative = lookup_run_for_date(target, BACKFILL_NON_FORWARD, data_dir=data_dir)
        assert authoritative is not None
        assert authoritative.run_id == r2["run"]["run_id"]
        assert authoritative.run_disposition == "SUCCESS"

        idx = load_run_index(data_dir)
        assert waiting_id in idx["runs"]
        assert r2["run"]["run_id"] in idx["runs"]


def test_identical_ready_data_remains_idempotent_no_duplicate_budget():
    dates = [f"2026-01-{d:02d}" for d in range(1, 16)]
    target = "2026-01-12"
    panel = _mini_panel(dates)

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        r1 = run_production_daily_research(
            panel,
            target_trade_date=target,
            run_mode=BACKFILL_NON_FORWARD,
            data_dir=data_dir,
            repo_root=REPO,
        )
        assert r1["run"]["run_disposition"] == "SUCCESS"
        births_1 = set(r1["run"].get("observations_born") or [])
        obs_after_1 = set(load_observation_index(data_dir).get("observations", {}).keys())

        r2 = run_production_daily_research(
            panel,
            target_trade_date=target,
            run_mode=BACKFILL_NON_FORWARD,
            data_dir=data_dir,
            repo_root=REPO,
        )
        assert r2["idempotent_replay"] is True
        assert r2["idempotent_reason"] == "terminal_success_or_skip"
        assert r2["run"]["run_id"] == r1["run"]["run_id"]

        obs_after_2 = set(load_observation_index(data_dir).get("observations", {}).keys())
        assert obs_after_2 == obs_after_1

        success_runs = [
            m
            for m in load_run_index(data_dir).get("runs", {}).values()
            if m.get("target_trade_date") == target
            and m.get("run_mode") == BACKFILL_NON_FORWARD
            and m.get("run_disposition") == "SUCCESS"
        ]
        assert len(success_runs) == 1
        # Birth set from first success remains the sole research budget for the day
        assert set(lookup_run(r1["run"]["run_id"], data_dir=data_dir).observations_born) == births_1


def test_waiting_then_ready_same_identity_allocates_attempt_suffix_without_overwrite():
    """
    If panel hash is unchanged but readiness flips to ready (EOD external advance),
    allocate a non-colliding run_id and never rewrite the frozen WAITING record.
    """
    from modules.edge_research.opr_bridge.production_daily_run_persistence import allocate_daily_run_id
    from modules.edge_research.opr_bridge.production_daily_run_records import compute_run_identity, new_run_id
    from modules.edge_research.opr_bridge.production_data_readiness_gate import DataReadinessResult
    from modules.edge_research.opr_bridge.production_daily_run_persistence import (
        persist_run,
        resolve_idempotent_daily_run,
    )
    from modules.edge_research.opr_bridge.production_daily_run_records import ProductionDailyResearchRun
    from modules.edge_research.opr_bridge.evidence_synthesis_records import utc_now_iso

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        identity = compute_run_identity(
            target_trade_date="2026-08-24",
            run_mode=BACKFILL_NON_FORWARD,
            source_dataset_hash="abc123",
            policy_hash_bundle="pol",
        )
        waiting_id = new_run_id(identity)
        waiting = ProductionDailyResearchRun(
            run_id=waiting_id,
            target_trade_date="2026-08-24",
            run_mode=BACKFILL_NON_FORWARD,
            run_started_at="2026-08-24T11:35:06Z",
            run_completed_at="2026-08-24T11:35:06Z",
            cutoff=None,
            source_dataset_identity="research_panel:abc123",
            source_dataset_hash="abc123",
            source_max_trade_date="2026-08-18",
            researcher_visible_max_trade_date="2026-08-18",
            market_context_identity=None,
            market_context_hash=None,
            prior_successful_run_id=None,
            policy_version_hashes={},
            observations_born=(),
            observations_reassessed=(),
            forward_outcomes_released=(),
            daily_summary_id=None,
            run_disposition="WAITING_FOR_DATA",
            failure_or_skip_reason="target_date_not_in_panel_sessions",
            counts_as_forward_evidence=False,
            current_phase="RUN_FINALIZED",
            phase_history=(),
            run_identity_hash=identity,
            frozen=True,
        )
        persist_run(waiting, data_dir=data_dir, allow_overwrite=True)
        before = json.loads((data_dir / "production_observations" / "daily_runs" / f"{waiting_id}.json").read_text())

        ready = DataReadinessResult(
            ready=True,
            disposition="READY",
            reason="ok",
            source_max_trade_date="2026-08-24",
            researcher_visible_max_trade_date="2026-08-24",
            source_dataset_identity="research_panel:abc123",
            source_dataset_hash="abc123",
            temporal_provenance_established=True,
            market_context_available=True,
            market_context_classification="OK",
            eod_completeness_established=True,
            eod_completeness_reason=None,
            calendar_eligible=True,
            errors=(),
        )
        existing, kind = resolve_idempotent_daily_run(
            "2026-08-24", BACKFILL_NON_FORWARD, readiness=ready, data_dir=data_dir
        )
        assert existing is None and kind is None

        allocated = allocate_daily_run_id(identity, data_dir=data_dir)
        assert allocated != waiting_id
        assert allocated == f"{waiting_id}-a2"

        after = json.loads((data_dir / "production_observations" / "daily_runs" / f"{waiting_id}.json").read_text())
        assert after == before


def test_scheduling_contract_documents_waiting_retry_policy():
    c = build_scheduling_contract()
    assert c["concurrency"]["waiting_for_data_policy"] == "retry_when_source_or_eod_advances"
    assert "unchanged_waiting" in c["concurrency"]["duplicate_same_day"]
    assert len(c["retry"]["same_day_timer_attempts"]) == 3
