"""Ledger filter isolation, sealed-byte cache, and display placement.

These tests cover the approved UI change. They do not rewrite the older
population assertion that still expects horizons to stay unattached.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
from pathlib import Path

import pytest

from research.v2_research_ledger.board_view import apply_filters, horizon_text
from research.v2_research_ledger.delivery_view import DELIVERY_UNAVAILABLE, DeliveryView
from research.v2_research_ledger.panel_board import HORIZON_STATUS
from modules.v2_research_ledger_panel import ui

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "research" / "v2_research_ledger" / "durable"
APP = ROOT / "app.py"
PANEL = ROOT / "modules" / "v2_research_ledger_panel" / "ui.py"
GUARDIAN = ROOT / "position_guardian.py"
GUARDIAN_RESEARCH = ROOT / "research" / "guardian_research" / "panel.py"
POPULATIONS = {"brain_linked", "brain_unlinked", "sweetspot", "sweetspot_blank"}


@pytest.fixture(autouse=True)
def _reset_ledger_success_cache():
    ui._CACHED_OK_BOARD = None
    yield
    ui._CACHED_OK_BOARD = None


class _Expander:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeStreamlit:
    """The panel tests' Streamlit stand-in. It has no fragment."""

    def __init__(self) -> None:
        self.captions: list[str] = []
        self.frames: list[object] = []

    def expander(self, *_args, **_kwargs):
        return _Expander()

    def caption(self, text: str) -> None:
        self.captions.append(str(text))

    def warning(self, text: str) -> None:
        self.captions.append(str(text))

    def selectbox(self, _label, options, index=0):
        return options[index]

    def text_input(self, _label, value=""):
        return value

    def dataframe(self, frame, *_args, **_kwargs):
        self.frames.append(frame)


def _copy_ledger(tmp_path: Path) -> Path:
    destination = tmp_path / "ledger"
    shutil.copytree(STORE, destination / "durable")
    shutil.copytree(STORE.parent / "outcomes", destination / "outcomes")
    return destination / "durable"


def _horizon_statuses(board: dict) -> set[str]:
    found: set[str] = set()
    for row in board.get("rows") or []:
        horizons = row.get("horizons") or {}
        if isinstance(horizons, dict):
            for cell in horizons.values():
                if isinstance(cell, dict):
                    found.add(str(cell.get("status") or ""))
    return found


def _with_contexts(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            yield node


def _is_v2_slot(node: ast.With) -> bool:
    for item in node.items:
        call = item.context_expr
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "container"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "_v2_slot"
        ):
            return True
    return False


def _call_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            names.append(child.func.id)
    return names


def test_sealed_fingerprint_is_stable_and_tracks_each_sealed_file(tmp_path: Path):
    first = ui.sealed_fingerprint(STORE)
    assert first == ui.sealed_fingerprint(STORE)
    assert any(part.startswith("identities.jsonl:") and not part.endswith(":absent") for part in first)
    assert any(part.startswith("index.json:") and not part.endswith(":absent") for part in first)
    assert any(part.startswith("generations/") for part in first)

    store = _copy_ledger(tmp_path)
    before = ui.sealed_fingerprint(store)
    generation = next(path for path in (store.parent / "outcomes" / "generations").glob("*.json"))
    generation.write_bytes(generation.read_bytes().replace(b"a2e868e74e62", b"000000000000", 1))
    after = ui.sealed_fingerprint(store)
    assert before != after

    index = store.parent / "outcomes" / "index.json"
    index.write_text(
        json.dumps({"schema": "v2_research_forward_index.v1", "generations": [{"path": "../identities.jsonl"}]}),
        encoding="utf-8",
    )
    escaped = ui.sealed_fingerprint(store)
    assert "path-escaped" in escaped
    assert not any(part.startswith("../") for part in escaped)


def test_same_bytes_validate_once_and_a_changed_fingerprint_does_not(tmp_path: Path):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    fingerprint_queue = tmp_path / "fingerprints.txt"
    board_queue = tmp_path / "boards.txt"
    log_path = tmp_path / "cache.log"
    fingerprint_queue.write_text("", encoding="utf-8")
    board_queue.write_text("", encoding="utf-8")

    def _pop(path: Path) -> str:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            raise AssertionError(f"queue exhausted: {path.name}")
        path.write_text("\n".join(lines[1:]) + ("\n" if lines[1:] else ""), encoding="utf-8")
        return lines[0]

    def _sealed(_path: Path):
        return (_pop(fingerprint_queue),)

    def _board(_path: Path):
        marker = _pop(board_queue)
        if marker == "INVALID":
            return "INVALID", None, "broken"
        return "OK", {"rows": [], "marker": marker}, ""

    monkey = pytest.MonkeyPatch()
    monkey.setattr(ui, "sealed_fingerprint", _sealed)
    monkey.setattr(ui, "_validated_durable_board", _board)
    os.environ["LEDGER_FP_QUEUE"] = str(fingerprint_queue)
    os.environ["LEDGER_BOARD_QUEUE"] = str(board_queue)
    os.environ["LEDGER_CACHE_LOG"] = str(log_path)
    script = tmp_path / "cache_app.py"
    script.write_text(
        "\n".join(
            [
                "import os",
                "import sys",
                "from pathlib import Path",
                f"sys.path.insert(0, {str(ROOT)!r})",
                "import streamlit as st",
                "from modules.v2_research_ledger_panel import ui",
                "ui._CACHED_OK_BOARD = None",
                "log = Path(os.environ['LEDGER_CACHE_LOG'])",
                "lines = []",
                "def record(msg):",
                "    lines.append(msg)",
                "    log.write_text('\\n'.join(lines) + '\\n', encoding='utf-8')",
                "loader = ui._streamlit_cached_loader(st)",
                "def attempt(label, fingerprint):",
                "    try:",
                "        board, confirmed = loader('/tmp/ledger-store', fingerprint)",
                "        record(label + ' OK ' + board['marker'] + ' ' + confirmed[0])",
                "    except ui._StoreNotOk:",
                "        record(label + ' STORE')",
                "    except ui._FingerprintRace:",
                "        record(label + ' RACE')",
                "    except Exception as exc:",
                "        record(label + ' ERR ' + type(exc).__name__)",
                "attempt('hit-a', ('aaa',))",
                "attempt('hit-b', ('aaa',))",
                "attempt('miss', ('bbb',))",
                "attempt('bad-a', ('bad',))",
                "attempt('bad-b', ('bad',))",
                "attempt('race', ('race',))",
                "attempt('race-retry', ('race',))",
                "st.text('done')",
            ]
        ),
        encoding="utf-8",
    )
    fingerprint_queue.write_text(
        "\n".join(
            [
                "aaa",
                "aaa",
                "bbb",
                "bbb",
                "bad",
                "bad",
                "race",
                "other",
                "race",
                "race",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    board_queue.write_text("M1\nM2\nINVALID\nINVALID\nM3\nM4\n", encoding="utf-8")
    try:
        app = AppTest.from_file(str(script)).run(timeout=30)
    finally:
        monkey.undo()
    assert not app.exception
    report = log_path.read_text(encoding="utf-8").splitlines()
    assert report == [
        "hit-a OK M1 aaa",
        "hit-b OK M1 aaa",
        "miss OK M2 bbb",
        "bad-a STORE",
        "bad-b STORE",
        "race RACE",
        "race-retry OK M4 race",
    ]


def test_mismatched_or_missing_generation_fails_closed(tmp_path: Path):
    store = _copy_ledger(tmp_path)
    board, _confirmed = ui._load_validated_for_fingerprint(str(store), ui.sealed_fingerprint(store))
    forward = board.get("forward_outcomes") if isinstance(board, dict) else None
    assert isinstance(forward, dict) and forward.get("status") == "attached"
    assert "APPROX_AVAILABLE" in _horizon_statuses(board)

    generation = next(path for path in (store.parent / "outcomes" / "generations").glob("*.json"))
    original = ui.sealed_fingerprint(store)
    payload = generation.read_text(encoding="utf-8")
    tampered = payload.replace(
        '"identities.jsonl": "a2e868e74e62fef8d74c0215f817194e9489cba7af523e788c42251f9c28b848"',
        '"identities.jsonl": "0000000000000000000000000000000000000000000000000000000000000000"',
        1,
    )
    assert tampered != payload
    generation.write_text(tampered, encoding="utf-8")
    changed = ui.sealed_fingerprint(store)
    assert changed != original
    with pytest.raises(ui._FingerprintRace):
        ui._load_validated_for_fingerprint(str(store), original)
    mismatched, _confirmed = ui._load_validated_for_fingerprint(str(store), changed)
    mismatched_forward = mismatched.get("forward_outcomes")
    assert not isinstance(mismatched_forward, dict) or mismatched_forward.get("status") != "attached"
    assert "APPROX_AVAILABLE" not in _horizon_statuses(mismatched)

    generation.unlink()
    missing_key = ui.sealed_fingerprint(store)
    assert any(part.endswith(":absent") for part in missing_key)
    missing, _confirmed = ui._load_validated_for_fingerprint(str(store), missing_key)
    assert "APPROX_AVAILABLE" not in _horizon_statuses(missing)
    with pytest.raises(ui._FingerprintRace):
        ui._load_validated_for_fingerprint(str(store), changed)


def test_invalid_store_is_not_a_successful_board(tmp_path: Path):
    store = tmp_path / "broken"
    store.mkdir()
    (store / "manifest.json").write_text('{"schema":"not-the-store"}\n', encoding="utf-8")
    (store / "identities.jsonl").write_text("{}\n", encoding="utf-8")
    key = ui.sealed_fingerprint(store)
    with pytest.raises(ui._StoreNotOk) as first:
        ui._load_validated_for_fingerprint(str(store), key)
    with pytest.raises(ui._StoreNotOk) as second:
        ui._load_validated_for_fingerprint(str(store), key)
    assert first.value.state == "INVALID"
    assert second.value.state == "INVALID"
    state, board, reason = ui._remember_validated_board(_FakeStreamlit(), store)
    assert state == "INVALID"
    assert board is None
    assert reason


def test_t0_filters_keep_their_own_horizons_populations_and_provenance():
    state, board, reason = ui._remember_validated_board(_FakeStreamlit(), STORE)
    assert state == "OK" and isinstance(board, dict) and reason == ""
    rows = list(board["rows"])
    dates = sorted({str(row.get("t0_date") or "") for row in rows if row.get("t0_date")})
    assert len(dates) >= 2
    by_id = {str(row.get("row_id")): row for row in rows}
    chosen = [dates[0], dates[-1]]
    seen: list[set[str]] = []
    for day in chosen:
        selected = apply_filters(rows, t0_date=day, population="all", source="all", state="all")
        assert selected
        assert {str(row.get("t0_date")) for row in selected} == {day}
        populations = {str(row.get("population")) for row in selected}
        assert populations <= POPULATIONS
        seen.append({str(row.get("row_id")) for row in selected})
        for row in selected:
            source = by_id[str(row.get("row_id"))]
            assert row["t0_price_provenance"] == source["t0_price_provenance"]
            assert row["t0_price_provenance"]
            assert row["population"] == source["population"]
            assert row["horizons"] == source["horizons"]
            assert horizon_text(row["horizons"]["T+1"]) == horizon_text(source["horizons"]["T+1"])
            assert horizon_text(row["horizons"]["T+20"]) == horizon_text(source["horizons"]["T+20"])
    assert seen[0].isdisjoint(seen[1])
    linked = apply_filters(rows, t0_date="all", population="brain_linked")
    blank = apply_filters(rows, t0_date="all", population="sweetspot_blank")
    assert linked and blank
    assert {row["population"] for row in linked} == {"brain_linked"}
    assert {row["population"] for row in blank} == {"sweetspot_blank"}
    sample = linked[0]
    by_symbol = apply_filters(rows, t0_date=str(sample["t0_date"]), symbol=str(sample["symbol"]))
    match = next(row for row in by_symbol if row["row_id"] == sample["row_id"])
    assert match["horizons"] == sample["horizons"]
    assert match["t0_price_provenance"] == sample["t0_price_provenance"]


def test_fake_streamlit_without_fragment_still_renders(tmp_path: Path):
    store = tmp_path / "broken"
    store.mkdir()
    (store / "manifest.json").write_text('{"schema":"not-the-store"}\n', encoding="utf-8")
    (store / "identities.jsonl").write_text("{}\n", encoding="utf-8")
    fake = _FakeStreamlit()
    assert not hasattr(fake, "fragment")
    ui.render_v2_research_ledger_panel(
        fake,
        remote=True,
        remote_view=DeliveryView(DELIVERY_UNAVAILABLE, "missing_secret"),
        row_store=store,
    )
    text = "\n".join(fake.captions)
    assert "DURABLE_STORE_INVALID:" in text
    assert "Historical remote data is not the current durable store." in text
    assert "durable_row_store identities=" not in text

    recorded: list[dict] = []

    class _FragmentStreamlit(_FakeStreamlit):
        def fragment(self, func=None, **kwargs):
            recorded.append(dict(kwargs))

            def _decorate(draw):
                def _wrapped():
                    return draw()

                return _wrapped

            if func is not None:
                return _decorate(func)
            return _decorate

    fragment_fake = _FragmentStreamlit()
    ui.render_v2_research_ledger_panel(
        fragment_fake,
        remote=True,
        remote_view=DeliveryView(DELIVERY_UNAVAILABLE, "missing_secret"),
        row_store=store,
    )
    assert recorded == [{}]
    assert "DURABLE_STORE_INVALID:" in "\n".join(fragment_fake.captions)


def test_fragment_body_has_no_timer_rerun_or_remote_fetch():
    source = PANEL.read_text(encoding="utf-8")
    assert "st.rerun" not in source
    assert "run_every" not in source
    assert "parallel" not in source
    tree = ast.parse(source)
    render = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_v2_research_ledger_panel"
    )
    draw = next(node for node in render.body if isinstance(node, ast.FunctionDef) and node.name == "_draw")
    loader = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_load_validated_for_fingerprint"
    )
    assert not any(isinstance(node, ast.FunctionDef) and node.name == "_draw" for node in ast.walk(loader))

    def _calls(scope: ast.AST, name: str) -> list[ast.Call]:
        return [
            node
            for node in ast.walk(scope)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        ]

    assert _calls(draw, "fetch_research_trio") == []
    assert _calls(draw, "resolve_remote_config") == []
    assert _calls(render, "fetch_research_trio")
    isolate_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "fragment"
    ]
    assert isolate_calls
    assert all(node.keywords == [] for node in isolate_calls)
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "selectbox" for node in ast.walk(draw))


def test_ledger_call_is_outside_the_v2_placeholder_exactly_once():
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert source.count("render_v2_research_ledger_panel(") == 1
    assert source.count("_v2_slot = st.empty()") == 1
    assert source.count("render_live_candidate_v2_panel(") == 1
    assert source.count("render_v2_shadow_action_panel()") == 1
    assert source.count("render_guardian(") == 1
    assert source.count("render_guardian_research_panel(") == 1
    assert source.count("st.rerun(") == 1
    assert 'auto_refresh = st.checkbox("Auto refresh", value=True)' in source
    assert 'refresh_seconds = st.selectbox("Nhịp", [60, 90, 120, 300, 600], index=2)' in source
    assert source.count("st.cache_data.clear()") == 2
    ledger_at = source.index("render_v2_research_ledger_panel(")
    guardian_at = source.index("render_guardian(")
    research_at = source.index("render_guardian_research_panel(")
    assert ledger_at < guardian_at < research_at
    slot_withs = [node for node in _with_contexts(tree) if _is_v2_slot(node)]
    assert slot_withs
    for node in slot_withs:
        names = _call_names(node)
        assert "render_v2_research_ledger_panel" not in names
    filled = next(node for node in slot_withs if "render_live_candidate_v2_panel" in _call_names(node))
    filled_names = _call_names(filled)
    assert "render_live_candidate_v2_panel" in filled_names
    assert "render_v2_shadow_action_panel" in filled_names
    assert "render_shadow_buy_research_panel" in filled_names
    assert "render_approximate_performance_panel" in filled_names
    assert "st.fragment" not in GUARDIAN.read_text(encoding="utf-8")
    assert "st.fragment" not in GUARDIAN_RESEARCH.read_text(encoding="utf-8")
    assert "render_v2_research_ledger_panel" not in GUARDIAN.read_text(encoding="utf-8")
    assert "render_v2_research_ledger_panel" not in GUARDIAN_RESEARCH.read_text(encoding="utf-8")


def _fragment_rerun(app, fragment_id: str, timeout: float):
    from unittest.mock import MagicMock

    from streamlit.runtime import Runtime
    from streamlit.runtime.caching.storage.dummy_cache_storage import MemoryCacheStorageManager
    from streamlit.runtime.dataframe_source_manager import DataframeSourceManager
    from streamlit.runtime.media_file_manager import MediaFileManager
    from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
    from streamlit.runtime.pages_manager import PagesManager
    from streamlit.runtime.scriptrunner import RerunData
    from streamlit.runtime.scriptrunner.script_cache import ScriptCache
    from streamlit.testing.v1.element_tree import parse_tree_from_messages
    from streamlit.testing.v1.local_script_runner import LocalScriptRunner, require_widgets_deltas

    runtime = MagicMock(spec=Runtime)
    runtime.media_file_mgr = MediaFileManager(MemoryMediaFileStorage("/mock/media"))
    runtime.dataframe_source_mgr = DataframeSourceManager()
    runtime.cache_storage_manager = MemoryCacheStorageManager()
    runtime.bidi_component_registry = app._bidi_component_manager
    Runtime._instance = runtime
    try:
        pages = PagesManager(app._script_path, ScriptCache(), setup_watcher=False)
        pages.set_current_page_script_hash(app._finished_page_script_hash)
        runner = LocalScriptRunner(
            app._script_path,
            app._session_state,
            pages,
            fragment_storage=app._fragment_storage,
        )
        runner._requests._rerun_data = RerunData(
            widget_states=app._tree.get_widget_states(),
            fragment_id_queue=[fragment_id],
            page_script_hash=app._finished_page_script_hash,
        )
        runner.start()
        require_widgets_deltas(runner, timeout)
        runner.join()
        tree = parse_tree_from_messages(runner.forward_msgs())
        tree._runner = app
        app._tree = tree
        return tree
    finally:
        Runtime._instance = None


def test_fragment_rerun_changes_t0_without_the_scan_prefix(tmp_path: Path):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    log_path = tmp_path / "fragment.log"
    log_path.write_text("", encoding="utf-8")
    os.environ["LEDGER_SPEED_LOG"] = str(log_path)
    os.environ["LEDGER_REPO"] = str(ROOT)
    os.environ["LEDGER_STORE"] = str(STORE)
    script = "\n".join(
        [
            "import os",
            "import sys",
            "from pathlib import Path",
            "sys.path.insert(0, os.environ['LEDGER_REPO'])",
            "log = Path(os.environ['LEDGER_SPEED_LOG'])",
            "def mark(msg):",
            "    with log.open('a', encoding='utf-8') as handle:",
            "        handle.write(msg + '\\n')",
            "mark('SCAN')",
            "mark('WRITE')",
            "from research.v2_research_ledger.delivery_view import DELIVERY_UNAVAILABLE, DeliveryView",
            "from modules.v2_research_ledger_panel import ui",
            "def _fetch(url, token):",
            "    mark('FETCH')",
            "    return DeliveryView(DELIVERY_UNAVAILABLE, 'missing_secret')",
            "ui.fetch_research_trio = _fetch",
            "real_board = ui._validated_durable_board",
            "def _board(path):",
            "    mark('VALIDATE')",
            "    return real_board(path)",
            "ui._validated_durable_board = _board",
            "ui._CACHED_OK_BOARD = None",
            "ui.render_v2_research_ledger_panel(remote=True, row_store=Path(os.environ['LEDGER_STORE']))",
            "mark('AFTER')",
            "import streamlit as st",
            "st.button('outside scan')",
        ]
    )

    def _counts() -> dict[str, int]:
        lines = log_path.read_text(encoding="utf-8").splitlines()
        return {name: lines.count(name) for name in ("SCAN", "WRITE", "FETCH", "VALIDATE", "AFTER")}

    original_fetch = ui.fetch_research_trio
    original_board = ui._validated_durable_board
    try:
        app = AppTest.from_string(script).run(timeout=60)
        assert not app.exception
        first = _counts()
        assert first == {"SCAN": 1, "WRITE": 1, "FETCH": 1, "VALIDATE": 1, "AFTER": 1}
        date_box = next(box for box in app.selectbox if box.label == "T0 date")
        assert "all" in date_box.options
        initial_rows = len(app.dataframe[0].value)
        assert 0 < initial_rows < 200
        fragment_ids = list(app._fragment_storage._fragments)
        assert len(fragment_ids) == 1
        date_box.set_value("all")
        rerun = _fragment_rerun(app, fragment_ids[0], timeout=60)
        assert not list(rerun.exception)
        assert _counts() == first
        updated = next(box for box in app.selectbox if box.label == "T0 date")
        assert updated.value == "all"
        assert len(app.dataframe[0].value) == 1434
        app.run(timeout=60)
        assert not app.exception
        full = _counts()
        assert full["SCAN"] == 2
        assert full["WRITE"] == 2
        assert full["FETCH"] == 2
        assert full["AFTER"] == 2
        assert full["VALIDATE"] == 1
        assert len(app.dataframe[0].value) == 1434
    finally:
        ui.fetch_research_trio = original_fetch
        ui._validated_durable_board = original_board
