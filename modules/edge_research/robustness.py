"""
Robustness test battery for Edge Research candidates (Phase 3).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.edge_research.baseline import compute_baseline_profiles
from modules.edge_research.contracts import (
    CANDIDATE_MIN_N,
    DATE_CONCENTRATION_SEVERE,
    FEATURE_BUCKETS,
    ROBUSTNESS_CONFIG_VERSION,
    SYMBOL_CONCENTRATION_SEVERE,
    TOP_WINNER_PCT_10,
    TOP_WINNER_PCT_5,
)
from modules.edge_research.discovery import ConditionClause, apply_condition
from modules.edge_research.metrics import (
    HORIZONS,
    RETURN_COLUMNS,
    compute_horizon_profile,
    compute_incremental_metrics,
    has_positive_incremental_evidence,
)


def reconstruct_clauses_from_ledger_row(row: pd.Series) -> Tuple[ConditionClause, ...]:
    """Rebuild condition clauses from hypothesis ledger row — no new discovery."""
    import json

    raw_json = row.get("feature_clauses_json") if hasattr(row, "get") else None
    if raw_json is not None and not (isinstance(raw_json, float) and pd.isna(raw_json)):
        text = str(raw_json).strip()
        if text and text not in ("nan", "None", "<NA>"):
            try:
                payload = json.loads(text) if isinstance(raw_json, str) else raw_json
            except (json.JSONDecodeError, TypeError):
                payload = None
            if isinstance(payload, list) and payload:
                parsed: List[ConditionClause] = []
                for item in payload:
                    if not isinstance(item, dict) or not item.get("feature"):
                        continue
                    parsed.append(
                        ConditionClause(
                            feature=str(item.get("feature", "")),
                            operator=str(item.get("operator", "")),
                            threshold_lo=item.get("threshold_lo"),
                            threshold_hi=item.get("threshold_hi"),
                            bucket_id=str(item.get("bucket_id") or ""),
                        )
                    )
                if parsed:
                    return tuple(parsed)

    clauses: List[ConditionClause] = []
    for i in (1, 2):
        feat = row.get(f"feature_{i}")
        if feat is None or (isinstance(feat, float) and pd.isna(feat)) or str(feat).strip() == "":
            continue
        op = str(row.get(f"operator_{i}", ""))
        thresh = pd.to_numeric(row.get(f"threshold_{i}"), errors="coerce")
        matched: Optional[ConditionClause] = None
        for bucket_id, lo, hi, bucket_op in FEATURE_BUCKETS.get(str(feat), ()):
            if bucket_op != op:
                continue
            if op == "<=" and hi is not None and not pd.isna(thresh) and float(thresh) == float(hi):
                matched = ConditionClause(str(feat), op, lo, hi, bucket_id)
                break
            if op == ">" and lo is not None and not pd.isna(thresh) and float(thresh) == float(lo):
                matched = ConditionClause(str(feat), op, lo, hi, bucket_id)
                break
            if op == "range" and hi is not None and not pd.isna(thresh) and float(thresh) == float(hi):
                matched = ConditionClause(str(feat), op, lo, hi, bucket_id)
                break
        if matched is None and not pd.isna(thresh):
            if op == "<=":
                matched = ConditionClause(str(feat), "<=", None, float(thresh), f"{feat}_custom")
            elif op == ">":
                matched = ConditionClause(str(feat), ">", float(thresh), None, f"{feat}_custom")
        if matched:
            clauses.append(matched)
    return tuple(clauses)


def filter_candidate_rows(
    panel: pd.DataFrame,
    row: pd.Series,
) -> pd.DataFrame:
    """Apply Phase 2 candidate condition within its market transition context."""
    clauses = reconstruct_clauses_from_ledger_row(row)
    if not clauses:
        return pd.DataFrame()
    transition = str(row.get("market_transition", ""))
    ctx = panel[panel["research_market_transition"] == transition]
    return apply_condition(ctx, clauses)


def _horizon_col(horizon: str) -> str:
    return RETURN_COLUMNS.get(horizon, "t5_return")


def _candidate_metrics(
    candidate_rows: pd.DataFrame,
    panel: pd.DataFrame,
    row: pd.Series,
    horizon: str,
) -> Dict[str, Any]:
    col = _horizon_col(horizon)
    matured = candidate_rows[candidate_rows[col].notna()]
    cp = compute_horizon_profile(matured[col], horizon)
    baseline = compute_baseline_profiles(
        panel,
        market_transition=str(row.get("market_transition", "")),
        market_state=str(row.get("market_state", "")),
    )
    bp = baseline.profiles.get(horizon, compute_horizon_profile(pd.Series(dtype=float), horizon))
    inc = compute_incremental_metrics(cp, bp)
    return {
        "n": cp.n,
        "candidate_profile": cp,
        "baseline_profile": bp,
        "incremental": inc,
        "baseline_type": baseline.baseline_type,
    }


def test_leave_best_date_out(
    candidate_rows: pd.DataFrame,
    panel: pd.DataFrame,
    row: pd.Series,
    horizon: str,
) -> Dict[str, Any]:
    col = _horizon_col(horizon)
    matured = candidate_rows[candidate_rows[col].notna()].copy()
    if matured.empty:
        return {"result": "INSUFFICIENT", "reason": "no_matured_rows"}

    pre = _candidate_metrics(candidate_rows, panel, row, horizon)
    by_date = matured.groupby("trade_date")[col].median()
    best_date = str(by_date.idxmax())
    after_rows = candidate_rows[candidate_rows["trade_date"] != best_date]
    post = _candidate_metrics(after_rows, panel, row, horizon)

    post_inc_med = post["incremental"].get("incremental_median")
    fragile = post_inc_med is None or post_inc_med <= 0
    return {
        "test_name": "leave_best_date_out",
        "best_date_removed": best_date,
        "n_after_best_date_removal": post["n"],
        "pre_incremental_median": pre["incremental"].get("incremental_median"),
        "post_incremental_median": post_inc_med,
        "post_incremental_mean": post["incremental"].get("incremental_mean"),
        "post_incremental_wr": post["incremental"].get("incremental_win_rate"),
        "result": "DATE_FRAGILE" if fragile else "PASS",
        "reason": "incremental_median_lost_after_best_date_removal" if fragile else "",
    }


def test_leave_top_winners_out(
    candidate_rows: pd.DataFrame,
    panel: pd.DataFrame,
    row: pd.Series,
    horizon: str,
    pct: float,
) -> Dict[str, Any]:
    col = _horizon_col(horizon)
    matured = candidate_rows[candidate_rows[col].notna()].copy()
    if matured.empty:
        return {"result": "INSUFFICIENT", "pct": pct}

    pre = _candidate_metrics(candidate_rows, panel, row, horizon)
    n_remove = max(1, int(np.ceil(len(matured) * pct)))
    top_idx = matured[col].nlargest(n_remove).index
    after_rows = candidate_rows[~candidate_rows.index.isin(top_idx)]
    post = _candidate_metrics(after_rows, panel, row, horizon)

    post_inc_med = post["incremental"].get("incremental_median")
    fragile = post_inc_med is None or post_inc_med <= 0
    suffix = "5" if pct <= TOP_WINNER_PCT_5 + 0.001 else "10"
    return {
        "test_name": f"leave_top_winners_out_{suffix}pct",
        "pct_removed": pct,
        "rows_removed": n_remove,
        f"inc_median_without_top{suffix}": post_inc_med,
        f"inc_mean_without_top{suffix}": post["incremental"].get("incremental_mean"),
        f"inc_wr_without_top{suffix}": post["incremental"].get("incremental_wr"),
        "pre_incremental_median": pre["incremental"].get("incremental_median"),
        "post_incremental_median": post_inc_med,
        "result": "OUTLIER_FRAGILE" if fragile else "PASS",
        "reason": f"edge_lost_after_top_{suffix}pct_removal" if fragile else "",
    }


def classify_mean_median(
    candidate_profile,
) -> str:
    mean = candidate_profile.mean_return
    median = candidate_profile.median_return
    if mean is None or median is None:
        return "UNKNOWN"
    if mean > 0 and median <= 0:
        return "MEAN_ONLY"
    if mean > 0 and median > 0:
        return "DISTRIBUTION_SUPPORTED"
    if median > 0 and mean is not None and mean < median * 0.5:
        return "TAIL_RISK"
    return "UNKNOWN"


def test_symbol_concentration(candidate_rows: pd.DataFrame) -> Dict[str, Any]:
    if candidate_rows.empty:
        return {"result": "INSUFFICIENT"}
    n = len(candidate_rows)
    sym_counts = candidate_rows["symbol"].value_counts()
    top1 = int(sym_counts.iloc[0])
    top5 = int(sym_counts.head(5).sum())
    pct_top1 = top1 / n
    pct_top5 = top5 / n
    concentrated = pct_top1 >= SYMBOL_CONCENTRATION_SEVERE
    return {
        "test_name": "symbol_concentration",
        "unique_symbols": int(sym_counts.shape[0]),
        "max_observations_one_symbol": top1,
        "pct_rows_top1_symbol": round(pct_top1 * 100, 2),
        "pct_rows_top5_symbols": round(pct_top5 * 100, 2),
        "result": "SYMBOL_CONCENTRATED" if concentrated else "PASS",
        "reason": "single_symbol_dominates" if concentrated else "",
    }


def test_group_concentration(candidate_rows: pd.DataFrame) -> Dict[str, Any]:
    if "group" not in candidate_rows.columns:
        return {"test_name": "group_concentration", "result": "NOT_AVAILABLE"}
    groups = candidate_rows["group"].dropna()
    if groups.empty:
        return {"test_name": "group_concentration", "result": "NOT_AVAILABLE"}
    n = len(candidate_rows)
    gc = groups.value_counts()
    return {
        "test_name": "group_concentration",
        "unique_groups": int(gc.shape[0]),
        "pct_rows_top1_group": round(float(gc.iloc[0] / n * 100), 2),
        "result": "PASS",
    }


def test_temporal_consistency(
    candidate_rows: pd.DataFrame,
    panel: pd.DataFrame,
    row: pd.Series,
    horizon: str,
) -> Dict[str, Any]:
    col = _horizon_col(horizon)
    matured = candidate_rows[candidate_rows[col].notna()].copy()
    if matured.empty:
        return {"result": "INSUFFICIENT"}

    baseline = compute_baseline_profiles(
        panel,
        market_transition=str(row.get("market_transition", "")),
        market_state=str(row.get("market_state", "")),
    )
    bp = baseline.profiles.get(horizon)
    base_median = bp.median_return if bp else 0.0

    pos = neg = neutral = 0
    date_stats: List[Dict[str, Any]] = []
    for d, grp in matured.groupby("trade_date"):
        med = float(grp[col].median())
        inc = med - (base_median or 0)
        if inc > 0.5:
            pos += 1
            bucket = "positive"
        elif inc < -0.5:
            neg += 1
            bucket = "negative"
        else:
            neutral += 1
            bucket = "neutral"
        date_stats.append({"date": str(d), "median": med, "bucket": bucket})

    best_date = max(date_stats, key=lambda x: x["median"])["date"] if date_stats else ""
    worst_date = min(date_stats, key=lambda x: x["median"])["date"] if date_stats else ""

    return {
        "test_name": "temporal_consistency",
        "number_of_dates": len(date_stats),
        "positive_incremental_dates": pos,
        "negative_incremental_dates": neg,
        "neutral_dates": neutral,
        "best_date": best_date,
        "worst_date": worst_date,
        "result": "PASS",
    }


def test_date_dominance(candidate_rows: pd.DataFrame) -> Dict[str, Any]:
    if candidate_rows.empty:
        return {"result": "INSUFFICIENT"}
    n = len(candidate_rows)
    dc = candidate_rows["trade_date"].value_counts()
    largest_share = float(dc.iloc[0] / n)
    concentrated = largest_share >= DATE_CONCENTRATION_SEVERE
    return {
        "test_name": "date_dominance",
        "largest_date_share_of_candidate_rows": round(largest_share * 100, 2),
        "dominant_date": str(dc.index[0]),
        "result": "DATE_CONCENTRATED" if concentrated else "PASS",
        "reason": "single_date_over_50pct" if concentrated else "",
    }


def test_horizon_consistency(
    candidate_rows: pd.DataFrame,
    panel: pd.DataFrame,
    row: pd.Series,
    best_horizon: str,
) -> Dict[str, Any]:
    profile: Dict[str, Dict[str, Optional[float]]] = {}
    inc_by_h: Dict[str, Optional[float]] = {}
    for h in HORIZONS:
        m = _candidate_metrics(candidate_rows, panel, row, h)
        cp = m["candidate_profile"]
        profile[h] = {
            "incremental_median": m["incremental"].get("incremental_median"),
            "incremental_mean": m["incremental"].get("incremental_mean"),
            "incremental_wr": m["incremental"].get("incremental_win_rate"),
        }
        inc_by_h[h] = m["incremental"].get("incremental_median")

    bh = best_horizon
    others = [h for h in HORIZONS if h != bh]
    best_inc = inc_by_h.get(bh)
    negative_others = sum(1 for h in others if (inc_by_h.get(h) or 0) < -1)
    positive_others = sum(1 for h in others if (inc_by_h.get(h) or 0) > 0)

    if best_inc is not None and best_inc > 0 and positive_others >= 1:
        classification = "CONSISTENT"
    elif best_inc is not None and best_inc > 0 and negative_others >= 2:
        classification = "OUTLIER_DRIVEN"
    elif bh == "T10" and (inc_by_h.get("T3") or 0) < 0 and (inc_by_h.get("T5") or 0) < 0:
        classification = "OUTLIER_DRIVEN"
    elif bh == "T5" and (inc_by_h.get("T3") or 0) < 0 and (inc_by_h.get("T10") or 0) > 0:
        classification = "DELAYED"
    elif negative_others >= 1 and positive_others >= 1:
        classification = "MIXED"
    else:
        classification = "UNKNOWN"

    return {
        "test_name": "horizon_consistency",
        "best_horizon": bh,
        "horizon_profile": profile,
        "classification": classification,
        "result": "OUTLIER_DRIVEN" if classification == "OUTLIER_DRIVEN" else "PASS",
    }


def _neighbor_buckets(clause: ConditionClause) -> List[ConditionClause]:
    """Adjacent bucket(s) for one feature — does not modify original."""
    buckets = FEATURE_BUCKETS.get(clause.feature, ())
    ids = [b[0] for b in buckets]
    if clause.bucket_id not in ids:
        return []
    idx = ids.index(clause.bucket_id)
    neighbors: List[ConditionClause] = []
    if idx > 0:
        bid, lo, hi, op = buckets[idx - 1]
        neighbors.append(ConditionClause(clause.feature, op, lo, hi, bid))
    if idx < len(buckets) - 1:
        bid, lo, hi, op = buckets[idx + 1]
        neighbors.append(ConditionClause(clause.feature, op, lo, hi, bid))
    return neighbors


def test_neighborhood_stability(
    panel: pd.DataFrame,
    row: pd.Series,
    clauses: Sequence[ConditionClause],
    horizon: str,
) -> Dict[str, Any]:
    """Test one adjacent bucket per feature at a time."""
    transition = str(row.get("market_transition", ""))
    ctx = panel[panel["research_market_transition"] == transition]
    original = apply_condition(ctx, clauses)
    orig_m = _candidate_metrics(original, panel, row, horizon)
    orig_inc = orig_m["incremental"].get("incremental_median") or 0

    neighbor_results: List[Dict[str, Any]] = []
    clause_list = list(clauses)
    for i, clause in enumerate(clause_list):
        for neighbor in _neighbor_buckets(clause):
            replaced = list(clause_list)
            replaced[i] = neighbor
            nb_rows = apply_condition(ctx, tuple(replaced))
            nb_m = _candidate_metrics(nb_rows, panel, row, horizon)
            nb_inc = nb_m["incremental"].get("incremental_median")
            neighbor_results.append(
                {
                    "feature": clause.feature,
                    "neighbor_bucket": neighbor.bucket_id,
                    "n": nb_m["n"],
                    "incremental_median": nb_inc,
                }
            )

    if not neighbor_results:
        stability = "UNKNOWN"
    else:
        positive_neighbors = sum(1 for r in neighbor_results if (r.get("incremental_median") or 0) > 0)
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
        "result": "BOUNDARY_SENSITIVE" if stability == "BOUNDARY_SENSITIVE" else "PASS",
    }


def evaluate_robustness_status(
    tests: Dict[str, Any],
    episode_summary: Dict[str, Any],
    pre_incremental: Dict[str, Optional[float]],
    candidate_n: int,
) -> Tuple[str, List[str], List[str], str]:
    """
    Determine PASS / FRAGILE / REJECT and collect flags/reasons.
    """
    fragility_flags: List[str] = []
    rejection_reasons: List[str] = []

    pre_med = pre_incremental.get("incremental_median")
    if pre_med is None or pre_med <= 0:
        rejection_reasons.append("pre_incremental_median_non_positive")

    lbd = tests.get("leave_best_date_out", {})
    if lbd.get("result") == "DATE_FRAGILE":
        fragility_flags.append("DATE_FRAGILE")
        if (lbd.get("post_incremental_median") or 0) <= 0:
            rejection_reasons.append("incremental_median_gone_after_best_date_removal")

    top5 = tests.get("leave_top_winners_out_5pct", {})
    if top5.get("result") == "OUTLIER_FRAGILE":
        fragility_flags.append("OUTLIER_FRAGILE")
        if (top5.get("post_incremental_median") or 0) <= 0:
            rejection_reasons.append("incremental_median_gone_after_top5_removal")

    top10 = tests.get("leave_top_winners_out_10pct", {})
    if top10.get("result") == "OUTLIER_FRAGILE":
        fragility_flags.append("OUTLIER_TOP10_FRAGILE")

    mm = tests.get("mean_median", {})
    if mm.get("classification") == "MEAN_ONLY":
        fragility_flags.append("MEAN_ONLY")
        rejection_reasons.append("mean_positive_median_non_positive")

    sym = tests.get("symbol_concentration", {})
    if sym.get("result") == "SYMBOL_CONCENTRATED":
        fragility_flags.append("SYMBOL_CONCENTRATED")

    date_dom = tests.get("date_dominance", {})
    if date_dom.get("result") == "DATE_CONCENTRATED":
        fragility_flags.append("DATE_CONCENTRATED")

    hz = tests.get("horizon_consistency", {})
    if hz.get("classification") == "OUTLIER_DRIVEN":
        fragility_flags.append("OUTLIER_DRIVEN_HORIZON")

    nb = tests.get("neighborhood_stability", {})
    if nb.get("stability") == "BOUNDARY_SENSITIVE":
        fragility_flags.append("BOUNDARY_SENSITIVE")
    if nb.get("stability") == "ISOLATED_BUCKET":
        fragility_flags.append("ISOLATED_BUCKET")

    obs_ep = episode_summary.get("observed_episodes", 0)
    if obs_ep <= 1:
        fragility_flags.append("ONE_EPISODE_ONLY")

    post_n = lbd.get("n_after_best_date_removal", candidate_n)
    if post_n < CANDIDATE_MIN_N:
        rejection_reasons.append("sample_below_minimum_after_robustness_removal")

    if obs_ep < 1:
        rejection_reasons.append("no_observed_market_episode")

    if rejection_reasons:
        status = "REJECT"
    elif fragility_flags:
        status = "FRAGILE"
    else:
        status = "PASS"

    main_flag = fragility_flags[0] if fragility_flags else ""
    if status == "REJECT" and rejection_reasons:
        main_flag = rejection_reasons[0].upper().replace(" ", "_")

    return status, fragility_flags, rejection_reasons, main_flag
