"""
Phase 3H.2A — Controlled Exposure Infrastructure.
Phase 3H.2B — First controlled exposure (rsi_slope) via explicit approval manifest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.adapters import build_research_panel, load_lifecycle
from modules.edge_research.research_data_expansion_audit import (
    EXPANSION_AUDIT_VERSION,
    ScientificSafetyClass,
    ResearchDataExpansionAudit,
    build_research_data_expansion_audit,
)
from modules.edge_research.research_feature_eligibility import (
    FIELD_AVAILABILITY_HORIZON,
    assess_feature_eligibility,
    field_availability_horizon,
)
from modules.edge_research.research_panel_exposure import (
    CORE_STOCK_PANEL_FIELDS,
    PANEL_EXPOSURE_DESIGN_VERSION,
    PHASE_3H2B_FIRST_CONTROLLED_FIELD,
    PanelExposureManifest,
    build_empty_panel_manifest,
    build_phase_3h2b_panel_manifest,
    get_active_panel_exposure_manifest,
    resolve_effective_stock_columns,
)
from modules.edge_research.research_provenance_proof import (
    PROVENANCE_PROOF_VERSION,
    FieldProvenanceProof,
    ResearchProvenanceProofReport,
    build_research_provenance_proof,
)

EXPOSURE_GOVERNANCE_VERSION = "research_exposure_governance_v2"
EXPOSURE_POLICY_VERSION = "controlled_exposure_policy_v1"
PHASE_3H1_1_FROZEN_COMMIT = "300810ff8"
PHASE_3H2A_FROZEN_COMMIT = "88e4df5f1"
PHASE_3H2B_APPROVAL_SOURCE = "PHASE_3H2B_EXPLICIT_MANIFEST"

_ELIGIBLE_SCIENTIFIC_CLASSES: FrozenSet[str] = frozenset(
    {
        ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
        ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
    }
)

_BLOCKED_SCIENTIFIC_CLASSES: FrozenSet[str] = frozenset(
    {
        ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value,
        ScientificSafetyClass.PROVENANCE_UNRESOLVED.value,
        ScientificSafetyClass.TEMPORALLY_UNSAFE_OR_PRODUCTION_ONLY.value,
    }
)


class ExposureLifecycleState(str, Enum):
    EXISTS_IN_SYSTEM = "EXISTS_IN_SYSTEM"
    PROVENANCE_AUDITED = "PROVENANCE_AUDITED"
    SCIENTIFICALLY_SAFE = "SCIENTIFICALLY_SAFE"
    ELIGIBLE_FOR_EXPOSURE = "ELIGIBLE_FOR_EXPOSURE"
    APPROVED_FOR_EXPOSURE = "APPROVED_FOR_EXPOSURE"
    WIRED_TO_RESEARCH_PANEL = "WIRED_TO_RESEARCH_PANEL"
    RESEARCH_ACCESSIBLE_NOW = "RESEARCH_ACCESSIBLE_NOW"
    TEMPORALLY_LEGAL_AT_HORIZON = "TEMPORALLY_LEGAL_AT_HORIZON"
    EXERCISED_BY_RESEARCHER = "EXERCISED_BY_RESEARCHER"


@dataclass(frozen=True)
class CapabilityExposureRecord:
    capability_id: str
    field_name: str
    source_id: str
    provenance_proof_id: str
    provenance_classification: str
    proof_confidence: str
    point_in_time_reconstructable: str
    future_dependency_detected: bool
    outcome_dependency_detected: bool
    retrospective_dependency_detected: bool
    revision_risk: str
    earliest_availability_horizon: int
    scientific_safety_status: str
    exists_in_system: bool
    provenance_audited: bool
    scientifically_safe: bool
    eligible_for_exposure: bool
    eligibility_reason: str
    approved_for_exposure: bool
    approval_source: str
    wired_to_panel: bool
    research_accessible_now: bool
    temporally_legal_at_horizon: bool
    exercised_by_researcher: bool
    blockers: Tuple[str, ...]
    exposure_version: str
    provenance_fingerprint: str
    proof_version: str
    policy_version: str
    audit_history: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "field_name": self.field_name,
            "source_id": self.source_id,
            "provenance_proof_id": self.provenance_proof_id,
            "provenance_classification": self.provenance_classification,
            "proof_confidence": self.proof_confidence,
            "point_in_time_reconstructable": self.point_in_time_reconstructable,
            "future_dependency_detected": self.future_dependency_detected,
            "outcome_dependency_detected": self.outcome_dependency_detected,
            "retrospective_dependency_detected": self.retrospective_dependency_detected,
            "revision_risk": self.revision_risk,
            "earliest_availability_horizon": self.earliest_availability_horizon,
            "scientific_safety_status": self.scientific_safety_status,
            "exists_in_system": self.exists_in_system,
            "provenance_audited": self.provenance_audited,
            "scientifically_safe": self.scientifically_safe,
            "eligible_for_exposure": self.eligible_for_exposure,
            "eligibility_reason": self.eligibility_reason,
            "approved_for_exposure": self.approved_for_exposure,
            "approval_source": self.approval_source,
            "wired_to_panel": self.wired_to_panel,
            "research_accessible_now": self.research_accessible_now,
            "temporally_legal_at_horizon": self.temporally_legal_at_horizon,
            "exercised_by_researcher": self.exercised_by_researcher,
            "blockers": list(self.blockers),
            "exposure_version": self.exposure_version,
            "provenance_fingerprint": self.provenance_fingerprint,
            "proof_version": self.proof_version,
            "policy_version": self.policy_version,
            "audit_history": list(self.audit_history),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CapabilityExposureRecord":
        return cls(
            capability_id=str(payload["capability_id"]),
            field_name=str(payload["field_name"]),
            source_id=str(payload.get("source_id") or ""),
            provenance_proof_id=str(payload.get("provenance_proof_id") or ""),
            provenance_classification=str(payload.get("provenance_classification") or ""),
            proof_confidence=str(payload.get("proof_confidence") or ""),
            point_in_time_reconstructable=str(
                payload.get("point_in_time_reconstructable", "unresolved")
            ),
            future_dependency_detected=bool(payload.get("future_dependency_detected", False)),
            outcome_dependency_detected=bool(payload.get("outcome_dependency_detected", False)),
            retrospective_dependency_detected=bool(
                payload.get("retrospective_dependency_detected", False)
            ),
            revision_risk=str(payload.get("revision_risk") or ""),
            earliest_availability_horizon=int(payload.get("earliest_availability_horizon", 999)),
            scientific_safety_status=str(payload.get("scientific_safety_status") or ""),
            exists_in_system=bool(payload.get("exists_in_system", False)),
            provenance_audited=bool(payload.get("provenance_audited", False)),
            scientifically_safe=bool(payload.get("scientifically_safe", False)),
            eligible_for_exposure=bool(payload.get("eligible_for_exposure", False)),
            eligibility_reason=str(payload.get("eligibility_reason") or ""),
            approved_for_exposure=bool(payload.get("approved_for_exposure", False)),
            approval_source=str(payload.get("approval_source") or ""),
            wired_to_panel=bool(payload.get("wired_to_panel", False)),
            research_accessible_now=bool(payload.get("research_accessible_now", False)),
            temporally_legal_at_horizon=bool(payload.get("temporally_legal_at_horizon", False)),
            exercised_by_researcher=bool(payload.get("exercised_by_researcher", False)),
            blockers=tuple(payload.get("blockers") or ()),
            exposure_version=str(payload.get("exposure_version", EXPOSURE_GOVERNANCE_VERSION)),
            provenance_fingerprint=str(payload.get("provenance_fingerprint") or ""),
            proof_version=str(payload.get("proof_version") or ""),
            policy_version=str(payload.get("policy_version", EXPOSURE_POLICY_VERSION)),
            audit_history=tuple(payload.get("audit_history") or ()),
        )


@dataclass(frozen=True)
class ResearchExposurePolicy:
    """Generic scientific policy — no field-name exceptions."""

    version: str = EXPOSURE_POLICY_VERSION
    require_provenance_investigated: bool = True
    require_point_in_time_reconstructable: bool = True
    require_no_future_dependency: bool = True
    require_no_outcome_dependency: bool = True
    require_no_retrospective_dependency: bool = True
    require_temporal_metadata: bool = True
    block_production_only: bool = True
    auto_approve: bool = False  # Phase 3H.2A: always false

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "require_provenance_investigated": self.require_provenance_investigated,
            "require_point_in_time_reconstructable": self.require_point_in_time_reconstructable,
            "require_no_future_dependency": self.require_no_future_dependency,
            "require_no_outcome_dependency": self.require_no_outcome_dependency,
            "require_no_retrospective_dependency": self.require_no_retrospective_dependency,
            "require_temporal_metadata": self.require_temporal_metadata,
            "block_production_only": self.block_production_only,
            "auto_approve": self.auto_approve,
        }


@dataclass(frozen=True)
class ResearchExposureApprovalEntry:
    """Explicit exposure approval bound to provenance fingerprint."""

    field_name: str
    provenance_proof_id: str
    provenance_fingerprint: str
    proof_version: str
    approval_source: str
    approved_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "provenance_proof_id": self.provenance_proof_id,
            "provenance_fingerprint": self.provenance_fingerprint,
            "proof_version": self.proof_version,
            "approval_source": self.approval_source,
            "approved_at": self.approved_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchExposureApprovalEntry":
        return cls(
            field_name=str(payload["field_name"]),
            provenance_proof_id=str(payload["provenance_proof_id"]),
            provenance_fingerprint=str(payload["provenance_fingerprint"]),
            proof_version=str(payload["proof_version"]),
            approval_source=str(payload.get("approval_source") or ""),
            approved_at=str(payload.get("approved_at") or ""),
        )


@dataclass
class ResearchExposureContract:
    """Session-persistent exposure governance contract."""

    version: str = EXPOSURE_GOVERNANCE_VERSION
    built_at: str = ""
    phase_3h1_1_frozen_commit: str = PHASE_3H1_1_FROZEN_COMMIT
    provenance_proof_version: str = PROVENANCE_PROOF_VERSION
    expansion_audit_version: str = EXPANSION_AUDIT_VERSION
    panel_exposure_version: str = PANEL_EXPOSURE_DESIGN_VERSION
    policy: ResearchExposurePolicy = field(default_factory=ResearchExposurePolicy)
    records: Dict[str, CapabilityExposureRecord] = field(default_factory=dict)
    panel_manifest: PanelExposureManifest = field(default_factory=PanelExposureManifest)
    approval_entries: Tuple[ResearchExposureApprovalEntry, ...] = field(default_factory=tuple)
    observation_horizon: int = 0
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    revoked_records: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "built_at": self.built_at,
            "phase_3h1_1_frozen_commit": self.phase_3h1_1_frozen_commit,
            "provenance_proof_version": self.provenance_proof_version,
            "expansion_audit_version": self.expansion_audit_version,
            "panel_exposure_version": self.panel_exposure_version,
            "policy": self.policy.to_dict(),
            "records": {k: v.to_dict() for k, v in sorted(self.records.items())},
            "panel_manifest": {
                "version": self.panel_manifest.version,
                "approved_field_names": sorted(self.panel_manifest.approved_field_names),
                "wired_field_names": sorted(self.panel_manifest.wired_field_names),
            },
            "approval_entries": [e.to_dict() for e in self.approval_entries],
            "observation_horizon": self.observation_horizon,
            "audit_trail": list(self.audit_trail),
            "revoked_records": list(self.revoked_records),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchExposureContract":
        manifest_raw = payload.get("panel_manifest") or {}
        records = {
            k: CapabilityExposureRecord.from_dict(v)
            for k, v in (payload.get("records") or {}).items()
        }
        policy_raw = payload.get("policy") or {}
        return cls(
            version=str(payload.get("version", EXPOSURE_GOVERNANCE_VERSION)),
            built_at=str(payload.get("built_at", "")),
            phase_3h1_1_frozen_commit=str(
                payload.get("phase_3h1_1_frozen_commit", PHASE_3H1_1_FROZEN_COMMIT)
            ),
            provenance_proof_version=str(
                payload.get("provenance_proof_version", PROVENANCE_PROOF_VERSION)
            ),
            expansion_audit_version=str(
                payload.get("expansion_audit_version", EXPANSION_AUDIT_VERSION)
            ),
            panel_exposure_version=str(
                payload.get("panel_exposure_version", PANEL_EXPOSURE_DESIGN_VERSION)
            ),
            policy=ResearchExposurePolicy(
                version=str(policy_raw.get("version", EXPOSURE_POLICY_VERSION)),
                require_provenance_investigated=bool(
                    policy_raw.get("require_provenance_investigated", True)
                ),
                require_point_in_time_reconstructable=bool(
                    policy_raw.get("require_point_in_time_reconstructable", True)
                ),
                require_no_future_dependency=bool(
                    policy_raw.get("require_no_future_dependency", True)
                ),
                require_no_outcome_dependency=bool(
                    policy_raw.get("require_no_outcome_dependency", True)
                ),
                require_no_retrospective_dependency=bool(
                    policy_raw.get("require_no_retrospective_dependency", True)
                ),
                require_temporal_metadata=bool(policy_raw.get("require_temporal_metadata", True)),
                block_production_only=bool(policy_raw.get("block_production_only", True)),
                auto_approve=bool(policy_raw.get("auto_approve", False)),
            ),
            records=records,
            panel_manifest=PanelExposureManifest(
                version=str(manifest_raw.get("version", PANEL_EXPOSURE_DESIGN_VERSION)),
                approved_field_names=frozenset(
                    str(x) for x in (manifest_raw.get("approved_field_names") or ())
                ),
                wired_field_names=frozenset(
                    str(x) for x in (manifest_raw.get("wired_field_names") or ())
                ),
            ),
            approval_entries=tuple(
                ResearchExposureApprovalEntry.from_dict(e)
                for e in (payload.get("approval_entries") or ())
            ),
            observation_horizon=int(payload.get("observation_horizon", 0)),
            audit_trail=list(payload.get("audit_trail") or []),
            revoked_records=list(payload.get("revoked_records") or []),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_provenance_fingerprint(
    *,
    proof_version: str,
    field_id: str,
    classification: str,
    producer_module: str,
    transformation_chain: Tuple[str, ...],
    policy_version: str,
) -> str:
    payload = {
        "proof_version": proof_version,
        "field_id": field_id,
        "classification": classification,
        "producer_module": producer_module,
        "transformation_chain": list(transformation_chain),
        "policy_version": policy_version,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"pf:{digest[:24]}"


def build_phase_3h2b_approval_entries(
    provenance_report: ResearchProvenanceProofReport,
    *,
    policy_version: str = EXPOSURE_POLICY_VERSION,
) -> Tuple[ResearchExposureApprovalEntry, ...]:
    """Derive explicit Phase 3H.2B approval for rsi_slope from provenance proof."""
    proof_id = f"provenance_proof:missing_panel:{PHASE_3H2B_FIRST_CONTROLLED_FIELD}"
    proof = provenance_report.field_proofs.get(proof_id)
    if proof is None:
        raise ValueError(f"MISSING_PROVENANCE_PROOF:{PHASE_3H2B_FIRST_CONTROLLED_FIELD}")

    fingerprint = compute_provenance_fingerprint(
        proof_version=provenance_report.version,
        field_id=proof.field_id,
        classification=proof.final_scientific_classification,
        producer_module=proof.producer_module,
        transformation_chain=proof.transformation_chain,
        policy_version=policy_version,
    )
    return (
        ResearchExposureApprovalEntry(
            field_name=PHASE_3H2B_FIRST_CONTROLLED_FIELD,
            provenance_proof_id=proof.field_id,
            provenance_fingerprint=fingerprint,
            proof_version=provenance_report.version,
            approval_source=PHASE_3H2B_APPROVAL_SOURCE,
            approved_at=_utc_now(),
        ),
    )


def resolve_validated_approval_fields(
    approval_entries: Sequence[ResearchExposureApprovalEntry],
    proofs: Dict[str, FieldProvenanceProof],
    *,
    policy_version: str,
    proof_version: str,
) -> Tuple[FrozenSet[str], Tuple[str, ...]]:
    """Return fields with fingerprint-valid explicit approval — fail closed."""
    approved: set[str] = set()
    errors: List[str] = []
    for entry in approval_entries:
        proof = proofs.get(entry.provenance_proof_id)
        if proof is None:
            errors.append(f"MISSING_PROOF:{entry.field_name}")
            continue
        if entry.proof_version != proof_version:
            errors.append(f"STALE_PROOF_VERSION:{entry.field_name}")
            continue
        expected = compute_provenance_fingerprint(
            proof_version=proof_version,
            field_id=proof.field_id,
            classification=proof.final_scientific_classification,
            producer_module=proof.producer_module,
            transformation_chain=proof.transformation_chain,
            policy_version=policy_version,
        )
        if expected != entry.provenance_fingerprint:
            errors.append(f"FINGERPRINT_MISMATCH:{entry.field_name}")
            continue
        approved.add(entry.field_name)
    return frozenset(approved), tuple(errors)


def _approval_source_for_field(
    field_name: str,
    approval_entries: Sequence[ResearchExposureApprovalEntry],
) -> str:
    for entry in approval_entries:
        if entry.field_name == field_name:
            return entry.approval_source
    return ""


def _temporally_legal(
    field_name: str,
    observation_horizon: int,
    *,
    earliest_horizon: Optional[int] = None,
) -> bool:
    avail = field_availability_horizon(field_name)
    if earliest_horizon is not None:
        avail = max(avail, earliest_horizon)
    if field_name in FIELD_AVAILABILITY_HORIZON or avail < 999:
        return observation_horizon >= avail
    assess = assess_feature_eligibility(field_name, observation_horizon=observation_horizon)
    return bool(assess.eligible_at_observation)


def evaluate_provenance_eligibility(
    *,
    proof: Optional[FieldProvenanceProof],
    expansion_entry: Optional[Any],
    policy: ResearchExposurePolicy,
    observation_horizon: int,
) -> Tuple[bool, str, Tuple[str, ...], bool, bool]:
    """
    Provenance gate — generic, fail-closed.

    Returns (eligible, reason, blockers, scientifically_safe, provenance_audited).
    """
    blockers: List[str] = []

    if proof is None:
        blockers.append("MISSING_PROVENANCE_PROOF")
        return False, "NO_PROVENANCE_PROOF", tuple(blockers), False, False

    provenance_audited = bool(proof.evidence_references)
    if policy.require_provenance_investigated and not provenance_audited:
        blockers.append("PROVENANCE_NOT_INVESTIGATED")

    classification = proof.final_scientific_classification
    if classification in _BLOCKED_SCIENTIFIC_CLASSES:
        blockers.append(f"BLOCKED_CLASS:{classification}")

    scientifically_safe = classification in _ELIGIBLE_SCIENTIFIC_CLASSES

    if policy.require_point_in_time_reconstructable:
        if proof.point_in_time_reconstructable != "true":
            blockers.append("NOT_POINT_IN_TIME_RECONSTRUCTABLE")

    if policy.require_no_future_dependency and proof.future_dependency_detected:
        blockers.append("FUTURE_DEPENDENCY")

    if policy.require_no_outcome_dependency and proof.outcome_dependency_detected:
        blockers.append("OUTCOME_DEPENDENCY")

    if policy.require_no_retrospective_dependency and proof.retrospective_classification_dependency:
        blockers.append("RETROSPECTIVE_DEPENDENCY")

    if proof.blocker and "PROVENANCE_UNRESOLVED" in proof.blocker.upper():
        blockers.append("UNRESOLVED_PROVENANCE_BLOCKER")

    if policy.block_production_only:
        if classification == ScientificSafetyClass.TEMPORALLY_UNSAFE_OR_PRODUCTION_ONLY.value:
            blockers.append("PRODUCTION_ONLY")

    if expansion_entry is not None:
        if getattr(expansion_entry, "scientific_class", "") in _BLOCKED_SCIENTIFIC_CLASSES:
            blockers.append(f"EXPANSION_AUDIT_BLOCKED:{expansion_entry.scientific_class}")
        if getattr(expansion_entry, "future_dependency", False):
            blockers.append("EXPANSION_FUTURE_DEPENDENCY")

    if policy.require_temporal_metadata:
        if proof.earliest_availability_horizon >= 999:
            blockers.append("MISSING_TEMPORAL_METADATA")

    if not scientifically_safe:
        blockers.append("NOT_SCIENTIFICALLY_SAFE")

    eligible = len(blockers) == 0
    reason = "ELIGIBILITY_PASSED" if eligible else "ELIGIBILITY_BLOCKED"
    return eligible, reason, tuple(blockers), scientifically_safe, provenance_audited


def evaluate_approval_gate(
    *,
    eligible: bool,
    approved_manifest: FrozenSet[str],
    field_name: str,
    wired_manifest: FrozenSet[str],
    panel_columns: FrozenSet[str],
    lifecycle_columns: FrozenSet[str],
    policy: ResearchExposurePolicy,
    prior_approved: bool,
    fingerprint_match: bool,
) -> Tuple[bool, bool, bool, Tuple[str, ...]]:
    """
    Approval gate — separate from eligibility. Phase 3H.2A: no auto-approval.

    Returns (approved, wired, accessible, blockers).
    """
    blockers: List[str] = []

    if not fingerprint_match:
        blockers.append("PROVENANCE_FINGERPRINT_MISMATCH")

    if not eligible:
        blockers.append("NOT_ELIGIBLE")
        return False, False, False, tuple(blockers)

    approved = field_name in approved_manifest or (
        policy.auto_approve and not blockers
    )
    if prior_approved and field_name in approved_manifest:
        approved = True
    if not approved:
        blockers.append("NOT_APPROVED_FOR_EXPOSURE")

    wired = approved and field_name in wired_manifest
    if approved and field_name in wired_manifest and field_name not in lifecycle_columns:
        blockers.append("MISSING_SOURCE_COLUMN")
        wired = False

    accessible = wired and field_name in panel_columns
    if wired and field_name not in panel_columns:
        blockers.append("NOT_ON_RESEARCH_PANEL")

    if not approved:
        return False, False, False, tuple(blockers)

    return approved, wired, accessible, tuple(blockers)


def _record_from_proof(
    proof: FieldProvenanceProof,
    *,
    expansion_entry: Optional[Any],
    policy: ResearchExposurePolicy,
    panel_columns: FrozenSet[str],
    lifecycle_columns: FrozenSet[str],
    approved_manifest: FrozenSet[str],
    wired_manifest: FrozenSet[str],
    observation_horizon: int,
    proof_version: str,
    approval_entries: Sequence[ResearchExposureApprovalEntry] = (),
    fingerprint_match: bool = True,
) -> CapabilityExposureRecord:
    fingerprint = compute_provenance_fingerprint(
        proof_version=proof_version,
        field_id=proof.field_id,
        classification=proof.final_scientific_classification,
        producer_module=proof.producer_module,
        transformation_chain=proof.transformation_chain,
        policy_version=policy.version,
    )

    eligible, elig_reason, elig_blockers, sci_safe, audited = evaluate_provenance_eligibility(
        proof=proof,
        expansion_entry=expansion_entry,
        policy=policy,
        observation_horizon=observation_horizon,
    )

    approved, wired, accessible, appr_blockers = evaluate_approval_gate(
        eligible=eligible,
        approved_manifest=approved_manifest,
        field_name=proof.field_name,
        wired_manifest=wired_manifest,
        panel_columns=panel_columns,
        lifecycle_columns=lifecycle_columns,
        policy=policy,
        prior_approved=proof.field_name in approved_manifest,
        fingerprint_match=fingerprint_match,
    )

    temporal_legal = _temporally_legal(
        proof.field_name,
        observation_horizon,
        earliest_horizon=proof.earliest_availability_horizon,
    )
    blockers = tuple(dict.fromkeys(elig_blockers + appr_blockers))
    approval_source = _approval_source_for_field(proof.field_name, approval_entries) if approved else ""

    history = (
        {
            "event": "EXPOSURE_RECORD_BUILT",
            "timestamp": _utc_now(),
            "eligible": eligible,
            "approved": approved,
            "wired": wired,
            "accessible": accessible,
            "fingerprint": fingerprint,
            "lifecycle_event": "EXPOSED" if accessible else "NOT_EXPOSED",
        },
    )

    return CapabilityExposureRecord(
        capability_id=f"exposure:{proof.field_name}",
        field_name=proof.field_name,
        source_id=proof.source_id,
        provenance_proof_id=proof.field_id,
        provenance_classification=proof.final_scientific_classification,
        proof_confidence=proof.confidence,
        point_in_time_reconstructable=proof.point_in_time_reconstructable,
        future_dependency_detected=proof.future_dependency_detected,
        outcome_dependency_detected=proof.outcome_dependency_detected,
        retrospective_dependency_detected=proof.retrospective_classification_dependency,
        revision_risk=proof.revision_risk,
        earliest_availability_horizon=proof.earliest_availability_horizon,
        scientific_safety_status=proof.final_scientific_classification,
        exists_in_system=proof.field_name in lifecycle_columns or proof.field_name == "close",
        provenance_audited=audited,
        scientifically_safe=sci_safe,
        eligible_for_exposure=eligible,
        eligibility_reason=elig_reason,
        approved_for_exposure=approved,
        approval_source=approval_source,
        wired_to_panel=wired,
        research_accessible_now=accessible,
        temporally_legal_at_horizon=temporal_legal,
        exercised_by_researcher=False,
        blockers=blockers,
        exposure_version=EXPOSURE_GOVERNANCE_VERSION,
        provenance_fingerprint=fingerprint,
        proof_version=proof_version,
        policy_version=policy.version,
        audit_history=history,
    )


def _record_from_expansion_negative_control(
    entry: Any,
    *,
    policy: ResearchExposurePolicy,
    panel_columns: FrozenSet[str],
    observation_horizon: int,
) -> CapabilityExposureRecord:
    """Negative-control record from expansion audit without deep proof."""
    field_name = entry.field_name
    classification = entry.scientific_class
    fingerprint = compute_provenance_fingerprint(
        proof_version="none",
        field_id=entry.capability_id,
        classification=classification,
        producer_module=entry.derivation_provenance or "",
        transformation_chain=(entry.derivation_provenance or "",),
        policy_version=policy.version,
    )

    eligible, elig_reason, blockers, sci_safe, audited = evaluate_provenance_eligibility(
        proof=None,
        expansion_entry=entry,
        policy=policy,
        observation_horizon=observation_horizon,
    )

    if classification in _BLOCKED_SCIENTIFIC_CLASSES:
        sci_safe = False
        blockers = tuple(dict.fromkeys(blockers + (f"BLOCKED_CLASS:{classification}",)))

    temporal_legal = _temporally_legal(field_name, observation_horizon)

    return CapabilityExposureRecord(
        capability_id=f"exposure:audit:{entry.capability_id}",
        field_name=field_name,
        source_id=entry.source_id,
        provenance_proof_id="",
        provenance_classification=classification,
        proof_confidence=entry.confidence,
        point_in_time_reconstructable="unresolved",
        future_dependency_detected=bool(entry.future_dependency),
        outcome_dependency_detected=bool(entry.future_dependency),
        retrospective_dependency_detected=False,
        revision_risk="UNKNOWN",
        earliest_availability_horizon=int(entry.earliest_legal_horizon),
        scientific_safety_status=classification,
        exists_in_system=bool(entry.exists),
        provenance_audited=audited,
        scientifically_safe=sci_safe,
        eligible_for_exposure=eligible,
        eligibility_reason=elig_reason,
        approved_for_exposure=False,
        approval_source="",
        wired_to_panel=False,
        research_accessible_now=False,
        temporally_legal_at_horizon=temporal_legal,
        exercised_by_researcher=False,
        blockers=blockers,
        exposure_version=EXPOSURE_GOVERNANCE_VERSION,
        provenance_fingerprint=fingerprint,
        proof_version="none",
        policy_version=policy.version,
        audit_history=(
            {
                "event": "NEGATIVE_CONTROL_EVALUATED",
                "timestamp": _utc_now(),
                "classification": classification,
            },
        ),
    )


def revoke_exposure_record(
    record: CapabilityExposureRecord,
    *,
    reason: str,
    prior_fingerprint: str,
) -> Tuple[CapabilityExposureRecord, Dict[str, Any]]:
    """Invalidate eligibility/approval — preserve audit history."""
    revoked_event = {
        "event": "EXPOSURE_REVOKED",
        "timestamp": _utc_now(),
        "reason": reason,
        "prior_fingerprint": prior_fingerprint,
        "record_capability_id": record.capability_id,
    }
    new_history = record.audit_history + (revoked_event,)
    updated = CapabilityExposureRecord(
        capability_id=record.capability_id,
        field_name=record.field_name,
        source_id=record.source_id,
        provenance_proof_id=record.provenance_proof_id,
        provenance_classification=record.provenance_classification,
        proof_confidence=record.proof_confidence,
        point_in_time_reconstructable=record.point_in_time_reconstructable,
        future_dependency_detected=record.future_dependency_detected,
        outcome_dependency_detected=record.outcome_dependency_detected,
        retrospective_dependency_detected=record.retrospective_dependency_detected,
        revision_risk=record.revision_risk,
        earliest_availability_horizon=record.earliest_availability_horizon,
        scientific_safety_status=record.scientific_safety_status,
        exists_in_system=record.exists_in_system,
        provenance_audited=record.provenance_audited,
        scientifically_safe=record.scientifically_safe,
        eligible_for_exposure=False,
        eligibility_reason="REVOKED",
        approved_for_exposure=False,
        approval_source="",
        wired_to_panel=False,
        research_accessible_now=False,
        temporally_legal_at_horizon=record.temporally_legal_at_horizon,
        exercised_by_researcher=False,
        blockers=record.blockers + (reason,),
        exposure_version=record.exposure_version,
        provenance_fingerprint=record.provenance_fingerprint,
        proof_version=record.proof_version,
        policy_version=record.policy_version,
        audit_history=new_history,
    )
    return updated, revoked_event


def validate_fingerprint_match(
    record: CapabilityExposureRecord,
    proof: FieldProvenanceProof,
    *,
    proof_version: str,
    policy_version: str,
) -> bool:
    expected = compute_provenance_fingerprint(
        proof_version=proof_version,
        field_id=proof.field_id,
        classification=proof.final_scientific_classification,
        producer_module=proof.producer_module,
        transformation_chain=proof.transformation_chain,
        policy_version=policy_version,
    )
    return record.provenance_fingerprint == expected


_NEGATIVE_CONTROL_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("pattern_knowledge", "win_rate_pct"),
    ("intraday_camera", "close"),
    ("observations", "decision_status"),
)


def build_research_exposure_contract(
    panel: Optional[pd.DataFrame] = None,
    *,
    provenance_report: Optional[ResearchProvenanceProofReport] = None,
    expansion_audit: Optional[ResearchDataExpansionAudit] = None,
    policy: Optional[ResearchExposurePolicy] = None,
    observation_horizon: int = 0,
    panel_manifest: Optional[PanelExposureManifest] = None,
    approval_entries: Optional[Sequence[ResearchExposureApprovalEntry]] = None,
) -> ResearchExposureContract:
    """Build exposure governance contract with optional Phase 3H.2B approval."""
    pol = policy or ResearchExposurePolicy()
    manifest = panel_manifest if panel_manifest is not None else get_active_panel_exposure_manifest()

    ok, reason = manifest.validate()
    if not ok:
        raise ValueError(f"MALFORMED_EXPOSURE_MANIFEST: {reason}")

    lifecycle = load_lifecycle()
    lifecycle_columns = frozenset(lifecycle.columns) if not lifecycle.empty else frozenset()

    if provenance_report is None or expansion_audit is None:
        baseline_panel = panel
        if baseline_panel is None:
            try:
                baseline_panel = build_research_panel(
                    lifecycle=lifecycle,
                    panel_manifest=build_empty_panel_manifest(),
                )
            except Exception:
                baseline_panel = pd.DataFrame()
        if expansion_audit is None:
            expansion_audit = build_research_data_expansion_audit(baseline_panel)
        if provenance_report is None:
            provenance_report = build_research_provenance_proof(baseline_panel, expansion_audit)

    if provenance_report.version != PROVENANCE_PROOF_VERSION:
        raise ValueError("STALE_PROVENANCE_PROOF_VERSION")

    entries = (
        tuple(approval_entries)
        if approval_entries is not None
        else build_phase_3h2b_approval_entries(provenance_report, policy_version=pol.version)
        if manifest.approved_field_names
        else ()
    )

    validated_approved, approval_errors = resolve_validated_approval_fields(
        entries,
        provenance_report.field_proofs,
        policy_version=pol.version,
        proof_version=provenance_report.version,
    )
    if approval_errors and manifest.approved_field_names:
        raise ValueError(f"APPROVAL_VALIDATION_FAILED:{approval_errors}")

    effective_approved = validated_approved & manifest.approved_field_names
    effective_wired = validated_approved & manifest.wired_field_names

    if panel is None:
        try:
            panel = build_research_panel(
                lifecycle=lifecycle,
                panel_manifest=manifest,
                contract_wired=effective_wired,
            )
        except Exception:
            panel = pd.DataFrame()

    panel_columns = frozenset(panel.columns) if not panel.empty else frozenset()

    records: Dict[str, CapabilityExposureRecord] = {}

    for proof in provenance_report.field_proofs.values():
        exp_key = f"expansion_audit:missing_panel_registry:{proof.field_name}"
        exp_entry = expansion_audit.entries.get(exp_key)
        fp_match = True
        if proof.field_name in manifest.approved_field_names:
            fp_match = proof.field_name in validated_approved
        rec = _record_from_proof(
            proof,
            expansion_entry=exp_entry,
            policy=pol,
            panel_columns=panel_columns,
            lifecycle_columns=lifecycle_columns,
            approved_manifest=effective_approved,
            wired_manifest=effective_wired,
            observation_horizon=observation_horizon,
            proof_version=provenance_report.version,
            approval_entries=entries,
            fingerprint_match=fp_match,
        )
        records[rec.capability_id] = rec

    for source_id, field_name in _NEGATIVE_CONTROL_FIELDS:
        cap_id = f"expansion_audit:{source_id}:{field_name}"
        entry = expansion_audit.entries.get(cap_id)
        if entry is None:
            continue
        rec = _record_from_expansion_negative_control(
            entry,
            policy=pol,
            panel_columns=panel_columns,
            observation_horizon=observation_horizon,
        )
        records[rec.capability_id] = rec

    effective_stock = resolve_effective_stock_columns(manifest)
    if manifest.approved_field_names:
        expected = CORE_STOCK_PANEL_FIELDS | (
            effective_wired - CORE_STOCK_PANEL_FIELDS
        )
        if effective_stock != expected and effective_wired:
            raise ValueError("WIRED_MANIFEST_PANEL_MISMATCH")

    policy_label = (
        "PHASE_3H2B_FIRST_CONTROLLED_EXPOSURE"
        if manifest.approved_field_names
        else "BUILD_DOOR_DO_NOT_OPEN"
    )

    return ResearchExposureContract(
        built_at=_utc_now(),
        policy=pol,
        records=records,
        panel_manifest=manifest,
        approval_entries=tuple(entries),
        observation_horizon=observation_horizon,
        audit_trail=[
            {
                "event": "EXPOSURE_CONTRACT_BUILT",
                "timestamp": _utc_now(),
                "record_count": len(records),
                "eligible_count": sum(1 for r in records.values() if r.eligible_for_exposure),
                "approved_count": sum(1 for r in records.values() if r.approved_for_exposure),
                "accessible_count": sum(1 for r in records.values() if r.research_accessible_now),
                "policy": policy_label,
            }
        ],
    )


def enrich_capability_registry_observational(
    capability_registry: Any,
    exposure_contract: ResearchExposureContract,
) -> Dict[str, Any]:
    """
    Observational overlay — does NOT mutate ResearchCapabilityRegistry.
    """
    overlay: Dict[str, Any] = {}
    for cap_id, cap in capability_registry.capabilities.items():
        exposure_records = [
            r
            for r in exposure_contract.records.values()
            if r.field_name == cap.name
        ]
        if not exposure_records:
            continue
        rec = exposure_records[0]
        overlay[cap_id] = {
            "exists_in_system": rec.exists_in_system,
            "scientifically_safe": rec.scientifically_safe,
            "eligible_for_exposure": rec.eligible_for_exposure,
            "approved_for_exposure": rec.approved_for_exposure,
            "wired_to_panel": rec.wired_to_panel,
            "research_accessible_now": rec.research_accessible_now,
            "temporally_legal_at_horizon": rec.temporally_legal_at_horizon,
            "exposure_blockers": list(rec.blockers),
            "provenance_fingerprint": rec.provenance_fingerprint,
            "exercised_by_researcher": rec.exercised_by_researcher,
        }
    return overlay


def record_exposure_exercise(
    contract: ResearchExposureContract,
    field_name: str,
    experiment_node_id: str,
) -> bool:
    """
    Mark EXERCISED_BY_RESEARCHER only after canonical executed experiment uses field.
    """
    cap_id = f"exposure:{field_name}"
    rec = contract.records.get(cap_id)
    if rec is None or not rec.research_accessible_now:
        return False
    if rec.exercised_by_researcher:
        return False

    event = {
        "event": "EXERCISED_BY_RESEARCHER",
        "timestamp": _utc_now(),
        "experiment_node_id": experiment_node_id,
        "field_name": field_name,
        "lifecycle_event": "EXECUTED",
    }
    updated = CapabilityExposureRecord(
        capability_id=rec.capability_id,
        field_name=rec.field_name,
        source_id=rec.source_id,
        provenance_proof_id=rec.provenance_proof_id,
        provenance_classification=rec.provenance_classification,
        proof_confidence=rec.proof_confidence,
        point_in_time_reconstructable=rec.point_in_time_reconstructable,
        future_dependency_detected=rec.future_dependency_detected,
        outcome_dependency_detected=rec.outcome_dependency_detected,
        retrospective_dependency_detected=rec.retrospective_dependency_detected,
        revision_risk=rec.revision_risk,
        earliest_availability_horizon=rec.earliest_availability_horizon,
        scientific_safety_status=rec.scientific_safety_status,
        exists_in_system=rec.exists_in_system,
        provenance_audited=rec.provenance_audited,
        scientifically_safe=rec.scientifically_safe,
        eligible_for_exposure=rec.eligible_for_exposure,
        eligibility_reason=rec.eligibility_reason,
        approved_for_exposure=rec.approved_for_exposure,
        approval_source=rec.approval_source,
        wired_to_panel=rec.wired_to_panel,
        research_accessible_now=rec.research_accessible_now,
        temporally_legal_at_horizon=rec.temporally_legal_at_horizon,
        exercised_by_researcher=True,
        blockers=rec.blockers,
        exposure_version=rec.exposure_version,
        provenance_fingerprint=rec.provenance_fingerprint,
        proof_version=rec.proof_version,
        policy_version=rec.policy_version,
        audit_history=rec.audit_history + (event,),
    )
    contract.records[cap_id] = updated
    contract.audit_trail.append(dict(event))
    return True


def is_field_governance_accessible(
    contract: ResearchExposureContract,
    field_name: str,
) -> bool:
    rec = contract.records.get(f"exposure:{field_name}")
    return rec is not None and rec.research_accessible_now


def extract_experiment_feature_fields(spec: Any) -> Tuple[str, ...]:
    """Canonical feature fields referenced by an experiment spec."""
    if spec is None:
        return ()
    inputs = dict(getattr(spec, "inputs", None) or {})
    fields: List[str] = []
    for key in ("feature_column", "partition_column"):
        val = inputs.get(key)
        if val:
            fields.append(str(val))
    return tuple(fields)


def record_experiment_exposure_exercises(
    contract: ResearchExposureContract,
    spec: Any,
    experiment_node_id: str,
) -> Tuple[str, ...]:
    """Record exposure exercise for governance-accessible fields in spec."""
    exercised: List[str] = []
    for fld in extract_experiment_feature_fields(spec):
        if record_exposure_exercise(contract, fld, experiment_node_id):
            exercised.append(fld)
    return tuple(exercised)


def represent_future_approval(
    record: CapabilityExposureRecord,
    *,
    approval_source: str,
    approved_at: str,
) -> Dict[str, Any]:
    """
    Represent explicit approval mechanism for 3H.2B — NOT enabled in 3H.2A.
    Returns a dict describing what approval would require without applying it.
    """
    return {
        "field_name": record.field_name,
        "currently_eligible": record.eligible_for_exposure,
        "would_require": [
            "eligible_for_exposure=true",
            f"approval_source={approval_source}",
            "panel_manifest.approved_field_names includes field",
            "panel_manifest.wired_field_names includes field",
            "source column present in lifecycle",
            "provenance_fingerprint valid",
            f"approved_at={approved_at}",
        ],
        "phase_3h2a_enabled": False,
    }


def ensure_session_exposure_contract(graph: Any) -> ResearchExposureContract:
    """Build or reload exposure contract on session — observational only."""
    if graph.session.research_exposure_contract:
        contract = ResearchExposureContract.from_dict(graph.session.research_exposure_contract)
        graph._exposure_contract = contract  # noqa: SLF001
        return contract
    contract = build_research_exposure_contract()
    graph.session.research_exposure_contract = contract.to_dict()
    graph._exposure_contract = contract  # noqa: SLF001
    return contract


def persist_exposure_contract(graph: Any) -> None:
    if getattr(graph, "_exposure_contract", None) is not None:
        graph.session.research_exposure_contract = graph._exposure_contract.to_dict()
