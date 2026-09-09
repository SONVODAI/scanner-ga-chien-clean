#!/usr/bin/env python3
"""Slice 1B: read-only examiner of an existing shadow ledger.

Writes only to --out (default /tmp/pxv-v1-slice1-examiner).
Does not touch Camera, production checkout, or the input ledger.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from modules.intraday_pxv_v1.examine import examine, write_examiner, load_ledger, compare_raw_published, write_compare


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--ledger",
        default="/tmp/pxv-v1-slice1-out/shadow_ledger.jsonl",
    )
    p.add_argument(
        "--report",
        default="/tmp/pxv-v1-slice1-out/shadow_report.json",
    )
    p.add_argument(
        "--out",
        default="/tmp/pxv-v1-slice1-examiner",
    )
    p.add_argument(
        "--evidence-col",
        default="evidence",
        help="Column to examine: evidence | raw_evidence | published_evidence",
    )
    p.add_argument("--compare", action="store_true", help="Write RAW vs PUBLISHED compare")
    args = p.parse_args()
    ledger = Path(args.ledger)
    if not ledger.exists():
        print(f"LEDGER_MISSING {ledger}", file=sys.stderr)
        return 2
    df = load_ledger(ledger)
    col = args.evidence_col
    if col not in df.columns:
        col = "evidence"
    result = examine(ledger, Path(args.report) if args.report else None, evidence_col=col)
    out = Path(args.out)
    write_examiner(result, out)
    if args.compare:
        cmp = compare_raw_published(df, str(ledger))
        write_compare(cmp, out)
        print("======== DEBOUNCE COMPARE ========")
        print(f"VERDICT: {cmp['debounce_verdict']['verdict']}")
        print(cmp["debounce_verdict"]["why"])
        print(json.dumps(cmp["comparison_table"], indent=2, default=str))
    v = result["verdict_block"]
    persist = result["persistence"]
    sim = result["alert_simulation"]
    print("======== SLICE 1B EXAMINER ========")
    print(f"EVIDENCE_COL: {col}")
    print(f"VERDICT: {v['verdict']}")
    print(v["why"])
    print(
        json.dumps(
            {
                "raw_transitions": result["raw_transition_arrows"],
                "sw_runs": persist["sw_runs"],
                "persist": {
                    k: persist[k]
                    for k in (
                        "1_bar",
                        "ge_2_bars",
                        "ge_3_bars",
                        "ge_15_min",
                        "ge_30_min",
                        "median_persist_bars",
                        "median_persist_min",
                        "direct_opposite_reversals",
                        "returned_to_neutral",
                    )
                },
                "timing_first_sw": result.get("timing_first_sw"),
                "timing_stable_ge2": result["timing_stable_ge2_first_hm"],
                "alerts": {k: sim[k] for k in sim if k.startswith("R")},
                "candidates": {
                    k: result["candidates"][k]
                    for k in (
                        "noisy_flicker_n",
                        "clean_persistent_n",
                        "never_leave_neutral_n",
                        "unusable_dominated_n",
                    )
                },
                "dgc": result["examples"]["structural"],
                "alert_eligible_true_count": result.get("alert_eligible_true_count"),
                "artifacts": str(out),
            },
            indent=2,
            default=str,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
