"""Research-only live 5m Camera shadow feed.

Isolated from V1A archival collect/reconcile. Does not write Camera parquet.
LiveShadowFeed is lazy so parquet observe does not import the KBS feed.
"""

__all__ = ["LiveShadowFeed"]


def __getattr__(name: str):
    if name == "LiveShadowFeed":
        from modules.live_camera_shadow.feed import LiveShadowFeed

        return LiveShadowFeed
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
