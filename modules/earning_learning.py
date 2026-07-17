"""
MR.BOT - EARNING MONEY LEARNING ENGINE
Passive learning from Earning Money Board. It never changes trading logic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

MODULE_VERSION = "1.0.0"
DEFAULT_HORIZONS: Tuple[int, ...] = (3, 5, 10)
DEFAULT_DATA_DIR = Path("data") / "earning_learning"

OBSERVATIONS_FILE = "observations.csv"
OUTCOMES_FILE = "outcomes.csv"
KNOWLEDGE_FILE = "pattern_knowledge.csv"
STATUS_FILE = "status.json"

_LOGGER = logging.getLogger(__name__)
_LOCK = threading.RLock()

COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "symbol": ("symbol", "ticker", "code", "mã", "ma", "Mã", "Ticker"),
    "trade_date": ("trade_date", "date", "datetime", "date_time", "time", "Ngày", "Ngày/Giờ"),
    "price": ("price", "close", "last", "current_price", "daily_price_before_live", "Giá", "Close"),
    "health_group": ("evolution_health_group", "health_group", "group_name", "health", "Trạng thái", "Nhóm"),
    "health_score": ("evolution_health_score", "health_score", "total_score", "Điểm", "Score"),
    "health_rank": ("evolution_health_rank", "health_rank", "rank"),
    "action": ("evolution_action", "action", "signal", "Mua/Bán", "Hành động"),
    "reason": ("evolution_reason", "reason", "Lý do"),
    "rsi14": ("rsi14", "rsi", "RSI", "RSI14"),
    "rsi_slope": ("rsi_slope", "rsi14_slope", "RSI slope"),
    "rs5": ("rs5", "RS5", "rs_5"),
    "rs10": ("rs10", "RS10", "rs_10"),
    "ema9": ("ema9", "EMA9"),
    "ma20": ("ma20", "sma20", "MA20", "SMA20"),
    "ema9_ma20_slope": ("ema9_ma20_slope", "trend_slope", "slope", "Slope"),
    "ema9_ma20_slope_change": ("ema9_ma20_slope_change", "slope_change"),
    "obv_status": ("obv_status", "obv", "OBV"),
    "volume": ("volume", "vol", "Volume", "Khối lượng"),
    "vol_ma20": ("vol_ma20", "volume_ma20", "Vol MA20"),
    "dist_from_ema9_pct": ("dist_from_ema9_pct", "dist_ema9_pct"),
    "near_bottom_20_pct": ("near_bottom_20_pct",),
    "near_bottom_60_pct": ("near_bottom_60_pct",),
    "dist_high20": ("dist_high20", "dist_high20_pct"),
    "green2": ("green_2_confirm", "green2", "early_green2"),
    "early": ("early", "early_signal", "early_dry_green2"),
    "pull": ("pull", "pull_label", "pull_signal"),
    "group": ("group", "evolution_stage", "stage"),
    "sector": ("sector", "industry", "ngành", "Ngành"),
    "market_score": ("market_score", "market_real", "market_health"),
    "market_regime": ("market_regime", "regime", "market_state"),
}

NUMERIC_FIELDS = (
    "price", "health_score", "health_rank", "rsi14", "rsi_slope", "rs5", "rs10",
    "ema9", "ma20", "ema9_ma20_slope", "ema9_ma20_slope_change", "volume",
    "vol_ma20", "dist_from_ema9_pct", "near_bottom_20_pct", "near_bottom_60_pct",
    "dist_high20", "market_score",
)
BOOLEAN_FIELDS = ("green2", "early", "pull")


@dataclass(frozen=True)
class LearningResult:
    ok: bool
    module_version: str
    trade_date: Optional[str]
    input_rows: int
    valid_rows: int
    observations_added: int
    observations_updated: int
    outcomes_added: int
    knowledge_rows: int
    skipped_reason: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _normalise_name(value: Any) -> str:
    return re.sub(r"\s+", "_", str(value).strip().lower())


def _normalise_symbol(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return re.sub(r"[^A-Z0-9._-]", "", str(value).strip().upper())


def _safe_float(value: Any) -> float:
    if value is None:
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            result = float(value)
            return result if math.isfinite(result) else np.nan
        except Exception:
            return np.nan
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text:
        return np.nan
    try:
        result = float(text)
        return result if math.isfinite(result) else np.nan
    except Exception:
        return np.nan


def _safe_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, (int, float, np.integer, np.floating)):
        return bool(value)
    return str(value).strip().lower() in {
        "1", "true", "yes", "y", "ok", "x", "có", "co", "đúng", "dung",
        "green2", "early", "pull", "confirmed",
    }


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _resolve_data_dir(data_dir: Optional[os.PathLike | str]) -> Path:
    path = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", prefix=path.stem + "_", dir=path.parent,
        delete=False, encoding="utf-8-sig", newline=""
    ) as handle:
        temp_path = Path(handle.name)
        df.to_csv(handle, index=False)
    os.replace(temp_path, path)


def _atomic_write_json(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix=path.stem + "_", dir=path.parent,
        delete=False, encoding="utf-8"
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
    os.replace(temp_path, path)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path)
    except Exception:
        _LOGGER.exception("Cannot read learning file: %s", path)
        return pd.DataFrame()


def _hash_payload(values: Iterable[Any]) -> str:
    raw = "|".join(_safe_text(value) for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _find_source_column(columns: Sequence[Any], aliases: Sequence[str]) -> Optional[Any]:
    exact = {str(col): col for col in columns}
    normalised = {_normalise_name(col): col for col in columns}
    for alias in aliases:
        if alias in exact:
            return exact[alias]
    for alias in aliases:
        key = _normalise_name(alias)
        if key in normalised:
            return normalised[key]
    return None


def _adapt_board(
    board_df: pd.DataFrame,
    market_context: Optional[Mapping[str, Any]] = None,
) -> pd.DataFrame:
    if not isinstance(board_df, pd.DataFrame):
        raise TypeError("earning_board_df must be a pandas DataFrame")
    if board_df.empty:
        return pd.DataFrame()

    source = board_df.copy(deep=True)
    canonical = pd.DataFrame(index=source.index)

    for canonical_name, aliases in COLUMN_ALIASES.items():
        source_col = _find_source_column(source.columns, aliases)
        canonical[canonical_name] = source[source_col] if source_col is not None else np.nan

    market_context = dict(market_context or {})
    for field in ("market_score", "market_regime"):
        if canonical[field].isna().all() and field in market_context:
            canonical[field] = market_context[field]

    canonical["symbol"] = canonical["symbol"].map(_normalise_symbol)
    canonical = canonical[canonical["symbol"] != ""].copy()

    context_date = market_context.get("trade_date") or market_context.get("date")
    parsed_date = pd.to_datetime(canonical["trade_date"], errors="coerce")
    if context_date is not None:
        parsed_date = parsed_date.fillna(pd.to_datetime(context_date, errors="coerce"))
    parsed_date = parsed_date.fillna(pd.Timestamp(date.today()))
    canonical["trade_date"] = parsed_date.dt.strftime("%Y-%m-%d")

    for field in NUMERIC_FIELDS:
        canonical[field] = canonical[field].map(_safe_float)
    for field in BOOLEAN_FIELDS:
        canonical[field] = canonical[field].map(_safe_bool)
    for field in ("health_group", "action", "reason", "obv_status", "group", "sector", "market_regime"):
        canonical[field] = canonical[field].map(_safe_text)

    canonical["rs_spread"] = canonical["rs5"] - canonical["rs10"]
    canonical["price_vs_ema9_pct"] = np.where(
        canonical["ema9"].abs() > 1e-12,
        (canonical["price"] / canonical["ema9"] - 1.0) * 100.0,
        canonical["dist_from_ema9_pct"],
    )
    canonical["price_vs_ma20_pct"] = np.where(
        canonical["ma20"].abs() > 1e-12,
        (canonical["price"] / canonical["ma20"] - 1.0) * 100.0,
        np.nan,
    )
    canonical["volume_ratio20"] = np.where(
        canonical["vol_ma20"].abs() > 1e-12,
        canonical["volume"] / canonical["vol_ma20"],
        np.nan,
    )

    canonical["observation_id"] = [
        _hash_payload((d, s)) for d, s in zip(canonical["trade_date"], canonical["symbol"])
    ]
    canonical["recorded_at"] = _utc_now_iso()
    canonical["module_version"] = MODULE_VERSION
    canonical = canonical.drop_duplicates(subset=["trade_date", "symbol"], keep="last")

    ordered = [
        "observation_id", "trade_date", "recorded_at", "module_version", "symbol", "price",
        "health_group", "health_score", "health_rank", "action", "reason",
        "rsi14", "rsi_slope", "rs5", "rs10", "rs_spread",
        "ema9", "ma20", "ema9_ma20_slope", "ema9_ma20_slope_change",
        "price_vs_ema9_pct", "price_vs_ma20_pct", "obv_status", "volume",
        "vol_ma20", "volume_ratio20", "dist_from_ema9_pct", "near_bottom_20_pct",
        "near_bottom_60_pct", "dist_high20", "green2", "early", "pull",
        "group", "sector", "market_score", "market_regime",
    ]
    return canonical[ordered].reset_index(drop=True)


def _upsert_observations(new_df: pd.DataFrame, path: Path):
    existing = _read_csv(path)
    if existing.empty:
        combined, added, updated = new_df.copy(), len(new_df), 0
    else:
        existing_keys = set(zip(existing["trade_date"].astype(str), existing["symbol"].astype(str)))
        new_keys = list(zip(new_df["trade_date"].astype(str), new_df["symbol"].astype(str)))
        added = sum(key not in existing_keys for key in new_keys)
        updated = len(new_df) - added
        combined = pd.concat([existing, new_df], ignore_index=True, sort=False)
        combined = combined.drop_duplicates(subset=["trade_date", "symbol"], keep="last")
    combined["trade_date"] = combined["trade_date"].astype(str)
    combined = combined.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
    _atomic_write_csv(combined, path)
    return combined, int(added), int(updated)


def _build_outcomes(observations: pd.DataFrame, horizons: Sequence[int] = DEFAULT_HORIZONS) -> pd.DataFrame:
    if observations.empty:
        return pd.DataFrame()

    df = observations.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["trade_date", "symbol", "price"])
    df = df.sort_values(["symbol", "trade_date"], kind="stable")

    rows = []
    for symbol, group in df.groupby("symbol", sort=False):
        group = group.reset_index(drop=True)
        for i, current in group.iterrows():
            base_price = _safe_float(current["price"])
            if not math.isfinite(base_price) or base_price <= 0:
                continue
            for horizon in horizons:
                target_index = i + int(horizon)
                if target_index >= len(group):
                    continue
                future = group.iloc[target_index]
                future_price = _safe_float(future["price"])
                if not math.isfinite(future_price) or future_price <= 0:
                    continue

                future_slice = group.iloc[i + 1:target_index + 1]
                slice_prices = pd.to_numeric(future_slice["price"], errors="coerce").dropna()
                return_pct = (future_price / base_price - 1.0) * 100.0
                max_gain_pct = (slice_prices.max() / base_price - 1.0) * 100.0 if not slice_prices.empty else np.nan
                max_drawdown_pct = (slice_prices.min() / base_price - 1.0) * 100.0 if not slice_prices.empty else np.nan
                leader_threshold = {3: 5.0, 5: 8.0, 10: 12.0}.get(int(horizon), 10.0)

                rows.append({
                    "outcome_id": _hash_payload((current["observation_id"], horizon)),
                    "observation_id": current["observation_id"],
                    "symbol": symbol,
                    "entry_date": current["trade_date"].strftime("%Y-%m-%d"),
                    "entry_price": base_price,
                    "horizon": int(horizon),
                    "target_date": future["trade_date"].strftime("%Y-%m-%d"),
                    "target_price": future_price,
                    "return_pct": return_pct,
                    "max_gain_pct": max_gain_pct,
                    "max_drawdown_pct": max_drawdown_pct,
                    "is_win": bool(return_pct > 0.0),
                    "is_leader": bool(max_gain_pct >= leader_threshold),
                    "evaluated_at": _utc_now_iso(),
                    "module_version": MODULE_VERSION,
                })

    if not rows:
        return pd.DataFrame()
    outcomes = pd.DataFrame(rows).drop_duplicates(subset=["outcome_id"], keep="last")
    return outcomes.sort_values(["entry_date", "symbol", "horizon"], kind="stable").reset_index(drop=True)


def _bucket_numeric(series: pd.Series, bins: Sequence[float], labels: Sequence[str]) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.cut(
        numeric, bins=[-np.inf, *bins, np.inf], labels=labels,
        include_lowest=True, right=False
    ).astype("string").fillna("NA")


def _normalise_health_group(value: Any) -> str:
    text = _safe_text(value).lower()
    if "đang hồi" in text or "dang hoi" in text:
        return "RECOVERING"
    if "trung tính" in text or "trung tinh" in text:
        return "NEUTRAL"
    if "yếu dần" in text or "yeu dan" in text:
        return "WEAKENING"
    if "rất yếu" in text or "rat yeu" in text:
        return "VERY_WEAK"
    if "yếu" in text or "yeu" in text:
        return "WEAK"
    return _safe_text(value).upper() or "UNKNOWN"


def _obv_bucket(value: Any) -> str:
    text = _safe_text(value).lower()
    if any(token in text for token in ("positive", "dương", "duong", "tăng", "tang", "above", "strong")):
        return "POSITIVE"
    if any(token in text for token in ("negative", "âm", "am", "giảm", "giam", "below", "weak")):
        return "NEGATIVE"
    return "NEUTRAL"


def _add_pattern_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["p_health"] = out["health_group"].map(_normalise_health_group)
    out["p_rsi"] = _bucket_numeric(out["rsi14"], (45, 50, 55, 60, 65, 70), ("<45", "45-50", "50-55", "55-60", "60-65", "65-70", ">=70"))
    out["p_rs10"] = _bucket_numeric(out["rs10"], (-2, 0, 2, 5, 10), ("<-2", "-2-0", "0-2", "2-5", "5-10", ">=10"))
    out["p_rs_spread"] = _bucket_numeric(out["rs_spread"], (-2, 0, 2, 5), ("<-2", "-2-0", "0-2", "2-5", ">=5"))
    out["p_slope"] = _bucket_numeric(out["ema9_ma20_slope"], (-0.2, 0, 0.2), ("STRONG_NEG", "NEG", "POS", "STRONG_POS"))
    out["p_volume"] = _bucket_numeric(out["volume_ratio20"], (0.7, 1.0, 1.2, 1.5), ("<0.7", "0.7-1.0", "1.0-1.2", "1.2-1.5", ">=1.5"))
    out["p_obv"] = out["obv_status"].map(_obv_bucket)
    out["p_green2"] = out["green2"].map(lambda x: "G2" if _safe_bool(x) else "NO_G2")
    out["p_early"] = out["early"].map(lambda x: "EARLY" if _safe_bool(x) else "NO_EARLY")
    out["p_pull"] = out["pull"].map(lambda x: "PULL" if _safe_bool(x) else "NO_PULL")
    out["p_market"] = _bucket_numeric(out["market_score"], (4, 6, 8), ("<4", "4-6", "6-8", ">=8"))
    fields = ["p_health", "p_rsi", "p_rs10", "p_rs_spread", "p_slope", "p_obv", "p_volume", "p_green2", "p_early", "p_pull", "p_market"]
    out["pattern_key"] = out[fields].astype(str).agg("|".join, axis=1)
    return out


def _build_pattern_knowledge(observations: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    if observations.empty or outcomes.empty:
        return pd.DataFrame()

    obs = _add_pattern_columns(observations)
    merged = outcomes.merge(obs, on=["observation_id", "symbol"], how="inner", suffixes=("_outcome", ""))
    if merged.empty:
        return pd.DataFrame()

    knowledge = (
        merged.groupby(["pattern_key", "horizon"], dropna=False)
        .agg(
            samples=("outcome_id", "count"),
            wins=("is_win", "sum"),
            leaders=("is_leader", "sum"),
            avg_return_pct=("return_pct", "mean"),
            median_return_pct=("return_pct", "median"),
            avg_max_gain_pct=("max_gain_pct", "mean"),
            avg_max_drawdown_pct=("max_drawdown_pct", "mean"),
            best_return_pct=("return_pct", "max"),
            worst_return_pct=("return_pct", "min"),
            first_seen=("entry_date", "min"),
            last_seen=("entry_date", "max"),
        )
        .reset_index()
    )

    knowledge["win_rate_pct"] = knowledge["wins"] / knowledge["samples"] * 100.0
    knowledge["leader_rate_pct"] = knowledge["leaders"] / knowledge["samples"] * 100.0

    z = 1.2815515655446004
    n = knowledge["samples"].astype(float)
    p = knowledge["wins"].astype(float) / n
    denominator = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * np.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    knowledge["win_rate_lower_bound_pct"] = (centre - margin) / denominator * 100.0

    knowledge["knowledge_score"] = (
        0.45 * knowledge["win_rate_lower_bound_pct"]
        + 0.25 * knowledge["leader_rate_pct"]
        + 0.20 * knowledge["avg_return_pct"].clip(-20, 30)
        + 0.10 * knowledge["avg_max_gain_pct"].clip(-20, 40)
    )
    knowledge["updated_at"] = _utc_now_iso()
    knowledge["module_version"] = MODULE_VERSION
    return knowledge.sort_values(
        ["horizon", "knowledge_score", "samples"],
        ascending=[True, False, False], kind="stable"
    ).reset_index(drop=True)


def _save_status(data_dir: Path, result: LearningResult) -> None:
    payload = result.to_dict()
    payload["last_run_at"] = _utc_now_iso()
    _atomic_write_json(payload, data_dir / STATUS_FILE)


def get_learning_status(data_dir: Optional[os.PathLike | str] = None) -> Dict[str, Any]:
    directory = _resolve_data_dir(data_dir)
    path = directory / STATUS_FILE
    if not path.exists():
        return {"ok": True, "module_version": MODULE_VERSION, "status": "NO_RUN_YET"}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        return {"ok": False, "module_version": MODULE_VERSION, "status": "STATUS_READ_ERROR", "error": str(exc)}


def get_pattern_knowledge(
    data_dir: Optional[os.PathLike | str] = None,
    min_samples: int = 3,
) -> pd.DataFrame:
    directory = _resolve_data_dir(data_dir)
    knowledge = _read_csv(directory / KNOWLEDGE_FILE)
    if knowledge.empty:
        return knowledge
    samples = pd.to_numeric(knowledge.get("samples"), errors="coerce")
    return knowledge[samples >= int(min_samples)].copy().reset_index(drop=True)


def update_learning(
    earning_board_df: pd.DataFrame,
    *,
    market_context: Optional[Mapping[str, Any]] = None,
    data_dir: Optional[os.PathLike | str] = None,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    strict: bool = False,
) -> Dict[str, Any]:
    """
    Save the current Earning Money Board and update T+3/T+5/T+10 outcomes.

    Production default is fail-safe: no exception is allowed to break app.py.
    Use strict=True only in local tests.
    """
    directory = _resolve_data_dir(data_dir)
    input_rows = len(earning_board_df) if isinstance(earning_board_df, pd.DataFrame) else 0

    try:
        with _LOCK:
            canonical = _adapt_board(earning_board_df, market_context=market_context)
            if canonical.empty:
                result = LearningResult(
                    True, MODULE_VERSION, None, input_rows, 0, 0, 0, 0, 0,
                    skipped_reason="EMPTY_OR_NO_VALID_SYMBOL",
                )
                _save_status(directory, result)
                return result.to_dict()

            trade_dates = sorted(canonical["trade_date"].astype(str).unique())
            trade_date_value = trade_dates[-1] if trade_dates else None

            observations, added, updated = _upsert_observations(
                canonical, directory / OBSERVATIONS_FILE
            )

            old_outcomes = _read_csv(directory / OUTCOMES_FILE)
            outcomes = _build_outcomes(observations, horizons=horizons)
            if not outcomes.empty:
                _atomic_write_csv(outcomes, directory / OUTCOMES_FILE)

            old_ids = set(old_outcomes.get("outcome_id", pd.Series(dtype=str)).astype(str))
            new_ids = set(outcomes.get("outcome_id", pd.Series(dtype=str)).astype(str))
            outcomes_added = len(new_ids - old_ids)

            knowledge = _build_pattern_knowledge(observations, outcomes)
            if not knowledge.empty:
                _atomic_write_csv(knowledge, directory / KNOWLEDGE_FILE)

            result = LearningResult(
                True, MODULE_VERSION, trade_date_value, input_rows, len(canonical),
                added, updated, outcomes_added, len(knowledge),
            )
            _save_status(directory, result)
            return result.to_dict()

    except Exception as exc:
        _LOGGER.exception("Earning Learning failed safely")
        result = LearningResult(
            False, MODULE_VERSION, None, input_rows, 0, 0, 0, 0, 0,
            error=f"{type(exc).__name__}: {exc}",
        )
        try:
            _save_status(directory, result)
        except Exception:
            _LOGGER.exception("Cannot save Learning failure status")
        if strict:
            raise
        return result.to_dict()


learn_from_earning_board = update_learning

__all__ = [
    "MODULE_VERSION",
    "DEFAULT_HORIZONS",
    "update_learning",
    "learn_from_earning_board",
    "get_learning_status",
    "get_pattern_knowledge",
]

