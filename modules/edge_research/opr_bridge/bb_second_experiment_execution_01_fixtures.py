"""
Phase 3J.7 — CF-SE1–CF-SE10 counterfactual fixtures for second-experiment execution.

DEVELOPMENT FIREWALL: No hidden benchmark answers or market-edge encoding.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import (
    BBFE_FORBIDDEN,
    _default_executability,
    all_bbfe_cases,
)
from modules.edge_research.opr_bridge.bb_first_experiment_interpretation_01_fixtures import (
    _base_quintile,
    _base_tool_result,
    _synthetic_envelope,
)
from modules.edge_research.opr_bridge.bb_second_experiment_design_01_fixtures import (
    _interpret_decide_design,
)
from modules.edge_research.opr_bridge.first_experiment_executor import (
    FORBIDDEN_ENVELOPE_INTERPRETATION_KEYS,
)
from modules.edge_research.opr_bridge.second_experiment_design_persistence import package_from_dict
from modules.edge_research.opr_bridge.second_experiment_execution_gate import validate_second_execution_eligibility
from modules.edge_research.opr_bridge.second_experiment_execution_records import build_second_execution_envelope
from modules.edge_research.opr_bridge.second_experiment_executor import execute_second_experiment
from modules.edge_research.opr_bridge.second_experiment_novelty_audit import (
    NoveltyDecomposition,
    classify_counterfactual_case,
    decompose_novelty,
)
from modules.edge_research.opr_bridge.second_experiment_records import SecondExperimentDisposition

BENCHMARK_VERSION = "bb_second_experiment_execution_01_v1_3j7"


def assert_bbfsex_firewall(obj: Any) -> None:
    import json

    blob = json.dumps(obj, default=str).lower()
    for tok in BBFE_FORBIDDEN:
        if tok.lower() in blob:
            raise ValueError(f"BB-SecondExperimentExecution firewall violation: {tok}")


def _build_context(
    case: Optional[Dict[str, Any]] = None,
    *,
    surviving_nulls: tuple = ("directional_reversal",),
):
    case = case or next(c for c in all_bbfe_cases() if c["case_id"] == "BBFE-01")
    prop = case["proposition"]
    panel = pd.DataFrame(case["panel_rows"])
    ex = case.get("executability") or _default_executability(case)

    _, decision, design = _interpret_decide_design(case, surviving_nulls=surviving_nulls)
    if design is None or design.package is None:
        raise RuntimeError("No second-experiment design context")
    if design.package.disposition != SecondExperimentDisposition.SELECTED.value:
        raise RuntimeError("Expected SELECTED second-experiment package")

    from modules.edge_research.opr_bridge.first_experiment_pipeline import run_first_experiment_pipeline

    first_pkg = run_first_experiment_pipeline(prop, panel, executability=ex)
    tr = _base_tool_result(cutoff=ex.data_cutoff)
    qm = _base_quintile()
    first_env = _synthetic_envelope(prop=prop, package=first_pkg, tool_result=tr, quintile_metrics=qm)

    return {
        "case": case,
        "prop": prop,
        "panel": panel,
        "executability": ex,
        "first_pkg": first_pkg,
        "first_env": first_env,
        "decision": decision.envelope,
        "design": design,
        "package": design.package,
    }


def _novelty_case_a() -> NoveltyDecomposition:
    return decompose_novelty(
        first_spec={"tool_name": "partition_group_compare", "inputs": {}, "research_scope": {}},
        first_identity={"cohort_strategy": "a", "contrast_relation": "x", "objective_target_uncertainty": "u1",
                        "information_gain_type": "f", "expected_epistemic_consequence_type": "e"},
        first_target_null="episode_artifact",
        first_target_uncertainty="episode_robustness",
        second_spec={"tool_name": "partition_group_compare", "inputs": {}, "research_scope": {}},
        second_identity={"cohort_strategy": "b", "contrast_relation": "y", "objective_target_uncertainty": "u2",
                         "information_gain_type": "f2", "expected_epistemic_consequence_type": "e2"},
        second_target_null="directional_reversal",
        second_target_uncertainty="directional_effect_full_universe",
        row_overlap_fraction=0.977,
    )


def _novelty_case_b() -> NoveltyDecomposition:
    return decompose_novelty(
        first_spec={"tool_name": "partition_group_compare", "inputs": {"partition_column": "rs_spread", "n_groups": 5},
                    "research_scope": {"population_spec": {"kind": "all"}, "outcome_spec": {"field": "t5_return"},
                                         "observation_horizon": 5}},
        first_identity={"cohort_strategy": "full_panel", "contrast_relation": "partition_quintile_contrast",
                        "objective_target_uncertainty": "directional_effect_full_universe",
                        "information_gain_type": "falsify", "expected_epistemic_consequence_type": "falsify_direction"},
        first_target_null="directional_reversal",
        first_target_uncertainty="directional_effect_full_universe",
        second_spec={"tool_name": "partition_group_compare", "inputs": {"partition_column": "rs_spread", "n_groups": 5},
                     "research_scope": {"population_spec": {"kind": "all"}, "outcome_spec": {"field": "t5_return"},
                                        "observation_horizon": 5}},
        second_identity={"cohort_strategy": "full_panel", "contrast_relation": "partition_quintile_contrast",
                         "objective_target_uncertainty": "directional_effect_full_universe",
                         "information_gain_type": "falsify", "expected_epistemic_consequence_type": "falsify_direction"},
        second_target_null="directional_reversal",
        second_target_uncertainty="directional_effect_full_universe",
        row_overlap_fraction=0.977,
    )


def run_cf_se_counterfactuals() -> Dict[str, Any]:
    ctx = _build_context()
    prop = ctx["prop"]
    panel = ctx["panel"]
    ex = ctx["executability"]
    package = ctx["package"]
    decision = ctx["decision"]
    first_env = ctx["first_env"]
    session = "bbfsex-test-session"

    cf: Dict[str, Any] = {}

    # CF-SE1 — Package mutation after freeze
    mut_dict = package.to_dict()
    spec = dict(mut_dict["selected_experiment_spec"])
    scope = dict(spec.get("research_scope") or {})
    pop = dict(scope.get("population_spec") or {})
    pop["kind"] = "filter"
    pop["filter_expr"] = "tampered"
    scope["population_spec"] = pop
    spec["research_scope"] = scope
    mut_dict["selected_experiment_spec"] = spec
    mut_pkg = package_from_dict(mut_dict)
    r1 = execute_second_experiment(
        mut_pkg, prop, panel,
        decision_envelope=decision,
        first_execution=first_env,
        session_id=session,
        executability=ex,
        row_overlap_fraction=0.5,
    )
    cf["CF-SE1"] = {
        "passed": r1.outcome == "NOT_ATTEMPTED" and r1.envelope is None,
        "description": "Population/outcome mutation after freeze → reject",
        "reasons": list(r1.eligibility.reasons),
    }

    # CF-SE2 — Decision mismatch (package null differs from frozen decision intent)
    bad_dict = package.to_dict()
    obj = dict(bad_dict["objective"])
    obj["target_null_key"] = "episode_artifact"
    bad_dict["objective"] = obj
    bad_pkg = package_from_dict(bad_dict)
    r2 = execute_second_experiment(
        bad_pkg, prop, panel,
        decision_envelope=decision,
        first_execution=first_env,
        session_id=session,
        executability=ex,
        row_overlap_fraction=0.5,
    )
    cf["CF-SE2"] = {
        "passed": r2.outcome == "NOT_ATTEMPTED",
        "description": "Package target null differs from frozen ResearchDecision → reject",
        "reasons": list(r2.eligibility.reasons),
    }

    # CF-SE3 — High row overlap / new question (Case A): gate admissible
    decomp_a = _novelty_case_a()
    assert classify_counterfactual_case(
        row_overlap=decomp_a.row_overlap,
        null_target_overlap=decomp_a.null_target_overlap,
        scientific_question_overlap=decomp_a.scientific_question_overlap,
    ).startswith("A_")
    overlap = next(
        c.first_experiment_overlap_fraction
        for c in package.deduplicated_candidates
        if c.candidate_id == package.selected_candidate_id
    )
    elig_a, _ = validate_second_execution_eligibility(
        package, prop, panel,
        decision_envelope=decision,
        executability=ex,
        first_execution=first_env,
        row_overlap_fraction=overlap,
        novelty_decomposition=decomp_a,
    )
    cf["CF-SE3"] = {
        "passed": elig_a.eligibility == "ELIGIBLE"
        and decomp_a.coarse_redundancy_interpretation == "HIGH_SAMPLE_REUSE_NEW_QUESTION",
        "description": "3J.6A Case A — high sample reuse + distinct question admissible at gate",
        "eligibility": elig_a.eligibility,
        "coarse": decomp_a.coarse_redundancy_interpretation,
    }

    # CF-SE4 — High row overlap / same question (Case B)
    decomp_b = _novelty_case_b()
    assert decomp_b.coarse_redundancy_interpretation == "SCIENTIFIC_REDUNDANCY"
    r4 = execute_second_experiment(
        package, prop, panel,
        decision_envelope=decision,
        first_execution=first_env,
        session_id=session,
        executability=ex,
        row_overlap_fraction=0.977,
        novelty_decomposition=decomp_b,
    )
    cf["CF-SE4"] = {
        "passed": r4.outcome == "NOT_ATTEMPTED" and "scientific_redundancy_blocked" in r4.eligibility.reasons,
        "description": "3J.6A Case B — high row overlap + same scientific question blocked",
    }

    # CF-SE5 — Low row overlap / wrong null (Case C context)
    wrong_dict = package.to_dict()
    for c in wrong_dict["deduplicated_candidates"]:
        if c["candidate_id"] == wrong_dict["selected_candidate_id"]:
            c["target_null_key"] = "population_concentration"
    wrong_pkg = package_from_dict(wrong_dict)
    decomp_c = decompose_novelty(
        first_spec={"tool_name": "x", "inputs": {}, "research_scope": {}},
        first_identity={"cohort_strategy": "a", "contrast_relation": "x",
                        "objective_target_uncertainty": "u1", "information_gain_type": "f",
                        "expected_epistemic_consequence_type": "e"},
        first_target_null="episode_artifact",
        first_target_uncertainty="episode_robustness",
        second_spec={"tool_name": "y", "inputs": {}, "research_scope": {}},
        second_identity={"cohort_strategy": "c", "contrast_relation": "z",
                         "objective_target_uncertainty": "u3", "information_gain_type": "f3",
                         "expected_epistemic_consequence_type": "e3"},
        second_target_null="population_concentration",
        second_target_uncertainty="directional_effect_full_universe",
        row_overlap_fraction=0.30,
    )
    r5 = execute_second_experiment(
        wrong_pkg, prop, panel,
        decision_envelope=decision,
        first_execution=first_env,
        session_id=session,
        executability=ex,
        row_overlap_fraction=0.30,
        novelty_decomposition=decomp_c,
    )
    cf["CF-SE5"] = {
        "passed": r5.outcome == "NOT_ATTEMPTED",
        "description": "3J.6A Case C — wrong null under low overlap context blocked",
        "reasons": list(r5.eligibility.reasons),
    }

    # CF-SE6 — Tool convenience: no substitution
    selected_tool = (package.selected_experiment_spec or {}).get("tool_name")
    alt_tool = "partition_group_compare" if selected_tool != "partition_group_compare" else "nonexistent_tool_xyz"
    r6 = execute_second_experiment(
        package, prop, panel,
        decision_envelope=decision,
        first_execution=first_env,
        session_id=session,
        executability=ex,
        row_overlap_fraction=overlap,
        requested_tool_override=alt_tool,
    )
    cf["CF-SE6"] = {
        "passed": r6.outcome == "NOT_ATTEMPTED" and not r6.substitution_occurred,
        "description": "Alternative easier tool invocation rejected — no semantic substitution",
        "selected_tool": selected_tool,
        "override_tool": alt_tool,
    }

    # CF-SE7 — Duplicate execution idempotency (real panel when available)
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    repo_prop = repo_root / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/02_frozen_proposition.json"
    repo_panel = repo_root / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
    repo_exec = repo_root / "diagnostics/phase_3j4_evidence_interpretation/artifacts/05_persisted_3j3_execution_envelope.json"
    repo_j2 = repo_root / "diagnostics/phase_3j2_first_experiment_selection/artifacts/03_real_proposition_diagnostic.json"
    repo_contract = repo_root / "diagnostics/phase_3i7_minimal_lifecycle/artifacts/03_interpretation_contract.json"
    if all(p.exists() for p in (repo_prop, repo_panel, repo_exec, repo_j2, repo_contract)):
        from diagnostics.phase_3j4_evidence_interpretation.run_phase_3j4 import _package_stub_from_persisted_execution
        from modules.edge_research.opr_bridge.first_experiment_contract_freeze import frozen_ref_from_historical_contract_artifact
        from modules.edge_research.opr_bridge.production_first_experiment_interpretation import run_production_first_experiment_interpretation
        from modules.edge_research.opr_bridge.production_first_experiment_research_decision import run_production_first_experiment_research_decision
        from modules.edge_research.opr_bridge.production_second_experiment_design import run_production_second_experiment_design
        from modules.edge_research.opr_bridge.first_experiment_execution_persistence import envelope_from_dict

        real_prop = json.loads(repo_prop.read_text())["full_record"]
        real_panel = pd.read_csv(repo_panel)
        execution_dict = json.loads(repo_exec.read_text())
        j2_package = json.loads(repo_j2.read_text())["package"]
        hist_contract = json.loads(repo_contract.read_text())
        package_dict = _package_stub_from_persisted_execution(execution_dict, j2_package)
        frozen_ref = frozen_ref_from_historical_contract_artifact(
            hist_contract,
            package_id=execution_dict["package_id"],
            experiment_content_hash=execution_dict["experiment_content_hash"],
            scientific_action_core_hash=execution_dict["scientific_action_core_hash"],
        )
        ix = run_production_first_experiment_interpretation(
            real_prop, session_id=session + "-real", package_dict=package_dict,
            execution_dict=execution_dict, frozen_contract_dict=frozen_ref.to_dict(),
        )
        dx = run_production_first_experiment_research_decision(
            real_prop, session_id=session + "-real", package_dict=package_dict,
            interpretation_dict=ix.interpretation.envelope.to_dict(),
        )
        sx = run_production_second_experiment_design(
            real_prop, real_panel, session_id=session + "-real",
            package_dict=package_dict, execution_dict=execution_dict,
            interpretation_dict=ix.interpretation.envelope.to_dict(),
            decision_dict=dx.decision.envelope.to_dict(),
        )
        real_pkg = sx.design.package
        real_decision = dx.decision.envelope
        real_first = envelope_from_dict(execution_dict)
        real_overlap = next(
            c.first_experiment_overlap_fraction
            for c in real_pkg.deduplicated_candidates
            if c.candidate_id == real_pkg.selected_candidate_id
        )
        r7a = execute_second_experiment(
            real_pkg, real_prop, real_panel,
            decision_envelope=real_decision,
            first_execution=real_first,
            session_id=session + "-real",
            row_overlap_fraction=real_overlap,
        )
        r7b = execute_second_experiment(
            r7a.package if r7a.envelope else real_pkg,
            real_prop,
            real_panel,
            decision_envelope=real_decision,
            first_execution=real_first,
            session_id=session + "-real",
            existing_envelope=r7a.envelope,
            row_overlap_fraction=real_overlap,
        )
        cf["CF-SE7"] = {
            "passed": r7a.envelope is not None and r7b.outcome == "IDEMPOTENT_REPLAY",
            "description": "Identical frozen package → idempotent reuse, no duplicate scientific run",
            "first_outcome": r7a.outcome,
            "second_outcome": r7b.outcome,
        }
    else:
        cf["CF-SE7"] = {"passed": True, "description": "Real panel unavailable — skipped", "skipped": True}

    # CF-SE8 — Stale provenance
    stale_prop = copy.deepcopy(prop)
    stale_prop["proposition_id"] = "prop-stale-mismatch"
    r8 = execute_second_experiment(
        package, stale_prop, panel,
        decision_envelope=decision,
        first_execution=first_env,
        session_id=session,
        executability=ex,
        row_overlap_fraction=overlap,
    )
    cf["CF-SE8"] = {
        "passed": r8.outcome == "NOT_ATTEMPTED" and "proposition_id_mismatch" in r8.eligibility.reasons,
        "description": "Dataset/research-state identity mismatch → fail closed",
    }

    # CF-SE9 — Tool semantic contamination: envelope has no epistemic judgment
    from modules.edge_research.opr_bridge.first_experiment_execution_records import ExecutionBindingAudit

    audit_stub = ExecutionBindingAudit(
        scientific_spec_hash="cf",
        execution_spec_hash="cf",
        scientific_action_core_hash="cf",
        population_spec={"kind": "all"},
        outcome_spec={"field": "t5_return", "kind": "compare", "operator": ">", "value": 0.0},
        observation_horizon=5,
        tool_name="partition_group_compare",
        tool_version="v1",
        inputs={"partition_column": "rs_spread", "n_groups": 5},
        binding_notes=("cf-se9",),
    )
    synth_env = build_second_execution_envelope(
        package_id=package.package_id,
        package_hash=package.package_hash,
        research_decision_id=str(decision.research_decision.get("decision_id", "")),
        research_decision_hash=str(decision.research_decision.get("record_hash", "")),
        first_execution_id=first_env.execution_id,
        proposition_id=package.proposition_id,
        proposition_hash=package.proposition_hash,
        session_id=session,
        selected_candidate_id=package.selected_candidate_id or "",
        scientific_action_core_hash="cf",
        experiment_content_hash="cf",
        execution_identity_hash="cf",
        target_null_key=package.objective.target_null_key,
        target_uncertainty=package.objective.target_uncertainty,
        novelty_decomposition=decomp_a.to_dict(),
        binding_audit=audit_stub,
        tool_result={"status": "OK", "sample_size": 100, "metrics": {}},
        tool_result_hash="cf",
        raw_quintile_metrics={"quintile_mean_spread": 0.1},
        panel_provenance_hash="cf",
        execution_outcome="SUCCESS",
    )
    blob = str(synth_env.to_dict()).lower()
    contaminated = any(k in blob for k in FORBIDDEN_ENVELOPE_INTERPRETATION_KEYS)
    cf["CF-SE9"] = {
        "passed": not contaminated
        and synth_env.interpretation_generated is False
        and synth_env.research_decision_generated is False,
        "description": "Execution envelope does not create epistemic judgment",
    }

    # CF-SE10 — Interpretation leakage: executor never generates interpretation/decision
    r10 = execute_second_experiment(
        package, prop, panel,
        decision_envelope=decision,
        first_execution=first_env,
        session_id=session,
        executability=ex,
        row_overlap_fraction=overlap,
    )
    cf["CF-SE10"] = {
        "passed": (
            r10.interpretation_generated is False
            and r10.research_decision_generated is False
        ),
        "description": "Execution path never creates Evidence Interpretation #2 or Research Decision #2",
    }

    cf["all_passed"] = all(v.get("passed") for v in cf.values() if isinstance(v, dict) and "passed" in v)
    cf["benchmark_version"] = BENCHMARK_VERSION
    assert_bbfsex_firewall(cf)
    return cf
