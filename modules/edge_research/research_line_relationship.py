"""
Phase 3H.10 — Component-explainable research-line relationships.

Promotes offline 3H.9 diagnosis into runtime-auditable classification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.research_line_identity import ResearchLineIdentity
from modules.edge_research.research_proposition_core import (
    CanonicalPropositionCore,
    RepresentationEnvelope,
    build_canonical_proposition_core,
    cores_materially_different,
    cores_same_question,
    instrument_features_materially_different,
)

RESEARCH_LINE_RELATIONSHIP_VERSION = "research_line_relationship_v2"


class ResearchLineRelationship(str, Enum):
    IDENTICAL = "IDENTICAL"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    SAME_QUESTION_DIFFERENT_INSTRUMENT = "SAME_QUESTION_DIFFERENT_INSTRUMENT"
    SAME_UNCERTAINTY_DIFFERENT_SLICE = "SAME_UNCERTAINTY_DIFFERENT_SLICE"
    SAME_LINE_NEW_EVIDENCE = "SAME_LINE_NEW_EVIDENCE"
    RELATED_BUT_DISTINCT = "RELATED_BUT_DISTINCT"
    GENUINELY_INDEPENDENT = "GENUINELY_INDEPENDENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class ResearchLineRelationshipAudit:
    version: str
    classification: str
    prior_line_id: str
    candidate_proposition_key: str
    prior_proposition_key: str
    component_evidence: Dict[str, Any]
    audit_questions: Dict[str, Any]
    built_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "classification": self.classification,
            "prior_line_id": self.prior_line_id,
            "candidate_proposition_key": self.candidate_proposition_key,
            "prior_proposition_key": self.prior_proposition_key,
            "component_evidence": dict(self.component_evidence),
            "audit_questions": dict(self.audit_questions),
            "built_at": self.built_at,
        }


def _core_from_identity(identity: ResearchLineIdentity) -> CanonicalPropositionCore:
    cached = identity.canonical_core or {}
    if cached.get("scientific_question_key"):
        return CanonicalPropositionCore(
            version=str(cached.get("version", "research_proposition_core_v1")),
            population_spec=dict(cached.get("population_spec") or identity.population_spec),
            outcome_spec=dict(cached.get("outcome_spec") or identity.outcome_spec),
            observation_horizon=int(cached.get("observation_horizon", identity.observation_horizon)),
            uncertainty_family=str(cached.get("uncertainty_family", "")),
            conditioning_context=dict(cached.get("conditioning_context") or identity.conditioning_context),
            research_needs=tuple(cached.get("research_needs") or identity.research_needs),
            completeness=str(cached.get("completeness", "COMPLETE")),
            enrichment_sources=tuple(cached.get("enrichment_sources") or ()),
        )
    return build_canonical_proposition_core(
        population_spec=identity.population_spec,
        outcome_spec=identity.outcome_spec,
        observation_horizon=identity.observation_horizon,
        uncertainty_codes=identity.uncertainty_codes,
        research_needs=identity.research_needs,
        conditioning_context=identity.conditioning_context,
    )


def _rep_from_identity(identity: ResearchLineIdentity) -> RepresentationEnvelope:
    cached = identity.representation or {}
    if cached:
        return RepresentationEnvelope(
            tool_name=str(cached.get("tool_name") or (identity.metadata or {}).get("tool_name", "")),
            action_id=str(cached.get("action_id") or (identity.metadata or {}).get("action_id", "")),
            frame_id=str(cached.get("frame_id") or (identity.metadata or {}).get("frame_id", "")),
            action_code=str(cached.get("action_code") or (identity.metadata or {}).get("action_code", "")),
            instrument_features=tuple(cached.get("instrument_features") or identity.feature_slice),
            execution_mechanism=str(cached.get("execution_mechanism") or ""),
        )
    return RepresentationEnvelope(
        tool_name=str((identity.metadata or {}).get("tool_name", "")),
        action_id=str((identity.metadata or {}).get("action_id", "")),
        frame_id=str((identity.metadata or {}).get("frame_id", "")),
        instrument_features=identity.feature_slice,
    )


def _same_population(a: ResearchLineIdentity, b: ResearchLineIdentity) -> bool:
    return bool(a.population_spec) and a.population_spec == b.population_spec


def _same_outcome(a: ResearchLineIdentity, b: ResearchLineIdentity) -> bool:
    return bool(a.outcome_spec) and a.outcome_spec == b.outcome_spec


def _same_horizon(a: ResearchLineIdentity, b: ResearchLineIdentity) -> bool:
    return a.observation_horizon == b.observation_horizon


def _same_uncertainty(a: ResearchLineIdentity, b: ResearchLineIdentity) -> bool:
    return bool(set(a.uncertainty_codes) & set(b.uncertainty_codes))


def _same_research_need(a: ResearchLineIdentity, b: ResearchLineIdentity) -> bool:
    return bool(set(a.research_needs) & set(b.research_needs))


def _same_conditioning(a: ResearchLineIdentity, b: ResearchLineIdentity) -> bool:
    if not a.conditioning_context and not b.conditioning_context:
        return True
    return bool(a.conditioning_context) and a.conditioning_context == b.conditioning_context


def _same_proposition(a: ResearchLineIdentity, b: ResearchLineIdentity) -> bool:
    return a.scientific_proposition_key() == b.scientific_proposition_key()


def _same_slice(a: ResearchLineIdentity, b: ResearchLineIdentity) -> bool:
    return bool(a.feature_slice) and a.feature_slice == b.feature_slice


def _same_tool_metadata(a: ResearchLineIdentity, b: ResearchLineIdentity) -> bool:
    ta = (a.metadata or {}).get("tool_name", "")
    tb = (b.metadata or {}).get("tool_name", "")
    return bool(ta) and ta == tb


def classify_research_line_relationship(
    prior: ResearchLineIdentity,
    candidate: ResearchLineIdentity,
    *,
    prior_line_id: str = "",
    new_evidence_available: bool = False,
) -> ResearchLineRelationshipAudit:
    """
    Component-explainable relationship — no opaque embedding scores.
    Fail-closed: insufficient evidence when components cannot justify sameness.
    """
    prior_core = _core_from_identity(prior)
    cand_core = _core_from_identity(candidate)
    prior_rep = _rep_from_identity(prior)
    cand_rep = _rep_from_identity(candidate)

    same_core = cores_same_question(prior_core, cand_core)
    same_pop = _same_population(prior, candidate)
    same_out = _same_outcome(prior, candidate)
    same_horizon = _same_horizon(prior, candidate)
    same_unc = _same_uncertainty(prior, candidate)
    same_need = _same_research_need(prior, candidate)
    same_cond = _same_conditioning(prior, candidate)
    same_prop = same_core or _same_proposition(prior, candidate)
    same_slice = _same_slice(prior, candidate)
    same_tool = _same_tool_metadata(prior, candidate)
    material_inst_diff = instrument_features_materially_different(prior_rep, cand_rep)
    material_core_diff = cores_materially_different(prior_core, cand_core)

    prior_action = (prior.metadata or {}).get("action_id", "")
    cand_action = (candidate.metadata or {}).get("action_id", "")
    same_action = bool(prior_action) and prior_action == cand_action

    component: Dict[str, Any] = {
        "same_canonical_core": same_core,
        "same_population": same_pop,
        "same_outcome": same_out,
        "same_horizon": same_horizon,
        "same_uncertainty": same_unc,
        "same_research_need": same_need,
        "same_conditioning_context": same_cond,
        "same_proposition": same_prop,
        "same_feature_slice": same_slice,
        "same_tool_metadata": same_tool,
        "same_action_id": same_action,
        "material_instrument_difference": material_inst_diff,
        "material_core_difference": material_core_diff,
        "prior_question_key": prior_core.scientific_question_key(),
        "candidate_question_key": cand_core.scientific_question_key(),
        "new_evidence_available": new_evidence_available,
    }

    audit_questions: Dict[str, Any] = {
        "same_canonical_core": same_core,
        "same_population": same_pop,
        "same_outcome": same_out,
        "same_horizon": same_horizon,
        "same_uncertainty": same_unc,
        "same_research_need": same_need,
        "same_conditioning_context": same_cond,
        "same_evidence_lineage": prior.evidence_lineage == candidate.evidence_lineage,
        "same_proposition": same_prop,
        "new_evidence_available": new_evidence_available,
        "could_resolve_prior_gap": new_evidence_available and same_unc,
        "core_completeness_prior": prior_core.completeness,
        "core_completeness_candidate": cand_core.completeness,
    }

    classification = ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value

    if not prior_core.has_minimal_semantics() or not cand_core.has_minimal_semantics():
        return ResearchLineRelationshipAudit(
            version=RESEARCH_LINE_RELATIONSHIP_VERSION,
            classification=classification,
            prior_line_id=prior_line_id,
            candidate_proposition_key=candidate.scientific_proposition_key(),
            prior_proposition_key=prior.scientific_proposition_key(),
            component_evidence=component,
            audit_questions=audit_questions,
        )

    if same_action and same_core:
        classification = ResearchLineRelationship.IDENTICAL.value
    elif same_core and same_tool and same_action:
        classification = ResearchLineRelationship.NEAR_DUPLICATE.value
    elif same_core and new_evidence_available:
        classification = ResearchLineRelationship.SAME_LINE_NEW_EVIDENCE.value
    elif same_core and material_inst_diff and same_unc:
        classification = ResearchLineRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value
    elif same_core and not same_tool:
        classification = ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value
    elif same_core and same_tool and not same_action:
        classification = ResearchLineRelationship.NEAR_DUPLICATE.value
    elif same_unc and material_inst_diff and same_out and same_pop and not same_core:
        classification = ResearchLineRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value
    elif material_core_diff and not same_unc:
        classification = ResearchLineRelationship.GENUINELY_INDEPENDENT.value
    elif not same_core and not same_unc and (same_out or same_pop):
        classification = ResearchLineRelationship.GENUINELY_INDEPENDENT.value
    elif same_unc and (same_out or same_pop) and not same_core:
        classification = ResearchLineRelationship.RELATED_BUT_DISTINCT.value
    elif material_core_diff:
        classification = ResearchLineRelationship.RELATED_BUT_DISTINCT.value

    return ResearchLineRelationshipAudit(
        version=RESEARCH_LINE_RELATIONSHIP_VERSION,
        classification=classification,
        prior_line_id=prior_line_id,
        candidate_proposition_key=candidate.scientific_proposition_key(),
        prior_proposition_key=prior.scientific_proposition_key(),
        component_evidence=component,
        audit_questions=audit_questions,
    )


def best_relationship_to_registry(
    candidate: ResearchLineIdentity,
    registry_lines: Dict[str, Dict[str, Any]],
    *,
    new_evidence_available: bool = False,
) -> Optional[ResearchLineRelationshipAudit]:
    """Find strongest auditable relationship against existing lines."""
    from modules.edge_research.research_line_identity import ResearchLineIdentity as RLI

    if not registry_lines:
        return None

    priority = {
        ResearchLineRelationship.IDENTICAL.value: 0,
        ResearchLineRelationship.NEAR_DUPLICATE.value: 1,
        ResearchLineRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value: 2,
        ResearchLineRelationship.SAME_LINE_NEW_EVIDENCE.value: 3,
        ResearchLineRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value: 4,
        ResearchLineRelationship.RELATED_BUT_DISTINCT.value: 5,
        ResearchLineRelationship.GENUINELY_INDEPENDENT.value: 6,
        ResearchLineRelationship.INSUFFICIENT_EVIDENCE.value: 7,
    }

    best: Optional[ResearchLineRelationshipAudit] = None
    for line_id, record in registry_lines.items():
        prior_payload = record.get("canonical_identity") or {}
        prior = RLI.from_dict(prior_payload)
        audit = classify_research_line_relationship(
            prior,
            candidate,
            prior_line_id=line_id,
            new_evidence_available=new_evidence_available,
        )
        if best is None or priority.get(audit.classification, 99) < priority.get(
            best.classification, 99
        ):
            best = audit
    return best
