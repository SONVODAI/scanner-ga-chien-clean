#!/usr/bin/env python3
"""Run one Follow-up Watch research session (SHADOW only).

Requires MRBOT_V2_FOLLOWUP_WATCH=1. Does not enable production BUY.
Preferred entry for manual / post-approval scheduled research ticks.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="V2 Follow-up Watch research session")
    p.add_argument("--session", required=True, help="YYYY-MM-DD")
    p.add_argument("--market-real", type=float, default=None)
    p.add_argument(
        "--trading-dates",
        default="",
        help="Comma-separated VNIndex sessions, oldest→newest",
    )
    p.add_argument("--sidecar", type=Path, default=None)
    p.add_argument("--scan-csv", type=Path, default=None)
    p.add_argument("--dir", type=Path, default=None)
    p.add_argument("--force", action="store_true", help="Bypass env flag (tests)")
    p.add_argument("--allow-retry", action="store_true", help="Re-run same session")
    args = p.parse_args()

    if not args.force and os.environ.get("MRBOT_V2_FOLLOWUP_WATCH", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print(json.dumps({"ok": False, "reason": "FEATURE_FLAG_OFF"}))
        return 2

    from modules.live_candidate.calendar import as_vn
    from modules.live_candidate_v2_followup.runtime import (
        load_scan_by_symbol,
        run_followup_runtime_cycle,
    )

    sidecar_rows = []
    if args.sidecar and args.sidecar.exists():
        doc = json.loads(args.sidecar.read_text(encoding="utf-8"))
        sidecar_rows = list(doc.get("rows") or [])

    if args.scan_csv:
        os.environ["MRBOT_V2_FOLLOWUP_SCAN_CSV"] = str(args.scan_csv)

    dates = [d.strip() for d in args.trading_dates.split(",") if d.strip()] or None
    scan_by = load_scan_by_symbol(scan_csv=args.scan_csv, sidecar_rows=sidecar_rows)
    result = run_followup_runtime_cycle(
        session=args.session,
        observed_at=as_vn(datetime.now().astimezone()),
        sidecar_rows=sidecar_rows,
        market_real=args.market_real,
        trading_dates=dates,
        scan_by_symbol=scan_by,
        directory=args.dir,
        force=args.force,
        allow_retry=args.allow_retry,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
