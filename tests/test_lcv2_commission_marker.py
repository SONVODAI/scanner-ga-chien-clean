"""Streamlit runtime observability marker.

Proves app.py carries a default-visible, passive caption so Community Cloud
revision can be confirmed from the normal page. Marker only: no git, no
Secrets, no env dump, no Gate A/B change.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP_PY = REPO / "app.py"
MARKER = "LCV2-COMMISSION-20260916-A"
FORBIDDEN_NAMES = frozenset(
    {
        "environ",
        "getenv",
        "secrets",
        "subprocess",
        "Popen",
        "system",
        "run",
        "check_output",
        "git",
        "rev_parse",
        "listdir",
        "scandir",
        "walk",
        "open",
        "Path",
        "urlopen",
        "request",
        "get",
        "put",
        "post",
        "requests",
        "httpx",
        "os",
    }
)


def _app_source() -> str:
    return APP_PY.read_text(encoding="utf-8")


def _caption_calls_with_marker(tree: ast.AST) -> list[ast.Call]:
    hits: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "caption"
            and isinstance(func.value, ast.Name)
            and func.value.id == "st"
        ):
            continue
        if len(node.args) != 1 or node.keywords:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and arg.value == MARKER:
            hits.append(node)
    return hits


def test_marker_is_one_literal_caption_under_title():
    src = _app_source()
    tree = ast.parse(src)
    hits = _caption_calls_with_marker(tree)
    assert len(hits) == 1
    call = hits[0]
    assert isinstance(call.args[0], ast.Constant)
    assert call.args[0].value == MARKER
    assert src.count(MARKER) == 1

    title_i = src.index('st.title("🤖 Mr.BOT PRO V4.0 - Scanner Gà Chiến")')
    marker_i = src.index(f'st.caption("{MARKER}")')
    pxv_i = src.index("# LIVE CANDIDATE × P×V")
    assert title_i < marker_i < pxv_i


def test_marker_call_has_no_side_channels():
    src = _app_source()
    tree = ast.parse(src)
    [call] = _caption_calls_with_marker(tree)
    for node in ast.walk(call):
        if isinstance(node, ast.Name):
            assert node.id not in FORBIDDEN_NAMES or node.id == "st"
        if isinstance(node, ast.Attribute):
            assert node.attr == "caption"
        if isinstance(node, ast.JoinedStr):
            raise AssertionError("marker must not be an f-string")
        if isinstance(node, (ast.Call,)) and node is not call:
            raise AssertionError("marker caption must not nest other calls")


def test_marker_is_not_inside_gate_a_or_gate_b():
    src = _app_source()
    tree = ast.parse(src)
    [call] = _caption_calls_with_marker(tree)
    gate_try = None
    for node in tree.body:
        if isinstance(node, ast.Try) and "run_v2_cloud_sidecar" in ast.dump(node):
            gate_try = node
            break
    assert gate_try is not None
    assert call not in ast.walk(gate_try)
    assert MARKER not in ast.get_source_segment(src, gate_try)


def test_gate_a_and_gate_b_lookups_unchanged():
    src = _app_source()
    assert 'os.environ.get("MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR", "")' in src
    assert 'os.environ.get("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH", "")' in src
    assert src.count("MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR") == 1
    assert src.count("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH") == 1
    tree = ast.parse(src)
    gate_try = None
    for node in tree.body:
        if isinstance(node, ast.Try) and "run_v2_cloud_sidecar" in ast.dump(node):
            gate_try = node
            break
    assert gate_try is not None
    dump = ast.dump(gate_try)
    assert "github_bus" in dump
    assert "cloud_hook" in dump
    assert "maybe_publish_v2_sidecar" in dump
    assert "run_v2_cloud_sidecar" in dump
