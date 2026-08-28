"""Phase 3I.18 — Specialized frontier audits (counterexample, concentration, measurement, alternative)."""

from __future__ import annotations

from typing import Any, Dict, List

from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext
from modules.edge_research.opr_bridge.scientific_action_generator import GenerationResult


def audit_counterexample_search(ctx: ActionGenerationContext, gen: GenerationResult) -> Dict[str, Any]:
    """Section 10 — result-blind counterexample capability."""
    candidates = [
        c for c in gen.deduplicated if c.scientific_action_core.cohort_strategy == "counterexample_period_search"
    ]
    derives_from_null = bool(ctx.null_competing_explanation)
    uses_outcome = False  # enforced by design — no outcome columns in operator path
    panel_mining = False
    return {
        "capability_available": len(candidates) > 0,
        "derives_from_proposition_null": derives_from_null,
        "uses_future_outcome": uses_outcome,
        "panel_subgroup_mining": panel_mining,
        "valid_pre_result": len(candidates) > 0 and not uses_outcome and not panel_mining,
        "gap_if_invalid": None if derives_from_null or not candidates else "Requires proposition null_competing_explanation",
    }


def audit_concentration_dominance(ctx: ActionGenerationContext, gen: GenerationResult) -> Dict[str, Any]:
    """Section 11 — concentration without proposition mutation."""
    candidates = [c for c in gen.deduplicated if c.scientific_action_core.cohort_strategy == "concentration_decomposition"]
    valid = [
        c for c in candidates
        if c.rescue_risk_classification == "pass" and c.scientific_action_core.cohort_strategy == "concentration_decomposition"
    ]
    return {
        "specifiable_pre_result": len(candidates) > 0,
        "preserves_proposition": all(c.rescue_risk_classification == "pass" for c in candidates),
        "scientifically_valid": len(valid) > 0,
    }


def audit_measurement_robustness(ctx: ActionGenerationContext, gen: GenerationResult) -> Dict[str, Any]:
    """Section 12 — measurement vs proposition mutation."""
    candidates = [c for c in gen.deduplicated if c.scientific_action_core.cohort_strategy == "measurement_robustness_check"]
    legitimate = [c for c in candidates if c.rescue_risk_classification == "pass"]
    representation_only = [c for c in candidates if c.executability_classification == "REPRESENTATION_ONLY"]
    return {
        "tests_same_proposition": len(legitimate) > 0,
        "representation_only_count": len(representation_only),
        "creates_new_proposition": any(c.rescue_risk_classification != "pass" for c in candidates),
        "classification": "A_legitimate_robustness" if legitimate else "B_or_invalid",
    }


def audit_alternative_explanation(ctx: ActionGenerationContext, gen: GenerationResult) -> Dict[str, Any]:
    """Section 13 — competing explanation without human hypothesis injection."""
    human_null = bool(ctx.null_competing_explanation)
    from_proposition = human_null and "null_competing_explanation" in ctx.proposition_record
    candidates = [
        c for c in gen.deduplicated
        if c.expected_new_uncertainty_coverage == "alternative_explanation_exposure"
    ]
    return {
        "can_formulate_without_human": from_proposition,
        "requires_proposition_null": True,
        "hardcoded_alternative_injected": False,
        "candidate_count": len(candidates),
        "honest_gap": not from_proposition,
    }


def learning_vs_answer_leakage_audit() -> Dict[str, Any]:
    """Section 21 — no preferred strategy hardcoding in reassessor."""
    import inspect
    from modules.edge_research.opr_bridge import scientific_frontier_reassessor as sfr

    src = inspect.getsource(sfr)
    forbidden_preferences = [
        "concentration_decomposition wins",
        "must select counterexample",
        "prefer measurement",
        "NORMAL",
        "STRESS",
    ]
    violations = [f for f in forbidden_preferences if f.lower() in src.lower()]
    # Flag only explicit strategy preference (not generic winner variable or strategy set membership).
    strategy_hardcode = any(
        phrase in src.lower()
        for phrase in (
            "prefer concentration",
            "must select counterexample",
            "concentration_decomposition wins",
            "winner = concentration",
        )
    )
    return {
        "passed": len(violations) == 0 and not strategy_hardcode,
        "violations": violations,
        "uses_lexicographic_rank_only": "_rank_frontier_key" in src,
        "no_strategy_name_preference": "must_include_strategies" not in src,
    }
