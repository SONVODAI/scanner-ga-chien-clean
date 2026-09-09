#!/usr/bin/env python3
"""Write a deterministic HTML snapshot of the read-only LIVE CANDIDATE × P×V panel.

Does not start Streamlit, Camera, or production. Used for visual review / tests.
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
    p = argparse.ArgumentParser(description="Preview LIVE CANDIDATE × P×V HTML")
    p.add_argument("--out", type=Path, default=Path("data/intraday_pxv_live_shadow/ui_preview.html"))
    p.add_argument("--watchlist", type=Path, default=None)
    p.add_argument("--evidence", type=Path, default=None)
    p.add_argument("--status", type=Path, default=None)
    p.add_argument("--now", default=None)
    p.add_argument("--fixture", action="store_true", help="Use built-in mixed fixture (no live files)")
    args = p.parse_args(argv)

    from modules.live_candidate_pxv_ui.html import render_html
    from modules.live_candidate_pxv_ui.read import load_panel_sources
    from modules.live_candidate_pxv_ui.view import build_panel

    now = datetime.fromisoformat(args.now).replace(tzinfo=VN) if args.now else datetime.now(VN)
    if args.fixture:
        sources = json.loads(_FIXTURE)
        panel = build_panel(now=now, sources=sources)
    else:
        panel = build_panel(
            now=now,
            watchlist_path=args.watchlist,
            evidence_path=args.evidence,
            status_path=args.status,
        )
    html = render_html(panel)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(args.out)
    return 0


_FIXTURE = r"""
{
  "watchlist": [
    {"symbol":"GEE","candidate_reason":"BUY ELITE","candidate_first_seen_ts":"2026-08-14T13:32:00+07:00","eligible_from":"2026-08-14T13:32:00+07:00"},
    {"symbol":"HPG","candidate_reason":"BUY ELITE","candidate_first_seen_ts":"2026-08-14T10:05:00+07:00","eligible_from":"2026-08-14T10:05:00+07:00"},
    {"symbol":"ACB","candidate_reason":"MUA NHỎ / ƯU TIÊN","candidate_first_seen_ts":"2026-08-14T09:40:00+07:00","eligible_from":"2026-08-14T09:40:00+07:00"},
    {"symbol":"VCB","candidate_reason":"BUY ELITE","candidate_first_seen_ts":"2026-08-14T13:10:00+07:00","eligible_from":"2026-08-14T13:10:00+07:00"}
  ],
  "evidence": [
    {"symbol":"GEE","bar_ts":"2026-08-14T13:50:00+07:00","asof_hm":"13:50","observed_at":"2026-08-14T13:52:00+07:00","raw_evidence":"STRENGTHEN","published_evidence":"STRENGTHEN","evidence_why":"5m expansion with P×V CONFIRMING","data_state":"QUALIFIED","chronology_legal":true,"alert_eligible":false},
    {"symbol":"HPG","bar_ts":"2026-08-14T14:10:00+07:00","asof_hm":"14:10","observed_at":"2026-08-14T14:12:00+07:00","raw_evidence":"NEUTRAL","published_evidence":"NEUTRAL","evidence_why":"no confirming or weakening P×V event at this bar","data_state":"QUALIFIED","chronology_legal":true,"alert_eligible":false},
    {"symbol":"ACB","bar_ts":"2026-08-14T13:35:00+07:00","asof_hm":"13:35","observed_at":"2026-08-14T13:37:00+07:00","raw_evidence":"STRENGTHEN","published_evidence":"STRENGTHEN","chronology_legal":false,"alert_eligible":false,"data_state":"QUALIFIED"}
  ],
  "status": {
    "observed_at":"2026-08-14T14:12:00+07:00",
    "alert_eligible":false,
    "symbols":[
      {"symbol":"GEE","status":"OK"},
      {"symbol":"HPG","status":"OK"},
      {"symbol":"ACB","status":"OK"},
      {"symbol":"VCB","status":"WAITING_COMPLETED_BAR"}
    ]
  }
}
"""


if __name__ == "__main__":
    raise SystemExit(main())
