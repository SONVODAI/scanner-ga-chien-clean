"""
Phase 3I.5 — Observation prioritization (research-only, no hidden-answer signals).

Pre-registered lexicographic ranking — no tuned weights from BB-Prop outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from modules.edge_research.opr_bridge.constants import MIN_SYMBOLS_PER_DATE
from modules.edge_research.opr_bridge.observation_entities import ScientificPropositionGroup
from modules.edge_research.opr_bridge.semantic_projection import project_contrast_semantics

PRIORITIZER_VERSION = "opr_prioritizer_v1_3i5"

# Pre-registered signals (justified in diagnostics/phase_3i5/01_prioritization_preregistration.json)
SELECTED_SIGNALS = (
    "evidence_quality_gate",
    "surprise_gate",
    "executability_gate",
    "contradiction_presence",
    "independent_repeated_evidence",
    "surprise_magnitude",
    "contrast_magnitude",
    "historical_rarity",
)

REJECTED_SIGNALS = (
    "chronological_order",
    "hidden_phenomenon_similarity",
    "known_edge_similarity",
    "profitability_labels",
    "template_ids",
    "hard_coded_preferred_feature",
)


@dataclass
class PrioritizationResult:
    """Output of prioritization pass."""

    ranked_groups: List[ScientificPropositionGroup] = field(default_factory=list)
    silenced_groups: List[Dict[str, Any]] = field(default_factory=list)
    gates_failed: List[Dict[str, Any]] = field(default_factory=list)
    rank_keys: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prioritizer_version": PRIORITIZER_VERSION,
            "ranked_groups": [g.to_dict() for g in self.ranked_groups],
            "silenced_groups": self.silenced_groups,
            "gates_failed": self.gates_failed,
            "rank_keys": self.rank_keys,
        }


def _group_rank_key(group: ScientificPropositionGroup) -> Tuple:
    """
    Lexicographic rank key (higher = more scientifically informative).

    Order (pre-registered):
      1. contradiction_present — conflicting evidence deserves investigation
      2. independent_evidence_count — repeated independent support
      3. max_quintile_spread — surprise magnitude
      4. max_abs_empirical_delta — effect/contrast magnitude
      5. max_abs_zscore — historical rarity vs baseline
    """
    spreads = [e.observation_event.evidence.quintile_return_spread for e in group.evidence_events]
    deltas = [abs(e.empirical_delta) for e in group.evidence_events]
    zscores = [abs(e.observation_event.surprise.zscore_vs_baseline) for e in group.evidence_events]

    return (
        1 if group.has_contradiction else 0,
        group.independent_evidence_count,
        max(spreads) if spreads else 0.0,
        max(deltas) if deltas else 0.0,
        max(zscores) if zscores else 0.0,
    )


def _passes_gates(group: ScientificPropositionGroup) -> Tuple[bool, str]:
    """Evidence-quality and executability gates."""
    if not group.evidence_events:
        return False, "NO_EVIDENCE"

    rep = group.representative
    if rep is None:
        return False, "NO_REPRESENTATIVE"

    if not rep.surprise.is_surprising:
        return False, "INSUFFICIENT_SURPRISE"

    if rep.evidence.cross_sectional_n < MIN_SYMBOLS_PER_DATE:
        return False, "INSUFFICIENT_CROSS_SECTION"

    proj = project_contrast_semantics(rep.evidence, rep.surprise)
    if not proj.executability_pass:
        return False, "NOT_EXECUTABLE"

    return True, "PASS"


def prioritize_proposition_groups(
    groups: List[ScientificPropositionGroup],
    *,
    max_unique_propositions: int,
) -> PrioritizationResult:
    """
    Rank proposition groups by expected scientific information value.

    Budget unit = unique scientific proposition (not observation date).
    """
    result = PrioritizationResult()
    eligible: List[Tuple[Tuple, ScientificPropositionGroup]] = []

    for group in groups:
        ok, reason = _passes_gates(group)
        if not ok:
            result.gates_failed.append(
                {"identity_key": group.identity_key, "reason": reason}
            )
            continue

        key = _group_rank_key(group)
        eligible.append((key, group))
        result.rank_keys.append(
            {
                "identity_key": group.identity_key,
                "rank_key": list(key),
                "scientific_question": group.scientific_question,
            }
        )

    eligible.sort(key=lambda x: x[0], reverse=True)

    for i, (_, group) in enumerate(eligible):
        if i < max_unique_propositions:
            result.ranked_groups.append(group)
        else:
            result.silenced_groups.append(
                {
                    "identity_key": group.identity_key,
                    "reason": "BUDGET_EXHAUSTED",
                    "rank_position": i + 1,
                }
            )

    return result
