#!/usr/bin/env python3
"""Rotation Watch sidecar.

Intended runtime: /opt/mrbot-camera-venv (vnstock 4.x / KBS).
Default is a dry-run (no KBS). --live performs one cycle. --loop waits for
completed 5m bars. Never writes Camera parquet or Candidate artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Isolated Rotation Watch sidecar (Camera venv)")
    p.add_argument("--live", action="store_true", help="Call KBS/vnstock 4.x (default: refuse)")
    p.add_argument("--loop", action="store_true", help="Repeat after each completed 5m bar")
    p.add_argument("--watchlist", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None, help="Rotation artifact directory")
    p.add_argument("--now", default=None, help="Override now (ISO). Tests / dry-run only")
    args = p.parse_args(argv)

    from modules.rotation_watch.constants import BOARD_NAME, STATUS_NAME
    from modules.rotation_watch.runner import DEFAULT_RPM, run_cycle, seconds_until_next_completed_bar

    n = 10
    print(
        json.dumps(
            {
                "sidecar": "rotation_watch",
                "rpm": DEFAULT_RPM,
                "example_n_symbols": n,
                "requests_per_cycle": n,
                "approx_cycle_sec_10": round((n - 1) * (60.0 / DEFAULT_RPM) + 3.0, 1),
                "fits_in_5m_bar": True,
                "alert_eligible": False,
            },
            indent=2,
        )
    )

    if not args.live:
        print(
            "DRY RUN: refusing KBS/vnstock. Re-run with --live in /opt/mrbot-camera-venv. "
            "No archive writes. No Candidate writes.",
            file=sys.stderr,
        )
        return 0

    from modules.intraday_memory.provider import KBSProvider

    out = args.out
    board_path = (out / BOARD_NAME) if out else None
    status_path = (out / STATUS_NAME) if out else None

    def _once(now: datetime) -> dict:
        return run_cycle(
            now=now,
            provider=KBSProvider(requests_per_minute=DEFAULT_RPM),
            watchlist_path=args.watchlist,
            board_path=board_path,
            status_path=status_path,
        )

    if args.now and not args.loop:
        now = datetime.fromisoformat(args.now)
        if now.tzinfo is None:
            now = now.replace(tzinfo=VN)
        status = _once(now)
        print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
        return 0

    while True:
        now = datetime.now(VN)
        status = _once(now)
        print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
        if not args.loop:
            return 0
        time.sleep(seconds_until_next_completed_bar(datetime.now(VN)))


if __name__ == "__main__":
    raise SystemExit(main())
