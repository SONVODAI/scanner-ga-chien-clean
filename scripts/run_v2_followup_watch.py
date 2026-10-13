#!/usr/bin/env python3
"""Run one Follow-up Watch research session (SHADOW only).

Requires MRBOT_V2_FOLLOWUP_WATCH=1. Does not enable production BUY.
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
    p.add_argument("--market-real", type=float, required=True)
    p.add_argument(
        "--trading-dates",
        required=True,
        help="Comma-separated VNIndex sessions, oldest→newest",
    )
    p.add_argument("--sidecar", type=Path, default=None)
    p.add_argument("--scan-csv", type=Path, default=None)
    p.add_argument("--dir", type=Path, default=None)
    p.add_argument("--force", action="store_true", help="Bypass env flag (tests)")
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
    from modules.live_candidate_v2_followup.guardian_bridge import guardian_map_from_scan
    from modules.live_candidate_v2_followup.session import run_followup_session

    sidecar_rows = []
    if args.sidecar and args.sidecar.exists():
        doc = json.loads(args.sidecar.read_text(encoding="utf-8"))
        sidecar_rows = list(doc.get("rows") or [])

    scan_by = {}
    guard = {}
    if args.scan_csv and args.scan_csv.exists():
        import pandas as pd

        scan = pd.read_csv(args.scan_csv)
        if "symbol" in scan.columns:
            for _, row in scan.iterrows():
                sym = str(row.get("symbol") or "").strip().upper()
                if sym:
                    scan_by[sym] = dict(row)
            guard = guardian_map_from_scan(scan)

    dates = [d.strip() for d in args.trading_dates.split(",") if d.strip()]
    result = run_followup_session(
        session=args.session,
        observed_at=as_vn(datetime.now().astimezone()),
        market_real=args.market_real,
        trading_dates=dates,
        sidecar_rows=sidecar_rows,
        scan_by_symbol=scan_by,
        guardian_by_symbol=guard,
        directory=args.dir,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
