#!/usr/bin/env python3
"""Research-only live 5m Camera shadow sweep.

Default is a dry-run against an injected/mock provider. Real KBS reads require
--live and vnstock 4.x. Never writes the canonical Camera archive. Never alerts.

V2 SHADOW observation uses the Gate B published sidecar (GitHub Contents)
unless --v2-sidecar / MRBOT_V2_CAMERA_SIDECAR points at an explicit file.
Never falls back to a stale repo-local sidecar. Never treats Elite as V2.
"""
from __future__ import annotations

import argparse
import json
import os
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
    p.add_argument("--watchlist", type=Path, default=None, help="Dynamic Watchlist JSON (overrides GitHub fetch)")
    p.add_argument("--v2-sidecar", type=Path, default=None, help="V2 Camera sidecar file (overrides GitHub fetch)")
    p.add_argument("--out", type=Path, default=None, help="Isolated shadow output dir")
    p.add_argument("--now", default=None, help="Override now (ISO VN). Dry-run / tests only")
    args = p.parse_args(argv)

    from modules.live_camera_shadow.feed import (
        LiveShadowFeed,
        default_shadow_dir,
        load_watchlist_rows,
    )
    from modules.live_camera_shadow.rate import rate_report
    from modules.live_candidate_v2_action.contract import ENV_V2_SIDECAR, ENV_V2_SIDECAR_SOURCE
    from modules.live_candidate_v2_action.sidecar_source import SOURCE_FILE, SOURCE_GITHUB
    from modules.live_shadow_transport.contract import VPS_SHADOW_STORE

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
    out = args.out or default_shadow_dir()
    shadow_store = Path(os.environ.get("MRBOT_LIVE_PXV_SHADOW_STORE", VPS_SHADOW_STORE))
    v2_path = args.v2_sidecar
    if v2_path is None:
        env_v2 = os.environ.get(ENV_V2_SIDECAR, "").strip()
        if env_v2:
            v2_path = Path(env_v2)
    if v2_path is not None:
        v2_source = SOURCE_FILE
    else:
        v2_source = (os.environ.get(ENV_V2_SIDECAR_SOURCE, "") or SOURCE_GITHUB).strip().lower() or SOURCE_GITHUB
    feed_kwargs = dict(
        provider=KBSProvider(requests_per_minute=18),
        out_dir=out,
        now_fn=lambda: now,
        shadow_store_dir=shadow_store,
        v2_sidecar_path=v2_path,
        v2_sidecar_source=v2_source,
    )
    if args.watchlist:
        rows = load_watchlist_rows(args.watchlist)
        feed = LiveShadowFeed(
            **feed_kwargs,
            watchlist_path=args.watchlist,
            watchlist_source="file",
        )
        status = feed.run_cycle(rows)
    else:
        feed = LiveShadowFeed(
            **feed_kwargs,
            watchlist_source="github",
        )
        status = feed.run_cycle()
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status.get("alert_eligible") is False else 2


if __name__ == "__main__":
    raise SystemExit(main())
