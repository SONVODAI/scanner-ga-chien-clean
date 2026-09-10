"""Deterministic Cloud ↔ VPS live-shadow transport. No production, no session start."""
from __future__ import annotations

import json
import socket
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.edge_research.artifact_server import ArtifactServer, ArtifactServerConfig
from modules.intraday_memory.provider import MockProvider
from modules.live_candidate.persist import apply_immutable_first_seen
from modules.live_candidate_pxv_ui.html import render_html
from modules.live_candidate_pxv_ui.read import load_panel_sources
from modules.live_candidate_pxv_ui.view import (
    EVIDENCE_TRANSPORT_BANNER,
    EMPTY_MESSAGE,
    NOT_LEGAL_NOTE,
    STALE_BANNER,
    WATCHLIST_TRANSPORT_BANNER,
    build_panel,
)
from modules.live_camera_shadow.feed import LiveShadowFeed
from modules.live_shadow_transport.artifact_get import (
    EvidenceTransportError,
    get_live_evidence_text,
    get_live_status_text,
)
from modules.live_shadow_transport.contract import (
    ARTIFACT_EVIDENCE_PATH,
    ARTIFACT_STATUS_PATH,
    EVIDENCE_TRANSPORT_ERROR,
    FORBIDDEN_CAMERA_ARCHIVE,
    GITHUB_WATCHLIST_PATH,
    RUNNER_STALE,
    VPS_SHADOW_STORE,
    WATCHLIST_TRANSPORT_ERROR,
)
from modules.live_shadow_transport.watchlist_bus import (
    WatchlistFetchResult,
    persist_and_publish_research_watchlist,
    publish_watchlist_bytes,
)
from tests.test_live_camera_shadow import _grid

VN = ZoneInfo("Asia/Ho_Chi_Minh")
TOKEN = "e2e-live-shadow-token"
FIRST_SEEN = "2026-08-14T10:05:00+07:00"


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _row(day: str, symbol: str, conclusion: str) -> dict:
    return {
        "date": day,
        "time": "10:05:00",
        "symbol": symbol,
        "conclusion": conclusion,
        "winprob": 80.0,
        "elite_score": 70.0,
        "group": "PULL VỪA",
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class MemoryGitHub:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.fail = False
        self.writes = 0

    def write(self, path: str, text: str, message: str) -> str:
        self.writes += 1
        if self.fail:
            return "GITHUB_ERROR"
        self.files[path] = text
        return "GITHUB_OK"

    def fetch(self) -> WatchlistFetchResult:
        if self.fail:
            return WatchlistFetchResult(ok=False, rows=[], raw_text="", error="github HTTP 503")
        text = self.files.get(GITHUB_WATCHLIST_PATH)
        if text is None:
            return WatchlistFetchResult(ok=False, rows=[], raw_text="", error="github HTTP 404")
        return WatchlistFetchResult(ok=True, rows=json.loads(text), raw_text=text, error=None)


def _start_artifact(tmp_path: Path, store: Path) -> tuple[ArtifactServer, str]:
    port = _free_port()
    config = ArtifactServerConfig(
        storage_root=tmp_path / "edge_durable",
        token=TOKEN,
        host="127.0.0.1",
        port=port,
        live_shadow_root=store,
    )
    server = ArtifactServer(config)
    server.start(blocking=False)
    return server, server.base_url


def test_e2e_timestamp_identity_cloud_to_vps_to_cloud_ui(tmp_path: Path):
    """Candidate first-seen on Cloud → GitHub snapshot → VPS → artifact GET → UI."""
    bus = MemoryGitHub()
    now = _ts("2026-08-14 10:05:00")
    hist = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")]),
        observed_at=now,
    )
    assert hist.iloc[0]["candidate_first_seen_ts"] == FIRST_SEEN

    wl_dir = tmp_path / "cloud_watchlist"
    path, pub = persist_and_publish_research_watchlist(
        hist,
        observed_at=now,
        out_dir=wl_dir,
        publisher=bus.write,
    )
    assert pub.ok is True
    published_text = bus.files[GITHUB_WATCHLIST_PATH]
    assert published_text == path.read_text(encoding="utf-8")
    published = json.loads(published_text)
    assert published[0]["candidate_first_seen_ts"] == FIRST_SEEN
    assert published[0]["eligible_from"]
    first_seen = published[0]["candidate_first_seen_ts"]
    eligible_from = published[0]["eligible_from"]
    updated = published[0]["candidate_updated_ts"]
    session = published[0]["session"]
    assert "BUY ELITE" in (published[0].get("candidate_reason") or published[0].get("status") or "")

    stale_local = tmp_path / "vps_stale_watchlist.json"
    stale_local.write_text(
        json.dumps([{"symbol": "FAKE", "candidate_first_seen_ts": "1999-01-01T00:00:00+07:00",
                     "eligible_from": "1999-01-01T00:00:00+07:00"}], ensure_ascii=False),
        encoding="utf-8",
    )

    store = tmp_path / "live_pxv_shadow"
    assert str(store) != FORBIDDEN_CAMERA_ARCHIVE
    assert VPS_SHADOW_STORE == "/var/lib/mrbot/live_pxv_shadow"
    out = tmp_path / "shadow_work"
    day = "2026-08-14"
    feed = LiveShadowFeed(
        provider=MockProvider({("HPG", day): _grid(day, "09:15", 20)}),
        out_dir=out,
        now_fn=lambda: _ts("2026-08-14 10:21:00"),
        archive_root=tmp_path / "camera_must_stay_empty",
        watchlist_path=stale_local,
        watchlist_source="github",
        watchlist_fetcher=bus.fetch,
        shadow_store_dir=store,
    )
    status = feed.run_cycle()
    assert status["watchlist_transport"] == "OK"
    assert status["alert_eligible"] is False
    ev = feed.read_evidence()
    assert ev, "legal completed 5m evidence must be generated"
    assert all(row["chronology_legal"] is True for row in ev)
    assert ev[0]["candidate_first_seen_ts"] == first_seen
    assert ev[0]["eligible_from"] == eligible_from
    assert ev[0]["session"] == session
    assert ev[0]["alert_eligible"] is False
    assert (tmp_path / "camera_must_stay_empty").exists() is False or not any(
        (tmp_path / "camera_must_stay_empty").rglob("*")
    )

    store_ev = (store / "live_evidence.jsonl").read_text(encoding="utf-8")
    store_st = (store / "live_shadow_status.json").read_text(encoding="utf-8")
    assert store_ev == (out / "live_evidence.jsonl").read_text(encoding="utf-8")
    assert json.loads(store_st)["watchlist_transport"] == "OK"

    server, base = _start_artifact(tmp_path, store)
    try:
        got_ev = get_live_evidence_text(base_url=base, token=TOKEN)
        got_st = get_live_status_text(base_url=base, token=TOKEN)
        assert got_ev == store_ev
        remote_status = json.loads(got_st)
        assert remote_status["observed_at"] == status["observed_at"]

        src = load_panel_sources(
            watchlist_path=path,
            source_mode="remote",
            evidence_fetcher=lambda: get_live_evidence_text(base_url=base, token=TOKEN),
            status_fetcher=lambda: get_live_status_text(base_url=base, token=TOKEN),
        )
        assert src["transport"]["error"] is None
        assert src["evidence"][0]["candidate_first_seen_ts"] == first_seen
        assert src["evidence"][0]["eligible_from"] == eligible_from
        assert src["evidence"][0]["bar_ts"] == ev[0]["bar_ts"]
        assert src["evidence"][0]["observed_at"] == ev[0]["observed_at"]
        panel = build_panel(now=_ts("2026-08-14 10:22:00"), sources=src)
        assert panel.alert_eligible is False
        assert panel.provider_called is False
        assert not panel.empty
        card = panel.cards[0]
        assert card["symbol"] == "HPG"
        assert card["candidate_first_seen_ts"] == first_seen
        assert card["eligible_from"] == eligible_from
        assert card["raw_evidence"]
        assert card["published_evidence"]
        assert card["chronology_legal"] is True
        assert panel.runner["label"] == "LIVE"
        html = render_html(panel)
        assert "HPG" in html
        assert "PUBLISHED" in html
        assert first_seen[:16] in html or card["candidate_first_seen_hm"] in html
    finally:
        server.stop()

    assert published[0]["candidate_updated_ts"] == updated
    assert ARTIFACT_EVIDENCE_PATH.endswith("live_evidence.jsonl")
    assert ARTIFACT_STATUS_PATH.endswith("live_shadow_status.json")


def test_empty_candidate_published_and_rendered(tmp_path: Path):
    bus = MemoryGitHub()
    path, pub = persist_and_publish_research_watchlist(
        pd.DataFrame(),
        observed_at=_ts("2026-08-14 10:05:00"),
        out_dir=tmp_path / "empty_wl",
        publisher=bus.write,
    )
    assert pub.ok is True
    assert json.loads(bus.files[GITHUB_WATCHLIST_PATH]) == []
    assert path.read_text(encoding="utf-8") == bus.files[GITHUB_WATCHLIST_PATH]

    store = tmp_path / "store"
    feed = LiveShadowFeed(
        provider=MockProvider({}),
        out_dir=tmp_path / "out",
        now_fn=lambda: _ts("2026-08-14 10:21:00"),
        watchlist_source="github",
        watchlist_fetcher=bus.fetch,
        shadow_store_dir=store,
    )
    st = feed.run_cycle()
    assert st["watchlist_transport"] == "OK"
    assert st["n_evidence"] == 0
    assert feed.read_evidence() == []
    src = load_panel_sources(
        watchlist_path=path,
        source_mode="local",
        evidence_path=tmp_path / "out" / "live_evidence.jsonl",
        status_path=tmp_path / "out" / "live_shadow_status.json",
    )
    panel = build_panel(now=_ts("2026-08-14 10:22:00"), sources=src)
    assert panel.empty is True
    assert panel.empty_message == EMPTY_MESSAGE
    assert panel.alert_eligible is False


def test_watchlist_transport_failure_no_stale_fallback(tmp_path: Path):
    bus = MemoryGitHub()
    bus.fail = True
    stale = tmp_path / "stale.json"
    stale.write_text(
        json.dumps([{
            "session": "2026-08-14",
            "symbol": "HPG",
            "candidate_first_seen_ts": FIRST_SEEN,
            "eligible_from": FIRST_SEEN,
            "candidate_reason": "BUY ELITE",
            "status": "ACTIVE",
        }], ensure_ascii=False),
        encoding="utf-8",
    )
    feed = LiveShadowFeed(
        provider=MockProvider({("HPG", "2026-08-14"): _grid("2026-08-14", "09:15", 12)}),
        out_dir=tmp_path / "out",
        now_fn=lambda: _ts("2026-08-14 10:21:00"),
        watchlist_path=stale,
        watchlist_source="github",
        watchlist_fetcher=bus.fetch,
        shadow_store_dir=tmp_path / "store",
    )
    st = feed.run_cycle()
    assert st["watchlist_transport"] == WATCHLIST_TRANSPORT_ERROR
    assert feed.read_evidence() == []
    assert all(row.get("symbol") != "HPG" for row in st.get("symbols") or [])
    panel = build_panel(
        now=_ts("2026-08-14 10:22:00"),
        sources={"watchlist": [], "evidence": [], "status": st, "transport": {}},
    )
    assert panel.runner["label"] == WATCHLIST_TRANSPORT_ERROR
    assert WATCHLIST_TRANSPORT_BANNER in panel.runner["banner"]
    assert panel.empty is True


def test_stale_evidence_not_shown_as_live(tmp_path: Path):
    src = {
        "watchlist": [{
            "symbol": "HPG",
            "candidate_reason": "BUY ELITE",
            "candidate_first_seen_ts": FIRST_SEEN,
            "eligible_from": FIRST_SEEN,
        }],
        "evidence": [{
            "symbol": "HPG",
            "bar_ts": "2026-08-14T10:15:00+07:00",
            "observed_at": "2026-08-14T10:16:00+07:00",
            "candidate_first_seen_ts": FIRST_SEEN,
            "eligible_from": FIRST_SEEN,
            "raw_evidence": "STRENGTHEN",
            "published_evidence": "STRENGTHEN",
            "chronology_legal": True,
            "data_state": "QUALIFIED",
            "alert_eligible": False,
        }],
        "status": {
            "observed_at": "2026-08-14T10:16:00+07:00",
            "alert_eligible": False,
            "symbols": [{"symbol": "HPG", "status": "OK"}],
        },
        "transport": {"error": None},
    }
    panel = build_panel(now=_ts("2026-08-14 10:30:00"), sources=src)
    assert panel.runner["label"] == RUNNER_STALE
    assert panel.runner["is_live"] is False
    assert panel.cards[0]["freshness"] == RUNNER_STALE
    assert STALE_BANNER in panel.runner["banner"]
    html = render_html(panel)
    assert "NOT current" in html


def test_artifact_get_failure_no_synthetic_pxv(tmp_path: Path):
    wl = tmp_path / "dynamic_watchlist.json"
    wl.write_text(
        json.dumps([{
            "symbol": "HPG",
            "candidate_reason": "BUY ELITE",
            "candidate_first_seen_ts": FIRST_SEEN,
            "eligible_from": FIRST_SEEN,
        }], ensure_ascii=False),
        encoding="utf-8",
    )
    local_ev = tmp_path / "stale_local" / "live_evidence.jsonl"
    local_ev.parent.mkdir()
    local_ev.write_text(
        json.dumps({
            "symbol": "HPG",
            "raw_evidence": "STRENGTHEN",
            "published_evidence": "STRENGTHEN",
            "chronology_legal": True,
            "bar_ts": "2026-08-14T10:15:00+07:00",
            "observed_at": "2026-08-14T10:16:00+07:00",
        }) + "\n",
        encoding="utf-8",
    )

    def boom() -> str:
        raise EvidenceTransportError("artifact HTTP 503")

    src = load_panel_sources(
        watchlist_path=wl,
        evidence_path=local_ev,
        source_mode="remote",
        evidence_fetcher=boom,
        status_fetcher=boom,
    )
    assert src["transport"]["error"] == EVIDENCE_TRANSPORT_ERROR
    assert src["evidence"] == []
    panel = build_panel(now=_ts("2026-08-14 10:22:00"), sources=src)
    assert panel.runner["label"] == EVIDENCE_TRANSPORT_ERROR
    assert EVIDENCE_TRANSPORT_BANNER in panel.runner["banner"]
    assert panel.cards[0]["published_evidence"] == ""
    assert panel.cards[0]["raw_evidence"] == ""
    assert panel.alert_eligible is False


def test_chronology_illegal_and_alert_eligible_false():
    src = {
        "watchlist": [{
            "symbol": "HPG",
            "candidate_reason": "BUY ELITE",
            "candidate_first_seen_ts": FIRST_SEEN,
            "eligible_from": FIRST_SEEN,
        }],
        "evidence": [{
            "symbol": "HPG",
            "bar_ts": "2026-08-14T09:00:00+07:00",
            "observed_at": "2026-08-14T10:16:00+07:00",
            "raw_evidence": "STRENGTHEN",
            "published_evidence": "STRENGTHEN",
            "chronology_legal": False,
            "alert_eligible": True,
        }],
        "status": {
            "observed_at": "2026-08-14T10:16:00+07:00",
            "alert_eligible": False,
            "symbols": [{"symbol": "HPG", "status": "OK"}],
        },
    }
    panel = build_panel(now=_ts("2026-08-14 10:17:00"), sources=src)
    assert panel.cards[0]["chronology_legal"] is False
    assert panel.cards[0]["published_evidence"] == ""
    assert NOT_LEGAL_NOTE in panel.cards[0]["explanation"]
    assert panel.alert_eligible is False
    assert panel.cards[0]["alert_eligible"] is False


def test_watchlist_publish_failure_is_explicit(tmp_path: Path):
    bus = MemoryGitHub()
    bus.fail = True
    hist = apply_immutable_first_seen(
        pd.DataFrame(),
        pd.DataFrame([_row("2026-08-14", "HPG", "BUY ELITE")]),
        observed_at=_ts("2026-08-14 10:05:00"),
    )
    path, pub = persist_and_publish_research_watchlist(
        hist,
        observed_at=_ts("2026-08-14 10:05:00"),
        out_dir=tmp_path,
        publisher=bus.write,
    )
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))[0]["candidate_first_seen_ts"] == FIRST_SEEN
    assert pub.ok is False
    assert pub.status == WATCHLIST_TRANSPORT_ERROR
    assert GITHUB_WATCHLIST_PATH not in bus.files


def test_publish_bytes_are_not_rebuilt():
    raw = '[{"symbol":"HPG","candidate_first_seen_ts":"2026-08-14T10:05:00+07:00"}]'
    captured: dict[str, str] = {}

    def writer(path: str, text: str, message: str) -> str:
        captured["text"] = text
        return "GITHUB_OK"

    result = publish_watchlist_bytes(raw, writer)
    assert result.ok is True
    assert captured["text"] == raw


def test_artifact_live_shadow_get_only_and_not_edge_bundle(tmp_path: Path):
    import urllib.error
    import urllib.request

    store = tmp_path / "live_pxv_shadow"
    store.mkdir()
    store.joinpath("live_evidence.jsonl").write_text('{"symbol":"HPG"}\n', encoding="utf-8")
    store.joinpath("live_shadow_status.json").write_text('{"observed_at":"x"}\n', encoding="utf-8")
    server, base = _start_artifact(tmp_path, store)
    try:
        ev = get_live_evidence_text(base_url=base, token=TOKEN)
        assert ev == '{"symbol":"HPG"}\n'
        req = urllib.request.Request(
            f"{base}{ARTIFACT_EVIDENCE_PATH}",
            data=b"nope",
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "text/plain"},
            method="PUT",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("PUT must not succeed")
        except urllib.error.HTTPError as exc:
            assert exc.code == 405
        bad = urllib.request.Request(
            f"{base}/current/bundle.tar.gz",
            headers={"Authorization": f"Bearer {TOKEN}"},
            method="GET",
        )
        try:
            urllib.request.urlopen(bad, timeout=10)
            raise AssertionError("bundle must be absent")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.stop()
