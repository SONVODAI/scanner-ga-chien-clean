"""
Frozen template-independence evaluator — post-generation audit only.

Does NOT modify or regenerate propositions. NOT for generator optimization.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

from modules.edge_research.opr_bridge.constants import (
    TI_SEMANTIC_ADJACENT,
    TI_SEMANTIC_INSTANCE,
    TI_SEMANTIC_REFRAME,
    TI_STRUCTURAL_INSTANCE,
    TI_STRUCTURAL_REFRAME,
)
from modules.edge_research.opr_bridge.proposition_record import (
    PropositionRecord,
    TemplateClassification,
    TemplateIndependenceResult,
)

# Frozen template catalog — question texts from research_actions.py (24 families subset)
# Used ONLY for offline isomorphism audit, never as synthesis input.
FROZEN_TEMPLATE_CATALOG: Tuple[Tuple[str, str, str], ...] = (
    ("UNCERTAIN_TIME_DISTRIBUTION", "DISTRIBUTION_ROBUSTNESS", "Is the observed relationship broadly distributed across dates or concentrated?"),
    ("UNCERTAIN_SYMBOL_DISTRIBUTION", "DISTRIBUTION_ROBUSTNESS", "Is the observed relationship broadly distributed across symbols or dominated by few names?"),
    ("UNCERTAIN_EPISODE_REPLICATION", "DISTRIBUTION_ROBUSTNESS", "Does the relationship replicate across independent market episodes?"),
    ("UNCERTAIN_MARKET_DEPENDENCE", "DISTRIBUTION_ROBUSTNESS", "How does the relationship differ across market states?"),
    ("UNCERTAIN_HORIZON_STABILITY", "HORIZON", "Does the relationship behave consistently across T3/T5/T10?"),
    ("UNCERTAIN_TRAJECTORY_ROLE", "HORIZON", "Does an explicit T0-safe temporal feature partition explain outcome differences?"),
    ("ADAPTIVE_PARTITION", "HORIZON", "Does partitioning by an explanatory feature reveal outcome differences?"),
    ("THRESHOLD_EXPLORATION", "HORIZON", "Does a threshold on an explanatory feature separate outcome distributions?"),
    ("INTERACTION_PARTITION", "HORIZON", "Does an interaction between features explain outcome variation?"),
    ("REPOPULATE_REFINED_COHORT", "HORIZON", "Does the relationship hold within a refined conditional population?"),
    ("REPOPULATE_WIDENED_COHORT", "HORIZON", "Does widening the population preserve or weaken the observed relationship?"),
    ("EVIDENCE_POPULATION_REFINE", "HORIZON", "Does a data-derived conditional population reveal structure?"),
    ("FALSIFY_DATE_ARTIFACT", "FALSIFICATION", "Does the result survive leave-one-date-out removal?"),
    ("FALSIFY_EXTREME_WINNER", "FALSIFICATION", "Does the result survive removal of the largest positive outcome?"),
    ("FALSIFY_SYMBOL_DOMINANCE", "FALSIFICATION", "Does the result survive leave-one-symbol-out removal?"),
    ("HORIZON_ADVANCEMENT", "HORIZON", "Does the relationship persist at a longer forward horizon?"),
    ("FRAME_REFRAME", "HORIZON", "Does reframing population or outcome reveal stable structure?"),
    ("REFRAME_ALTERNATIVE_OUTCOME", "HORIZON", "Does an alternative outcome measure show the same pattern?"),
    ("CATEGORY_POPULATION_REFINE", "HORIZON", "Does category refinement change the observed relationship?"),
    ("THRESHOLD_POPULATION_REFINE", "HORIZON", "Does threshold refinement change the observed relationship?"),
    ("THRESHOLD_NEIGHBORHOOD", "HORIZON", "Does neighboring threshold values show consistent effects?"),
    ("STOP_NO_FURTHER_VALUE", "FALSIFICATION", "Stop this branch — no further investigation warranted."),
    ("ABANDON_FRAGILE", "FALSIFICATION", "Abandon this branch — fragility or contradiction undermines the hypothesis."),
    ("STOP_SESSION_GLOBAL", "FALSIFICATION", "Stop entire research session — global stopping criteria satisfied."),
)

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "does", "do", "how", "what", "if", "or", "and",
        "to", "of", "in", "on", "for", "by", "with", "across", "within", "this", "that",
        "observed", "relationship", "result", "hold", "reveal", "explain", "show",
    }
)


def _tokenize(text: str) -> Set[str]:
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def semantic_similarity(text_a: str, text_b: str) -> float:
    """Frozen v1: Jaccard similarity on token sets — deterministic, no ML API."""
    ta, tb = _tokenize(text_a), _tokenize(text_b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _structural_match_score(record: PropositionRecord, template_id: str, gap_family: str) -> float:
    """Score structural alignment with template family."""
    score = 0.0
    rel = record.explanatory_relation.get("relation_type", "")
    tool_caps = record.execution_requirements.get("required_tool_capabilities", [])
    unc = record.canonical_proposition_core.get("uncertainty_family", "")

    if "partition" in template_id.lower() or "ADAPTIVE" in template_id:
        if "partition_group_compare" in tool_caps:
            score += 0.4
    if gap_family in unc or gap_family in template_id:
        score += 0.3
    if rel in ("predicts", "modulates", "contrasts_with"):
        score += 0.2
    if record.population_context.get("kind") == "all":
        score += 0.1
    return min(1.0, score)


def _gap_family_for_template(template_id: str) -> str:
    for tid, fam, _ in FROZEN_TEMPLATE_CATALOG:
        if tid == template_id:
            return fam
    return "UNKNOWN"


def _new_observational_axis_documented(record: PropositionRecord) -> bool:
    """BC_Q2 cites empirical statistic beyond template default motivation."""
    bc_q2 = next((a for a in record.birth_certificate.answers if a.question_id == "BC_Q2"), None)
    if not bc_q2 or not bc_q2.passed:
        return False
    text = bc_q2.answer.lower()
    numeric_markers = ("z=", "std=", "spread=", "quintile", "baseline", "0.", "1.", "2.", "3.")
    return any(m in text for m in numeric_markers)


def evaluate_template_independence(record: PropositionRecord) -> TemplateIndependenceResult:
    """
    Apply frozen 3I.1 decision tree — evaluation only, never regeneration.
    """
    if not record.observation_provenance.passes_minimum_payload():
        return TemplateIndependenceResult(
            classification=TemplateClassification.INSUFFICIENT_EVIDENCE,
            structural_match_score=0.0,
            semantic_similarity=0.0,
            best_template_match="",
            new_observational_axis_documented=False,
            rationale="observation_provenance fails minimum payload",
        )

    if not record.birth_certificate.all_passed():
        return TemplateIndependenceResult(
            classification=TemplateClassification.INSUFFICIENT_EVIDENCE,
            structural_match_score=0.0,
            semantic_similarity=0.0,
            best_template_match="",
            new_observational_axis_documented=False,
            rationale="birth certificate incomplete",
        )

    composite_text = " ".join(
        [
            record.scientific_question,
            record.motivating_observation,
            record.surprise_or_uncertainty,
        ]
    )

    best_id = ""
    best_sem = 0.0
    best_struct = 0.0
    best_gap = ""
    for tid, gap_fam, qtext in FROZEN_TEMPLATE_CATALOG:
        sem = semantic_similarity(composite_text, qtext)
        struct = _structural_match_score(record, tid, gap_fam)
        combined = 0.6 * sem + 0.4 * struct
        if combined > best_sem * 0.6 + best_struct * 0.4:
            best_id = tid
            best_sem = sem
            best_struct = struct
            best_gap = gap_fam

    new_axis = _new_observational_axis_documented(record)

    if (
        best_struct >= TI_STRUCTURAL_INSTANCE
        and best_sem >= TI_SEMANTIC_INSTANCE
        and not new_axis
    ):
        cls = TemplateClassification.TEMPLATE_INSTANCE
        rationale = f"High structural ({best_struct:.2f}) and semantic ({best_sem:.2f}) match to {best_id}"
    elif (
        best_struct >= TI_STRUCTURAL_REFRAME
        and best_sem >= TI_SEMANTIC_REFRAME
        and best_gap in record.canonical_proposition_core.get("uncertainty_family", "")
        and not new_axis
    ):
        cls = TemplateClassification.TEMPLATE_REFRAME
        rationale = f"Reframe of {best_id} (struct={best_struct:.2f}, sem={best_sem:.2f})"
    elif best_gap in record.canonical_proposition_core.get("uncertainty_family", "") or (
        best_sem >= TI_SEMANTIC_ADJACENT and new_axis
    ):
        cls = TemplateClassification.TEMPLATE_ADJACENT
        rationale = f"Adjacent to {best_id} with documented observational axis (sem={best_sem:.2f})"
    elif best_sem < TI_SEMANTIC_ADJACENT and not best_gap:
        cls = TemplateClassification.SCIENTIFICALLY_NOVEL
        rationale = f"Low semantic overlap (best={best_sem:.2f}, template={best_id})"
    elif best_sem < TI_SEMANTIC_ADJACENT:
        cls = TemplateClassification.SCIENTIFICALLY_NOVEL
        rationale = f"Scientific uncertainty not mapped to catalog (sem={best_sem:.2f})"
    else:
        cls = TemplateClassification.TEMPLATE_ADJACENT
        rationale = f"Related to {best_id} with new empirical axis (sem={best_sem:.2f})"

    return TemplateIndependenceResult(
        classification=cls,
        structural_match_score=best_struct,
        semantic_similarity=best_sem,
        best_template_match=best_id,
        new_observational_axis_documented=new_axis,
        rationale=rationale,
    )
