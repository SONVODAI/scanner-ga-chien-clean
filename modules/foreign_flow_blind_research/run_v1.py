"""
Foreign Flow Blind Research V1 — research-only, no production mutation.

Neutral search over PIT foreign-flow features → session forward outcomes.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "foreign_flow_history"
CANONICAL_DIR = DATA_ROOT / "canonical" / "by_symbol"
FREEZE_PATH = DATA_ROOT / "manifests" / "research_freeze.json"
ELIG_PATH = ROOT / "diagnostics" / "foreign_flow_historical_audit" / "ems142_hsx_eligibility.json"
OUT_DIR = ROOT / "diagnostics" / "foreign_flow_blind_research_v1"

SCHEMA_VERSION = "ff_hsx_symbol_daily_v1"
FEATURE_GRAMMAR_VERSION = "ff_blind_v1_grammar"
OUTCOME_VERSION = "session_close_to_close_v1"
RESEARCH_SEED = 42  # used only if any shuffle needed; primary design is chronological

HORIZONS = (1, 3, 5, 10)

# Chronological partitions by calendar date (trading sessions within each era)
SPLIT = {
    "discovery": ("2009-01-02", "2016-12-31"),
    "validation": ("2017-01-01", "2021-12-31"),
    "holdout": ("2022-01-01", "2026-12-31"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT))
            .decode()
            .strip()
        )
    except Exception:
        return "UNKNOWN"


# ---------------------------------------------------------------------------
# 1. Freeze verification
# ---------------------------------------------------------------------------

def verify_and_record_freeze() -> Dict[str, Any]:
    if not FREEZE_PATH.exists():
        raise RuntimeError("STOP_RESEARCH_DATA_NOT_FROZEN: missing research_freeze.json")
    fr = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    hashes = fr.get("hashes") or {}
    if not hashes:
        raise RuntimeError("STOP_RESEARCH_DATA_NOT_FROZEN: empty hashes")

    mismatches = []
    missing_files = []
    for sym, expected in hashes.items():
        p = CANONICAL_DIR / f"{sym}.csv"
        if not p.exists():
            missing_files.append(sym)
            continue
        actual = sha256_file(p)
        if actual != expected:
            mismatches.append({"symbol": sym, "expected": expected, "actual": actual})

    files = sorted(CANONICAL_DIR.glob("*.csv"))
    row_count = 0
    firsts, lasts, ns = [], [], []
    buy_null = close_zero = 0
    for p in files:
        df = pd.read_csv(p, usecols=["trade_date", "foreign_buy_value", "close_price"])
        row_count += len(df)
        firsts.append(str(df["trade_date"].min()))
        lasts.append(str(df["trade_date"].max()))
        ns.append(len(df))
        buy_null += int(df["foreign_buy_value"].isna().sum())
        close_zero += int((pd.to_numeric(df["close_price"], errors="coerce").fillna(0) <= 0).sum())

    elig = json.loads(ELIG_PATH.read_text(encoding="utf-8")) if ELIG_PATH.exists() else {}
    manifest = {
        "research_run_id": f"ff_blind_v1_{utc_now().replace(':','').replace('-','')}",
        "verified_at": utc_now(),
        "input_freeze_path": str(FREEZE_PATH.relative_to(ROOT)),
        "dataset_version": fr.get("dataset_version"),
        "schema_version": fr.get("schema_version"),
        "source": fr.get("source"),
        "grain": fr.get("grain"),
        "symbol_count_freeze": fr.get("symbol_count"),
        "row_count_freeze": fr.get("row_count"),
        "symbol_count_disk": len(files),
        "row_count_disk": row_count,
        "first_trade_date": min(firsts) if firsts else None,
        "last_trade_date": max(lasts) if lasts else None,
        "coverage_sessions_min": int(min(ns)) if ns else None,
        "coverage_sessions_median": float(np.median(ns)) if ns else None,
        "coverage_sessions_max": int(max(ns)) if ns else None,
        "buy_null_count": buy_null,
        "close_nonpositive_count": close_zero,
        "hash_mismatches": mismatches,
        "missing_files": missing_files,
        "exclusions": fr.get("exclusions"),
        "known_biases": fr.get("known_biases"),
        "eligibility_asof": elig.get("trade_date"),
        "cohort_label": "current_EMS_HOSE_overlap_117_not_historical_membership",
        "integrity_ok": len(mismatches) == 0 and len(missing_files) == 0
        and row_count == fr.get("row_count")
        and len(files) == fr.get("symbol_count"),
        "input_dataset_hash": hashlib.sha256(
            json.dumps(hashes, sort_keys=True).encode()
        ).hexdigest(),
        "code_commit": git_commit(),
    }
    if not manifest["integrity_ok"]:
        raise RuntimeError(
            "STOP_RESEARCH_DATA_NOT_FROZEN: "
            + json.dumps(
                {
                    "mismatches": len(mismatches),
                    "missing": missing_files,
                    "row_disk": row_count,
                    "row_freeze": fr.get("row_count"),
                }
            )
        )
    return manifest


# ---------------------------------------------------------------------------
# 2. Load panel + outcomes
# ---------------------------------------------------------------------------

def load_canonical_panel() -> pd.DataFrame:
    frames = []
    for p in sorted(CANONICAL_DIR.glob("*.csv")):
        df = pd.read_csv(
            p,
            usecols=[
                "trade_date",
                "symbol",
                "foreign_buy_value",
                "foreign_sell_value",
                "foreign_net_value",
                "foreign_buy_volume",
                "foreign_sell_volume",
                "open_price",
                "high_price",
                "low_price",
                "close_price",
            ],
        )
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    panel["trade_date"] = panel["trade_date"].astype(str).str[:10]
    panel["symbol"] = panel["symbol"].astype(str).str.upper()
    for c in [
        "foreign_buy_value",
        "foreign_sell_value",
        "foreign_net_value",
        "foreign_buy_volume",
        "foreign_sell_volume",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
    ]:
        panel[c] = pd.to_numeric(panel[c], errors="coerce")
    panel = panel.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    return panel


def add_outcomes(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Session-based close-to-close forward returns.
    T0 close is state only; T1 = next session close / T0 close - 1.
    Invalid if any involved close <= 0.
    """
    out = panel.copy()
    g = out.groupby("symbol", sort=False)
    close = out["close_price"]
    valid_close = close > 0
    out["valid_t0_price"] = valid_close

    for h in HORIZONS:
        fwd = g["close_price"].shift(-h)
        ret = fwd / close - 1.0
        ok = valid_close & (fwd > 0)
        # also require intervening path for MFE/MAE at h
        out[f"ret_t{h}"] = np.where(ok, ret, np.nan)
        out[f"win_t{h}"] = np.where(ok, (ret > 0).astype(float), np.nan)

    # MFE/MAE over next 10 sessions using highs/lows vs T0 close (path)
    # Only when T0 close > 0 and next 10 closes exist with positive prices
    highs = []
    lows = []
    for k in range(1, 11):
        highs.append(g["high_price"].shift(-k))
        lows.append(g["low_price"].shift(-k))
    max_high = pd.concat(highs, axis=1).max(axis=1)
    min_low = pd.concat(lows, axis=1).min(axis=1)
    path_ok = valid_close & (max_high > 0) & (min_low > 0) & out["ret_t10"].notna()
    out["mfe_t10"] = np.where(path_ok, max_high / close - 1.0, np.nan)
    out["mae_t10"] = np.where(path_ok, min_low / close - 1.0, np.nan)

    # Extreme overnight jump flag (possible CA / bad print) — exclude from research rows
    prev = g["close_price"].shift(1)
    ratio = close / prev
    out["extreme_jump_flag"] = (
        valid_close & (prev > 0) & ((ratio > 1.8) | (ratio < 0.55))
    )
    # Also flag if T0 close nonpositive
    out["research_eligible"] = valid_close & (~out["extreme_jump_flag"].fillna(False))
    return out


# ---------------------------------------------------------------------------
# 3. Features (bounded grammar)
# ---------------------------------------------------------------------------

def add_features(
    panel: pd.DataFrame,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """All features use only past+present T0 information (PIT)."""
    df = panel.copy()
    g = df.groupby("symbol", sort=False)
    net = df["foreign_net_value"]
    buy = df["foreign_buy_value"]
    sell = df["foreign_sell_value"]

    # Raw sign
    df["net_sign"] = np.sign(net).replace(0.0, 0.0)
    df["net_pos"] = (net > 0).astype(int)
    df["net_neg"] = (net < 0).astype(int)
    df["net_zero"] = (net == 0).astype(int)

    # Price direction at T0 (same-session state; not an outcome)
    prev_close = g["close_price"].shift(1)
    df["px_ret_1"] = np.where(
        (df["close_price"] > 0) & (prev_close > 0),
        df["close_price"] / prev_close - 1.0,
        np.nan,
    )
    df["px_sign"] = np.sign(df["px_ret_1"]).fillna(0.0)

    # Persistence: consecutive same-sign nets (including today)
    def _streak(s: pd.Series) -> pd.Series:
        signs = np.sign(s.fillna(0.0).to_numpy())
        out = np.zeros(len(signs), dtype=int)
        for i, v in enumerate(signs):
            if i == 0 or v == 0 or v != signs[i - 1]:
                out[i] = int(v)
            else:
                # accumulate magnitude of streak with sign
                prev = out[i - 1]
                out[i] = prev + int(np.sign(prev) or v)
        return pd.Series(out, index=s.index)

    df["net_streak"] = g["foreign_net_value"].transform(_streak)
    df["streak_pos_ge3"] = (df["net_streak"] >= 3).astype(int)
    df["streak_neg_le_m3"] = (df["net_streak"] <= -3).astype(int)
    df["streak_pos_ge5"] = (df["net_streak"] >= 5).astype(int)
    df["streak_neg_le_m5"] = (df["net_streak"] <= -5).astype(int)

    # Rolling cumulative (past including T0)
    for w in (5, 20):
        df[f"net_sum_{w}"] = g["foreign_net_value"].transform(
            lambda s, w=w: s.rolling(w, min_periods=w).sum()
        )
        df[f"net_sum_{w}_pos"] = (df[f"net_sum_{w}"] > 0).astype(float)
        df[f"net_sum_{w}_neg"] = (df[f"net_sum_{w}"] < 0).astype(float)

    # Rolling z-score (PIT: uses trailing window including T0)
    def rolling_z(s: pd.Series, w: int = 60) -> pd.Series:
        m = s.rolling(w, min_periods=w).mean()
        sd = s.rolling(w, min_periods=w).std(ddof=0)
        return (s - m) / sd.replace(0, np.nan)

    df["net_z_60"] = g["foreign_net_value"].transform(lambda s: rolling_z(s, 60))
    df["abs_net_z_60"] = df["net_z_60"].abs()
    df["abn_net_pos_z15"] = (df["net_z_60"] > 1.5).astype(float)
    df["abn_net_neg_z15"] = (df["net_z_60"] < -1.5).astype(float)
    df["abn_net_pos_z20"] = (df["net_z_60"] > 2.0).astype(float)
    df["abn_net_neg_z20"] = (df["net_z_60"] < -2.0).astype(float)
    df["abn_abs_z20"] = (df["abs_net_z_60"] > 2.0).astype(float)

    # Rolling percentile of net (252) — pandas rolling.rank is PIT within window
    df["net_pct_252"] = g["foreign_net_value"].transform(
        lambda s: s.rolling(252, min_periods=252).rank(pct=True)
    )
    df["net_hi_pct90"] = (df["net_pct_252"] >= 0.90).astype(float)
    df["net_lo_pct10"] = (df["net_pct_252"] <= 0.10).astype(float)

    # Transitions
    prev_sign = g["net_sign"].shift(1)
    df["trans_pos_to_neg"] = ((prev_sign > 0) & (df["net_sign"] < 0)).astype(int)
    df["trans_neg_to_pos"] = ((prev_sign < 0) & (df["net_sign"] > 0)).astype(int)

    # Price × flow interaction (all T0 state)
    df["agree_pos"] = ((df["net_sign"] > 0) & (df["px_sign"] > 0)).astype(int)
    df["agree_neg"] = ((df["net_sign"] < 0) & (df["px_sign"] < 0)).astype(int)
    df["diverge_buy_down"] = ((df["net_sign"] > 0) & (df["px_sign"] < 0)).astype(int)
    df["diverge_sell_up"] = ((df["net_sign"] < 0) & (df["px_sign"] > 0)).astype(int)

    # Abnormal + price interaction
    df["abn_buy_z15_px_down"] = (
        (df["abn_net_pos_z15"] == 1) & (df["px_sign"] < 0)
    ).astype(float)
    df["abn_sell_z15_px_up"] = (
        (df["abn_net_neg_z15"] == 1) & (df["px_sign"] > 0)
    ).astype(float)
    df["abn_buy_z15_px_up"] = (
        (df["abn_net_pos_z15"] == 1) & (df["px_sign"] > 0)
    ).astype(float)
    df["abn_sell_z15_px_down"] = (
        (df["abn_net_neg_z15"] == 1) & (df["px_sign"] < 0)
    ).astype(float)

    grammar = [
        {"name": "net_pos", "family": "sign", "lookback": 0, "pit": True, "def": "foreign_net_value > 0"},
        {"name": "net_neg", "family": "sign", "lookback": 0, "pit": True, "def": "foreign_net_value < 0"},
        {"name": "net_zero", "family": "sign", "lookback": 0, "pit": True, "def": "foreign_net_value == 0"},
        {"name": "streak_pos_ge3", "family": "persistence", "lookback": "variable", "pit": True, "def": ">=3 consecutive positive net sessions"},
        {"name": "streak_neg_le_m3", "family": "persistence", "lookback": "variable", "pit": True, "def": ">=3 consecutive negative net sessions"},
        {"name": "streak_pos_ge5", "family": "persistence", "lookback": "variable", "pit": True, "def": ">=5 consecutive positive net"},
        {"name": "streak_neg_le_m5", "family": "persistence", "lookback": "variable", "pit": True, "def": ">=5 consecutive negative net"},
        {"name": "net_sum_5_pos", "family": "persistence", "lookback": 5, "pit": True, "def": "sum net 5 sessions > 0"},
        {"name": "net_sum_5_neg", "family": "persistence", "lookback": 5, "pit": True, "def": "sum net 5 sessions < 0"},
        {"name": "net_sum_20_pos", "family": "persistence", "lookback": 20, "pit": True, "def": "sum net 20 sessions > 0"},
        {"name": "net_sum_20_neg", "family": "persistence", "lookback": 20, "pit": True, "def": "sum net 20 sessions < 0"},
        {"name": "abn_net_pos_z15", "family": "magnitude", "lookback": 60, "pit": True, "def": "net_z_60 > 1.5"},
        {"name": "abn_net_neg_z15", "family": "magnitude", "lookback": 60, "pit": True, "def": "net_z_60 < -1.5"},
        {"name": "abn_net_pos_z20", "family": "magnitude", "lookback": 60, "pit": True, "def": "net_z_60 > 2.0"},
        {"name": "abn_net_neg_z20", "family": "magnitude", "lookback": 60, "pit": True, "def": "net_z_60 < -2.0"},
        {"name": "abn_abs_z20", "family": "magnitude", "lookback": 60, "pit": True, "def": "|net_z_60| > 2.0"},
        {"name": "net_hi_pct90", "family": "magnitude", "lookback": 252, "pit": True, "def": "net percentile >= 90 over 252"},
        {"name": "net_lo_pct10", "family": "magnitude", "lookback": 252, "pit": True, "def": "net percentile <= 10 over 252"},
        {"name": "trans_pos_to_neg", "family": "transition", "lookback": 1, "pit": True, "def": "prior net+ then T0 net-"},
        {"name": "trans_neg_to_pos", "family": "transition", "lookback": 1, "pit": True, "def": "prior net- then T0 net+"},
        {"name": "agree_pos", "family": "interaction", "lookback": 1, "pit": True, "def": "net+ and px+ (vs prior close)"},
        {"name": "agree_neg", "family": "interaction", "lookback": 1, "pit": True, "def": "net- and px-"},
        {"name": "diverge_buy_down", "family": "interaction", "lookback": 1, "pit": True, "def": "net+ but px-"},
        {"name": "diverge_sell_up", "family": "interaction", "lookback": 1, "pit": True, "def": "net- but px+"},
        {"name": "abn_buy_z15_px_down", "family": "interaction", "lookback": 60, "pit": True, "def": "abnormal buy z>1.5 with px down"},
        {"name": "abn_sell_z15_px_up", "family": "interaction", "lookback": 60, "pit": True, "def": "abnormal sell z<-1.5 with px up"},
        {"name": "abn_buy_z15_px_up", "family": "interaction", "lookback": 60, "pit": True, "def": "abnormal buy with px up"},
        {"name": "abn_sell_z15_px_down", "family": "interaction", "lookback": 60, "pit": True, "def": "abnormal sell with px down"},
    ]
    for gitem in grammar:
        gitem["availability"] = "HOSE_symbol_daily_canonical"
        gitem["complexity"] = 1
        col = gitem["name"]
        if col in df.columns:
            gitem["missingness"] = float(df.loc[df["research_eligible"], col].isna().mean())
        else:
            gitem["missingness"] = 1.0
    # Deferred families
    deferred = [
        {
            "name": "liquidity_normalized_flow",
            "family": "liquidity",
            "status": "DEFERRED",
            "reason": "No PIT-safe historical ADV/turnover denominator in canonical store",
        },
        {
            "name": "market_fc_regime_interaction",
            "family": "market_context",
            "status": "DEFERRED_LONG_HISTORY",
            "reason": "Market FC/REAL history much shorter than foreign-flow history; kept separate",
        },
    ]
    return df, grammar, deferred


# ---------------------------------------------------------------------------
# 4. Stats helpers
# ---------------------------------------------------------------------------

def subset_split(df: pd.DataFrame, split: str) -> pd.DataFrame:
    a, b = SPLIT[split]
    return df[(df["trade_date"] >= a) & (df["trade_date"] <= b)]


def condition_mask(df: pd.DataFrame, feature: str) -> pd.Series:
    s = df[feature]
    return (s == 1) | (s == 1.0)


def describe_outcome(df: pd.DataFrame, horizon: int) -> Dict[str, Any]:
    col = f"ret_t{horizon}"
    wcol = f"win_t{horizon}"
    s = df[col].dropna()
    if s.empty:
        return {
            "n": 0,
            "n_symbols": 0,
            "n_dates": 0,
            "mean_ret": None,
            "median_ret": None,
            "win_rate": None,
            "std_ret": None,
            "mfe_t10_mean": None,
            "mae_t10_mean": None,
        }
    sub = df.loc[s.index]
    return {
        "n": int(len(s)),
        "n_symbols": int(sub["symbol"].nunique()),
        "n_dates": int(sub["trade_date"].nunique()),
        "mean_ret": float(s.mean()),
        "median_ret": float(s.median()),
        "win_rate": float(sub[wcol].dropna().mean()) if wcol in sub else None,
        "std_ret": float(s.std(ddof=0)),
        "mfe_t10_mean": float(sub["mfe_t10"].dropna().mean()) if "mfe_t10" in sub else None,
        "mae_t10_mean": float(sub["mae_t10"].dropna().mean()) if "mae_t10" in sub else None,
    }


def concentration(df: pd.DataFrame, horizon: int) -> Dict[str, Any]:
    col = f"ret_t{horizon}"
    sub = df.dropna(subset=[col])
    if sub.empty:
        return {"top1_share_abs_sumret": None, "top5_share": None, "top10_share": None}
    # contribution by symbol to total absolute sum of returns (proxy for influence)
    by = sub.groupby("symbol")[col].sum()
    abs_sum = by.abs().sum()
    if abs_sum == 0:
        return {"top1_share_abs_sumret": 0.0, "top5_share": 0.0, "top10_share": 0.0, "top_symbols": []}
    ranked = by.abs().sort_values(ascending=False)
    def share(k):
        return float(ranked.head(k).sum() / abs_sum)
    return {
        "top1_share_abs_sumret": share(1),
        "top5_share": share(5),
        "top10_share": share(10),
        "top_symbols": ranked.head(10).index.tolist(),
        "n_symbols": int(sub["symbol"].nunique()),
    }


# ---------------------------------------------------------------------------
# 5. Search + validation
# ---------------------------------------------------------------------------

BINARY_FEATURES = [
    "net_pos",
    "net_neg",
    "net_zero",
    "streak_pos_ge3",
    "streak_neg_le_m3",
    "streak_pos_ge5",
    "streak_neg_le_m5",
    "net_sum_5_pos",
    "net_sum_5_neg",
    "net_sum_20_pos",
    "net_sum_20_neg",
    "abn_net_pos_z15",
    "abn_net_neg_z15",
    "abn_net_pos_z20",
    "abn_net_neg_z20",
    "abn_abs_z20",
    "net_hi_pct90",
    "net_lo_pct10",
    "trans_pos_to_neg",
    "trans_neg_to_pos",
    "agree_pos",
    "agree_neg",
    "diverge_buy_down",
    "diverge_sell_up",
    "abn_buy_z15_px_down",
    "abn_sell_z15_px_up",
    "abn_buy_z15_px_up",
    "abn_sell_z15_px_down",
]


def evaluate_condition(
    df: pd.DataFrame,
    feature: str,
    horizon: int,
    baseline: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    mask = condition_mask(df, feature) & df["research_eligible"]
    sub = df.loc[mask]
    stats = describe_outcome(sub, horizon)
    if stats["n"] < 200:
        return None
    if stats["n_symbols"] < 15:
        return None
    if stats["n_dates"] < 50:
        return None
    base_mean = baseline.get("mean_ret")
    incr = None if base_mean is None or stats["mean_ret"] is None else stats["mean_ret"] - base_mean
    base_wr = baseline.get("win_rate")
    incr_wr = None if base_wr is None or stats["win_rate"] is None else stats["win_rate"] - base_wr
    conc = concentration(sub, horizon)
    return {
        "feature": feature,
        "horizon": horizon,
        **stats,
        "baseline_mean_ret": base_mean,
        "incremental_mean_ret": incr,
        "baseline_win_rate": base_wr,
        "incremental_win_rate": incr_wr,
        **{f"conc_{k}": v for k, v in conc.items() if k != "top_symbols"},
        "top_symbols": conc.get("top_symbols"),
    }


def classify_candidate(
    disc: Dict[str, Any],
    val: Optional[Dict[str, Any]],
    hold: Optional[Dict[str, Any]],
    falsification: Dict[str, Any],
) -> str:
    """
    Conservative classification. No EDGE ACTIVE.
    """
    if disc is None or disc.get("n", 0) < 200:
        return "REJECT"

    incr_d = disc.get("incremental_mean_ret")
    if incr_d is None or abs(incr_d) < 0.0005:  # <5 bps
        return "DESCRIPTIVE_ONLY"

    # sign consistency across periods
    def sgn(x):
        if x is None:
            return 0
        return 1 if x > 0 else (-1 if x < 0 else 0)

    if val is None or val.get("n", 0) < 100:
        return "FRAGILE"
    if sgn(incr_d) != sgn(val.get("incremental_mean_ret")):
        return "FRAGILE"
    if abs(val.get("incremental_mean_ret") or 0) < 0.0003:
        return "FRAGILE"

    # concentration
    if (disc.get("conc_top5_share") or 0) > 0.55:
        return "FRAGILE"

    if hold is None or hold.get("n", 0) < 80:
        return "FRAGILE"
    if sgn(incr_d) != sgn(hold.get("incremental_mean_ret")):
        return "FRAGILE"
    if abs(hold.get("incremental_mean_ret") or 0) < 0.0002:
        return "FRAGILE"

    # falsification deaths
    if falsification.get("killed"):
        return "REJECT" if falsification.get("kill_severity") == "hard" else "FRAGILE"

    # robust bar: all three periods same sign, holdout incr >= 3bps, symbols>=25 in holdout,
    # top5 concentration < 0.4, survived leave-top-symbols
    if (
        abs(hold.get("incremental_mean_ret") or 0) >= 0.0005
        and (hold.get("n_symbols") or 0) >= 25
        and (disc.get("conc_top5_share") or 1) < 0.40
        and falsification.get("survived_leave_top5")
        and falsification.get("survived_alt_horizon")
    ):
        return "ROBUST_CANDIDATE"

    # research candidate: consistent sign discovery+validation+holdout, moderate effect
    if abs(incr_d) >= 0.0008 and abs(val.get("incremental_mean_ret") or 0) >= 0.0004:
        return "RESEARCH_CANDIDATE"

    return "FRAGILE"


def falsify(
    panel: pd.DataFrame,
    feature: str,
    horizon: int,
    disc_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """Attempt to kill the candidate."""
    base_all = describe_outcome(panel.loc[panel["research_eligible"]], horizon)
    disc = subset_split(panel, "discovery")
    val = subset_split(panel, "validation")
    hold = subset_split(panel, "holdout")

    results: Dict[str, Any] = {"killed": False, "kill_severity": None, "tests": []}

    # 1) leave-top-5 symbols from discovery contribution
    mask = condition_mask(disc, feature) & disc["research_eligible"]
    sub = disc.loc[mask].dropna(subset=[f"ret_t{horizon}"])
    top5 = sub.groupby("symbol")[f"ret_t{horizon}"].sum().abs().sort_values(ascending=False).head(5).index.tolist()
    sub2 = sub[~sub["symbol"].isin(top5)]
    st2 = describe_outcome(sub2, horizon)
    base_d = describe_outcome(disc.loc[disc["research_eligible"]], horizon)
    incr2 = None if st2["mean_ret"] is None else st2["mean_ret"] - (base_d["mean_ret"] or 0)
    results["survived_leave_top5"] = incr2 is not None and np.sign(incr2) == np.sign(
        disc_stats.get("incremental_mean_ret") or 0
    ) and abs(incr2) >= 0.5 * abs(disc_stats.get("incremental_mean_ret") or 0)
    results["tests"].append({"test": "leave_top5_symbols", "removed": top5, "incr": incr2, "survived": results["survived_leave_top5"]})

    # 2) alternative neighboring horizons
    alt_ok = 0
    for h in HORIZONS:
        if h == horizon:
            continue
        ev = evaluate_condition(disc, feature, h, base_d)
        if ev and np.sign(ev.get("incremental_mean_ret") or 0) == np.sign(disc_stats.get("incremental_mean_ret") or 0):
            alt_ok += 1
    results["survived_alt_horizon"] = alt_ok >= 1
    results["tests"].append({"test": "neighbor_horizons_same_sign", "n_agree": alt_ok, "survived": results["survived_alt_horizon"]})

    # 3) reverse proposition (opposite feature if exists)
    reverse_map = {
        "net_pos": "net_neg",
        "net_neg": "net_pos",
        "streak_pos_ge3": "streak_neg_le_m3",
        "streak_neg_le_m3": "streak_pos_ge3",
        "abn_net_pos_z15": "abn_net_neg_z15",
        "abn_net_neg_z15": "abn_net_pos_z15",
        "abn_net_pos_z20": "abn_net_neg_z20",
        "abn_net_neg_z20": "abn_net_pos_z20",
        "net_hi_pct90": "net_lo_pct10",
        "net_lo_pct10": "net_hi_pct90",
        "trans_pos_to_neg": "trans_neg_to_pos",
        "trans_neg_to_pos": "trans_pos_to_neg",
        "agree_pos": "agree_neg",
        "agree_neg": "agree_pos",
        "diverge_buy_down": "diverge_sell_up",
        "diverge_sell_up": "diverge_buy_down",
        "net_sum_5_pos": "net_sum_5_neg",
        "net_sum_5_neg": "net_sum_5_pos",
        "net_sum_20_pos": "net_sum_20_neg",
        "net_sum_20_neg": "net_sum_20_pos",
    }
    rev = reverse_map.get(feature)
    if rev and rev in disc.columns:
        ev_rev = evaluate_condition(disc, rev, horizon, base_d)
        # If reverse has SAME signed incremental effect, original sign story is weak
        same = (
            ev_rev
            and ev_rev.get("incremental_mean_ret") is not None
            and np.sign(ev_rev["incremental_mean_ret"]) == np.sign(disc_stats.get("incremental_mean_ret") or 0)
            and abs(ev_rev["incremental_mean_ret"]) >= abs(disc_stats.get("incremental_mean_ret") or 0) * 0.5
        )
        results["tests"].append({"test": "reverse_feature", "reverse": rev, "same_direction_effect": same, "rev_incr": None if not ev_rev else ev_rev.get("incremental_mean_ret")})
        if same:
            results["killed"] = True
            results["kill_severity"] = "soft"
            results["kill_reason"] = "reverse_feature_same_direction"

    # 4) remove strongest year
    if not sub.empty:
        sub = sub.copy()
        sub["year"] = sub["trade_date"].str[:4]
        top_year = sub.groupby("year")[f"ret_t{horizon}"].sum().abs().sort_values(ascending=False).index[0]
        sub_y = sub[sub["year"] != top_year]
        st_y = describe_outcome(sub_y, horizon)
        incr_y = None if st_y["mean_ret"] is None else st_y["mean_ret"] - (base_d["mean_ret"] or 0)
        survived_y = incr_y is not None and np.sign(incr_y) == np.sign(disc_stats.get("incremental_mean_ret") or 0)
        results["tests"].append({"test": "drop_strongest_year", "year": top_year, "incr": incr_y, "survived": survived_y})
        if not survived_y:
            results["killed"] = True
            results["kill_severity"] = "soft"
            results["kill_reason"] = f"depends_on_year_{top_year}"

    # 5) simpler parent: net_pos/net_neg if feature is more complex
    parent = None
    if feature.startswith("abn_net_pos") or feature.startswith("streak_pos") or feature.endswith("_pos") or "buy" in feature:
        parent = "net_pos"
    elif feature.startswith("abn_net_neg") or feature.startswith("streak_neg") or feature.endswith("_neg") or "sell" in feature:
        parent = "net_neg"
    if parent and parent != feature and parent in disc.columns:
        ev_p = evaluate_condition(disc, parent, horizon, base_d)
        # If parent explains most of the incremental effect
        if ev_p and disc_stats.get("incremental_mean_ret") and ev_p.get("incremental_mean_ret"):
            ratio = abs(ev_p["incremental_mean_ret"]) / max(abs(disc_stats["incremental_mean_ret"]), 1e-12)
            results["tests"].append({"test": "parent_condition", "parent": parent, "parent_incr": ev_p["incremental_mean_ret"], "ratio_parent_over_child": ratio})
            if ratio >= 0.85 and np.sign(ev_p["incremental_mean_ret"]) == np.sign(disc_stats["incremental_mean_ret"]):
                results["killed"] = True
                results["kill_severity"] = "soft"
                results["kill_reason"] = "simpler_parent_explains"

    return results


def run_research() -> Dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- freeze ---
    freeze_manifest = verify_and_record_freeze()
    (OUT_DIR / "DATA_FREEZE_MANIFEST.json").write_text(
        json.dumps(freeze_manifest, indent=2) + "\n", encoding="utf-8"
    )

    # --- protocol docs written by caller / here ---
    panel = load_canonical_panel()
    panel = add_outcomes(panel)
    panel, grammar, deferred = add_features(panel)

    # Persist research panel is heavy; write parquet-like csv sample stats only
    eligible = panel.loc[panel["research_eligible"]].copy()

    # Baseline report
    baseline_rows = []
    for split in ("discovery", "validation", "holdout", "all"):
        part = eligible if split == "all" else subset_split(eligible, split)
        for h in HORIZONS:
            st = describe_outcome(part, h)
            baseline_rows.append({"split": split, "horizon": h, "condition": "UNCONDITIONAL", **st})
            # broad states
            for feat in ("net_pos", "net_neg", "net_zero"):
                if feat not in part.columns:
                    continue
                sub = part.loc[condition_mask(part, feat)]
                st2 = describe_outcome(sub, h)
                base = st
                incr = None if st2["mean_ret"] is None or base["mean_ret"] is None else st2["mean_ret"] - base["mean_ret"]
                baseline_rows.append(
                    {
                        "split": split,
                        "horizon": h,
                        "condition": feat,
                        **st2,
                        "incremental_mean_ret": incr,
                    }
                )
    base_df = pd.DataFrame(baseline_rows)
    base_df.to_csv(OUT_DIR / "BASELINE_REPORT.csv", index=False)

    # Search accounting
    hypotheses = []
    cand_id = 0
    registry = []
    temporal_rows = []
    concentration_rows = []
    falsification_docs = []

    disc = subset_split(eligible, "discovery")
    val = subset_split(eligible, "validation")
    hold = subset_split(eligible, "holdout")

    n_examined = 0
    for feat in BINARY_FEATURES:
        if feat not in eligible.columns:
            continue
        for h in HORIZONS:
            n_examined += 1
            base_d = describe_outcome(disc, h)
            ev_d = evaluate_condition(disc, feat, h, base_d)
            hypotheses.append({"feature": feat, "horizon": h, "stage": "discovery_screen", "kept": ev_d is not None})
            if ev_d is None:
                continue
            # require minimal incremental signal in discovery to promote
            if abs(ev_d.get("incremental_mean_ret") or 0) < 0.0005:
                hypotheses[-1]["kept"] = False
                hypotheses[-1]["reason"] = "incr_too_small"
                continue

            base_v = describe_outcome(val, h)
            base_h = describe_outcome(hold, h)
            ev_v = evaluate_condition(val, feat, h, base_v)
            ev_ho = evaluate_condition(hold, feat, h, base_h)
            fals = falsify(eligible, feat, h, ev_d)
            label = classify_candidate(ev_d, ev_v, ev_ho, fals)
            cand_id += 1
            cid = f"FFB1_{cand_id:04d}"
            family = next((g["family"] for g in grammar if g["name"] == feat), "unknown")
            entry = {
                "candidate_id": cid,
                "feature": feat,
                "family": family,
                "horizon": h,
                "classification": label,
                "discovery": ev_d,
                "validation": ev_v,
                "holdout": ev_ho,
                "falsification": fals,
            }
            registry.append(entry)
            for split_name, ev in (("discovery", ev_d), ("validation", ev_v), ("holdout", ev_ho)):
                if not ev:
                    continue
                temporal_rows.append(
                    {
                        "candidate_id": cid,
                        "feature": feat,
                        "horizon": h,
                        "split": split_name,
                        "mean_ret": ev.get("mean_ret"),
                        "incremental_mean_ret": ev.get("incremental_mean_ret"),
                        "win_rate": ev.get("win_rate"),
                        "n": ev.get("n"),
                        "n_symbols": ev.get("n_symbols"),
                        "n_dates": ev.get("n_dates"),
                        "classification": label,
                    }
                )
                concentration_rows.append(
                    {
                        "candidate_id": cid,
                        "feature": feat,
                        "horizon": h,
                        "split": split_name,
                        "top1_share": ev.get("conc_top1_share_abs_sumret"),
                        "top5_share": ev.get("conc_top5_share"),
                        "top10_share": ev.get("conc_top10_share"),
                        "n_symbols": ev.get("n_symbols"),
                        "top_symbols": ",".join(ev.get("top_symbols") or []),
                    }
                )
            falsification_docs.append({"candidate_id": cid, "feature": feat, "horizon": h, **fals})

    search_accounting = {
        "feature_grammar_version": FEATURE_GRAMMAR_VERSION,
        "n_binary_features": len(BINARY_FEATURES),
        "n_horizons": len(HORIZONS),
        "n_hypotheses_examined": n_examined,
        "n_promoted_from_discovery": len(registry),
        "adaptive_search_depth": "single_pass_predeclared_grammar_no_posthoc_expansion",
        "search_budget": "bounded_grammar_x_horizons",
        "random_seed": RESEARCH_SEED,
        "notes": [
            "No opportunistic feature invention after seeing outcomes.",
            "Primary evidence is chronological discovery/validation/holdout.",
            "Multiple-testing burden: treat discovery screen as exploratory; require validation+holdout sign consistency.",
        ],
        "hypotheses_trace_sample": hypotheses[:50],
        "n_hypotheses_trace": len(hypotheses),
    }

    # Write artifacts
    (OUT_DIR / "FEATURE_GRAMMAR.json").write_text(
        json.dumps({"version": FEATURE_GRAMMAR_VERSION, "features": grammar, "deferred": deferred}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "SEARCH_ACCOUNTING.json").write_text(json.dumps(search_accounting, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "CANDIDATE_REGISTRY.json").write_text(json.dumps(registry, indent=2, default=str) + "\n", encoding="utf-8")
    pd.DataFrame(temporal_rows).to_csv(OUT_DIR / "TEMPORAL_VALIDATION.csv", index=False)
    pd.DataFrame(concentration_rows).to_csv(OUT_DIR / "CONCENTRATION_TESTS.csv", index=False)

    # Summaries for reports
    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for r in registry:
        by_class.setdefault(r["classification"], []).append(r)

    def rank_key(r):
        ho = r.get("holdout") or {}
        va = r.get("validation") or {}
        # prefer holdout absolute incremental, then validation
        return (
            abs(ho.get("incremental_mean_ret") or 0),
            abs(va.get("incremental_mean_ret") or 0),
            abs((r.get("discovery") or {}).get("incremental_mean_ret") or 0),
        )

    # strongest positive / negative by holdout incremental among non-REJECT
    nontrivial = [r for r in registry if r["classification"] not in ("REJECT",)]
    pos = sorted(
        [r for r in nontrivial if ((r.get("holdout") or {}).get("incremental_mean_ret") or 0) > 0],
        key=rank_key,
        reverse=True,
    )
    neg = sorted(
        [r for r in nontrivial if ((r.get("holdout") or {}).get("incremental_mean_ret") or 0) < 0],
        key=rank_key,
        reverse=True,
    )
    # surprising nulls: intuitive sign features with near-zero incr in holdout
    nulls = []
    for feat, h in (("net_pos", 5), ("net_neg", 5), ("net_pos", 3), ("net_neg", 3), ("net_pos", 10), ("net_neg", 10)):
        base_h = describe_outcome(hold, h)
        ev = evaluate_condition(hold, feat, h, base_h) if feat in hold.columns else None
        if ev:
            nulls.append({"feature": feat, "horizon": h, **ev})

    # Determine primary verdict
    if by_class.get("ROBUST_CANDIDATE"):
        verdict = "FOREIGN_FLOW_ROBUST_CANDIDATE_FOUND"
        confirm = "YES"
    elif by_class.get("RESEARCH_CANDIDATE"):
        verdict = "FOREIGN_FLOW_RESEARCH_CANDIDATE_FOUND"
        confirm = "YES"
    elif by_class.get("FRAGILE") or by_class.get("DESCRIPTIVE_ONLY"):
        verdict = "FOREIGN_FLOW_SIGNAL_FRAGILE"
        confirm = "NO"
    else:
        verdict = "FOREIGN_FLOW_NO_ROBUST_SIGNAL"
        confirm = "NO"

    # Family strength: which family has most consistent holdout signal
    family_scores: Dict[str, List[float]] = {}
    for r in registry:
        ho = (r.get("holdout") or {}).get("incremental_mean_ret")
        if ho is None:
            continue
        if r["classification"] in ("REJECT", "DESCRIPTIVE_ONLY"):
            continue
        family_scores.setdefault(r["family"], []).append(ho)
    family_summary = {
        fam: {
            "n": len(vs),
            "mean_abs_holdout_incr": float(np.mean(np.abs(vs))),
            "mean_holdout_incr": float(np.mean(vs)),
        }
        for fam, vs in family_scores.items()
    }

    # Horizon strength
    horizon_scores: Dict[int, List[float]] = {}
    for r in registry:
        ho = (r.get("holdout") or {}).get("incremental_mean_ret")
        if ho is None or r["classification"] in ("REJECT", "DESCRIPTIVE_ONLY"):
            continue
        horizon_scores.setdefault(r["horizon"], []).append(abs(ho))
    horizon_summary = {
        str(h): {"n": len(vs), "mean_abs_holdout_incr": float(np.mean(vs))}
        for h, vs in horizon_scores.items()
    }

    evidence = {
        "verdict": verdict,
        "DEDICATED_CONFIRMATION_PHASE": confirm,
        "n_candidates": len(registry),
        "class_counts": {k: len(v) for k, v in by_class.items()},
        "strongest_positive": pos[:5],
        "strongest_negative": neg[:5],
        "intuitive_nulls": nulls,
        "family_summary": family_summary,
        "horizon_summary": horizon_summary,
        "split": SPLIT,
        "n_research_eligible_rows": int(eligible.shape[0]),
        "n_excluded_bad_price_or_jump": int((~panel["research_eligible"]).sum()),
        "freeze_dataset_version": freeze_manifest["dataset_version"],
        "code_commit": freeze_manifest["code_commit"],
    }
    (OUT_DIR / "EVIDENCE.json").write_text(json.dumps(evidence, indent=2, default=str) + "\n", encoding="utf-8")

    # Write markdown reports
    _write_markdown_reports(
        freeze_manifest,
        grammar,
        deferred,
        base_df,
        registry,
        falsification_docs,
        evidence,
        search_accounting,
        panel,
    )

    # Run reproducibility manifest
    run_manifest = {
        "research_run_id": freeze_manifest["research_run_id"],
        "input_dataset_hash": freeze_manifest["input_dataset_hash"],
        "dataset_version": freeze_manifest["dataset_version"],
        "code_commit": freeze_manifest["code_commit"],
        "feature_grammar_version": FEATURE_GRAMMAR_VERSION,
        "outcome_version": OUTCOME_VERSION,
        "temporal_split": SPLIT,
        "search_budget": search_accounting["search_budget"],
        "n_hypotheses_examined": n_examined,
        "random_seed": RESEARCH_SEED,
        "candidate_ids": [r["candidate_id"] for r in registry],
        "verdict": verdict,
        "DEDICATED_CONFIRMATION_PHASE": confirm,
        "created_at": utc_now(),
    }
    (OUT_DIR / "RESEARCH_RUN_MANIFEST.json").write_text(json.dumps(run_manifest, indent=2) + "\n", encoding="utf-8")

    return evidence


def _write_markdown_reports(
    freeze_manifest,
    grammar,
    deferred,
    base_df,
    registry,
    falsification_docs,
    evidence,
    search_accounting,
    panel,
):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUT_DIR / "RESEARCH_PROTOCOL.md").write_text(
        f"""# Foreign Flow Blind Research V1 — Protocol

**Mode:** Scientific research only. No trading translation. No production mutation.

## Blindness contract

No preferred proposition. Sign / magnitude / persistence / transition / interaction treated symmetrically.
`NO ROBUST EDGE FOUND` is acceptable.

## Input

- Canonical freeze: `{freeze_manifest['dataset_version']}`
- Input hash: `{freeze_manifest['input_dataset_hash']}`
- Cohort: current EMS HOSE overlap (117) — **not** historical membership-as-of

## Temporal semantics

See `OUTCOME_SEMANTICS.md`.

## Splits (chronological)

| Split | Dates |
|-------|-------|
| Discovery | {SPLIT['discovery'][0]} → {SPLIT['discovery'][1]} |
| Validation | {SPLIT['validation'][0]} → {SPLIT['validation'][1]} |
| Holdout | {SPLIT['holdout'][0]} → {SPLIT['holdout'][1]} |

## Search

Pre-declared bounded grammar (`FEATURE_GRAMMAR.json`). Single pass × horizons T1/T3/T5/T10.
No post-hoc feature invention after seeing outcomes.

## Classification

`DESCRIPTIVE_ONLY` | `FRAGILE` | `RESEARCH_CANDIDATE` | `ROBUST_CANDIDATE` | `REJECT`  
No `EDGE ACTIVE` in this phase.
""",
        encoding="utf-8",
    )

    (OUT_DIR / "OUTCOME_SEMANTICS.md").write_text(
        """# Outcome Semantics

## PIT timing

- Each canonical row is one HOSE `trade_date × symbol` session from the official HSX foreign endpoint.
- Fields (`foreign_*`, OHLC) are treated as **known at/after that session's close** for research purposes.
- Exact intra-day release timestamp of HSX foreign prints is **not** separately verified; conservative rule: **no same-session forward return using T0 close as both feature path and exit**.

## Earliest legitimate outcome

- **T0 close** = state / marking price only.
- **T1** = next trading session's close / T0 close − 1.
- **T3 / T5 / T10** = 3rd / 5th / 10th subsequent **trading session** close / T0 close − 1.
- Horizons are **session counts**, not calendar days.

## Integrity filters

- Drop research rows where `close_price <= 0`.
- Drop rows with extreme prior-close→T0 jump (`ratio > 1.8` or `< 0.55`) as likely CA/bad prints.
- Forward return requires destination close `> 0`.
- Corporate-action adjustment status of provider OHLC is **unknown**; long-horizon levels may still contain split artifacts even after jump filters — documented as a caveat.

## MFE / MAE

- MFE/MAE over next 10 sessions vs T0 close using path high/low when available.
- Not used as primary discovery metric; descriptive only.
""",
        encoding="utf-8",
    )

    # Falsification report
    lines = ["# Falsification Report", ""]
    for f in falsification_docs:
        lines.append(f"## {f.get('candidate_id')} — `{f.get('feature')}` T{f.get('horizon')}")
        lines.append(f"- killed: `{f.get('killed')}` severity=`{f.get('kill_severity')}` reason=`{f.get('kill_reason')}`")
        lines.append(f"- survived_leave_top5: `{f.get('survived_leave_top5')}`")
        lines.append(f"- survived_alt_horizon: `{f.get('survived_alt_horizon')}`")
        for t in f.get("tests") or []:
            lines.append(f"  - {t}")
        lines.append("")
    (OUT_DIR / "FALSIFICATION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")

    # Holdout report
    hold_lines = ["# Holdout Report", "", f"Holdout window: {SPLIT['holdout'][0]} → {SPLIT['holdout'][1]}", ""]
    for r in registry:
        ho = r.get("holdout")
        if not ho:
            continue
        hold_lines.append(
            f"- `{r['candidate_id']}` `{r['feature']}` T{r['horizon']} class=`{r['classification']}` "
            f"incr={ho.get('incremental_mean_ret')} wr={ho.get('win_rate')} n={ho.get('n')} symbols={ho.get('n_symbols')}"
        )
    (OUT_DIR / "HOLDOUT_REPORT.md").write_text("\n".join(hold_lines) + "\n", encoding="utf-8")

    # Final report
    verdict = evidence["verdict"]
    confirm = evidence["DEDICATED_CONFIRMATION_PHASE"]
    pos = evidence.get("strongest_positive") or []
    neg = evidence.get("strongest_negative") or []

    def fmt_cand(r):
        if not r:
            return "_none_"
        ho = r.get("holdout") or {}
        va = r.get("validation") or {}
        di = r.get("discovery") or {}
        return (
            f"`{r['feature']}` T{r['horizon']} [{r['classification']}] "
            f"disc_incr={di.get('incremental_mean_ret')} val_incr={va.get('incremental_mean_ret')} "
            f"hold_incr={ho.get('incremental_mean_ret')} hold_n={ho.get('n')} hold_symbols={ho.get('n_symbols')}"
        )

    final = f"""# Foreign Flow Blind Research V1 — Final Report

## Verdict

`{verdict}`

`DEDICATED_CONFIRMATION_PHASE = {confirm}`

## Answers to required questions

1. **Does foreign-flow history contain reproducible information about subsequent stock outcomes?**  
   See verdict above. Classification counts: `{json.dumps(evidence.get('class_counts'))}`.

2. **At which horizon(s), if any?**  
   Horizon summary (mean |holdout incremental| among non-trivial): `{json.dumps(evidence.get('horizon_summary'))}`.

3. **What type of information carries it?**  
   Family summary: `{json.dumps(evidence.get('family_summary'))}`.

4. **Incremental effect vs baseline?**  
   Strongest positive holdout: {fmt_cand(pos[0] if pos else None)}  
   Strongest negative holdout: {fmt_cand(neg[0] if neg else None)}

5. **Survive later periods?**  
   Candidates require validation + holdout sign consistency for `RESEARCH_CANDIDATE` / `ROBUST_CANDIDATE`.

6. **Survive removal of dominant stocks/dates/years?**  
   See `FALSIFICATION_REPORT.md` (leave-top5, drop strongest year, parent condition, reverse feature).

7. **Strongest anti-edge / failure condition?**  
   {fmt_cand(neg[0] if neg else None)}

8. **What would falsify a surviving candidate next?**  
   Pre-registered confirmation: new untouched post-freeze period; leave-one-sector-out; stricter CA-adjusted prices; parent-condition horse-race; liquidity-normalized variants only if ADV history becomes available.

9. **Dedicated confirmation phase justified?**  
   `{confirm}`

## Data freeze

- dataset: `{freeze_manifest['dataset_version']}`
- rows: `{freeze_manifest['row_count_disk']}`
- symbols: `{freeze_manifest['symbol_count_disk']}`
- range: `{freeze_manifest['first_trade_date']}` → `{freeze_manifest['last_trade_date']}`
- excluded bad-price/jump rows: `{evidence.get('n_excluded_bad_price_or_jump')}`
- research-eligible rows: `{evidence.get('n_research_eligible_rows')}`

## Search accounting

- hypotheses examined: `{search_accounting['n_hypotheses_examined']}`
- promoted from discovery: `{search_accounting['n_promoted_from_discovery']}`
- depth: `{search_accounting['adaptive_search_depth']}`

## Top findings (operator-facing, limited)

### Strongest positive future-outcome candidates
{chr(10).join('- ' + fmt_cand(r) for r in pos[:3]) or '- none'}

### Strongest negative / anti-edge candidates
{chr(10).join('- ' + fmt_cand(r) for r in neg[:3]) or '- none'}

### Important intuitive nulls (holdout)
{chr(10).join('- ' + json.dumps({{'feature':n.get('feature'),'horizon':n.get('horizon'),'incr':n.get('incremental_mean_ret'),'mean':n.get('mean_ret'),'n':n.get('n')}}) for n in (evidence.get('intuitive_nulls') or [])[:6]) or '- none'}

## Confirmation proposal (ONLY if YES)

If confirmation = YES: freeze the surviving candidate definition(s), register a post-2026-08-24 (or next available) forward window, pre-declare success thresholds (sign consistency + min incremental bps + min symbols), and re-run without expanding the feature grammar.

## Vietnamese summary

Xem phần cuối `FINAL_REPORT.md` (operator block).

---

### Operator block (VI)

**Sau khoảng 17 năm dữ liệu, khối ngoại thực sự có chứa thông tin giúp dự báo T3/T5/T10 hay không?**

Kết luận khoa học của phase này: **`{verdict}`**.  
Confirmation phase: **`{confirm}`**.

Chi tiết ứng viên và bằng chứng OOS/falsification nằm trong `CANDIDATE_REGISTRY.json`, `TEMPORAL_VALIDATION.csv`, `FALSIFICATION_REPORT.md`.  
Không diễn giải thành khuyến nghị giao dịch trong phase này.
"""
    # Fill VI section more carefully after we know verdict - rewrite with better Vietnamese at end of run_research via evidence
    (OUT_DIR / "FINAL_REPORT.md").write_text(final, encoding="utf-8")


if __name__ == "__main__":
    ev = run_research()
    print(json.dumps({"verdict": ev["verdict"], "CONFIRM": ev["DEDICATED_CONFIRMATION_PHASE"], "classes": ev["class_counts"]}, indent=2))
