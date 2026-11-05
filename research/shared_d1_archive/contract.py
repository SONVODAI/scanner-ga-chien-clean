"""Shared Research D1 Archive — Stage A data contract (provider-neutral).

Research-only. Does not feed Research Ledger B1 VerifiedSessionCalendar /
PriceBook, Guardian outcomes, or production scanners.

Provider-specific names/endpoints live in ``fetcher.py`` only.
"""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA_OBSERVATION = "shared_research_d1.observation.v1"
SCHEMA_SESSION_INDEX = "shared_research_d1.session_index.v1"
SCHEMA_RUN_REPORT = "shared_research_d1.run_report.v1"

RECORD_OBSERVATION = "d1_observation"
RECORD_SESSION_INDEX = "candidate_session_index"
RECORD_QUALITY = "d1_quality_event"

RESOLUTION = "1D"
DEFAULT_START_DATE = "2025-01-01"
VNINDEX_SYMBOL = "VNINDEX"
VNINDEX_TYPE = "index"
STOCK_TYPE = "stock"

# Explicit: vendor corporate-action adjust policy is unknown.
ADJUSTMENT_UNVERIFIED = "UNVERIFIED"

# Candidate calendar must remain unverified.
SESSION_INDEX_STATUS = "CANDIDATE_NOT_VERIFIED"

# Quality flag labels
FLAG_MISSING_SYMBOL = "MISSING_SYMBOL"
FLAG_MISSING_SESSION = "MISSING_SESSION"
FLAG_DUPLICATE_DATE = "DUPLICATE_DATE"
FLAG_CONFLICTING_VALUE = "CONFLICTING_HISTORICAL_VALUE"
FLAG_EMPTY_FETCH = "EMPTY_FETCH"
FLAG_INVALID_ROW = "INVALID_ROW"

DEFAULT_HISTORY_DIRNAME = "shared_d1_archive_history"
OBSERVATIONS_FILENAME = "d1_observations.jsonl"
QUALITY_FILENAME = "d1_quality_events.jsonl"
SESSION_INDEX_FILENAME = "vnindex_session_index_candidate.json"
RUN_REPORT_FILENAME = "d1_run_reports.jsonl"


def observation_may_feed_research_outcomes(record: Mapping[str, Any]) -> bool:
    """Stage A gate: unverified archive rows must not enter B1/Guardian outcomes."""
    if not isinstance(record, Mapping):
        return False
    if record.get("adjustment_status") == ADJUSTMENT_UNVERIFIED:
        return False
    if record.get("verified_for_research_ledger_b1") is not True:
        return False
    if record.get("verified_for_guardian_outcomes") is not True:
        return False
    return True


def session_index_may_feed_verified_calendar(document: Mapping[str, Any]) -> bool:
    """Only an explicitly verified session document may feed a verified calendar."""
    if not isinstance(document, Mapping):
        return False
    return document.get("verified") is True
