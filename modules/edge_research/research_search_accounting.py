"""
Search accounting, complexity control, and scientific skepticism (Phase 3G).

Tracks cumulative search burden at session/branch/candidate levels.
Provides deterministic complexity scoring and evidence-vs-search assessment.
Research-only — no edge validation or production coupling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from modules.edge_research.research_grammar import (
    OutcomeSpec,
    PopulationSpec,
    build_search_accounting,
    parse_outcome_spec,
    parse_population_spec,
)
from modules.edge_research.research_state import (
    ExperimentSpec,
    NodeStatus,
    NodeType,
    ResearchNode,
)
from modules.edge_research.statistical_guardrails import screening_statistics_semantics

SEARCH_ACCOUNTING_VERSION = "search_accounting_v1"

# Deterministic complexity weights — NOT tuned against real benchmark.
WEIGHT_BRANCH_DEPTH = 2.0
WEIGHT_PREDICATE = 1.5
WEIGHT_OUTCOME_COMPLEXITY = 2.0
WEIGHT_POPULATION_COMPLEXITY = 2.0
WEIGHT_THRESHOLD_EXPLORED = 1.0
WEIGHT_FEATURE_EXPLORED = 1.0
WEIGHT_PARTITION_EVALUATED = 0.75
WEIGHT_INTERACTION_DEPTH = 3.0
WEIGHT_ALTERNATIVES = 0.5
WEIGHT_CATEGORICAL_LEVEL = 0.5
WEIGHT_NEIGHBORHOOD_CUT = 0.75
WEIGHT_REFINEMENT = 1.25

# Planner penalty scale — exploration value minus these terms.
COMPLEXITY_PENALTY_SCALE = 0.35
BRANCH_COMPLEXITY_PENALTY_SCALE = 0.25

# Skepticism escalation bonuses (falsification priority).
SKEPTICISM_HIGH_WINRATE = 3.0
SKEPTICISM_STRONG_THRESHOLD = 2.5
SKEPTICISM_COMPLEX_INTERACTION = 2.0
SKEPTICISM_REFINED_POPULATION = 2.0
SKEPTICISM_EXTREME_BIN = 2.5
SKEPTICISM_MANY_HYPOTHESES = 1.5

# Evidence thresholds for planner stop/abandon under high search burden.
WEAK_EVIDENCE_EFFECT_THRESHOLD = 0.05
HIGH_COMPLEXITY_THRESHOLD = 15.0
HIGH_SEARCH_CARDINALITY_THRESHOLD = 20


class ResearchStatus(str, Enum):
    EXPLORATORY = "EXPLORATORY"
    CANDIDATE_DISCOVERED = "CANDIDATE_DISCOVERED"
    NEEDS_FALSIFICATION = "NEEDS_FALSIFICATION"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    REJECTED = "REJECTED"
    ABANDONED = "ABANDONED"


class ConfirmationStatus(str, Enum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    PENDING = "PENDING"
    INDEPENDENT_CONFIRMED = "INDEPENDENT_CONFIRMED"
    SAME_SAMPLE_ONLY = "SAME_SAMPLE_ONLY"
    FAILED = "FAILED"


class DiscoveryEvidenceType(str, Enum):
    DISCOVERY = "DISCOVERY"
    SAME_SAMPLE_ROBUSTNESS = "SAME_SAMPLE_ROBUSTNESS"
    INDEPENDENT_CONFIRMATION = "INDEPENDENT_CONFIRMATION"


class EvidenceSearchAssessment(str, Enum):
    STRONG_RELATIVE_TO_SEARCH = "STRONG_RELATIVE_TO_SEARCH"
    MODERATE_RELATIVE_TO_SEARCH = "MODERATE_RELATIVE_TO_SEARCH"
    WEAK_RELATIVE_TO_SEARCH = "WEAK_RELATIVE_TO_SEARCH"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass
class SearchCountLedger:
    """Cumulative search counters — auditable raw components."""

    experiments_executed: int = 0
    questions_generated: int = 0
    candidate_actions_considered: int = 0
    unique_outcome_specs: Set[str] = field(default_factory=set)
    unique_population_specs: Set[str] = field(default_factory=set)
    unique_research_frames: Set[str] = field(default_factory=set)
    explanatory_features_tested: Set[str] = field(default_factory=set)
    partitions_evaluated: int = 0
    threshold_candidates_evaluated: int = 0
    neighborhood_cuts_evaluated: int = 0
    categorical_levels_evaluated: int = 0
    interactions_attempted: int = 0
    branch_depth_max: int = 0
    refinements_reframes: int = 0
    duplicate_experiments_blocked: int = 0
    abandoned_branches: int = 0
    falsification_experiments_executed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiments_executed": self.experiments_executed,
            "questions_generated": self.questions_generated,
            "candidate_actions_considered": self.candidate_actions_considered,
            "unique_outcome_specs": sorted(self.unique_outcome_specs),
            "unique_population_specs": sorted(self.unique_population_specs),
            "unique_research_frames": sorted(self.unique_research_frames),
            "explanatory_features_tested": sorted(self.explanatory_features_tested),
            "partitions_evaluated": self.partitions_evaluated,
            "threshold_candidates_evaluated": self.threshold_candidates_evaluated,
            "neighborhood_cuts_evaluated": self.neighborhood_cuts_evaluated,
            "categorical_levels_evaluated": self.categorical_levels_evaluated,
            "interactions_attempted": self.interactions_attempted,
            "branch_depth_max": self.branch_depth_max,
            "refinements_reframes": self.refinements_reframes,
            "duplicate_experiments_blocked": self.duplicate_experiments_blocked,
            "abandoned_branches": self.abandoned_branches,
            "falsification_experiments_executed": self.falsification_experiments_executed,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SearchCountLedger":
        return cls(
            experiments_executed=int(payload.get("experiments_executed", 0)),
            questions_generated=int(payload.get("questions_generated", 0)),
            candidate_actions_considered=int(payload.get("candidate_actions_considered", 0)),
            unique_outcome_specs=set(payload.get("unique_outcome_specs") or []),
            unique_population_specs=set(payload.get("unique_population_specs") or []),
            unique_research_frames=set(payload.get("unique_research_frames") or []),
            explanatory_features_tested=set(payload.get("explanatory_features_tested") or []),
            partitions_evaluated=int(payload.get("partitions_evaluated", 0)),
            threshold_candidates_evaluated=int(payload.get("threshold_candidates_evaluated", 0)),
            neighborhood_cuts_evaluated=int(payload.get("neighborhood_cuts_evaluated", 0)),
            categorical_levels_evaluated=int(payload.get("categorical_levels_evaluated", 0)),
            interactions_attempted=int(payload.get("interactions_attempted", 0)),
            branch_depth_max=int(payload.get("branch_depth_max", 0)),
            refinements_reframes=int(payload.get("refinements_reframes", 0)),
            duplicate_experiments_blocked=int(payload.get("duplicate_experiments_blocked", 0)),
            abandoned_branches=int(payload.get("abandoned_branches", 0)),
            falsification_experiments_executed=int(payload.get("falsification_experiments_executed", 0)),
        )

    def merge(self, other: "SearchCountLedger") -> None:
        self.experiments_executed += other.experiments_executed
        self.questions_generated += other.questions_generated
        self.candidate_actions_considered += other.candidate_actions_considered
        self.unique_outcome_specs |= other.unique_outcome_specs
        self.unique_population_specs |= other.unique_population_specs
        self.unique_research_frames |= other.unique_research_frames
        self.explanatory_features_tested |= other.explanatory_features_tested
        self.partitions_evaluated += other.partitions_evaluated
        self.threshold_candidates_evaluated += other.threshold_candidates_evaluated
        self.neighborhood_cuts_evaluated += other.neighborhood_cuts_evaluated
        self.categorical_levels_evaluated += other.categorical_levels_evaluated
        self.interactions_attempted += other.interactions_attempted
        self.branch_depth_max = max(self.branch_depth_max, other.branch_depth_max)
        self.refinements_reframes += other.refinements_reframes
        self.duplicate_experiments_blocked += other.duplicate_experiments_blocked
        self.abandoned_branches += other.abandoned_branches
        self.falsification_experiments_executed += other.falsification_experiments_executed


@dataclass(frozen=True)
class SearchComplexityScore:
    """Transparent deterministic complexity — raw components + aggregate."""

    branch_depth: int = 0
    predicate_count: int = 0
    outcome_complexity: int = 0
    population_complexity: int = 0
    thresholds_explored: int = 0
    features_explored: int = 0
    partitions_evaluated: int = 0
    interaction_depth: int = 0
    alternatives_considered: int = 0
    categorical_levels: int = 0
    neighborhood_cuts: int = 0
    refinements: int = 0
    aggregate_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch_depth": self.branch_depth,
            "predicate_count": self.predicate_count,
            "outcome_complexity": self.outcome_complexity,
            "population_complexity": self.population_complexity,
            "thresholds_explored": self.thresholds_explored,
            "features_explored": self.features_explored,
            "partitions_evaluated": self.partitions_evaluated,
            "interaction_depth": self.interaction_depth,
            "alternatives_considered": self.alternatives_considered,
            "categorical_levels": self.categorical_levels,
            "neighborhood_cuts": self.neighborhood_cuts,
            "refinements": self.refinements,
            "aggregate_score": self.aggregate_score,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SearchComplexityScore":
        return cls(
            branch_depth=int(payload.get("branch_depth", 0)),
            predicate_count=int(payload.get("predicate_count", 0)),
            outcome_complexity=int(payload.get("outcome_complexity", 0)),
            population_complexity=int(payload.get("population_complexity", 0)),
            thresholds_explored=int(payload.get("thresholds_explored", 0)),
            features_explored=int(payload.get("features_explored", 0)),
            partitions_evaluated=int(payload.get("partitions_evaluated", 0)),
            interaction_depth=int(payload.get("interaction_depth", 0)),
            alternatives_considered=int(payload.get("alternatives_considered", 0)),
            categorical_levels=int(payload.get("categorical_levels", 0)),
            neighborhood_cuts=int(payload.get("neighborhood_cuts", 0)),
            refinements=int(payload.get("refinements", 0)),
            aggregate_score=float(payload.get("aggregate_score", 0.0)),
        )


def compute_complexity_score(
    ledger: SearchCountLedger,
    *,
    branch_depth: int = 0,
    outcome_complexity: int = 0,
    population_complexity: int = 0,
    predicate_count: int = 0,
    alternatives_considered: int = 0,
) -> SearchComplexityScore:
    """
    Deterministic complexity score from ledger + spec metadata.

    Increases with deeper branches, more predicates, composite outcomes,
    refined populations, thresholds, features, interactions, and alternatives.
    """
    depth = max(branch_depth, ledger.branch_depth_max)
    oc = outcome_complexity or len(ledger.unique_outcome_specs)
    pc = population_complexity or len(ledger.unique_population_specs)
    pred = predicate_count or (oc + pc)
    features = len(ledger.explanatory_features_tested)
    interactions = ledger.interactions_attempted

    aggregate = (
        depth * WEIGHT_BRANCH_DEPTH
        + pred * WEIGHT_PREDICATE
        + oc * WEIGHT_OUTCOME_COMPLEXITY
        + pc * WEIGHT_POPULATION_COMPLEXITY
        + ledger.threshold_candidates_evaluated * WEIGHT_THRESHOLD_EXPLORED
        + features * WEIGHT_FEATURE_EXPLORED
        + ledger.partitions_evaluated * WEIGHT_PARTITION_EVALUATED
        + interactions * WEIGHT_INTERACTION_DEPTH
        + alternatives_considered * WEIGHT_ALTERNATIVES
        + ledger.categorical_levels_evaluated * WEIGHT_CATEGORICAL_LEVEL
        + ledger.neighborhood_cuts_evaluated * WEIGHT_NEIGHBORHOOD_CUT
        + ledger.refinements_reframes * WEIGHT_REFINEMENT
    )

    return SearchComplexityScore(
        branch_depth=depth,
        predicate_count=pred,
        outcome_complexity=oc,
        population_complexity=pc,
        thresholds_explored=ledger.threshold_candidates_evaluated,
        features_explored=features,
        partitions_evaluated=ledger.partitions_evaluated,
        interaction_depth=interactions,
        alternatives_considered=alternatives_considered,
        categorical_levels=ledger.categorical_levels_evaluated,
        neighborhood_cuts=ledger.neighborhood_cuts_evaluated,
        refinements=ledger.refinements_reframes,
        aggregate_score=round(aggregate, 4),
    )


@dataclass(frozen=True)
class MultipleHypothesisAccounting:
    """Honest multiple-hypothesis accounting — no false FDR precision for adaptive search."""

    effective_hypotheses_tested: int
    raw_p_value: Optional[float] = None
    raw_q_value: Optional[float] = None
    correction_applicable: bool = False
    correction_method: str = "NONE_ADAPTIVE_SEQUENTIAL"
    limitation_disclaimer: str = (
        "Adaptive sequential search invalidates naive batch FDR assumptions. "
        "Effective hypothesis count is a conservative audit estimate, not a "
        "formal false-discovery guarantee."
    )
    batch_fdr_semantics: Dict[str, Any] = field(default_factory=screening_statistics_semantics)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effective_hypotheses_tested": self.effective_hypotheses_tested,
            "raw_p_value": self.raw_p_value,
            "raw_q_value": self.raw_q_value,
            "correction_applicable": self.correction_applicable,
            "correction_method": self.correction_method,
            "limitation_disclaimer": self.limitation_disclaimer,
            "batch_fdr_semantics": dict(self.batch_fdr_semantics),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "MultipleHypothesisAccounting":
        return cls(
            effective_hypotheses_tested=int(payload.get("effective_hypotheses_tested", 0)),
            raw_p_value=payload.get("raw_p_value"),
            raw_q_value=payload.get("raw_q_value"),
            correction_applicable=bool(payload.get("correction_applicable", False)),
            correction_method=str(payload.get("correction_method", "NONE_ADAPTIVE_SEQUENTIAL")),
            limitation_disclaimer=str(payload.get("limitation_disclaimer", "")),
            batch_fdr_semantics=dict(payload.get("batch_fdr_semantics") or screening_statistics_semantics()),
        )


def compute_effective_hypotheses(ledger: SearchCountLedger) -> MultipleHypothesisAccounting:
    """
    Conservative effective hypothesis count from search ledger.

    Uses unique spec combinations × features × tool categories — not batch FDR.
    """
    n_outcomes = max(1, len(ledger.unique_outcome_specs))
    n_populations = max(1, len(ledger.unique_population_specs))
    n_features = max(1, len(ledger.explanatory_features_tested))
    n_thresholds = max(1, ledger.threshold_candidates_evaluated + 1)
    n_partitions = max(1, ledger.partitions_evaluated + 1)

    effective = (
        ledger.experiments_executed
        + ledger.candidate_actions_considered
        + n_outcomes * n_populations * n_features
        + ledger.interactions_attempted * 2
        + n_thresholds
        + n_partitions
        + ledger.refinements_reframes
    )

    return MultipleHypothesisAccounting(
        effective_hypotheses_tested=effective,
        correction_applicable=False,
        correction_method="NONE_ADAPTIVE_SEQUENTIAL",
    )


@dataclass(frozen=True)
class ConfirmationSplitMetadata:
    """Hook for chronological confirmation — no real split yet."""

    discovery_cutoff: Optional[str] = None
    discovery_date_range: Optional[Tuple[str, str]] = None
    confirmation_cutoff: Optional[str] = None
    confirmation_date_range: Optional[Tuple[str, str]] = None
    observations_overlap: Optional[bool] = None
    confirmation_independence_status: str = ConfirmationStatus.NOT_AVAILABLE.value
    confirmation_status: str = ConfirmationStatus.NOT_AVAILABLE.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "discovery_cutoff": self.discovery_cutoff,
            "discovery_date_range": list(self.discovery_date_range) if self.discovery_date_range else None,
            "confirmation_cutoff": self.confirmation_cutoff,
            "confirmation_date_range": (
                list(self.confirmation_date_range) if self.confirmation_date_range else None
            ),
            "observations_overlap": self.observations_overlap,
            "confirmation_independence_status": self.confirmation_independence_status,
            "confirmation_status": self.confirmation_status,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ConfirmationSplitMetadata":
        dr = payload.get("discovery_date_range")
        cr = payload.get("confirmation_date_range")
        return cls(
            discovery_cutoff=payload.get("discovery_cutoff"),
            discovery_date_range=tuple(dr) if dr else None,
            confirmation_cutoff=payload.get("confirmation_cutoff"),
            confirmation_date_range=tuple(cr) if cr else None,
            observations_overlap=payload.get("observations_overlap"),
            confirmation_independence_status=str(
                payload.get("confirmation_independence_status", ConfirmationStatus.NOT_AVAILABLE.value)
            ),
            confirmation_status=str(payload.get("confirmation_status", ConfirmationStatus.NOT_AVAILABLE.value)),
        )


@dataclass(frozen=True)
class ParentComparison:
    """Incremental gain vs simpler parent population/outcome."""

    parent_population_hash: str = ""
    parent_outcome_hash: str = ""
    parent_effect: Optional[float] = None
    candidate_effect: Optional[float] = None
    incremental_effect: Optional[float] = None
    parent_n: Optional[int] = None
    candidate_n: Optional[int] = None
    sample_loss: Optional[int] = None
    complexity_increase: float = 0.0
    incremental_warranted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parent_population_hash": self.parent_population_hash,
            "parent_outcome_hash": self.parent_outcome_hash,
            "parent_effect": self.parent_effect,
            "candidate_effect": self.candidate_effect,
            "incremental_effect": self.incremental_effect,
            "parent_n": self.parent_n,
            "candidate_n": self.candidate_n,
            "sample_loss": self.sample_loss,
            "complexity_increase": self.complexity_increase,
            "incremental_warranted": self.incremental_warranted,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ParentComparison":
        return cls(
            parent_population_hash=str(payload.get("parent_population_hash", "")),
            parent_outcome_hash=str(payload.get("parent_outcome_hash", "")),
            parent_effect=payload.get("parent_effect"),
            candidate_effect=payload.get("candidate_effect"),
            incremental_effect=payload.get("incremental_effect"),
            parent_n=payload.get("parent_n"),
            candidate_n=payload.get("candidate_n"),
            sample_loss=payload.get("sample_loss"),
            complexity_increase=float(payload.get("complexity_increase", 0.0)),
            incremental_warranted=bool(payload.get("incremental_warranted", False)),
        )


@dataclass(frozen=True)
class EvidenceBurdenRecord:
    """Evidence vs search burden — research prioritization only."""

    raw_effect: Optional[float] = None
    incremental_effect: Optional[float] = None
    sample_size: Optional[int] = None
    uncertainty: Optional[float] = None
    shape_strength: Optional[float] = None
    search_complexity: float = 0.0
    search_cardinality_preceding: int = 0
    concentration_flags: Tuple[str, ...] = field(default_factory=tuple)
    evidence_to_search_ratio: Optional[float] = None
    evidence_search_assessment: str = EvidenceSearchAssessment.INSUFFICIENT.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_effect": self.raw_effect,
            "incremental_effect": self.incremental_effect,
            "sample_size": self.sample_size,
            "uncertainty": self.uncertainty,
            "shape_strength": self.shape_strength,
            "search_complexity": self.search_complexity,
            "search_cardinality_preceding": self.search_cardinality_preceding,
            "concentration_flags": list(self.concentration_flags),
            "evidence_to_search_ratio": self.evidence_to_search_ratio,
            "evidence_search_assessment": self.evidence_search_assessment,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "EvidenceBurdenRecord":
        return cls(
            raw_effect=payload.get("raw_effect"),
            incremental_effect=payload.get("incremental_effect"),
            sample_size=payload.get("sample_size"),
            uncertainty=payload.get("uncertainty"),
            shape_strength=payload.get("shape_strength"),
            search_complexity=float(payload.get("search_complexity", 0.0)),
            search_cardinality_preceding=int(payload.get("search_cardinality_preceding", 0)),
            concentration_flags=tuple(payload.get("concentration_flags") or ()),
            evidence_to_search_ratio=payload.get("evidence_to_search_ratio"),
            evidence_search_assessment=str(
                payload.get("evidence_search_assessment", EvidenceSearchAssessment.INSUFFICIENT.value)
            ),
        )


def compute_evidence_burden(
    *,
    raw_effect: Optional[float],
    incremental_effect: Optional[float],
    sample_size: Optional[int],
    uncertainty: Optional[float],
    shape_strength: Optional[float],
    complexity: SearchComplexityScore,
    search_cardinality: int,
    concentration_flags: Sequence[str] = (),
) -> EvidenceBurdenRecord:
    """Compute evidence-to-search ratio and assessment."""
    effect = abs(incremental_effect if incremental_effect is not None else (raw_effect or 0.0))
    complexity_denom = max(1.0, complexity.aggregate_score)
    cardinality_denom = max(1, search_cardinality)
    ratio = effect / (complexity_denom * (1.0 + 0.01 * cardinality_denom))

    if effect < WEAK_EVIDENCE_EFFECT_THRESHOLD or (sample_size or 0) < 10:
        assessment = EvidenceSearchAssessment.INSUFFICIENT
    elif ratio >= 0.15 and effect >= 0.1:
        assessment = EvidenceSearchAssessment.STRONG_RELATIVE_TO_SEARCH
    elif ratio >= 0.05:
        assessment = EvidenceSearchAssessment.MODERATE_RELATIVE_TO_SEARCH
    else:
        assessment = EvidenceSearchAssessment.WEAK_RELATIVE_TO_SEARCH

    if concentration_flags:
        if assessment == EvidenceSearchAssessment.STRONG_RELATIVE_TO_SEARCH:
            assessment = EvidenceSearchAssessment.MODERATE_RELATIVE_TO_SEARCH
        elif assessment == EvidenceSearchAssessment.MODERATE_RELATIVE_TO_SEARCH:
            assessment = EvidenceSearchAssessment.WEAK_RELATIVE_TO_SEARCH

    return EvidenceBurdenRecord(
        raw_effect=raw_effect,
        incremental_effect=incremental_effect,
        sample_size=sample_size,
        uncertainty=uncertainty,
        shape_strength=shape_strength,
        search_complexity=complexity.aggregate_score,
        search_cardinality_preceding=search_cardinality,
        concentration_flags=tuple(concentration_flags),
        evidence_to_search_ratio=round(ratio, 6),
        evidence_search_assessment=assessment.value,
    )


@dataclass
class SearchAccountingState:
    """Session-level search accounting with branch snapshots."""

    version: str = SEARCH_ACCOUNTING_VERSION
    session_ledger: SearchCountLedger = field(default_factory=SearchCountLedger)
    branch_ledgers: Dict[str, SearchCountLedger] = field(default_factory=dict)
    candidate_summaries: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "session_ledger": self.session_ledger.to_dict(),
            "branch_ledgers": {k: v.to_dict() for k, v in sorted(self.branch_ledgers.items())},
            "candidate_summaries": dict(sorted(self.candidate_summaries.items())),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SearchAccountingState":
        branch_raw = payload.get("branch_ledgers") or {}
        return cls(
            version=str(payload.get("version", SEARCH_ACCOUNTING_VERSION)),
            session_ledger=SearchCountLedger.from_dict(payload.get("session_ledger") or {}),
            branch_ledgers={k: SearchCountLedger.from_dict(v) for k, v in branch_raw.items()},
            candidate_summaries=dict(payload.get("candidate_summaries") or {}),
        )

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def deserialize(cls, text: str) -> "SearchAccountingState":
        return cls.from_dict(json.loads(text))


@dataclass(frozen=True)
class CandidateResearchSummary:
    """Structured research-only summary for promising branches."""

    candidate_id: str
    population_spec: Dict[str, Any]
    outcome_spec: Dict[str, Any]
    conditions: Dict[str, Any] = field(default_factory=dict)
    raw_outcome_metric: Optional[float] = None
    parent_baseline: Optional[float] = None
    incremental_effect: Optional[float] = None
    n: Optional[int] = None
    dates: Tuple[str, ...] = field(default_factory=tuple)
    episodes: Tuple[str, ...] = field(default_factory=tuple)
    shape_evidence: Dict[str, Any] = field(default_factory=dict)
    threshold_neighborhood_evidence: Dict[str, Any] = field(default_factory=dict)
    concentration_evidence: Dict[str, Any] = field(default_factory=dict)
    search_accounting: Dict[str, Any] = field(default_factory=dict)
    complexity_score: Dict[str, Any] = field(default_factory=dict)
    effective_hypotheses_tested: int = 0
    discovery_evidence_type: str = DiscoveryEvidenceType.DISCOVERY.value
    confirmation_status: str = ConfirmationStatus.NOT_AVAILABLE.value
    confirmation_split: Optional[Dict[str, Any]] = None
    fragility_flags: Tuple[str, ...] = field(default_factory=tuple)
    current_research_status: str = ResearchStatus.EXPLORATORY.value
    why_interesting: str = ""
    why_not_validated: str = "Research-only; validated=False always in Phase 3G."
    next_required_test: str = ""
    parent_comparison: Optional[Dict[str, Any]] = None
    evidence_burden: Optional[Dict[str, Any]] = None
    lineage_discovery_vs_falsification: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "population_spec": dict(self.population_spec),
            "outcome_spec": dict(self.outcome_spec),
            "conditions": dict(self.conditions),
            "raw_outcome_metric": self.raw_outcome_metric,
            "parent_baseline": self.parent_baseline,
            "incremental_effect": self.incremental_effect,
            "n": self.n,
            "dates": list(self.dates),
            "episodes": list(self.episodes),
            "shape_evidence": dict(self.shape_evidence),
            "threshold_neighborhood_evidence": dict(self.threshold_neighborhood_evidence),
            "concentration_evidence": dict(self.concentration_evidence),
            "search_accounting": dict(self.search_accounting),
            "complexity_score": dict(self.complexity_score),
            "effective_hypotheses_tested": self.effective_hypotheses_tested,
            "discovery_evidence_type": self.discovery_evidence_type,
            "confirmation_status": self.confirmation_status,
            "confirmation_split": dict(self.confirmation_split) if self.confirmation_split else None,
            "fragility_flags": list(self.fragility_flags),
            "current_research_status": self.current_research_status,
            "why_interesting": self.why_interesting,
            "why_not_validated": self.why_not_validated,
            "next_required_test": self.next_required_test,
            "parent_comparison": dict(self.parent_comparison) if self.parent_comparison else None,
            "evidence_burden": dict(self.evidence_burden) if self.evidence_burden else None,
            "lineage_discovery_vs_falsification": list(self.lineage_discovery_vs_falsification),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CandidateResearchSummary":
        return cls(
            candidate_id=str(payload.get("candidate_id", "")),
            population_spec=dict(payload.get("population_spec") or {}),
            outcome_spec=dict(payload.get("outcome_spec") or {}),
            conditions=dict(payload.get("conditions") or {}),
            raw_outcome_metric=payload.get("raw_outcome_metric"),
            parent_baseline=payload.get("parent_baseline"),
            incremental_effect=payload.get("incremental_effect"),
            n=payload.get("n"),
            dates=tuple(payload.get("dates") or ()),
            episodes=tuple(payload.get("episodes") or ()),
            shape_evidence=dict(payload.get("shape_evidence") or {}),
            threshold_neighborhood_evidence=dict(payload.get("threshold_neighborhood_evidence") or {}),
            concentration_evidence=dict(payload.get("concentration_evidence") or {}),
            search_accounting=dict(payload.get("search_accounting") or {}),
            complexity_score=dict(payload.get("complexity_score") or {}),
            effective_hypotheses_tested=int(payload.get("effective_hypotheses_tested", 0)),
            discovery_evidence_type=str(
                payload.get("discovery_evidence_type", DiscoveryEvidenceType.DISCOVERY.value)
            ),
            confirmation_status=str(payload.get("confirmation_status", ConfirmationStatus.NOT_AVAILABLE.value)),
            confirmation_split=dict(payload.get("confirmation_split")) if payload.get("confirmation_split") else None,
            fragility_flags=tuple(payload.get("fragility_flags") or ()),
            current_research_status=str(payload.get("current_research_status", ResearchStatus.EXPLORATORY.value)),
            why_interesting=str(payload.get("why_interesting", "")),
            why_not_validated=str(payload.get("why_not_validated", "")),
            next_required_test=str(payload.get("next_required_test", "")),
            parent_comparison=dict(payload.get("parent_comparison")) if payload.get("parent_comparison") else None,
            evidence_burden=dict(payload.get("evidence_burden")) if payload.get("evidence_burden") else None,
            lineage_discovery_vs_falsification=tuple(payload.get("lineage_discovery_vs_falsification") or ()),
        )


# --- Tool classification for ledger updates ---

_PARTITION_TOOLS = frozenset(
    {
        "partition_group_compare",
        "adaptive_partition_compare",
        "trajectory_partition_compare",
        "categorical_adaptive_compare",
    }
)
_THRESHOLD_TOOLS = frozenset({"threshold_exploration"})
_NEIGHBORHOOD_TOOLS = frozenset({"threshold_neighborhood", "neighborhood_stability"})
_INTERACTION_TOOLS = frozenset({"interaction_partition"})
_FALSIFICATION_TOOLS = frozenset(
    {
        "date_decomposition",
        "symbol_decomposition",
        "sensitivity_analysis",
        "episode_decomposition",
    }
)
_REFRAME_INTENTS = frozenset({"REFRAME", "REPOPULATE", "REDESCRIBE_OUTCOME", "WIDEN"})


def _extract_feature_from_spec(spec: ExperimentSpec) -> Optional[str]:
    inputs = spec.inputs or {}
    for key in ("feature_column", "partition_column", "trajectory_feature"):
        if key in inputs:
            return str(inputs[key])
    return None


def _extract_specs_from_scope(scope: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    oh = scope.get("outcome_spec_hash") or scope.get("outcome_spec", {}).get("hash")
    ph = scope.get("population_spec_hash") or scope.get("population_spec", {}).get("hash")
    if not oh and scope.get("outcome_spec"):
        try:
            oh = parse_outcome_spec(scope["outcome_spec"]).content_hash()
        except Exception:
            pass
    if not ph and scope.get("population_spec"):
        try:
            ph = parse_population_spec(scope["population_spec"]).content_hash()
        except Exception:
            pass
    return oh, ph


def branch_root_id(graph: Any, node_id: str) -> str:
    """Find branch root (first question or observation in lineage)."""
    lineage = graph.reconstruct_lineage(node_id)
    for node in lineage:
        if node.node_type in (NodeType.QUESTION, NodeType.OBSERVATION):
            return node.node_id
    return node_id


def branch_depth(graph: Any, experiment_node_id: str) -> int:
    """Count experiment nodes in lineage."""
    return sum(
        1
        for n in graph.reconstruct_lineage(experiment_node_id)
        if n.node_type == NodeType.EXPERIMENT
    )


def lineage_step_roles(graph: Any, experiment_node_id: str) -> Tuple[str, ...]:
    """Classify lineage steps as discovery vs falsification."""
    roles: List[str] = []
    for node in graph.reconstruct_lineage(experiment_node_id):
        if node.node_type != NodeType.EXPERIMENT or not node.experiment_spec:
            continue
        tool = node.experiment_spec.tool_name
        if tool in _FALSIFICATION_TOOLS:
            roles.append("FALSIFICATION")
        elif node.rationale and node.rationale.reason_code in ("ABANDON_FRAGILE", "STOP"):
            roles.append("TERMINAL")
        else:
            roles.append("DISCOVERY")
    return tuple(roles)


def record_question_generated(state: SearchAccountingState, graph: Any, question_node_id: str) -> None:
    state.session_ledger.questions_generated += 1
    root = branch_root_id(graph, question_node_id)
    branch = state.branch_ledgers.setdefault(root, SearchCountLedger())
    branch.questions_generated += 1


def record_candidates_considered(
    state: SearchAccountingState,
    graph: Any,
    experiment_node_id: str,
    count: int,
) -> None:
    state.session_ledger.candidate_actions_considered += count
    root = branch_root_id(graph, experiment_node_id)
    branch = state.branch_ledgers.setdefault(root, SearchCountLedger())
    branch.candidate_actions_considered += count


def record_duplicate_blocked(state: SearchAccountingState, graph: Any, experiment_node_id: str) -> None:
    state.session_ledger.duplicate_experiments_blocked += 1
    root = branch_root_id(graph, experiment_node_id)
    branch = state.branch_ledgers.setdefault(root, SearchCountLedger())
    branch.duplicate_experiments_blocked += 1


def record_abandoned_branch(state: SearchAccountingState, graph: Any, node_id: str) -> None:
    state.session_ledger.abandoned_branches += 1
    root = branch_root_id(graph, node_id)
    branch = state.branch_ledgers.setdefault(root, SearchCountLedger())
    branch.abandoned_branches += 1


def _frame_id_from_experiment(graph: Any, experiment_node_id: str) -> Optional[str]:
    """Resolve research frame id from parent question context."""
    node = graph.get_node(experiment_node_id)
    for pid in node.parent_node_ids:
        parent = graph.get_node(pid)
        if parent.question_context and parent.question_context.frame_id:
            return parent.question_context.frame_id
    return None


def record_experiment_executed(
    state: SearchAccountingState,
    graph: Any,
    experiment_node_id: str,
    *,
    is_falsification: bool = False,
    is_reframe: bool = False,
) -> SearchCountLedger:
    """Update session and branch ledgers after an experiment completes."""
    node = graph.get_node(experiment_node_id)
    spec = node.experiment_spec
    root = branch_root_id(graph, experiment_node_id)
    depth = branch_depth(graph, experiment_node_id)

    session = state.session_ledger
    branch = state.branch_ledgers.setdefault(root, SearchCountLedger())

    session.experiments_executed += 1
    branch.experiments_executed += 1
    session.branch_depth_max = max(session.branch_depth_max, depth)
    branch.branch_depth_max = max(branch.branch_depth_max, depth)

    if is_falsification:
        session.falsification_experiments_executed += 1
        branch.falsification_experiments_executed += 1

    if spec:
        scope = spec.research_scope or {}
        if not is_reframe and scope.get("frame_transformation"):
            is_reframe = True
        oh, ph = _extract_specs_from_scope(scope)
        if oh:
            session.unique_outcome_specs.add(oh)
            branch.unique_outcome_specs.add(oh)
        if ph:
            session.unique_population_specs.add(ph)
            branch.unique_population_specs.add(ph)

        frame_id = _frame_id_from_experiment(graph, experiment_node_id)
        if frame_id:
            session.unique_research_frames.add(frame_id)
            branch.unique_research_frames.add(frame_id)

        if is_reframe:
            session.refinements_reframes += 1
            branch.refinements_reframes += 1

        feat = _extract_feature_from_spec(spec)
        if feat:
            session.explanatory_features_tested.add(feat)
            branch.explanatory_features_tested.add(feat)

        tool = spec.tool_name
        if tool in _PARTITION_TOOLS:
            session.partitions_evaluated += 1
            branch.partitions_evaluated += 1
            n_levels = spec.inputs.get("max_bins") or spec.inputs.get("n_levels") or 1
            session.categorical_levels_evaluated += int(n_levels)
            branch.categorical_levels_evaluated += int(n_levels)
        if tool in _THRESHOLD_TOOLS:
            n_thr = spec.inputs.get("n_thresholds") or spec.inputs.get("threshold_count") or 1
            session.threshold_candidates_evaluated += int(n_thr)
            branch.threshold_candidates_evaluated += int(n_thr)
        if tool in _NEIGHBORHOOD_TOOLS:
            session.neighborhood_cuts_evaluated += 1
            branch.neighborhood_cuts_evaluated += 1
        if tool in _INTERACTION_TOOLS:
            session.interactions_attempted += 1
            branch.interactions_attempted += 1
        if tool in _FALSIFICATION_TOOLS:
            session.falsification_experiments_executed += 1
            branch.falsification_experiments_executed += 1

    return branch


def infer_research_status(
    *,
    interesting: bool,
    fragility: Sequence[str],
    falsification_pending: bool,
    abandoned: bool = False,
    conditional_candidate: bool = True,
) -> str:
    if abandoned:
        return ResearchStatus.ABANDONED.value
    if fragility and not interesting:
        return ResearchStatus.REJECTED.value
    if interesting and falsification_pending:
        return ResearchStatus.NEEDS_FALSIFICATION.value
    if interesting and conditional_candidate:
        return ResearchStatus.CANDIDATE_DISCOVERED.value
    if interesting:
        return ResearchStatus.EXPLORATORY.value
    return ResearchStatus.EXPLORATORY.value


def build_parent_comparison(
    parent_pop: Optional[PopulationSpec],
    parent_outcome: Optional[OutcomeSpec],
    candidate_pop: PopulationSpec,
    candidate_outcome: OutcomeSpec,
    *,
    parent_effect: Optional[float],
    candidate_effect: Optional[float],
    parent_n: Optional[int],
    candidate_n: Optional[int],
) -> ParentComparison:
    inc = None
    if parent_effect is not None and candidate_effect is not None:
        inc = candidate_effect - parent_effect
    sample_loss = None
    if parent_n is not None and candidate_n is not None:
        sample_loss = parent_n - candidate_n
    parent_complexity = (parent_pop.complexity() if parent_pop else 0) + (
        parent_outcome.complexity() if parent_outcome else 0
    )
    cand_complexity = candidate_pop.complexity() + candidate_outcome.complexity()
    complexity_inc = cand_complexity - parent_complexity
    warranted = bool(inc is not None and inc > WEAK_EVIDENCE_EFFECT_THRESHOLD)
    return ParentComparison(
        parent_population_hash=parent_pop.content_hash() if parent_pop else "",
        parent_outcome_hash=parent_outcome.content_hash() if parent_outcome else "",
        parent_effect=parent_effect,
        candidate_effect=candidate_effect,
        incremental_effect=inc,
        parent_n=parent_n,
        candidate_n=candidate_n,
        sample_loss=sample_loss,
        complexity_increase=complexity_inc,
        incremental_warranted=warranted,
    )


def build_candidate_research_summary(
    *,
    candidate_id: str,
    population_spec: PopulationSpec,
    outcome_spec: OutcomeSpec,
    branch_ledger: SearchCountLedger,
    session_ledger: SearchCountLedger,
    metrics: Dict[str, Any],
    assessment_fragility: Sequence[str] = (),
    assessment_concentration: Sequence[str] = (),
    interesting: bool = False,
    conditional_candidate: bool = True,
    parent_comparison: Optional[ParentComparison] = None,
    confirmation_split: Optional[ConfirmationSplitMetadata] = None,
    lineage_roles: Sequence[str] = (),
    discovery_cutoff: Optional[str] = None,
) -> CandidateResearchSummary:
    """Build durable research-only candidate summary."""
    depth = branch_ledger.branch_depth_max
    oc = outcome_spec.complexity()
    pc = population_spec.complexity()
    complexity = compute_complexity_score(
        branch_ledger,
        branch_depth=depth,
        outcome_complexity=oc,
        population_complexity=pc,
        predicate_count=oc + pc,
    )
    mh = compute_effective_hypotheses(branch_ledger)
    raw_effect = metrics.get("best_group_success_rate") or metrics.get("success_rate")
    if raw_effect is None:
        raw_effect = metrics.get("incremental_median")
    parent_effect = parent_comparison.parent_effect if parent_comparison else None
    inc_effect = parent_comparison.incremental_effect if parent_comparison else None
    n = metrics.get("sample_size") or metrics.get("candidate_n")
    shape_ev = dict(metrics.get("shape") or {})
    threshold_ev = {
        k: metrics[k]
        for k in ("stability_class", "threshold", "neighborhood_width")
        if k in metrics
    }
    conc_ev = {k: metrics.get(k) for k in ("date_concentration", "symbol_concentration") if k in metrics}

    evidence = compute_evidence_burden(
        raw_effect=float(raw_effect) if raw_effect is not None else None,
        incremental_effect=float(inc_effect) if inc_effect is not None else None,
        sample_size=int(n) if n is not None else None,
        uncertainty=metrics.get("effect_spread"),
        shape_strength=shape_ev.get("strength"),
        complexity=complexity,
        search_cardinality=mh.effective_hypotheses_tested,
        concentration_flags=assessment_concentration,
    )

    fals_pending = bool(assessment_concentration or assessment_fragility)
    status = infer_research_status(
        interesting=interesting,
        fragility=assessment_fragility,
        falsification_pending=fals_pending and interesting,
        conditional_candidate=conditional_candidate,
    )

    next_test = ""
    if assessment_concentration:
        next_test = "Falsify date/symbol concentration"
    elif assessment_fragility:
        next_test = "Neighborhood or extreme-winner sensitivity"
    elif status == ResearchStatus.CANDIDATE_DISCOVERED.value:
        next_test = "Independent confirmation (not available in Phase 3G)"

    if confirmation_split is None:
        confirmation_split = ConfirmationSplitMetadata(
            discovery_cutoff=discovery_cutoff,
            confirmation_status=ConfirmationStatus.NOT_AVAILABLE.value,
        )

    why_interesting = ""
    if interesting:
        why_interesting = f"Descriptive group difference with effect={raw_effect}"

    return CandidateResearchSummary(
        candidate_id=candidate_id,
        population_spec=population_spec.to_dict(),
        outcome_spec=outcome_spec.to_dict(),
        conditions=dict(metrics.get("conditions") or {}),
        raw_outcome_metric=float(raw_effect) if raw_effect is not None else None,
        parent_baseline=parent_effect,
        incremental_effect=inc_effect,
        n=int(n) if n is not None else None,
        shape_evidence=shape_ev,
        threshold_neighborhood_evidence=threshold_ev,
        concentration_evidence={k: v for k, v in conc_ev.items() if v is not None},
        search_accounting={
            "session": session_ledger.to_dict(),
            "branch": branch_ledger.to_dict(),
        },
        complexity_score=complexity.to_dict(),
        effective_hypotheses_tested=mh.effective_hypotheses_tested,
        discovery_evidence_type=DiscoveryEvidenceType.DISCOVERY.value,
        confirmation_status=confirmation_split.confirmation_status,
        confirmation_split=confirmation_split.to_dict(),
        fragility_flags=tuple(assessment_fragility),
        current_research_status=status,
        why_interesting=why_interesting,
        next_required_test=next_test,
        parent_comparison=parent_comparison.to_dict() if parent_comparison else None,
        evidence_burden=evidence.to_dict(),
        lineage_discovery_vs_falsification=tuple(lineage_roles),
    )


def compute_planner_complexity_penalty(
    complexity: SearchComplexityScore,
    *,
    branch_depth: int = 0,
) -> Tuple[float, float]:
    """Return (search_complexity_penalty, branch_complexity_penalty)."""
    search_penalty = complexity.aggregate_score * COMPLEXITY_PENALTY_SCALE
    branch_penalty = branch_depth * WEIGHT_BRANCH_DEPTH * BRANCH_COMPLEXITY_PENALTY_SCALE
    return search_penalty, branch_penalty


def compute_skepticism_escalation(
    *,
    success_rate: Optional[float] = None,
    threshold_strength: Optional[float] = None,
    has_interaction: bool = False,
    population_refined: bool = False,
    extreme_bin: bool = False,
    effective_hypotheses: int = 0,
) -> Dict[str, float]:
    """
    Mandatory skepticism escalation — higher apparent strength → higher falsification priority.

    Generic — no encoded T3 behavior.
    """
    bonuses: Dict[str, float] = {}
    if success_rate is not None and success_rate >= 0.7:
        bonuses["skepticism_high_winrate"] = SKEPTICISM_HIGH_WINRATE
    if threshold_strength is not None and threshold_strength >= 0.5:
        bonuses["skepticism_strong_threshold"] = SKEPTICISM_STRONG_THRESHOLD
    if has_interaction:
        bonuses["skepticism_complex_interaction"] = SKEPTICISM_COMPLEX_INTERACTION
    if population_refined:
        bonuses["skepticism_refined_population"] = SKEPTICISM_REFINED_POPULATION
    if extreme_bin:
        bonuses["skepticism_extreme_bin"] = SKEPTICISM_EXTREME_BIN
    if effective_hypotheses >= HIGH_SEARCH_CARDINALITY_THRESHOLD:
        bonuses["skepticism_many_hypotheses"] = SKEPTICISM_MANY_HYPOTHESES
    return bonuses


def weak_evidence_high_complexity_should_stop(
    evidence: EvidenceBurdenRecord,
    complexity: SearchComplexityScore,
) -> bool:
    """Weak evidence + high complexity tends toward STOP/ABANDON."""
    if complexity.aggregate_score < HIGH_COMPLEXITY_THRESHOLD:
        return False
    return evidence.evidence_search_assessment in (
        EvidenceSearchAssessment.WEAK_RELATIVE_TO_SEARCH.value,
        EvidenceSearchAssessment.INSUFFICIENT.value,
    )


def validate_confirmation_independence(split: ConfirmationSplitMetadata) -> bool:
    """
    Confirmation cannot reuse discovery observations.

    Returns True when split is valid (disjoint or not yet available).
    """
    if split.confirmation_status == ConfirmationStatus.NOT_AVAILABLE.value:
        return True
    if split.observations_overlap is True:
        return False
    if split.discovery_cutoff and split.confirmation_cutoff:
        if split.discovery_cutoff >= split.confirmation_cutoff and split.observations_overlap is not False:
            return False
    return True
