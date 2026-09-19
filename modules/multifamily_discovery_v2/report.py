"""Render the Multi-Family Discovery V2 research report (markdown)."""

from __future__ import annotations

from typing import Any, Dict, List


def _md_table(headers: List[str], rows: List[List[Any]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join("" if c is None else str(c) for c in row) + " |" for row in rows]
    return "\n".join([line, sep, *body])


def _overall_verdict(scoreboard: List[Dict[str, Any]], split: Dict[str, Any]) -> str:
    oos_n = int(split.get("oos_rows") or 0)
    extra = [r for r in scoreboard if "CONTROL" not in str(r.get("family"))]
    promising = [r for r in extra if r.get("verdict") == "PROMISING"]
    if oos_n < 200:
        # Still allow a data-insufficiency overall if OOS is thin AND nothing promising.
        if not promising:
            return "D. CURRENT DATA INSUFFICIENT"
    if promising:
        if len(promising) >= 2:
            return "C. MULTI-FAMILY EXPANSION STRONGLY WARRANTED"
        return "B. LIMITED NON-RS EXPANSION WARRANTED"
    return "A. RS/RSI REMAINS SUFFICIENT"


def render_report(payload: Dict[str, Any]) -> str:
    audit = payload.get("_audit") or {}
    scoreboard = payload.get("scoreboard") or []
    experiments = payload.get("_experiments") or {}
    insight = payload.get("_insight") or {}
    split = payload.get("split") or {}
    overall = _overall_verdict(scoreboard, split)

    lines: List[str] = []
    lines.append("# Multi-Family Discovery V2 — Research Report")
    lines.append("")
    lines.append("**Status:** research-only. No production promotion.")
    lines.append(f"**Engine:** `{payload.get('engine_version')}`")
    lines.append(
        f"**Production untouched:** `{payload.get('production_untouched')}` "
        f"(violations: {payload.get('production_violations') or []})"
    )
    lines.append("")
    lines.append("## 1. Architecture")
    lines.append("")
    lines.append("### Current production path (CONTROL)")
    lines.append("")
    lines.append(
        "UI `Run discovery` → `EdgeResearchEngine.run_discovery()` → "
        "`build_research_panel()` (stock T0: `close, rs5, rs10, rsi14, rs_spread`) → "
        "`run_discovery()` over `SEARCH_FEATURES`. Challenger robustness-tests that ledger only."
    )
    lines.append("")
    lines.append("### V2 isolated path")
    lines.append("")
    lines.append(
        "`modules/multifamily_discovery_v2/` reads lifecycle/outcomes/market snapshots, "
        "writes only `data/multifamily_discovery_v2/`. It does not call "
        "`EdgeResearchEngine`, does not write `data/edge_research/`, and does not "
        "modify Learning Insight or earning-learning."
    )
    lines.append("")
    lines.append("### Files added")
    lines.append("")
    lines.append("- `modules/multifamily_discovery_v2/*`")
    lines.append("- `scripts/run_multifamily_discovery_v2.py`")
    lines.append("- `tests/test_multifamily_discovery_v2.py`")
    lines.append("- `docs/multifamily_discovery_v2_report.md`")
    lines.append("- `data/multifamily_discovery_v2/*` (research artifacts)")
    lines.append("")
    lines.append("Production Historical Discovery, Challenger, UI, timers, and trading rules are not modified.")
    lines.append("")
    lines.append("## 2. Feature audit")
    lines.append("")
    lines.append(
        f"Lifecycle rows: **{audit.get('n_rows')}**; symbols: **{audit.get('n_symbols')}**; "
        f"dates: {audit.get('date_min')} → {audit.get('date_max')} ({audit.get('n_dates')} dates)."
    )
    lines.append("")
    headers = [
        "field",
        "family",
        "datatype",
        "missing_pct",
        "date_cov%",
        "symbol_cov%",
        "eligible",
        "degenerate",
        "suitable",
    ]
    rows = []
    for f in audit.get("features") or []:
        rows.append(
            [
                f.get("field"),
                f.get("family"),
                f.get("datatype"),
                f.get("missing_pct"),
                f.get("coverage_by_date_pct"),
                f.get("coverage_by_symbol_pct"),
                f.get("search_eligible_v2"),
                f.get("degenerate_reason") or "",
                f.get("scientifically_suitable"),
            ]
        )
    lines.append(_md_table(headers, rows))
    lines.append("")
    lines.append(f"Empty aliases: `{audit.get('empty_aliases')}`")
    lines.append(f"Demoted from search after audit: `{payload.get('demoted_features')}`")
    lines.append("")
    lines.append("## 3. Search-space accounting")
    lines.append("")
    acc_headers = [
        "experiment",
        "features",
        "templates",
        "contexts",
        "unique hypotheses",
        "insufficient",
        "no incremental",
        "raw signal",
        "FDR survivors",
    ]
    acc_rows = []
    for spec_id, packed in experiments.items():
        d = packed.get("discovery") or {}
        acc_rows.append(
            [
                spec_id,
                ",".join(d.get("features_enabled") or []),
                d.get("templates_generated"),
                d.get("market_contexts"),
                d.get("unique_hypotheses"),
                d.get("rejected_insufficient_sample"),
                d.get("rejected_no_incremental_edge"),
                d.get("raw_signal_count"),
                d.get("fdr_survivors"),
            ]
        )
    lines.append(_md_table(acc_headers, acc_rows))
    lines.append("")
    lines.append(
        f"OOS split: discovery_end={split.get('discovery_end_date')}, "
        f"oos_start={split.get('oos_start_date')}, "
        f"discovery_rows={split.get('discovery_rows')}, oos_rows={split.get('oos_rows')}."
    )
    lines.append("")
    lines.append("Three-feature combinations: **disabled** (Phase 5 default).")
    lines.append("")
    lines.append("## 4. Family scoreboard")
    lines.append("")
    sb_headers = [
        "Family",
        "Coverage",
        "Hypotheses",
        "FDR",
        "PASS",
        "FRAGILE",
        "OOS T3",
        "OOS T5",
        "OOS T10",
        "Nested vs RS",
        "Top-regime share",
        "Verdict",
    ]
    sb_rows = []
    for r in scoreboard:
        sb_rows.append(
            [
                r.get("family"),
                r.get("coverage"),
                r.get("hypotheses_tested"),
                r.get("fdr_survivors"),
                r.get("robust_pass"),
                r.get("robust_fragile"),
                r.get("oos_t3_median_inc"),
                r.get("oos_t5_median_inc"),
                r.get("oos_t10_median_inc"),
                r.get("nested_vs_rs_max_inc_median"),
                r.get("concentration_risk"),
                r.get("verdict"),
            ]
        )
    lines.append(_md_table(sb_headers, sb_rows))
    lines.append("")
    lines.append("## 5. Incremental-edge analysis")
    lines.append("")
    lines.append(
        "Nested incremental median compares an RS+family hypothesis to the **nested RS-only "
        "subset** in the same market context. Positive nested lift is required before a family "
        "is treated as adding information beyond RS/RSI. Family-only singles have no nested RS "
        "subset; they are compared only to the same-transition baseline."
    )
    lines.append("")
    for r in scoreboard:
        lines.append(
            f"- **{r.get('family')}**: verdict `{r.get('verdict')}`; "
            f"nested vs RS max={r.get('nested_vs_rs_max_inc_median')}; "
            f"family-containing FDR survivors={r.get('family_containing_survivors')}."
        )
    lines.append("")
    lines.append("## 6. Robustness / OOS / episodes / concentration")
    lines.append("")
    for spec_id, packed in experiments.items():
        rob = packed.get("robustness") or {}
        ctx = packed.get("market_context") or {}
        lines.append(
            f"- **{spec_id}**: PASS={rob.get('robustness_pass')} "
            f"FRAGILE={rob.get('robustness_fragile')} REJECT={rob.get('robustness_reject')}; "
            f"transitions={ctx.get('n_transitions')}, top share={ctx.get('top_transition_share')}, "
            f"regime_specific={ctx.get('regime_specific')}."
        )
        for res in (rob.get("results") or [])[:8]:
            lines.append(
                f"  - `{res.get('condition_text')}` @ `{res.get('market_transition')}` → "
                f"{res.get('robustness_status')} / {res.get('scientific_status')} "
                f"(n={res.get('candidate_n')}, episodes={res.get('observed_episodes')}, "
                f"symbols={res.get('unique_symbol_count')}, flag={res.get('main_fragility_flag')})"
            )
    lines.append("")
    lines.append("A regime-specific survivor is **not** treated as universal edge.")
    lines.append("")
    lines.append("## 7. Learning Insight comparison")
    lines.append("")
    lines.append("Systems remain uncoupled. Comparison is descriptive only.")
    lines.append("")
    for cmp_ in insight.get("comparisons") or []:
        lines.append(
            f"- **{cmp_.get('family')}**: V2 `{cmp_.get('v2_verdict')}` vs Insight `{cmp_.get('insight_dimension')}` "
            f"(T3→T5 spread {cmp_.get('insight_t3_to_t5_spread_pct')}) → **{cmp_.get('relation')}**"
        )
    if not insight.get("comparisons"):
        lines.append("- No Insight comparison rows.")
    lines.append("")
    lines.append("## 8. Failure findings")
    lines.append("")
    lines.append(f"- Audit-demoted fields: `{payload.get('demoted_features')}`")
    lines.append("- `green2` / `early` / `pull` inventoried and not repaired.")
    lines.append("- Absolute `obv` / `volume` / `ema9` / `ma20` excluded as not cross-sectionally comparable.")
    lines.append("- `group` excluded (production action labels; circularity risk).")
    lines.append("- `leader_score` inventoried, not searched (sparsity).")
    interaction = payload.get("interaction") or {}
    lines.append(
        f"- Phase 5 interaction: skipped={interaction.get('skipped')} reason={interaction.get('reason')}"
    )
    lines.append("")
    lines.append("## 9. Final verdict")
    lines.append("")
    lines.append(f"**{overall}**")
    lines.append("")
    promising = payload.get("promising_families") or []
    if overall.startswith("B") or overall.startswith("C"):
        lines.append(
            "Families that deserve further **research** (not production): "
            + (", ".join(promising) if promising else "(see scoreboard)")
        )
        lines.append("")
        lines.append("Do **not** deploy to production Historical Discovery/Challenger yet.")
    else:
        lines.append(
            "No non-RS family demonstrated incremental, robust, out-of-sample information "
            "beyond the RS/RSI control under the predeclared V2 protocol."
        )
    lines.append("")
    lines.append("A larger search space is not automatically a better scientist.")
    lines.append("")
    return "\n".join(lines)
