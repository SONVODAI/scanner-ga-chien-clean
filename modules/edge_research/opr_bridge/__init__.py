"""
Phase 3I.2 — Minimal Observation-to-Proposition Record (OPR) bridge.

Parallel experimental capability. Does NOT modify the 24-template research generator.
Research-only artifacts — not connected to live trading or planner selection.
"""

from modules.edge_research.opr_bridge.constants import OPR_GENERATOR_VERSION
from modules.edge_research.opr_bridge.pipeline import OprPipelineResult, run_opr_pipeline
from modules.edge_research.opr_bridge.prioritized_pipeline import (
    PrioritizedOprPipelineResult,
    run_opr_pipeline_prioritized,
)
from modules.edge_research.opr_bridge.prioritization import PRIORITIZER_VERSION

__all__ = [
    "OPR_GENERATOR_VERSION",
    "PRIORITIZER_VERSION",
    "OprPipelineResult",
    "PrioritizedOprPipelineResult",
    "run_opr_pipeline",
    "run_opr_pipeline_prioritized",
]
