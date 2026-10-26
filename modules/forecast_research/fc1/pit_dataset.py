"""
FC-1 PIT feature dataset builder.

Sources (read-only): observations, EMS, forecast_t0_daily, MDT0, t0_observation_freeze.
Never uses lifecycle outcome columns as features.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.forecast_research.fc1.contract import (
    COMPLETENESS_COMPLETE,
    COMPLETENESS_PARTIAL,
    EXPECTED_UNIVERSE_SIZE,
    FC1_PIT_SCHEMA_VERSION,
    FC1_VERSION,
    FEATURE_REGISTRY,
    FORBIDDEN_FEATURE_EXACT,
    FORBIDDEN_FEATURE_PREFIXES,
    GROUP_SHARE_MAP,
    GROUPS,
    PIT_SAFE_FEATURES,
    PROVENANCE_PIT_SAFE,
    PROVENANCE_SAFE_RECONSTRUCTABLE,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _norm_date(s: Any) -> str:
    return str(s)[:10]


def assert_no_forbidden_feature_columns(columns: Sequence[str]) -> None:
    bad: List[str] = []
    exact = {x.lower() for x in FORBIDDEN_FEATURE_EXACT}
    prefixes = tuple(x.lower() for x in FORBIDDEN_FEATURE_PREFIXES)
    for col in columns:
        cl = str(col).lower()
        if cl in exact or any(cl.startswith(p) for p in prefixes):
            bad.append(str(col))
    if bad:
        raise ValueError(f"Forbidden outcome/lifecycle feature columns: {sorted(set(bad))}")


def _share(mask: pd.Series) -> float:
    if mask is None or len(mask) == 0:
        return float("nan")
    return float(pd.Series(mask).astype(bool).mean())


def _board_features(board: pd.DataFrame) -> Dict[str, float]:
    """Cross-sectional features from a same-day stock board (EMS or observations)."""
    out: Dict[str, float] = {}
    n = len(board)
    if n == 0:
        return out
    if "group" in board.columns:
        for g, key in GROUP_SHARE_MAP.items():
            out[key] = float((board["group"] == g).mean())
    else:
        for key in GROUP_SHARE_MAP.values():
            out[key] = float("nan")

    rsi = pd.to_numeric(board.get("rsi14"), errors="coerce")
    if rsi is not None and rsi.notna().any():
        out["rsi40_share"] = float((rsi > 40).mean())
        out["rsi50_share"] = float((rsi > 50).mean())
        out["rsi60_share"] = float((rsi > 60).mean())
        out["med_rsi14"] = float(rsi.median())
    else:
        out.update(
            {
                "rsi40_share": float("nan"),
                "rsi50_share": float("nan"),
                "rsi60_share": float("nan"),
                "med_rsi14": float("nan"),
            }
        )

    if "obv_status" in board.columns:
        out["obv_green_share"] = _share(board["obv_status"].astype(str) == "🟢")
    else:
        out["obv_green_share"] = float("nan")

    slope = pd.to_numeric(board.get("ema9_ma20_slope"), errors="coerce")
    out["slope_pos_share"] = float((slope > 0).mean()) if slope is not None and len(slope) else float("nan")

    rs5 = pd.to_numeric(board.get("rs5"), errors="coerce")
    rs10 = pd.to_numeric(board.get("rs10"), errors="coerce")
    out["mean_rs5"] = float(rs5.mean()) if rs5 is not None and rs5.notna().any() else float("nan")
    out["mean_rs10"] = float(rs10.mean()) if rs10 is not None and rs10.notna().any() else float("nan")
    out["pos_rs5_share"] = float((rs5 > 0).mean()) if rs5 is not None and rs5.notna().any() else float("nan")
    out["pos_rs10_share"] = float((rs10 > 0).mean()) if rs10 is not None and rs10.notna().any() else float("nan")
    out["rs5_dispersion"] = float(rs5.std()) if rs5 is not None and rs5.notna().sum() > 1 else float("nan")

    nb20 = pd.to_numeric(board.get("near_bottom_20_pct"), errors="coerce")
    nb60 = pd.to_numeric(board.get("near_bottom_60_pct"), errors="coerce")
    # EMS uses dist_high20_pct; observations may use dist_high20
    dh = board.get("dist_high20_pct")
    if dh is None:
        dh = board.get("dist_high20")
    dh = pd.to_numeric(dh, errors="coerce") if dh is not None else None
    out["near_low20_share"] = float((nb20 <= 3).mean()) if nb20 is not None and nb20.notna().any() else float("nan")
    out["near_low60_share"] = float((nb60 <= 5).mean()) if nb60 is not None and nb60.notna().any() else float("nan")
    out["near_high20_share"] = (
        float((dh >= -3).mean()) if dh is not None and dh.notna().any() else float("nan")
    )

    if rs5 is not None and rs5.notna().any():
        top = rs5.nlargest(min(10, int(rs5.notna().sum())))
        total_pos = float(rs5.clip(lower=0).sum())
        out["lead_conc_top10"] = float(top.clip(lower=0).sum() / total_pos) if total_pos > 0 else float("nan")
    else:
        out["lead_conc_top10"] = float("nan")
    return out


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _board_for_date(
    *,
    trade_date: str,
    ems: pd.DataFrame,
    obs: pd.DataFrame,
    freeze: pd.DataFrame,
) -> Tuple[pd.DataFrame, str]:
    """Prefer EMS, then freeze, then observations. Same-day boards only."""
    td = _norm_date(trade_date)
    if not ems.empty and "snapshot_date" in ems.columns:
        b = ems[ems["snapshot_date"].astype(str).str[:10] == td]
        if len(b) > 0:
            return b.copy(), "ems"
    if not freeze.empty and "trade_date" in freeze.columns:
        b = freeze[freeze["trade_date"].astype(str).str[:10] == td]
        if len(b) > 0:
            return b.copy(), "t0_observation_freeze"
    if not obs.empty and "trade_date" in obs.columns:
        b = obs[obs["trade_date"].astype(str).str[:10] == td]
        if len(b) > 0:
            return b.copy(), "observations"
    return pd.DataFrame(), "none"


def _market_fields(
    trade_date: str,
    *,
    board: pd.DataFrame,
    mdt0: pd.DataFrame,
    ft0: pd.DataFrame,
) -> Dict[str, Any]:
    td = _norm_date(trade_date)
    out: Dict[str, Any] = {
        "market_real": float("nan"),
        "market_live": float("nan"),
        "market_forecast": float("nan"),
        "breadth_score": float("nan"),
        "vnindex_daily_return_pct": float("nan"),
        "market_regime": None,
        "market_source": None,
    }
    # Prefer MDT0 AFTER_CLOSE / last row for date
    if not mdt0.empty and "trade_date" in mdt0.columns:
        hit = mdt0[mdt0["trade_date"].astype(str).str[:10] == td]
        if not hit.empty:
            row = hit.iloc[-1]
            out["market_real"] = pd.to_numeric(row.get("market_real"), errors="coerce")
            out["market_live"] = pd.to_numeric(row.get("market_live"), errors="coerce")
            out["market_forecast"] = pd.to_numeric(row.get("market_forecast"), errors="coerce")
            out["breadth_score"] = pd.to_numeric(row.get("breadth_score"), errors="coerce")
            out["vnindex_daily_return_pct"] = pd.to_numeric(
                row.get("vnindex_daily_return_pct"), errors="coerce"
            )
            out["market_regime"] = row.get("market_regime")
            out["market_source"] = "mdt0"
            return out
    # forecast_t0 frozen row
    if not ft0.empty and "trade_date" in ft0.columns:
        hit = ft0[ft0["trade_date"].astype(str).str[:10] == td]
        if not hit.empty:
            row = hit.iloc[-1]
            out["market_real"] = pd.to_numeric(row.get("market_real"), errors="coerce")
            out["market_live"] = pd.to_numeric(row.get("market_live"), errors="coerce")
            out["market_forecast"] = pd.to_numeric(row.get("market_forecast"), errors="coerce")
            out["breadth_score"] = pd.to_numeric(row.get("breadth_score_md"), errors="coerce")
            out["vnindex_daily_return_pct"] = pd.to_numeric(
                row.get("vnindex_daily_return_pct"), errors="coerce"
            )
            out["market_source"] = "forecast_t0_daily"
            return out
    # Same-day board persisted market columns (EMS/obs)
    if not board.empty:
        for src_col, dst in (
            ("market_real", "market_real"),
            ("market_live", "market_live"),
            ("market_forecast", "market_forecast"),
            ("market_breadth_score", "breadth_score"),
            ("breadth", "breadth_score"),
            ("market_regime", "market_regime"),
        ):
            if src_col in board.columns:
                val = board[src_col].iloc[0]
                if dst == "market_regime":
                    out[dst] = val
                else:
                    out[dst] = pd.to_numeric(val, errors="coerce")
        out["market_source"] = "board_same_day"
    return out


def _completeness(row: Dict[str, Any], universe_count: int) -> str:
    core = ["market_real", "market_live", "market_forecast", "rsi50_share", "obv_green_share"]
    present = sum(1 for c in core if c in row and pd.notna(row.get(c)))
    if universe_count >= EXPECTED_UNIVERSE_SIZE and present == len(core):
        return COMPLETENESS_COMPLETE
    if universe_count >= EXPECTED_UNIVERSE_SIZE and present >= 3:
        return COMPLETENESS_PARTIAL
    # Board composition alone still usable as PARTIAL for opportunity research
    if universe_count >= EXPECTED_UNIVERSE_SIZE and pd.notna(row.get("rsi50_share")):
        return COMPLETENESS_PARTIAL
    return COMPLETENESS_PARTIAL if universe_count > 0 else "INSUFFICIENT"


def build_pit_dataset(
    *,
    repo_root: Optional[Path] = None,
    ems_path: Optional[Path] = None,
    obs_path: Optional[Path] = None,
    freeze_path: Optional[Path] = None,
    mdt0_path: Optional[Path] = None,
    ft0_path: Optional[Path] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    One row per trade_date with PIT_SAFE features + metadata.

    Lag features use only prior rows (strictly earlier dates).
    """
    root = repo_root or REPO_ROOT
    ems_path = ems_path or (root / "data" / "earning_money_snapshots.csv")
    obs_path = obs_path or (root / "data" / "earning_learning" / "observations.csv")
    freeze_path = freeze_path or (root / "data" / "earning_learning" / "t0_observation_freeze.csv")
    mdt0_path = mdt0_path or (root / "data" / "earning_learning" / "market_daily_t0.csv")
    ft0_path = ft0_path or (root / "data" / "forecast_research" / "forecast_t0_daily.csv")

    ems = _load_csv(ems_path)
    obs = _load_csv(obs_path)
    freeze = _load_csv(freeze_path)
    mdt0 = _load_csv(mdt0_path)
    ft0 = _load_csv(ft0_path)

    dates: set[str] = set()
    if not ems.empty and "snapshot_date" in ems.columns:
        dates |= set(ems["snapshot_date"].astype(str).str[:10])
    if not obs.empty and "trade_date" in obs.columns:
        dates |= set(obs["trade_date"].astype(str).str[:10])
    if not freeze.empty and "trade_date" in freeze.columns:
        dates |= set(freeze["trade_date"].astype(str).str[:10])
    if not mdt0.empty and "trade_date" in mdt0.columns:
        dates |= set(mdt0["trade_date"].astype(str).str[:10])
    if not ft0.empty and "trade_date" in ft0.columns:
        dates |= set(ft0["trade_date"].astype(str).str[:10])

    rows: List[Dict[str, Any]] = []
    for td in sorted(d for d in dates if d and d != "nan"):
        board, board_source = _board_for_date(trade_date=td, ems=ems, obs=obs, freeze=freeze)
        if board.empty:
            continue
        feats = _board_features(board)
        mkt = _market_fields(td, board=board, mdt0=mdt0, ft0=ft0)
        row: Dict[str, Any] = {
            "trade_date": td,
            "fc1_version": FC1_VERSION,
            "pit_schema_version": FC1_PIT_SCHEMA_VERSION,
            "universe_count": int(len(board)),
            "expected_universe_size": EXPECTED_UNIVERSE_SIZE,
            "board_source": board_source,
            "market_source": mkt.get("market_source"),
        }
        for k in (
            "market_real",
            "market_live",
            "market_forecast",
            "breadth_score",
            "vnindex_daily_return_pct",
            "market_regime",
        ):
            row[k] = mkt.get(k)
        row.update(feats)
        row["completeness_status"] = _completeness(row, int(len(board)))
        # Missingness flags for core PIT fields
        for f in PIT_SAFE_FEATURES:
            if f.endswith("_lag1"):
                continue
            row[f"missing__{f}"] = int(f not in row or pd.isna(row.get(f)))
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        meta = {
            "fc1_version": FC1_VERSION,
            "feature_registry": FEATURE_REGISTRY,
            "n_dates": 0,
        }
        return df, meta

    df = df.sort_values("trade_date").reset_index(drop=True)
    # Strict past-only lags
    for src, lag_name in (
        ("market_real", "market_real_lag1"),
        ("market_forecast", "market_forecast_lag1"),
        ("rsi50_share", "rsi50_share_lag1"),
        ("obv_green_share", "obv_green_share_lag1"),
    ):
        df[lag_name] = pd.to_numeric(df[src], errors="coerce").shift(1)
        df[f"missing__{lag_name}"] = df[lag_name].isna().astype(int)

    feature_cols = [c for c in df.columns if c in FEATURE_REGISTRY]
    assert_no_forbidden_feature_columns(feature_cols)

    # Provenance columns (never mix classes silently)
    for feat, prov in FEATURE_REGISTRY.items():
        if feat in df.columns:
            df[f"provenance__{feat}"] = prov

    meta = {
        "fc1_version": FC1_VERSION,
        "pit_schema_version": FC1_PIT_SCHEMA_VERSION,
        "feature_registry": dict(FEATURE_REGISTRY),
        "pit_safe_features": list(PIT_SAFE_FEATURES),
        "safe_reconstructable_features": [
            k for k, v in FEATURE_REGISTRY.items() if v == PROVENANCE_SAFE_RECONSTRUCTABLE
        ],
        "n_dates": int(len(df)),
        "date_min": str(df["trade_date"].min()),
        "date_max": str(df["trade_date"].max()),
        "n_complete": int((df["completeness_status"] == COMPLETENESS_COMPLETE).sum()),
        "n_partial": int((df["completeness_status"] == COMPLETENESS_PARTIAL).sum()),
        "sources": {
            "ems": str(ems_path),
            "observations": str(obs_path),
            "freeze": str(freeze_path),
            "mdt0": str(mdt0_path),
            "forecast_t0": str(ft0_path),
        },
    }
    return df, meta


def fit_past_only_zscore(
    train_frame: pd.DataFrame,
    feature_cols: Sequence[str],
) -> Dict[str, Tuple[float, float]]:
    """Fit mean/std on train only — never on future rows."""
    stats: Dict[str, Tuple[float, float]] = {}
    for c in feature_cols:
        s = pd.to_numeric(train_frame[c], errors="coerce") if c in train_frame.columns else pd.Series(dtype=float)
        mu = float(s.mean()) if s.notna().any() else 0.0
        sd = float(s.std(ddof=0)) if s.notna().sum() > 1 else 1.0
        if sd == 0 or np.isnan(sd):
            sd = 1.0
        stats[c] = (mu, sd)
    return stats


def apply_zscore(row: pd.Series, stats: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for c, (mu, sd) in stats.items():
        v = pd.to_numeric(row.get(c), errors="coerce")
        out[c] = float("nan") if pd.isna(v) else float((float(v) - mu) / sd)
    return out


def feature_matrix_hash(df: pd.DataFrame, feature_cols: Sequence[str]) -> str:
    payload = df.loc[:, [c for c in feature_cols if c in df.columns]].to_csv(index=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
