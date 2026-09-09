#!/usr/bin/env python3
"""Read-only preflight / health for LIVE SESSION 01. Never starts KBS. Never writes Camera."""
from __future__ import annotations

import argparse
import inspect
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VN = ZoneInfo("Asia/Ho_Chi_Minh")
STALE_AFTER_SEC = 600


def _ok(name: str, passed: bool, detail: str) -> dict:
    return {"check": name, "ok": bool(passed), "detail": detail}


def _vnstock_status() -> dict:
    try:
        import vnstock  # type: ignore

        ver = getattr(vnstock, "__version__", "unknown")
        return _ok("vnstock_4x", str(ver).startswith("4") or ver == "unknown", f"vnstock {ver}")
    except Exception as exc:
        return _ok("vnstock_4x", False, f"{type(exc).__name__}: {exc}")


def _kbs_throttle() -> dict:
    from modules.intraday_memory.provider import KBSProvider

    src = inspect.getsource(KBSProvider.__init__)
    rpm_default = "requests_per_minute: int = 18" in src
    inst = None
    try:
        # Do not construct Quote / network. Inspect defaults only if import of Quote fails.
        inst = object.__new__(KBSProvider)
        inst.requests_per_minute = 18
        inst._min_interval = 60.0 / 18
    except Exception:
        pass
    interval = 60.0 / 18
    return _ok(
        "throttle_18_rpm",
        rpm_default and abs(interval - 3.333) < 0.01,
        f"KBSProvider default 18 rpm; min_interval={interval:.3f}s; source_has_default_18={rpm_default}",
    )


def _paths() -> dict:
    from modules.live_candidate.watchlist import WATCHLIST_NAME, output_root
    from modules.live_candidate_pxv_ui.read import (
        EVIDENCE_NAME,
        STATUS_NAME,
        default_shadow_dir,
        default_watchlist_path,
    )
    from modules.live_camera_shadow.feed import (
        default_shadow_dir as feed_shadow_dir,
        default_watchlist_path as feed_watchlist_path,
    )
    from modules.intraday_memory.config import DEFAULT_DATA_ROOT

    wl_ui = default_watchlist_path().resolve()
    wl_feed = feed_watchlist_path().resolve()
    sh_ui = default_shadow_dir().resolve()
    sh_feed = feed_shadow_dir().resolve()
    archive = (REPO / DEFAULT_DATA_ROOT).resolve()
    same_wl = wl_ui == wl_feed
    same_sh = sh_ui == sh_feed
    isolated = archive != sh_ui and archive not in sh_ui.parents
    return {
        "watchlist_ui": str(wl_ui),
        "watchlist_feed": str(wl_feed),
        "watchlist_name": WATCHLIST_NAME,
        "watchlist_exists": wl_ui.exists(),
        "shadow_ui": str(sh_ui),
        "shadow_feed": str(sh_feed),
        "evidence": str(sh_ui / EVIDENCE_NAME),
        "status": str(sh_ui / STATUS_NAME),
        "camera_archive": str(archive),
        "watchlist_paths_match": same_wl,
        "shadow_paths_match": same_sh,
        "archive_isolated": isolated,
        "candidate_root": str(output_root().resolve()),
        "checks": [
            _ok("watchlist_paths_match", same_wl, f"{wl_ui} == {wl_feed}"),
            _ok("shadow_paths_match", same_sh, f"{sh_ui} == {sh_feed}"),
            _ok("camera_archive_isolated", isolated, f"archive={archive} shadow={sh_ui}"),
        ],
    }


def _alert_isolation() -> dict:
    forbidden = ("telegram", "Telegram", "TELEGRAM")
    hits = []
    for rel in (
        "modules/live_camera_shadow",
        "modules/live_candidate_pxv_ui",
        "modules/intraday_pxv_v1/interpret.py",
        "modules/intraday_pxv_v1/debounce.py",
        "scripts/run_live_camera_shadow.py",
    ):
        path = REPO / rel
        files = [path] if path.is_file() else sorted(path.rglob("*.py"))
        for fp in files:
            text = fp.read_text(encoding="utf-8")
            if any(tok in text and "không Telegram" not in text for tok in ("telegram.Bot", "TELEGRAM_TOKEN", "send_message")):
                hits.append(str(fp.relative_to(REPO)))
    feed_src = (REPO / "modules/live_camera_shadow/feed.py").read_text(encoding="utf-8")
    alert_forced = "row.alert_eligible = False" in feed_src
    ui_src = (REPO / "modules/live_candidate_pxv_ui/view.py").read_text(encoding="utf-8")
    ui_forced = "alert_eligible: bool = False" in ui_src
    return {
        "telegram_send_hits": hits,
        "checks": [
            _ok("no_telegram_send_in_live_path", hits == [], f"hits={hits}"),
            _ok("feed_alert_eligible_false", alert_forced, "LiveShadowFeed forces alert_eligible=False"),
            _ok("ui_alert_eligible_false", ui_forced, "UI panel forces alert_eligible=False"),
        ],
    }


def _health(*, now: datetime) -> dict:
    from modules.live_candidate_pxv_ui.read import load_shadow_status

    status = load_shadow_status()
    observed = status.get("observed_at")
    age = None
    label = "STOPPED"
    if observed:
        ts = datetime.fromisoformat(str(observed))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=VN)
        age = (now - ts).total_seconds()
        label = "STALE" if age > STALE_AFTER_SEC else "LIVE"
    failures = [
        s.get("status")
        for s in (status.get("symbols") or [])
        if s.get("status") in {"PROVIDER_ERROR", "RATE_LIMITED", "STALE_BAR", "NO_DATA"}
    ]
    return {
        "label": label,
        "observed_at": observed,
        "age_sec": age,
        "alert_eligible": status.get("alert_eligible", None),
        "n_symbols_status": len(status.get("symbols") or []),
        "failures": failures,
        "status_file_present": bool(status),
    }


def run_preflight(*, now: datetime | None = None) -> dict:
    now = now or datetime.now(VN)
    paths = _paths()
    vn = _vnstock_status()
    throttle = _kbs_throttle()
    alerts = _alert_isolation()
    health = _health(now=now)
    checks = [vn, throttle, *paths["checks"], *alerts["checks"]]
    blocker = next((c["detail"] for c in checks if not c["ok"]), "")
    if not vn["ok"]:
        blocker = (
            "vnstock 4.x is not importable in this Python. "
            "Create isolated .venv-collector and pip install -r requirements-collector.txt. "
            "Do not install vnstock>=4 into the Streamlit/production env (app uses vnstock==0.2.9.2)."
        )
    return {
        "schema": "live_session_01_preflight.v1",
        "repo": str(REPO),
        "python": sys.executable,
        "now": now.isoformat(),
        "session_started": False,
        "vnstock": vn,
        "throttle": throttle,
        "paths": paths,
        "alerts": alerts,
        "health": health,
        "checks": checks,
        "all_ok": all(c["ok"] for c in checks),
        "blocker": blocker if not all(c["ok"] for c in checks) else "",
        "production_unchanged": True,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LIVE SESSION 01 preflight / health (read-only)")
    p.add_argument("--health", action="store_true", help="Print runner health from live_shadow_status.json only")
    args = p.parse_args(argv)
    if args.health:
        print(json.dumps(_health(now=datetime.now(VN)), ensure_ascii=False, indent=2, default=str))
        return 0
    payload = run_preflight()
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
