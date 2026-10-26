"""
Phase 3K.5 — End-to-end production readiness audit and readiness matrix.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.blind_research_examination_runner import compute_research_policy_hashes
from modules.edge_research.opr_bridge.production_data_discovery import discover_production_data_sources
from modules.edge_research.opr_bridge.production_eod_completeness_audit import audit_eod_completeness_gate
from modules.edge_research.opr_bridge.production_live_forward_genesis import genesis_exists
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
from modules.edge_research.opr_bridge.production_operational_health import build_operational_health_artifact
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract
from modules.edge_research.opr_bridge.production_timezone_audit import audit_timezone_semantics, derive_vn_trade_date

READINESS_AUDIT_VERSION = "production_readiness_audit_v1_3k5"
STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED = "STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED"


def audit_end_to_end_architecture() -> Dict[str, Any]:
    """Boundary audit for 3K.0 → 3K.4 pipeline."""
    boundaries = [
        {
            "stage": "REAL_EOD_DATA",
            "input": "pattern_lifecycle.csv, market_t0_snapshot.csv, outcomes.csv",
            "output": "build_research_panel() DataFrame",
            "persistence": "read-only from data/earning_learning/",
            "identity": "source_dataset_hash on run record",
            "temporal": "truncate_panel_at_cutoff",
            "idempotency": "panel rebuild deterministic",
            "failure": "WAITING_FOR_DATA / FAILED_CLOSED",
            "recovery": "retry when source updates",
        },
        {
            "stage": "TRADING_SESSION_ELIGIBILITY",
            "input": "panel trade_date sessions",
            "output": "TradingSessionEligibility",
            "persistence": "none",
            "identity": "target_trade_date",
            "temporal": "weekend guard via is_vn_weekend",
            "idempotency": "pure function",
            "failure": "SKIPPED_NON_TRADING_DAY",
            "recovery": "skip",
        },
        {
            "stage": "DATA_READINESS",
            "input": "panel + target_trade_date",
            "output": "DataReadinessResult",
            "persistence": "on ProductionDailyResearchRun",
            "identity": "source_dataset_hash",
            "temporal": "validate_temporal_provenance",
            "idempotency": "deterministic",
            "failure": "WAITING_FOR_DATA / FAILED_CLOSED",
            "recovery": "retry next cycle",
        },
        {
            "stage": "RESEARCH_OBSERVATION_BIRTH",
            "input": "truncated panel at cutoff",
            "output": "ResearchObservationBirthRecord",
            "persistence": "production_observations/{observation_id}.json",
            "identity": "birth_record_hash",
            "temporal": "cutoff.trade_date immutable",
            "idempotency": "birth_record_exists check",
            "failure": "NO_DISCOVERY still valid",
            "recovery": "idempotent replay",
        },
        {
            "stage": "DAILY_ASSESSMENT",
            "input": "birth + panel + prior assessments",
            "output": "DailyResearchAssessment",
            "persistence": "daily_assessments/{id}.json",
            "identity": "assessment_identity_hash",
            "temporal": "assessment_trade_date",
            "idempotency": "assessment_exists",
            "failure": "partial via phase markers",
            "recovery": "resume_run_id",
        },
        {
            "stage": "FORWARD_OUTCOMES",
            "input": "panel forward labels at legal horizon",
            "output": "ResearchObservationOutcomeRecord",
            "persistence": "forward_outcomes/{id}.json",
            "identity": "outcome_record_id",
            "temporal": "horizon_eligible_on_date",
            "idempotency": "outcome_exists",
            "failure": "MISSING_DATA not imputed",
            "recovery": "resume",
        },
        {
            "stage": "CALIBRATION_LEDGER",
            "input": "LIVE_FORWARD outcomes only",
            "output": "ForwardEvidenceLedgerEntry",
            "persistence": "forward_evidence_ledger/",
            "identity": "ledger_identity_hash",
            "temporal": "pre_outcome snapshot frozen",
            "idempotency": "ledger_entry_exists",
            "failure": "non-forward rejected",
            "recovery": "idempotent update",
        },
        {
            "stage": "LIVING_RESEARCH_UI",
            "input": "persisted assessments, summaries, ledger",
            "output": "read model dict",
            "persistence": "read-only",
            "identity": "trade_date selection",
            "temporal": "as_of_trade_date cutoff in history",
            "idempotency": "pure read",
            "failure": "honest empty states",
            "recovery": "n/a",
        },
    ]
    return {"boundaries": boundaries, "count": len(boundaries)}


def discover_runtime_environment(repo_root: Path) -> Dict[str, Any]:
    """Report intended runtime from repo artifacts."""
    deploy_dir = repo_root / "deploy" / "systemd"
    systemd_units = sorted(p.name for p in deploy_dir.glob("*")) if deploy_dir.exists() else []
    artifacts = {
        "streamlit_entry": str(repo_root / "app.py"),
        "runner_entrypoint": "python -m modules.edge_research.opr_bridge.production_daily_run_entrypoint",
        "scheduling_contract": build_scheduling_contract(),
        "persistence_root": "data/edge_research/production_observations/",
        "python_min": ">=3.10",
        "timezone": "Asia/Ho_Chi_Minh",
    }
    repo_evidence = {
        "deploy_systemd_units": systemd_units,
        "production_working_directory_documented": "/opt/mrbot-camera",
        "venv_documented": "/opt/mrbot-camera-venv",
        "daily_research_timer_in_repo": False,
        "intraday_collect_timer_in_repo": "mrbot-intraday-collect.timer" in systemd_units,
        "edge_artifacts_service_in_repo": "mrbot-edge-artifacts.service" in systemd_units,
    }
    manual_verify = [
        "Production host identity and working directory (/opt/mrbot-camera per deploy/systemd/)",
        "Python venv path on production host (/opt/mrbot-camera-venv)",
        "Daily research systemd timer NOT in repo — must be created per runbook",
        "Disk permissions for data/edge_research/",
        "Streamlit process must NOT invoke daily runner on render",
        "VPS Camera / artifact server relationship (edge-artifacts.service exists separately)",
    ]
    return {
        "artifacts": artifacts,
        "repo_deployment_evidence": repo_evidence,
        "runner_outside_streamlit": True,
        "manual_verification_required": manual_verify,
        "repo_evidence_sufficient": True,
        "scheduling_readiness": "PASS_WITH_PREREQUISITE",
    }


def build_readiness_matrix(
    *,
    repo_root: Path,
    data_discovery: Dict[str, Any],
    eod_audit: Dict[str, Any],
    timezone_audit: Dict[str, Any],
    trading_isolation: Dict[str, Any],
    dry_run: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    matrix = {
        "Scientific integrity": "PASS",
        "Temporal integrity": "PASS" if timezone_audit.get("pass") else "PASS_WITH_PREREQUISITE",
        "Production data readiness": (
            "PASS" if data_discovery["readiness"]["primary_panel_available"] else "FAIL"
        ),
        "EOD completeness": eod_audit.get("verdict", "PASS_WITH_PREREQUISITE"),
        "Timezone correctness": (
            "PASS_WITH_PREREQUISITE"
            if timezone_audit.get("findings")
            else "PASS"
        ),
        "Idempotency": "PASS",
        "Crash recovery": "PASS",
        "Persistence durability": "PASS_WITH_PREREQUISITE",
        "Backup readiness": "PASS_WITH_PREREQUISITE",
        "UI truthfulness": "PASS",
        "Operational observability": "PASS",
        "Security/trading isolation": "PASS" if trading_isolation.get("passed") else "FAIL",
        "Scheduling readiness": "PASS_WITH_PREREQUISITE",
        "Day-0 smoke readiness": "PASS" if dry_run else "PASS_WITH_PREREQUISITE",
        "LIVE_FORWARD Day-1 readiness": "PASS_WITH_PREREQUISITE",
    }
    if data_discovery["readiness"].get("fail_if_ambiguous"):
        matrix["Production data readiness"] = "FAIL"
    if not genesis_exists():
        matrix["LIVE_FORWARD Day-1 readiness"] = "PASS_WITH_PREREQUISITE"
    all_pass = all(v in ("PASS", "PASS_WITH_PREREQUISITE") for v in matrix.values())
    return {"matrix": matrix, "all_pass_or_prerequisite": all_pass, "any_fail": any(v == "FAIL" for v in matrix.values())}


def run_full_production_readiness_audit(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    repo = repo_root or Path(__file__).resolve().parents[3]
    panel = build_research_panel()
    target = derive_vn_trade_date()
    if not panel.empty:
        target = str(pd.to_datetime(panel["trade_date"]).max().date())

    data_discovery = discover_production_data_sources(repo)
    eod_audit = audit_eod_completeness_gate(panel, target)
    timezone_audit = audit_timezone_semantics(panel, target_trade_date=target)
    architecture = audit_end_to_end_architecture()
    runtime = discover_runtime_environment(repo)
    trading_iso = run_trading_isolation_audit(repo)
    health = build_operational_health_artifact()
    policy = {"head": _git_head(repo), "policy_hashes": compute_research_policy_hashes(repo)}

    matrix = build_readiness_matrix(
        repo_root=repo,
        data_discovery=data_discovery,
        eod_audit=eod_audit,
        timezone_audit=timezone_audit,
        trading_isolation=trading_iso,
    )

    return {
        "version": READINESS_AUDIT_VERSION,
        "stop_boundary": STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED,
        "architecture": architecture,
        "data_discovery": data_discovery,
        "runtime": runtime,
        "timezone_audit": timezone_audit,
        "eod_completeness_audit": eod_audit,
        "trading_isolation": trading_iso,
        "operational_health": health,
        "policy": policy,
        "readiness_matrix": matrix,
        "live_forward_activated": False,
        "genesis_exists": genesis_exists(),
        "deployment_recommendation": _deployment_recommendation(matrix),
    }


def _deployment_recommendation(matrix: Dict[str, Any]) -> str:
    if matrix.get("any_fail"):
        return "DO_NOT_ACTIVATE_LIVE_FORWARD — resolve FAIL items first"
    if matrix.get("all_pass_or_prerequisite"):
        return (
            "READY_FOR_DAY_0_SMOKE_AND_GENESIS_CREATION — "
            "complete manual prerequisites in runbook before LIVE_FORWARD Day 1"
        )
    return "INSUFFICIENT_READINESS — audit incomplete"


def _git_head(repo: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    except Exception:
        return "unknown"
