"""Isolated Guardian Research Stage A — exact generate_signal reuse.

Separate from production Position Guardian UI/holdings and from the V2
Research Ledger. Does not collect market data.
"""

from research.guardian_research.collector import (
    CollectReport,
    classify_scan_row,
    collect_guardian_t0,
    load_guardian_classifier,
    missing_snapshot_fields,
    row_tech_complete,
    scan_fingerprint,
)
from research.guardian_research.contract import (
    CLASSIFICATION_FN,
    REQUIRED_TECH_FIELDS,
    SCHEMA_VERSION,
    STATUS_MISSING,
    STATUS_VALID,
)
from research.guardian_research.store import (
    GuardianT0Store,
    default_history_dir,
    default_snapshot_path,
    snapshot_identity,
)

__all__ = [
    "CLASSIFICATION_FN",
    "CollectReport",
    "GuardianT0Store",
    "REQUIRED_TECH_FIELDS",
    "SCHEMA_VERSION",
    "STATUS_MISSING",
    "STATUS_VALID",
    "classify_scan_row",
    "collect_guardian_t0",
    "default_history_dir",
    "default_snapshot_path",
    "load_guardian_classifier",
    "missing_snapshot_fields",
    "row_tech_complete",
    "scan_fingerprint",
    "snapshot_identity",
]
