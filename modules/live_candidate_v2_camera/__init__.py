"""Isolated V2 Camera sidecar + LiveShadowFeed pass-through (Slice 2, SHADOW ONLY).

Does not publish dynamic_watchlist.json.
Does not change production ENABLED_SOURCES.
Does not start the live runner.

Cloud writer/sidecar builders are lazy. The VPS live consumer only needs
contract + feed_pass + observe + GitHub fetch — not Brain A / router.
"""

from modules.live_candidate_v2_camera.contract import (
    ENV_V2_CLOUD_SIDECAR,
    ENV_V2_GITHUB_PUBLISH,
    GITHUB_V2_SIDECAR_PATH,
    SCHEMA_ID,
    SHADOW_V2_ENABLED_SOURCES,
    SRC_MARKET_AWARE_SWEETSPOT,
)
from modules.live_candidate_v2_camera.feed_pass import is_v2_camera_row, v2_event_reason
from modules.live_candidate_v2_camera.observe import observe_close_vs_ref, pxv_implies_buy
from modules.live_candidate_v2_nomination.contract import SRC_BRAIN_A

__all__ = [
    "DEFAULT_SIDECAR_PATH",
    "ENV_V2_CLOUD_SIDECAR",
    "ENV_V2_GITHUB_PUBLISH",
    "GITHUB_V2_SIDECAR_PATH",
    "SCHEMA_ID",
    "SHADOW_V2_ENABLED_SOURCES",
    "SRC_BRAIN_A",
    "SRC_MARKET_AWARE_SWEETSPOT",
    "build_sidecar_from_scan",
    "build_sidecar_rows",
    "is_v2_camera_row",
    "observe_close_vs_ref",
    "pxv_implies_buy",
    "run_v2_cloud_sidecar",
    "shadow_route_v2",
    "v2_cloud_sidecar_enabled",
    "v2_event_reason",
    "write_sidecar",
]

_LAZY = {
    "DEFAULT_SIDECAR_PATH": ("modules.live_candidate_v2_camera.sidecar", "DEFAULT_SIDECAR_PATH"),
    "build_sidecar_from_scan": ("modules.live_candidate_v2_camera.sidecar", "build_sidecar_from_scan"),
    "build_sidecar_rows": ("modules.live_candidate_v2_camera.sidecar", "build_sidecar_rows"),
    "shadow_route_v2": ("modules.live_candidate_v2_camera.sidecar", "shadow_route_v2"),
    "write_sidecar": ("modules.live_candidate_v2_camera.sidecar", "write_sidecar"),
    "run_v2_cloud_sidecar": ("modules.live_candidate_v2_camera.cloud_hook", "run_v2_cloud_sidecar"),
    "v2_cloud_sidecar_enabled": ("modules.live_candidate_v2_camera.cloud_hook", "v2_cloud_sidecar_enabled"),
}


def __getattr__(name: str):
    spec = _LAZY.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(spec[0]), spec[1])
