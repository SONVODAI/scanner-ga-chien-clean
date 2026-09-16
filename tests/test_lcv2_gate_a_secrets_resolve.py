"""Gate A env-then-secrets resolution. Default OFF. Gate B unchanged.

Never logs or renders secret values. Test fixtures use only the public
truthy flag tokens (1 / true), not credentials.
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
    run_v2_cloud_sidecar,
)
from modules.live_candidate_v2_camera.contract import (
    ENV_V2_CLOUD_SIDECAR,
    ENV_V2_CLOUD_SIDECAR_TRUTHY,
    ENV_V2_GITHUB_PUBLISH,
)

REPO = Path(__file__).resolve().parents[1]
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CAPTION_PREFIX = "LCV2-GATE-A-WROTE rows="
TRUTHY = ("1", "true", "yes", "on")


def _app_source() -> str:
    return (REPO / "app.py").read_text(encoding="utf-8")


def _v2_hook_try_node(src: str | None = None) -> ast.Try:
    tree = ast.parse(src or _app_source())
    for node in tree.body:
        if isinstance(node, ast.Try) and "run_v2_cloud_sidecar" in ast.dump(node):
            return node
    raise AssertionError("V2 sidecar Try block not found in app.py")


def _hook_src() -> str:
    src = ast.get_source_segment(_app_source(), _v2_hook_try_node())
    assert src
    return src


class _FakeSidecar:
    def __init__(self, *, ok, skipped, reason, n_rows=0, error=""):
        self.ok = ok
        self.skipped = skipped
        self.reason = reason
        self.n_rows = n_rows
        self.error = error
        self.path = ""
        self.snapshot_text = ""


class _Secrets:
    def __init__(self, value=None, *, error: Exception | None = None):
        self._value = value
        self._error = error
        self.calls = 0

    def get(self, name, default=""):
        self.calls += 1
        if self._error is not None:
            raise self._error
        if name != ENV_V2_CLOUD_SIDECAR:
            return default
        if self._value is None:
            return default
        return self._value


def _scan_hpg() -> dict:
    return {
        "symbol": "HPG",
        "date": "2026-08-14",
        "group": "PULL ĐẸP",
        "price": 27.5,
        "ema9": 27.1,
        "breakout_ref": 28.0,
        "dist_from_ema9_pct": 1.4,
        "total_score": 5,
        "obv_status": "🟢",
        "warning": "",
    }


def _exec_hook(*, env_a=None, env_b=None, secrets=None, result=None, real_runner=None):
    captured: dict = {}
    captions: list[str] = []
    warnings: list[str] = []
    import modules.live_candidate_v2_camera.cloud_hook as ch

    orig = ch.run_v2_cloud_sidecar

    def runner(**kwargs):
        captured["kwargs"] = kwargs
        if real_runner is not None:
            return real_runner(**kwargs)
        assert result is not None
        return result

    ch.run_v2_cloud_sidecar = runner  # type: ignore[assignment]
    before_v2 = {k for k in sys.modules if "live_candidate_v2" in k}
    before_gh = {k for k in sys.modules if "github_bus" in k}
    ns = {
        "os": os,
        "scan_df": pd.DataFrame([_scan_hpg()]),
        "market_real": 7.2,
        "vn_now": lambda: datetime(2026, 8, 14, 10, 5, tzinfo=VN),
        "buy_elite_df": pd.DataFrame(),
        "early_buy_lab_df": pd.DataFrame(),
        "st": types.SimpleNamespace(
            warning=lambda msg: warnings.append(str(msg)),
            caption=lambda msg: captions.append(str(msg)),
            secrets=secrets if secrets is not None else _Secrets(None),
        ),
    }
    saved_a = os.environ.get(ENV_V2_CLOUD_SIDECAR)
    saved_b = os.environ.get(ENV_V2_GITHUB_PUBLISH)
    try:
        os.environ.pop(ENV_V2_CLOUD_SIDECAR, None)
        os.environ.pop(ENV_V2_GITHUB_PUBLISH, None)
        if env_a is not None:
            os.environ[ENV_V2_CLOUD_SIDECAR] = env_a
        if env_b is not None:
            os.environ[ENV_V2_GITHUB_PUBLISH] = env_b
        exec(compile(_hook_src(), "app.py", "exec"), ns, ns)
    finally:
        ch.run_v2_cloud_sidecar = orig
        os.environ.pop(ENV_V2_CLOUD_SIDECAR, None)
        os.environ.pop(ENV_V2_GITHUB_PUBLISH, None)
        if saved_a is not None:
            os.environ[ENV_V2_CLOUD_SIDECAR] = saved_a
        if saved_b is not None:
            os.environ[ENV_V2_GITHUB_PUBLISH] = saved_b
    after_v2 = {k for k in sys.modules if "live_candidate_v2" in k}
    after_gh = {k for k in sys.modules if "github_bus" in k}
    return {
        "captions": captions,
        "warnings": warnings,
        "captured": captured,
        "ns": ns,
        "imported_v2": bool(after_v2 - before_v2),
        "imported_github": "modules.live_candidate_v2_camera.github_bus" in (after_gh - before_gh),
        "sidecar_bound": "_v2_sidecar" in ns,
    }


def test_hook_uses_env_then_secrets_and_passes_env_kwarg():
    src = _hook_src()
    env_i = src.index('os.environ.get("MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR", "")')
    sec_i = src.index('st.secrets.get("MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR", "")')
    call_i = src.index("run_v2_cloud_sidecar(")
    pub_i = src.index("_v2_pub_gate")
    assert env_i < sec_i < call_i < pub_i
    assert 'env={"MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR": _v2_gate}' in src
    env_b = src.index('os.environ.get("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH", "")')
    sec_b = src.index('st.secrets.get("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH", "")')
    pub_call = src.index("maybe_publish_v2_sidecar(")
    assert call_i < env_b < sec_b < pub_call
    assert 'env={"MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH": _v2_pub_gate}' in src


def test_env_gate_a_on_still_writes_via_passed_env():
    got = _exec_hook(
        env_a="1",
        secrets=_Secrets(None),
        result=_FakeSidecar(ok=True, skipped=False, reason=REASON_WROTE, n_rows=2),
    )
    assert got["captions"] == [f"{CAPTION_PREFIX}2"]
    assert got["warnings"] == []
    env = got["captured"]["kwargs"]["env"]
    assert env == {ENV_V2_CLOUD_SIDECAR: "1"}
    assert got["imported_github"] is False


def test_empty_env_secrets_one_enters_and_passes_resolved_flag():
    got = _exec_hook(
        env_a=None,
        secrets=_Secrets("1"),
        result=_FakeSidecar(ok=True, skipped=False, reason=REASON_WROTE, n_rows=1),
    )
    assert got["sidecar_bound"] is True
    env = got["captured"]["kwargs"]["env"]
    assert list(env) == [ENV_V2_CLOUD_SIDECAR]
    assert env[ENV_V2_CLOUD_SIDECAR] in TRUTHY
    assert got["captions"] == [f"{CAPTION_PREFIX}1"]
    assert got["warnings"] == []
    assert got["imported_github"] is False


def test_secrets_int_one_normalizes_to_truthy_and_passed_env():
    got = _exec_hook(
        env_a=None,
        secrets=_Secrets(1),
        result=_FakeSidecar(ok=True, skipped=False, reason=REASON_WROTE, n_rows=1),
    )
    env = got["captured"]["kwargs"]["env"]
    assert env[ENV_V2_CLOUD_SIDECAR] == "1"
    assert got["captions"] == [f"{CAPTION_PREFIX}1"]
    assert got["warnings"] == []


def test_passed_env_produces_wrote_not_gate_off_when_os_environ_empty(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_V2_CLOUD_SIDECAR, raising=False)
    dest = tmp_path / "camera_sidecar.json"
    result = run_v2_cloud_sidecar(
        scan_rows=[_scan_hpg()],
        market_real=7.2,
        observed_at=datetime(2026, 8, 14, 10, 5, tzinfo=VN),
        path=dest,
        env={ENV_V2_CLOUD_SIDECAR: "1"},
    )
    assert result.ok is True
    assert result.skipped is False
    assert result.reason == REASON_WROTE
    assert dest.exists()

    def real_runner(**kwargs):
        kwargs = dict(kwargs)
        kwargs["path"] = dest
        kwargs["scan_rows"] = [_scan_hpg()]
        kwargs["observed_at"] = datetime(2026, 8, 14, 11, 0, tzinfo=VN)
        return run_v2_cloud_sidecar(**kwargs)

    got = _exec_hook(env_a=None, secrets=_Secrets("1"), real_runner=real_runner)
    assert got["captured"]["kwargs"]["env"] == {ENV_V2_CLOUD_SIDECAR: "1"}
    sidecar = got["ns"]["_v2_sidecar"]
    assert sidecar.reason == REASON_WROTE
    assert sidecar.skipped is False
    assert got["captions"] and got["captions"][0].startswith(CAPTION_PREFIX)
    assert got["warnings"] == []
    assert got["imported_github"] is False


def test_missing_secret_is_off_no_v2_import():
    got = _exec_hook(env_a=None, secrets=_Secrets(None), result=_FakeSidecar(
        ok=True, skipped=True, reason=REASON_GATE_OFF
    ))
    assert got["captured"] == {}
    assert got["sidecar_bound"] is False
    assert got["captions"] == []
    assert got["warnings"] == []


def test_secrets_access_exception_is_off():
    got = _exec_hook(
        env_a=None,
        secrets=_Secrets(error=RuntimeError("unavailable")),
        result=_FakeSidecar(ok=True, skipped=True, reason=REASON_GATE_OFF),
    )
    assert got["captured"] == {}
    assert got["sidecar_bound"] is False
    assert got["captions"] == []
    assert got["warnings"] == []


def test_gate_a_off_subprocess_no_v2_import():
    script = (
        "import os, sys, types\n"
        "from datetime import datetime\n"
        "from zoneinfo import ZoneInfo\n"
        "import pandas as pd\n"
        "os.environ.pop(%r, None)\n"
        "os.environ.pop(%r, None)\n"
        "before = {k for k in sys.modules if 'live_candidate_v2' in k}\n"
        "ns = {\n"
        "    'os': os,\n"
        "    'scan_df': pd.DataFrame([{'symbol': 'HPG'}]),\n"
        "    'market_real': 7.2,\n"
        "    'vn_now': lambda: datetime.now(tz=ZoneInfo('Asia/Ho_Chi_Minh')),\n"
        "    'buy_elite_df': pd.DataFrame(),\n"
        "    'early_buy_lab_df': pd.DataFrame(),\n"
        "    'st': types.SimpleNamespace(\n"
        "        warning=lambda msg: (_ for _ in ()).throw(AssertionError(msg)),\n"
        "        caption=lambda msg: (_ for _ in ()).throw(AssertionError(msg)),\n"
        "    ),\n"
        "}\n"
        "hook = %r\n"
        "exec(compile(hook, 'app.py', 'exec'), ns, ns)\n"
        "after = {k for k in sys.modules if 'live_candidate_v2' in k}\n"
        "assert after == before\n"
        "assert '_v2_sidecar' not in ns\n"
        "print('OK')\n"
    ) % (ENV_V2_CLOUD_SIDECAR, ENV_V2_GITHUB_PUBLISH, _hook_src())
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {ENV_V2_CLOUD_SIDECAR, ENV_V2_GITHUB_PUBLISH}
    }
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


def test_wrote_empty_caption_zero():
    got = _exec_hook(
        env_a="1",
        result=_FakeSidecar(ok=True, skipped=False, reason=REASON_WROTE, n_rows=0),
    )
    assert got["captions"] == [f"{CAPTION_PREFIX}0"]
    assert got["warnings"] == []


def test_load_failed_warning_no_caption():
    got = _exec_hook(
        env_a="1",
        result=_FakeSidecar(
            ok=False, skipped=False, reason=REASON_LOAD_FAILED, error="corrupted sidecar JSON: x"
        ),
    )
    assert got["captions"] == []
    assert got["warnings"] == ["V2 Camera sidecar: corrupted sidecar JSON: x"]
    assert got["imported_github"] is False


def test_write_failed_warning_no_caption():
    got = _exec_hook(
        env_a="1",
        result=_FakeSidecar(
            ok=False, skipped=False, reason=REASON_WRITE_FAILED, error="OSError: disk full"
        ),
    )
    assert got["captions"] == []
    assert got["warnings"] == ["V2 Camera sidecar: OSError: disk full"]


def test_gate_b_unset_not_imported_on_secrets_wrote():
    got = _exec_hook(
        env_a=None,
        secrets=_Secrets("1"),
        result=_FakeSidecar(ok=True, skipped=False, reason=REASON_WROTE, n_rows=3),
    )
    assert got["imported_github"] is False
    assert "maybe_publish_v2_sidecar" not in got["ns"]
    src = _hook_src()
    pub = src[src.index("_v2_pub_gate") :]
    assert 'os.environ.get("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH", "")' in pub
    assert 'st.secrets.get("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH", "")' in pub
    assert set(ENV_V2_CLOUD_SIDECAR_TRUTHY) == set(TRUTHY)
