"""Remote live-shadow HTTP 404 is missing artifact, not EvidenceTransportError."""
from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.live_candidate_pxv_ui.read import load_panel_sources
from modules.live_candidate_pxv_ui.view import EVIDENCE_TRANSPORT_ERROR, build_panel
from modules.live_shadow_transport.artifact_get import (
    EvidenceTransportError,
    LiveShadowNotFound,
    get_live_evidence_text,
    get_live_shadow_bytes,
    get_live_status_text,
)
from modules.live_shadow_transport.contract import (
    ARTIFACT_EVIDENCE_PATH,
    ARTIFACT_STATUS_PATH,
    RUNNER_STOPPED,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime.fromisoformat("2026-09-10T16:00:00").replace(tzinfo=VN)
BASE = "http://artifact.test"


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


def _opener_by_code(codes: dict[str, int], bodies: dict[str, bytes] | None = None):
    bodies = bodies or {}

    def opener(req, timeout=20):
        url = req.full_url
        for path, code in codes.items():
            if url.endswith(path):
                if code == 200:
                    return _Resp(bodies.get(path, b""))
                raise _http_error(code, url)
        raise _http_error(500, url)

    return opener


def _remote_sources(*, ev_code: int, st_code: int, ev_body: bytes = b"", st_body: bytes = b"{}"):
    opener = _opener_by_code(
        {ARTIFACT_EVIDENCE_PATH: ev_code, ARTIFACT_STATUS_PATH: st_code},
        {ARTIFACT_EVIDENCE_PATH: ev_body, ARTIFACT_STATUS_PATH: st_body},
    )

    def ev():
        return get_live_evidence_text(base_url=BASE, token="t", opener=opener)

    def st():
        return get_live_status_text(base_url=BASE, token="t", opener=opener)

    return load_panel_sources(
        source_mode="remote",
        evidence_fetcher=ev,
        status_fetcher=st,
    )


def test_a_both_404_stopped_stale_not_transport_error():
    src = _remote_sources(ev_code=404, st_code=404)
    assert src["transport"]["error"] is None
    assert src["evidence"] == []
    assert src["status"] == {}
    p = build_panel(now=NOW, sources=src)
    assert p.runner["label"] == RUNNER_STOPPED
    assert p.runner["is_stale"] is True
    assert p.alert_eligible is False
    assert p.empty is True
    assert p.runner["label"] != EVIDENCE_TRANSPORT_ERROR
    assert src["transport"]["error"] != EVIDENCE_TRANSPORT_ERROR


def test_b_evidence_404_valid_status_no_synthetic_evidence():
    status_body = json.dumps(
        {"observed_at": "2026-09-10T15:00:00+07:00", "alert_eligible": False, "symbols": []}
    ).encode("utf-8")
    src = _remote_sources(ev_code=404, st_code=200, st_body=status_body)
    assert src["transport"]["error"] is None
    assert src["evidence"] == []
    assert src["status"].get("observed_at")
    p = build_panel(now=NOW, sources=src)
    assert p.alert_eligible is False
    assert all(not c.get("raw_evidence") for c in p.cards)
    assert p.runner["label"] != EVIDENCE_TRANSPORT_ERROR


def test_c_valid_evidence_status_404_no_transport_error():
    ev_line = (
        '{"symbol":"HPG","session":"2026-09-10","bar_ts":"2026-09-10T14:10:00+07:00",'
        '"observed_at":"2026-09-10T14:12:00+07:00","raw_evidence":"NEUTRAL",'
        '"published_evidence":"NEUTRAL","chronology_legal":true,"alert_eligible":false}\n'
    ).encode("utf-8")
    src = _remote_sources(ev_code=200, st_code=404, ev_body=ev_line)
    assert src["transport"]["error"] is None
    assert src["status"] == {}
    assert len(src["evidence"]) == 1
    assert src["evidence"][0]["symbol"] == "HPG"
    p = build_panel(now=NOW, sources=src)
    assert p.alert_eligible is False
    assert p.runner["label"] == RUNNER_STOPPED
    assert p.runner["is_stale"] is True
    assert p.runner["label"] != EVIDENCE_TRANSPORT_ERROR


def test_d_http_401_is_transport_error():
    src = _remote_sources(ev_code=401, st_code=401)
    assert src["transport"]["error"] == EVIDENCE_TRANSPORT_ERROR
    p = build_panel(now=NOW, sources=src)
    assert p.runner["label"] == EVIDENCE_TRANSPORT_ERROR
    assert p.alert_eligible is False


def test_e_http_500_is_transport_error():
    src = _remote_sources(ev_code=500, st_code=500)
    assert src["transport"]["error"] == EVIDENCE_TRANSPORT_ERROR
    p = build_panel(now=NOW, sources=src)
    assert p.runner["label"] == EVIDENCE_TRANSPORT_ERROR


def test_f_timeout_network_is_transport_error():
    def opener(req, timeout=20):
        raise TimeoutError("timed out")

    def ev():
        return get_live_evidence_text(base_url=BASE, token="t", opener=opener)

    def st():
        return get_live_status_text(base_url=BASE, token="t", opener=opener)

    src = load_panel_sources(source_mode="remote", evidence_fetcher=ev, status_fetcher=st)
    assert src["transport"]["error"] == EVIDENCE_TRANSPORT_ERROR
    p = build_panel(now=NOW, sources=src)
    assert p.runner["label"] == EVIDENCE_TRANSPORT_ERROR


def test_g_remote_200_path_unchanged():
    ev_line = b'{"symbol":"HPG","raw_evidence":"NEUTRAL","alert_eligible":false}\n'
    st_body = b'{"observed_at":"2026-09-10T15:00:00+07:00","alert_eligible":false,"symbols":[]}'
    src = _remote_sources(ev_code=200, st_code=200, ev_body=ev_line, st_body=st_body)
    assert src["transport"]["error"] is None
    assert src["transport"]["evidence"] == "OK"
    assert src["transport"]["status"] == "OK"
    assert src["evidence"][0]["symbol"] == "HPG"
    assert src["status"]["observed_at"] == "2026-09-10T15:00:00+07:00"


def test_h_local_missing_files_unchanged(tmp_path: Path):
    src = load_panel_sources(
        source_mode="local",
        watchlist_path=tmp_path / "missing_watchlist.json",
        evidence_path=tmp_path / "missing_evidence.jsonl",
        status_path=tmp_path / "missing_status.json",
    )
    assert src["transport"]["mode"] == "local"
    assert src["transport"]["error"] is None
    assert src["evidence"] == []
    assert src["status"] == {}
    p = build_panel(now=NOW, sources=src)
    assert p.runner["label"] == RUNNER_STOPPED
    assert p.runner["is_stale"] is True
    assert p.alert_eligible is False


def test_http_403_is_transport_error_not_missing():
    src = _remote_sources(ev_code=403, st_code=403)
    assert src["transport"]["error"] == EVIDENCE_TRANSPORT_ERROR


def test_get_live_shadow_bytes_404_raises_not_found_not_transport():
    opener = _opener_by_code({ARTIFACT_EVIDENCE_PATH: 404})
    try:
        get_live_shadow_bytes(
            ARTIFACT_EVIDENCE_PATH, base_url=BASE, token="t", opener=opener
        )
        raise AssertionError("expected LiveShadowNotFound")
    except LiveShadowNotFound:
        pass
    except EvidenceTransportError as exc:
        raise AssertionError(f"404 must not be transport error: {exc}") from exc
