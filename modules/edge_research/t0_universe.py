"""
PIT-safe current T0 universe for Future Recognition (Phase B).

Canonical source: earning-learning first-write-wins `t0_observation_freeze.csv`.
Never uses outcome-gated `pattern_lifecycle.csv` or a mutable intraday scan frame
as a silent fallback.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.adapters import EARNING_LEARNING_DIR, file_digest

T0_FREEZE_FILENAME = "t0_observation_freeze.csv"
CANONICAL_T0_FREEZE_PATH = EARNING_LEARNING_DIR / T0_FREEZE_FILENAME
REQUIRED_IDENTITY_COLUMNS: Tuple[str, ...] = ("trade_date", "symbol")
DISCOVERY_FEATURES: Tuple[str, ...] = ("rs5", "rs10", "rsi14", "rs_spread")


class T0UniverseError(ValueError):
    """Canonical T0 universe is missing or scientifically unsafe to scan."""


@dataclass
class T0Universe:
    trade_date: str
    frame: pd.DataFrame
    universe_count: int
    universe_hash: str
    pit_artifact: str
    pit_artifact_hash: Optional[str]
    symbols: List[str] = field(default_factory=list)
    feature_coverage: Dict[str, int] = field(default_factory=dict)
    source_status: str = "OK"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "universe_count": self.universe_count,
            "universe_hash": self.universe_hash,
            "pit_artifact": self.pit_artifact,
            "pit_artifact_hash": self.pit_artifact_hash,
            "source_status": self.source_status,
            "feature_coverage": self.feature_coverage,
            "symbol_count": len(self.symbols),
        }


def canonical_t0_freeze_path(explicit: Optional[Path] = None) -> Path:
    return Path(explicit) if explicit is not None else CANONICAL_T0_FREEZE_PATH


def _normalize_trade_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return str(value or "").strip()[:10]
    return str(ts.date())


def universe_hash_from_frame(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty:
        return hashlib.sha256(b"").hexdigest()[:16]
    work = frame.copy()
    work["symbol"] = work["symbol"].astype(str).str.upper().str.strip()
    if "observation_id" in work.columns:
        payload = work[["symbol", "observation_id"]].astype(str).sort_values("symbol")
    else:
        payload = work[["symbol"]].astype(str).sort_values("symbol")
    return hashlib.sha256(payload.to_csv(index=False).encode("utf-8")).hexdigest()[:16]


def _ensure_rs_spread(frame: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct rs_spread with the Discovery/earning-learning definition: rs5 - rs10."""
    out = frame.copy()
    if "rs5" in out.columns and "rs10" in out.columns:
        rs5 = pd.to_numeric(out["rs5"], errors="coerce")
        rs10 = pd.to_numeric(out["rs10"], errors="coerce")
        calculated = rs5 - rs10
        if "rs_spread" not in out.columns:
            out["rs_spread"] = calculated
        else:
            existing = pd.to_numeric(out["rs_spread"], errors="coerce")
            out["rs_spread"] = existing.where(existing.notna(), calculated)
    return out


def load_t0_freeze(path: Optional[Path] = None) -> pd.DataFrame:
    freeze_path = canonical_t0_freeze_path(path)
    if not freeze_path.exists() or freeze_path.stat().st_size == 0:
        raise T0UniverseError("canonical T0 freeze missing or empty")
    df = pd.read_csv(freeze_path, encoding="utf-8-sig", low_memory=False)
    if df.empty:
        raise T0UniverseError("canonical T0 freeze is empty")
    return df


def latest_freeze_trade_date(freeze: pd.DataFrame) -> Optional[str]:
    if freeze is None or freeze.empty or "trade_date" not in freeze.columns:
        return None
    dates = pd.to_datetime(freeze["trade_date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return str(dates.max().date())


def load_session_universe(
    trade_date: str,
    *,
    freeze_df: Optional[pd.DataFrame] = None,
    freeze_path: Optional[Path] = None,
    required_features: Sequence[str] = DISCOVERY_FEATURES,
) -> T0Universe:
    """
    Load the PIT-safe T0 universe for one session from the canonical freeze.

    Does not fall back to pattern_lifecycle or a live scan frame.
    """
    artifact = str(canonical_t0_freeze_path(freeze_path))
    artifact_hash = None
    if freeze_df is None:
        path = canonical_t0_freeze_path(freeze_path)
        freeze_df = load_t0_freeze(path)
        artifact_hash = None
        try:
            from modules.edge_research.adapters import file_digest

            artifact_hash = file_digest(path)
        except Exception:
            artifact_hash = None
    else:
        artifact = "injected_freeze_df"

    if freeze_df.empty:
        raise T0UniverseError("canonical T0 freeze is empty")
    for col in REQUIRED_IDENTITY_COLUMNS:
        if col not in freeze_df.columns:
            raise T0UniverseError(f"T0 freeze missing required column {col}")

    work = freeze_df.copy()
    work["_session"] = work["trade_date"].map(_normalize_trade_date)
    target = _normalize_trade_date(trade_date)
    session = work[work["_session"] == target].copy()
    if session.empty:
        raise T0UniverseError(f"T0 freeze has no rows for session {target}")

    session["symbol"] = session["symbol"].astype(str).str.upper().str.strip()
    session = session[session["symbol"] != ""].drop_duplicates(subset=["symbol"], keep="first")
    session = _ensure_rs_spread(session)
    session["trade_date"] = target

    coverage = {}
    for feat in required_features:
        if feat not in session.columns:
            coverage[feat] = 0
        else:
            coverage[feat] = int(pd.to_numeric(session[feat], errors="coerce").notna().sum())

    symbols = sorted(session["symbol"].unique().tolist())
    return T0Universe(
        trade_date=target,
        frame=session.reset_index(drop=True),
        universe_count=int(len(session)),
        universe_hash=universe_hash_from_frame(session),
        pit_artifact=artifact,
        pit_artifact_hash=artifact_hash,
        symbols=symbols,
        feature_coverage=coverage,
        source_status="OK",
    )


def systemic_features_missing(
    universe: T0Universe,
    required_features: Sequence[str],
) -> List[str]:
    missing: List[str] = []
    n = max(universe.universe_count, 1)
    for feat in required_features:
        covered = int(universe.feature_coverage.get(feat, 0))
        if covered == 0:
            missing.append(str(feat))
        elif covered < min(3, n) and covered / n < 0.05:
            missing.append(str(feat))
    return missing
