"""
Edge Research Engine V1 — foundation orchestrator (Phase 0/1).

No edge discovery, no production coupling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.edge_research.adapters import (
    build_research_panel,
    earning_learning_digests,
    load_lifecycle,
    load_verified_decisions,
)
from modules.edge_research.contracts import ENGINE_VERSION
from modules.edge_research.storage import (
    count_ledger_rows,
    ensure_storage,
    read_status,
    resolve_data_dir,
    write_status,
)


@dataclass
class FoundationStatus:
    engine_version: str
    phase: str
    production_coupling: str
    research_market_state: str
    research_market_transition: str
    coverage_start: Optional[str]
    coverage_end: Optional[str]
    observation_count: int
    hypotheses: int
    validated_edges: int
    independent_episodes: int
    last_research_event: str
    action: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "phase": self.phase,
            "production_coupling": self.production_coupling,
            "research_market_state": self.research_market_state,
            "research_market_transition": self.research_market_transition,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "observation_count": self.observation_count,
            "hypotheses": self.hypotheses,
            "validated_edges": self.validated_edges,
            "independent_episodes": self.independent_episodes,
            "last_research_event": self.last_research_event,
            "action": self.action,
        }


class EdgeResearchEngine:
    """Research-only foundation engine."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = resolve_data_dir(data_dir)

    def initialize(self) -> Path:
        return ensure_storage(self.data_dir)

    def get_foundation_status(
        self,
        current_market_state: Optional[str] = None,
        current_market_transition: Optional[str] = None,
    ) -> FoundationStatus:
        self.initialize()
        stored = read_status(self.data_dir)

        lifecycle = load_lifecycle()
        if lifecycle.empty:
            lifecycle = load_verified_decisions()

        coverage_start = None
        coverage_end = None
        obs_count = 0
        if not lifecycle.empty and "trade_date" in lifecycle.columns:
            dates = pd.to_datetime(lifecycle["trade_date"], errors="coerce").dropna()
            if not dates.empty:
                coverage_start = str(dates.min().date())
                coverage_end = str(dates.max().date())
                obs_count = int(len(lifecycle))

        hypotheses = count_ledger_rows("edge_hypothesis_ledger.csv", self.data_dir)
        validated = count_ledger_rows("edge_memory.csv", self.data_dir)
        episodes = count_ledger_rows("edge_episode_registry.csv", self.data_dir)

        status = FoundationStatus(
            engine_version=ENGINE_VERSION,
            phase="foundation",
            production_coupling="NONE",
            research_market_state=current_market_state or "UNKNOWN",
            research_market_transition=current_market_transition or "UNKNOWN",
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            observation_count=obs_count,
            hypotheses=hypotheses,
            validated_edges=validated,
            independent_episodes=episodes,
            last_research_event=str(stored.get("last_research_event", "NONE")),
            action="RESEARCH ONLY",
        )
        write_status(status.to_dict(), data_dir=self.data_dir)
        return status

    def build_panel(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        ohlcv_by_symbol: Optional[dict] = None,
    ) -> pd.DataFrame:
        """Read-only canonical panel builder — no persistence of fake edges."""
        return build_research_panel(
            start=start,
            end=end,
            ohlcv_by_symbol=ohlcv_by_symbol,
        )

    @staticmethod
    def verify_learning_files_unchanged(before: Dict[str, Optional[str]]) -> bool:
        after = earning_learning_digests()
        return before == after
