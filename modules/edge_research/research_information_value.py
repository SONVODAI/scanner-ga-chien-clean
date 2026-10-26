"""
Phase 3H.6 — Evidence-Based Research Information Value bridge.

Connects unresolved evidence / uncertainty to auditable valuation adjustments.
INFORMATION VALUE ≠ COMPETENCE PREFERENCE ≠ ACTION.

Competence may inform what uncertainties exist; this module independently
determines whether resolving them has marginal scientific information value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from modules.edge_research.research_actions import ActionIntent, ResearchActionCandidate
from modules.edge_research.research_assessment import DescriptiveStrength, ResearchAssessment
from modules.edge_research.research_interpreter import (
    FALSIFY_DATE_ARTIFACT,
    FALSIFY_EPISODE_FLUKE,
    FALSIFY_EXTREME_WINNER,
    FALSIFY_SYMBOL_DOMINANCE,
    GAP_CATEGORY_REFINEMENT,
    GAP_EPISODE_REPLICATION,
    GAP_HORIZON_STABILITY,
    GAP_INTERACTION_FOLLOWUP,
    GAP_MARKET_DEPENDENCE,
    GAP_NEIGHBORHOOD_STABILITY,
    GAP_NEIGHBORHOOD_THRESHOLD,
    GAP_SYMBOL_DISTRIBUTION,
    GAP_THRESHOLD_EXPLORATION,
    GAP_TIME_DISTRIBUTION,
    GAP_TRAJECTORY_ROLE,
)

RESEARCH_INFORMATION_VALUE_VERSION = "research_information_value_v1"

# Generic scales — not tuned from BB09 action outcomes.
INFO_VALUE_SCALE = 2.5
FALSIFICATION_INFO_SCALE = 3.0
HETEROGENEITY_INFO_SCALE = 2.5
REDUNDANCY_DIMINISH_STEP = 0.35

# Observation codes indicating falsification already adequate (CASE B).
ROBUST_FALSIFICATION_OBSERVATIONS: FrozenSet[str] = frozenset(
    {
        "EXTREME_WINNER_ROBUST",
        "SENSITIVITY_ROBUST",
    }
)
FRAGILE_FALSIFICATION_OBSERVATIONS: FrozenSet[str] = frozenset(
    {
        "EXTREME_WINNER_SENSITIVE",
        "SENSITIVITY_FRAGILE",
    }
)

# Evidence topology: which executed tools address which uncertainty codes.
# Used for redundancy counting only — not for tool-name bonuses.
UNCERTAINTY_RESOLUTION_TOOLS: Dict[str, FrozenSet[str]] = {
    GAP_TIME_DISTRIBUTION: frozenset({"date_decomposition"}),
    GAP_SYMBOL_DISTRIBUTION: frozenset({"symbol_decomposition"}),
    GAP_EPISODE_REPLICATION: frozenset({"episode_decomposition"}),
    GAP_MARKET_DEPENDENCE: frozenset({"market_conditioning"}),
    GAP_HORIZON_STABILITY: frozenset({"horizon_comparison"}),
    GAP_NEIGHBORHOOD_STABILITY: frozenset({"neighborhood_stability", "threshold_neighborhood"}),
    GAP_TRAJECTORY_ROLE: frozenset({"trajectory_partition_compare"}),
    GAP_THRESHOLD_EXPLORATION: frozenset({"threshold_exploration"}),
    GAP_NEIGHBORHOOD_THRESHOLD: frozenset({"threshold_neighborhood"}),
    GAP_CATEGORY_REFINEMENT: frozenset({"categorical_adaptive_compare", "adaptive_partition_compare"}),
    GAP_INTERACTION_FOLLOWUP: frozenset({"interaction_partition"}),
    FALSIFY_EXTREME_WINNER: frozenset({"sensitivity_analysis", "neighborhood_stability"}),
    FALSIFY_DATE_ARTIFACT: frozenset({"sensitivity_analysis", "date_decomposition"}),
    FALSIFY_SYMBOL_DOMINANCE: frozenset({"sensitivity_analysis", "symbol_decomposition"}),
    FALSIFY_EPISODE_FLUKE: frozenset({"sensitivity_analysis", "episode_decomposition"}),
}

HETEROGENEITY_GAPS: FrozenSet[str] = frozenset(
    {
        GAP_TIME_DISTRIBUTION,
        GAP_SYMBOL_DISTRIBUTION,
        GAP_EPISODE_REPLICATION,
        GAP_MARKET_DEPENDENCE,
    }
)

HETEROGENEITY_INTENTS: FrozenSet[str] = frozenset(
    {
        ActionIntent.DECOMPOSITION.value,
        ActionIntent.REPLICATION.value,
        ActionIntent.CONDITIONING.value,
    }
)

_FORBIDDEN_BRIDGE_TOKENS: FrozenSet[str] = frozenset(
    {
        "competence_match_bonus",
        "falsification_bonus",
        "decomposition_bonus",
        "sensitivity_analysis_bonus",
        "preferred_tool",
        "preferred_feature",
        "bb09",
        "blind_benchmark",
        "chatgpt",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _claim_strength(assessment: ResearchAssessment) -> float:
    """Evidence-based claim strength — not competence-derived."""
    ds = assessment.descriptive_strength
    if ds == DescriptiveStrength.GROUP_DIFFERENCE.value:
        return 1.0
    if assessment.interesting:
        return 0.75
    if ds == DescriptiveStrength.NO_CLEAR_DIFFERENCE.value:
        return 0.35
    if ds == DescriptiveStrength.NO_VARIATION.value:
        return 0.15
    return 0.1


def _prior_resolution_attempts(uncertainty_code: str, branch_tools: Sequence[str]) -> int:
    tools = UNCERTAINTY_RESOLUTION_TOOLS.get(uncertainty_code, frozenset())
    return sum(1 for t in branch_tools if t in tools)


def _redundancy_burden(prior_attempts: int) -> float:
    return min(1.0, prior_attempts * REDUNDANCY_DIMINISH_STEP)


def _uncertainty_type(uncertainty_code: str, assessment: ResearchAssessment) -> str:
    if uncertainty_code in assessment.possible_falsification_targets:
        return "falsification_target"
    if uncertainty_code in assessment.information_gaps:
        return "information_gap"
    if uncertainty_code in assessment.unresolved_uncertainties:
        return "unresolved_uncertainty"
    return "none"


def _directness(uncertainty_code: str, candidate: ResearchActionCandidate, assessment: ResearchAssessment) -> float:
    unc = candidate.uncertainty_addressed
    if not unc or unc != uncertainty_code:
        return 0.0
    if unc in assessment.information_gaps:
        return 1.0
    if unc in assessment.possible_falsification_targets and candidate.intent == ActionIntent.FALSIFICATION.value:
        return 1.0
    if unc in assessment.unresolved_uncertainties:
        return 0.5
    return 0.0


def _falsification_pathway(
    candidate: ResearchActionCandidate,
    assessment: ResearchAssessment,
    *,
    prior_attempts: int,
) -> Tuple[float, str, Dict[str, float]]:
    """Generic falsification information value — Cases A–E."""
    components: Dict[str, float] = {}
    unc = candidate.uncertainty_addressed

    if candidate.intent != ActionIntent.FALSIFICATION.value:
        return 0.0, "not_falsification_intent", components
    if unc not in assessment.possible_falsification_targets:
        return 0.0, "no_active_falsification_target", components

    # CASE B — adequate falsification already performed
    if unc == FALSIFY_EXTREME_WINNER:
        obs = set(assessment.branch_observation_codes)
        if obs & ROBUST_FALSIFICATION_OBSERVATIONS:
            return 0.0, "adequate_falsification_already_performed", components

    # CASE C — weak / no substantive claim
    claim = _claim_strength(assessment)
    components["claim_strength"] = claim
    if claim < 0.2 and not assessment.possible_falsification_targets:
        return 0.0, "weak_no_substantive_claim", components

    redundancy = _redundancy_burden(prior_attempts)
    components["redundancy_burden"] = redundancy
    components["evidence_deficit"] = 1.0 if unc in assessment.possible_falsification_targets else 0.0
    components["directness"] = 1.0

    # CASE A / D / E — compete on evidence merit with diminishing returns
    if components["evidence_deficit"] <= 0:
        return 0.0, "no_evidence_deficit", components

    marginal = claim * (1.0 - redundancy) * FALSIFICATION_INFO_SCALE
    components["falsification_marginal_value"] = marginal
    reason = "unresolved_robustness_uncertainty_no_prior_adequate_falsification"
    if prior_attempts > 0:
        reason = "falsification_redundancy_reduced_marginal_value"
    return marginal, reason, components


def _heterogeneity_pathway(
    candidate: ResearchActionCandidate,
    assessment: ResearchAssessment,
    *,
    prior_attempts: int,
) -> Tuple[float, str, Dict[str, float]]:
    """Generic heterogeneity resolution value — not decomposition-by-tool-name."""
    components: Dict[str, float] = {}
    unc = candidate.uncertainty_addressed

    if unc not in HETEROGENEITY_GAPS or unc not in assessment.information_gaps:
        return 0.0, "no_unresolved_heterogeneity_gap", components
    if candidate.intent not in HETEROGENEITY_INTENTS:
        return 0.0, "not_heterogeneity_resolving_intent", components

    redundancy = _redundancy_burden(prior_attempts)
    components["redundancy_burden"] = redundancy
    components["evidence_deficit"] = 1.0
    components["directness"] = 1.0

    marginal = (1.0 - redundancy) * HETEROGENEITY_INFO_SCALE
    components["heterogeneity_marginal_value"] = marginal
    reason = "unresolved_heterogeneity_directly_addressable"
    if prior_attempts > 0:
        reason = "heterogeneity_resolution_redundancy_reduced"
    return marginal, reason, components


def _generic_gap_pathway(
    candidate: ResearchActionCandidate,
    assessment: ResearchAssessment,
    *,
    prior_attempts: int,
) -> Tuple[float, str, Dict[str, float]]:
    """Other active information gaps with direct uncertainty match."""
    components: Dict[str, float] = {}
    unc = candidate.uncertainty_addressed

    if unc not in assessment.information_gaps:
        return 0.0, "uncertainty_not_active_gap", components
    if candidate.intent in (
        ActionIntent.STOP.value,
        ActionIntent.STOP_SESSION.value,
        ActionIntent.ABANDON.value,
    ):
        return 0.0, "terminal_intent", components

    directness = _directness(unc, candidate, assessment)
    if directness <= 0:
        return 0.0, "not_directly_addressing_gap", components

    redundancy = _redundancy_burden(prior_attempts)
    components["redundancy_burden"] = redundancy
    components["evidence_deficit"] = 1.0
    components["directness"] = directness
    marginal = directness * (1.0 - redundancy) * INFO_VALUE_SCALE
    components["generic_marginal_value"] = marginal
    return marginal, "active_gap_direct_resolution", components


@dataclass(frozen=True)
class ResearchInformationValue:
    """Auditable information-value assessment for one candidate."""

    version: str
    action_id: str
    candidate_tool_name: str
    candidate_intent: str
    uncertainty_code: str
    uncertainty_type: str
    evidence_supporting_uncertainty: Tuple[str, ...]
    can_directly_address: bool
    prior_resolution_attempts: int
    redundancy_burden: float
    evidence_deficit: float
    directness: float
    falsification_relevance: float
    heterogeneity_relevance: float
    estimated_uncertainty_reduction: float
    valuation_contribution: float
    contribution_reason: str
    contribution_zero_reason: str
    pathway_components: Dict[str, float] = field(default_factory=dict)
    built_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "action_id": self.action_id,
            "candidate_tool_name": self.candidate_tool_name,
            "candidate_intent": self.candidate_intent,
            "uncertainty_code": self.uncertainty_code,
            "uncertainty_type": self.uncertainty_type,
            "evidence_supporting_uncertainty": list(self.evidence_supporting_uncertainty),
            "can_directly_address": self.can_directly_address,
            "prior_resolution_attempts": self.prior_resolution_attempts,
            "redundancy_burden": self.redundancy_burden,
            "evidence_deficit": self.evidence_deficit,
            "directness": self.directness,
            "falsification_relevance": self.falsification_relevance,
            "heterogeneity_relevance": self.heterogeneity_relevance,
            "estimated_uncertainty_reduction": self.estimated_uncertainty_reduction,
            "valuation_contribution": self.valuation_contribution,
            "contribution_reason": self.contribution_reason,
            "contribution_zero_reason": self.contribution_zero_reason,
            "pathway_components": dict(self.pathway_components),
            "built_at": self.built_at,
        }


def assess_research_information_value(
    candidate: ResearchActionCandidate,
    assessment: ResearchAssessment,
    *,
    graph: Any = None,
    experiment_node_id: str = "",
) -> ResearchInformationValue:
    """
    Evidence-based information value for one candidate.

    Does NOT consult competence model or apply competence-match bonuses.
    """
    unc = candidate.uncertainty_addressed or ""
    branch_tools = assessment.branch_tools_attempted
    prior = _prior_resolution_attempts(unc, branch_tools) if unc else 0
    u_type = _uncertainty_type(unc, assessment)

    evidence_support: List[str] = []
    if unc in assessment.information_gaps:
        evidence_support.append(f"information_gap:{unc}")
    if unc in assessment.possible_falsification_targets:
        evidence_support.append(f"falsification_target:{unc}")
    if unc in assessment.unresolved_uncertainties:
        evidence_support.append(f"unresolved:{unc}")

    fals_val, fals_reason, fals_comp = _falsification_pathway(
        candidate, assessment, prior_attempts=prior
    )
    het_val, het_reason, het_comp = _heterogeneity_pathway(
        candidate, assessment, prior_attempts=prior
    )
    gen_val, gen_reason, gen_comp = _generic_gap_pathway(
        candidate, assessment, prior_attempts=prior
    )

    pathways = [
        (fals_val, fals_reason, fals_comp, "falsification"),
        (het_val, het_reason, het_comp, "heterogeneity"),
        (gen_val, gen_reason, gen_comp, "generic_gap"),
    ]
    best_val, best_reason, best_comp, best_name = max(pathways, key=lambda x: x[0])

    directness = max(
        _directness(unc, candidate, assessment),
        fals_comp.get("directness", 0.0),
        het_comp.get("directness", 0.0),
        gen_comp.get("directness", 0.0),
    )
    evidence_deficit = max(
        fals_comp.get("evidence_deficit", 0.0),
        het_comp.get("evidence_deficit", 0.0),
        gen_comp.get("evidence_deficit", 0.0),
    )
    redundancy = max(
        fals_comp.get("redundancy_burden", 0.0),
        het_comp.get("redundancy_burden", 0.0),
        gen_comp.get("redundancy_burden", 0.0),
    )

    merged_comp = {**fals_comp, **het_comp, **gen_comp, "winning_pathway": best_name}

    zero_reason = ""
    if best_val <= 0:
        zero_reason = best_reason or "no_active_uncertainty_for_candidate"

    can_direct = directness > 0 and evidence_deficit > 0

    return ResearchInformationValue(
        version=RESEARCH_INFORMATION_VALUE_VERSION,
        action_id=candidate.action_id,
        candidate_tool_name=candidate.tool_name or "",
        candidate_intent=candidate.intent,
        uncertainty_code=unc,
        uncertainty_type=u_type,
        evidence_supporting_uncertainty=tuple(evidence_support),
        can_directly_address=can_direct,
        prior_resolution_attempts=prior,
        redundancy_burden=redundancy,
        evidence_deficit=evidence_deficit,
        directness=directness,
        falsification_relevance=fals_val,
        heterogeneity_relevance=het_val,
        estimated_uncertainty_reduction=best_val / max(FALSIFICATION_INFO_SCALE, HETEROGENEITY_INFO_SCALE, INFO_VALUE_SCALE),
        valuation_contribution=best_val,
        contribution_reason=best_reason if best_val > 0 else "",
        contribution_zero_reason=zero_reason,
        pathway_components=merged_comp,
    )


def apply_information_value_bridge(
    base_scores: Dict[str, Tuple[float, Dict[str, float]]],
    *,
    graph: Any,
    assessment: ResearchAssessment,
    candidates: Sequence[ResearchActionCandidate],
    experiment_node_id: Optional[str] = None,
    branch_root_id: str = "",
) -> Tuple[Dict[str, Tuple[float, Dict[str, float]]], List[ResearchInformationValue]]:
    """
    Apply evidence-based information value adjustments to base planner scores.

    Preserves base_planner_score separately in components for audit.
    """
    bridged: Dict[str, Tuple[float, Dict[str, float]]] = {}
    assessments: List[ResearchInformationValue] = []

    for cand in candidates:
        base, comp = base_scores.get(cand.action_id, (0.0, {}))
        riv = assess_research_information_value(
            cand, assessment, graph=graph, experiment_node_id=experiment_node_id or ""
        )
        adjustment = riv.valuation_contribution
        new_comp = {
            **comp,
            "base_planner_score": base,
            "information_value_adjustment": adjustment,
            "information_value_uncertainty_code": riv.uncertainty_code,
            "information_value_pathway": riv.pathway_components.get("winning_pathway", ""),
            "final_planner_score_before_portfolio": base + adjustment,
        }
        for k, v in riv.pathway_components.items():
            if k != "winning_pathway":
                new_comp[f"info_val_{k}"] = v
        bridged[cand.action_id] = (base + adjustment, new_comp)
        assessments.append(riv)

    return bridged, assessments


@dataclass(frozen=True)
class InformationValueSelectionAudit:
    """Counterfactual selection audit for one planning decision."""

    event: str
    timestamp: str
    experiment_node_id: str
    winner_with_bridge: str
    winner_without_bridge: str
    selection_changed: bool
    winner_with_bridge_score: float
    winner_without_bridge_score: float
    scientific_reason: str
    candidate_assessments: Tuple[Dict[str, Any], ...]
    counterfactual_details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "timestamp": self.timestamp,
            "experiment_node_id": self.experiment_node_id,
            "winner_with_bridge": self.winner_with_bridge,
            "winner_without_bridge": self.winner_without_bridge,
            "selection_changed": self.selection_changed,
            "winner_with_bridge_score": self.winner_with_bridge_score,
            "winner_without_bridge_score": self.winner_without_bridge_score,
            "scientific_reason": self.scientific_reason,
            "candidate_assessments": list(self.candidate_assessments),
            "counterfactual_details": dict(self.counterfactual_details),
        }


def _best_candidate_by_score(
    candidates: Sequence[ResearchActionCandidate],
    scores: Dict[str, Tuple[float, Dict[str, float]]],
) -> Tuple[str, float]:
    best_id = ""
    best_score = float("-inf")
    for cand in candidates:
        if cand.blocked:
            continue
        total, _ = scores.get(cand.action_id, (float("-inf"), {}))
        if total > best_score:
            best_score = total
            best_id = cand.action_id
    return best_id, best_score


def build_selection_counterfactual_audit(
    *,
    experiment_node_id: str,
    candidates: Sequence[ResearchActionCandidate],
    base_scores: Dict[str, Tuple[float, Dict[str, float]]],
    bridged_scores: Dict[str, Tuple[float, Dict[str, float]]],
    assessments: Sequence[ResearchInformationValue],
    selected_action_id: str = "",
) -> InformationValueSelectionAudit:
    """Compare winners with and without information-value bridge (planner layer)."""
    w_without, s_without = _best_candidate_by_score(candidates, base_scores)
    w_with, s_with = _best_candidate_by_score(candidates, bridged_scores)
    changed = w_without != w_with

    riv_by_id = {a.action_id: a for a in assessments}
    reason = "selection_unchanged_bridge_components_zero_or_equal"
    if changed:
        riv = riv_by_id.get(w_with)
        if riv and riv.contribution_reason:
            reason = (
                f"Bridge increased information value for {riv.uncertainty_code}: "
                f"{riv.contribution_reason}; marginal contribution={riv.valuation_contribution:.3f}"
            )
        else:
            reason = "bridge_reordered_planner_layer_scores"

    return InformationValueSelectionAudit(
        event="INFORMATION_VALUE_SELECTION_AUDIT",
        timestamp=_utc_now(),
        experiment_node_id=experiment_node_id,
        winner_with_bridge=w_with,
        winner_without_bridge=w_without,
        selection_changed=changed,
        winner_with_bridge_score=s_with,
        winner_without_bridge_score=s_without,
        scientific_reason=reason,
        candidate_assessments=tuple(a.to_dict() for a in assessments),
        counterfactual_details={
            "selected_action_id": selected_action_id,
            "actual_selected_matches_bridge_winner": selected_action_id == w_with or not selected_action_id,
        },
    )


def record_information_value_audit(
    graph: Any,
    audit: InformationValueSelectionAudit,
) -> None:
    trail = list(getattr(graph.session, "research_information_value_audit", None) or [])
    trail.append(audit.to_dict())
    graph.session.research_information_value_audit = trail


def validate_no_forbidden_bridge_patterns(source: Any) -> List[str]:
    text = str(source).lower()
    return sorted(t for t in _FORBIDDEN_BRIDGE_TOKENS if t in text)
