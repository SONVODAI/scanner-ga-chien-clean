#!/usr/bin/env python3
"""Mature Follow-up Watch T3/T5/T10 outcomes (SHADOW / RESEARCH).

Requires MRBOT_V2_FOLLOWUP_WATCH=1 unless --force.
Uses only trading dates / prices with session <= --as-of (no future peek).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Mature Follow-up Watch outcomes as-of")
    p.add_argument("--as-of", required=True, help="YYYY-MM-DD (inclusive cutoff)")
    p.add_argument("--trading-dates", default="", help="Comma-separated VNIndex sessions")
    p.add_argument("--dir", type=Path, default=None)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    if not args.force and os.environ.get("MRBOT_V2_FOLLOWUP_WATCH", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print(json.dumps({"ok": False, "reason": "FEATURE_FLAG_OFF"}))
        return 2

    from modules.live_candidate_v2_followup.measure import mature_buy_ready_outcomes
    from modules.live_candidate_v2_followup.runtime import (
        load_price_maps,
        resolve_trading_dates,
    )

    dates = resolve_trading_dates(
        session=args.as_of,
        explicit=[d.strip() for d in args.trading_dates.split(",") if d.strip()] or None,
    )
    asof_dates = [d for d in dates if d <= str(args.as_of)[:10]]
    sym_px, vni_px = load_price_maps()
    result = mature_buy_ready_outcomes(
        directory=args.dir,
        symbol_session_prices=sym_px,
        vnindex_session_prices=vni_px,
        trading_dates=asof_dates,
        as_of_session=args.as_of,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
