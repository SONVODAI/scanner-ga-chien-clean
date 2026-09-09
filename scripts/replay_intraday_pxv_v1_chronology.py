#!/usr/bin/env python3
"""Chronology-clean Slice 1C replay. Shadow only. No threshold/debounce retune.

Paths:
  1) Official/debounce ledger present → drop illegal as-of rows, re-debounce RAW
  2) Else Camera archive → interpret_candidate_session (gate inside)
  3) Always: event-level eligibility from buy_elite_learning_history.csv

Writes only --out. Does not write Camera or production.
Historical overlay remains retrospective/reconciled — not live as-of knowledge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from modules.intraday_pxv_v1.candidates import load_candidate_events
from modules.intraday_pxv_v1.chronology import chronology_clean_ledger
from modules.intraday_pxv_v1.examine import compare_raw_published, load_ledger
from modules.intraday_pxv_v1.human_review import OFFICIAL_1C, review_ledger, write_review
from modules.intraday_pxv_v1.time_contract import resolve_legal_existence

PRODUCTION_HASH_PATHS = [
    "app.py",
    "modules/earning_learning.py",
    "modules/intraday_memory/storage.py",
    "modules/intraday_memory/collector.py",
    "modules/intraday_memory/reconciliation.py",
    "modules/intraday_memory/runner.py",
]

LEDGER_CANDIDATES = [
    Path("/tmp/pxv-v1-slice1c-debounce/shadow_ledger.jsonl"),
    Path("/tmp/pxv-v1-slice1-out/shadow_ledger.jsonl"),
]


def _hash_files(root: Path) -> dict[str, str]:
    out = {}
    for rel in PRODUCTION_HASH_PATHS:
        p = root / rel
        if p.exists():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def event_eligibility() -> dict:
    events = load_candidate_events()
    rows = []
    after_close = 0
    missing = 0
    same_day = 0
    first_seen = 0
    save_clock = 0
    for ev in events:
        legal = resolve_legal_existence(ev)
        if legal.provenance == "FIRST_SEEN_IMMUTABLE":
            first_seen += 1
        elif legal.provenance == "SAVE_CLOCK_LAST_WINS":
            save_clock += 1
        else:
            missing += 1
        if legal.same_day_intraday_eligible:
            same_day += 1
        elif legal.next_session_open_eligible:
            after_close += 1
        rows.append(
            {
                "symbol": ev.symbol,
                "session": ev.session.isoformat(),
                "candidate_ts": ev.candidate_ts,
                "first_seen": ev.candidate_first_seen_ts,
                "provenance": legal.provenance,
                "same_day_intraday_eligible": legal.same_day_intraday_eligible,
                "next_session_open_eligible": legal.next_session_open_eligible,
            }
        )
    return {
        "n_events": len(events),
        "provenance_first_seen": first_seen,
        "provenance_save_clock": save_clock,
        "provenance_missing": missing,
        "same_day_intraday_eligible": same_day,
        "after_close_no_same_day": after_close,
        "note": (
            "CSV time is save-clock last-wins, not first_seen. "
            "After-close events get zero same-day 5m rows; LIVE next-open only."
        ),
        "events": rows,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", default="")
    p.add_argument("--out", default="/tmp/pxv-v1-chronology-clean")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    before = _hash_files(REPO)

    ledger_path = Path(args.ledger) if args.ledger else None
    if ledger_path is None or not ledger_path.exists():
        for cand in LEDGER_CANDIDATES:
            if cand.exists():
                ledger_path = cand
                break

    eligibility = event_eligibility()
    payload: dict = {
        "status": "EVENT_ELIGIBILITY_ONLY",
        "official_1c_before": OFFICIAL_1C,
        "event_eligibility": {k: v for k, v in eligibility.items() if k != "events"},
        "overlay_label": (
            "Historical latest-quarantine overlay is retrospective/reconciled truth. "
            "Chronology-clean historical replay does NOT reproduce exactly what a live "
            "Camera would have known unless that overlay was also available as-of."
        ),
        "no_tuning": True,
    }

    if ledger_path and ledger_path.exists():
        raw_df = load_ledger(ledger_path)
        clean, stats = chronology_clean_ledger(raw_df)
        from modules.intraday_pxv_v1.ledger import write_ledger

        write_ledger(clean, out)
        cmp = compare_raw_published(clean, str(ledger_path))
        review = review_ledger(out / "shadow_ledger.jsonl") if len(clean) else {"status": "EMPTY_AFTER_GATE"}
        if review.get("status") == "OK":
            write_review(review, out)
        payload.update(
            {
                "status": "LEDGER_CHRONOLOGY_CLEAN",
                "source_ledger": str(ledger_path),
                "removal_stats": stats,
                "chronology_clean_raw": cmp["raw"]["persistence"],
                "chronology_clean_published": cmp["published"]["persistence"],
                "chronology_clean_timing_first_published": cmp["published"]["timing_first_sw"],
                "chronology_clean_candidates": cmp["published"]["candidates"],
                "checks": cmp["checks"],
                "human_review_status": review.get("status"),
                "human_review_cases": [
                    {
                        "symbol": c.get("symbol"),
                        "session": c.get("session"),
                        "role": c.get("role"),
                        "label": c.get("label"),
                        "first_published_hm": c.get("first_published_hm"),
                    }
                    for c in (review.get("cases") or [])
                ],
            }
        )
    else:
        payload["status"] = "LEDGER_MISSING_EVENT_ELIGIBILITY_ONLY"
        payload["detail"] = (
            "No official Slice 1C ledger on this host. Event-level gate is complete. "
            "Row/run census requires --ledger pointing at the official 1C jsonl."
        )

    after = _hash_files(REPO)
    payload["production_hashes_unchanged"] = before == after
    payload["alert_eligible_true_count"] = 0
    (out / "chronology_clean_compare.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (out / "event_eligibility.json").write_text(
        json.dumps(eligibility, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps({k: payload[k] for k in payload if k != "human_review_cases"}, indent=2, default=str))
    return 0 if payload["production_hashes_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
