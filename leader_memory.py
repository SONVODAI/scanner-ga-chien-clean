"""
Mr.BOT Intelligence Center - Leader Memory V5
================================================
- Lưu snapshot theo ngày, chống ghi trùng khi Streamlit rerun.
- Tự cập nhật T+1 / T+3 / T+5 / T+10 theo phiên dữ liệu.
- Sinh Leader Brain, Hall of Fame, Pattern Library, AI Recommendation.
- Giữ tương thích:
      update_memory(scan_df)
      load_memory()
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


ENGINE_NAME = "Mr.BOT Intelligence Center"
ENGINE_VERSION = "5.0.0"
SCHEMA_VERSION = 5

MODULE_DIR = Path(__file__).resolve().parent
BRAIN_DIR = MODULE_DIR / "brain"

HISTORY_FILE = BRAIN_DIR / "leader_history.csv"
BRAIN_FILE = BRAIN_DIR / "leader_brain.csv"
PATTERN_FILE = BRAIN_DIR / "pattern_library.csv"
HALL_OF_FAME_FILE = BRAIN_DIR / "hall_of_fame.csv"
RECOMMENDATION_FILE = BRAIN_DIR / "ai_recommendation.csv"
LEGACY_MEMORY_FILE = MODULE_DIR / "leader_memory.csv"
CONFIG_FILE = BRAIN_DIR / "learning_config.json"
LOG_FILE = BRAIN_DIR / "leader_memory.log"
LOCK_FILE = BRAIN_DIR / ".leader_memory.lock"

BRAIN_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("leader_memory_v5")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)
logger.propagate = False


DEFAULT_CONFIG: Dict[str, Any] = {
    "engine_name": ENGINE_NAME,
    "engine_version": ENGINE_VERSION,
    "schema_version": SCHEMA_VERSION,
    "horizons": [1, 3, 5, 10],
    "win_threshold_pct": {"1": 0.0, "3": 1.0, "5": 2.0, "10": 3.0},
    "persistence_window": 20,
    "max_brain_rows": 5000,
    "max_pattern_rows": 500,
    "max_hall_of_fame_rows": 200,
    "max_recommendation_rows": 100,
    "dedupe_keys": ["session_date", "symbol"],
    "leader_score_weights": {
        "strength": 0.30,
        "persistence": 0.20,
        "quality": 0.20,
        "performance": 0.20,
        "market_fit": 0.10,
    },
    "column_aliases": {
        "symbol": ["symbol", "ticker", "code", "stock", "MÃ", "Mã"],
        "price": ["price", "close", "last", "last_price", "current_price", "Giá"],
        "group": ["group", "nhom", "Nhóm", "TRẠNG THÁI", "status_group"],
        "sector": ["sector", "industry", "NGÀNH", "nganh"],
        "rs5": ["rs5", "RS5", "relative_strength_5"],
        "rs10": ["rs10", "RS10", "relative_strength_10"],
        "rsi14": ["rsi14", "RSI14", "rsi", "RSI"],
        "obv": ["obv", "OBV", "obv_value"],
        "obv_status": ["obv_status", "OBV_STATUS", "obv_trend", "DÒNG TIỀN"],
        "total_score": ["total_score", "score", "TOTAL_SCORE", "SCORE"],
        "trend_score": ["trend_score", "TREND_SCORE"],
        "buy_score": ["buy_score", "BUY_SCORE"],
        "persistence": ["Persistence", "persistence", "PERSISTENCE"],
        "evolution": ["evolution", "Evolution", "TIẾN HÓA"],
        "recent_change": ["recent_change", "RECENT_CHANGE", "GẦN NHẤT"],
        "ema9_ma20_slope": ["ema9_ma20_slope", "EMA9_MA20_SLOPE", "slope"],
        "dist_from_ema9_pct": ["dist_from_ema9_pct", "DIST_EMA9_PCT"],
        "volume": ["volume", "vol", "VOLUME", "VOL"],
        "vol_ma20": ["vol_ma20", "volume_ma20", "VOL_MA20"],
        "market_real": ["market_real", "MARKET_REAL"],
        "market_forecast": ["market_forecast", "MARKET_FORECAST"],
        "market_regime": ["market_regime", "regime", "MARKET_REGIME"],
        "storm": ["storm", "Storm", "STORM"],
        "early": ["early", "EARLY"],
        "pullback": ["pullback", "PULLBACK"],
        "green2": ["green2", "GREEN2"],
        "dryup": ["dryup", "dry_up", "DRYUP"],
        "health_group": [
            "evolution_health_group", "health_group", "health",
            "Health", "Trạng thái",
        ],
        "action": ["action", "ACTION", "mua_ban", "MUA_BÁN"],
        "reason": ["reason", "REASON", "ly_do", "LÝ_DO"],
    },
    "group_quality_map": {
        "CP MẠNH": 100,
        "GÀ TĂNG TỐC": 95,
        "MUA BREAK": 92,
        "PULL ĐẸP": 90,
        "PULL VỪA": 82,
        "MUA EARLY": 78,
        "TÍCH LŨY": 70,
        "🌱 ĐANG HỒI": 75,
        "ĐANG HỒI": 75,
        "🟡 TRUNG TÍNH": 55,
        "TRUNG TÍNH": 55,
        "THEO DÕI": 50,
        "⚠️ YẾU DẦN": 30,
        "YẾU DẦN": 30,
        "🔴 YẾU": 20,
        "YẾU": 20,
        "⛔ RẤT YẾU": 5,
        "RẤT YẾU": 5,
    },
}


BASE_FEATURE_COLUMNS = [
    "session_date", "snapshot_time", "symbol", "price", "group", "sector",
    "rs5", "rs10", "rsi14", "obv", "obv_status", "total_score",
    "trend_score", "buy_score", "source_persistence", "evolution",
    "recent_change", "ema9_ma20_slope", "dist_from_ema9_pct",
    "volume", "vol_ma20", "volume_ratio", "market_real",
    "market_forecast", "market_regime", "storm", "early", "pullback",
    "green2", "dryup", "action", "reason", "feature_signature",
    "schema_version", "engine_version",
]

OUTCOME_COLUMNS: List[str] = []
for h in [1, 3, 5, 10]:
    OUTCOME_COLUMNS += [
        f"price_t{h}",
        f"return_t{h}_pct",
        f"win_t{h}",
        f"max_gain_t{h}_pct",
        f"max_drawdown_t{h}_pct",
        f"evaluated_t{h}",
    ]

HISTORY_COLUMNS = BASE_FEATURE_COLUMNS + OUTCOME_COLUMNS

BRAIN_COLUMNS = [
    "symbol", "first_seen", "last_seen", "appearances", "active_days_20",
    "persistence_20_pct", "current_group", "current_sector",
    "current_price", "current_rs5", "current_rs10", "current_rsi14",
    "current_obv_status", "current_total_score", "avg_score_5",
    "avg_score_10", "best_score", "avg_rs5_5", "avg_rs10_5",
    "avg_rsi14_5", "strength_score", "quality_score",
    "performance_score", "market_fit_score", "leader_score",
    "leader_level", "confidence_score",
    "winrate_t1_pct", "avg_return_t1_pct", "samples_t1",
    "winrate_t3_pct", "avg_return_t3_pct", "samples_t3",
    "winrate_t5_pct", "avg_return_t5_pct", "samples_t5",
    "winrate_t10_pct", "avg_return_t10_pct", "samples_t10",
    "best_return_pct", "worst_drawdown_pct", "feature_signature",
    "recommendation", "recommendation_reason", "updated_at",
    "schema_version", "engine_version",
]

PATTERN_COLUMNS = [
    "pattern_id", "feature_signature", "market_regime", "sample_count",
    "symbols_count", "avg_entry_score", "avg_rs5", "avg_rs10",
    "avg_rsi14", "obv_up_rate_pct", "winrate_t3_pct",
    "avg_return_t3_pct", "winrate_t5_pct", "avg_return_t5_pct",
    "winrate_t10_pct", "avg_return_t10_pct", "pattern_score",
    "pattern_level", "first_seen", "last_seen", "updated_at",
    "schema_version", "engine_version",
]

HOF_COLUMNS = [
    "rank", "symbol", "leader_score", "leader_level",
    "confidence_score", "appearances", "persistence_20_pct",
    "best_score", "winrate_t5_pct", "avg_return_t5_pct",
    "winrate_t10_pct", "avg_return_t10_pct", "best_return_pct",
    "worst_drawdown_pct", "first_seen", "last_seen", "updated_at",
]

RECOMMENDATION_COLUMNS = [
    "rank", "symbol", "recommendation", "confidence_score",
    "leader_score", "leader_level", "current_group", "current_price",
    "current_rs5", "current_rs10", "current_rsi14",
    "current_obv_status", "winrate_t5_pct", "avg_return_t5_pct",
    "pattern_match_score", "matched_pattern_id", "reason", "updated_at",
    "ExperienceAdjustment", "ExperienceSamples", "LearnedWinRate",
    "ContinuationScore", "MatchedPattern", "MatchedMarketContext",
    "LearningStatus",
]

# Canonical earning-learning (STEP 1) rank bridge — separate from Leader Memory pattern library.
_EXPERIENCE_MAX_ADJUSTMENT = 8.0
_EXPERIENCE_RANK_WEIGHT = 0.25
EARNING_LEARNING_AUDIT_COLS = (
    "ExperienceAdjustment",
    "ExperienceSamples",
    "LearnedWinRate",
    "ContinuationScore",
    "MatchedPattern",
    "MatchedMarketContext",
    "ContextMatchMode",
    "LearningStatus",
)


@dataclass
class UpdateResult:
    ok: bool
    message: str
    session_date: str = ""
    input_rows: int = 0
    saved_rows: int = 0
    history_rows: int = 0
    brain_rows: int = 0
    pattern_rows: int = 0
    recommendation_rows: int = 0
    warnings: List[str] = field(default_factory=list)


_PROCESS_LOCK = threading.RLock()


class FileLock:
    def __init__(self, path: Path, timeout_seconds: float = 15.0):
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.fd: Optional[int] = None

    def __enter__(self):
        import time
        started = time.time()
        while True:
            try:
                self.fd = os.open(
                    str(self.path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(self.fd, str(os.getpid()).encode("utf-8"))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 120:
                        self.path.unlink(missing_ok=True)
                except Exception:
                    pass
                if time.time() - started > self.timeout_seconds:
                    raise TimeoutError(f"Không lấy được lock: {self.path}")
                time.sleep(0.15)

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.fd is not None:
                os.close(self.fd)
            self.path.unlink(missing_ok=True)
        except Exception:
            pass


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return date.today().isoformat()


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _upper_text(value: Any) -> str:
    return _clean_text(value).upper()


def _normalize_symbol(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    symbol = str(value).strip().upper()
    for suffix in [".VN", ".HO", ".HM", ".HNX", ".UPCOM"]:
        if symbol.endswith(suffix):
            symbol = symbol[:-len(suffix)]
    return symbol


def _safe_float(value: Any, default: float = np.nan) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        if isinstance(value, str):
            value = value.strip().replace("%", "").replace(",", "").replace("−", "-")
            if not value:
                return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {
        "1", "true", "yes", "y", "up", "tăng", "tốt",
        "positive", "green", "xanh", "đạt", "ok",
    }


def _clip(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    x = _safe_float(value, low)
    if math.isnan(x):
        x = low
    return float(min(max(x, low), high))


def _ensure_columns(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    result = df.copy()
    for col in columns:
        if col not in result.columns:
            result[col] = np.nan
    return result[list(columns)]


def _deep_update(target: Dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, Mapping):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _atomic_write_json(data: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=str(path.parent),
        encoding="utf-8", suffix=".tmp"
    ) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        temp_name = tmp.name
    os.replace(temp_name, path)


def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=str(path.parent),
        encoding="utf-8-sig", newline="", suffix=".tmp"
    ) as tmp:
        temp_name = tmp.name
    try:
        df.to_csv(temp_name, index=False, encoding="utf-8-sig")
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _safe_read_csv(path: Path, columns: Optional[Sequence[str]] = None) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=list(columns or []))
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=list(columns or []))
    except Exception as exc:
        logger.exception("READ ERROR %s: %s", path.name, exc)
        return pd.DataFrame(columns=list(columns or []))
    return _ensure_columns(df, columns) if columns else df


def _load_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        _atomic_write_json(DEFAULT_CONFIG, CONFIG_FILE)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        _deep_update(merged, user_cfg)
        return merged
    except Exception:
        logger.exception("CONFIG ERROR")
        _atomic_write_json(DEFAULT_CONFIG, CONFIG_FILE)
        return json.loads(json.dumps(DEFAULT_CONFIG))


def _find_column(df: pd.DataFrame, canonical: str, config: Mapping[str, Any]) -> Optional[str]:
    aliases = config.get("column_aliases", {}).get(canonical, [])
    exact = {str(c): c for c in df.columns}
    lower = {str(c).strip().lower(): c for c in df.columns}
    for alias in aliases:
        if alias in exact:
            return exact[alias]
        key = str(alias).strip().lower()
        if key in lower:
            return lower[key]
    return None


def _series(df: pd.DataFrame, canonical: str, config: Mapping[str, Any], default=np.nan) -> pd.Series:
    col = _find_column(df, canonical, config)
    if col is None:
        return pd.Series([default] * len(df), index=df.index)
    return df[col]


def _numeric_series(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        return pd.to_numeric(
            series.astype(str)
            .str.replace("%", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.replace("−", "-", regex=False),
            errors="coerce",
        )
    return pd.to_numeric(series, errors="coerce")


def _normalize_session_date(value: Any) -> str:
    if value is None or value == "":
        return _today()
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return _today()


def _obv_direction(status: Any, obv_value: Any = np.nan) -> str:
    text = _upper_text(status)
    if any(t in text for t in ["UP", "TĂNG", "DƯƠNG", "MẠNH", "TRÊN", "TỐT", "↑"]):
        return "UP"
    if any(t in text for t in ["DOWN", "GIẢM", "ÂM", "YẾU", "DƯỚI", "XẤU", "↓"]):
        return "DOWN"
    x = _safe_float(obv_value)
    if not math.isnan(x):
        if x > 0:
            return "UP"
        if x < 0:
            return "DOWN"
    return "NEUTRAL"


def _bucket_rs(value: Any) -> str:
    x = _safe_float(value)
    if math.isnan(x): return "RS_NA"
    if x >= 90: return "RS_90P"
    if x >= 75: return "RS_75_89"
    if x >= 60: return "RS_60_74"
    if x >= 40: return "RS_40_59"
    return "RS_LT40"


def _bucket_rsi(value: Any) -> str:
    x = _safe_float(value)
    if math.isnan(x): return "RSI_NA"
    if x >= 70: return "RSI_70P"
    if x >= 58: return "RSI_58_69"
    if x >= 50: return "RSI_50_57"
    if x >= 40: return "RSI_40_49"
    if x >= 30: return "RSI_30_39"
    return "RSI_LT30"


def _bucket_score(value: Any) -> str:
    x = _safe_float(value)
    if math.isnan(x): return "SCORE_NA"
    if x >= 85: return "SCORE_85P"
    if x >= 70: return "SCORE_70_84"
    if x >= 55: return "SCORE_55_69"
    if x >= 40: return "SCORE_40_54"
    return "SCORE_LT40"


def _normalize_regime(value: Any) -> str:
    text = _upper_text(value)
    if not text:
        return "UNKNOWN"
    if any(t in text for t in ["UPTREND", "MÙA XUÂN", "BULL", "TỐT"]):
        return "UPTREND"
    if any(t in text for t in ["DOWNTREND", "MÙA ĐÔNG", "BEAR", "XẤU"]):
        return "DOWNTREND"
    if any(t in text for t in ["SIDEWAY", "TRUNG TÍNH", "NEUTRAL"]):
        return "SIDEWAY"
    return text[:30]


def _feature_signature(row: Mapping[str, Any]) -> str:
    flags = []
    for name in ["storm", "early", "pullback", "green2", "dryup"]:
        if _safe_bool(row.get(name)):
            flags.append(name.upper())
    return "|".join([
        _bucket_rs(row.get("rs5")),
        _bucket_rs(row.get("rs10")),
        _bucket_rsi(row.get("rsi14")),
        _bucket_score(row.get("total_score")),
        f"OBV_{_obv_direction(row.get('obv_status'), row.get('obv'))}",
        f"GROUP_{(_upper_text(row.get('group')) or 'NA')[:24]}",
        f"REGIME_{_normalize_regime(row.get('market_regime'))}",
        "+".join(flags) if flags else "NOFLAG",
    ])


def _prepare_snapshot(
    scan_df: pd.DataFrame,
    session_date: Optional[Any],
    market_real: Optional[Any],
    market_forecast: Optional[Any],
    market_regime: Optional[Any],
    config: Mapping[str, Any],
) -> Tuple[pd.DataFrame, List[str]]:
    warnings: List[str] = []
    if not isinstance(scan_df, pd.DataFrame):
        raise TypeError("scan_df phải là pandas.DataFrame")
    if scan_df.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS), ["scan_df đang rỗng"]

    symbol_col = _find_column(scan_df, "symbol", config)
    if symbol_col is None:
        raise ValueError("Không tìm thấy cột symbol/ticker/code/MÃ")

    frame = pd.DataFrame(index=scan_df.index)
    frame["session_date"] = _normalize_session_date(session_date)
    frame["snapshot_time"] = _now()
    frame["symbol"] = scan_df[symbol_col].map(_normalize_symbol)

    names = [
        "price", "group", "sector", "rs5", "rs10", "rsi14", "obv",
        "obv_status", "total_score", "trend_score", "buy_score",
        "persistence", "evolution", "recent_change", "ema9_ma20_slope",
        "dist_from_ema9_pct",         "volume", "vol_ma20", "market_real",
        "market_forecast", "market_regime", "storm", "early", "pullback",
        "green2", "dryup", "health_group", "action", "reason",
    ]
    for name in names:
        frame[name] = _series(scan_df, name, config)

    if market_real is not None:
        frame["market_real"] = market_real
    if market_forecast is not None:
        frame["market_forecast"] = market_forecast
    if market_regime is not None:
        frame["market_regime"] = market_regime

    frame = frame.rename(columns={"persistence": "source_persistence"})

    numeric_cols = [
        "price", "rs5", "rs10", "rsi14", "obv", "total_score",
        "trend_score", "buy_score", "source_persistence", "evolution",
        "recent_change", "ema9_ma20_slope", "dist_from_ema9_pct",
        "volume", "vol_ma20", "market_real", "market_forecast",
    ]
    for col in numeric_cols:
        frame[col] = _numeric_series(frame[col])

    for col in ["storm", "early", "pullback", "green2", "dryup"]:
        frame[col] = frame[col].map(_safe_bool)

    for col in ["group", "sector", "obv_status", "market_regime", "action", "reason"]:
        frame[col] = frame[col].map(_clean_text)

    frame["volume_ratio"] = np.where(
        frame["vol_ma20"].fillna(0) > 0,
        frame["volume"] / frame["vol_ma20"],
        np.nan,
    )
    frame["feature_signature"] = frame.apply(
        lambda r: _feature_signature(r.to_dict()), axis=1
    )
    frame["schema_version"] = SCHEMA_VERSION
    frame["engine_version"] = ENGINE_VERSION
    frame = frame[frame["symbol"] != ""].copy()

    dup = int(frame.duplicated(subset=["symbol"], keep="last").sum())
    if dup:
        warnings.append(f"Đã loại {dup} dòng trùng mã.")
        frame = frame.drop_duplicates(subset=["symbol"], keep="last")

    return _ensure_columns(frame, HISTORY_COLUMNS).reset_index(drop=True), warnings


def _merge_snapshot(history: pd.DataFrame, snapshot: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    history = _ensure_columns(history, HISTORY_COLUMNS)
    snapshot = _ensure_columns(snapshot, HISTORY_COLUMNS)
    keys = config.get("dedupe_keys", ["session_date", "symbol"])

    incoming = set(zip(snapshot[keys[0]].astype(str), snapshot[keys[1]].astype(str)))
    if not history.empty:
        existing = list(zip(history[keys[0]].astype(str), history[keys[1]].astype(str)))
        history = history.loc[[key not in incoming for key in existing]].copy()

    combined = pd.concat([history, snapshot], ignore_index=True)
    combined = combined.drop_duplicates(subset=keys, keep="last")
    return combined.sort_values(["session_date", "symbol"], kind="stable").reset_index(drop=True)


def _update_outcomes(history: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    if history.empty:
        return _ensure_columns(history, HISTORY_COLUMNS)

    result = _ensure_columns(history, HISTORY_COLUMNS)
    result["session_date"] = pd.to_datetime(result["session_date"], errors="coerce")
    result["price"] = pd.to_numeric(result["price"], errors="coerce")

    thresholds = config.get("win_threshold_pct", {})
    parts = []

    for _, g in result.groupby("symbol", sort=False):
        g = g.sort_values("session_date", kind="stable").copy()
        prices = g["price"].to_numpy(dtype=float)
        n = len(g)

        for h in [1, 3, 5, 10]:
            future_price = np.full(n, np.nan)
            future_return = np.full(n, np.nan)
            future_win = np.full(n, np.nan)
            max_gain = np.full(n, np.nan)
            max_dd = np.full(n, np.nan)
            evaluated = np.zeros(n, dtype=bool)

            for i in range(n):
                target = i + h
                entry = prices[i]
                if target >= n or not np.isfinite(entry) or entry <= 0:
                    continue
                exit_price = prices[target]
                if not np.isfinite(exit_price):
                    continue

                window = prices[i + 1: target + 1]
                valid = window[np.isfinite(window)]

                future_price[i] = exit_price
                future_return[i] = (exit_price / entry - 1.0) * 100.0
                future_win[i] = float(
                    future_return[i] >= float(thresholds.get(str(h), 0.0))
                )
                if len(valid):
                    max_gain[i] = (np.max(valid) / entry - 1.0) * 100.0
                    max_dd[i] = (np.min(valid) / entry - 1.0) * 100.0
                evaluated[i] = True

            g[f"price_t{h}"] = future_price
            g[f"return_t{h}_pct"] = np.round(future_return, 4)
            g[f"win_t{h}"] = future_win
            g[f"max_gain_t{h}_pct"] = np.round(max_gain, 4)
            g[f"max_drawdown_t{h}_pct"] = np.round(max_dd, 4)
            g[f"evaluated_t{h}"] = evaluated

        parts.append(g)

    result = pd.concat(parts, ignore_index=True)
    result["session_date"] = result["session_date"].dt.strftime("%Y-%m-%d")
    return _ensure_columns(
        result.sort_values(["session_date", "symbol"], kind="stable").reset_index(drop=True),
        HISTORY_COLUMNS,
    )


def _group_quality(value: Any, config: Mapping[str, Any]) -> float:
    text = _upper_text(value)
    mapping = config.get("group_quality_map", {})
    if text in mapping:
        return float(mapping[text])
    for key, score in mapping.items():
        if _upper_text(key) in text or text in _upper_text(key):
            return float(score)
    return 50.0


def _mean_tail(series: pd.Series, size: int) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().tail(size)
    return round(float(values.mean()), 2) if len(values) else np.nan


def _aggregate_horizon(g: pd.DataFrame, h: int) -> Tuple[float, float, int]:
    mask = g[f"evaluated_t{h}"].astype(str).str.lower().isin(["true", "1"])
    e = g[mask]
    wins = pd.to_numeric(e[f"win_t{h}"], errors="coerce").dropna()
    rets = pd.to_numeric(e[f"return_t{h}_pct"], errors="coerce").dropna()
    samples = len(wins)
    winrate = round(float(wins.mean() * 100), 2) if samples else np.nan
    avg_return = round(float(rets.mean()), 2) if len(rets) else np.nan
    return winrate, avg_return, samples


def _strength_score(row: Mapping[str, Any]) -> float:
    pieces = []
    rs5 = _safe_float(row.get("current_rs5"))
    rs10 = _safe_float(row.get("current_rs10"))
    rsi = _safe_float(row.get("current_rsi14"))
    total = _safe_float(row.get("current_total_score"))

    if not math.isnan(rs5): pieces.append((_clip(rs5), 0.30))
    if not math.isnan(rs10): pieces.append((_clip(rs10), 0.30))
    if not math.isnan(rsi):
        pieces.append((_clip(100 - min(abs(rsi - 62) * 2.6, 100)), 0.20))
    if not math.isnan(total): pieces.append((_clip(total), 0.20))

    if not pieces:
        return 0.0
    w = sum(x[1] for x in pieces)
    return round(sum(v * wt for v, wt in pieces) / w, 2)


def _performance_score(row: Mapping[str, Any]) -> float:
    weights = {1: 0.10, 3: 0.20, 5: 0.30, 10: 0.40}
    parts = []
    for h, wt in weights.items():
        winrate = _safe_float(row.get(f"winrate_t{h}_pct"))
        avg_return = _safe_float(row.get(f"avg_return_t{h}_pct"))
        samples = int(_safe_float(row.get(f"samples_t{h}"), 0))
        if samples <= 0 or math.isnan(winrate):
            continue
        ret_component = 50 if math.isnan(avg_return) else _clip(50 + avg_return * 5)
        score = winrate * 0.7 + ret_component * 0.3
        score *= 0.5 + 0.5 * min(samples / 10, 1)
        parts.append((score, wt))
    if not parts:
        return 50.0
    total_w = sum(w for _, w in parts)
    return round(sum(v * w for v, w in parts) / total_w, 2)


def _market_fit_score(g: pd.DataFrame) -> float:
    mask = g["evaluated_t5"].astype(str).str.lower().isin(["true", "1"])
    e = g[mask]
    if e.empty:
        return 50.0
    m = pd.to_numeric(e["market_real"], errors="coerce")
    r = pd.to_numeric(e["return_t5_pct"], errors="coerce")
    valid = m.notna() & r.notna()
    if not valid.any():
        return 50.0
    m, r = m[valid], r[valid]
    score = 50.0
    if (m >= 6).any():
        score += np.clip(r[m >= 6].mean() * 4, -25, 25)
    if (m < 6).any():
        score += np.clip(r[m < 6].mean() * 2, -20, 20)
    return round(_clip(score), 2)


def _confidence_score(row: Mapping[str, Any]) -> float:
    samples = sum(int(_safe_float(row.get(f"samples_t{h}"), 0)) for h in [1, 3, 5, 10])
    appearances = int(_safe_float(row.get("appearances"), 0))
    persistence = _safe_float(row.get("persistence_20_pct"), 0)
    return round(_clip(
        min(samples / 30, 1) * 50
        + min(appearances / 30, 1) * 25
        + _clip(persistence) * 0.25
    ), 2)


def _leader_level(score: Any, confidence: Any) -> str:
    s, c = _safe_float(score, 0), _safe_float(confidence, 0)
    if s >= 88 and c >= 65: return "👑 SIÊU LEADER"
    if s >= 80 and c >= 50: return "⭐⭐⭐⭐⭐ LEADER A+"
    if s >= 72: return "⭐⭐⭐⭐ LEADER A"
    if s >= 62: return "⭐⭐⭐ LEADER B"
    if s >= 52: return "⭐⭐ THEO DÕI"
    return "⭐ CHƯA ĐỦ CHẤT LƯỢNG"


def _recommend(row: Mapping[str, Any]) -> Tuple[str, str]:
    score = _safe_float(row.get("leader_score"), 0)
    confidence = _safe_float(row.get("confidence_score"), 0)
    rs5 = _safe_float(row.get("current_rs5"))
    rs10 = _safe_float(row.get("current_rs10"))
    rsi = _safe_float(row.get("current_rsi14"))
    obv = _upper_text(row.get("current_obv_status"))
    group = _upper_text(row.get("current_group"))
    persistence = _safe_float(row.get("persistence_20_pct"), 0)
    win5 = _safe_float(row.get("winrate_t5_pct"))

    positives, warnings = [], []

    if not math.isnan(rs5) and not math.isnan(rs10):
        if rs5 > rs10 and rs10 >= 60:
            positives.append("RS5 > RS10")
        elif rs5 < rs10:
            warnings.append("RS ngắn hạn chậm lại")

    if not math.isnan(rsi):
        if 50 <= rsi <= 70:
            positives.append("RSI khỏe")
        elif rsi > 75:
            warnings.append("RSI cao")
        elif rsi < 45:
            warnings.append("RSI yếu")

    if obv == "UP":
        positives.append("OBV xác nhận")
    elif obv == "DOWN":
        warnings.append("OBV chưa xác nhận")

    if persistence >= 60:
        positives.append("độ bền tốt")
    elif persistence < 25:
        warnings.append("mới xuất hiện")

    if not math.isnan(win5) and win5 >= 65:
        positives.append(f"Winrate T+5 {win5:.0f}%")

    weak = any(t in group for t in ["YẾU", "RẤT YẾU", "YẾU DẦN"])
    if weak:
        action = "TRÁNH / CHỜ PHỤC HỒI"
    elif score >= 80 and confidence >= 55 and not warnings:
        action = "ƯU TIÊN CAO"
    elif score >= 72 and confidence >= 35:
        action = "THEO DÕI MUA"
    elif score >= 60:
        action = "THEO DÕI"
    else:
        action = "CHƯA HÀNH ĐỘNG"

    reason = ". ".join(positives[:4])
    if warnings:
        reason += (". " if reason else "") + "Lưu ý: " + "; ".join(warnings[:3])
    return action, reason or "Chưa đủ dữ liệu xác nhận."


def _build_brain(history: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=BRAIN_COLUMNS)

    data = _ensure_columns(history, HISTORY_COLUMNS).copy()
    data["session_date_dt"] = pd.to_datetime(data["session_date"], errors="coerce")
    all_dates = sorted(data["session_date"].astype(str).unique().tolist())
    recent_dates = set(all_dates[-int(config.get("persistence_window", 20)):])
    weights = config.get("leader_score_weights", {})
    rows = []

    for symbol, g in data.groupby("symbol", sort=False):
        g = g.sort_values("session_date_dt", kind="stable").copy()
        latest = g.iloc[-1]
        appearances = int(g["session_date"].nunique())
        active_days = int(g[g["session_date"].astype(str).isin(recent_dates)]["session_date"].nunique())
        denominator = min(len(recent_dates), int(config.get("persistence_window", 20)))
        persistence = active_days / denominator * 100 if denominator else 0

        row = {
            "symbol": symbol,
            "first_seen": str(g["session_date"].iloc[0]),
            "last_seen": str(g["session_date"].iloc[-1]),
            "appearances": appearances,
            "active_days_20": active_days,
            "persistence_20_pct": round(persistence, 2),
            "current_group": _clean_text(latest.get("group")),
            "current_sector": _clean_text(latest.get("sector")),
            "current_price": _safe_float(latest.get("price")),
            "current_rs5": _safe_float(latest.get("rs5")),
            "current_rs10": _safe_float(latest.get("rs10")),
            "current_rsi14": _safe_float(latest.get("rsi14")),
            "current_obv_status": _obv_direction(latest.get("obv_status"), latest.get("obv")),
            "current_total_score": _safe_float(latest.get("total_score")),
            "avg_score_5": _mean_tail(g["total_score"], 5),
            "avg_score_10": _mean_tail(g["total_score"], 10),
            "best_score": _safe_float(pd.to_numeric(g["total_score"], errors="coerce").max()),
            "avg_rs5_5": _mean_tail(g["rs5"], 5),
            "avg_rs10_5": _mean_tail(g["rs10"], 5),
            "avg_rsi14_5": _mean_tail(g["rsi14"], 5),
            "feature_signature": _clean_text(latest.get("feature_signature")),
            "updated_at": _now(),
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
        }

        for h in [1, 3, 5, 10]:
            winrate, avg_return, samples = _aggregate_horizon(g, h)
            row[f"winrate_t{h}_pct"] = winrate
            row[f"avg_return_t{h}_pct"] = avg_return
            row[f"samples_t{h}"] = samples

        returns = pd.concat(
            [pd.to_numeric(g[f"return_t{h}_pct"], errors="coerce") for h in [1,3,5,10]],
            ignore_index=True
        ).dropna()
        drawdowns = pd.concat(
            [pd.to_numeric(g[f"max_drawdown_t{h}_pct"], errors="coerce") for h in [1,3,5,10]],
            ignore_index=True
        ).dropna()

        row["best_return_pct"] = round(float(returns.max()), 2) if len(returns) else np.nan
        row["worst_drawdown_pct"] = round(float(drawdowns.min()), 2) if len(drawdowns) else np.nan

        row["strength_score"] = _strength_score(row)
        row["quality_score"] = round(_group_quality(row["current_group"], config), 2)
        row["performance_score"] = _performance_score(row)
        row["market_fit_score"] = _market_fit_score(g)

        leader_score = (
            row["strength_score"] * float(weights.get("strength", 0.30))
            + _clip(row["persistence_20_pct"]) * float(weights.get("persistence", 0.20))
            + row["quality_score"] * float(weights.get("quality", 0.20))
            + row["performance_score"] * float(weights.get("performance", 0.20))
            + row["market_fit_score"] * float(weights.get("market_fit", 0.10))
        )
        row["leader_score"] = round(_clip(leader_score), 2)
        row["confidence_score"] = _confidence_score(row)
        row["leader_level"] = _leader_level(row["leader_score"], row["confidence_score"])
        row["recommendation"], row["recommendation_reason"] = _recommend(row)
        rows.append(row)

    brain = _ensure_columns(pd.DataFrame(rows), BRAIN_COLUMNS)
    brain = brain.sort_values(
        ["leader_score", "confidence_score", "persistence_20_pct"],
        ascending=[False, False, False],
        kind="stable"
    ).reset_index(drop=True)
    return brain.head(int(config.get("max_brain_rows", 5000)))


def _pattern_level(score: Any, samples: Any) -> str:
    s, n = _safe_float(score, 0), int(_safe_float(samples, 0))
    if n < 5: return "MẪU MỚI"
    if s >= 82: return "🏆 MẪU HÌNH TINH HOA"
    if s >= 72: return "⭐⭐⭐⭐ MẪU MẠNH"
    if s >= 62: return "⭐⭐⭐ MẪU KHÁ"
    return "ĐANG HỌC"


def _build_patterns(history: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=PATTERN_COLUMNS)

    data = _ensure_columns(history, HISTORY_COLUMNS).copy()
    data["market_regime_norm"] = data["market_regime"].map(_normalize_regime)
    rows = []

    for (signature, regime), g in data.groupby(
        ["feature_signature", "market_regime_norm"], dropna=False, sort=False
    ):
        row = {
            "feature_signature": _clean_text(signature),
            "market_regime": _clean_text(regime) or "UNKNOWN",
            "sample_count": int(len(g)),
            "symbols_count": int(g["symbol"].nunique()),
            "avg_entry_score": _mean_tail(g["total_score"], len(g)),
            "avg_rs5": _mean_tail(g["rs5"], len(g)),
            "avg_rs10": _mean_tail(g["rs10"], len(g)),
            "avg_rsi14": _mean_tail(g["rsi14"], len(g)),
            "obv_up_rate_pct": round(
                g.apply(lambda r: _obv_direction(r.get("obv_status"), r.get("obv")) == "UP", axis=1).mean() * 100,
                2
            ),
            "first_seen": str(g["session_date"].min()),
            "last_seen": str(g["session_date"].max()),
            "updated_at": _now(),
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
        }

        for h in [3, 5, 10]:
            winrate, avg_return, _ = _aggregate_horizon(g, h)
            row[f"winrate_t{h}_pct"] = winrate
            row[f"avg_return_t{h}_pct"] = avg_return

        win5 = _safe_float(row.get("winrate_t5_pct"), 50)
        win10 = _safe_float(row.get("winrate_t10_pct"), 50)
        avg5 = _safe_float(row.get("avg_return_t5_pct"), 0)
        avg10 = _safe_float(row.get("avg_return_t10_pct"), 0)
        if math.isnan(win5): win5 = 50
        if math.isnan(win10): win10 = 50
        if math.isnan(avg5): avg5 = 0
        if math.isnan(avg10): avg10 = 0

        sample_score = min(row["sample_count"] / 30, 1) * 100
        return_score = _clip(50 + avg5 * 4 + avg10 * 2)
        row["pattern_score"] = round(_clip(
            win5 * 0.30 + win10 * 0.25 + return_score * 0.20
            + sample_score * 0.15 + row["obv_up_rate_pct"] * 0.10
        ), 2)
        row["pattern_level"] = _pattern_level(row["pattern_score"], row["sample_count"])
        key = f"{row['feature_signature']}|{row['market_regime']}"
        row["pattern_id"] = "P-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10].upper()
        rows.append(row)

    patterns = _ensure_columns(pd.DataFrame(rows), PATTERN_COLUMNS)
    patterns = patterns.sort_values(
        ["pattern_score", "sample_count"],
        ascending=[False, False],
        kind="stable"
    ).reset_index(drop=True)
    return patterns.head(int(config.get("max_pattern_rows", 500)))


def _build_hof(brain: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    if brain.empty:
        return pd.DataFrame(columns=HOF_COLUMNS)
    hof = brain[
        (pd.to_numeric(brain["appearances"], errors="coerce").fillna(0) >= 3)
        | (pd.to_numeric(brain["leader_score"], errors="coerce").fillna(0) >= 70)
    ].copy()
    hof = hof.sort_values(
        ["leader_score", "confidence_score", "best_return_pct"],
        ascending=[False, False, False],
        kind="stable"
    ).reset_index(drop=True)
    hof["rank"] = np.arange(1, len(hof) + 1)
    return _ensure_columns(hof, HOF_COLUMNS).head(
        int(config.get("max_hall_of_fame_rows", 200))
    )


def _tokens(signature: Any) -> set:
    return {x for x in _clean_text(signature).split("|") if x}


def _similarity(a: Any, b: Any) -> float:
    aa, bb = _tokens(a), _tokens(b)
    if not aa or not bb:
        return 0.0
    return round(len(aa & bb) / len(aa | bb) * 100, 2)


def _best_pattern(signature: Any, patterns: pd.DataFrame) -> Tuple[float, str]:
    best_score, best_id = 0.0, ""
    for _, p in patterns.head(200).iterrows():
        score = _similarity(signature, p.get("feature_signature")) * 0.70 + _safe_float(p.get("pattern_score"), 0) * 0.30
        if score > best_score:
            best_score = score
            best_id = _clean_text(p.get("pattern_id"))
    return round(best_score, 2), best_id


def _effective_experience_adjustment(
    experience_adjustment: Any,
    market_real: Optional[Any],
    *,
    obv_status: Any = None,
) -> float:
    """
    Safety-first gate for canonical earning-learning rank influence.
    leader_score is independent of Buy Elite; this applies ExperienceAdjustment once here.
    """
    adj = _safe_float(experience_adjustment, 0.0)
    if math.isnan(adj):
        adj = 0.0
    adj = float(np.clip(adj, -_EXPERIENCE_MAX_ADJUSTMENT, _EXPERIENCE_MAX_ADJUSTMENT))
    if adj == 0.0:
        return 0.0

    mr = _safe_float(market_real, np.nan)
    if not math.isnan(mr) and mr < 6:
        adj = min(adj, 0.0)

    obv = _upper_text(obv_status)
    if obv == "DOWN" and adj > 0:
        adj = 0.0

    return adj


def _build_experience_frame(
    snapshot: pd.DataFrame,
    market_real: Optional[Any],
    market_forecast: Optional[Any],
) -> pd.DataFrame:
    """
    Attach canonical T3/T5/T10 earning-learning evidence via STEP 1 lookup.
    Does not recalculate knowledge; reuses apply_learning_experience().
    """
    if snapshot is None or snapshot.empty or "symbol" not in snapshot.columns:
        return pd.DataFrame()

    frame = snapshot.copy()
    if "pull" not in frame.columns and "pullback" in frame.columns:
        frame["pull"] = frame["pullback"]

    try:
        from modules.earning_learning import apply_learning_experience

        mr = _safe_float(market_real, np.nan)
        mf = _safe_float(market_forecast, np.nan)
        return apply_learning_experience(
            frame,
            market_real=mr if not math.isnan(mr) else np.nan,
            market_forecast=mf if not math.isnan(mf) else np.nan,
        )
    except Exception:
        logger.exception("Canonical earning-learning attach failed safely")
        return frame


def _experience_row_map(experience_df: pd.DataFrame) -> Dict[str, Mapping[str, Any]]:
    if experience_df is None or experience_df.empty or "symbol" not in experience_df.columns:
        return {}

    lookup: Dict[str, Mapping[str, Any]] = {}
    for _, row in experience_df.iterrows():
        symbol = _normalize_symbol(row.get("symbol"))
        if symbol:
            lookup[symbol] = row
    return lookup


def _build_recommendations(
    brain: pd.DataFrame,
    patterns: pd.DataFrame,
    config: Mapping[str, Any],
    *,
    experience_df: Optional[pd.DataFrame] = None,
    market_real: Optional[Any] = None,
    market_forecast: Optional[Any] = None,
) -> pd.DataFrame:
    if brain.empty:
        return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)

    experience_by_symbol = _experience_row_map(experience_df)
    rows = []
    for _, item in brain.iterrows():
        action = _clean_text(item.get("recommendation"))
        if action in {"TRÁNH / CHỜ PHỤC HỒI", "CHƯA HÀNH ĐỘNG"}:
            continue
        match_score, pattern_id = _best_pattern(item.get("feature_signature"), patterns)
        symbol = _normalize_symbol(item.get("symbol"))
        exp = experience_by_symbol.get(symbol, {})
        experience_adj = _effective_experience_adjustment(
            exp.get("ExperienceAdjustment", 0.0),
            market_real,
            obv_status=item.get("current_obv_status"),
        )
        reason = _clean_text(item.get("recommendation_reason"))
        raw_adj = _safe_float(exp.get("ExperienceAdjustment", 0.0), 0.0)
        learning_status = _clean_text(exp.get("LearningStatus", ""))
        if not math.isnan(raw_adj) and raw_adj > 0:
            reason = (reason + ". " if reason else "") + f"Earning-learning +{raw_adj:.1f}"
        elif not math.isnan(raw_adj) and raw_adj < 0:
            reason = (reason + ". " if reason else "") + f"Earning-learning {raw_adj:.1f}"
        if learning_status and learning_status not in {"READY_FOR_CONNECTION", ""}:
            reason = (reason + ". " if reason else "") + f"LearningStatus={learning_status}"

        row = {
            "symbol": item.get("symbol"),
            "recommendation": action,
            "confidence_score": item.get("confidence_score"),
            "leader_score": item.get("leader_score"),
            "leader_level": item.get("leader_level"),
            "current_group": item.get("current_group"),
            "current_price": item.get("current_price"),
            "current_rs5": item.get("current_rs5"),
            "current_rs10": item.get("current_rs10"),
            "current_rsi14": item.get("current_rsi14"),
            "current_obv_status": item.get("current_obv_status"),
            "winrate_t5_pct": item.get("winrate_t5_pct"),
            "avg_return_t5_pct": item.get("avg_return_t5_pct"),
            "pattern_match_score": match_score,
            "matched_pattern_id": pattern_id,
            "reason": reason,
            "updated_at": _now(),
            "_experience_rank_adj": experience_adj,
        }
        for col in EARNING_LEARNING_AUDIT_COLS:
            row[col] = exp.get(col, np.nan if col in {
                "LearnedWinRate", "ContinuationScore",
            } else "")
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)

    rec = pd.DataFrame(rows)
    # Leader Memory pattern library + leader history scores (unchanged weights).
    # Canonical earning-learning enters once via verified ExperienceAdjustment.
    rec["_rank_score"] = (
        pd.to_numeric(rec["leader_score"], errors="coerce").fillna(0) * 0.55
        + pd.to_numeric(rec["confidence_score"], errors="coerce").fillna(0) * 0.20
        + pd.to_numeric(rec["pattern_match_score"], errors="coerce").fillna(0) * 0.25
        + pd.to_numeric(rec["_experience_rank_adj"], errors="coerce").fillna(0)
        * _EXPERIENCE_RANK_WEIGHT
    )
    rec = rec.sort_values(["_rank_score", "leader_score"], ascending=[False, False], kind="stable").reset_index(drop=True)
    rec["rank"] = np.arange(1, len(rec) + 1)
    rec = rec.drop(columns=["_rank_score", "_experience_rank_adj"])
    return _ensure_columns(rec, RECOMMENDATION_COLUMNS).head(
        int(config.get("max_recommendation_rows", 100))
    )


def create_empty_memory() -> pd.DataFrame:
    return pd.DataFrame(columns=BRAIN_COLUMNS)


def load_memory() -> pd.DataFrame:
    brain = _safe_read_csv(BRAIN_FILE, BRAIN_COLUMNS)
    if not brain.empty:
        return brain

    if LEGACY_MEMORY_FILE.exists():
        legacy = _safe_read_csv(LEGACY_MEMORY_FILE)
        if not legacy.empty and "symbol" in legacy.columns:
            migrated = create_empty_memory()
            migrated["symbol"] = legacy["symbol"].map(_normalize_symbol)
            if "first_seen" in legacy.columns:
                migrated["first_seen"] = legacy["first_seen"]
            if "last_seen" in legacy.columns:
                migrated["last_seen"] = legacy["last_seen"]
            migrated["appearances"] = 1
            migrated["active_days_20"] = 1
            migrated["persistence_20_pct"] = 100.0
            migrated["updated_at"] = _now()
            migrated["schema_version"] = SCHEMA_VERSION
            migrated["engine_version"] = ENGINE_VERSION
            return migrated[migrated["symbol"] != ""].reset_index(drop=True)

    return create_empty_memory()


def save_memory(memory_df: pd.DataFrame) -> None:
    _atomic_write_csv(
        _ensure_columns(memory_df if memory_df is not None else create_empty_memory(), BRAIN_COLUMNS),
        BRAIN_FILE
    )


def load_history(limit: Optional[int] = None) -> pd.DataFrame:
    df = _safe_read_csv(HISTORY_FILE, HISTORY_COLUMNS)
    return df.tail(int(limit)).reset_index(drop=True) if limit else df


def load_pattern_library() -> pd.DataFrame:
    return _safe_read_csv(PATTERN_FILE, PATTERN_COLUMNS)


def load_hall_of_fame() -> pd.DataFrame:
    return _safe_read_csv(HALL_OF_FAME_FILE, HOF_COLUMNS)


def load_recommendations() -> pd.DataFrame:
    return _safe_read_csv(RECOMMENDATION_FILE, RECOMMENDATION_COLUMNS)


def update_memory(
    df_today: pd.DataFrame,
    session_date: Optional[Any] = None,
    market_real: Optional[Any] = None,
    market_forecast: Optional[Any] = None,
    market_regime: Optional[Any] = None,
    raise_errors: bool = False,
) -> pd.DataFrame: 
    config = _load_config()
    try:
        with _PROCESS_LOCK:
            with FileLock(LOCK_FILE):
                snapshot, warnings = _prepare_snapshot(
                    df_today, session_date, market_real,
                    market_forecast, market_regime, config
                )
                if snapshot.empty:
                    logger.warning("SNAPSHOT EMPTY: %s", warnings)
                    return load_memory()

                history = _safe_read_csv(HISTORY_FILE, HISTORY_COLUMNS)
                history = _merge_snapshot(history, snapshot, config)
                history = _update_outcomes(history, config)

                brain = _build_brain(history, config)
                patterns = _build_patterns(history, config)
                hof = _build_hof(brain, config)
                experience_df = _build_experience_frame(
                    snapshot,
                    market_real=market_real,
                    market_forecast=market_forecast,
                )
                rec = _build_recommendations(
                    brain,
                    patterns,
                    config,
                    experience_df=experience_df,
                    market_real=market_real,
                    market_forecast=market_forecast,
                )

                _atomic_write_csv(history, HISTORY_FILE)
                _atomic_write_csv(brain, BRAIN_FILE)
                _atomic_write_csv(patterns, PATTERN_FILE)
                _atomic_write_csv(hof, HALL_OF_FAME_FILE)
                _atomic_write_csv(rec, RECOMMENDATION_FILE)

                legacy_cols = [
                    "symbol", "first_seen", "last_seen", "appearances",
                    "persistence_20_pct", "current_group", "current_rs5",
                    "current_rs10", "current_rsi14", "current_obv_status",
                    "leader_score", "leader_level", "confidence_score",
                    "recommendation",
                ]
                _atomic_write_csv(
                    brain[[c for c in legacy_cols if c in brain.columns]].copy(),
                    LEGACY_MEMORY_FILE,
                )

                logger.info(
                    "UPDATE OK | date=%s input=%s history=%s brain=%s patterns=%s rec=%s",
                    _normalize_session_date(session_date),
                    len(df_today), len(history), len(brain), len(patterns), len(rec)
                )
                return brain

    except Exception as exc:
        logger.exception("UPDATE MEMORY ERROR: %s", exc)
        if raise_errors:
            raise
        return load_memory()


def update_memory_with_result(
    df_today: pd.DataFrame,
    session_date: Optional[Any] = None,
    market_real: Optional[Any] = None,
    market_forecast: Optional[Any] = None,
    market_regime: Optional[Any] = None,
) -> UpdateResult:
    try:
        brain = update_memory(
            df_today, session_date, market_real,
            market_forecast, market_regime, True
        )
        return UpdateResult(
            ok=True,
            message="Cập nhật thành công.",
            session_date=_normalize_session_date(session_date),
            input_rows=len(df_today),
            saved_rows=len(df_today),
            history_rows=len(load_history()),
            brain_rows=len(brain),
            pattern_rows=len(load_pattern_library()),
            recommendation_rows=len(load_recommendations()),
        )
    except Exception as exc:
        return UpdateResult(
            ok=False,
            message=str(exc),
            session_date=_normalize_session_date(session_date),
        )


def get_active_leaders(limit: int = 30) -> pd.DataFrame:
    brain = load_memory()
    cols = [
        "symbol", "leader_level", "leader_score", "confidence_score",
        "persistence_20_pct", "current_group", "current_price",
        "current_rs5", "current_rs10", "current_rsi14",
        "current_obv_status", "winrate_t5_pct", "avg_return_t5_pct",
        "recommendation", "recommendation_reason",
    ]
    return brain[[c for c in cols if c in brain.columns]].head(limit).reset_index(drop=True)


def get_intelligence_tables(
    leader_limit: int = 30,
    pattern_limit: int = 30,
    hof_limit: int = 50,
    recommendation_limit: int = 30,
) -> Dict[str, pd.DataFrame]:
    return {
        "active_leaders": get_active_leaders(leader_limit),
        "brain_score": load_memory().head(leader_limit),
        "hall_of_fame": load_hall_of_fame().head(hof_limit),
        "pattern_library": load_pattern_library().head(pattern_limit),
        "ai_recommendation": load_recommendations().head(recommendation_limit),
    }


def get_engine_status() -> Dict[str, Any]:
    return {
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "brain_dir": str(BRAIN_DIR),
        "files": {
            name: {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
            for name, path in {
                "history": HISTORY_FILE,
                "brain": BRAIN_FILE,
                "patterns": PATTERN_FILE,
                "hall_of_fame": HALL_OF_FAME_FILE,
                "recommendations": RECOMMENDATION_FILE,
                "config": CONFIG_FILE,
                "log": LOG_FILE,
            }.items()
        },
    }


def backup_brain(destination_dir: Optional[Any] = None) -> Path:
    destination = (
        Path(destination_dir)
        if destination_dir is not None
        else BRAIN_DIR / "backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    destination.mkdir(parents=True, exist_ok=True)
    for path in [
        HISTORY_FILE, BRAIN_FILE, PATTERN_FILE, HALL_OF_FAME_FILE,
        RECOMMENDATION_FILE, CONFIG_FILE, LOG_FILE, LEGACY_MEMORY_FILE
    ]:
        if path.exists():
            shutil.copy2(path, destination / path.name)
    return destination


def rebuild_all() -> Dict[str, int]:
    config = _load_config()
    with _PROCESS_LOCK:
        with FileLock(LOCK_FILE):
            history = _safe_read_csv(HISTORY_FILE, HISTORY_COLUMNS)
            history = _update_outcomes(history, config)
            brain = _build_brain(history, config)  
            patterns = _build_patterns(history, config)
            hof = _build_hof(brain, config)
            rec = _build_recommendations(brain, patterns, config)

            _atomic_write_csv(history, HISTORY_FILE)
            _atomic_write_csv(brain, BRAIN_FILE)
            _atomic_write_csv(patterns, PATTERN_FILE)
            _atomic_write_csv(hof, HALL_OF_FAME_FILE)
            _atomic_write_csv(rec, RECOMMENDATION_FILE)

    return {
        "history_rows": len(history),
        "brain_rows": len(brain),
        "pattern_rows": len(patterns),
        "hall_of_fame_rows": len(hof),
        "recommendation_rows": len(rec),
    }


def initialize_engine() -> Dict[str, Any]:
    _load_config()
    for path, cols in [
        (HISTORY_FILE, HISTORY_COLUMNS),
        (BRAIN_FILE, BRAIN_COLUMNS),
        (PATTERN_FILE, PATTERN_COLUMNS),
        (HALL_OF_FAME_FILE, HOF_COLUMNS),
        (RECOMMENDATION_FILE, RECOMMENDATION_COLUMNS),
    ]:
        if not path.exists():
            _atomic_write_csv(pd.DataFrame(columns=cols), path)

    return {
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "brain_dir": str(BRAIN_DIR),
    }


__all__ = [
    "ENGINE_NAME", "ENGINE_VERSION", "SCHEMA_VERSION",
    "create_empty_memory", "load_memory", "save_memory",
    "update_memory", "update_memory_with_result",
    "load_history", "load_pattern_library",
    "load_hall_of_fame", "load_recommendations",
    "get_active_leaders", "get_intelligence_tables",
    "get_engine_status", "backup_brain",
    "rebuild_all", "initialize_engine", "UpdateResult",
]
