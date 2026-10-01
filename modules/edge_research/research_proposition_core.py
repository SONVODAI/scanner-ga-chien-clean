"""
Phase 3H.12 — Canonical scientific proposition core.

Separates the scientific question ("what uncertainty would this experiment resolve?")
from experimental representation (tool, action, frame, instrument feature column).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

RESEARCH_PROPOSITION_CORE_VERSION = "research_proposition_core_v1"


def _stable_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def uncertainty_family(codes: Tuple[str, ...]) -> str:
    """Normalize uncertainty codes to a stable family string."""
    if not codes:
        return "UNSPECIFIED"
    families = []
    for c in codes:
        cu = str(c).upper()
        if "HORIZON" in cu:
            families.append("HORIZON")
        elif cu in (
            "EPISODE_REPLICATION",
            "TIME_DISTRIBUTION",
            "SYMBOL_DISTRIBUTION",
            "MARKET_DEPENDENCE",
        ):
            families.append("DISTRIBUTION_ROBUSTNESS")
        elif "EXTREME" in cu or "FALSIF" in cu:
            families.append("FALSIFICATION")
        elif "STABILITY" in cu or "HETEROG" in cu:
            families.append("HORIZON")
        else:
            families.append(cu[:32])
    return "|".join(sorted(set(families)))


@dataclass(frozen=True)
class RepresentationEnvelope:
    """Experimental representation — never sufficient alone for proposition sameness."""

    tool_name: str = ""
    action_id: str = ""
    frame_id: str = ""
    action_code: str = ""
    instrument_features: Tuple[str, ...] = ()
    execution_mechanism: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "action_id": self.action_id,
            "frame_id": self.frame_id,
            "action_code": self.action_code,
            "instrument_features": list(self.instrument_features),
            "execution_mechanism": self.execution_mechanism,
        }


@dataclass(frozen=True)
class CanonicalPropositionCore:
    """
    Minimal auditable representation of the scientific question under test.

    Excludes tool name, action id, and instrument partition columns from the core key.
    """

    version: str
    population_spec: Dict[str, Any]
    outcome_spec: Dict[str, Any]
    observation_horizon: int
    uncertainty_family: str
    conditioning_context: Dict[str, Any]
    research_needs: Tuple[str, ...] = ()
    completeness: str = "COMPLETE"
    enrichment_sources: Tuple[str, ...] = ()

    def scientific_question_key(self) -> str:
        """Stable key from scientific content only."""
        pop_hash = _stable_hash(self.population_spec) if self.population_spec else "_"
        out_hash = _stable_hash(self.outcome_spec) if self.outcome_spec else "_"
        cond_hash = _stable_hash(self.conditioning_context) if self.conditioning_context else "_"
        needs_part = _stable_hash({"needs": list(self.research_needs)}) if self.research_needs else "_"
        return (
            f"q-{self.uncertainty_family[:20]}-{self.observation_horizon}-"
            f"{pop_hash}-{out_hash}-{cond_hash}-{needs_part}"
        )

    def has_minimal_semantics(self) -> bool:
        """True when enough fields exist to compare propositions safely."""
        has_pop = bool(self.population_spec)
        has_out = bool(self.outcome_spec)
        has_unc = self.uncertainty_family != "UNSPECIFIED"
        return (has_pop and has_out) or (has_pop and has_unc) or (has_out and has_unc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "population_spec": dict(self.population_spec),
            "outcome_spec": dict(self.outcome_spec),
            "observation_horizon": self.observation_horizon,
            "uncertainty_family": self.uncertainty_family,
            "conditioning_context": dict(self.conditioning_context),
            "research_needs": list(self.research_needs),
            "completeness": self.completeness,
            "enrichment_sources": list(self.enrichment_sources),
            "scientific_question_key": self.scientific_question_key(),
        }


def _extract_instrument_features(inputs: Dict[str, Any]) -> Tuple[str, ...]:
    keys = (
        "feature_column",
        "partition_column",
        "trajectory_feature",
        "primary_feature",
        "slice_column",
        "threshold_column",
    )
    return tuple(sorted(str(inputs[k]) for k in keys if k in inputs and inputs[k]))


def _merge_scope_specs(scope: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], int, Dict[str, Any]]:
    """Normalize population/outcome/horizon/conditioning from scope + pending_question_context."""
    pending = scope.get("pending_question_context") or {}
    pop = dict(scope.get("population_spec") or pending.get("population_spec") or {})
    out = dict(scope.get("outcome_spec") or pending.get("outcome_spec") or {})
    horizon = int(pending.get("observation_horizon") or scope.get("observation_horizon") or 0)
    conditioning = dict(scope.get("conditioning_context") or pending.get("conditioning_context") or {})
    return pop, out, horizon, conditioning


def enrich_scope_from_branch_context(
    graph: Any,
    *,
    branch_root_id: str = "",
    pop: Dict[str, Any],
    out: Dict[str, Any],
    horizon: int,
    conditioning: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], int, Dict[str, Any], Tuple[str, ...]]:
    """
    Fill missing semantic fields from auditable branch context already in the graph.

    Does NOT fabricate semantics — only propagates existing experiment scope.
    """
    sources = []
    if not graph or not branch_root_id:
        return pop, out, horizon, conditioning, tuple(sources)

    node = graph.nodes.get(branch_root_id) if hasattr(graph, "nodes") else None
    if node is None and hasattr(graph, "get_node"):
        try:
            node = graph.get_node(branch_root_id)
        except Exception:
            node = None
    if node is None or not getattr(node, "experiment_spec", None):
        return pop, out, horizon, conditioning, tuple(sources)

    scope = getattr(node.experiment_spec, "research_scope", None) or {}
    pending = scope.get("pending_question_context") or {}

    if not pop and (scope.get("population_spec") or pending.get("population_spec")):
        pop = dict(scope.get("population_spec") or pending.get("population_spec") or {})
        sources.append("branch_root.population_spec")
    if not out and (scope.get("outcome_spec") or pending.get("outcome_spec")):
        out = dict(scope.get("outcome_spec") or pending.get("outcome_spec") or {})
        sources.append("branch_root.outcome_spec")
    if horizon == 0 and pending.get("observation_horizon"):
        horizon = int(pending.get("observation_horizon") or 0)
        sources.append("branch_root.observation_horizon")
    if not conditioning and (scope.get("conditioning_context") or pending.get("conditioning_context")):
        conditioning = dict(scope.get("conditioning_context") or pending.get("conditioning_context") or {})
        sources.append("branch_root.conditioning_context")

    return pop, out, horizon, conditioning, tuple(sources)


def build_canonical_proposition_core(
    *,
    population_spec: Dict[str, Any],
    outcome_spec: Dict[str, Any],
    observation_horizon: int = 0,
    uncertainty_codes: Tuple[str, ...] = (),
    research_needs: Tuple[str, ...] = (),
    conditioning_context: Optional[Dict[str, Any]] = None,
    enrichment_sources: Tuple[str, ...] = (),
) -> CanonicalPropositionCore:
    pop = dict(population_spec or {})
    out = dict(outcome_spec or {})
    cond = dict(conditioning_context or {})
    unc_fam = uncertainty_family(uncertainty_codes)

    completeness = "COMPLETE"
    if not pop and not out:
        completeness = "EMPTY"
    elif not pop or not out:
        completeness = "PARTIAL"

    return CanonicalPropositionCore(
        version=RESEARCH_PROPOSITION_CORE_VERSION,
        population_spec=pop,
        outcome_spec=out,
        observation_horizon=int(observation_horizon or 0),
        uncertainty_family=unc_fam,
        conditioning_context=cond,
        research_needs=tuple(research_needs or ()),
        completeness=completeness,
        enrichment_sources=tuple(enrichment_sources),
    )


def build_core_from_scope(
    scope: Dict[str, Any],
    *,
    uncertainty_codes: Tuple[str, ...] = (),
    research_needs: Tuple[str, ...] = (),
    graph: Any = None,
    branch_root_id: str = "",
) -> Tuple[CanonicalPropositionCore, RepresentationEnvelope, Tuple[str, ...]]:
    """Build core + representation envelope from a research_scope dict."""
    pop, out, horizon, conditioning = _merge_scope_specs(scope or {})
    pop, out, horizon, conditioning, enrich_src = enrich_scope_from_branch_context(
        graph,
        branch_root_id=branch_root_id,
        pop=pop,
        out=out,
        horizon=horizon,
        conditioning=conditioning,
    )
    core = build_canonical_proposition_core(
        population_spec=pop,
        outcome_spec=out,
        observation_horizon=horizon,
        uncertainty_codes=uncertainty_codes,
        research_needs=research_needs,
        conditioning_context=conditioning,
        enrichment_sources=enrich_src,
    )
    inputs = scope.get("inputs") or {}
    rep = RepresentationEnvelope(
        tool_name=str(scope.get("tool_name") or ""),
        frame_id=str((scope.get("pending_question_context") or {}).get("frame_id") or scope.get("frame_id") or ""),
        instrument_features=_extract_instrument_features(inputs),
        execution_mechanism=str(scope.get("frame_transformation") or ""),
    )
    return core, rep, enrich_src


def cores_same_question(a: CanonicalPropositionCore, b: CanonicalPropositionCore) -> bool:
    """True when two cores resolve the same scientific question."""
    if not a.has_minimal_semantics() or not b.has_minimal_semantics():
        return False
    pop_match = bool(a.population_spec) and a.population_spec == b.population_spec
    out_match = bool(a.outcome_spec) and a.outcome_spec == b.outcome_spec
    hor_match = a.observation_horizon == b.observation_horizon
    if pop_match and out_match and hor_match:
        a_unc = a.uncertainty_family not in ("UNSPECIFIED", "")
        b_unc = b.uncertainty_family not in ("UNSPECIFIED", "")
        if a_unc and b_unc and a.uncertainty_family != b.uncertainty_family:
            return False
        return True
    return a.scientific_question_key() == b.scientific_question_key()


def cores_materially_different(a: CanonicalPropositionCore, b: CanonicalPropositionCore) -> bool:
    """True when cores differ on outcome, population, horizon, or uncertainty family."""
    if (
        a.uncertainty_family != b.uncertainty_family
        and a.uncertainty_family != "UNSPECIFIED"
        and b.uncertainty_family != "UNSPECIFIED"
    ):
        return True
    if a.outcome_spec and b.outcome_spec and a.outcome_spec != b.outcome_spec:
        return True
    if a.population_spec and b.population_spec and a.population_spec != b.population_spec:
        return True
    if a.observation_horizon != b.observation_horizon and (a.observation_horizon or b.observation_horizon):
        return True
    return False


def instrument_features_materially_different(
    a: RepresentationEnvelope,
    b: RepresentationEnvelope,
) -> bool:
    """Different explanatory targets (not merely different tools)."""
    if not a.instrument_features or not b.instrument_features:
        return False
    return a.instrument_features != b.instrument_features
