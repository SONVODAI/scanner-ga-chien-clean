"""Read-only Live Candidate V2 Brain A panel.

Current-cycle Gate B GET only. Zero candidates is valid. Not BUY.
"""

from __future__ import annotations

import ast
import json
import types
from pathlib import Path

from modules.live_candidate_v2_camera.github_bus import (
    STATUS_INVALID_DOCUMENT,
    STATUS_OK_EMPTY,
    STATUS_OK_ROWS,
    STATUS_TRANSPORT_ERROR,
    V2FetchResult,
)
from modules.live_candidate_v2_camera.ui import (
    EMPTY_MESSAGE,
    KIND_FAILURE,
    KIND_OK_EMPTY,
    KIND_OK_ROWS,
    KIND_UNAVAILABLE,
    OPERATOR_COLUMNS,
    PANEL_TITLE,
    SEMANTIC_CAPTION,
    UNAVAILABLE_MESSAGE,
    project_operator_rows,
    render_live_candidate_v2_panel,
    unavailable_v2_ui,
    v2_ui_from_failure,
    v2_ui_from_get,
)

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.sample.json"
UI_PY = REPO / "modules" / "live_candidate_v2_camera" / "ui.py"
APP_PY = REPO / "app.py"
PROD_WATCHLIST = REPO / "data" / "live_candidate" / "dynamic_watchlist.json"
_TOK = "sectok"


class _FakeSt:
    def __init__(self):
        self.markdowns: list[str] = []
        self.captions: list[str] = []
        self.warnings: list[str] = []
        self.tables: list[object] = []
        self.session_state: dict = {}

    def markdown(self, msg, **kwargs):
        self.markdowns.append(str(msg))

    def caption(self, msg, **kwargs):
        self.captions.append(str(msg))

    def warning(self, msg, **kwargs):
        self.warnings.append(str(msg))

    def dataframe(self, data, **kwargs):
        self.tables.append(data)

    def error(self, msg, **kwargs):
        raise AssertionError(f"error must not be used: {msg}")


def _sample_doc(*, rows=None, ledger=None) -> dict:
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if rows is not None:
        doc["rows"] = rows
    if ledger is not None:
        doc["freeze_ledger"] = ledger
    return doc


def _render(view) -> _FakeSt:
    st = _FakeSt()
    render_live_candidate_v2_panel(view, st_module=st)
    return st


def test_ui_module_has_no_fetch_watchlist_or_session_cache():
    src = UI_PY.read_text(encoding="utf-8")
    assert "fetch_v2_sidecar" not in src
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "dynamic_watchlist.json" not in node.value
        if isinstance(node, ast.Attribute):
            assert node.attr != "session_state"
    assert "session_state" not in src
    assert "snapshot_text" not in src
    assert "source_action" not in src
    assert "source_action" not in {key for _label, key in OPERATOR_COLUMNS}
    assert "BUY_READY" not in src
    assert "ACTIONABLE" not in src
    assert "run_v2_cloud_sidecar" not in src


def test_importing_ui_does_not_import_github_bus():
    import os
    import subprocess
    import sys

    script = (
        "import sys\n"
        "sys.modules.pop('modules.live_candidate_v2_camera.github_bus', None)\n"
        "sys.modules.pop('modules.live_candidate_v2_camera.ui', None)\n"
        "import modules.live_candidate_v2_camera.ui as ui\n"
        "assert ui.unavailable_v2_ui().kind == 'UNAVAILABLE'\n"
        "assert 'modules.live_candidate_v2_camera.github_bus' not in sys.modules\n"
        "print('OK')\n"
    )
    env = dict(os.environ)
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


def test_ok_empty_is_calm_not_warning_or_table():
    doc = _sample_doc(rows=[], ledger=[{"session": "2026-08-14", "symbol": "HPG"}])
    fetched = V2FetchResult(ok=True, status=STATUS_OK_EMPTY, document=doc, n_rows=0)
    view = v2_ui_from_get(fetched)
    assert view.kind == KIND_OK_EMPTY
    assert view.rows == ()
    st = _render(view)
    assert PANEL_TITLE in st.markdowns[0]
    assert EMPTY_MESSAGE in st.markdowns
    assert UNAVAILABLE_MESSAGE not in st.markdowns
    assert st.warnings == []
    assert st.tables == []
    assert SEMANTIC_CAPTION in st.captions
    assert all("HPG" not in m for m in st.markdowns)


def test_ok_empty_ignores_nonempty_freeze_ledger():
    ledger = [
        {
            "session": "2026-08-14",
            "symbol": "HPG",
            "candidate_first_seen_ts": "2026-08-14T10:05:00+07:00",
            "price_at_first_seen": 27.5,
            "ema9_at_first_seen": 27.1,
            "breakout_ref_at_first_seen": 28.0,
        }
    ]
    doc = _sample_doc(rows=[], ledger=ledger)
    view = v2_ui_from_get(
        V2FetchResult(ok=True, status=STATUS_OK_EMPTY, document=doc, n_rows=0)
    )
    table = project_operator_rows(view.rows)
    assert table == []
    st = _render(view)
    joined = "\n".join(st.markdowns + st.captions)
    assert "HPG" not in joined
    assert EMPTY_MESSAGE in st.markdowns


def test_ok_rows_renders_exact_stored_values_not_recomputed():
    doc = _sample_doc()
    row = doc["rows"][0]
    first_seen = row["candidate_first_seen_ts"]
    ema = row["ema9_at_first_seen"]
    brk = row["breakout_ref_at_first_seen"]
    price = row["price_at_first_seen"]
    fetched = V2FetchResult(
        ok=True, status=STATUS_OK_ROWS, document=doc, n_rows=len(doc["rows"])
    )
    view = v2_ui_from_get(fetched)
    assert view.kind == KIND_OK_ROWS
    table = project_operator_rows(view.rows)
    assert table[0]["Symbol"] == row["symbol"]
    assert table[0]["Setup"] == row["setup"]
    assert table[0]["Source"] == row["nomination_source"]
    assert table[0]["Why"] == row["nomination_reason"]
    assert table[0]["Detail"] == row["source_reason"]
    assert table[0]["Waiting for"] == row["observation_intent"]
    assert table[0]["Watch ref"] == row["observation_reference"]
    assert table[0]["First seen"] == first_seen
    assert table[0]["Frozen price"] == price
    assert table[0]["Frozen EMA9"] == ema
    assert table[0]["Frozen breakout"] == brk
    assert table[0]["Elite grade (metadata)"] == row["elite_buy_grade"]
    assert "source_action" not in table[0]
    assert "Source action" not in table[0]
    st = _render(view)
    assert st.tables and st.tables[0] == table
    assert EMPTY_MESSAGE not in st.markdowns
    assert st.warnings == []
    assert table[0]["First seen"] == "2026-08-14T10:05:00+07:00"
    assert table[0]["Frozen EMA9"] == 27.1


def test_source_falls_back_to_source_when_nomination_source_missing():
    rec = {"symbol": "HPG", "source": "brain_a_scan_setup"}
    table = project_operator_rows([rec])
    assert table[0]["Source"] == "brain_a_scan_setup"


def test_blank_elite_grade_is_emdash_metadata_only():
    rec = {"symbol": "SSI", "elite_buy_grade": ""}
    table = project_operator_rows([rec])
    assert table[0]["Elite grade (metadata)"] == "—"


def test_unavailable_is_not_empty_candidate_sentence():
    view = unavailable_v2_ui()
    st = _render(view)
    assert UNAVAILABLE_MESSAGE in st.markdowns
    assert EMPTY_MESSAGE not in st.markdowns
    assert st.tables == []
    assert st.warnings == []
    assert SEMANTIC_CAPTION in st.captions


def test_put_and_get_failure_are_status_only_not_empty_or_table():
    for status in (STATUS_TRANSPORT_ERROR, STATUS_INVALID_DOCUMENT, "NOT_FOUND"):
        view = v2_ui_from_failure(status=status, error=f"token {_TOK} ghp_abcdefghijklmnopqrstuvwxyz012345")
        st = _render(view)
        assert EMPTY_MESSAGE not in st.markdowns
        assert UNAVAILABLE_MESSAGE not in st.markdowns
        assert st.tables == []
        assert any(f"status={status}" in c or "status=" in c for c in st.captions)
        joined = "\n".join(st.markdowns + st.captions + st.warnings)
        assert _TOK not in joined
        assert "ghp_" not in joined
        assert "Authorization" not in joined


def test_get_failure_from_fetch_result_is_failure_kind():
    view = v2_ui_from_get(
        V2FetchResult(
            ok=False,
            status=STATUS_INVALID_DOCUMENT,
            document=None,
            error="invalid or missing schema",
        )
    )
    assert view.kind == KIND_FAILURE
    st = _render(view)
    assert EMPTY_MESSAGE not in st.markdowns
    assert st.tables == []


def test_renderer_does_not_call_fetch(monkeypatch):
    import modules.live_candidate_v2_camera.github_bus as gb
    import modules.live_candidate_v2_camera.ui as ui

    def boom(*a, **k):
        raise AssertionError("renderer must not call fetch_v2_sidecar")

    monkeypatch.setattr(gb, "fetch_v2_sidecar", boom)
    monkeypatch.setattr(ui, "fetch_v2_sidecar", boom, raising=False)
    doc = _sample_doc(rows=[])
    view = v2_ui_from_get(
        V2FetchResult(ok=True, status=STATUS_OK_EMPTY, document=doc, n_rows=0)
    )
    _render(view)
    _render(unavailable_v2_ui())
    _render(v2_ui_from_failure(status=STATUS_TRANSPORT_ERROR))


def test_no_buy_actionable_nav_derived_in_projection():
    doc = _sample_doc()
    table = project_operator_rows(doc["rows"])
    blob = json.dumps(table, ensure_ascii=False)
    assert "BUY_READY" not in blob
    assert "ACTIONABLE" not in blob
    assert "NAV" not in blob
    assert "source_action" not in blob
    assert "MUA PULL ĐẸP" not in blob
    src = UI_PY.read_text(encoding="utf-8")
    assert SEMANTIC_CAPTION in src
    assert "Candidate ≠ BUY" in SEMANTIC_CAPTION


def test_app_placement_and_gate_captions_unchanged():
    src = APP_PY.read_text(encoding="utf-8")
    dash = src.index("# DEFAULT MAIN DASHBOARD")
    ui_call = src.index("render_live_candidate_v2_panel(")
    ai = src.index('with st.expander("🤖 AI Recommendation", expanded=False):')
    pxv = src.index("render_live_candidate_pxv_panel()")
    assert pxv < dash
    assert dash < ui_call < ai
    assert 'st.caption(f"LCV2-GATE-A-WROTE rows={_v2_sidecar.n_rows}")' in src
    assert "LCV2-GATE-B-GITHUB status={_v2_fetched.status} rows={_v2_fetched.n_rows}" in src
    assert src.count("fetch_v2_sidecar()") == 1
    assert "_v2_ui = None" in src
    assert "_v2_ui = v2_ui_from_get(_v2_fetched)" in src
    assert "v2_ui_from_failure(" in src
    hook = src[src.index("_v2_ui = None") : src.index("except Exception as e:")]
    assert "st.session_state" not in hook
    assert "dynamic_watchlist.json" not in hook
    assert PROD_WATCHLIST.exists()


def test_gate_a_b_conditions_still_nested():
    src = APP_PY.read_text(encoding="utf-8")
    assert '_v2_sidecar.reason == "WROTE"' in src
    assert '_v2_pub_gate in ("1", "true", "yes", "on")' in src
    assert 'env={"MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH": _v2_pub_gate}' in src
    assert "run_v2_cloud_sidecar(" in src
    tree = ast.parse(src)
    try_node = None
    for node in tree.body:
        if isinstance(node, ast.Try) and "run_v2_cloud_sidecar" in ast.dump(node):
            try_node = node
            break
    assert try_node is not None
    dump = ast.dump(try_node)
    assert "maybe_publish_v2_sidecar" in dump
    assert "fetch_v2_sidecar" in dump
    assert "render_live_candidate_pxv_panel" not in dump


def test_exec_hook_binds_current_cycle_get_without_second_fetch(monkeypatch):
    import ast as ast_mod
    import os
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import pandas as pd

    from modules.live_candidate_v2_camera.cloud_hook import REASON_WROTE
    from modules.live_candidate_v2_camera.contract import (
        ENV_V2_CLOUD_SIDECAR,
        ENV_V2_GITHUB_PUBLISH,
    )
    from modules.live_candidate_v2_camera.github_bus import (
        STATUS_PUBLISHED,
        V2PublishResult,
    )
    import modules.live_candidate_v2_camera.cloud_hook as ch
    import modules.live_candidate_v2_camera.github_bus as gb

    src = APP_PY.read_text(encoding="utf-8")
    tree = ast_mod.parse(src)
    try_node = None
    for node in tree.body:
        if isinstance(node, ast_mod.Try) and "run_v2_cloud_sidecar" in ast_mod.dump(node):
            try_node = node
            break
    hook = ast_mod.get_source_segment(src, try_node)
    doc = _sample_doc(rows=[])
    fetch_calls: list[int] = []

    class FakeSidecar:
        ok = True
        skipped = False
        reason = REASON_WROTE
        n_rows = 0
        error = ""
        path = "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"
        snapshot_text = json.dumps(doc)

    def runner(**kwargs):
        return FakeSidecar()

    def publisher(**kwargs):
        return V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED)

    def fetcher(**kwargs):
        fetch_calls.append(1)
        return V2FetchResult(ok=True, status=STATUS_OK_EMPTY, document=doc, n_rows=0)

    orig_run = ch.run_v2_cloud_sidecar
    orig_pub = gb.maybe_publish_v2_sidecar
    orig_fetch = gb.fetch_v2_sidecar
    ch.run_v2_cloud_sidecar = runner  # type: ignore[assignment]
    gb.maybe_publish_v2_sidecar = publisher  # type: ignore[assignment]
    gb.fetch_v2_sidecar = fetcher  # type: ignore[assignment]
    captions: list[str] = []
    warnings: list[str] = []
    ns = {
        "os": os,
        "scan_df": pd.DataFrame([{"symbol": "HPG"}]),
        "market_real": 7.2,
        "vn_now": lambda: datetime(2026, 8, 14, 10, 5, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        "buy_elite_df": pd.DataFrame(),
        "early_buy_lab_df": pd.DataFrame(),
        "st": types.SimpleNamespace(
            warning=lambda msg: warnings.append(str(msg)),
            caption=lambda msg: captions.append(str(msg)),
            secrets=types.SimpleNamespace(get=lambda *a, **k: ""),
        ),
    }
    saved_a = os.environ.get(ENV_V2_CLOUD_SIDECAR)
    saved_b = os.environ.get(ENV_V2_GITHUB_PUBLISH)
    try:
        os.environ[ENV_V2_CLOUD_SIDECAR] = "1"
        os.environ[ENV_V2_GITHUB_PUBLISH] = "1"
        exec(compile(hook, "app.py", "exec"), ns, ns)
    finally:
        ch.run_v2_cloud_sidecar = orig_run
        gb.maybe_publish_v2_sidecar = orig_pub
        gb.fetch_v2_sidecar = orig_fetch
        os.environ.pop(ENV_V2_CLOUD_SIDECAR, None)
        os.environ.pop(ENV_V2_GITHUB_PUBLISH, None)
        if saved_a is not None:
            os.environ[ENV_V2_CLOUD_SIDECAR] = saved_a
        if saved_b is not None:
            os.environ[ENV_V2_GITHUB_PUBLISH] = saved_b
    assert fetch_calls == [1]
    assert any(c.startswith("LCV2-GATE-A-WROTE rows=") for c in captions)
    assert any(c.startswith("LCV2-GATE-B-GITHUB status=OK_EMPTY") for c in captions)
    view = ns["_v2_ui"]
    assert view.kind == KIND_OK_EMPTY
    st = _render(view)
    assert EMPTY_MESSAGE in st.markdowns
    assert fetch_calls == [1]


def test_exec_hook_gate_b_off_stays_unavailable():
    import ast as ast_mod
    import os
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import pandas as pd

    from modules.live_candidate_v2_camera.cloud_hook import REASON_WROTE
    from modules.live_candidate_v2_camera.contract import (
        ENV_V2_CLOUD_SIDECAR,
        ENV_V2_GITHUB_PUBLISH,
    )
    from modules.live_candidate_v2_camera.ui import unavailable_v2_ui
    import modules.live_candidate_v2_camera.cloud_hook as ch

    src = APP_PY.read_text(encoding="utf-8")
    tree = ast_mod.parse(src)
    try_node = None
    for node in tree.body:
        if isinstance(node, ast_mod.Try) and "run_v2_cloud_sidecar" in ast_mod.dump(node):
            try_node = node
            break
    hook = ast_mod.get_source_segment(src, try_node)

    class FakeSidecar:
        ok = True
        skipped = False
        reason = REASON_WROTE
        n_rows = 0
        error = ""
        path = "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"
        snapshot_text = "{}"

    orig_run = ch.run_v2_cloud_sidecar
    ch.run_v2_cloud_sidecar = lambda **k: FakeSidecar()  # type: ignore[assignment]
    captions: list[str] = []
    ns = {
        "os": os,
        "_v2_ui": unavailable_v2_ui(),
        "scan_df": pd.DataFrame([{"symbol": "HPG"}]),
        "market_real": 7.2,
        "vn_now": lambda: datetime(2026, 8, 14, 10, 5, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        "buy_elite_df": pd.DataFrame(),
        "early_buy_lab_df": pd.DataFrame(),
        "st": types.SimpleNamespace(
            warning=lambda msg: (_ for _ in ()).throw(AssertionError(msg)),
            caption=lambda msg: captions.append(str(msg)),
            secrets=types.SimpleNamespace(get=lambda *a, **k: ""),
        ),
    }
    saved_a = os.environ.get(ENV_V2_CLOUD_SIDECAR)
    saved_b = os.environ.get(ENV_V2_GITHUB_PUBLISH)
    try:
        os.environ[ENV_V2_CLOUD_SIDECAR] = "1"
        os.environ.pop(ENV_V2_GITHUB_PUBLISH, None)
        exec(compile(hook, "app.py", "exec"), ns, ns)
    finally:
        ch.run_v2_cloud_sidecar = orig_run
        os.environ.pop(ENV_V2_CLOUD_SIDECAR, None)
        os.environ.pop(ENV_V2_GITHUB_PUBLISH, None)
        if saved_a is not None:
            os.environ[ENV_V2_CLOUD_SIDECAR] = saved_a
        if saved_b is not None:
            os.environ[ENV_V2_GITHUB_PUBLISH] = saved_b
    assert ns["_v2_ui"].kind == KIND_UNAVAILABLE
    assert captions == ["LCV2-GATE-A-WROTE rows=0"]
    st = _render(ns["_v2_ui"])
    assert UNAVAILABLE_MESSAGE in st.markdowns
    assert EMPTY_MESSAGE not in st.markdowns


def test_exec_hook_put_failure_binds_failure_not_empty():
    import ast as ast_mod
    import os
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import pandas as pd

    from modules.live_candidate_v2_camera.cloud_hook import REASON_WROTE
    from modules.live_candidate_v2_camera.contract import (
        ENV_V2_CLOUD_SIDECAR,
        ENV_V2_GITHUB_PUBLISH,
    )
    from modules.live_candidate_v2_camera.github_bus import V2PublishResult
    from modules.live_candidate_v2_camera.ui import unavailable_v2_ui
    import modules.live_candidate_v2_camera.cloud_hook as ch
    import modules.live_candidate_v2_camera.github_bus as gb

    src = APP_PY.read_text(encoding="utf-8")
    tree = ast_mod.parse(src)
    try_node = None
    for node in tree.body:
        if isinstance(node, ast_mod.Try) and "run_v2_cloud_sidecar" in ast_mod.dump(node):
            try_node = node
            break
    hook = ast_mod.get_source_segment(src, try_node)
    fetch_calls: list[int] = []

    class FakeSidecar:
        ok = True
        skipped = False
        reason = REASON_WROTE
        n_rows = 0
        error = ""
        path = "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"
        snapshot_text = "{}"

    orig_run = ch.run_v2_cloud_sidecar
    orig_pub = gb.maybe_publish_v2_sidecar
    orig_fetch = gb.fetch_v2_sidecar
    ch.run_v2_cloud_sidecar = lambda **k: FakeSidecar()  # type: ignore[assignment]
    gb.maybe_publish_v2_sidecar = lambda **k: V2PublishResult(  # type: ignore[assignment]
        ok=False, skipped=False, status=STATUS_TRANSPORT_ERROR, error="GITHUB_FAIL_401"
    )

    def fetcher(**kwargs):
        fetch_calls.append(1)
        raise AssertionError("GET must not run after PUT failure")

    gb.fetch_v2_sidecar = fetcher  # type: ignore[assignment]
    captions: list[str] = []
    warnings: list[str] = []
    ns = {
        "os": os,
        "_v2_ui": unavailable_v2_ui(),
        "scan_df": pd.DataFrame([{"symbol": "HPG"}]),
        "market_real": 7.2,
        "vn_now": lambda: datetime(2026, 8, 14, 10, 5, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        "buy_elite_df": pd.DataFrame(),
        "early_buy_lab_df": pd.DataFrame(),
        "st": types.SimpleNamespace(
            warning=lambda msg: warnings.append(str(msg)),
            caption=lambda msg: captions.append(str(msg)),
            secrets=types.SimpleNamespace(get=lambda *a, **k: ""),
        ),
    }
    saved_a = os.environ.get(ENV_V2_CLOUD_SIDECAR)
    saved_b = os.environ.get(ENV_V2_GITHUB_PUBLISH)
    try:
        os.environ[ENV_V2_CLOUD_SIDECAR] = "1"
        os.environ[ENV_V2_GITHUB_PUBLISH] = "1"
        exec(compile(hook, "app.py", "exec"), ns, ns)
    finally:
        ch.run_v2_cloud_sidecar = orig_run
        gb.maybe_publish_v2_sidecar = orig_pub
        gb.fetch_v2_sidecar = orig_fetch
        os.environ.pop(ENV_V2_CLOUD_SIDECAR, None)
        os.environ.pop(ENV_V2_GITHUB_PUBLISH, None)
        if saved_a is not None:
            os.environ[ENV_V2_CLOUD_SIDECAR] = saved_a
        if saved_b is not None:
            os.environ[ENV_V2_GITHUB_PUBLISH] = saved_b
    assert fetch_calls == []
    assert ns["_v2_ui"].kind == KIND_FAILURE
    assert captions == ["LCV2-GATE-A-WROTE rows=0"]
    assert warnings
    st = _render(ns["_v2_ui"])
    assert EMPTY_MESSAGE not in st.markdowns
    assert st.tables == []
    assert "GITHUB_FAIL_401" in warnings[0] or "TRANSPORT" in warnings[0]


def test_production_watchlist_untouched():
    assert PROD_WATCHLIST.exists()
    ui = UI_PY.read_text(encoding="utf-8")
    assert "dynamic_watchlist.json" not in ast.dump(ast.parse(ui))
    hook_src = APP_PY.read_text(encoding="utf-8")
    start = hook_src.index("from modules.live_candidate_v2_camera.ui import")
    panel = hook_src[start : hook_src.index('with st.expander("🤖 AI Recommendation"')]
    assert "dynamic_watchlist.json" not in panel
    init = (REPO / "modules" / "live_candidate_v2_camera" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "ui import" not in init and "from modules.live_candidate_v2_camera.ui" not in init
    cloud = (REPO / "modules" / "live_candidate_v2_camera" / "cloud_hook.py").read_text(
        encoding="utf-8"
    )
    assert "live_candidate_v2_camera.ui" not in cloud
