"""
BB-CapabilityGapAudit-01 — CF-CG1–10 audit-integrity counterfactuals (examiner-only).
"""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.capability_gap_auditor import (
    audit_process_integrity_delta,
    freeze_policy_hashes,
)
from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.capability_probe import probe_missing_capability
from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.process_integrity_delta import (
    _classify_process_integrity_loss,
    _localize_lifecycle_event,
)
from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.silence_classifier import classify_silence

BENCHMARK_VERSION = "bb_capability_gap_audit_01_v1_3j14"


def _episode_exhausted_package() -> Dict[str, Any]:
    return {
        "disposition": "NO_FAITHFUL_EXPERIMENT",
        "experiment_ordinal": 3,
        "generator_version": "follow_on_experiment_generator_v1_3j13",
        "objective": {
            "target_null_key": "episode_artifact",
            "target_uncertainty": "episode_robustness",
            "selected_action": "SEEK_FALSIFICATION",
        },
        "candidates_considered": [
            {
                "target_null_key": "episode_artifact",
                "scientific_identity": {"cohort_strategy": "counterexample_period_search"},
                "primary_classification": "INADMISSIBLE",
                "rejection_reasons": ["previously_rejected_core_hash", "representation_alias_core_hash_match"],
            },
            {
                "target_null_key": "episode_artifact",
                "scientific_identity": {"cohort_strategy": "episode_holdout_excluding_motivating"},
                "primary_classification": "INADMISSIBLE",
                "rejection_reasons": ["previously_rejected_core_hash"],
            },
        ],
        "rejected": [],
        "deduplicated_candidates": [],
    }


def run_cf_cg_counterfactuals(repo_root: Path) -> Dict[str, Any]:
    cf: Dict[str, Any] = {}

    # CF-CG1 — justified silence not mislabeled capability gap
    c1 = classify_silence(
        package=_episode_exhausted_package(),
        prior_packages=[
            {
                "objective": {"target_null_key": "episode_artifact", "target_uncertainty": "episode_robustness"},
                "selected_candidate_id": "c1",
                "deduplicated_candidates": [
                    {
                        "candidate_id": "c1",
                        "scientific_identity": {"cohort_strategy": "episode_holdout_excluding_motivating"},
                        "primary_classification": "ADMISSIBLE",
                    }
                ],
            }
        ],
    )
    cf["CF-CG1"] = {
        "passed": c1["classification"] in ("JUSTIFIED_SCIENTIFIC_SILENCE", "REDUNDANCY_STOP"),
        "description": "Exhausted episode grammar → justified silence, not capability gap",
        "classification": c1["classification"],
    }

    # CF-CG2 — representational gap detected
    c2 = classify_silence(
        package={
            "disposition": "NO_FAITHFUL_EXPERIMENT",
            "objective": {"target_null_key": "unknown_null_xyz", "target_uncertainty": "x"},
            "candidates_considered": [],
        }
    )
    cf["CF-CG2"] = {
        "passed": c2["classification"] == "CAPABILITY_GAP",
        "description": "Unknown null not in grammar → CAPABILITY_GAP",
        "classification": c2["classification"],
    }

    # CF-CG3 — executable faithful candidate accidentally unreachable
    c3 = classify_silence(
        package={
            "disposition": "NO_FAITHFUL_EXPERIMENT",
            "objective": {
                "target_null_key": "directional_reversal",
                "target_uncertainty": "directional_effect_full_universe",
                "selected_action": "SEEK_FALSIFICATION",
            },
            "candidates_considered": [
                {
                    "target_null_key": "directional_reversal",
                    "scientific_identity": {"cohort_strategy": "full_panel_contrast"},
                    "primary_classification": "INADMISSIBLE",
                    "rejection_reasons": ["not_executable:missing_tool"],
                }
            ],
        }
    )
    cf["CF-CG3"] = {
        "passed": c3["classification"] == "EXECUTABILITY_GAP",
        "description": "Faithful design exists but not executable → EXECUTABILITY_GAP",
        "classification": c3["classification"],
    }

    # CF-CG4 — scoring artifact vs scientific defect (synthetic BLIND-B pattern)
    loss = _classify_process_integrity_loss(
        seed=201,
        blind_class="BLIND-B",
        baseline_reveal={"process_integrity_score": 1.0, "notable_findings": [], "calibration_category": "SILENT"},
        new_reveal={
            "process_integrity_score": 0.5,
            "notable_findings": ["risky_calibration:final_state=SUPPORTED", "possible_artifact_or_confound_overgeneralization"],
            "calibration_category": "UNRESOLVED",
        },
        baseline_journey={"lifecycle_outcome": "BUDGET_EXHAUSTED", "final_epistemic_state": None, "journey_rows": []},
        new_journey={
            "lifecycle_outcome": "SCIENTIFIC_STOP",
            "final_epistemic_state": "SUPPORTED",
            "final_stop_reason": "STOP_LOW_INCREMENTAL",
            "journey_rows": [{}, {"ordinal": 2, "decision_leaving": "STOP"}],
        },
        localization={"divergence_ordinal": 2},
    )
    cf["CF-CG4"] = {
        "passed": loss == "EXPECTED_LONGER_JOURNEY_COST",
        "description": "PI loss from examiner penalties after decision completes, not scientific defect",
        "loss_classification": loss,
    }

    # CF-CG5 — conservative fail-closed vs scientific success
    loss5 = _classify_process_integrity_loss(
        seed=501,
        blind_class="BLIND-E",
        baseline_reveal={"process_integrity_score": 1.0, "notable_findings": []},
        new_reveal={"process_integrity_score": 1.0, "notable_findings": ["fail_closed_termination"]},
        baseline_journey={"lifecycle_outcome": "SCIENTIFIC_STOP", "termination_reason": "STOP_LOW_INCREMENTAL"},
        new_journey={"lifecycle_outcome": "FAILED_CLOSED", "termination_reason": "experiment_3_execution_failed"},
        localization={"divergence_ordinal": 3},
    )
    cf["CF-CG5"] = {
        "passed": loss5 == "CONSERVATIVE_FAIL_CLOSED",
        "description": "FAILED_CLOSED on silence execution attempt classified correctly",
        "loss_classification": loss5,
    }

    # CF-CG6 — examiner probe cannot enter researcher path
    research_root = repo_root / "modules/edge_research/opr_bridge"
    forbidden_imports = ["bb_capability_gap_audit", "capability_probe", "seed_to_blind_class"]
    hits = []
    for name in research_root.glob("*.py"):
        if "bb_" in name.name or name.name.startswith("test_"):
            continue
        blob = name.read_text(encoding="utf-8")
        for tok in forbidden_imports:
            if tok in blob:
                hits.append((name.name, tok))
    cf["CF-CG6"] = {
        "passed": not hits,
        "description": "Examiner audit modules not imported by research runtime",
        "hits": hits,
    }

    # CF-CG7 — process integrity loss localized
    loc = _localize_lifecycle_event(
        baseline_journey={
            "lifecycle_outcome": "BUDGET_EXHAUSTED",
            "journey_rows": [{"ordinal": 1, "decision_leaving": "ACTION"}, {"ordinal": 2, "decision_leaving": None}],
        },
        new_journey={
            "lifecycle_outcome": "SCIENTIFIC_STOP",
            "journey_rows": [{"ordinal": 1, "decision_leaving": "ACTION"}, {"ordinal": 2, "decision_leaving": "STOP", "stop_reason": "STOP_LOW_INCREMENTAL"}],
        },
    )
    cf["CF-CG7"] = {
        "passed": loc.get("divergence_ordinal") == 2 and loc.get("divergence_field") == "decision_leaving",
        "description": "PI delta localized to ordinal 2 decision event",
        "localization": loc,
    }

    # CF-CG8 — FP zero from inability flagged when dominant
    from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.fp_restraint_analysis import (
        analyze_false_positive_restraint,
    )

    fp_all_silent = analyze_false_positive_restraint(
        reveals=[{"false_positive_risk": "LOW", "blind_class": "BLIND-D", "calibration_category": "SILENT", "anonymous_case_id": "x"}] * 12,
        journeys=[{"lifecycle_outcome": "BOOTSTRAP_SILENT", "anonymous_case_id": "x", "final_epistemic_state": None}] * 12,
    )
    cf["CF-CG8"] = {
        "passed": fp_all_silent["flag_fp_zero_from_inability_only"] is True,
        "description": "All-bootstrap-silent suite flags FP-zero-from-inability",
        "flag": fp_all_silent["flag_fp_zero_from_inability_only"],
    }

    # CF-CG9 — anti-loop restraint classification
    c9 = classify_silence(
        package={
            "disposition": "NO_FAITHFUL_EXPERIMENT",
            "objective": {"target_null_key": "directional_reversal", "target_uncertainty": "directional_effect_full_universe"},
            "candidates_considered": [
                {
                    "target_null_key": "directional_reversal",
                    "scientific_identity": {"cohort_strategy": "full_panel_contrast"},
                    "primary_classification": "INADMISSIBLE",
                    "rejection_reasons": ["null_cycling_detected"],
                }
            ],
        }
    )
    cf["CF-CG9"] = {
        "passed": c9["classification"] == "REDUNDANCY_STOP",
        "description": "Null cycling → REDUNDANCY_STOP (anti-loop restraint)",
        "classification": c9["classification"],
    }

    # CF-CG10 — audit ordering invariance
    pkg_a = _episode_exhausted_package()
    pkg_b = copy.deepcopy(pkg_a)
    pkg_b["candidates_considered"] = list(reversed(pkg_b["candidates_considered"]))
    s_a = classify_silence(package=pkg_a)
    s_b = classify_silence(package=pkg_b)
    cf["CF-CG10"] = {
        "passed": s_a["classification"] == s_b["classification"],
        "description": "Candidate ordering does not change silence classification",
    }

    return cf
