#!/usr/bin/env python3
"""Read-only Slice 1C published-evidence human case review.

Reads an existing Slice 1C shadow ledger. Writes only --out.
Does not touch Camera, production, or the input ledger.
Does not change thresholds, debounce, or enable alerts.
Does not use T+n.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from modules.intraday_pxv_v1.human_review import review_ledger, write_review


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", default="/tmp/pxv-v1-slice1c-debounce/shadow_ledger.jsonl")
    p.add_argument("--out", default="/tmp/pxv-v1-slice1c-human-review")
    args = p.parse_args()
    ledger = Path(args.ledger)
    out = Path(args.out)
    if not ledger.exists():
        print(f"LEDGER_MISSING {ledger}", file=sys.stderr)
        print(
            "Run in an isolated /tmp clone against the official Slice 1C replay ledger. "
            "Do not checkout /opt/mrbot-camera.",
            file=sys.stderr,
        )
        return 2
    result = review_ledger(ledger)
    md = write_review(result, out)
    print("======== SLICE 1C HUMAN CASE REVIEW ========")
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "n_rows": result.get("n_rows"),
                "checks": result.get("checks"),
                "label_counts": result.get("label_counts"),
                "cases": [
                    {
                        "symbol": c["symbol"],
                        "session": c["session"],
                        "role": c["role"],
                        "label": c["label"],
                        "first_published": c.get("first_published"),
                        "first_published_hm": c.get("first_published_hm"),
                        "missing": c.get("missing"),
                    }
                    for c in result.get("cases") or []
                ],
                "artifacts": str(md),
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
