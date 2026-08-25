"""Build BACKFILL_REPORT.md + research freeze from checkpoint (no provider calls)."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from modules.foreign_flow_history.backfill import build_research_freeze, load_eligibility
from modules.foreign_flow_history.store import load_checkpoint, resolve_root, symbol_coverage_summary


def build_report(
    root: Path = Path("data/foreign_flow_history"),
    out: Path = Path("diagnostics/foreign_flow_canonical_backfill/BACKFILL_REPORT.md"),
    eligibility_path: Path = Path("diagnostics/foreign_flow_historical_audit/ems142_hsx_eligibility.json"),
) -> dict:
    eligibility = load_eligibility(eligibility_path)
    cp = load_checkpoint(root)
    symbols = cp.get("symbols") or {}

    completed = []
    failed = []
    rate_limited = []
    empty = []
    for sym, meta in sorted(symbols.items()):
        st = meta.get("status")
        if st in ("completed", "completed_with_anomalies"):
            completed.append((sym, meta))
        elif st == "completed_empty":
            empty.append(sym)
        elif st == "rate_limited":
            rate_limited.append(sym)
        elif st in ("failed", "write_failed"):
            failed.append((sym, meta))

    rows = [int(m.get("n_rows") or 0) for _, m in completed]
    firsts = [m["first_trade_date"] for _, m in completed if m.get("first_trade_date")]
    lasts = [m["last_trade_date"] for _, m in completed if m.get("last_trade_date")]

    hose = set(eligibility["hose_eligible"])
    completed_set = {s for s, _ in completed}
    hose_cov = sorted(hose & completed_set)

    disk = 0
    for p in (root / "canonical" / "by_symbol").glob("*.csv"):
        disk += p.stat().st_size
    for p in (root / "raw").glob("*.jsonl"):
        disk += p.stat().st_size

    integrity = [
        {"symbol": s, "codes": m.get("issue_codes")}
        for s, m in completed
        if m.get("status") == "completed_with_anomalies"
    ]

    n_hose = len(hose)
    n_cov = len(hose_cov)
    stage_b_done = n_cov >= n_hose and not rate_limited and not failed

    if stage_b_done:
        verdict = "FOREIGN_FLOW_CANONICAL_BACKFILL_COMPLETE"
        blind = "YES"
    elif completed and (rate_limited or failed or n_cov < n_hose):
        verdict = "FOREIGN_FLOW_CANONICAL_BACKFILL_PARTIAL_RESUMABLE"
        # Blind ready if we have deep multi-year panel for a usable HOSE cohort
        blind = "YES" if n_cov >= 50 and (max(rows) if rows else 0) >= 1000 else "NO"
    elif not completed:
        verdict = "FOREIGN_FLOW_BACKFILL_BLOCKED"
        blind = "NO"
    else:
        verdict = "FOREIGN_FLOW_CANONICAL_BACKFILL_PARTIAL_RESUMABLE"
        blind = "NO"

    freeze = None
    if completed:
        freeze = build_research_freeze(root, eligibility_path)

    lines = [
        "# Canonical HSX Foreign Flow Historical Backfill — Report",
        "",
        f"**Schema:** `ff_hsx_symbol_daily_v1`",
        f"**Grain:** `trade_date × symbol`",
        f"**Store:** `{root}`",
        f"**Freeze dataset:** `{freeze['dataset_version'] if freeze else 'n/a'}`",
        "",
        "## Final verdict",
        "",
        f"`{verdict}`",
        "",
        f"`BLIND_FOREIGN_FLOW_RESEARCH_READY = {blind}`",
        "",
        "## Coverage summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Symbols attempted (checkpoint) | {len(symbols)} |",
        f"| Symbols completed | {len(completed)} |",
        f"| Symbols empty | {len(empty)} |",
        f"| Symbols failed | {len(failed)} |",
        f"| Symbols rate-limited | {len(rate_limited)} |",
        f"| Total rows | {sum(rows)} |",
        f"| Earliest date | {min(firsts) if firsts else None} |",
        f"| Latest date | {max(lasts) if lasts else None} |",
        f"| Median sessions/symbol | {statistics.median(rows) if rows else None} |",
        f"| Max sessions/symbol | {max(rows) if rows else None} |",
        f"| Current EMS HOSE coverage | {n_cov}/{n_hose} |",
        f"| Excluded HNX/UPCOM | {len(eligibility['hsx_empty'])} |",
        f"| Disk footprint (bytes) | {disk} |",
        f"| Integrity soft/hard anomalies | {len(integrity)} |",
        "",
        "## Excluded HNX/UPCOM (not fabricated)",
        "",
        ", ".join(eligibility["hsx_empty"]),
        "",
        "## Known biases",
        "",
        "- Current EMS HOSE overlap is present-day relevance, not historical membership-as-of.",
        "- Listing-age bias: long-listed names have deeper history.",
        "- No complete historical HOSE membership reconstruction claimed (Stage C not complete).",
        "- Raw provider OHLC; corporate-action adjustment unverified.",
        "- Market-context / ADV overlap much shorter than foreign-flow history.",
        "",
        "## Price outcome readiness (no labels computed)",
        "",
        "Same-provider OHLC supports later session-based T1/T3/T5/T10/(T20) and path MFE/MAE.",
        "Outcome labels are **not** mixed into T0 canonical rows.",
        "",
        "## Resumability",
        "",
        "Checkpoint: `data/foreign_flow_history/manifests/backfill_checkpoint.json`.",
        "Re-run stages skip `status=completed` symbols. Partial failure does not destroy completed symbols.",
        "",
        "## Failed / rate-limited",
        "",
        f"- failed: {failed}",
        f"- rate_limited: {rate_limited}",
        "",
        "## Production safety",
        "",
        "No P0 / Forecast / MDRR / Edge / Camera / Streamlit / systemd mutations in this task.",
        "",
        "STOP — no edge discovery performed.",
        "",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "verdict": verdict,
        "BLIND_FOREIGN_FLOW_RESEARCH_READY": blind,
        "n_completed": len(completed),
        "n_failed": len(failed),
        "n_rate_limited": len(rate_limited),
        "total_rows": sum(rows),
        "ems_hose_coverage": f"{n_cov}/{n_hose}",
        "freeze": freeze["dataset_version"] if freeze else None,
        "report": str(out),
    }
    (out.parent / "BACKFILL_SUMMARY.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2))
