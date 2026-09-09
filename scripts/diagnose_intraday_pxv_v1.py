#!/usr/bin/env python3
"""Post-examiner diagnosis. Read-only on an existing shadow ledger.

Writes only --out. Does not touch Camera, production, or the ledger.
Does not enable alerts, does not tune thresholds, does not use T+n.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from modules.intraday_pxv_v1.diagnose import diagnose, write_diagnosis


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", default="/tmp/pxv-v1-slice1-out/shadow_ledger.jsonl")
    p.add_argument("--out", default="/tmp/pxv-v1-slice1-diagnosis")
    p.add_argument("--focus", default="GMD:2026-08-28", help="SYMBOL:YYYY-MM-DD, optional extra")
    args = p.parse_args()
    ledger = Path(args.ledger)
    out = Path(args.out)
    if not ledger.exists():
        md = write_diagnosis(None, out)
        print(f"LEDGER_MISSING {ledger}", file=sys.stderr)
        print(f"Wrote design-only diagnosis (official persist rows only) to {md}")
        return 2
    result = diagnose(ledger)
    if args.focus and ":" in args.focus:
        sym, sess = args.focus.split(":", 1)
        from modules.intraday_pxv_v1.diagnose import annotate_sw_runs, explain_session
        from modules.intraday_pxv_v1.examine import SW, collect_runs, load_ledger

        df = load_ledger(ledger)
        sw = [r for r in collect_runs(df) if r["evidence"] in SW]
        ann = annotate_sw_runs(df, sw)
        focused = explain_session(df, ann, sym.upper(), sess)
        if focused["n_bars"]:
            # prepend so GMD is first even if not noisiest
            rest = [
                t
                for t in result["timelines"]
                if not (t["symbol"] == sym.upper() and t["session"] == sess)
            ]
            result["timelines"] = [focused] + rest
        else:
            result["focus_missing"] = args.focus
    md = write_diagnosis(result, out)
    print("======== POST-EXAMINER DIAGNOSIS ========")
    print(
        json.dumps(
            {
                "sw_runs": result["sw_runs"],
                "causes_one_bar_primary": result["causes"]["one_bar_runs"]["primary"],
                "causes_opposite_primary": result["causes"]["opposite_reversals"]["primary"],
                "normalized_alerts": [
                    {k: r[k] for k in ("rule", "baseline", "retained", "suppressed", "retention_pct")}
                    for r in result["normalized_alerts"]["table"]
                ],
                "would_be_alert_logged": result["would_be_alert_logged"],
                "would_be_alert_replay": result["would_be_alert_replay"],
                "would_be_alert_match": result["would_be_alert_match"],
                "timelines": [
                    {
                        "symbol": t["symbol"],
                        "session": t["session"],
                        "n_bars": t["n_bars"],
                        "run_exits": t.get("run_exits"),
                    }
                    for t in result["timelines"]
                ],
                "artifacts": str(out),
            },
            indent=2,
            default=str,
            ensure_ascii=False,
        )
    )
    print(f"markdown: {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
