"""
Phase 3K.2 — Notification event contract (no delivery in this phase).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.evidence_synthesis_records import utc_now_iso
from modules.edge_research.opr_bridge.production_daily_run_records import (
    NotificationEvent,
    NotificationEventKind,
    ProductionDailyResearchRun,
    DailyManifest,
)


def build_notification_events(
    run: ProductionDailyResearchRun,
    manifest: DailyManifest,
) -> List[NotificationEvent]:
    """Build neutral notification events — delivery_status always NOT_DELIVERED."""
    events: List[NotificationEvent] = []
    ts = utc_now_iso()

    if run.run_disposition == "SUCCESS":
        events.append(NotificationEvent(
            event_kind=NotificationEventKind.DAILY_RESEARCH_READY.value,
            run_id=run.run_id,
            trade_date=run.target_trade_date,
            payload={
                "summary_id": manifest.summary_id,
                "bot_spoke_today": manifest.bot_spoke_today,
                "silence_or_no_discovery": manifest.silence_or_no_discovery,
                "discovery_count": manifest.discovery_count,
            },
            timestamp=ts,
        ))
        if manifest.newly_released_outcomes:
            events.append(NotificationEvent(
                event_kind=NotificationEventKind.FORWARD_OUTCOME_RELEASED.value,
                run_id=run.run_id,
                trade_date=run.target_trade_date,
                payload={"outcome_ids": list(manifest.newly_released_outcomes)},
                timestamp=ts,
            ))
        if manifest.meaningful_belief_changes > 0:
            events.append(NotificationEvent(
                event_kind=NotificationEventKind.MATERIAL_BELIEF_CHANGE.value,
                run_id=run.run_id,
                trade_date=run.target_trade_date,
                payload={"count": manifest.meaningful_belief_changes},
                timestamp=ts,
            ))
    elif run.run_disposition == "SKIPPED_NON_TRADING_DAY":
        events.append(NotificationEvent(
            event_kind=NotificationEventKind.RUN_SKIPPED.value,
            run_id=run.run_id,
            trade_date=run.target_trade_date,
            payload={"reason": run.failure_or_skip_reason},
            timestamp=ts,
        ))
    elif run.run_disposition == "WAITING_FOR_DATA":
        events.append(NotificationEvent(
            event_kind=NotificationEventKind.WAITING_FOR_DATA.value,
            run_id=run.run_id,
            trade_date=run.target_trade_date,
            payload={"reason": run.failure_or_skip_reason},
            timestamp=ts,
        ))
    elif run.run_disposition in ("FAILED_CLOSED", "PARTIAL_RECOVERABLE"):
        events.append(NotificationEvent(
            event_kind=NotificationEventKind.RUN_FAILED.value,
            run_id=run.run_id,
            trade_date=run.target_trade_date,
            payload={"reason": run.failure_or_skip_reason, "disposition": run.run_disposition},
            timestamp=ts,
        ))

    return events
