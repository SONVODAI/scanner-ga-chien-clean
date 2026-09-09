"""Post-examiner diagnosis: flicker causes + one-baseline alert accounting.

Read-only on an existing shadow ledger. Does not tune thresholds, does not
use T+n, does not write Camera or production, does not enable alerts.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from modules.intraday_pxv_v1.constants import (
    RESEARCH_DEFAULT_CONTRACTION_X,
    RESEARCH_DEFAULT_EXPANSION_X,
    RESEARCH_DEFAULT_PACE_AHEAD_X,
)
from modules.intraday_pxv_v1.examine import (
    OPP,
    SW,
    _parse_ts,
    collect_runs,
    load_ledger,
)
from modules.intraday_pxv_v1.features import FAM_EXPANSION, FAM_PACE, FAM_PXV

# Official Slice 1B VPS examiner (operator-observed). Used only when the
# ledger is not on this host; persist rows are identities, not estimates.
OFFICIAL_SLICE1B = {
    "sw_runs": 967,
    "1_bar": 814,
    "ge_2_bars": 153,
    "ge_3_bars": 27,
    "ge_15_min": 11,
    "ge_30_min": 7,
    "returned_to_neutral": 840,
    "direct_opposite_reversals": 122,
    "raw_transitions": 5023,
    "ledger_would_be_alert": 113,
    "n_candidate_events": 135,
}

# Pre-declared diagnostic bands — not trading thresholds, not T+n fitted.
BAND_EXPANSION = 0.25
BAND_CONTRACTION = 0.10
PRICE_MATERIAL_PCT = 0.25
PRICE_NOISE_PCT = 0.15
WINDOW_DROP = 0.80

CAUSE_A = "A_THRESHOLD_BOUNDARY"
CAUSE_B = "B_PRICE_DIRECTION"
CAUSE_C = "C_VOLUME_EXPANSION"
CAUSE_C_WINDOW = "C_WINDOW_SELF_EXTINGUISH"
CAUSE_D = "D_TOD_PACE"
CAUSE_E = "E_OVERLAY_STALE_WRITE"
CAUSE_F = "F_DATA_STATE"
CAUSE_G = "G_CONTRADICTORY_PXV"
CAUSE_OTHER = "OTHER"

BASELINE_DEFINITION = (
    "STRENGTHEN/WEAKEN run-start: the first bar of each consecutive "
    "same-label STRENGTHEN or WEAKEN streak in a symbol-session. "
    "This is the raw evidence-event universe the 1-bar state machine emits. "
    "Every suppression rule below is a filter on this same ordered list. "
    "R0 ledger would-be-alert (113) is NOT the baseline — it is already "
    "persist>=2 + one-per-direction + skip LOW_CONFIDENCE/UNUSABLE."
)


def _as_dict(val: Any) -> dict[str, Any]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _feat_pack(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    if isinstance(row, dict):
        feats = _as_dict(row.get("features"))
        ev_why = str(row.get("evidence_why") or "")
        data_state = str(row.get("data_state") or "")
        src = str(row.get("bar_source_last") or "")
        overlay = bool(row.get("overlay_applied", False))
        evidence = str(row.get("evidence") or "")
    else:
        feats = _as_dict(row.get("features") if "features" in row.index else {})
        ev_why = str(row.get("evidence_why", "") or "")
        data_state = str(row.get("data_state", "") or "")
        src = str(row.get("bar_source_last", "") or "")
        overlay = bool(row.get("overlay_applied", False))
        evidence = str(row.get("evidence", "") or "")
    exp = feats.get(FAM_EXPANSION) or {}
    pxv = feats.get(FAM_PXV) or {}
    pace = feats.get(FAM_PACE) or {}
    ratio = exp.get("value")
    pace_v = pace.get("value")
    pct = pxv.get("price_change_pct")
    up = bool(pxv.get("up_bar"))
    down = bool(pxv.get("down_bar"))
    if not up and not down and pct is not None:
        up = float(pct) > 0
        down = float(pct) < 0
    return {
        "evidence": evidence,
        "exp_state": str(exp.get("state") or ""),
        "exp_ratio": float(ratio) if ratio is not None else None,
        "pxv_state": str(pxv.get("state") or ""),
        "up": up,
        "down": down,
        "pct": float(pct) if pct is not None else None,
        "pace": float(pace_v) if pace_v is not None else None,
        "why": ev_why,
        "data_state": data_state,
        "bar_source": src,
        "overlay": overlay,
    }


def _near(value: float | None, center: float, band: float) -> bool:
    if value is None:
        return False
    return abs(value - center) <= band


def _crossed(a: float | None, b: float | None, thresh: float) -> bool:
    if a is None or b is None:
        return False
    return (a - thresh) * (b - thresh) < 0 or (a >= thresh) != (b >= thresh)


def classify_exit(cur: dict[str, Any], nxt: dict[str, Any] | None) -> dict[str, Any]:
    """Tag why a STRENGTHEN/WEAKEN run ended. Multi-label + one primary."""
    tags: list[str] = []
    notes: list[str] = []
    if nxt is None:
        return {
            "primary": "ENDED_SESSION",
            "tags": ["ENDED_SESSION"],
            "notes": ["run reached last evaluated bar"],
        }

    if cur["data_state"] != nxt["data_state"]:
        tags.append(CAUSE_F)
        notes.append(f"data_state {cur['data_state']} -> {nxt['data_state']}")

    # Session-level overlay_applied is NOT a flicker cause. Only a per-bar
    # source change (canonical vs revised_quarantine) can be E.
    if cur["bar_source"] and nxt["bar_source"] and cur["bar_source"] != nxt["bar_source"]:
        tags.append(CAUSE_E)
        notes.append(f"bar_source {cur['bar_source']} -> {nxt['bar_source']}")

    price_flipped = (cur["up"] != nxt["up"]) or (cur["down"] != nxt["down"])
    if price_flipped:
        tags.append(CAUSE_B)
        a = f"{cur['pct']:+.2f}%" if cur["pct"] is not None else "?"
        b = f"{nxt['pct']:+.2f}%" if nxt["pct"] is not None else "?"
        notes.append(f"price dir {a} -> {b}")

    exp_changed = cur["exp_state"] != nxt["exp_state"]
    ratio_drop = (
        cur["exp_ratio"] is not None
        and nxt["exp_ratio"] is not None
        and (cur["exp_ratio"] - nxt["exp_ratio"]) >= WINDOW_DROP
    )
    if exp_changed or ratio_drop:
        tags.append(CAUSE_C)
        notes.append(
            f"vol {cur['exp_state']} {cur['exp_ratio']} -> {nxt['exp_state']} {nxt['exp_ratio']}"
        )

    window = (
        cur["evidence"] in SW
        and cur["exp_state"] == "EXPANSION"
        and nxt["exp_state"] != "EXPANSION"
        and cur["exp_ratio"] is not None
        and nxt["exp_ratio"] is not None
        and cur["exp_ratio"] >= RESEARCH_DEFAULT_EXPANSION_X
        and nxt["exp_ratio"] < RESEARCH_DEFAULT_EXPANSION_X
        and (
            cur["exp_ratio"] >= RESEARCH_DEFAULT_EXPANSION_X + BAND_EXPANSION
            or ratio_drop
        )
    )
    if window:
        tags.append(CAUSE_C_WINDOW)
        notes.append("spike likely entered the prior-6 median window")

    boundary = False
    if _crossed(cur["exp_ratio"], nxt["exp_ratio"], RESEARCH_DEFAULT_EXPANSION_X):
        if _near(cur["exp_ratio"], RESEARCH_DEFAULT_EXPANSION_X, BAND_EXPANSION) or _near(
            nxt["exp_ratio"], RESEARCH_DEFAULT_EXPANSION_X, BAND_EXPANSION
        ):
            boundary = True
    if _crossed(cur["exp_ratio"], nxt["exp_ratio"], RESEARCH_DEFAULT_CONTRACTION_X):
        if _near(cur["exp_ratio"], RESEARCH_DEFAULT_CONTRACTION_X, BAND_CONTRACTION) or _near(
            nxt["exp_ratio"], RESEARCH_DEFAULT_CONTRACTION_X, BAND_CONTRACTION
        ):
            boundary = True
    if boundary:
        tags.append(CAUSE_A)
        notes.append("expansion/contraction ratio crossed a RESEARCH_DEFAULT cut near the band")

    pace_flip = _crossed(cur["pace"], nxt["pace"], RESEARCH_DEFAULT_PACE_AHEAD_X)
    why_has_pace = "pace" in (cur["why"] or "").lower() or "pace" in (nxt["why"] or "").lower()
    if pace_flip and why_has_pace:
        tags.append(CAUSE_D)
        notes.append(f"pace {cur['pace']} -> {nxt['pace']}")

    opposite = nxt["evidence"] == OPP.get(cur["evidence"], "")
    both_expanding = cur["exp_state"] == "EXPANSION" and nxt["exp_state"] == "EXPANSION"
    cur_mat = cur["pct"] is not None and abs(cur["pct"]) >= PRICE_MATERIAL_PCT
    nxt_mat = nxt["pct"] is not None and abs(nxt["pct"]) >= PRICE_MATERIAL_PCT
    cur_noise = cur["pct"] is not None and abs(cur["pct"]) < PRICE_NOISE_PCT
    nxt_noise = nxt["pct"] is not None and abs(nxt["pct"]) < PRICE_NOISE_PCT
    if opposite and both_expanding and price_flipped and cur_mat and nxt_mat:
        tags.append(CAUSE_G)
        notes.append("both bars expanding with material opposite close-vs-open")

    # Primary: data/source first, then the mechanism that actually flips evidence.
    if CAUSE_F in tags:
        primary = CAUSE_F
    elif CAUSE_E in tags:
        primary = CAUSE_E
    elif CAUSE_A in tags and CAUSE_C_WINDOW not in tags:
        primary = CAUSE_A
    elif CAUSE_C_WINDOW in tags:
        primary = CAUSE_C_WINDOW
    elif opposite and both_expanding and (cur_noise or nxt_noise):
        primary = CAUSE_B
    elif CAUSE_G in tags:
        primary = CAUSE_G
    elif CAUSE_B in tags and opposite:
        primary = CAUSE_B
    elif CAUSE_C in tags:
        primary = CAUSE_C
    elif CAUSE_B in tags:
        primary = CAUSE_B
    elif CAUSE_D in tags:
        primary = CAUSE_D
    else:
        primary = CAUSE_OTHER
        notes.append("no feature delta matched a declared cause")

    return {"primary": primary, "tags": tags or [CAUSE_OTHER], "notes": notes}


def annotate_sw_runs(df: pd.DataFrame, sw_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = {key: g.reset_index(drop=True) for key, g in df.groupby(["symbol", "session"], sort=False)}
    out = []
    for run in sw_runs:
        g = groups.get((run["symbol"], run["session"]))
        rec = dict(run)
        if g is None or g.empty:
            rec["cause"] = {"primary": CAUSE_OTHER, "tags": [CAUSE_OTHER], "notes": ["session missing"]}
            out.append(rec)
            continue
        # Find start row by asof
        start_hits = g.index[g["asof"].astype(str) == str(run["first_asof"])].tolist()
        if not start_hits:
            start_i = 0
        else:
            start_i = int(start_hits[0])
        last_i = start_i + int(run["n_bars"]) - 1
        last_i = min(last_i, len(g) - 1)
        cur = _feat_pack(g.iloc[last_i])
        nxt_row = g.iloc[last_i + 1] if last_i + 1 < len(g) else None
        nxt = _feat_pack(nxt_row) if nxt_row is not None else None
        rec["cause"] = classify_exit(cur, nxt)
        rec["cur_feat"] = {k: cur[k] for k in ("exp_state", "exp_ratio", "pxv_state", "pct", "pace")}
        rec["nxt_feat"] = (
            {k: nxt[k] for k in ("exp_state", "exp_ratio", "pxv_state", "pct", "pace", "evidence")}
            if nxt
            else None
        )
        out.append(rec)
    return out


def cause_summary(annotated: list[dict[str, Any]], *, one_bar_only: bool = False) -> dict[str, Any]:
    rows = [r for r in annotated if (r["n_bars"] == 1 if one_bar_only else True)]
    opp = [r for r in annotated if r.get("to_opposite")]
    def counts(items):
        c = Counter(r["cause"]["primary"] for r in items)
        tag_c = Counter(t for r in items for t in r["cause"]["tags"])
        n = max(len(items), 1)
        return {
            "n": len(items),
            "primary": dict(c),
            "primary_pct": {k: round(100.0 * v / n, 1) for k, v in c.items()},
            "tags": dict(tag_c),
        }
    return {
        "one_bar_runs": counts(rows) if one_bar_only else counts([r for r in annotated if r["n_bars"] == 1]),
        "opposite_reversals": counts(opp),
        "all_sw_runs": counts(annotated),
        "note": (
            "D (TOD pace) cannot create extra STRENGTHEN under Slice 1: "
            "P×V CONFIRMING already requires expansion, so (pace_ahead AND confirm) "
            "is a subset of (expanding AND confirm). E (overlay_applied) is a "
            "session-level flag and does not flip 5m evidence by itself."
        ),
    }


def _ordered(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(runs, key=lambda r: (str(r["session"]), str(r["symbol"]), str(r["first_asof"])))


def _filter_first(rows: list[dict[str, Any]], keyfn) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    kept: list[dict[str, Any]] = []
    for r in rows:
        k = keyfn(r)
        if k in seen:
            continue
        seen.add(k)
        kept.append(r)
    return kept


def _filter_cooldown(rows: list[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
    last: dict[tuple[str, str], pd.Timestamp] = {}
    kept: list[dict[str, Any]] = []
    for r in rows:
        ts = _parse_ts(r["first_asof"])
        k = (str(r["symbol"]), str(r["session"]))
        prev = last.get(k)
        if prev is None or (ts - prev).total_seconds() / 60.0 >= minutes:
            kept.append(r)
            last[k] = ts
    return kept


def _filter_material(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """First leave-NEUTRAL, then only opposite-direction re-prints."""
    last_dir: dict[tuple[str, str], str] = {}
    kept: list[dict[str, Any]] = []
    for r in rows:
        k = (str(r["symbol"]), str(r["session"]))
        prev = last_dir.get(k)
        if prev is None or prev != r["evidence"]:
            kept.append(r)
            last_dir[k] = r["evidence"]
    return kept


def _row(name: str, baseline_n: int, kept: list[dict[str, Any]], definition: str) -> dict[str, Any]:
    k = len(kept)
    return {
        "rule": name,
        "definition": definition,
        "baseline": baseline_n,
        "retained": k,
        "suppressed": baseline_n - k,
        "retention_pct": round(100.0 * k / max(baseline_n, 1), 1),
    }


def normalized_suppression(sw_runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay every named policy from the SAME run-start universe."""
    base = _ordered(sw_runs)
    n = len(base)
    p2 = [r for r in base if r["n_bars"] >= 2]
    p3 = [r for r in base if r["n_bars"] >= 3]
    p15 = [r for r in base if r["elapsed_min"] >= 15]
    eligible = [r for r in p2 if r.get("data_state") not in {"UNUSABLE", "LOW_CONFIDENCE"}]
    table = [
        _row("baseline_identity", n, base, "all STRENGTHEN/WEAKEN run-starts"),
        _row("persist_ge_2", n, p2, "keep runs with n_bars >= 2"),
        _row("persist_ge_3", n, p3, "keep runs with n_bars >= 3"),
        _row("persist_ge_15m", n, p15, "keep runs with elapsed_min >= 15"),
        _row(
            "first_per_symbol_session",
            n,
            _filter_first(base, lambda r: (r["symbol"], r["session"])),
            "keep the first SW run of each symbol-session (any direction)",
        ),
        _row(
            "one_per_direction",
            n,
            _filter_first(base, lambda r: (r["symbol"], r["session"], r["evidence"])),
            "keep first STRENGTHEN and first WEAKEN per symbol-session",
        ),
        _row(
            "cooldown_30m",
            n,
            _filter_cooldown(base, 30),
            "keep a run if 30m elapsed since last KEPT run of that symbol-session",
        ),
        _row(
            "persist_ge_2_plus_one_per_direction",
            n,
            _filter_first(p2, lambda r: (r["symbol"], r["session"], r["evidence"])),
            "persist>=2, then first STRENGTHEN and first WEAKEN per symbol-session",
        ),
        _row(
            "persist_ge_2_plus_cooldown_30m",
            n,
            _filter_cooldown(p2, 30),
            "persist>=2, then 30m cooldown on remaining runs",
        ),
        _row(
            "persist_ge_2_plus_material_change_only",
            n,
            _filter_material(p2),
            "persist>=2, then first run and later opposite-direction only",
        ),
        _row(
            "slice1_would_be_alert_replay",
            n,
            _filter_first(eligible, lambda r: (r["symbol"], r["session"], r["evidence"])),
            "persist>=2 + skip LOW/UNUSABLE + one-per-direction (Slice 1 would_be_alert)",
        ),
    ]
    return {
        "baseline_definition": BASELINE_DEFINITION,
        "baseline_count": n,
        "table": table,
        "mixed_universe_warning": (
            "Slice 1B examiner R0=would_be_alert, R1=persist>=2 runs, R7=cooldown "
            "on persist>=2 were not the same event universe. This table fixes that. "
            "No T+n was used to choose a rule."
        ),
    }


def official_persist_table() -> dict[str, Any]:
    """Persist rows that are already known from the official examiner, same baseline 967."""
    n = OFFICIAL_SLICE1B["sw_runs"]
    rows = [
        ("baseline_identity", n),
        ("persist_ge_2", OFFICIAL_SLICE1B["ge_2_bars"]),
        ("persist_ge_3", OFFICIAL_SLICE1B["ge_3_bars"]),
        ("persist_ge_15m", OFFICIAL_SLICE1B["ge_15_min"]),
        ("persist_ge_30m", OFFICIAL_SLICE1B["ge_30_min"]),
        ("slice1_logged_would_be_alert", OFFICIAL_SLICE1B["ledger_would_be_alert"]),
        ("persist_ge_2_plus_cooldown_30m_from_examiner_R7", 142),
    ]
    table = []
    for name, kept in rows:
        table.append(
            {
                "rule": name,
                "baseline": n,
                "retained": kept,
                "suppressed": n - kept,
                "retention_pct": round(100.0 * kept / n, 1),
                "source": "official_slice1b_examiner",
            }
        )
    return {
        "baseline_definition": BASELINE_DEFINITION,
        "baseline_count": n,
        "table": table,
        "note": (
            "first-per-session / one-per-direction / cooldown-on-all-967 / "
            "material-change require the shadow ledger replay. "
            "R7=142 is cooldown on persist>=2 (153), reported against baseline 967 here."
        ),
    }


def compact_timeline(df: pd.DataFrame, symbol: str, session: str, limit: int = 48) -> dict[str, Any]:
    g = df[(df["symbol"] == symbol) & (df["session"].astype(str) == str(session))].copy()
    g = g.sort_values("asof_ts") if "asof_ts" in g.columns else g
    lines = []
    prev_ev = None
    for _, row in g.iterrows():
        p = _feat_pack(row)
        mark = "" if p["evidence"] == prev_ev else " *"
        ratio = f"{p['exp_ratio']:.2f}x" if p["exp_ratio"] is not None else "n/a"
        pct = f"{p['pct']:+.2f}%" if p["pct"] is not None else "n/a"
        pace = f"{p['pace']:.2f}x" if p["pace"] is not None else "n/a"
        lines.append(
            f"{row['asof_hm']}  {p['evidence']:<11}{mark}  "
            f"exp={p['exp_state'] or '-':<12} {ratio:<7}  "
            f"pxv={p['pxv_state'] or '-':<14} {pct:<8}  "
            f"pace={pace}  state={p['data_state']}"
        )
        prev_ev = p["evidence"]
        if len(lines) >= limit:
            break
    return {
        "symbol": symbol,
        "session": str(session),
        "n_bars": int(len(g)),
        "candidate_reason": str(g.iloc[0].get("candidate_reason", "")) if len(g) else "",
        "lines": lines,
    }


def pick_noisy_keys(annotated: list[dict[str, Any]], n: int = 4) -> list[tuple[str, str]]:
    by_ss: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"one": 0, "opp": 0, "sw": 0})
    for r in annotated:
        k = (str(r["symbol"]), str(r["session"]))
        by_ss[k]["sw"] += 1
        if r["n_bars"] == 1:
            by_ss[k]["one"] += 1
        if r.get("to_opposite"):
            by_ss[k]["opp"] += 1
    ranked = sorted(by_ss.items(), key=lambda kv: (kv[1]["one"], kv[1]["opp"], kv[1]["sw"]), reverse=True)
    return [k for k, _ in ranked[:n]]


def explain_session(df: pd.DataFrame, annotated: list[dict[str, Any]], symbol: str, session: str) -> dict[str, Any]:
    tl = compact_timeline(df, symbol, session)
    runs = [r for r in annotated if r["symbol"] == symbol and str(r["session"]) == str(session)]
    exits = []
    for r in runs:
        exits.append(
            {
                "evidence": r["evidence"],
                "first_hm": r["first_hm"],
                "last_hm": r["last_hm"],
                "n_bars": r["n_bars"],
                "next": r.get("next"),
                "primary": r["cause"]["primary"],
                "tags": r["cause"]["tags"],
                "notes": r["cause"]["notes"],
            }
        )
    return {**tl, "run_exits": exits}


def diagnose(ledger_path: Path) -> dict[str, Any]:
    df = load_ledger(ledger_path)
    runs = collect_runs(df)
    sw = [r for r in runs if r["evidence"] in SW]
    annotated = annotate_sw_runs(df, sw)
    causes = cause_summary(annotated)
    table = normalized_suppression(annotated)
    keys = [("GMD", "2026-08-28")]
    for k in pick_noisy_keys(annotated, 4):
        if k not in keys:
            keys.append(k)
    timelines = [explain_session(df, annotated, s, d) for s, d in keys]
    timelines = [t for t in timelines if t["n_bars"] > 0]
    logged_wb = int(df["would_be_alert"].sum()) if "would_be_alert" in df.columns and len(df) else 0
    replay_wb = next(r["retained"] for r in table["table"] if r["rule"] == "slice1_would_be_alert_replay")
    return {
        "ledger": str(ledger_path),
        "n_rows": int(len(df)),
        "n_symbol_sessions": int(df.groupby(["symbol", "session"]).ngroups) if len(df) else 0,
        "sw_runs": len(sw),
        "causes": causes,
        "normalized_alerts": table,
        "would_be_alert_logged": logged_wb,
        "would_be_alert_replay": replay_wb,
        "would_be_alert_match": logged_wb == replay_wb,
        "timelines": timelines,
        "pace_path_redundant": True,
        "overlay_is_session_flag": True,
    }


def render_markdown(result: dict[str, Any] | None) -> str:
    """Human diagnosis. Ledger result is optional; official persist rows always included."""
    official = official_persist_table()
    lines = [
        "# Slice 1B post-examiner diagnosis (design only)",
        "",
        "Shadow / research only. No live alerts. No Slice 2/3. No T+n fitting. No production writes.",
        "",
        "Architecture stays: BOT Candidate → Dynamic/Core Watchlist → Live 5m Camera → P×V Evidence → meaningful alert → Human decides.",
        "",
        "## A. Root cause of flicker",
        "",
        "The interpreter publishes a **1-bar boolean** with **no hysteresis and no confirmation**:",
        "",
        "- `STRENGTHEN = (expanding AND confirming)` where confirming is already `up AND expansion>=2.0×`",
        "- `WEAKEN = up+contraction OR (down+expansion vs long thesis)`",
        "- expansion = current 5m volume / median of the **prior 6 bars** (current excluded)",
        "",
        "That definition is **self-extinguishing**. A 2×+ spike fires STRENGTHEN; the next bar that spike **enters the lookback**, the ratio collapses, evidence returns to NEUTRAL. This is cause **C / C_WINDOW**, not a data bug.",
        "",
        "Direct STRENGTHEN↔WEAKEN reversals are mostly **B (close vs open flip)** while expansion stays on. Tiny close−open differences still count as up/down (`close != open`). Material two-sided expansion is **G**; near-doji flips are B-noise, not genuine contradiction.",
        "",
        "| Cause | Operative in Slice 1 evidence? | Why |",
        "|---|---|---|",
        "| A threshold-boundary | Secondary | Ratio hovering around 2.0× / 0.70× |",
        "| B price-direction | Yes — main reversal path | close>open vs close<open |",
        "| C volume expansion/contraction | Yes — main 1-bar path | spike then fade; window self-extinguish |",
        "| D same-TOD / TOD_PRELIMINARY | **No (dead path)** | `CONFIRMING` already requires expansion, so pace-ahead cannot add STRENGTHEN |",
        "| E overlay / stale-first-write | **Not 5m flicker** | `overlay_applied` is session-level if *any* bar was replaced |",
        "| F data-state changes | Possible, expected rare | gate can change as bars accumulate |",
        "| G contradictory P×V | Yes, subset of reversals | both bars expanding, material opposite direction |",
        "",
        "Official 1B: **814/967 = 84.2%** one-bar runs; **122** direct opposite reversals; median persist **1 bar**. "
        "That shape matches C_WINDOW + B, not overlay and not TOD.",
        "",
        "All stable ≥2 being QUALIFIED / overlay=true is **tautological** if every Camera session has some quarantine: the flag is copied onto every row of the session. It cannot explain bar-by-bar flicker.",
        "",
        "Slice 1 `would_be_alert` already requires persist≥2 and one-per-direction, with `alert_eligible=false`. The examiner still judged TOO_NOISY because the **published evidence series** flickers, not because the alert counter is unfiltered.",
        "",
    ]
    if result:
        c = result["causes"]
        lines += [
            "### Empirical cause split (from shadow ledger)",
            "",
            "One-bar runs (primary):",
            "```",
            json.dumps(c["one_bar_runs"], indent=2),
            "```",
            "",
            "Direct opposite reversals (primary):",
            "```",
            json.dumps(c["opposite_reversals"], indent=2),
            "```",
            "",
            c["note"],
            "",
        ]
    else:
        lines += [
            "### Empirical cause split",
            "",
            "Shadow ledger is not on this host (`/tmp/pxv-v1-slice1-out/shadow_ledger.jsonl` lives on the isolated VPS clone). "
            "Re-run `scripts/diagnose_intraday_pxv_v1.py --ledger /tmp/pxv-v1-slice1-out/shadow_ledger.jsonl` there to fill A–G counts. "
            "The mechanism tests in `tests/test_intraday_pxv_v1_diagnose.py` already reproduce C_WINDOW and B on the real interpreter.",
            "",
        ]

    lines += [
        "## B. Normalized apples-to-apples alert table",
        "",
        f"**Baseline event:** {BASELINE_DEFINITION}",
        "",
        f"**Baseline count (official 1B):** {OFFICIAL_SLICE1B['sw_runs']}",
        "",
        "Every row uses that same 967. Retention % = retained / 967.",
        "",
        "| Rule | baseline | retained | suppressed | retention % | source |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in official["table"]:
        lines.append(
            f"| `{r['rule']}` | {r['baseline']} | {r['retained']} | {r['suppressed']} | {r['retention_pct']}% | {r['source']} |"
        )

    lines += [
        "",
        "Known identities from official 1B (same baseline 967):",
        "",
        "- persist ≥2 → **153** retained (15.8%) — suppresses the 814 one-bar runs",
        "- persist ≥3 → **27** (2.8%)",
        "- persist ≥15m → **11** (1.1%)",
        "- Slice 1 logged would-be-alert → **113** (11.7%) = persist≥2 + one-per-direction + skip LOW/UNUSABLE",
        "- examiner R7 cooldown 30m on persist≥2 → **142** (14.7% of 967). Cooldown only removed **11** of 153 persistent runs.",
        "",
        "Why the old table was not comparable: **R0=113 is already compressed**. R1=153 counts every persist≥2 run, including 40 same-direction repeats after the first fire (153−113). R7=142 applies cooldown to the 153, not to the 113, and not to the 967. Some “compressed” counts exceeded R0 because they were not subsets of R0.",
        "",
        "No rule below was chosen with T+n returns.",
        "",
    ]
    if result:
        lines += [
            "### Ledger replay (same baseline = all SW run-starts in this file)",
            "",
            f"Baseline count in file: **{result['normalized_alerts']['baseline_count']}**",
            f"Slice 1 would-be logged={result['would_be_alert_logged']} replay={result['would_be_alert_replay']} match={result['would_be_alert_match']}",
            "",
            "| Rule | baseline | retained | suppressed | retention % |",
            "|---|---:|---:|---:|---:|",
        ]
        for r in result["normalized_alerts"]["table"]:
            lines.append(
                f"| `{r['rule']}` | {r['baseline']} | {r['retained']} | {r['suppressed']} | {r['retention_pct']}% |"
            )
        lines.append("")
        lines.append(result["normalized_alerts"]["mixed_universe_warning"])
        lines.append("")
    else:
        lines += [
            "Ledger-dependent rows (first-per-symbol-session, one-per-direction on all 967, cooldown on all 967, persist+material) are produced by the diagnosis script against the existing VPS ledger. They are filters of the same 967, never a new event universe.",
            "",
        ]

    lines += [
        "## C. Concrete noisy timelines",
        "",
        "### C0. Mechanism (real interpreter, synthetic bars — not GMD prints)",
        "",
        "These are what the current state machine **must** do. They are the explanation of the 814 one-bar runs and 122 reversals.",
        "",
        "**C0a. Window self-extinguish (cause C_WINDOW)** — real interpreter, synthetic 5m bars",
        "",
        "```",
        "09:55  NEUTRAL     exp=NORMAL    1.00x  pxv=FLAT",
        "10:00  NEUTRAL     exp=NORMAL    1.00x  pxv=FLAT",
        "10:05  STRENGTHEN  exp=EXPANSION 4.00x  pxv=CONFIRMING     +1.00%   <- spike",
        "10:10  NEUTRAL     exp=NORMAL    1.00x  pxv=FLAT           +1.20%   <- spike now in prior-6 median",
        "```",
        "",
        "One-bar STRENGTHEN. Persist>=2 suppresses it because the next bar is not expanding versus a window that now includes the spike. This is the structural reason 84.2% of runs last one bar — not overlay, not TOD.",
        "",
        "**C0b. Direct opposite reversal (cause B, G if both moves are material)**",
        "",
        "```",
        "10:05  STRENGTHEN  exp=EXPANSION 4.00x  pxv=CONFIRMING     +1.00%",
        "10:10  WEAKEN      exp=EXPANSION 3.80x  pxv=SELL_EXPANSION -1.24%   <- same expansion family, opposite close-vs-open",
        "```",
        "",
        "No NEUTRAL in between. Volume did not reverse; candle direction did. Near-doji close!=open flips are B-noise; material two-sided expansion is G.",
        "",
        "**C0c. Weak-up after a spike (cause C)**",
        "",
        "Up-bar expansion STRENGTHEN, next up-bar on contracted volume → WEAKEN (`price up on contracted volume`). Direction stayed up; volume state flipped.",
        "",
        "**C0d. Boundary (cause A)**",
        "",
        "Ratio 2.05× then 1.95× with the same up direction. Evidence chatters around the 2.0× cut. Hysteresis (enter 2.0 / exit 1.3) would hold; 2-bar confirmation would also hold unless both bars sit on opposite sides of the cut.",
        "",
    ]
    if result and result.get("timelines"):
        lines.append("### Observed symbol-sessions from the shadow ledger")
        lines.append("")
        for tl in result["timelines"]:
            lines.append(f"**{tl['symbol']} {tl['session']}** · {tl.get('candidate_reason','')} · {tl['n_bars']} as-of bars")
            lines.append("")
            lines.append("```")
            lines.extend(tl["lines"])
            lines.append("```")
            lines.append("")
            if tl.get("run_exits"):
                lines.append("Run exits:")
                for ex in tl["run_exits"]:
                    lines.append(
                        f"- {ex['first_hm']}–{ex['last_hm']} {ex['evidence']} n={ex['n_bars']} → {ex['next']}: "
                        f"{ex['primary']} tags={ex['tags']}"
                    )
                lines.append("")
    else:
        lines += [
            "### GMD 2026-08-28 (observed — ledger required)",
            "",
            "This host does not have `/tmp/pxv-v1-slice1-out/shadow_ledger.jsonl`. Do not invent GMD prints.",
            "",
            "On the isolated VPS clone (do **not** checkout the PR on `/opt/mrbot-camera`):",
            "",
            "```",
            "python scripts/diagnose_intraday_pxv_v1.py \\",
            "  --ledger /tmp/pxv-v1-slice1-out/shadow_ledger.jsonl \\",
            "  --out /tmp/pxv-v1-slice1-diagnosis \\",
            "  --focus GMD:2026-08-28",
            "```",
            "",
            "Expected if GMD is the noisy example: many 1-bar STRENGTHEN tagged C_WINDOW, plus STRENGTHEN↔WEAKEN tagged B/G, overlay=true on every row (session flag), TOD_PRELIMINARY on every row (confidence label, not the boolean driver).",
            "",
        ]

    lines += [
        "## D. Smallest recommended change (Interpreter / state machine) — do not implement yet",
        "",
        "Do **not** retune 2.0× / 0.70× / 1.5× against T+n. Do **not** add live alerts.",
        "",
        "| Mechanism | Addresses observed failure? | Or only hides alerts? |",
        "|---|---|---|",
        "| Persistence / debounce (2-bar confirm to *enter* S/W, 2-bar confirm to *reverse*) | **Yes.** 1-bar spikes never publish; 1-bar opposite does not reverse. Matches C_WINDOW + B. Persist≥2 as an *alert* filter already exists; the gap is that **published evidence** is still 1-bar. | Alert-only persist without changing published evidence just hid 814 runs from R0 while the examiner still saw flicker. |",
        "| Hysteresis on expansion ratio (enter 2.0×, exit ~1.3×, pre-declared) | **Yes for A and residual C.** After 2-bar confirm, add only if boundary chatter remains. | If exit is too sticky, a dead spike stays STRENGTHEN — that would hide a real fade. |",
        "| State-transition confirmation | Same as debounce if confirmation is on evidence, not on alerts. | — |",
        "| Material-change re-alert | No. Dedup after quality exists. | Hides same-direction repeats (the 40 extra persist≥2 runs). Fine as layer 2. |",
        "| 30m cooldown / dedup | **No.** R7: 153→142. Almost no effect on persistent events; if applied to all 967 it would fire on the first 1-bar spike then mute the morning. | Pure hiding. |",
        "",
        "**Smallest change:** debounce the *published* evidence state.",
        "",
        "1. Keep the current 1-bar boolean as `raw`.",
        "2. Publish STRENGTHEN/WEAKEN only after **two consecutive raw** bars of that label.",
        "3. Reverse S↔W only after **two consecutive** opposite raw bars; a single opposite or NEUTRAL returns published state to NEUTRAL (do not hold STRENGTHEN across a fade).",
        "4. Leave RESEARCH_DEFAULT cuts unchanged. Leave TOD pace unused until TOD_EARLY *and* CONFIRMING is redefined (today pace is dead code).",
        "5. Keep `alert_eligible=false`. Keep one-per-direction as a later alert policy, not as a substitute for confirmation.",
        "",
        "Cooldown-only or material-change-only would make the alert counter look quieter without fixing the 84% one-bar evidence.",
        "",
        "## E. Evidence required before live informational alerts",
        "",
        "Still not Slice 2. Pre-declare these gates; do not fit them on T+n.",
        "",
        "1. Re-run Slice 1B examiner on **published** (debounced) evidence, same archive, same candidates.",
        "2. One-bar published S/W rate well below 84% (pre-declare e.g. <30% of published runs).",
        "3. Direct opposite reversals drop vs 122/967; remaining reversals mostly tagged G (material two-sided expansion), not B-noise.",
        "4. Cause split shows F+E are not the driver (overlay/session flag remains labeled QUALIFIED, never TRUSTED).",
        "5. Normalized table from the **same** published-run baseline: persist≥2 is no longer the thing doing all the work (most published runs already last ≥2 by construction).",
        "6. Human read of 5–10 symbol-sessions (including GMD 2026-08-28 and one clean persist example): message is informational, no trade verbs except BOT reason pass-through.",
        "7. TOD still PRELIMINARY (16 sessions): any live message must say so. Do not wait for TOD_EARLY to allow *informational* alerts, but do not treat same-TOD ratios as trusted.",
        "8. DGC remains UNUSABLE / no S/W (gate holds).",
        "9. Production Camera, Discovery, Learning, BUY ELITE, Guardian unchanged.",
        "10. Architecture unchanged. Human still decides. No BUY/SELL. No threshold search on T+n.",
        "",
        "Until (1)–(6) hold, keep shadow-only.",
        "",
        "## Operator replay (isolated VPS clone, not /opt/mrbot-camera)",
        "",
        "```",
        "cd /tmp/pxv-v1-slice1b   # or a fresh clone of this commit",
        "python scripts/diagnose_intraday_pxv_v1.py \\",
        "  --ledger /tmp/pxv-v1-slice1-out/shadow_ledger.jsonl \\",
        "  --out /tmp/pxv-v1-slice1-diagnosis \\",
        "  --focus GMD:2026-08-28",
        "```",
        "",
        "Writes only `--out`. Does not touch Camera, production HEAD, or the ledger.",
        "",
    ]
    return "\n".join(lines)


def write_diagnosis(result: dict[str, Any] | None, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = render_markdown(result)
    (out_dir / "POST_EXAMINER_DIAGNOSIS.md").write_text(md, encoding="utf-8")
    payload = result or {"ledger": None, "normalized_alerts": official_persist_table()}
    (out_dir / "diagnosis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return out_dir / "POST_EXAMINER_DIAGNOSIS.md"
