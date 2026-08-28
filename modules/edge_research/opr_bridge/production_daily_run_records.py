"""
Phase 3K.2 — Production daily research run record types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.production_observation_records import (
    DEFAULT_SHADOW_AUTHORITY,
    ShadowAuthoritySemantics,
)

DAILY_RUN_VERSION = "production_daily_research_run_v1_3k2"
MANIFEST_VERSION = "production_daily_manifest_v1_3k2"
FORWARD_CLOCK_VERSION = "forward_clock_ledger_v1_3k2"
SCHEDULING_CONTRACT_VERSION = "daily_run_scheduling_contract_v1_3k2"
NOTIFICATION_CONTRACT_VERSION = "daily_run_notification_contract_v1_3k2"

STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY = "STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY"

STOP_LIVING_RESEARCH_UI_READY = "STOP_LIVING_RESEARCH_UI_READY"
STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED = "STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED"

HISTORICAL_REPLAY_TEST = "HISTORICAL_REPLAY_TEST"
BACKFILL_NON_FORWARD = "BACKFILL_NON_FORWARD"
LIVE_FORWARD = "LIVE_FORWARD"
DAY_0_SMOKE = "DAY_0_SMOKE"
PRE_DEPLOYMENT_DRY_RUN = "PRE_DEPLOYMENT_DRY_RUN"

FORWARD_EVIDENCE_MODES = frozenset({LIVE_FORWARD})
NON_FORWARD_MODES = frozenset({HISTORICAL_REPLAY_TEST, BACKFILL_NON_FORWARD, DAY_0_SMOKE, PRE_DEPLOYMENT_DRY_RUN})


class RunDisposition(str, Enum):
    SUCCESS = "SUCCESS"
    SKIPPED_NON_TRADING_DAY = "SKIPPED_NON_TRADING_DAY"
    WAITING_FOR_DATA = "WAITING_FOR_DATA"
    FAILED_CLOSED = "FAILED_CLOSED"
    PARTIAL_RECOVERABLE = "PARTIAL_RECOVERABLE"


class RunPhase(str, Enum):
    STARTED = "STARTED"
    DATA_READINESS = "DATA_READINESS"
    CUTOFF_ESTABLISHED = "CUTOFF_ESTABLISHED"
    RESEARCH_COMPLETED = "RESEARCH_COMPLETED"
    BIRTHS_PERSISTED = "BIRTHS_PERSISTED"
    OUTCOMES_RELEASED = "OUTCOMES_RELEASED"
    ASSESSMENTS_COMPLETED = "ASSESSMENTS_COMPLETED"
    SUMMARY_COMPLETED = "SUMMARY_COMPLETED"
    RUN_FINALIZED = "RUN_FINALIZED"


class NotificationEventKind(str, Enum):
    DAILY_RESEARCH_READY = "DAILY_RESEARCH_READY"
    FORWARD_OUTCOME_RELEASED = "FORWARD_OUTCOME_RELEASED"
    MATERIAL_BELIEF_CHANGE = "MATERIAL_BELIEF_CHANGE"
    RUN_FAILED = "RUN_FAILED"
    RUN_SKIPPED = "RUN_SKIPPED"
    WAITING_FOR_DATA = "WAITING_FOR_DATA"


@dataclass
class ProductionDailyResearchRun:
    run_id: str
    target_trade_date: str
    run_mode: str
    run_started_at: str
    run_completed_at: Optional[str]
    cutoff: Optional[Dict[str, Any]]
    source_dataset_identity: str
    source_dataset_hash: str
    source_max_trade_date: Optional[str]
    researcher_visible_max_trade_date: Optional[str]
    market_context_identity: Optional[str]
    market_context_hash: Optional[str]
    prior_successful_run_id: Optional[str]
    policy_version_hashes: Dict[str, str]
    observations_born: Tuple[str, ...]
    observations_reassessed: Tuple[str, ...]
    forward_outcomes_released: Tuple[str, ...]
    daily_summary_id: Optional[str]
    run_disposition: str
    failure_or_skip_reason: Optional[str]
    counts_as_forward_evidence: bool
    current_phase: str
    phase_history: Tuple[Dict[str, Any], ...]
    shadow_authority: ShadowAuthoritySemantics = DEFAULT_SHADOW_AUTHORITY
    run_identity_hash: str = ""
    frozen: bool = False
    record_version: str = DAILY_RUN_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "target_trade_date": self.target_trade_date,
            "run_mode": self.run_mode,
            "run_started_at": self.run_started_at,
            "run_completed_at": self.run_completed_at,
            "cutoff": dict(self.cutoff) if self.cutoff else None,
            "source_dataset_identity": self.source_dataset_identity,
            "source_dataset_hash": self.source_dataset_hash,
            "source_max_trade_date": self.source_max_trade_date,
            "researcher_visible_max_trade_date": self.researcher_visible_max_trade_date,
            "market_context_identity": self.market_context_identity,
            "market_context_hash": self.market_context_hash,
            "prior_successful_run_id": self.prior_successful_run_id,
            "policy_version_hashes": dict(self.policy_version_hashes),
            "observations_born": list(self.observations_born),
            "observations_reassessed": list(self.observations_reassessed),
            "forward_outcomes_released": list(self.forward_outcomes_released),
            "daily_summary_id": self.daily_summary_id,
            "run_disposition": self.run_disposition,
            "failure_or_skip_reason": self.failure_or_skip_reason,
            "counts_as_forward_evidence": self.counts_as_forward_evidence,
            "current_phase": self.current_phase,
            "phase_history": list(self.phase_history),
            "shadow_authority": self.shadow_authority.to_dict(),
            "run_identity_hash": self.run_identity_hash,
            "frozen": self.frozen,
            "record_version": self.record_version,
        }


@dataclass(frozen=True)
class DailyManifest:
    trade_date: str
    run_id: str
    run_status: str
    bot_spoke_today: bool
    discovery_count: int
    active_assessment_count: int
    newly_released_outcomes: Tuple[str, ...]
    meaningful_belief_changes: int
    silence_or_no_discovery: bool
    market_context_hash: Optional[str]
    summary_id: Optional[str]
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]
    shadow_authority: ShadowAuthoritySemantics
    counts_as_forward_evidence: bool
    record_version: str = MANIFEST_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "run_id": self.run_id,
            "run_status": self.run_status,
            "bot_spoke_today": self.bot_spoke_today,
            "discovery_count": self.discovery_count,
            "active_assessment_count": self.active_assessment_count,
            "newly_released_outcomes": list(self.newly_released_outcomes),
            "meaningful_belief_changes": self.meaningful_belief_changes,
            "silence_or_no_discovery": self.silence_or_no_discovery,
            "market_context_hash": self.market_context_hash,
            "summary_id": self.summary_id,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "shadow_authority": self.shadow_authority.to_dict(),
            "counts_as_forward_evidence": self.counts_as_forward_evidence,
            "record_version": self.record_version,
        }


@dataclass(frozen=True)
class ForwardClockEntry:
    observation_id: str
    birth_trade_date: str
    age_trading_sessions: int
    t3_eligible_date: str
    t5_eligible_date: str
    t10_eligible_date: str
    t3_release_date: Optional[str]
    t5_release_date: Optional[str]
    t10_release_date: Optional[str]
    missing_data_delay: Optional[str]
    record_version: str = FORWARD_CLOCK_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "birth_trade_date": self.birth_trade_date,
            "age_trading_sessions": self.age_trading_sessions,
            "t3_eligible_date": self.t3_eligible_date,
            "t5_eligible_date": self.t5_eligible_date,
            "t10_eligible_date": self.t10_eligible_date,
            "t3_release_date": self.t3_release_date,
            "t5_release_date": self.t5_release_date,
            "t10_release_date": self.t10_release_date,
            "missing_data_delay": self.missing_data_delay,
            "record_version": self.record_version,
        }


@dataclass(frozen=True)
class NotificationEvent:
    event_kind: str
    run_id: str
    trade_date: str
    payload: Dict[str, Any]
    timestamp: str
    delivery_status: str = "NOT_DELIVERED"
    record_version: str = NOTIFICATION_CONTRACT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_kind": self.event_kind,
            "run_id": self.run_id,
            "trade_date": self.trade_date,
            "payload": dict(self.payload),
            "timestamp": self.timestamp,
            "delivery_status": self.delivery_status,
            "record_version": self.record_version,
        }


def compute_run_identity(
    *,
    target_trade_date: str,
    run_mode: str,
    source_dataset_hash: str,
    policy_hash_bundle: str,
) -> str:
    return stable_hash({
        "target_trade_date": target_trade_date,
        "run_mode": run_mode,
        "source_dataset_hash": source_dataset_hash,
        "policy_hash_bundle": policy_hash_bundle,
        "version": DAILY_RUN_VERSION,
    })


def new_run_id(identity_hash: str) -> str:
    return f"pdrun-{identity_hash[:16]}"


def mode_counts_as_forward_evidence(run_mode: str) -> bool:
    return run_mode in FORWARD_EVIDENCE_MODES


def reject_mode_conversion(original_mode: str, proposed_mode: str) -> bool:
    """CF-RUN18 — mode conversion after persistence is forbidden."""
    return original_mode != proposed_mode
