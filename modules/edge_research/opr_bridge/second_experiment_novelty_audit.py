"""
Phase 3J.6A — Scientific novelty / redundancy decomposition (audit-only).

Distinguishes sample reuse from scientific question overlap.
Does NOT change 3J.6 selection semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash


@dataclass(frozen=True)
class NoveltyDecomposition:
    row_overlap: float
    population_overlap: float
    contrast_overlap: float
    outcome_overlap: float
    null_target_overlap: float
    scientific_question_overlap: float
    information_novelty: str
    sample_novelty: str
    scientific_contrast_novelty: str
    coarse_redundancy_interpretation: str
    decomposition_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ROW_OVERLAP": self.row_overlap,
            "POPULATION_OVERLAP": self.population_overlap,
            "CONTRAST_OVERLAP": self.contrast_overlap,
            "OUTCOME_OVERLAP": self.outcome_overlap,
            "NULL_TARGET_OVERLAP": self.null_target_overlap,
            "SCIENTIFIC_QUESTION_OVERLAP": self.scientific_question_overlap,
            "INFORMATION_NOVELTY": self.information_novelty,
            "SAMPLE_NOVELTY": self.sample_novelty,
            "SCIENTIFIC_CONTRAST_NOVELTY": self.scientific_contrast_novelty,
            "coarse_redundancy_interpretation": self.coarse_redundancy_interpretation,
            "decomposition_hash": self.decomposition_hash,
        }


def _scope(spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return dict((spec or {}).get("research_scope") or {})


def _identity(spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not spec:
        return {}
    scope = _scope(spec)
    return {
        "tool": spec.get("tool_name"),
        "inputs": dict(spec.get("inputs") or {}),
        "population": scope.get("population_spec"),
        "outcome": scope.get("outcome_spec"),
        "horizon": scope.get("observation_horizon"),
    }


def _contrast_key(scientific_identity: Dict[str, str], spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ident = _identity(spec)
    return {
        "cohort_strategy": scientific_identity.get("cohort_strategy"),
        "contrast_relation": scientific_identity.get("contrast_relation"),
        "partition_column": (ident.get("inputs") or {}).get("partition_column"),
        "n_groups": (ident.get("inputs") or {}).get("n_groups"),
    }


def _question_key(scientific_identity: Dict[str, str]) -> Dict[str, Any]:
    return {
        "target_uncertainty": scientific_identity.get("objective_target_uncertainty"),
        "information_gain_type": scientific_identity.get("information_gain_type"),
        "expected_epistemic_consequence_type": scientific_identity.get("expected_epistemic_consequence_type"),
    }


def _overlap_bool(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    return 1.0 if a == b else 0.0


def _population_subset_overlap(first_pop: Dict[str, Any], second_pop: Dict[str, Any], *, row_overlap: float) -> float:
    if first_pop == second_pop:
        return 1.0
    if first_pop.get("kind") == "all" and second_pop.get("kind") == "all":
        return 1.0
    if row_overlap >= 0.95 and first_pop != second_pop:
        return row_overlap
    return row_overlap


def _information_novelty(
    *,
    row_overlap: float,
    null_target_overlap: float,
    scientific_question_overlap: float,
    exp1_rows: Optional[int] = None,
    exp2_rows: Optional[int] = None,
) -> str:
    if null_target_overlap >= 1.0 and scientific_question_overlap >= 1.0:
        return "NONE"
    new_rows = None
    if exp1_rows is not None and exp2_rows is not None:
        new_rows = max(exp2_rows - exp1_rows, 0)
    if null_target_overlap == 0.0 and row_overlap >= 0.90:
        if new_rows is not None and new_rows <= 200:
            return "MARGINAL_POPULATION_COMPLETION"
        return "CONTRAST_SHIFT_ON_SUPERSET"
    if row_overlap < 0.50:
        return "HIGH"
    if row_overlap < 0.90:
        return "MODERATE"
    return "LOW"


def decompose_novelty(
    *,
    first_spec: Dict[str, Any],
    first_identity: Dict[str, str],
    first_target_null: str,
    first_target_uncertainty: str,
    second_spec: Dict[str, Any],
    second_identity: Dict[str, str],
    second_target_null: str,
    second_target_uncertainty: str,
    row_overlap_fraction: float,
    first_row_count: Optional[int] = None,
    second_row_count: Optional[int] = None,
) -> NoveltyDecomposition:
    """Audit decomposition — does not affect selection."""
    i1, i2 = _identity(first_spec), _identity(second_spec)
    c1, c2 = _contrast_key(first_identity, first_spec), _contrast_key(second_identity, second_spec)
    q1 = {**_question_key(first_identity), "target_null": first_target_null, "target_uncertainty": first_target_uncertainty}
    q2 = {**_question_key(second_identity), "target_null": second_target_null, "target_uncertainty": second_target_uncertainty}

    contrast_overlap = _overlap_bool(c1, c2)
    outcome_overlap = _overlap_bool(dict(i1.get("outcome") or {}), dict(i2.get("outcome") or {}))
    null_target_overlap = 1.0 if first_target_null == second_target_null else 0.0
    scientific_question_overlap = _overlap_bool(q1, q2)
    population_overlap = _population_subset_overlap(
        dict(i1.get("population") or {}),
        dict(i2.get("population") or {}),
        row_overlap=row_overlap_fraction,
    )

    info = _information_novelty(
        row_overlap=row_overlap_fraction,
        null_target_overlap=null_target_overlap,
        scientific_question_overlap=scientific_question_overlap,
        exp1_rows=first_row_count,
        exp2_rows=second_row_count,
    )

    sample_novelty = "LOW" if row_overlap_fraction >= 0.85 else ("MODERATE" if row_overlap_fraction >= 0.50 else "HIGH")
    sci_contrast = "LOW" if null_target_overlap >= 1.0 and scientific_question_overlap >= 1.0 else (
        "HIGH" if null_target_overlap == 0.0 else "MODERATE"
    )

    if null_target_overlap >= 1.0 and contrast_overlap >= 1.0 and outcome_overlap >= 1.0:
        coarse = "SCIENTIFIC_REDUNDANCY"
    elif row_overlap_fraction >= 0.85 and null_target_overlap == 0.0:
        coarse = "HIGH_SAMPLE_REUSE_NEW_QUESTION"
    elif row_overlap_fraction >= 0.85:
        coarse = "HIGH_FIRST_EXPERIMENT_OVERLAP"
    else:
        coarse = "LOW"

    body = {
        "row_overlap": row_overlap_fraction,
        "null_target_overlap": null_target_overlap,
        "scientific_question_overlap": scientific_question_overlap,
        "contrast_overlap": contrast_overlap,
        "info": info,
    }
    return NoveltyDecomposition(
        row_overlap=row_overlap_fraction,
        population_overlap=population_overlap,
        contrast_overlap=contrast_overlap,
        outcome_overlap=outcome_overlap,
        null_target_overlap=null_target_overlap,
        scientific_question_overlap=scientific_question_overlap,
        information_novelty=info,
        sample_novelty=sample_novelty,
        scientific_contrast_novelty=sci_contrast,
        coarse_redundancy_interpretation=coarse,
        decomposition_hash=stable_hash(body),
    )


def classify_counterfactual_case(
    *,
    row_overlap: float,
    null_target_overlap: float,
    scientific_question_overlap: float,
    contrast_overlap: float = 1.0,
) -> str:
    """A/B/C conceptual classification for audit sanity checks."""
    if null_target_overlap >= 1.0 and scientific_question_overlap >= 1.0 and contrast_overlap >= 1.0:
        return "B_HIGH_ROWS_SAME_CONTRAST_REJECT"
    if null_target_overlap == 0.0 and row_overlap < 0.50:
        return "C_LOW_ROWS_WRONG_QUESTION_CONTEXT"
    if null_target_overlap == 0.0 and row_overlap >= 0.85:
        return "A_HIGH_ROWS_NEW_CONTRAST_ADMISSIBLE"
    if null_target_overlap == 0.0:
        return "A_MODERATE_ROWS_NEW_CONTRAST_ADMISSIBLE"
    return "REVIEW"
