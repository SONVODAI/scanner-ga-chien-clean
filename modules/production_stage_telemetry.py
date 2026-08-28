"""Lightweight STAGE_START / STAGE_END telemetry for the daily production run."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

_logger = logging.getLogger("production_daily_pipeline")


def emit_stage_start(stage: str, **fields: Any) -> float:
    started = time.monotonic()
    extras = _fmt(fields)
    line = f"[STAGE_START] stage={stage}{extras}"
    print(line, flush=True)
    _logger.info(line)
    return started


def emit_stage_end(
    stage: str,
    *,
    started_monotonic: float,
    disposition: str,
    **fields: Any,
) -> float:
    elapsed = max(0.0, time.monotonic() - float(started_monotonic))
    payload = {"disposition": disposition, "elapsed_s": round(elapsed, 3), **fields}
    extras = _fmt(payload)
    line = f"[STAGE_END] stage={stage}{extras}"
    print(line, flush=True)
    _logger.info(line)
    return elapsed


def io_fields(summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not summary:
        return {}
    keep = (
        "target",
        "success",
        "failed",
        "skipped",
        "timeouts",
        "retries",
        "elapsed_s",
        "budget_exhausted",
    )
    return {k: summary.get(k) for k in keep if k in summary}


def _fmt(fields: Dict[str, Any]) -> str:
    if not fields:
        return ""
    parts = []
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return (" " + " ".join(parts)) if parts else ""
