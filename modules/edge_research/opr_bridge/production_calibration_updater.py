"""
Phase 3K.3 — Incremental calibration ledger updater (idempotent, crash-safe).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.edge_research.opr_bridge.production_calibration_cohorts import build_cohort_identity
from modules.edge_research.opr_bridge.production_calibration_engine import (
    build_calibration_snapshot,
    reject_missing_as_zero,
)
from modules.edge_research.opr_bridge.production_calibration_ledger_persistence import (
    ledger_entry_exists,
    list_ledger_entries,
    persist_calibration_snapshot,
    persist_ledger_entry,
    snapshot_exists,
)
from modules.edge_research.opr_bridge.production_calibration_records import (
    ForwardEvidenceLedgerEntry,
    compute_ledger_entry_identity,
    new_ledger_entry_id,
)
from modules.edge_research.opr_bridge.production_daily_run_records import LIVE_FORWARD
from modules.edge_research.opr_bridge.production_forward_evidence_eligibility import (
    evaluate_forward_evidence_eligibility,
    reject_backfill_as_forward_evidence,
)
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    list_outcomes_for_observation,
)
from modules.edge_research.opr_bridge.production_market_delta import extract_market_snapshot
from modules.edge_research.opr_bridge.production_observation_cutoff import truncate_panel_at_cutoff
from modules.edge_research.opr_bridge.production_observation_persistence import lookup_birth_record
from modules.edge_research.opr_bridge.production_pre_outcome_snapshot import (
    build_pre_outcome_snapshot,
    reject_post_outcome_assessment_substitution,
)
from modules.edge_research.opr_bridge.production_observation_records import DEFAULT_SHADOW_AUTHORITY
import pandas as pd


def _build_ledger_entry_from_outcome(
    *,
    observation_id: str,
    outcome,
    run_id: str,
    run_mode: str,
    run_counts_as_forward_evidence: bool,
    panel: pd.DataFrame,
    data_dir: Optional[Path],
) -> Tuple[Optional[ForwardEvidenceLedgerEntry], str]:
    birth = lookup_birth_record(observation_id, data_dir=data_dir)
    if birth is None:
        return None, "birth_not_found"

    release_date = (outcome.provenance or {}).get("assessment_trade_date") or outcome.eligible_evaluation_date
    elig = evaluate_forward_evidence_eligibility(
        birth=birth,
        outcome=outcome,
        run_mode=run_mode,
        run_counts_as_forward_evidence=run_counts_as_forward_evidence,
        release_trade_date=str(release_date),
    )
    if not elig.eligible:
        return None, elig.reason

    pre = build_pre_outcome_snapshot(
        observation_id,
        outcome.horizon,
        eligible_evaluation_date=outcome.eligible_evaluation_date,
        release_trade_date=str(release_date),
        data_dir=data_dir,
    )
    if pre is None:
        return None, "pre_outcome_snapshot_missing"

    if reject_post_outcome_assessment_substitution(
        pre_assessment_date=pre.assessment_trade_date,
        release_trade_date=str(release_date),
        eligible_evaluation_date=outcome.eligible_evaluation_date,
    ):
        return None, "post_outcome_assessment_substitution_rejected"

    ok_missing, reason = reject_missing_as_zero(outcome.evaluation_status, outcome.realized_outcomes or {})
    if not ok_missing:
        return None, reason

    truncated, _ = truncate_panel_at_cutoff(panel, str(release_date)) if not panel.empty else (panel, {})
    snap = extract_market_snapshot(truncated, str(release_date)) if not panel.empty else {}

    cohort = build_cohort_identity(
        birth=birth,
        horizon=outcome.horizon,
        epistemic_state=pre.epistemic_state,
        evidence_strength=pre.evidence_strength,
        observation_age=pre.observation_age_trading_days,
        outcome_status=outcome.evaluation_status,
        market_snapshot=snap,
    )

    identity = compute_ledger_entry_identity(
        observation_id=observation_id,
        horizon=outcome.horizon,
        outcome_record_id=outcome.outcome_record_id,
        birth_record_hash=birth.birth_record_hash,
        pre_outcome_snapshot_hash=pre.snapshot_provenance_hash,
        run_mode=run_mode,
    )
    entry_id = new_ledger_entry_id(identity)

    if ledger_entry_exists(entry_id, data_dir):
        return lookup_existing(entry_id, data_dir), "idempotent_existing"

    entry = ForwardEvidenceLedgerEntry(
        ledger_entry_id=entry_id,
        observation_id=observation_id,
        horizon=outcome.horizon,
        birth_record_hash=birth.birth_record_hash,
        outcome_record_id=outcome.outcome_record_id,
        run_id=run_id,
        run_mode=run_mode,
        pre_outcome_snapshot=pre,
        outcome_values=dict(outcome.realized_outcomes or {}),
        outcome_status=outcome.evaluation_status,
        release_trade_date=str(release_date),
        eligible_evaluation_date=outcome.eligible_evaluation_date,
        cohort_identity=cohort,
        provenance={
            "birth_record_hash": birth.birth_record_hash,
            "outcome_record_id": outcome.outcome_record_id,
            "run_id": run_id,
            "temporal_provenance_hash": birth.cutoff.temporal_provenance_hash,
        },
        counts_as_forward_evidence=True,
        dependence_warning=birth.dependence_warning,
        ledger_identity_hash=identity,
        shadow_authority=DEFAULT_SHADOW_AUTHORITY,
    )
    return entry, "created"


def lookup_existing(entry_id: str, data_dir: Optional[Path]) -> Optional[ForwardEvidenceLedgerEntry]:
    from modules.edge_research.opr_bridge.production_calibration_ledger_persistence import lookup_ledger_entry
    return lookup_ledger_entry(entry_id, data_dir)


def update_calibration_ledger(
    *,
    panel: pd.DataFrame,
    as_of_trade_date: str,
    run_id: str,
    run_mode: str,
    run_counts_as_forward_evidence: bool,
    newly_released_outcome_ids: Tuple[str, ...] = (),
    observation_ids: Optional[List[str]] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Incrementally update forward evidence ledger after daily run outcomes persisted.
    Idempotent: same source records -> same ledger state.
    """
    rejected, reason = reject_backfill_as_forward_evidence(run_mode)
    if not rejected:
        return {
            "updated": False,
            "reason": reason,
            "entries_created": [],
            "counts_as_forward_evidence": False,
        }

    if run_mode != LIVE_FORWARD or not run_counts_as_forward_evidence:
        return {
            "updated": False,
            "reason": "non_live_forward_run_skipped",
            "entries_created": [],
            "counts_as_forward_evidence": False,
        }

    created: List[str] = []
    skipped: List[Dict[str, str]] = []
    oids = observation_ids or []

    for oid in oids:
        outcomes = list_outcomes_for_observation(oid, data_dir=data_dir)
        for outcome in outcomes:
            if newly_released_outcome_ids and outcome.outcome_record_id not in newly_released_outcome_ids:
                continue
            entry, status = _build_ledger_entry_from_outcome(
                observation_id=oid,
                outcome=outcome,
                run_id=run_id,
                run_mode=run_mode,
                run_counts_as_forward_evidence=run_counts_as_forward_evidence,
                panel=panel,
                data_dir=data_dir,
            )
            if entry is None:
                skipped.append({"outcome_id": outcome.outcome_record_id, "reason": status})
                continue
            if status == "idempotent_existing":
                continue
            persist_ledger_entry(entry, data_dir=data_dir)
            created.append(entry.ledger_entry_id)

    all_entries = list_ledger_entries(data_dir=data_dir, forward_only=True)
    snapshot = build_calibration_snapshot(
        all_entries,
        as_of_trade_date=as_of_trade_date,
        total_live_forward_observations=len(set(e.observation_id for e in all_entries)),
    )
    if not snapshot_exists(snapshot.snapshot_id, data_dir):
        persist_calibration_snapshot(snapshot, data_dir=data_dir)

    return {
        "updated": True,
        "entries_created": created,
        "skipped": skipped,
        "snapshot_id": snapshot.snapshot_id,
        "maturity_label": snapshot.maturity_label,
        "eligible_n": snapshot.eligible_n,
        "counts_as_forward_evidence": True,
    }
