"""
Phase 3K.2 — Future scheduling contract (NOT activated — audit only).
"""

from __future__ import annotations

from typing import Any, Dict

from modules.edge_research.opr_bridge.production_daily_run_records import SCHEDULING_CONTRACT_VERSION

STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY = "STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY"


def build_scheduling_contract() -> Dict[str, Any]:
    """
    Contract for future post-EOD daily run — cron/systemd NOT installed in 3K.2.
    """
    return {
        "version": SCHEDULING_CONTRACT_VERSION,
        "entrypoint": "python -m modules.edge_research.opr_bridge.production_daily_run_entrypoint",
        "expected_environment": {
            "python": ">=3.10",
            "data_dir": "data/edge_research/",
            "timezone": "Asia/Ho_Chi_Minh",
            "required_env": [],
        },
        "target_time_window": {
            "description": "Post-EOD after canonical T0 freeze (>= 18:00 VN)",
            "earliest_local": "18:00",
            "latest_local": "23:59",
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "concurrency": {
            "lock_file": "data/edge_research/production_observations/daily_run.lock",
            "behavior": "exclusive_non_blocking",
            # SUCCESS / SKIPPED_NON_TRADING_DAY: idempotent replay.
            # WAITING_FOR_DATA: retry on later timer cycles when source/EOD advances;
            # unchanged waiting readiness remains idempotent; prior waiting records stay immutable.
            "lock_acquired_before": "headless_eod_and_all_data_producing_stages",
            "duplicate_same_day": "idempotent_replay_terminal_or_unchanged_waiting",
            "waiting_for_data_policy": "retry_when_source_or_eod_advances",
        },
        "retry": {
            "safe_retry": True,
            "resume_from_phase_markers": True,
            "max_retries": 3,
            "backoff_seconds": [60, 300, 900],
            "same_day_timer_attempts": [
                "18:35 Asia/Ho_Chi_Minh — may WAITING_FOR_DATA if EOD incomplete",
                "20:05 Asia/Ho_Chi_Minh — retry; must not freeze on prior WAITING",
                "22:35 Asia/Ho_Chi_Minh — final same-day retry",
            ],
        },
        "data_readiness": {
            "require_panel_through_target_date": True,
            "fail_closed_on_provenance_ambiguity": True,
            "weekend_behavior": "SKIP_NON_TRADING_DAY",
        },
        "exit_codes": {
            "0": "SUCCESS or idempotent replay",
            "1": "FAILED_CLOSED",
            "2": "WAITING_FOR_DATA",
            "3": "SKIPPED_NON_TRADING_DAY",
            "4": "PARTIAL_RECOVERABLE",
            "10": "LOCK_HELD",
        },
        "health_output": {
            "manifest_path": "data/edge_research/production_observations/daily_manifests/{run_id}.json",
            "status_fields": ["run_status", "bot_spoke_today", "summary_id"],
        },
        "activated": False,
        "cron_installed": False,
        "systemd_timer_installed": False,
        "systemd_artifacts_prepared": True,
        "systemd_service_unit": "mrbot-daily-research.service",
        "systemd_timer_unit": "mrbot-daily-research.timer",
        "systemd_install_script": "deploy/systemd/install-daily-research.sh",
        "stop_boundary": STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY,
    }
