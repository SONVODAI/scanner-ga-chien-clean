"""
Phase 3K.2 — Production daily research run orchestrator.

Infrastructure/orchestration only — no scientific policy changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.blind_research_examination_runner import compute_research_policy_hashes
from modules.edge_research.opr_bridge.production_daily_manifest import build_daily_manifest
from modules.edge_research.opr_bridge.production_daily_run_observability import DailyRunObservability
from modules.edge_research.opr_bridge.production_daily_run_persistence import (
    load_phase_marker,
    lookup_prior_successful_run,
    lookup_run,
    lookup_run_for_date,
    persist_manifest,
    persist_phase_marker,
    persist_run,
    phase_completed,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (
    BACKFILL_NON_FORWARD,
    HISTORICAL_REPLAY_TEST,
    LIVE_FORWARD,
    ProductionDailyResearchRun,
    RunDisposition,
    RunPhase,
    compute_run_identity,
    mode_counts_as_forward_evidence,
    new_run_id,
    STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY,
)
from modules.edge_research.opr_bridge.production_data_readiness_gate import verify_data_readiness
from modules.edge_research.opr_bridge.production_forward_clock import build_forward_clock_ledger
from modules.edge_research.opr_bridge.production_living_research_observation import (
    list_active_observation_ids,
    run_daily_living_assessment,
)
from modules.edge_research.opr_bridge.production_notification_contract import build_notification_events
from modules.edge_research.opr_bridge.production_observation_cutoff import (
    build_observation_cutoff,
    compute_market_context_identity,
    truncate_panel_at_cutoff,
)
from modules.edge_research.opr_bridge.production_observation_persistence import (
    birth_record_exists,
    load_observation_index,
)
from modules.edge_research.opr_bridge.production_observation_records import DEFAULT_SHADOW_AUTHORITY
from modules.edge_research.opr_bridge.production_research_observation import run_production_research_observation
from modules.edge_research.opr_bridge.production_trading_session_eligibility import (
    extract_panel_trading_sessions,
)
from modules.edge_research.opr_bridge.evidence_synthesis_records import utc_now_iso


def _policy_bundle(policy_hashes: Dict[str, str]) -> str:
    from modules.edge_research.opr_bridge.production_observation_cutoff import compute_policy_hash_bundle
    return compute_policy_hash_bundle(policy_hashes)


def _append_phase(run: ProductionDailyResearchRun, phase: str) -> None:
    history = list(run.phase_history)
    history.append({"phase": phase, "timestamp": utc_now_iso()})
    run.phase_history = tuple(history)
    run.current_phase = phase


def _finalize_skip_run(
    run: ProductionDailyResearchRun,
    *,
    disposition: str,
    reason: str,
    obs: DailyRunObservability,
    data_dir: Optional[Path],
) -> Dict[str, Any]:
    run.run_disposition = disposition
    run.failure_or_skip_reason = reason
    run.run_completed_at = utc_now_iso()
    run.frozen = True
    _append_phase(run, RunPhase.RUN_FINALIZED.value)
    persist_run(run, data_dir=data_dir)
    obs.skip_or_fail(disposition=disposition, reason=reason)
    obs.run_finalized(disposition=disposition)
    manifest = build_daily_manifest(run)
    persist_manifest(manifest, data_dir=data_dir)
    notifications = build_notification_events(run, manifest)
    return {
        "run": run.to_dict(),
        "manifest": manifest.to_dict(),
        "notifications": [n.to_dict() for n in notifications],
        "observability": obs.to_dict(),
        "idempotent_replay": False,
        "stop_boundary": STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY,
    }


def run_production_daily_research(
    panel: pd.DataFrame,
    *,
    target_trade_date: str,
    run_mode: str = BACKFILL_NON_FORWARD,
    data_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    resume_run_id: Optional[str] = None,
    crash_after_phase: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute one complete production daily research run for target_trade_date.

    crash_after_phase: test hook — abort after named phase (crash recovery matrix).
    """
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    policy_hashes = compute_research_policy_hashes(repo_root)
    policy_bundle = _policy_bundle(policy_hashes)

    readiness = verify_data_readiness(panel, target_trade_date)
    dataset_hash = readiness.source_dataset_hash
    identity = compute_run_identity(
        target_trade_date=target_trade_date,
        run_mode=run_mode,
        source_dataset_hash=dataset_hash,
        policy_hash_bundle=policy_bundle,
    )
    run_id = resume_run_id or new_run_id(identity)

    existing = lookup_run_for_date(target_trade_date, run_mode, data_dir=data_dir)
    if existing and existing.frozen and not resume_run_id:
        return {
            "run": existing.to_dict(),
            "idempotent_replay": True,
            "stop_boundary": STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY,
        }

    if resume_run_id:
        run = lookup_run(resume_run_id, data_dir=data_dir)
        if run is None:
            raise ValueError(f"resume_run_not_found:{resume_run_id}")
    else:
        run = ProductionDailyResearchRun(
            run_id=run_id,
            target_trade_date=target_trade_date,
            run_mode=run_mode,
            run_started_at=utc_now_iso(),
            run_completed_at=None,
            cutoff=None,
            source_dataset_identity=readiness.source_dataset_identity,
            source_dataset_hash=dataset_hash,
            source_max_trade_date=readiness.source_max_trade_date,
            researcher_visible_max_trade_date=readiness.researcher_visible_max_trade_date,
            market_context_identity=None,
            market_context_hash=None,
            prior_successful_run_id=lookup_prior_successful_run(target_trade_date, data_dir=data_dir),
            policy_version_hashes=dict(policy_hashes),
            observations_born=(),
            observations_reassessed=(),
            forward_outcomes_released=(),
            daily_summary_id=None,
            run_disposition=RunDisposition.FAILED_CLOSED.value,
            failure_or_skip_reason=None,
            counts_as_forward_evidence=mode_counts_as_forward_evidence(run_mode),
            current_phase=RunPhase.STARTED.value,
            phase_history=(),
            run_identity_hash=identity,
        )
        persist_run(run, data_dir=data_dir, allow_overwrite=True)

    obs = DailyRunObservability(run_id, target_trade_date)
    obs.start()

    if not readiness.ready:
        obs.data_readiness(ready=False, disposition=readiness.disposition, reason=readiness.reason)
        return _finalize_skip_run(
            run,
            disposition=readiness.disposition,
            reason=readiness.reason,
            obs=obs,
            data_dir=data_dir,
        )

    obs.data_readiness(ready=True, disposition="READY", reason=readiness.reason)
    persist_phase_marker(run_id, RunPhase.DATA_READINESS.value, data_dir=data_dir)
    _append_phase(run, RunPhase.DATA_READINESS.value)
    if crash_after_phase == RunPhase.DATA_READINESS.value:
        raise RuntimeError(f"crash_simulated:{RunPhase.DATA_READINESS.value}")

    # Track observations before research to detect new births
    index_before = set(load_observation_index(data_dir).get("observations", {}).keys())

    # --- CUTOFF + RESEARCH (3K.0) ---
    if not phase_completed(run_id, RunPhase.CUTOFF_ESTABLISHED.value, data_dir=data_dir):
        truncated, _ = truncate_panel_at_cutoff(panel, target_trade_date)
        focal_dates = sorted(truncated["trade_date"].astype(str).unique().tolist())
        cutoff, _ = build_observation_cutoff(
            panel,
            data_cutoff_date=target_trade_date,
            policy_hashes=policy_hashes,
            focal_dates=focal_dates,
            repo_root=repo_root,
            observation_mode=run_mode,
        )
        run.cutoff = cutoff.to_dict()
        ctx_id, ctx_hash = compute_market_context_identity(truncated, target_trade_date)
        run.market_context_identity = ctx_id
        run.market_context_hash = ctx_hash
        run.researcher_visible_max_trade_date = cutoff.panel_max_trade_date
        obs.cutoff_established(cutoff_hash=cutoff.temporal_provenance_hash)
        persist_phase_marker(run_id, RunPhase.CUTOFF_ESTABLISHED.value, data_dir=data_dir)
        _append_phase(run, RunPhase.CUTOFF_ESTABLISHED.value)
        persist_run(run, data_dir=data_dir, allow_overwrite=True)
        if crash_after_phase == RunPhase.CUTOFF_ESTABLISHED.value:
            raise RuntimeError(f"crash_simulated:{RunPhase.CUTOFF_ESTABLISHED.value}")

    if not phase_completed(run_id, RunPhase.RESEARCH_COMPLETED.value, data_dir=data_dir):
        session = run_production_research_observation(
            panel,
            data_cutoff_date=target_trade_date,
            data_dir=data_dir,
            repo_root=repo_root,
            observation_mode=run_mode,
            persist=True,
        )
        obs.research_completed(
            observation_id=session.observation_id,
            outcome_kind=session.birth_record.observation_outcome_kind if session.birth_record else None,
        )
        persist_phase_marker(run_id, RunPhase.RESEARCH_COMPLETED.value, data_dir=data_dir)
        _append_phase(run, RunPhase.RESEARCH_COMPLETED.value)
        persist_run(run, data_dir=data_dir, allow_overwrite=True)
        if crash_after_phase == RunPhase.RESEARCH_COMPLETED.value:
            raise RuntimeError(f"crash_simulated:{RunPhase.RESEARCH_COMPLETED.value}")

    # --- BIRTHS ---
    if not phase_completed(run_id, RunPhase.BIRTHS_PERSISTED.value, data_dir=data_dir):
        index_after = set(load_observation_index(data_dir).get("observations", {}).keys())
        new_births = sorted(index_after - index_before)
        run.observations_born = tuple(new_births)
        obs.births_persisted(observation_ids=list(new_births))
        persist_phase_marker(run_id, RunPhase.BIRTHS_PERSISTED.value, data_dir=data_dir)
        _append_phase(run, RunPhase.BIRTHS_PERSISTED.value)
        persist_run(run, data_dir=data_dir, allow_overwrite=True)
        if crash_after_phase == RunPhase.BIRTHS_PERSISTED.value:
            raise RuntimeError(f"crash_simulated:{RunPhase.BIRTHS_PERSISTED.value}")

    # --- OUTCOMES + ASSESSMENTS (3K.1) ---
    active_ids = list_active_observation_ids(data_dir)
    assessment_result: Dict[str, Any] = {}

    if not phase_completed(run_id, RunPhase.ASSESSMENTS_COMPLETED.value, data_dir=data_dir):
        assessment_result = run_daily_living_assessment(
            panel,
            assessment_trade_date=target_trade_date,
            observation_ids=active_ids,
            data_dir=data_dir,
            persist=True,
            replay_mode=run_mode,
        )
        run.observations_reassessed = tuple(
            a.get("observation_id") for a in assessment_result.get("assessments", [])
        )
        run.forward_outcomes_released = tuple(
            oid
            for a in assessment_result.get("assessments", [])
            for oid in (a.get("forward_outcomes_newly_available") or [])
        )
        run.daily_summary_id = (assessment_result.get("summary") or {}).get("summary_id")
        obs.outcomes_released(outcome_ids=list(run.forward_outcomes_released))
        obs.assessments_completed(
            assessment_ids=[a.get("assessment_id") for a in assessment_result.get("assessments", [])]
        )
        persist_phase_marker(run_id, RunPhase.OUTCOMES_RELEASED.value, data_dir=data_dir)
        _append_phase(run, RunPhase.OUTCOMES_RELEASED.value)
        persist_phase_marker(run_id, RunPhase.ASSESSMENTS_COMPLETED.value, data_dir=data_dir)
        _append_phase(run, RunPhase.ASSESSMENTS_COMPLETED.value)
        persist_run(run, data_dir=data_dir, allow_overwrite=True)
        if crash_after_phase in (RunPhase.OUTCOMES_RELEASED.value, RunPhase.ASSESSMENTS_COMPLETED.value):
            raise RuntimeError(f"crash_simulated:{crash_after_phase}")
    else:
        assessment_result = run_daily_living_assessment(
            panel,
            assessment_trade_date=target_trade_date,
            observation_ids=active_ids,
            data_dir=data_dir,
            persist=True,
            replay_mode=run_mode,
        )
        run.observations_reassessed = tuple(
            a.get("observation_id") for a in assessment_result.get("assessments", [])
        )
        run.forward_outcomes_released = tuple(
            oid
            for a in assessment_result.get("assessments", [])
            for oid in (a.get("forward_outcomes_newly_available") or [])
        )
        run.daily_summary_id = (assessment_result.get("summary") or {}).get("summary_id")

    if not phase_completed(run_id, RunPhase.SUMMARY_COMPLETED.value, data_dir=data_dir):
        obs.summary_completed(summary_id=run.daily_summary_id)
        persist_phase_marker(run_id, RunPhase.SUMMARY_COMPLETED.value, data_dir=data_dir)
        _append_phase(run, RunPhase.SUMMARY_COMPLETED.value)
        persist_run(run, data_dir=data_dir, allow_overwrite=True)
        if crash_after_phase == RunPhase.SUMMARY_COMPLETED.value:
            raise RuntimeError(f"crash_simulated:{RunPhase.SUMMARY_COMPLETED.value}")

    # Forward clock ledger (audit artifact, not forward evidence in non-forward modes)
    sessions = extract_panel_trading_sessions(
        truncate_panel_at_cutoff(panel, target_trade_date)[0]
    )
    forward_clock = [
        e.to_dict()
        for e in build_forward_clock_ledger(
            active_ids,
            assessment_trade_date=target_trade_date,
            trading_sessions=sessions,
            data_dir=data_dir,
        )
    ]

    run.run_disposition = RunDisposition.SUCCESS.value
    run.run_completed_at = utc_now_iso()
    run.frozen = True
    _append_phase(run, RunPhase.RUN_FINALIZED.value)
    persist_run(run, data_dir=data_dir)
    persist_phase_marker(run_id, RunPhase.RUN_FINALIZED.value, data_dir=data_dir)
    obs.run_finalized(disposition=RunDisposition.SUCCESS.value)

    manifest = build_daily_manifest(run, assessment_results=assessment_result)
    persist_manifest(manifest, data_dir=data_dir)
    notifications = build_notification_events(run, manifest)

    return {
        "run": run.to_dict(),
        "manifest": manifest.to_dict(),
        "notifications": [n.to_dict() for n in notifications],
        "assessment_result": assessment_result,
        "forward_clock": forward_clock,
        "observability": obs.to_dict(),
        "idempotent_replay": False,
        "counts_as_forward_evidence": run.counts_as_forward_evidence,
        "stop_boundary": STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY,
    }


def run_production_simulation_15_sessions(
    panel: pd.DataFrame,
    *,
    start_trade_date: Optional[str] = None,
    num_sessions: int = 15,
    run_mode: str = HISTORICAL_REPLAY_TEST,
    data_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Simulate sequential production daily runs — NON_FORWARD, no policy tuning.
    """
    sessions = extract_panel_trading_sessions(panel)
    if not sessions:
        return {"error": "no_panel_sessions", "counts_as_forward_evidence": False}

    start = start_trade_date or sessions[0]
    if start not in sessions:
        start = sessions[0]
    start_idx = sessions.index(start)
    replay_dates = sessions[start_idx : start_idx + num_sessions]
    if len(replay_dates) < num_sessions:
        replay_dates = sessions[start_idx:]

    daily_runs = []
    crash_tests = []

    for i, d in enumerate(replay_dates):
        result = run_production_daily_research(
            panel,
            target_trade_date=d,
            run_mode=run_mode,
            data_dir=data_dir,
            repo_root=repo_root,
        )
        daily_runs.append({
            "trade_date": d,
            "run_id": result.get("run", {}).get("run_id"),
            "disposition": result.get("run", {}).get("run_disposition"),
            "idempotent_replay": result.get("idempotent_replay"),
        })

    # Crash/resume matrix on three boundaries (using last session date)
    if replay_dates:
        test_date = replay_dates[min(3, len(replay_dates) - 1)]
        for phase in (
            RunPhase.BIRTHS_PERSISTED.value,
            RunPhase.OUTCOMES_RELEASED.value,
            RunPhase.SUMMARY_COMPLETED.value,
        ):
            import tempfile
            from pathlib import Path as P
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = P(tmp)
                try:
                    run_production_daily_research(
                        panel,
                        target_trade_date=test_date,
                        run_mode=run_mode,
                        data_dir=tmp_dir,
                        repo_root=repo_root,
                        crash_after_phase=phase,
                    )
                    crash_tests.append({"phase": phase, "crashed": False})
                except RuntimeError as e:
                    if "crash_simulated" in str(e):
                        run_id = new_run_id(
                            compute_run_identity(
                                target_trade_date=test_date,
                                run_mode=run_mode,
                                source_dataset_hash=verify_data_readiness(panel, test_date).source_dataset_hash,
                                policy_hash_bundle=_policy_bundle(compute_research_policy_hashes(repo_root or P("."))),
                            )
                        )
                        resumed = run_production_daily_research(
                            panel,
                            target_trade_date=test_date,
                            run_mode=run_mode,
                            data_dir=tmp_dir,
                            repo_root=repo_root,
                            resume_run_id=run_id,
                        )
                        crash_tests.append({
                            "phase": phase,
                            "crashed": True,
                            "resumed": resumed.get("run", {}).get("run_disposition") == "SUCCESS",
                        })
                    else:
                        crash_tests.append({"phase": phase, "crashed": True, "error": str(e)})

        # Idempotent duplicate invocation
        dup = run_production_daily_research(
            panel,
            target_trade_date=replay_dates[-1],
            run_mode=run_mode,
            data_dir=data_dir,
            repo_root=repo_root,
        )
        idempotent_ok = dup.get("idempotent_replay") is True
    else:
        idempotent_ok = False

    return {
        "test_kind": "PRODUCTION_SIMULATION_15_SESSIONS",
        "run_mode": run_mode,
        "replay_dates": replay_dates,
        "num_sessions": len(replay_dates),
        "daily_runs": daily_runs,
        "crash_recovery_tests": crash_tests,
        "duplicate_invocation_idempotent": idempotent_ok,
        "counts_as_forward_evidence": False,
        "stop_boundary": STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY,
    }
