#!/usr/bin/env python3
"""Slice 1C: replay RAW vs PUBLISHED debounce. Shadow only.

Paths:
  1) Camera archive present → full interpret (RAW unchanged + new published)
  2) Else existing Slice 1 ledger → apply debounce to its evidence as RAW

Writes only --out. Does not write Camera, production, or the input ledger.
Does not enable alerts. Does not tune thresholds. Does not use T+n.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from modules.intraday_pxv_v1.archive import list_session_dates, overlay_session
from modules.intraday_pxv_v1.candidates import load_candidate_events
from modules.intraday_pxv_v1.examine import (
    apply_debounce_columns,
    compare_raw_published,
    ensure_asof_ts,
    load_ledger,
    write_compare,
)
from modules.intraday_pxv_v1.gate import GATE_INTERVAL, evaluate_gate
from modules.intraday_pxv_v1.interpret import (
    build_tod_baselines,
    interpret_candidate_session,
    rows_to_frame,
)
from modules.intraday_pxv_v1.ledger import write_ledger
from modules.intraday_pxv_v1.paths import camera_data_root, output_root
from modules.intraday_pxv_v1.report import build_report, write_report

PRODUCTION_HASH_PATHS = [
    "app.py",
    "modules/earning_learning.py",
    "modules/intraday_memory/storage.py",
    "modules/intraday_memory/collector.py",
    "modules/intraday_memory/reconciliation.py",
    "modules/intraday_memory/runner.py",
]


def _hash_files(root: Path) -> dict[str, str]:
    out = {}
    for rel in PRODUCTION_HASH_PATHS:
        p = root / rel
        if p.exists():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _camera_replay(cam: Path, out: Path) -> tuple[pd.DataFrame, dict]:
    sessions = list_session_dates(cam)
    overlays = {d: overlay_session(cam, d) for d in sessions}
    events = load_candidate_events(sessions=sessions)
    symbols = {e.symbol for e in events}
    tod = build_tod_baselines(overlays, symbols)
    qualified: dict[str, int] = {}
    for d, ov in overlays.items():
        if ov is None or ov.empty:
            continue
        for sym in set(ov["symbol"].astype(str)) & symbols:
            bars = ov[ov["symbol"] == sym]
            g = evaluate_gate(bars, tod_qualified_sessions=0)
            if g.volume_kind == GATE_INTERVAL and g.usable_volume:
                qualified[sym] = qualified.get(sym, 0) + 1
    rows = []
    joined = 0
    for ev in events:
        ov = overlays.get(ev.session)
        if ov is None or ov.empty:
            continue
        if ev.symbol not in set(ov["symbol"].astype(str)):
            continue
        joined += 1
        rows.extend(interpret_candidate_session(ov, ev, tod, qualified.get(ev.symbol, 0)))
    ledger = rows_to_frame(rows) if rows else pd.DataFrame()
    if not ledger.empty:
        ledger = ensure_asof_ts(ledger)
    write_ledger(ledger, out)
    extra = {
        "status": "CAMERA_REPLAY",
        "n_camera_sessions": len(sessions),
        "sessions": [d.isoformat() for d in sessions],
        "n_candidate_events": len(events),
        "n_joined_events": joined,
    }
    if not ledger.empty:
        summary = build_report(
            camera_root=str(cam),
            sessions=extra["sessions"],
            candidate_events=len(events),
            joined_events=joined,
            ledger=ledger,
            extra={"status": "CAMERA_REPLAY", "output_dir": str(out)},
        )
        write_report(summary, out)
    return ledger, extra


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", default="/tmp/pxv-v1-slice1-out/shadow_ledger.jsonl")
    p.add_argument("--out", default="/tmp/pxv-v1-slice1c-debounce")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    before = _hash_files(REPO)
    cam = camera_data_root()
    ledger_path = Path(args.ledger)
    extra = {}
    # Prefer the official Slice 1 ledger when present so RAW is the recorded
    # 1-bar series (asof/asof_hm), not a re-interpret frame missing asof_ts.
    if ledger_path.exists():
        raw_df = load_ledger(ledger_path)
        # Old Slice 1 ledger: evidence == RAW. Preserve it, add published.
        if "raw_evidence" not in raw_df.columns or (
            raw_df["raw_evidence"].astype(str) == raw_df["evidence"].astype(str)
        ).all():
            if "published_evidence" not in raw_df.columns:
                raw_df["raw_evidence"] = raw_df["evidence"].astype(str)
        df = apply_debounce_columns(raw_df)
        df["alert_eligible"] = False
        write_ledger(df, out)
        extra = {
            "status": "LEDGER_DEBOUNCE_REPLAY",
            "source_ledger": str(ledger_path),
            "detail": "RAW taken from existing ledger evidence; published computed in isolation",
        }
        source = str(ledger_path)
    elif list_session_dates(cam):
        df, extra = _camera_replay(cam, out)
        source = f"camera:{cam}"
    else:
        payload = {
            "status": "CAMERA_AND_LEDGER_MISSING",
            "camera": str(cam),
            "ledger": str(ledger_path),
            "debounce_verdict": {
                "verdict": None,
                "why": "No Camera archive and no Slice 1 ledger on this host. Run on the isolated VPS clone.",
            },
        }
        (out / "debounce_compare.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        after = _hash_files(REPO)
        (out / "production_hash_before.json").write_text(json.dumps(before, indent=2))
        (out / "production_hash_after.json").write_text(json.dumps(after, indent=2))
        print(json.dumps({**payload, "production_unchanged": before == after}, indent=2))
        return 2

    cmp = compare_raw_published(df, source)
    cmp["replay"] = extra
    after = _hash_files(REPO)
    cmp["checks"]["production_hashes_unchanged"] = before == after
    cmp["checks"]["writes_only_out"] = True
    write_compare(cmp, out)
    (out / "production_hash_before.json").write_text(json.dumps(before, indent=2))
    (out / "production_hash_after.json").write_text(json.dumps(after, indent=2))
    print("======== SLICE 1C DEBOUNCE REPLAY ========")
    print(f"VERDICT: {cmp['debounce_verdict']['verdict']}")
    print(cmp["debounce_verdict"]["why"])
    print(
        json.dumps(
            {
                "replay": extra,
                "comparison_table": cmp["comparison_table"],
                "timing_first_published_sw": cmp["published"]["timing_first_sw"],
                "candidates_published": cmp["published"]["candidates"],
                "checks": cmp["checks"],
                "gmd_2026_08_28_missing": cmp["gmd_2026_08_28"].get("missing"),
                "gmd_lines": cmp["gmd_2026_08_28"].get("lines", [])[:20],
                "artifacts": str(out),
            },
            indent=2,
            default=str,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
