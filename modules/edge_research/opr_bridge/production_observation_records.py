"""
Phase 3K.0 — Production research observation record types (shadow scientific system).

Immutable semantics: research_only, no trading authority, no future outcomes at birth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso

OBSERVATION_VERSION = "production_research_observation_v1_3k0"
BIRTH_RECORD_VERSION = "research_observation_birth_v1_3k0"
LEDGER_VERSION = "production_research_observation_ledger_v1_3k0"
FORWARD_CONTRACT_VERSION = "forward_evaluation_contract_v1_3k0"
FORWARD_CONTRACT_VERSION_V2 = "forward_evaluation_contract_v2_claim_aligned"
OUTCOME_RECORD_VERSION = "research_observation_outcome_v1_3k0"
NARRATIVE_CONTRACT_VERSION = "observation_narrative_contract_v1_3k0"
UI_CONTRACT_VERSION = "observation_ui_contract_v1_3k0"

STOP_PRODUCTION_RESEARCH_OBSERVATION_FOUNDATION = "STOP_PRODUCTION_RESEARCH_OBSERVATION_FOUNDATION"

HISTORICAL_REPLAY_TEST = "HISTORICAL_REPLAY_TEST"


class DataAvailabilityStatus(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    INTRADAY = "INTRADAY"
    EOD_FINAL = "EOD_FINAL"
    POST_EOD = "POST_EOD"


class ForwardHorizon(str, Enum):
    T3 = "T3"
    T5 = "T5"
    T10 = "T10"


class ForwardEvaluationStatus(str, Enum):
    PENDING_FUTURE = "PENDING_FUTURE"
    ELIGIBLE = "ELIGIBLE"
    EVALUATED = "EVALUATED"
    MISSING_DATA = "MISSING_DATA"
    SUSPENDED = "SUSPENDED"
    DELISTED = "DELISTED"


class ObservationOutcomeKind(str, Enum):
    DISCOVERY = "DISCOVERY"
    SILENCE = "SILENCE"
    NO_DISCOVERY = "NO_DISCOVERY"
    STOP = "STOP"
    REJECTED = "REJECTED"
    WEAKENED = "WEAKENED"
    FAILED_CLOSED = "FAILED_CLOSED"
    DESIGN_SILENCE = "DESIGN_SILENCE"


@dataclass(frozen=True)
class ShadowAuthoritySemantics:
    """Immutable shadow-system authority flags — never grant trading power."""

    research_only: bool = True
    trading_authority: bool = False
    buy_signal: bool = False
    sell_signal: bool = False
    edge_active: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "research_only": self.research_only,
            "trading_authority": self.trading_authority,
            "buy_signal": self.buy_signal,
            "sell_signal": self.sell_signal,
            "edge_active": self.edge_active,
        }


DEFAULT_SHADOW_AUTHORITY = ShadowAuthoritySemantics()


@dataclass(frozen=True)
class ObservationCutoff:
    """Authoritative temporal boundary for production research observation."""

    observation_id: str
    trade_date: str
    cutoff_timestamp: str
    timezone: str
    data_availability_status: str
    market_data_max_timestamp: str
    dataset_identities: Tuple[str, ...]
    dataset_hashes: Tuple[str, ...]
    universe_identity: str
    universe_hash: str
    market_context_identity: str
    market_context_hash: str
    research_policy_hashes: Dict[str, str]
    code_identity: str
    panel_row_count: int
    panel_max_trade_date: str
    temporal_provenance_hash: str
    record_version: str = OBSERVATION_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "trade_date": self.trade_date,
            "cutoff_timestamp": self.cutoff_timestamp,
            "timezone": self.timezone,
            "data_availability_status": self.data_availability_status,
            "market_data_max_timestamp": self.market_data_max_timestamp,
            "dataset_identities": list(self.dataset_identities),
            "dataset_hashes": list(self.dataset_hashes),
            "universe_identity": self.universe_identity,
            "universe_hash": self.universe_hash,
            "market_context_identity": self.market_context_identity,
            "market_context_hash": self.market_context_hash,
            "research_policy_hashes": dict(self.research_policy_hashes),
            "code_identity": self.code_identity,
            "panel_row_count": self.panel_row_count,
            "panel_max_trade_date": self.panel_max_trade_date,
            "temporal_provenance_hash": self.temporal_provenance_hash,
            "record_version": self.record_version,
        }


@dataclass(frozen=True)
class ForwardHorizonPlaceholder:
    horizon: str
    status: str = ForwardEvaluationStatus.PENDING_FUTURE.value
    eligible_evaluation_date: Optional[str] = None
    realized_outcome: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizon": self.horizon,
            "status": self.status,
            "eligible_evaluation_date": self.eligible_evaluation_date,
            "realized_outcome": self.realized_outcome,
        }


@dataclass(frozen=True)
class ForwardEvaluationContract:
    """Frozen contract for future T3/T5/T10 evaluation — defined at birth, not executed in 3K.0."""

    contract_id: str
    observation_id: str
    horizons: Tuple[str, ...]
    evaluation_criteria: Dict[str, Any]
    cohort_evaluation_rules: Dict[str, Any]
    missing_data_policy: str
    contract_hash: str
    record_version: str = FORWARD_CONTRACT_VERSION
    claim_family: str = "LEGACY_UNSPECIFIED"
    claim_spec: Dict[str, Any] = field(default_factory=dict)
    claim_contract_status: str = "LEGACY_INSUFFICIENT_CLAIM_SPEC"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "observation_id": self.observation_id,
            "horizons": list(self.horizons),
            "evaluation_criteria": dict(self.evaluation_criteria),
            "cohort_evaluation_rules": dict(self.cohort_evaluation_rules),
            "missing_data_policy": self.missing_data_policy,
            "contract_hash": self.contract_hash,
            "record_version": self.record_version,
            "claim_family": self.claim_family,
            "claim_spec": dict(self.claim_spec),
            "claim_contract_status": self.claim_contract_status,
        }


@dataclass(frozen=True)
class ResearchObservationOutcomeRecord:
    """Schema for future outcome evaluation — NOT populated in Phase 3K.0."""

    outcome_record_id: str
    observation_id: str
    horizon: str
    eligible_evaluation_date: str
    actual_evaluation_timestamp: Optional[str]
    realized_outcomes: Optional[Dict[str, Any]]
    evaluation_status: str
    data_identity: Optional[str]
    missing_handling: Optional[str]
    contract_id: str
    contract_hash: str
    provenance: Dict[str, Any]
    record_version: str = OUTCOME_RECORD_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome_record_id": self.outcome_record_id,
            "observation_id": self.observation_id,
            "horizon": self.horizon,
            "eligible_evaluation_date": self.eligible_evaluation_date,
            "actual_evaluation_timestamp": self.actual_evaluation_timestamp,
            "realized_outcomes": self.realized_outcomes,
            "evaluation_status": self.evaluation_status,
            "data_identity": self.data_identity,
            "missing_handling": self.missing_handling,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "provenance": dict(self.provenance),
            "record_version": self.record_version,
        }


@dataclass(frozen=True)
class CohortAttribution:
    attribution_kind: str  # MARKET_WIDE | COHORT | SECTOR | INDIVIDUAL | MIXED
    population_spec: Dict[str, Any]
    symbols_at_birth: Tuple[str, ...]
    sector_groups: Tuple[str, ...]
    cohort_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attribution_kind": self.attribution_kind,
            "population_spec": dict(self.population_spec),
            "symbols_at_birth": list(self.symbols_at_birth),
            "sector_groups": list(self.sector_groups),
            "cohort_hash": self.cohort_hash,
        }


@dataclass
class ResearchObservationBirthRecord:
    """Immutable snapshot of exactly what Mr.BOT knew and concluded at observation birth."""

    observation_id: str
    birth_timestamp: str
    cutoff: ObservationCutoff
    shadow_authority: ShadowAuthoritySemantics
    session_id: Optional[str]
    proposition_id: Optional[str]
    proposition_hash: Optional[str]
    research_question: Optional[str]
    cohort_attribution: CohortAttribution
    observation_outcome_kind: str
    final_epistemic_state: Optional[str]
    strongest_evidence: Optional[Dict[str, Any]]
    evidence_strength: Optional[str]
    incremental_evidence_strength: Optional[str]
    null_ledger_summary: List[Dict[str, Any]]
    surviving_nulls: Tuple[str, ...]
    dependence_warning: Optional[str]
    contradictions: Tuple[str, ...]
    stop_reason: Optional[str]
    limitations: Tuple[str, ...]
    experiment_count: int
    research_burden: Dict[str, Any]
    rejected_hypotheses: Tuple[str, ...]
    weakened_findings: Tuple[str, ...]
    artifact_warnings: Tuple[str, ...]
    unresolved_uncertainties: Tuple[str, ...]
    lifecycle_outcome: Optional[str]
    termination_reason: Optional[str]
    journey_rows: List[Dict[str, Any]]
    forward_horizons: Tuple[ForwardHorizonPlaceholder, ...]
    forward_evaluation_contract: ForwardEvaluationContract
    research_session_identity_hash: str
    birth_record_hash: str
    observation_mode: str = "PRODUCTION_SHADOW"
    record_version: str = BIRTH_RECORD_VERSION
    frozen: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "birth_timestamp": self.birth_timestamp,
            "cutoff": self.cutoff.to_dict(),
            "shadow_authority": self.shadow_authority.to_dict(),
            "session_id": self.session_id,
            "proposition_id": self.proposition_id,
            "proposition_hash": self.proposition_hash,
            "research_question": self.research_question,
            "cohort_attribution": self.cohort_attribution.to_dict(),
            "observation_outcome_kind": self.observation_outcome_kind,
            "final_epistemic_state": self.final_epistemic_state,
            "strongest_evidence": self.strongest_evidence,
            "evidence_strength": self.evidence_strength,
            "incremental_evidence_strength": self.incremental_evidence_strength,
            "null_ledger_summary": list(self.null_ledger_summary),
            "surviving_nulls": list(self.surviving_nulls),
            "dependence_warning": self.dependence_warning,
            "contradictions": list(self.contradictions),
            "stop_reason": self.stop_reason,
            "limitations": list(self.limitations),
            "experiment_count": self.experiment_count,
            "research_burden": dict(self.research_burden),
            "rejected_hypotheses": list(self.rejected_hypotheses),
            "weakened_findings": list(self.weakened_findings),
            "artifact_warnings": list(self.artifact_warnings),
            "unresolved_uncertainties": list(self.unresolved_uncertainties),
            "lifecycle_outcome": self.lifecycle_outcome,
            "termination_reason": self.termination_reason,
            "journey_rows": list(self.journey_rows),
            "forward_horizons": [h.to_dict() for h in self.forward_horizons],
            "forward_evaluation_contract": self.forward_evaluation_contract.to_dict(),
            "research_session_identity_hash": self.research_session_identity_hash,
            "birth_record_hash": self.birth_record_hash,
            "observation_mode": self.observation_mode,
            "record_version": self.record_version,
            "frozen": self.frozen,
        }

    def finalize_hash(self) -> None:
        payload = {
            k: v
            for k, v in self.to_dict().items()
            if k not in ("birth_record_hash",)
        }
        self.birth_record_hash = stable_hash(payload)


@dataclass
class ProductionResearchObservationSession:
    """Wraps bounded autonomous research lifecycle with observation provenance."""

    observation_id: str
    cutoff: ObservationCutoff
    shadow_authority: ShadowAuthoritySemantics
    trigger_outcome: str
    lifecycle_outcome: Optional[str]
    session_id: Optional[str]
    proposition_record: Optional[Dict[str, Any]]
    session_record_dict: Optional[Dict[str, Any]]
    lifecycle_result_dict: Optional[Dict[str, Any]]
    birth_record: Optional[ResearchObservationBirthRecord]
    idempotent_replay: bool = False
    errors: Tuple[str, ...] = ()
    observation_mode: str = "PRODUCTION_SHADOW"
    record_version: str = OBSERVATION_VERSION
    selection_provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "cutoff": self.cutoff.to_dict(),
            "shadow_authority": self.shadow_authority.to_dict(),
            "trigger_outcome": self.trigger_outcome,
            "lifecycle_outcome": self.lifecycle_outcome,
            "session_id": self.session_id,
            "birth_record": self.birth_record.to_dict() if self.birth_record else None,
            "idempotent_replay": self.idempotent_replay,
            "errors": list(self.errors),
            "observation_mode": self.observation_mode,
            "record_version": self.record_version,
            "selection_provenance": self.selection_provenance,
        }


@dataclass(frozen=True)
class ObservationLedgerEntry:
    """Append-only ledger row for scientific auditability."""

    ledger_entry_id: str
    observation_id: str
    birth_timestamp: str
    cutoff_timestamp: str
    trade_date: str
    what_bot_believed: str
    when_believed: str
    data_visible_summary: Dict[str, Any]
    why_believed: str
    evidence_strength: Optional[str]
    uncertainty_remaining: Tuple[str, ...]
    stop_reason: Optional[str]
    pending_horizons: Tuple[str, ...]
    observation_outcome_kind: str
    final_epistemic_state: Optional[str]
    birth_record_hash: str
    research_session_identity_hash: str
    shadow_authority: Dict[str, Any]
    record_version: str = LEDGER_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ledger_entry_id": self.ledger_entry_id,
            "observation_id": self.observation_id,
            "birth_timestamp": self.birth_timestamp,
            "cutoff_timestamp": self.cutoff_timestamp,
            "trade_date": self.trade_date,
            "what_bot_believed": self.what_bot_believed,
            "when_believed": self.when_believed,
            "data_visible_summary": dict(self.data_visible_summary),
            "why_believed": self.why_believed,
            "evidence_strength": self.evidence_strength,
            "uncertainty_remaining": list(self.uncertainty_remaining),
            "stop_reason": self.stop_reason,
            "pending_horizons": list(self.pending_horizons),
            "observation_outcome_kind": self.observation_outcome_kind,
            "final_epistemic_state": self.final_epistemic_state,
            "birth_record_hash": self.birth_record_hash,
            "research_session_identity_hash": self.research_session_identity_hash,
            "shadow_authority": dict(self.shadow_authority),
            "record_version": self.record_version,
        }


@dataclass(frozen=True)
class ObservationNarrativeContract:
    """Structured narrative inputs — presentation layer derives prose from frozen state."""

    observation_id: str
    research_topic_vi_key: str
    research_topic_en: str
    evidence_summary_keys: Tuple[str, ...]
    counter_evidence_keys: Tuple[str, ...]
    surviving_null_keys: Tuple[str, ...]
    independence_status_key: str
    continue_reason_key: Optional[str]
    stop_reason_key: Optional[str]
    unknowns_keys: Tuple[str, ...]
    pending_verification_keys: Tuple[str, ...]
    structured_state_snapshot: Dict[str, Any]
    narrative_authority: str = "STRUCTURED_STATE_ONLY"
    record_version: str = NARRATIVE_CONTRACT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "research_topic_vi_key": self.research_topic_vi_key,
            "research_topic_en": self.research_topic_en,
            "evidence_summary_keys": list(self.evidence_summary_keys),
            "counter_evidence_keys": list(self.counter_evidence_keys),
            "surviving_null_keys": list(self.surviving_null_keys),
            "independence_status_key": self.independence_status_key,
            "continue_reason_key": self.continue_reason_key,
            "stop_reason_key": self.stop_reason_key,
            "unknowns_keys": list(self.unknowns_keys),
            "pending_verification_keys": list(self.pending_verification_keys),
            "structured_state_snapshot": dict(self.structured_state_snapshot),
            "narrative_authority": self.narrative_authority,
            "record_version": self.record_version,
        }


@dataclass(frozen=True)
class ObservationUIContract:
    """Future Research UI schema — no UI built in 3K.0."""

    observation_id: str
    sections: Tuple[Dict[str, Any], ...]
    no_buy_button: bool = True
    no_sell_button: bool = True
    no_trade_recommendation: bool = True
    record_version: str = UI_CONTRACT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "sections": list(self.sections),
            "no_buy_button": self.no_buy_button,
            "no_sell_button": self.no_sell_button,
            "no_trade_recommendation": self.no_trade_recommendation,
            "record_version": self.record_version,
        }


def compute_observation_identity(
    *,
    data_cutoff_date: str,
    evidence_cutoff_hash: str,
    policy_hash_bundle: str,
    panel_hash: str,
    observation_mode: str = "PRODUCTION_SHADOW",
) -> str:
    return stable_hash(
        {
            "data_cutoff_date": data_cutoff_date,
            "evidence_cutoff_hash": evidence_cutoff_hash,
            "policy_hash_bundle": policy_hash_bundle,
            "panel_hash": panel_hash,
            "observation_mode": observation_mode,
            "version": OBSERVATION_VERSION,
        }
    )


def new_observation_id(identity_hash: str) -> str:
    return f"obs-{identity_hash[:16]}"


def build_forward_evaluation_contract(
    observation_id: str,
    *,
    claim_spec: Optional[Dict[str, Any]] = None,
) -> ForwardEvaluationContract:
    """
    Frozen forward contract. claim_spec is additive/versioned.

    Legacy callers (no claim_spec) keep v1 semantics and are marked
    LEGACY_INSUFFICIENT_CLAIM_SPEC so old generic outcomes are never
    reinterpreted as claim-aligned evidence.
    """
    criteria = {
        "horizons": [ForwardHorizon.T3.value, ForwardHorizon.T5.value, ForwardHorizon.T10.value],
        "return_field_by_horizon": {"T3": "t3_return_pct", "T5": "t5_return_pct", "T10": "t10_return_pct"},
        "cohort_metrics": ["return", "positive_return_indicator", "relative_return", "cohort_distribution"],
        "success_criteria_frozen_at_birth": True,
    }
    cohort_rules = {
        "preserve_birth_cohort_membership": True,
        "no_retrospective_symbol_changes": True,
        "no_hindsight_regrouping": True,
        "membership_source": "frozen_t0_group_membership_or_legacy_unspecified",
    }
    spec = dict(claim_spec or {})
    aligned = bool(spec.get("sufficient_for_claim_replay"))
    claim_family = str(spec.get("claim_family") or "LEGACY_UNSPECIFIED")
    claim_status = str(
        spec.get("claim_contract_status")
        or ("CLAIM_ALIGNED" if aligned else "LEGACY_INSUFFICIENT_CLAIM_SPEC")
    )
    version = FORWARD_CONTRACT_VERSION_V2 if spec else FORWARD_CONTRACT_VERSION
    if spec:
        criteria["claim_spec"] = spec
        criteria["claim_family"] = claim_family
        criteria["claim_contract_status"] = claim_status
        criteria["required_contrast"] = list(spec.get("required_contrast") or [])
        criteria["success_metric"] = spec.get("success_metric")
    contract_id = new_id("fwdc")
    payload = {
        "contract_id": contract_id,
        "observation_id": observation_id,
        "criteria": criteria,
        "cohort_rules": cohort_rules,
        "version": version,
        "claim_family": claim_family,
        "claim_spec": spec,
        "claim_contract_status": claim_status,
    }
    contract_hash = stable_hash(payload)
    return ForwardEvaluationContract(
        contract_id=contract_id,
        observation_id=observation_id,
        horizons=(ForwardHorizon.T3.value, ForwardHorizon.T5.value, ForwardHorizon.T10.value),
        evaluation_criteria=criteria,
        cohort_evaluation_rules=cohort_rules,
        missing_data_policy="MARK_MISSING_DO_NOT_IMPUTE",
        contract_hash=contract_hash,
        record_version=version,
        claim_family=claim_family,
        claim_spec=spec,
        claim_contract_status=claim_status,
    )


def build_forward_horizon_placeholders(trade_date: str) -> Tuple[ForwardHorizonPlaceholder, ...]:
    from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
        HORIZON_SESSION_OFFSETS,
        compute_horizon_eligible_date_vn,
    )

    out = []
    for h in HORIZON_SESSION_OFFSETS:
        eligible = compute_horizon_eligible_date_vn(trade_date, h)
        out.append(
            ForwardHorizonPlaceholder(
                horizon=h,
                status=ForwardEvaluationStatus.PENDING_FUTURE.value,
                eligible_evaluation_date=eligible,
                realized_outcome=None,
            )
        )
    return tuple(out)
