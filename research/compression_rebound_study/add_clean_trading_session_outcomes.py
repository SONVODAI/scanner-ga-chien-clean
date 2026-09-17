#!/usr/bin/env python3
"""
READ-ONLY examiner overlay: clean trading-session T3/T5/T10.

Does not modify production outcomes, earning-learning files, Edge Memory,
discovery, UI, services, timers, or historical artifacts.

Reads:
  research/compression_rebound_study/compression_stock_research.csv
  corroborating stored price artifacts (for calendar evidence only)

Writes:
  research/compression_rebound_study/compression_stock_research_clean_outcomes.csv
  Appends section 14 to compression_research_audit.md
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
PANEL_PATH = OUT_DIR / "compression_stock_research.csv"
AUDIT_PATH = OUT_DIR / "compression_research_audit.md"
OUT_CSV = OUT_DIR / "compression_stock_research_clean_outcomes.csv"
EL = ROOT / "data" / "earning_learning"

HORIZONS = (3, 5, 10)

# Documented non-trading weekdays in the study window.
# 2026-09-02 is Vietnam National Day (Quốc khánh). Stored artifacts have
# zero independent session evidence on Mon 08-31, Tue 09-01, and Wed 09-02.
NATIONAL_DAY_WINDOW = ("2026-08-31", "2026-09-01", "2026-09-02")


def _norm_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.strftime("%Y-%m-%d")


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def load_corroboration() -> pd.DataFrame:
    """Independent session evidence. Observation rows are NOT sufficient."""
    gev = pd.read_csv(ROOT / "group_evolution_history.csv", encoding="utf-8-sig")
    snap = pd.read_csv(ROOT / "data" / "earning_money_snapshots.csv", encoding="utf-8-sig")
    mkt = pd.read_csv(EL / "market_daily_t0.csv", encoding="utf-8-sig")
    mkt_s = pd.read_csv(EL / "market_t0_snapshot.csv", encoding="utf-8-sig")
    obs = pd.read_csv(EL / "observations.csv", encoding="utf-8-sig")

    gev_d = set(_norm_date(gev["date"]))
    gev_px = set(
        _norm_date(gev.loc[_num(gev["price"]).notna(), "date"])
    )
    snap_d = set(_norm_date(snap["snapshot_date"]))
    mkt_d = set(_norm_date(mkt["trade_date"]))
    # Session snapshot counts only if VNINDEX close is present.
    mkt_s = mkt_s.copy()
    mkt_s["trade_date"] = _norm_date(mkt_s["trade_date"])
    mkt_s["vnindex_close"] = _num(mkt_s.get("vnindex_close"))
    sess_d = set(mkt_s.loc[mkt_s["vnindex_close"].notna(), "trade_date"])

    obs = obs.copy()
    obs["trade_date"] = _norm_date(obs["trade_date"])
    obs["volume"] = _num(obs.get("volume"))
    obs["dt"] = pd.to_datetime(obs["trade_date"])
    weekday_vol_obs = set(
        obs.loc[(obs["dt"].dt.dayofweek < 5) & obs["volume"].notna(), "trade_date"]
    )

    rows = []
    window = {
        d.strftime("%Y-%m-%d")
        for d in pd.date_range("2026-07-23", "2026-09-08", freq="D")
    }
    all_dates = (
        gev_d | snap_d | mkt_d | sess_d | weekday_vol_obs | window | set(NATIONAL_DAY_WINDOW)
    )
    for d in sorted(all_dates):
        dt = pd.Timestamp(d)
        rows.append(
            {
                "date": d,
                "weekday": dt.day_name(),
                "is_weekend": bool(dt.dayofweek >= 5),
                "in_national_day_window": d in NATIONAL_DAY_WINDOW,
                "gev_price": d in gev_px,
                "snapshot": d in snap_d,
                "market_daily_t0": d in mkt_d,
                "market_session_vnindex": d in sess_d,
                "weekday_obs_with_volume": d in weekday_vol_obs,
            }
        )
    ev = pd.DataFrame(rows)
    ev["independent_session_evidence"] = (
        ev["gev_price"]
        | ev["snapshot"]
        | ev["market_daily_t0"]
        | ev["market_session_vnindex"]
        | ev["weekday_obs_with_volume"]
    )
    ev["eligible_session"] = (
        ~ev["is_weekend"]
        & ~ev["in_national_day_window"]
        & ev["independent_session_evidence"]
    )
    return ev


def project_nth_weekday(t0: str, n: int, holidays: set[str]) -> str | None:
    """Walk calendar days after T0, counting Mon–Fri minus known holidays."""
    cur = pd.Timestamp(t0)
    found = 0
    # Guard: do not invent an unbounded future.
    for _ in range(40):
        cur = cur + timedelta(days=1)
        ds = cur.strftime("%Y-%m-%d")
        if cur.dayofweek >= 5:
            continue
        if ds in holidays:
            continue
        found += 1
        if found == n:
            return ds
    return None


def attach_clean(panel: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["trade_date"] = _norm_date(out["trade_date"])
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    out["close"] = _num(out["close"])

    holidays = set(NATIONAL_DAY_WINDOW)
    confirmed = sorted(
        evidence.loc[evidence["eligible_session"], "date"].tolist()
    )
    # Restrict to the examiner panel window so T+n stays inside stored history
    # when the session exists; later weekdays are projected as WAITING only.
    panel_dates = set(out["trade_date"])
    confirmed = [d for d in confirmed if d in panel_dates or d >= min(panel_dates)]
    # Eligible T0/T+n sessions used for MATURE closes: weekday panel dates
    # that also have independent evidence and are not holidays/weekends.
    session_dates = sorted(
        d
        for d in out.loc[~out["is_weekend"].astype(bool), "trade_date"].unique()
        if d in set(evidence.loc[evidence["eligible_session"], "date"])
    )
    last_session = session_dates[-1] if session_dates else None
    index = {d: i for i, d in enumerate(session_dates)}

    close_map = {
        (r.trade_date, r.ticker): r.close
        for r in out[["trade_date", "ticker", "close"]].itertuples(index=False)
        if pd.notna(r.close)
    }

    def resolve(t0: str, ticker: str, n: int) -> tuple[str | None, float, str]:
        if t0 not in index:
            return None, np.nan, "UNAVAILABLE"
        c0 = close_map.get((t0, ticker))
        if c0 is None or not np.isfinite(c0) or float(c0) == 0:
            return None, np.nan, "UNAVAILABLE"
        j = index[t0] + n
        if j < len(session_dates):
            tn = session_dates[j]
            cn = close_map.get((tn, ticker))
            if cn is None or not np.isfinite(cn) or float(cn) == 0:
                return tn, np.nan, "UNAVAILABLE"
            # Definition: close(T+n)/close(T0)-1. Stored ×100 so the unit
            # matches production t*_return (percentage points).
            ret = (float(cn) / float(c0) - 1.0) * 100.0
            return tn, ret, "MATURE"
        tn = project_nth_weekday(t0, n, holidays)
        return tn, np.nan, "WAITING"

    for n in HORIZONS:
        dates: list = []
        rets: list = []
        stats: list = []
        for t0, ticker in zip(out["trade_date"], out["ticker"]):
            d, r, s = resolve(str(t0), str(ticker), n)
            dates.append(d)
            rets.append(r)
            stats.append(s)
        out[f"clean_T{n}_date"] = dates
        out[f"clean_T{n}_return"] = rets
        out[f"clean_T{n}_status"] = stats

    out.attrs["session_dates"] = session_dates
    out.attrs["last_session"] = last_session
    out.attrs["holidays"] = sorted(holidays)
    return out


def fmt(x, digits=4):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "n/a"
    return f"{float(x):.{digits}f}"


def compare_horizon(df: pd.DataFrame, n: int) -> dict:
    prod_ret = f"t{n}_return"
    prod_dt = f"t{n}_target_date"
    prod_st = f"t{n}_status"
    cln_ret = f"clean_T{n}_return"
    cln_dt = f"clean_T{n}_date"
    cln_st = f"clean_T{n}_status"

    both = df[(df[prod_st] == "MATURE") & (df[cln_st] == "MATURE")].copy()
    both[prod_dt] = _norm_date(both[prod_dt])
    both[cln_dt] = _norm_date(both[cln_dt])
    both["_abs"] = (_num(both[prod_ret]) - _num(both[cln_ret])).abs()
    date_diff = both[prod_dt] != both[cln_dt]

    # Dates where production target is a weekend, or T0 is weekend.
    t0_weekend = df["is_weekend"].astype(bool)
    prod_tgt = pd.to_datetime(df[prod_dt], errors="coerce")
    prod_tgt_weekend = prod_tgt.dt.dayofweek >= 5

    affected = df.loc[
        t0_weekend | prod_tgt_weekend.fillna(False),
        "trade_date",
    ].value_counts()

    return {
        "n": n,
        "prod_mature": int((df[prod_st] == "MATURE").sum()),
        "clean_mature": int((df[cln_st] == "MATURE").sum()),
        "prod_waiting": int((df[prod_st] == "WAITING").sum()),
        "clean_waiting": int((df[cln_st] == "WAITING").sum()),
        "prod_unavail": int((df[prod_st] == "UNAVAILABLE").sum()),
        "clean_unavail": int((df[cln_st] == "UNAVAILABLE").sum()),
        "comparable": int(len(both)),
        "date_diff_n": int(date_diff.sum()),
        "date_diff_pct": float(date_diff.mean() * 100.0) if len(both) else np.nan,
        "abs_mean": float(both["_abs"].mean()) if len(both) else np.nan,
        "abs_median": float(both["_abs"].median()) if len(both) else np.nan,
        "affected_t0": affected.head(8).to_dict(),
        "both": both,
    }


def most_date_mismatch_t0(both: pd.DataFrame, n: int) -> list[str]:
    if both.empty:
        return []
    prod_dt = f"t{n}_target_date"
    cln_dt = f"clean_T{n}_date"
    mask = both[prod_dt] != both[cln_dt]
    vc = both.loc[mask, "trade_date"].value_counts().head(8)
    return [f"{d}: {int(c)} rows" for d, c in vc.items()]


def build_section(df: pd.DataFrame, evidence: pd.DataFrame, session_dates: list[str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    comps = [compare_horizon(df, n) for n in HORIZONS]
    ev_win = evidence[
        (evidence["date"] >= "2026-07-23") & (evidence["date"] <= "2026-09-08")
    ].copy()

    lines = []
    lines.append("")
    lines.append("## 14. Clean trading-session T3/T5/T10 (examiner overlay)")
    lines.append("")
    lines.append(f"Appended at: `{now}` (UTC).")
    lines.append("Status: **examiner overlay only**. Production `t3/t5/t10_*` columns are unchanged.")
    lines.append("No threshold was tuned. No hypothesis test. No trading rule. No production write.")
    lines.append("")
    lines.append("### 14.1 File")
    lines.append("")
    lines.append(f"- `{OUT_CSV}`")
    lines.append(f"- Rows: **{len(df)}** (same identity as `compression_stock_research.csv`)")
    lines.append("- Added columns: `clean_T3_date`, `clean_T3_return`, `clean_T3_status`, and the T5/T10 analogues")
    lines.append("")
    lines.append("### 14.2 Definition")
    lines.append("")
    lines.append("- T0 = the row’s `trade_date` **only if** that date is an eligible HOSE/HNX session")
    lines.append("- T+n = the **nth eligible trading session after T0**")
    lines.append("- Raw return = `close(T+n) / close(T0) - 1`")
    lines.append("- `clean_T*_return` is stored as **percentage points** (`× 100`) so it sits beside production `t*_return`")
    lines.append("- If T0 is not an eligible session (weekend observation row): all clean horizons = `UNAVAILABLE`")
    lines.append("- If T+n session exists in the confirmed calendar but that ticker’s close is missing: `UNAVAILABLE` (no jump to another date)")
    lines.append("- If T+n falls after the last confirmed stored session (**2026-09-08**): `WAITING` (date may be a weekday projection; return is empty)")
    lines.append("")
    lines.append("### 14.3 Trading calendar source / derivation")
    lines.append("")
    lines.append("There is **no official HOSE calendar artifact** in the repo. The examiner calendar is derived, not inferred from observation rows alone.")
    lines.append("")
    lines.append("A date is an **eligible session** only if all of the following hold:")
    lines.append("")
    lines.append("1. It is Monday–Friday.")
    lines.append("2. It is **not** in the 2026 National Day non-trading window `2026-08-31`, `2026-09-01`, `2026-09-02`.")
    lines.append("3. It has **independent session evidence** from at least one stored price/market artifact:")
    lines.append("   - `group_evolution_history.csv` with a non-null `price`")
    lines.append("   - `data/earning_money_snapshots.csv`")
    lines.append("   - `data/earning_learning/market_daily_t0.csv`")
    lines.append("   - `data/earning_learning/market_t0_snapshot.csv` with a VNINDEX close")
    lines.append("   - weekday `observations.csv` rows that also store `volume` (weekend observation rows are ignored even if they exist)")
    lines.append("")
    lines.append("Observation-row presence **alone** is not enough. That is why `2026-07-26`, `2026-08-01`, `2026-08-02`, and `2026-08-08` are excluded.")
    lines.append("")
    lines.append("**National Day:** 2 Sep 2026 is Vietnam’s Quốc khánh. Across `observations`, freeze, snapshots, group-evolution, and market T0, those three weekdays have **zero** stored session prints. They are treated as the exchange holiday window. They are not synthesized as sessions.")
    lines.append("")
    lines.append("**2026-08-26** is kept. It is a Wednesday. `observations` / group-evolution missed it, but `earning_money_snapshots.csv` has 142 names whose prices/volumes differ from 2026-08-25 and 2026-08-27 (120/142 prices changed vs 25 Aug). That is treated as a real session, not a holiday.")
    lines.append("")
    lines.append("Confirmed eligible sessions used for MATURE closes:")
    lines.append("")
    lines.append("`" + ", ".join(session_dates) + "`")
    lines.append("")
    lines.append("Evidence table for the study window:")
    lines.append("")
    lines.append("| date | wd | weekend | ND window | gev px | snap | mkt daily | VNINDEX sess | wd obs+vol | eligible |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for _, r in ev_win.iterrows():
        lines.append(
            "| {d} | {wd} | {we} | {nd} | {g} | {s} | {m} | {v} | {o} | {e} |".format(
                d=r["date"],
                wd=str(r["weekday"])[:3],
                we="Y" if r["is_weekend"] else "",
                nd="Y" if r["in_national_day_window"] else "",
                g="Y" if r["gev_price"] else "",
                s="Y" if r["snapshot"] else "",
                m="Y" if r["market_daily_t0"] else "",
                v="Y" if r["market_session_vnindex"] else "",
                o="Y" if r["weekday_obs_with_volume"] else "",
                e="YES" if r["eligible_session"] else "",
            )
        )
    lines.append("")
    lines.append("Closes used for clean returns are the stored `close` values already on the examiner panel for that ticker × eligible session (freeze > observations > snapshot fill). No close was recomputed or interpolated.")
    lines.append("")
    lines.append("### 14.4 Production vs clean comparison")
    lines.append("")
    lines.append("Comparable row = production status `MATURE` **and** clean status `MATURE`. Date comparison uses production `t*_target_date` vs `clean_T*_date`. Return difference is absolute percentage-point gap.")
    lines.append("")
    lines.append("| horizon | prod MATURE | clean MATURE | prod WAITING | clean WAITING | prod UNAVAIL | clean UNAVAIL | comparable | target date differs | date-diff % | mean\\|Δret\\| | median\\|Δret\\| |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for c in comps:
        lines.append(
            "| T{n} | {pm} | {cm} | {pw} | {cw} | {pu} | {cu} | {k} | {dd} | {ddp} | {am} | {amd} |".format(
                n=c["n"],
                pm=c["prod_mature"],
                cm=c["clean_mature"],
                pw=c["prod_waiting"],
                cw=c["clean_waiting"],
                pu=c["prod_unavail"],
                cu=c["clean_unavail"],
                k=c["comparable"],
                dd=c["date_diff_n"],
                ddp=fmt(c["date_diff_pct"], 1),
                am=fmt(c["abs_mean"], 4),
                amd=fmt(c["abs_median"], 4),
            )
        )
    lines.append("")
    lines.append("Maturity-date differences (clean vs production):")
    lines.append("")
    for c in comps:
        delta = c["clean_mature"] - c["prod_mature"]
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"- T{c['n']}: clean has {sign}{delta} MATURE rows vs production "
            f"({c['clean_mature']} vs {c['prod_mature']}). "
            f"Clean WAITING={c['clean_waiting']} (production {c['prod_waiting']}); "
            f"clean UNAVAILABLE={c['clean_unavail']} (production {c['prod_unavail']})."
        )
    lines.append("")
    lines.append("T0 dates with the most production-vs-clean **target date** mismatches among comparable rows:")
    lines.append("")
    for c in comps:
        hits = most_date_mismatch_t0(c["both"], c["n"])
        lines.append(f"- T{c['n']}: {', '.join(hits) if hits else 'none'}")
    lines.append("")
    lines.append("### 14.5 Dates most affected by weekend / holiday observation rows")
    lines.append("")
    lines.append("Weekend T0 rows (`is_weekend=true`) are **not** eligible sessions. Clean T3/T5/T10 on those rows are `UNAVAILABLE`. Production still treats them as observation-index T0.")
    lines.append("")
    weekend_n = int(df["is_weekend"].astype(bool).sum())
    lines.append(f"- Weekend T0 rows in the panel: **{weekend_n}** (4 dates × 142 names).")
    lines.append("- Weekend T0 dates: `2026-07-26`, `2026-08-01`, `2026-08-02`, `2026-08-08`.")
    lines.append("- National Day window skipped by the clean calendar: `2026-08-31`, `2026-09-01`, `2026-09-02`.")
    lines.append("- Capture hole that **is** a session: `2026-08-26` (in clean calendar via snapshots; absent from production observation index).")
    lines.append("- Capture hole that stretches production T+n: `2026-09-03` has only 4 observation rows, so production often jumps from `2026-08-28` to `2026-09-04` for the other 138 names. Clean T+1 after `2026-08-28` is `2026-09-03` for every name that has a stored close that day.")
    lines.append("")
    # Concrete examples
    def example(ticker: str, t0: str) -> str:
        row = df[(df["ticker"] == ticker) & (df["trade_date"] == t0)]
        if row.empty:
            return f"{ticker} {t0}: not in panel"
        r = row.iloc[0]
        return (
            f"{ticker} {t0}: prod T3 {r['t3_status']} date={r['t3_target_date']} ret={fmt(r['t3_return'], 3)}; "
            f"clean T3 {r['clean_T3_status']} date={r['clean_T3_date']} ret={fmt(r['clean_T3_return'], 3)}"
        )

    lines.append("Worked examples (not a rule):")
    lines.append("")
    lines.append(f"- {example('ACB', '2026-08-08')}  ← Saturday observation T0")
    lines.append(f"- {example('ACB', '2026-08-25')}  ← production skips 2026-08-26")
    lines.append(f"- {example('ACB', '2026-08-28')}  ← National Day + 09-03 observation hole")
    lines.append(f"- {example('ACB', '2026-08-26')}  ← snapshot-only session; production has no observation_id")
    lines.append("")
    lines.append("Use this overlay only to see how much the observation-row T+n clock differs from a session clock. Do not encode the difference as an edge.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    panel = pd.read_csv(PANEL_PATH, encoding="utf-8")
    evidence = load_corroboration()
    out = attach_clean(panel, evidence)
    session_dates = list(out.attrs.get("session_dates") or [])

    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    section = build_section(out, evidence, session_dates)
    existing = AUDIT_PATH.read_text(encoding="utf-8")
    marker = "## 14. Clean trading-session T3/T5/T10"
    if marker in existing:
        existing = existing.split(marker)[0].rstrip() + "\n"
    AUDIT_PATH.write_text(existing + section, encoding="utf-8")

    artifacts = Path("/opt/cursor/artifacts")
    if artifacts.exists():
        try:
            out.to_csv(artifacts / "compression_stock_research_clean_outcomes.csv", index=False, encoding="utf-8")
            (artifacts / "compression_research_audit.md").write_text(
                AUDIT_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        except OSError:
            pass

    print(f"wrote {OUT_CSV} rows={len(out)}")
    print("sessions", session_dates)
    for n in HORIZONS:
        print(
            f"T{n}",
            out[f"clean_T{n}_status"].value_counts().to_dict(),
        )


if __name__ == "__main__":
    main()
