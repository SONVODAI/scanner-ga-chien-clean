"""Post-examiner diagnosis tests — synthetic ledger + real interpreter.

No Camera writes. No T+n. No production paths.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.diagnose import (
    CAUSE_A,
    CAUSE_B,
    CAUSE_C_WINDOW,
    CAUSE_E,
    CAUSE_G,
    annotate_sw_runs,
    classify_exit,
    diagnose,
    normalized_suppression,
    official_persist_table,
)
from modules.intraday_pxv_v1.evidence import decide_evidence
from modules.intraday_pxv_v1.examine import SW, collect_runs, load_ledger
from modules.intraday_pxv_v1.features import FAM_EXPANSION, FAM_PACE, FAM_PXV, compute_features
from modules.intraday_pxv_v1.gate import evaluate_gate


def _ts(day: str, hm: str) -> datetime:
    return datetime.fromisoformat(f"{day} {hm}:00").replace(tzinfo=VN_TZ)


def _row(symbol, session, t, evidence, features, state="QUALIFIED", would=False, src="canonical"):
    return {
        "symbol": symbol,
        "session": session,
        "asof": t.isoformat(),
        "asof_hm": t.strftime("%H:%M"),
        "candidate_reason": "MUA NHỎ / ƯU TIÊN",
        "data_state": state,
        "gate_reason": "INTERVAL+TOD_IMMATURE",
        "tod_maturity": "TOD_PRELIMINARY",
        "overlay_applied": True,
        "bar_source_last": src,
        "evidence": evidence,
        "evidence_why": "5m expansion with P×V CONFIRMING",
        "would_be_alert": would,
        "alert_eligible": False,
        "features": features,
    }


def _feats(ratio, exp_state, pxv, pct, up, down, pace=1.1):
    return {
        FAM_EXPANSION: {"value": ratio, "state": exp_state},
        FAM_PXV: {
            "state": pxv,
            "up_bar": up,
            "down_bar": down,
            "price_change_pct": pct,
        },
        FAM_PACE: {"value": pace, "confidence": "LOW_CONFIDENCE"},
    }


def test_normalized_table_uses_one_baseline(tmp_path: Path):
    day = "2026-08-28"
    t0 = _ts(day, "09:30")
    rows = []
    # AAA: 1-bar S, later 2-bar S (same direction), 1-bar W
    rows.append(_row("AAA", day, t0, "STRENGTHEN", _feats(3.5, "EXPANSION", "CONFIRMING", 0.8, True, False)))
    rows.append(_row("AAA", day, t0 + timedelta(minutes=5), "NEUTRAL", _feats(0.9, "NORMAL", "FLAT", 0.1, True, False)))
    rows.append(
        _row(
            "AAA",
            day,
            t0 + timedelta(minutes=40),
            "STRENGTHEN",
            _feats(2.6, "EXPANSION", "CONFIRMING", 0.5, True, False),
            would=True,
        )
    )
    rows.append(_row("AAA", day, t0 + timedelta(minutes=45), "STRENGTHEN", _feats(2.4, "EXPANSION", "CONFIRMING", 0.4, True, False)))
    rows.append(_row("AAA", day, t0 + timedelta(minutes=50), "WEAKEN", _feats(2.5, "EXPANSION", "SELL_EXPANSION", -0.6, False, True)))
    rows.append(_row("AAA", day, t0 + timedelta(minutes=55), "NEUTRAL", _feats(1.0, "NORMAL", "FLAT", 0.0, False, False)))
    # BBB: only 1-bar
    rows.append(_row("BBB", day, t0, "WEAKEN", _feats(0.4, "CONTRACTION", "WEAK", 0.3, True, False)))
    rows.append(_row("BBB", day, t0 + timedelta(minutes=5), "NEUTRAL", _feats(1.0, "NORMAL", "FLAT", 0.1, True, False)))

    ledger = tmp_path / "shadow_ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    result = diagnose(ledger)
    table = {r["rule"]: r for r in result["normalized_alerts"]["table"]}
    n = table["baseline_identity"]["baseline"]
    assert n == result["sw_runs"] == 4
    for r in result["normalized_alerts"]["table"]:
        assert r["baseline"] == n
        assert r["retained"] + r["suppressed"] == n
    assert table["persist_ge_2"]["retained"] == 1
    assert table["persist_ge_2"]["retention_pct"] == 25.0
    # first-per-ss: AAA first S, BBB first W → 2
    assert table["first_per_symbol_session"]["retained"] == 2
    # one-per-direction includes 1-bar first prints: AAA S, AAA W, BBB W → 3
    assert table["one_per_direction"]["retained"] == 3
    # persist>=2 + one-per-direction: only AAA 2-bar S
    assert table["persist_ge_2_plus_one_per_direction"]["retained"] == 1
    # cooldown on ALL 4: AAA 1-bar S, skip AAA 2-bar S (only 40m later — 40>=30 so KEEP),
    # then AAA W 10m later suppressed, BBB W kept → depends on 30m from last KEPT
    # AAA S 09:30 kept; AAA 2-bar S 10:10 is 40m later kept; AAA W 10:20 suppressed; BBB kept
    assert table["cooldown_30m"]["retained"] == 3
    assert table["slice1_would_be_alert_replay"]["retained"] == 1
    assert result["would_be_alert_match"] is True


def test_classify_window_self_extinguish():
    cur = {
        "evidence": "STRENGTHEN",
        "exp_state": "EXPANSION",
        "exp_ratio": 3.6,
        "pxv_state": "CONFIRMING",
        "up": True,
        "down": False,
        "pct": 0.8,
        "pace": 1.1,
        "why": "5m expansion with P×V CONFIRMING",
        "data_state": "QUALIFIED",
        "bar_source": "canonical",
        "overlay": True,
    }
    nxt = dict(cur)
    nxt.update(
        {
            "evidence": "NEUTRAL",
            "exp_state": "NORMAL",
            "exp_ratio": 0.9,
            "pxv_state": "FLAT",
            "pct": 0.1,
        }
    )
    got = classify_exit(cur, nxt)
    assert got["primary"] == CAUSE_C_WINDOW
    assert CAUSE_E not in got["tags"]  # session overlay is not a per-bar source change


def test_classify_boundary_vs_window():
    cur = {
        "evidence": "STRENGTHEN",
        "exp_state": "EXPANSION",
        "exp_ratio": 2.08,
        "pxv_state": "CONFIRMING",
        "up": True,
        "down": False,
        "pct": 0.4,
        "pace": 1.0,
        "why": "5m expansion with P×V CONFIRMING",
        "data_state": "QUALIFIED",
        "bar_source": "canonical",
        "overlay": False,
    }
    nxt = dict(cur)
    nxt.update({"evidence": "NEUTRAL", "exp_state": "NORMAL", "exp_ratio": 1.90, "pxv_state": "FLAT", "pct": 0.2})
    got = classify_exit(cur, nxt)
    assert got["primary"] == CAUSE_A


def test_classify_opposite_material_is_g():
    cur = {
        "evidence": "STRENGTHEN",
        "exp_state": "EXPANSION",
        "exp_ratio": 2.8,
        "pxv_state": "CONFIRMING",
        "up": True,
        "down": False,
        "pct": 0.9,
        "pace": 1.2,
        "why": "5m expansion with P×V CONFIRMING",
        "data_state": "QUALIFIED",
        "bar_source": "canonical",
        "overlay": False,
    }
    nxt = dict(cur)
    nxt.update(
        {
            "evidence": "WEAKEN",
            "pxv_state": "SELL_EXPANSION",
            "up": False,
            "down": True,
            "pct": -0.7,
        }
    )
    got = classify_exit(cur, nxt)
    assert CAUSE_G in got["tags"]
    assert CAUSE_B in got["tags"]
    assert got["primary"] == CAUSE_G


def test_classify_near_doji_opposite_is_b_not_g():
    cur = {
        "evidence": "STRENGTHEN",
        "exp_state": "EXPANSION",
        "exp_ratio": 2.5,
        "pxv_state": "CONFIRMING",
        "up": True,
        "down": False,
        "pct": 0.08,
        "pace": 1.0,
        "why": "5m expansion with P×V CONFIRMING",
        "data_state": "QUALIFIED",
        "bar_source": "canonical",
        "overlay": False,
    }
    nxt = dict(cur)
    nxt.update(
        {
            "evidence": "WEAKEN",
            "pxv_state": "SELL_EXPANSION",
            "up": False,
            "down": True,
            "pct": -0.05,
        }
    )
    got = classify_exit(cur, nxt)
    assert got["primary"] == CAUSE_B
    assert CAUSE_G not in got["tags"]


def test_overlay_session_flag_is_not_cause_e():
    cur = {
        "evidence": "STRENGTHEN",
        "exp_state": "EXPANSION",
        "exp_ratio": 3.0,
        "pxv_state": "CONFIRMING",
        "up": True,
        "down": False,
        "pct": 0.5,
        "pace": 1.0,
        "why": "x",
        "data_state": "QUALIFIED",
        "bar_source": "revised_quarantine",
        "overlay": True,
    }
    nxt = dict(cur)
    nxt.update({"evidence": "NEUTRAL", "exp_state": "NORMAL", "exp_ratio": 1.0, "pxv_state": "FLAT"})
    got = classify_exit(cur, nxt)
    assert CAUSE_E not in got["tags"]
    assert got["primary"] == CAUSE_C_WINDOW


def test_pace_ahead_cannot_create_strengthen_without_expansion():
    """Slice 1 CONFIRMING already requires expansion — TOD pace is a dead STRENGTHEN path."""
    from modules.intraday_pxv_v1.constants import DATA_QUALIFIED, TOD_PRELIMINARY
    from modules.intraday_pxv_v1.gate import GATE_INTERVAL, GateResult

    gate = GateResult(
        data_state=DATA_QUALIFIED,
        gate_reason="INTERVAL+TOD_IMMATURE",
        volume_kind=GATE_INTERVAL,
        tod_maturity=TOD_PRELIMINARY,
        overlay_applied=False,
        n_bars=20,
        expected_bars=46,
        doji_frac=0.0,
        median_gap_sec=300,
        last_over_sum=None,
        max_over_sum=None,
        notes=[],
    )
    feats = {
        FAM_EXPANSION: {"value": 1.1, "state": "NORMAL"},
        FAM_PXV: {"state": "FLAT", "up_bar": True, "down_bar": False, "price_change_pct": 0.4},
        FAM_PACE: {"value": 2.5, "confidence": "LOW_CONFIDENCE"},
    }
    ev = decide_evidence(gate, feats, thesis_long=True)
    assert ev.evidence != "STRENGTHEN"
    assert ev.strengthen is False


def test_interpreter_spike_is_one_bar_strengthen():
    """Real feature math: a 4× up-bar then a normal up-bar is STRENGTHEN → NEUTRAL."""
    day = "2026-08-28"
    start = _ts(day, "09:15")
    rows = []
    t = start
    for i in range(12):
        vol = 4000 if i == 10 else 1000
        close = 20100 if i != 11 else 20120
        rows.append(
            {
                "symbol": "GMD",
                "timestamp": t,
                "session_date": t.date(),
                "open": 20000,
                "high": close + 50,
                "low": 19900,
                "close": close,
                "volume": vol,
                "source": "test",
                "collected_at": t,
                "quality_flag": "ok",
                "overlay_applied": False,
            }
        )
        t += timedelta(minutes=5)
        if t.hour == 11 and t.minute > 30:
            t = _ts(day, "13:00")

    import pandas as pd

    df = pd.DataFrame(rows)
    evs = []
    for i in range(8, len(df)):
        asof = df.iloc[i]["timestamp"].to_pydatetime()
        gate = evaluate_gate(df.iloc[: i + 1], asof=asof, tod_qualified_sessions=5)
        feats = compute_features(
            df.iloc[: i + 1],
            gate,
            asof=asof,
            tod_rvol_baseline=1000.0,
            tod_pace_baseline=20000.0,
        )
        ev = decide_evidence(gate, feats, thesis_long=True)
        evs.append((df.iloc[i]["timestamp"].strftime("%H:%M"), ev.evidence, feats.get(FAM_EXPANSION, {})))
    labels = [e[1] for e in evs]
    assert "STRENGTHEN" in labels
    s_idx = labels.index("STRENGTHEN")
    assert labels[s_idx + 1] == "NEUTRAL"
    spike = evs[s_idx][2]
    after = evs[s_idx + 1][2]
    assert spike.get("state") == "EXPANSION"
    assert after.get("state") != "EXPANSION"
    cur = {
        "evidence": "STRENGTHEN",
        "exp_state": spike["state"],
        "exp_ratio": spike["value"],
        "pxv_state": "CONFIRMING",
        "up": True,
        "down": False,
        "pct": 0.5,
        "pace": 1.0,
        "why": "5m expansion with P×V CONFIRMING",
        "data_state": "QUALIFIED",
        "bar_source": "canonical",
        "overlay": False,
    }
    nxt = dict(cur)
    nxt.update(
        {
            "evidence": "NEUTRAL",
            "exp_state": after.get("state", "NORMAL"),
            "exp_ratio": after.get("value"),
            "pxv_state": "FLAT",
            "pct": 0.1,
        }
    )
    assert classify_exit(cur, nxt)["primary"] == CAUSE_C_WINDOW


def test_official_persist_table_is_apples_to_apples():
    t = official_persist_table()
    assert t["baseline_count"] == 967
    by = {r["rule"]: r for r in t["table"]}
    assert by["persist_ge_2"]["retained"] == 153
    assert by["persist_ge_2"]["suppressed"] == 814
    assert by["persist_ge_2"]["retention_pct"] == 15.8
    assert by["slice1_logged_would_be_alert"]["retained"] == 113
    # 113 is a subset of 967, not a competing universe
    assert by["slice1_logged_would_be_alert"]["baseline"] == 967


def test_annotate_attaches_cause(tmp_path: Path):
    day = "2026-08-28"
    t0 = _ts(day, "13:00")
    rows = [
        _row("GMD", day, t0, "STRENGTHEN", _feats(3.2, "EXPANSION", "CONFIRMING", 0.6, True, False)),
        _row("GMD", day, t0 + timedelta(minutes=5), "NEUTRAL", _feats(0.8, "NORMAL", "FLAT", 0.1, True, False)),
        _row("GMD", day, t0 + timedelta(minutes=10), "STRENGTHEN", _feats(2.7, "EXPANSION", "CONFIRMING", 0.5, True, False)),
        _row(
            "GMD",
            day,
            t0 + timedelta(minutes=15),
            "WEAKEN",
            _feats(2.6, "EXPANSION", "SELL_EXPANSION", -0.5, False, True),
        ),
    ]
    ledger = tmp_path / "shadow_ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    df = load_ledger(ledger)
    sw = [r for r in collect_runs(df) if r["evidence"] in SW]
    ann = annotate_sw_runs(df, sw)
    assert len(ann) == 3
    assert ann[0]["cause"]["primary"] == CAUSE_C_WINDOW
    assert ann[1]["cause"]["primary"] in {CAUSE_G, CAUSE_B}
    assert ann[1]["n_bars"] == 1
