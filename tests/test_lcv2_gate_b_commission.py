"""Gate B commissioning: secrets-safe flag, token, PUT→GET, sanitized UI.

Default OFF. Empty universe is success. No VPS/KBS/runner. No production path.
"""

from __future__ import annotations

import ast
import email.message
import json
import os
import subprocess
import sys
import types
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.live_candidate_v2_camera.cloud_hook import REASON_WROTE
from modules.live_candidate_v2_camera.contract import (
    ENV_V2_CLOUD_SIDECAR,
    ENV_V2_GITHUB_PUBLISH,
    ENV_V2_GITHUB_PUBLISH_TRUTHY,
    GITHUB_V2_SIDECAR_PATH,
    PRODUCTION_WATCHLIST_RELPATH,
)
from modules.live_candidate_v2_camera.github_bus import (
    STATUS_INVALID_DOCUMENT,
    STATUS_OK_EMPTY,
    STATUS_OK_ROWS,
    STATUS_PUBLISHED,
    STATUS_TRANSPORT_ERROR,
    V2FetchResult,
    V2PublishResult,
    fetch_v2_sidecar,
    maybe_publish_v2_sidecar,
    resolve_v2_github_token,
    sanitize_v2_github_message,
    v2_github_contents_writer,
)
from modules.live_shadow_transport.contract import GITHUB_WATCHLIST_PATH

REPO = Path(__file__).resolve().parents[1]
VN = ZoneInfo("Asia/Ho_Chi_Minh")
SAMPLE = REPO / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.sample.json"
CAPTION_A = "LCV2-GATE-A-WROTE rows="
CAPTION_B = "LCV2-GATE-B-GITHUB status="
TRUTHY = ("1", "true", "yes", "on")
PROD_WATCHLIST = REPO / PRODUCTION_WATCHLIST_RELPATH
_TOK_ENV = "envtok"
_TOK_SEC = "sectok"


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


def _empty_doc_text() -> str:
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    doc["rows"] = []
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def _rows_doc_text() -> str:
    return SAMPLE.read_text(encoding="utf-8")


class _Secrets:
    def __init__(self, mapping=None, *, error: Exception | None = None):
        self._mapping = dict(mapping or {})
        self._error = error
        self.calls: list[str] = []

    def get(self, name, default=""):
        self.calls.append(str(name))
        if self._error is not None:
            raise self._error
        if name not in self._mapping:
            return default
        return self._mapping[name]


class _FakeSidecar:
    def __init__(
        self,
        *,
        ok=True,
        skipped=False,
        reason=REASON_WROTE,
        n_rows=0,
        error="",
        path="research/live_candidate_v2_camera_sidecar/camera_sidecar.json",
        snapshot_text="",
    ):
        self.ok = ok
        self.skipped = skipped
        self.reason = reason
        self.n_rows = n_rows
        self.error = error
        self.path = path
        self.snapshot_text = snapshot_text


class RecWriter:
    def __init__(self, status="GITHUB_OK"):
        self.calls: list[tuple[str, str, str]] = []
        self.status = status

    def __call__(self, path: str, text: str, message: str) -> str:
        assert path == GITHUB_V2_SIDECAR_PATH
        assert path != GITHUB_WATCHLIST_PATH
        assert "dynamic_watchlist.json" not in path
        self.calls.append((path, text, message))
        if self.status == "raise":
            raise RuntimeError("github down")
        return self.status


def _assert_no_token_leak(*blobs: object) -> None:
    joined = "\n".join(str(b) for b in blobs)
    for needle in (_TOK_ENV, _TOK_SEC, "ghp_", "github_pat_", "Bearer ", "Authorization:"):
        assert needle not in joined


def _exec_hook(
    *,
    env_a=None,
    env_b=None,
    secrets=None,
    sidecar=None,
    publish=None,
    fetch=None,
    load_boom=False,
):
    captions: list[str] = []
    warnings: list[str] = []
    pub_kwargs: dict = {}
    fetch_calls: list[dict] = []
    import modules.live_candidate_v2_camera.cloud_hook as ch
    import modules.live_candidate_v2_camera.github_bus as gb

    orig_run = ch.run_v2_cloud_sidecar
    orig_pub = gb.maybe_publish_v2_sidecar
    orig_fetch = gb.fetch_v2_sidecar
    orig_load = gb.load_local_v2_sidecar_text

    def runner(**kwargs):
        assert sidecar is not None
        return sidecar

    def publisher(**kwargs):
        pub_kwargs.update(kwargs)
        if publish is not None:
            return publish
        return orig_pub(**kwargs)

    def fetcher(**kwargs):
        fetch_calls.append(dict(kwargs))
        if fetch is not None:
            return fetch
        return orig_fetch(**kwargs)

    def boom_load(*args, **kwargs):
        raise AssertionError("must not reopen local sidecar when snapshot_text supplied")

    ch.run_v2_cloud_sidecar = runner  # type: ignore[assignment]
    gb.maybe_publish_v2_sidecar = publisher  # type: ignore[assignment]
    gb.fetch_v2_sidecar = fetcher  # type: ignore[assignment]
    if load_boom:
        gb.load_local_v2_sidecar_text = boom_load  # type: ignore[assignment]

    before_gh = "modules.live_candidate_v2_camera.github_bus" in sys.modules
    ns = {
        "os": os,
        "scan_df": pd.DataFrame([{"symbol": "HPG"}]),
        "market_real": 7.2,
        "vn_now": lambda: datetime(2026, 8, 14, 10, 5, tzinfo=VN),
        "buy_elite_df": pd.DataFrame(),
        "early_buy_lab_df": pd.DataFrame(),
        "st": types.SimpleNamespace(
            warning=lambda msg: warnings.append(str(msg)),
            caption=lambda msg: captions.append(str(msg)),
            secrets=secrets if secrets is not None else _Secrets({}),
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
        ch.run_v2_cloud_sidecar = orig_run
        gb.maybe_publish_v2_sidecar = orig_pub
        gb.fetch_v2_sidecar = orig_fetch
        gb.load_local_v2_sidecar_text = orig_load
        os.environ.pop(ENV_V2_CLOUD_SIDECAR, None)
        os.environ.pop(ENV_V2_GITHUB_PUBLISH, None)
        if saved_a is not None:
            os.environ[ENV_V2_CLOUD_SIDECAR] = saved_a
        if saved_b is not None:
            os.environ[ENV_V2_GITHUB_PUBLISH] = saved_b
    for key in ("_v2_gate_a_caption", "_v2_gate_b_caption"):
        val = ns.get(key)
        if val:
            captions.append(str(val))
    return {
        "captions": captions,
        "warnings": warnings,
        "pub_kwargs": pub_kwargs,
        "fetch_calls": fetch_calls,
        "ns": ns,
        "imported_github": (not before_gh)
        and ("modules.live_candidate_v2_camera.github_bus" in sys.modules)
        and ("maybe_publish_v2_sidecar" in ns),
        "bound_publish": "maybe_publish_v2_sidecar" in ns,
    }


def test_gate_b_resolution_env_then_secrets_ast():
    src = _hook_src()
    env_i = src.index('os.environ.get("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH", "")')
    sec_i = src.index('st.secrets.get("MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH", "")')
    pub_i = src.index("maybe_publish_v2_sidecar(")
    fetch_i = src.index("fetch_v2_sidecar()")
    cap_a = src.index('_v2_gate_a_caption = f"LCV2-GATE-A-WROTE rows={_v2_sidecar.n_rows}"')
    assert cap_a < env_i < sec_i < pub_i < fetch_i
    assert 'env={"MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH": _v2_pub_gate}' in src
    assert "_v2_sidecar.snapshot_text" in src[pub_i : pub_i + 400]
    assert "LCV2-GATE-B-GITHUB status=" in src
    assert set(ENV_V2_GITHUB_PUBLISH_TRUTHY) == set(TRUTHY)


def test_gate_b_env_on_still_works_empty_ok():
    snap = _empty_doc_text()
    sidecar = _FakeSidecar(n_rows=0, snapshot_text=snap)
    got = _exec_hook(
        env_a="1",
        env_b="1",
        sidecar=sidecar,
        publish=V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_EMPTY, n_rows=0),
        load_boom=True,
    )
    assert got["captions"] == [
        f"{CAPTION_A}0",
        f"{CAPTION_B}{STATUS_OK_EMPTY} rows=0",
    ]
    assert got["warnings"] == []
    env = got["pub_kwargs"]["env"]
    assert env == {ENV_V2_GITHUB_PUBLISH: "1"}
    assert got["pub_kwargs"]["snapshot_text"] == snap
    assert got["pub_kwargs"]["path"] == sidecar.path
    assert len(got["fetch_calls"]) == 1
    _assert_no_token_leak(got["captions"], got["warnings"], env)


def test_gate_b_empty_env_secrets_one_works():
    snap = _empty_doc_text()
    sidecar = _FakeSidecar(n_rows=0, snapshot_text=snap)
    secrets = _Secrets({ENV_V2_GITHUB_PUBLISH: "1"})
    got = _exec_hook(
        env_a="1",
        env_b=None,
        secrets=secrets,
        sidecar=sidecar,
        publish=V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_EMPTY, n_rows=0),
    )
    assert ENV_V2_GITHUB_PUBLISH in secrets.calls
    assert got["pub_kwargs"]["env"] == {ENV_V2_GITHUB_PUBLISH: "1"}
    assert got["captions"][-1] == f"{CAPTION_B}{STATUS_OK_EMPTY} rows=0"
    assert got["warnings"] == []
    assert len(got["fetch_calls"]) == 1


def test_gate_b_secrets_int_one_normalizes_and_is_passed():
    snap = _empty_doc_text()
    sidecar = _FakeSidecar(n_rows=0, snapshot_text=snap)
    got = _exec_hook(
        env_a="1",
        env_b=None,
        secrets=_Secrets({ENV_V2_GITHUB_PUBLISH: 1}),
        sidecar=sidecar,
        publish=V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_EMPTY, n_rows=0),
    )
    assert got["pub_kwargs"]["env"] == {ENV_V2_GITHUB_PUBLISH: "1"}
    assert got["captions"][-1] == f"{CAPTION_B}{STATUS_OK_EMPTY} rows=0"


def test_gate_b_missing_secret_is_off():
    sidecar = _FakeSidecar(n_rows=0, snapshot_text=_empty_doc_text())
    got = _exec_hook(
        env_a="1",
        env_b=None,
        secrets=_Secrets({}),
        sidecar=sidecar,
        publish=V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_EMPTY, n_rows=0),
    )
    assert got["pub_kwargs"] == {}
    assert got["fetch_calls"] == []
    assert got["bound_publish"] is False
    assert got["captions"] == [f"{CAPTION_A}0"]
    assert got["warnings"] == []


def test_gate_b_broken_secret_is_off():
    sidecar = _FakeSidecar(n_rows=0, snapshot_text=_empty_doc_text())
    got = _exec_hook(
        env_a="1",
        env_b=None,
        secrets=_Secrets(error=RuntimeError("unavailable")),
        sidecar=sidecar,
        publish=V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_EMPTY, n_rows=0),
    )
    assert got["pub_kwargs"] == {}
    assert got["fetch_calls"] == []
    assert got["bound_publish"] is False
    assert got["captions"] == [f"{CAPTION_A}0"]
    assert got["warnings"] == []


def test_gate_b_off_subprocess_no_github_bus_import_put_get():
    script = (
        "import os, sys, types\n"
        "from datetime import datetime\n"
        "from zoneinfo import ZoneInfo\n"
        "import pandas as pd\n"
        "os.environ['MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR'] = '1'\n"
        "os.environ.pop(%r, None)\n"
        "before = {k for k in sys.modules if 'github_bus' in k or 'watchlist_bus' in k}\n"
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
        "        secrets=types.SimpleNamespace(get=lambda *a, **k: ''),\n"
        "    ),\n"
        "}\n"
        "import modules.live_candidate_v2_camera.cloud_hook as ch\n"
        "class Fake:\n"
        "    ok = True\n"
        "    skipped = False\n"
        "    reason = 'WROTE'\n"
        "    n_rows = 0\n"
        "    error = ''\n"
        "    path = 'research/live_candidate_v2_camera_sidecar/camera_sidecar.json'\n"
        "    snapshot_text = '{ }'\n"
        "ch.run_v2_cloud_sidecar = lambda **k: Fake()\n"
        "hook = %r\n"
        "exec(compile(hook, 'app.py', 'exec'), ns, ns)\n"
        "after = {k for k in sys.modules if 'github_bus' in k or 'watchlist_bus' in k}\n"
        "assert after == before\n"
        "assert 'maybe_publish_v2_sidecar' not in ns\n"
        "assert 'fetch_v2_sidecar' not in ns\n"
        "for key in ('_v2_gate_a_caption', '_v2_gate_b_caption'):\n"
        "    val = ns.get(key)\n"
        "    if val:\n"
        "        captions.append(str(val))\n"
        "assert captions == ['LCV2-GATE-A-WROTE rows=0']\n"
        "print('OK')\n"
    ) % (ENV_V2_GITHUB_PUBLISH, _hook_src())
    env = {k: v for k, v in os.environ.items() if k != ENV_V2_GITHUB_PUBLISH}
    env[ENV_V2_CLOUD_SIDECAR] = "1"
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
    assert "github_bus" not in proc.stdout
    assert "urlopen" not in proc.stdout


def test_nonempty_put_get_ok_rows_caption():
    snap = _rows_doc_text()
    n_rows = len(json.loads(snap)["rows"])
    sidecar = _FakeSidecar(n_rows=n_rows, snapshot_text=snap)
    got = _exec_hook(
        env_a="1",
        env_b="true",
        sidecar=sidecar,
        publish=V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_ROWS, n_rows=n_rows),
    )
    assert got["pub_kwargs"]["env"] == {ENV_V2_GITHUB_PUBLISH: "true"}
    assert got["pub_kwargs"]["snapshot_text"] == snap
    assert got["captions"] == [
        f"{CAPTION_A}{n_rows}",
        f"{CAPTION_B}{STATUS_OK_ROWS} rows={n_rows}",
    ]
    assert got["warnings"] == []
    assert len(got["fetch_calls"]) == 1


def test_put_failure_warning_no_get_no_success_caption(tmp_path):
    dest = tmp_path / "camera_sidecar.json"
    snap = _empty_doc_text()
    dest.write_text(snap, encoding="utf-8")
    before = dest.read_text(encoding="utf-8")
    sidecar = _FakeSidecar(n_rows=0, path=str(dest), snapshot_text=snap)
    got = _exec_hook(
        env_a="1",
        env_b="1",
        sidecar=sidecar,
        publish=V2PublishResult(
            ok=False,
            skipped=False,
            status=STATUS_TRANSPORT_ERROR,
            error="GITHUB_FAIL_401",
        ),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_EMPTY, n_rows=0),
    )
    assert got["fetch_calls"] == []
    assert all(CAPTION_B not in c for c in got["captions"])
    assert got["captions"] == [f"{CAPTION_A}0"]
    assert got["warnings"] == ["V2 Camera sidecar GitHub: GITHUB_FAIL_401"]
    assert dest.read_text(encoding="utf-8") == before
    _assert_no_token_leak(got["warnings"], got["captions"])


def test_get_failure_warning_no_success_caption(tmp_path):
    dest = tmp_path / "camera_sidecar.json"
    snap = _empty_doc_text()
    dest.write_text(snap, encoding="utf-8")
    sidecar = _FakeSidecar(n_rows=0, path=str(dest), snapshot_text=snap)
    got = _exec_hook(
        env_a="1",
        env_b="1",
        sidecar=sidecar,
        publish=V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED),
        fetch=V2FetchResult(
            ok=False,
            status=STATUS_INVALID_DOCUMENT,
            error="invalid or missing schema",
        ),
    )
    assert len(got["fetch_calls"]) == 1
    assert all(CAPTION_B not in c for c in got["captions"])
    assert got["captions"] == [f"{CAPTION_A}0"]
    assert got["warnings"] == ["V2 Camera sidecar GitHub: invalid or missing schema"]
    assert dest.read_text(encoding="utf-8") == snap


def test_get_transport_error_no_success_caption():
    sidecar = _FakeSidecar(n_rows=0, snapshot_text=_empty_doc_text())
    got = _exec_hook(
        env_a="1",
        env_b="1",
        sidecar=sidecar,
        publish=V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED),
        fetch=V2FetchResult(ok=False, status=STATUS_TRANSPORT_ERROR, error="github HTTP 500"),
    )
    assert all(CAPTION_B not in c for c in got["captions"])
    assert got["warnings"] == ["V2 Camera sidecar GitHub: github HTTP 500"]
    assert got["captions"] == [f"{CAPTION_A}0"]


def test_exact_snapshot_text_is_put_writer_skips_local_reopen(tmp_path):
    dest = tmp_path / "camera_sidecar.json"
    snap = _empty_doc_text()
    dest.write_text(snap, encoding="utf-8")
    dest.write_text('{"schema":"stale-local"}', encoding="utf-8")
    writer = RecWriter()

    def boom_load(*args, **kwargs):
        raise AssertionError("must not reopen local sidecar when snapshot_text supplied")

    import modules.live_candidate_v2_camera.github_bus as gb

    orig = gb.load_local_v2_sidecar_text
    gb.load_local_v2_sidecar_text = boom_load  # type: ignore[assignment]
    try:
        pub = maybe_publish_v2_sidecar(
            local_ok=True,
            local_skipped=False,
            path=dest,
            snapshot_text=snap,
            writer=writer,
            env={ENV_V2_GITHUB_PUBLISH: "1"},
        )
    finally:
        gb.load_local_v2_sidecar_text = orig
    assert pub.ok is True
    assert pub.status == STATUS_PUBLISHED
    assert writer.calls[0][0] == GITHUB_V2_SIDECAR_PATH
    assert writer.calls[0][1] == snap
    assert dest.read_text(encoding="utf-8") == '{"schema":"stale-local"}'
    fetched = fetch_v2_sidecar(text_fetcher=lambda **k: writer.calls[0][1])
    assert fetched.status == STATUS_OK_EMPTY
    assert fetched.n_rows == 0


def test_dedicated_v2_path_only_production_untouched():
    assert GITHUB_V2_SIDECAR_PATH == "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"
    assert PRODUCTION_WATCHLIST_RELPATH == "data/live_candidate/dynamic_watchlist.json"
    assert GITHUB_WATCHLIST_PATH == PRODUCTION_WATCHLIST_RELPATH
    assert GITHUB_V2_SIDECAR_PATH != GITHUB_WATCHLIST_PATH
    src = (REPO / "modules" / "live_candidate_v2_camera" / "github_bus.py").read_text(
        encoding="utf-8"
    )
    assert "refusing production dynamic_watchlist.json" in src
    hook = _hook_src()
    assert "dynamic_watchlist.json" not in hook
    assert PROD_WATCHLIST.exists()


def test_token_env_first_does_not_read_secrets(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", _TOK_ENV)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    fake = types.ModuleType("streamlit")

    class Boom:
        def get(self, *a, **k):
            raise AssertionError("secrets must not be read when env token present")

    fake.secrets = Boom()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    got = resolve_v2_github_token()
    assert got == _TOK_ENV
    assert got != ""


def test_token_secrets_fallback_when_env_empty(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    class Sec:
        def get(self, name, default=""):
            if name == "GITHUB_TOKEN":
                return _TOK_SEC
            return default

    fake = types.ModuleType("streamlit")
    fake.secrets = Sec()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    got = resolve_v2_github_token()
    assert bool(got) is True
    assert got == _TOK_SEC


def test_token_broken_secrets_is_empty(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    class Sec:
        def get(self, *a, **k):
            raise RuntimeError("unavailable")

    fake = types.ModuleType("streamlit")
    fake.secrets = Sec()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    assert resolve_v2_github_token() == ""


def test_writer_uses_resolved_token_status_has_no_token(monkeypatch):
    monkeypatch.setattr(
        "modules.live_candidate_v2_camera.github_bus.resolve_v2_github_token",
        lambda: _TOK_SEC,
    )
    seen: list[urllib.request.Request] = []

    class Resp:
        status = 201

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=20):
        seen.append(req)
        if req.get_method() == "GET":
            raise urllib.error.HTTPError(
                req.full_url, 404, "nf", email.message.Message(), None
            )
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    status = v2_github_contents_writer(GITHUB_V2_SIDECAR_PATH, _empty_doc_text(), "m")
    assert status == "GITHUB_OK"
    assert status != "LOCAL_ONLY"
    assert GITHUB_V2_SIDECAR_PATH in seen[0].full_url
    assert "dynamic_watchlist.json" not in seen[0].full_url
    assert _TOK_SEC not in seen[0].full_url
    assert _TOK_SEC not in status
    auth_present = any(
        str(k).lower() == "authorization" for k in (seen[0].headers or {})
    )
    assert auth_present is True


def test_writer_no_token_is_local_only_no_network(monkeypatch):
    monkeypatch.setattr(
        "modules.live_candidate_v2_camera.github_bus.resolve_v2_github_token",
        lambda: "",
    )

    def boom(*a, **k):
        raise AssertionError("network must not run without token")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert v2_github_contents_writer(GITHUB_V2_SIDECAR_PATH, "{}", "m") == "LOCAL_ONLY"


def test_fetch_default_path_passes_resolved_token(monkeypatch):
    monkeypatch.setattr(
        "modules.live_candidate_v2_camera.github_bus.resolve_v2_github_token",
        lambda: _TOK_SEC,
    )
    seen: dict[str, object] = {}

    def getter(*, token=None, path=None, **kwargs):
        seen["has_token"] = bool(token)
        seen["path"] = path
        return _empty_doc_text()

    # Default getter path (text_fetcher is None) must resolve the Cloud token.
    import modules.live_candidate_v2_camera.github_bus as gb

    monkeypatch.setattr(gb, "fetch_github_watchlist_text", getter)
    result = fetch_v2_sidecar()
    assert seen["has_token"] is True
    assert seen["path"] == GITHUB_V2_SIDECAR_PATH
    assert result.status == STATUS_OK_EMPTY
    assert result.n_rows == 0
    assert _TOK_SEC not in str(result.as_dict())


def test_sanitize_never_emits_token_or_query():
    leaked = (
        f"fail Authorization: token {_TOK_SEC} ghp_abcdefghijklmnopqrstuvwxyz012345 "
        "https://api.github.com/repos/o/r/contents/x?access_token=abc"
    )
    out = sanitize_v2_github_message(leaked)
    _assert_no_token_leak(out)
    assert "access_token" not in out
    assert "[REDACTED]" in out
    assert "ghp_" not in out


def test_hook_warnings_sanitize_tokenish_errors():
    sidecar = _FakeSidecar(n_rows=0, snapshot_text=_empty_doc_text())
    got = _exec_hook(
        env_a="1",
        env_b="1",
        sidecar=sidecar,
        publish=V2PublishResult(
            ok=False,
            skipped=False,
            status=STATUS_TRANSPORT_ERROR,
            error=f"token {_TOK_SEC} ghp_abcdefghijklmnopqrstuvwxyz012345",
        ),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_EMPTY, n_rows=0),
    )
    assert got["fetch_calls"] == []
    assert got["warnings"]
    _assert_no_token_leak(got["warnings"], got["captions"])
    assert all(CAPTION_B not in c for c in got["captions"])
    assert got["captions"] == [f"{CAPTION_A}0"]


def test_unrelated_github_token_consumers_untouched():
    app = _app_source()
    assert "def get_github_token():" in app
    fn = app[app.index("def get_github_token():") : app.index("def read_evolution_history()")]
    assert 'return st.secrets.get("GITHUB_TOKEN", None)' in fn
    assert "resolve_v2_github_token" not in fn
    bus = (REPO / "modules" / "live_shadow_transport" / "watchlist_bus.py").read_text(
        encoding="utf-8"
    )
    assert "resolve_v2_github_token" not in bus
    assert "live_candidate_v2_camera.github_bus" not in bus


def test_gate_a_wrote_survives_and_stays_before_gate_b():
    snap = _empty_doc_text()
    sidecar = _FakeSidecar(n_rows=0, snapshot_text=snap)
    got = _exec_hook(
        env_a="1",
        env_b="1",
        sidecar=sidecar,
        publish=V2PublishResult(
            ok=False, skipped=False, status=STATUS_TRANSPORT_ERROR, error="GITHUB_ERROR"
        ),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_EMPTY, n_rows=0),
    )
    assert got["captions"][0] == f"{CAPTION_A}0"
    assert f"{CAPTION_A}0" in got["captions"]
    src = _hook_src()
    assert src.index("LCV2-GATE-A-WROTE") < src.index("LCV2-GATE-B-GITHUB")


def test_no_get_when_gate_a_not_wrote():
    sidecar = _FakeSidecar(
        ok=False, skipped=False, reason="LOAD_FAILED", error="corrupted sidecar JSON: x"
    )
    got = _exec_hook(
        env_a="1",
        env_b="1",
        sidecar=sidecar,
        publish=V2PublishResult(ok=True, skipped=False, status=STATUS_PUBLISHED),
        fetch=V2FetchResult(ok=True, status=STATUS_OK_EMPTY, n_rows=0),
    )
    assert got["pub_kwargs"] == {}
    assert got["fetch_calls"] == []
    assert all(CAPTION_B not in c for c in got["captions"])
    assert got["warnings"] == ["V2 Camera sidecar: corrupted sidecar JSON: x"]
    assert got["bound_publish"] is False
