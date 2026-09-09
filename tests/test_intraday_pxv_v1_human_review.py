"""Human case review — synthetic Slice 1C ledger only. No Camera writes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.human_review import review_ledger, write_review


def _row(symbol, session, t, raw, pub, state="QUALIFIED", gate="INTERVAL+TOD_IMMATURE", **feat):
    return {
        "symbol": symbol,
        "session": session,
        "asof": t.isoformat(),
        "asof_hm": t.strftime("%H:%M"),
        "candidate_reason": "MUA NHỎ / ƯU TIÊN",
        "data_state": state,
        "gate_reason": gate,
        "tod_maturity": "TOD_PRELIMINARY",
        "overlay_applied": True,
        "raw_evidence": raw,
        "published_evidence": pub,
        "evidence": pub,
        "evidence_why": "5m expansion with P×V CONFIRMING" if raw == "STRENGTHEN" else "no confirming or weakening P×V event at this bar",
        "published_why": "published STRENGTHEN after 2 consecutive RAW STRENGTHEN" if pub == "STRENGTHEN" else "",
        "would_be_alert": False,
        "alert_eligible": False,
        "features": {
            "volume_expansion": {"value": feat.get("ratio", 1.0), "state": feat.get("exp", "NORMAL")},
            "price_volume": {
                "state": feat.get("pxv", "FLAT"),
                "up_bar": feat.get("up", True),
                "down_bar": not feat.get("up", True),
                "price_change_pct": feat.get("pct", 0.1),
            },
            "tod_relative_volume": {"value": 1.1, "confidence": "LOW_CONFIDENCE", "tod_maturity": "TOD_PRELIMINARY"},
        },
    }


def test_review_selects_gmd_and_does_not_invent(tmp_path: Path):
    day = "2026-08-28"
    t0 = datetime(2026, 8, 28, 13, 0, tzinfo=VN_TZ)
    recs = []
    # GMD: raw flicker, published stays NEUTRAL
    for i, raw in enumerate(["STRENGTHEN", "NEUTRAL", "WEAKEN", "NEUTRAL"]):
        recs.append(_row("GMD", day, t0 + timedelta(minutes=5 * i), raw, "NEUTRAL", ratio=3.2 if raw != "NEUTRAL" else 1.0, exp="EXPANSION" if raw != "NEUTRAL" else "NORMAL"))
    # Clean persist STRENGTHEN afternoon
    for i, (raw, pub) in enumerate(
        [("NEUTRAL", "NEUTRAL"), ("STRENGTHEN", "NEUTRAL"), ("STRENGTHEN", "STRENGTHEN"), ("STRENGTHEN", "STRENGTHEN"), ("STRENGTHEN", "STRENGTHEN"), ("NEUTRAL", "NEUTRAL")]
    ):
        recs.append(
            _row(
                "HPG",
                day,
                t0 + timedelta(minutes=5 * i),
                raw,
                pub,
                ratio=3.5 if raw == "STRENGTHEN" else 1.0,
                exp="EXPANSION" if raw == "STRENGTHEN" else "NORMAL",
                pxv="CONFIRMING" if raw == "STRENGTHEN" else "FLAT",
                pct=0.8 if raw == "STRENGTHEN" else 0.1,
            )
        )
    # 1-bar published fade
    for i, (raw, pub) in enumerate([("STRENGTHEN", "NEUTRAL"), ("STRENGTHEN", "STRENGTHEN"), ("NEUTRAL", "NEUTRAL")]):
        recs.append(_row("VCB", day, t0 + timedelta(minutes=5 * i), raw, pub, ratio=3.0 if raw == "STRENGTHEN" else 0.9, exp="EXPANSION" if raw == "STRENGTHEN" else "NORMAL", pct=0.5))
    # never leave
    recs.append(_row("MSN", day, t0, "NEUTRAL", "NEUTRAL"))
    recs.append(_row("MSN", day, t0 + timedelta(minutes=5), "NEUTRAL", "NEUTRAL"))
    # DGC unusable
    recs.append(_row("DGC", day, t0, "UNUSABLE", "UNUSABLE", state="UNUSABLE", gate="STRUCTURAL"))
    recs.append(_row("DGC", day, t0 + timedelta(minutes=5), "UNUSABLE", "UNUSABLE", state="UNUSABLE", gate="STRUCTURAL"))

    ledger = tmp_path / "shadow_ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    result = review_ledger(ledger)
    assert result["status"] == "OK"
    assert result["checks"]["alert_eligible_true_count"] == 0
    assert result["checks"]["dgc_published_sw"] is False
    keys = {(c["symbol"], c["session"], c["role"]) for c in result["cases"]}
    assert ("GMD", day, "GMD_QUIET") in keys
    assert any(c["symbol"] == "HPG" and c["label"] == "USEFUL" for c in result["cases"])
    gmd = next(c for c in result["cases"] if c["symbol"] == "GMD")
    assert gmd["missing"] is False
    assert "STRENGTHEN" not in (gmd.get("first_published") or "")
    assert "not a BUY signal" in (next(c for c in result["cases"] if c["symbol"] == "HPG")["ui_message"])
    md = write_review(result, tmp_path / "out")
    assert md.exists()
    text = md.read_text(encoding="utf-8")
    assert "AAA 2026-01-01" not in text  # no fabricated symbols
