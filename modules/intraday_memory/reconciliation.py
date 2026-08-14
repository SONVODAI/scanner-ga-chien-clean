"""
Reconciliation logic for intraday memory V1A.

Detects new, missing, and changed bars without silently destroying evidence.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from modules.intraday_memory.manifest import RunManifest
from modules.intraday_memory.schema import CanonicalBar
from modules.intraday_memory.storage import (
    bars_to_dataframe,
    compare_sessions,
    load_session,
    upsert_session,
)
from modules.intraday_memory.validate import validate_raw_bar


def reconcile_session(
    data_root,
    session_date: date,
    symbol_bars: dict[str, list[dict[str, Any]]],
    *,
    collected_at=None,
    source: str = "vnstock4_kbs",
    requests_per_minute: int = 0,
) -> tuple[RunManifest, dict[str, Any]]:
    """
    Reconcile provider data against stored session.

    Fills missing bars, detects changes (quarantined), reports differences.
    """
    from pathlib import Path

    from modules.intraday_memory.config import COLLECTOR_VERSION
    from modules.intraday_memory.timezone_policy import VN_TZ
    from datetime import datetime

    root = Path(data_root)
    manifest = RunManifest(
        mode="reconcile",
        requested_session=session_date.isoformat(),
        provider="KBS",
        collector_version=COLLECTOR_VERSION,
        storage_root=str(root),
    )
    now = collected_at or datetime.now(VN_TZ)

    all_valid: list[CanonicalBar] = []
    for symbol, raw_bars in symbol_bars.items():
        for raw in raw_bars:
            outcome = validate_raw_bar(
                symbol, raw, collected_at=now, source=source,
                expected_session_date=session_date,
            )
            manifest.bars_fetched += 1
            if outcome.accepted and outcome.bar:
                all_valid.append(outcome.bar)
                manifest.bars_valid += 1
            else:
                manifest.bars_rejected += 1

    stored = load_session(root, session_date)
    incoming_df = bars_to_dataframe(all_valid)
    comparison = compare_sessions(stored, incoming_df)

    upsert = upsert_session(
        root, session_date, all_valid, reconcile=True
    )
    manifest.bars_new = upsert.new
    manifest.bars_existing = upsert.existing
    manifest.bars_changed = upsert.changed
    manifest.duplicate_count = upsert.duplicate_count
    manifest.universe_count = len(symbol_bars)
    manifest.symbols_success = sorted(symbol_bars.keys())
    manifest.requests_per_minute = requests_per_minute
    manifest.finish()

    report = {
        "session_date": session_date.isoformat(),
        "comparison": comparison,
        "upsert": {
            "new": upsert.new,
            "existing": upsert.existing,
            "changed": upsert.changed,
            "quarantined_count": len(upsert.quarantined or []),
        },
    }
    return manifest, report
