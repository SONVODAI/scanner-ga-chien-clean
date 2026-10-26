"""
Phase 3H.10 — Semantic research-line identity.

Represents the scientific proposition under investigation — not tool/frame/action identity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.research_proposition_core import (
    RESEARCH_PROPOSITION_CORE_VERSION,
    RepresentationEnvelope,
    build_canonical_proposition_core,
    build_core_from_scope,
    enrich_scope_from_branch_context,
    uncertainty_family as _uncertainty_family_core,
)

RESEARCH_LINE_IDENTITY_VERSION = "research_line_identity_v2"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uncertainty_family(codes: Tuple[str, ...]) -> str:
    return _uncertainty_family_core(codes)

@dataclass(frozen=True)
class ResearchLineIdentity:
    """
    Auditable scientific proposition identity.

    Tool name, action_id, frontier_id, frame_id, branch_root_id are metadata only —
    never sufficient for identity equality.
    """

    version: str
    population_spec: Dict[str, Any]
    outcome_spec: Dict[str, Any]
    observation_horizon: int
    uncertainty_codes: Tuple[str, ...]
    research_needs: Tuple[str, ...]
    conditioning_context: Dict[str, Any]
    feature_slice: Tuple[str, ...]
    evidence_lineage: Tuple[str, ...]
    parent_proposition_key: str = ""
    canonical_core: Dict[str, Any] = field(default_factory=dict)
    representation: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    built_at: str = field(default_factory=_utc_now)

    def scientific_proposition_key(self) -> str:
        """Stable key from canonical scientific question (excludes instrument representation)."""
        if self.canonical_core and self.canonical_core.get("scientific_question_key"):
            return str(self.canonical_core["scientific_question_key"])
        core = build_canonical_proposition_core(
            population_spec=self.population_spec,
            outcome_spec=self.outcome_spec,
            observation_horizon=self.observation_horizon,
            uncertainty_codes=self.uncertainty_codes,
            research_needs=self.research_needs,
            conditioning_context=self.conditioning_context,
        )
        return core.scientific_question_key()

    def legacy_proposition_key(self) -> str:
        """Pre-3H.12 key including feature slice — for over-collapse audit only."""
        family = _uncertainty_family(self.uncertainty_codes)
        base = hashlib.sha256(
            json.dumps(
                {"pop": self.population_spec or {}, "out": self.outcome_spec or {}, "h": self.observation_horizon},
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]
        slice_part = hashlib.sha256(
            json.dumps(list(self.feature_slice), sort_keys=True).encode()
        ).hexdigest()[:8]
        return f"prop-{family[:24]}-{base}-{slice_part}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "population_spec": dict(self.population_spec),
            "outcome_spec": dict(self.outcome_spec),
            "observation_horizon": self.observation_horizon,
            "uncertainty_codes": list(self.uncertainty_codes),
            "research_needs": list(self.research_needs),
            "conditioning_context": dict(self.conditioning_context),
            "feature_slice": list(self.feature_slice),
            "evidence_lineage": list(self.evidence_lineage),
            "parent_proposition_key": self.parent_proposition_key,
            "scientific_proposition_key": self.scientific_proposition_key(),
            "legacy_proposition_key": self.legacy_proposition_key(),
            "canonical_core": dict(self.canonical_core),
            "representation": dict(self.representation),
            "metadata": dict(self.metadata),
            "built_at": self.built_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchLineIdentity":
        return cls(
            version=str(payload.get("version", RESEARCH_LINE_IDENTITY_VERSION)),
            population_spec=dict(payload.get("population_spec") or {}),
            outcome_spec=dict(payload.get("outcome_spec") or {}),
            observation_horizon=int(payload.get("observation_horizon", 0)),
            uncertainty_codes=tuple(payload.get("uncertainty_codes") or ()),
            research_needs=tuple(payload.get("research_needs") or ()),
            conditioning_context=dict(payload.get("conditioning_context") or {}),
            feature_slice=tuple(payload.get("feature_slice") or ()),
            evidence_lineage=tuple(payload.get("evidence_lineage") or ()),
            parent_proposition_key=str(payload.get("parent_proposition_key", "")),
            canonical_core=dict(payload.get("canonical_core") or {}),
            representation=dict(payload.get("representation") or {}),
            metadata=dict(payload.get("metadata") or {}),
            built_at=str(payload.get("built_at", _utc_now())),
        )


def _feature_slice_from_inputs(inputs: Dict[str, Any]) -> Tuple[str, ...]:
    keys = (
        "feature_column",
        "partition_column",
        "trajectory_feature",
        "primary_feature",
        "slice_column",
        "threshold_column",
    )
    return tuple(str(inputs[k]) for k in keys if k in inputs and inputs[k])


def _scope_specs(scope: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], int, Dict[str, Any]]:
    pending = scope.get("pending_question_context") or {}
    pop = dict(scope.get("population_spec") or pending.get("population_spec") or {})
    out = dict(scope.get("outcome_spec") or pending.get("outcome_spec") or {})
    horizon = int(pending.get("observation_horizon") or scope.get("observation_horizon") or 0)
    conditioning = dict(scope.get("conditioning_context") or pending.get("conditioning_context") or {})
    return pop, out, horizon, conditioning


def _build_identity(
    *,
    pop: Dict[str, Any],
    out: Dict[str, Any],
    horizon: int,
    conditioning: Dict[str, Any],
    uncertainty_codes: Tuple[str, ...],
    research_needs: Tuple[str, ...],
    feature_slice: Tuple[str, ...],
    evidence_lineage: Tuple[str, ...],
    metadata: Dict[str, Any],
    graph: Any = None,
    branch_root_id: str = "",
    scope_for_rep: Optional[Dict[str, Any]] = None,
) -> ResearchLineIdentity:
    enrich_src: Tuple[str, ...] = ()
    if graph and branch_root_id:
        pop, out, horizon, conditioning, enrich_src = enrich_scope_from_branch_context(
            graph,
            branch_root_id=branch_root_id,
            pop=pop,
            out=out,
            horizon=horizon,
            conditioning=conditioning,
        )
        if enrich_src:
            from modules.edge_research.research_line_identity import derive_identity_from_graph_experiment

            branch_ident = derive_identity_from_graph_experiment(graph, branch_root_id)
            if branch_ident and branch_ident.uncertainty_codes:
                uncertainty_codes = branch_ident.uncertainty_codes
    core = build_canonical_proposition_core(
        population_spec=pop,
        outcome_spec=out,
        observation_horizon=horizon,
        uncertainty_codes=uncertainty_codes,
        research_needs=research_needs,
        conditioning_context=conditioning,
        enrichment_sources=enrich_src,
    )
    rep_scope = dict(scope_for_rep or {})
    if metadata.get("tool_name"):
        rep_scope.setdefault("tool_name", metadata["tool_name"])
    rep = RepresentationEnvelope(
        tool_name=str(metadata.get("tool_name") or rep_scope.get("tool_name") or ""),
        action_id=str(metadata.get("action_id") or ""),
        frame_id=str(metadata.get("frame_id") or ""),
        action_code=str(metadata.get("action_code") or ""),
        instrument_features=feature_slice,
    )
    return ResearchLineIdentity(
        version=RESEARCH_LINE_IDENTITY_VERSION,
        population_spec=pop,
        outcome_spec=out,
        observation_horizon=horizon,
        uncertainty_codes=uncertainty_codes,
        research_needs=research_needs,
        conditioning_context=conditioning,
        feature_slice=feature_slice,
        evidence_lineage=evidence_lineage,
        canonical_core=core.to_dict(),
        representation=rep.to_dict(),
        metadata=metadata,
    )


def derive_identity_from_experiment_spec(
    *,
    experiment_spec: Any,
    uncertainty_codes: Tuple[str, ...] = (),
    research_needs: Tuple[str, ...] = (),
    evidence_lineage: Tuple[str, ...] = (),
    metadata: Optional[Dict[str, Any]] = None,
) -> ResearchLineIdentity:
    scope = getattr(experiment_spec, "research_scope", None) or {}
    inputs = getattr(experiment_spec, "inputs", None) or {}
    pop, out, horizon, conditioning = _scope_specs(scope)
    meta = dict(metadata or {})
    meta["tool_name"] = getattr(experiment_spec, "tool_name", "")
    return _build_identity(
        pop=pop,
        out=out,
        horizon=horizon,
        conditioning=conditioning,
        uncertainty_codes=uncertainty_codes,
        research_needs=research_needs,
        feature_slice=_feature_slice_from_inputs(inputs),
        evidence_lineage=evidence_lineage,
        metadata=meta,
        scope_for_rep={"tool_name": meta.get("tool_name", ""), "inputs": inputs},
    )


def derive_identity_from_candidate(
    candidate: Any,
    *,
    uncertainty_codes: Tuple[str, ...] = (),
    research_needs: Tuple[str, ...] = (),
    evidence_lineage: Tuple[str, ...] = (),
    graph: Any = None,
    branch_root_id: str = "",
) -> Optional[ResearchLineIdentity]:
    draft = getattr(candidate, "draft_spec", None)
    if draft is None:
        return None
    scope = getattr(draft, "research_scope", None) or {}
    inputs = getattr(draft, "inputs", None) or {}
    pop, out, horizon, conditioning = _scope_specs(scope)
    needs = research_needs or tuple(getattr(candidate, "rationale_codes", None) or ())
    unc = uncertainty_codes
    if not unc:
        ua = getattr(candidate, "uncertainty_addressed", None)
        if ua:
            unc = (str(ua),)
    meta = {
        "tool_name": getattr(candidate, "tool_name", "") or getattr(draft, "tool_name", ""),
        "action_id": getattr(candidate, "action_id", ""),
        "frame_id": getattr(candidate, "frame_id", ""),
        "action_code": getattr(candidate, "action_code", ""),
    }
    return _build_identity(
        pop=pop,
        out=out,
        horizon=horizon,
        conditioning=conditioning,
        uncertainty_codes=unc,
        research_needs=needs,
        feature_slice=_feature_slice_from_inputs(inputs),
        evidence_lineage=evidence_lineage,
        metadata=meta,
        graph=graph,
        branch_root_id=branch_root_id,
        scope_for_rep={"tool_name": meta.get("tool_name", ""), "inputs": inputs, **scope},
    )


def derive_identity_from_frontier_item(item: Any, *, graph: Any = None) -> ResearchLineIdentity:
    draft = getattr(item, "draft_spec", None) or {}
    inputs = draft.get("inputs") or {}
    scope = draft.get("research_scope") or {}
    pop = dict(getattr(item, "population_spec", None) or scope.get("population_spec") or {})
    out = dict(getattr(item, "outcome_spec", None) or scope.get("outcome_spec") or {})
    _, _, horizon, conditioning = _scope_specs(scope)
    if not pop and getattr(item, "population_spec", None):
        pop = dict(item.population_spec)
    if not out and getattr(item, "outcome_spec", None):
        out = dict(item.outcome_spec)
    meta = {
        "tool_name": draft.get("tool_name", ""),
        "action_id": getattr(item, "action_id", ""),
        "frame_id": getattr(item, "frame_id", ""),
        "frontier_id": getattr(item, "frontier_id", ""),
        "branch_root_id": getattr(item, "branch_root_id", ""),
    }
    branch_root = getattr(item, "branch_root_id", "") or meta.get("branch_root_id", "")
    return _build_identity(
        pop=pop,
        out=out,
        horizon=horizon,
        conditioning=conditioning,
        uncertainty_codes=(),
        research_needs=(),
        feature_slice=_feature_slice_from_inputs(inputs),
        evidence_lineage=(),
        metadata=meta,
        graph=graph,
        branch_root_id=branch_root,
        scope_for_rep=draft if isinstance(draft, dict) else {},
    )


def derive_identity_from_graph_experiment(graph: Any, experiment_node_id: str) -> Optional[ResearchLineIdentity]:
    node = graph.get_node(experiment_node_id)
    if not node or not node.experiment_spec:
        return None
    from modules.edge_research.research_assessment import ResearchAssessment

    assessment_payload = None
    snaps = getattr(graph.session, "experiment_assessment_snapshots", None) or {}
    if experiment_node_id in snaps:
        assessment_payload = snaps[experiment_node_id]
    unc: Tuple[str, ...] = ()
    if assessment_payload:
        gaps = assessment_payload.get("information_gaps") or []
        unc = tuple(str(g) for g in gaps[:3])
    return derive_identity_from_experiment_spec(
        experiment_spec=node.experiment_spec,
        uncertainty_codes=unc,
        evidence_lineage=(experiment_node_id,),
        metadata={"experiment_node_id": experiment_node_id},
    )
