"""Rotation Watch Cloud←VPS transport. Isolated from Candidate / Edge semantics."""

from __future__ import annotations

import ast
import inspect
import json
import socket
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.live_shadow_transport.artifact_get import get_live_shadow_bytes
from modules.live_shadow_transport.contract import (
    ARTIFACT_EVIDENCE_PATH as SHADOW_EVIDENCE_PATH,
    ARTIFACT_STATUS_PATH as SHADOW_STATUS_PATH,
)
from modules.rotation_watch.artifact_get import (
    RotationTransportError,
    get_rotation_bytes,
)
from modules.rotation_watch.constants import (
    ARTIFACT_BOARD_PATH,
    ARTIFACT_STATUS_PATH as ROTATION_STATUS_PATH,
    BOARD_NAME,
    SCHEMA_BOARD,
    SCHEMA_STATUS,
    STATUS_NAME,
    ST_BUY_READY,
    ST_DATA_UNCERTAIN,
    ST_LOWER_ZONE,
    ST_SELL_READY,
    TRANSPORT_ERROR,
    VPS_ROTATION_STORE,
)
from modules.rotation_watch.publish import ALLOWED_ROTATION_FILES, publish_rotation_artifacts
from modules.rotation_watch.read import load_panel_sources
from modules.rotation_watch.view import build_panel

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
TEST_TOKEN = "test-artifact-token-placeholder"


def _load_artifact_server():
    """Import artifact_server without executing Edge engine (scipy)."""
    import importlib.util
    import sys
    import types

    er = REPO / "modules" / "edge_research"

    def load(fullname: str, filepath: Path):
        if fullname in sys.modules:
            return sys.modules[fullname]
        spec = importlib.util.spec_from_file_location(fullname, filepath)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = mod
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    if "modules" not in sys.modules:
        pkg = types.ModuleType("modules")
        pkg.__path__ = [str(REPO / "modules")]
        sys.modules["modules"] = pkg
    existing = sys.modules.get("modules.edge_research")
    if existing is None or getattr(existing, "__file__", None) is None:
        pkg = types.ModuleType("modules.edge_research")
        pkg.__path__ = [str(er)]
        sys.modules["modules.edge_research"] = pkg
        load("modules.edge_research.contracts", er / "contracts.py")
        load("modules.edge_research.storage", er / "storage.py")
        load("modules.edge_research.bundle", er / "bundle.py")
    return load("modules.edge_research.artifact_server", er / "artifact_server.py")
PRODUCTION_UNTOUCHED = (
    "modules/edge_research/engine.py",
    "modules/edge_research/ui.py",
    "modules/learning_insight_candidates.py",
    "modules/live_candidate/watchlist.py",
    "modules/intraday_memory/collector.py",
    "decision_engine.py",
    "learning_engine.py",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(method: str, url: str, token: str | None = None, data: bytes | None = None) -> tuple[int, bytes]:
    headers = {"User-Agent": "test"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _board_payload(*, observed_at: str, state: str = ST_BUY_READY, **row_over: object) -> dict:
    action = {
        ST_BUY_READY: "BUY READY",
        ST_SELL_READY: "SELL READY",
        ST_LOWER_ZONE: "WATCH LOWER",
    }.get(state, "WAIT")
    row = {
        "symbol": "TCH",
        "current_price": 11.78,
        "location": "LOWER",
        "lower_zone": "11.60–11.90",
        "upper_zone": "12.20–12.40",
        "last_session_state": state,
        "last_session_action": action,
        "rotation_state": state,
        "suggested_action": action,
        "published_pxv": "STRENGTHEN",
        "raw_pxv": "STRENGTHEN",
        "pxv_why": "frozen P×V",
        "rotation_evidence": ["LOWER + STRENGTHEN"],
        "last_bar_ts": "2026-08-14T10:35:00+07:00",
        "freshness": "LIVE",
        "data_source": "vnstock4_kbs",
        "data_source_label": "Camera KBS 5m (vnstock4 Quote source=KBS)",
    }
    row.update(row_over)
    return {
        "schema": SCHEMA_BOARD,
        "observed_at": observed_at,
        "session_phase": "LIVE",
        "empty": False,
        "alert_eligible": False,
        "source": "rotation_watch_sidecar",
        "rows": [row],
    }


def _status_payload(*, observed_at: str) -> dict:
    return {
        "schema": SCHEMA_STATUS,
        "observed_at": observed_at,
        "session_phase": "LIVE",
        "alert_eligible": False,
        "n_symbols": 1,
        "symbols": [{"symbol": "TCH", "ok": True}],
    }


def _write_working(src: Path, *, board: dict | None = None, status: dict | None = None) -> Path:
    src.mkdir(parents=True, exist_ok=True)
    observed = "2026-08-14T10:40:00+07:00"
    (src / BOARD_NAME).write_text(
        json.dumps(board or _board_payload(observed_at=observed), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (src / STATUS_NAME).write_text(
        json.dumps(status or _status_payload(observed_at=observed), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (src / "state.json").write_text('{"schema":"rotation_watch_state.v1","TCH":{}}\n', encoding="utf-8")
    (src / "watchlist.csv").write_text(
        "symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note\n"
        "TCH,true,11.60,11.90,12.20,12.40,,,\"manual rotation watch\"\n",
        encoding="utf-8",
    )
    return src


def test_publisher_copies_only_board_and_status(tmp_path):
    src = _write_working(tmp_path / "work")
    dest = tmp_path / "store"
    pub = publish_rotation_artifacts(src, dest)
    assert pub["ok"] is True
    assert pub["copied"] == [BOARD_NAME, STATUS_NAME]
    assert ALLOWED_ROTATION_FILES == (BOARD_NAME, STATUS_NAME)
    assert (dest / BOARD_NAME).read_bytes() == (src / BOARD_NAME).read_bytes()
    assert (dest / STATUS_NAME).read_bytes() == (src / STATUS_NAME).read_bytes()
    assert not (dest / "state.json").exists()
    assert not (dest / "watchlist.csv").exists()
    assert set(p.name for p in dest.iterdir()) == {BOARD_NAME, STATUS_NAME}


def test_publisher_refuses_camera_and_candidate_stores(tmp_path):
    from modules.rotation_watch.constants import (
        FORBIDDEN_CAMERA_ARCHIVE,
        FORBIDDEN_EDGE_DURABLE,
        FORBIDDEN_LIVE_SHADOW_STORE,
    )

    src = _write_working(tmp_path / "work")
    for dest in (
        Path(FORBIDDEN_CAMERA_ARCHIVE),
        Path(FORBIDDEN_LIVE_SHADOW_STORE),
        Path(FORBIDDEN_EDGE_DURABLE),
    ):
        result = publish_rotation_artifacts(src, dest)
        assert result["ok"] is False, dest
        assert "refusing" in result["detail"]


def test_publisher_default_store_path():
    assert VPS_ROTATION_STORE == "/var/lib/mrbot/rotation_watch"


def _start_server(tmp_path, *, rotation=None, shadow=None):
    mod = _load_artifact_server()
    ArtifactServer = mod.ArtifactServer
    ArtifactServerConfig = mod.ArtifactServerConfig

    storage = tmp_path / "durable_root"
    storage.mkdir()
    rot = rotation if rotation is not None else tmp_path / "rotation_watch"
    sh = shadow if shadow is not None else tmp_path / "live_pxv_shadow"
    rot.mkdir(parents=True, exist_ok=True)
    sh.mkdir(parents=True, exist_ok=True)
    config = ArtifactServerConfig(
        storage_root=storage,
        token=TEST_TOKEN,
        host="127.0.0.1",
        port=_free_port(),
        live_shadow_root=sh,
        rotation_watch_root=rot,
    )
    server = ArtifactServer(config)
    server.start(blocking=False)
    return server, rot, sh, storage


def test_rotation_get_board_and_status_with_bearer(tmp_path):
    src = _write_working(tmp_path / "work")
    dest = tmp_path / "rotation_watch"
    publish_rotation_artifacts(src, dest)
    server, _, _, _ = _start_server(tmp_path, rotation=dest)
    try:
        status, body = _request("GET", f"{server.base_url}{ARTIFACT_BOARD_PATH}", TEST_TOKEN)
        assert status == 200
        assert json.loads(body)["schema"] == SCHEMA_BOARD
        assert json.loads(body)["rows"][0]["symbol"] == "TCH"
        status, body = _request("GET", f"{server.base_url}{ROTATION_STATUS_PATH}", TEST_TOKEN)
        assert status == 200
        assert json.loads(body)["schema"] == SCHEMA_STATUS
    finally:
        server.stop()


def test_unauthenticated_rotation_get_rejected(tmp_path):
    dest = tmp_path / "rotation_watch"
    dest.mkdir()
    (dest / BOARD_NAME).write_text("{}", encoding="utf-8")
    server, _, _, _ = _start_server(tmp_path, rotation=dest)
    try:
        status, _ = _request("GET", f"{server.base_url}{ARTIFACT_BOARD_PATH}", None)
        assert status == 401
        status, _ = _request("GET", f"{server.base_url}{ROTATION_STATUS_PATH}", "wrong")
        assert status == 401
    finally:
        server.stop()


def test_rotation_write_methods_rejected(tmp_path):
    dest = tmp_path / "rotation_watch"
    dest.mkdir()
    (dest / BOARD_NAME).write_text("{}", encoding="utf-8")
    before = (dest / BOARD_NAME).read_bytes()
    server, _, _, _ = _start_server(tmp_path, rotation=dest)
    try:
        for method in ("PUT", "POST", "DELETE"):
            status, _ = _request(method, f"{server.base_url}{ARTIFACT_BOARD_PATH}", TEST_TOKEN, b"x")
            assert status == 405, method
        assert (dest / BOARD_NAME).read_bytes() == before
    finally:
        server.stop()


def test_unknown_rotation_path_and_traversal_rejected(tmp_path):
    dest = tmp_path / "rotation_watch"
    dest.mkdir()
    (dest / BOARD_NAME).write_text('{"ok":true}\n', encoding="utf-8")
    (dest / "state.json").write_text("secret\n", encoding="utf-8")
    server, _, _, _ = _start_server(tmp_path, rotation=dest)
    try:
        status, _ = _request("GET", f"{server.base_url}/current/rotation_watch/state.json", TEST_TOKEN)
        assert status == 404
        status, _ = _request("GET", f"{server.base_url}/current/rotation_watch/watchlist.csv", TEST_TOKEN)
        assert status == 404
        for path in (
            "/current/rotation_watch/../live_shadow/live_evidence.jsonl",
            "/current/rotation_watch/../../etc/passwd",
            "/current/rotation_watch/board.json/../state.json",
        ):
            status, _ = _request("GET", f"{server.base_url}{path}", TEST_TOKEN)
            assert status == 404, path
    finally:
        server.stop()


def test_missing_rotation_artifact_is_404(tmp_path):
    server, _, _, _ = _start_server(tmp_path)
    try:
        status, body = _request("GET", f"{server.base_url}{ARTIFACT_BOARD_PATH}", TEST_TOKEN)
        assert status == 404
        assert b"rotation_watch_not_found" in body
        status, body = _request("GET", f"{server.base_url}{ROTATION_STATUS_PATH}", TEST_TOKEN)
        assert status == 404
    finally:
        server.stop()


def test_candidate_live_shadow_get_still_works(tmp_path):
    shadow = tmp_path / "live_pxv_shadow"
    shadow.mkdir()
    shadow.joinpath("live_evidence.jsonl").write_text('{"symbol":"HPG"}\n', encoding="utf-8")
    shadow.joinpath("live_shadow_status.json").write_text('{"runner":"LIVE"}\n', encoding="utf-8")
    server, _, _, _ = _start_server(tmp_path, shadow=shadow)
    try:
        status, body = _request("GET", f"{server.base_url}{SHADOW_EVIDENCE_PATH}", TEST_TOKEN)
        assert status == 200
        assert body == b'{"symbol":"HPG"}\n'
        status, body = _request("GET", f"{server.base_url}{SHADOW_STATUS_PATH}", TEST_TOKEN)
        assert status == 200
        assert body == b'{"runner":"LIVE"}\n'
    finally:
        server.stop()


def test_edge_bundle_get_put_unchanged_with_rotation_routes(tmp_path):
    server, _, _, storage = _start_server(tmp_path)
    try:
        payload = b"edge-bundle-bytes"
        status, body = _request("PUT", f"{server.base_url}/current/bundle.tar.gz", TEST_TOKEN, payload)
        # malformed gzip is 400 — use a real tiny valid? Edge validates tar.
        # Existing CASE 4: invalid gzip → 400. That is unchanged behavior.
        assert status == 400
        assert not (storage / "current" / "bundle.tar.gz").exists()
        status, _ = _request("GET", f"{server.base_url}/current/bundle.tar.gz", TEST_TOKEN)
        assert status == 404
        status, _ = _request("GET", f"{server.base_url}/current/bundle.tar.gz", None)
        assert status == 401
    finally:
        server.stop()


def test_candidate_client_allowlist_unchanged():
    src = inspect.getsource(get_live_shadow_bytes)
    assert "rotation_watch" not in src
    assert "board.json" not in src
    try:
        get_live_shadow_bytes(ARTIFACT_BOARD_PATH, base_url="http://example.test", token="t")
        raise AssertionError("rotation path must be rejected by Candidate client")
    except Exception as exc:
        assert "disallowed" in str(exc)
    # Allowlist remains the two Candidate objects.
    assert SHADOW_EVIDENCE_PATH == "/current/live_shadow/live_evidence.jsonl"
    assert SHADOW_STATUS_PATH == "/current/live_shadow/live_shadow_status.json"


def test_rotation_reader_uses_owned_get_client():
    read_src = (REPO / "modules" / "rotation_watch" / "read.py").read_text(encoding="utf-8")
    assert "get_rotation_board_text" in read_src
    assert "get_rotation_status_text" in read_src
    assert "get_live_shadow_bytes" not in read_src
    get_src = (REPO / "modules" / "rotation_watch" / "artifact_get.py").read_text(encoding="utf-8")
    assert "from modules.live_shadow_transport" not in get_src
    assert "Never PUT" in get_src


def test_rotation_get_client_allowlist():
    try:
        get_rotation_bytes("/current/live_shadow/live_evidence.jsonl", base_url="http://example.test", token="t")
        raise AssertionError("Candidate path must be rejected by Rotation client")
    except RotationTransportError as exc:
        assert "disallowed" in str(exc)


def test_remote_failure_has_no_local_fallback(tmp_path, monkeypatch):
    local = tmp_path / "rotation"
    _write_working(local)
    monkeypatch.setenv("MRBOT_ROTATION_WATCH_DIR", str(local))
    monkeypatch.setenv("EDGE_RESEARCH_DURABLE_URL", "https://example.test")
    monkeypatch.setenv("EDGE_RESEARCH_DURABLE_TOKEN", "t")
    monkeypatch.delenv("MRBOT_ROTATION_WATCH_UI_SOURCE", raising=False)

    def boom():
        raise RotationTransportError("artifact HTTP 503")

    packed = load_panel_sources(board_fetcher=boom, status_fetcher=lambda: "{}")
    assert packed["board"] is None
    assert packed["transport"]["error"] == TRANSPORT_ERROR
    panel = build_panel(
        now=datetime(2026, 8, 14, 10, 41, tzinfo=VN),
        board_fetcher=boom,
        status_fetcher=lambda: "{}",
    )
    row = panel["rows"][0]
    assert row["last_session_state"] == ST_DATA_UNCERTAIN
    assert row["suggested_action"] == "WAIT"
    assert row["symbol"] != "TCH"


def test_missing_invalid_stale_remote_board_is_uncertain():
    live = datetime(2026, 8, 14, 10, 55, tzinfo=VN)

    from modules.rotation_watch.artifact_get import RotationArtifactNotFound

    def not_found():
        raise RotationArtifactNotFound(ARTIFACT_BOARD_PATH)

    panel = build_panel(now=live, board_fetcher=not_found, status_fetcher=lambda: "{}")
    assert panel["rows"][0]["suggested_action"] == "WAIT"
    assert panel["rows"][0]["last_session_state"] == ST_DATA_UNCERTAIN

    panel = build_panel(now=live, board_fetcher=lambda: '{"nope": true}', status_fetcher=lambda: "{}")
    assert panel["rows"][0]["suggested_action"] == "WAIT"
    assert panel["rows"][0]["last_session_state"] == ST_DATA_UNCERTAIN

    stale_board = json.dumps(_board_payload(observed_at="2026-08-14T10:40:00+07:00"))
    stale_status = json.dumps(_status_payload(observed_at="2026-08-14T10:40:00+07:00"))
    panel = build_panel(now=live, board_fetcher=lambda: stale_board, status_fetcher=lambda: stale_status)
    row = panel["rows"][0]
    assert row["symbol"] == "TCH"
    assert row["last_session_state"] == ST_BUY_READY
    assert row["suggested_action"] == "WAIT"
    assert row["freshness"] == "STALE"


def test_weekend_remote_buy_ready_is_wait():
    board = json.dumps(_board_payload(observed_at="2026-08-14T10:40:00+07:00"))
    status = json.dumps(_status_payload(observed_at="2026-08-14T10:40:00+07:00"))
    sat = datetime(2026, 8, 15, 10, 0, tzinfo=VN)
    panel = build_panel(now=sat, board_fetcher=lambda: board, status_fetcher=lambda: status)
    row = panel["rows"][0]
    assert row["symbol"] == "TCH"
    assert row["last_session_state"] == ST_BUY_READY
    assert row["published_pxv"] == "STRENGTHEN"
    assert row["suggested_action"] == "WAIT"
    assert row["actionable"] is False
    assert row["session_phase"] == "WEEKEND"


def test_status_failure_fail_closes_even_if_board_ok():
    board = json.dumps(_board_payload(observed_at="2026-08-14T10:40:00+07:00"))
    from modules.rotation_watch.artifact_get import RotationArtifactNotFound

    panel = build_panel(
        now=datetime(2026, 8, 14, 10, 41, tzinfo=VN),
        board_fetcher=lambda: board,
        status_fetcher=lambda: (_ for _ in ()).throw(RotationArtifactNotFound(ROTATION_STATUS_PATH)),
    )
    assert panel["rows"][0]["suggested_action"] == "WAIT"
    assert panel["rows"][0]["last_session_state"] == ST_DATA_UNCERTAIN


def test_rotation_ui_import_still_works_without_vnstock():
    import importlib.util

    from modules.rotation_watch.html import render_html
    from modules.rotation_watch.render import render_rotation_watch_panel
    from modules.rotation_watch.view import build_panel as _bp

    assert render_rotation_watch_panel is not None
    panel = _bp(now=datetime(2026, 8, 15, 10, 0, tzinfo=VN), artifact_path=Path("/tmp/no-rotation-board.json"))
    assert "WAIT" in render_html(panel)
    assert importlib.util.find_spec("vnstock") is None


def test_no_production_semantic_edits():
    import subprocess

    changed = subprocess.check_output(
        ["git", "diff", "main", "--name-only", "--", *PRODUCTION_UNTOUCHED],
        cwd=REPO,
        text=True,
    ).strip()
    assert changed == "", changed


def test_app_panel_order_unchanged():
    app = (REPO / "app.py").read_text(encoding="utf-8")
    assert app.index("render_live_candidate_pxv_panel") < app.index("render_rotation_watch_panel")
    assert app.index("render_rotation_watch_panel") < app.index("EARNING MONEY BOARD")
    assert app.index("render_rotation_watch_panel") < app.index("run_scan(WATCHLIST)")


def test_rotation_transport_modules_do_not_import_candidate_parse():
    for rel in (
        "modules/rotation_watch/artifact_get.py",
        "modules/rotation_watch/read.py",
        "modules/rotation_watch/publish.py",
    ):
        src = (REPO / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
        blob = " ".join(names)
        assert "live_shadow_transport.artifact_get" not in blob
        assert "modules.rotation_watch.engine" not in blob
        assert "KBSProvider" not in src
        assert "vnstock" not in src


def test_remote_200_200_load_panel_sources_without_fetcher_injection(tmp_path, monkeypatch):
    src = _write_working(tmp_path / "work")
    dest = tmp_path / "rotation_watch"
    publish_rotation_artifacts(src, dest)
    server, _, _, _ = _start_server(tmp_path, rotation=dest)
    try:
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_URL", server.base_url)
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_TOKEN", TEST_TOKEN)
        monkeypatch.delenv("MRBOT_ROTATION_WATCH_UI_SOURCE", raising=False)
        packed = load_panel_sources()
        assert packed["transport"]["mode"] == "remote"
        assert packed["transport"]["error"] is None
        assert packed["board"] is not None
        assert packed["board"]["rows"][0]["symbol"] == "TCH"
        assert packed["status"]["schema"] == SCHEMA_STATUS
        panel = build_panel(now=datetime(2026, 8, 14, 10, 41, tzinfo=VN))
        assert panel["rows"][0]["symbol"] == "TCH"
        assert panel["rows"][0]["location"] == "LOWER"
    finally:
        server.stop()


def test_remote_board_404_fail_closes(tmp_path, monkeypatch):
    dest = tmp_path / "rotation_watch"
    dest.mkdir()
    (dest / STATUS_NAME).write_text(json.dumps(_status_payload(observed_at="2026-08-14T10:40:00+07:00")), encoding="utf-8")
    server, _, _, _ = _start_server(tmp_path, rotation=dest)
    try:
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_URL", server.base_url)
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_TOKEN", TEST_TOKEN)
        packed = load_panel_sources()
        assert packed["board"] is None
        assert packed["transport"]["error"] == TRANSPORT_ERROR
        assert "board missing" in packed["transport"]["detail"]
        panel = build_panel(now=datetime(2026, 8, 14, 10, 41, tzinfo=VN))
        assert panel["rows"][0]["last_session_state"] == ST_DATA_UNCERTAIN
        assert panel["rows"][0]["suggested_action"] == "WAIT"
        assert panel["rows"][0]["actionable"] is False
    finally:
        server.stop()


def test_remote_status_404_fail_closes_even_if_board_ok(tmp_path, monkeypatch):
    dest = tmp_path / "rotation_watch"
    dest.mkdir()
    (dest / BOARD_NAME).write_text(
        json.dumps(_board_payload(observed_at="2026-08-14T10:40:00+07:00")),
        encoding="utf-8",
    )
    server, _, _, _ = _start_server(tmp_path, rotation=dest)
    try:
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_URL", server.base_url)
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_TOKEN", TEST_TOKEN)
        packed = load_panel_sources()
        assert packed["board"] is None
        assert packed["transport"]["error"] == TRANSPORT_ERROR
        assert "status missing" in packed["transport"]["detail"]
        panel = build_panel(now=datetime(2026, 8, 14, 10, 41, tzinfo=VN))
        assert panel["rows"][0]["last_session_state"] == ST_DATA_UNCERTAIN
        assert panel["rows"][0]["suggested_action"] == "WAIT"
    finally:
        server.stop()


def test_remote_invalid_board_json_and_schema_fail_closed():
    live = datetime(2026, 8, 14, 10, 55, tzinfo=VN)
    status = json.dumps(_status_payload(observed_at="2026-08-14T10:40:00+07:00"))
    for bad in ("not-json", '{"nope": true}', "[]"):
        packed = load_panel_sources(board_fetcher=lambda b=bad: b, status_fetcher=lambda: status)
        assert packed["board"] is None
        assert packed["transport"]["error"] == TRANSPORT_ERROR
        panel = build_panel(now=live, board_fetcher=lambda b=bad: b, status_fetcher=lambda: status)
        assert panel["rows"][0]["last_session_state"] == ST_DATA_UNCERTAIN
        assert panel["rows"][0]["suggested_action"] == "WAIT"
        assert panel["rows"][0]["actionable"] is False


def test_remote_invalid_status_json_and_schema_fail_closed():
    live = datetime(2026, 8, 14, 10, 41, tzinfo=VN)
    board = json.dumps(_board_payload(observed_at="2026-08-14T10:40:00+07:00"))
    for bad in ("not-json", '{"nope": true}', "[]"):
        packed = load_panel_sources(board_fetcher=lambda: board, status_fetcher=lambda b=bad: b)
        assert packed["board"] is None
        assert packed["transport"]["error"] == TRANSPORT_ERROR
        panel = build_panel(now=live, board_fetcher=lambda: board, status_fetcher=lambda b=bad: b)
        assert panel["rows"][0]["last_session_state"] == ST_DATA_UNCERTAIN
        assert panel["rows"][0]["suggested_action"] == "WAIT"
        assert panel["rows"][0]["actionable"] is False


def test_remote_auth_failure_is_transport_error_no_local_fallback(tmp_path, monkeypatch):
    local = _write_working(tmp_path / "rotation")
    dest = tmp_path / "rotation_watch"
    publish_rotation_artifacts(local, dest)
    server, _, _, _ = _start_server(tmp_path, rotation=dest)
    try:
        monkeypatch.setenv("MRBOT_ROTATION_WATCH_DIR", str(local))
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_URL", server.base_url)
        monkeypatch.setenv("EDGE_RESEARCH_DURABLE_TOKEN", "wrong-token")
        packed = load_panel_sources()
        assert packed["board"] is None
        assert packed["transport"]["error"] == TRANSPORT_ERROR
        assert "401" in packed["transport"]["detail"]
        assert packed["board"] is None or packed["board"].get("rows", [{}])[0].get("symbol") != "TCH"
    finally:
        server.stop()


def test_remote_transport_failure_without_fetcher_does_not_read_local(tmp_path, monkeypatch):
    local = _write_working(tmp_path / "rotation")
    monkeypatch.setenv("MRBOT_ROTATION_WATCH_DIR", str(local))
    monkeypatch.setenv("EDGE_RESEARCH_DURABLE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("EDGE_RESEARCH_DURABLE_TOKEN", "t")
    monkeypatch.delenv("MRBOT_ROTATION_WATCH_UI_SOURCE", raising=False)
    packed = load_panel_sources()
    assert packed["board"] is None
    assert packed["transport"]["error"] == TRANSPORT_ERROR
    panel = build_panel(now=datetime(2026, 8, 14, 10, 41, tzinfo=VN))
    assert panel["rows"][0]["symbol"] != "TCH"
    assert panel["rows"][0]["suggested_action"] == "WAIT"


def test_weekend_historical_sell_ready_is_not_current_sell():
    board = json.dumps(_board_payload(observed_at="2026-08-14T10:40:00+07:00", state=ST_SELL_READY))
    status = json.dumps(_status_payload(observed_at="2026-08-14T10:40:00+07:00"))
    sat = datetime(2026, 8, 15, 10, 0, tzinfo=VN)
    panel = build_panel(now=sat, board_fetcher=lambda: board, status_fetcher=lambda: status)
    row = panel["rows"][0]
    assert row["last_session_state"] == ST_SELL_READY
    assert row["last_session_action"] == "SELL READY"
    assert row["suggested_action"] == "WAIT"
    assert row["actionable"] is False
    assert row["session_phase"] == "WEEKEND"


def test_vps_weekend_tch_artifact_renders_historical_wait_only():
    """Real F-shaped TCH weekend artifact: historical LOWER_ZONE, current WAIT."""
    from modules.rotation_watch.html import render_html

    observed = "2026-09-12T08:54:00+07:00"
    board = json.dumps(
        _board_payload(
            observed_at=observed,
            state=ST_LOWER_ZONE,
            current_price=11.70,
            location="LOWER",
            published_pxv="NEUTRAL",
            raw_pxv="NEUTRAL",
            last_bar_ts="2026-09-11T14:45:00+07:00",
            freshness="SESSION_CLOSED",
            last_session_action="WATCH LOWER",
            suggested_action="WATCH LOWER",
        )
    )
    status = json.dumps(_status_payload(observed_at=observed))
    sat = datetime(2026, 9, 12, 10, 0, tzinfo=VN)
    panel = build_panel(now=sat, board_fetcher=lambda: board, status_fetcher=lambda: status)
    row = panel["rows"][0]
    assert row["symbol"] == "TCH"
    assert row["current_price"] == 11.70
    assert row["location"] == "LOWER"
    assert row["last_session_state"] == ST_LOWER_ZONE
    assert row["last_session_action"] == "WATCH LOWER"
    assert row["published_pxv"] == "NEUTRAL"
    assert row["freshness"] == "SESSION_CLOSED"
    assert row["session_phase"] == "WEEKEND"
    assert row["suggested_action"] == "WAIT"
    assert row["actionable"] is False
    html = render_html(panel)
    assert "TCH" in html
    assert "11.7" in html
    assert "LOWER" in html
    assert "LOWER_ZONE" in html
    assert "WATCH LOWER" in html
    assert "NEUTRAL" in html
    assert "SESSION_CLOSED" in html
    assert "WEEKEND" in html
    assert "WAIT" in html
    assert "BUY READY" not in html
    assert "SELL READY" not in html
