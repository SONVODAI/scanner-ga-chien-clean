"""Slice 1B examiner tests — synthetic ledger only, no Camera writes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.examine import examine


def _row(
    symbol,
    session,
    t,
    evidence,
    state="QUALIFIED",
    overlay=False,
    would=False,
    gate="INTERVAL+TOD_IMMATURE",
):
    return {
        "symbol": symbol,
        "session": session,
        "asof": t.isoformat(),
        "asof_hm": t.strftime("%H:%M"),
        "candidate_reason": "MUA NHỎ / ƯU TIÊN",
        "data_state": state,
        "gate_reason": gate,
        "tod_maturity": "TOD_PRELIMINARY",
        "overlay_applied": overlay,
        "evidence": evidence,
        "would_be_alert": would,
        "alert_eligible": False,
        "features": {},
    }


def test_examiner_persistence_and_dgc(tmp_path: Path):
    day = "2026-08-14"
    t0 = datetime(2026, 8, 14, 9, 30, tzinfo=VN_TZ)
    rows = []
    for i in range(4):
        rows.append(
            _row("HPG", day, t0 + timedelta(minutes=5 * i), "STRENGTHEN", would=(i == 1))
        )
    rows.append(_row("HPG", day, t0 + timedelta(minutes=20), "NEUTRAL"))
    rows.append(_row("VCB", day, t0, "WEAKEN"))
    rows.append(_row("VCB", day, t0 + timedelta(minutes=5), "NEUTRAL"))
    rows.append(
        _row("DGC", day, t0, "UNUSABLE", state="UNUSABLE", gate="STRUCTURAL")
    )
    rows.append(
        _row(
            "DGC",
            day,
            t0 + timedelta(minutes=5),
            "UNUSABLE",
            state="UNUSABLE",
            gate="STRUCTURAL",
        )
    )
    rows.append(_row("MSN", day, t0, "STRENGTHEN"))
    rows.append(_row("MSN", day, t0 + timedelta(minutes=5), "WEAKEN"))

    ledger = tmp_path / "shadow_ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    result = examine(ledger, None)
    p = result["persistence"]
    assert p["sw_runs"] == 4
    assert p["1_bar"] >= 2
    assert p["ge_2_bars"] >= 1
    assert p["direct_opposite_reversals"] >= 1
    st = result["examples"]["structural"]
    assert st["dgc_rows"] == 2
    assert st["any_dgc_strengthen_weaken"] is False
    assert result["verdict_block"]["verdict"] in {
        "READY_FOR_ALERT_DESIGN",
        "PROMISING_BUT_TOO_NOISY",
        "NOT_READY",
    }
    assert result["alert_simulation"]["R0_ledger_would_be_alert"] == 1
