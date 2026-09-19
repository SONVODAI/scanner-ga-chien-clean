"""
Multi-Family Discovery V2 — isolated research-only search space.

Does NOT write to production Historical Discovery, Challenger, Learning Insight,
earning-learning stores, Edge Memory, or production UI.
"""

from modules.multifamily_discovery_v2.contracts import (
    V2_ARTIFACT_DIRNAME,
    V2_ENGINE_VERSION,
)

__all__ = ["V2_ARTIFACT_DIRNAME", "V2_ENGINE_VERSION"]
