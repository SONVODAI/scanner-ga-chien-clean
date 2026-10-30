"""Source contract for the Guardian editor form and fragment wrapper."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / "position_guardian.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    tree = ast.parse(SRC)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(SRC, node) or ""
    raise AssertionError(f"{name} not found")


def test_editor_commits_only_through_the_form():
    editor = _function_source("render_holdings_editor")
    assert "st.form(" in editor
    assert "clear_on_submit=False" in editor
    assert "st.form_submit_button(" in editor
    assert "st.button(" not in editor
    assert editor.index("st.form(") < editor.index("st.data_editor(")
    assert editor.index("st.data_editor(") < editor.index("st.form_submit_button(")
    assert "commit_editor_positions(" in editor
    assert "num_rows=\"dynamic\"" in editor
    assert "current_fragment_id" in editor
    assert "render_guardian(" in editor
    assert not _calls_named(editor, "rerun")


def _calls_named(source: str, name: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if called == name:
            found.append(called)
    return found


def test_guardian_fragment_is_not_nested_and_does_not_rerun():
    body = _function_source("_render_guardian_body")
    dispatcher = _function_source("render_guardian")
    assert "st.fragment" not in body
    assert "@st.fragment" not in body
    assert "render_holdings_editor(" in body
    assert "get_script_run_ctx" in dispatcher
    assert "_render_guardian_body(" in dispatcher
    assert "_render_guardian_fragment(" in dispatcher
    assert "current_fragment_id" not in body
    assert "render_guardian(" not in body
    assert "_warn_fragment_unavailable(" in dispatcher
    assert _calls_named(SRC, "rerun") == []
    assert _calls_named(SRC, "fragment") == []
