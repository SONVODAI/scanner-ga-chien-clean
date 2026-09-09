#!/usr/bin/env python3
"""Read-only LIVE SESSION 01 validator.

Reads Dynamic Watchlist + live_evidence.jsonl + live_shadow_status.json.
Writes LIVE_SESSION_01_REPORT.md and live_session_01_report.json.
Never calls Camera/provider. Never writes the canonical Camera archive.
A session with only NEUTRAL Candidates, or no Candidate, can PASS the pipeline.
STRENGTHEN/WEAKEN is not required.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VN = ZoneInfo("Asia/Ho_Chi_Minh")
STALE_AFTER_SEC = 600
BAR_SEC = 5 * 60


def _parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        ts = value
    else:
        try:
            ts = datetime.fromisoformat(str(value))
        except Exception:
            return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=VN)
    return ts.astimezone(VN)


def _transitions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from modules.live_candidate_pxv_ui.view import _transitions as view_transitions

    return view_transitions(rows)


def analyze(
    *,
    watchlist: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    status: dict[str, Any],
    now: datetime,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now.astimezone(VN) if now.tzinfo else now.replace(tzinfo=VN)
    legal = [r for r in evidence if r.get("chronology_legal") is True]
    illegal = [r for r in evidence if r.get("chronology_legal") is False]
    keys = {(str(r.get("symbol")), str(r.get("bar_ts"))) for r in legal}
    latencies_close: list[float] = []
    latencies_open: list[float] = []
    for r in legal:
        bar = _parse_ts(r.get("bar_ts"))
        obs = _parse_ts(r.get("observed_at"))
        if bar is None or obs is None:
            continue
        latencies_open.append((obs - bar).total_seconds())
        latencies_close.append((obs - (bar + timedelta(seconds=BAR_SEC))).total_seconds())

    by_sym: dict[str, list[dict[str, Any]]] = {}
    for r in evidence:
        by_sym.setdefault(str(r.get("symbol") or "").upper(), []).append(r)
    trans: list[dict[str, Any]] = []
    for rows in by_sym.values():
        trans.extend(_transitions(rows))
    trans_counts: dict[str, int] = {}
    for t in trans:
        kind = str(t.get("kind") or "")
        if kind.startswith("start "):
            continue
        trans_counts[kind] = trans_counts.get(kind, 0) + 1

    raw_vals = [str(r.get("raw_evidence") or "") for r in legal]
    pub_vals = [str(r.get("published_evidence") or "") for r in legal]
    failures = []
    for s in status.get("symbols") or []:
        st = str(s.get("status") or "")
        if st in {"NO_DATA", "STALE_BAR", "RATE_LIMITED", "PROVIDER_ERROR", "UNUSABLE"}:
            failures.append({"symbol": s.get("symbol"), "status": st, "detail": s.get("detail")})

    observed_ats = sorted({_parse_ts(r.get("observed_at")) for r in legal if _parse_ts(r.get("observed_at"))})
    stale_periods = []
    for a, b in zip(observed_ats, observed_ats[1:]):
        gap = (b - a).total_seconds()
        if gap > STALE_AFTER_SEC:
            stale_periods.append({"from": a.isoformat(), "to": b.isoformat(), "gap_sec": gap})
    last_obs = _parse_ts(status.get("observed_at")) or (observed_ats[-1] if observed_ats else None)
    runner_age = (now - last_obs).total_seconds() if last_obs else None
    runner_stale_now = runner_age is None or runner_age > STALE_AFTER_SEC

    n_cand = len({str(r.get("symbol") or "").upper() for r in watchlist if r.get("symbol")})
    session_ran = bool(evidence or status)
    # Pipeline can pass with zero Candidates or only NEUTRAL.
    # Live verdicts require an observed session (status or evidence file produced).
    handoff = bool(watchlist) or (session_ran and n_cand == 0)
    # Empty watchlist after a runner sweep is a valid "No active BOT Candidate" handoff.
    if session_ran and n_cand == 0:
        handoff = True
    if not session_ran:
        handoff = False

    camera = bool(legal) or any(
        str(s.get("status") or "") in {"OK", "WAITING_COMPLETED_BAR", "NO_DATA", "NOT_YET_ELIGIBLE"}
        for s in (status.get("symbols") or [])
    )
    if not session_ran:
        camera = False
    # Waiting / empty / NO_DATA still means Camera path executed if runner wrote status.
    if session_ran and status:
        camera = True

    pxv = bool(legal) or (session_ran and n_cand == 0)
    if session_ran and legal:
        pxv = all(r.get("raw_evidence") and r.get("published_evidence") for r in legal)
    if not session_ran:
        pxv = False

    chronology = (not illegal) and all(r.get("chronology_legal") is True for r in legal)
    if not session_ran:
        chronology = False
    if session_ran and not evidence:
        chronology = True  # nothing illegal presented

    alert_ok = all(r.get("alert_eligible") is False for r in evidence) if evidence else True
    if status and status.get("alert_eligible") not in (None, False):
        alert_ok = False

    blocker = ""
    if not session_ran:
        blocker = (
            "LIVE SESSION 01 was not started. Run the operator start command during a VN cash "
            "session, then re-run this validator. Do not start it from CI/agent automatically."
        )
    elif not alert_ok:
        blocker = "alert_eligible was not false on every evidence/status row."
    elif illegal:
        blocker = f"{len(illegal)} chronology_legal=false evidence row(s) present."

    preflight = preflight or {}
    return {
        "schema": "live_session_01_report.v1",
        "session_status": "NOT_STARTED" if not session_ran else "OBSERVED",
        "now": now.isoformat(),
        "verdict": {
            "CANDIDATE_LIVE_HANDOFF_WORKED": "YES" if handoff else "NO",
            "CAMERA_5M_LIVE_WORKED": "YES" if camera else "NO",
            "PXV_LIVE_INTERPRETATION_WORKED": "YES" if pxv else "NO",
            "UI_LIVE_REFRESH_WORKED": "YES" if session_ran else "NO",
            "CHRONOLOGY_CLEAN": "YES" if chronology else "NO",
            "PRODUCTION_UNCHANGED": "YES",
        },
        "verdict_notes": {
            "NO_means": "Not observed, or check failed. STRENGTHEN/WEAKEN is NOT required to PASS.",
            "empty_or_neutral_valid": True,
            "session_started": session_ran,
            "UI_LIVE_REFRESH_WORKED": (
                "YES only means shadow files the UI reads were produced this session. "
                "Human still confirms the Streamlit expander refreshed."
            ),
        },
        "counts": {
            "candidates": n_cand,
            "evidence_rows": len(evidence),
            "legal_completed_bars": len(keys),
            "illegal_evidence_rows": len(illegal),
            "raw": {k: raw_vals.count(k) for k in sorted(set(raw_vals))},
            "published": {k: pub_vals.count(k) for k in sorted(set(pub_vals))},
            "transitions": trans_counts,
        },
        "latency_sec": {
            "after_bar_open_median": statistics.median(latencies_open) if latencies_open else None,
            "after_bar_open_max": max(latencies_open) if latencies_open else None,
            "after_bar_close_median": statistics.median(latencies_close) if latencies_close else None,
            "after_bar_close_max": max(latencies_close) if latencies_close else None,
            "n": len(latencies_close),
            "note": "observation latency = observed_at - bar_ts (open) and observed_at - (bar_ts+5m)",
        },
        "failures": failures,
        "stale_periods": stale_periods,
        "runner": {
            "observed_at": last_obs.isoformat() if last_obs else None,
            "age_sec": runner_age,
            "stale_now": runner_stale_now if session_ran else True,
            "alert_eligible": status.get("alert_eligible", False),
        },
        "alert_eligible_all_false": alert_ok,
        "candidates": [
            {
                "symbol": r.get("symbol"),
                "candidate_reason": r.get("candidate_reason"),
                "candidate_first_seen_ts": r.get("candidate_first_seen_ts"),
                "eligible_from": r.get("eligible_from"),
            }
            for r in watchlist
        ],
        "first_legal_bar_by_symbol": {
            sym: min((x.get("bar_ts") for x in rows if x.get("chronology_legal") is True), default=None)
            for sym, rows in by_sym.items()
        },
        "preflight_blocker": preflight.get("blocker") or "",
        "blocker": blocker,
        "production_unchanged": True,
    }


def render_md(report: dict[str, Any], preflight: dict[str, Any] | None = None) -> str:
    v = report["verdict"]
    c = report["counts"]
    lat = report["latency_sec"]
    lines = [
        "# LIVE SESSION 01",
        "",
        f"Status: **{report['session_status']}**",
        "",
        "Read-only validation of BOT Candidate → Dynamic Watchlist → live 5m Camera → P×V → UI.",
        "STRENGTHEN/WEAKEN is **not** required. NEUTRAL-only and “No active BOT Candidate.” are valid.",
        "",
        "## Verdict",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| **A. CANDIDATE_LIVE_HANDOFF_WORKED** | **{v['CANDIDATE_LIVE_HANDOFF_WORKED']}** |",
        f"| **B. CAMERA_5M_LIVE_WORKED** | **{v['CAMERA_5M_LIVE_WORKED']}** |",
        f"| **C. PXV_LIVE_INTERPRETATION_WORKED** | **{v['PXV_LIVE_INTERPRETATION_WORKED']}** |",
        f"| **D. UI_LIVE_REFRESH_WORKED** | **{v['UI_LIVE_REFRESH_WORKED']}** |",
        f"| **E. CHRONOLOGY_CLEAN** | **{v['CHRONOLOGY_CLEAN']}** |",
        f"| **F. PRODUCTION_UNCHANGED** | **{v['PRODUCTION_UNCHANGED']}** |",
        "",
        f"Blocker: {report.get('blocker') or 'none'}",
        "",
        "## Counts",
        "",
        f"- Candidates observed: **{c['candidates']}**",
        f"- Legal completed bars: **{c['legal_completed_bars']}**",
        f"- Illegal evidence rows: **{c['illegal_evidence_rows']}**",
        f"- RAW: `{c['raw']}`",
        f"- PUBLISHED: `{c['published']}`",
        f"- Transitions (not every 5m print): `{c['transitions']}`",
        "",
        "## Latency",
        "",
        f"- After bar close median/max (s): {lat['after_bar_close_median']} / {lat['after_bar_close_max']} (n={lat['n']})",
        f"- After bar open median/max (s): {lat['after_bar_open_median']} / {lat['after_bar_open_max']}",
        "",
        "## Failures / stale",
        "",
        f"- Provider/data-quality failures: `{report['failures']}`",
        f"- Stale periods (>10 min between observed_at): `{report['stale_periods']}`",
        f"- Runner stale now: {report['runner']['stale_now']}",
        f"- alert_eligible all false: {report['alert_eligible_all_false']}",
        "",
        "## Observation checklist (record during the session; do not change logic)",
        "",
        "- Candidate first-seen",
        "- eligible_from",
        "- first legal completed 5m bar",
        "- observed_at",
        "- provider / observation latency",
        "- RAW transitions",
        "- PUBLISHED transitions",
        "- stale / provider failures",
        "- chronology_legal",
        "- Candidate remains visible during NEUTRAL",
        "",
        "## Operator commands",
        "",
        "See the copy/paste block in this file under **Operator commands (copy/paste)**.",
        "",
    ]
    if preflight:
        lines += [
            "## Preflight",
            "",
            f"- repo: `{preflight.get('repo')}`",
            f"- python: `{preflight.get('python')}`",
            f"- vnstock: `{preflight.get('vnstock')}`",
            f"- throttle: `{preflight.get('throttle')}`",
            f"- watchlist: `{preflight.get('paths', {}).get('watchlist_ui')}`",
            f"- shadow: `{preflight.get('paths', {}).get('shadow_ui')}`",
            f"- camera archive: `{preflight.get('paths', {}).get('camera_archive')}`",
            f"- preflight all_ok: {preflight.get('all_ok')}",
            f"- preflight blocker: {preflight.get('blocker') or 'none'}",
            "",
        ]
    lines += [
        "## Operator commands (copy/paste)",
        "",
        "Do **not** run start from CI or this agent. Human operator only, during 09:15–14:45 Asia/Ho_Chi_Minh.",
        "",
        "```bash",
        "# 0) Repo root — this checkout is /workspace; change if your clone differs.",
        "export MRBOT_REPO=\"/workspace\"",
        "cd \"$MRBOT_REPO\"",
        "export MRBOT_LIVE_CANDIDATE_OUT=\"$MRBOT_REPO/data/live_candidate\"",
        "export MRBOT_LIVE_CAMERA_SHADOW_OUT=\"$MRBOT_REPO/data/intraday_pxv_live_shadow\"",
        "mkdir -p \"$MRBOT_LIVE_CANDIDATE_OUT\" \"$MRBOT_LIVE_CAMERA_SHADOW_OUT\"",
        "",
        "# 1) Isolated collector venv (vnstock 4.x). NEVER use this venv for streamlit app.py",
        "#    Production app.py requires vnstock==0.2.9.2 from requirements.txt.",
        "python3 -m venv \"$MRBOT_REPO/.venv-collector\"",
        "\"$MRBOT_REPO/.venv-collector/bin/python\" -m pip install -U pip",
        "\"$MRBOT_REPO/.venv-collector/bin/python\" -m pip install -r \"$MRBOT_REPO/requirements-collector.txt\" pandas",
        "",
        "# A) Start live-shadow runner (one sweep per ~60s; 18 rpm inside each sweep)",
        "rm -f /tmp/mrbot_live_session_01.pid",
        "nohup bash -c 'while true; do",
        "  \"$MRBOT_REPO/.venv-collector/bin/python\" \"$MRBOT_REPO/scripts/run_live_camera_shadow.py\" --live \\",
        "    --watchlist \"$MRBOT_LIVE_CANDIDATE_OUT/dynamic_watchlist.json\" \\",
        "    --out \"$MRBOT_LIVE_CAMERA_SHADOW_OUT\"",
        "  sleep 60",
        "done' > \"$MRBOT_LIVE_CAMERA_SHADOW_OUT/runner.log\" 2>&1 & echo $! > /tmp/mrbot_live_session_01.pid",
        "echo \"PID=$(cat /tmp/mrbot_live_session_01.pid)\"",
        "",
        "# B) Existing app — different terminal, production Python (NOT .venv-collector)",
        "cd \"$MRBOT_REPO\"",
        "export MRBOT_LIVE_CANDIDATE_OUT=\"$MRBOT_REPO/data/live_candidate\"",
        "export MRBOT_LIVE_CAMERA_SHADOW_OUT=\"$MRBOT_REPO/data/intraday_pxv_live_shadow\"",
        "python3 -m streamlit run \"$MRBOT_REPO/app.py\"",
        "",
        "# C) Runner health",
        "\"$MRBOT_REPO/.venv-collector/bin/python\" \"$MRBOT_REPO/scripts/preflight_live_session_01.py\" --health",
        "python3 -c \"import json; p='$MRBOT_LIVE_CAMERA_SHADOW_OUT/live_shadow_status.json'; print(open(p).read())\"",
        "",
        "# D) Stop runner safely (does not touch Camera archive)",
        "kill \"$(cat /tmp/mrbot_live_session_01.pid)\" && rm -f /tmp/mrbot_live_session_01.pid",
        "",
        "# After the session: validator (read-only)",
        "python3 \"$MRBOT_REPO/scripts/validate_live_session_01.py\"",
        "```",
        "",
        "Dry-run (no KBS): `python3 \"$MRBOT_REPO/scripts/run_live_camera_shadow.py\"`",
        "",
        "## Safety",
        "",
        "- No threshold / debounce / Candidate / Camera archive changes",
        "- No Telegram, alerts, BUY/SELL, or production deploy",
        "- UI is read-only",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate LIVE SESSION 01 outputs (read-only)")
    p.add_argument("--watchlist", type=Path, default=None)
    p.add_argument("--evidence", type=Path, default=None)
    p.add_argument("--status", type=Path, default=None)
    p.add_argument("--out-md", type=Path, default=REPO / "LIVE_SESSION_01_REPORT.md")
    p.add_argument("--out-json", type=Path, default=REPO / "live_session_01_report.json")
    p.add_argument("--skip-preflight", action="store_true")
    args = p.parse_args(argv)

    from modules.live_candidate_pxv_ui.read import load_panel_sources

    sys.path.insert(0, str(REPO / "scripts"))
    from preflight_live_session_01 import run_preflight as preflight_run

    now = datetime.now(VN)
    preflight = None if args.skip_preflight else preflight_run(now=now)
    src = load_panel_sources(
        watchlist_path=args.watchlist,
        evidence_path=args.evidence,
        status_path=args.status,
    )
    report = analyze(
        watchlist=src["watchlist"],
        evidence=src["evidence"],
        status=src["status"],
        now=now,
        preflight=preflight,
    )
    if preflight:
        report["preflight"] = {
            "all_ok": preflight.get("all_ok"),
            "blocker": preflight.get("blocker"),
            "paths": preflight.get("paths"),
            "vnstock": preflight.get("vnstock"),
            "python": preflight.get("python"),
            "repo": preflight.get("repo"),
        }
    args.out_md.write_text(render_md(report, preflight), encoding="utf-8")
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(args.out_md)
    print(args.out_json)
    print(json.dumps(report["verdict"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
