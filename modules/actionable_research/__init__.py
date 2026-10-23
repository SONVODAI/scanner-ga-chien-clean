"""Actionable Research Fusion — evidence fusion, RESEARCH ONLY."""

from modules.actionable_research.contracts import AUTHORITY_LABEL, FUSION_VERSION
from modules.actionable_research.engine import fuse_session
from modules.actionable_research.production_hook import (
    attach_fusion_to_daily_result,
    run_actionable_research_after_daily,
)

__all__ = [
    "AUTHORITY_LABEL",
    "FUSION_VERSION",
    "fuse_session",
    "run_actionable_research_after_daily",
    "attach_fusion_to_daily_result",
]
