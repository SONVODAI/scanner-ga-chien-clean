"""
Read-only adapters from existing Mr.BOT historical sources.

NEVER writes to data/earning_learning/ or production stores.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from modules.edge_research.contracts import RESEARCH_OBSERVATION_COLUMNS, ResearchObservation
from modules.edge_research.market_state import (
    RawMarketSnapshot,
    enrich_date_with_market_research,
    select_canonical_market_snapshot,
)
from modules.edge_research.outcomes import attach_outcomes_to_panel

REPO_ROOT = Path(__file__).resolve().parents[2]

EARNING_LEARNING_DIR = REPO_ROOT / "data" / "earning_learning"
PATTERN_HISTORY_PATH = REPO_ROOT / "pattern_history.csv"
BUY_ELITE_HISTORY_PATH = REPO_ROOT / "buy_elite_learning_history.csv"
RESEARCH_EXPORTS_DIR = REPO_ROOT / "research_exports"


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False, **kwargs)


def load_lifecycle(path: Optional[Path] = None) -> pd.DataFrame:
    p = path or (EARNING_LEARNING_DIR / "pattern_lifecycle.csv")
    return _read_csv(p)


def load_verified_decisions(path: Optional[Path] = None) -> pd.DataFrame:
    p = path or (EARNING_LEARNING_DIR / "verified_decisions.csv")
    return _read_csv(p)


def load_observations(path: Optional[Path] = None) -> pd.DataFrame:
    p = path or (EARNING_LEARNING_DIR / "observations.csv")
    return _read_csv(p)


def load_raw_market_snapshots(
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[RawMarketSnapshot]:
    """Load raw market snapshots from read-only repo sources."""
    frames: List[pd.DataFrame] = []

    ph = _read_csv(PATTERN_HISTORY_PATH)
    if not ph.empty and {"date", "market_real"}.issubset(ph.columns):
        sub = ph[["date", "time", "market_real", "market_forecast", "breadth_score"]].copy()
        sub = sub.dropna(subset=["date"])
        frames.append(sub)

    be = _read_csv(BUY_ELITE_HISTORY_PATH)
    if not be.empty and "market_real" in be.columns:
        sub = be[["date", "time", "market_real", "market_forecast"]].copy()
        sub["breadth_score"] = np.nan
        frames.append(sub)

    if not frames:
        return []

    raw = pd.concat(frames, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    raw = raw.dropna(subset=["date"])
    if start:
        raw = raw[raw["date"] >= start]
    if end:
        raw = raw[raw["date"] <= end]

    snapshots: List[RawMarketSnapshot] = []
    for _, row in raw.iterrows():
        mr = pd.to_numeric(row.get("market_real"), errors="coerce")
        if pd.isna(mr):
            continue
        snapshots.append(
            RawMarketSnapshot(
                date=str(row["date"]),
                time=str(row.get("time", "") or ""),
                market_real=float(mr),
                market_forecast=(
                    None
                    if pd.isna(pd.to_numeric(row.get("market_forecast"), errors="coerce"))
                    else float(pd.to_numeric(row.get("market_forecast"), errors="coerce"))
                ),
                breadth_score=(
                    None
                    if pd.isna(pd.to_numeric(row.get("breadth_score"), errors="coerce"))
                    else float(pd.to_numeric(row.get("breadth_score"), errors="coerce"))
                ),
            )
        )
    return snapshots


def build_canonical_market_series(
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    snapshots = load_raw_market_snapshots(start=start, end=end)
    if not snapshots:
        return pd.DataFrame(
            columns=["date", "market_real", "market_forecast", "breadth_score", "ambiguous"]
        )

    by_date: Dict[str, List[RawMarketSnapshot]] = {}
    for s in snapshots:
        by_date.setdefault(s.date, []).append(s)

    canonical_rows = []
    for date in sorted(by_date.keys()):
        canon = select_canonical_market_snapshot(by_date[date])
        canonical_rows.append(
            {
                "date": date,
                "time": canon.time,
                "market_real": canon.market_real,
                "market_forecast": canon.market_forecast,
                "breadth_score": canon.breadth_score,
                "ambiguous": canon.ambiguous,
                "snapshot_count": canon.snapshot_count,
                "distinct_market_real_values": "|".join(
                    str(v) for v in canon.distinct_market_real_values
                ),
            }
        )
    return pd.DataFrame(canonical_rows)


def _stock_panel_from_lifecycle(
    lifecycle: pd.DataFrame,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    if lifecycle.empty:
        return pd.DataFrame(columns=list(RESEARCH_OBSERVATION_COLUMNS))

    df = lifecycle.copy()
    date_col = "trade_date" if "trade_date" in df.columns else "date"
    df["trade_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    if start:
        df = df[df["trade_date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["trade_date"] <= pd.Timestamp(end)]

    price_col = "price" if "price" in df.columns else "close"
    out = pd.DataFrame(
        {
            "trade_date": df["trade_date"].dt.strftime("%Y-%m-%d"),
            "symbol": df["symbol"].astype(str),
            "close": pd.to_numeric(df.get(price_col), errors="coerce"),
            "rs5": pd.to_numeric(df.get("rs5"), errors="coerce"),
            "rs10": pd.to_numeric(df.get("rs10"), errors="coerce"),
            "rsi14": pd.to_numeric(df.get("rsi14"), errors="coerce"),
        }
    )
    if "rs_spread" in df.columns:
        out["rs_spread"] = pd.to_numeric(df["rs_spread"], errors="coerce")
    else:
        out["rs_spread"] = out["rs5"] - out["rs10"]
    return out.drop_duplicates(subset=["trade_date", "symbol"], keep="last")


def build_research_panel(
    start: Optional[str] = None,
    end: Optional[str] = None,
    lifecycle: Optional[pd.DataFrame] = None,
    ohlcv_by_symbol: Optional[Dict[str, pd.DataFrame]] = None,
    source: str = "pattern_lifecycle",
) -> pd.DataFrame:
    """
    Build canonical research panel (read-only sources).

    T0 features from lifecycle/observations.
    Forward labels from trading-session OHLCV when provided — never from
    lifecycle t*_return_pct (observation-row semantics).
    """
    if lifecycle is None:
        if source == "verified_decisions":
            lifecycle = load_verified_decisions()
        else:
            lifecycle = load_lifecycle()

    stock = _stock_panel_from_lifecycle(lifecycle, start=start, end=end)
    if stock.empty:
        return pd.DataFrame(columns=list(RESEARCH_OBSERVATION_COLUMNS))

    market_canonical = build_canonical_market_series(start=start, end=end)
    if market_canonical.empty:
        market_series = pd.DataFrame(
            columns=["date", "market_real", "market_forecast", "breadth_score", "ambiguous"]
        )
    else:
        market_series = market_canonical[
            ["date", "market_real", "market_forecast", "breadth_score", "ambiguous"]
        ].copy()

    state_history: Dict[str, str] = {}
    enriched_rows: List[Dict[str, Any]] = []

    for trade_date, day_df in stock.groupby("trade_date", sort=True):
        market_fields = enrich_date_with_market_research(
            str(trade_date),
            market_series,
            day_df,
            state_history,
        )
        canon_row = market_canonical[market_canonical["date"] == trade_date]
        snap_time = str(canon_row.iloc[0]["time"]) if not canon_row.empty else ""
        snap_amb = bool(canon_row.iloc[0]["ambiguous"]) if not canon_row.empty else True
        snap_count = int(canon_row.iloc[0]["snapshot_count"]) if not canon_row.empty else 0

        for _, srow in day_df.iterrows():
            row = {
                "trade_date": trade_date,
                "symbol": srow["symbol"],
                "close": srow["close"],
                "rs5": srow["rs5"],
                "rs10": srow["rs10"],
                "rsi14": srow["rsi14"],
                "rs_spread": srow["rs_spread"],
                "market_real": market_fields.get("mr_t0"),
                "market_forecast": (
                    None
                    if canon_row.empty
                    else canon_row.iloc[0].get("market_forecast")
                ),
                "breadth_score": market_fields.get("breadth_t0"),
                "market_snapshot_time": snap_time,
                "market_snapshot_ambiguous": snap_amb,
                "market_snapshot_count": snap_count,
                **market_fields,
            }
            enriched_rows.append(row)

    panel = pd.DataFrame(enriched_rows)

    if ohlcv_by_symbol:
        panel = attach_outcomes_to_panel(panel, ohlcv_by_symbol)
    else:
        panel["t3_return"] = np.nan
        panel["t5_return"] = np.nan
        panel["t10_return"] = np.nan
        panel["outcome_source"] = "unavailable"
        panel["outcome_missing_reason"] = "ohlcv_not_provided"

    for col in RESEARCH_OBSERVATION_COLUMNS:
        if col not in panel.columns:
            panel[col] = np.nan
    return panel[list(RESEARCH_OBSERVATION_COLUMNS)]


def panel_to_observations(panel: pd.DataFrame) -> List[ResearchObservation]:
    return [ResearchObservation.from_dict(row) for row in panel.to_dict(orient="records")]


def file_digest(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def earning_learning_digests() -> Dict[str, Optional[str]]:
    names = [
        "pattern_lifecycle.csv",
        "verified_decisions.csv",
        "observations.csv",
        "t0_observation_freeze.csv",
        "decision_archive.csv",
        "pattern_knowledge.csv",
        "continuation_knowledge.csv",
    ]
    return {n: file_digest(EARNING_LEARNING_DIR / n) for n in names}
