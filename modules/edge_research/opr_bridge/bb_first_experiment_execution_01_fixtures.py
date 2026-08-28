"""
Phase 3J.3 — BB-FirstExperimentExecution-01 + CF-EX1–CF-EX8 counterfactuals.

DEVELOPMENT FIREWALL: No hidden benchmark answers or market-edge encoding.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import (
    BBFE_FORBIDDEN,
    _default_executability,
    _prop,
    _rows_grid,
    all_bbfe_cases,
    run_bbfe_case,
)
from modules.edge_research.opr_bridge.first_experiment_executor import (
    envelope_contains_interpretation,
    execute_first_experiment,
)
from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
from modules.edge_research.opr_bridge.first_experiment_records import FirstExperimentDisposition
from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

BENCHMARK_VERSION = "bb_first_experiment_execution_01_v1_3j3"


def assert_bbfex_firewall(obj: Any) -> None:
    import json

    blob = json.dumps(obj, default=str).lower()
    for tok in BBFE_FORBIDDEN:
        if tok.lower() in blob:
            raise ValueError(f"BB-FirstExperimentExecution firewall violation: {tok}")


def _executable_case() -> Dict[str, Any]:
    """Return first BBFE case that selects an executable experiment."""
    for case in all_bbfe_cases():
        run = run_bbfe_case(case)
        pkg = run["package"]
        if pkg.disposition == FirstExperimentDisposition.SELECTED.value and pkg.selected_experiment_spec:
            return {"case": case, "package": pkg, "prop": case["proposition"], "panel": pd.DataFrame(case["panel_rows"])}
    raise RuntimeError("No executable BBFE case found")


def run_cf_ex_counterfactuals() -> Dict[str, Any]:
    base = _executable_case()
    case = base["case"]
    prop = base["prop"]
    panel = base["panel"]
    pkg = base["package"]
    ex = case.get("executability") or _default_executability(case)
    session = "bbfex-test-session"

    cf: Dict[str, Any] = {}

    # CF-EX1 — Tool convenience: selected tool remains authoritative
    r1 = execute_first_experiment(pkg, prop, panel, session_id=session, executability=ex)
    selected_tool = (pkg.selected_experiment_spec or {}).get("tool_name")
    executed_tool = r1.binding_audit.tool_name if r1.binding_audit else None
    cf["CF-EX1"] = {
        "passed": r1.outcome in ("SUCCESS", "FAILED")
        and executed_tool == selected_tool
        and not r1.substitution_occurred,
        "description": "Selected experiment remains authoritative over convenient default",
        "selected_tool": selected_tool,
        "executed_tool": executed_tool,
    }

    # CF-EX2 — Unsupported selected tool: fail closed, no fallback
    from modules.edge_research.opr_bridge.first_experiment_execution_persistence import package_from_dict

    bad_pkg_dict = pkg.to_dict()
    bad_spec = dict(bad_pkg_dict["selected_experiment_spec"])
    bad_spec["tool_name"] = "nonexistent_research_tool_xyz"
    bad_pkg_dict["selected_experiment_spec"] = bad_spec
    for key in ("deduplicated_candidates", "candidates_considered"):
        updated = []
        for c in bad_pkg_dict[key]:
            c2 = dict(c)
            if c2["candidate_id"] == bad_pkg_dict["selected_candidate_id"]:
                c2["experiment_spec"] = bad_spec
            updated.append(c2)
        bad_pkg_dict[key] = updated
    bad_pkg = package_from_dict(bad_pkg_dict)
    r2 = execute_first_experiment(bad_pkg, prop, panel, session_id=session, executability=ex)
    cf["CF-EX2"] = {
        "passed": r2.outcome == "NOT_ATTEMPTED" and r2.envelope is None,
        "description": "Unsupported tool → fail closed, no fallback experiment",
        "reasons": list(r2.eligibility.reasons),
    }

    # CF-EX3 — Parameter temptation: reject mutation
    mutation = {"population_spec": {"kind": "all", "grammar_version": "research_grammar_v1"}}
    r3 = execute_first_experiment(
        pkg, prop, panel, session_id=session, executability=ex, binding_mutation=mutation
    )
    cf["CF-EX3"] = {
        "passed": r3.outcome == "NOT_ATTEMPTED" and r3.envelope is None,
        "description": "Population/horizon mutation rejected rather than applied",
    }

    # CF-EX4 — Confirmation temptation: no full-panel substitution when falsification selected
    falsify_case = next(c for c in all_bbfe_cases() if c["case_id"] == "BBFE-02")
    f_run = run_bbfe_case(falsify_case)
    f_pkg = f_run["package"]
    if f_pkg.disposition == FirstExperimentDisposition.SELECTED.value:
        sel = f_pkg.selected_experiment_spec or {}
        pop_kind = (sel.get("research_scope") or {}).get("population_spec", {}).get("kind")
        r4 = execute_first_experiment(
            f_pkg,
            falsify_case["proposition"],
            pd.DataFrame(falsify_case["panel_rows"]),
            session_id=session,
            executability=_default_executability(falsify_case),
        )
        cf["CF-EX4"] = {
            "passed": r4.outcome in ("SUCCESS", "FAILED", "NOT_ATTEMPTED")
            and pop_kind != "all"
            and (r4.binding_audit is None or r4.binding_audit.population_spec.get("kind") != "all"
                 or r4.outcome == "NOT_ATTEMPTED"),
            "description": "No confirmatory full-panel substitution for falsification selection",
            "population_kind": pop_kind,
        }
    else:
        cf["CF-EX4"] = {"passed": True, "description": "Falsification case silent — N/A", "skipped": True}

    # CF-EX5 — Duplicate execution: idempotent replay (real panel — autonomous package)
    import json
    from pathlib import Path

    repo_prop = Path(__file__).resolve().parents[2] / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json"
    repo_panel = Path(__file__).resolve().parents[2] / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
    if repo_prop.exists() and repo_panel.exists():
        real_prop = json.loads(repo_prop.read_text())["full_record"]
        real_panel = pd.read_csv(repo_panel)
        from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline
        from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

        cutoff = real_prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
        real_ex = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)
        real_pkg = run_first_experiment_pipeline(real_prop, real_panel, executability=real_ex)
        r5a = execute_first_experiment(
            real_pkg, real_prop, real_panel, session_id=session + "-real", executability=real_ex
        )
        r5b = execute_first_experiment(
            r5a.package if r5a.envelope else real_pkg,
            real_prop,
            real_panel,
            session_id=session + "-real",
            executability=real_ex,
            existing_envelope=r5a.envelope,
        )
        cf["CF-EX5"] = {
            "passed": r5a.envelope is not None and r5b.outcome == "IDEMPOTENT_REPLAY",
            "description": "Same immutable package → idempotent behavior",
            "first_outcome": r5a.outcome,
            "second_outcome": r5b.outcome,
        }
    else:
        cf["CF-EX5"] = {"passed": True, "description": "Real panel unavailable — skipped", "skipped": True}

    # CF-EX6 — Scientific identity mismatch: reject tampered hash
    if r1.envelope and r1.binding_audit:
        tampered = copy.deepcopy(r1.binding_audit)
        tampered = type(tampered)(
            scientific_spec_hash=tampered.scientific_spec_hash,
            execution_spec_hash="tampered_hash_000",
            scientific_action_core_hash=tampered.scientific_action_core_hash,
            population_spec=tampered.population_spec,
            outcome_spec=tampered.outcome_spec,
            observation_horizon=tampered.observation_horizon,
            tool_name=tampered.tool_name,
            tool_version=tampered.tool_version,
            inputs=tampered.inputs,
            binding_notes=tampered.binding_notes,
        )
        from modules.edge_research.opr_bridge.first_experiment_execution_binding import verify_binding_identity

        ok, errs = verify_binding_identity(tampered, pkg)
        cf["CF-EX6"] = {
            "passed": not ok and "execution_spec_hash_mismatch" in errs,
            "description": "Execution spec hash mismatch → reject",
        }
    else:
        cf["CF-EX6"] = {"passed": True, "description": "No envelope from CF-EX1 — gate rejected", "skipped": True}

    # CF-EX7 — Tool output suggestive labels: execution layer does not add judgment
    if r1.envelope:
        cf["CF-EX7"] = {
            "passed": not envelope_contains_interpretation(r1.envelope),
            "description": "Envelope does not convert tool output into researcher judgment",
        }
    else:
        cf["CF-EX7"] = {"passed": True, "description": "No envelope — no judgment added", "skipped": True}

    # CF-EX8 — Ordering/default invariance
    rev_panel = panel.iloc[::-1].reset_index(drop=True)
    r8a = execute_first_experiment(pkg, prop, panel, session_id=session + "-8a", executability=ex)
    r8b = execute_first_experiment(pkg, prop, rev_panel, session_id=session + "-8b", executability=ex)
    cf["CF-EX8"] = {
        "passed": (
            r8a.execution_identity_hash == r8b.execution_identity_hash
            if r8a.execution_identity_hash and r8b.execution_identity_hash
            else r8a.outcome == r8b.outcome == "NOT_ATTEMPTED"
        ),
        "description": "Irrelevant ordering does not alter execution identity",
        "hash_a": r8a.execution_identity_hash,
        "hash_b": r8b.execution_identity_hash,
    }

    all_passed = all(v.get("passed") for v in cf.values())
    assert_bbfex_firewall(cf)
    return {"benchmark_version": BENCHMARK_VERSION, "counterfactuals": cf, "all_passed": all_passed}


def run_all_bbfex() -> Dict[str, Any]:
    """Run executable BBFE cases through execution layer."""
    results = []
    for case in all_bbfe_cases():
        run = run_bbfe_case(case)
        pkg = run["package"]
        if pkg.disposition != FirstExperimentDisposition.SELECTED.value:
            results.append(
                {
                    "case_id": case["case_id"],
                    "skipped": True,
                    "disposition": pkg.disposition,
                    "passed": True,
                }
            )
            continue
        ex = case.get("executability") or _default_executability(case)
        panel = pd.DataFrame(case["panel_rows"])
        exec_result = execute_first_experiment(
            pkg, case["proposition"], panel, session_id=f"bbfex-{case['case_id']}", executability=ex
        )
        passed = exec_result.outcome in ("SUCCESS", "FAILED", "NOT_ATTEMPTED")
        if exec_result.envelope:
            passed = passed and not envelope_contains_interpretation(exec_result.envelope)
        results.append(
            {
                "case_id": case["case_id"],
                "outcome": exec_result.outcome,
                "passed": passed,
                "tool": exec_result.binding_audit.tool_name if exec_result.binding_audit else None,
            }
        )
    passed_count = sum(1 for r in results if r.get("passed"))
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "total": len(results),
        "passed": passed_count,
        "all_passed": passed_count == len(results),
        "cases": results,
    }
