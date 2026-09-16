"""LIVE CANDIDATE V2 Slice 3B — GitHub Contents sidecar transport.

Shadow only. Candidate != BUY. No KBS. No runner. No production watchlist.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.candidate_router.contract import ENABLED_SOURCES, SRC_BUY_ELITE, SRC_ROTATION
from modules.live_candidate_v2_camera.cloud_hook import (
    REASON_GATE_OFF,
    REASON_LOAD_FAILED,
    run_v2_cloud_sidecar,
)
from modules.live_candidate_v2_camera.contract import (
    ENV_V2_CLOUD_SIDECAR,
    ENV_V2_GITHUB_PUBLISH,
    ENV_V2_GITHUB_PUBLISH_TRUTHY,
    GITHUB_V2_SIDECAR_PATH,
    SCHEMA_ID,
)
from modules.live_candidate_v2_camera.github_bus import (
    IMMUTABLE_ON_V2_TRANSPORT,
    STATUS_GATE_OFF,
    STATUS_INVALID_DOCUMENT,
    STATUS_LOAD_FAILED,
    STATUS_NOT_ELIGIBLE,
    STATUS_NOT_FOUND,
    STATUS_OK_EMPTY,
    STATUS_OK_ROWS,
    STATUS_PUBLISHED,
    STATUS_TRANSPORT_ERROR,
    assert_v2_github_path,
    fetch_v2_sidecar,
    maybe_publish_v2_sidecar,
    publish_v2_sidecar_file,
    v2_github_publish_enabled,
)
from modules.live_candidate_v2_nomination.contract import SRC_BRAIN_A
from modules.live_shadow_transport.contract import GITHUB_WATCHLIST_PATH
from modules.live_shadow_transport.watchlist_bus import WatchlistTransportError

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.sample.json"
ON_A = {ENV_V2_CLOUD_SIDECAR: "1"}
ON_B = {ENV_V2_GITHUB_PUBLISH: "1"}
ON_AB = {ENV_V2_CLOUD_SIDECAR: "1", ENV_V2_GITHUB_PUBLISH: "1"}


class RecWriter:
    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, path: str, text: str, message: str) -> str:
        assert path == GITHUB_V2_SIDECAR_PATH
        assert path != GITHUB_WATCHLIST_PATH
        self.calls.append((path, text, message))
        return "GITHUB_OK"


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=VN)


def _scan(symbol: str, group: str, **extra) -> dict:
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


def _write_local(tmp_path: Path, env=None, rows=None) -> tuple[object, Path]:
    dest = tmp_path / "camera_sidecar.json"
    result = run_v2_cloud_sidecar(
        scan_rows=rows if rows is not None else [_scan("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=_ts("2026-08-14 10:05:00"),
        path=dest,
        env=env if env is not None else ON_A,
    )
    return result, dest


def test_publish_gate_default_off(monkeypatch):
    monkeypatch.delenv(ENV_V2_GITHUB_PUBLISH, raising=False)
    assert v2_github_publish_enabled({}) is False
    assert v2_github_publish_enabled({ENV_V2_GITHUB_PUBLISH: ""}) is False
    assert v2_github_publish_enabled({ENV_V2_GITHUB_PUBLISH: "0"}) is False
    assert v2_github_publish_enabled({ENV_V2_GITHUB_PUBLISH: "false"}) is False
    assert v2_github_publish_enabled({ENV_V2_GITHUB_PUBLISH: "off"}) is False
    for val in ENV_V2_GITHUB_PUBLISH_TRUTHY:
        assert v2_github_publish_enabled({ENV_V2_GITHUB_PUBLISH: val}) is True
        assert v2_github_publish_enabled({ENV_V2_GITHUB_PUBLISH: val.upper()}) is True


def test_gate_a_on_gate_b_off_local_only_no_github_write(tmp_path):
    writer = RecWriter()
    local, dest = _write_local(tmp_path, env=ON_A)
    assert local.ok and not local.skipped
    assert dest.exists()
    pub = maybe_publish_v2_sidecar(
        local_ok=local.ok,
        local_skipped=local.skipped,
        path=dest,
        writer=writer,
        env=ON_A,
    )
    assert pub.ok is True
    assert pub.skipped is True
    assert pub.status == STATUS_GATE_OFF
    assert writer.calls == []
    assert json.loads(dest.read_text(encoding="utf-8"))["schema"] == SCHEMA_ID


def test_gate_a_off_gate_b_on_does_not_invent_or_publish(tmp_path):
    writer = RecWriter()
    leftover = json.loads(SAMPLE.read_text(encoding="utf-8"))
    dest = tmp_path / "camera_sidecar.json"
    dest.write_text(json.dumps(leftover), encoding="utf-8")
    local, _ = _write_local(tmp_path, env={}, rows=[_scan("HPG", "PULL ĐẸP")])
    assert local.skipped is True
    assert local.reason == REASON_GATE_OFF
    pub = maybe_publish_v2_sidecar(
        local_ok=local.ok,
        local_skipped=local.skipped,
        path=dest,
        writer=writer,
        env=ON_B,
    )
    assert pub.skipped is True
    assert pub.status == STATUS_NOT_ELIGIBLE
    assert writer.calls == []


def test_both_gates_off_no_v2_transport(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_V2_CLOUD_SIDECAR, raising=False)
    monkeypatch.delenv(ENV_V2_GITHUB_PUBLISH, raising=False)
    writer = RecWriter()
    local, dest = _write_local(tmp_path, env={})
    pub = maybe_publish_v2_sidecar(
        local_ok=local.ok,
        local_skipped=local.skipped,
        path=dest,
        writer=writer,
        env={},
    )
    assert local.skipped is True
    assert not dest.exists()
    assert pub.status == STATUS_GATE_OFF
    assert writer.calls == []


def test_valid_nonempty_sidecar_publishes_v2_path(tmp_path):
    writer = RecWriter()
    local, dest = _write_local(tmp_path, env=ON_A)
    pub = maybe_publish_v2_sidecar(
        local_ok=local.ok,
        local_skipped=local.skipped,
        path=dest,
        writer=writer,
        env=ON_AB,
    )
    assert pub.ok is True
    assert pub.skipped is False
    assert pub.status == STATUS_PUBLISHED
    assert pub.path == GITHUB_V2_SIDECAR_PATH
    assert len(writer.calls) == 1
    path, text, _message = writer.calls[0]
    assert path == GITHUB_V2_SIDECAR_PATH
    assert path != GITHUB_WATCHLIST_PATH
    doc = json.loads(text)
    assert doc["schema"] == SCHEMA_ID
    assert doc["rows"]
    assert doc["rows"][0]["symbol"] == "HPG"
    assert json.loads(dest.read_text(encoding="utf-8")) == doc


def test_valid_empty_rows_publishes_as_empty_universe(tmp_path):
    writer = RecWriter()
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    doc["rows"] = []
    dest = tmp_path / "camera_sidecar.json"
    dest.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pub = publish_v2_sidecar_file(dest, writer=writer, env=ON_B)
    assert pub.ok is True
    assert pub.status == STATUS_PUBLISHED
    published = json.loads(writer.calls[0][1])
    assert published["rows"] == []
    assert published["schema"] == SCHEMA_ID
    assert isinstance(published["freeze_ledger"], list)
    assert published["freeze_ledger"]


def test_corrupt_sidecar_does_not_publish(tmp_path):
    writer = RecWriter()
    dest = tmp_path / "camera_sidecar.json"
    dest.write_text("{not-json", encoding="utf-8")
    before = dest.read_text(encoding="utf-8")
    pub = publish_v2_sidecar_file(dest, writer=writer, env=ON_B)
    assert pub.ok is False
    assert pub.status == STATUS_LOAD_FAILED
    assert writer.calls == []
    assert dest.read_text(encoding="utf-8") == before


def test_load_failed_local_cycle_does_not_publish(tmp_path):
    writer = RecWriter()
    dest = tmp_path / "camera_sidecar.json"
    dest.write_text("{not-json", encoding="utf-8")
    local = run_v2_cloud_sidecar(
        scan_rows=[_scan("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=_ts("2026-08-14 10:05:00"),
        path=dest,
        env=ON_A,
    )
    assert local.ok is False
    assert local.reason == REASON_LOAD_FAILED
    pub = maybe_publish_v2_sidecar(
        local_ok=local.ok,
        local_skipped=local.skipped,
        path=dest,
        writer=writer,
        env=ON_AB,
    )
    assert pub.skipped is True
    assert pub.status == STATUS_NOT_ELIGIBLE
    assert writer.calls == []
    assert dest.read_text(encoding="utf-8") == "{not-json"


def test_refuses_production_watchlist_path():
    try:
        assert_v2_github_path(GITHUB_WATCHLIST_PATH)
        raise AssertionError("must refuse production watchlist")
    except Exception as exc:
        assert "dynamic_watchlist" in str(exc)
    assert assert_v2_github_path(GITHUB_V2_SIDECAR_PATH) == GITHUB_V2_SIDECAR_PATH
    assert GITHUB_V2_SIDECAR_PATH == "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"


def test_fetch_valid_rows_ok_rows():
    text = SAMPLE.read_text(encoding="utf-8")

    def getter(*, path, **kwargs):
        assert path == GITHUB_V2_SIDECAR_PATH
        return text

    result = fetch_v2_sidecar(text_fetcher=getter)
    assert result.ok is True
    assert result.status == STATUS_OK_ROWS
    assert result.n_rows == 2
    assert result.document["rows"][0]["symbol"] == "HPG"


def test_fetch_valid_empty_ok_empty():
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    doc["rows"] = []
    text = json.dumps(doc)

    def getter(*, path, **kwargs):
        return text

    result = fetch_v2_sidecar(text_fetcher=getter)
    assert result.ok is True
    assert result.status == STATUS_OK_EMPTY
    assert result.n_rows == 0
    assert result.document["rows"] == []
    assert result.document["freeze_ledger"]


def test_fetch_404_is_not_found_not_empty():
    def getter(*, path, **kwargs):
        raise WatchlistTransportError("github HTTP 404")

    result = fetch_v2_sidecar(text_fetcher=getter)
    assert result.ok is False
    assert result.status == STATUS_NOT_FOUND
    assert result.document is None
    assert result.n_rows == 0


def test_fetch_malformed_json_invalid_document():
    def getter(*, path, **kwargs):
        return "{not-json"

    result = fetch_v2_sidecar(text_fetcher=getter)
    assert result.ok is False
    assert result.status == STATUS_INVALID_DOCUMENT
    assert result.document is None


def test_fetch_wrong_schema_and_flags_invalid():
    def wrong_schema(*, path, **kwargs):
        doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
        doc["schema"] = "not-v2"
        return json.dumps(doc)

    def buy_true(*, path, **kwargs):
        doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
        doc["candidate_is_buy"] = True
        return json.dumps(doc)

    def alert_true(*, path, **kwargs):
        doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
        doc["alert_eligible"] = True
        return json.dumps(doc)

    for getter in (wrong_schema, buy_true, alert_true):
        result = fetch_v2_sidecar(text_fetcher=getter)
        assert result.status == STATUS_INVALID_DOCUMENT
        assert result.ok is False


def test_fetch_network_failure_transport_error():
    def getter(*, path, **kwargs):
        raise WatchlistTransportError("github fetch failed: timeout")

    result = fetch_v2_sidecar(text_fetcher=getter)
    assert result.ok is False
    assert result.status == STATUS_TRANSPORT_ERROR
    assert result.document is None


def test_publish_fetch_round_trip_preserves_immutable_fields(tmp_path):
    writer = RecWriter()
    local, dest = _write_local(tmp_path, env=ON_A)
    pub = maybe_publish_v2_sidecar(
        local_ok=local.ok,
        local_skipped=local.skipped,
        path=dest,
        writer=writer,
        env=ON_AB,
    )
    assert pub.ok
    published_text = writer.calls[0][1]
    before = json.loads(published_text)

    def getter(*, path, **kwargs):
        assert path == GITHUB_V2_SIDECAR_PATH
        return published_text

    fetched = fetch_v2_sidecar(text_fetcher=getter)
    assert fetched.status == STATUS_OK_ROWS
    after = fetched.document
    assert after["freeze_ledger"] == before["freeze_ledger"]
    assert after["candidate_is_buy"] is False
    assert after["alert_eligible"] is False
    assert after["generated_at"] == before["generated_at"]
    assert after["session"] == before["session"]
    brow = before["rows"][0]
    arow = after["rows"][0]
    for key in IMMUTABLE_ON_V2_TRANSPORT:
        assert arow[key] == brow[key]
    assert arow["candidate_first_seen_ts"] == brow["candidate_first_seen_ts"]
    assert arow["eligible_from"] == brow["eligible_from"]
    assert arow["setup"] == brow["setup"]
    assert arow["group"] == brow["group"]
    assert arow["observation_intent"] == brow["observation_intent"]
    assert arow["observation_reference"] == brow["observation_reference"]
    assert arow["price_at_first_seen"] == brow["price_at_first_seen"]
    assert arow["ema9_at_first_seen"] == brow["ema9_at_first_seen"]
    assert arow["breakout_ref_at_first_seen"] == brow["breakout_ref_at_first_seen"]
    assert arow["provenance"] == brow["provenance"]


def test_production_isolation_unchanged():
    assert GITHUB_WATCHLIST_PATH == "data/live_candidate/dynamic_watchlist.json"
    assert GITHUB_V2_SIDECAR_PATH != GITHUB_WATCHLIST_PATH
    assert ENABLED_SOURCES == frozenset({SRC_BUY_ELITE})
    assert SRC_BRAIN_A not in ENABLED_SOURCES
    assert SRC_ROTATION not in ENABLED_SOURCES
    bus = (REPO / "modules" / "live_shadow_transport" / "watchlist_bus.py").read_text(
        encoding="utf-8"
    )
    assert "live_candidate_v2_camera.github_bus" not in bus
    src = (REPO / "modules" / "live_candidate_v2_camera" / "github_bus.py").read_text(
        encoding="utf-8"
    )
    assert "vnstock" not in src
    assert "run_cycle" not in src
    assert "run_live_camera_shadow" not in src
    assert "systemctl" not in src
    assert "/opt/mrbot" not in src
    assert "artifact_server" not in src
    hook = (REPO / "modules" / "live_candidate_v2_camera" / "cloud_hook.py").read_text(
        encoding="utf-8"
    )
    assert "watchlist_bus" not in hook
    assert "github_bus" not in hook
    interpret = (REPO / "modules" / "intraday_pxv_v1" / "interpret.py").read_text(encoding="utf-8")
    assert "github_bus" not in interpret
    from modules.live_shadow_transport.watchlist_bus import fetch_github_watchlist_text, fetch_published_watchlist
    import inspect

    default_path = inspect.signature(fetch_github_watchlist_text).parameters["path"].default
    assert default_path == GITHUB_WATCHLIST_PATH
    assert "path" not in inspect.signature(fetch_published_watchlist).parameters


def test_app_hook_publish_is_nested_inside_both_gates():
    app = (REPO / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(app)
    elite = app.index("buy_elite_df = build_buy_elite_decision_engine(")
    hook = app.index("_v2_sidecar = run_v2_cloud_sidecar(")
    pub = app.index("maybe_publish_v2_sidecar(")
    learn = app.index("= run_buy_elite_learning_cycle(")
    assert elite < hook < pub < learn
    assert ENV_V2_GITHUB_PUBLISH in app
    try_node = None
    for node in tree.body:
        if isinstance(node, ast.Try) and "maybe_publish_v2_sidecar" in ast.dump(node):
            try_node = node
            break
    assert try_node is not None
    gate_a = None
    for node in try_node.body:
        if isinstance(node, ast.If) and "cloud_hook" in ast.dump(node):
            gate_a = node
            break
    assert gate_a is not None
    gate_b = None
    for node in ast.walk(gate_a):
        if isinstance(node, ast.If) and "github_bus" in ast.dump(node):
            gate_b = node
            break
    assert gate_b is not None
    assert "maybe_publish_v2_sidecar" in ast.dump(gate_b)
    assert "github_bus" not in ast.dump(ast.Module(body=list(gate_a.orelse), type_ignores=[]))
    for inner in ast.walk(try_node):
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
            assert inner.func.id != "run_buy_elite_learning_cycle"
            assert inner.func.id != "persist_and_publish_research_watchlist"
            assert inner.func.id != "fetch_published_watchlist"
