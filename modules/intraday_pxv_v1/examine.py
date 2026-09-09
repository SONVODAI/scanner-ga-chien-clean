"""Read-only Shadow Evidence Examiner (Slice 1B).

Does not write Camera, production, or the original shadow ledger.
Does not tune thresholds on T+n.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

SW = {"STRENGTHEN", "WEAKEN"}
OPP = {"STRENGTHEN": "WEAKEN", "WEAKEN": "STRENGTHEN"}

BUCKETS = (
    ("09:15-10:00", "09:15", "10:00"),
    ("10:00-11:30", "10:00", "11:30"),
    ("13:00-14:00", "13:00", "14:00"),
    ("14:00-close", "14:00", "15:01"),
)


def _parse_ts(val: Any) -> pd.Timestamp:
    ts = pd.Timestamp(val)
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Ho_Chi_Minh")
    return ts


def _hm_min(hm: str) -> int:
    hh, mm = str(hm).split(":")[:2]
    return int(hh) * 60 + int(mm)


def _bucket(hm: str) -> str:
    m = _hm_min(hm)
    for name, a, b in BUCKETS:
        if _hm_min(a) <= m < _hm_min(b):
            return name
    return "other"


def load_ledger(path: Path) -> pd.DataFrame:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if isinstance(rec.get("features"), str):
                try:
                    rec["features"] = json.loads(rec["features"])
                except json.JSONDecodeError:
                    rec["features"] = {}
            rows.append(rec)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["asof_ts"] = df["asof"].map(_parse_ts)
    df["evidence"] = df["evidence"].astype(str)
    df["data_state"] = df["data_state"].astype(str)
    df["tod_maturity"] = df.get("tod_maturity", pd.Series([""] * len(df))).astype(str)
    if "overlay_applied" in df.columns:
        df["overlay_applied"] = df["overlay_applied"].astype(bool)
    else:
        df["overlay_applied"] = False
    if "would_be_alert" not in df.columns:
        df["would_be_alert"] = False
    return df.sort_values(["symbol", "session", "asof_ts"]).reset_index(drop=True)


def _runs(g: pd.DataFrame) -> list[dict[str, Any]]:
    evs = g["evidence"].tolist()
    if not evs:
        return []
    runs = []
    start = 0
    for i in range(1, len(evs) + 1):
        if i == len(evs) or evs[i] != evs[start]:
            sl = g.iloc[start:i]
            first = sl.iloc[0]
            last = sl.iloc[-1]
            nxt = g.iloc[i]["evidence"] if i < len(g) else "END"
            dt_min = (last["asof_ts"] - first["asof_ts"]).total_seconds() / 60.0
            runs.append(
                {
                    "symbol": first["symbol"],
                    "session": first["session"],
                    "evidence": first["evidence"],
                    "data_state": first["data_state"],
                    "gate_reason": first.get("gate_reason", ""),
                    "tod_maturity": first.get("tod_maturity", ""),
                    "overlay_applied": bool(first.get("overlay_applied", False)),
                    "first_hm": first["asof_hm"],
                    "last_hm": last["asof_hm"],
                    "first_asof": str(first["asof"]),
                    "n_bars": int(len(sl)),
                    "elapsed_min": round(dt_min, 1),
                    "next": nxt,
                    "to_neutral": nxt == "NEUTRAL",
                    "to_opposite": nxt == OPP.get(first["evidence"], ""),
                    "candidate_reason": first.get("candidate_reason", ""),
                }
            )
            start = i
    return runs


def collect_runs(df: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _, g in df.groupby(["symbol", "session"], sort=False):
        out.extend(_runs(g))
    return out


def transition_counts(df: pd.DataFrame) -> dict[str, int]:
    c: Counter[str] = Counter()
    for _, g in df.groupby(["symbol", "session"], sort=False):
        ev = g["evidence"].tolist()
        st = g["data_state"].tolist()
        for i in range(1, len(ev)):
            key = f"{ev[i-1]}->{ev[i]}"
            c[key] += 1
            if st[i] != st[i - 1]:
                c["data_state_change_along_transition"] += 1
            if "UNUSABLE" in (ev[i - 1], ev[i]) or "UNUSABLE" in (st[i - 1], st[i]):
                c["involves_unusable_or_unusable_state"] += 1
    return dict(c)


def persist_dist(sw_runs: list[dict[str, Any]]) -> dict[str, int]:
    n = len(sw_runs)
    return {
        "sw_runs": n,
        "1_bar": sum(1 for r in sw_runs if r["n_bars"] == 1),
        "ge_2_bars": sum(1 for r in sw_runs if r["n_bars"] >= 2),
        "ge_3_bars": sum(1 for r in sw_runs if r["n_bars"] >= 3),
        "ge_15_min": sum(1 for r in sw_runs if r["elapsed_min"] >= 15),
        "ge_30_min": sum(1 for r in sw_runs if r["elapsed_min"] >= 30),
    }


def simulate_alerts(sw_runs: list[dict[str, Any]], raw_would_be: int) -> dict[str, int]:
    """Non-return-optimized suppression. Order is session clock."""
    ordered = sorted(sw_runs, key=lambda r: (r["session"], r["symbol"], r["first_asof"]))

    def count(pred) -> int:
        return sum(1 for r in ordered if pred(r))

    p2 = [r for r in ordered if r["n_bars"] >= 2]
    p3 = [r for r in ordered if r["n_bars"] >= 3]
    p15 = [r for r in ordered if r["elapsed_min"] >= 15]
    p30 = [r for r in ordered if r["elapsed_min"] >= 30]
    qual = [r for r in p2 if r["data_state"] == "QUALIFIED" and not r["overlay_applied"]]

    def first_per_ss(rows, keyfn):
        seen: set[Any] = set()
        n = 0
        for r in rows:
            k = keyfn(r)
            if k in seen:
                continue
            seen.add(k)
            n += 1
        return n

    def cooldown(rows, minutes: int) -> int:
        last: dict[tuple[str, str], pd.Timestamp] = {}
        n = 0
        for r in rows:
            ts = _parse_ts(r["first_asof"])
            k = (r["symbol"], r["session"])
            prev = last.get(k)
            if prev is None or (ts - prev).total_seconds() / 60.0 >= minutes:
                n += 1
                last[k] = ts
        return n

    def material_rows(rows) -> list[dict[str, Any]]:
        """First leave-NEUTRAL and later opposite-direction only."""
        last_dir: dict[tuple[str, str], str] = {}
        kept: list[dict[str, Any]] = []
        for r in rows:
            k = (r["symbol"], r["session"])
            prev = last_dir.get(k)
            if prev is None or prev != r["evidence"]:
                kept.append(r)
                last_dir[k] = r["evidence"]
        return kept

    def material(rows) -> int:
        return len(material_rows(rows))

    early = [r for r in p2 if _hm_min(r["first_hm"]) < _hm_min("14:00")]

    return {
        "R0_ledger_would_be_alert": int(raw_would_be),
        "R1_persist_ge_2_bars": len(p2),
        "R2_persist_ge_3_bars": len(p3),
        "R3_persist_ge_15_min": len(p15),
        "R4_persist_ge_30_min": len(p30),
        "R5_first_alert_per_symbol_session": first_per_ss(p2, lambda r: (r["symbol"], r["session"])),
        "R6_one_per_direction_per_symbol_session": first_per_ss(
            p2, lambda r: (r["symbol"], r["session"], r["evidence"])
        ),
        "R7_cooldown_30min_any_direction": cooldown(p2, 30),
        "R8_material_change_only_on_ge2": material(p2),
        "R9_ge3_plus_one_per_direction": first_per_ss(
            p3, lambda r: (r["symbol"], r["session"], r["evidence"])
        ),
        "R10_ge15min_plus_one_per_direction": first_per_ss(
            p15, lambda r: (r["symbol"], r["session"], r["evidence"])
        ),
        "R11_ge2_material_plus_30min_cooldown": cooldown(material_rows(p2), 30),
        "R12_qualified_no_overlay_ge2_one_dir": first_per_ss(
            qual, lambda r: (r["symbol"], r["session"], r["evidence"])
        ),
        "R13_ge2_first_before_14:00_one_dir": first_per_ss(
            early, lambda r: (r["symbol"], r["session"], r["evidence"])
        ),
        "note": (
            "Rules are RESEARCH_DEFAULT simulations, not fitted to T+n. "
            "R6 matches Slice 1 would-be intent (persist>=2, one per direction/session)."
        ),
    }


def candidate_behavior(df: pd.DataFrame, runs: list[dict[str, Any]]) -> dict[str, Any]:
    sw = [r for r in runs if r["evidence"] in SW]
    by_ss = defaultdict(list)
    for r in sw:
        by_ss[(r["symbol"], r["session"])].append(r)

    noisy, clean, never, unusable = [], [], [], []
    last = df.sort_values("asof_ts").groupby(["symbol", "session"], as_index=False).tail(1)
    ev_all = df.groupby(["symbol", "session"])["evidence"].apply(set)

    for _, row in last.iterrows():
        key = (row["symbol"], row["session"])
        rs = by_ss.get(key, [])
        n1 = sum(1 for r in rs if r["n_bars"] == 1)
        nstab = sum(1 for r in rs if r["n_bars"] >= 3)
        evset = set(ev_all.loc[key]) if key in ev_all.index else set()
        rec = {
            "symbol": row["symbol"],
            "session": row["session"],
            "last_evidence": row["evidence"],
            "last_data_state": row["data_state"],
            "gate_reason": row.get("gate_reason", ""),
            "sw_runs": len(rs),
            "one_bar_runs": n1,
            "ge3_runs": nstab,
        }
        if row["evidence"] == "UNUSABLE" or str(row.get("gate_reason", "")).startswith("STRUCTURAL"):
            unusable.append(rec)
        elif not rs and evset <= {"NEUTRAL"}:
            never.append(rec)
        elif n1 >= 3 and nstab == 0:
            noisy.append(rec)
        elif nstab >= 1 and n1 <= 1:
            clean.append(rec)

    return {
        "noisy_flicker_n": len(noisy),
        "clean_persistent_n": len(clean),
        "never_leave_neutral_n": len(never),
        "unusable_dominated_n": len(unusable),
        "noisy_examples": noisy[:12],
        "clean_examples": clean[:12],
        "neutral_examples": never[:8],
        "unusable_examples": unusable[:8],
    }


def timelines(df: pd.DataFrame, keys: list[tuple[str, str]], limit_bars: int = 40) -> list[dict[str, Any]]:
    out = []
    for sym, sess in keys:
        g = df[(df["symbol"] == sym) & (df["session"] == sess)]
        if g.empty:
            continue
        seq = [
            {"hm": r.asof_hm, "ev": r.evidence, "state": r.data_state}
            for r in g.itertuples()
        ]
        out.append(
            {
                "symbol": sym,
                "session": sess,
                "reason": g.iloc[0].get("candidate_reason", ""),
                "seq": seq[:limit_bars],
                "n": int(len(g)),
            }
        )
    return out


def pick_examples(sw_runs: list[dict[str, Any]], df: pd.DataFrame) -> dict[str, Any]:
    def best(ev: str):
        cands = [
            r
            for r in sw_runs
            if r["evidence"] == ev
            and r["n_bars"] >= 3
            and r["data_state"] == "QUALIFIED"
            and not r["overlay_applied"]
        ]
        cands.sort(key=lambda r: (-r["n_bars"], -r["elapsed_min"]))
        return cands[0] if cands else None

    strengthen = best("STRENGTHEN")
    weaken = best("WEAKEN")
    noisy = None
    counts: dict[tuple[str, str], int] = Counter()
    for r in sw_runs:
        if r["n_bars"] == 1:
            counts[(r["symbol"], r["session"])] += 1
    if counts:
        key = max(counts, key=lambda k: counts[k])
        noisy = {"symbol": key[0], "session": key[1], "one_bar_runs": counts[key]}
    dgc = df[df["symbol"] == "DGC"]
    structural = {
        "dgc_rows": int(len(dgc)),
        "dgc_evidence": dict(dgc["evidence"].value_counts()) if len(dgc) else {},
        "dgc_gate": dict(dgc["gate_reason"].value_counts()) if len(dgc) else {},
        "any_dgc_strengthen_weaken": bool(len(dgc) and dgc["evidence"].isin(SW).any()),
    }
    keys = []
    if strengthen:
        keys.append((strengthen["symbol"], strengthen["session"]))
    if weaken:
        keys.append((weaken["symbol"], weaken["session"]))
    if noisy:
        keys.append((noisy["symbol"], noisy["session"]))
    if len(dgc):
        keys.append(("DGC", str(dgc.iloc[0]["session"])))
    return {
        "clean_strengthen": strengthen,
        "clean_weaken": weaken,
        "noisy": noisy,
        "structural": structural,
        "timelines": timelines(df, keys),
    }


def verdict(dist: dict[str, int], sw_runs: list[dict[str, Any]], trans: dict[str, int], n_ss: int) -> dict[str, str]:
    n = max(dist["sw_runs"], 1)
    ge2 = dist["ge_2_bars"] / n
    opp = sum(1 for r in sw_runs if r["to_opposite"]) / n
    trans_n = sum(v for k, v in trans.items() if "->" in k)
    per_ss = trans_n / max(n_ss, 1)
    early = sum(1 for r in sw_runs if r["n_bars"] >= 2 and _hm_min(r["first_hm"]) < _hm_min("14:00"))
    early_frac = early / max(dist["ge_2_bars"], 1)
    onebar = dist["1_bar"] / n

    # Pre-declared, not T+n fitted.
    if dist["ge_2_bars"] < 10 or ge2 < 0.15:
        v = "NOT_READY"
        why = "too few persistent STRENGTHEN/WEAKEN runs"
    elif onebar >= 0.55 or per_ss >= 8 or opp >= 0.25:
        v = "PROMISING_BUT_TOO_NOISY"
        why = "persistent events exist but 1-bar flicker and/or opposite reversals dominate"
    elif early_frac < 0.20:
        v = "PROMISING_BUT_TOO_NOISY"
        why = "stable events exist but too few appear before 14:00"
    else:
        v = "READY_FOR_ALERT_DESIGN"
        why = "enough persistent same-direction events, limited opposite reversals, some pre-14:00"
    return {"verdict": v, "why": why}


def examine(ledger_path: Path, report_path: Path | None = None) -> dict[str, Any]:
    df = load_ledger(ledger_path)
    meta = {}
    if report_path and report_path.exists():
        meta = json.loads(report_path.read_text(encoding="utf-8"))
    runs = collect_runs(df)
    sw_runs = [r for r in runs if r["evidence"] in SW]
    dist = persist_dist(sw_runs)
    trans = transition_counts(df)
    n_ss = int(df.groupby(["symbol", "session"]).ngroups) if len(df) else 0
    raw_wb = int(df["would_be_alert"].sum()) if len(df) else 0
    med_bars = float(pd.Series([r["n_bars"] for r in sw_runs]).median()) if sw_runs else 0.0
    med_min = float(pd.Series([r["elapsed_min"] for r in sw_runs]).median()) if sw_runs else 0.0
    opp = sum(1 for r in sw_runs if r["to_opposite"])
    neu = sum(1 for r in sw_runs if r["to_neutral"])

    stable = [r for r in sw_runs if r["n_bars"] >= 2]
    timing = Counter(_bucket(r["first_hm"]) for r in stable)

    last = df.sort_values("asof_ts").groupby(["symbol", "session"], as_index=False).tail(1) if len(df) else df
    dq = {
        "last_bar_data_state": dict(last["data_state"].value_counts()) if len(last) else {},
        "last_bar_tod": dict(last["tod_maturity"].value_counts()) if len(last) else {},
        "last_bar_overlay_true": int(last["overlay_applied"].sum()) if len(last) else 0,
        "sw_runs_by_data_state": dict(Counter(r["data_state"] for r in sw_runs)),
        "stable_ge2_by_data_state": dict(Counter(r["data_state"] for r in stable)),
        "stable_ge2_overlay_true": sum(1 for r in stable if r["overlay_applied"]),
        "note": (
            "TOD_PRELIMINARY must not be treated as TRUSTED. "
            "overlay/STALE_FIRST_WRITE is QUALIFIED at best."
        ),
    }

    out = {
        "source_ledger": str(ledger_path),
        "n_rows": int(len(df)),
        "n_symbol_sessions": n_ss,
        "shadow_report_meta": {
            k: meta.get(k)
            for k in (
                "n_camera_sessions",
                "n_candidate_events",
                "n_joined_events",
                "would_be_alert_count",
                "flicker_transitions",
                "tod_maturity_counts",
            )
            if meta
        },
        "persistence": {
            **dist,
            "median_persist_bars": med_bars,
            "median_persist_min": med_min,
            "returned_to_neutral": neu,
            "direct_opposite_reversals": opp,
            "ended_session_still_active": sum(1 for r in sw_runs if r["next"] == "END"),
        },
        "transitions": trans,
        "raw_transition_arrows": sum(v for k, v in trans.items() if "->" in k),
        "timing_stable_ge2_first_hm": dict(timing),
        "alert_simulation": simulate_alerts(sw_runs, raw_wb),
        "candidates": candidate_behavior(df, runs),
        "data_quality": dq,
        "examples": pick_examples(sw_runs, df),
        "verdict_block": verdict(dist, sw_runs, trans, n_ss),
    }
    return out


def write_examiner(result: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    js = out_dir / "examiner.json"
    js.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = out_dir / "examiner.md"
    v = result["verdict_block"]
    p = result["persistence"]
    a = result["alert_simulation"]
    lines = [
        "# Slice 1B Shadow Evidence Examiner",
        "",
        f"## A. VERDICT: {v['verdict']}",
        v["why"],
        "",
        "## B. Key numbers",
        f"- raw arrow transitions: {result['raw_transition_arrows']}",
        f"- STRENGTHEN/WEAKEN runs: {p['sw_runs']}",
        f"- persist 1-bar / >=2 / >=3 / >=15m / >=30m: "
        f"{p['1_bar']} / {p['ge_2_bars']} / {p['ge_3_bars']} / {p['ge_15_min']} / {p['ge_30_min']}",
        f"- median persist: {p['median_persist_bars']} bars, {p['median_persist_min']} min",
        f"- return to NEUTRAL: {p['returned_to_neutral']}",
        f"- direct opposite reversals: {p['direct_opposite_reversals']}",
        f"- raw would-be alerts (ledger): {a['R0_ledger_would_be_alert']}",
        "",
        "Compressed (not T+n fitted):",
        json.dumps({k: v for k, v in a.items() if k != "note"}, indent=2),
        "",
        "## Timing (stable >=2 bar first print)",
        json.dumps(result["timing_stable_ge2_first_hm"], indent=2),
        "",
        "## Transitions",
        json.dumps(result["transitions"], indent=2),
        "",
        "## DGC / structural",
        json.dumps(result["examples"]["structural"], indent=2),
        "",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")
    return js
