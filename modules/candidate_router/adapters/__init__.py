"""Downstream source adapters. Rotation / HOF / Insight stay disconnected in Slice 1."""

from modules.candidate_router.adapters.rotation import nominations_from_rotation_artifact

__all__ = ["nominations_from_rotation_artifact"]
