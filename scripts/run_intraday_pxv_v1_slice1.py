#!/usr/bin/env python3
"""Slice 1 shadow runner. Read-only Camera. Writes only data/intraday_pxv_v1/."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from modules.intraday_pxv_v1.archive import list_session_dates, overlay_session
from modules.intraday_pxv_v1.candidates import load_candidate_events
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


def main() -> int:
    cam = camera_data_root()
    out = output_root()
    out.mkdir(parents=True, exist_ok=True)
    before = _hash_files(REPO)

    sessions = list_session_dates(cam)
    if not sessions:
        summary = build_report(
            camera_root=str(cam),
            sessions=[],
            candidate_events=0,
            joined_events=0,
            ledger=__import__("pandas").DataFrame(),
            extra={
                "status": "CAMERA_ARCHIVE_NOT_MOUNTED",
                "detail": (
                    f"No bars.parquet under {cam}. "
                    "Set MRBOT_INTRADAY_DATA_ROOT to the live archive to produce real shadow results."
                ),
            },
        )
        write_report(summary, out)
        (out / "production_hash_before.json").write_text(json.dumps(before, indent=2))
        (out / "production_hash_after.json").write_text(json.dumps(_hash_files(REPO), indent=2))
        print(json.dumps(summary, indent=2, default=str))
        return 0

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
        rows.extend(
            interpret_candidate_session(
                ov, ev, tod, qualified.get(ev.symbol, 0)
            )
        )

    import pandas as pd

    ledger = rows_to_frame(rows) if rows else pd.DataFrame()
    write_ledger(ledger, out)

    examples = {}
    if not ledger.empty:
        last = ledger.sort_values("asof").groupby(["symbol", "session"], as_index=False).tail(1)
        for key in ("STRENGTHEN", "WEAKEN", "NEUTRAL", "UNUSABLE", "CONFLICT"):
            hit = last[last["evidence"] == key]
            if not hit.empty:
                r = hit.iloc[0]
                examples[key] = {
                    "symbol": r["symbol"],
                    "session": r["session"],
                    "asof_hm": r["asof_hm"],
                    "data_state": r["data_state"],
                    "gate_reason": r["gate_reason"],
                    "evidence": r["evidence"],
                    "message": r["message"],
                }

    after = _hash_files(REPO)
    summary = build_report(
        camera_root=str(cam),
        sessions=[d.isoformat() for d in sessions],
        candidate_events=len(events),
        joined_events=joined,
        ledger=ledger,
        extra={
            "status": "OK",
            "output_dir": str(out),
            "examples": examples,
            "production_hashes_unchanged": before == after,
        },
    )
    write_report(summary, out)
    (out / "production_hash_before.json").write_text(json.dumps(before, indent=2))
    (out / "production_hash_after.json").write_text(json.dumps(after, indent=2))
    print(json.dumps({k: summary[k] for k in summary if k != "rejected_last_bar"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
