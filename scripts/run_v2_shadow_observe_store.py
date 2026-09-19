#!/usr/bin/env python3
"""Read-only V2 SHADOW observe from collected Camera parquet.

Does not call KBS. Does not start Brain A. Does not write /var/lib/mrbot/intraday_memory.
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
    p = argparse.ArgumentParser(description="V2 SHADOW observe from collected Camera parquet")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--camera-root", type=Path, default=None)
    p.add_argument("--now", default=None, help="ISO VN override. Tests only")
    args = p.parse_args(argv)

    from modules.live_candidate_v2_action.contract import ALERT_ELIGIBLE, CANDIDATE_IS_BUY, PXV_IMPLIES_BUY
    from modules.live_candidate_v2_action.observe_store import observe_from_collected_session
    from modules.live_candidate_v2_action.sidecar_source import SOURCE_GITHUB
    from modules.live_shadow_transport.contract import VPS_SHADOW_STORE

    now = datetime.fromisoformat(args.now).replace(tzinfo=VN) if args.now else datetime.now(VN)
    out = args.out or Path(os.environ.get("MRBOT_LIVE_CAMERA_SHADOW_OUT", "data/intraday_pxv_live_shadow"))
    store = Path(os.environ.get("MRBOT_LIVE_PXV_SHADOW_STORE", VPS_SHADOW_STORE))
    payload = observe_from_collected_session(
        session=now.date(),
        now=now,
        camera_root=args.camera_root,
        out_dir=out,
        shadow_store_dir=store,
        sidecar_source=SOURCE_GITHUB,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if payload.get("candidate_is_buy") is True or payload.get("alert_eligible") is True:
        return 2
    assert CANDIDATE_IS_BUY is False and PXV_IMPLIES_BUY is False and ALERT_ELIGIBLE is False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
