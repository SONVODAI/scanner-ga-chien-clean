"""
Phase 3I.2 — Minimal Observation-to-Proposition Record (OPR) bridge.

Parallel experimental capability. Does NOT modify the 24-template research generator.
Research-only artifacts — not connected to live trading or planner selection.
"""

from modules.edge_research.opr_bridge.constants import OPR_GENERATOR_VERSION
from modules.edge_research.opr_bridge.pipeline import OprPipelineResult, run_opr_pipeline

__all__ = [
    "OPR_GENERATOR_VERSION",
    "OprPipelineResult",
    "run_opr_pipeline",
]
