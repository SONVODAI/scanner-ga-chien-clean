"""V2 robustness battery. In-memory only — never writes production challenger files."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from modules.edge_research.contracts import (
    ROBUSTNESS_FRAGILE,
    ROBUSTNESS_PASS,
    ROBUSTNESS_REJECT,
    TOP_WINNER_PCT_10,
    TOP_WINNER_PCT_5,
)
from modules.edge_research.episodes import segment_market_episodes, summarize_candidate_episodes
from modules.edge_research.hypothesis import derive_scientific_status
from modules.edge_research.robustness import (
    classify_mean_median,
    evaluate_robustness_status,
    test_date_dominance,
    test_group_concentration,
    test_horizon_consistency,
    test_leave_best_date_out,
    test_leave_top_winners_out,
    test_symbol_concentration,
    test_temporal_consistency,
    _candidate_metrics,
)
from modules.edge_research.statistical_guardrails import (
    compute_concentration_diagnostics,
    compute_correlation_diagnostics,
    evaluate_concentration_fragility,
)
from modules.multifamily_discovery_v2.clauses import (
    apply_clauses,
    clause_from_dict,
    neighbor_clauses,
)


def _clause_tuple(cand: Dict[str, Any]):
    return tuple(clause_from_dict(c) for c in cand.get("clauses") or [])


def _filter_rows(panel: pd.DataFrame, cand: Dict[str, Any]) -> pd.DataFrame:
    clauses = _clause_tuple(cand)
    if not clauses:
        return panel.iloc[0:0].copy()
    ctx = panel[panel["research_market_transition"] == str(cand.get("market_transition", ""))]
    return apply_clauses(ctx, clauses)


def _neighborhood(panel: pd.DataFrame, cand: Dict[str, Any], horizon: str) -> Dict[str, Any]:
    clauses = list(_clause_tuple(cand))
    transition = str(cand.get("market_transition", ""))
    ctx = panel[panel["research_market_transition"] == transition]
    original = apply_clauses(ctx, clauses)
    fake_row = pd.Series(
        {
            "market_transition": transition,
            "market_state": cand.get("market_state", ""),
            "best_horizon": horizon,
        }
    )
    orig_m = _candidate_metrics(original, panel, fake_row, horizon)
    neighbor_results: List[Dict[str, Any]] = []
    for i, clause in enumerate(clauses):
        for neighbor in neighbor_clauses(clause):
            replaced = list(clauses)
            replaced[i] = neighbor
            nb_rows = apply_clauses(ctx, replaced)
            nb_m = _candidate_metrics(nb_rows, panel, fake_row, horizon)
            neighbor_results.append(
                {
                    "feature": clause.feature,
                    "neighbor_bucket": neighbor.bucket_id,
                    "n": nb_m["n"],
                    "incremental_median": nb_m["incremental"].get("incremental_median"),
                }
            )
    if not neighbor_results:
        stability = "UNKNOWN"
    else:
        positive_neighbors = sum(
            1 for r in neighbor_results if (r.get("incremental_median") or 0) > 0
        )
        if positive_neighbors >= len(neighbor_results) // 2 + 1:
            stability = "BROAD_STABLE"
        elif positive_neighbors == 0:
            stability = "ISOLATED_BUCKET"
        else:
            stability = "BOUNDARY_SENSITIVE"
    return {
        "test_name": "neighborhood_stability",
        "stability": stability,
        "neighbor_results": neighbor_results,
        "original_incremental_median": orig_m["incremental"].get("incremental_median"),
    }


def evaluate_candidates(panel: pd.DataFrame, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    episodes = segment_market_episodes(panel)
    results: List[Dict[str, Any]] = []
    n_pass = n_frag = n_rej = 0
    for cand in candidates:
        horizon = str(cand.get("best_horizon", "T5"))
        rows = _filter_rows(panel, cand)
        fake_row = pd.Series(
            {
                "market_transition": cand.get("market_transition", ""),
                "market_state": cand.get("market_state", ""),
                "best_horizon": horizon,
            }
        )
        if rows.empty:
            results.append(
                {
                    "condition_text": cand.get("condition_text"),
                    "robustness_status": ROBUSTNESS_REJECT,
                    "scientific_status": "REJECTED",
                    "rejection_reasons": ["no_matching_candidate_rows"],
                }
            )
            n_rej += 1
            continue
        pre = _candidate_metrics(rows, panel, fake_row, horizon)
        ep_sum = summarize_candidate_episodes(rows, episodes, best_horizon=horizon)
        concentration = compute_concentration_diagnostics(rows, horizon=horizon)
        tests = {
            "concentration_diagnostics": concentration,
            "correlation_diagnostics": compute_correlation_diagnostics(rows),
            "leave_best_date_out": test_leave_best_date_out(rows, panel, fake_row, horizon),
            "leave_top_winners_out_5pct": test_leave_top_winners_out(
                rows, panel, fake_row, horizon, TOP_WINNER_PCT_5
            ),
            "leave_top_winners_out_10pct": test_leave_top_winners_out(
                rows, panel, fake_row, horizon, TOP_WINNER_PCT_10
            ),
            "mean_median": {"classification": classify_mean_median(pre["candidate_profile"])},
            "symbol_concentration": test_symbol_concentration(rows),
            "group_concentration": test_group_concentration(rows),
            "temporal_consistency": test_temporal_consistency(rows, panel, fake_row, horizon),
            "date_dominance": test_date_dominance(rows),
            "horizon_consistency": test_horizon_consistency(rows, panel, fake_row, horizon),
            "neighborhood_stability": _neighborhood(panel, cand, horizon),
        }
        status, flags, reasons, main_flag = evaluate_robustness_status(
            tests, ep_sum, pre["incremental"], len(rows)
        )
        guard = cand.get("guardrails") or {}
        scientific = derive_scientific_status(
            raw_signal=bool(guard.get("raw_signal", True)),
            multiple_testing_survives=bool(guard.get("multiple_testing_survives", True)),
            robustness_status=status,
            concentration_fragile=evaluate_concentration_fragility(concentration),
            episode_consistency=str(
                (guard.get("episode_validation") or {}).get(
                    "episode_consistency", ep_sum.get("episode_consistency", "INSUFFICIENT")
                )
            ),
        ).value
        results.append(
            {
                "condition_text": cand.get("condition_text"),
                "condition_key": cand.get("condition_key"),
                "families": cand.get("families"),
                "market_transition": cand.get("market_transition"),
                "best_horizon": horizon,
                "candidate_n": int(len(rows)),
                "robustness_status": status,
                "scientific_status": scientific,
                "fragility_flags": flags,
                "rejection_reasons": reasons,
                "main_fragility_flag": main_flag,
                "observed_episodes": ep_sum.get("observed_episodes", 0),
                "unique_symbol_count": int(rows["symbol"].nunique()),
                "date_count": int(rows["trade_date"].nunique()),
                "incremental": pre["incremental"],
                "nested_rs_incremental": cand.get("nested_rs_incremental"),
                "episode_summary": ep_sum,
                "concentration": concentration,
            }
        )
        if status == ROBUSTNESS_PASS:
            n_pass += 1
        elif status == ROBUSTNESS_FRAGILE:
            n_frag += 1
        else:
            n_rej += 1
    return {
        "candidates_entering": len(candidates),
        "robustness_pass": n_pass,
        "robustness_fragile": n_frag,
        "robustness_reject": n_rej,
        "results": results,
    }
