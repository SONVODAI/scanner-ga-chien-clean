"""
Phase 3K.2 — Structured operational logging for production daily runs.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.evidence_synthesis_records import utc_now_iso

LOG_VERSION = "production_daily_run_observability_v1_3k2"

_logger = logging.getLogger("production_daily_research_run")


class DailyRunObservability:
    """Structured operational log — references record IDs, not scientific interpretation."""

    def __init__(self, run_id: str, target_trade_date: str) -> None:
        self.run_id = run_id
        self.target_trade_date = target_trade_date
        self.events: List[Dict[str, Any]] = []

    def _emit(self, event: str, **fields: Any) -> None:
        row = {
            "timestamp": utc_now_iso(),
            "run_id": self.run_id,
            "target_trade_date": self.target_trade_date,
            "event": event,
            "version": LOG_VERSION,
            **fields,
        }
        self.events.append(row)
        _logger.info(json.dumps(row, default=str))

    def start(self) -> None:
        self._emit("run_started")

    def data_readiness(self, *, ready: bool, disposition: str, reason: str) -> None:
        self._emit("data_readiness", ready=ready, disposition=disposition, reason=reason)

    def cutoff_established(self, *, cutoff_hash: str, observation_id: Optional[str] = None) -> None:
        self._emit("cutoff_established", cutoff_hash=cutoff_hash, observation_id=observation_id)

    def research_completed(self, *, observation_id: Optional[str], outcome_kind: Optional[str]) -> None:
        self._emit("research_completed", observation_id=observation_id, outcome_kind=outcome_kind)

    def births_persisted(self, *, observation_ids: List[str]) -> None:
        self._emit("births_persisted", observation_ids=observation_ids)

    def outcomes_released(self, *, outcome_ids: List[str]) -> None:
        self._emit("outcomes_released", outcome_ids=outcome_ids)

    def assessments_completed(self, *, assessment_ids: List[str]) -> None:
        self._emit("assessments_completed", assessment_ids=assessment_ids)

    def summary_completed(self, *, summary_id: Optional[str]) -> None:
        self._emit("summary_completed", summary_id=summary_id)

    def run_finalized(self, *, disposition: str) -> None:
        self._emit("run_finalized", disposition=disposition)

    def skip_or_fail(self, *, disposition: str, reason: str) -> None:
        self._emit("skip_or_fail", disposition=disposition, reason=reason)

    def to_dict(self) -> Dict[str, Any]:
        return {"run_id": self.run_id, "events": list(self.events)}
