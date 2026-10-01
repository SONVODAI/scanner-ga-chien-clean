"""
BB-CapabilityGapAudit-01 Zone D — Orchestrator for capability gap audit (examiner-only).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.capability_probe import probe_missing_capability
from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.fp_restraint_analysis import (
    analyze_false_positive_restraint,
)
from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.longer_journey_safety import (
    aggregate_journey_safety,
    audit_journey_safety,
)
from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.process_integrity_delta import (
    audit_process_integrity_delta,
)
from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.silence_classifier import classify_silence
from benchmarks.bb_capability_gap_audit_01.zone_d_examiner.toolbox_coverage_map import build_toolbox_coverage_map

AUDIT_VERSION = "bb_capability_gap_audit_orchestrator_v1_3j14"


def freeze_policy_hashes(repo_root: Path) -> Dict[str, Any]:
    from modules.edge_research.opr_bridge.blind_research_examination_runner import (
        compute_research_policy_hashes,
    )

    extra = [
        "follow_on_experiment_candidates.py",
        "follow_on_experiment_history_context.py",
        "follow_on_experiment_selector.py",
        "second_experiment_pipeline.py",
        "second_experiment_candidates.py",
    ]
    base = compute_research_policy_hashes(repo_root)
    root = repo_root / "modules/edge_research/opr_bridge"
    for name in extra:
        path = root / name
        if path.exists():
            base[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return base


def run_blind_suite(
    repo_root: Path,
    *,
    max_iterations: int,
) -> List[Dict[str, Any]]:
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
    from modules.edge_research.opr_bridge.blind_research_examination_runner import (
        run_blind_research_examination,
    )
    from benchmarks.bb_blind_exam_01.zone_d_examiner.lifecycle_examiner import reveal_and_score

    registry = json.loads(
        (repo_root / "benchmarks/bb_blind_exam_01/zone_b_researcher/case_registry.json").read_text()
    )
    import sys

    zone_c = repo_root / "benchmarks/bb_blind_exam_01/zone_c_examiner"
    sys.path.insert(0, str(zone_c))
    from panel_generator import generate_blind_panel_for_seed

    cases: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        for case in registry["cases"]:
            panel, gt = generate_blind_panel_for_seed(case["seed"])
            frozen = run_blind_research_examination(
                panel,
                anonymous_case_id=case["anonymous_id"],
                data_cutoff_date=case["cutoff"],
                data_dir=data_dir,
                budget=ResearchBudget(max_experiment_iterations=max_iterations),
            )
            reveal = reveal_and_score(
                frozen.to_dict(),
                seed=case["seed"],
                ground_truth=gt.to_dict(),
                reveal_after_hash=frozen.lifecycle_frozen_hash,
            )
            cases.append(
                {
                    "anonymous_id": case["anonymous_id"],
                    "seed": case["seed"],
                    "journey": frozen.to_dict(),
                    "reveal": reveal.to_dict(),
                }
            )
    return cases


def audit_silence_from_production_journey(
    *,
    session_record,
    experiment_ordinal: int = 3,
) -> Optional[Dict[str, Any]]:
    from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history

    history = build_experiment_history(session_record)
    entry = next((e for e in history if e.ordinal == experiment_ordinal), None)
    if not entry or not entry.package:
        return None
    pkg = entry.package
    disp = pkg.get("disposition", "")
    if disp not in ("NO_FAITHFUL_EXPERIMENT", "NO_FAITHFUL_SECOND_EXPERIMENT"):
        return None

    prior_packages = [e.package for e in history if e.package and e.ordinal < experiment_ordinal]
    prior = next((e for e in history if e.ordinal == experiment_ordinal - 1), None)
    prior_decision = prior.decision if prior else None

    classification = classify_silence(
        package=pkg,
        prior_decision=prior_decision,
        prior_packages=[p for p in prior_packages if p],
    )
    exercised = []
    for p in prior_packages:
        if not p:
            continue
        obj = p.get("objective") or {}
        nk = obj.get("target_null_key", "")
        for c in p.get("deduplicated_candidates") or []:
            if c.get("candidate_id") == p.get("selected_candidate_id"):
                cohort = (c.get("scientific_identity") or {}).get("cohort_strategy", "")
                exercised.append((nk, cohort, obj.get("target_uncertainty", "")))

    probe = probe_missing_capability(
        target_null_key=classification["target_null_key"],
        target_uncertainty=classification["target_uncertainty"],
        selected_action=classification["selected_action"],
        exercised_pairs=exercised,
        rejection_reasons=classification["rejection_reasons_aggregate"],
        admissible_count=classification["admissible_count"],
    )
    return {
        "experiment_ordinal": experiment_ordinal,
        "package_disposition": disp,
        "silence_classification": classification,
        "capability_probe": probe,
        "prior_decision_summary": {
            "chosen_action": (prior_decision or {}).get("research_decision", {}).get("chosen_next_action"),
            "decision_kind": (prior_decision or {}).get("decision_kind"),
        },
    }


def run_full_capability_gap_audit(repo_root: Path) -> Dict[str, Any]:
    baseline_path = (
        repo_root / "diagnostics/phase_3j11_blind_autonomous_research/artifacts/03_blind_examination_cases.json"
    )
    baseline_cases = json.loads(baseline_path.read_text()) if baseline_path.exists() else []
    longer_cases = run_blind_suite(repo_root, max_iterations=4)

    pi_delta = audit_process_integrity_delta(baseline_cases=baseline_cases, new_cases=longer_cases)

    safety_reports = [
        audit_journey_safety(c["journey"], seed=c["seed"], blind_class=c["reveal"]["blind_class"])
        for c in longer_cases
    ]
    safety = aggregate_journey_safety(safety_reports)

    fp_analysis = analyze_false_positive_restraint(
        reveals=[c["reveal"] for c in longer_cases],
        journeys=[c["journey"] for c in longer_cases],
    )

    toolbox = build_toolbox_coverage_map()

    # Collect ordinal>=3 silence from longer budget via production path for seeds that fail-closed
    silence_audits: List[Dict[str, Any]] = []
    from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
    from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
    from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity

    import sys

    zone_c = repo_root / "benchmarks/bb_blind_exam_01/zone_c_examiner"
    sys.path.insert(0, str(zone_c))
    from panel_generator import generate_blind_panel_for_seed

    for seed in [501, 502, 601, 602, 77]:
        if seed == 77:
            from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel

            panel = _anomaly_panel(seed=77)
        else:
            panel, _ = generate_blind_panel_for_seed(seed)
        det = detect_production_opportunity(panel, data_cutoff_date="2026-02-15")
        if det.outcome != "OPPORTUNITY_DETECTED":
            continue
        with tempfile.TemporaryDirectory() as tmp:
            r = run_bounded_autonomous_research(
                det.proposition_record,
                panel,
                data_cutoff_date="2026-02-15",
                data_dir=Path(tmp),
                budget=ResearchBudget(max_experiment_iterations=4),
                bootstrap_new_session=True,
            )
        if r.session_record:
            sa = audit_silence_from_production_journey(session_record=r.session_record, experiment_ordinal=3)
            if sa:
                sa["seed"] = seed
                silence_audits.append(sa)

    return {
        "audit_version": AUDIT_VERSION,
        "process_integrity_delta": pi_delta,
        "longer_journey_safety": safety,
        "false_positive_restraint": fp_analysis,
        "toolbox_coverage_map": toolbox,
        "ordinal_ge3_silence_audits": silence_audits,
        "longer_budget_case_count": len(longer_cases),
    }
