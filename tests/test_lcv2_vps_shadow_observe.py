"""VPS SHADOW observation plumbing: sidecar source, artifacts, Cloud GET."""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.intraday_memory.provider import MockProvider
from modules.live_camera_shadow.feed import LiveShadowFeed
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M,
)
from modules.live_candidate_v2_action.sidecar_source import (
    REASON_ABSENT,
    REASON_STALE_SESSION,
    SOURCE_GITHUB,
    accept_sidecar_document,
    resolve_published_v2_sidecar,
)
from modules.live_candidate_v2_action.ui import (
    LOCAL_UNAVAILABLE_MESSAGE,
    STALE_MESSAGE,
    accept_shadow_state_document,
    load_accepted_shadow_state,
    render_v2_shadow_action_panel,
    shadow_waiting_for_eligible_bar,
)
from modules.live_candidate_v2_camera.contract import GITHUB_V2_SIDECAR_PATH
from modules.live_candidate_v2_camera.github_bus import STATUS_NOT_FOUND, V2FetchResult
from modules.live_candidate_v2_camera.observe import pxv_implies_buy
from modules.live_shadow_transport.artifact_get import (
    EvidenceTransportError,
    get_v2_action_state_text,
)
from modules.live_shadow_transport.contract import ARTIFACT_V2_ACTION_STATE_PATH
from modules.live_shadow_transport.shadow_store import publish_shadow_artifacts

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
SESSION = "2026-09-19"
NOW = datetime.fromisoformat("2026-09-19T10:05:00").replace(tzinfo=VN)
BASE = "http://artifact.test"


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _row(symbol="HPG", session=SESSION) -> dict:
    return {
        "symbol": symbol,
        "session": session,
        "candidate_first_seen_ts": f"{session}T09:00:00+07:00",
        "eligible_from": f"{session}T09:00:00+07:00",
        "source": "brain_a_scan_setup",
        "setup": "PULL ĐẸP",
        "group": "PULL ĐẸP",
        "observation_intent": "WATCH_PULL",
        "observation_reference": "EMA9",
        "price_at_first_seen": 27100,
        "ema9_at_first_seen": 27.1,
        "breakout_ref_at_first_seen": None,
        "source_action": "MUA PULL ĐẸP",
        "source_reason": "Pull sát EMA9, OBV còn xanh",
        "elite_buy_grade": "",
        "provenance": ["brain_a_scan_setup"],
        "candidate_is_buy": False,
        "alert_eligible": False,
    }


def _sidecar(session=SESSION, rows=None, **extra) -> dict:
    rows = rows or [_row(session=session)]
    ledger = [
        {
            "session": session,
            "symbol": r["symbol"],
            "candidate_first_seen_ts": r["candidate_first_seen_ts"],
            "price_at_first_seen": r.get("price_at_first_seen"),
            "ema9_at_first_seen": r.get("ema9_at_first_seen"),
            "breakout_ref_at_first_seen": r.get("breakout_ref_at_first_seen"),
        }
        for r in rows
    ]
    doc = {
        "schema": "live_candidate_v2_camera_sidecar_v1",
        "session": session,
        "generated_at": f"{session}T09:05:00+07:00",
        "candidate_is_buy": False,
        "alert_eligible": False,
        "freeze_ledger": ledger,
        "rows": rows,
    }
    doc.update(extra)
    return doc


def _fetch(doc=None, *, ok=True, status="OK_ROWS", error=""):
    return lambda: V2FetchResult(
        ok=ok,
        status=status,
        document=doc,
        n_rows=len((doc or {}).get("rows") or []),
        error=error,
    )


class _Resp:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *_a) -> bool:
        return False


def _http_error(code: int, url: str = BASE + "/x") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "err", hdrs=None, fp=io.BytesIO(b""))


class _St:
    def __init__(self) -> None:
        self.markdowns = []
        self.captions = []
        self.tables = []

    def markdown(self, msg, **k):
        self.markdowns.append(str(msg))

    def caption(self, msg, **k):
        self.captions.append(str(msg))

    def dataframe(self, data, **k):
        self.tables.append(data)


def test_permissions_remain_false():
    assert CANDIDATE_IS_BUY is False
    assert PXV_IMPLIES_BUY is False
    assert ALERT_ELIGIBLE is False
    assert pxv_implies_buy("STRENGTHEN") is False


def test_github_sidecar_current_session_only():
    doc = _sidecar(rows=[_row("HPG"), _row("SSI", session="2026-09-18")])
    resolved = resolve_published_v2_sidecar(
        session=SESSION,
        source=SOURCE_GITHUB,
        fetcher=_fetch(doc),
    )
    assert resolved.ok is True
    assert [r["symbol"] for r in resolved.rows] == ["HPG"]
    assert resolved.source == SOURCE_GITHUB
    assert resolved.detail == GITHUB_V2_SIDECAR_PATH


def test_stale_session_sidecar_fail_closed():
    resolved = resolve_published_v2_sidecar(
        session=SESSION,
        source=SOURCE_GITHUB,
        fetcher=_fetch(_sidecar(session="2026-09-18")),
    )
    assert resolved.ok is False
    assert resolved.rows == []
    assert resolved.reason == REASON_STALE_SESSION


def test_absent_sidecar_fail_closed_not_elite():
    resolved = resolve_published_v2_sidecar(
        session=SESSION,
        source=SOURCE_GITHUB,
        fetcher=_fetch(ok=False, status=STATUS_NOT_FOUND, error="404"),
    )
    assert resolved.ok is False
    assert resolved.rows == []
    assert resolved.reason == REASON_ABSENT


def test_buy_flags_on_sidecar_rejected():
    doc = _sidecar()
    doc["candidate_is_buy"] = True
    accepted = accept_sidecar_document(doc, session=SESSION, source=SOURCE_GITHUB)
    assert accepted.ok is False
    assert accepted.rows == []


def test_feed_github_union_does_not_flip_elite_evidence(tmp_path):
    elite = [
        {
            "session": SESSION,
            "symbol": "HPG",
            "candidate_first_seen_ts": f"{SESSION}T08:00:00+07:00",
            "candidate_updated_ts": f"{SESSION}T08:00:00+07:00",
            "candidate_reason": "BUY ELITE",
            "source": "buy_elite_learning_history",
            "status": "ACTIVE",
            "eligible_from": f"{SESSION}T08:00:00+07:00",
        }
    ]
    feed = LiveShadowFeed(
        provider=MockProvider({}),
        out_dir=tmp_path,
        now_fn=lambda: NOW,
        v2_sidecar_source=SOURCE_GITHUB,
        v2_sidecar_fetcher=_fetch(_sidecar(rows=[_row("VCI")])),
    )
    status = feed.run_cycle(elite)
    assert status["v2_sidecar"]["ok"] is True
    assert status["v2_union"]["n_v2"] == 1
    assert status["v2_union"]["n_elite"] == 1
    assert "VCI" in status["v2_union"].get("overlap_symbols", []) or status["v2_union"]["n_merged"] == 2
    assert status["candidate_is_buy"] is False
    assert status["pxv_implies_buy"] is False
    assert status["alert_eligible"] is False


def test_feed_without_source_does_not_use_elite_as_v2(tmp_path):
    elite = [
        {
            "session": SESSION,
            "symbol": "HPG",
            "candidate_first_seen_ts": f"{SESSION}T08:00:00+07:00",
            "candidate_updated_ts": f"{SESSION}T08:00:00+07:00",
            "candidate_reason": "BUY ELITE",
            "source": "buy_elite_learning_history",
            "status": "ACTIVE",
            "eligible_from": f"{SESSION}T08:00:00+07:00",
        }
    ]
    feed = LiveShadowFeed(
        provider=MockProvider({}),
        out_dir=tmp_path,
        now_fn=lambda: NOW,
    )
    status = feed.run_cycle(elite)
    assert status["v2_sidecar"]["reason"] == "SIDECAR_ABSENT"
    assert status["v2_union"]["n_v2"] == 0
    assert feed._v2_action_items == []


def test_file_sidecar_wrong_session_empty(tmp_path):
    path = tmp_path / "camera_sidecar.json"
    path.write_text(json.dumps(_sidecar(session="2026-09-01")), encoding="utf-8")
    resolved = resolve_published_v2_sidecar(session=SESSION, source="file", path=path)
    assert resolved.ok is False
    assert resolved.rows == []
    assert resolved.reason == REASON_STALE_SESSION


def test_publish_elite_survives_missing_v2(tmp_path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    (src / "live_evidence.jsonl").write_text("{}\n", encoding="utf-8")
    (src / "live_shadow_status.json").write_text("{}\n", encoding="utf-8")
    pub = publish_shadow_artifacts(src, dest)
    assert pub["ok"] is True
    assert pub["copied"] == ["live_evidence.jsonl", "live_shadow_status.json"]
    assert pub["v2_status"] == "ABSENT"
    assert (dest / "live_evidence.jsonl").exists()
    assert not (dest / "v2_action_state.json").exists()


def test_publish_copies_v2_state_atomically(tmp_path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    (src / "live_evidence.jsonl").write_text("{}\n", encoding="utf-8")
    (src / "live_shadow_status.json").write_text("{}\n", encoding="utf-8")
    v2 = src / "v2_action"
    v2.mkdir()
    state = {"schema": "live_candidate_v2_action_state.v1", "session": SESSION, "candidate_is_buy": False}
    (v2 / "v2_action_state.json").write_text(json.dumps(state), encoding="utf-8")
    (v2 / "v2_action_evidence.jsonl").write_text("{}\n", encoding="utf-8")
    pub = publish_shadow_artifacts(src, dest)
    assert pub["ok"] is True
    assert pub["v2_status"] == "OK"
    assert "v2_action_state.json" in pub["v2_copied"]
    written = json.loads((dest / "v2_action_state.json").read_text(encoding="utf-8"))
    assert written["session"] == SESSION
    assert written["candidate_is_buy"] is False


def test_artifact_server_and_get_allow_v2_state():
    server_src = (REPO / "modules" / "edge_research" / "artifact_server.py").read_text(encoding="utf-8")
    assert ARTIFACT_V2_ACTION_STATE_PATH in server_src
    assert '"v2_action_state.json"' in server_src

    def opener(req, timeout=20):
        if req.full_url.endswith(ARTIFACT_V2_ACTION_STATE_PATH):
            return _Resp(b'{"session":"2026-09-19","candidate_is_buy":false}\n')
        raise _http_error(404, req.full_url)

    text = get_v2_action_state_text(base_url=BASE, token="t", opener=opener)
    assert "2026-09-19" in text

    def bad(req, timeout=20):
        raise _http_error(404, req.full_url)

    try:
        get_v2_action_state_text(base_url=BASE, token="t", opener=bad)
        raise AssertionError("404 must not invent state")
    except Exception as exc:
        assert exc.__class__.__name__ == "LiveShadowNotFound"


def test_get_rejects_unknown_path():
    try:
        from modules.live_shadow_transport.artifact_get import get_live_shadow_bytes

        get_live_shadow_bytes("/current/bundle.tar.gz", base_url=BASE, token="t")
        raise AssertionError("bundle must stay disallowed")
    except EvidenceTransportError as exc:
        assert "disallowed" in str(exc)


def test_ui_remote_fresh_state_and_waiting_caption():
    payload = {
        "schema": "live_candidate_v2_action_state.v1",
        "session": SESSION,
        "observed_at": NOW.isoformat(),
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": [{"symbol": "HPG", "shadow_action": "NOMINATED", "n_legal_bars": 0}],
    }
    doc, reason = load_accepted_shadow_state(
        source_mode="remote",
        now=NOW,
        fetcher=lambda: json.dumps(payload),
    )
    assert reason == "OK"
    assert doc is not None
    assert shadow_waiting_for_eligible_bar(doc) is True
    st = _St()
    render_v2_shadow_action_panel(doc, st_module=st, now=NOW, source_mode="remote")
    assert any(WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M in c for c in st.captions)


def test_ui_rejects_stale_and_wrong_session():
    stale = {
        "session": SESSION,
        "observed_at": (NOW - timedelta(minutes=20)).isoformat(),
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "rows": [{"symbol": "HPG", "n_legal_bars": 2}],
    }
    doc, reason = accept_shadow_state_document(stale, now=NOW)
    assert doc is None
    assert reason == "STALE_OBSERVED_AT"
    wrong = dict(stale, session="2026-09-18", observed_at=NOW.isoformat())
    doc, reason = accept_shadow_state_document(wrong, now=NOW)
    assert doc is None
    assert reason == "STALE_SESSION"
    st = _St()
    render_v2_shadow_action_panel(None, st_module=st, now=NOW, source_mode="remote", fetcher=lambda: json.dumps(stale))
    assert STALE_MESSAGE in st.captions
    assert not st.tables


def test_ui_local_absent_is_honest(tmp_path):
    st = _St()
    render_v2_shadow_action_panel(None, st_module=st, artifact_dir=tmp_path, now=NOW)
    assert LOCAL_UNAVAILABLE_MESSAGE in st.captions


def test_runner_does_not_default_to_repo_sidecar():
    src = (REPO / "scripts" / "run_live_camera_shadow.py").read_text(encoding="utf-8")
    assert "DEFAULT_SIDECAR_RELPATH" not in src
    assert "SOURCE_GITHUB" in src
    assert "MRBOT_V2_SIDECAR_SOURCE" in src or "ENV_V2_SIDECAR_SOURCE" in src


def test_vps_install_allowlist_is_narrow():
    src = (REPO / "scripts" / "vps_install_live_camera_consumer.sh").read_text(encoding="utf-8")
    assert "modules/live_candidate_v2_action/sidecar_source.py" in src
    assert "modules/live_candidate_v2_action/observe_bars.py" in src
    assert "modules/live_candidate_v2_camera/github_bus.py" in src
    assert "modules/live_candidate_v2_camera/feed_pass.py" in src
    assert "modules/live_candidate_v2_nomination/contract.py" in src
    assert "modules/live_candidate_v2_nomination/intent.py" in src
    assert "rsync -a ./" not in src
    assert "cp -a \"$ISO/.\"" not in src


def test_feed_lazy_import_stays_off_replay():
    src = (REPO / "modules" / "live_camera_shadow" / "feed.py").read_text(encoding="utf-8")
    assert "live_candidate_v2_action.observe_bars import interpret_legal_history" in src
    assert "live_candidate_v2_action.replay import interpret_legal_history" not in src
    init = (REPO / "modules" / "live_candidate_v2_action" / "__init__.py").read_text(encoding="utf-8")
    assert init.index("def __getattr__") < init.index("from modules.live_candidate_v2_action.replay import")


def _pinned_vps_relpaths() -> list[str]:
    import re

    text = (REPO / "scripts" / "vps_install_live_camera_consumer.sh").read_text(encoding="utf-8")
    out: list[str] = []
    for block in ("FILES", "LATER_LIVE_ONLY"):
        match = re.search(rf"{block}=\((.*?)\)", text, re.S)
        assert match, block
        out.extend(re.findall(r'"([^"]+)"', match.group(1)))
    assert out
    return out


def test_isolated_vps_allowlist_imports_live_path(tmp_path):
    """Reproduce #168: import from the pinned tree, not the full repo."""
    import shutil
    import sys

    dest = tmp_path / "opt-mrbot-live-shadow"
    for rel in _pinned_vps_relpaths():
        src = REPO / rel
        assert src.is_file(), rel
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)

    assert not (dest / "modules" / "intraday_memory" / "storage.py").exists()
    assert not (dest / "modules" / "candidate_router").exists()
    assert not (dest / "modules" / "live_candidate_pxv_ui").exists()

    saved_path = list(sys.path)
    doomed = [k for k in sys.modules if k == "modules" or k.startswith("modules.")]
    saved_mods = {k: sys.modules[k] for k in doomed}
    try:
        for k in doomed:
            del sys.modules[k]
        sys.path = [str(dest)] + [p for p in saved_path if Path(p).resolve() != REPO.resolve()]
        from modules.live_camera_shadow.feed import LiveShadowFeed
        from modules.live_candidate_v2_action.contract import (
            ALERT_ELIGIBLE,
            CANDIDATE_IS_BUY,
            PXV_IMPLIES_BUY,
        )
        from modules.live_candidate_v2_action.sidecar_source import resolve_published_v2_sidecar
        from modules.live_candidate_v2_action.state import evaluate_shadow_action
        from modules.live_candidate_v2_camera.contract import GITHUB_V2_SIDECAR_PATH
        from modules.live_candidate_v2_camera.github_bus import fetch_v2_sidecar
        from modules.live_shadow_transport.artifact_get import get_v2_action_state_text
        from modules.live_shadow_transport.shadow_store import publish_shadow_artifacts

        assert LiveShadowFeed is not None
        assert resolve_published_v2_sidecar is not None
        assert evaluate_shadow_action is not None
        assert fetch_v2_sidecar is not None
        assert get_v2_action_state_text is not None
        assert publish_shadow_artifacts is not None
        assert GITHUB_V2_SIDECAR_PATH == "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"
        assert CANDIDATE_IS_BUY is False
        assert PXV_IMPLIES_BUY is False
        assert ALERT_ELIGIBLE is False
        assert "modules.intraday_memory.storage" not in sys.modules
        assert "modules.live_candidate_v2_action.replay" not in sys.modules
        assert "modules.live_candidate_v2_camera.sidecar" not in sys.modules
        assert "modules.live_candidate_v2_camera.cloud_hook" not in sys.modules
    finally:
        for k in list(sys.modules):
            if k == "modules" or k.startswith("modules."):
                del sys.modules[k]
        sys.path[:] = saved_path
        sys.modules.update(saved_mods)
