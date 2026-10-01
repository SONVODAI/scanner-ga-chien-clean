"""
Phase 3K.3 — Descriptive calibration engine (no policy feedback).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.production_calibration_records import (
    CalibrationSnapshot,
    ClaimMaturity,
    ForwardEvidenceLedgerEntry,
    compute_snapshot_identity,
    derive_claim_maturity,
    evidence_strength_bucket,
)
from modules.edge_research.opr_bridge.production_calibration_cohorts import audit_anti_cherry_picking


def _outcome_sign(values: Dict[str, Any]) -> Optional[str]:
    ret = values.get("cohort_mean_return")
    if ret is None:
        return None
    r = float(ret)
    if r > 0:
        return "POSITIVE"
    if r < 0:
        return "NEGATIVE"
    return "ZERO"


def reject_binary_correctness_label(
    *,
    epistemic_state: Optional[str],
    outcome_sign: Optional[str],
    observation_outcome_kind: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    CF-CAL9/10 — NO_DISCOVERY not a failed pick; UNRESOLVED + positive != correct.
    Returns (allowed, reason). allowed=False means label rejected.
    """
    if observation_outcome_kind in ("NO_DISCOVERY", "SILENCE", "DESIGN_SILENCE"):
        if outcome_sign is not None:
            return False, "no_discovery_cannot_be_scored_as_prediction"
    if epistemic_state in ("UNRESOLVED", "INSUFFICIENT_EVIDENCE", None):
        if outcome_sign == "POSITIVE":
            return False, "unresolved_plus_positive_not_labeled_correct"
        if outcome_sign == "NEGATIVE":
            return False, "unresolved_plus_negative_not_labeled_incorrect"
    return True, "ok"


def reject_missing_as_zero(outcome_status: str, outcome_values: Dict[str, Any]) -> Tuple[bool, str]:
    """CF-CAL11 — missing/suspended cannot be silently treated as zero."""
    if outcome_status in ("MISSING_DATA", "SUSPENDED", "DELISTED"):
        if outcome_values.get("cohort_mean_return") == 0.0:
            return False, "missing_treated_as_zero_rejected"
        if outcome_values.get("cohort_mean_return") is not None:
            return False, "missing_with_imputed_return_rejected"
    return True, "ok"


def reject_trading_authority_from_calibration(summary: Dict[str, Any]) -> Tuple[bool, str]:
    """CF-CAL14 — trading authority inferred from favorable results blocked."""
    forbidden = ("EDGE_ACTIVE", "BUY", "SELL", "PROFITABLE", "BUYABLE")
    blob = str(summary).upper()
    for tok in forbidden:
        if tok in blob and "NOT_" + tok not in blob:
            return False, f"trading_authority_inference_blocked:{tok}"
    return True, "ok"


def reject_policy_mutation_from_calibration(action: str) -> Tuple[bool, str]:
    """CF-CAL13 — policy mutation based on calibration blocked."""
    forbidden = ("tune_threshold", "adjust_policy", "modify_brain", "update_weights")
    if action.lower() in forbidden:
        return False, "policy_mutation_from_calibration_blocked"
    return True, "ok"


def build_descriptive_calibration_views(
    entries: List[ForwardEvidenceLedgerEntry],
) -> Dict[str, Any]:
    """Descriptive-only calibration dimensions — always show N."""
    by_epistemic: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"n": 0, "outcomes": []})
    by_strength: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"n": 0, "outcomes": []})
    by_lifecycle: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"n": 0, "outcomes": []})
    by_horizon: Dict[str, Dict[str, int]] = defaultdict(lambda: {"released": 0, "n": 0})

    dependence_flags: List[str] = []

    for e in entries:
        pre = e.pre_outcome_snapshot
        ep = pre.epistemic_state or "UNRESOLVED"
        strength = evidence_strength_bucket(pre.evidence_strength)
        lifecycle = pre.lifecycle_state or "UNKNOWN"
        sign = _outcome_sign(e.outcome_values)

        by_epistemic[ep]["n"] += 1
        if sign:
            by_epistemic[ep]["outcomes"].append(sign)

        by_strength[strength]["n"] += 1
        if sign:
            by_strength[strength]["outcomes"].append(sign)

        by_lifecycle[lifecycle]["n"] += 1
        if sign:
            by_lifecycle[lifecycle]["outcomes"].append(sign)

        by_horizon[e.horizon]["n"] += 1
        by_horizon[e.horizon]["released"] += 1

        if e.dependence_warning:
            dependence_flags.append(f"{e.observation_id}:{e.dependence_warning}")

    return {
        "by_epistemic_state": dict(by_epistemic),
        "by_evidence_strength": dict(by_strength),
        "by_lifecycle_state": dict(by_lifecycle),
        "by_horizon": dict(by_horizon),
        "dependence_flags": sorted(set(dependence_flags)),
        "total_n": len(entries),
        "anti_cherry_picking": audit_anti_cherry_picking(entries),
    }


def build_calibration_snapshot(
    entries: List[ForwardEvidenceLedgerEntry],
    *,
    as_of_trade_date: str,
    pending_n: int = 0,
    missing_n: int = 0,
    total_live_forward_observations: int = 0,
) -> CalibrationSnapshot:
    """Immutable snapshot — only includes entries legally known by as_of_trade_date."""
    eligible = [e for e in entries if e.release_trade_date <= as_of_trade_date]
    views = build_descriptive_calibration_views(eligible)
    maturity = derive_claim_maturity(len(eligible))
    entry_ids = tuple(sorted(e.ledger_entry_id for e in eligible))
    prov = compute_snapshot_identity(as_of_trade_date=as_of_trade_date, ledger_entry_ids=entry_ids)
    snapshot_id = f"calsnap-{prov[:16]}"

    return CalibrationSnapshot(
        snapshot_id=snapshot_id,
        as_of_trade_date=as_of_trade_date,
        snapshot_timestamp=utc_now_iso(),
        maturity_label=maturity,
        total_live_forward_observations=total_live_forward_observations or len(set(e.observation_id for e in eligible)),
        eligible_n=len(eligible),
        pending_n=pending_n,
        missing_n=missing_n,
        by_horizon=views["by_horizon"],
        by_epistemic_state=views["by_epistemic_state"],
        by_evidence_strength=views["by_evidence_strength"],
        by_lifecycle_state=views["by_lifecycle_state"],
        dependence_flags=tuple(views["dependence_flags"]),
        ledger_entry_ids=entry_ids,
        provenance_hash=prov,
        counts_as_forward_evidence=True,
        frozen=True,
    )
