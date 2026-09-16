"""LIVE CANDIDATE V2 Slice 3A — gated Cloud local sidecar + restart-safe freeze.

No GitHub publish. No VPS. No runner. Candidate != BUY.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import types
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
    ENV_V2_CLOUD_SIDECAR_TRUTHY,
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


def _app_source() -> str:
    return (REPO / "app.py").read_text(encoding="utf-8")


def _v2_hook_try_node(src: str | None = None) -> ast.Try:
    tree = ast.parse(src or _app_source())
    for node in tree.body:
        if isinstance(node, ast.Try):
            blob = ast.dump(node)
            if "cloud_hook" in blob or "run_v2_cloud_sidecar" in blob:
                return node
    raise AssertionError("V2 sidecar Try block not found in app.py")


def test_app_hook_location_and_isolation():
    app = _app_source()
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


def test_gate_off_missing_sidecar_is_irrelevant(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_V2_CLOUD_SIDECAR, raising=False)
    dest = tmp_path / "missing" / "camera_sidecar.json"
    assert not dest.exists()
    result = run_v2_cloud_sidecar(
        scan_rows=[_scan("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=_ts("2026-08-14 10:05:00"),
        path=dest,
        env={},
    )
    assert result.ok is True
    assert result.skipped is True
    assert result.reason == REASON_GATE_OFF
    assert not dest.exists()
    assert not dest.parent.exists()


def test_gate_off_corrupted_sidecar_is_irrelevant(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_V2_CLOUD_SIDECAR, raising=False)
    dest = tmp_path / "camera_sidecar.json"
    dest.write_text("{not-json", encoding="utf-8")
    before = dest.read_text(encoding="utf-8")
    result = run_v2_cloud_sidecar(
        scan_rows=[_scan("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=_ts("2026-08-14 10:05:00"),
        path=dest,
        env={},
    )
    assert result.ok is True
    assert result.skipped is True
    assert result.reason == REASON_GATE_OFF
    assert dest.read_text(encoding="utf-8") == before


def test_gate_off_run_does_not_load_write_or_nominate(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_V2_CLOUD_SIDECAR, raising=False)
    import modules.live_candidate_v2_camera.cloud_hook as ch

    def boom(name):
        def _inner(*args, **kwargs):
            raise AssertionError(f"{name} must not run when gate OFF")

        return _inner

    monkeypatch.setattr(ch, "load_sidecar_document", boom("load_sidecar_document"))
    monkeypatch.setattr(ch, "write_sidecar", boom("write_sidecar"))
    monkeypatch.setattr(ch, "build_sidecar_from_scan", boom("build_sidecar_from_scan"))
    result = run_v2_cloud_sidecar(
        scan_rows=[_scan("HPG", "PULL ĐẸP")],
        market_real=7.2,
        observed_at=_ts("2026-08-14 10:05:00"),
        path=tmp_path / "camera_sidecar.json",
        env={},
    )
    assert result.reason == REASON_GATE_OFF
    assert not (tmp_path / "camera_sidecar.json").exists()


def test_app_has_no_unconditional_v2_import():
    src = _app_source()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert "live_candidate_v2" not in (node.module or "")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "live_candidate_v2" not in alias.name


def test_app_hook_gates_import_and_call_before_learning():
    src = _app_source()
    tree = ast.parse(src)
    try_node = _v2_hook_try_node(src)
    gated_if = None
    for node in try_node.body:
        if isinstance(node, ast.If):
            inner = ast.dump(node)
            if "run_v2_cloud_sidecar" in inner and "cloud_hook" in inner:
                gated_if = node
                break
    assert gated_if is not None
    if_src = ast.get_source_segment(src, gated_if) or ""
    assert ENV_V2_CLOUD_SIDECAR in ast.get_source_segment(src, try_node)
    assert "cloud_hook" in if_src
    assert "run_v2_cloud_sidecar" in if_src
    body_dump = ast.dump(ast.Module(body=list(gated_if.body), type_ignores=[]))
    orelse_dump = ast.dump(ast.Module(body=list(gated_if.orelse), type_ignores=[]))
    assert "cloud_hook" in body_dump
    assert "run_v2_cloud_sidecar" in body_dump
    assert "cloud_hook" not in orelse_dump
    assert "run_v2_cloud_sidecar" not in orelse_dump
    truthy = {
        const.value
        for node in ast.walk(gated_if.test)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert truthy == set(ENV_V2_CLOUD_SIDECAR_TRUTHY)

    elite = None
    learn = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if not isinstance(func, ast.Name):
            continue
        if func.id == "build_buy_elite_decision_engine":
            elite = node
        elif func.id == "run_buy_elite_learning_cycle":
            learn = node
    assert elite is not None and learn is not None
    assert elite.lineno < try_node.lineno < learn.lineno
    for inner in ast.walk(try_node):
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
            assert inner.func.id != "run_buy_elite_learning_cycle"
            assert inner.func.id != "build_buy_elite_decision_engine"


def test_extracted_app_hook_gate_off_does_not_call_or_import_v2(monkeypatch):
    monkeypatch.delenv(ENV_V2_CLOUD_SIDECAR, raising=False)
    src = _app_source()
    try_node = _v2_hook_try_node(src)
    hook_src = ast.get_source_segment(src, try_node)
    assert hook_src
    script = (
        "import os, sys, types\n"
        "from datetime import datetime\n"
        "from zoneinfo import ZoneInfo\n"
        "import pandas as pd\n"
        "os.environ.pop(%r, None)\n"
        "before = {k for k in sys.modules if 'live_candidate_v2' in k}\n"
        "ns = {\n"
        "    'os': os,\n"
        "    'scan_df': pd.DataFrame([{'symbol': 'HPG'}]),\n"
        "    'market_real': 7.2,\n"
        "    'vn_now': lambda: datetime.now(tz=ZoneInfo('Asia/Ho_Chi_Minh')),\n"
        "    'buy_elite_df': pd.DataFrame(),\n"
        "    'early_buy_lab_df': pd.DataFrame(),\n"
        "    'st': types.SimpleNamespace(warning=lambda msg: (_ for _ in ()).throw(AssertionError(msg))),\n"
        "}\n"
        "hook = %r\n"
        "exec(compile(hook, 'app.py', 'exec'), ns, ns)\n"
        "after = {k for k in sys.modules if 'live_candidate_v2' in k}\n"
        "assert after == before\n"
        "assert '_v2_sidecar' not in ns\n"
        "print('OK')\n"
    ) % (ENV_V2_CLOUD_SIDECAR, hook_src)
    env = {k: v for k, v in os.environ.items() if k != ENV_V2_CLOUD_SIDECAR}
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


def test_extracted_app_hook_v2_exception_does_not_block_learning(monkeypatch):
    monkeypatch.setenv(ENV_V2_CLOUD_SIDECAR, "1")
    src = _app_source()
    try_node = _v2_hook_try_node(src)
    hook_src = ast.get_source_segment(src, try_node)
    assert hook_src

    def boom(**kwargs):
        raise RuntimeError("sidecar boom")

    import modules.live_candidate_v2_camera.cloud_hook as ch

    monkeypatch.setattr(ch, "run_v2_cloud_sidecar", boom)
    warnings: list[str] = []
    order: list[str] = []
    ns = {
        "os": os,
        "scan_df": pd.DataFrame([{"symbol": "HPG"}]),
        "market_real": 7.2,
        "vn_now": lambda: datetime.now(tz=VN),
        "buy_elite_df": pd.DataFrame(),
        "early_buy_lab_df": pd.DataFrame(),
        "st": types.SimpleNamespace(warning=lambda msg: warnings.append(str(msg))),
    }
    order.append("elite")
    exec(compile(hook_src, "app.py", "exec"), ns, ns)
    order.append("learn")
    assert order == ["elite", "learn"]
    assert warnings and "sidecar boom" in warnings[0]


def test_importing_cloud_hook_gate_off_causes_no_v2_io():
    script = r"""
import builtins
import os
import sys

os.environ.pop("MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR", None)
hits = []
real_open = builtins.open

def guarded_open(file, *args, **kwargs):
    path = str(file).replace("\\", "/")
    if any(n in path for n in ("camera_sidecar", "nominations.json", "dynamic_watchlist.json")):
        hits.append(path)
        raise AssertionError("V2 artifact I/O at import: " + path)
    return real_open(file, *args, **kwargs)

builtins.open = guarded_open
from modules.live_candidate_v2_camera.cloud_hook import run_v2_cloud_sidecar, v2_cloud_sidecar_enabled
assert v2_cloud_sidecar_enabled() is False
assert hits == []
assert "requests" not in sys.modules
assert "vnstock" not in sys.modules
assert "github" not in sys.modules
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
result = run_v2_cloud_sidecar(
    scan_rows=[{"symbol": "HPG", "group": "PULL ĐẸP", "date": "2026-08-14"}],
    market_real=7.2,
    observed_at=datetime(2026, 8, 14, 10, 5, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
    path=Path("research/live_candidate_v2_camera_sidecar/camera_sidecar.json"),
    env={},
)
assert result.skipped is True
assert result.reason == "GATE_OFF"
assert hits == []
print("OK")
"""
    env = {k: v for k, v in os.environ.items() if k != ENV_V2_CLOUD_SIDECAR}
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


def test_off_path_has_no_github_network_vps_provider_call():
    hook_src = (REPO / "modules" / "live_candidate_v2_camera" / "cloud_hook.py").read_text(
        encoding="utf-8"
    )
    sidecar_src = (REPO / "modules" / "live_candidate_v2_camera" / "sidecar.py").read_text(
        encoding="utf-8"
    )
    app = _app_source()
    try_src = ast.get_source_segment(app, _v2_hook_try_node(app)) or ""
    for blob in (hook_src, sidecar_src, try_src):
        assert "watchlist_bus" not in blob
        assert "_github_write_text" not in blob
        assert "github.com" not in blob
        assert "requests." not in blob
        assert "vnstock" not in blob
        assert "run_live_camera_shadow" not in blob
        assert "artifact_server" not in blob
        assert "systemctl" not in blob
        assert "/opt/mrbot-camera" not in blob
    tree = ast.parse(hook_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "requests" not in (node.module or "")
            assert "vnstock" not in (node.module or "")
            assert "github" not in (node.module or "")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in {"requests", "vnstock", "github"}
