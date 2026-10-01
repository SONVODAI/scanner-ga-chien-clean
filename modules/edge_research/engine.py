"""
Edge Research Engine V1 — orchestrator (Phase 0–4 / Phase A + B + C).

No production BUY/execution coupling. Discovery → Challenger → freeze →
prospective OOS → ACTIVE memory → future recognition (LIVE_FORWARD births) →
trading-session maturity → contemporaneous baseline → edge health
(ACTIVE / DECAYING / INVALIDATED) → research-only anti-context.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.adapters import (
    build_research_panel,
    earning_learning_digests,
    load_lifecycle,
    load_verified_decisions,
)
from modules.edge_research.autonomous_research import (
    AutonomousResearchConfig,
    AutonomousResearchResult,
    autonomous_research_enabled,
    load_autonomous_research_session,
    run_autonomous_research_session,
)
from modules.edge_research.challenger import ChallengerRunResult, run_challenger
from modules.edge_research.contracts import ENGINE_VERSION, ROBUSTNESS_FRAGILE, ROBUSTNESS_PASS, ROBUSTNESS_REJECT
from modules.edge_research.discovery import DiscoveryRunResult, run_discovery
from modules.edge_research.edge_memory import count_active_edges, promote_evaluations
from modules.edge_research.freeze import freeze_eligible_candidates, load_all_frozen_specs
from modules.edge_research.migration import audit_existing_candidates
from modules.edge_research.oos import OOSLeakageError
from modules.edge_research.oos_eval import evaluate_all_frozen_oos
from modules.edge_research.persistence import publish_durable, try_restore_durable
from modules.edge_research.storage import (
    append_candidates,
    append_robustness_history,
    count_ledger_rows,
    ensure_storage,
    get_challenger_ledger_hash,
    load_existing_condition_keys,
    read_challenger_run,
    read_discovery_run,
    read_ledger,
    read_status,
    read_top_candidates,
    resolve_discovery_cohort,
    resolve_data_dir,
    supersede_challenger_runs,
    update_ledger_robustness,
    write_challenger_run,
    write_discovery_run,
    write_episode_registry,
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
    observed_episodes: int
    last_research_event: str
    action: str
    discovery_summary: Optional[Dict[str, Any]] = None
    challenger_summary: Optional[Dict[str, Any]] = None

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
            "observed_episodes": self.observed_episodes,
            "last_research_event": self.last_research_event,
            "action": self.action,
        }
        if self.discovery_summary:
            d["discovery_summary"] = self.discovery_summary
        if self.challenger_summary:
            d["challenger_summary"] = self.challenger_summary
        return d


class EdgeResearchEngine:
    """Research-only engine — foundation, discovery, challenger, freeze, OOS, memory, recognition."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = resolve_data_dir(data_dir)

    def initialize(self) -> Path:
        root = ensure_storage(self.data_dir)
        try_restore_durable(self.data_dir)
        return root

    def get_foundation_status(
        self,
        current_market_state: Optional[str] = None,
        current_market_transition: Optional[str] = None,
    ) -> FoundationStatus:
        self.initialize()
        stored = read_status(self.data_dir)
        discovery = read_discovery_run(self.data_dir)
        challenger = read_challenger_run(self.data_dir)

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
        validated = count_active_edges(self.data_dir)

        last_event = str(stored.get("last_research_event", "NONE"))
        discovery_summary = None
        if discovery:
            dq = discovery.get("data_quality", {})
            discovery_summary = {
                "eligible_observations": dq.get("eligible_observations", 0),
                "market_contexts_analyzed": discovery.get("market_contexts_analyzed", 0),
                "conditions_tested": discovery.get("conditions_tested", 0),
                "candidates_discovered": discovery.get("promoted_candidates", 0),
            }

        challenger_summary = None
        observed_episodes = 0
        phase = "discovery"
        if challenger and challenger.get("run_id") not in (None, "skipped"):
            phase = "challenger"
            challenger_summary = {
                "discovery_run_id": challenger.get("discovery_run_id", ""),
                "candidates_entering": challenger.get("candidates_entering", challenger.get("candidates_entered", 0)),
                "robustness_pass": challenger.get("robustness_pass", 0),
                "robustness_fragile": challenger.get("robustness_fragile", 0),
                "robustness_reject": challenger.get("robustness_reject", 0),
                "episodes_segmented": challenger.get("episodes_segmented", 0),
            }
            observed_episodes = challenger.get("episodes_segmented", 0)
        if load_all_frozen_specs(self.data_dir):
            phase = "oos"
        if validated > 0:
            phase = "qualified_memory"

        status = FoundationStatus(
            engine_version=ENGINE_VERSION,
            phase=phase,
            production_coupling="NONE",
            research_market_state=current_market_state or "UNKNOWN",
            research_market_transition=current_market_transition or "UNKNOWN",
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            observation_count=obs_count,
            hypotheses=candidates,
            validated_edges=validated,
            independent_episodes=0,
            observed_episodes=observed_episodes,
            last_research_event=last_event,
            action="RESEARCH ONLY",
            discovery_summary=discovery_summary,
            challenger_summary=challenger_summary,
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
        apply_chronological_holdout: bool = True,
    ) -> DiscoveryRunResult:
        self.initialize()
        panel = self.build_panel(start=start, end=end)
        existing_keys = load_existing_condition_keys(self.data_dir)
        result = run_discovery(
            panel,
            enable_three_feature=enable_three_feature,
            max_candidates=max_candidates,
            apply_chronological_holdout=apply_chronological_holdout,
        )
        new_count = append_candidates(
            result.candidates,
            self.data_dir,
            existing_keys,
            discovery_run_id=result.run_id,
        )
        write_discovery_run(result.to_dict(), data_dir=self.data_dir)

        if new_count > 0:
            top = result.candidates[0]
            voice = (
                f"EDGE CANDIDATE — {top.condition_text} | "
                f"Market: {top.market_transition} | Best: {top.best_horizon}"
            )
            write_status({**self.get_foundation_status().to_dict(), "last_research_event": voice}, data_dir=self.data_dir)
        elif result.no_edge_outcome and result.conditions_tested > 0:
            write_status(
                {
                    **self.get_foundation_status().to_dict(),
                    "last_research_event": result.no_edge_outcome,
                },
                data_dir=self.data_dir,
            )

        publish_durable(self.data_dir)
        return result

    def _challenger_panel(self) -> pd.DataFrame:
        """Challenger must not see OOS holdout when discovery used a chronological split."""
        panel = self.build_panel()
        discovery = read_discovery_run(self.data_dir)
        if discovery.get("holdout_applied") and discovery.get("discovery_end_date"):
            end = pd.Timestamp(discovery["discovery_end_date"])
            work = panel.copy()
            work["_td"] = pd.to_datetime(work["trade_date"], errors="coerce")
            panel = work[work["_td"] <= end].drop(columns=["_td"])
        return panel

    def run_challenger(self, *, force: bool = False) -> ChallengerRunResult:
        """Explicit Phase 3 robustness run — not on every UI rerender."""
        self.initialize()
        discovery = read_discovery_run(self.data_dir)
        discovery_run_id = str(discovery.get("run_id", "") or "")
        cohort = resolve_discovery_cohort(self.data_dir, discovery_run_id=discovery_run_id or None)
        if cohort.empty:
            raise ValueError("No Phase 2 candidates found for the latest discovery cohort. Run discovery first.")

        panel = self._challenger_panel()
        existing = read_challenger_run(self.data_dir)
        existing_hash = existing.get("candidate_ledger_hash") or existing.get("ledger_hash") if existing else None

        result = run_challenger(
            panel,
            cohort,
            discovery_run_id=discovery_run_id,
            force=force,
            existing_run_hash=existing_hash,
        )

        if result.run_id == "skipped":
            return result

        supersede_challenger_runs(
            result.run_id,
            reason="superseded_by_new_cohort_scoped_challenger_run",
            data_dir=self.data_dir,
            exclude_run_id=result.run_id,
        )
        write_challenger_run(result.to_dict(), data_dir=self.data_dir)
        update_ledger_robustness(result.results, result.run_id, data_dir=self.data_dir)
        write_episode_registry(result, panel, data_dir=self.data_dir)

        for cr in result.results:
            test_records = []
            for name, test in cr.tests.items():
                if isinstance(test, dict):
                    test_records.append(
                        {
                            "test_name": test.get("test_name", name),
                            "pre_n": cr.candidate_n,
                            "post_n": test.get("n_after_best_date_removal", test.get("rows_removed", "")),
                            "pre_incremental_median": test.get("pre_incremental_median", ""),
                            "post_incremental_median": test.get("post_incremental_median", test.get("inc_median_without_top5", "")),
                            "result": test.get("result", ""),
                            "reason": test.get("reason", ""),
                        }
                    )
            append_robustness_history(result.run_id, cr.edge_id, result.timestamp, test_records, self.data_dir)

        if result.results:
            top = result.results[0]
            voice = self._format_challenger_voice(top)
            write_status({**self.get_foundation_status().to_dict(), "last_research_event": voice}, data_dir=self.data_dir)

        try:
            freeze_eligible_candidates(data_dir=self.data_dir, panel=panel)
        except Exception:
            # Freeze is isolated from challenger persistence success.
            pass

        publish_durable(self.data_dir)
        return result

    def freeze_eligible(self, panel: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        self.initialize()
        if panel is None:
            try:
                panel = self._challenger_panel()
            except Exception:
                panel = None
        result = freeze_eligible_candidates(data_dir=self.data_dir, panel=panel)
        try:
            publish_durable(self.data_dir)
        except Exception:
            pass
        return result.to_dict()

    def evaluate_oos(self, panel: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
        self.initialize()
        if panel is None:
            panel = self.build_panel()
        evaluations = evaluate_all_frozen_oos(panel, data_dir=self.data_dir)
        specs = {s.hypothesis_id: s for s in load_all_frozen_specs(self.data_dir)}
        promote_evaluations(evaluations, specs, data_dir=self.data_dir)
        try:
            publish_durable(self.data_dir)
        except Exception:
            pass
        return [e.to_dict() for e in evaluations]

    def run_qualification_cycle(self, panel: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Isolated freeze → OOS → promote cycle.

        Failures here must never corrupt earning-learning canonical truth.
        Does not run discovery/challenger, matcher, or execution.
        """
        self.initialize()
        audit = audit_existing_candidates(self.data_dir)
        freeze_result: Dict[str, Any] = {}
        oos_result: List[Dict[str, Any]] = []
        errors: List[str] = []
        try:
            freeze_result = self.freeze_eligible(panel=panel)
        except Exception as exc:
            errors.append(f"freeze: {exc}")
        try:
            oos_result = self.evaluate_oos(panel=panel)
        except OOSLeakageError as exc:
            errors.append(f"oos_leakage: {exc}")
        except Exception as exc:
            errors.append(f"oos: {exc}")
        return {
            "freeze": freeze_result,
            "oos": oos_result,
            "active_edges": count_active_edges(self.data_dir),
            "migration_audit": audit.get("counts", {}),
            "errors": errors,
        }

    def run_future_recognition(
        self,
        *,
        trade_date: Optional[str] = None,
        freeze_df: Optional[pd.DataFrame] = None,
        freeze_path: Optional[Path] = None,
        market_context: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Isolated Phase B recognition session.

        Failures here must never corrupt earning-learning canonical truth or
        Phase A qualification artifacts. Does not place orders or mature
        forward outcomes.
        """
        from modules.edge_research.future_recognition import run_future_recognition as _run_fr

        self.initialize()
        result = _run_fr(
            trade_date=trade_date,
            data_dir=self.data_dir,
            freeze_df=freeze_df,
            freeze_path=freeze_path,
            market_context=market_context,
        )
        try:
            publish_durable(self.data_dir)
        except Exception:
            pass
        return result

    def run_continuous_learning(
        self,
        session_date: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        from modules.edge_research.eod_cycle import run_continuous_learning

        self.initialize()
        result = run_continuous_learning(session_date, data_dir=self.data_dir, **kwargs)
        try:
            publish_durable(self.data_dir)
        except Exception:
            pass
        return result

    def run_eod_cycle(self, **kwargs: Any) -> Dict[str, Any]:
        from modules.edge_research.eod_cycle import run_edge_research_eod_cycle

        self.initialize()
        result = run_edge_research_eod_cycle(data_dir=self.data_dir, **kwargs)
        try:
            publish_durable(self.data_dir)
        except Exception:
            pass
        return result

    @staticmethod
    def _format_challenger_voice(cr: Any) -> str:
        if cr.robustness_status == ROBUSTNESS_PASS:
            return (
                f"EDGE CANDIDATE — ROBUSTNESS PASS — {cr.edge_id} | {cr.condition_text} "
                f"— READY_FOR_OOS (not validated; OOS still required)"
            )
        if cr.robustness_status == ROBUSTNESS_FRAGILE:
            return f"EDGE FRAGILE — {cr.edge_id} | Main issue: {cr.main_fragility_flag}"
        return f"EDGE REJECTED — {cr.edge_id} | Reason: {cr.rejection_reasons[0] if cr.rejection_reasons else 'robustness_failed'}"

    def get_top_candidates(self, limit: int = 10) -> List[Dict[str, Any]]:
        return read_top_candidates(self.data_dir, limit=limit)

    def get_last_discovery(self) -> Dict[str, Any]:
        return read_discovery_run(self.data_dir)

    def get_last_challenger(self) -> Dict[str, Any]:
        return read_challenger_run(self.data_dir)

    def has_discovery_candidates(self) -> bool:
        ledger = read_ledger("edge_hypothesis_ledger.csv", self.data_dir)
        return not ledger.empty

    def has_valid_discovery_cohort(self) -> bool:
        """True when the latest persisted discovery run has a non-empty cohort."""
        discovery = read_discovery_run(self.data_dir)
        run_id = str(discovery.get("run_id", "") or "")
        if not run_id:
            return False
        cohort = resolve_discovery_cohort(self.data_dir, discovery_run_id=run_id)
        return not cohort.empty

    @staticmethod
    def verify_learning_files_unchanged(before: Dict[str, Optional[str]]) -> bool:
        after = earning_learning_digests()
        return before == after

    def is_autonomous_research_enabled(self) -> bool:
        """Feature flag for PATCH 3D autonomous research entry point."""
        return autonomous_research_enabled()

    def run_autonomous_research(
        self,
        config: AutonomousResearchConfig,
        *,
        panel: Optional[pd.DataFrame] = None,
        enabled: Optional[bool] = None,
    ) -> AutonomousResearchResult:
        """
        Safe autonomous research session on read-only panel (PATCH 3D).

        Does not mutate discovery/challenger ledgers or production paths.
        """
        self.initialize()
        work_panel = panel if panel is not None else self.build_panel()
        return run_autonomous_research_session(
            work_panel,
            config,
            data_dir=self.data_dir,
            enabled=enabled,
        )

    def load_autonomous_research_session(self, session_id: str) -> Any:
        """Reload persisted research session graph."""
        from modules.edge_research.research_graph import ResearchGraph

        self.initialize()
        graph = load_autonomous_research_session(session_id, data_dir=self.data_dir)
        if not isinstance(graph, ResearchGraph):
            raise TypeError("Expected ResearchGraph from session loader")
        return graph
