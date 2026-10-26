"""
BB-CapabilityGapAudit-01 Zone D — Process-integrity delta audit (3J.11 vs longer-budget).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

AUDIT_VERSION = "bb_capability_gap_audit_process_integrity_delta_v1_3j14"

LOSS_CLASSIFICATIONS = (
    "REAL_SCIENTIFIC_DEFECT",
    "CONSERVATIVE_FAIL_CLOSED",
    "BUDGET_ARTIFACT",
    "SCORING_ARTIFACT",
    "EXPECTED_LONGER_JOURNEY_COST",
    "UNKNOWN",
)


def _localize_lifecycle_event(
    *,
    baseline_journey: Dict[str, Any],
    new_journey: Dict[str, Any],
) -> Dict[str, Any]:
    """Identify ordinal/stage where journeys diverge."""
    base_rows = baseline_journey.get("journey_rows") or []
    new_rows = new_journey.get("journey_rows") or []
    max_ord = max(len(base_rows), len(new_rows), 0)
    divergence_ordinal = None
    divergence_field = None
    for i in range(max_ord):
        bo = base_rows[i] if i < len(base_rows) else {}
        no = new_rows[i] if i < len(new_rows) else {}
        for field in (
            "decision_leaving",
            "epistemic_state_leaving",
            "chosen_action",
            "stop_reason",
        ):
            if bo.get(field) != no.get(field):
                divergence_ordinal = no.get("ordinal") or bo.get("ordinal") or (i + 1)
                divergence_field = field
                break
        if divergence_ordinal:
            break

    if baseline_journey.get("lifecycle_outcome") != new_journey.get("lifecycle_outcome"):
        return {
            "divergence_ordinal": divergence_ordinal or len(new_rows) or len(base_rows),
            "divergence_stage": "lifecycle_outcome",
            "baseline_outcome": baseline_journey.get("lifecycle_outcome"),
            "new_outcome": new_journey.get("lifecycle_outcome"),
            "divergence_field": divergence_field,
        }
    return {
        "divergence_ordinal": divergence_ordinal,
        "divergence_stage": "decision" if divergence_field else "none",
        "divergence_field": divergence_field,
        "baseline_outcome": baseline_journey.get("lifecycle_outcome"),
        "new_outcome": new_journey.get("lifecycle_outcome"),
    }


def _classify_process_integrity_loss(
    *,
    seed: int,
    blind_class: str,
    baseline_reveal: Dict[str, Any],
    new_reveal: Dict[str, Any],
    baseline_journey: Dict[str, Any],
    new_journey: Dict[str, Any],
    localization: Dict[str, Any],
) -> str:
    delta = new_reveal.get("process_integrity_score", 0) - baseline_reveal.get("process_integrity_score", 0)

    if new_journey.get("lifecycle_outcome") == "FAILED_CLOSED":
        if "experiment_3_execution_failed" in str(new_journey.get("termination_reason", "")):
            return "CONSERVATIVE_FAIL_CLOSED"
        return "CONSERVATIVE_FAIL_CLOSED"

    if delta >= 0:
        return "NO_LOSS"

    new_findings = set(new_reveal.get("notable_findings") or [])
    base_findings = set(baseline_reveal.get("notable_findings") or [])

    if (
        baseline_journey.get("lifecycle_outcome") == "BUDGET_EXHAUSTED"
        and new_journey.get("lifecycle_outcome") == "SCIENTIFIC_STOP"
        and "risky_calibration:final_state=SUPPORTED" in new_findings
        and blind_class in ("BLIND-B", "BLIND-E")
    ):
        return "EXPECTED_LONGER_JOURNEY_COST"

    if "risky_calibration" in str(new_findings) and "risky_calibration" not in str(base_findings):
        if new_reveal.get("calibration_category") != "SILENT":
            return "SCORING_ARTIFACT"

    if baseline_journey.get("final_epistemic_state") is None and new_journey.get("final_epistemic_state"):
        return "EXPECTED_LONGER_JOURNEY_COST"

    if new_journey.get("lifecycle_outcome") == "SCIENTIFIC_STOP" and new_journey.get("final_stop_reason") in (
        "STOP_LOW_INCREMENTAL",
        "STOP_NO_INFORMATIVE_ACTION",
    ):
        return "EXPECTED_LONGER_JOURNEY_COST"

    return "UNKNOWN"


def _lost_dimensions(
    *,
    baseline_score: float,
    new_score: float,
    new_findings: List[str],
) -> List[str]:
    dims: List[str] = []
    if new_score < baseline_score:
        for f in new_findings:
            if f.startswith("risky_calibration"):
                dims.append("risky_calibration_penalty")
            elif f.startswith("possible_artifact"):
                dims.append("artifact_overgeneralization_penalty")
            elif f.startswith("false_discovery"):
                dims.append("false_discovery_penalty")
            elif f.startswith("fail_closed"):
                dims.append("fail_closed_cap")
            elif f.startswith("major_failure"):
                dims.append("major_failure_penalty")
    return dims or (["score_decreased_no_specific_finding"] if new_score < baseline_score else [])


def audit_process_integrity_delta(
    *,
    baseline_cases: List[Dict[str, Any]],
    new_cases: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compare per-case process integrity between baseline (3J.11 budget=2) and longer-budget re-exam.
    """
    by_seed_base = {c["seed"]: c for c in baseline_cases}
    by_seed_new = {c["seed"]: c for c in new_cases}
    rows: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []

    for seed in sorted(by_seed_base.keys()):
        base = by_seed_base[seed]
        new = by_seed_new.get(seed)
        if not new:
            continue
        br = base.get("reveal") or {}
        nr = new.get("reveal") or {}
        bj = base.get("journey") or {}
        nj = new.get("journey") or {}
        orig = float(br.get("process_integrity_score", 0))
        new_score = float(nr.get("process_integrity_score", 0))
        delta = round(new_score - orig, 3)
        localization = _localize_lifecycle_event(baseline_journey=bj, new_journey=nj)
        loss_class = _classify_process_integrity_loss(
            seed=seed,
            blind_class=str(nr.get("blind_class", "")),
            baseline_reveal=br,
            new_reveal=nr,
            baseline_journey=bj,
            new_journey=nj,
            localization=localization,
        )
        row = {
            "seed": seed,
            "anonymous_id": base.get("anonymous_id"),
            "blind_class": nr.get("blind_class"),
            "original_score": orig,
            "new_score": new_score,
            "delta": delta,
            "lost_dimensions": _lost_dimensions(
                baseline_score=orig,
                new_score=new_score,
                new_findings=list(nr.get("notable_findings") or []),
            ),
            "localization": localization,
            "loss_classification": loss_class if delta < 0 else "NO_LOSS",
            "baseline_outcome": bj.get("lifecycle_outcome"),
            "new_outcome": nj.get("lifecycle_outcome"),
            "baseline_final_epistemic": bj.get("final_epistemic_state"),
            "new_final_epistemic": nj.get("final_epistemic_state"),
            "new_findings": nr.get("notable_findings"),
            "baseline_findings": br.get("notable_findings"),
        }
        rows.append(row)
        if delta != 0:
            changed.append(row)

    n = len(rows)
    avg_orig = sum(r["original_score"] for r in rows) / n if n else 0
    avg_new = sum(r["new_score"] for r in rows) / n if n else 0

    return {
        "audit_version": AUDIT_VERSION,
        "case_count": n,
        "avg_original_process_integrity": round(avg_orig, 3),
        "avg_new_process_integrity": round(avg_new, 3),
        "avg_delta": round(avg_new - avg_orig, 3),
        "changed_case_count": len(changed),
        "per_case": rows,
        "changed_cases": changed,
        "explanation_0917": _explain_0917(changed, avg_orig, avg_new),
    }


def _explain_0917(changed: List[Dict[str, Any]], avg_orig: float, avg_new: float) -> str:
    if not changed:
        return f"No per-case changes; average remains {avg_new:.3f}"
    parts = [
        f"Average process integrity dropped from {avg_orig:.3f} to {avg_new:.3f} "
        f"({avg_new - avg_orig:+.3f}) due to {len(changed)} case(s) with score changes."
    ]
    for c in changed:
        parts.append(
            f"Seed {c['seed']} ({c['blind_class']}): {c['original_score']}→{c['new_score']} "
            f"at ordinal {c['localization'].get('divergence_ordinal')} "
            f"({c['loss_classification']}): {', '.join(c['lost_dimensions'])}"
        )
    return " ".join(parts)
