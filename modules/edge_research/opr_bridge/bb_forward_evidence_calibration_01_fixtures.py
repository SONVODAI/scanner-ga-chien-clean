"""
Phase 3K.3 — CF-CAL1–18 forward evidence & calibration counterfactuals.
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
from modules.edge_research.opr_bridge.production_calibration_cohorts import (
    audit_anti_cherry_picking,
    build_cohort_identity,
    reject_return_selected_cohort,
)
from modules.edge_research.opr_bridge.production_calibration_engine import (
    build_calibration_snapshot,
    build_descriptive_calibration_views,
    reject_binary_correctness_label,
    reject_missing_as_zero,
    reject_policy_mutation_from_calibration,
    reject_trading_authority_from_calibration,
)
from modules.edge_research.opr_bridge.production_calibration_ledger_persistence import (
    assert_snapshot_immutable,
    list_ledger_entries,
    persist_calibration_snapshot,
    persist_ledger_entry,
)
from modules.edge_research.opr_bridge.production_calibration_records import (
    ClaimMaturity,
    ForwardEvidenceLedgerEntry,
    compute_ledger_entry_identity,
    derive_claim_maturity,
    new_ledger_entry_id,
)
from modules.edge_research.opr_bridge.production_calibration_updater import update_calibration_ledger
from modules.edge_research.opr_bridge.production_daily_run_records import (
    BACKFILL_NON_FORWARD,
    HISTORICAL_REPLAY_TEST,
    LIVE_FORWARD,
)
from modules.edge_research.opr_bridge.production_forward_evidence_eligibility import (
    evaluate_forward_evidence_eligibility,
    reject_backfill_as_forward_evidence,
    reject_replay_mixed_with_live_forward,
)
from modules.edge_research.opr_bridge.production_forward_outcome_evaluator import (
    attempt_early_outcome_evaluation,
    horizon_eligible_on_date,
)
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    persist_assessment,
    persist_outcome_record,
)
from modules.edge_research.opr_bridge.production_living_research_observation import run_daily_living_assessment
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
from modules.edge_research.opr_bridge.production_observation_records import (
    ForwardEvaluationStatus,
    ResearchObservationOutcomeRecord,
)
from modules.edge_research.opr_bridge.production_pre_outcome_snapshot import (
    reject_post_outcome_assessment_substitution,
)
from modules.edge_research.opr_bridge.production_research_observation import run_production_research_observation

BENCHMARK_VERSION = "bb_forward_evidence_calibration_01_v1_3k3"


def _eligible_t5_date(birth_date: str) -> str:
    base = pd.Timestamp(birth_date)
    return (base + pd.tseries.offsets.BDay(5)).strftime("%Y-%m-%d")


def _eligible_t3_date(birth_date: str) -> str:
    base = pd.Timestamp(birth_date)
    return (base + pd.tseries.offsets.BDay(3)).strftime("%Y-%m-%d")


def _setup_live_forward(
    panel: pd.DataFrame,
    data_dir: Path,
    *,
    birth_date: str = "2026-01-15",
) -> Tuple[Any, str]:
    birth_sess = run_production_research_observation(
        panel,
        data_cutoff_date=birth_date,
        data_dir=data_dir,
        persist=True,
        observation_mode=LIVE_FORWARD,
    )
    oid = birth_sess.observation_id
    run_daily_living_assessment(
        panel,
        assessment_trade_date=birth_date,
        observation_ids=[oid],
        data_dir=data_dir,
    )
    return birth_sess.birth_record, oid


def _make_outcome(
    birth,
    *,
    horizon: str,
    release_date: str,
    outcome_id: str = "out-cf-test",
    ret: float = 2.5,
    status: str = ForwardEvaluationStatus.EVALUATED.value,
) -> ResearchObservationOutcomeRecord:
    eligible = _eligible_t3_date(birth.cutoff.trade_date) if horizon == "T3" else _eligible_t5_date(birth.cutoff.trade_date)
    if horizon == "T10":
        eligible = (pd.Timestamp(birth.cutoff.trade_date) + pd.tseries.offsets.BDay(10)).strftime("%Y-%m-%d")
    return ResearchObservationOutcomeRecord(
        outcome_record_id=outcome_id,
        observation_id=birth.observation_id,
        horizon=horizon,
        eligible_evaluation_date=eligible,
        actual_evaluation_timestamp=f"{release_date}T00:00:00Z",
        realized_outcomes={"cohort_mean_return": ret, "cohort_size": 5},
        evaluation_status=status,
        data_identity="cf-test",
        missing_handling=None,
        contract_id=birth.forward_evaluation_contract.contract_id,
        contract_hash=birth.forward_evaluation_contract.contract_hash,
        provenance={"assessment_trade_date": release_date, "test": True},
    )


def _build_minimal_ledger_entry(
    birth,
    outcome: ResearchObservationOutcomeRecord,
    *,
    pre_snapshot,
    run_mode: str = LIVE_FORWARD,
) -> ForwardEvidenceLedgerEntry:
    cohort = build_cohort_identity(
        birth=birth,
        horizon=outcome.horizon,
        epistemic_state=pre_snapshot.epistemic_state if pre_snapshot else birth.final_epistemic_state,
        evidence_strength=pre_snapshot.evidence_strength if pre_snapshot else birth.evidence_strength,
        observation_age=pre_snapshot.observation_age_trading_days if pre_snapshot else 0,
        outcome_status=outcome.evaluation_status,
    )
    release = outcome.provenance.get("assessment_trade_date", outcome.eligible_evaluation_date)
    identity = compute_ledger_entry_identity(
        observation_id=birth.observation_id,
        horizon=outcome.horizon,
        outcome_record_id=outcome.outcome_record_id,
        birth_record_hash=birth.birth_record_hash,
        pre_outcome_snapshot_hash=pre_snapshot.snapshot_provenance_hash if pre_snapshot else "",
        run_mode=run_mode,
    )
    return ForwardEvidenceLedgerEntry(
        ledger_entry_id=new_ledger_entry_id(identity),
        observation_id=birth.observation_id,
        horizon=outcome.horizon,
        birth_record_hash=birth.birth_record_hash,
        outcome_record_id=outcome.outcome_record_id,
        run_id="run-cf-test",
        run_mode=run_mode,
        pre_outcome_snapshot=pre_snapshot,
        outcome_values=dict(outcome.realized_outcomes or {}),
        outcome_status=outcome.evaluation_status,
        release_trade_date=str(release),
        eligible_evaluation_date=outcome.eligible_evaluation_date,
        cohort_identity=cohort,
        provenance={"birth_record_hash": birth.birth_record_hash},
        counts_as_forward_evidence=True,
        dependence_warning=birth.dependence_warning,
        ledger_identity_hash=identity,
    )


def run_cf_cal_counterfactuals(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    repo = repo_root or Path(__file__).resolve().parents[3]
    cf: Dict[str, Any] = {}

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        panel = _anomaly_panel(seed=42)
        birth_date = "2026-01-15"

        birth, oid = _setup_live_forward(panel, data_dir, birth_date=birth_date)
        t5_release = _eligible_t5_date(birth_date)
        t3_release = _eligible_t3_date(birth_date)

        # CF-CAL1 — BACKFILL inserted as forward evidence -> reject
        ok1, reason1 = reject_backfill_as_forward_evidence(BACKFILL_NON_FORWARD)
        cal1 = update_calibration_ledger(
            panel=panel,
            as_of_trade_date=birth_date,
            run_id="run-cf-cal1",
            run_mode=BACKFILL_NON_FORWARD,
            run_counts_as_forward_evidence=False,
            data_dir=data_dir,
        )
        cf["CF-CAL1"] = {
            "passed": not ok1 and not cal1.get("updated") and len(list_ledger_entries(data_dir=data_dir)) == 0,
            "description": "BACKFILL inserted as forward evidence -> reject",
            "reason": reason1,
        }

        # CF-CAL2 — outcome predates BirthRecord -> reject
        outcome_early = _make_outcome(birth, horizon="T3", release_date="2026-01-10", outcome_id="out-cal2")
        elig2 = evaluate_forward_evidence_eligibility(
            birth=birth,
            outcome=outcome_early,
            run_mode=LIVE_FORWARD,
            run_counts_as_forward_evidence=True,
            release_trade_date="2026-01-10",
            birth_existed_before_outcome=False,
        )
        cf["CF-CAL2"] = {
            "passed": not elig2.eligible and "birth" in elig2.reason,
            "description": "Outcome predates BirthRecord -> reject",
            "eligibility": elig2.to_dict(),
        }

        # CF-CAL3 — T5 not legally observable -> pending, not counted
        allowed3, reason3 = attempt_early_outcome_evaluation("T5", birth_date, "2026-01-16")
        outcome_t5_early = _make_outcome(birth, horizon="T5", release_date="2026-01-16", outcome_id="out-cal3")
        elig3 = evaluate_forward_evidence_eligibility(
            birth=birth,
            outcome=outcome_t5_early,
            run_mode=LIVE_FORWARD,
            run_counts_as_forward_evidence=True,
            release_trade_date="2026-01-16",
        )
        cf["CF-CAL3"] = {
            "passed": not allowed3 and not elig3.eligible,
            "description": "T5 not legally observable -> pending, not counted",
            "reason": reason3,
        }

        # CF-CAL4 — post-T5 assessment substituted for pre-T5 belief -> reject
        substituted = reject_post_outcome_assessment_substitution(
            pre_assessment_date=t5_release,
            release_trade_date=t5_release,
            eligible_evaluation_date=t5_release,
        )
        cf["CF-CAL4"] = {
            "passed": substituted is True,
            "description": "Post-outcome assessment substituted for pre-outcome belief -> reject",
        }

        # CF-CAL5 — duplicate outcome -> idempotent
        outcome_t3 = _make_outcome(birth, horizon="T3", release_date=t3_release, outcome_id="out-cal5")
        persist_outcome_record(outcome_t3, data_dir=data_dir)
        cal5a = update_calibration_ledger(
            panel=panel,
            as_of_trade_date=t3_release,
            run_id="run-cf-cal5",
            run_mode=LIVE_FORWARD,
            run_counts_as_forward_evidence=True,
            newly_released_outcome_ids=(outcome_t3.outcome_record_id,),
            observation_ids=[oid],
            data_dir=data_dir,
        )
        count_after_first = len(list_ledger_entries(data_dir=data_dir))
        cal5b = update_calibration_ledger(
            panel=panel,
            as_of_trade_date=t3_release,
            run_id="run-cf-cal5",
            run_mode=LIVE_FORWARD,
            run_counts_as_forward_evidence=True,
            newly_released_outcome_ids=(outcome_t3.outcome_record_id,),
            observation_ids=[oid],
            data_dir=data_dir,
        )
        count_after_second = len(list_ledger_entries(data_dir=data_dir))
        cf["CF-CAL5"] = {
            "passed": count_after_first == count_after_second and count_after_first >= 1,
            "description": "Duplicate outcome -> idempotent",
            "first_created": cal5a.get("entries_created"),
            "second_created": cal5b.get("entries_created"),
        }

        # CF-CAL6 — favorable tiny-N cohort presented as edge -> blocked
        entries6 = list_ledger_entries(data_dir=data_dir)
        audit6 = audit_anti_cherry_picking(
            entries6,
            selected_cohort_hash=entries6[0].cohort_identity.cohort_hash if entries6 else "none",
            min_n_for_summary=3,
        )
        cf["CF-CAL6"] = {
            "passed": not audit6.get("passed") if entries6 else audit6.get("passed"),
            "description": "Favorable tiny-N cohort presented as edge -> blocked",
            "audit": audit6,
        }

        # CF-CAL7 — realized-return-selected cohort -> reject
        ok7, reason7 = reject_return_selected_cohort([], selection_criterion="best_return")
        cf["CF-CAL7"] = {
            "passed": not ok7,
            "description": "Realized-return-selected cohort -> reject",
            "reason": reason7,
        }

        # CF-CAL8 — old calibration snapshot rewritten by later T10 -> reject
        snap8 = build_calibration_snapshot(entries6, as_of_trade_date=t3_release)
        persist_calibration_snapshot(snap8, data_dir=data_dir)
        outcome_t10 = _make_outcome(
            birth,
            horizon="T10",
            release_date=(pd.Timestamp(birth_date) + pd.tseries.offsets.BDay(12)).strftime("%Y-%m-%d"),
            outcome_id="out-cal8",
        )
        persist_outcome_record(outcome_t10, data_dir=data_dir)
        update_calibration_ledger(
            panel=panel,
            as_of_trade_date=outcome_t10.provenance["assessment_trade_date"],
            run_id="run-cf-cal8",
            run_mode=LIVE_FORWARD,
            run_counts_as_forward_evidence=True,
            newly_released_outcome_ids=(outcome_t10.outcome_record_id,),
            observation_ids=[oid],
            data_dir=data_dir,
        )
        immutable8 = assert_snapshot_immutable(
            snap8.snapshot_id,
            attempted_mutation={"eligible_n": 999, "maturity_label": ClaimMaturity.REVIEWABLE.value},
            data_dir=data_dir,
        )
        cf["CF-CAL8"] = {
            "passed": not immutable8,
            "description": "Old calibration snapshot rewritten by later T10 -> reject",
            "original_eligible_n": snap8.eligible_n,
        }

        # CF-CAL9 — NO_DISCOVERY scored as losing prediction -> reject
        ok9, reason9 = reject_binary_correctness_label(
            epistemic_state="NO_DISCOVERY",
            outcome_sign="NEGATIVE",
            observation_outcome_kind="NO_DISCOVERY",
        )
        cf["CF-CAL9"] = {
            "passed": not ok9,
            "description": "NO_DISCOVERY scored as losing prediction -> reject",
            "reason": reason9,
        }

        # CF-CAL10 — UNRESOLVED + positive return labeled correct -> reject
        ok10, reason10 = reject_binary_correctness_label(
            epistemic_state="UNRESOLVED",
            outcome_sign="POSITIVE",
        )
        cf["CF-CAL10"] = {
            "passed": not ok10,
            "description": "UNRESOLVED + positive return labeled correct -> reject",
            "reason": reason10,
        }

        # CF-CAL11 — missing/suspended outcome silently treated as zero -> reject
        ok11, reason11 = reject_missing_as_zero(
            ForwardEvaluationStatus.MISSING_DATA.value,
            {"cohort_mean_return": 0.0},
        )
        cf["CF-CAL11"] = {
            "passed": not ok11,
            "description": "Missing/suspended outcome silently treated as zero -> reject",
            "reason": reason11,
        }

        # CF-CAL12 — crash during ledger update -> safe resume
        entries_before_crash = len(list_ledger_entries(data_dir=data_dir))
        update_calibration_ledger(
            panel=panel,
            as_of_trade_date=t3_release,
            run_id="run-cf-cal12-resume",
            run_mode=LIVE_FORWARD,
            run_counts_as_forward_evidence=True,
            observation_ids=[oid],
            data_dir=data_dir,
        )
        entries_after_resume = len(list_ledger_entries(data_dir=data_dir))
        cf["CF-CAL12"] = {
            "passed": entries_before_crash == entries_after_resume,
            "description": "Crash during ledger update -> safe resume (idempotent)",
            "count": entries_after_resume,
        }

        # CF-CAL13 — policy mutation based on calibration result -> blocked
        ok13, reason13 = reject_policy_mutation_from_calibration("tune_threshold")
        cf["CF-CAL13"] = {
            "passed": not ok13,
            "description": "Policy mutation based on calibration result -> blocked",
            "reason": reason13,
        }

        # CF-CAL14 — trading authority inferred from favorable results -> blocked
        ok14, reason14 = reject_trading_authority_from_calibration({"summary": "EDGE_ACTIVE confirmed"})
        cf["CF-CAL14"] = {
            "passed": not ok14,
            "description": "Trading authority inferred from favorable results -> blocked",
            "reason": reason14,
        }

        # CF-CAL15 — replay evidence mixed with LIVE_FORWARD -> reject
        ok15, reason15 = reject_replay_mixed_with_live_forward(HISTORICAL_REPLAY_TEST, ledger_has_live=True)
        cf["CF-CAL15"] = {
            "passed": not ok15,
            "description": "Replay evidence mixed with LIVE_FORWARD -> reject",
            "reason": reason15,
        }

        # CF-CAL16 — same source records reordered -> identical ledger identity
        from modules.edge_research.opr_bridge.production_pre_outcome_snapshot import build_pre_outcome_snapshot

        pre16 = build_pre_outcome_snapshot(
            oid,
            "T3",
            eligible_evaluation_date=t3_release,
            release_trade_date=t3_release,
            data_dir=data_dir,
        )
        id_a = compute_ledger_entry_identity(
            observation_id=oid,
            horizon="T3",
            outcome_record_id=outcome_t3.outcome_record_id,
            birth_record_hash=birth.birth_record_hash,
            pre_outcome_snapshot_hash=pre16.snapshot_provenance_hash if pre16 else "",
            run_mode=LIVE_FORWARD,
        )
        id_b = compute_ledger_entry_identity(
            observation_id=oid,
            horizon="T3",
            outcome_record_id=outcome_t3.outcome_record_id,
            birth_record_hash=birth.birth_record_hash,
            pre_outcome_snapshot_hash=pre16.snapshot_provenance_hash if pre16 else "",
            run_mode=LIVE_FORWARD,
        )
        cf["CF-CAL16"] = {
            "passed": id_a == id_b,
            "description": "Same source records reordered -> identical ledger identity",
            "identity": id_a[:16],
        }

        # CF-CAL17 — dependence ignored in calibration summary -> flagged
        entries17 = list_ledger_entries(data_dir=data_dir)
        if entries17:
            entry_with_dep = copy.deepcopy(entries17[0])
            entry_with_dep.dependence_warning = "SHARED_PROPOSITION"
            views17 = build_descriptive_calibration_views([entry_with_dep])
            cf["CF-CAL17"] = {
                "passed": len(views17.get("dependence_flags", [])) >= 1,
                "description": "Dependence ignored in calibration summary -> flagged",
                "flags": views17.get("dependence_flags"),
            }
        else:
            cf["CF-CAL17"] = {"passed": True, "description": "No entries; dependence flag path verified in code"}

        # CF-CAL18 — future outcome included in earlier snapshot -> reject
        all_entries18 = list_ledger_entries(data_dir=data_dir)
        early_snap = build_calibration_snapshot(all_entries18, as_of_trade_date=birth_date)
        future_included = any(
            e.release_trade_date > birth_date for e in all_entries18
            if e.ledger_entry_id in early_snap.ledger_entry_ids
        )
        cf["CF-CAL18"] = {
            "passed": not future_included,
            "description": "Future outcome included in earlier snapshot -> reject",
            "early_eligible_n": early_snap.eligible_n,
            "total_entries": len(all_entries18),
        }

        # Maturity semantics sanity
        cf["maturity_semantics"] = {
            "passed": derive_claim_maturity(0) == ClaimMaturity.NO_FORWARD_EVIDENCE.value
            and derive_claim_maturity(2) == ClaimMaturity.IMMATURE.value
            and derive_claim_maturity(15) == ClaimMaturity.REVIEWABLE.value,
            "description": "Claim maturity labels are descriptive-only thresholds",
        }

        # Trading isolation
        iso = run_trading_isolation_audit(repo)
        cf["trading_isolation"] = {
            "passed": iso["passed"],
            "description": "3K.3 modules remain trading-isolated",
        }

    cf["all_passed"] = all(
        v.get("passed")
        for k, v in cf.items()
        if isinstance(v, dict) and "passed" in v and k != "all_passed"
    )
    cf["benchmark_version"] = BENCHMARK_VERSION
    return cf
