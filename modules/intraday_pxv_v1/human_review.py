"""Read-only published-evidence human case review.

Does not change thresholds, debounce, Camera, or production.
Does not use T+n. Does not invent bars.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from modules.intraday_pxv_v1.examine import (
    SW,
    _hm_min,
    _with_col,
    candidate_behavior,
    collect_runs,
    ensure_asof_ts,
    examine_frame,
    load_ledger,
)
from modules.intraday_pxv_v1.features import FAM_EXPANSION, FAM_PACE, FAM_PXV, FAM_TOD_RVOL

OFFICIAL_1C = {
    "raw_sw_runs": 967,
    "published_sw_runs": 152,
    "raw_1_bar": 814,
    "published_1_bar": 108,
    "raw_ge2": 153,
    "published_ge2": 44,
    "raw_ge3": 27,
    "published_ge3": 11,
    "raw_ge15": 11,
    "published_ge15": 3,
    "raw_ge30": 7,
    "published_ge30": 1,
    "raw_opposite": 122,
    "published_opposite": 2,
    "timing_first_published": {
        "09:15-10:00": 9,
        "10:00-11:30": 44,
        "13:00-14:00": 74,
        "14:00-close": 25,
    },
    "candidates": {
        "noisy_flicker": 6,
        "clean_persistent": 9,
        "never_leave_neutral": 39,
        "unusable_dominated": 2,
    },
}


def _feat(row: pd.Series) -> dict[str, Any]:
    feats = row.get("features") or {}
    if isinstance(feats, str):
        try:
            feats = json.loads(feats)
        except json.JSONDecodeError:
            feats = {}
    if not isinstance(feats, dict):
        feats = {}
    exp = feats.get(FAM_EXPANSION) or {}
    pxv = feats.get(FAM_PXV) or {}
    tod = feats.get(FAM_TOD_RVOL) or {}
    pace = feats.get(FAM_PACE) or {}
    pct = pxv.get("price_change_pct")
    if pxv.get("up_bar"):
        direction = "up"
    elif pxv.get("down_bar"):
        direction = "down"
    else:
        direction = "flat"
    return {
        "exp_state": exp.get("state"),
        "exp_ratio": exp.get("value"),
        "pxv_state": pxv.get("state"),
        "pct": pct,
        "direction": direction,
        "tod_rvol": tod.get("value"),
        "tod_conf": tod.get("confidence"),
        "pace": pace.get("value"),
        "pace_conf": pace.get("confidence"),
    }


def _fmt(val: Any, spec: str = ".2f", suffix: str = "") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "n/a"
    try:
        return f"{float(val):{spec}}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def _afternoon(hm: str) -> bool:
    return _hm_min(hm) >= _hm_min("13:00")


def render_ui_message(row: pd.Series, published: str, raw_why: str, pub_why: str) -> str:
    f = _feat(row)
    reason = str(row.get("candidate_reason") or "")
    bits = []
    if published == "STRENGTHEN":
        bits.append("2 consecutive RAW confirming bars.")
    elif published == "WEAKEN":
        bits.append("2 consecutive RAW weakening bars.")
    elif published == "UNUSABLE":
        bits.append("Gate UNUSABLE — no volume evidence.")
    else:
        bits.append("No published directional evidence.")
    why = (pub_why or raw_why or "").strip()
    if why:
        bits.append(why)
    vol = f"Volume {f['exp_state'] or 'n/a'} ({_fmt(f['exp_ratio'], '.2f', '×')})"
    pxv = f"P×V {f['pxv_state'] or 'n/a'} · bar {_fmt(f['pct'], '+.2f', '%')} {f['direction']}"
    return "\n".join(
        [
            f"{row['symbol']} | {row['asof_hm']} | P×V {published}",
            " ".join(bits),
            f"{vol}; {pxv}.",
            f"Data: {row.get('data_state')} | {row.get('tod_maturity')} | overlay={bool(row.get('overlay_applied'))}.",
            "Intraday evidence only — not a BUY signal.",
            f"BOT reason (pass-through): {reason}" if reason else "",
        ]
    ).strip()


def classify_coherence(*, role: str, run: dict[str, Any] | None, f: dict[str, Any], row: pd.Series | None) -> tuple[str, str]:
    """P×V-message coherence only. Not T+n, not a trading label."""
    if role == "UNUSABLE_STRUCTURAL":
        return "UNUSABLE", "structural/UNUSABLE gate — correctly no directional evidence"
    if role == "NEVER_NEUTRAL":
        return "USEFUL", "published never left NEUTRAL — correct silence, useful as a non-event"
    if role == "GMD_QUIET":
        return "USEFUL", "RAW flickered; published stayed NEUTRAL — debounce did the right thing"
    if run is None or row is None:
        return "BORDERLINE", "insufficient published event to judge"
    n = int(run.get("n_bars") or 0)
    ratio = f.get("exp_ratio")
    pct = f.get("pct")
    state = str(row.get("data_state") or "")
    if state == "UNUSABLE":
        return "UNUSABLE", "data_state UNUSABLE"
    near_cut = ratio is not None and 1.75 <= float(ratio) <= 2.25
    tiny = pct is not None and abs(float(pct)) < 0.15
    if role == "NOISY_FLICKER":
        return "NOISY", "session still has many 1-bar published prints and no >=3-bar hold"
    if role == "OPPOSITE":
        if ratio is not None and float(ratio) >= 2.5 and pct is not None and abs(float(pct)) >= 0.25:
            return "BORDERLINE", "direct S↔W after confirmation — contradictory P×V, may be genuine two-sided expansion"
        return "NOISY", "direct published reversal without a clear material two-sided expansion story"
    if n >= 3 and not tiny:
        return "USEFUL", "published hold >=3 bars; P×V message can be read as a standing condition"
    if n >= 2 and not near_cut and not tiny:
        return "USEFUL", "published hold >=2 bars; more interpretable than a single confirmed flash"
    if n == 1 and ratio is not None and float(ratio) >= 2.5 and not tiny:
        return "BORDERLINE", "confirmed-then-fade: two RAW bars were real, but the published print lasts one bar"
    if n == 1 and (near_cut or tiny):
        return "NOISY", "1-bar published near the 2.0× cut or with a tiny close-vs-open — still chatter"
    if n == 1:
        return "BORDERLINE", "1-bar published confirmed-then-fade — short-lived information, not old 1-RAW flicker"
    return "BORDERLINE", "published event exists but is short or weakly described"


def _window(g: pd.DataFrame, center_idx: int, before: int = 4, after: int = 7) -> pd.DataFrame:
    lo = max(0, center_idx - before)
    hi = min(len(g), center_idx + after + 1)
    return g.iloc[lo:hi]


def _bar_line(row: pd.Series, mark: str = "") -> str:
    f = _feat(row)
    raw = str(row.get("raw_evidence", row.get("evidence", "")))
    pub = str(row.get("published_evidence", row.get("evidence", "")))
    return (
        f"{row['asof_hm']}{mark}  raw={raw:<11} pub={pub:<11}  "
        f"dir={f['direction']:<4} {_fmt(f['pct'], '+.2f', '%'):<8}  "
        f"exp={str(f['exp_state'] or '-'):<12} {_fmt(f['exp_ratio'], '.2f', '×'):<7}  "
        f"pxv={str(f['pxv_state'] or '-'):<14}  "
        f"todR={_fmt(f['tod_rvol'], '.2f', '×')} pace={_fmt(f['pace'], '.2f', '×')}  "
        f"state={row.get('data_state')} tod={row.get('tod_maturity')} overlay={bool(row.get('overlay_applied'))}"
    )


def _first_pub_idx(g: pd.DataFrame) -> int | None:
    pubs = g["published_evidence"].astype(str)
    hits = [i for i, v in enumerate(pubs.tolist()) if v in SW]
    return hits[0] if hits else None


def explain_case(
    df: pd.DataFrame,
    symbol: str,
    session: str,
    role: str,
    run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    g = df[(df["symbol"] == symbol) & (df["session"].astype(str) == str(session))].copy()
    g = ensure_asof_ts(g).sort_values("asof_ts").reset_index(drop=True)
    if g.empty:
        return {
            "symbol": symbol,
            "session": str(session),
            "role": role,
            "missing": True,
            "label": "UNUSABLE",
            "why": "symbol-session not in this ledger — do not invent bars",
            "lines": [],
            "ui_message": "",
        }
    idx = None
    if run:
        hits = g.index[g["asof"].astype(str) == str(run.get("first_asof"))].tolist()
        if hits:
            idx = int(hits[0])
    if idx is None:
        idx = _first_pub_idx(g)
    if idx is None:
        idx = max(0, len(g) // 2)
    sl = _window(g, idx)
    fire = g.iloc[idx]
    pub_at = str(fire.get("published_evidence", ""))
    mark_hm = str(fire["asof_hm"])
    lines = []
    for _, row in sl.iterrows():
        star = "  << PUBLISHED ENTERS" if str(row["asof_hm"]) == mark_hm and pub_at in SW else ""
        lines.append(_bar_line(row, star))
    f = _feat(fire)
    label, why = classify_coherence(role=role, run=run, f=f, row=fire)
    raw_why = str(fire.get("evidence_why") or "")
    pub_why = str(fire.get("published_why") or "")
    ui = render_ui_message(fire, pub_at if pub_at in SW or pub_at == "UNUSABLE" else "NEUTRAL", raw_why, pub_why)
    return {
        "symbol": symbol,
        "session": str(session),
        "role": role,
        "missing": False,
        "candidate_reason": str(g.iloc[0].get("candidate_reason") or ""),
        "first_published_hm": mark_hm if pub_at in SW else None,
        "first_published": pub_at if pub_at in SW else None,
        "run": run,
        "label": label,
        "why": why,
        "lines": lines,
        "raw_why": raw_why,
        "published_why": pub_why,
        "ui_message": ui,
        "n_bars_session": int(len(g)),
        "raw_sw_bars": int(g["raw_evidence"].isin(SW).sum()) if "raw_evidence" in g.columns else None,
        "published_sw_bars": int(g["published_evidence"].isin(SW).sum()) if "published_evidence" in g.columns else None,
    }


def _pick(sw_runs: list[dict[str, Any]], ev: str, min_bars: int, afternoon: bool) -> dict[str, Any] | None:
    cands = [
        r
        for r in sw_runs
        if r["evidence"] == ev
        and r["n_bars"] >= min_bars
        and r.get("data_state") == "QUALIFIED"
        and (not afternoon or _afternoon(r["first_hm"]))
    ]
    cands.sort(key=lambda r: (-r["n_bars"], -_hm_min(r["first_hm"])))
    return cands[0] if cands else None


def select_cases(df: pd.DataFrame) -> list[tuple[str, str, str, dict[str, Any] | None]]:
    work = ensure_asof_ts(df)
    pub = _with_col(work, "published_evidence")
    pub_runs = collect_runs(pub)
    sw = [r for r in pub_runs if r["evidence"] in SW]
    beh = candidate_behavior(pub, pub_runs)
    picked: list[tuple[str, str, str, dict[str, Any] | None]] = []
    seen: set[tuple[str, str]] = set()

    def add(sym: str, sess: str, role: str, run: dict[str, Any] | None = None) -> None:
        key = (str(sym), str(sess))
        if key in seen:
            return
        seen.add(key)
        picked.append((str(sym), str(sess), role, run))

    gmd = work[(work["symbol"] == "GMD") & (work["session"].astype(str) == "2026-08-28")]
    gmd_run = next((r for r in sw if r["symbol"] == "GMD" and str(r["session"]) == "2026-08-28"), None)
    if len(gmd) and not gmd["published_evidence"].isin(SW).any():
        add("GMD", "2026-08-28", "GMD_QUIET", None)
    else:
        add("GMD", "2026-08-28", "GMD_REQUIRED", gmd_run)

    for ev, role, nmin in (
        ("STRENGTHEN", "CLEAN_STRENGTHEN", 3),
        ("WEAKEN", "CLEAN_WEAKEN", 3),
        ("STRENGTHEN", "CLEAN_STRENGTHEN_GE2", 2),
        ("WEAKEN", "CLEAN_WEAKEN_GE2", 2),
    ):
        r = _pick(sw, ev, nmin, afternoon=True) or _pick(sw, ev, nmin, afternoon=False)
        if r:
            add(r["symbol"], r["session"], role, r)

    fades = [r for r in sw if r["n_bars"] == 1 and _afternoon(r["first_hm"])]
    fades.sort(key=lambda r: -_hm_min(r["first_hm"]))
    for r in fades[:4]:
        add(r["symbol"], r["session"], "ONE_BAR_FADE", r)

    for rec in beh.get("noisy_examples") or []:
        add(rec["symbol"], rec["session"], "NOISY_FLICKER")
        break
    for rec in beh.get("neutral_examples") or []:
        add(rec["symbol"], rec["session"], "NEVER_NEUTRAL")
        break
    for rec in beh.get("unusable_examples") or []:
        add(rec["symbol"], rec["session"], "UNUSABLE_STRUCTURAL")
        break

    opp = [r for r in sw if r.get("to_opposite")]
    for r in opp[:2]:
        add(r["symbol"], r["session"], "OPPOSITE", r)

    return picked[:15]


def review_ledger(path: Path) -> dict[str, Any]:
    df = load_ledger(path)
    if df.empty:
        return {"status": "EMPTY_LEDGER", "path": str(path)}
    if "raw_evidence" not in df.columns:
        df["raw_evidence"] = df["evidence"]
    if "published_evidence" not in df.columns:
        df["published_evidence"] = df["evidence"]
    df["alert_eligible"] = df.get("alert_eligible", False)
    raw = examine_frame(df, evidence_col="raw_evidence", source_ledger=str(path))
    pub = examine_frame(df, evidence_col="published_evidence", source_ledger=str(path))
    picks = select_cases(df)
    cases = [explain_case(df, s, d, role, run) for s, d, role, run in picks]
    counts = defaultdict(int)
    for c in cases:
        counts[c["label"]] += 1
    return {
        "status": "OK",
        "path": str(path),
        "n_rows": int(len(df)),
        "official_1c_observed": OFFICIAL_1C,
        "this_file_raw_persist": raw["persistence"],
        "this_file_published_persist": pub["persistence"],
        "this_file_published_timing": pub.get("timing_first_sw"),
        "this_file_candidates": {
            k: pub["candidates"][k]
            for k in (
                "noisy_flicker_n",
                "clean_persistent_n",
                "never_leave_neutral_n",
                "unusable_dominated_n",
            )
        },
        "checks": {
            "alert_eligible_true_count": int(df["alert_eligible"].sum()) if "alert_eligible" in df.columns else 0,
            "dgc_published_sw": bool(pub["examples"]["structural"].get("any_dgc_strengthen_weaken")),
        },
        "cases": cases,
        "label_counts": dict(counts),
        "note": (
            "Labels are P×V-message coherence only. Not T+n. Not BUY/SELL. "
            "Close/volume levels are omitted when the ledger stored only features."
        ),
    }


def write_review(result: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "human_case_review.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    lines = [
        "# Slice 1C published-evidence human case review",
        "",
        "Read-only. No threshold change. No T+n. No live alerts.",
        "",
        f"Source: `{result.get('path')}`",
        f"Checks: `{result.get('checks')}`",
        "",
        "## Official 1C observed (operator)",
        json.dumps(OFFICIAL_1C, indent=2),
        "",
        "## Selected real cases",
        "",
    ]
    for i, c in enumerate(result.get("cases") or [], 1):
        lines.append(f"### {i}. {c['symbol']} {c['session']} — {c['role']} → **{c['label']}**")
        lines.append(c.get("why") or "")
        if c.get("missing"):
            lines.append("Missing from this ledger. Do not invent bars.")
            lines.append("")
            continue
        lines.append(f"BOT reason: {c.get('candidate_reason')}")
        lines.append(f"First published: {c.get('first_published')} at {c.get('first_published_hm')}")
        lines.append("```")
        lines.extend(c.get("lines") or [])
        lines.append("```")
        lines.append("Simulated UI message:")
        lines.append("```")
        lines.append(c.get("ui_message") or "")
        lines.append("```")
        lines.append("")
    lines += [
        "## Label counts (this selection)",
        json.dumps(result.get("label_counts"), indent=2),
        "",
    ]
    md = out_dir / "human_case_review.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    return md
