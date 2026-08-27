"""
Phase 3H.8 — Realized information gain from completed experiments.

Measures scientific change from prior assessment → current assessment.
Available BEFORE the next planning decision (computed post-interpret, pre-plan).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.edge_research.research_assessment import ResearchAssessment

RESEARCH_REALIZED_INFORMATION_GAIN_VERSION = "research_realized_information_gain_v1"


class RealizedGainLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    ZERO = "ZERO"
    UNRESOLVED = "UNRESOLVED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class RealizedInformationGain:
    """Auditable realized information gain for one completed experiment."""

    version: str
    experiment_node_id: str
    branch_root_id: str
    gain_level: str
    gaps_resolved: Tuple[str, ...]
    gaps_narrowed: Tuple[str, ...]
    falsification_resolved: Tuple[str, ...]
    new_observations: Tuple[str, ...]
    uncertainties_unchanged: Tuple[str, ...]
    component_explanations: Dict[str, str]
    built_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "experiment_node_id": self.experiment_node_id,
            "branch_root_id": self.branch_root_id,
            "gain_level": self.gain_level,
            "gaps_resolved": list(self.gaps_resolved),
            "gaps_narrowed": list(self.gaps_narrowed),
            "falsification_resolved": list(self.falsification_resolved),
            "new_observations": list(self.new_observations),
            "uncertainties_unchanged": list(self.uncertainties_unchanged),
            "component_explanations": dict(self.component_explanations),
            "built_at": self.built_at,
        }


def _assessment_from_dict(payload: Dict[str, Any]) -> ResearchAssessment:
    tuple_fields = (
        "empirical_findings",
        "unresolved_uncertainties",
        "contradictions",
        "concentration_concerns",
        "replication_concerns",
        "fragility_evidence",
        "context_dependence",
        "horizon_dependence",
        "information_gaps",
        "possible_falsification_targets",
        "branch_tools_attempted",
        "branch_observation_codes",
    )
    kwargs = dict(payload)
    for key in tuple_fields:
        if key in kwargs and isinstance(kwargs[key], list):
            kwargs[key] = tuple(kwargs[key])
    return ResearchAssessment(**kwargs)


def store_assessment_snapshot(graph: Any, experiment_node_id: str, assessment: ResearchAssessment) -> None:
    snaps = dict(getattr(graph.session, "experiment_assessment_snapshots", None) or {})
    snaps[experiment_node_id] = assessment.to_dict()
    graph.session.experiment_assessment_snapshots = snaps


def _prior_assessment_for_experiment(graph: Any, experiment_node_id: str) -> Optional[ResearchAssessment]:
    """Parent experiment assessment snapshot — state before current experiment ran."""
    from modules.edge_research.research_state import NodeType

    node = graph.get_node(experiment_node_id)
    snaps = getattr(graph.session, "experiment_assessment_snapshots", None) or {}
    for qid in node.parent_node_ids:
        q = graph.get_node(qid)
        if q.node_type != NodeType.QUESTION:
            continue
        for peid in q.parent_node_ids:
            if peid in snaps:
                return _assessment_from_dict(snaps[peid])
    return None


def assess_realized_information_gain(
    *,
    graph: Any,
    experiment_node_id: str,
    current_assessment: ResearchAssessment,
    branch_root_id: str,
    prior_assessment: Optional[ResearchAssessment] = None,
) -> RealizedInformationGain:
    """Compare current assessment to legally available prior state."""
    prior = prior_assessment or _prior_assessment_for_experiment(graph, experiment_node_id)

    prior_gaps: Set[str] = set(prior.information_gaps) if prior else set()
    prior_fals: Set[str] = set(prior.possible_falsification_targets) if prior else set()
    prior_obs: Set[str] = set(prior.branch_observation_codes) if prior else set()
    prior_unc: Set[str] = set(prior.unresolved_uncertainties) if prior else set()

    curr_gaps = set(current_assessment.information_gaps)
    curr_fals = set(current_assessment.possible_falsification_targets)
    curr_obs = set(current_assessment.branch_observation_codes)
    curr_unc = set(current_assessment.unresolved_uncertainties)

    gaps_resolved = prior_gaps - curr_gaps
    fals_resolved = prior_fals - curr_fals
    new_obs = curr_obs - prior_obs
    unc_unchanged = prior_unc & curr_unc
    gaps_narrowed: Set[str] = set()

    explanations: Dict[str, str] = {}

    if gaps_resolved:
        explanations["gaps_resolved"] = f"Resolved gaps: {sorted(gaps_resolved)}"
    if fals_resolved:
        explanations["falsification_resolved"] = f"Falsification targets addressed: {sorted(fals_resolved)}"
    if new_obs:
        explanations["new_observations"] = f"New observation codes: {sorted(new_obs)}"

    level = RealizedGainLevel.UNRESOLVED.value
    if gaps_resolved or fals_resolved:
        level = RealizedGainLevel.HIGH.value
        if len(gaps_resolved) + len(fals_resolved) == 1 and not new_obs:
            level = RealizedGainLevel.MEDIUM.value
    elif new_obs and len(new_obs) >= 2:
        level = RealizedGainLevel.MEDIUM.value
    elif new_obs:
        level = RealizedGainLevel.LOW.value
    elif not prior:
        level = RealizedGainLevel.MEDIUM.value
        explanations["initial_experiment"] = "First assessment on branch — baseline information"
    else:
        if (
            current_assessment.descriptive_strength == prior.descriptive_strength
            and not new_obs
            and prior_gaps == curr_gaps
        ):
            level = RealizedGainLevel.ZERO.value
            explanations["no_distinction"] = "Repeated experiment produced no new distinction"
        else:
            level = RealizedGainLevel.LOW.value

    return RealizedInformationGain(
        version=RESEARCH_REALIZED_INFORMATION_GAIN_VERSION,
        experiment_node_id=experiment_node_id,
        branch_root_id=branch_root_id,
        gain_level=level,
        gaps_resolved=tuple(sorted(gaps_resolved)),
        gaps_narrowed=tuple(sorted(gaps_narrowed)),
        falsification_resolved=tuple(sorted(fals_resolved)),
        new_observations=tuple(sorted(new_obs)),
        uncertainties_unchanged=tuple(sorted(unc_unchanged)),
        component_explanations=explanations,
    )


def record_realized_information_gain(graph: Any, gain: RealizedInformationGain) -> None:
    """Persist on session for branch marginal state and audit."""
    history = list(getattr(graph.session, "research_realized_information_gain_history", None) or [])
    history.append(gain.to_dict())
    graph.session.research_realized_information_gain_history = history

    by_branch: Dict[str, List[Dict[str, Any]]] = dict(
        getattr(graph.session, "research_realized_gain_by_branch", None) or {}
    )
    branch = gain.branch_root_id or "unknown"
    entries = list(by_branch.get(branch, []))
    entries.append(gain.to_dict())
    by_branch[branch] = entries[-20:]
    graph.session.research_realized_gain_by_branch = by_branch


def get_branch_realized_gain_history(graph: Any, branch_root_id: str) -> List[Dict[str, Any]]:
    by_branch = getattr(graph.session, "research_realized_gain_by_branch", None) or {}
    return list(by_branch.get(branch_root_id, []))
