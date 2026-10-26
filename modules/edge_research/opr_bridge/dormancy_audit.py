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


def lifecycle_integration_recommendation() -> Dict[str, Any]:
    """
    Audit-only: dormancy should become authoritative downstream of NO_HIGH_INFORMATION_ACTION
    but is NOT auto-wired in this phase (benchmark-only mechanism).
    """
    return {
        "should_integrate_downstream_of": "NO_HIGH_INFORMATION_ACTION",
        "auto_wired_in_this_phase": False,
        "rationale": "Minimal mechanism validated via BB-Dormancy-01 before lifecycle hook wiring",
        "epistemic_state_unchanged_on_dormancy": True,
    }
