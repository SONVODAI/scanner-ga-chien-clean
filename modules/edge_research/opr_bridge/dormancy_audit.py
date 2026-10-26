"""Phase 3I.19 — Learning-vs-answer leakage audit for dormancy module."""

from __future__ import annotations

import inspect
from typing import Any, Dict


def learning_vs_answer_leakage_audit() -> Dict[str, Any]:
    from modules.edge_research.opr_bridge import dormancy_deriver as dd
    from modules.edge_research.opr_bridge import dormant_research_reopening_evaluator as dre

    sources = inspect.getsource(dd) + inspect.getsource(dre)
    forbidden = [
        "wait for crash",
        "wait for regime",
        "wait x days",
        "t5_return",
        "must reopen when profitable",
        "prefer reopen",
        "NORMAL",
        "STRESS",
        "use zone_c",
        "zone_c_reopen",
    ]
    violations = [f for f in forbidden if f.lower() in sources.lower()]
    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "evidence_derived_reopening": "derive_reopening_conditions" in sources,
        "no_clock_reopening": "CLOCK_ELAPSED" in sources,
        "no_outcome_triggers": "OUTCOME_PROFITABILITY" in sources,
    }


def lifecycle_integration_leakage_audit() -> Dict[str, Any]:
    import inspect
    from modules.edge_research.opr_bridge import lifecycle_dormancy_integration as ldi

    src = inspect.getsource(ldi)
    forbidden = [
        "wait for crash",
        "wait for regime",
        "wait x days",
        "t5_return",
        "must reopen when profitable",
        "reopen t2",
        "prop-efb650d9",
        "use zone_c",
    ]
    violations = [f for f in forbidden if f.lower() in src.lower()]
    reopening_section = src.split("on_research_opportunity_state_changed", 1)
    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "has_dormancy_hook": "on_scientific_frontier_completed" in src,
        "has_reopening_hook": "on_research_opportunity_state_changed" in src,
        "no_auto_experiment_in_reopening_hook": "generate_scientific_actions" not in (reopening_section[1] if len(reopening_section) > 1 else ""),
    }


def lifecycle_integration_recommendation() -> Dict[str, Any]:
    """3I.20: dormancy is now auto-wired downstream of frontier assessment."""
    return {
        "should_integrate_downstream_of": "NO_HIGH_INFORMATION_ACTION",
        "auto_wired_in_this_phase": True,
        "hook": "on_scientific_frontier_completed",
        "reopening_hook": "on_research_opportunity_state_changed",
        "epistemic_state_unchanged_on_dormancy": True,
    }
