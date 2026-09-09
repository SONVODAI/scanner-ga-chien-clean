"""Read-only Camera archive + latest-quarantine overlay.

Never writes parquet, quarantine, or manifests.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from modules.intraday_memory.schema import CANONICAL_COLUMNS
from modules.intraday_memory.timezone_policy import VN_TZ

OHLCV = ("open", "high", "low", "close", "volume")
SRC_CANONICAL = "canonical"
SRC_REVISED = "revised_quarantine"


def list_session_dates(camera_root: Path) -> list[date]:
    dates: list[date] = []
    canon = camera_root / "canonical"
    if not canon.exists():
        return dates
    for parquet in sorted(canon.glob("**/session_date=*/bars.parquet")):
        token = parquet.parent.name.split("=", 1)[-1]
        dates.append(date.fromisoformat(token))
    return dates


def _session_dir(camera_root: Path, session: date) -> Path:
    return (
        camera_root
        / "canonical"
        / f"year={session.year}"
        / f"month={session.month:02d}"
        / f"session_date={session.isoformat()}"
    )


def load_canonical_session(camera_root: Path, session: date) -> pd.DataFrame:
    path = _session_dir(camera_root, session) / "bars.parquet"
    if not path.exists():
        return pd.DataFrame(columns=list(CANONICAL_COLUMNS))
    df = pd.read_parquet(path)
    return _normalize_bars(df)


def load_latest_quarantine(camera_root: Path, session: date) -> pd.DataFrame:
    qdir = _session_dir(camera_root, session) / "quarantine"
    if not qdir.exists():
        return pd.DataFrame()
    files = sorted(qdir.glob("*.parquet"))
    if not files:
        return pd.DataFrame()
    frames = [pd.read_parquet(f) for f in files]
    q = pd.concat(frames, ignore_index=True)
    q = _normalize_bars(q)
    if q.empty:
        return q
    q = q.sort_values(["symbol", "timestamp"])
    return q.drop_duplicates(["symbol", "timestamp"], keep="last")


def _normalize_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=list(CANONICAL_COLUMNS))
    out = df.copy()
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=False)
        if getattr(out["timestamp"].dt, "tz", None) is None:
            out["timestamp"] = out["timestamp"].dt.tz_localize(VN_TZ)
        else:
            out["timestamp"] = out["timestamp"].dt.tz_convert(VN_TZ)
    if "symbol" in out.columns:
        out["symbol"] = out["symbol"].astype(str).str.upper()
    for col in OHLCV:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    keep = [c for c in CANONICAL_COLUMNS if c in out.columns]
    extra = [c for c in out.columns if c not in keep]
    return out[keep + extra]


def overlay_session(camera_root: Path, session: date) -> pd.DataFrame:
    """Canonical bars with latest quarantine OHLCV replacing matching keys.

    Adds:
      bar_source: canonical | revised_quarantine
      overlay_applied: bool (session-level, copied onto every row)
    """
    canon = load_canonical_session(camera_root, session)
    revised = load_latest_quarantine(camera_root, session)
    if canon.empty and revised.empty:
        return pd.DataFrame()

    if canon.empty:
        out = revised.copy()
        out["bar_source"] = SRC_REVISED
        out["overlay_applied"] = True
        return out.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    canon = canon.copy()
    canon["bar_source"] = SRC_CANONICAL
    if revised.empty:
        canon["overlay_applied"] = False
        return canon.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    key = ["symbol", "timestamp"]
    rev = revised[key + [c for c in OHLCV if c in revised.columns]].copy()
    rev = rev.rename(columns={c: f"_rev_{c}" for c in OHLCV if c in rev.columns})
    merged = canon.merge(rev, on=key, how="left")
    replaced = 0
    for col in OHLCV:
        rcol = f"_rev_{col}"
        if rcol not in merged.columns:
            continue
        mask = merged[rcol].notna()
        replaced += int(mask.sum())
        merged.loc[mask, col] = merged.loc[mask, rcol]
    merged["bar_source"] = SRC_CANONICAL
    if "_rev_close" in merged.columns:
        merged.loc[merged["_rev_close"].notna(), "bar_source"] = SRC_REVISED
    drop = [c for c in merged.columns if c.startswith("_rev_")]
    merged = merged.drop(columns=drop)
    # Quarantine-only keys (new timestamps) — append, do not invent into identity.
    extra_keys = revised.merge(canon[key], on=key, how="left", indicator=True)
    extra = extra_keys[extra_keys["_merge"] == "left_only"].drop(columns="_merge")
    if not extra.empty:
        extra = extra.copy()
        extra["bar_source"] = SRC_REVISED
        merged = pd.concat([merged, extra], ignore_index=True)
    merged["overlay_applied"] = bool(replaced > 0 or not extra.empty)
    return merged.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def symbol_session_bars(overlay: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if overlay is None or overlay.empty:
        return pd.DataFrame()
    out = overlay[overlay["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    return out.sort_values("timestamp").reset_index(drop=True)


def asof_slice(bars: pd.DataFrame, asof: datetime) -> pd.DataFrame:
    if bars is None or bars.empty:
        return pd.DataFrame()
    ts = pd.Timestamp(asof)
    if ts.tzinfo is None:
        ts = ts.tz_localize(VN_TZ)
    else:
        ts = ts.tz_convert(VN_TZ)
    return bars[bars["timestamp"] <= ts].copy().reset_index(drop=True)
