"""
Phase 3H.10 — Auditable freshness evidence for revisits and frontier items.

ERV change alone is NOT freshness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.research_line_identity import ResearchLineIdentity

RESEARCH_LINE_FRESHNESS_VERSION = "research_line_freshness_v1"


class FreshnessClassification(str, Enum):
    FRESH_NEW_EVIDENCE = "FRESH_NEW_EVIDENCE"
    FRESH_NEW_HORIZON = "FRESH_NEW_HORIZON"
    FRESH_NEW_POPULATION = "FRESH_NEW_POPULATION"
    FRESH_NEW_OUTCOME = "FRESH_NEW_OUTCOME"
    FRESH_NEW_CONTEXT = "FRESH_NEW_CONTEXT"
    REVALUED_ONLY = "REVALUED_ONLY"
    SAME_EVIDENCE = "SAME_EVIDENCE"
    STALE = "STALE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class EvidenceSnapshot:
    """Frozen uncertainty/evidence state at defer or enqueue."""

    uncertainty_codes: Tuple[str, ...]
    observation_horizon: int
    population_spec: Dict[str, Any]
    outcome_spec: Dict[str, Any]
    conditioning_context: Dict[str, Any] = field(default_factory=dict)
    observation_count: int = 0
    data_horizon: int = 0
    planning_sequence: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uncertainty_codes": list(self.uncertainty_codes),
            "observation_horizon": self.observation_horizon,
            "population_spec": dict(self.population_spec),
            "outcome_spec": dict(self.outcome_spec),
            "conditioning_context": dict(self.conditioning_context),
            "observation_count": self.observation_count,
            "data_horizon": self.data_horizon,
            "planning_sequence": self.planning_sequence,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "EvidenceSnapshot":
        return cls(
            uncertainty_codes=tuple(payload.get("uncertainty_codes") or ()),
            observation_horizon=int(payload.get("observation_horizon", 0)),
            population_spec=dict(payload.get("population_spec") or {}),
            outcome_spec=dict(payload.get("outcome_spec") or {}),
            conditioning_context=dict(payload.get("conditioning_context") or {}),
            observation_count=int(payload.get("observation_count", 0)),
            data_horizon=int(payload.get("data_horizon", 0)),
            planning_sequence=int(payload.get("planning_sequence", 0)),
        )

    @classmethod
    def from_assessment(
        cls,
        assessment: Any,
        *,
        identity: Optional[ResearchLineIdentity] = None,
        planning_sequence: int = 0,
    ) -> "EvidenceSnapshot":
        unc = tuple(getattr(assessment, "unresolved_uncertainties", None) or ())
        gaps = tuple(getattr(assessment, "information_gaps", None) or ())
        merged = tuple(sorted(set(unc) | set(gaps)))
        pop: Dict[str, Any] = {}
        out: Dict[str, Any] = {}
        horizon = 0
        conditioning: Dict[str, Any] = {}
        if identity:
            pop = dict(identity.population_spec)
            out = dict(identity.outcome_spec)
            horizon = identity.observation_horizon
            conditioning = dict(identity.conditioning_context)
        obs_count = len(getattr(assessment, "branch_observation_codes", None) or ())
        return cls(
            uncertainty_codes=merged,
            observation_horizon=horizon,
            population_spec=pop,
            outcome_spec=out,
            conditioning_context=conditioning,
            observation_count=obs_count,
            planning_sequence=planning_sequence,
        )


@dataclass(frozen=True)
class FreshnessEvidence:
    version: str
    classification: str
    research_line_id: str
    evidence_added_since_last_attempt: bool
    uncertainty_changed_since_last_attempt: bool
    population_changed: bool
    outcome_changed: bool
    horizon_changed: bool
    conditioning_context_changed: bool
    new_observation_count: int
    prior_attempt_count: int
    prior_realized_gain: str
    last_attempt_sequence: int
    defer_snapshot: Optional[Dict[str, Any]]
    current_snapshot: Dict[str, Any]
    component_explanations: Dict[str, str]
    built_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "classification": self.classification,
            "research_line_id": self.research_line_id,
            "evidence_added_since_last_attempt": self.evidence_added_since_last_attempt,
            "uncertainty_changed_since_last_attempt": self.uncertainty_changed_since_last_attempt,
            "population_changed": self.population_changed,
            "outcome_changed": self.outcome_changed,
            "horizon_changed": self.horizon_changed,
            "conditioning_context_changed": self.conditioning_context_changed,
            "new_observation_count": self.new_observation_count,
            "prior_attempt_count": self.prior_attempt_count,
            "prior_realized_gain": self.prior_realized_gain,
            "last_attempt_sequence": self.last_attempt_sequence,
            "defer_snapshot": dict(self.defer_snapshot) if self.defer_snapshot else None,
            "current_snapshot": dict(self.current_snapshot),
            "component_explanations": dict(self.component_explanations),
            "built_at": self.built_at,
        }


def assess_freshness(
    *,
    identity: ResearchLineIdentity,
    research_line_id: str,
    defer_snapshot: Optional[EvidenceSnapshot],
    current_snapshot: EvidenceSnapshot,
    prior_attempt_count: int = 0,
    prior_realized_gain: str = "",
    last_attempt_sequence: int = 0,
    erv_changed_only: bool = False,
) -> FreshnessEvidence:
    """Classify revisit/frontier freshness from evidence deltas — not ERV alone."""
    explanations: Dict[str, str] = {}

    if defer_snapshot is None:
        return FreshnessEvidence(
            version=RESEARCH_LINE_FRESHNESS_VERSION,
            classification=FreshnessClassification.INSUFFICIENT_EVIDENCE.value,
            research_line_id=research_line_id,
            evidence_added_since_last_attempt=False,
            uncertainty_changed_since_last_attempt=False,
            population_changed=False,
            outcome_changed=False,
            horizon_changed=False,
            conditioning_context_changed=False,
            new_observation_count=0,
            prior_attempt_count=prior_attempt_count,
            prior_realized_gain=prior_realized_gain,
            last_attempt_sequence=last_attempt_sequence,
            defer_snapshot=None,
            current_snapshot=current_snapshot.to_dict(),
            component_explanations={"reason": "No defer snapshot — fail-closed freshness"},
        )

    unc_changed = defer_snapshot.uncertainty_codes != current_snapshot.uncertainty_codes
    pop_changed = defer_snapshot.population_spec != current_snapshot.population_spec
    out_changed = defer_snapshot.outcome_spec != current_snapshot.outcome_spec
    horizon_changed = defer_snapshot.observation_horizon != current_snapshot.observation_horizon
    cond_changed = defer_snapshot.conditioning_context != identity.conditioning_context
    new_obs = max(0, current_snapshot.observation_count - defer_snapshot.observation_count)
    evidence_added = new_obs > 0 or unc_changed

    if pop_changed:
        explanations["population"] = "Population spec changed since defer"
    if out_changed:
        explanations["outcome"] = "Outcome spec changed since defer"
    if horizon_changed:
        explanations["horizon"] = "Observation horizon changed since defer"
    if unc_changed:
        explanations["uncertainty"] = "Uncertainty state changed since defer"
    if new_obs > 0:
        explanations["observations"] = f"{new_obs} new observation codes since defer"

    classification = FreshnessClassification.INSUFFICIENT_EVIDENCE.value

    if evidence_added and unc_changed:
        classification = FreshnessClassification.FRESH_NEW_EVIDENCE.value
    elif horizon_changed:
        classification = FreshnessClassification.FRESH_NEW_HORIZON.value
    elif pop_changed:
        classification = FreshnessClassification.FRESH_NEW_POPULATION.value
    elif out_changed:
        classification = FreshnessClassification.FRESH_NEW_OUTCOME.value
    elif cond_changed:
        classification = FreshnessClassification.FRESH_NEW_CONTEXT.value
    elif erv_changed_only and not evidence_added:
        classification = FreshnessClassification.REVALUED_ONLY.value
        explanations["revalued_only"] = "ERV/revaluation changed without evidence delta"
    elif not evidence_added and prior_attempt_count > 0:
        classification = FreshnessClassification.STALE.value
        explanations["stale"] = "No material evidence change since prior attempt"
    elif not evidence_added:
        classification = FreshnessClassification.SAME_EVIDENCE.value
        explanations["same_evidence"] = "Evidence state unchanged"

    return FreshnessEvidence(
        version=RESEARCH_LINE_FRESHNESS_VERSION,
        classification=classification,
        research_line_id=research_line_id,
        evidence_added_since_last_attempt=evidence_added,
        uncertainty_changed_since_last_attempt=unc_changed,
        population_changed=pop_changed,
        outcome_changed=out_changed,
        horizon_changed=horizon_changed,
        conditioning_context_changed=cond_changed,
        new_observation_count=new_obs,
        prior_attempt_count=prior_attempt_count,
        prior_realized_gain=prior_realized_gain,
        last_attempt_sequence=last_attempt_sequence,
        defer_snapshot=defer_snapshot.to_dict(),
        current_snapshot=current_snapshot.to_dict(),
        component_explanations=explanations,
    )
