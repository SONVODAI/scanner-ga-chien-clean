"""LIVE CANDIDATE V2 Slice 2 — Camera sidecar + injected LiveShadowFeed.

No live runner. No production watchlist publish. Candidate != BUY.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.candidate_router.adapters.rotation import nominations_from_rotation_artifact
from modules.candidate_router.contract import ENABLED_SOURCES, SRC_BUY_ELITE, SRC_LEARNING_INSIGHT, SRC_ROTATION, WATCHLIST_COLUMNS
from modules.candidate_router.router import classify_nominations, to_watchlist_frame
from modules.intraday_memory.provider import MockProvider as FakeProvider
from modules.live_camera_shadow.feed import LiveShadowFeed
from modules.live_camera_shadow.universe import LIVE_UNIVERSE_CAP, eligible_watchlist_symbols
from modules.live_candidate_v2_camera.contract import (
    GENERIC_PXV,
    SCHEMA_ID,
    SHADOW_V2_ENABLED_SOURCES,
    SIDECAR_ROW_FIELDS,
)
from modules.live_candidate_v2_camera.observe import observe_close_vs_ref, pxv_implies_buy
from modules.live_candidate_v2_camera.sidecar import (
    DEFAULT_SIDECAR_PATH,
    PRODUCTION_WATCHLIST,
    build_sidecar_from_scan,
    shadow_route_v2,
    write_sidecar,
)
from modules.live_candidate_v2_nomination.contract import SRC_BRAIN_A
from modules.live_candidate_v2_nomination.nominate import to_nominated_candidate

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _scan_row(symbol: str, group: str, **extra) -> dict:
    rec = {
        "symbol": symbol,
        "date": extra.pop("date", "2026-08-14"),
        "group": group,
        "price": extra.pop("price", 27.5),
        "ema9": extra.pop("ema9", 27.1),
        "breakout_ref": extra.pop("breakout_ref", 28.0),
        "dist_from_ema9_pct": extra.pop("dist_from_ema9_pct", 1.4),
        "total_score": extra.pop("total_score", 5),
        "obv_status": extra.pop("obv_status", "🟢"),
        "warning": extra.pop("warning", ""),
    }
    rec.update(extra)
    return rec


def _raw_bar(ts: str, close: float = 27.4, vol: int = 2000) -> dict:
    return {
        "time": ts,
        "open": close,
        "high": close + 0.05,
        "low": close - 0.05,
        "close": close,
        "volume": vol,
    }


def _grid(day: str, start_hm: str = "09:15", n: int = 16, close0: float = 27.4) -> list[dict]:
    t = _ts(f"{day} {start_hm}:00")
    rows = []
    for i in range(n):
        hm = (t.hour, t.minute)
        if (9, 15) <= hm <= (11, 30) or (13, 0) <= hm <= (14, 45):
            rows.append(_raw_bar(t.strftime("%Y-%m-%d %H:%M:%S"), close=close0 + i * 0.02, vol=2000 + i * 80))
        t += timedelta(minutes=5)
        if t.hour == 11 and t.minute > 30:
            t = _ts(f"{day} 13:00:00")
    return rows


def _e2e(tmp_path: Path, scan_rows, *, now: datetime, bars_by_sym: dict, market_real=7.2, nominate_at=None):
    nom_at = nominate_at or now
    report, sidecar = build_sidecar_from_scan(scan_rows, market_real=market_real, observed_at=nom_at)
    write_sidecar(
        sidecar,
        observed_at=nom_at,
        path=tmp_path / "camera_sidecar.json",
        market_real=report.market_real,
        market_permission=report.market_permission,
    )
    day = now.date().isoformat()
    data = {(sym, day): bars for (sym, day), bars in bars_by_sym.items()}
    feed = LiveShadowFeed(
        provider=FakeProvider(data),
        out_dir=tmp_path / "shadow",
        now_fn=lambda: now,
        archive_root=tmp_path / "camera_must_stay_empty",
    )
    status = feed.run_cycle(sidecar)
    return report, sidecar, feed, status


def test_end_to_end_brain_a_sidecar_injected_feed_evidence(tmp_path):
    now = _ts("2026-08-14 10:40:00")
    nom_at = _ts("2026-08-14 10:05:00")
    scan = [
        _scan_row("HPG", "PULL ĐẸP", conclusion="BUY ELITE", price=27.5, ema9=27.1),
        _scan_row("SSI", "MUA BREAK", price=32.0, ema9=30.8, breakout_ref=31.5),
    ]
    bars = {
        ("HPG", "2026-08-14"): _grid("2026-08-14", close0=27.4),
        ("SSI", "2026-08-14"): _grid("2026-08-14", close0=32.2),
    }
    report, sidecar, feed, status = _e2e(
        tmp_path, scan, now=now, bars_by_sym=bars, nominate_at=nom_at
    )
    by_side = {r["symbol"]: r for r in sidecar}
    for key in SIDECAR_ROW_FIELDS:
        assert key in by_side["HPG"]
    assert by_side["HPG"]["candidate_is_buy"] is False
    assert by_side["HPG"]["alert_eligible"] is False
    assert by_side["HPG"]["setup"] == "PULL ĐẸP"
    assert by_side["HPG"]["observation_intent"] == "WATCH_PRICE_TAPE_VS_FROZEN_REF"
    assert by_side["HPG"]["observation_reference"] == "EMA9"
    assert by_side["HPG"]["ema9_at_first_seen"] == 27.1
    assert by_side["HPG"]["source"] == SRC_BRAIN_A
    assert isinstance(by_side["HPG"]["provenance"], list)
    assert by_side["HPG"]["provenance"]
    assert by_side["SSI"]["observation_reference"] == "BREAKOUT_REF"

    ev = feed.read_evidence()
    assert ev
    by_ev = {}
    for row in ev:
        by_ev.setdefault(row["symbol"], row)
    hpg = by_ev["HPG"]
    assert hpg["setup"] == "PULL ĐẸP"
    assert hpg["observation_intent"] == "WATCH_PRICE_TAPE_VS_FROZEN_REF"
    assert hpg["ema9_at_first_seen"] == 27.1
    assert hpg["price_at_first_seen"] == 27.5
    assert hpg["candidate_first_seen_ts"].startswith("2026-08-14T10:05:00")
    assert hpg["eligible_from"].startswith("2026-08-14T10:05:00")
    assert hpg["nomination_source"] == SRC_BRAIN_A
    assert hpg["source"] == SRC_BRAIN_A
    assert hpg["feed_source"] == "live_shadow"
    assert hpg["candidate_is_buy"] is False
    assert hpg["alert_eligible"] is False
    assert hpg["candidate_reason"] != "BUY ELITE"
    assert "BUY ELITE" not in str(hpg["candidate_reason"])
    assert hpg["elite_buy_grade"] == "BUY ELITE"
    assert hpg["published_evidence"] in GENERIC_PXV
    assert pxv_implies_buy(hpg["published_evidence"]) is False
    assert hpg["pxv_implies_buy"] is False
    assert hpg.get("buy_action") is None
    expected = observe_close_vs_ref(by_side["HPG"], hpg["close"])
    assert hpg["reference_value"] == 27.1
    assert hpg["close_vs_ref"] == expected["close_vs_ref"]
    assert hpg["close_vs_ref_pct"] == expected["close_vs_ref_pct"]
    ssi = by_ev["SSI"]
    assert ssi["observation_reference"] == "BREAKOUT_REF"
    assert ssi["reference_value"] == 31.5
    assert ssi["close_vs_ref"] == ssi["close"] - 31.5
    assert isinstance(hpg["provenance"], list) and len(hpg["provenance"]) >= 1
    assert status["alert_eligible"] is False


def test_close_vs_ref_arithmetic_and_unavailable():
    ema = {
        "observation_reference": "EMA9",
        "ema9_at_first_seen": 27.1,
        "breakout_ref_at_first_seen": 28.0,
    }
    got = observe_close_vs_ref(ema, 27.4)
    assert got["reference_value"] == 27.1
    assert abs(got["close_vs_ref"] - 0.3) < 1e-9
    assert abs(got["close_vs_ref_pct"] - (0.3 / 27.1 * 100)) < 1e-9
    brk = {"observation_reference": "BREAKOUT_REF", "breakout_ref_at_first_seen": 31.5}
    got_b = observe_close_vs_ref(brk, 32.2)
    assert abs(got_b["close_vs_ref"] - 0.7) < 1e-9
    empty = observe_close_vs_ref({"observation_reference": ""}, 27.4)
    assert empty["reference_value"] is None
    assert empty["close_vs_ref"] is None
    assert empty["reference_state"] == "UNAVAILABLE"
    missing = observe_close_vs_ref({"observation_reference": "EMA9", "ema9_at_first_seen": None}, 27.4)
    assert missing["close_vs_ref"] is None
    assert "buy" not in json.dumps(got).lower() or got["close_vs_ref"] is not None
    assert pxv_implies_buy("STRENGTHEN") is False
    assert pxv_implies_buy("WEAKEN") is False
    assert pxv_implies_buy("CONFLICT") is False


def test_strengthen_does_not_imply_buy():
    assert pxv_implies_buy("STRENGTHEN") is False
    for state in GENERIC_PXV:
        assert pxv_implies_buy(state) is False


def test_no_buy_elite_fallback_for_v2(tmp_path):
    now = _ts("2026-08-14 10:40:00")
    _, sidecar, feed, _ = _e2e(
        tmp_path,
        [_scan_row("HPG", "PULL ĐẸP")],
        now=now,
        bars_by_sym={("HPG", "2026-08-14"): _grid("2026-08-14")},
        nominate_at=_ts("2026-08-14 10:05:00"),
    )
    sidecar[0].pop("candidate_reason", None)
    sidecar[0].pop("nomination_reason", None)
    sidecar[0]["elite_buy_grade"] = ""
    feed2 = LiveShadowFeed(
        provider=FakeProvider({("HPG", "2026-08-14"): _grid("2026-08-14")}),
        out_dir=tmp_path / "shadow2",
        now_fn=lambda: now,
    )
    feed2.run_cycle(sidecar)
    ev = feed2.read_evidence()
    assert ev
    assert ev[-1]["candidate_reason"] != "BUY ELITE"
    assert ev[-1]["source"] != "BUY ELITE"
    assert ev[-1]["candidate_is_buy"] is False


def test_not_yet_eligible_does_not_fetch(tmp_path):
    now = _ts("2026-08-14 10:00:00")
    report, sidecar = build_sidecar_from_scan(
        [_scan_row("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=_ts("2026-08-14 13:37:00"),
    )
    assert sidecar[0]["eligible_from"].startswith("2026-08-14T13:37:00")
    feed = LiveShadowFeed(
        provider=FakeProvider({("HPG", "2026-08-14"): _grid("2026-08-14")}),
        out_dir=tmp_path,
        now_fn=lambda: now,
    )
    st = feed.run_cycle(sidecar)
    assert st["symbols"][0]["status"] == "NOT_YET_ELIGIBLE"
    assert feed.provider.call_count == 0
    assert feed.read_evidence() == []


def test_no_bar_before_first_seen_interpreted(tmp_path):
    first = "2026-08-14T13:37:00+07:00"
    scan = [_scan_row("HPG", "PULL ĐẸP")]
    report, sidecar = build_sidecar_from_scan(scan, market_real=7.2, observed_at=_ts("2026-08-14 13:37:00"))
    assert sidecar[0]["candidate_first_seen_ts"] == first
    bars = [
        _raw_bar("2026-08-14 13:25:00"),
        _raw_bar("2026-08-14 13:30:00"),
        _raw_bar("2026-08-14 13:35:00"),
        _raw_bar("2026-08-14 13:40:00"),
    ]
    feed = LiveShadowFeed(
        provider=FakeProvider({("HPG", "2026-08-14"): bars}),
        out_dir=tmp_path,
        now_fn=lambda: _ts("2026-08-14 13:46:00"),
    )
    feed.run_cycle(sidecar)
    ev = feed.read_evidence()
    assert ev
    assert all(e["asof_hm"] != "13:35" for e in ev)
    assert ev[0]["asof_hm"] == "13:40"
    assert ev[0]["candidate_first_seen_ts"] == first
    assert ev[0]["bar_ts"] != first


def test_after_close_waits_and_preserves_sessions(tmp_path):
    nom_now = _ts("2026-08-14 15:41:00")
    _, sidecar = build_sidecar_from_scan(
        [_scan_row("VCB", "PULL ĐẸP", ema9=21.0)],
        market_real=7.2,
        observed_at=nom_now,
    )
    assert sidecar[0]["session"] == "2026-08-14"
    assert sidecar[0]["eligible_from"].startswith("2026-08-17T09:15:00")
    fri = LiveShadowFeed(
        provider=FakeProvider({("VCB", "2026-08-14"): _grid("2026-08-14")}),
        out_dir=tmp_path / "fri",
        now_fn=lambda: _ts("2026-08-14 15:50:00"),
    )
    st = fri.run_cycle(sidecar)
    assert st["symbols"][0]["status"] == "NOT_YET_ELIGIBLE"
    assert fri.provider.call_count == 0

    mon_now = _ts("2026-08-17 09:20:00")
    mon = LiveShadowFeed(
        provider=FakeProvider({("VCB", "2026-08-17"): _grid("2026-08-17", n=8, close0=21.5)}),
        out_dir=tmp_path / "mon",
        now_fn=lambda: mon_now,
    )
    mon.run_cycle(sidecar)
    ev = mon.read_evidence()
    assert ev
    assert ev[0]["nomination_session"] == "2026-08-14"
    assert ev[0]["camera_session"] == "2026-08-17"
    assert ev[0]["nomination_session"] != ev[0]["camera_session"]
    assert ev[0]["candidate_first_seen_ts"] == sidecar[0]["candidate_first_seen_ts"]
    assert not ev[0]["candidate_first_seen_ts"].startswith("2026-08-17T09:15")
    assert ev[0]["bar_ts"].startswith("2026-08-17T")


def test_injected_now_not_wall_clock(tmp_path):
    frozen_nom = _ts("2026-08-14 10:05:00")
    frozen_feed = _ts("2026-08-14 10:40:00")
    _, sidecar, feed, _ = _e2e(
        tmp_path,
        [_scan_row("HPG", "PULL ĐẸP")],
        now=frozen_feed,
        bars_by_sym={("HPG", "2026-08-14"): _grid("2026-08-14")},
        nominate_at=frozen_nom,
    )
    ev = feed.read_evidence()
    assert ev
    assert ev[0]["observed_at"].startswith("2026-08-14T10:40:00")
    assert sidecar[0]["candidate_first_seen_ts"].startswith("2026-08-14T10:05:00")
    assert all(e["candidate_first_seen_ts"].startswith("2026-08-14T10:05:00") for e in ev)
    assert ev[-1]["candidate_first_seen_ts"] != ev[-1]["observed_at"]
    assert ev[-1]["bar_ts"] != ev[-1]["observed_at"]


def test_cap_behavior_unchanged_for_v2_rows():
    now = _ts("2026-08-14 10:20:00")
    rows = []
    for i in range(60):
        rows.append(
            {
                "v2_camera": True,
                "symbol": f"S{i:03d}",
                "session": "2026-08-14",
                "eligible_from": f"2026-08-14T09:{15 + (i % 3):02d}:00+07:00",
                "candidate_first_seen_ts": "2026-08-14T09:15:00+07:00",
                "observation_intent": "WATCH_PRICE_TAPE_VS_FROZEN_REF",
                "candidate_is_buy": False,
                "source": SRC_BRAIN_A,
            }
        )
    picked = eligible_watchlist_symbols(rows, now=now, cap=LIVE_UNIVERSE_CAP)
    eligible = [r for r in picked if r.get("_skip") != "NOT_YET_ELIGIBLE"]
    assert len(eligible) == 50
    assert LIVE_UNIVERSE_CAP == 50


def test_provenance_is_a_list_not_a_single_source_assumption(tmp_path):
    now = _ts("2026-08-14 10:40:00")
    _, sidecar = build_sidecar_from_scan(
        [_scan_row("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=_ts("2026-08-14 10:05:00"),
    )
    sidecar[0]["provenance"] = [
        dict(sidecar[0]["provenance"][0]),
        {
            "source": SRC_LEARNING_INSIGHT,
            "candidate_first_seen_ts": "2026-08-14T10:40:00+07:00",
            "setup": "PULL ĐẸP",
            "group": "PULL ĐẸP",
            "source_action": "",
            "source_reason": "future-brain-b-placeholder",
            "candidate_reason": "",
            "status": "NOMINATED",
            "eligible_from": "2026-08-14T10:40:00+07:00",
        },
    ]
    feed = LiveShadowFeed(
        provider=FakeProvider({("HPG", "2026-08-14"): _grid("2026-08-14")}),
        out_dir=tmp_path,
        now_fn=lambda: now,
    )
    feed.run_cycle(sidecar)
    ev = feed.read_evidence()
    assert isinstance(ev[0]["provenance"], list)
    assert {p["source"] for p in ev[0]["provenance"]} == {SRC_BRAIN_A, SRC_LEARNING_INSIGHT}
    assert "confirmation_score" not in ev[0]
    assert SRC_LEARNING_INSIGHT not in SHADOW_V2_ENABLED_SOURCES
    assert SRC_LEARNING_INSIGHT not in ENABLED_SOURCES


def test_shadow_router_override_does_not_change_production_enabled_sources():
    assert ENABLED_SOURCES == frozenset({SRC_BUY_ELITE})
    assert SRC_BRAIN_A not in ENABLED_SOURCES
    assert SRC_BRAIN_A in SHADOW_V2_ENABLED_SOURCES
    assert SRC_LEARNING_INSIGHT not in SHADOW_V2_ENABLED_SOURCES
    now = _ts("2026-08-14 10:20:00")
    report, sidecar = build_sidecar_from_scan(
        [_scan_row("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=now,
    )
    nom = to_nominated_candidate(report.nominations[0])
    accepted, rejected = classify_nominations([nom], now=now)
    assert accepted == []
    assert rejected[0].reason == "SOURCE_NOT_ENABLED"
    shadowed = shadow_route_v2([nom], now=now)
    assert shadowed.canonical[0].symbol == "HPG"
    assert list(to_watchlist_frame(shadowed.canonical).columns) == WATCHLIST_COLUMNS
    assert "observation_intent" not in list(to_watchlist_frame(shadowed.canonical).columns)
    assert "setup" not in WATCHLIST_COLUMNS


def test_production_watchlist_and_rotation_untouched(tmp_path):
    before = PRODUCTION_WATCHLIST.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    now = _ts("2026-08-14 10:20:00")
    _, sidecar = build_sidecar_from_scan(
        [_scan_row("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=now,
    )
    write_sidecar(sidecar, observed_at=now, path=tmp_path / "camera_sidecar.json")
    try:
        write_sidecar(sidecar, observed_at=now, path=PRODUCTION_WATCHLIST)
        raise AssertionError("must refuse production watchlist")
    except RuntimeError:
        pass
    assert hashlib.sha256(PRODUCTION_WATCHLIST.read_bytes()).hexdigest() == digest
    assert "research/live_candidate_v2_camera_sidecar" in DEFAULT_SIDECAR_PATH.as_posix()
    assert DEFAULT_SIDECAR_PATH.name != "dynamic_watchlist.json"
    assert nominations_from_rotation_artifact({"rows": [{"symbol": "CII"}]}) == ()
    assert SRC_ROTATION not in ENABLED_SOURCES
    assert SRC_ROTATION not in SHADOW_V2_ENABLED_SOURCES
    cam_root = REPO / "modules" / "live_candidate_v2_camera"
    for path in cam_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "modules.rotation_watch" not in text
        assert "systemctl" not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "GROUP_RANK"
    assert "intraday_pxv_v1.interpret" not in (REPO / "modules" / "live_candidate_v2_camera" / "observe.py").read_text()


def test_elite_feed_path_still_defaults_buy_elite_and_skips_v2_overlay(tmp_path):
    now = _ts("2026-08-14 10:40:00")
    rec = {
        "session": "2026-08-14",
        "symbol": "HPG",
        "candidate_first_seen_ts": "2026-08-14T08:00:00+07:00",
        "candidate_updated_ts": "2026-08-14T08:00:00+07:00",
        "status": "ACTIVE",
        "eligible_from": "2026-08-14T08:00:00+07:00",
        "source": "buy_elite_learning_history",
    }
    feed = LiveShadowFeed(
        provider=FakeProvider({("HPG", "2026-08-14"): _grid("2026-08-14")}),
        out_dir=tmp_path,
        now_fn=lambda: now,
    )
    feed.run_cycle([rec])
    ev = feed.read_evidence()
    assert ev
    assert ev[0].get("v2_camera") is not True
    assert "nomination_source" not in ev[0]
    assert "nomination_session" not in ev[0]
    assert ev[0]["source"] == "live_shadow"
    feed_src = (REPO / "modules" / "live_camera_shadow" / "feed.py").read_text(encoding="utf-8")
    assert 'event_reason = str(rec.get("candidate_reason") or "BUY ELITE")' in feed_src


def test_production_eight_column_frame_drops_v2_fields():
    now = _ts("2026-08-14 10:20:00")
    report, sidecar = build_sidecar_from_scan(
        [_scan_row("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=now,
    )
    nom = to_nominated_candidate(report.nominations[0])
    frame = to_watchlist_frame([nom])
    assert list(frame.columns) == WATCHLIST_COLUMNS
    lost = {
        "setup",
        "observation_intent",
        "observation_reference",
        "ema9_at_first_seen",
        "breakout_ref_at_first_seen",
        "price_at_first_seen",
        "provenance",
        "candidate_is_buy",
        "alert_eligible",
        "source_action",
        "source_reason",
        "elite_buy_grade",
        "market_real",
        "market_permission",
    }
    for col in lost:
        assert col not in frame.columns
        assert col in sidecar[0]


def test_sidecar_schema_id():
    now = _ts("2026-08-14 10:20:00")
    _, sidecar = build_sidecar_from_scan(
        [_scan_row("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=now,
    )
    from modules.live_candidate_v2_camera.sidecar import build_sidecar_document

    doc = build_sidecar_document(sidecar, observed_at=now, market_real=7.2)
    assert doc["schema"] == SCHEMA_ID
    assert doc["candidate_is_buy"] is False
    assert doc["router_wired_to_production"] is False
    assert SRC_BUY_ELITE in doc["production_enabled_sources"]
    assert SRC_BRAIN_A not in doc["production_enabled_sources"]
