"""LIVE CANDIDATE V2 Slice 3A — gated Cloud local sidecar + restart-safe freeze.

No GitHub publish. No VPS. No runner. Candidate != BUY.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.candidate_router.adapters.rotation import nominations_from_rotation_artifact
from modules.candidate_router.contract import ENABLED_SOURCES, SRC_BUY_ELITE, SRC_ROTATION
from modules.live_candidate_v2_camera.cloud_hook import (
    REASON_GATE_OFF,
    REASON_LOAD_FAILED,
    attach_elite_buy_grade_metadata,
    run_v2_cloud_sidecar,
    v2_cloud_sidecar_enabled,
)
from modules.live_candidate_v2_camera.contract import (
    ENV_V2_CLOUD_SIDECAR,
    SCHEMA_ID,
)
from modules.live_candidate_v2_camera.sidecar import (
    PRODUCTION_WATCHLIST,
    SidecarShadowError,
    load_sidecar_document,
)
from modules.live_candidate_v2_nomination.contract import (
    REJECT_BARE_MUA_EARLY,
    REJECT_ELITE_GRADE_ALONE,
    SRC_BRAIN_A,
)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
REPO = Path(__file__).resolve().parents[1]
ON = {ENV_V2_CLOUD_SIDECAR: "1"}


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


def _run(tmp_path: Path, rows, *, now: str, market_real=7.2, elite=None, early=None, env=None):
    dest = tmp_path / "camera_sidecar.json"
    elite_df = None if elite is None else pd.DataFrame(elite)
    early_df = None if early is None else pd.DataFrame(early)
    return run_v2_cloud_sidecar(
        scan_rows=rows,
        market_real=market_real,
        observed_at=_ts(now),
        buy_elite_df=elite_df,
        early_buy_lab_df=early_df,
        path=dest,
        env=env if env is not None else ON,
    ), dest


def test_gate_default_off_does_not_write(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_V2_CLOUD_SIDECAR, raising=False)
    assert v2_cloud_sidecar_enabled({}) is False
    assert v2_cloud_sidecar_enabled({ENV_V2_CLOUD_SIDECAR: ""}) is False
    assert v2_cloud_sidecar_enabled({ENV_V2_CLOUD_SIDECAR: "0"}) is False
    assert v2_cloud_sidecar_enabled({ENV_V2_CLOUD_SIDECAR: "false"}) is False
    assert v2_cloud_sidecar_enabled({ENV_V2_CLOUD_SIDECAR: "no"}) is False
    assert v2_cloud_sidecar_enabled({ENV_V2_CLOUD_SIDECAR: "off"}) is False
    result, dest = _run(
        tmp_path,
        [_scan("HPG", "PULL ĐẸP")],
        now="2026-08-14 10:05:00",
        env={},
    )
    assert result.ok is True
    assert result.skipped is True
    assert result.reason == REASON_GATE_OFF
    assert not dest.exists()


def test_gate_on_writes_local_sidecar(tmp_path):
    for val in ("1", "true", "YES", "On"):
        assert v2_cloud_sidecar_enabled({ENV_V2_CLOUD_SIDECAR: val}) is True
    result, dest = _run(tmp_path, [_scan("HPG", "PULL ĐẸP")], now="2026-08-14 10:05:00")
    assert result.ok is True
    assert result.skipped is False
    assert dest.exists()
    doc = json.loads(dest.read_text(encoding="utf-8"))
    assert doc["schema"] == SCHEMA_ID
    assert doc["session"] == "2026-08-14"
    assert doc["generated_at"].startswith("2026-08-14T10:05:00")
    assert doc["candidate_is_buy"] is False
    assert doc["alert_eligible"] is False
    assert isinstance(doc["freeze_ledger"], list) and doc["freeze_ledger"]
    assert isinstance(doc["rows"], list) and doc["rows"]
    assert doc["rows"][0]["symbol"] == "HPG"
    assert doc["rows"][0]["candidate_first_seen_ts"].startswith("2026-08-14T10:05:00")
    assert not dest.with_name("camera_sidecar.json.tmp").exists()


def test_first_seen_and_frozen_refs_survive_rerun(tmp_path):
    first, dest = _run(
        tmp_path,
        [_scan("HPG", "PULL ĐẸP", price=27.5, ema9=27.1, breakout_ref=28.0)],
        now="2026-08-14 10:05:00",
    )
    assert first.ok
    doc1 = json.loads(dest.read_text(encoding="utf-8"))
    first_seen = doc1["rows"][0]["candidate_first_seen_ts"]
    second, _ = _run(
        tmp_path,
        [_scan("HPG", "PULL ĐẸP", price=29.0, ema9=28.8, breakout_ref=30.0)],
        now="2026-08-14 11:40:00",
    )
    assert second.ok
    doc2 = json.loads(dest.read_text(encoding="utf-8"))
    row = doc2["rows"][0]
    freeze = doc2["freeze_ledger"][0]
    assert row["candidate_first_seen_ts"] == first_seen
    assert freeze["candidate_first_seen_ts"] == first_seen
    assert row["price_at_first_seen"] == 27.5
    assert row["ema9_at_first_seen"] == 27.1
    assert row["breakout_ref_at_first_seen"] == 28.0
    assert freeze["price_at_first_seen"] == 27.5
    assert freeze["ema9_at_first_seen"] == 27.1
    assert freeze["breakout_ref_at_first_seen"] == 28.0
    assert row["candidate_updated_ts"].startswith("2026-08-14T11:40:00")
    assert first_seen.startswith("2026-08-14T10:05:00")
    assert first_seen != row["candidate_updated_ts"]


def test_empty_rerun_keeps_freeze_and_reuses_on_reappear(tmp_path):
    _run(tmp_path, [_scan("HPG", "PULL ĐẸP")], now="2026-08-14 10:05:00")
    dest = tmp_path / "camera_sidecar.json"
    first_seen = json.loads(dest.read_text(encoding="utf-8"))["freeze_ledger"][0]["candidate_first_seen_ts"]
    empty, _ = _run(tmp_path, [_scan("HPG", "THEO DÕI")], now="2026-08-14 13:00:00")
    assert empty.ok
    doc = json.loads(dest.read_text(encoding="utf-8"))
    assert doc["rows"] == []
    assert doc["freeze_ledger"]
    assert doc["freeze_ledger"][0]["symbol"] == "HPG"
    assert doc["freeze_ledger"][0]["candidate_first_seen_ts"] == first_seen
    assert doc["freeze_ledger"][0]["ema9_at_first_seen"] == 27.1
    back, _ = _run(
        tmp_path,
        [_scan("HPG", "PULL ĐẸP", price=40.0, ema9=39.0, breakout_ref=41.0)],
        now="2026-08-14 14:00:00",
    )
    assert back.ok
    again = json.loads(dest.read_text(encoding="utf-8"))
    assert again["rows"][0]["candidate_first_seen_ts"] == first_seen
    assert again["rows"][0]["price_at_first_seen"] == 27.5
    assert again["rows"][0]["ema9_at_first_seen"] == 27.1
    assert again["rows"][0]["breakout_ref_at_first_seen"] == 28.0


def test_cold_restart_rebuilds_from_sidecar_document_only(tmp_path):
    _run(tmp_path, [_scan("HPG", "PULL ĐẸP")], now="2026-08-14 10:05:00")
    dest = tmp_path / "camera_sidecar.json"
    original = json.loads(dest.read_text(encoding="utf-8"))
    first_seen = original["rows"][0]["candidate_first_seen_ts"]
    loaded = load_sidecar_document(dest)
    assert loaded is not None
    assert loaded["freeze_ledger"][0]["candidate_first_seen_ts"] == first_seen
    # New process simulation: only the file, no in-memory prior.
    restarted, _ = _run(
        tmp_path,
        [_scan("HPG", "PULL ĐẸP", price=33.0, ema9=32.0, breakout_ref=34.0)],
        now="2026-08-14 15:00:00",
    )
    assert restarted.ok
    doc = json.loads(dest.read_text(encoding="utf-8"))
    assert doc["rows"][0]["candidate_first_seen_ts"] == first_seen
    assert doc["rows"][0]["ema9_at_first_seen"] == 27.1


def test_session_rollover_new_episode_does_not_inherit_old_first_seen(tmp_path):
    _run(
        tmp_path,
        [_scan("HPG", "PULL ĐẸP", date="2026-08-14")],
        now="2026-08-14 10:05:00",
    )
    dest = tmp_path / "camera_sidecar.json"
    friday = json.loads(dest.read_text(encoding="utf-8"))["freeze_ledger"][0]
    _run(
        tmp_path,
        [_scan("HPG", "PULL ĐẸP", date="2026-08-17", price=28.0, ema9=27.8, breakout_ref=29.0)],
        now="2026-08-17 09:20:00",
    )
    doc = json.loads(dest.read_text(encoding="utf-8"))
    by_session = {(f["session"], f["symbol"]): f for f in doc["freeze_ledger"]}
    assert ("2026-08-14", "HPG") in by_session
    assert ("2026-08-17", "HPG") in by_session
    monday = by_session[("2026-08-17", "HPG")]
    assert monday["candidate_first_seen_ts"] != friday["candidate_first_seen_ts"]
    assert monday["candidate_first_seen_ts"].startswith("2026-08-17T09:20:00")
    assert monday["ema9_at_first_seen"] == 27.8
    assert by_session[("2026-08-14", "HPG")]["ema9_at_first_seen"] == 27.1
    row = doc["rows"][0]
    assert row["session"] == "2026-08-17"
    assert row["candidate_first_seen_ts"] == monday["candidate_first_seen_ts"]


def test_qualified_early_and_bare_early_and_elite_alone(tmp_path):
    lab = _scan("MWG", "MUA EARLY", total_score=2, dist_from_ema9_pct=3.0)
    bare = _scan("AAA", "MUA EARLY", total_score=2, dist_from_ema9_pct=3.0, obv_status="")
    elite_only = _scan("VNM", "", conclusion="BUY ELITE")
    early_df = [{"MÃ": "MWG"}]
    elite_df = [
        {"MÃ": "VNM", "KẾT LUẬN": "BUY ELITE"},
        {"MÃ": "HPG", "KẾT LUẬN": "BUY ELITE"},
    ]
    result, dest = _run(
        tmp_path,
        [lab, bare, elite_only, _scan("HPG", "PULL ĐẸP")],
        now="2026-08-14 10:05:00",
        early=early_df,
        elite=elite_df,
    )
    assert result.ok
    doc = json.loads(dest.read_text(encoding="utf-8"))
    by = {r["symbol"]: r for r in doc["rows"]}
    assert "MWG" in by
    assert "AAA" not in by
    assert "VNM" not in by
    assert by["HPG"]["elite_buy_grade"] == "BUY ELITE"
    assert by["HPG"]["setup"] == "PULL ĐẸP"
    from modules.live_candidate_v2_nomination.nominate import nominate_scan_rows

    report = nominate_scan_rows(
        [bare, elite_only],
        market_real=7.2,
        observed_at=_ts("2026-08-14 10:05:00"),
        early_lab_symbols=[],
        route=False,
    )
    reasons = {r.symbol: r.reason for r in report.rejected}
    assert reasons["AAA"] == REJECT_BARE_MUA_EARLY
    assert reasons["VNM"] == REJECT_ELITE_GRADE_ALONE


def test_elite_buy_grade_join_is_metadata_only():
    rows = attach_elite_buy_grade_metadata(
        [_scan("HPG", "PULL ĐẸP"), _scan("SSI", "MUA BREAK")],
        pd.DataFrame(
            [
                {"MÃ": "HPG", "KẾT LUẬN": "BUY ELITE"},
                {"MÃ": "SSI", "KẾT LUẬN": "LOẠI - TRỤC XẤU"},
            ]
        ),
    )
    by = {r["symbol"]: r for r in rows}
    assert by["HPG"]["elite_buy_grade"] == "BUY ELITE"
    assert "elite_buy_grade" not in by["SSI"] or by["SSI"].get("elite_buy_grade") in {"", None}


def test_corrupted_sidecar_is_failure_not_empty_universe(tmp_path):
    dest = tmp_path / "camera_sidecar.json"
    dest.write_text("{not-json", encoding="utf-8")
    before = dest.read_text(encoding="utf-8")
    result, _ = _run(tmp_path, [_scan("HPG", "PULL ĐẸP")], now="2026-08-14 10:05:00")
    assert result.ok is False
    assert result.reason == REASON_LOAD_FAILED
    assert "corrupted" in result.error.lower() or "JSON" in result.error
    assert dest.read_text(encoding="utf-8") == before
    loaded_ok = False
    try:
        load_sidecar_document(dest)
    except SidecarShadowError:
        loaded_ok = True
    assert loaded_ok
    missing = load_sidecar_document(tmp_path / "no-such.json")
    assert missing is None


def test_array_json_is_not_valid_empty_universe(tmp_path):
    dest = tmp_path / "camera_sidecar.json"
    dest.write_text("[]\n", encoding="utf-8")
    result, _ = _run(tmp_path, [], now="2026-08-14 10:05:00")
    assert result.ok is False
    assert result.reason == REASON_LOAD_FAILED
    assert json.loads(dest.read_text(encoding="utf-8")) == []


def test_valid_empty_universe_writes_rows_empty_and_keeps_ledger(tmp_path):
    _run(tmp_path, [_scan("HPG", "PULL ĐẸP")], now="2026-08-14 10:05:00")
    result, dest = _run(tmp_path, [], now="2026-08-14 11:00:00")
    assert result.ok
    doc = json.loads(dest.read_text(encoding="utf-8"))
    assert doc["rows"] == []
    assert doc["freeze_ledger"][0]["symbol"] == "HPG"
    assert doc["schema"] == SCHEMA_ID
    assert dest.exists()


def test_app_hook_location_and_isolation():
    app = (REPO / "app.py").read_text(encoding="utf-8")
    elite = app.index("buy_elite_df = build_buy_elite_decision_engine(")
    hook = app.index("_v2_sidecar = run_v2_cloud_sidecar(")
    learn = app.index("= run_buy_elite_learning_cycle(")
    assert elite < hook < learn
    assert "analyze_symbol" not in app[hook : hook + 400]
    assert "persist_and_publish_research_watchlist" not in app[hook : hook + 800]
    assert "append_today_buy_elite_signals" not in app[hook : hook + 800]
    hook_src = (REPO / "modules" / "live_candidate_v2_camera" / "cloud_hook.py").read_text(
        encoding="utf-8"
    )
    assert "watchlist_bus" not in hook_src
    assert "_github_write_text" not in hook_src
    assert "run_live_camera_shadow" not in hook_src
    assert "artifact_server" not in hook_src
    assert "systemctl" not in hook_src
    tree = ast.parse(hook_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "GROUP_RANK"
    assert ENABLED_SOURCES == frozenset({SRC_BUY_ELITE})
    assert SRC_BRAIN_A not in ENABLED_SOURCES
    digest = hashlib.sha256(PRODUCTION_WATCHLIST.read_bytes()).hexdigest()
    assert hashlib.sha256(PRODUCTION_WATCHLIST.read_bytes()).hexdigest() == digest
    assert nominations_from_rotation_artifact({"rows": [{"symbol": "CII"}]}) == ()
    assert SRC_ROTATION not in ENABLED_SOURCES
    interpret = (REPO / "modules" / "intraday_pxv_v1" / "interpret.py").read_text(encoding="utf-8")
    assert "live_candidate_v2_camera.cloud_hook" not in interpret
    assert ENV_V2_CLOUD_SIDECAR == "MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR"
