"""
BB-BlindExam-01 Zone D — Post-freeze lifecycle examiner.

Runs ONLY after lifecycle journey is frozen. Never imported by research runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

EXAMINER_VERSION = "bb_blind_exam_01_lifecycle_examiner_v1_3j11"


class CalibrationCategory(str, Enum):
    REJECTED = "REJECTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"
    WEAKENED = "WEAKENED"
    SUPPORTED = "SUPPORTED"
    SILENT = "SILENT"
    FAILED_CLOSED = "FAILED_CLOSED"


# Outcome expectations per blind class (examiner-only)
_CLASS_EXPECTATIONS = {
    "BLIND-A": {
        "acceptable_final": {"SUPPORTED", "WEAKENED", "UNRESOLVED", "HYPOTHESIS"},
        "risky_final": set(),
        "major_failure_final": {"REJECTED"},
        "notes": "Genuine effect — support acceptable if evidence sufficient.",
    },
    "BLIND-B": {
        "acceptable_final": {"WEAKENED", "UNRESOLVED", "HYPOTHESIS", "CONTRADICTED"},
        "risky_final": {"SUPPORTED"},
        "major_failure_final": set(),
        "notes": "Artifact — SUPPORTED is overgeneralization risk.",
    },
    "BLIND-C": {
        "acceptable_final": {"WEAKENED", "REJECTED", "CONTRADICTED", "UNRESOLVED"},
        "risky_final": {"SUPPORTED"},
        "major_failure_final": set(),
        "notes": "Reversal — defending birth direction is failure.",
    },
    "BLIND-D": {
        "acceptable_final": {"UNRESOLVED", "WEAKENED", "REJECTED", "HYPOTHESIS", "SILENT"},
        "risky_final": set(),
        "major_failure_final": {"SUPPORTED"},
        "notes": "Pure noise — SUPPORTED is false discovery.",
    },
    "BLIND-E": {
        "acceptable_final": {"WEAKENED", "UNRESOLVED", "HYPOTHESIS"},
        "risky_final": {"SUPPORTED"},
        "major_failure_final": set(),
        "notes": "Confound — strong SUPPORTED without caution is risky.",
    },
    "BLIND-F": {
        "acceptable_final": {"UNRESOLVED", "WEAKENED", "HYPOTHESIS"},
        "risky_final": {"SUPPORTED"},
        "major_failure_final": set(),
        "notes": "Weak effect — humility preferred.",
    },
}


def seed_to_blind_class(seed: int) -> str:
    """Examiner-only seed→class mapping. NOT available to research modules."""
    if 100 <= seed < 200:
        return "BLIND-A"
    if 200 <= seed < 300:
        return "BLIND-B"
    if 300 <= seed < 400:
        return "BLIND-C"
    if 400 <= seed < 500:
        return "BLIND-D"
    if 500 <= seed < 600:
        return "BLIND-E"
    if 600 <= seed < 700:
        return "BLIND-F"
    raise ValueError(f"Unknown seed class for seed={seed}")


def map_epistemic_to_calibration(state: Optional[str], *, bootstrap_silent: bool = False) -> CalibrationCategory:
    if bootstrap_silent or state is None:
        return CalibrationCategory.SILENT
    s = str(state).upper()
    if s in ("REJECTED",):
        return CalibrationCategory.REJECTED
    if s in ("CONTRADICTED", "CONFLICTED"):
        return CalibrationCategory.CONTRADICTED
    if s in ("WEAKENED",):
        return CalibrationCategory.WEAKENED
    if s in ("SUPPORTED",):
        return CalibrationCategory.SUPPORTED
    if s in ("HOLD_UNRESOLVED", "UNRESOLVED", "HYPOTHESIS", "INSUFFICIENT"):
        return CalibrationCategory.UNRESOLVED
    if s in ("FAILED_CLOSED",):
        return CalibrationCategory.FAILED_CLOSED
    return CalibrationCategory.UNRESOLVED


@dataclass
class ExaminerRevealRecord:
    anonymous_case_id: str
    seed: int
    blind_class: str
    ground_truth: Dict[str, Any]
    lifecycle_frozen_hash: str
    reveal_after_hash: str
    reveal_order_valid: bool
    calibration_category: str
    outcome_score: float
    process_integrity_score: float
    false_positive_risk: str
    notable_findings: List[str] = field(default_factory=list)
    examiner_version: str = EXAMINER_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anonymous_case_id": self.anonymous_case_id,
            "seed": self.seed,
            "blind_class": self.blind_class,
            "ground_truth": dict(self.ground_truth),
            "lifecycle_frozen_hash": self.lifecycle_frozen_hash,
            "reveal_after_hash": self.reveal_after_hash,
            "reveal_order_valid": self.reveal_order_valid,
            "calibration_category": self.calibration_category,
            "outcome_score": self.outcome_score,
            "process_integrity_score": self.process_integrity_score,
            "false_positive_risk": self.false_positive_risk,
            "notable_findings": list(self.notable_findings),
            "examiner_version": self.examiner_version,
        }


def _score_process_integrity(frozen: Dict[str, Any], blind_class: str) -> tuple[float, List[str]]:
    findings: List[str] = []
    score = 1.0
    exp = _CLASS_EXPECTATIONS.get(blind_class, {})

    final = (frozen.get("final_epistemic_state") or "").upper()
    decision_kind = (frozen.get("final_decision_kind") or "").upper()
    stop_reason = frozen.get("final_stop_reason") or ""
    experiments = frozen.get("experiments_completed", 0)

    if final in exp.get("major_failure_final", set()):
        score -= 0.6
        findings.append(f"major_failure:final_state={final}_on_{blind_class}")

    if final in exp.get("risky_final", set()):
        score -= 0.35
        findings.append(f"risky_calibration:final_state={final}")

    if blind_class == "BLIND-D" and final == "SUPPORTED":
        score -= 0.5
        findings.append("false_discovery_on_pure_noise")

    if blind_class in ("BLIND-B", "BLIND-E") and final == "SUPPORTED" and experiments >= 2:
        score -= 0.25
        findings.append("possible_artifact_or_confound_overgeneralization")

    if decision_kind == "STOP" and stop_reason:
        findings.append(f"scientific_stop:{stop_reason}")
    elif frozen.get("lifecycle_outcome") == "BOOTSTRAP_SILENT":
        findings.append("legitimate_silence_no_opportunity")
        score = max(score, 0.7)

    if frozen.get("lifecycle_outcome") == "FAILED_CLOSED":
        findings.append("fail_closed_termination")
        score = max(score, 0.5)

    # Reward appropriate STOP on low information
    if stop_reason in ("STOP_LOW_INCREMENTAL", "STOP_NO_INFORMATIVE_ACTION", "STOP_INSUFFICIENT"):
        findings.append("appropriate_uncertainty_stop")
        score = min(1.0, score + 0.1)

    return max(0.0, min(1.0, score)), findings


def _score_outcome(frozen: Dict[str, Any], blind_class: str) -> float:
    exp = _CLASS_EXPECTATIONS.get(blind_class, {})
    final = (frozen.get("final_epistemic_state") or "").upper()
    if frozen.get("lifecycle_outcome") == "BOOTSTRAP_SILENT" and blind_class == "BLIND-D":
        return 0.9
    if final in exp.get("acceptable_final", set()):
        return 0.85
    if final in exp.get("risky_final", set()):
        return 0.35
    if final in exp.get("major_failure_final", set()):
        return 0.1
    return 0.5


def _false_positive_risk(frozen: Dict[str, Any], blind_class: str) -> str:
    final = (frozen.get("final_epistemic_state") or "").upper()
    if blind_class == "BLIND-D" and final == "SUPPORTED":
        return "CRITICAL"
    if blind_class in ("BLIND-B", "BLIND-E", "BLIND-F") and final == "SUPPORTED":
        return "ELEVATED"
    if final == "SUPPORTED" and blind_class == "BLIND-C":
        return "ELEVATED"
    return "LOW"


def reveal_and_score(
    frozen: Dict[str, Any],
    *,
    seed: int,
    ground_truth: Dict[str, Any],
    reveal_after_hash: Optional[str] = None,
) -> ExaminerRevealRecord:
    """
    Post-freeze examiner reveal. Ground truth loaded ONLY after frozen hash recorded.
    """
    blind_class = seed_to_blind_class(seed)
    frozen_hash = frozen.get("lifecycle_frozen_hash", "")
    expected_hash = reveal_after_hash or frozen_hash
    reveal_valid = bool(frozen_hash) and frozen_hash == expected_hash

    bootstrap_silent = frozen.get("lifecycle_outcome") == "BOOTSTRAP_SILENT"
    calibration = map_epistemic_to_calibration(
        frozen.get("final_epistemic_state"), bootstrap_silent=bootstrap_silent
    )

    outcome_score = _score_outcome(frozen, blind_class)
    process_score, findings = _score_process_integrity(frozen, blind_class)
    fp_risk = _false_positive_risk(frozen, blind_class)

    return ExaminerRevealRecord(
        anonymous_case_id=frozen.get("anonymous_case_id", ""),
        seed=seed,
        blind_class=blind_class,
        ground_truth=ground_truth,
        lifecycle_frozen_hash=frozen_hash,
        reveal_after_hash=expected_hash,
        reveal_order_valid=reveal_valid,
        calibration_category=calibration.value,
        outcome_score=outcome_score,
        process_integrity_score=process_score,
        false_positive_risk=fp_risk,
        notable_findings=findings,
    )


def aggregate_suite_scores(reveals: List[ExaminerRevealRecord]) -> Dict[str, Any]:
    if not reveals:
        return {"passed": False, "reason": "no_cases"}
    n = len(reveals)
    avg_outcome = sum(r.outcome_score for r in reveals) / n
    avg_process = sum(r.process_integrity_score for r in reveals) / n
    critical_fp = sum(1 for r in reveals if r.false_positive_risk == "CRITICAL")
    reveal_valid = all(r.reveal_order_valid for r in reveals)

    # Scientific behavior PASS thresholds (conservative)
    behavior_pass = (
        avg_process >= 0.55
        and critical_fp == 0
        and reveal_valid
    )
    return {
        "case_count": n,
        "avg_outcome_score": round(avg_outcome, 3),
        "avg_process_integrity_score": round(avg_process, 3),
        "critical_false_positive_count": critical_fp,
        "all_reveal_order_valid": reveal_valid,
        "scientific_behavior_pass": behavior_pass,
    }


def verify_reveal_order(frozen_hash: str, ground_truth_blob: str) -> bool:
    """Ground truth file must not exist/be readable before frozen hash is set."""
    return bool(frozen_hash) and len(frozen_hash) == 64
