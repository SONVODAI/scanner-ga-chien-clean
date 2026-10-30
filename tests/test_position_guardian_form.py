"""Form editor for the holdings ledger. Does not touch the production JSON file."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO = Path(__file__).resolve().parents[1]
EDITOR_KEY = "user_holdings_ledger_editor_ddmm_0"


def _script(json_path: Path, text_path: Path) -> str:
    return f"""
import os
import sys
os.environ["GITHUB_TOKEN"] = ""
os.environ["GH_TOKEN"] = ""
os.environ["MRBOT_USER_HOLDINGS_JSON"] = r"{json_path}"
os.environ["MRBOT_USER_HOLDINGS_FILE"] = r"{text_path}"
sys.path.insert(0, r"{REPO}")
import streamlit as st
from modules.user_holdings import load_positions
from position_guardian import render_holdings_editor
loaded = load_positions()
st.text(
    "LOADED "
    + ",".join(
        f"{{item['symbol']}}:{{item['entry_price']}}:{{item['entry_date']}}"
        for item in loaded
    )
)
render_holdings_editor()
"""


def _seed(path: Path, positions: list[dict]) -> None:
    path.write_text(
        json.dumps({"schema": "user_holdings.v1", "positions": positions}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _stored(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "user_holdings.v1"
    for item in data["positions"]:
        assert set(item) == {"symbol", "entry_price", "entry_date"}
    return data["positions"]


def _editor_source() -> str:
    src = (REPO / "position_guardian.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "render_holdings_editor":
            return ast.get_source_segment(src, node) or ""
    raise AssertionError("render_holdings_editor missing")


def _button(at: AppTest, label: str):
    matches = [button for button in at.button if button.label == label]
    assert len(matches) == 1, label
    return matches[0]


@pytest.fixture
def ledger(tmp_path: Path):
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("GH_TOKEN", None)
    json_path = tmp_path / "positions.json"
    text_path = tmp_path / "portfolio_symbols.txt"
    _seed(
        json_path,
        [
            {"symbol": "SSI", "entry_price": 24.5, "entry_date": "2026-09-01"},
            {"symbol": "PVD", "entry_price": 18.0, "entry_date": "2026-09-08"},
        ],
    )
    return json_path, text_path


def _start(ledger) -> AppTest:
    json_path, text_path = ledger
    app = AppTest.from_string(_script(json_path, text_path))
    return app.run(timeout=30)


def test_editor_is_a_form_without_fragment_or_rerun():
    src = _editor_source()
    tree = ast.parse(src)
    forms = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr == "form"
            for item in node.items
        )
    ]
    assert len(forms) == 1
    form = forms[0]
    keywords = {
        keyword.arg: keyword.value
        for item in form.items
        if isinstance(item.context_expr, ast.Call)
        for keyword in item.context_expr.keywords
    }
    assert isinstance(keywords["clear_on_submit"], ast.Constant)
    assert keywords["clear_on_submit"].value is False
    inner = ast.get_source_segment(src, form) or ""
    assert "st.data_editor" in inner
    assert "st.form_submit_button" in inner
    assert "st.checkbox" in inner
    assert "Lưu danh sách nắm giữ" in inner
    assert "Hủy" in inner
    assert "st.button" not in src
    assert "st.fragment" not in src
    assert "current_fragment_id" not in src
    assert "st.rerun" not in src
    assert "render_guardian" not in src
    assert "quantity" not in src.lower()
    assert "số lượng" not in src.lower()


def test_app_call_paths_are_unchanged():
    app = (REPO / "app.py").read_text(encoding="utf-8")
    assert app.count("render_guardian(") == 1
    assert "render_holdings_editor()" in app
    assert app.index("render_holdings_editor()") < app.index("render_guardian(")


def test_price_edit_is_not_saved_until_submit(ledger):
    json_path, _text_path = ledger
    before = json_path.read_text(encoding="utf-8")
    app = _start(ledger)
    assert _button(app, "Lưu danh sách nắm giữ").form_id
    assert _button(app, "Hủy").form_id
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {0: {"Giá vốn": 30.25}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.run(timeout=30)
    assert json_path.read_text(encoding="utf-8") == before


def _confirm(at: AppTest):
    matches = [box for box in at.checkbox if "Xác nhận xóa" in box.label]
    assert len(matches) == 1
    assert matches[0].form_id
    return matches[0]


def test_price_edit_saves_without_confirmation(ledger):
    json_path, _text_path = ledger
    app = _start(ledger)
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {0: {"Giá vốn": 30.25}},
        "added_rows": [],
        "deleted_rows": [],
    }
    _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    stored = _stored(json_path)
    ssi = next(item for item in stored if item["symbol"] == "SSI")
    assert ssi["entry_price"] == 30.25
    assert ssi["entry_date"] == "2026-09-01"
    assert [item["symbol"] for item in stored] == ["SSI", "PVD"]


def test_date_edit_saves_without_confirmation(ledger):
    json_path, _text_path = ledger
    app = _start(ledger)
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {1: {"Ngày mua": "11/09/2026"}},
        "added_rows": [],
        "deleted_rows": [],
    }
    _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    stored = _stored(json_path)
    pvd = next(item for item in stored if item["symbol"] == "PVD")
    assert pvd["entry_date"] == "2026-09-11"
    assert pvd["entry_price"] == 18.0
    assert [item["symbol"] for item in stored] == ["SSI", "PVD"]


def test_save_persists_price_and_date_together(ledger):
    json_path, _text_path = ledger
    app = _start(ledger)
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {0: {"Giá vốn": 30.25, "Ngày mua": "02/09/2026"}},
        "added_rows": [],
        "deleted_rows": [],
    }
    _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    stored = _stored(json_path)
    ssi = next(item for item in stored if item["symbol"] == "SSI")
    assert ssi["entry_price"] == 30.25
    assert ssi["entry_date"] == "2026-09-02"
    assert any(item["symbol"] == "PVD" for item in stored)


def test_cancel_restores_persisted_values(ledger):
    json_path, _text_path = ledger
    before = _stored(json_path)
    app = _start(ledger)
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {0: {"Giá vốn": 99.0}},
        "added_rows": [],
        "deleted_rows": [],
    }
    cancelled = _button(app, "Hủy").click().run(timeout=30)
    assert _stored(json_path) == before
    assert any("Đã hủy" in item.value for item in cancelled.info)
    assert cancelled.session_state["position_guardian_holdings_editor_nonce"] == 1


def test_invalid_date_blocks_save_and_keeps_the_draft(ledger):
    json_path, _text_path = ledger
    before = json_path.read_text(encoding="utf-8")
    app = _start(ledger)
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {0: {"Ngày mua": "32/09/2026"}},
        "added_rows": [],
        "deleted_rows": [],
    }
    failed = _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    assert json_path.read_text(encoding="utf-8") == before
    assert failed.error
    assert "32/09/2026" in str(failed.session_state[EDITOR_KEY])


def test_future_date_blocks_save_and_keeps_the_draft(ledger):
    json_path, _text_path = ledger
    before = json_path.read_text(encoding="utf-8")
    app = _start(ledger)
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {0: {"Ngày mua": "01/01/2099"}},
        "added_rows": [],
        "deleted_rows": [],
    }
    failed = _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    assert json_path.read_text(encoding="utf-8") == before
    assert failed.error
    assert "01/01/2099" in str(failed.session_state[EDITOR_KEY])


def _stage_delete(app: AppTest, rows: list[int], edits: dict | None = None) -> None:
    app.session_state[EDITOR_KEY] = {
        "edited_rows": edits or {},
        "added_rows": [],
        "deleted_rows": rows,
    }


def test_unconfirmed_deletion_writes_nothing(ledger):
    json_path, _text_path = ledger
    before = _stored(json_path)
    app = _start(ledger)
    _stage_delete(app, [1])
    refused = _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    assert _stored(json_path) == before
    message = " ".join(item.value for item in refused.error)
    assert "PVD" in message
    assert "SSI" not in message


def test_several_unconfirmed_deletions_list_every_symbol(ledger):
    json_path, _text_path = ledger
    before = _stored(json_path)
    app = _start(ledger)
    _stage_delete(app, [0, 1])
    refused = _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    assert _stored(json_path) == before
    message = " ".join(item.value for item in refused.error)
    assert "SSI" in message and "PVD" in message


def test_confirmed_deletion_persists_only_the_intended_change(ledger):
    json_path, _text_path = ledger
    app = _start(ledger)
    _stage_delete(app, [1], {0: {"Giá vốn": 30.25}})
    _confirm(app).check()
    saved = _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    stored = _stored(json_path)
    assert stored == [
        {"symbol": "SSI", "entry_price": 30.25, "entry_date": "2026-09-01"}
    ]
    assert any("Đã lưu" in item.value for item in saved.success)


def test_confirmed_deletion_can_remove_several_symbols(ledger):
    json_path, _text_path = ledger
    app = _start(ledger)
    _stage_delete(app, [0, 1])
    _confirm(app).check()
    _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    assert _stored(json_path) == []


def test_cancel_restores_rows_staged_for_deletion(ledger):
    json_path, _text_path = ledger
    before = _stored(json_path)
    app = _start(ledger)
    _stage_delete(app, [0, 1])
    cancelled = _button(app, "Hủy").click().run(timeout=30)
    assert _stored(json_path) == before
    assert any("Đã hủy" in item.value for item in cancelled.info)
    assert cancelled.session_state["position_guardian_holdings_editor_nonce"] == 1


def test_add_holding_persists_on_save(ledger):
    json_path, _text_path = ledger
    app = _start(ledger)
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {},
        "added_rows": [{"Mã": "FPT", "Giá vốn": 120.5, "Ngày mua": "10/09/2026"}],
        "deleted_rows": [],
    }
    _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    stored = _stored(json_path)
    added = next(item for item in stored if item["symbol"] == "FPT")
    assert added == {
        "symbol": "FPT",
        "entry_price": 120.5,
        "entry_date": "2026-09-10",
    }


def test_refresh_loads_saved_holdings(ledger):
    json_path, text_path = ledger
    app = _start(ledger)
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {0: {"Giá vốn": 31.0}},
        "added_rows": [],
        "deleted_rows": [],
    }
    _button(app, "Lưu danh sách nắm giữ").click().run(timeout=30)
    refreshed = AppTest.from_string(_script(json_path, text_path)).run(timeout=30)
    shown = " ".join(item.value for item in refreshed.text)
    assert "LOADED SSI:31.0:2026-09-01" in shown
    assert "PVD:18.0:2026-09-08" in shown
