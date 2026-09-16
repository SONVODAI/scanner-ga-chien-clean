"""Isolated V2 Camera sidecar + LiveShadowFeed pass-through (Slice 2, SHADOW ONLY).

Does not publish dynamic_watchlist.json.
Does not change production ENABLED_SOURCES.
Does not start the live runner.
"""

from modules.live_candidate_v2_camera.contract import SCHEMA_ID, SHADOW_V2_ENABLED_SOURCES
from modules.live_candidate_v2_camera.feed_pass import is_v2_camera_row, v2_event_reason
from modules.live_candidate_v2_camera.observe import observe_close_vs_ref, pxv_implies_buy
from modules.live_candidate_v2_camera.sidecar import (
    DEFAULT_SIDECAR_PATH,
    build_sidecar_from_scan,
    build_sidecar_rows,
    shadow_route_v2,
    write_sidecar,
)
from modules.live_candidate_v2_nomination.contract import SRC_BRAIN_A

__all__ = [
    "DEFAULT_SIDECAR_PATH",
    "SCHEMA_ID",
    "SHADOW_V2_ENABLED_SOURCES",
    "SRC_BRAIN_A",
    "build_sidecar_from_scan",
    "build_sidecar_rows",
    "is_v2_camera_row",
    "observe_close_vs_ref",
    "pxv_implies_buy",
    "shadow_route_v2",
    "v2_event_reason",
    "write_sidecar",
]
