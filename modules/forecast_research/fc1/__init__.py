"""Forecast V2 Phase FC-1 — research evaluation harness (no production coupling)."""

from modules.forecast_research.fc1.contract import FC1_VERSION
from modules.forecast_research.fc1.runner import run_fc1_harness

__all__ = ["FC1_VERSION", "run_fc1_harness"]
