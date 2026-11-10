"""The reference server serves one authenticated file and nothing else."""

import json

from research.guardian_research.reference_server import ReferenceServerError, create_app, serve


def _call(app, method, path, token=""):
    captured = {}

    def start_response(status, headers):
        captured["status"] = int(status.split()[0])

    environ = {"REQUEST_METHOD": method, "PATH_INFO": path}
    if token:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    body = b"".join(app(environ, start_response))
    return captured["status"], body


def test_get_requires_bearer_and_rejects_every_other_route(tmp_path):
    (tmp_path / "reference_store.json").write_text('{"ok":true}\n', encoding="utf-8")
    app = create_app(tmp_path, "secret")
    status, body = _call(app, "GET", "/current/guardian_research/reference_store.json")
    assert status == 401
    assert b"reference_store" not in body
    status, body = _call(app, "GET", "/current/guardian_research/reference_store.json", "secret")
    assert status == 200
    assert json.loads(body) == {"ok": True}
    status, _ = _call(app, "GET", "/current/guardian_research/reference_store.json", "wrong")
    assert status == 401
    status, _ = _call(app, "PUT", "/current/guardian_research/reference_store.json", "secret")
    assert status == 405
    status, _ = _call(app, "GET", "/current/bundle.tar.gz", "secret")
    assert status == 404
    status, body = _call(app, "GET", "/health")
    assert status == 200
    assert b"reference_store.json" not in body


def test_symlink_outside_the_root_is_not_served(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text('{"secret":true}\n', encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "reference_store.json").symlink_to(outside)
    app = create_app(root, "secret")
    status, body = _call(app, "GET", "/current/guardian_research/reference_store.json", "secret")
    assert status == 404
    assert b"secret" not in body


def test_server_refuses_a_public_bind_and_the_camera_archive(tmp_path):
    try:
        serve(tmp_path, "secret", host="0.0.0.0", port=9)
    except ReferenceServerError as exc:
        assert exc.reason == "NON_LOOPBACK_BIND"
    else:
        raise AssertionError("public bind must be refused")
    try:
        serve("/var/lib/mrbot/intraday_memory", "secret", host="127.0.0.1", port=9)
    except ReferenceServerError as exc:
        assert exc.reason == "ROOT_OVERLAPS_ARCHIVE"
    else:
        raise AssertionError("archive root must be refused")
