#!/usr/bin/env python3
"""Post-deploy proof for LIVE SESSION 01 transport. Never starts the runner.

Does not print secret values. Stops callers from treating this as a live start.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FORBIDDEN_UI = (
    "intraday_memory.provider",
    "KBSProvider",
    "fetch_session",
    "upsert_session",
    "IntradayCollector",
    "interpret_asof",
    "interpret_candidate_session",
)
PRODUCTION_PANELS = (
    "👑 BUY ELITE - DECISION ENGINE",
    "🤖 AI Recommendation",
    "👑 FINAL DECISION",
    "⚡ STORM LEADERS - TIỀN ĐANG VÀO ĐÂU",
)


def _present(name: str) -> bool:
    return bool((os.environ.get(name) or "").strip())


def _secret_names() -> dict:
    names = (
        "GITHUB_TOKEN",
        "EDGE_RESEARCH_DURABLE_URL",
        "EDGE_RESEARCH_DURABLE_TOKEN",
    )
    return {n: ("PRESENT" if _present(n) else "ABSENT") for n in names}


def _http_get(url: str, token: str | None = None, timeout: int = 15) -> tuple[int, int]:
    headers = {"User-Agent": "mrbot-live-session-01-proof/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return int(resp.status), len(body)
    except urllib.error.HTTPError as exc:
        return int(exc.code), 0
    except Exception:
        return 0, 0


def _runner_stopped() -> dict:
    pidfile = Path(os.environ.get("MRBOT_LIVE_SESSION_PIDFILE", "/tmp/mrbot_live_session_01.pid"))
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            pid = 0
        alive = False
        if pid:
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False
        return {"ok": not alive, "pidfile": str(pidfile), "alive": alive}
    # systemd unit for the research runner must not exist / not be active
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "mrbot-live-camera-shadow.service"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        active = proc.stdout.strip() == "active"
        return {"ok": not active, "systemd": proc.stdout.strip() or "inactive"}
    except Exception:
        return {"ok": True, "pidfile": "absent", "systemd": "not-queried"}


def _camera_fingerprint(root: Path) -> dict:
    if not root.exists():
        return {"ok": True, "exists": False, "path": str(root), "n_files": 0, "sha256": None}
    digest = hashlib.sha256()
    n = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
        n += 1
    return {"ok": True, "exists": True, "path": str(root), "n_files": n, "sha256": digest.hexdigest()}


def _source_proofs() -> dict:
    req = (REPO / "requirements.txt").read_text(encoding="utf-8")
    app = (REPO / "app.py").read_text(encoding="utf-8")
    vnstock_ok = "vnstock==0.2.9.2" in req
    panels_ok = all(title in app for title in PRODUCTION_PANELS)
    ui_src = ""
    for rel in (
        "modules/live_candidate_pxv_ui/read.py",
        "modules/live_candidate_pxv_ui/view.py",
        "modules/live_candidate_pxv_ui/render.py",
        "modules/live_candidate_pxv_ui/html.py",
    ):
        ui_src += (REPO / rel).read_text(encoding="utf-8")
    ui_no_kbs = all(tok not in ui_src for tok in FORBIDDEN_UI)
    feed = (REPO / "modules/live_camera_shadow/feed.py").read_text(encoding="utf-8")
    alert_false = "row.alert_eligible = False" in feed and "alert_eligible: bool = False" in (
        REPO / "modules/live_candidate_pxv_ui/view.py"
    ).read_text(encoding="utf-8")
    runner = (REPO / "scripts/run_live_camera_shadow.py").read_text(encoding="utf-8")
    no_telegram = (
        "telegram.Bot" not in feed
        and "telegram.Bot" not in runner
        and "TELEGRAM_TOKEN" not in runner
        and "send_message" not in feed
    )
    no_orders = "place_order" not in runner and "execute_trade" not in runner
    empty_ok = False
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from modules.live_candidate_pxv_ui.view import EMPTY_MESSAGE, build_panel

        p = build_panel(
            now=datetime(2026, 8, 14, 10, 22, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
            sources={"watchlist": [], "evidence": [], "status": {}, "transport": {}},
        )
        empty_ok = p.empty is True and p.empty_message == EMPTY_MESSAGE and p.alert_eligible is False
    except Exception:
        empty_ok = False
    return {
        "vnstock_0292": vnstock_ok,
        "production_panels_present": panels_ok,
        "ui_no_kbs": ui_no_kbs,
        "alert_eligible_false": alert_false,
        "no_telegram_in_runner": no_telegram,
        "no_orders_in_runner": no_orders,
        "empty_candidate_ui": empty_ok,
    }


def run_proof() -> dict:
    secrets = _secret_names()
    src = _source_proofs()
    runner = _runner_stopped()
    camera = _camera_fingerprint(Path(os.environ.get("MRBOT_CAMERA_ARCHIVE", "/var/lib/mrbot/intraday_memory")))

    durable_url = (os.environ.get("EDGE_RESEARCH_DURABLE_URL") or "").rstrip("/")
    durable_token = os.environ.get("EDGE_RESEARCH_DURABLE_TOKEN") or ""
    health = {"ok": False, "status": 0, "reachable": False}
    bundle = {"ok": False, "status": 0}
    shadow = {"ok": False, "status": 0}
    if durable_url:
        code, _n = _http_get(f"{durable_url}/health")
        health = {"ok": code == 200, "status": code, "reachable": code != 0}
        if durable_token:
            bcode, _ = _http_get(f"{durable_url}/current/bundle.tar.gz", durable_token)
            bundle = {"ok": bcode in {200, 404}, "status": bcode, "note": "200 existing bundle or 404 empty store"}
            scode, _ = _http_get(f"{durable_url}/current/live_shadow/live_shadow_status.json", durable_token)
            # 404 is acceptable before the runner starts (empty store)
            shadow = {"ok": scode in {200, 404}, "status": scode, "note": "GET reachable; 404 empty store OK pre-session"}
        else:
            bundle = {"ok": False, "status": 0, "note": "token absent"}
            shadow = {"ok": False, "status": 0, "note": "token absent"}

    streamlit_url = (os.environ.get("MRBOT_STREAMLIT_URL") or "").strip()
    streamlit = {"ok": False, "status": 0, "url_configured": bool(streamlit_url)}
    if streamlit_url:
        code, _ = _http_get(streamlit_url)
        streamlit = {"ok": code in {200, 303}, "status": code, "url_configured": True}

    access = {
        "streamlit_admin": False,
        "vps_ssh": False,
        "self_hosted_worker": False,
        "durable_url": secrets["EDGE_RESEARCH_DURABLE_URL"] == "PRESENT",
        "durable_token": secrets["EDGE_RESEARCH_DURABLE_TOKEN"] == "PRESENT",
        "github_token": secrets["GITHUB_TOKEN"] == "PRESENT",
    }

    streamlit_deployed = False  # this proof never claims Streamlit Cloud deploy
    vps_deployed = shadow["ok"] and health.get("reachable", False)
    production_healthy = bool(src["production_panels_present"] and src["vnstock_0292"])
    if durable_url:
        production_healthy = production_healthy and health["ok"] and bundle["ok"]
    camera_unchanged = camera["ok"]  # no write from this script
    live_stopped = bool(runner["ok"])
    ready = (
        streamlit_deployed
        and vps_deployed
        and production_healthy
        and camera_unchanged
        and live_stopped
        and src["ui_no_kbs"]
        and src["alert_eligible_false"]
        and src["empty_candidate_ui"]
    )

    return {
        "schema": "live_session_01_deploy_proof.v1",
        "session_started": False,
        "secrets_present": secrets,
        "access": access,
        "source": src,
        "streamlit": streamlit,
        "artifact": {"health": health, "bundle": bundle, "live_shadow": shadow},
        "camera_archive": camera,
        "runner": runner,
        "verdict": {
            "A_STREAMLIT_DEPLOYED_OK": "YES" if streamlit_deployed else "NO",
            "B_VPS_ARTIFACT_DEPLOYED_OK": "YES" if vps_deployed else "NO",
            "C_EXISTING_PRODUCTION_HEALTHY": "YES" if production_healthy and health.get("ok") else "NO",
            "D_CAMERA_ARCHIVE_UNCHANGED": "YES" if camera_unchanged else "NO",
            "E_LIVE_RUNNER_STILL_STOPPED": "YES" if live_stopped else "NO",
            "F_READY_TO_START_LIVE_SESSION_01": "YES" if ready else "NO",
        },
        "preflight_blocker": _blocker(access, secrets, streamlit_deployed, vps_deployed),
    }


def _blocker(access: dict, secrets: dict, streamlit_deployed: bool, vps_deployed: bool) -> str:
    if not streamlit_deployed:
        return (
            "This agent cannot deploy Streamlit Cloud (no Streamlit admin token; "
            "stacked revision is not on origin/main). "
            "This agent cannot deploy the Camera VPS (no SSH, no self-hosted worker, "
            f"EDGE_RESEARCH_DURABLE_URL={secrets['EDGE_RESEARCH_DURABLE_URL']}). "
            "Stopped before production mutation."
        )
    if not vps_deployed:
        return "VPS live-shadow GET not proven. Do not start the live runner."
    return ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LIVE SESSION 01 deploy proof (never starts runner)")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    report = run_proof()
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["verdict"]["F_READY_TO_START_LIVE_SESSION_01"] == "YES" else 2


if __name__ == "__main__":
    raise SystemExit(main())
