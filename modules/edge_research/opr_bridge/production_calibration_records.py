"""
Phase 3K.3 — Forward evidence & calibration ledger record types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.production_observation_records import DEFAULT_SHADOW_AUTHORITY, ShadowAuthoritySemantics

CALIBRATION_VERSION = "forward_evidence_calibration_v1_3k3"
LEDGER_ENTRY_VERSION = "forward_evidence_ledger_entry_v1_3k3"
PRE_OUTCOME_SNAPSHOT_VERSION = "pre_outcome_state_snapshot_v1_3k3"
CALIBRATION_SNAPSHOT_VERSION = "calibration_snapshot_v1_3k3"
COHORT_IDENTITY_VERSION = "forward_cohort_identity_v1_3k3"
SELF_KNOWLEDGE_VERSION = "calibration_self_knowledge_v1_3k3"

STOP_FORWARD_EVIDENCE_CALIBRATION_READY = "STOP_FORWARD_EVIDENCE_CALIBRATION_READY"


class ClaimMaturity(str, Enum):
    NO_FORWARD_EVIDENCE = "NO_FORWARD_EVIDENCE"
    IMMATURE = "IMMATURE"
    EARLY_SAMPLE = "EARLY_SAMPLE"
    ACCUMULATING = "ACCUMULATING"
    REVIEWABLE = "REVIEWABLE"


# Conservative operational thresholds — descriptive only, not scientific policy
MATURITY_THRESHOLDS = {
    ClaimMaturity.IMMATURE: 1,
    ClaimMaturity.EARLY_SAMPLE: 3,
    ClaimMaturity.ACCUMULATING: 6,
    ClaimMaturity.REVIEWABLE: 15,
}


class OutcomeAvailability(str, Enum):
    PENDING = "PENDING"
    ELIGIBLE = "ELIGIBLE"
    RELEASED = "RELEASED"
    MISSING = "MISSING"
    SUSPENDED = "SUSPENDED"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class PreOutcomeStateSnapshot:
    """Frozen belief state immediately before outcome became observable."""

    snapshot_id: str
    observation_id: str
    horizon: str
    assessment_id: Optional[str]
    assessment_trade_date: str
    epistemic_state: Optional[str]
    evidence_strength: Optional[str]
    lifecycle_state: Optional[str]
    surviving_nulls: Tuple[str, ...]
    unresolved_uncertainties: Tuple[str, ...]
    market_context_hash: Optional[str]
    observation_age_trading_days: int
    voice_assessment_id: Optional[str]
    snapshot_provenance_hash: str
    record_version: str = PRE_OUTCOME_SNAPSHOT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "observation_id": self.observation_id,
            "horizon": self.horizon,
            "assessment_id": self.assessment_id,
            "assessment_trade_date": self.assessment_trade_date,
            "epistemic_state": self.epistemic_state,
            "evidence_strength": self.evidence_strength,
            "lifecycle_state": self.lifecycle_state,
            "surviving_nulls": list(self.surviving_nulls),
            "unresolved_uncertainties": list(self.unresolved_uncertainties),
            "market_context_hash": self.market_context_hash,
            "observation_age_trading_days": self.observation_age_trading_days,
            "voice_assessment_id": self.voice_assessment_id,
            "snapshot_provenance_hash": self.snapshot_provenance_hash,
            "record_version": self.record_version,
        }


@dataclass(frozen=True)
class ForwardCohortIdentity:
    """Pre-declared cohort dimensions for descriptive aggregation."""

    cohort_id: str
    birth_regime: Optional[str]
    market_transition: Optional[str]
    hypothesis_family: Optional[str]
    epistemic_state: Optional[str]
    evidence_strength_bucket: Optional[str]
    horizon: str
    observation_age_bucket: Optional[str]
    outcome_availability: str
    cohort_hash: str
    record_version: str = COHORT_IDENTITY_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "birth_regime": self.birth_regime,
            "market_transition": self.market_transition,
            "hypothesis_family": self.hypothesis_family,
            "epistemic_state": self.epistemic_state,
            "evidence_strength_bucket": self.evidence_strength_bucket,
            "horizon": self.horizon,
            "observation_age_bucket": self.observation_age_bucket,
            "outcome_availability": self.outcome_availability,
            "cohort_hash": self.cohort_hash,
            "record_version": self.record_version,
        }


@dataclass
class ForwardEvidenceLedgerEntry:
    """Append-only authoritative forward evidence entry — LIVE_FORWARD only."""

    ledger_entry_id: str
    observation_id: str
    horizon: str
    birth_record_hash: str
    outcome_record_id: str
    run_id: str
    run_mode: str
    pre_outcome_snapshot: PreOutcomeStateSnapshot
    outcome_values: Dict[str, Any]
    outcome_status: str
    release_trade_date: str
    eligible_evaluation_date: str
    cohort_identity: ForwardCohortIdentity
    provenance: Dict[str, Any]
    counts_as_forward_evidence: bool
    dependence_warning: Optional[str]
    ledger_identity_hash: str = ""
    shadow_authority: ShadowAuthoritySemantics = DEFAULT_SHADOW_AUTHORITY
    record_version: str = LEDGER_ENTRY_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ledger_entry_id": self.ledger_entry_id,
            "observation_id": self.observation_id,
            "horizon": self.horizon,
            "birth_record_hash": self.birth_record_hash,
            "outcome_record_id": self.outcome_record_id,
            "run_id": self.run_id,
            "run_mode": self.run_mode,
            "pre_outcome_snapshot": self.pre_outcome_snapshot.to_dict(),
            "outcome_values": dict(self.outcome_values),
            "outcome_status": self.outcome_status,
            "release_trade_date": self.release_trade_date,
            "eligible_evaluation_date": self.eligible_evaluation_date,
            "cohort_identity": self.cohort_identity.to_dict(),
            "provenance": dict(self.provenance),
            "counts_as_forward_evidence": self.counts_as_forward_evidence,
            "dependence_warning": self.dependence_warning,
            "ledger_identity_hash": self.ledger_identity_hash,
            "shadow_authority": self.shadow_authority.to_dict(),
            "record_version": self.record_version,
        }


@dataclass
class CalibrationSnapshot:
    """Immutable point-in-time calibration view — later outcomes cannot rewrite."""

    snapshot_id: str
    as_of_trade_date: str
    snapshot_timestamp: str
    maturity_label: str
    total_live_forward_observations: int
    eligible_n: int
    pending_n: int
    missing_n: int
    by_horizon: Dict[str, Dict[str, int]]
    by_epistemic_state: Dict[str, Dict[str, Any]]
    by_evidence_strength: Dict[str, Dict[str, Any]]
    by_lifecycle_state: Dict[str, Dict[str, Any]]
    dependence_flags: Tuple[str, ...]
    ledger_entry_ids: Tuple[str, ...]
    provenance_hash: str
    counts_as_forward_evidence: bool
    frozen: bool = True
    record_version: str = CALIBRATION_SNAPSHOT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "as_of_trade_date": self.as_of_trade_date,
            "snapshot_timestamp": self.snapshot_timestamp,
            "maturity_label": self.maturity_label,
            "total_live_forward_observations": self.total_live_forward_observations,
            "eligible_n": self.eligible_n,
            "pending_n": self.pending_n,
            "missing_n": self.missing_n,
            "by_horizon": dict(self.by_horizon),
            "by_epistemic_state": dict(self.by_epistemic_state),
            "by_evidence_strength": dict(self.by_evidence_strength),
            "by_lifecycle_state": dict(self.by_lifecycle_state),
            "dependence_flags": list(self.dependence_flags),
            "ledger_entry_ids": list(self.ledger_entry_ids),
            "provenance_hash": self.provenance_hash,
            "counts_as_forward_evidence": self.counts_as_forward_evidence,
            "frozen": self.frozen,
            "record_version": self.record_version,
        }


def compute_ledger_entry_identity(
    *,
    observation_id: str,
    horizon: str,
    outcome_record_id: str,
    birth_record_hash: str,
    pre_outcome_snapshot_hash: str,
    run_mode: str,
) -> str:
    return stable_hash({
        "observation_id": observation_id,
        "horizon": horizon,
        "outcome_record_id": outcome_record_id,
        "birth_record_hash": birth_record_hash,
        "pre_outcome_snapshot_hash": pre_outcome_snapshot_hash,
        "run_mode": run_mode,
        "version": LEDGER_ENTRY_VERSION,
    })


def new_ledger_entry_id(identity_hash: str) -> str:
    return f"fwdev-{identity_hash[:16]}"


def compute_snapshot_identity(*, as_of_trade_date: str, ledger_entry_ids: Tuple[str, ...]) -> str:
    return stable_hash({
        "as_of_trade_date": as_of_trade_date,
        "ledger_entry_ids": sorted(ledger_entry_ids),
        "version": CALIBRATION_SNAPSHOT_VERSION,
    })


def derive_claim_maturity(eligible_n: int) -> str:
    if eligible_n <= 0:
        return ClaimMaturity.NO_FORWARD_EVIDENCE.value
    if eligible_n < MATURITY_THRESHOLDS[ClaimMaturity.EARLY_SAMPLE]:
        return ClaimMaturity.IMMATURE.value
    if eligible_n < MATURITY_THRESHOLDS[ClaimMaturity.ACCUMULATING]:
        return ClaimMaturity.EARLY_SAMPLE.value
    if eligible_n < MATURITY_THRESHOLDS[ClaimMaturity.REVIEWABLE]:
        return ClaimMaturity.ACCUMULATING.value
    return ClaimMaturity.REVIEWABLE.value


def evidence_strength_bucket(strength: Optional[str]) -> str:
    if not strength:
        return "UNKNOWN"
    s = str(strength).upper()
    if s in ("STRONG", "SUPPORTED"):
        return "STRONG_OR_SUPPORTED"
    if s in ("MODERATE", "WEAK"):
        return s
    return "OTHER"
