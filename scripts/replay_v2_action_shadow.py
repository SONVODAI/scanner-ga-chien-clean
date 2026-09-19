#!/usr/bin/env python3
"""Deterministic SHADOW V2 Action Layer replay.

freeze_ledger / sidecar nomination as-of + historical completed 5m parquet.
Does not use Elite CSV save time as first_seen.
Does not tune thresholds against T+n.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Replay V2 Action Layer (SHADOW only)")
    p.add_argument("--sidecar", type=Path, required=True, help="V2 camera sidecar JSON")
    p.add_argument("--camera-root", type=Path, default=None, help="Camera parquet root")
    p.add_argument("--session", default=None, help="YYYY-MM-DD (default: now date)")
    p.add_argument("--now", default=None, help="Override now ISO VN")
    args = p.parse_args(argv)

    from modules.live_candidate_v2_action.contract import (
        ALERT_ELIGIBLE,
        CANDIDATE_IS_BUY,
        PXV_IMPLIES_BUY,
    )
    from modules.live_candidate_v2_action.replay import replay_sidecar_session

    now = datetime.fromisoformat(args.now).replace(tzinfo=VN) if args.now else datetime.now(VN)
    sess = date.fromisoformat(args.session) if args.session else now.date()
    results = replay_sidecar_session(
        args.sidecar,
        now=now,
        camera_root=args.camera_root,
        session=sess,
    )
    payload = {
        "mode": "SHADOW_ONLY",
        "candidate_is_buy": CANDIDATE_IS_BUY,
        "pxv_implies_buy": PXV_IMPLIES_BUY,
        "alert_eligible": ALERT_ELIGIBLE,
        "session": sess.isoformat(),
        "n": len(results),
        "rows": [r.as_dict() for r in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
