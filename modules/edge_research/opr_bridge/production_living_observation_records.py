"""
Phase 3K.1 — Living research observation record types.

Three temporal layers:
  A. ResearchObservationBirthRecord (immutable, 3K.0)
  B. DailyResearchAssessment (append-only daily state)
  C. ResearchObservationOutcomeRecord (append-only forward outcomes)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.production_observation_records import (
    DEFAULT_SHADOW_AUTHORITY,
    ShadowAuthoritySemantics,
)

LIVING_OBSERVATION_VERSION = "living_research_observation_v1_3k1"
DAILY_ASSESSMENT_VERSION = "daily_research_assessment_v1_3k1"
DAILY_VOICE_VERSION = "daily_voice_contract_v1_3k1"
DAILY_SUMMARY_VERSION = "daily_research_summary_v1_3k1"
READ_MODEL_VERSION = "living_observation_read_model_v1_3k1"

STOP_LIVING_RESEARCH_OBSERVATION_READY = "STOP_LIVING_RESEARCH_OBSERVATION_READY"

HISTORICAL_MULTI_DAY_REPLAY = "HISTORICAL_MULTI_DAY_REPLAY"


class ChangeKind(str, Enum):
    DATA_CHANGED = "DATA_CHANGED"
    MARKET_CHANGED = "MARKET_CHANGED"
    EVIDENCE_CHANGED = "EVIDENCE_CHANGED"
    BELIEF_CHANGED = "BELIEF_CHANGED"
    UNCHANGED = "UNCHANGED"


class ObservationLifecycleState(str, Enum):
    BORN = "BORN"
    ACTIVE_PENDING = "ACTIVE_PENDING"
    STRENGTHENED = "STRENGTHENED"
    UNCHANGED = "UNCHANGED"
    CHALLENGED = "CHALLENGED"
    WEAKENED = "WEAKENED"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    SILENCE = "SILENCE"


@dataclass(frozen=True)
class MarketDelta:
    regime_changed: bool
    breadth_direction: str  # STRENGTHENED | WEAKENED | UNCHANGED | UNKNOWN
    transition_direction: str
    dispersion_changed: bool
    cohort_relative_changed: bool
    compatibility_direction: str  # MORE_COMPATIBLE | LESS_COMPATIBLE | UNCHANGED | UNKNOWN
    summary_keys: Tuple[str, ...]
    previous_context_hash: str
    current_context_hash: str
    delta_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime_changed": self.regime_changed,
            "breadth_direction": self.breadth_direction,
            "transition_direction": self.transition_direction,
            "dispersion_changed": self.dispersion_changed,
            "cohort_relative_changed": self.cohort_relative_changed,
            "compatibility_direction": self.compatibility_direction,
            "summary_keys": list(self.summary_keys),
            "previous_context_hash": self.previous_context_hash,
            "current_context_hash": self.current_context_hash,
            "delta_hash": self.delta_hash,
        }


@dataclass(frozen=True)
class EpistemicDelta:
    previous_state: Optional[str]
    current_state: Optional[str]
    changed: bool
    change_kind: str
    rationale_keys: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "previous_state": self.previous_state,
            "current_state": self.current_state,
            "changed": self.changed,
            "change_kind": self.change_kind,
            "rationale_keys": list(self.rationale_keys),
        }


@dataclass
class DailyResearchAssessment:
    assessment_id: str
    observation_id: str
    assessment_trade_date: str
    assessment_timestamp: str
    previous_assessment_id: Optional[str]
    birth_record_hash: str
    cutoff_provenance: Dict[str, Any]
    current_market_context_identity: str
    current_market_context_hash: str
    previous_market_context_identity: Optional[str]
    previous_market_context_hash: Optional[str]
    market_delta: MarketDelta
    new_evidence_since_prior: Tuple[str, ...]
    forward_outcomes_newly_available: Tuple[str, ...]
    current_epistemic_state: Optional[str]
    previous_epistemic_state: Optional[str]
    epistemic_delta: EpistemicDelta
    null_ledger_current: List[Dict[str, Any]]
    null_ledger_delta: Tuple[str, ...]
    contradictions: Tuple[str, ...]
    dependence_warnings: Tuple[str, ...]
    unresolved_uncertainties: Tuple[str, ...]
    current_limitations: Tuple[str, ...]
    current_research_status: str
    current_lifecycle_status: str
    observation_lifecycle_state: str
    what_changed: Tuple[str, ...]
    what_did_not_change: Tuple[str, ...]
    why_belief_changed_or_not: str
    what_bot_is_waiting_for: str
    next_eligible_evaluation_horizon: Optional[str]
    next_eligible_evaluation_date: Optional[str]
    observation_age_trading_days: int
    change_flags: Tuple[str, ...]
    shadow_authority: ShadowAuthoritySemantics = DEFAULT_SHADOW_AUTHORITY
    assessment_identity_hash: str = ""
    stale_copy_risk: bool = False
    record_version: str = DAILY_ASSESSMENT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "observation_id": self.observation_id,
            "assessment_trade_date": self.assessment_trade_date,
            "assessment_timestamp": self.assessment_timestamp,
            "previous_assessment_id": self.previous_assessment_id,
            "birth_record_hash": self.birth_record_hash,
            "cutoff_provenance": dict(self.cutoff_provenance),
            "current_market_context_identity": self.current_market_context_identity,
            "current_market_context_hash": self.current_market_context_hash,
            "previous_market_context_identity": self.previous_market_context_identity,
            "previous_market_context_hash": self.previous_market_context_hash,
            "market_delta": self.market_delta.to_dict(),
            "new_evidence_since_prior": list(self.new_evidence_since_prior),
            "forward_outcomes_newly_available": list(self.forward_outcomes_newly_available),
            "current_epistemic_state": self.current_epistemic_state,
            "previous_epistemic_state": self.previous_epistemic_state,
            "epistemic_delta": self.epistemic_delta.to_dict(),
            "null_ledger_current": list(self.null_ledger_current),
            "null_ledger_delta": list(self.null_ledger_delta),
            "contradictions": list(self.contradictions),
            "dependence_warnings": list(self.dependence_warnings),
            "unresolved_uncertainties": list(self.unresolved_uncertainties),
            "current_limitations": list(self.current_limitations),
            "current_research_status": self.current_research_status,
            "current_lifecycle_status": self.current_lifecycle_status,
            "observation_lifecycle_state": self.observation_lifecycle_state,
            "what_changed": list(self.what_changed),
            "what_did_not_change": list(self.what_did_not_change),
            "why_belief_changed_or_not": self.why_belief_changed_or_not,
            "what_bot_is_waiting_for": self.what_bot_is_waiting_for,
            "next_eligible_evaluation_horizon": self.next_eligible_evaluation_horizon,
            "next_eligible_evaluation_date": self.next_eligible_evaluation_date,
            "observation_age_trading_days": self.observation_age_trading_days,
            "change_flags": list(self.change_flags),
            "shadow_authority": self.shadow_authority.to_dict(),
            "assessment_identity_hash": self.assessment_identity_hash,
            "stale_copy_risk": self.stale_copy_risk,
            "record_version": self.record_version,
        }

    def finalize_hash(self) -> None:
        payload = {k: v for k, v in self.to_dict().items() if k != "assessment_identity_hash"}
        self.assessment_identity_hash = stable_hash(payload)


@dataclass(frozen=True)
class DailyVoiceContract:
    assessment_id: str
    observation_id: str
    assessment_trade_date: str
    q1_today_i_see_vi: str
    q2_vs_prior_session_vi: str
    q3_market_change_vi: str
    q4_new_evidence_vi: str
    q5_belief_changed_vi: str
    q6_if_not_why_vi: str
    q7_counter_hypothesis_vi: str
    q8_still_unknown_vi: str
    q9_waiting_for_vi: str
    q10_old_observations_vi: str
    structured_trace: Dict[str, Any]
    narrative_authority: str = "STRUCTURED_STATE_ONLY"
    record_version: str = DAILY_VOICE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "observation_id": self.observation_id,
            "assessment_trade_date": self.assessment_trade_date,
            "q1_today_i_see_vi": self.q1_today_i_see_vi,
            "q2_vs_prior_session_vi": self.q2_vs_prior_session_vi,
            "q3_market_change_vi": self.q3_market_change_vi,
            "q4_new_evidence_vi": self.q4_new_evidence_vi,
            "q5_belief_changed_vi": self.q5_belief_changed_vi,
            "q6_if_not_why_vi": self.q6_if_not_why_vi,
            "q7_counter_hypothesis_vi": self.q7_counter_hypothesis_vi,
            "q8_still_unknown_vi": self.q8_still_unknown_vi,
            "q9_waiting_for_vi": self.q9_waiting_for_vi,
            "q10_old_observations_vi": self.q10_old_observations_vi,
            "structured_trace": dict(self.structured_trace),
            "narrative_authority": self.narrative_authority,
            "record_version": self.record_version,
        }


@dataclass
class DailyResearchSummary:
    summary_id: str
    trade_date: str
    summary_timestamp: str
    market_state_summary: Dict[str, Any]
    most_meaningful_market_delta: Optional[str]
    new_observations_born: Tuple[str, ...]
    active_observations_reassessed: Tuple[str, ...]
    strengthened_count: int
    weakened_or_challenged_count: int
    resolved_or_rejected_count: int
    silence_or_no_discovery: bool
    newly_arrived_forward_evidence: Tuple[str, ...]
    most_important_unresolved_question: Optional[str]
    what_bot_is_waiting_for: str
    provenance_hash: str
    shadow_authority: ShadowAuthoritySemantics = DEFAULT_SHADOW_AUTHORITY
    record_version: str = DAILY_SUMMARY_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "trade_date": self.trade_date,
            "summary_timestamp": self.summary_timestamp,
            "market_state_summary": dict(self.market_state_summary),
            "most_meaningful_market_delta": self.most_meaningful_market_delta,
            "new_observations_born": list(self.new_observations_born),
            "active_observations_reassessed": list(self.active_observations_reassessed),
            "strengthened_count": self.strengthened_count,
            "weakened_or_challenged_count": self.weakened_or_challenged_count,
            "resolved_or_rejected_count": self.resolved_or_rejected_count,
            "silence_or_no_discovery": self.silence_or_no_discovery,
            "newly_arrived_forward_evidence": list(self.newly_arrived_forward_evidence),
            "most_important_unresolved_question": self.most_important_unresolved_question,
            "what_bot_is_waiting_for": self.what_bot_is_waiting_for,
            "provenance_hash": self.provenance_hash,
            "shadow_authority": self.shadow_authority.to_dict(),
            "record_version": self.record_version,
        }


def compute_daily_assessment_identity(
    *,
    observation_id: str,
    assessment_trade_date: str,
    birth_record_hash: str,
    cutoff_provenance_hash: str,
    previous_assessment_id: Optional[str],
    market_context_hash: str,
    outcome_ids: Tuple[str, ...],
) -> str:
    return stable_hash(
        {
            "observation_id": observation_id,
            "assessment_trade_date": assessment_trade_date,
            "birth_record_hash": birth_record_hash,
            "cutoff_provenance_hash": cutoff_provenance_hash,
            "previous_assessment_id": previous_assessment_id,
            "market_context_hash": market_context_hash,
            "outcome_ids": sorted(outcome_ids),
            "version": DAILY_ASSESSMENT_VERSION,
        }
    )


def new_assessment_id(identity_hash: str) -> str:
    return f"asmt-{identity_hash[:16]}"


def new_summary_id(trade_date: str, provenance_hash: str) -> str:
    return f"dysum-{stable_hash({'trade_date': trade_date, 'prov': provenance_hash})[:16]}"
