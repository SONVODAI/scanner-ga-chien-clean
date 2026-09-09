"""Shadow validation report writer (research only)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from modules.intraday_pxv_v1.candidates import CANDIDATE_FILTER, CANDIDATE_SOURCE
from modules.intraday_pxv_v1.paths import output_root


def build_report(
    *,
    camera_root: str,
    sessions: list[str],
    candidate_events: int,
    joined_events: int,
    ledger: pd.DataFrame,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if ledger is None or ledger.empty:
        summary = {
            "camera_root": camera_root,
            "n_camera_sessions": len(sessions),
            "sessions": sessions,
            "candidate_source": CANDIDATE_SOURCE,
            "candidate_filter": CANDIDATE_FILTER,
            "n_candidate_events": candidate_events,
            "n_joined_events": joined_events,
            "n_ledger_rows": 0,
        }
    else:
        last = ledger.sort_values("asof").groupby(["symbol", "session"], as_index=False).tail(1)
        rejected = last[last["evidence"] == "UNUSABLE"]
        reject_why = (
            rejected.groupby(["symbol", "gate_reason"]).size().reset_index(name="n").to_dict(orient="records")
            if not rejected.empty
            else []
        )
        dgc = last[last["symbol"] == "DGC"]
        first_ev = ledger[ledger["evidence"].isin(["STRENGTHEN", "WEAKEN"])]
        first_times = (
            first_ev.sort_values("asof").groupby(["symbol", "session", "evidence"])["asof_hm"].first()
            if not first_ev.empty
            else pd.Series(dtype=str)
        )
        # flicker: evidence changes within a symbol-session
        flicker = 0
        for _, g in ledger.groupby(["symbol", "session"]):
            evs = g.sort_values("asof")["evidence"].tolist()
            flicker += sum(1 for i in range(1, len(evs)) if evs[i] != evs[i - 1])
        summary = {
            "camera_root": camera_root,
            "n_camera_sessions": len(sessions),
            "sessions": sessions,
            "candidate_source": CANDIDATE_SOURCE,
            "candidate_filter": CANDIDATE_FILTER,
            "n_candidate_events": candidate_events,
            "n_joined_events": joined_events,
            "n_interpretable_last_bar": int((last["evidence"] != "UNUSABLE").sum()) if len(last) else 0,
            "n_ledger_rows": int(len(ledger)),
            "data_state_counts_last_bar": dict(last["data_state"].value_counts()) if len(last) else {},
            "evidence_counts_last_bar": dict(last["evidence"].value_counts()) if len(last) else {},
            "evidence_counts_all_asof": dict(ledger["evidence"].value_counts()),
            "rejected_last_bar": reject_why[:80],
            "dgc_rows": int((ledger["symbol"] == "DGC").sum()),
            "dgc_last_bar": dgc[["session", "data_state", "gate_reason", "evidence", "n_bars"]].to_dict(orient="records")
            if len(dgc)
            else [],
            "overlay_last_bar_n": int(last["overlay_applied"].sum()) if len(last) else 0,
            "tod_maturity_counts": dict(last["tod_maturity"].value_counts()) if len(last) else {},
            "would_be_alert_count": int(ledger["would_be_alert"].sum()),
            "alert_eligible_true_count": int(ledger["alert_eligible"].sum()),
            "flicker_transitions": int(flicker),
            "first_evidence_hm": dict(Counter(first_times.tolist())) if len(first_times) else {},
        }
    if extra:
        summary.update(extra)
    return summary


def write_report(summary: dict[str, Any], out_dir: Path | None = None) -> Path:
    root = out_dir or output_root()
    root.mkdir(parents=True, exist_ok=True)
    js = root / "shadow_report.json"
    js.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = root / "shadow_report.md"
    md.write_text(_to_markdown(summary), encoding="utf-8")
    return md


def _to_markdown(s: dict[str, Any]) -> str:
    lines = [
        "# Intraday P×V V1 Slice 1 — shadow report",
        "",
        "Research/shadow only. `alert_eligible` is always false. No trade instruction.",
        "",
        f"- Camera root: `{s.get('camera_root')}`",
        f"- Camera sessions: **{s.get('n_camera_sessions')}** `{s.get('sessions')}`",
        f"- Candidate source: `{s.get('candidate_source')}` — {s.get('candidate_filter')}",
        f"- Candidate events: **{s.get('n_candidate_events')}**",
        f"- Joined to Camera: **{s.get('n_joined_events')}**",
        f"- Ledger rows (all as-of): **{s.get('n_ledger_rows')}**",
        f"- Interpretable last-bar events: **{s.get('n_interpretable_last_bar')}**",
        f"- data_state (last bar): `{s.get('data_state_counts_last_bar')}`",
        f"- evidence (last bar): `{s.get('evidence_counts_last_bar')}`",
        f"- would-be alerts (logged only): **{s.get('would_be_alert_count')}**",
        f"- alert_eligible true: **{s.get('alert_eligible_true_count')}** (must be 0)",
        f"- overlay last-bar sessions: **{s.get('overlay_last_bar_n')}**",
        f"- TOD maturity: `{s.get('tod_maturity_counts')}`",
        f"- flicker transitions: **{s.get('flicker_transitions')}**",
        f"- DGC ledger rows: **{s.get('dgc_rows')}**",
        "",
        "T+n association was not used to set thresholds.",
        "",
    ]
    return "\n".join(lines)
