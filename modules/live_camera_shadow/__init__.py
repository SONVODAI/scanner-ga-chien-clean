"""Research-only live 5m Camera shadow feed.

Isolated from V1A archival collect/reconcile. Does not write Camera parquet.
"""

from modules.live_camera_shadow.feed import LiveShadowFeed

__all__ = ["LiveShadowFeed"]
