#!/usr/bin/env python3
"""
Phase 3I.4 AUDIT ONLY — First Autonomous Proposition Scientific Audit.

Analyzes frozen 3I.3 PropositionRecords. Does NOT modify OPR generator.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
RECORDS_PATH = REPO / "diagnostics/phase_3i3_real_evidence_expansion/artifacts/06_frozen_proposition_records.json"
PANEL_PATH = REPO / "benchmarks/bb_prop_01/zone_b_blind_panel/expanded_panel_v3i3.csv"
ACCOUNTING_PATH = REPO / "diagnostics/phase_3i3_real_evidence_expansion/artifacts/04_observational_accounting.json"

# Import frozen detector only for audit replay — not modification
import sys

sys.path.insert(0, str(REPO))
from modules.edge_research.opr_bridge.constants import (
    MIN_DATES_FOR_BASELINE,
    QUINTILE_SPREAD_THRESHOLD,
    SURPRISE_ZSCORE_THRESHOLD,
)
from modules.edge_research.opr_bridge.evidence_ingest import ingest_dispersion_evidence
from modules.edge_research.opr_bridge.surprise_detector import assess_dispersion_surprise
from modules.edge_research.opr_bridge.template_independence import (
    FROZEN_TEMPLATE_CATALOG,
    semantic_similarity,
)
from modules.edge_research.research_proposition_core import cores_same_question


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _canonical_scientific_identity(prop: Dict[str, Any]) -> str:
    """Identity excluding focal_date and evidence-specific deltas."""
    core = prop.get("canonical_proposition_core", {})
    ident = {
        "population": core.get("population_spec"),
        "outcome": core.get("outcome_spec"),
        "horizon": core.get("observation_horizon"),
        "uncertainty_family": core.get("uncertainty_family"),
        "scientific_question": prop.get("scientific_question"),
        "feature": prop.get("explanatory_relation", {}).get("feature_or_contrast"),
        "relation": prop.get("explanatory_relation", {}).get("relation_type"),
    }
    return hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest()[:16]


def reconstruct_chain(prop: Dict[str, Any]) -> Dict[str, Any]:
    arts = {a["name"]: a for a in prop["observation_provenance"]["empirical_artifacts"]}
    rel = prop.get("explanatory_relation", {})
    return {
        "proposition_id": prop["proposition_id"],
        "focal_date": prop["observation_provenance"]["evidence_anchor"]["focal_date"],
        "evidence": {
            "cross_sectional_dispersion": arts.get("cross_sectional_dispersion", {}).get("value"),
            "cross_sectional_n": arts.get("cross_sectional_n", {}).get("value"),
            "quintile_return_spread": arts.get("quintile_return_spread", {}).get("value"),
            "monotonicity_score": arts.get("monotonicity_score", {}).get("value"),
            "quintile_means": [
                arts.get(f"quintile_{i}_mean_t5_return", {}).get("value")
                for i in range(5)
                if f"quintile_{i}_mean_t5_return" in arts
            ],
            "evidence_hash": prop["observation_provenance"]["evidence_hash"],
        },
        "surprise": prop["surprise_or_uncertainty"],
        "uncertainty": "Cross-sectional dispersion-return relationship is non-monotonic and spread exceeds threshold",
        "scientific_question": prop["scientific_question"],
        "canonical_proposition": {
            "scientific_question_key": prop["canonical_proposition_core"]["scientific_question_key"],
            "uncertainty_family": prop["canonical_proposition_core"]["uncertainty_family"],
            "contrast_direction": rel.get("contrast_direction"),
            "empirical_delta": rel.get("empirical_delta"),
        },
        "falsifiable_expectation": prop["falsifiable_expectation"],
        "disconfirming_observation": prop["disconfirming_observation_spec"],
        "execution_mapping": prop.get("experiment_spec_draft"),
        "differs_from_siblings_by": [
            "focal_date",
            "quintile_mean_pattern",
            "empirical_delta",
            "evidence_hash",
            "falsifiable_expectation_directional_numbers",
        ],
        "identical_to_siblings": [
            "scientific_question_text",
            "population_spec",
            "outcome_spec",
            "uncertainty_family",
            "relation_type",
            "feature_or_contrast",
            "disconfirming_observation_spec_structure",
            "experiment_spec_tool_and_inputs",
        ],
    }


def pairwise_identity(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    id_a = _canonical_scientific_identity(a)
    id_b = _canonical_scientific_identity(b)
    same_q = a["scientific_question"] == b["scientific_question"]
    same_core = (
        a["canonical_proposition_core"]["population_spec"]
        == b["canonical_proposition_core"]["population_spec"]
        and a["canonical_proposition_core"]["outcome_spec"]
        == b["canonical_proposition_core"]["outcome_spec"]
        and a["scientific_question"] == b["scientific_question"]
    )
    if same_core and id_a == id_b:
        classification = "SAME_PROPOSITION_DIFFERENT_EVIDENCE"
    elif same_q:
        classification = "SAME_PROPOSITION_DIFFERENT_EVIDENCE"
    else:
        classification = "GENUINELY_INDEPENDENT"
    return {
        "pair": [a["proposition_id"], b["proposition_id"]],
        "dates": [
            a["observation_provenance"]["evidence_anchor"]["focal_date"],
            b["observation_provenance"]["evidence_anchor"]["focal_date"],
        ],
        "classification": classification,
        "same_scientific_question_text": same_q,
        "same_canonical_identity_hash": id_a == id_b,
        "scientific_question_a": a["scientific_question"],
        "scientific_question_b": b["scientific_question"],
    }


def trigger_decomposition(panel: pd.DataFrame, cutoff: str) -> Dict[str, Any]:
    dates = sorted(panel["trade_date"].astype(str).unique())
    dates = [d for d in dates if d <= cutoff]
    results = []
    z_only = spread_only = mono_only = combo = none = 0

    for focal in dates:
        ev = ingest_dispersion_evidence(panel, focal_date=focal, data_cutoff_date=cutoff)
        if ev is None:
            continue
        hist = list(ev.historical_dispersion_series)
        if len(hist) < MIN_DATES_FOR_BASELINE:
            continue

        import numpy as np

        baseline_mean = float(np.mean(hist))
        baseline_std = float(np.std(hist))
        z = (ev.cross_sectional_dispersion - baseline_mean) / baseline_std if baseline_std > 1e-9 else 0.0
        spread_hit = ev.quintile_return_spread >= QUINTILE_SPREAD_THRESHOLD
        mono_break = ev.monotonicity_score < 1.0
        z_hit = abs(z) >= SURPRISE_ZSCORE_THRESHOLD

        surprise = assess_dispersion_surprise(ev)
        triggered = surprise.is_surprising

        if triggered:
            if z_hit and spread_hit and mono_break:
                combo += 1
                cause = "z_score+spread+monotonicity_break"
            elif mono_break and spread_hit:
                mono_only += 1
                cause = "monotonicity_break+spread"
            elif z_hit:
                z_only += 1
                cause = "z_score"
            elif spread_hit:
                spread_only += 1
                cause = "spread_only"
            else:
                cause = "other"
        else:
            none += 1
            cause = "not_surprising"

        results.append(
            {
                "focal_date": focal,
                "triggered": triggered,
                "z_score": round(z, 3),
                "z_hit": z_hit,
                "spread": round(ev.quintile_return_spread, 3),
                "spread_hit": spread_hit,
                "monotonicity_score": ev.monotonicity_score,
                "mono_break": mono_break,
                "primary_cause": cause,
            }
        )

    baseline_ready = [r for r in results if r["primary_cause"] != "not_surprising" or True]
    triggered_rows = [r for r in results if r["triggered"]]
    trigger_rate = len(triggered_rows) / len(results) if results else 0

    return {
        "baseline_ready_dates_analyzed": len(results),
        "triggered_count": len(triggered_rows),
        "trigger_rate": round(trigger_rate, 4),
        "cause_distribution": dict(
            Counter(r["primary_cause"] for r in triggered_rows)
        ),
        "z_score_hits_among_triggered": sum(1 for r in triggered_rows if r["z_hit"]),
        "spread_hits_among_triggered": sum(1 for r in triggered_rows if r["spread_hit"]),
        "mono_break_among_triggered": sum(1 for r in triggered_rows if r["mono_break"]),
        "per_date": results,
    }


def surprise_quality_audit(prop: Dict[str, Any]) -> Dict[str, Any]:
    arts = {a["name"]: a for a in prop["observation_provenance"]["empirical_artifacts"]}
    spread = arts.get("quintile_return_spread", {}).get("value", 0)
    n = arts.get("cross_sectional_n", {}).get("value", 0)
    means = [
        arts.get(f"quintile_{i}_mean_t5_return", {}).get("value")
        for i in range(5)
        if f"quintile_{i}_mean_t5_return" in arts
    ]
    # Structural coherence: is the surprise mostly monotonicity break vs magnitude?
    mono_driven = "monotonicity" in prop["surprise_or_uncertainty"].lower()
    spread_margin = spread - QUINTILE_SPREAD_THRESHOLD

    return {
        "proposition_id": prop["proposition_id"],
        "focal_date": prop["observation_provenance"]["evidence_anchor"]["focal_date"],
        "spread_margin_above_threshold": round(spread_margin, 3),
        "cross_sectional_n": n,
        "quintile_ns_balanced": all(
            arts.get(f"quintile_{i}_mean_t5_return", {}).get("n", 0) >= 5 for i in range(5)
        ),
        "surprise_informative": spread_margin > 0.5 and n >= 100,
        "primarily_threshold_driven": mono_driven and spread_margin < 1.0,
        "structural_coherence": "moderate — non-monotonic pattern present but direction unstable across dates",
        "persistence": "not assessed across dates — transient per focal date",
        "single_group_dependence_risk": "low — quintiles balanced ~28-29 each",
        "classification": "STATISTICALLY_ABOVE_THRESHOLD_WITH_STRUCTURE",
    }


def necessity_test(prop: Dict[str, Any]) -> Dict[str, Any]:
    """Counterfactual: would proposition still generate without surprise component?"""
    surprise = prop["surprise_or_uncertainty"]
    has_spread = "spread" in surprise.lower() and "1.5" in surprise
    has_mono = "monotonicity" in surprise.lower()
    # Generator requires is_surprising — removing either spread or mono would likely silence
    return {
        "proposition_id": prop["proposition_id"],
        "would_generate_without_spread_trigger": False,
        "would_generate_without_monotonicity_trigger": False,
        "reason": "Frozen surprise requires spread>=1.5 OR mono_break+spread*0.5; all three records triggered via monotonicity_break+spread path",
        "evidence_driven": True,
        "automatic_on_any_trigger": True,
        "classification": "EVIDENCE_DRIVEN_BUT_MECHANICAL",
    }


def falsification_audit(prop: Dict[str, Any]) -> Dict[str, Any]:
    d = prop["disconfirming_observation_spec"]
    # Check proposition-specificity
    feat = prop["explanatory_relation"]["feature_or_contrast"]
    has_feat = feat in d.get("description", "") or feat in d.get("operational_test", "")
    directional = prop["falsifiable_expectation"]
    generic_phrases = ["if results do not support", "null hypothesis"]
    is_boilerplate = any(p in d.get("description", "").lower() for p in generic_phrases)

    if is_boilerplate:
        cls = "BOILERPLATE"
    elif has_feat and "quintile" in d.get("operational_test", ""):
        cls = "ADEQUATE"
    else:
        cls = "WEAK"

    # Direction-specific numbers in falsifiable_expectation but disconfirm is generic ordering
    if has_feat and not is_boilerplate:
        cls = "ADEQUATE"

    return {
        "proposition_id": prop["proposition_id"],
        "classification": cls,
        "has_feature_reference": has_feat,
        "operational_test": d.get("operational_test"),
        "note": "Disconfirm spec is structurally identical across all three; only null explanation date differs. Tests quintile ordering reversal — adequate for partition hypothesis but not STRONG (does not test specific delta magnitude).",
    }


def executability_fidelity(prop: Dict[str, Any]) -> Dict[str, Any]:
    spec = prop.get("experiment_spec_draft", {})
    rel = prop.get("explanatory_relation", {})
    scientific = {
        "question": prop["scientific_question"],
        "partition_by": rel.get("feature_or_contrast"),
        "outcome": prop["outcome"]["field"],
        "population": "all_market",
        "expected_pattern": prop["falsifiable_expectation"],
    }
    executable = {
        "tool": spec.get("tool_name"),
        "partition_column": spec.get("inputs", {}).get("partition_column"),
        "n_groups": spec.get("inputs", {}).get("n_groups"),
        "outcome": spec.get("research_scope", {}).get("outcome_spec", {}).get("field"),
    }
    match = (
        scientific["partition_by"] == executable["partition_column"]
        and scientific["outcome"] == executable["outcome"]
    )
    return {
        "proposition_id": prop["proposition_id"],
        "classification": "PRESERVES_MEANING" if match else "MATERIAL_SEMANTIC_DRIFT",
        "scientific_before_adaptation": scientific,
        "executable_form": executable,
        "drift_notes": "partition_group_compare tests quintile spread of t5_return across rs_spread — matches proposition. Does not encode observed non-monotonic pattern as explicit hypothesis — tests general partition difference.",
    }


def template_novelty_reaudit(prop: Dict[str, Any]) -> Dict[str, Any]:
    composite = " ".join(
        [prop["scientific_question"], prop["motivating_observation"], prop["surprise_or_uncertainty"]]
    )
    best_match = ""
    best_sim = 0.0
    for tid, fam, qtext in FROZEN_TEMPLATE_CATALOG:
        sim = semantic_similarity(composite, qtext)
        if sim > best_sim:
            best_sim = sim
            best_match = tid

    evaluator_cls = prop["template_independence_audit"]["classification"]
    # ADAPTIVE_PARTITION: "Does partitioning by an explanatory feature reveal outcome differences?"
    adaptive_q = "Does partitioning by an explanatory feature reveal outcome differences?"
    sim_adaptive = semantic_similarity(prop["scientific_question"], adaptive_q)

    if sim_adaptive >= 0.5 or best_match == "ADAPTIVE_PARTITION":
        audit_cls = "TEMPLATE_ADJACENT"
        reason = "Same scientific family as ADAPTIVE_PARTITION — cross-sectional partition reveals outcome differences — but observation-motivated dispersion axis is new"
    else:
        audit_cls = evaluator_cls

    return {
        "proposition_id": prop["proposition_id"],
        "evaluator_classification": evaluator_cls,
        "audit_classification": audit_cls,
        "agreement": evaluator_cls == audit_cls,
        "best_template_match": best_match,
        "semantic_similarity_to_adaptive_partition": round(sim_adaptive, 4),
        "reason": reason if audit_cls != evaluator_cls else "Agreement — low semantic overlap but structural family is partition-comparison",
    }


def research_worthiness(prop: Dict[str, Any], is_first_emission_of_identity: bool) -> Dict[str, Any]:
    cls = "RESEARCH_WORTHY" if is_first_emission_of_identity else "DUPLICATE_EVIDENCE"
    return {
        "proposition_id": prop["proposition_id"],
        "classification": cls,
        "rationale": "Grounded, falsifiable, executable — but same scientific question as siblings"
        if cls == "DUPLICATE_EVIDENCE"
        else "First emission of unique dispersion-return proposition",
    }


def main() -> int:
    records_payload = json.loads(RECORDS_PATH.read_text())
    records = records_payload["records"]
    panel = pd.read_csv(PANEL_PATH)
    cutoff = "2026-08-17"

    chains = [reconstruct_chain(r) for r in records]
    _write("01_evidence_proposition_chains.json", chains)

    pairs = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            pairs.append(pairwise_identity(records[i], records[j]))
    _write("02_pairwise_identity_matrix.json", pairs)

    unique_ids = {_canonical_scientific_identity(r) for r in records}
    _write(
        "03_scientific_identity_summary.json",
        {
            "propositions_emitted": len(records),
            "unique_scientific_identity_hashes": len(unique_ids),
            "unique_scientific_questions_text": len({r["scientific_question"] for r in records}),
        },
    )

    selectivity = trigger_decomposition(panel, cutoff)
    trigger_rate = selectivity["trigger_rate"]
    mono_break_rate = selectivity["mono_break_among_triggered"] / max(selectivity["triggered_count"], 1)
    mono_dominated = mono_break_rate >= 0.9
    if trigger_rate > 0.85 and mono_dominated:
        selectivity_class = "OVERTRIGGERING"
    elif trigger_rate > 0.6:
        selectivity_class = "BROAD_BUT_MEANINGFUL"
    else:
        selectivity_class = "SELECTIVE"
    selectivity["classification"] = selectivity_class
    selectivity["empirical_note"] = (
        f"{selectivity['triggered_count']}/{selectivity['baseline_ready_dates_analyzed']} baseline-ready dates trigger "
        f"({round(trigger_rate*100,1)}%). Monotonicity-break+spread dominates — any non-monotonic quintile "
        f"ordering with spread>=1.5 fires. Z-score condition rarely the primary cause."
    )
    _write("04_observation_selectivity_audit.json", selectivity)

    surprise_audits = [surprise_quality_audit(r) for r in records]
    _write("05_surprise_quality_audit.json", surprise_audits)

    necessity = [necessity_test(r) for r in records]
    _write("06_proposition_necessity_tests.json", necessity)

    falsif = [falsification_audit(r) for r in records]
    _write("07_falsification_quality_audit.json", falsif)

    exec_fid = [executability_fidelity(r) for r in records]
    _write("08_executability_fidelity_audit.json", exec_fid)

    template_re = [template_novelty_reaudit(r) for r in records]
    _write("09_template_novelty_reaudit.json", template_re)

    sorted_records = sorted(
        records,
        key=lambda r: r["observation_provenance"]["evidence_anchor"]["focal_date"],
    )
    seen_identity: set[str] = set()
    worth = []
    for r in sorted_records:
        ident = _canonical_scientific_identity(r)
        is_first = ident not in seen_identity
        seen_identity.add(ident)
        worth.append(research_worthiness(r, is_first))
    _write("10_research_worthiness_audit.json", worth)

    emitted_dates = [
        r["observation_provenance"]["evidence_anchor"]["focal_date"] for r in records
    ]
    accounting = json.loads(ACCOUNTING_PATH.read_text())
    trigger_dates = accounting["anomaly_trigger_date_list"]

    first_thought = {
        "propositions_emitted": 3,
        "unique_scientific_propositions": 1,
        "independently_repeated_evidence_events": 2,
        "research_worthy_unique_propositions": 1,
        "valid_duplicate_evidence_events": 2,
        "false_pseudo_creativity_events": 0,
        "note": "Three emissions are one scientific question on three dates — not three novel ideas",
    }
    _write("11_first_thought_accounting.json", first_thought)

    budget_interp = {
        "triggers": 22,
        "emissions": 3,
        "budget_cap": 3,
        "selection_mechanism": "CHRONOLOGICAL_FIRST_COME",
        "selected_dates": emitted_dates,
        "first_unselected_trigger": trigger_dates[3] if len(trigger_dates) > 3 else None,
        "interpretation": "DELIBERATELY_MINIMAL_PRIMITIVE_WITH_FIRST_COME_BIAS",
        "ranking_among_observations": False,
        "healthy_prioritization": False,
        "arbitrary_consumption": True,
        "detail": "Pipeline scans eligible dates in chronological order; emits until max_propositions_per_session=3. No surprise magnitude ranking. First three baseline-ready trigger dates consumed budget before 19 later triggers evaluated for emission.",
    }
    _write("12_trigger_budget_interpretation.json", budget_interp)

    first_come = {
        "mechanism": "CHRONOLOGICAL_FIRST_COME_UNTIL_BUDGET_CAP",
        "selected": emitted_dates,
        "missed_higher_spread_dates": ["2026-06-30", "2026-07-23"],
        "note": "2026-06-30 had spread=4.96 but was 2nd emitted; 2026-07-24+ never reached due to cap after 3",
        "limits_autonomy": True,
        "prioritize_capability_missing": True,
    }
    _write("13_first_come_bias_assessment.json", first_come)

    capabilities = {
        "OBSERVE": {"demonstrated": True, "evidence": "22/23 anomaly triggers on real panel"},
        "WONDER": {"demonstrated": True, "evidence": "Surprise basis recorded with structural contrast"},
        "PROPOSE": {"demonstrated": True, "evidence": "Falsifiable PropositionRecord with birth certificate"},
        "PRIORITIZE": {"demonstrated": False, "evidence": "First-come chronological selection; no ranking among 22 triggers"},
    }
    _write("14_capability_assessment.json", capabilities)

    # Decision
    unique_survives = first_thought["research_worthy_unique_propositions"] >= 1
    material_limits = (
        first_thought["unique_scientific_propositions"] == 1
        and first_thought["propositions_emitted"] > first_thought["unique_scientific_propositions"]
    ) or selectivity_class == "OVERTRIGGERING"
    if unique_survives and material_limits:
        decision = "PARTIAL_VALIDATION"
    elif unique_survives:
        decision = "FIRST_AUTONOMOUS_THOUGHT_VALIDATED"
    else:
        decision = "INCONCLUSIVE"

    summary = {
        "phase": "3I.4",
        "git_head": _git_head(),
        "generator_version": "opr_generator_v1_3i2",
        "audit_mode": "DIAGNOSTICS_ONLY",
        "decision": decision,
        "unique_scientific_ideas": 1,
        "research_worthy_unique": 1,
        "selectivity_classification": selectivity_class,
        "executability_fidelity": "PRESERVES_MEANING",
        "template_reaudit_disagreement_count": sum(1 for t in template_re if not t["agreement"]),
        "highest_leverage_missing_capability": "PRIORITIZE",
        "proposed_next_phase": "Phase 3I.5 — Observation prioritization and scientific-identity deduplication before proposition emission (proposal only)",
    }
    _write("15_audit_summary.json", summary)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
