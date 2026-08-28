"""
Bounded external I/O policy for the autonomous daily production pipeline.

These constants are the internal wall-clock contract. systemd TimeoutStartSec
is a safety ceiling above this envelope, not the mechanism that should kill
slow api.hsx.vn calls.

Classification (scientific integrity):
  REQUIRED for A→C→B: canonical T0 freeze / panel session presence.
  OPTIONAL / degradable: P0 universe-foreign HSX walk, Foreign Flow confirmation
  ingest, artifact publish. Their failure must not fabricate NO_QUALIFIED_MATCH
  and must not hold the closed loop indefinitely.
"""

from __future__ import annotations

from typing import Any, Dict

# Per-request HSX / api.hsx.vn bounds (production daily path).
HSX_CONNECT_TIMEOUT_SEC = 5.0
HSX_READ_TIMEOUT_SEC = 8.0
# urllib.urlopen uses a single timeout covering connect+read.
HSX_URLLIB_TIMEOUT_SEC = HSX_READ_TIMEOUT_SEC
HSX_MAX_RETRIES = 1  # attempts = retries + 1 → 2
HSX_BACKOFF_BASE_SEC = 1.0
HSX_PACING_SEC = 0.15

# Stage wall-clock budgets. Remaining symbols are skipped (PARTIAL / WAITING),
# never filled with 0, never converted into NO_QUALIFIED_MATCH.
P0_UNIVERSE_FOREIGN_STAGE_BUDGET_SEC = 480.0  # 8 minutes
FF_CONFIRMATION_STAGE_BUDGET_SEC = 480.0  # 8 minutes
FF_PRODUCTION_MAX_PAGES = 4  # exact trade_date is typically on page 1

# Artifact publish (after science). Fail-safe; must not dominate the job.
ARTIFACT_PUBLISH_TIMEOUT_SEC = 30.0

# Assumed local-stage envelopes used only for systemd ceiling justification.
# Not enforced as hard caps (those stages are not the 2026-08-28 failure mode).
ASSUMED_HEADLESS_SCAN_SEC = 600.0
ASSUMED_LOCAL_EOD_SEC = 600.0
ASSUMED_OPR_RESEARCH_SEC = 900.0
ASSUMED_ABC_SEC = 600.0
ASSUMED_RECEIPT_SYNC_SEC = 180.0
SYSTEMD_SAFETY_TIMEOUT_SEC = 5400  # 90 minutes; safety ceiling, not the API watchdog


def per_request_worst_case_sec() -> float:
    """One HSX GET with bounded retry + backoff."""
    attempts = HSX_MAX_RETRIES + 1
    retries = HSX_MAX_RETRIES
    return attempts * HSX_READ_TIMEOUT_SEC + retries * HSX_BACKOFF_BASE_SEC


def expected_runtime_envelope() -> Dict[str, Any]:
    """Operator-facing wall-clock envelope after internal I/O bounding."""
    p0 = P0_UNIVERSE_FOREIGN_STAGE_BUDGET_SEC
    ff = FF_CONFIRMATION_STAGE_BUDGET_SEC
    local = (
        ASSUMED_HEADLESS_SCAN_SEC
        + ASSUMED_LOCAL_EOD_SEC
        + ASSUMED_OPR_RESEARCH_SEC
        + ASSUMED_ABC_SEC
        + ASSUMED_RECEIPT_SYNC_SEC
    )
    # Duplicate Forecast Memory (P0+FF) in the same process is skipped; one
    # bounded pass of each enrichment is the degraded path.
    degraded = local + p0 + ff
    # Healthy HSX: scan ~2min, local EOD ~5min, P0 ~3min, FF ~5min, OPR ~5min,
    # ABC ~3min, receipt ~1min.
    normal = 2 * 60 + 5 * 60 + 3 * 60 + 5 * 60 + 5 * 60 + 3 * 60 + 60
    hard = degraded  # stage budgets are the internal hard stop for HSX
    systemd = SYSTEMD_SAFETY_TIMEOUT_SEC
    return {
        "normal_expected_sec": int(normal),
        "degraded_provider_expected_sec": int(degraded),
        "hard_upper_bound_sec": int(hard),
        "systemd_safety_timeout_sec": systemd,
        "per_request_worst_case_sec": per_request_worst_case_sec(),
        "p0_universe_foreign_budget_sec": p0,
        "ff_confirmation_budget_sec": ff,
        "hsx_connect_timeout_sec": HSX_CONNECT_TIMEOUT_SEC,
        "hsx_read_timeout_sec": HSX_READ_TIMEOUT_SEC,
        "hsx_max_retries": HSX_MAX_RETRIES,
        "notes": (
            "Duplicate Forecast Memory HSX walk in the same process is skipped. "
            "P0/FF are optional enrichments; ABC proceeds with UNABLE_TO_ASSESS "
            "only when required T0 evidence is missing, never via fabricated "
            "NO_QUALIFIED_MATCH."
        ),
    }


def empty_io_summary(*, target: int = 0) -> Dict[str, Any]:
    return {
        "target": int(target),
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "timeouts": 0,
        "retries": 0,
        "elapsed_s": 0.0,
        "budget_sec": None,
        "budget_exhausted": False,
    }
