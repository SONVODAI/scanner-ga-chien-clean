"""
Phase 3K.2 — Data readiness gate before scientific execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.production_market_delta import extract_market_snapshot
from modules.edge_research.opr_bridge.production_observation_cutoff import (
    compute_panel_hash,
    truncate_panel_at_cutoff,
    validate_temporal_provenance,
)
from modules.edge_research.opr_bridge.production_observation_records import DataAvailabilityStatus
from modules.edge_research.opr_bridge.production_eod_completeness import verify_eod_completeness
from modules.edge_research.opr_bridge.production_trading_session_eligibility import (
    evaluate_trading_session_eligibility,
)
from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
    evaluate_calendar_session_eligibility,
)


@dataclass(frozen=True)
class DataReadinessResult:
    ready: bool
    disposition: str  # READY | WAITING_FOR_DATA | FAILED_CLOSED
    reason: str
    source_max_trade_date: Optional[str]
    researcher_visible_max_trade_date: Optional[str]
    source_dataset_identity: str
    source_dataset_hash: str
    temporal_provenance_established: bool
    market_context_available: bool
    market_context_classification: str
    eod_completeness_established: bool
    eod_completeness_reason: Optional[str]
    calendar_eligible: bool
    errors: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ready": self.ready,
            "disposition": self.disposition,
            "reason": self.reason,
            "source_max_trade_date": self.source_max_trade_date,
            "researcher_visible_max_trade_date": self.researcher_visible_max_trade_date,
            "source_dataset_identity": self.source_dataset_identity,
            "source_dataset_hash": self.source_dataset_hash,
            "temporal_provenance_established": self.temporal_provenance_established,
            "market_context_available": self.market_context_available,
            "market_context_classification": self.market_context_classification,
            "eod_completeness_established": self.eod_completeness_established,
            "eod_completeness_reason": self.eod_completeness_reason,
            "calendar_eligible": self.calendar_eligible,
            "errors": list(self.errors),
        }


def verify_data_readiness(
    panel: pd.DataFrame,
    target_trade_date: str,
    *,
    require_eod: bool = True,
    require_authoritative_eod: bool = False,
    require_calendar: bool = False,
    eod_data_root: Optional[Path] = None,
) -> DataReadinessResult:
    """
    Fail closed on ambiguous provenance. Verify EOD data exists for target session.
    """
    errors: List[str] = []
    dataset_hash = compute_panel_hash(panel)
    dataset_identity = f"research_panel:{dataset_hash[:16]}"

    if panel.empty:
        return DataReadinessResult(
            ready=False,
            disposition="WAITING_FOR_DATA",
            reason="empty_source_panel",
            source_max_trade_date=None,
            researcher_visible_max_trade_date=None,
            source_dataset_identity=dataset_identity,
            source_dataset_hash=dataset_hash,
            temporal_provenance_established=False,
            market_context_available=False,
            market_context_classification="UNAVAILABLE",
            eod_completeness_established=False,
            eod_completeness_reason="empty_source_panel",
            calendar_eligible=False,
            errors=("empty_source_panel",),
        )

    calendar = evaluate_calendar_session_eligibility(target_trade_date)
    if require_calendar and not calendar.eligible:
        return DataReadinessResult(
            ready=False,
            disposition=calendar.disposition if calendar.disposition != "CALENDAR_UNKNOWN" else "FAILED_CLOSED",
            reason=calendar.reason,
            source_max_trade_date=None,
            researcher_visible_max_trade_date=None,
            source_dataset_identity=dataset_identity,
            source_dataset_hash=dataset_hash,
            temporal_provenance_established=False,
            market_context_available=False,
            market_context_classification="UNAVAILABLE",
            eod_completeness_established=False,
            eod_completeness_reason=None,
            calendar_eligible=False,
            errors=(calendar.reason,),
        )

    source_max = str(pd.to_datetime(panel["trade_date"]).max().date())
    session = evaluate_trading_session_eligibility(panel, target_trade_date)
    if not session.eligible:
        return DataReadinessResult(
            ready=False,
            disposition=session.disposition,
            reason=session.reason,
            source_max_trade_date=source_max,
            researcher_visible_max_trade_date=None,
            source_dataset_identity=dataset_identity,
            source_dataset_hash=dataset_hash,
            temporal_provenance_established=False,
            market_context_available=False,
            market_context_classification="UNAVAILABLE",
            eod_completeness_established=False,
            eod_completeness_reason=None,
            calendar_eligible=calendar.eligible,
            errors=(session.reason,),
        )

    if source_max < target_trade_date:
        return DataReadinessResult(
            ready=False,
            disposition="WAITING_FOR_DATA",
            reason="source_max_trade_date_before_target",
            source_max_trade_date=source_max,
            researcher_visible_max_trade_date=None,
            source_dataset_identity=dataset_identity,
            source_dataset_hash=dataset_hash,
            temporal_provenance_established=False,
            market_context_available=False,
            market_context_classification="UNAVAILABLE",
            eod_completeness_established=False,
            eod_completeness_reason=None,
            calendar_eligible=calendar.eligible,
            errors=("source_max_trade_date_before_target",),
        )

    truncated, diag = truncate_panel_at_cutoff(panel, target_trade_date)
    ok, prov_errors = validate_temporal_provenance(truncated, target_trade_date, diag)
    if not ok:
        errors.extend(prov_errors)
        return DataReadinessResult(
            ready=False,
            disposition="FAILED_CLOSED",
            reason="temporal_provenance_failed",
            source_max_trade_date=source_max,
            researcher_visible_max_trade_date=diag.get("max_researcher_visible_trade_date"),
            source_dataset_identity=dataset_identity,
            source_dataset_hash=dataset_hash,
            temporal_provenance_established=False,
            market_context_available=False,
            market_context_classification="UNAVAILABLE",
            eod_completeness_established=False,
            eod_completeness_reason=None,
            calendar_eligible=calendar.eligible,
            errors=tuple(errors),
        )

    snap = extract_market_snapshot(truncated, target_trade_date)
    mkt_class = "AVAILABLE" if snap else "MISSING_CLASSIFIED"
    if not snap:
        errors.append("market_context_missing_for_target_date")

    sub = truncated[truncated["trade_date"].astype(str) == str(target_trade_date)]
    if sub.empty:
        return DataReadinessResult(
            ready=False,
            disposition="WAITING_FOR_DATA",
            reason="no_rows_for_target_trade_date",
            source_max_trade_date=source_max,
            researcher_visible_max_trade_date=diag.get("max_researcher_visible_trade_date"),
            source_dataset_identity=dataset_identity,
            source_dataset_hash=dataset_hash,
            temporal_provenance_established=True,
            market_context_available=False,
            market_context_classification="UNAVAILABLE",
            eod_completeness_established=False,
            eod_completeness_reason=None,
            calendar_eligible=calendar.eligible,
            errors=("no_rows_for_target_trade_date",),
        )

    if require_eod and len(sub) < 1:
        return DataReadinessResult(
            ready=False,
            disposition="WAITING_FOR_DATA",
            reason="incomplete_eod_for_target",
            source_max_trade_date=source_max,
            researcher_visible_max_trade_date=diag.get("max_researcher_visible_trade_date"),
            source_dataset_identity=dataset_identity,
            source_dataset_hash=dataset_hash,
            temporal_provenance_established=True,
            market_context_available=bool(snap),
            market_context_classification=mkt_class,
            eod_completeness_established=False,
            eod_completeness_reason=None,
            calendar_eligible=calendar.eligible,
            errors=("incomplete_eod_for_target",),
        )

    eod_result = None
    if require_authoritative_eod:
        eod_result = verify_eod_completeness(
            panel, target_trade_date, data_root=eod_data_root
        )
        if not eod_result.complete:
            disp = "FAILED_CLOSED" if eod_result.disposition == "FAILED_CLOSED" else "WAITING_FOR_DATA"
            return DataReadinessResult(
                ready=False,
                disposition=disp,
                reason=eod_result.reason,
                source_max_trade_date=source_max,
                researcher_visible_max_trade_date=diag.get("max_researcher_visible_trade_date"),
                source_dataset_identity=dataset_identity,
                source_dataset_hash=dataset_hash,
                temporal_provenance_established=True,
                market_context_available=bool(snap),
                market_context_classification=mkt_class,
                eod_completeness_established=False,
                eod_completeness_reason=eod_result.reason,
                calendar_eligible=calendar.eligible,
                errors=tuple(errors) + eod_result.errors,
            )

    return DataReadinessResult(
        ready=True,
        disposition="READY",
        reason="data_ready",
        source_max_trade_date=source_max,
        researcher_visible_max_trade_date=diag.get("max_researcher_visible_trade_date"),
        source_dataset_identity=dataset_identity,
        source_dataset_hash=dataset_hash,
        temporal_provenance_established=True,
        market_context_available=bool(snap),
        market_context_classification=mkt_class,
        eod_completeness_established=eod_result.complete if eod_result else not require_authoritative_eod,
        eod_completeness_reason=eod_result.reason if eod_result else None,
        calendar_eligible=calendar.eligible,
        errors=tuple(errors),
    )
