"""
Phase 3I.17b — EvidenceDerivedCohortBinder.

Determines from pre-result evidence structure which legally expressible cohort
would provide genuinely new scientific information, or concludes none is defensible.

Causal order:
  uncertainty → required independence → candidate cohort semantics
  → overlap assessment → selection / silence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from modules.edge_research.opr_bridge.cohort_binding_records import (
    COHORT_BINDER_VERSION,
    CohortCandidateRecord,
    CohortRedundancy,
    CohortSelectionDisposition,
    build_cohort_candidate,
)
from modules.edge_research.opr_bridge.cohort_overlap_estimator import (
    PanelMetadataIndex,
    PriorCohortFingerprint,
    candidate_row_keys,
    derive_independence_from_overlap,
    estimate_overlap,
)
from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext
from modules.edge_research.opr_bridge.scientific_action_records import (
    ExecutabilityClass,
    RescueRiskClass,
    ScientificObjectiveRecord,
)
from modules.edge_research.research_grammar import ALLOWED_POPULATION_CATEGORICAL, GRAMMAR_VERSION

MIN_SAMPLE_DEFAULT = 30
MIN_SAMPLE_ABSTRACT = 3


@dataclass(frozen=True)
class CohortBindingResult:
    disposition: CohortSelectionDisposition
    candidates: Tuple[CohortCandidateRecord, ...]
    selected: Optional[CohortCandidateRecord]
    reason: str
    binder_version: str = COHORT_BINDER_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "candidate_count": len(self.candidates),
            "selected_cohort_id": self.selected.cohort_id if self.selected else None,
            "selected_semantic_hash": self.selected.cohort_semantic_hash if self.selected else None,
            "reason": self.reason,
            "binder_version": self.binder_version,
            "candidates": [c.to_dict() for c in self.candidates],
        }


def build_prior_fingerprints(
    ctx: ActionGenerationContext,
    panel: PanelMetadataIndex,
) -> List[PriorCohortFingerprint]:
    """Build prior cohort fingerprints from ledger + evidence specs (pre-result only)."""
    priors: List[PriorCohortFingerprint] = []
    spec_by_id = {s.get("evidence_id", s.get("experiment_id", "")): s for s in ctx.evidence_specs}

    for entry in ctx.ledger_entries:
        spec = spec_by_id.get(entry.evidence_id, {})
        pop_spec = _population_spec_from_evidence(entry, spec, ctx)
        keys = candidate_row_keys(panel, pop_spec)
        dates = {d for d, _ in keys}
        symbols = {s for _, s in keys}
        contexts = {panel.context_by_row.get(k, "UNKNOWN") for k in keys}
        priors.append(
            PriorCohortFingerprint(
                evidence_id=entry.evidence_id,
                row_keys=keys,
                dates=dates,
                symbols=symbols,
                contexts=contexts,
                population_semantics=entry.population_semantics,
                cohort_overlap_ratio=entry.cohort_overlap_ratio,
            )
        )
    return priors


def _population_spec_from_evidence(
    entry: Any,
    spec: Dict[str, Any],
    ctx: ActionGenerationContext,
) -> Dict[str, Any]:
    exp_spec = spec.get("experiment_spec") or spec.get("frozen_experiment_spec") or {}
    scope = exp_spec.get("research_scope") or {}
    if scope.get("population_spec"):
        return dict(scope["population_spec"])

    pop = entry.population_semantics
    cohort_scope = entry.cohort_episode_scope or spec.get("scope", "")

    if pop in ("holdout", "holdout_exclude_dates") or "holdout" in pop or "holdout" in cohort_scope:
        return {
            "kind": "filter",
            "field": "trade_date",
            "operator": "not_in",
            "values": list(ctx.motivating_dates),
            "grammar_version": GRAMMAR_VERSION,
        }
    if pop == "filtered_date_cohort":
        # Use authoritative experiment_spec when present (pre-result structure only)
        exp_spec = spec.get("experiment_spec") or {}
        scope = exp_spec.get("research_scope") or {}
        if scope.get("population_spec"):
            return dict(scope["population_spec"])
    if pop.startswith("subgroup_"):
        val = pop.replace("subgroup_", "")
        return {
            "kind": "filter",
            "field": "research_market_state",
            "operator": "in",
            "values": [val],
            "grammar_version": GRAMMAR_VERSION,
        }
    if pop in ("full", "full_universe"):
        return {"kind": "all", "grammar_version": GRAMMAR_VERSION}
    if pop.startswith("filtered_"):
        val = pop.split("_")[-1]
        field = spec.get("cohort_field", "research_market_state")
        return {
            "kind": "filter",
            "field": field if field != "context_state" else "research_market_state",
            "operator": "in",
            "values": [val],
            "grammar_version": GRAMMAR_VERSION,
        }
    if cohort_scope.endswith("_only") or "_only" in cohort_scope:
        val = cohort_scope.replace("_only", "").upper()
        if val.startswith("CTX"):
            return {
                "kind": "filter",
                "field": "research_market_state",
                "operator": "in",
                "values": [val],
                "grammar_version": GRAMMAR_VERSION,
            }
    return {"kind": "all", "grammar_version": GRAMMAR_VERSION}


def _discover_categorical_dimensions(panel: PanelMetadataIndex, ctx: ActionGenerationContext) -> List[str]:
    """Legal categorical dimensions observable in panel metadata."""
    cols = ctx.executability.panel_columns
    abstract = ctx.executability.abstract_mode
    dims: List[str] = []
    for field in sorted(ALLOWED_POPULATION_CATEGORICAL):
        if field in ("trade_date", "symbol"):
            continue
        if abstract and field == "research_market_state":
            dims.append("context_state")
        elif field in cols or (abstract and field == "research_market_state"):
            dims.append(field if not abstract else "context_state")
    if abstract and "context_state" not in dims:
        dims.append("context_state")
    return list(dict.fromkeys(dims))


def _distinct_values(panel: PanelMetadataIndex, field: str) -> List[str]:
    if field in ("context_state", "research_market_state"):
        return sorted(panel.contexts)
    if field == "symbol":
        return sorted(panel.symbols)
    if field == "trade_date":
        return sorted(panel.dates)
    return sorted(panel.contexts)


def _make_population_filter(field: str, value: str) -> Dict[str, Any]:
    mapped = "research_market_state" if field == "context_state" else field
    return {
        "kind": "filter",
        "field": mapped,
        "operator": "in",
        "values": [value],
        "grammar_version": GRAMMAR_VERSION,
    }


def _episode_holdout_spec(ctx: ActionGenerationContext) -> Dict[str, Any]:
    return {
        "kind": "filter",
        "field": "trade_date",
        "operator": "not_in",
        "values": list(ctx.motivating_dates),
        "grammar_version": GRAMMAR_VERSION,
    }


def _semantic_preservation_gate(
    population_spec: Dict[str, Any],
    ctx: ActionGenerationContext,
) -> Tuple[bool, str]:
    """Reject cohorts that mutate proposition semantics."""
    kind = population_spec.get("kind", "all")
    if kind in ("refine", "widen"):
        return False, "FORK_REQUIRED: population refine/widen mutates proposition claim"
    field = population_spec.get("field", "")
    prop_outcome = ctx.proposition_record.get("outcome", {})
    if isinstance(prop_outcome, dict):
        outcome_field = prop_outcome.get("field", "")
        if field == outcome_field:
            return False, "FORK_REQUIRED: cohort filter on outcome field"
    rel = ctx.proposition_record.get("explanatory_relation", {})
    feat = rel.get("feature_or_contrast") or ctx.proposition_record.get("feature", "")
    if field and str(field) == str(feat):
        return False, "FORK_REQUIRED: cohort filter on feature field changes hypothesis"
    return True, "PASS"


def _anti_rescue_gate(
    population_spec: Dict[str, Any],
    overlap_profile: Any,
    ctx: ActionGenerationContext,
    *,
    axis: str,
) -> Tuple[str, str]:
    """Detect rescue-like cohort selection intent."""
    if ctx.has_contradiction and overlap_profile.row_overlap_fraction < 0.3:
        if population_spec.get("kind") == "filter" and population_spec.get("operator") == "in":
            return RescueRiskClass.POPULATION_NARROWING.value, "Rescue: narrow subset after contradiction"
    if overlap_profile.overlaps_prior_falsification_cohort and overlap_profile.row_overlap_fraction > 0.85:
        return RescueRiskClass.POPULATION_NARROWING.value, "Rescue: overlaps prior falsification cohort"
    if axis == "population_robustness" and overlap_profile.max_prior_row_overlap > 0.9:
        return RescueRiskClass.POPULATION_NARROWING.value, "Rescue: high overlap with prior evidence"
    return RescueRiskClass.PASS.value, "No rescue pattern detected"


def _redundancy_status(overlap_profile: Any) -> str:
    if overlap_profile.row_overlap_fraction >= 0.92:
        return CohortRedundancy.REDUNDANT.value
    if overlap_profile.row_overlap_fraction >= 0.75:
        return CohortRedundancy.PARTIALLY_COVERED.value
    return CohortRedundancy.NOVEL.value


def _executability_status(
    population_spec: Dict[str, Any],
    sample_count: int,
    ctx: ActionGenerationContext,
    *,
    min_sample: int,
) -> str:
    if sample_count < min_sample:
        return ExecutabilityClass.INVALID.value
    field = population_spec.get("field", "")
    real_field = "research_market_state" if field == "context_state" else field
    if population_spec.get("kind") == "filter" and real_field == "research_market_state":
        if not ctx.executability.has_regime_column and not ctx.executability.abstract_mode:
            return ExecutabilityClass.SCIENTIFICALLY_VALID_NOT_EXECUTABLE.value
    if sample_count >= min_sample:
        return ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value
    return ExecutabilityClass.INVALID.value


def _generate_categorical_candidates(
    panel: PanelMetadataIndex,
    priors: List[PriorCohortFingerprint],
    ctx: ActionGenerationContext,
    objective: ScientificObjectiveRecord,
) -> List[CohortCandidateRecord]:
    candidates: List[CohortCandidateRecord] = []
    motivating = ctx.motivating_dates
    min_sample = ctx.executability.min_sample if not ctx.executability.abstract_mode else MIN_SAMPLE_ABSTRACT

    for dim in _discover_categorical_dimensions(panel, ctx):
        values = _distinct_values(panel, dim)
        if len(values) < 2:
            continue
        for val in values:
            pop_spec = _make_population_filter(dim, val)
            keys = candidate_row_keys(panel, pop_spec)
            overlap = estimate_overlap(keys, panel, priors, motivating_dates=motivating)
            indep = derive_independence_from_overlap(overlap, source_dimension=dim)
            sem_ok, sem_reason = _semantic_preservation_gate(pop_spec, ctx)
            rescue, rescue_reason = _anti_rescue_gate(pop_spec, overlap, ctx, axis=objective.target_uncertainty)
            if not sem_ok:
                rescue = "FORK_REQUIRED"
                rescue_reason = sem_reason
            exec_status = _executability_status(pop_spec, overlap.candidate_row_count, ctx, min_sample=min_sample)
            redundancy = _redundancy_status(overlap)
            rationale = (
                f"Categorical slice {dim}={val}; overlap={overlap.row_overlap_fraction:.3f}; "
                f"independence sample={indep.sample_independence}"
            )
            candidates.append(
                build_cohort_candidate(
                    cohort_semantic_definition=f"{dim} cohort value {val}",
                    source_dimension=dim,
                    population_spec=pop_spec,
                    derivation_provenance={
                        "source": "legal_categorical_dimension",
                        "dimension": dim,
                        "value": val,
                        "binder_version": COHORT_BINDER_VERSION,
                    },
                    relation_to_proposition_population="subset" if pop_spec.get("kind") == "filter" else "equivalent",
                    overlap_profile=overlap,
                    independence_profile=indep,
                    redundancy_status=redundancy,
                    rescue_risk_status=rescue,
                    executability_status=exec_status,
                    scientific_rationale=rationale,
                )
            )
        # Complementary partition candidate (full dimension contrast)
        if len(values) >= 2:
            for val in values:
                others = [v for v in values if v != val]
                pop_spec = {
                    "kind": "filter",
                    "field": "research_market_state" if dim == "context_state" else dim,
                    "operator": "in",
                    "values": others,
                    "grammar_version": GRAMMAR_VERSION,
                }
                keys = candidate_row_keys(panel, pop_spec)
                overlap = estimate_overlap(keys, panel, priors, motivating_dates=motivating)
                indep = derive_independence_from_overlap(overlap, source_dimension=f"{dim}_complement")
                sem_ok, sem_reason = _semantic_preservation_gate(pop_spec, ctx)
                rescue, _ = _anti_rescue_gate(pop_spec, overlap, ctx, axis=objective.target_uncertainty)
                if not sem_ok:
                    rescue = "FORK_REQUIRED"
                exec_status = _executability_status(pop_spec, overlap.candidate_row_count, ctx, min_sample=min_sample)
                candidates.append(
                    build_cohort_candidate(
                        cohort_semantic_definition=f"complement of {dim}={val} ({','.join(others)})",
                        source_dimension=f"{dim}_complement",
                        population_spec=pop_spec,
                        derivation_provenance={
                            "source": "complementary_partition",
                            "dimension": dim,
                            "excluded_value": val,
                            "binder_version": COHORT_BINDER_VERSION,
                        },
                        relation_to_proposition_population="complement_subset",
                        overlap_profile=overlap,
                        independence_profile=indep,
                        redundancy_status=_redundancy_status(overlap),
                        rescue_risk_status=rescue,
                        executability_status=exec_status,
                        scientific_rationale=f"Complementary partition excluding {val}; overlap={overlap.row_overlap_fraction:.3f}",
                    )
                )
    return candidates


def _generate_temporal_candidates(
    panel: PanelMetadataIndex,
    priors: List[PriorCohortFingerprint],
    ctx: ActionGenerationContext,
    objective: ScientificObjectiveRecord,
) -> List[CohortCandidateRecord]:
    if not ctx.motivating_dates:
        return []
    min_sample = ctx.executability.min_sample if not ctx.executability.abstract_mode else MIN_SAMPLE_ABSTRACT
    pop_spec = _episode_holdout_spec(ctx)
    keys = candidate_row_keys(panel, pop_spec)
    overlap = estimate_overlap(keys, panel, priors, motivating_dates=ctx.motivating_dates)
    indep = derive_independence_from_overlap(overlap, source_dimension="trade_date_holdout")
    rescue, _ = _anti_rescue_gate(pop_spec, overlap, ctx, axis=objective.target_uncertainty)
    exec_status = _executability_status(pop_spec, overlap.candidate_row_count, ctx, min_sample=min_sample)
    return [
        build_cohort_candidate(
            cohort_semantic_definition="episode holdout excluding motivating dates",
            source_dimension="trade_date",
            population_spec=pop_spec,
            derivation_provenance={
                "source": "motivating_date_exclusion",
                "motivating_dates": ",".join(ctx.motivating_dates),
                "binder_version": COHORT_BINDER_VERSION,
            },
            relation_to_proposition_population="holdout_subset",
            overlap_profile=overlap,
            independence_profile=indep,
            redundancy_status=_redundancy_status(overlap),
            rescue_risk_status=rescue,
            executability_status=exec_status,
            scientific_rationale=f"Temporal holdout; row_overlap={overlap.row_overlap_fraction:.3f}",
        )
    ]


def _rank_key(candidate: CohortCandidateRecord, objective: ScientificObjectiveRecord, *, min_sample: int = MIN_SAMPLE_ABSTRACT) -> Tuple:
    """Lexicographic scientific dominance — pre-registered, no tuned weights."""
    rescue_rank = 0 if candidate.rescue_risk_status == RescueRiskClass.PASS.value else 1
    fork_rank = 0 if candidate.rescue_risk_status != "FORK_REQUIRED" else 2
    redundant_rank = {"NOVEL": 0, "PARTIALLY_COVERED": 1, "REDUNDANT": 2}.get(candidate.redundancy_status, 2)
    indep = candidate.independence_profile
    req = set(objective.required_independence_characteristics)
    weak_penalty = 0
    for dim in req:
        val = getattr(indep, dim.replace("-", "_"), None) or indep.to_dict().get(dim, "UNKNOWN")
        if val in ("LOW", "NONE"):
            weak_penalty += 1
        elif val == "UNKNOWN":
            weak_penalty += 0.5
    overlap = candidate.overlap_profile.row_overlap_fraction
    sample_ok = 0 if candidate.expected_sample_coverage >= min_sample else 1
    exec_rank = 0 if candidate.executability_status == ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value else (
        1 if candidate.executability_status == ExecutabilityClass.SCIENTIFICALLY_VALID_NOT_EXECUTABLE.value else 2
    )
    semantic = 0 if indep.semantic_continuity in ("HIGH", "MEDIUM") else 1
    return (fork_rank, rescue_rank, redundant_rank, weak_penalty, semantic, overlap, sample_ok, exec_rank, candidate.cohort_semantic_hash)


def _select_candidate(candidates: Sequence[CohortCandidateRecord], objective: ScientificObjectiveRecord, *, min_sample: int = MIN_SAMPLE_ABSTRACT) -> CohortBindingResult:
    if not candidates:
        return CohortBindingResult(
            disposition=CohortSelectionDisposition.NO_DEFENSIBLE_COHORT,
            candidates=tuple(),
            selected=None,
            reason="No cohort candidates generated",
        )

    eligible = [
        c
        for c in candidates
        if c.rescue_risk_status == RescueRiskClass.PASS.value
        and c.redundancy_status != CohortRedundancy.REDUNDANT.value
        and c.executability_status != ExecutabilityClass.INVALID.value
    ]

    if not eligible:
        return CohortBindingResult(
            disposition=CohortSelectionDisposition.NO_DEFENSIBLE_COHORT,
            candidates=tuple(sorted(candidates, key=lambda c: _rank_key(c, objective, min_sample=min_sample))),
            selected=None,
            reason="All candidates rejected: redundant, rescue, fork, or insufficient sample",
        )

    ranked = sorted(eligible, key=lambda c: _rank_key(c, objective, min_sample=min_sample))
    best_key = _rank_key(ranked[0], objective, min_sample=min_sample)
    ties = [c for c in ranked if _rank_key(c, objective, min_sample=min_sample) == best_key]

    if len(ties) > 1:
        return CohortBindingResult(
            disposition=CohortSelectionDisposition.AMBIGUOUS_COHORT_SELECTION,
            candidates=tuple(sorted(candidates, key=lambda c: _rank_key(c, objective, min_sample=min_sample))),
            selected=None,
            reason=f"Ambiguous tie among {len(ties)} scientifically equivalent cohorts",
        )

    return CohortBindingResult(
        disposition=CohortSelectionDisposition.SELECTED,
        candidates=tuple(sorted(candidates, key=lambda c: _rank_key(c, objective, min_sample=min_sample))),
        selected=ranked[0],
        reason=f"Evidence-derived winner: {ranked[0].cohort_semantic_definition}",
    )


class EvidenceDerivedCohortBinder:
    """Minimal generic cohort binding from pre-result evidence structure."""

    def bind_for_axis(
        self,
        ctx: ActionGenerationContext,
        objective: ScientificObjectiveRecord,
        panel: PanelMetadataIndex,
        *,
        include_temporal: bool = True,
        include_categorical: bool = True,
    ) -> CohortBindingResult:
        priors = build_prior_fingerprints(ctx, panel)
        min_sample = ctx.executability.min_sample if not ctx.executability.abstract_mode else MIN_SAMPLE_ABSTRACT
        candidates: List[CohortCandidateRecord] = []
        if include_categorical:
            candidates.extend(_generate_categorical_candidates(panel, priors, ctx, objective))
        if include_temporal:
            candidates.extend(_generate_temporal_candidates(panel, priors, ctx, objective))
        return _select_candidate(candidates, objective, min_sample=min_sample)

    def bind_population_axis(
        self,
        ctx: ActionGenerationContext,
        objective: ScientificObjectiveRecord,
        panel: PanelMetadataIndex,
    ) -> CohortBindingResult:
        return self.bind_for_axis(ctx, objective, panel, include_temporal=False, include_categorical=True)

    def bind_temporal_axis(
        self,
        ctx: ActionGenerationContext,
        objective: ScientificObjectiveRecord,
        panel: PanelMetadataIndex,
    ) -> CohortBindingResult:
        return self.bind_for_axis(ctx, objective, panel, include_temporal=True, include_categorical=True)


def panel_from_context(ctx: ActionGenerationContext, fixture: Optional[Dict[str, Any]] = None) -> PanelMetadataIndex:
    """Resolve panel metadata index from fixture or real panel path."""
    if fixture is not None:
        return PanelMetadataIndex.from_abstract_fixture(fixture)
    import pandas as pd
    from pathlib import Path

    repo_panel = Path("benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv")
    if repo_panel.exists() and not ctx.executability.abstract_mode:
        df = pd.read_csv(repo_panel)
        cutoff = ctx.executability.data_cutoff
        return PanelMetadataIndex.from_dataframe(df, cutoff=cutoff)
    # Abstract fallback from executability context
    rows = []
    for i, d in enumerate(["2019-01-10", "2019-01-15", "2019-02-01", "2019-03-01", "2019-04-01"]):
        for j, sym in enumerate(["S1", "S2", "S3", "S4"]):
            for ctx_val in ["CTX_A", "CTX_B", "CTX_C"]:
                rows.append({"trade_date": d, "symbol": sym, "context_state": ctx_val})
    return PanelMetadataIndex.from_abstract_fixture({"rows": rows})
