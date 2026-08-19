"""
Edge Research Engine V1 — orchestrator (Phase 0/1 foundation + Phase 2 discovery).

No production coupling. Stops at CANDIDATE — no OOS or EDGE ACTIVE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.adapters import (
    build_research_panel,
    earning_learning_digests,
    load_lifecycle,
    load_verified_decisions,
)
from modules.edge_research.contracts import (
    CANDIDATE_STATUS_CANDIDATE,
    DISCOVERY_CONFIG_VERSION,
    ENGINE_VERSION,
)
from modules.edge_research.discovery import DiscoveryRunResult, run_discovery
from modules.edge_research.storage import (
    append_candidates,
    count_ledger_rows,
    ensure_storage,
    load_existing_condition_keys,
    read_discovery_run,
    read_status,
    read_top_candidates,
    resolve_data_dir,
    write_discovery_run,
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
    discovery_summary: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
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
        if self.discovery_summary:
            d["discovery_summary"] = self.discovery_summary
        return d


class EdgeResearchEngine:
    """Research-only engine — foundation + controlled discovery."""

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
        discovery = read_discovery_run(self.data_dir)

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

        candidates = count_ledger_rows("edge_hypothesis_ledger.csv", self.data_dir)
        validated = count_ledger_rows("edge_memory.csv", self.data_dir)

        last_event = str(stored.get("last_research_event", "NONE"))
        discovery_summary = None
        if discovery:
            dq = discovery.get("data_quality", {})
            discovery_summary = {
                "eligible_observations": dq.get("eligible_observations", 0),
                "market_contexts_analyzed": discovery.get("market_contexts_analyzed", 0),
                "conditions_tested": discovery.get("conditions_tested", 0),
                "candidates_discovered": discovery.get("promoted_candidates", 0),
                "rejected_insufficient_sample": discovery.get("rejected_insufficient_sample", 0),
                "rejected_no_incremental_edge": discovery.get("rejected_no_incremental_edge", 0),
            }

        status = FoundationStatus(
            engine_version=ENGINE_VERSION,
            phase="discovery",
            production_coupling="NONE",
            research_market_state=current_market_state or "UNKNOWN",
            research_market_transition=current_market_transition or "UNKNOWN",
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            observation_count=obs_count,
            hypotheses=candidates,
            validated_edges=validated,
            independent_episodes=0,
            last_research_event=last_event,
            action="RESEARCH ONLY",
            discovery_summary=discovery_summary,
        )
        write_status(status.to_dict(), data_dir=self.data_dir)
        return status

    def build_panel(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        ohlcv_by_symbol: Optional[dict] = None,
    ) -> pd.DataFrame:
        return build_research_panel(start=start, end=end, ohlcv_by_symbol=ohlcv_by_symbol)

    def run_discovery(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        *,
        enable_three_feature: bool = False,
        max_candidates: int = 20,
    ) -> DiscoveryRunResult:
        """Explicit discovery run — not invoked on every UI render."""
        self.initialize()
        panel = self.build_panel(start=start, end=end)
        existing_keys = load_existing_condition_keys(self.data_dir)
        result = run_discovery(
            panel,
            enable_three_feature=enable_three_feature,
            max_candidates=max_candidates,
        )
        new_count = append_candidates(result.candidates, self.data_dir, existing_keys)
        write_discovery_run(result.to_dict(), data_dir=self.data_dir)

        if new_count > 0:
            top = result.candidates[0]
            voice = (
                f"EDGE CANDIDATE — {top.condition_text} | "
                f"Market: {top.market_transition} | Best: {top.best_horizon}"
            )
            write_status(
                {
                    **self.get_foundation_status().to_dict(),
                    "last_research_event": voice,
                },
                data_dir=self.data_dir,
            )
        elif result.promoted_candidates == 0:
            write_status(
                {**self.get_foundation_status().to_dict(), "last_research_event": "NONE"},
                data_dir=self.data_dir,
            )

        return result

    def get_top_candidates(self, limit: int = 10) -> List[Dict[str, Any]]:
        return read_top_candidates(self.data_dir, limit=limit)

    def get_last_discovery(self) -> Dict[str, Any]:
        return read_discovery_run(self.data_dir)

    @staticmethod
    def verify_learning_files_unchanged(before: Dict[str, Optional[str]]) -> bool:
        after = earning_learning_digests()
        return before == after
