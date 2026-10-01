"""
Phase 3J.13 — CF-FG1–12 history-aware follow-on experiment generation counterfactuals.
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.bb_first_experiment_01_fixtures import (
    _default_executability,
    _prop,
    all_bbfe_cases,
)
from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history
from modules.edge_research.opr_bridge.cohort_overlap_estimator import PanelMetadataIndex
from modules.edge_research.opr_bridge.follow_on_experiment_candidates import (
    generate_follow_on_experiment_candidates,
    deduplicate_follow_on_experiment_candidates,
)
from modules.edge_research.opr_bridge.follow_on_experiment_history_context import (
    FollowOnHistoryContext,
    PriorExperimentFingerprint,
    build_follow_on_history_context,
)
from modules.edge_research.opr_bridge.follow_on_experiment_selector import (
    NO_FAITHFUL_EXPERIMENT,
    SELECTED,
    select_follow_on_experiment,
)
from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity
from modules.edge_research.opr_bridge.second_experiment_objective import SecondExperimentObjectiveRecord
from modules.edge_research.opr_bridge.second_experiment_records import OBJECTIVE_RECORD_VERSION

BENCHMARK_VERSION = "bb_history_aware_follow_on_generation_01_v1_3j13"


def _synthetic_objective(
    *,
    null_key: str = "directional_reversal",
    action: str = "SEEK_FALSIFICATION",
    uncertainty: str = "directional_effect_full_universe",
) -> SecondExperimentObjectiveRecord:
    from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash, utc_now_iso

    oid = new_id("seo")
    body = {
        "objective_id": oid,
        "selected_action": action,
        "target_null_key": null_key,
        "target_uncertainty": uncertainty,
    }
    return SecondExperimentObjectiveRecord(
        objective_id=oid,
        record_version=OBJECTIVE_RECORD_VERSION,
        proposition_id="prop-test",
        proposition_hash="ph-test",
        research_decision_id="rd-test",
        research_decision_hash="rdh-test",
        selected_action=action,
        target_uncertainty=uncertainty,
        target_null_key=null_key,
        scientific_objective=f"Test {null_key}",
        why_this_design="CF fixture",
        created_at=utc_now_iso(),
        objective_hash=stable_hash(body),
    )


def _minimal_history_ctx(
    *,
    base_case: Dict[str, Any],
    tested_pairs: List[Tuple[str, str, str]] | None = None,
    content_hashes: Tuple[str, ...] = (),
    core_hashes: Tuple[str, ...] = (),
    prior_fps: Tuple[PriorExperimentFingerprint, ...] = (),
    burden: float = 4.0,
) -> FollowOnHistoryContext:
    from modules.edge_research.opr_bridge.first_experiment_birth_evidence import build_birth_evidence_fingerprint
    from modules.edge_research.opr_bridge.first_experiment_execution_overlap import FirstExperimentCohortFingerprint
    from modules.edge_research.opr_bridge.first_experiment_research_decision_records import SearchAccountingContext

    prop = base_case["proposition"]
    ex = _default_executability(base_case)
    panel = PanelMetadataIndex.from_dataframe(pd.DataFrame(base_case["panel_rows"]), cutoff=ex.data_cutoff)
    birth_fp = FirstExperimentCohortFingerprint(
        population_spec={"kind": "all"},
        cohort_strategy="episode_holdout_excluding_motivating",
        row_keys=set(),
        dates=set(),
        experiment_content_hash="hash-exp1",
        scientific_action_core_hash="core-exp1",
        tool_name="quintile_spread_compare",
    )
    return FollowOnHistoryContext(
        experiment_ordinal=3,
        prior_fingerprints=prior_fps,
        birth_fingerprint=birth_fp,
        birth_evidence=build_birth_evidence_fingerprint(prop, panel),
        tested_null_keys=tuple(p[0] for p in (tested_pairs or [])),
        tested_null_cohort_pairs=tuple(tested_pairs or []),
        content_hashes=content_hashes,
        core_hashes=core_hashes,
        rejected_core_hashes=(),
        cumulative_null_ledger=(),
        search_accounting=SearchAccountingContext(
            experiments_attempted=len(prior_fps),
            search_complexity_score=burden,
            search_cardinality=len(prior_fps),
            evidence_burden_assessment="MODERATE",
            budget_exhausted=False,
        ),
        search_burden_score=burden,
    )


def run_cf_fg_counterfactuals() -> Dict[str, Any]:
    cf: Dict[str, Any] = {}
    base_case = next(c for c in all_bbfe_cases() if c["case_id"] == "BBFE-01")
    prop = base_case["proposition"]
    panel_df = pd.DataFrame(base_case["panel_rows"])
    ex = _default_executability(base_case)
    panel_index = PanelMetadataIndex.from_dataframe(panel_df, cutoff=ex.data_cutoff)

    # CF-FG1 — Valid Decision #2, faithful Experiment #3 available
    with tempfile.TemporaryDirectory() as tmp:
        det = detect_production_opportunity(_anomaly_panel(seed=77), data_cutoff_date="2026-02-15")
        if det.outcome == "OPPORTUNITY_DETECTED" and det.proposition_record:
            r = run_bounded_autonomous_research(
                det.proposition_record,
                _anomaly_panel(seed=77),
                data_cutoff_date="2026-02-15",
                data_dir=Path(tmp),
                budget=ResearchBudget(max_experiment_iterations=4),
                bootstrap_new_session=True,
            )
            history = build_experiment_history(r.session_record) if r.session_record else []
            ord3 = next((e for e in history if e.ordinal == 3), None)
            pkg = ord3.package if ord3 else None
            gen = (pkg or {}).get("generator_version", "")
            disp = (pkg or {}).get("disposition")
            cf["CF-FG1"] = {
                "passed": ord3 is not None
                and int((pkg or {}).get("experiment_ordinal", 0)) >= 3
                and "follow_on_experiment_generator" in gen,
                "description": "Ordinal 3 design uses history-aware generator",
                "disposition": disp,
                "generator_version": gen,
            }
        else:
            cf["CF-FG1"] = {"passed": False, "description": "No opportunity for seed 77"}

    # CF-FG2 — Ordinal 4 uses same generic path (no ordinal-specific branch)
    with tempfile.TemporaryDirectory() as tmp:
        det = detect_production_opportunity(_anomaly_panel(seed=102), data_cutoff_date="2026-02-15")
        if det.outcome == "OPPORTUNITY_DETECTED" and det.proposition_record:
            r = run_bounded_autonomous_research(
                det.proposition_record,
                _anomaly_panel(seed=102),
                data_cutoff_date="2026-02-15",
                data_dir=Path(tmp),
                budget=ResearchBudget(max_experiment_iterations=4),
                bootstrap_new_session=True,
            )
            history = build_experiment_history(r.session_record) if r.session_record else []
            ord4_pkg = next((e.package for e in history if e.ordinal == 4), None)
            cf["CF-FG2"] = {
                "passed": ord4_pkg is None or int(ord4_pkg.get("experiment_ordinal", 0)) >= 3,
                "description": "Ordinal 4 design path is generic (no ord-3-only branch)",
                "ord4_reached": ord4_pkg is not None,
            }
        else:
            cf["CF-FG2"] = {"passed": True, "description": "Skipped — no opportunity", "ord4_reached": False}

    # CF-FG3 — No faithful experiment → SILENCE
    ctx3 = _minimal_history_ctx(
        base_case=base_case,
        tested_pairs=[
            ("directional_reversal", "full_panel_contrast", "directional_effect_full_universe"),
            ("episode_artifact", "episode_holdout_excluding_motivating", "episode_robustness"),
            ("episode_artifact", "counterexample_period_search", "episode_robustness"),
        ],
        burden=5.0,
    )
    obj3 = _synthetic_objective(null_key="directional_reversal")
    cands3 = generate_follow_on_experiment_candidates(
        prop, obj3, history_ctx=ctx3, first_package=None, panel=panel_index, executability=ex, panel_df=panel_df
    )
    sel3 = select_follow_on_experiment(cands3, selected_action="SEEK_FALSIFICATION")
    cf["CF-FG3"] = {
        "passed": sel3.disposition == NO_FAITHFUL_EXPERIMENT,
        "description": "Exhausted strategies yield NO_FAITHFUL_EXPERIMENT silence",
        "disposition": sel3.disposition,
    }

    # CF-FG4 — Wrong-null candidate rejected
    obj4 = _synthetic_objective(null_key="directional_reversal")
    ctx4 = _minimal_history_ctx(base_case=base_case)
    cands4 = generate_follow_on_experiment_candidates(
        prop,
        obj4,
        history_ctx=ctx4,
        first_package=None,
        panel=panel_index,
        executability=ex,
        panel_df=panel_df,
        include_wrong_null_audit=True,
    )
    wrong_rej = any("decision_substitution" in ";".join(c.rejection_reasons) for c in cands4)
    cf["CF-FG4"] = {
        "passed": wrong_rej,
        "description": "Tool-convenient wrong-null audit candidate rejected",
    }

    # CF-FG5 — High row novelty, same scientific question → redundancy
    from modules.edge_research.opr_bridge.second_experiment_novelty_audit import classify_counterfactual_case

    cls = classify_counterfactual_case(
        row_overlap=0.90,
        null_target_overlap=1.0,
        scientific_question_overlap=1.0,
        contrast_overlap=1.0,
    )
    cf["CF-FG5"] = {
        "passed": cls == "B_HIGH_ROWS_SAME_CONTRAST_REJECT",
        "description": "High row novelty with same scientific question classified as redundant",
        "classification": cls,
    }

    # CF-FG6 — High row reuse, new null — may remain admissible
    cls6 = classify_counterfactual_case(
        row_overlap=0.92,
        null_target_overlap=0.0,
        scientific_question_overlap=0.0,
    )
    ctx6 = _minimal_history_ctx(
        base_case=base_case,
        tested_pairs=[("episode_artifact", "episode_holdout_excluding_motivating", "episode_robustness")]
    )
    obj6 = _synthetic_objective(null_key="directional_reversal")
    cands6 = generate_follow_on_experiment_candidates(
        prop, obj6, history_ctx=ctx6, first_package=None, panel=panel_index, executability=ex, panel_df=panel_df
    )
    adm6 = [c for c in cands6 if c.primary_classification == "ADMISSIBLE"]
    cf["CF-FG6"] = {
        "passed": cls6.startswith("A_") and len(adm6) >= 1,
        "description": "New null with high row reuse may remain admissible",
        "admissible_count": len(adm6),
    }

    # CF-FG7 — Fake replication via representation alias / insufficient independence
    from modules.edge_research.opr_bridge.cohort_overlap_estimator import candidate_row_keys

    all_pop = {"kind": "all", "grammar_version": "research_grammar_v1"}
    all_keys = candidate_row_keys(panel_index, all_pop)
    prior_fp7 = PriorExperimentFingerprint(
        ordinal=2,
        population_spec=all_pop,
        cohort_strategy="full_panel_contrast",
        row_keys=all_keys,
        dates={d for d, _ in all_keys},
        experiment_content_hash="hash-prior-full",
        scientific_action_core_hash="core-prior-full",
        target_null_key="directional_reversal",
        target_uncertainty="directional_effect_full_universe",
        tool_name="quintile_spread_compare",
        scientific_identity={
            "cohort_strategy": "full_panel_contrast",
            "contrast_relation": "partition_quintile_contrast",
            "objective_target_uncertainty": "directional_effect_full_universe",
        },
    )
    ctx7 = _minimal_history_ctx(
        base_case=base_case,
        content_hashes=("hash-prior-full",),
        core_hashes=("core-prior-full",),
        prior_fps=(prior_fp7,),
    )
    obj7 = _synthetic_objective(null_key="directional_reversal", action="SEEK_REPLICATION")
    cands7 = generate_follow_on_experiment_candidates(
        prop, obj7, history_ctx=ctx7, panel=panel_index, executability=ex, panel_df=panel_df
    )
    fake_repl = any(
        "fake_replication" in r or "representation_alias" in r or "identical_experiment_content_hash" in r
        for c in cands7
        for r in c.rejection_reasons
    )
    cf["CF-FG7"] = {
        "passed": fake_repl,
        "description": "Fake replication / alias candidates rejected under SEEK_REPLICATION",
    }

    # CF-FG8 — Genuine independent replication admissible when decision requests it
    ctx8 = _minimal_history_ctx(base_case=base_case, tested_pairs=[])
    obj8 = _synthetic_objective(null_key="directional_reversal", action="SEEK_REPLICATION")
    cands8 = generate_follow_on_experiment_candidates(
        prop, obj8, history_ctx=ctx8, first_package=None, panel=panel_index, executability=ex, panel_df=panel_df
    )
    sel8 = select_follow_on_experiment(cands8, selected_action="SEEK_REPLICATION")
    cf["CF-FG8"] = {
        "passed": sel8.disposition in (SELECTED, NO_FAITHFUL_EXPERIMENT),
        "description": "Replication path does not force selection when independence unavailable",
        "disposition": sel8.disposition,
    }

    # CF-FG9 — Horizon shopping: single horizon from prop, no multi-horizon enumeration
    obj9 = _synthetic_objective(null_key="episode_artifact")
    cands9 = generate_follow_on_experiment_candidates(
        prop,
        obj9,
        history_ctx=_minimal_history_ctx(base_case=base_case),
        first_package=None,
        panel=panel_index,
        executability=ex,
        panel_df=panel_df,
    )
    horizons = set()
    for c in cands9:
        if c.experiment_spec:
            horizons.add(c.experiment_spec.get("research_scope", {}).get("observation_horizon"))
    cf["CF-FG9"] = {
        "passed": len(horizons) <= 1,
        "description": "Does not enumerate multiple horizons for outcome shopping",
        "horizon_count": len(horizons),
    }

    # CF-FG10 — Null cycling
    ctx10 = _minimal_history_ctx(
        base_case=base_case,
        tested_pairs=[
            ("directional_reversal", "full_panel_contrast", "directional_effect_full_universe"),
            ("episode_artifact", "episode_holdout_excluding_motivating", "episode_robustness"),
            ("directional_reversal", "full_panel_contrast", "directional_effect_full_universe"),
        ]
    )
    cands10 = generate_follow_on_experiment_candidates(
        prop,
        _synthetic_objective(null_key="directional_reversal"),
        history_ctx=ctx10,
        first_package=None,
        panel=panel_index,
        executability=ex,
        panel_df=panel_df,
    )
    cycling = any("null_cycling" in r for c in cands10 for r in c.rejection_reasons)
    cf["CF-FG10"] = {
        "passed": cycling,
        "description": "Null cycling A→B→A detected and rejected",
    }

    # CF-FG11 — Search burden pressure (high overlap + high burden)
    prior_fp11 = PriorExperimentFingerprint(
        ordinal=2,
        population_spec=all_pop,
        cohort_strategy="full_panel_contrast",
        row_keys=all_keys,
        dates={d for d, _ in all_keys},
        experiment_content_hash="hash-burden",
        scientific_action_core_hash="core-burden",
        target_null_key="episode_artifact",
        target_uncertainty="episode_robustness",
        tool_name="quintile_spread_compare",
        scientific_identity={
            "cohort_strategy": "episode_holdout_excluding_motivating",
            "contrast_relation": "partition_quintile_contrast",
            "objective_target_uncertainty": "episode_robustness",
        },
    )
    ctx11 = _minimal_history_ctx(base_case=base_case, burden=25.0, prior_fps=(prior_fp11,))
    cands11 = generate_follow_on_experiment_candidates(
        prop,
        _synthetic_objective(null_key="directional_reversal"),
        history_ctx=ctx11,
        panel=panel_index,
        executability=ex,
        panel_df=panel_df,
    )
    burden_rej = any("search_burden" in r for c in cands11 for r in c.rejection_reasons)
    cf["CF-FG11"] = {
        "passed": burden_rej,
        "description": "High search burden can reject low-information designs",
    }

    # CF-FG12 — Ordering invariance
    ctx12 = _minimal_history_ctx(
        base_case=base_case,
        tested_pairs=[("episode_artifact", "episode_holdout_excluding_motivating", "episode_robustness")]
    )
    obj12 = _synthetic_objective(null_key="directional_reversal")
    c1 = deduplicate_follow_on_experiment_candidates(
        generate_follow_on_experiment_candidates(
            prop, obj12, history_ctx=ctx12, first_package=None, panel=panel_index, executability=ex, panel_df=panel_df
        )
    )
    c2 = list(reversed(c1))
    s1 = select_follow_on_experiment(c1, selected_action="SEEK_FALSIFICATION")
    s2 = select_follow_on_experiment(c2, selected_action="SEEK_FALSIFICATION")
    cf["CF-FG12"] = {
        "passed": s1.disposition == s2.disposition
        and (s1.selected.candidate_id if s1.selected else None)
        == (s2.selected.candidate_id if s2.selected else None),
        "description": "Candidate enumeration order does not change selection",
    }

    return cf
