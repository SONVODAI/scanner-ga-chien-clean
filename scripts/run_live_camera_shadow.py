#!/usr/bin/env python3
"""Research-only live 5m Camera shadow sweep.

Default is a dry-run against an injected/mock provider. Real KBS reads require
--live and vnstock 4.x. Never writes the canonical Camera archive. Never alerts.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Isolated live 5m Camera → P×V shadow sweep")
    p.add_argument("--live", action="store_true", help="Call KBS/vnstock (default: refuse without --live)")
    p.add_argument("--watchlist", type=Path, default=None, help="Dynamic Watchlist JSON")
    p.add_argument("--out", type=Path, default=None, help="Isolated shadow output dir")
    p.add_argument("--now", default=None, help="Override now (ISO VN). Dry-run / tests only")
    args = p.parse_args(argv)

    from modules.live_camera_shadow.feed import (
        LiveShadowFeed,
        default_shadow_dir,
        default_watchlist_path,
        load_watchlist_rows,
    )
    from modules.live_camera_shadow.rate import rate_report

    print(json.dumps(rate_report(), ensure_ascii=False, indent=2))

    if not args.live:
        print(
            "DRY RUN: refusing KBS/vnstock. Re-run with --live for a real session read. "
            "No archive writes. No alerts.",
            file=sys.stderr,
        )
        return 0

    from modules.intraday_memory.provider import KBSProvider

    now = datetime.fromisoformat(args.now).replace(tzinfo=VN) if args.now else datetime.now(VN)
    watch_path = args.watchlist or default_watchlist_path()
    rows = load_watchlist_rows(watch_path)
    out = args.out or default_shadow_dir()
    feed = LiveShadowFeed(
        provider=KBSProvider(requests_per_minute=18),
        out_dir=out,
        now_fn=lambda: now,
        watchlist_path=watch_path,
    )
    status = feed.run_cycle(rows)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status.get("alert_eligible") is False else 2


if __name__ == "__main__":
    raise SystemExit(main())
