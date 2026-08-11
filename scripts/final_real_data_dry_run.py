#!/usr/bin/env python3
"""Final real-data dry run — observational validation only (no weight changes)."""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from final_decision_engine import build_final_decision
from leader_memory import (
    HISTORY_FILE,
    RECOMMENDATION_FILE,
    _build_experience_frame,
    _build_recommendations,
    _load_config,
    _persist_learning_insight_candidates,
    _persist_recommendation_shadow,
    load_memory,
    load_pattern_library,
    load_recommendations,
    update_memory,
)
from modules.learning_insight_candidates import (
    build_learning_insight_candidates,
    compute_insight_candidate_score,
)
from modules.regime_alpha import (
    RECALL_LEVEL_EXACT,
    RECALL_LEVEL_FAMILY,
    RECALL_LEVEL_GLOBAL,
    RECALL_LEVEL_NO_EVIDENCE,
    classify_context_match,
    compute_recall_evidence,
    load_recall_index,
)
from modules.regime_alpha_forward_eval import IMMUTABLE_T0_FIELDS
from modules.regime_alpha_shadow import (
    build_shadow_candidate_universe,
    build_shadow_with_recall,
)


def _calc_market_real(df: pd.DataFrame) -> float:
    total = len(df)
    if total == 0:
        return 0.0
    e_ratio = len(df[df["E"] >= 1]) / total
    r_ratio = len(df[df["R"] >= 1]) / total
    o_ratio = len(df[df["O"] >= 1]) / total
    s_ratio = len(df[df["S"] >= 1]) / total
    strong = len(df[df["group"] == "CP MẠNH"])
    accel = len(df[df["group"] == "GÀ TĂNG TỐC"])
    pull_good = len(df[df["group"] == "PULL ĐẸP"])
    pull_ok = len(df[df["group"] == "PULL VỪA"])
    score = (
        e_ratio * 3.0
        + r_ratio * 2.5
        + o_ratio * 2.5
        + s_ratio * 2.0
        + min(strong / 12, 1) * 1.0
        + min(accel / 8, 1) * 1.2
        + min((pull_good + pull_ok) / 12, 1) * 0.8
    )
    return round(min(score, 13), 1)


def _calc_breadth(df: pd.DataFrame) -> float:
    rsi = pd.to_numeric(df.get("rsi14"), errors="coerce").dropna()
    if rsi.empty:
        return 50.0
    return float(round((rsi > 50).sum() / len(rsi) * 100))


def _snapshot_to_scan(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename = {
        "pull_label": "pullback",
        "green_2_confirm": "green2",
        "early_dry_green2": "early",
        "health": "evolution_health_group",
        "volume_ratio20": "volume_ratio20",
    }
    for src, dst in rename.items():
        if src in out.columns and dst not in out.columns:
            out[dst] = out[src]
    if "health" in out.columns and "health_group" not in out.columns:
        out["health_group"] = out["health"]
    if "is_live_adjusted" not in out.columns:
        out["is_live_adjusted"] = True
    return out


def _df_hash(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "EMPTY"
    payload = df.fillna("").astype(str).to_csv(index=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _score_stats(series: pd.Series) -> Dict[str, float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return {"min": np.nan, "max": np.nan, "mean": np.nan, "std": np.nan, "p95": np.nan}
    return {
        "min": round(float(s.min()), 4),
        "max": round(float(s.max()), 4),
        "mean": round(float(s.mean()), 4),
        "std": round(float(s.std()), 4),
        "p95": round(float(s.quantile(0.95)), 4),
    }


def _top10_symbols(df: pd.DataFrame, rank_col: str) -> List[str]:
    if df is None or df.empty or rank_col not in df.columns:
        return []
    sub = df.copy()
    sub[rank_col] = pd.to_numeric(sub[rank_col], errors="coerce")
    sub = sub[sub[rank_col].notna() & (sub[rank_col] <= 10)].sort_values(rank_col)
    return [str(s).strip().upper() for s in sub["symbol"].tolist()]


def rebuild_memory_from_snapshots() -> tuple[str, float, float, float]:
    snap_path = ROOT / "data" / "earning_money_snapshots.csv"
    snaps = pd.read_csv(snap_path)
    dates = sorted(snaps["snapshot_date"].astype(str).unique())
    session_date = dates[-1]

    for d in dates:
        day = _snapshot_to_scan(snaps[snaps["snapshot_date"] == d])
        mr = _calc_market_real(day)
        mf = 3.5 if d == "2026-08-07" else mr  # align with stored observations
        update_memory(
            day,
            session_date=d,
            market_real=mr,
            market_forecast=mf,
            breadth=_calc_breadth(day),
        )

    latest = _snapshot_to_scan(snaps[snaps["snapshot_date"] == session_date])
    return session_date, _calc_market_real(latest), 3.5, _calc_breadth(latest)


def run_engines(
    session_date: str,
    market_real: float,
    market_forecast: float,
    breadth: float,
) -> Dict[str, Any]:
    config = _load_config()
    brain = load_memory()
    patterns = load_pattern_library()
    production = load_recommendations()

    history = pd.read_csv(HISTORY_FILE) if HISTORY_FILE.exists() else pd.DataFrame()
    latest_snap = history[history["session_date"].astype(str) == session_date]
    experience = _build_experience_frame(
        latest_snap,
        market_real=market_real,
        market_forecast=market_forecast,
        breadth=breadth,
        brain=brain,
        history=history,
        session_date=session_date,
    )

    max_shadow = int(config.get("max_shadow_candidate_rows", 250))
    candidates = build_shadow_candidate_universe(brain, patterns, production, max_candidates=max_shadow)

    shadow = build_shadow_with_recall(
        candidates,
        brain,
        experience,
        session_date=session_date,
        market_real=market_real,
        market_forecast=market_forecast,
        breadth=breadth,
    )

    insight = build_learning_insight_candidates(
        candidates,
        brain,
        session_date=session_date,
        market_real=market_real,
        market_forecast=market_forecast,
        breadth=breadth,
    )

    return {
        "brain": brain,
        "patterns": patterns,
        "production": production,
        "experience": experience,
        "candidates": candidates,
        "shadow": shadow,
        "insight": insight,
    }


def build_comparison_table(data: Dict[str, Any]) -> pd.DataFrame:
    prod = data["production"].copy()
    shadow = data["shadow"].copy()
    insight = data["insight"].copy()

    prod["symbol"] = prod["symbol"].astype(str).str.strip().str.upper()
    shadow["symbol"] = shadow["symbol"].astype(str).str.strip().str.upper()
    insight["symbol"] = insight["symbol"].astype(str).str.strip().str.upper()

    prod_cols = prod[["symbol", "rank"]].rename(columns={"rank": "ProductionRank"})
    base_cols = shadow[
        [
            "symbol",
            "BaselineRank",
            "BaselineScore",
            "ShadowExperienceRank",
            "ShadowFinalScore",
            "PatternKnowledgeAdj",
            "ContinuationAdj",
            "HorizonAdj",
            "RecallComponent",
            "RecallConfidence",
            "ContextMatchMode",
            "ExperienceSamples",
            "LearnedWinRate",
            "ContinuationScore",
            "MatchedPattern",
            "MatchedMarketContext",
            "RecallLevel",
        ]
    ].rename(columns={"ShadowExperienceRank": "ShadowRank"})

    ins_cols = insight[
        ["symbol", "InsightRank", "InsightCandidateScore"]
    ]

    merged = prod_cols.merge(base_cols, on="symbol", how="outer")
    merged = merged.merge(ins_cols, on="symbol", how="outer")

    all_syms: Set[str] = set()
    for col, df in [
        ("BaselineRank", shadow),
        ("ShadowRank", shadow),
        ("InsightRank", insight),
        ("ProductionRank", prod),
    ]:
        rank_col = "ShadowExperienceRank" if col == "ShadowRank" else col.replace("ShadowRank", "ShadowExperienceRank")
        if col == "ShadowRank":
            rank_col = "ShadowExperienceRank"
        elif col == "BaselineRank":
            rank_col = "BaselineRank"
        elif col == "InsightRank":
            rank_col = "InsightRank"
        else:
            rank_col = "rank"
        sub = df.copy()
        sub[rank_col] = pd.to_numeric(sub[rank_col], errors="coerce")
        top = sub[sub[rank_col] <= 10].sort_values(rank_col)
        all_syms.update(top["symbol"].astype(str).str.upper())

    out = merged[merged["symbol"].isin(all_syms)].copy()
    sort_key = out["ProductionRank"].fillna(999)
    out = out.assign(_sort=sort_key).sort_values("_sort").drop(columns=["_sort"])
    return out.reset_index(drop=True)


def divergence_report(name_a: str, top_a: List[str], name_b: str, top_b: List[str]) -> Dict[str, Any]:
    set_a, set_b = set(top_a), set(top_b)
    return {
        "overlap_top10": len(set_a & set_b),
        f"{name_a}_only": sorted(set_a - set_b),
        f"{name_b}_only": sorted(set_b - set_a),
        "consensus": sorted(set_a & set_b),
    }


def context_match_counts(shadow: pd.DataFrame) -> Dict[str, Any]:
    counts = {"EXACT": 0, "FAMILY": 0, "GLOBAL": 0, "NO_EVIDENCE": 0}
    sample_dist: Dict[str, int] = {}
    for _, row in shadow.iterrows():
        level = str(row.get("RecallLevel", ""))
        if level == RECALL_LEVEL_EXACT:
            counts["EXACT"] += 1
        elif level == RECALL_LEVEL_FAMILY:
            counts["FAMILY"] += 1
        elif level == RECALL_LEVEL_GLOBAL:
            counts["GLOBAL"] += 1
        else:
            counts["NO_EVIDENCE"] += 1

        mode = str(row.get("ContextMatchMode", "") or "")
        samples = int(pd.to_numeric(row.get("ExperienceSamples", 0), errors="coerce") or 0)
        recall_samples = int(pd.to_numeric(row.get("RecallSamples", 0), errors="coerce") or 0)
        key = f"exp={samples},recall={recall_samples},mode={mode or 'NA'}"
        sample_dist[key] = sample_dist.get(key, 0) + 1

    return {"counts": counts, "sample_distribution_top20": dict(sorted(sample_dist.items(), key=lambda x: -x[1])[:20])}


def family_match_validation(shadow: pd.DataFrame, recall_index: pd.DataFrame) -> Dict[str, Any]:
    family_rows = shadow[shadow["RecallLevel"] == RECALL_LEVEL_FAMILY]
    examples = []
    for _, row in family_rows.head(5).iterrows():
        live_ctx = str(row.get("market_context_key", ""))
        matched = str(row.get("RecallMatchedContext", ""))
        mode = classify_context_match(live_ctx, matched)
        examples.append(
            {
                "symbol": row["symbol"],
                "live_context": live_ctx,
                "matched_context": matched,
                "classify": mode,
                "recall_confidence": row.get("RecallConfidence"),
                "recall_samples": row.get("RecallSamples"),
            }
        )
    return {"family_count": len(family_rows), "examples": examples}


def horizon_examples(shadow: pd.DataFrame) -> List[Dict[str, Any]]:
    examples = []
    for _, row in shadow.iterrows():
        t3 = pd.to_numeric(row.get("RecallT3Samples"), errors="coerce")
        t5 = pd.to_numeric(row.get("RecallT5Samples"), errors="coerce")
        t10 = pd.to_numeric(row.get("RecallT10Samples"), errors="coerce")
        hz = pd.to_numeric(row.get("HorizonAdj"), errors="coerce")
        if not np.isfinite(hz) or abs(hz) < 0.01:
            continue
        profile = "MIXED"
        mt3 = pd.to_numeric(row.get("RecallMeanT3"), errors="coerce")
        mt5 = pd.to_numeric(row.get("RecallMeanT5"), errors="coerce")
        mt10 = pd.to_numeric(row.get("RecallMeanT10"), errors="coerce")
        if np.isfinite(t3) and t3 >= 5 and (not np.isfinite(t5) or t5 < 5):
            profile = "T3-oriented"
        elif np.isfinite(t5) and t5 >= 5 and abs(hz) > 0:
            if np.isfinite(mt5) and np.isfinite(mt3) and mt5 < mt3 * 0.5:
                profile = "T3-oriented (T5 fade)"
            else:
                profile = "T5 continuation"
        if np.isfinite(t10) and t10 >= 5 and np.isfinite(mt10) and np.isfinite(mt3) and mt10 >= mt3:
            profile = "T10 compounder"
        examples.append(
            {
                "symbol": row["symbol"],
                "profile": profile,
                "HorizonAdj": hz,
                "RecallMeanT3": mt3,
                "RecallMeanT5": mt5,
                "RecallMeanT10": mt10,
                "RecallT3Samples": t3,
                "RecallT5Samples": t5,
                "RecallT10Samples": t10,
                "stock_pattern_key": row.get("stock_pattern_key"),
            }
        )
    examples.sort(key=lambda x: abs(float(x["HorizonAdj"] or 0)), reverse=True)
    return examples[:10]


def insight_independence_check(insight: pd.DataFrame, shadow: pd.DataFrame, production: pd.DataFrame) -> Dict[str, Any]:
    src = inspect.getsource(compute_insight_candidate_score)
    forbidden = ["ShadowFinalScore", "ShadowExperienceRank", "ProductionRank", "shadow_final"]
    found = [t for t in forbidden if t in src]
    build_src = inspect.getsource(build_learning_insight_candidates)
    build_forbidden = [t for t in forbidden if t in build_src]

    merged = insight.merge(
        shadow[["symbol", "ShadowFinalScore", "ShadowExperienceRank"]],
        on="symbol",
        how="left",
        suffixes=("", "_shadow"),
    )
    merged = merged.merge(production[["symbol", "rank"]], on="symbol", how="left")
    corr_shadow = merged["InsightCandidateScore"].corr(merged["ShadowFinalScore"])
    corr_rank = merged["InsightCandidateScore"].corr(merged["rank"])

    return {
        "forbidden_in_compute_insight_score": found,
        "forbidden_in_build_insight": build_forbidden,
        "correlation_insight_vs_shadow_score": round(float(corr_shadow), 4) if np.isfinite(corr_shadow) else None,
        "correlation_insight_vs_production_rank": round(float(corr_rank), 4) if np.isfinite(corr_rank) else None,
        "programmatically_independent": len(found) == 0 and len(build_forbidden) == 0,
    }


def insight_top10_reasons(insight: pd.DataFrame) -> List[Dict[str, Any]]:
    sub = insight.copy()
    sub["InsightRank"] = pd.to_numeric(sub["InsightRank"], errors="coerce")
    top = sub[sub["InsightRank"] <= 10].sort_values("InsightRank")
    rows = []
    for _, r in top.iterrows():
        rows.append(
            {
                "InsightRank": int(r["InsightRank"]),
                "symbol": r["symbol"],
                "InsightCandidateScore": r["InsightCandidateScore"],
                "InsightReason": r.get("InsightReason"),
                "MatchedPattern": r.get("MatchedPattern"),
                "ContextMatchMode": r.get("ContextMatchMode"),
                "ExperienceSamples": r.get("ExperienceSamples"),
                "LearnedWinRate": r.get("LearnedWinRate"),
                "ContinuationScore": r.get("ContinuationScore"),
                "PatternWinRateT3": r.get("PatternWinRateT3"),
                "PatternWinRateT5": r.get("PatternWinRateT5"),
                "PatternWinRateT10": r.get("PatternWinRateT10"),
                "ContinuationT3ToT5Rate": r.get("ContinuationT3ToT5Rate"),
                "ContinuationT3ToT10Rate": r.get("ContinuationT3ToT10Rate"),
            }
        )
    return rows


def forward_ledger_check() -> Dict[str, Any]:
    from modules.regime_alpha_forward_eval import INSIGHT_IMMUTABLE_T0_FIELDS

    required_ranks = [
        "BaselineRank",
        "ShadowExperienceRank",
        "ProductionRank",
    ]
    missing = [f for f in required_ranks if f not in IMMUTABLE_T0_FIELDS]
    ledger_path = ROOT / "brain" / "regime_alpha_shadow_ledger.csv"
    ledger_cols = list(pd.read_csv(ledger_path, nrows=0).columns) if ledger_path.exists() else []
    return {
        "immutable_t0_fields_count": len(IMMUTABLE_T0_FIELDS),
        "rank_fields_in_immutable": {f: f in IMMUTABLE_T0_FIELDS for f in required_ranks + ["InsightRank"]},
        "missing_required": missing,
        "insight_immutable_fields_count": len(INSIGHT_IMMUTABLE_T0_FIELDS),
        "InsightRank_in_insight_immutable": "InsightRank" in INSIGHT_IMMUTABLE_T0_FIELDS,
        "InsightEvidenceStatus_in_insight_immutable": "InsightEvidenceStatus" in INSIGHT_IMMUTABLE_T0_FIELDS,
        "ledger_has_baseline_and_shadow_ranks": all(c in ledger_cols for c in ["BaselineRank", "ShadowExperienceRank", "ProductionRank"]),
    }


def isolation_regression(
    session_date: str,
    market_real: float,
    market_forecast: float,
    breadth: float,
) -> Dict[str, Any]:
    prod_before = load_recommendations()
    prod_hash_before = _df_hash(prod_before)

    brain = load_memory()
    patterns = load_pattern_library()
    history = pd.read_csv(HISTORY_FILE)
    latest_snap = history[history["session_date"].astype(str) == session_date]
    experience = _build_experience_frame(
        latest_snap,
        market_real=market_real,
        market_forecast=market_forecast,
        breadth=breadth,
        brain=brain,
        history=history,
        session_date=session_date,
    )
    rec = prod_before.copy()

    buy_elite_stub = pd.DataFrame(
        [
            {
                "MÃ": "AAA",
                "KẾT LUẬN": "MUA ELITE",
                "EliteScore": 88,
                "EliteScoreBase": 85,
                "WinProb": 72,
                "ĐỘ TIN CẬY": "CAO",
                "ĐỒNG THUẬN": "4/5",
                "NHÓM": "CP MẠNH",
                "GIÁ": 10.0,
            }
        ]
    )
    elite_before, note_before = build_final_decision(buy_elite_stub)

    _persist_recommendation_shadow(
        rec, brain, experience, session_date,
        market_real=market_real, market_forecast=market_forecast, breadth=breadth, patterns=patterns,
    )
    _persist_learning_insight_candidates(
        rec, brain, session_date,
        market_real=market_real, market_forecast=market_forecast, breadth=breadth, patterns=patterns,
    )

    prod_after = load_recommendations()
    elite_after, note_after = build_final_decision(buy_elite_stub)

    return {
        "production_hash_before": prod_hash_before,
        "production_hash_after": _df_hash(prod_after),
        "production_identical": prod_hash_before == _df_hash(prod_after),
        "buy_elite_identical": _df_hash(elite_before) == _df_hash(elite_after),
        "buy_elite_note_identical": note_before == note_after,
    }


def score_scale_report(shadow: pd.DataFrame, insight: pd.DataFrame) -> Dict[str, Any]:
    baseline_stats = _score_stats(shadow["BaselineScore"])
    flags = []
    for col, max_expected in [
        ("PatternKnowledgeAdj", 8),
        ("ContinuationAdj", 8),
        ("HorizonAdj", 6),
        ("RecallComponent", 15),
    ]:
        stats = _score_stats(shadow[col])
        base_mean = baseline_stats["mean"]
        if np.isfinite(stats["max"]) and np.isfinite(base_mean) and base_mean > 0:
            if abs(stats["max"]) > base_mean * 0.25:
                conf = shadow.loc[shadow[col].abs() == shadow[col].abs().max(), "RecallConfidence"]
                samples = shadow.loc[shadow[col].abs() == shadow[col].abs().max(), "ExperienceSamples"]
                flags.append(
                    {
                        "component": col,
                        "max_abs": stats["max"],
                        "baseline_mean": base_mean,
                        "ratio_to_baseline_mean": round(abs(stats["max"]) / base_mean, 3),
                        "at_max_recall_confidence": float(conf.iloc[0]) if len(conf) else None,
                        "at_max_experience_samples": int(samples.iloc[0]) if len(samples) else None,
                        "expected_max_order": max_expected,
                    }
                )
    return {
        "BaselineScore": baseline_stats,
        "PatternKnowledgeAdj": _score_stats(shadow["PatternKnowledgeAdj"]),
        "ContinuationAdj": _score_stats(shadow["ContinuationAdj"]),
        "HorizonAdj": _score_stats(shadow["HorizonAdj"]),
        "RecallComponent": _score_stats(shadow["RecallComponent"]),
        "ShadowFinalScore": _score_stats(shadow["ShadowFinalScore"]),
        "InsightCandidateScore": _score_stats(insight["InsightCandidateScore"]),
        "dominance_flags": flags,
    }


def main() -> None:
    print("=" * 60)
    print("FINAL REAL-DATA DRY RUN")
    print("=" * 60)

    session_date, market_real, market_forecast, breadth = rebuild_memory_from_snapshots()
    print(f"\nSession: {session_date} | market_real={market_real} forecast={market_forecast} breadth={breadth}")

    data = run_engines(session_date, market_real, market_forecast, breadth)
    shadow = data["shadow"]
    insight = data["insight"]
    production = data["production"]
    recall_index = load_recall_index()

    comparison = build_comparison_table(data)
    print("\n## 1. TOP 10 COMPARISON TABLE")
    print(comparison.to_string(index=False))

    top_baseline = _top10_symbols(shadow, "BaselineRank")
    top_shadow = _top10_symbols(shadow, "ShadowExperienceRank")
    top_insight = _top10_symbols(insight, "InsightRank")
    top_prod = _top10_symbols(production, "rank")

    print("\n## 2. DIVERGENCE")
    bs = divergence_report("Baseline", top_baseline, "Shadow", top_shadow)
    print("Baseline vs Shadow:", json.dumps({**bs, "promoted_into_shadow": bs["Shadow_only"], "demoted_out_of_shadow": bs["Baseline_only"]}, indent=2))

    si = divergence_report("Shadow", top_shadow, "Insight", top_insight)
    print("Shadow vs Insight:", json.dumps(si, indent=2))

    ib = divergence_report("Baseline", top_baseline, "Insight", top_insight)
    print("Insight vs Baseline:", json.dumps({"overlap_top10": ib["overlap_top10"], "insight_only": ib["Insight_only"]}, indent=2))

    if top_baseline == top_shadow:
        print("\nBaseline == Shadow Top10 (identical). Reason: learning adjustments near zero or rank tie-break unchanged.")

    adj = shadow.copy()
    adj["net_learning"] = (
        pd.to_numeric(adj["PatternKnowledgeAdj"], errors="coerce").fillna(0)
        + pd.to_numeric(adj["ContinuationAdj"], errors="coerce").fillna(0)
        + pd.to_numeric(adj["HorizonAdj"], errors="coerce").fillna(0)
        + pd.to_numeric(adj["RecallComponent"], errors="coerce").fillna(0)
    )
    pos = adj.nlargest(5, "net_learning")[["symbol", "net_learning", "PatternKnowledgeAdj", "ContinuationAdj", "HorizonAdj", "RecallComponent"]]
    neg = adj.nsmallest(5, "net_learning")[["symbol", "net_learning", "PatternKnowledgeAdj", "ContinuationAdj", "HorizonAdj", "RecallComponent"]]
    print("\nLargest positive Shadow adjustments:\n", pos.to_string(index=False))
    print("\nLargest negative Shadow adjustments:\n", neg.to_string(index=False))

    print("\n## 3. SCORE SCALE")
    print(json.dumps(score_scale_report(shadow, insight), indent=2))

    print("\n## 4. CONTEXT MATCHING")
    ctx = context_match_counts(shadow)
    print(json.dumps(ctx, indent=2))
    print("FAMILY validation:", json.dumps(family_match_validation(shadow, recall_index), indent=2))

    print("\n## 5. HORIZON EXAMPLES")
    hz = horizon_examples(shadow)
    print(json.dumps(hz, indent=2, default=str))
    if not hz:
        print("(No symbols with non-zero HorizonAdj in current universe)")

    print("\n## 6. INSIGHT INDEPENDENCE & EVIDENCE STATUS")
    status_counts = insight["InsightEvidenceStatus"].astype(str).value_counts().to_dict()
    qualified = int(status_counts.get("QUALIFIED", 0))
    fallback = len(insight) - qualified
    coverage = round(qualified / len(insight) * 100, 2) if len(insight) else 0.0
    print(json.dumps({
        **insight_independence_check(insight, shadow, production),
        "evidence_status_counts": status_counts,
        "qualified_count": qualified,
        "fallback_count": fallback,
        "coverage_pct": coverage,
    }, indent=2))
    print("Insight Top10 reasons:", json.dumps(insight_top10_reasons(insight), indent=2, default=str))

    print("\n## 7. ISOLATION REGRESSION")
    print(json.dumps(isolation_regression(session_date, market_real, market_forecast, breadth), indent=2))

    print("\n## 8. FORWARD LEDGER")
    from modules.regime_alpha_forward_eval import (
        INSIGHT_IMMUTABLE_T0_FIELDS,
        freeze_insight_t0_ledger,
        load_insight_forward_ledger,
        EVAL_MODE_FORWARD_FROZEN,
    )
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ledger_path = Path(tmp) / "insight_ledger.csv"
        freeze_insight_t0_ledger(
            insight,
            evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
            ledger_path=ledger_path,
        )
        frozen = load_insight_forward_ledger(ledger_path=ledger_path)
        sample = frozen.head(3).to_dict(orient="records") if not frozen.empty else []
    print(json.dumps({
        **forward_ledger_check(),
        "insight_immutable_fields_count": len(INSIGHT_IMMUTABLE_T0_FIELDS),
        "InsightRank_in_insight_immutable": "InsightRank" in INSIGHT_IMMUTABLE_T0_FIELDS,
        "frozen_ledger_sample": sample,
    }, indent=2, default=str))

    out_path = ROOT / "brain" / "final_dry_run_report.json"
    report = {
        "session_date": session_date,
        "market": {"real": market_real, "forecast": market_forecast, "breadth": breadth},
        "comparison_table": comparison.to_dict(orient="records"),
        "top10": {
            "baseline": top_baseline,
            "shadow": top_shadow,
            "insight": top_insight,
            "production": top_prod,
        },
        "score_scale": score_scale_report(shadow, insight),
        "context_matching": ctx,
        "horizon_examples": hz,
        "insight_reasons": insight_top10_reasons(insight),
    }
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nReport saved: {out_path}")


if __name__ == "__main__":
    main()
