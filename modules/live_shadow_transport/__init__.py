"""Live shadow Cloud↔VPS transport contract. No runtime transport in this slice."""

from modules.live_shadow_transport.contract import (
    ARTIFACT_EVIDENCE_PATH,
    ARTIFACT_STATUS_PATH,
    GITHUB_WATCHLIST_PATH,
    IDENTITY_FIELDS,
)

__all__ = [
    "ARTIFACT_EVIDENCE_PATH",
    "ARTIFACT_STATUS_PATH",
    "GITHUB_WATCHLIST_PATH",
    "IDENTITY_FIELDS",
]
