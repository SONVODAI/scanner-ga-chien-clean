"""
Phase 3I.16 — Executability binding (tools-last).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from modules.edge_research.opr_bridge.scientific_action_context import ActionGenerationContext
from modules.edge_research.opr_bridge.scientific_action_records import (
    ExecutabilityClass,
    RescueRiskClass,
    ScientificActionCore,
)
from modules.edge_research.research_grammar import GRAMMAR_VERSION


def bind_experiment_spec(
    ctx: ActionGenerationContext,
    *,
    core: ScientificActionCore,
    rescue_risk: str,
    tool_override: Optional[str] = None,
    alt_envelope: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], str, str]:
    """Bind representation envelope and ExperimentSpec after scientific action defined."""
    if rescue_risk != RescueRiskClass.PASS.value:
        envelope = alt_envelope or {"tool": "none", "rescue_risk": rescue_risk}
        return None, envelope, ExecutabilityClass.RESCUE_RISK.value, f"Rescue risk: {rescue_risk}"

    tool = tool_override or _select_tool(core, ctx)
    envelope = alt_envelope or _build_envelope(core, ctx, tool)
    spec = _build_spec(core, ctx, tool, envelope)

    exec_class, detail = assess_executability(ctx, core, tool, spec, envelope)
    return spec, envelope, exec_class, detail


def _select_tool(core: ScientificActionCore, ctx: ActionGenerationContext) -> str:
    if ctx.executability.abstract_mode:
        if core.cohort_strategy == "concentration_decomposition":
            return "symbol_decomposition"
        if core.cohort_strategy == "measurement_robustness_check":
            return "measurement_sensitivity"
        if core.cohort_strategy in ("rolling_stability_contrast",):
            return "flux_decomposition"
        return "tier_compare"

    if core.cohort_strategy in ("rolling_stability_contrast",):
        return "date_decomposition"
    return "partition_group_compare"


def _feature_field(ctx: ActionGenerationContext) -> str:
    if ctx.executability.abstract_mode:
        return str(ctx.proposition_record.get("feature", "flux_index"))
    rel = ctx.proposition_record.get("explanatory_relation", {})
    return rel.get("feature_or_contrast") or ctx.proposition_record.get("execution_requirements", {}).get(
        "partition_column", "rs_spread"
    )


def _outcome_field(ctx: ActionGenerationContext) -> str:
    if ctx.executability.abstract_mode:
        return str(ctx.proposition_record.get("outcome", "delta_yield"))
    outcome = ctx.proposition_record.get("outcome", {})
    if isinstance(outcome, dict):
        return outcome.get("field", "t5_return")
    draft = ctx.proposition_record.get("experiment_spec_draft", {})
    return (draft.get("research_scope") or {}).get("outcome_spec", {}).get("field", "t5_return")


def _base_scope(ctx: ActionGenerationContext) -> Dict[str, Any]:
    horizon = int(ctx.proposition_record.get("observation_horizon", 0))
    pop = ctx.proposition_record.get("population_context", {"kind": "all", "grammar_version": GRAMMAR_VERSION})
    outcome_field = _outcome_field(ctx)
    return {
        "population_spec": dict(pop),
        "outcome_spec": {
            "kind": "compare",
            "field": outcome_field,
            "operator": ">",
            "value": 0.0,
            "grammar_version": GRAMMAR_VERSION,
        },
        "observation_horizon": horizon,
    }


def _population_for_strategy(core: ScientificActionCore, ctx: ActionGenerationContext) -> Dict[str, Any]:
    strategy = core.cohort_strategy
    if strategy == "episode_holdout_excluding_motivating":
        return {
            "kind": "filter",
            "field": "trade_date",
            "operator": "not_in",
            "values": list(ctx.motivating_dates),
            "grammar_version": GRAMMAR_VERSION,
        }
    if strategy == "regime_separated_contrast":
        return {
            "kind": "filter",
            "field": "research_market_state",
            "operator": "in",
            "values": ["STRESS"],
            "grammar_version": GRAMMAR_VERSION,
        }
    if strategy == "population_subgroup_contrast":
        return {
            "kind": "filter",
            "field": "research_market_state",
            "operator": "in",
            "values": ["NORMAL"],
            "grammar_version": GRAMMAR_VERSION,
        }
    if strategy == "counterexample_period_search":
        return {
            "kind": "filter",
            "field": "trade_date",
            "operator": "not_in",
            "values": list(ctx.motivating_dates),
            "grammar_version": GRAMMAR_VERSION,
        }
    if strategy == "independent_replication_cohort":
        return {
            "kind": "filter",
            "field": "trade_date",
            "operator": "not_in",
            "values": list(ctx.motivating_dates),
            "grammar_version": GRAMMAR_VERSION,
        }
    if strategy == "contradiction_discriminating_test":
        return {"kind": "all", "grammar_version": GRAMMAR_VERSION}
    return {"kind": "all", "grammar_version": GRAMMAR_VERSION}


def _build_envelope(core: ScientificActionCore, ctx: ActionGenerationContext, tool: str) -> Dict[str, Any]:
    return {
        "tool": tool,
        "cohort_strategy": core.cohort_strategy,
        "feature": _feature_field(ctx),
        "outcome": _outcome_field(ctx),
        "population_spec": _population_for_strategy(core, ctx),
        "syntax": "grammar_v1",
    }


def _build_spec(
    core: ScientificActionCore,
    ctx: ActionGenerationContext,
    tool: str,
    envelope: Dict[str, Any],
) -> Dict[str, Any]:
    scope = _base_scope(ctx)
    scope["population_spec"] = envelope["population_spec"]
    feat = envelope["feature"]
    if tool in ("tier_compare", "partition_group_compare"):
        inputs = {"partition_column": feat, "n_groups": 5}
    elif tool == "date_decomposition":
        inputs = {"horizon": "H3" if ctx.executability.abstract_mode else "T5"}
    elif tool in ("symbol_decomposition", "measurement_sensitivity"):
        inputs = {"feature": feat}
    else:
        inputs = {"partition_column": feat, "n_groups": 5}

    return {
        "tool_name": tool,
        "tool_version": "v1",
        "inputs": inputs,
        "research_scope": scope,
        "data_cutoff_date": ctx.executability.data_cutoff,
    }


def assess_executability(
    ctx: ActionGenerationContext,
    core: ScientificActionCore,
    tool: str,
    spec: Dict[str, Any],
    envelope: Dict[str, Any],
) -> Tuple[str, str]:
    ex = ctx.executability

    if tool not in ex.available_tools:
        return (
            ExecutabilityClass.SCIENTIFICALLY_VALID_NOT_EXECUTABLE.value,
            f"Tool {tool} not in available registry — scientific action preserved",
        )

    if core.cohort_strategy == "concentration_decomposition" and not ex.has_symbol_level:
        return (
            ExecutabilityClass.SCIENTIFICALLY_VALID_NOT_EXECUTABLE.value,
            "Symbol-level decomposition required — no interpreter",
        )

    if core.cohort_strategy == "measurement_robustness_check" and tool == "measurement_sensitivity":
        if "measurement_sensitivity" not in ex.available_tools:
            return (
                ExecutabilityClass.SCIENTIFICALLY_VALID_NOT_EXECUTABLE.value,
                "Measurement sensitivity interpreter unavailable",
            )

    required_cols = {_feature_field(ctx), _outcome_field(ctx), "trade_date"}
    if core.cohort_strategy == "regime_separated_contrast":
        required_cols.add("research_market_state")
    missing = required_cols - ex.panel_columns
    if missing and not ex.abstract_mode:
        return (
            ExecutabilityClass.SCIENTIFICALLY_VALID_NOT_EXECUTABLE.value,
            f"Missing panel columns: {sorted(missing)}",
        )

    if spec.get("data_cutoff_date", "") > "2090-01-01":
        return ExecutabilityClass.INVALID.value, "Invalid leaky cutoff"

    if core.cohort_strategy in ex.panel_columns and core.cohort_strategy == "invalid_leakage":
        return ExecutabilityClass.INVALID.value, "Leakage pattern detected"

    return ExecutabilityClass.SCIENTIFICALLY_VALID_EXECUTABLE.value, f"Tool {tool} binds to {core.cohort_strategy}"


def detect_rescue_risk(ctx: ActionGenerationContext, population_spec: Dict[str, Any]) -> str:
    """Anti-rescue check — mirrors 3I.9 semantics."""
    base_outcome = _outcome_field(ctx)
    if population_spec.get("kind") in ("refine", "widen"):
        return RescueRiskClass.POPULATION_NARROWING.value
    prop_outcome = ctx.proposition_record.get("outcome", {})
    if isinstance(prop_outcome, dict) and population_spec.get("field") != prop_outcome.get("field"):
        return RescueRiskClass.OUTCOME_MUTATION.value
    return RescueRiskClass.PASS.value
