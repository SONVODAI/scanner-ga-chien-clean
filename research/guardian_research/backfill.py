"""Seal one reconstructed Guardian session. A sealed file is never replaced."""

from __future__ import annotations

from pathlib import Path

from research.guardian_research.pipeline import observations_from_scan
from research.guardian_research.scan_archive import load_persisted_scan
from research.guardian_research.snapshot import build_snapshot, label_observation_origin, write_snapshot
from research.guardian_research.universe import load_tracked_symbols


def seal_reconstructed_session(project_root: Path, session: str, root: Path) -> dict:
    """Classify a persisted scan and store it as BACKFILLED. The live flag is not used."""
    tracked = load_tracked_symbols()
    loaded = load_persisted_scan(project_root, session, tracked)
    observations, info = observations_from_scan(loaded["scan_df"], session)
    if not info["verified"]:
        return {"status": "refused", "reason": info["reason"], "path": None}
    document = build_snapshot(
        session,
        observations=observations,
        market={
            "market_real": loaded["market_real"],
            "market_real_provenance": loaded["provenance"]["market_real_source"],
        },
        symbols=tracked,
    )
    labeled = label_observation_origin(
        document,
        "BACKFILLED",
        reconstruction={
            "source": loaded["provenance"]["source"],
            "saved_at": loaded["provenance"]["saved_at"],
            "label": "reconstructed from the persisted scan; not a contemporaneous close seal",
        },
    )
    path = write_snapshot(root, labeled)
    return {
        "status": "sealed",
        "reason": "BACKFILLED",
        "path": path,
        "document": labeled,
    }
