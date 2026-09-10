"""TEMP Cloud restore diagnostic: sanitizer + no extra restore GET."""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.persistence import PersistenceStatus
from modules.edge_research.restore_diagnostic import (
    HTTP_401,
    HTTP_404,
    TIMEOUT,
    autonomous_diagnostic_from_restore_result,
    challenger_diagnostic_from_status,
    classify_restore_detail,
    contains_unsafe_material,
    format_restore_diagnostic_text,
)


UNSAFE_SAMPLE = (
    "HTTPError: HTTP Error 401 Unauthorized from "
    "https://artifacts.example.com/edge-research/current/bundle.tar.gz "
    "Authorization: Bearer supersecrettokenvalue123 "
    "token=ghp_thisisnotarealtoken "
    "EDGE_RESEARCH_DURABLE_TOKEN=abcd"
)


def test_classify_401():
    out = classify_restore_detail("HTTP load failed: 401")
    assert out["http_class"] == HTTP_401
    assert out["reason"] == "HTTP load failed: 401"
    assert not contains_unsafe_material(out["reason"])
    assert not contains_unsafe_material(out["http_class"])


def test_classify_404():
    out = classify_restore_detail("HTTP load failed: 404")
    assert out["http_class"] == HTTP_404
    out2 = classify_restore_detail("no remote bundle (404)")
    assert out2["http_class"] == HTTP_404
    assert out2["reason"] == "no remote bundle"


def test_classify_timeout():
    out = classify_restore_detail("HTTP load failed: The read operation timed out")
    assert out["http_class"] == TIMEOUT
    assert out["reason"] == TIMEOUT


def test_classify_backend_not_configured():
    out = classify_restore_detail("durable backend not configured")
    assert out["category"] == "BACKEND_NOT_CONFIGURED"
    assert out["reason"] == "durable backend not configured"
    assert out["http_class"] == "n/a"


def test_classify_unsafe_exception_does_not_leak_url_or_token():
    out = classify_restore_detail(UNSAFE_SAMPLE)
    blob = " ".join(out.values())
    assert "https://" not in blob
    assert "artifacts.example.com" not in blob
    assert "Bearer " not in blob
    assert "supersecrettokenvalue123" not in blob
    assert "ghp_" not in blob
    assert "EDGE_RESEARCH_DURABLE_TOKEN=abcd" not in blob
    assert "token=ghp" not in blob.lower()
    assert contains_unsafe_material(UNSAFE_SAMPLE)
    assert not contains_unsafe_material(blob)
    assert out["http_class"] == HTTP_401
    text = format_restore_diagnostic_text(
        challenger=challenger_diagnostic_from_status(
            PersistenceStatus(
                last_result="skipped",
                message=UNSAFE_SAMPLE,
                backend="http",
            )
        ),
        autonomous=autonomous_diagnostic_from_restore_result(
            {"ok": False, "error": UNSAFE_SAMPLE}
        ),
    )
    assert "https://" not in text
    assert "Bearer" not in text
    assert "supersecrettokenvalue123" not in text
    assert "artifacts.example.com" not in text
    assert contains_unsafe_material(text) is False


def test_challenger_diagnostic_reads_existing_status_only(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("try_restore_durable must not be called from diagnostic")

    monkeypatch.setattr(
        "modules.edge_research.persistence.try_restore_durable",
        boom,
    )
    status = PersistenceStatus(
        last_operation="restore",
        last_result="skipped",
        message="durable backend not configured",
        backend="none",
    )
    out = challenger_diagnostic_from_status(status)
    assert out["CHALLENGER_BACKEND_CONFIGURED"] == "NO"
    assert out["CHALLENGER_RESTORE_RESULT"] == "skipped"
    assert out["CHALLENGER_RESTORE_REASON"] == "durable backend not configured"
    assert out["CHALLENGER_HTTP_CLASS"] == "n/a"


def test_autonomous_diagnostic_does_not_call_restore(monkeypatch, tmp_path):
    calls = {"n": 0}

    def fake_restore(*, data_dir=None):
        calls["n"] += 1
        return {"ok": False, "skipped": True, "reason": "durable_backend_disabled"}

    monkeypatch.setattr(
        "modules.edge_research.production_observations_sync.try_restore_production_observations_durable",
        fake_restore,
    )
    from modules.edge_research.autonomous_daily_edge_ui import build_autonomous_daily_edge_ui_view

    edge = tmp_path / "edge"
    view = build_autonomous_daily_edge_ui_view(data_dir=edge)
    assert calls["n"] == 1
    d1 = autonomous_diagnostic_from_restore_result(view.get("durable_restore"))
    d2 = autonomous_diagnostic_from_restore_result(view.get("durable_restore"))
    assert calls["n"] == 1
    assert d1 == d2
    assert d1["AUTONOMOUS_BACKEND_CONFIGURED"] == "NO"
    assert d1["AUTONOMOUS_RESTORE_RESULT"] == "skipped"


def test_autonomous_http_401_from_existing_return_dict():
    out = autonomous_diagnostic_from_restore_result({"ok": False, "error": "HTTP:401"})
    assert out["AUTONOMOUS_BACKEND_CONFIGURED"] == "YES"
    assert out["AUTONOMOUS_RESTORE_RESULT"] == "error"
    assert out["AUTONOMOUS_HTTP_CLASS"] == HTTP_401
    assert out["AUTONOMOUS_RESTORE_REASON"] == "HTTP load failed: 401"


def test_no_camera_modules_imported_by_diagnostic():
    paths = [
        REPO / "modules/edge_research/restore_diagnostic.py",
        REPO / "modules/edge_research/autonomous_daily_edge_ui.py",
        REPO / "modules/edge_research/ui.py",
    ]
    forbidden = (
        "live_candidate",
        "live_shadow_transport",
        "live_candidate_pxv_ui",
        "intraday_memory",
        "intraday_pxv_v1",
    )
    for path in paths:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            joined = " ".join(names)
            for bad in forbidden:
                assert bad not in joined, f"{path} imports {joined}"


def test_research_execution_path_unchanged():
    diag = (REPO / "modules/edge_research/restore_diagnostic.py").read_text(encoding="utf-8")
    assert "run_discovery" not in diag
    assert "run_challenger" not in diag
    assert "publish_durable" not in diag
    assert "try_restore_durable" not in diag
    assert "try_restore_production_observations_durable" not in diag

    import modules.edge_research.ui as ui_mod

    helper = inspect.getsource(ui_mod._render_durable_restore_diagnostic)
    assert "try_restore_durable" not in helper
    assert "try_restore_production_observations_durable" not in helper
    assert "read_persistence_status" in helper
    assert "run_discovery" not in helper
    assert "Durable Restore Diagnostic — TEMP" in helper

    panel = inspect.getsource(ui_mod.render_edge_research_panel)
    assert "_render_durable_restore_diagnostic" in panel
    assert panel.index("build_autonomous_daily_edge_ui_view") < panel.index("engine.initialize")
    assert panel.index("engine.initialize") < panel.index("_render_durable_restore_diagnostic")


def test_ui_expander_does_not_change_metric_labels():
    src = (REPO / "modules/edge_research/ui.py").read_text(encoding="utf-8")
    assert 'st.metric("Engine status"' in src
    assert 'st.metric("Hypotheses"' in src
    assert 'st.metric("Observed Market episodes"' in src
    assert "Chưa có autonomous daily research session trong production_observations." in (
        REPO / "modules/edge_research/autonomous_daily_edge_ui.py"
    ).read_text(encoding="utf-8")
