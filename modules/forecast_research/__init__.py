"""
Forecast Research package — PIT data contract for future true Market Forecast.

Research infrastructure only. No model training. No Market First / trading coupling.
"""

from modules.forecast_research.contract import (
    CONTRACT_VERSION,
    EXPECTED_UNIVERSE_SIZE,
    FEATURE_SCHEMA_VERSION,
    OUTCOME_SCHEMA_VERSION,
)

__all__ = [
    "CONTRACT_VERSION",
    "EXPECTED_UNIVERSE_SIZE",
    "FEATURE_SCHEMA_VERSION",
    "OUTCOME_SCHEMA_VERSION",
]
