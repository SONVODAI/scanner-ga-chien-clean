"""Slice 1 Candidate Router: Elite-only, shadow, no production publish."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.candidate_router.adapters.rotation import nominations_from_rotation_artifact
from modules.candidate_router.contract import (
    ENABLED_SOURCES,
    NominatedCandidate,
    REJECT_CHRONOLOGY_BACKWARD,
    REJECT_ILLEGAL_FIRST_SEEN,
    REJECT_MISSING_FIRST_SEEN,
    REJECT_SOURCE_NOT_ENABLED,
    SOURCE_PRIORITY,
    SRC_BUY_ELITE,
    SRC_HOF,
    SRC_LEARNING_INSIGHT,
    SRC_ROTATION,
    UNIVERSE_CAP,
    WATCHLIST_COLUMNS,
)
from modules.candidate_router.elite import nominations_from_buy_elite_history
from modules.candidate_router.router import (
    build_routed_report,
    build_routed_watchlist,
    classify_nominations,
    route_candidates,
    route_report,
)
from modules.live_camera_shadow.rate import LIVE_UNIVERSE_CAP
from modules.live_candidate.calendar import next_trading_session_open
from modules.live_candidate.contract import SOURCE as ELITE_SOURCE
from modules.live_candidate.persist import apply_immutable_first_seen
from modules.live_candidate.watchlist import build_research_watchlist, encode_watchlist_text

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _row(day: str, symbol: str, conclusion: str, **extra) -> dict:
    rec = {
        "date": day,
        "time": extra.pop("time", "10:00:00"),
        "symbol": symbol,
        "conclusion": conclusion,
        "winprob": extra.pop("winprob", 80.0),
        "elite_score": extra.pop("elite_score", 70.0),
        "group": extra.pop("group", "PULL VỪA"),
    }
    rec.update(extra)
    return rec


def _hist(*rows: dict, observed: str = "2026-08-14 10:05:00") -> pd.DataFrame:
    return apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame(list(rows)),
        observed_at=_ts(observed),
    )


def _nom(
    symbol: str,
    *,
    source: str = SRC_BUY_ELITE,
    first_seen: str = "2026-08-14T10:05:00+07:00",
    eligible_from: str | None = None,
    session: str = "2026-08-14",
    updated: str | None = None,
    status: str = "ACTIVE",
    reason: str = "BUY ELITE",
    group: str = "",
    setup: str = "",
    source_state: str | None = None,
    source_action: str = "",
    source_reason: str | None = None,
) -> NominatedCandidate:
    if eligible_from is None:
        eligible_from = first_seen
    if updated is None:
        updated = first_seen
    if source_state is None:
        source_state = status
    if source_reason is None:
        source_reason = reason
    return NominatedCandidate(
        symbol=symbol,
        source=source,
        candidate_first_seen_ts=first_seen,
        candidate_updated_ts=updated,
        eligible_from=eligible_from,
        session=session,
        status=status,
        candidate_reason=reason,
        source_state=source_state,
        source_action=source_action,
        source_reason=source_reason,
        group=group,
        setup=setup,
    )


def test_universe_cap_matches_live_camera_constant():
    assert UNIVERSE_CAP == 50
    assert UNIVERSE_CAP == LIVE_UNIVERSE_CAP


def test_slice1_enables_only_buy_elite():
    assert ENABLED_SOURCES == frozenset({SRC_BUY_ELITE})
    assert SRC_BUY_ELITE == ELITE_SOURCE
    assert SRC_BUY_ELITE == "buy_elite_learning_history"
    for src in (SRC_ROTATION, SRC_HOF, SRC_LEARNING_INSIGHT):
        assert src not in ENABLED_SOURCES
        assert src in SOURCE_PRIORITY


def test_elite_only_router_matches_current_watchlist_bytes():
    hist = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame(
            [
                _row("2026-08-14", "HPG", "BUY ELITE"),
                _row("2026-08-14", "VCB", "MUA NHỎ / ƯU TIÊN"),
                _row("2026-08-14", "AAA", "WATCHLIST"),
            ]
        ),
        observed_at=_ts("2026-08-14 10:05:00"),
    )
    now = _ts("2026-08-14 10:05:00")
    current = build_research_watchlist(hist, now=now)
    routed = build_routed_watchlist(hist, now=now, cap=None)
    pd.testing.assert_frame_equal(
        current.reset_index(drop=True),
        routed.reset_index(drop=True),
        check_dtype=False,
    )
    assert encode_watchlist_text(current) == encode_watchlist_text(routed)
    assert list(routed.columns) == WATCHLIST_COLUMNS


def test_elite_equivalence_after_close_and_held_status():
    friday = _ts("2026-08-14 15:41:00")
    hist = _hist(_row("2026-08-14", "VCB", "MUA NHỎ / ƯU TIÊN"), observed="2026-08-14 15:41:00")
    assert build_routed_watchlist(hist, now=friday, cap=None).empty
    assert build_research_watchlist(hist, now=friday).empty
    monday = next_trading_session_open(friday.date())
    routed = build_routed_watchlist(hist, now=monday, cap=None)
    current = build_research_watchlist(hist, now=monday)
    pd.testing.assert_frame_equal(
        current.reset_index(drop=True),
        routed.reset_index(drop=True),
        check_dtype=False,
    )

    t0 = _ts("2026-08-14 10:05:00")
    t1 = _ts("2026-08-14 11:00:00")
    first = _hist(_row("2026-08-14", "HPG", "BUY ELITE"), observed="2026-08-14 10:05:00")
    later = apply_immutable_first_seen(
        first,
        pd.DataFrame([_row("2026-08-14", "HPG", "WATCHLIST")]),
        observed_at=t1,
    )
    routed_held = build_routed_watchlist(later, now=t1, cap=None)
    current_held = build_research_watchlist(later, now=t1)
    pd.testing.assert_frame_equal(
        current_held.reset_index(drop=True),
        routed_held.reset_index(drop=True),
        check_dtype=False,
    )
    assert routed_held.iloc[0]["status"] == "HELD"
    assert routed_held.iloc[0]["candidate_first_seen_ts"] == t0.isoformat()


def test_illegal_and_missing_first_seen_rejected():
    now = _ts("2026-08-14 10:05:00")
    missing = _nom("HPG", first_seen="")
    nan = _nom("VCB", first_seen="nan")
    garbage = _nom("AAA", first_seen="not-a-timestamp")
    accepted, rejected = classify_nominations([missing, nan, garbage], now=now)
    assert accepted == []
    reasons = {r.nomination.symbol: r.reason for r in rejected}
    assert reasons["HPG"] == REJECT_MISSING_FIRST_SEEN
    assert reasons["VCB"] == REJECT_MISSING_FIRST_SEEN
    assert reasons["AAA"] == REJECT_ILLEGAL_FIRST_SEEN
    out = route_candidates([missing, nan, garbage, _nom("SSI")], now=now)
    assert list(out["symbol"]) == ["SSI"]
    assert out.iloc[0]["candidate_first_seen_ts"] == "2026-08-14T10:05:00+07:00"

    prior = pd.DataFrame([_row("2026-06-29", "ACB", "BUY ELITE", time="22:30:23")])
    assert "candidate_first_seen_ts" not in prior.columns
    routed = build_routed_watchlist(prior, now=now, cap=None)
    assert routed.empty
    assert "ACB" not in set(routed["symbol"]) if len(routed) else True


def test_never_reconstructs_first_seen_from_csv_save_time():
    now = _ts("2026-08-14 10:05:00")
    hist = pd.DataFrame(
        [
            {
                "date": "2026-08-14",
                "time": "22:30:23",
                "symbol": "HPG",
                "conclusion": "BUY ELITE",
                "winprob": 80.0,
                "elite_score": 70.0,
                "group": "PULL VỪA",
                "csv_saved_at": "2026-08-14T22:30:23+07:00",
            }
        ]
    )
    routed = build_routed_watchlist(hist, now=now, cap=None)
    assert routed.empty
    noms = nominations_from_buy_elite_history(hist, now=now)
    assert noms == ()


def test_dedup_is_deterministic():
    now = _ts("2026-08-14 11:00:00")
    early = _nom("HPG", first_seen="2026-08-14T10:05:00+07:00", updated="2026-08-14T10:05:00+07:00")
    late = _nom("HPG", first_seen="2026-08-14T10:40:00+07:00", updated="2026-08-14T10:40:00+07:00")
    a = route_candidates([early, late], now=now)
    b = route_candidates([late, early], now=now)
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
    assert len(a) == 1
    assert a.iloc[0]["candidate_first_seen_ts"] == "2026-08-14T10:40:00+07:00"


def test_cap_is_deterministic():
    now = _ts("2026-08-14 11:00:00")
    noms = [
        _nom("CCC", eligible_from="2026-08-14T10:30:00+07:00", first_seen="2026-08-14T10:30:00+07:00"),
        _nom("AAA", eligible_from="2026-08-14T10:10:00+07:00", first_seen="2026-08-14T10:10:00+07:00"),
        _nom("BBB", eligible_from="2026-08-14T10:10:00+07:00", first_seen="2026-08-14T10:10:00+07:00"),
        _nom("DDD", eligible_from="2026-08-14T10:40:00+07:00", first_seen="2026-08-14T10:40:00+07:00"),
    ]
    out = route_candidates(list(reversed(noms)), now=now, cap=2)
    assert list(out["symbol"]) == ["AAA", "BBB"]
    again = route_candidates(noms, now=now, cap=UNIVERSE_CAP)
    assert list(again["symbol"]) == ["AAA", "BBB", "CCC", "DDD"]
    assert len(route_candidates(noms, now=now, cap=0)) == 0


def test_chronology_cannot_move_backward():
    now = _ts("2026-08-14 11:00:00")
    later_stamp = _nom("HPG", first_seen="2026-08-14T10:40:00+07:00", eligible_from="2026-08-14T10:40:00+07:00")
    earlier_stamp = _nom("HPG", first_seen="2026-08-14T10:05:00+07:00", eligible_from="2026-08-14T10:05:00+07:00")
    out = route_candidates([later_stamp, earlier_stamp], now=now)
    assert out.iloc[0]["candidate_first_seen_ts"] == "2026-08-14T10:40:00+07:00"

    illegal = _nom(
        "VCB",
        first_seen="2026-08-14T10:40:00+07:00",
        eligible_from="2026-08-14T10:00:00+07:00",
    )
    accepted, rejected = classify_nominations([illegal], now=now)
    assert accepted == []
    assert rejected[0].reason == REJECT_CHRONOLOGY_BACKWARD

    t0 = _ts("2026-08-14 10:05:00")
    hist = _hist(_row("2026-08-14", "HPG", "BUY ELITE"), observed="2026-08-14 10:05:00")
    early = build_routed_watchlist(hist, now=_ts("2026-08-14 10:04:00"), cap=None)
    assert early.empty
    on_time = build_routed_watchlist(hist, now=t0, cap=None)
    later = build_routed_watchlist(hist, now=_ts("2026-08-14 13:00:00"), cap=None)
    assert on_time.iloc[0]["candidate_first_seen_ts"] == t0.isoformat()
    assert later.iloc[0]["candidate_first_seen_ts"] == t0.isoformat()
    assert later.iloc[0]["eligible_from"] == on_time.iloc[0]["eligible_from"]


def test_source_provenance_preserved():
    hist = _hist(_row("2026-08-14", "HPG", "BUY ELITE"), observed="2026-08-14 10:05:00")
    routed = build_routed_watchlist(hist, now=_ts("2026-08-14 10:05:00"), cap=None)
    assert list(routed["source"]) == [SRC_BUY_ELITE]
    nom = nominations_from_buy_elite_history(hist, now=_ts("2026-08-14 10:05:00"))[0]
    assert nom.source == SRC_BUY_ELITE
    assert nom.source_state == "ACTIVE"
    assert nom.candidate_reason == "BUY ELITE"
    assert nom.group == "PULL VỪA"
    assert nom.setup == ""


def test_no_non_elite_source_can_enter_this_slice():
    now = _ts("2026-08-14 10:05:00")
    noms = [
        _nom("CII", source=SRC_ROTATION),
        _nom("FPT", source=SRC_HOF),
        _nom("MWG", source=SRC_LEARNING_INSIGHT),
        _nom("HPG", source=SRC_BUY_ELITE),
        _nom("FAKE", source="unknown_source"),
    ]
    accepted, rejected = classify_nominations(noms, now=now)
    assert [n.symbol for n in accepted] == ["HPG"]
    assert {r.nomination.symbol: r.reason for r in rejected} == {
        "CII": REJECT_SOURCE_NOT_ENABLED,
        "FPT": REJECT_SOURCE_NOT_ENABLED,
        "MWG": REJECT_SOURCE_NOT_ENABLED,
        "FAKE": REJECT_SOURCE_NOT_ENABLED,
    }
    out = route_candidates(noms, now=now)
    assert list(out["symbol"]) == ["HPG"]
    assert list(out["source"]) == [SRC_BUY_ELITE]
    assert nominations_from_rotation_artifact({"rows": [{"symbol": "CII"}]}) == ()


def test_buy_elite_history_is_not_modified():
    hist = _hist(
        _row("2026-08-14", "HPG", "BUY ELITE", winprob=88.0, elite_score=91.0),
        observed="2026-08-14 10:05:00",
    )
    before = hist.copy(deep=True)
    build_routed_watchlist(hist, now=_ts("2026-08-14 10:05:00"), cap=None)
    nominations_from_buy_elite_history(hist, now=_ts("2026-08-14 10:05:00"))
    pd.testing.assert_frame_equal(before, hist)
    assert hist.iloc[0]["conclusion"] == "BUY ELITE"
    assert float(hist.iloc[0]["winprob"]) == 88.0
    assert float(hist.iloc[0]["elite_score"]) == 91.0


def test_priority_infrastructure_is_deterministic_when_enabled():
    now = _ts("2026-08-14 11:00:00")
    elite = _nom("HPG", source=SRC_BUY_ELITE, first_seen="2026-08-14T10:05:00+07:00")
    rotation = _nom("HPG", source=SRC_ROTATION, first_seen="2026-08-14T10:40:00+07:00")
    both = frozenset({SRC_BUY_ELITE, SRC_ROTATION})
    out = route_candidates([rotation, elite], now=now, enabled_sources=both)
    assert len(out) == 1
    assert out.iloc[0]["source"] == SRC_BUY_ELITE
    assert out.iloc[0]["candidate_first_seen_ts"] == "2026-08-14T10:05:00+07:00"
    reversed_out = route_candidates([elite, rotation], now=now, enabled_sources=both)
    pd.testing.assert_frame_equal(out.reset_index(drop=True), reversed_out.reset_index(drop=True))


def _imports_candidate_router(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "modules.candidate_router" or alias.name.startswith(
                    "modules.candidate_router."
                ):
                    return True
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "modules.candidate_router" or node.module.startswith(
                "modules.candidate_router."
            ):
                return True
            if "candidate_router" in node.module.split("."):
                return True
    return False


def test_rotation_watch_does_not_import_candidate_router():
    root = REPO / "modules" / "rotation_watch"
    hits = [p for p in root.rglob("*.py") if _imports_candidate_router(p)]
    assert hits == []


def test_production_write_path_does_not_use_router():
    bus = (REPO / "modules" / "live_shadow_transport" / "watchlist_bus.py").read_text(encoding="utf-8")
    watchlist = (REPO / "modules" / "live_candidate" / "watchlist.py").read_text(encoding="utf-8")
    persist = (REPO / "modules" / "live_candidate" / "persist.py").read_text(encoding="utf-8")
    app_src = (REPO / "app.py").read_text(encoding="utf-8")
    for src in (bus, watchlist, persist):
        assert "candidate_router" not in src
        assert "build_routed_watchlist" not in src
        assert "route_candidates" not in src
    assert "persist_and_publish_research_watchlist" in app_src
    assert "build_routed_watchlist" not in app_src
    assert "route_candidates" not in app_src
    from modules.live_shadow_transport.watchlist_bus import persist_and_publish_research_watchlist

    source = inspect.getsource(persist_and_publish_research_watchlist)
    assert "persist_research_watchlist" in source
    assert "build_routed_watchlist" not in source


def test_router_does_not_stamp_first_seen_via_persist():
    for path in (REPO / "modules" / "candidate_router").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "apply_immutable_first_seen" not in text
        assert "systemctl" not in text
        assert ".service" not in text


def test_default_router_cap_is_none():
    assert inspect.signature(route_candidates).parameters["cap"].default is None
    assert inspect.signature(route_report).parameters["cap"].default is None
    assert inspect.signature(build_routed_watchlist).parameters["cap"].default is None
    now = _ts("2026-08-14 11:00:00")
    noms = [
        _nom("CCC", eligible_from="2026-08-14T10:30:00+07:00", first_seen="2026-08-14T10:30:00+07:00"),
        _nom("AAA", eligible_from="2026-08-14T10:10:00+07:00", first_seen="2026-08-14T10:10:00+07:00"),
        _nom("BBB", eligible_from="2026-08-14T10:10:00+07:00", first_seen="2026-08-14T10:10:00+07:00"),
        _nom("DDD", eligible_from="2026-08-14T10:40:00+07:00", first_seen="2026-08-14T10:40:00+07:00"),
    ]
    out = route_candidates(noms, now=now)
    assert list(out["symbol"]) == ["AAA", "BBB", "CCC", "DDD"]
    assert UNIVERSE_CAP == LIVE_UNIVERSE_CAP == 50


def test_group_setup_survive_history_adapter_router():
    hist = _hist(
        _row("2026-08-14", "HPG", "BUY ELITE", group="PULL ĐẸP"),
        _row("2026-08-14", "VCB", "MUA NHỎ / ƯU TIÊN", group="MUA EARLY"),
        observed="2026-08-14 10:05:00",
    )
    now = _ts("2026-08-14 10:05:00")
    noms = nominations_from_buy_elite_history(hist, now=now)
    by_sym = {n.symbol: n for n in noms}
    assert by_sym["HPG"].candidate_reason == "BUY ELITE"
    assert by_sym["HPG"].group == "PULL ĐẸP"
    assert by_sym["HPG"].setup == ""
    assert by_sym["VCB"].candidate_reason == "MUA NHỎ / ƯU TIÊN"
    assert by_sym["VCB"].group == "MUA EARLY"
    report = build_routed_report(hist, now=now)
    routed_groups = {n.symbol: n.group for n in report.canonical}
    assert routed_groups == {"HPG": "PULL ĐẸP", "VCB": "MUA EARLY"}
    assert list(report.watchlist.columns) == WATCHLIST_COLUMNS
    assert "group" not in report.watchlist.columns
    assert "setup" not in report.watchlist.columns
    current = build_research_watchlist(hist, now=now)
    pd.testing.assert_frame_equal(
        current.reset_index(drop=True),
        report.watchlist.reset_index(drop=True),
        check_dtype=False,
    )
    assert encode_watchlist_text(current) == encode_watchlist_text(report.watchlist)


def test_group_is_not_inferred_from_candidate_reason():
    hist = _hist(_row("2026-08-14", "HPG", "BUY ELITE", group=""), observed="2026-08-14 10:05:00")
    hist = hist.drop(columns=["group"])
    now = _ts("2026-08-14 10:05:00")
    nom = nominations_from_buy_elite_history(hist, now=now)[0]
    assert nom.candidate_reason == "BUY ELITE"
    assert nom.group == ""
    assert nom.setup == ""
    report = build_routed_report(hist, now=now)
    assert report.canonical[0].group == ""
    assert report.canonical[0].setup == ""


def test_setup_is_not_manufactured_from_group():
    hist = _hist(_row("2026-08-14", "HPG", "BUY ELITE", group="CP MẠNH"), observed="2026-08-14 10:05:00")
    assert "setup" not in hist.columns
    nom = nominations_from_buy_elite_history(hist, now=_ts("2026-08-14 10:05:00"))[0]
    assert nom.group == "CP MẠNH"
    assert nom.setup == ""


def test_history_setup_column_is_passed_through_when_present():
    hist = _hist(_row("2026-08-14", "HPG", "BUY ELITE", group="PULL VỪA"), observed="2026-08-14 10:05:00")
    hist["setup"] = "PULL VỪA"
    nom = nominations_from_buy_elite_history(hist, now=_ts("2026-08-14 10:05:00"))[0]
    assert nom.group == "PULL VỪA"
    assert nom.setup == "PULL VỪA"
    assert nom.candidate_reason == "BUY ELITE"


def test_competing_nominations_keep_losing_provenance():
    now = _ts("2026-08-14 11:00:00")
    elite = _nom(
        "HPG",
        source=SRC_BUY_ELITE,
        first_seen="2026-08-14T10:05:00+07:00",
        group="PULL ĐẸP",
        reason="BUY ELITE",
        source_state="ACTIVE",
        source_reason="BUY ELITE",
    )
    rotation = _nom(
        "HPG",
        source=SRC_ROTATION,
        first_seen="2026-08-14T10:40:00+07:00",
        group="",
        setup="",
        reason="WATCH LOWER",
        source_state="WATCH",
        source_action="WATCH LOWER",
        source_reason="BELOW_LOWER",
    )
    both = frozenset({SRC_BUY_ELITE, SRC_ROTATION})
    a = route_report([rotation, elite], now=now, enabled_sources=both)
    b = route_report([elite, rotation], now=now, enabled_sources=both)
    assert a.canonical[0].source == SRC_BUY_ELITE
    assert b.canonical[0].source == SRC_BUY_ELITE
    assert a.canonical[0].group == "PULL ĐẸP"
    assert a.watchlist.iloc[0]["source"] == SRC_BUY_ELITE
    assert "group" not in a.watchlist.columns
    pd.testing.assert_frame_equal(a.watchlist.reset_index(drop=True), b.watchlist.reset_index(drop=True))

    def _by_source(report):
        prov = next(p for p in report.provenance if p.symbol == "HPG")
        return {n.source: n for n in prov.nominations}, prov

    a_map, a_prov = _by_source(a)
    b_map, b_prov = _by_source(b)
    assert a_prov.canonical.source == SRC_BUY_ELITE
    assert set(a_map) == {SRC_BUY_ELITE, SRC_ROTATION}
    assert set(b_map) == {SRC_BUY_ELITE, SRC_ROTATION}
    lost = a_map[SRC_ROTATION]
    assert lost.source == SRC_ROTATION
    assert lost.source_reason == "BELOW_LOWER"
    assert lost.source_state == "WATCH"
    assert lost.source_action == "WATCH LOWER"
    assert lost.candidate_first_seen_ts == "2026-08-14T10:40:00+07:00"
    assert lost.group == ""
    assert a_map[SRC_BUY_ELITE].group == "PULL ĐẸP"
    assert a_map[SRC_BUY_ELITE].candidate_first_seen_ts == "2026-08-14T10:05:00+07:00"
    assert a_prov.nominations[0].source == SRC_BUY_ELITE

