"""Gate A WROTE caption — success observability without logs/Secrets.

Default OFF. Caption only after a successful local 3A write. Gate B unchanged.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.live_candidate_v2_camera.cloud_hook import (
    REASON_GATE_OFF,
    REASON_LOAD_FAILED,
    REASON_WRITE_FAILED,
    REASON_WROTE,
)
from modules.live_candidate_v2_camera.contract import (
    ENV_V2_CLOUD_SIDECAR,
    ENV_V2_GITHUB_PUBLISH,
)

REPO = Path(__file__).resolve().parents[1]
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CAPTION_PREFIX = "LCV2-GATE-A-WROTE rows="


def _app_source() -> str:
    return (REPO / "app.py").read_text(encoding="utf-8")


def _v2_hook_try_node(src: str | None = None) -> ast.Try:
    tree = ast.parse(src or _app_source())
    for node in tree.body:
        if isinstance(node, ast.Try):
            blob = ast.dump(node)
            if "run_v2_cloud_sidecar" in blob:
                return node
    raise AssertionError("V2 sidecar Try block not found in app.py")


class _FakeSidecar:
    def __init__(
        self,
        *,
        ok: bool,
        skipped: bool,
        reason: str,
        n_rows: int = 0,
        error: str = "",
        path: str = "research/live_candidate_v2_camera_sidecar/camera_sidecar.json",
        snapshot_text: str = "",
    ):
        self.ok = ok
        self.skipped = skipped
        self.reason = reason
        self.n_rows = n_rows
        self.error = error
        self.path = path
        self.snapshot_text = snapshot_text


def _exec_hook(*, gate_a: str | None, gate_b: str | None, result: _FakeSidecar | None):
    src = _app_source()
    hook_src = ast.get_source_segment(src, _v2_hook_try_node(src))
    assert hook_src
    captions: list[str] = []
    warnings: list[str] = []

    import modules.live_candidate_v2_camera.cloud_hook as ch

    fake = result

    def runner(**kwargs):
        assert fake is not None
        return fake

    orig = ch.run_v2_cloud_sidecar
    ch.run_v2_cloud_sidecar = runner  # type: ignore[assignment]
    before = {k for k in sys.modules if "github_bus" in k}
    ns = {
        "os": os,
        "scan_df": pd.DataFrame([{"symbol": "HPG"}]),
        "market_real": 7.2,
        "vn_now": lambda: datetime.now(tz=VN),
        "buy_elite_df": pd.DataFrame(),
        "early_buy_lab_df": pd.DataFrame(),
        "st": types.SimpleNamespace(
            warning=lambda msg: warnings.append(str(msg)),
            caption=lambda msg: captions.append(str(msg)),
        ),
    }
    try:
        # Isolate env for os.environ.get inside the extracted hook.
        saved_a = os.environ.get(ENV_V2_CLOUD_SIDECAR)
        saved_b = os.environ.get(ENV_V2_GITHUB_PUBLISH)
        os.environ.pop(ENV_V2_CLOUD_SIDECAR, None)
        os.environ.pop(ENV_V2_GITHUB_PUBLISH, None)
        if gate_a is not None:
            os.environ[ENV_V2_CLOUD_SIDECAR] = gate_a
        if gate_b is not None:
            os.environ[ENV_V2_GITHUB_PUBLISH] = gate_b
        exec(compile(hook_src, "app.py", "exec"), ns, ns)
    finally:
        ch.run_v2_cloud_sidecar = orig
        os.environ.pop(ENV_V2_CLOUD_SIDECAR, None)
        os.environ.pop(ENV_V2_GITHUB_PUBLISH, None)
        if saved_a is not None:
            os.environ[ENV_V2_CLOUD_SIDECAR] = saved_a
        if saved_b is not None:
            os.environ[ENV_V2_GITHUB_PUBLISH] = saved_b
    after = {k for k in sys.modules if "github_bus" in k}
    for key in ("_v2_gate_a_caption", "_v2_gate_b_caption"):
        val = ns.get(key)
        if val:
            captions.append(str(val))
    return captions, warnings, ns, before, after


def test_caption_placement_after_warning_before_gate_b():
    src = _app_source()
    try_node = _v2_hook_try_node(src)
    hook = ast.get_source_segment(src, try_node) or ""
    warn_i = hook.index("st.warning(f\"V2 Camera sidecar: ")
    cap_i = hook.index("_v2_gate_a_caption = f\"LCV2-GATE-A-WROTE rows={_v2_sidecar.n_rows}\"")
    pub_i = hook.index("_v2_pub_gate")
    github_i = hook.index("maybe_publish_v2_sidecar(")
    assert warn_i < cap_i < pub_i < github_i
    assert "reason == \"WROTE\"" in hook[warn_i:cap_i] or 'reason == "WROTE"' in hook
    assert "_v2_sidecar.reason == \"WROTE\"" in hook


def test_gate_a_off_no_caption_no_v2_import():
    script = (
        "import os, sys, types\n"
        "from datetime import datetime\n"
        "from zoneinfo import ZoneInfo\n"
        "import pandas as pd\n"
        "os.environ.pop(%r, None)\n"
        "os.environ.pop(%r, None)\n"
        "before = {k for k in sys.modules if 'live_candidate_v2' in k}\n"
        "captions = []\n"
        "ns = {\n"
        "    'os': os,\n"
        "    'scan_df': pd.DataFrame([{'symbol': 'HPG'}]),\n"
        "    'market_real': 7.2,\n"
        "    'vn_now': lambda: datetime.now(tz=ZoneInfo('Asia/Ho_Chi_Minh')),\n"
        "    'buy_elite_df': pd.DataFrame(),\n"
        "    'early_buy_lab_df': pd.DataFrame(),\n"
        "    'st': types.SimpleNamespace(\n"
        "        warning=lambda msg: (_ for _ in ()).throw(AssertionError(msg)),\n"
        "        caption=lambda msg: captions.append(str(msg)),\n"
        "    ),\n"
        "}\n"
        "hook = %r\n"
        "exec(compile(hook, 'app.py', 'exec'), ns, ns)\n"
        "after = {k for k in sys.modules if 'live_candidate_v2' in k}\n"
        "assert after == before\n"
        "assert '_v2_sidecar' not in ns\n"
        "assert captions == []\n"
        "print('OK')\n"
    )
    src = _app_source()
    hook_src = ast.get_source_segment(src, _v2_hook_try_node(src))
    script = script % (ENV_V2_CLOUD_SIDECAR, ENV_V2_GITHUB_PUBLISH, hook_src)
    env = {k: v for k, v in os.environ.items() if k not in {ENV_V2_CLOUD_SIDECAR, ENV_V2_GITHUB_PUBLISH}}
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


def test_wrote_nonempty_emits_caption():
    captions, warnings, ns, before, after = _exec_hook(
        gate_a="1",
        gate_b=None,
        result=_FakeSidecar(ok=True, skipped=False, reason=REASON_WROTE, n_rows=3),
    )
    assert captions == [f"{CAPTION_PREFIX}3"]
    assert warnings == []
    assert "modules.live_candidate_v2_camera.github_bus" not in (after - before)
    assert ns["_v2_sidecar"].reason == REASON_WROTE


def test_wrote_empty_rows_is_success_caption_zero():
    captions, warnings, *_ = _exec_hook(
        gate_a="1",
        gate_b=None,
        result=_FakeSidecar(ok=True, skipped=False, reason=REASON_WROTE, n_rows=0),
    )
    assert captions == [f"{CAPTION_PREFIX}0"]
    assert warnings == []


def test_load_failed_no_success_caption_keeps_warning():
    captions, warnings, *_ = _exec_hook(
        gate_a="1",
        gate_b=None,
        result=_FakeSidecar(
            ok=False,
            skipped=False,
            reason=REASON_LOAD_FAILED,
            error="corrupted sidecar JSON: x",
        ),
    )
    assert captions == []
    assert warnings == ["V2 Camera sidecar: corrupted sidecar JSON: x"]


def test_write_failed_no_success_caption_keeps_warning():
    captions, warnings, *_ = _exec_hook(
        gate_a="1",
        gate_b=None,
        result=_FakeSidecar(
            ok=False,
            skipped=False,
            reason=REASON_WRITE_FAILED,
            error="OSError: disk full",
        ),
    )
    assert captions == []
    assert warnings == ["V2 Camera sidecar: OSError: disk full"]


def test_skipped_gate_off_result_no_caption():
    captions, warnings, *_ = _exec_hook(
        gate_a="1",
        gate_b=None,
        result=_FakeSidecar(ok=True, skipped=True, reason=REASON_GATE_OFF, n_rows=2),
    )
    assert captions == []
    assert warnings == []


def test_ok_but_not_wrote_no_caption():
    captions, warnings, *_ = _exec_hook(
        gate_a="1",
        gate_b=None,
        result=_FakeSidecar(ok=True, skipped=False, reason="OTHER", n_rows=4),
    )
    assert captions == []
    assert warnings == []


def test_gate_b_stays_off_on_wrote_caption():
    captions, warnings, _ns, before, after = _exec_hook(
        gate_a="1",
        gate_b=None,
        result=_FakeSidecar(ok=True, skipped=False, reason=REASON_WROTE, n_rows=1),
    )
    assert captions == [f"{CAPTION_PREFIX}1"]
    assert warnings == []
    assert "modules.live_candidate_v2_camera.github_bus" not in (after - before)
    src = _app_source()
    try_node = _v2_hook_try_node(src)
    gate_a = None
    for node in try_node.body:
        if isinstance(node, ast.If) and "cloud_hook" in ast.dump(node):
            gate_a = node
            break
    assert gate_a is not None
    gate_b = None
    for node in ast.walk(gate_a):
        if (
            isinstance(node, ast.If)
            and node is not gate_a
            and "github_bus" in ast.dump(node)
        ):
            gate_b = node
            break
    assert gate_b is not None
    cap_dump = ""
    for node in gate_a.body:
        blob = ast.dump(node)
        if "LCV2-GATE-A-WROTE" in blob or "caption" in blob:
            cap_dump = blob
            break
    assert "caption" in cap_dump
    assert "github_bus" not in cap_dump
    assert "maybe_publish_v2_sidecar" not in cap_dump
    assert "github_bus" in ast.dump(gate_b)
    assert "LCV2-GATE-A-WROTE" not in ast.dump(gate_b)
