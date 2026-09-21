"""#160 runtime discriminator: unconditional top-of-page caption.

Proves Cloud loaded an app.py descendant of #160 without logs/Secrets.
Independent of Gate A/B, scan, env, git, and network.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP_PY = REPO / "app.py"
PRIOR = "LCV2-COMMISSION-20260916-A"
MARKER = "LCV2-CODE-160-READY"
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


def _caption_calls_with_marker(tree: ast.AST, token: str) -> list[ast.Call]:
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
        if isinstance(arg, ast.Constant) and arg.value == token:
            hits.append(node)
    return hits


def test_code_160_ready_is_literal_caption_after_commission_before_v2_slot():
    src = _app_source()
    tree = ast.parse(src)
    hits = _caption_calls_with_marker(tree, MARKER)
    assert len(hits) == 1
    assert isinstance(hits[0].args[0], ast.Constant)
    assert hits[0].args[0].value == MARKER
    assert src.count(MARKER) == 1

    prior_i = src.index(f'st.caption("{PRIOR}")')
    marker_i = src.index(f'st.caption("{MARKER}")')
    slot_i = src.index("_v2_slot = st.empty()")
    assert prior_i < marker_i < slot_i

    call = hits[0]
    for node in ast.walk(call):
        if isinstance(node, ast.Name):
            assert node.id not in FORBIDDEN_NAMES or node.id == "st"
        if isinstance(node, ast.Attribute):
            assert node.attr == "caption"
        if isinstance(node, ast.JoinedStr):
            raise AssertionError("marker must not be an f-string")
        if isinstance(node, ast.Call) and node is not call:
            raise AssertionError("marker caption must not nest other calls")

    gate_try = None
    for node in tree.body:
        if isinstance(node, ast.Try) and "run_v2_cloud_sidecar" in ast.dump(node):
            gate_try = node
            break
    assert gate_try is not None
    assert call not in ast.walk(gate_try)
    assert MARKER not in ast.get_source_segment(src, gate_try)
    assert 'os.environ.get("MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR", "")' in src
    assert 'st.secrets.get("MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR", "")' in src
    assert 'os.environ.get("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH", "")' in src
    assert 'st.secrets.get("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH", "")' in src
    assert 'env={"MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH": _v2_pub_gate}' in src
