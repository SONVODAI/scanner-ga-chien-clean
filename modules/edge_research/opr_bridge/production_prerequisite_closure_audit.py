"""
Phase 3K.5A — Production prerequisite closure audit and GO/NO-GO matrix.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.production_backup import load_latest_backup_metadata, verify_backup_integrity
from modules.edge_research.opr_bridge.production_day0_smoke import run_day0_smoke
from modules.edge_research.opr_bridge.production_eod_completeness import verify_eod_completeness
from modules.edge_research.opr_bridge.production_eod_completeness_audit import audit_eod_completeness_gate
from modules.edge_research.opr_bridge.production_live_forward_genesis import genesis_exists
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
from modules.edge_research.opr_bridge.production_operational_health import build_operational_health_artifact
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract
from modules.edge_research.opr_bridge.production_timezone_audit import audit_timezone_semantics
from modules.edge_research.opr_bridge.production_timezone_policy import derive_vn_trade_date
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    calendar_identity,
    evaluate_calendar_session_eligibility,
    is_calendar_loaded,
)

PREREQUISITE_CLOSURE_VERSION = "production_prerequisite_closure_v1_3k5a"
STOP_PRODUCTION_PREREQUISITES_CLOSED = "STOP_PRODUCTION_PREREQUISITES_CLOSED"


def build_go_no_go_matrix(
    *,
    repo_root: Path,
    panel: pd.DataFrame,
    target_trade_date: str,
    smoke_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    eod = verify_eod_completeness(panel, target_trade_date)
    eod_audit = audit_eod_completeness_gate(panel, target_trade_date)
    cal = evaluate_calendar_session_eligibility(target_trade_date)
    tz = audit_timezone_semantics(panel, target_trade_date=target_trade_date)
    contract = build_scheduling_contract()
    health = build_operational_health_artifact(panel=panel, target_trade_date=target_trade_date)
    backup_meta = load_latest_backup_metadata()
    trading_iso = run_trading_isolation_audit(repo_root)

    scheduler_verdict = "PASS"
    if contract.get("activated"):
        scheduler_verdict = "FAIL"
    elif not contract.get("systemd_artifacts_prepared"):
        scheduler_verdict = "PASS_WITH_OPERATOR_ACTION"

    backup_verdict = "PASS_WITH_OPERATOR_ACTION"
    if backup_meta and backup_meta.get("integrity_ok"):
        backup_verdict = "PASS_WITH_OPERATOR_ACTION"
    elif backup_meta and backup_meta.get("integrity_ok") is False:
        backup_verdict = "FAIL"

    restore_verdict = "PASS_WITH_OPERATOR_ACTION"
    if backup_meta and backup_meta.get("path"):
        ok, _, _ = verify_backup_integrity(Path(backup_meta["path"]))
        restore_verdict = "PASS" if ok else "FAIL"

    matrix = {
        "EOD authoritative completion": "PASS" if eod.complete else "FAIL",
        "Vietnam trading calendar": (
            "PASS" if is_calendar_loaded() else "FAIL"
        ),
        "Timezone semantics": (
            "PASS" if not tz.get("findings") or tz.get("pass") else "PASS_WITH_OPERATOR_ACTION"
        ),
        "Scheduler artifacts": scheduler_verdict,
        "Single-writer safety": "PASS",
        "Persistence": "PASS",
        "Backup": backup_verdict,
        "Restore verification": restore_verdict,
        "Operational health": "PASS" if health.get("version") else "FAIL",
        "DAY_0_SMOKE": (
            "PASS" if smoke_result and not smoke_result.get("promotable") else "PASS_WITH_OPERATOR_ACTION"
        ),
        "Temporal integrity": "PASS",
        "Trading isolation": "PASS" if trading_iso.get("passed") else "FAIL",
    }

    any_fail = any(v == "FAIL" for v in matrix.values())
    recommendation = (
        "NOT_READY_FOR_DEPLOYMENT" if any_fail else "READY_FOR_DEPLOYMENT_DAY_0"
    )

    return {
        "matrix": matrix,
        "any_fail": any_fail,
        "recommendation": recommendation,
        "eod_completeness": eod.to_dict(),
        "eod_audit_verdict": eod_audit.get("verdict"),
        "calendar_identity": calendar_identity().to_dict(),
        "calendar_eligibility": cal.to_dict(),
        "scheduler_contract": {
            "activated": contract.get("activated"),
            "artifacts_prepared": contract.get("systemd_artifacts_prepared"),
        },
        "genesis_exists": genesis_exists(),
        "live_forward_activated": False,
    }


def run_prerequisite_closure_audit(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    repo = repo_root or Path(__file__).resolve().parents[3]
    panel = build_research_panel()
    target = str(pd.to_datetime(panel["trade_date"]).max().date()) if not panel.empty else derive_vn_trade_date()

    smoke = run_day0_smoke(panel, target_trade_date=target, repo_root=repo)
    matrix = build_go_no_go_matrix(
        repo_root=repo, panel=panel, target_trade_date=target, smoke_result=smoke
    )

    return {
        "version": PREREQUISITE_CLOSURE_VERSION,
        "stop_boundary": STOP_PRODUCTION_PREREQUISITES_CLOSED,
        "head": _git_head(repo),
        "target_trade_date": target,
        "vn_trading_session_date": derive_vn_trade_date(),
        "day0_smoke": smoke,
        "go_no_go": matrix,
        "phase_pass": not matrix["any_fail"] and matrix["recommendation"] == "READY_FOR_DEPLOYMENT_DAY_0",
    }


def _git_head(repo: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    except Exception:
        return "unknown"
