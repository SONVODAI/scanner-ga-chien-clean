"""
Phase 3K.2 — Daily manifest builder for monitoring/UI/notification sources.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.production_daily_run_records import (
    DailyManifest,
    DEFAULT_SHADOW_AUTHORITY,
    ProductionDailyResearchRun,
)


def build_daily_manifest(
    run: ProductionDailyResearchRun,
    *,
    assessment_results: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[str]] = None,
    errors: Optional[List[str]] = None,
) -> DailyManifest:
    assessment_results = assessment_results or {}
    assessments = assessment_results.get("assessments") or []
    summary = assessment_results.get("summary") or {}

    belief_changes = sum(
        1 for a in assessments
        if (a.get("epistemic_delta") or {}).get("changed")
    )
    discovery_count = len(run.observations_born)
    silence = summary.get("silence_or_no_discovery", False) or (
        not assessments and not run.observations_born
    )
    bot_spoke = bool(summary.get("summary_id") or assessments)

    return DailyManifest(
        trade_date=run.target_trade_date,
        run_id=run.run_id,
        run_status=run.run_disposition,
        bot_spoke_today=bot_spoke,
        discovery_count=discovery_count,
        active_assessment_count=len(run.observations_reassessed),
        newly_released_outcomes=run.forward_outcomes_released,
        meaningful_belief_changes=belief_changes,
        silence_or_no_discovery=silence,
        market_context_hash=run.market_context_hash,
        summary_id=run.daily_summary_id,
        errors=tuple(errors or []),
        warnings=tuple(warnings or []),
        shadow_authority=DEFAULT_SHADOW_AUTHORITY,
        counts_as_forward_evidence=run.counts_as_forward_evidence,
    )
