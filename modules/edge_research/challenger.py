"""
Challenger orchestrator for Edge Research Phase 3.

Runs robustness battery on Phase 2 candidates only — no new discovery.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.contracts import (
    EPISODE_CONFIG_VERSION,
    ROBUSTNESS_CONFIG_VERSION,
    ROBUSTNESS_FRAGILE,
    ROBUSTNESS_PASS,
    ROBUSTNESS_REJECT,
    TOP_WINNER_PCT_5,
    TOP_WINNER_PCT_10,
)
from modules.edge_research.episodes import segment_market_episodes, summarize_candidate_episodes
from modules.edge_research.robustness import (
    classify_mean_median,
    evaluate_robustness_status,
    filter_candidate_rows,
    reconstruct_clauses_from_ledger_row,
    test_date_dominance,
    test_group_concentration,
    test_horizon_consistency,
    test_leave_best_date_out,
    test_leave_top_winners_out,
    test_neighborhood_stability,
    test_symbol_concentration,
    test_temporal_consistency,
    _candidate_metrics,
)
from modules.edge_research.hypothesis import ScientificStatus, derive_scientific_status
from modules.edge_research.statistical_guardrails import (
    compute_concentration_diagnostics,
    compute_correlation_diagnostics,
    evaluate_concentration_fragility,
)


@dataclass
class CandidateRobustnessResult:
    edge_id: str
    condition_text: str
    market_transition: str
    best_horizon: str
    candidate_n: int
    robustness_status: str
    fragility_flags: List[str]
    rejection_reasons: List[str]
    main_fragility_flag: str
    observed_episodes: int
    positive_episodes: int
    negative_episodes: int
    mixed_episodes: int
    date_count: int
    unique_symbol_count: int
    tests: Dict[str, Any]
    episode_summary: Dict[str, Any]
    scientific_status: str = ScientificStatus.CANDIDATE.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "condition_text": self.condition_text,
            "market_transition": self.market_transition,
            "best_horizon": self.best_horizon,
            "candidate_n": self.candidate_n,
            "robustness_status": self.robustness_status,
            "scientific_status": self.scientific_status,
            "fragility_flags": self.fragility_flags,
            "rejection_reasons": self.rejection_reasons,
            "main_fragility_flag": self.main_fragility_flag,
            "observed_episodes": self.observed_episodes,
            "positive_episodes": self.positive_episodes,
            "negative_episodes": self.negative_episodes,
            "mixed_episodes": self.mixed_episodes,
            "date_count": self.date_count,
            "unique_symbol_count": self.unique_symbol_count,
            "tests": self.tests,
            "episode_summary": self.episode_summary,
        }


@dataclass
class ChallengerRunResult:
    run_id: str
    timestamp: str
    robustness_config_version: str
    episode_config_version: str
    discovery_run_id: str
    candidate_ledger_hash: str
    ledger_hash: str
    dataset_start: str
    dataset_end: str
    candidates_entering: int
    robustness_pass: int = 0
    robustness_fragile: int = 0
    robustness_reject: int = 0
    episodes_segmented: int = 0
    episodes_unknown: int = 0
    report_status: str = "ACTIVE"
    data_quality: Dict[str, Any] = field(default_factory=dict)
    results: List[CandidateRobustnessResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "robustness_config_version": self.robustness_config_version,
            "episode_config_version": self.episode_config_version,
            "discovery_run_id": self.discovery_run_id,
            "candidate_ledger_hash": self.candidate_ledger_hash,
            "ledger_hash": self.ledger_hash,
            "report_status": self.report_status,
            "dataset_start": self.dataset_start,
            "dataset_end": self.dataset_end,
            "candidates_entering": self.candidates_entering,
            "candidates_entered": self.candidates_entering,
            "robustness_pass": self.robustness_pass,
            "robustness_fragile": self.robustness_fragile,
            "robustness_reject": self.robustness_reject,
            "episodes_segmented": self.episodes_segmented,
            "episodes_unknown": self.episodes_unknown,
            "data_quality": self.data_quality,
            "results": [r.to_dict() for r in self.results],
        }


def _ledger_hash(ledger: pd.DataFrame) -> str:
    if ledger.empty:
        return ""
    cols = ["edge_id", "condition_text", "market_transition", "candidate_n", "incremental_median"]
    sub = ledger[[c for c in cols if c in ledger.columns]]
    return hashlib.sha256(sub.to_csv(index=False).encode()).hexdigest()[:16]


def run_challenger(
    panel: pd.DataFrame,
    candidates_ledger: pd.DataFrame,
    *,
    discovery_run_id: str = "",
    force: bool = False,
    existing_run_hash: Optional[str] = None,
) -> ChallengerRunResult:
    """
    Run Phase 3 challenger on existing Phase 2 candidates.
    Does NOT create new candidates or modify conditions.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidate_ledger_hash = _ledger_hash(candidates_ledger)
    ledger_hash = candidate_ledger_hash

    if not force and existing_run_hash and existing_run_hash == candidate_ledger_hash:
        return ChallengerRunResult(
            run_id="skipped",
            timestamp=ts,
            robustness_config_version=ROBUSTNESS_CONFIG_VERSION,
            episode_config_version=EPISODE_CONFIG_VERSION,
            discovery_run_id=discovery_run_id,
            candidate_ledger_hash=candidate_ledger_hash,
            ledger_hash=ledger_hash,
            dataset_start="",
            dataset_end="",
            candidates_entering=0,
        )

    run_id = hashlib.sha256(f"{ts}:{candidate_ledger_hash}:{discovery_run_id}".encode()).hexdigest()[:12]

    dates = pd.to_datetime(panel["trade_date"], errors="coerce").dropna()
    ds = str(dates.min().date()) if not dates.empty else ""
    de = str(dates.max().date()) if not dates.empty else ""

    episodes = segment_market_episodes(panel)
    unknown_eps = sum(1 for d in panel["trade_date"].unique() if True)  # placeholder

    cand_df = candidates_ledger[candidates_ledger["status"] == "CANDIDATE"].copy()
    if cand_df.empty:
        cand_df = candidates_ledger.copy()

    data_quality = {
        "discovery_run_id": discovery_run_id,
        "candidate_count_entering": len(cand_df),
        "candidate_ledger_hash": candidate_ledger_hash,
        "candidate_rows_total": int(len(panel)),
        "date_range_start": ds,
        "date_range_end": de,
        "valid_market_states": int((panel["research_market_state"] != "UNKNOWN").sum()),
        "distinct_t0_dates": int(panel["trade_date"].nunique()),
        "episodes_segmented": len(episodes),
        "note": "observations are not independent Market confirmations",
    }

    result = ChallengerRunResult(
        run_id=run_id,
        timestamp=ts,
        robustness_config_version=ROBUSTNESS_CONFIG_VERSION,
        episode_config_version=EPISODE_CONFIG_VERSION,
        discovery_run_id=discovery_run_id,
        candidate_ledger_hash=candidate_ledger_hash,
        ledger_hash=ledger_hash,
        dataset_start=ds,
        dataset_end=de,
        candidates_entering=len(cand_df),
        episodes_segmented=len(episodes),
        data_quality=data_quality,
    )

    for _, crow in cand_df.iterrows():
        edge_id = str(crow.get("edge_id", ""))
        horizon = str(crow.get("best_horizon", "T5"))
        candidate_rows = filter_candidate_rows(panel, crow)
        clauses = reconstruct_clauses_from_ledger_row(crow)

        if candidate_rows.empty:
            cr = CandidateRobustnessResult(
                edge_id=edge_id,
                condition_text=str(crow.get("condition_text", "")),
                market_transition=str(crow.get("market_transition", "")),
                best_horizon=horizon,
                candidate_n=0,
                robustness_status=ROBUSTNESS_REJECT,
                fragility_flags=[],
                rejection_reasons=["no_matching_candidate_rows"],
                main_fragility_flag="NO_ROWS",
                observed_episodes=0,
                positive_episodes=0,
                negative_episodes=0,
                mixed_episodes=0,
                date_count=0,
                unique_symbol_count=0,
                tests={},
                episode_summary={},
            )
            result.results.append(cr)
            result.robustness_reject += 1
            continue

        pre = _candidate_metrics(candidate_rows, panel, crow, horizon)
        ep_sum = summarize_candidate_episodes(candidate_rows, episodes, best_horizon=horizon)
        concentration = compute_concentration_diagnostics(candidate_rows, horizon=horizon)
        correlation = compute_correlation_diagnostics(candidate_rows)

        tests: Dict[str, Any] = {
            "concentration_diagnostics": concentration,
            "correlation_diagnostics": correlation,
            "leave_best_date_out": test_leave_best_date_out(candidate_rows, panel, crow, horizon),
            "leave_top_winners_out_5pct": test_leave_top_winners_out(
                candidate_rows, panel, crow, horizon, TOP_WINNER_PCT_5
            ),
            "leave_top_winners_out_10pct": test_leave_top_winners_out(
                candidate_rows, panel, crow, horizon, TOP_WINNER_PCT_10
            ),
            "mean_median": {
                "classification": classify_mean_median(pre["candidate_profile"]),
            },
            "symbol_concentration": test_symbol_concentration(candidate_rows),
            "group_concentration": test_group_concentration(candidate_rows),
            "temporal_consistency": test_temporal_consistency(candidate_rows, panel, crow, horizon),
            "date_dominance": test_date_dominance(candidate_rows),
            "horizon_consistency": test_horizon_consistency(candidate_rows, panel, crow, horizon),
            "neighborhood_stability": test_neighborhood_stability(panel, crow, clauses, horizon),
        }

        status, flags, reasons, main_flag = evaluate_robustness_status(
            tests,
            ep_sum,
            pre["incremental"],
            len(candidate_rows),
        )

        notes_val = crow.get("notes", "")
        notes_raw = "" if pd.isna(notes_val) else str(notes_val)
        guardrails_meta: Dict[str, Any] = {}
        if notes_raw.strip().startswith("{"):
            try:
                import json

                guardrails_meta = json.loads(notes_raw).get("guardrails", {})
            except json.JSONDecodeError:
                guardrails_meta = {}

        scientific_status = derive_scientific_status(
            raw_signal=bool(guardrails_meta.get("raw_signal", True)),
            multiple_testing_survives=bool(guardrails_meta.get("multiple_testing_survives", True)),
            robustness_status=status,
            concentration_fragile=evaluate_concentration_fragility(concentration),
            episode_consistency=str(
                (guardrails_meta.get("episode_validation") or {}).get(
                    "episode_consistency",
                    ep_sum.get("episode_consistency", "INSUFFICIENT"),
                )
            ),
        ).value

        cr = CandidateRobustnessResult(
            edge_id=edge_id,
            condition_text=str(crow.get("condition_text", "")),
            market_transition=str(crow.get("market_transition", "")),
            best_horizon=horizon,
            candidate_n=len(candidate_rows),
            robustness_status=status,
            fragility_flags=flags,
            rejection_reasons=reasons,
            main_fragility_flag=main_flag,
            observed_episodes=ep_sum.get("observed_episodes", 0),
            positive_episodes=ep_sum.get("positive_episodes", 0),
            negative_episodes=ep_sum.get("negative_episodes", 0),
            mixed_episodes=ep_sum.get("mixed_episodes", 0),
            date_count=int(candidate_rows["trade_date"].nunique()),
            unique_symbol_count=int(candidate_rows["symbol"].nunique()),
            tests=tests,
            episode_summary=ep_sum,
            scientific_status=scientific_status,
        )
        result.results.append(cr)
        if status == ROBUSTNESS_PASS:
            result.robustness_pass += 1
        elif status == ROBUSTNESS_FRAGILE:
            result.robustness_fragile += 1
        else:
            result.robustness_reject += 1

    return result
