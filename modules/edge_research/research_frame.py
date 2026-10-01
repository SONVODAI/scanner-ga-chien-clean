"""
Research frame — population + outcome + information horizon as a searchable unit (Phase 3G.2).

Enables autonomous reframing when a frame is saturated without sufficient payoff.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.edge_research.metrics import HORIZONS, RETURN_COLUMNS
from modules.edge_research.research_feature_eligibility import (
    field_availability_horizon,
    get_research_observation_horizon,
)
from modules.edge_research.research_grammar import (
    ALLOWED_OUTCOME_FIELDS,
    GrammarValidationError,
    OutcomeKind,
    OutcomeSpec,
    PopulationKind,
    PopulationSpec,
    build_search_accounting,
    outcome_specs_equal,
    population_specs_equal,
    propose_outcome_reframes,
    validate_outcome_spec,
    validate_population_spec,
)

RESEARCH_FRAME_VERSION = "research_frame_v1"

# Generic saturation thresholds — not tuned to any benchmark.
MIN_EXPERIMENTS_FOR_SATURATION = 3
MIN_FEATURE_COVERAGE_RATIO = 0.5
MIN_CANDIDATE_YIELD = 1
STOP_BRANCH_SATURATION_COUNT = 2


class FrameStatus(str, Enum):
    ACTIVE = "ACTIVE"
    UNDEREXPLORED = "UNDEREXPLORED"
    PRODUCTIVE = "PRODUCTIVE"
    LOW_YIELD = "LOW_YIELD"
    EXHAUSTED = "EXHAUSTED"
    SUPERSEDED = "SUPERSEDED"


class FrameTransformationType(str, Enum):
    INITIAL = "INITIAL"
    OUTCOME_REFRAME = "OUTCOME_REFRAME"
    POPULATION_REFRAME = "POPULATION_REFRAME"
    HORIZON_ADVANCE = "HORIZON_ADVANCE"
    OUTCOME_TO_POPULATION = "OUTCOME_TO_POPULATION"
    CONTEXT_REFRAME = "CONTEXT_REFRAME"
    STRUCTURAL_TRIGGER = "STRUCTURAL_TRIGGER"


@dataclass
class FrameLineageRecord:
    """Audit: why Bot changed research frame."""

    old_frame_id: str
    new_frame_id: str
    transformation: str
    trigger: str
    saturation_evidence: Dict[str, Any] = field(default_factory=dict)
    parent_outcome_hash: str = ""
    parent_population_hash: str = ""
    new_outcome_hash: str = ""
    new_population_hash: str = ""
    observation_horizon: int = 0
    sample_n: Optional[int] = None
    temporal_legal: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "old_frame_id": self.old_frame_id,
            "new_frame_id": self.new_frame_id,
            "transformation": self.transformation,
            "trigger": self.trigger,
            "saturation_evidence": dict(self.saturation_evidence),
            "parent_outcome_hash": self.parent_outcome_hash,
            "parent_population_hash": self.parent_population_hash,
            "new_outcome_hash": self.new_outcome_hash,
            "new_population_hash": self.new_population_hash,
            "observation_horizon": self.observation_horizon,
            "sample_n": self.sample_n,
            "temporal_legal": self.temporal_legal,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FrameLineageRecord":
        return cls(
            old_frame_id=str(payload.get("old_frame_id", "")),
            new_frame_id=str(payload.get("new_frame_id", "")),
            transformation=str(payload.get("transformation", "")),
            trigger=str(payload.get("trigger", "")),
            saturation_evidence=dict(payload.get("saturation_evidence") or {}),
            parent_outcome_hash=str(payload.get("parent_outcome_hash", "")),
            parent_population_hash=str(payload.get("parent_population_hash", "")),
            new_outcome_hash=str(payload.get("new_outcome_hash", "")),
            new_population_hash=str(payload.get("new_population_hash", "")),
            observation_horizon=int(payload.get("observation_horizon", 0)),
            sample_n=payload.get("sample_n"),
            temporal_legal=bool(payload.get("temporal_legal", True)),
        )


@dataclass
class ResearchFrame:
    """One research question frame: population + outcome + information horizon."""

    frame_id: str
    population: PopulationSpec
    outcome: OutcomeSpec
    observation_horizon: int = 0
    context_scope: Dict[str, Any] = field(default_factory=dict)
    parent_frame_id: str = ""
    reason_created: str = ""
    triggering_evidence: Dict[str, Any] = field(default_factory=dict)
    transformation: str = FrameTransformationType.INITIAL.value
    frame_depth: int = 0
    experiments_in_frame: int = 0
    features_explored: Tuple[str, ...] = field(default_factory=tuple)
    candidate_yield: int = 0
    falsification_yield: int = 0
    stop_branch_count: int = 0
    flat_noisy_count: int = 0
    complexity_burden: float = 0.0
    information_gain_score: float = 0.0
    status: str = FrameStatus.ACTIVE.value
    eligible_feature_count: int = 0

    def content_hash(self) -> str:
        payload = {
            "population": self.population.content_hash(),
            "outcome": self.outcome.content_hash(),
            "observation_horizon": self.observation_horizon,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        import hashlib
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "population_spec": self.population.to_dict(),
            "outcome_spec": self.outcome.to_dict(),
            "observation_horizon": self.observation_horizon,
            "context_scope": dict(self.context_scope),
            "parent_frame_id": self.parent_frame_id,
            "reason_created": self.reason_created,
            "triggering_evidence": dict(self.triggering_evidence),
            "transformation": self.transformation,
            "frame_depth": self.frame_depth,
            "experiments_in_frame": self.experiments_in_frame,
            "features_explored": list(self.features_explored),
            "candidate_yield": self.candidate_yield,
            "falsification_yield": self.falsification_yield,
            "stop_branch_count": self.stop_branch_count,
            "flat_noisy_count": self.flat_noisy_count,
            "complexity_burden": self.complexity_burden,
            "information_gain_score": self.information_gain_score,
            "status": self.status,
            "eligible_feature_count": self.eligible_feature_count,
            "content_hash": self.content_hash(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchFrame":
        return cls(
            frame_id=str(payload["frame_id"]),
            population=PopulationSpec.from_dict(payload["population_spec"]),
            outcome=OutcomeSpec.from_dict(payload["outcome_spec"]),
            observation_horizon=int(payload.get("observation_horizon", 0)),
            context_scope=dict(payload.get("context_scope") or {}),
            parent_frame_id=str(payload.get("parent_frame_id", "")),
            reason_created=str(payload.get("reason_created", "")),
            triggering_evidence=dict(payload.get("triggering_evidence") or {}),
            transformation=str(payload.get("transformation", FrameTransformationType.INITIAL.value)),
            frame_depth=int(payload.get("frame_depth", 0)),
            experiments_in_frame=int(payload.get("experiments_in_frame", 0)),
            features_explored=tuple(payload.get("features_explored") or ()),
            candidate_yield=int(payload.get("candidate_yield", 0)),
            falsification_yield=int(payload.get("falsification_yield", 0)),
            stop_branch_count=int(payload.get("stop_branch_count", 0)),
            flat_noisy_count=int(payload.get("flat_noisy_count", 0)),
            complexity_burden=float(payload.get("complexity_burden", 0.0)),
            information_gain_score=float(payload.get("information_gain_score", 0.0)),
            status=str(payload.get("status", FrameStatus.ACTIVE.value)),
            eligible_feature_count=int(payload.get("eligible_feature_count", 0)),
        )

    @classmethod
    def initial(
        cls,
        frame_id: str,
        population: PopulationSpec,
        outcome: OutcomeSpec,
        *,
        eligible_feature_count: int = 0,
    ) -> "ResearchFrame":
        return cls(
            frame_id=frame_id,
            population=population,
            outcome=outcome,
            observation_horizon=0,
            transformation=FrameTransformationType.INITIAL.value,
            status=FrameStatus.UNDEREXPLORED.value,
            eligible_feature_count=eligible_feature_count,
        )

    def child(
        self,
        new_id: str,
        *,
        population: Optional[PopulationSpec] = None,
        outcome: Optional[OutcomeSpec] = None,
        observation_horizon: Optional[int] = None,
        transformation: str,
        reason: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> "ResearchFrame":
        return ResearchFrame(
            frame_id=new_id,
            population=population if population is not None else self.population,
            outcome=outcome if outcome is not None else self.outcome,
            observation_horizon=observation_horizon if observation_horizon is not None else self.observation_horizon,
            parent_frame_id=self.frame_id,
            reason_created=reason,
            triggering_evidence=dict(evidence or {}),
            transformation=transformation,
            frame_depth=self.frame_depth + 1,
            eligible_feature_count=self.eligible_feature_count,
            status=FrameStatus.UNDEREXPLORED.value,
        )


@dataclass
class ResearchFrameRegistry:
    """Session-level frame tracking and lineage."""

    version: str = RESEARCH_FRAME_VERSION
    frames: Dict[str, ResearchFrame] = field(default_factory=dict)
    lineage: List[FrameLineageRecord] = field(default_factory=list)
    active_frame_id: str = ""
    _counter: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "frames": {k: v.to_dict() for k, v in sorted(self.frames.items())},
            "lineage": [r.to_dict() for r in self.lineage],
            "active_frame_id": self.active_frame_id,
            "_counter": self._counter,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchFrameRegistry":
        return cls(
            version=str(payload.get("version", RESEARCH_FRAME_VERSION)),
            frames={
                k: ResearchFrame.from_dict(v)
                for k, v in (payload.get("frames") or {}).items()
            },
            lineage=[FrameLineageRecord.from_dict(r) for r in (payload.get("lineage") or [])],
            active_frame_id=str(payload.get("active_frame_id", "")),
            _counter=int(payload.get("_counter", 0)),
        )

    def next_id(self) -> str:
        self._counter += 1
        return f"frame-{self._counter:05d}"

    def get(self, frame_id: str) -> Optional[ResearchFrame]:
        return self.frames.get(frame_id)

    def register(self, frame: ResearchFrame, *, set_active: bool = True) -> None:
        self.frames[frame.frame_id] = frame
        if set_active:
            self.active_frame_id = frame.frame_id

    def record_transition(
        self,
        old_frame: ResearchFrame,
        new_frame: ResearchFrame,
        *,
        trigger: str,
        saturation_evidence: Optional[Dict[str, Any]] = None,
        sample_n: Optional[int] = None,
    ) -> None:
        self.lineage.append(
            FrameLineageRecord(
                old_frame_id=old_frame.frame_id,
                new_frame_id=new_frame.frame_id,
                transformation=new_frame.transformation,
                trigger=trigger,
                saturation_evidence=dict(saturation_evidence or {}),
                parent_outcome_hash=old_frame.outcome.content_hash(),
                parent_population_hash=old_frame.population.content_hash(),
                new_outcome_hash=new_frame.outcome.content_hash(),
                new_population_hash=new_frame.population.content_hash(),
                observation_horizon=new_frame.observation_horizon,
                sample_n=sample_n,
                temporal_legal=validate_frame_temporal_legality(new_frame),
            )
        )
        old_frame.status = FrameStatus.SUPERSEDED.value
        self.register(new_frame)

    def unique_outcome_count(self) -> int:
        return len({f.outcome.content_hash() for f in self.frames.values()})

    def unique_population_count(self) -> int:
        return len({f.population.content_hash() for f in self.frames.values()})


def validate_frame_temporal_legality(frame: ResearchFrame) -> bool:
    """Ensure population filters and outcomes respect information horizon."""
    obs = frame.observation_horizon
    try:
        validate_outcome_spec(frame.outcome)
    except GrammarValidationError:
        return False
    try:
        validate_population_at_horizon(frame.population, observation_horizon=obs)
    except GrammarValidationError:
        return False
    # Outcome must be forward relative to observation horizon.
    max_outcome_h = _max_outcome_horizon_sessions(frame.outcome)
    if max_outcome_h <= obs:
        return False
    return True


def validate_population_at_horizon(spec: PopulationSpec, *, observation_horizon: int) -> None:
    """Validate population — outcome fields allowed only when observable at horizon."""
    if spec.kind == PopulationKind.ALL.value:
        return
    if spec.kind == PopulationKind.FILTER.value:
        assert spec.filter_field is not None
        field = spec.filter_field
        if field in ALLOWED_OUTCOME_FIELDS:
            avail = field_availability_horizon(field)
            if avail > observation_horizon:
                raise GrammarValidationError(
                    f"Future leakage: {field!r} available at session {avail}, "
                    f"observation_horizon={observation_horizon}"
                )
            return
        validate_population_spec(spec)
        return
    if spec.kind == PopulationKind.AND.value:
        for child in spec.children:
            validate_population_at_horizon(child, observation_horizon=observation_horizon)
        return
    if spec.kind == PopulationKind.REFINE.value:
        if spec.parent is not None:
            validate_population_at_horizon(spec.parent, observation_horizon=observation_horizon)
        for child in spec.children:
            validate_population_at_horizon(child, observation_horizon=observation_horizon)
        return
    if spec.kind == PopulationKind.WIDEN.value:
        if spec.parent is not None:
            validate_population_at_horizon(spec.parent, observation_horizon=observation_horizon)
        return
    validate_population_spec(spec)


def _max_outcome_horizon_sessions(outcome: OutcomeSpec) -> int:
    """Latest horizon session referenced by outcome spec."""
    if outcome.kind == OutcomeKind.COMPARE.value and outcome.outcome_field:
        return field_availability_horizon(outcome.outcome_field)
    if outcome.kind == OutcomeKind.CONTINUATION.value and outcome.late_horizon:
        return field_availability_horizon(RETURN_COLUMNS.get(outcome.late_horizon, ""))
    if outcome.late_horizon:
        return field_availability_horizon(RETURN_COLUMNS.get(outcome.late_horizon, ""))
    if outcome.outcome_field:
        return field_availability_horizon(outcome.outcome_field)
    for h in outcome.horizons:
        col = RETURN_COLUMNS.get(h)
        if col:
            return max(field_availability_horizon(col), 0)
    return 0


def population_from_observed_outcome(
    outcome: OutcomeSpec,
    *,
    reason_code: str,
    triggering_evidence: Optional[Dict[str, Any]] = None,
) -> Optional[PopulationSpec]:
    """
    Outcome-to-population: a COMPARE outcome becomes a population filter
    once its field is observable at the frame's information horizon.
    """
    if outcome.kind != OutcomeKind.COMPARE.value:
        return None
    if outcome.outcome_field is None or outcome.operator is None or outcome.value is None:
        return None
    filt = PopulationSpec.filter_numeric(
        outcome.outcome_field, outcome.operator, float(outcome.value)
    )
    filt = PopulationSpec.refine(
        PopulationSpec.all_(),
        filt,
        reason_code=reason_code,
        triggering_evidence=dict(triggering_evidence or {}),
    )
    return filt


def propose_horizon_advancement_frames(
    frame: ResearchFrame,
) -> Tuple[ResearchFrame, ...]:
    """
    Advance information horizon — earlier outcome may define population for later outcome.
    """
    proposals: List[ResearchFrame] = []
    obs = frame.observation_horizon

    if frame.outcome.kind == OutcomeKind.COMPARE.value and frame.outcome.outcome_field:
        early_field = frame.outcome.outcome_field
        early_avail = field_availability_horizon(early_field)
        if early_avail <= obs:
            return tuple()

        pop = population_from_observed_outcome(
            frame.outcome,
            reason_code="OUTCOME_TO_POPULATION",
            triggering_evidence={"source_outcome_hash": frame.outcome.content_hash()},
        )
        if pop is None:
            return tuple(proposals)

        new_obs = early_avail
        for late_col in sorted(ALLOWED_OUTCOME_FIELDS):
            late_avail = field_availability_horizon(late_col)
            if late_avail <= new_obs:
                continue
            late_outcome = OutcomeSpec.compare(late_col, ">", 0.0)
            try:
                validate_outcome_spec(late_outcome)
                validate_population_at_horizon(pop, observation_horizon=new_obs)
            except GrammarValidationError:
                continue
            child = frame.child(
                "pending",
                population=pop,
                outcome=late_outcome,
                observation_horizon=new_obs,
                transformation=FrameTransformationType.OUTCOME_TO_POPULATION.value,
                reason=f"Condition on observed {early_field}, investigate {late_col}",
                evidence={"early_field": early_field, "late_field": late_col},
            )
            if validate_frame_temporal_legality(child):
                proposals.append(child)

    # Generic horizon step: advance obs by one session if legal.
    next_obs = obs + 1
    max_h = max(field_availability_horizon(c) for c in ALLOWED_OUTCOME_FIELDS)
    if next_obs <= max_h:
        child = frame.child(
            "pending",
            observation_horizon=next_obs,
            transformation=FrameTransformationType.HORIZON_ADVANCE.value,
            reason=f"Advance observation horizon to session {next_obs}",
            evidence={"prior_obs": obs},
        )
        if validate_frame_temporal_legality(child):
            proposals.append(child)

    return tuple(proposals)


def propose_population_from_observed_data(
    current: PopulationSpec,
    *,
    categorical_values: Dict[str, Sequence[str]],
    numeric_median_splits: Dict[str, float],
    reason_code: str,
    triggering_evidence: Optional[Dict[str, Any]] = None,
) -> Tuple[PopulationSpec, ...]:
    """Evidence-driven population refinements — generic field names only."""
    proposals: List[PopulationSpec] = []
    evidence = dict(triggering_evidence or {})

    for feat, values in categorical_values.items():
        if not values:
            continue
        filt = PopulationSpec.filter_categorical(feat, values[:1])
        refined = PopulationSpec.refine(current, filt, reason_code=reason_code, triggering_evidence=evidence)
        try:
            validate_population_spec(refined)
            if not population_specs_equal(refined, current):
                proposals.append(refined)
        except GrammarValidationError:
            pass

    for feat, median in numeric_median_splits.items():
        filt = PopulationSpec.filter_numeric(feat, ">", float(median))
        refined = PopulationSpec.refine(current, filt, reason_code=reason_code, triggering_evidence=evidence)
        try:
            validate_population_spec(refined)
            if not population_specs_equal(refined, current):
                proposals.append(refined)
        except GrammarValidationError:
            pass

    seen: set[str] = {current.content_hash()}
    unique: List[PopulationSpec] = []
    for p in proposals:
        h = p.content_hash()
        if h not in seen:
            seen.add(h)
            unique.append(p)
    return tuple(unique)


def propose_structural_reframes(
    frame: ResearchFrame,
    *,
    observation_kind: str,
    observation_codes: Sequence[str],
) -> Tuple[ResearchFrame, ...]:
    """Structural observations may spawn new outcome/population/horizon frames."""
    proposals: List[ResearchFrame] = []
    codes = set(observation_codes)
    evidence = {"observation_kind": observation_kind, "codes": list(codes)}

    if "HORIZON_HETEROGENEOUS" in codes or observation_kind == "STRUCTURAL_OBSERVATION":
        for alt_outcome in propose_outcome_reframes(frame.outcome):
            if outcome_specs_equal(alt_outcome, frame.outcome):
                continue
            child = frame.child(
                "pending",
                outcome=alt_outcome,
                transformation=FrameTransformationType.STRUCTURAL_TRIGGER.value,
                reason="Horizon heterogeneity suggests alternative outcome framing",
                evidence=evidence,
            )
            if validate_frame_temporal_legality(child):
                proposals.append(child)

    if "MARKET_HETEROGENEOUS" in codes:
        child = frame.child(
            "pending",
            transformation=FrameTransformationType.CONTEXT_REFRAME.value,
            reason="Market heterogeneity suggests context-stratified research frame",
            evidence=evidence,
        )
        if validate_frame_temporal_legality(child):
            proposals.append(child)

    proposals.extend(propose_horizon_advancement_frames(frame))
    return tuple(proposals)


def assess_frame_saturation(frame: ResearchFrame) -> Tuple[str, Dict[str, Any]]:
    """
    Determine if frame is saturated (LOW_YIELD / EXHAUSTED) vs productive.

    Returns (status, evidence_dict).
    """
    evidence: Dict[str, Any] = {
        "experiments_in_frame": frame.experiments_in_frame,
        "features_explored": len(frame.features_explored),
        "eligible_features": frame.eligible_feature_count,
        "candidate_yield": frame.candidate_yield,
        "stop_branch_count": frame.stop_branch_count,
        "flat_noisy_count": frame.flat_noisy_count,
    }

    if frame.candidate_yield >= MIN_CANDIDATE_YIELD:
        return FrameStatus.PRODUCTIVE.value, evidence

    if frame.experiments_in_frame < MIN_EXPERIMENTS_FOR_SATURATION:
        return FrameStatus.UNDEREXPLORED.value, evidence

    feature_ratio = (
        len(frame.features_explored) / max(1, frame.eligible_feature_count)
        if frame.eligible_feature_count > 0
        else 0.0
    )
    evidence["feature_coverage_ratio"] = feature_ratio

    low_signal = (
        frame.flat_noisy_count >= 2
        or frame.stop_branch_count >= STOP_BRANCH_SATURATION_COUNT
        or (feature_ratio >= MIN_FEATURE_COVERAGE_RATIO and frame.candidate_yield == 0)
    )

    if low_signal and frame.experiments_in_frame >= MIN_EXPERIMENTS_FOR_SATURATION:
        return FrameStatus.LOW_YIELD.value, evidence

    if frame.experiments_in_frame >= MIN_EXPERIMENTS_FOR_SATURATION * 2 and frame.candidate_yield == 0:
        return FrameStatus.EXHAUSTED.value, evidence

    return FrameStatus.ACTIVE.value, evidence


def check_sample_sufficiency(
    *,
    resulting_n: int,
    parent_n: int,
    min_effective_n: int = 20,
) -> Tuple[bool, float]:
    """
    Returns (sufficient, sample_loss_ratio).
    Tiny cohorts should not receive excessive planner priority.
    """
    if parent_n <= 0:
        return resulting_n >= min_effective_n, 0.0
    ratio = 1.0 - (resulting_n / parent_n)
    sufficient = resulting_n >= min_effective_n
    return sufficient, ratio


def frame_from_question_context(
    frame_id: str,
    population: PopulationSpec,
    outcome: OutcomeSpec,
    *,
    observation_horizon: Optional[int] = None,
    scope: Optional[Dict[str, Any]] = None,
) -> ResearchFrame:
    obs = observation_horizon
    if obs is None and scope:
        obs = get_research_observation_horizon(scope)
    if obs is None:
        obs = 0
    return ResearchFrame(
        frame_id=frame_id,
        population=population,
        outcome=outcome,
        observation_horizon=int(obs),
    )
