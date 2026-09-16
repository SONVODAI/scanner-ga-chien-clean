"""LIVE CANDIDATE V2 Slice 1 — Brain A nomination SHADOW.

Candidate != BUY. Isolated from production dynamic_watchlist.json.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.candidate_router.adapters.rotation import nominations_from_rotation_artifact
from modules.candidate_router.contract import ENABLED_SOURCES, SRC_BUY_ELITE, SRC_ROTATION
from modules.candidate_router.router import classify_nominations
from modules.live_candidate_v2_nomination.artifact import (
    DEFAULT_SHADOW_PATH,
    PRODUCTION_WATCHLIST,
    assert_not_production_watchlist,
    build_shadow_document,
    write_shadow_artifact,
)
from modules.live_candidate_v2_nomination.contract import (
    PRIMARY_SETUPS,
    REJECT_BARE_MUA_EARLY,
    REJECT_ELITE_GRADE_ALONE,
    REJECT_HARD_BAD,
    REJECT_MARKET_WEAK,
    REJECT_SETUP_EXCLUDED,
    REJECT_SETUP_RESERVED,
    REJECT_WATCHLIST_ALONE,
    REJECT_WINPROB_ALONE,
    SRC_BRAIN_A,
)
from modules.live_candidate_v2_nomination.intent import (
    APP_PY_INTENT_STRINGS,
    CANH_ADD_ACTION,
    CHO_PULL_ACTION,
    MUA_BREAK_ACTION,
    MUA_BREAK_REASON,
    PULL_DEP_ACTION,
    PULL_VUA_ACTION,
    TEST_EARLY_ACTION,
    observation_intent,
)
from modules.live_candidate_v2_nomination.nominate import nominate_scan_rows, to_nominated_candidate

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _row(symbol: str, group: str, **extra) -> dict:
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


def _nominate(rows, *, market_real=7.2, observed="2026-08-14 10:05:00", prior=None, route=True):
    return nominate_scan_rows(
        rows,
        market_real=market_real,
        observed_at=_ts(observed),
        prior_freeze=prior,
        route=route,
    )


def test_1_primary_setups_nominate():
    rows = [
        _row("HPG", "PULL ĐẸP"),
        _row("VCB", "PULL VỪA"),
        _row("SSI", "MUA BREAK"),
        _row("FPT", "CP MẠNH", dist_from_ema9_pct=2.0),
    ]
    report = _nominate(rows)
    got = {n.symbol: n.setup for n in report.nominations}
    assert got == {"HPG": "PULL ĐẸP", "VCB": "PULL VỪA", "SSI": "MUA BREAK", "FPT": "CP MẠNH"}
    assert PRIMARY_SETUPS == set(got.values())
    assert all(n.status == "NOMINATED" for n in report.nominations)
    assert all(n.source == SRC_BRAIN_A for n in report.nominations)
    assert all("BUY" not in n.status for n in report.nominations)


def test_2_qualified_early_nominates():
    lab = _row("MWG", "MUA EARLY", InEarlyLab=True, total_score=2, dist_from_ema9_pct=3.0)
    test_early = _row(
        "PNJ",
        "MUA EARLY",
        InEarlyLab=False,
        total_score=4,
        obv_status="🟢",
        dist_from_ema9_pct=1.0,
    )
    report = _nominate([lab, test_early])
    by = {n.symbol: n for n in report.nominations}
    assert set(by) == {"MWG", "PNJ"}
    assert "IN_EARLY_LAB" in by["MWG"].qualified_by
    assert "TEST EARLY" in by["PNJ"].qualified_by
    assert TEST_EARLY_ACTION in by["PNJ"].observation_intent
    assert by["MWG"].in_early_lab is True


def test_3_bare_mua_early_does_not_nominate():
    bare = _row(
        "AAA",
        "MUA EARLY",
        InEarlyLab=False,
        total_score=2,
        dist_from_ema9_pct=3.5,
        obv_status="🟡",
    )
    report = _nominate([bare])
    assert report.nominations == ()
    assert report.rejected[0].reason == REJECT_BARE_MUA_EARLY
    assert report.rejected[0].symbol == "AAA"


def test_4_theo_doi_and_tich_luy_do_not_nominate():
    rows = [_row("BBB", "THEO DÕI"), _row("CCC", "TÍCH LŨY")]
    report = _nominate(rows)
    assert report.nominations == ()
    reasons = {r.symbol: r.reason for r in report.rejected}
    assert reasons == {"BBB": REJECT_SETUP_EXCLUDED, "CCC": REJECT_SETUP_EXCLUDED}


def test_5_market_weak_and_hard_bad_do_not_spend_camera():
    pull = _row("HPG", "PULL ĐẸP", conclusion="BUY ELITE")
    weak = _nominate([pull], market_real=5.5)
    assert weak.nominations == ()
    assert weak.rejected[0].reason == REJECT_MARKET_WEAK
    assert weak.market_permission == "WATCHLIST - MARKET YẾU"

    bad_obv = _row("VCB", "PULL VỪA", warning="OBV gãy | RSI yếu")
    bad_ema = _row("SSI", "MUA BREAK", warning="Giá dưới EMA9")
    bad_concl = _row("FPT", "CP MẠNH", conclusion="LOẠI - TRỤC XẤU")
    hard = _nominate([bad_obv, bad_ema, bad_concl], market_real=8.0)
    assert hard.nominations == ()
    assert {r.reason for r in hard.rejected} == {REJECT_HARD_BAD}


def test_6_watchlist_or_winprob_alone_cannot_nominate():
    wl = _row("AAA", "", conclusion="WATCHLIST", WinProb=70)
    wp = _row("BBB", "", WinProb=92.0)
    report = _nominate([wl, wp])
    assert report.nominations == ()
    reasons = {r.symbol: r.reason for r in report.rejected}
    assert reasons["AAA"] == REJECT_WATCHLIST_ALONE
    assert reasons["BBB"] == REJECT_WINPROB_ALONE


def test_7_buy_elite_alone_cannot_nominate_without_eligible_setup():
    elite_watch = _row("AAA", "THEO DÕI", conclusion="BUY ELITE", WinProb=90)
    elite_empty = _row("BBB", "", conclusion="BUY ELITE", WinProb=91)
    mua_nho = _row("CCC", "TÍCH LŨY", conclusion="MUA NHỎ / ƯU TIÊN")
    accel = _row("DDD", "GÀ TĂNG TỐC", conclusion="BUY ELITE")
    report = _nominate([elite_watch, elite_empty, mua_nho, accel])
    assert report.nominations == ()
    reasons = {r.symbol: r.reason for r in report.rejected}
    assert reasons["AAA"] == REJECT_SETUP_EXCLUDED
    assert reasons["BBB"] == REJECT_ELITE_GRADE_ALONE
    assert reasons["CCC"] == REJECT_SETUP_EXCLUDED
    assert reasons["DDD"] == REJECT_SETUP_RESERVED
    # Primary + BUY ELITE still nominates; grade is metadata only.
    ok = _nominate([_row("HPG", "PULL ĐẸP", conclusion="BUY ELITE")])
    assert ok.nominations[0].setup == "PULL ĐẸP"
    assert ok.nominations[0].elite_buy_grade == "BUY ELITE"
    assert ok.nominations[0].status == "NOMINATED"


def test_8_first_seen_is_immutable_across_rescans():
    t0 = "2026-08-14 10:05:00"
    t1 = "2026-08-14 13:20:00"
    first = _nominate([_row("HPG", "PULL ĐẸP")], observed=t0)
    assert first.nominations[0].candidate_first_seen_ts == _ts(t0).isoformat()
    second = _nominate(
        [_row("HPG", "PULL VỪA", price=30.0)],
        observed=t1,
        prior=first.freeze_ledger,
    )
    assert second.nominations[0].candidate_first_seen_ts == _ts(t0).isoformat()
    assert second.nominations[0].candidate_updated_ts == _ts(t1).isoformat()
    # Drop then return same session: do not restamp.
    gone = _nominate([_row("AAA", "THEO DÕI")], observed="2026-08-14 11:00:00", prior=first.freeze_ledger)
    assert gone.nominations == ()
    back = _nominate([_row("HPG", "PULL ĐẸP")], observed="2026-08-14 14:00:00", prior=gone.freeze_ledger)
    assert back.nominations[0].candidate_first_seen_ts == _ts(t0).isoformat()
    # Later row must not backfill an earlier clock.
    late_first = _nominate([_row("VCB", "MUA BREAK")], observed="2026-08-14 14:00:00")
    assert late_first.nominations[0].candidate_first_seen_ts == _ts("2026-08-14 14:00:00").isoformat()
    assert late_first.nominations[0].candidate_first_seen_ts != _ts(t0).isoformat()
    # Next session is a new episode.
    nxt = _nominate(
        [_row("HPG", "PULL ĐẸP", date="2026-08-17")],
        observed="2026-08-17 09:20:00",
        prior=first.freeze_ledger,
    )
    assert nxt.nominations[0].candidate_first_seen_ts == _ts("2026-08-17 09:20:00").isoformat()
    assert nxt.nominations[0].session == "2026-08-17"


def test_9_price_and_frozen_refs_immutable_with_first_seen():
    t0 = "2026-08-14 10:05:00"
    first = _nominate(
        [_row("HPG", "MUA BREAK", price=27.5, ema9=27.1, breakout_ref=28.0)],
        observed=t0,
    )
    nom = first.nominations[0]
    assert nom.price_at_first_seen == 27.5
    assert nom.ema9_at_first_seen == 27.1
    assert nom.breakout_ref_at_first_seen == 28.0
    second = _nominate(
        [_row("HPG", "MUA BREAK", price=31.0, ema9=29.0, breakout_ref=33.0)],
        observed="2026-08-14 13:20:00",
        prior=first.freeze_ledger,
    )
    again = second.nominations[0]
    assert again.candidate_first_seen_ts == nom.candidate_first_seen_ts
    assert again.price_at_first_seen == 27.5
    assert again.ema9_at_first_seen == 27.1
    assert again.breakout_ref_at_first_seen == 28.0


def test_10_setup_reason_intent_survive_routing_and_shadow_serialization(tmp_path):
    rows = [
        _row("HPG", "PULL ĐẸP", conclusion="WATCHLIST"),
        _row("FPT", "CP MẠNH", dist_from_ema9_pct=5.0),
        _row("PNJ", "MUA EARLY", total_score=4, dist_from_ema9_pct=1.0),
    ]
    report = _nominate(rows)
    by = {n.symbol: n for n in report.nominations}
    assert PULL_DEP_ACTION in by["HPG"].observation_intent
    assert by["FPT"].observation_action == CHO_PULL_ACTION
    assert TEST_EARLY_ACTION in by["PNJ"].observation_intent
    assert MUA_BREAK_REASON  # lock imported existing text
    assert PULL_VUA_ACTION
    assert CANH_ADD_ACTION
    assert report.route_report is not None
    routed = {n.symbol: n for n in report.route_report.canonical}
    assert routed["HPG"].group == "PULL ĐẸP"
    assert routed["HPG"].setup == "PULL ĐẸP"
    assert routed["HPG"].candidate_reason == by["HPG"].nomination_reason
    assert routed["HPG"].source_reason == by["HPG"].observation_intent
    assert routed["HPG"].source == SRC_BRAIN_A
    assert routed["FPT"].source_action == CHO_PULL_ACTION
    path = write_shadow_artifact(report, path=tmp_path / "nominations.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["candidate_is_buy"] is False
    snap = {n["symbol"]: n for n in doc["nominations"]}
    assert snap["HPG"]["setup"] == "PULL ĐẸP"
    assert snap["HPG"]["nomination_reason"] == by["HPG"].nomination_reason
    assert snap["HPG"]["observation_intent"] == by["HPG"].observation_intent
    assert snap["HPG"]["elite_buy_grade"] == ""
    assert snap["FPT"]["observation_intent"] == by["FPT"].observation_intent
    routed_obj = to_nominated_candidate(by["PNJ"])
    assert routed_obj.group == "MUA EARLY"
    assert routed_obj.source_action == TEST_EARLY_ACTION


def test_11_no_production_watchlist_bytes_change(tmp_path):
    before = PRODUCTION_WATCHLIST.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    report = _nominate([_row("HPG", "PULL ĐẸP")])
    write_shadow_artifact(report, path=tmp_path / "nominations.json")
    assert hashlib.sha256(PRODUCTION_WATCHLIST.read_bytes()).hexdigest() == digest
    assert PRODUCTION_WATCHLIST.read_bytes() == before
    assert PRODUCTION_WATCHLIST.as_posix().endswith("data/live_candidate/dynamic_watchlist.json")
    try:
        write_shadow_artifact(report, path=PRODUCTION_WATCHLIST)
        raise AssertionError("must refuse production watchlist path")
    except RuntimeError as exc:
        assert "dynamic_watchlist.json" in str(exc)
    try:
        assert_not_production_watchlist(tmp_path / "dynamic_watchlist.json")
        raise AssertionError("must refuse that filename")
    except RuntimeError:
        pass
    # Default shadow path is research/, not data/live_candidate/.
    assert "research/live_candidate_v2_nomination_shadow" in DEFAULT_SHADOW_PATH.as_posix()
    assert DEFAULT_SHADOW_PATH.name != "dynamic_watchlist.json"


def test_12_rotation_remains_disconnected():
    assert ENABLED_SOURCES == frozenset({SRC_BUY_ELITE})
    assert SRC_BRAIN_A not in ENABLED_SOURCES
    assert SRC_ROTATION not in ENABLED_SOURCES
    assert nominations_from_rotation_artifact({"rows": [{"symbol": "CII"}]}) == ()
    report = _nominate([_row("HPG", "PULL ĐẸP")])
    accepted, rejected = classify_nominations(
        [to_nominated_candidate(report.nominations[0])],
        now=_ts("2026-08-14 10:05:00"),
    )
    assert accepted == []
    assert rejected[0].reason == "SOURCE_NOT_ENABLED"
    nom_root = REPO / "modules" / "live_candidate_v2_nomination"
    for path in nom_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "modules.rotation_watch" not in text
        assert "intraday_pxv" not in text
        assert "GROUP_RANK" not in text
        assert "apply_immutable_first_seen" not in text
        assert "persist_research_watchlist" not in text
        assert "persist_and_publish_research_watchlist" not in text
        assert "systemctl" not in text
        assert "telegram" not in text.lower()


def test_observation_intent_strings_are_existing_buy_recommendation_text():
    app_src = (REPO / "app.py").read_text(encoding="utf-8")
    start = app_src.index("def buy_recommendation")
    end = app_src.index("\ndef build_buy_table")
    body = app_src[start:end]
    for phrase in APP_PY_INTENT_STRINGS:
        assert phrase in body
    assert observation_intent(_row("HPG", "PULL ĐẸP")).startswith("MUA PULL ĐẸP")
    assert "không đuổi quá xa" in observation_intent(_row("SSI", "MUA BREAK"))


def test_production_publishers_do_not_import_brain_a():
    def _imports(path: Path, name: str) -> bool:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == name or alias.name.startswith(name + "."):
                        return True
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == name or node.module.startswith(name + "."):
                    return True
        return False

    forbidden = []
    for rel in (
        "app.py",
        "modules/live_candidate/watchlist.py",
        "modules/live_candidate/persist.py",
        "modules/live_shadow_transport/watchlist_bus.py",
        "modules/candidate_router/router.py",
        "modules/candidate_router/elite.py",
        "modules/candidate_router/contract.py",
    ):
        path = REPO / rel
        if _imports(path, "modules.live_candidate_v2_nomination"):
            forbidden.append(rel)
    assert forbidden == []
    rot = REPO / "modules" / "rotation_watch"
    if rot.exists():
        hits = [p for p in rot.rglob("*.py") if _imports(p, "modules.live_candidate_v2_nomination")]
        assert hits == []
    pxv = REPO / "modules" / "intraday_pxv_v1"
    if pxv.exists():
        hits = [p for p in pxv.rglob("*.py") if _imports(p, "modules.live_candidate_v2_nomination")]
        assert hits == []
    from modules.live_shadow_transport.watchlist_bus import persist_and_publish_research_watchlist

    source = inspect.getsource(persist_and_publish_research_watchlist)
    assert "live_candidate_v2_nomination" not in source
    assert "nominate_scan_rows" not in source


def test_after_close_chronology_stamps_eligible_from_next_open():
    friday = _nominate([_row("VCB", "PULL ĐẸP")], observed="2026-08-14 15:41:00")
    nom = friday.nominations[0]
    assert nom.candidate_first_seen_ts == _ts("2026-08-14 15:41:00").isoformat()
    assert nom.eligible_from.startswith("2026-08-17T09:15:00")
    assert nom.chronology_status == "NOT_YET_ELIGIBLE"
    monday = nominate_scan_rows(
        [_row("VCB", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=_ts("2026-08-17 09:15:00"),
        prior_freeze=friday.freeze_ledger,
    )
    # Same session date keeps Friday first_seen; Camera is eligible at Monday open.
    assert monday.nominations[0].session == "2026-08-14"
    assert monday.nominations[0].candidate_first_seen_ts == nom.candidate_first_seen_ts
    assert monday.nominations[0].chronology_status == "ELIGIBLE"


def test_shadow_document_schema_and_sample_fields():
    report = _nominate(
        [
            _row("HPG", "PULL ĐẸP", conclusion="BUY ELITE", price=27.5, ema9=27.1),
            _row("AAA", "THEO DÕI", conclusion="WATCHLIST", WinProb=66),
        ]
    )
    doc = build_shadow_document(report, generated_at=_ts("2026-08-14 10:05:00"))
    assert doc["schema"] == "live_candidate_v2_brain_a_nomination_shadow_v1"
    assert doc["mode"] == "SHADOW_ONLY"
    assert doc["candidate_is_buy"] is False
    assert doc["router_wired_to_production"] is False
    nom = doc["nominations"][0]
    for key in (
        "symbol",
        "setup",
        "candidate_first_seen_ts",
        "price_at_first_seen",
        "ema9_at_first_seen",
        "breakout_ref_at_first_seen",
        "nomination_reason",
        "observation_intent",
        "elite_buy_grade",
        "market_real",
        "market_permission",
        "source",
        "eligible_from",
        "chronology_status",
    ):
        assert key in nom
    assert nom["elite_buy_grade"] == "BUY ELITE"
    assert nom["source"] == SRC_BRAIN_A
