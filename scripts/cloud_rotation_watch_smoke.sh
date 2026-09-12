#!/usr/bin/env bash
# HUMAN-ONLY public HTTPS Rotation Watch smoke.
# Proves: production reverse proxy → authenticated Rotation GET.
# Never prints bearer values. Never puts the bearer on argv / curl -H.
# Does not deploy Streamlit, restart services, edit nginx, or merge.
#
# Preferred host: mrbot-camera as root (same as VPS A–G).
#   cd /root && /tmp/cloud_rotation_watch_smoke.sh
#
# Token source (first available, never echoed):
#   1. /etc/mrbot/edge-artifacts.env  key EDGE_RESEARCH_ARTIFACT_TOKEN
#   2. already-exported EDGE_RESEARCH_ARTIFACT_TOKEN / EDGE_RESEARCH_DURABLE_TOKEN
#   3. hidden getpass if a TTY is available
#
# Public URL source (first available; repo has no production hostname):
#   1. already-exported EDGE_RESEARCH_DURABLE_URL (URL only — not the bearer)
#   2. same env-file key EDGE_RESEARCH_DURABLE_URL if an operator added it
#   3. nginx server_name + location /edge-research/
#   Unknown hostname → STOP (do not guess).
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,22p' "$0"
  exit 0
fi

exec python3 - "$0" <<'PY'
from __future__ import annotations

import getpass
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ENV_FILE = Path("/etc/mrbot/edge-artifacts.env")
NGINX_DIRS = (
    Path("/etc/nginx/sites-enabled"),
    Path("/etc/nginx/conf.d"),
    Path("/etc/nginx/sites-available"),
    Path("/etc/nginx"),
)
TOKEN_KEYS = ("EDGE_RESEARCH_ARTIFACT_TOKEN", "EDGE_RESEARCH_DURABLE_TOKEN")
URL_KEYS = ("EDGE_RESEARCH_DURABLE_URL",)
PLACEHOLDER_HOSTS = {
    "your-domain",
    "artifacts.example.com",
    "vps.example",
    "mrbot-edge.example.test",
    "example.test",
    "localhost",
    "127.0.0.1",
}


def die(msg: str) -> None:
    print(f"STOP: {msg}", file=sys.stderr)
    raise SystemExit(2)


def load_kv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        die(f"cannot read {path} ({type(exc).__name__})")
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, val = s.split("=", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def first_nonempty(*vals: str | None) -> str:
    for v in vals:
        if v and str(v).strip():
            return str(v).strip()
    return ""


def env_file_map() -> dict[str, str]:
    return load_kv_file(ENV_FILE)


def load_token() -> tuple[str, str]:
    file_map = env_file_map()
    for key in TOKEN_KEYS:
        val = first_nonempty(file_map.get(key), os.environ.get(key))
        if val:
            return val, f"{ENV_FILE if file_map.get(key) else 'process-env'}:{key}"
    if sys.stdin.isatty():
        print(
            "Token file/env missing. Hidden input (not echoed, not stored). "
            "Do not paste the bearer into chat.",
            file=sys.stderr,
        )
        val = getpass.getpass("Bearer (hidden): ")
        if val.strip():
            return val.strip(), "hidden-tty"
    die(
        "bearer source missing — expected "
        f"{ENV_FILE} key EDGE_RESEARCH_ARTIFACT_TOKEN. "
        "Do not put the bearer on the command line."
    )
    raise AssertionError


def _nginx_texts() -> list[str]:
    blobs: list[str] = []
    seen: set[Path] = set()
    for root in NGINX_DIRS:
        if root.is_file() and root not in seen:
            try:
                blobs.append(root.read_text(encoding="utf-8", errors="replace"))
                seen.add(root)
            except OSError:
                pass
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.endswith("~") or path.name.startswith("."):
                continue
            if path.suffix and path.suffix not in {".conf", ".txt"}:
                continue
            if path in seen:
                continue
            try:
                blobs.append(path.read_text(encoding="utf-8", errors="replace"))
                seen.add(path)
            except OSError:
                continue
    return blobs


def _server_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    i = 0
    while True:
        j = text.find("server", i)
        if j < 0:
            break
        k = text.find("{", j)
        if k < 0:
            break
        depth = 0
        end = None
        for n, ch in enumerate(text[k:], k):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = n
                    break
        if end is None:
            break
        blocks.append(text[j : end + 1])
        i = end + 1
    return blocks


def discover_from_nginx() -> list[str]:
    found: list[str] = []
    for blob in _nginx_texts():
        for block in _server_blocks(blob):
            if "/edge-research" not in block:
                continue
            names: list[str] = []
            for line in block.splitlines():
                s = line.strip()
                if s.startswith("server_name"):
                    rest = s[len("server_name") :].strip().rstrip(";")
                    names.extend(p for p in rest.split() if p and p != "_")
            if not names:
                continue
            host = names[0]
            loc = "/edge-research"
            for line in block.splitlines():
                s = line.strip()
                if s.startswith("location") and "edge-research" in s:
                    parts = s.split()
                    for p in parts[1:]:
                        if p.startswith("/"):
                            loc = p.rstrip("{").strip()
                            break
            loc = "/" + loc.strip("/")
            found.append(f"https://{host}{loc}")
    # unique preserve order
    out: list[str] = []
    for item in found:
        if item not in out:
            out.append(item)
    return out


def normalize_base(url: str, *, source: str) -> str:
    raw = url.strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        die(f"public smoke requires https (source={source}; scheme={parsed.scheme or 'missing'})")
    host = (parsed.hostname or "").lower()
    if not host or host in PLACEHOLDER_HOSTS:
        die(f"hostname unknown or placeholder ({host or 'empty'}; source={source})")
    if parsed.port not in (None, 443):
        die(f"unexpected TLS port {parsed.port} (source={source})")
    path = parsed.path.rstrip("/") or "/edge-research"
    return f"https://{parsed.netloc}{path}"


def load_base() -> tuple[str, str]:
    file_map = env_file_map()
    env_url = first_nonempty(*(os.environ.get(k) for k in URL_KEYS))
    if env_url:
        return normalize_base(env_url, source="process-env:EDGE_RESEARCH_DURABLE_URL"), "process-env"
    file_url = first_nonempty(*(file_map.get(k) for k in URL_KEYS))
    if file_url:
        return normalize_base(file_url, source=f"{ENV_FILE}:EDGE_RESEARCH_DURABLE_URL"), str(ENV_FILE)
    nginx = discover_from_nginx()
    if len(nginx) == 1:
        return normalize_base(nginx[0], source="nginx:/edge-research/"), "nginx"
    if len(nginx) > 1:
        die(
            "ambiguous public hostname from nginx. "
            "Export EDGE_RESEARCH_DURABLE_URL (URL only, from Streamlit Secrets) "
            "and rerun. Do not put the bearer on the command line."
        )
    die(
        "public HTTPS hostname unknown. Repo docs only have placeholders "
        "(your-domain / artifacts.example.com). Run on mrbot-camera so nginx "
        "location /edge-research/ can be read, or export EDGE_RESEARCH_DURABLE_URL "
        "(URL only). Do not guess a host. Do not put the bearer on the command line."
    )
    raise AssertionError


def http_get(url: str, token: str | None, timeout: int = 20) -> tuple[int, bytes, str]:
    headers = {"User-Agent": "mrbot-rotation-https-smoke/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return int(resp.status), resp.read(), ""
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read() if exc.fp else b"", ""
    except ssl.SSLError as exc:
        die(f"TLS failed for public GET ({type(exc).__name__})")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        rname = type(reason).__name__
        if isinstance(reason, ssl.SSLError) or "SSL" in rname:
            die("TLS failed for public GET")
        die(f"public GET failed ({rname}) — proxy/DNS/TLS")
    except Exception as exc:  # noqa: BLE001
        die(f"public GET failed ({type(exc).__name__})")
    raise AssertionError


def main() -> int:
    if any("=" in a and "TOKEN" in a.upper() for a in sys.argv):
        die("refuse TOKEN= on the command line")
    base, base_src = load_base()
    token, token_src = load_token()
    parsed = urlparse(base)
    print(f"DURABLE_SCHEME={parsed.scheme}")
    print(f"DURABLE_HOST={parsed.netloc}")
    print(f"DURABLE_PREFIX={parsed.path or '/'}")
    print(f"URL_SOURCE={base_src}")
    print(f"TOKEN_SOURCE={token_src}")
    print("TOKEN_PRINTED=no")

    health_code, _, _ = http_get(f"{base}/health", None)
    print(f"HEALTH={health_code}")
    if health_code == 0:
        die("health request did not complete")
    if health_code != 200:
        die(f"public /health expected 200, got {health_code} (proxy/route/TLS)")

    board_url = f"{base}/current/rotation_watch/board.json"
    status_url = f"{base}/current/rotation_watch/status.json"
    cand_url = f"{base}/current/live_shadow/live_evidence.jsonl"

    rot_b_unauth, _, _ = http_get(board_url, None)
    rot_s_unauth, _, _ = http_get(status_url, None)
    print(f"ROTATION_BOARD_UNAUTH={rot_b_unauth}")
    print(f"ROTATION_STATUS_UNAUTH={rot_s_unauth}")
    if rot_b_unauth in {0, 404} or rot_s_unauth in {0, 404}:
        die("Rotation public route absent or not the artifact server (unauth 404/000)")
    if rot_b_unauth != 401 or rot_s_unauth != 401:
        die(f"Rotation unauth expected 401/401, got {rot_b_unauth}/{rot_s_unauth}")

    rot_b, board_raw, _ = http_get(board_url, token)
    print(f"ROTATION_BOARD_AUTH={rot_b}")
    if rot_b == 401:
        die("Rotation board auth 401 — bearer rejected")
    if rot_b != 200:
        die(f"Rotation board auth expected 200, got {rot_b}")
    try:
        board = json.loads(board_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        die("Rotation board is not valid JSON")
    if not isinstance(board, dict) or board.get("schema") != "rotation_watch_board.v1":
        die(f"board schema expected rotation_watch_board.v1, got {board.get('schema') if isinstance(board, dict) else type(board).__name__}")
    rows = board.get("rows") or []
    tch = next((r for r in rows if str(r.get("symbol") or "") == "TCH"), None)
    if tch is None:
        die("TCH row missing from public board")
    session = str(tch.get("session_phase") or board.get("session_phase") or "")
    last_state = str(tch.get("last_session_state") or "")
    last_action = str(tch.get("last_session_action") or "")
    action = str(tch.get("suggested_action") or "")
    print("BOARD_SCHEMA", board.get("schema"))
    print("BOARD_SESSION", board.get("session_phase"))
    print(
        "ROW",
        json.dumps(
            {
                "symbol": tch.get("symbol"),
                "current_price": tch.get("current_price"),
                "location": tch.get("location"),
                "last_session_state": tch.get("last_session_state"),
                "last_session_action": tch.get("last_session_action"),
                "suggested_action": tch.get("suggested_action"),
                "published_pxv": tch.get("published_pxv"),
                "freshness": tch.get("freshness"),
                "session_phase": tch.get("session_phase"),
                "actionable": tch.get("actionable"),
                "last_bar_ts": tch.get("last_bar_ts"),
                "data_source": tch.get("data_source"),
            },
            ensure_ascii=False,
        ),
    )
    if session != "WEEKEND":
        die(f"session expected WEEKEND, got {session}")
    if not last_state or last_state == "DATA_UNCERTAIN":
        die("historical last_session_state missing")
    if not last_action:
        die("historical last_session_action missing")
    if action != "WAIT":
        die(f"current suggested_action expected WAIT, got {action}")
    if tch.get("actionable") is True:
        die("weekend artifact must not be actionable")
    if action in {"BUY READY", "SELL READY"}:
        die("weekend current action must not be BUY/SELL")

    rot_s, status_raw, _ = http_get(status_url, token)
    print(f"ROTATION_STATUS_AUTH={rot_s}")
    if rot_s != 200:
        die(f"Rotation status auth expected 200, got {rot_s}")
    try:
        status = json.loads(status_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        die("Rotation status is not valid JSON")
    if not isinstance(status, dict) or status.get("schema") != "rotation_watch_status.v1":
        die(
            "status schema expected rotation_watch_status.v1, got "
            f"{status.get('schema') if isinstance(status, dict) else type(status).__name__}"
        )
    print("STATUS_SCHEMA", status.get("schema"))
    print("STATUS_SESSION", status.get("session_phase"))

    cand, _, _ = http_get(cand_url, token)
    print(f"CANDIDATE_AUTH_GET={cand}")
    if cand not in {200, 404}:
        die(f"Candidate auth expected 200 or legitimate 404, got {cand}")
    if cand == 404:
        print("CANDIDATE_NOTE=404 empty live-shadow store is legitimate")

    token = ""
    del token
    print("OK: public HTTPS Rotation GET (bearer not printed; Streamlit Cloud not claimed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
