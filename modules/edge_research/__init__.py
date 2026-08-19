"""
MR.BOT Edge Research Engine V1 — research-only foundation.

Isolated from production BUY/SELL, Market First, and earning_learning writers.
"""

from modules.edge_research.contracts import (
    ENGINE_VERSION,
    RESEARCH_OBSERVATION_COLUMNS,
    ResearchObservation,
)
from modules.edge_research.engine import EdgeResearchEngine

__all__ = [
    "ENGINE_VERSION",
    "RESEARCH_OBSERVATION_COLUMNS",
    "ResearchObservation",
    "EdgeResearchEngine",
]
