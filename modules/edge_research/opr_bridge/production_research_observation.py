"""
Phase 3K.0 — Production research observation orchestrator.

Wraps frozen bounded autonomous research lifecycle with temporal cutoff provenance.
Does NOT validate profitability, activate edges, or create trading signals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.blind_research_examination_runner import (
    _build_journey_rows,
    _final_decision,
    _final_epistemic_state,
    compute_research_policy_hashes,
)
from modules.edge_research.opr_bridge.bounded_lifecycle_records import ResearchBudget
from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history
from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash, utc_now_iso
from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
from modules.edge_research.opr_bridge.production_observation_cutoff import (
    build_observation_cutoff,
    truncate_panel_at_cutoff,
)
from modules.edge_research.opr_bridge.production_observation_persistence import (
    append_ledger_entry,
    birth_record_exists,
    build_ledger_entry_from_birth,
    lookup_birth_record,
    persist_birth_record,
)
from modules.edge_research.opr_bridge.production_observation_records import (
    DEFAULT_SHADOW_AUTHORITY,
    HISTORICAL_REPLAY_TEST,
    CohortAttribution,
    ObservationOutcomeKind,
    ProductionResearchObservationSession,
    ResearchObservationBirthRecord,
    build_forward_evaluation_contract,
    build_forward_horizon_placeholders,
)
from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity


def _extract_cohort_attribution(
    prop: Optional[Dict[str, Any]],
    panel: pd.DataFrame,
    journey_rows: List[Dict[str, Any]],
) -> CohortAttribution:
    symbols: List[str] = []
    sectors: List[str] = []
    population_spec: Dict[str, Any] = {}
    kind = "MARKET_WIDE"

    if prop:
        pop = (prop.get("observation_provenance") or {}).get("population") or {}
        population_spec = dict(pop) if isinstance(pop, dict) else {}
        if population_spec.get("symbols"):
            kind = "INDIVIDUAL"
            symbols = [str(s) for s in population_spec["symbols"]]
        elif population_spec.get("sector"):
            kind = "SECTOR"
            sectors = [str(population_spec["sector"])]

    if not symbols and not panel.empty and "symbol" in panel.columns:
        symbols = sorted(panel["symbol"].astype(str).unique().tolist())[:200]
        if len(symbols) <= 5:
            kind = "INDIVIDUAL" if len(symbols) == 1 else "COHORT"

    for row in journey_rows:
        pop = row.get("population")
        if isinstance(pop, dict) and pop.get("symbols"):
            kind = "COHORT"
            symbols = [str(s) for s in pop["symbols"]]

    cohort_hash = stable_hash(
        {
            "kind": kind,
            "symbols": symbols,
            "sectors": sectors,
            "population_spec": population_spec,
        }
    )
    return CohortAttribution(
        attribution_kind=kind,
        population_spec=population_spec,
        symbols_at_birth=tuple(symbols),
        sector_groups=tuple(sectors),
        cohort_hash=cohort_hash,
    )


def _classify_observation_outcome_kind(
    trigger_outcome: str,
    lifecycle_outcome: Optional[str],
    final_epistemic: Optional[str],
    final_decision_kind: Optional[str],
) -> str:
    if trigger_outcome in ("SILENT", "NO_ELIGIBLE_OBSERVATION"):
        return ObservationOutcomeKind.NO_DISCOVERY.value
    if lifecycle_outcome == "DESIGN_SILENCE":
        return ObservationOutcomeKind.DESIGN_SILENCE.value
    if lifecycle_outcome == "FAILED_CLOSED":
        return ObservationOutcomeKind.FAILED_CLOSED.value
    if final_epistemic == "REJECTED" or final_decision_kind == "STOP":
        return ObservationOutcomeKind.REJECTED.value
    if final_epistemic == "WEAKENED":
        return ObservationOutcomeKind.WEAKENED.value
    if lifecycle_outcome in ("SCIENTIFIC_STOP", "BUDGET_EXHAUSTED"):
        return ObservationOutcomeKind.STOP.value
    if trigger_outcome == "OPPORTUNITY_DETECTED":
        return ObservationOutcomeKind.DISCOVERY.value
    return ObservationOutcomeKind.SILENCE.value


def _extract_negative_findings(
    session_record,
    journey_rows: List[Dict[str, Any]],
) -> Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]:
    rejected: List[str] = []
    weakened: List[str] = []
    artifacts: List[str] = []
    unresolved: List[str] = []

    history = build_experiment_history(session_record) if session_record else []
    for entry in history:
        interp = entry.interpretation or {}
        ea = interp.get("evidence_assessment") or {}
        if ea.get("evidence_class") == "CONTRADICTING":
            rejected.append(str(ea.get("direction") or "contradiction"))
        if ea.get("artifact_warning"):
            artifacts.append(str(ea.get("artifact_warning")))
        ep = entry.epistemic_update or {}
        state = ep.get("resulting_epistemic_state") or interp.get("resulting_epistemic_state")
        if state == "WEAKENED":
            weakened.append(f"ordinal_{entry.ordinal}")
        if state in ("INSUFFICIENT_EVIDENCE", "UNRESOLVED"):
            unresolved.append(f"ordinal_{entry.ordinal}:{state}")

    for row in journey_rows:
        if row.get("evidence_direction") == "CONTRADICTING":
            rejected.append(f"ordinal_{row.get('ordinal')}")
        if row.get("decision_leaving") == "STOP":
            unresolved.append(f"stop_at_ordinal_{row.get('ordinal')}")

    return tuple(rejected), tuple(weakened), tuple(artifacts), tuple(unresolved)


def _extract_evidence_summary(session_record, journey_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    strongest = None
    strength = None
    incremental = None
    dependence = None
    contradictions: List[str] = []
    null_ledger: List[Dict[str, Any]] = []
    surviving: List[str] = []
    limitations: List[str] = []
    burden: Dict[str, Any] = {}

    history = build_experiment_history(session_record) if session_record else []
    for entry in history:
        interp = entry.interpretation or {}
        ea = interp.get("evidence_assessment") or {}
        inc = interp.get("incremental_assessment") or {}
        if ea:
            strongest = {
                "ordinal": entry.ordinal,
                "direction": ea.get("direction"),
                "strength": ea.get("strength"),
                "evidence_class": ea.get("evidence_class"),
            }
            strength = ea.get("strength")
        if inc:
            incremental = inc.get("incremental_strength")
        dep = (interp.get("dependence_assessment") or interp.get("cumulative_assessment") or {}).get(
            "dependence_accounting"
        )
        if dep:
            dependence = str(dep.get("dependence_class") or dep.get("warning") or dep)
        if ea.get("limitations"):
            limitations.extend([str(x) for x in ea["limitations"]])

    for e in reversed(history):
        if e.decision:
            dec = e.decision
            null_ledger = list(dec.get("cumulative_null_ledger") or [])
            surviving_raw = dec.get("surviving_nulls") or []
            surviving = [
                str(n.get("null_key", n)) if isinstance(n, dict) else str(n)
                for n in surviving_raw
            ]
            if not surviving and null_ledger:
                surviving = [str(n.get("null_key", "")) for n in null_ledger if n.get("status") == "SURVIVING"]
            sa = dec.get("search_accounting") or {}
            burden = {
                "search_complexity_score": sa.get("search_complexity_score"),
                "search_cardinality": sa.get("search_cardinality"),
            }
            break

    for row in journey_rows:
        if row.get("evidence_direction") == "CONTRADICTING":
            contradictions.append(f"ordinal_{row.get('ordinal')}")

    return {
        "strongest_evidence": strongest,
        "evidence_strength": strength,
        "incremental_evidence_strength": incremental,
        "dependence_warning": dependence,
        "contradictions": tuple(contradictions),
        "null_ledger_summary": null_ledger,
        "surviving_nulls": tuple(surviving),
        "limitations": tuple(limitations),
        "research_burden": burden,
    }


def build_birth_record(
    *,
    cutoff,
    shadow_authority,
    trigger_outcome: str,
    panel: pd.DataFrame,
    session_result,
    observation_mode: str = "PRODUCTION_SHADOW",
) -> ResearchObservationBirthRecord:
    session_record = session_result.session_record if session_result else None
    lifecycle = session_result.lifecycle if session_result else None
    prop = session_result.session_record.proposition_record if session_record else None

    journey_rows = _build_journey_rows(session_record) if session_record else []
    final_epistemic = _final_epistemic_state(session_record)
    dk, action, stop = _final_decision(session_record)
    evidence = _extract_evidence_summary(session_record, journey_rows)
    rejected, weakened, artifacts, unresolved = _extract_negative_findings(session_record, journey_rows)
    cohort = _extract_cohort_attribution(prop, panel, journey_rows)

    outcome_kind = _classify_observation_outcome_kind(
        trigger_outcome,
        lifecycle.outcome if lifecycle else None,
        final_epistemic,
        dk,
    )

    history = build_experiment_history(session_record) if session_record else []
    experiment_count = len([e for e in history if e.execution])

    forward_contract = build_forward_evaluation_contract(cutoff.observation_id)
    forward_horizons = build_forward_horizon_placeholders(cutoff.trade_date)

    session_identity = stable_hash(
        {
            "observation_id": cutoff.observation_id,
            "session_id": session_record.session_id if session_record else None,
            "proposition_hash": session_record.proposition_hash if session_record else None,
            "lifecycle_outcome": lifecycle.outcome if lifecycle else None,
            "termination_reason": lifecycle.termination_reason if lifecycle else trigger_outcome,
            "journey_rows": journey_rows,
        }
    )

    birth = ResearchObservationBirthRecord(
        observation_id=cutoff.observation_id,
        birth_timestamp=utc_now_iso(),
        cutoff=cutoff,
        shadow_authority=shadow_authority,
        session_id=session_record.session_id if session_record else None,
        proposition_id=session_record.proposition_id if session_record else None,
        proposition_hash=session_record.proposition_hash if session_record else None,
        research_question=(prop or {}).get("scientific_question") if prop else None,
        cohort_attribution=cohort,
        observation_outcome_kind=outcome_kind,
        final_epistemic_state=final_epistemic,
        strongest_evidence=evidence["strongest_evidence"],
        evidence_strength=evidence["evidence_strength"],
        incremental_evidence_strength=evidence["incremental_evidence_strength"],
        null_ledger_summary=evidence["null_ledger_summary"],
        surviving_nulls=evidence["surviving_nulls"],
        dependence_warning=evidence["dependence_warning"],
        contradictions=evidence["contradictions"],
        stop_reason=stop or (lifecycle.termination_reason if lifecycle else trigger_outcome),
        limitations=evidence["limitations"],
        experiment_count=experiment_count,
        research_burden=evidence["research_burden"],
        rejected_hypotheses=rejected,
        weakened_findings=weakened,
        artifact_warnings=artifacts,
        unresolved_uncertainties=unresolved,
        lifecycle_outcome=lifecycle.outcome if lifecycle else None,
        termination_reason=lifecycle.termination_reason if lifecycle else trigger_outcome,
        journey_rows=journey_rows,
        forward_horizons=forward_horizons,
        forward_evaluation_contract=forward_contract,
        research_session_identity_hash=session_identity,
        birth_record_hash="",
        observation_mode=observation_mode,
    )
    birth.finalize_hash()
    return birth


def run_production_research_observation(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    data_dir: Optional[Path] = None,
    budget: Optional[ResearchBudget] = None,
    repo_root: Optional[Path] = None,
    observation_mode: str = "PRODUCTION_SHADOW",
    persist: bool = True,
) -> ProductionResearchObservationSession:
    """
    Run production research observation at authoritative cutoff.

    Input: only data legally available at cutoff (panel truncated internally).
    Output: immutable birth record + optional ledger append.
    """
    budget = budget or ResearchBudget(max_experiment_iterations=2)
    policy_hashes = compute_research_policy_hashes(repo_root or Path(__file__).resolve().parents[3])

    truncated, cutoff_diag = truncate_panel_at_cutoff(panel, data_cutoff_date)
    focal_dates = sorted(truncated["trade_date"].astype(str).unique().tolist()) if not truncated.empty else []

    cutoff, meta = build_observation_cutoff(
        panel,
        data_cutoff_date=data_cutoff_date,
        policy_hashes=policy_hashes,
        focal_dates=focal_dates,
        repo_root=repo_root,
        observation_mode=observation_mode,
    )

    if persist and birth_record_exists(cutoff.observation_id, data_dir=data_dir):
        existing = lookup_birth_record(cutoff.observation_id, data_dir=data_dir)
        return ProductionResearchObservationSession(
            observation_id=cutoff.observation_id,
            cutoff=cutoff,
            shadow_authority=DEFAULT_SHADOW_AUTHORITY,
            trigger_outcome=existing.observation_outcome_kind if existing else "IDEMPOTENT_REPLAY",
            lifecycle_outcome=existing.lifecycle_outcome if existing else None,
            session_id=existing.session_id if existing else None,
            proposition_record=None,
            session_record_dict=None,
            lifecycle_result_dict=None,
            birth_record=existing,
            idempotent_replay=True,
            observation_mode=observation_mode,
        )

    det = detect_production_opportunity(truncated, data_cutoff_date=data_cutoff_date)
    session_result = None

    if det.outcome == "OPPORTUNITY_DETECTED" and det.proposition_record:
        session_result = run_bounded_autonomous_research(
            det.proposition_record,
            truncated,
            data_cutoff_date=data_cutoff_date,
            data_dir=data_dir,
            budget=budget,
            bootstrap_new_session=True,
        )

    birth = build_birth_record(
        cutoff=cutoff,
        shadow_authority=DEFAULT_SHADOW_AUTHORITY,
        trigger_outcome=det.outcome,
        panel=truncated,
        session_result=session_result,
        observation_mode=observation_mode,
    )

    if persist:
        persist_birth_record(birth, data_dir=data_dir)
        append_ledger_entry(build_ledger_entry_from_birth(birth), data_dir=data_dir)

    return ProductionResearchObservationSession(
        observation_id=cutoff.observation_id,
        cutoff=cutoff,
        shadow_authority=DEFAULT_SHADOW_AUTHORITY,
        trigger_outcome=det.outcome,
        lifecycle_outcome=session_result.lifecycle.outcome if session_result and session_result.lifecycle else None,
        session_id=session_result.session_record.session_id if session_result and session_result.session_record else None,
        proposition_record=det.proposition_record,
        session_record_dict=session_result.session_record.to_dict() if session_result and session_result.session_record else None,
        lifecycle_result_dict=session_result.lifecycle.to_dict() if session_result and session_result.lifecycle else None,
        birth_record=birth,
        idempotent_replay=False,
        observation_mode=observation_mode,
    )


def run_historical_replay_test(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    data_dir: Optional[Path] = None,
    budget: Optional[ResearchBudget] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    HISTORICAL_REPLAY_TEST — infrastructure validation only, NOT forward evidence.
    """
    session = run_production_research_observation(
        panel,
        data_cutoff_date=data_cutoff_date,
        data_dir=data_dir,
        budget=budget,
        repo_root=repo_root,
        observation_mode=HISTORICAL_REPLAY_TEST,
        persist=True,
    )
    truncated, diag = truncate_panel_at_cutoff(panel, data_cutoff_date)
    return {
        "test_kind": HISTORICAL_REPLAY_TEST,
        "observation_id": session.observation_id,
        "cutoff": session.cutoff.to_dict(),
        "cutoff_diagnostics": diag,
        "max_researcher_visible_trade_date": diag.get("max_researcher_visible_trade_date"),
        "future_t0_rows_in_source": diag.get("future_t0_rows_in_source"),
        "temporal_provenance_established": diag.get("temporal_provenance_established"),
        "birth_record": session.birth_record.to_dict() if session.birth_record else None,
        "forward_horizons_at_birth": [
            h.to_dict() for h in (session.birth_record.forward_horizons if session.birth_record else [])
        ],
        "counts_as_forward_evidence": False,
        "idempotent_replay": session.idempotent_replay,
    }
