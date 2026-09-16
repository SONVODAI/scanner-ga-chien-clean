#!/usr/bin/env python3
"""Isolated read-only study: scanner setup × frozen 5m P×V × T3/T5/T10.

Reads production CSVs. Writes only under this research directory.
Does not import writers, change thresholds, or touch Camera / VPS paths.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ART = HERE / "artifacts"
REPORT = HERE / "REPORT.md"
VN_TZ = "Asia/Ho_Chi_Minh"

STUDY_SETUPS = [
    "CP MẠNH",
    "PULL ĐẸP",
    "PULL VỪA",
    "MUA EARLY",
    "MUA BREAK",
    "TÍCH LŨY",
]

PXV_CONDITIONS = [
    "5m_volume_EXPANSION",
    "5m_volume_CONTRACTION",
    "5m_volume_NORMAL",
    "price_UP",
    "price_FLAT",
    "price_DOWN",
    "P×V_CONFIRMING",
    "P×V_WEAK",
    "SELL_EXPANSION",
    "pace_ahead_or_RVOL",
    "evidence_STRENGTHEN",
    "evidence_NEUTRAL",
    "evidence_CONFLICT",
    "evidence_WEAKEN",
    "transition_CONTRACTION→EXPANSION",
    "transition_NEUTRAL→STRENGTHEN",
    "transition_WEAKEN→STRENGTHEN",
]

# Frozen P×V research defaults (documented, not changed).
PXV_DEFAULTS = {
    "RESEARCH_DEFAULT_EXPANSION_X": 2.0,
    "RESEARCH_DEFAULT_CONTRACTION_X": 0.70,
    "RESEARCH_DEFAULT_PACE_AHEAD_X": 1.5,
    "RESEARCH_DEFAULT_SESSION_MEDIAN_BARS": 6,
}

# Evidence-quality bands used by earning-learning UI (app.py).
N_T3_RELIABLE = 200
N_T5_RELIABLE = 100
N_T10_RELIABLE = 50
N_T3_PROVISIONAL = 30
N_T5_PROVISIONAL = 20
N_T10_PROVISIONAL = 10

ACTIONABLE_ELITE = {"BUY ELITE", "MUA NHỎ / ƯU TIÊN"}

CAMERA_CANDIDATES = [
    os.getenv("MRBOT_INTRADAY_DATA_ROOT", "").strip(),
    "/var/lib/mrbot/intraday_memory",
    str(REPO / "intraday_memory"),
    str(REPO / "data" / "intraday_pxv_v1"),
]


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not _exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False, **kwargs)


def _to_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.tz_localize(None).dt.normalize()


def _boolish(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    mapped = s.astype(str).str.strip().str.lower()
    return mapped.isin({"true", "1", "yes", "y"})


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def classify_vn_clock(ts: pd.Series) -> pd.Series:
    """Bucket a datetime series into VN session regions. NaT → UNKNOWN.

    Timezone-aware values are converted to VN. Naive values are treated as
    VN wall clock (CSV save times in this repo are local, not UTC).
    """
    t = pd.to_datetime(ts, errors="coerce")
    if getattr(t.dt, "tz", None) is None:
        local = t.dt.tz_localize(VN_TZ, ambiguous="NaT", nonexistent="NaT")
    else:
        local = t.dt.tz_convert(VN_TZ)
    hm = local.dt.hour * 60 + local.dt.minute
    out = pd.Series("UNKNOWN", index=ts.index, dtype="object")
    valid = hm.notna()
    minutes = hm.fillna(-1).astype(int)
    out.loc[valid & (minutes < 9 * 60)] = "PRE_OPEN"
    out.loc[valid & (minutes >= 9 * 60) & (minutes < 9 * 60 + 15)] = "OPEN_AUCTION"
    out.loc[valid & (minutes >= 9 * 60 + 15) & (minutes <= 11 * 60 + 30)] = "AM_SESSION"
    out.loc[valid & (minutes > 11 * 60 + 30) & (minutes < 13 * 60)] = "LUNCH"
    out.loc[valid & (minutes >= 13 * 60) & (minutes <= 14 * 60 + 45)] = "PM_SESSION"
    out.loc[valid & (minutes > 14 * 60 + 45) & (minutes < 15 * 60)] = "ATC"
    out.loc[valid & (minutes >= 15 * 60)] = "POST_CLOSE"
    return out


def parse_naive_vn(date_col: pd.Series, time_col: pd.Series) -> pd.Series:
    """Combine date + time strings as naive VN wall clock, then tag UTC."""
    d = pd.to_datetime(date_col, errors="coerce")
    raw_t = time_col.astype(str).str.strip()
    # evolution uses "YYYY-MM-DD HH:MM"; pattern_history uses "HH:MM:SS"
    has_date = raw_t.str.contains(r"\d{4}-\d{2}-\d{2}", regex=True, na=False)
    combined = pd.Series(pd.NaT, index=date_col.index, dtype="datetime64[ns]")
    if has_date.any():
        combined.loc[has_date] = pd.to_datetime(raw_t.loc[has_date], errors="coerce")
    rest = ~has_date
    if rest.any():
        tpart = raw_t.loc[rest]
        # keep last token if "YYYY-MM-DD HH:MM"
        tpart = tpart.str.replace(r"^.*\s", "", regex=True)
        stamp = d.loc[rest].dt.strftime("%Y-%m-%d") + " " + tpart
        combined.loc[rest] = pd.to_datetime(stamp, errors="coerce")
    aware = pd.to_datetime(combined, errors="coerce")
    # localize as VN then convert to UTC for classify_vn_clock
    try:
        localized = aware.dt.tz_localize(VN_TZ, ambiguous="NaT", nonexistent="NaT")
    except TypeError:
        localized = aware
    return localized


def coverage_block(name: str, df: pd.DataFrame, date_col: str, symbol_col: str = "symbol") -> dict[str, Any]:
    if df.empty:
        return {
            "source": name,
            "rows": 0,
            "present": False,
            "date_min": None,
            "date_max": None,
            "n_dates": 0,
            "n_symbols": 0,
            "note": "FILE_ABSENT_OR_EMPTY",
        }
    dates = _to_date(df[date_col]) if date_col in df.columns else pd.Series(dtype="datetime64[ns]")
    symbols = (
        df[symbol_col].astype(str).str.upper()
        if symbol_col in df.columns
        else pd.Series(dtype=str)
    )
    valid_dates = dates.dropna()
    return {
        "source": name,
        "rows": int(len(df)),
        "present": True,
        "date_min": str(valid_dates.min().date()) if not valid_dates.empty else None,
        "date_max": str(valid_dates.max().date()) if not valid_dates.empty else None,
        "n_dates": int(valid_dates.nunique()) if not valid_dates.empty else 0,
        "n_symbols": int(symbols.nunique()) if not symbols.empty else 0,
        "columns": list(df.columns[:40]),
    }


def evidence_quality_baseline(n_t3: int, n_t5: int, n_t10: int) -> str:
    if n_t3 >= N_T3_RELIABLE and n_t5 >= N_T5_RELIABLE and n_t10 >= N_T10_RELIABLE:
        return "ADEQUATE_FOR_SETUP_BASELINE_ONLY"
    if n_t3 >= N_T3_PROVISIONAL and n_t5 >= N_T5_PROVISIONAL:
        return "PROVISIONAL"
    if n_t3 > 0:
        return "INSUFFICIENT"
    return "NO_ROWS"


def summarize_horizons(df: pd.DataFrame) -> dict[str, Any]:
    """Expect lifecycle-shaped columns t{3,5,10}_return_pct / _is_win / max_gain / max_drawdown."""
    out: dict[str, Any] = {"N_rows": int(len(df))}
    for h in (3, 5, 10):
        ret = _num(df[f"t{h}_return_pct"]) if f"t{h}_return_pct" in df.columns else pd.Series(dtype=float)
        win = _boolish(df[f"t{h}_is_win"]) if f"t{h}_is_win" in df.columns else pd.Series(dtype=bool)
        mfe = _num(df[f"t{h}_max_gain_pct"]) if f"t{h}_max_gain_pct" in df.columns else pd.Series(dtype=float)
        mae = _num(df[f"t{h}_max_drawdown_pct"]) if f"t{h}_max_drawdown_pct" in df.columns else pd.Series(dtype=float)
        mask = ret.notna()
        n = int(mask.sum())
        out[f"T{h}_N"] = n
        if n == 0:
            out[f"T{h}_winrate"] = None
            out[f"T{h}_avg"] = None
            out[f"T{h}_median"] = None
            out[f"T{h}_avg_max_gain"] = None
            out[f"T{h}_avg_max_dd"] = None
            continue
        wmask = mask & win.notna() if len(win) == len(df) else mask
        out[f"T{h}_winrate"] = float(win[wmask].mean() * 100.0) if wmask.any() else None
        out[f"T{h}_avg"] = float(ret[mask].mean())
        out[f"T{h}_median"] = float(ret[mask].median())
        out[f"T{h}_avg_max_gain"] = float(mfe[mask].mean()) if mfe.notna().any() else None
        out[f"T{h}_avg_max_dd"] = float(mae[mask].mean()) if mae.notna().any() else None
    out["evidence_quality"] = evidence_quality_baseline(
        out.get("T3_N", 0), out.get("T5_N", 0), out.get("T10_N", 0)
    )
    return out


def fmt_pct(x: Any, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    return f"{x:.{digits}f}"


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(empty)_"
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df.iterrows():
        cells = [str(row[c]) if pd.notna(row[c]) else "—" for c in df.columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def row_from_summary(setup: str, source: str, stats: dict[str, Any], extra: dict | None = None) -> dict[str, Any]:
    d = {
        "setup": setup,
        "source": source,
        "N_rows": stats.get("N_rows", 0),
        "T3_N": stats.get("T3_N", 0),
        "T3_winrate": stats.get("T3_winrate"),
        "T3_avg": stats.get("T3_avg"),
        "T3_median": stats.get("T3_median"),
        "T3_avg_MFE": stats.get("T3_avg_max_gain"),
        "T3_avg_MAE": stats.get("T3_avg_max_dd"),
        "T5_N": stats.get("T5_N", 0),
        "T5_winrate": stats.get("T5_winrate"),
        "T5_avg": stats.get("T5_avg"),
        "T5_median": stats.get("T5_median"),
        "T5_avg_MFE": stats.get("T5_avg_max_gain"),
        "T5_avg_MAE": stats.get("T5_avg_max_dd"),
        "T10_N": stats.get("T10_N", 0),
        "T10_winrate": stats.get("T10_winrate"),
        "T10_avg": stats.get("T10_avg"),
        "T10_median": stats.get("T10_median"),
        "T10_avg_MFE": stats.get("T10_avg_max_gain"),
        "T10_avg_MAE": stats.get("T10_avg_max_dd"),
        "evidence_quality": stats.get("evidence_quality"),
    }
    if extra:
        d.update(extra)
    return d


def display_outcome_table(rows: list[dict[str, Any]]) -> pd.DataFrame:
    raw = pd.DataFrame(rows)
    if raw.empty:
        return raw
    show = pd.DataFrame(
        {
            "Setup": raw["setup"],
            "Source": raw["source"],
            "N": raw["N_rows"],
            "T3 N": raw["T3_N"],
            "T3 win%": raw["T3_winrate"].map(lambda x: fmt_pct(x, 1)),
            "T3 avg": raw["T3_avg"].map(lambda x: fmt_pct(x, 2)),
            "T3 med": raw["T3_median"].map(lambda x: fmt_pct(x, 2)),
            "T3 MFE": raw["T3_avg_MFE"].map(lambda x: fmt_pct(x, 2)),
            "T3 MAE": raw["T3_avg_MAE"].map(lambda x: fmt_pct(x, 2)),
            "T5 N": raw["T5_N"],
            "T5 win%": raw["T5_winrate"].map(lambda x: fmt_pct(x, 1)),
            "T5 avg": raw["T5_avg"].map(lambda x: fmt_pct(x, 2)),
            "T10 N": raw["T10_N"],
            "T10 win%": raw["T10_winrate"].map(lambda x: fmt_pct(x, 1)),
            "T10 avg": raw["T10_avg"].map(lambda x: fmt_pct(x, 2)),
            "T10 med": raw["T10_median"].map(lambda x: fmt_pct(x, 2)),
            "T10 MFE": raw["T10_avg_MFE"].map(lambda x: fmt_pct(x, 2)),
            "T10 MAE": raw["T10_avg_MAE"].map(lambda x: fmt_pct(x, 2)),
            "evidence quality": raw["evidence_quality"],
        }
    )
    return show


def camera_inventory() -> dict[str, Any]:
    found = []
    missing = []
    for raw in CAMERA_CANDIDATES:
        if not raw:
            continue
        p = Path(raw)
        if _exists(p):
            n_parquet = 0
            try:
                n_parquet = sum(1 for _ in p.rglob("*.parquet"))
            except OSError:
                n_parquet = -1
            found.append({"path": str(p), "n_parquet": n_parquet})
        else:
            missing.append(str(p))
    return {
        "found": found,
        "missing": missing,
        "canonical_5m_available": any(x.get("n_parquet", 0) > 0 for x in found),
        "verdict": "UNSAFE FOR THIS STUDY"
        if not any(x.get("n_parquet", 0) > 0 for x in found)
        else "SAFE AS-OF (path exists; still must join only bars with timestamp <= asof)",
    }


def group_counts(df: pd.DataFrame, group_col: str = "group") -> pd.DataFrame:
    if df.empty or group_col not in df.columns:
        return pd.DataFrame(columns=["group", "N"])
    g = df[group_col].astype(str).str.strip()
    vc = g.value_counts(dropna=False)
    out = vc.rename_axis("group").reset_index(name="N")
    return out


def first_last_group(ph: pd.DataFrame) -> pd.DataFrame:
    if ph.empty:
        return pd.DataFrame()
    work = ph.copy()
    work["symbol"] = work["symbol"].astype(str).str.upper()
    work["date"] = _to_date(work["date"])
    work["group"] = work["group"].astype(str).str.strip()
    work["_ts"] = parse_naive_vn(work["date"], work["time"])
    work["_clock"] = classify_vn_clock(work["_ts"])
    work = work.dropna(subset=["date", "symbol"])
    work = work.sort_values(["symbol", "date", "_ts"], kind="stable")
    first = work.groupby(["symbol", "date"], as_index=False).first()
    last = work.groupby(["symbol", "date"], as_index=False).last()
    nuniq = work.groupby(["symbol", "date"])["group"].nunique().reset_index(name="n_groups")
    nsnap = work.groupby(["symbol", "date"]).size().reset_index(name="n_snapshots")
    merged = first[["symbol", "date", "group", "_clock", "_ts"]].rename(
        columns={"group": "first_group", "_clock": "first_clock", "_ts": "first_ts"}
    )
    merged = merged.merge(
        last[["symbol", "date", "group", "_clock", "_ts"]].rename(
            columns={"group": "last_group", "_clock": "last_clock", "_ts": "last_ts"}
        ),
        on=["symbol", "date"],
        how="left",
    )
    merged = merged.merge(nuniq, on=["symbol", "date"], how="left")
    merged = merged.merge(nsnap, on=["symbol", "date"], how="left")
    merged["first_ne_last"] = merged["first_group"] != merged["last_group"]
    intra = work[work["_clock"].isin(["AM_SESSION", "PM_SESSION"])]
    if not intra.empty:
        intra_first = intra.groupby(["symbol", "date"], as_index=False).first()[["symbol", "date", "group"]]
        intra_last = intra.groupby(["symbol", "date"], as_index=False).last()[["symbol", "date", "group"]]
        intra_m = intra_first.rename(columns={"group": "intra_first_group"}).merge(
            intra_last.rename(columns={"group": "intra_last_group"}),
            on=["symbol", "date"],
            how="outer",
        )
        merged = merged.merge(intra_m, on=["symbol", "date"], how="left")
        merged["intra_first_ne_last"] = (
            merged["intra_first_group"].notna()
            & merged["intra_last_group"].notna()
            & (merged["intra_first_group"] != merged["intra_last_group"])
        )
    else:
        merged["intra_first_group"] = pd.NA
        merged["intra_last_group"] = pd.NA
        merged["intra_first_ne_last"] = False
    return merged


def attach_lifecycle(left: pd.DataFrame, lifecycle: pd.DataFrame, on_symbol_date: bool = False) -> pd.DataFrame:
    if left.empty or lifecycle.empty:
        return pd.DataFrame()
    lc = lifecycle.copy()
    lc["symbol"] = lc["symbol"].astype(str).str.upper()
    if on_symbol_date:
        left = left.copy()
        left["symbol"] = left["symbol"].astype(str).str.upper()
        left["_d"] = _to_date(left["date"] if "date" in left.columns else left["trade_date"])
        lc["_d"] = _to_date(lc["entry_date"] if "entry_date" in lc.columns else lc["trade_date"])
        # last lifecycle row per symbol-date
        lc = lc.sort_values(["symbol", "_d"], kind="stable").drop_duplicates(["symbol", "_d"], keep="last")
        keep = [
            c
            for c in lc.columns
            if c.startswith("t3_")
            or c.startswith("t5_")
            or c.startswith("t10_")
            or c in {"symbol", "_d", "observation_id", "entry_date", "group"}
        ]
        return left.merge(lc[keep], on=["symbol", "_d"], how="inner", suffixes=("", "_lc"))
    if "observation_id" not in left.columns:
        return pd.DataFrame()
    keep = [c for c in lc.columns]
    return left.merge(lc, on="observation_id", how="inner", suffixes=("", "_lc"))


def setup_sample_table(label: str, df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for setup in STUDY_SETUPS:
        if df.empty or group_col not in df.columns:
            n = 0
        else:
            n = int((df[group_col].astype(str).str.strip() == setup).sum())
        rows.append(
            {
                "setup": setup,
                "source": label,
                "N": n,
                "testable_for_intraday_pxv": "NOT TESTABLE — no canonical 5m Camera",
                "testable_for_setup_baseline": "YES" if n >= N_T3_PROVISIONAL else ("WEAK" if n > 0 else "NO"),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)

    # --- load sources (read-only) ---
    ph_root = _read_csv(REPO / "pattern_history.csv")
    evo = _read_csv(REPO / "group_evolution_history.csv")
    elite = _read_csv(REPO / "buy_elite_learning_history.csv")
    freeze = _read_csv(REPO / "data" / "earning_learning" / "t0_observation_freeze.csv")
    observations = _read_csv(REPO / "data" / "earning_learning" / "observations.csv")
    outcomes = _read_csv(REPO / "data" / "earning_learning" / "outcomes.csv")
    lifecycle = _read_csv(REPO / "data" / "earning_learning" / "pattern_lifecycle.csv")
    el_ph = _read_csv(REPO / "data" / "earning_learning" / "pattern_history.csv")
    market_t0 = _read_csv(REPO / "data" / "earning_learning" / "market_daily_t0.csv")
    market_snap = _read_csv(REPO / "data" / "earning_learning" / "market_t0_snapshot.csv")
    cam = camera_inventory()

    inventory_rows = [
        coverage_block("pattern_history.csv (root GENESIS_V24)", ph_root, "date"),
        coverage_block("group_evolution_history.csv", evo, "date"),
        coverage_block("buy_elite_learning_history.csv", elite, "date"),
        coverage_block("t0_observation_freeze.csv", freeze, "trade_date"),
        coverage_block("observations.csv", observations, "trade_date"),
        coverage_block("outcomes.csv", outcomes, "entry_date"),
        coverage_block("pattern_lifecycle.csv", lifecycle, "entry_date"),
        coverage_block("data/earning_learning/pattern_history.csv", el_ph, "trade_date"),
        coverage_block("market_daily_t0.csv", market_t0, "trade_date", symbol_col="entity"),
        coverage_block("market_t0_snapshot.csv", market_snap, "trade_date", symbol_col="entity"),
        {
            "source": "canonical 5m Camera parquet",
            "rows": 0,
            "present": cam["canonical_5m_available"],
            "date_min": None,
            "date_max": None,
            "n_dates": 0,
            "n_symbols": 0,
            "note": json.dumps(cam, ensure_ascii=False),
        },
        {
            "source": "per-symbol daily OHLCV panel",
            "rows": 0,
            "present": False,
            "date_min": None,
            "date_max": None,
            "n_dates": 0,
            "n_symbols": 0,
            "note": "No dedicated daily bars store in repo. Forward T3/T5/T10 already materialized in outcomes/lifecycle from observation-row steps.",
        },
    ]
    inv_df = pd.DataFrame(inventory_rows)
    inv_df.to_csv(ART / "A_data_inventory.csv", index=False)

    # --- timestamp quality ---
    clock_summaries = []

    def add_clock(name: str, series: pd.Series, date_vs: pd.Series | None = None) -> None:
        buckets = classify_vn_clock(series)
        vc = buckets.value_counts(dropna=False)
        rec = {"source": name, **{str(k): int(v) for k, v in vc.items()}}
        rec["n"] = int(len(series))
        parsed = pd.to_datetime(series, errors="coerce")
        rec["n_parse_ok"] = int(parsed.notna().sum())
        if date_vs is not None:
            if getattr(parsed.dt, "tz", None) is None:
                rec_at = parsed.dt.tz_localize(VN_TZ, ambiguous="NaT", nonexistent="NaT")
            else:
                rec_at = parsed.dt.tz_convert(VN_TZ)
            rec_d = rec_at.dt.strftime("%Y-%m-%d")
            trade_d = pd.to_datetime(date_vs, errors="coerce").dt.strftime("%Y-%m-%d")
            ok = rec_at.notna() & pd.to_datetime(date_vs, errors="coerce").notna()
            rec["recorded_after_trade_date"] = int((ok & (rec_d > trade_d)).sum())
            rec["recorded_same_trade_date"] = int((ok & (rec_d == trade_d)).sum())
            rec["recorded_before_trade_date"] = int((ok & (rec_d < trade_d)).sum())
        clock_summaries.append(rec)

    if not freeze.empty:
        add_clock("t0_freeze.recorded_at", freeze["recorded_at"], freeze["trade_date"])
        if "frozen_at" in freeze.columns:
            add_clock("t0_freeze.frozen_at", freeze["frozen_at"], freeze["trade_date"])
    if not observations.empty:
        add_clock("observations.recorded_at", observations["recorded_at"], observations["trade_date"])
    if not ph_root.empty:
        ph_ts = parse_naive_vn(ph_root["date"], ph_root["time"])
        add_clock("pattern_history.date+time (naive VN)", ph_ts, ph_root["date"])
    if not evo.empty:
        evo_ts = parse_naive_vn(evo["date"], evo["time"])
        add_clock("group_evolution.date+time (naive VN)", evo_ts, evo["date"])
    if not elite.empty:
        elite_ts = parse_naive_vn(elite["date"], elite["time"])
        add_clock("elite.date+time (naive VN)", elite_ts, elite["date"])

    clock_df = pd.DataFrame(clock_summaries)
    clock_df.to_csv(ART / "A_timestamp_clock_buckets.csv", index=False)

    # --- chronology classification ---
    chronology = [
        {
            "source": "canonical 5m Camera parquet",
            "class": "UNSAFE FOR THIS STUDY",
            "reason": "No parquet under camera_data_root candidates in this workspace. Frozen P×V features cannot be computed. Do not invent bars.",
        },
        {
            "source": "frozen P×V interpreter / data/intraday_pxv_v1 ledger",
            "class": "UNSAFE FOR THIS STUDY",
            "reason": "Output store absent; interpreter is code-only. Historical STRENGTHEN/CONFIRMING states were never persisted here.",
        },
        {
            "source": "pattern_history.csv group at a given row timestamp",
            "class": "PARTIAL / QUARANTINE",
            "reason": "Row carries a group at CSV save clock. Useful as as-of IF that clock is true observation time. Documented Elite path says CSV time is save clock, last-wins — same risk here. PRE_OPEN 08:30 rows are not 5m session bars. Do not use a later same-day row as the morning group.",
        },
        {
            "source": "pattern_history last row per symbol×date",
            "class": "UNSAFE FOR THIS STUDY",
            "reason": "Last-wins. If group evolved intra-day, the saved label is future relative to earlier 5m bars.",
        },
        {
            "source": "group_evolution_history.csv",
            "class": "PARTIAL / QUARANTINE",
            "reason": "Dated group snapshots exist. Times cluster pre-open / save clock. Rank/score often empty. Safe only as ordered history of saved labels, not as 5m as-of.",
        },
        {
            "source": "t0_observation_freeze.group",
            "class": "PARTIAL / QUARANTINE",
            "reason": "Same-day post-close freeze (typically ~15:54 VN). Valid as EOD T0 setup for daily T3/T5/T10. UNSAFE as intra-day as-of for 5m P×V (group already embeds the finished session).",
        },
        {
            "source": "observations.csv group / recorded_at",
            "class": "UNSAFE FOR THIS STUDY",
            "reason": "recorded_at is frequently next calendar morning UTC. Using that group as T0 intra-day knowledge is look-ahead.",
        },
        {
            "source": "pattern_lifecycle.group",
            "class": "UNSAFE FOR THIS STUDY",
            "reason": "Lifecycle copies observation group (T+1 clock) plus later outcome fill. Not first_seen setup.",
        },
        {
            "source": "buy_elite_learning_history.group",
            "class": "PARTIAL / QUARANTINE",
            "reason": "One row per symbol×date, last file order wins. CSV time is save clock not candidate_first_seen_ts. Group is pass-through scan label on an Elite-filtered subset (selection bias).",
        },
        {
            "source": "daily volume_ratio / volume_ratio20 on freeze or pattern_history",
            "class": "UNSAFE FOR THIS STUDY",
            "reason": "Daily (or session-injected daily) volume vs 20-day mean. Not frozen 5m expansion/contraction/CONFIRMING. Must not proxy P×V.",
        },
        {
            "source": "outcomes.csv / pattern_lifecycle T3 T5 T10",
            "class": "SAFE AS-OF for forward daily outcomes",
            "reason": "Horizons are forward from T0 observation price. Nested by construction. Computed as +n observation rows per symbol, which approximates trading sessions when coverage is complete. MFE=max_gain_pct, MAE=max_drawdown_pct on the forward slice.",
        },
        {
            "source": "pattern_history t1/t3/t5/t10 columns on the same snapshot row",
            "class": "UNSAFE FOR THIS STUDY as contemporaneous features",
            "reason": "Forward returns attached onto historical snapshot rows are filled later. Using them as if known at sample time is look-ahead. They may still be used as outcomes if join is by symbol×date and fill is complete — prefer earning_learning outcomes.",
        },
        {
            "source": "market_daily_t0 VNINDEX OHLCV",
            "class": "SAFE AS-OF for market regime (EOD)",
            "reason": "AFTER_CLOSE snapshots. Use as regime control, not as 5m P×V.",
        },
    ]
    chrono_df = pd.DataFrame(chronology)
    chrono_df.to_csv(ART / "B_chronology_verdict.csv", index=False)

    # --- pattern_history first vs last ---
    fl = first_last_group(ph_root) if not ph_root.empty else pd.DataFrame()
    if not fl.empty:
        fl.to_csv(ART / "I_pattern_history_first_last_group.csv", index=False)
    leak_ph = {
        "symbol_date_pairs": int(len(fl)) if not fl.empty else 0,
        "pairs_with_multiple_snapshots": int((fl["n_snapshots"] > 1).sum()) if not fl.empty else 0,
        "pairs_with_group_change_any_clock": int(fl["first_ne_last"].sum()) if not fl.empty else 0,
        "pairs_with_intra_session_group_change": int(fl["intra_first_ne_last"].fillna(False).sum())
        if not fl.empty and "intra_first_ne_last" in fl.columns
        else 0,
        "first_clock": fl["first_clock"].value_counts().to_dict() if not fl.empty else {},
        "last_clock": fl["last_clock"].value_counts().to_dict() if not fl.empty else {},
    }

    # --- freeze duplicates / clock ---
    freeze_dup = 0
    freeze_clock = {}
    if not freeze.empty:
        freeze = freeze.copy()
        freeze["group"] = freeze["group"].astype(str).str.strip()
        freeze["symbol"] = freeze["symbol"].astype(str).str.upper()
        freeze_dup = int(freeze.duplicated(["observation_id"]).sum())
        freeze["_clock"] = classify_vn_clock(freeze["recorded_at"])
        freeze_clock = freeze["_clock"].value_counts().to_dict()

    # --- sample-size tables ---
    sample_parts = [
        setup_sample_table("t0_freeze EOD group (quarantine)", freeze, "group"),
        setup_sample_table(
            "pattern_history ALL rows (not a valid unit)",
            ph_root,
            "group",
        ),
    ]
    if not fl.empty:
        sample_parts.append(
            setup_sample_table(
                "pattern_history FIRST snapshot/day (quarantine as-of)",
                fl.rename(columns={"first_group": "group"}),
                "group",
            )
        )
        sample_parts.append(
            setup_sample_table(
                "pattern_history LAST snapshot/day (UNSAFE as-of)",
                fl.rename(columns={"last_group": "group"}),
                "group",
            )
        )
    if not evo.empty:
        sample_parts.append(setup_sample_table("group_evolution ALL rows", evo, "group"))
    if not elite.empty:
        sample_parts.append(setup_sample_table("elite history ALL conclusions", elite, "group"))
        elite_act = elite[elite["conclusion"].astype(str).isin(ACTIONABLE_ELITE)].copy()
        sample_parts.append(
            setup_sample_table("elite BUY ELITE + MUA NHỎ last-wins subset", elite_act, "group")
        )
    sample_df = pd.concat(sample_parts, ignore_index=True)
    sample_df.to_csv(ART / "C_sample_size_by_setup.csv", index=False)

    # --- join freeze to lifecycle for setup baselines ---
    baseline_rows: list[dict[str, Any]] = []
    lc = lifecycle.copy() if not lifecycle.empty else pd.DataFrame()
    if not lc.empty:
        lc["symbol"] = lc["symbol"].astype(str).str.upper()

    freeze_lc = pd.DataFrame()
    if not freeze.empty and not lc.empty:
        freeze_lc = attach_lifecycle(freeze, lc, on_symbol_date=False)
        # observation_id merge may duplicate group columns
        gcol = "group" if "group" in freeze_lc.columns else "group_lc"
        if gcol in freeze_lc.columns:
            freeze_lc["_setup"] = freeze_lc[gcol].astype(str).str.strip()
        stats = summarize_horizons(freeze_lc)
        baseline_rows.append(row_from_summary("ALL_FREEZE_JOIN", "t0_freeze ⨝ lifecycle (EOD group)", stats))
        for setup in STUDY_SETUPS:
            sub = freeze_lc[freeze_lc["_setup"] == setup] if "_setup" in freeze_lc.columns else pd.DataFrame()
            baseline_rows.append(
                row_from_summary(setup, "t0_freeze ⨝ lifecycle (EOD group, QUARANTINE)", summarize_horizons(sub))
            )

    # observations-group join is UNSAFE; compute only as leakage contrast, labeled.
    obs_lc = pd.DataFrame()
    if not observations.empty and not lc.empty:
        obs = observations.copy()
        obs["group"] = obs["group"].astype(str).str.strip()
        obs_lc = attach_lifecycle(obs, lc, on_symbol_date=False)
        if "group" in obs_lc.columns:
            obs_lc["_setup"] = obs_lc["group"].astype(str).str.strip()
        baseline_rows.append(
            row_from_summary(
                "ALL_OBS_JOIN",
                "observations ⨝ lifecycle (UNSAFE T+1 group clock)",
                summarize_horizons(obs_lc),
            )
        )
        for setup in STUDY_SETUPS:
            sub = obs_lc[obs_lc["_setup"] == setup] if "_setup" in obs_lc.columns else pd.DataFrame()
            baseline_rows.append(
                row_from_summary(
                    setup,
                    "observations ⨝ lifecycle (UNSAFE T+1 group clock)",
                    summarize_horizons(sub),
                )
            )

    # pattern_history first-of-day ⨝ lifecycle by symbol×date
    if not fl.empty and not lc.empty:
        first_map = fl.rename(columns={"first_group": "group", "date": "date"}).copy()
        first_map["date"] = first_map["date"]
        joined = attach_lifecycle(first_map, lc, on_symbol_date=True)
        if not joined.empty:
            joined["_setup"] = joined["group"].astype(str).str.strip()
            baseline_rows.append(
                row_from_summary(
                    "ALL_PH_FIRST",
                    "pattern_history FIRST/day ⨝ lifecycle (QUARANTINE save-clock)",
                    summarize_horizons(joined),
                )
            )
            for setup in STUDY_SETUPS:
                sub = joined[joined["_setup"] == setup]
                baseline_rows.append(
                    row_from_summary(
                        setup,
                        "pattern_history FIRST/day ⨝ lifecycle (QUARANTINE save-clock)",
                        summarize_horizons(sub),
                    )
                )
        last_map = fl.rename(columns={"last_group": "group"}).copy()
        last_j = attach_lifecycle(last_map, lc, on_symbol_date=True)
        if not last_j.empty:
            last_j["_setup"] = last_j["group"].astype(str).str.strip()
            baseline_rows.append(
                row_from_summary(
                    "ALL_PH_LAST",
                    "pattern_history LAST/day ⨝ lifecycle (UNSAFE last-wins)",
                    summarize_horizons(last_j),
                )
            )
            for setup in STUDY_SETUPS:
                sub = last_j[last_j["_setup"] == setup]
                baseline_rows.append(
                    row_from_summary(
                        setup,
                        "pattern_history LAST/day ⨝ lifecycle (UNSAFE last-wins)",
                        summarize_horizons(sub),
                    )
                )

    # Elite subset
    if not elite.empty and not lc.empty:
        e = elite.copy()
        e["symbol"] = e["symbol"].astype(str).str.upper()
        e["date"] = _to_date(e["date"])
        e["conclusion"] = e["conclusion"].astype(str)
        e["group"] = e["group"].astype(str).str.strip()
        e = e.sort_values(["symbol", "date"], kind="stable").drop_duplicates(["symbol", "date"], keep="last")
        e_act = e[e["conclusion"].isin(ACTIONABLE_ELITE)]
        e_join = attach_lifecycle(e_act.rename(columns={"date": "date"}), lc, on_symbol_date=True)
        if not e_join.empty:
            e_join["_setup"] = e_join["group"].astype(str).str.strip()
            baseline_rows.append(
                row_from_summary(
                    "ALL_ELITE_ACTIONABLE",
                    "elite BUY/MUA NHỎ ⨝ lifecycle (selection bias + save clock)",
                    summarize_horizons(e_join),
                )
            )
            for setup in STUDY_SETUPS:
                sub = e_join[e_join["_setup"] == setup]
                baseline_rows.append(
                    row_from_summary(
                        setup,
                        "elite BUY/MUA NHỎ ⨝ lifecycle (selection bias + save clock)",
                        summarize_horizons(sub),
                    )
                )

    baseline_raw = pd.DataFrame(baseline_rows)
    baseline_raw.to_csv(ART / "E_setup_unconditional_baselines_raw.csv", index=False)

    # freeze-only display table (the least-wrong setup baseline for daily outcomes)
    freeze_display_src = "t0_freeze ⨝ lifecycle (EOD group, QUARANTINE)"
    freeze_rows = [r for r in baseline_rows if r["source"] == freeze_display_src]
    all_freeze = [r for r in baseline_rows if r["setup"] == "ALL_FREEZE_JOIN"]
    display_rows = all_freeze + freeze_rows
    display_df = display_outcome_table(display_rows)
    display_df.to_csv(ART / "E_setup_unconditional_baselines_freeze_eod.csv", index=False)

    # --- P×V conditional table: empty by construction ---
    pxv_rows = []
    for setup in STUDY_SETUPS:
        for cond in PXV_CONDITIONS:
            pxv_rows.append(
                {
                    "setup": setup,
                    "pxv_condition": cond,
                    "N": 0,
                    "T3_winrate": None,
                    "T3_avg": None,
                    "T5_winrate": None,
                    "T5_avg": None,
                    "T10_winrate": None,
                    "T10_avg": None,
                    "evidence_quality": "NOT TESTABLE",
                    "blocker": "canonical 5m Camera parquet absent; frozen P×V features not computable",
                }
            )
    pxv_df = pd.DataFrame(pxv_rows)
    pxv_df.to_csv(ART / "D_setup_x_pxv_x_outcome.csv", index=False)

    # --- generic interpreter baseline: also empty ---
    generic = pd.DataFrame(
        [
            {
                "interpreter_state": s,
                "N": 0,
                "T3_winrate": None,
                "T5_winrate": None,
                "T10_winrate": None,
                "evidence_quality": "NOT TESTABLE",
                "blocker": "no historical P×V ledger and no Camera bars",
            }
            for s in ["STRENGTHEN", "NEUTRAL", "CONFLICT", "WEAKEN", "UNUSABLE"]
        ]
    )
    generic.to_csv(ART / "E_generic_pxv_interpreter_baseline.csv", index=False)

    # --- market regime concentration on freeze ---
    regime_tbl = pd.DataFrame()
    if not freeze_lc.empty and "market_regime" in freeze_lc.columns:
        freeze_lc["_regime"] = freeze_lc["market_regime"].astype(str)
        freeze_lc["_setup"] = freeze_lc.get("_setup", freeze_lc.get("group"))
        regime_tbl = (
            freeze_lc.groupby(["_setup", "_regime"], dropna=False)
            .size()
            .reset_index(name="N")
            .rename(columns={"_setup": "setup", "_regime": "market_regime"})
        )
        regime_tbl.to_csv(ART / "I_freeze_setup_x_market_regime.csv", index=False)

    # --- outcomes definition audit: observation-row step vs calendar ---
    outcome_def = {
        "win_rule": "is_win = return_pct > 0 (strictly positive close-to-close)",
        "return": "(target_price / entry_price - 1) * 100",
        "MFE": "max_gain_pct = max(forward slice prices)/entry - 1, percent",
        "MAE": "max_drawdown_pct = min(forward slice prices)/entry - 1, percent (negative)",
        "horizon_index": "+n observation rows of the same symbol in observations.csv, DEFAULT_HORIZONS=(3,5,10)",
        "not": "Not independent trials; T3 ⊂ T5 ⊂ T10 on the same observation",
        "leader": "is_leader if max_gain_pct >= 5/8/12 for T3/T5/T10",
        "daily_ohlcv_panel": "absent — cannot independently recompute trading-session T+n in this workspace",
    }
    if not outcomes.empty:
        gap_notes = []
        o = outcomes.copy()
        o["entry_date"] = _to_date(o["entry_date"])
        o["target_date"] = _to_date(o["target_date"])
        o["horizon"] = _num(o["horizon"])
        o["cal_days"] = (o["target_date"] - o["entry_date"]).dt.days
        for h in (3, 5, 10):
            sub = o[o["horizon"] == h]
            if sub.empty:
                continue
            gap_notes.append(
                {
                    "horizon": h,
                    "N": int(len(sub)),
                    "median_calendar_days": float(sub["cal_days"].median()),
                    "p90_calendar_days": float(sub["cal_days"].quantile(0.9)),
                    "max_calendar_days": float(sub["cal_days"].max()),
                    "unique_symbols": int(sub["symbol"].nunique()),
                    "unique_entry_dates": int(sub["entry_date"].nunique()),
                }
            )
        pd.DataFrame(gap_notes).to_csv(ART / "A_outcome_horizon_calendar_span.csv", index=False)

    # --- group fill / missing ---
    ph_t_fill = {}
    if not ph_root.empty:
        for c in ["t1_return", "t3_return", "t5_return", "t10_return"]:
            if c in ph_root.columns:
                ph_t_fill[c] = {
                    "n_non_null": int(_num(ph_root[c]).notna().sum()),
                    "n_rows": int(len(ph_root)),
                }

    # --- elite conclusion mix ---
    elite_conc = elite["conclusion"].astype(str).value_counts().to_dict() if not elite.empty else {}

    # --- freeze vs first/last disagreement for study setups ---
    asof_disagree = {}
    if not freeze.empty and not fl.empty:
        fz = freeze.copy()
        fz["_d"] = _to_date(fz["trade_date"])
        m = fz.merge(
            fl.rename(columns={"date": "_d"}),
            on=["symbol", "_d"],
            how="inner",
            suffixes=("_fz", ""),
        )
        if not m.empty:
            asof_disagree = {
                "freeze_vs_ph_first_disagree": int((m["group"] != m["first_group"]).sum()),
                "freeze_vs_ph_last_disagree": int((m["group"] != m["last_group"]).sum()),
                "n_joined": int(len(m)),
                "freeze_vs_ph_first_rate": float((m["group"] != m["first_group"]).mean()),
                "freeze_vs_ph_last_rate": float((m["group"] != m["last_group"]).mean()),
            }

    # --- missing sessions vs union calendar ---
    date_sets = {}
    for name, df, col in [
        ("pattern_history", ph_root, "date"),
        ("evolution", evo, "date"),
        ("elite", elite, "date"),
        ("freeze", freeze, "trade_date"),
        ("observations", observations, "trade_date"),
        ("lifecycle", lc, "entry_date"),
        ("market_t0", market_t0, "trade_date"),
    ]:
        if df is None or df.empty or col not in df.columns:
            date_sets[name] = set()
            continue
        date_sets[name] = set(_to_date(df[col]).dropna().dt.strftime("%Y-%m-%d"))
    union = set().union(*date_sets.values()) if date_sets else set()
    date_cov = pd.DataFrame(
        [
            {
                "source": k,
                "n_dates": len(v),
                "missing_vs_union": len(union - v) if v else len(union),
                "date_min": min(v) if v else None,
                "date_max": max(v) if v else None,
            }
            for k, v in date_sets.items()
        ]
    )
    weekday_union = {d for d in union if pd.Timestamp(d).dayofweek < 5}
    weekend_union = union - weekday_union
    date_cov["n_weekdays"] = [
        sum(pd.Timestamp(x).dayofweek < 5 for x in date_sets[k]) for k in date_cov["source"]
    ]
    date_cov["missing_vs_weekday_union"] = [
        len(weekday_union - date_sets[k]) for k in date_cov["source"]
    ]
    date_cov.to_csv(ART / "A_session_coverage_vs_union.csv", index=False)

    # weekend contamination
    weekend_counts = {}
    weekend_dates = {}
    for name, df, col in [
        ("pattern_history", ph_root, "date"),
        ("freeze", freeze, "trade_date"),
        ("observations", observations, "trade_date"),
        ("evolution", evo, "date"),
        ("elite", elite, "date"),
    ]:
        if df is None or df.empty or col not in df.columns:
            continue
        d = _to_date(df[col]).dropna()
        weekend_counts[name] = int((d.dt.dayofweek >= 5).sum())
        weekend_dates[name] = int(d[d.dt.dayofweek >= 5].dt.strftime("%Y-%m-%d").nunique())

    # --- findings ---
    findings = [
        {
            "id": "F1",
            "claim": "Different scanner setups have materially different frozen 5m P×V signatures associated with better/worse forward outcomes.",
            "class": "NOT TESTABLE",
            "why": "Canonical 5m Camera bars are absent. No historical P×V ledger. Conditional tables are empty by construction.",
        },
        {
            "id": "F2",
            "claim": "Volume expansion means the same thing across setups.",
            "class": "NOT TESTABLE",
            "why": "5m expansion state cannot be computed without Camera bars. Daily volume_ratio must not be substituted.",
        },
        {
            "id": "F3",
            "claim": "Volume contraction has different meaning in pullback vs momentum setups.",
            "class": "NOT TESTABLE",
            "why": "Same blocker as F2. Hypotheses (PULL ĐẸP dry-up, CP MẠNH expansion) were not encoded and were not measured.",
        },
        {
            "id": "F4",
            "claim": "Transitions (CONTRACTION→EXPANSION, NEUTRAL→STRENGTHEN, WEAKEN→STRENGTHEN) are more informative than a single 5m state.",
            "class": "NOT TESTABLE",
            "why": "Sequences require ordered 5m evidence states. None available.",
        },
        {
            "id": "F5",
            "claim": "The current generic P×V interpreter loses useful setup-specific information.",
            "class": "NOT TESTABLE",
            "why": "Cannot compare generic STRENGTHEN/WEAKEN vs setup-conditional outcomes without 5m features. Architecture (Elite first → generic P×V) is a design fact, not an outcome fact.",
        },
        {
            "id": "F6",
            "claim": "t0_observation_freeze.group is an end-of-day T0 setup, not an intra-day as-of setup.",
            "class": "SUPPORTED",
            "why": "recorded_at/frozen_at clock buckets are POST_CLOSE on the trade date (VN ~15:54). Valid for daily T3/T5/T10 baseline; invalid for 5m as-of.",
        },
        {
            "id": "F7",
            "claim": "observations.csv group cannot be used as T0 as-of setup.",
            "class": "SUPPORTED",
            "why": "2141/5400 observation rows have recorded_at on a later calendar date than trade_date; remaining clocks are mixed same-day. The column is not a T0 as-of first_seen.",
        },
        {
            "id": "F8",
            "claim": "pattern_history last-wins group is look-ahead vs first snapshot of the same symbol×session.",
            "class": "SUPPORTED" if leak_ph.get("pairs_with_group_change_any_clock", 0) > 0 else "NO EVIDENCE",
            "why": f"first≠last on {leak_ph.get('pairs_with_group_change_any_clock')} of {leak_ph.get('symbol_date_pairs')} symbol×date pairs; intra-session changes {leak_ph.get('pairs_with_intra_session_group_change')}.",
        },
        {
            "id": "F9",
            "claim": "Scanner setups have different unconditional daily T3/T5/T10 base rates (control, not a P×V signal).",
            "class": "FRAGILE",
            "why": "EOD freeze ⨝ lifecycle can be tabulated per setup. Sample sizes and regime concentration may be uneven; this is a control table so P×V is not confused with a good setup. Not chronology-safe for intra-day.",
        },
        {
            "id": "F10",
            "claim": "Elite BUY subset is an unbiased sample of scanner setups.",
            "class": "CONTRADICTED",
            "why": "Elite history is filtered to actionable conclusions and last-wins per symbol×date. Live Candidate pipeline is Elite-first. Using Elite rows as if they were the scanner universe is selected-symbol bias.",
        },
        {
            "id": "F11",
            "claim": "Corporate-action-adjusted prices are available for this study.",
            "class": "NOT TESTABLE",
            "why": "No CA calendar in repo. Outcomes use observation prices as stored.",
        },
        {
            "id": "F12",
            "claim": "PULL ĐẸP / CP MẠNH / MUA BREAK historical as-of samples exist at 5m resolution.",
            "class": "NOT TESTABLE",
            "why": "5m resolution absent. Daily EOD freeze counts are not 5m as-of counts. PULL ĐẸP freeze N=5 and MUA BREAK freeze N=19 are also insufficient as daily baselines.",
        },
        {
            "id": "F13",
            "claim": "MUA BREAK and TÍCH LŨY can be reconstructed as-of from pattern_history.csv.",
            "class": "NOT TESTABLE",
            "why": "pattern_history first/last per day N=0 for both labels. Evolution and freeze contain those groups. Copying a later source onto PH timestamps would be look-ahead. Leave as NOT TESTABLE from PH.",
        },
        {
            "id": "F14",
            "claim": "Freeze ⨝ lifecycle outcomes are diversified across market regimes.",
            "class": "CONTRADICTED",
            "why": "Joined freeze rows are 100% labeled market_regime='🔴 Forecast rủi ro'. Any setup base-rate table is concentrated in one forecast-risk window.",
        },
        {
            "id": "F15",
            "claim": "Dated scanner CSVs contain only VN trading sessions.",
            "class": "CONTRADICTED",
            "why": f"Weekend rows: pattern_history={weekend_counts.get('pattern_history', 0)}, observations={weekend_counts.get('observations', 0)}, evolution={weekend_counts.get('evolution', 0)}. Freeze weekend rows=0. Union includes {len(weekend_union)} weekend dates. Quarantine weekend dates for any follow-up.",
        },
        {
            "id": "F16",
            "claim": "T3/T5/T10 are exact +n VN trading sessions.",
            "class": "FRAGILE",
            "why": "earning_learning walks +n observation rows per symbol. T3 median calendar span=4d, p90=6d, max=11d — gaps in observation coverage stretch the horizon. No independent daily OHLCV panel to rebuild session-exact T+n here.",
        },
    ]
    findings_df = pd.DataFrame(findings)
    findings_df.to_csv(ART / "findings_classification.csv", index=False)

    # --- observation unit ---
    unit = {
        "preferred_scientific_unit": "symbol × session_date × setup_asof × 5m_bar_asof",
        "preferred_status": "NOT TESTABLE in this workspace",
        "fallback_daily_unit": "symbol × trade_date × setup_label_with_chronology_class",
        "fallback_status": "PARTIAL / QUARANTINE for EOD freeze group; UNSAFE for last-wins / T+1 observation group",
        "do_not_use": "later saved group as though it were known earlier; daily volume_ratio as 5m P×V",
        "production_contracts": "unchanged",
    }

    # --- freeze group counts for report ---
    freeze_group_n = group_counts(freeze).to_dict(orient="records") if not freeze.empty else []
    ph_group_n = group_counts(ph_root).to_dict(orient="records") if not ph_root.empty else []

    meta = {
        "generated_from_git": "research/setup_intraday_pxv_forward/run_study.py",
        "camera": cam,
        "pxv_defaults_documented_not_changed": PXV_DEFAULTS,
        "outcome_definitions": outcome_def,
        "observation_unit": unit,
        "leak_pattern_history": leak_ph,
        "freeze_duplicates_observation_id": freeze_dup,
        "freeze_clock": freeze_clock,
        "asof_disagree_freeze_vs_ph": asof_disagree,
        "weekend_row_counts": weekend_counts,
        "weekend_unique_dates": weekend_dates,
        "weekday_union_n": len(weekday_union),
        "weekend_union_n": len(weekend_union),
        "pattern_history_tn_fill": ph_t_fill,
        "elite_conclusions": elite_conc,
        "union_n_dates": len(union),
    }
    (ART / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # --- REPORT.md ---
    def _src_line(row: dict) -> str:
        note = row.get("note") or ""
        return (
            f"- **{row.get('source')}**: present={row.get('present')} rows={row.get('rows')} "
            f"dates={row.get('date_min')}→{row.get('date_max')} (n_dates={row.get('n_dates')}) "
            f"symbols={row.get('n_symbols')} {note}"
        )

    inv_lines = "\n".join(_src_line(r) for r in inventory_rows)
    chrono_md = md_table(chrono_df[["source", "class", "reason"]])
    sample_md = md_table(sample_df)
    freeze_md = md_table(display_df) if not display_df.empty else "_(no freeze⨝lifecycle join)_"
    pxv_head = md_table(pxv_df.head(18))
    findings_md = md_table(findings_df)
    clock_md = md_table(clock_df.fillna("—")) if not clock_df.empty else "_(none)_"
    date_md = md_table(date_cov)
    regime_md = md_table(regime_tbl.head(40)) if not regime_tbl.empty else "_(no freeze regime join)_"

    # compact freeze N per study setup
    n_lines = []
    for setup in STUDY_SETUPS:
        n_fz = int((freeze["group"] == setup).sum()) if not freeze.empty else 0
        n_ph_first = (
            int((fl["first_group"] == setup).sum()) if not fl.empty else 0
        )
        n_ph_last = int((fl["last_group"] == setup).sum()) if not fl.empty else 0
        n_elite = 0
        if not elite.empty:
            ea = elite[elite["conclusion"].astype(str).isin(ACTIONABLE_ELITE)]
            n_elite = int((ea["group"].astype(str).str.strip() == setup).sum())
        n_lines.append(
            f"| {setup} | {n_fz} | {n_ph_first} | {n_ph_last} | {n_elite} | "
            f"{'NOT TESTABLE' if True else ''} |"
        )
    n_table = (
        "| Setup | N freeze EOD | N PH first/day | N PH last/day | N elite actionable rows | 5m P×V |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + "\n".join(n_lines)
    )

    # strongest / contradictory from freeze baselines if any
    freeze_stats_by_setup = {
        r["setup"]: r for r in freeze_rows
    }
    strongest = []
    contradictory = []
    insufficient = []
    for setup in STUDY_SETUPS:
        r = freeze_stats_by_setup.get(setup)
        if not r:
            insufficient.append(f"- **{setup}**: no freeze⨝lifecycle rows.")
            continue
        eq = r.get("evidence_quality")
        if eq in {"INSUFFICIENT", "NO_ROWS"}:
            insufficient.append(
                f"- **{setup}**: T3 N={r.get('T3_N')} T10 N={r.get('T10_N')} ({eq}). Do not interpret P×V or even setup edge."
            )
        elif eq == "PROVISIONAL":
            strongest.append(
                f"- **{setup}** (control only, FRAGILE): T3 N={r.get('T3_N')} win={fmt_pct(r.get('T3_winrate'),1)}% "
                f"avg={fmt_pct(r.get('T3_avg'))}; T10 N={r.get('T10_N')} win={fmt_pct(r.get('T10_winrate'),1)}% "
                f"avg={fmt_pct(r.get('T10_avg'))}. EOD group, not 5m P×V."
            )
        else:
            strongest.append(
                f"- **{setup}** (control only): T3 N={r.get('T3_N')} win={fmt_pct(r.get('T3_winrate'),1)}% "
                f"avg={fmt_pct(r.get('T3_avg'))}; T10 N={r.get('T10_N')} win={fmt_pct(r.get('T10_winrate'),1)}% "
                f"avg={fmt_pct(r.get('T10_avg'))}. EOD group, not 5m P×V."
            )

    # compare setups vs ALL freeze if possible
    all_s = all_freeze[0] if all_freeze else None
    if all_s:
        for setup in STUDY_SETUPS:
            r = freeze_stats_by_setup.get(setup)
            if not r or not r.get("T3_N"):
                continue
            if r.get("T3_N", 0) < N_T3_PROVISIONAL:
                continue
            # flag if winrate differs by >= 8pp or avg differs by >= 0.5 — descriptive only
            if r.get("T3_winrate") is not None and all_s.get("T3_winrate") is not None:
                dlt = r["T3_winrate"] - all_s["T3_winrate"]
                if abs(dlt) >= 8:
                    contradictory.append(
                        f"- **{setup}** T3 winrate {fmt_pct(r['T3_winrate'],1)}% vs ALL-freeze {fmt_pct(all_s['T3_winrate'],1)}% "
                        f"(Δ {dlt:+.1f} pp). This is a **setup base-rate** difference, not a P×V effect. Classification: FRAGILE control."
                    )
            if (
                r.get("T10_N", 0) >= N_T10_RELIABLE
                and r.get("T10_winrate") is not None
                and all_s.get("T10_winrate") is not None
            ):
                dlt10 = r["T10_winrate"] - all_s["T10_winrate"]
                if abs(dlt10) >= 8:
                    contradictory.append(
                        f"- **{setup}** T10 winrate {fmt_pct(r['T10_winrate'],1)}% vs ALL-freeze {fmt_pct(all_s['T10_winrate'],1)}% "
                        f"(Δ {dlt10:+.1f} pp, T10 N={r.get('T10_N')}). Setup base-rate only, one-regime window. FRAGILE control — not P×V."
                    )

    report = f"""# Setup × Intraday P×V × Forward Outcome

Research date: 2026-09-16  
Scope: **DATA, not rules.** Isolated under `research/setup_intraday_pxv_forward/`.  
Production: **not modified.** Candidate Router, Elite, Rotation, scanner GROUP_RANK, frozen P×V interpreter, Telegram, live-shadow, Streamlit, VPS, `/opt/mrbot-camera` untouched.

**Headline:** Frozen 5m P×V × setup × forward outcome is **NOT TESTABLE** in this workspace because canonical Camera 5m parquet is absent. Setup × daily T3/T5/T10 **controls** can be tabulated from EOD freeze labels (quarantined: not intra-day as-of). No BUY/SELL rules.

---

## Observation unit

| Item | Value |
| --- | --- |
| Preferred scientific unit | `{unit['preferred_scientific_unit']}` |
| Status | **{unit['preferred_status']}** |
| Fallback (P×V stripped) | `{unit['fallback_daily_unit']}` |
| Fallback status | {unit['fallback_status']} |
| Production contracts | unchanged |

Do not treat a later saved group as the group known at an earlier 5m bar.

---

## A. Data inventory

Camera resolution: `{json.dumps(cam, ensure_ascii=False)}`

{inv_lines}

Session coverage vs union of all dated sources ({len(union)} union dates):

{date_md}

Weekend row counts (contamination check): `{json.dumps(weekend_counts)}`

Timestamp clock buckets (VN, UTC-aware when `Z` present; naive CSV times localized as VN):

{clock_md}

### Outcome definitions (existing earning-learning convention)

- Horizons: **T3 / T5 / T10** = `DEFAULT_HORIZONS = (3, 5, 10)`
- Indexing: **+n observation rows of the same symbol** in `observations.csv` (approximates trading sessions when that symbol is observed every session; gaps stretch calendar span)
- `return_pct = (target_price / entry_price − 1) × 100`
- `is_win = return_pct > 0` (zero is a loss)
- Favorable excursion: `max_gain_pct` on the forward price slice
- Adverse excursion: `max_drawdown_pct` on the forward price slice (typically ≤ 0)
- `is_leader` if MFE ≥ 5 / 8 / 12 percent at T3 / T5 / T10
- T3/T5/T10 on the same `observation_id` are **nested, not independent**
- Independent daily OHLCV panel: **absent** (cannot rebuild trading-session T+n from bars here)
- `pattern_history` `t*_return` columns: fill `{json.dumps(ph_t_fill)}` — **do not** treat as known at snapshot time

Frozen P×V research defaults (**documented, not changed**): `{json.dumps(PXV_DEFAULTS)}`

Required 5m families (from `modules/intraday_pxv_v1/features.py` + `evidence.py`): interval volume EXPANSION/CONTRACTION/NORMAL vs prior-session median; price up/down; P×V CONFIRMING / WEAK / SELL_EXPANSION / FLAT; cumulative pace / TOD RVOL; evidence STRENGTHEN / NEUTRAL / CONFLICT / WEAKEN. All **NOT TESTABLE** without Camera.

---

## B. Chronology verdict

{chrono_md}

**Can historical setup/group be reconstructed as-of without look-ahead?**

- **At 5m bar time:** **NO** in this workspace (no Camera; group sources are save-clock or EOD).
- **As EOD T0 setup for daily outcomes:** **PARTIAL** via `t0_observation_freeze.group` (post-close same day). Quarantine: not intra-day.
- **From pattern_history first snapshot/day:** **PARTIAL / QUARANTINE** (clock often PRE_OPEN; save clock ≠ first_seen).
- **From last snapshot, lifecycle group, or observations.recorded_at:** **UNSAFE**.

pattern_history first vs last (look-ahead audit): `{json.dumps(leak_ph, default=str)}`

Freeze vs pattern_history group disagreement: `{json.dumps(asof_disagree)}`

---

## C. Sample-size table

Study setups are **not pooled**.

{n_table}

Full source breakdown:

{sample_md}

If N=0 for a setup in a chronology-safe 5m frame, the setup is **NOT TESTABLE** at that frame — do not reconstruct it with a later label.

Source-specific **NOT TESTABLE** (do not fill from another file):

- **MUA BREAK** and **TÍCH LŨY**: `pattern_history` first/last per day **N=0**. Those labels exist on freeze/evolution only.
- **PULL ĐẸP**: freeze EOD N=5 → daily baseline **INSUFFICIENT**; 5m **NOT TESTABLE**.
- **MUA BREAK**: freeze EOD N=19 → daily baseline **INSUFFICIENT**; 5m **NOT TESTABLE**.
- All six setups: chronology-safe 5m P×V **NOT TESTABLE** (no Camera).

---

## D. Setup × P×V × outcome

**All cells N=0, evidence quality = NOT TESTABLE.**

First 18 rows (full CSV: `artifacts/D_setup_x_pxv_x_outcome.csv`):

{pxv_head}

Generic current interpreter baseline (STRENGTHEN / NEUTRAL / CONFLICT / WEAKEN): likewise **NOT TESTABLE** (`artifacts/E_generic_pxv_interpreter_baseline.csv`).

Daily `volume_ratio20` on freeze is **not** used as a substitute 5m expansion feature.

---

## E. Baseline comparisons (setup without P×V)

These tables answer: *does the setup itself have a daily forward base rate?*  
They do **not** answer the P×V question. Use them so a good setup is not mistaken for a good 5m signal.

### E1. Unconditional setup — t0 freeze EOD group ⨝ pattern_lifecycle (QUARANTINE)

{freeze_md}

ALL-freeze join row is the control for “same setup without a P×V condition” — here the P×V condition does not exist, so this **is** the unconditional setup outcome.

### E2. Generic current P×V interpretation

**NOT TESTABLE** (no ledger, no Camera).

### E3. Elite actionable subset

Selection-biased. See raw CSV `E_setup_unconditional_baselines_raw.csv` rows sourced `elite BUY/MUA NHỎ`. Elite conclusions mix: `{json.dumps(elite_conc, ensure_ascii=False)}`

### E4. UNSAFE contrasts (leakage, not findings)

Rows sourced `observations ⨝ lifecycle` and `pattern_history LAST/day` are computed only to show how last-wins / T+1 clocks move N and rates. Do not promote them.

---

## F. Strongest observations

None of the following is a trading rule. None is a 5m P×V result.

- **Camera 5m data is missing** in every resolved `camera_data_root` candidate. Core study **NOT TESTABLE**.
- **EOD freeze group is post-close.** Using it as the setup that was known at 10:05 would leak the finished session into the label.
- **observations.group is T+1 clock.** SUPPORTED look-ahead.
- Setup daily base rates (EOD freeze, FRAGILE/control):

{chr(10).join(strongest) if strongest else "- No freeze⨝lifecycle setup rows to describe."}

---

## G. Contradictory observations

{chr(10).join(contradictory) if contradictory else "- No setup vs ALL-freeze T3 winrate gap ≥ 8 pp with N_T3 ≥ 30 on the EOD freeze join. Absence of a gap is **not** evidence that P×V is setup-invariant."}

- Elite-first Candidate path vs scanner-group identity: **CONTRADICTED** that Elite rows represent the scanner universe (F10).
- First vs last pattern_history group disagreement, if N>0, **contradicts** using a later saved group as morning as-of (F8).

---

## H. Insufficient-evidence areas

- Every 5m P×V condition and every transition sequence: **NOT TESTABLE**.
- Intra-day setup-as-of at 09:15–14:45 joined to frozen features: **NOT TESTABLE**.
{chr(10).join(insufficient) if insufficient else ""}
- Corporate actions: **NOT TESTABLE**.
- Incomplete 5m bars / session completeness vs 09:15–11:30 & 13:00–14:45 grid: **NOT TESTABLE** (no bars).
- Repeated 5m observations from the same symbol×session: would require clustered standard errors **if** Camera existed; not estimated.
- Overlapping T3/T5/T10: by design nested; do not treat the three horizons as three independent samples.
- Market-regime concentration on freeze join:

{regime_md}

---

## I. Leakage / bias findings

| Check | Result |
| --- | --- |
| Look-ahead from setup labels | Last-wins pattern_history / evolution / elite: **UNSAFE**. Freeze EOD: **quarantine** (not 5m as-of). observations.recorded_at next morning: **UNSAFE**. |
| CSV save clock vs true first_seen | Elite candidates.py documents save clock ≠ first_seen. pattern_history `time` treated the same: **PARTIAL**. |
| Incomplete 5m bars | **NOT TESTABLE** (no Camera). |
| Survivorship / selected-symbol | Watchlist ~140 names; Elite actionable is a further filter. Freeze/observations cover scanner universe more broadly than Elite. |
| Repeated symbol×session | pattern_history: `{leak_ph.get("pairs_with_multiple_snapshots")} / {leak_ph.get("symbol_date_pairs")}` pairs have >1 snapshot. Valid 5m study would cluster or pick one as-of. |
| Overlapping T3/T5/T10 | Nested on `observation_id`. |
| Corporate actions | No calendar; unadjusted observation prices. |
| Market-regime concentration | See freeze × regime table. Freeze coverage is a short 2026 window (see inventory), not a multi-year panel. |
| Freeze observation_id dups | {freeze_dup} |
| Daily volume as P×V | Explicitly **UNSAFE**; not used. |

Quarantine policy used: empty P×V cells rather than filling with daily volume or last-wins group.

---

## Finding classes (only these labels)

{findings_md}

---

## What would make the core question testable

1. Canonical 5m Camera parquet with `timestamp` ≤ as-of, incomplete bars quarantined.
2. Setup label whose **first_seen** at or before that as-of is stored (not last-wins, not T+1 `recorded_at`, not post-close freeze used as 10:05 knowledge).
3. Frozen P×V features computed with **unchanged** research defaults, plus optional transition flags on consecutive usable 5m states.
4. Forward T3/T5/T10 from existing earning-learning convention, clustered by symbol×session, with setup-unconditional and generic-interpreter controls.
5. Stop: still no BUY/SELL rules; classify SUPPORTED / FRAGILE / NO EVIDENCE / CONTRADICTED / NOT TESTABLE.

---

## Isolation record

Wrote only:

- `research/setup_intraday_pxv_forward/run_study.py`
- `research/setup_intraday_pxv_forward/README.md`
- `research/setup_intraday_pxv_forward/REPORT.md`
- `research/setup_intraday_pxv_forward/artifacts/*`

Did not change Candidate Router, Elite, Rotation, scanner, frozen P×V, live-shadow, Telegram, Streamlit, VPS, or `/opt/mrbot-camera`.
"""
    REPORT.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT}")
    print(f"Artifacts in {ART}")
    print(f"Camera available: {cam['canonical_5m_available']}")
    print(f"Freeze rows: {0 if freeze.empty else len(freeze)}")
    print(f"Findings: {findings_df['class'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
