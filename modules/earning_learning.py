"""
MR.BOT PRO - EARNING MONEY LEARNING ENGINE V3
==============================================

Mục tiêu
--------
- Học thụ động từ Earning Money Board, tuyệt đối không thay đổi logic giao dịch.
- Giữ nguyên API công khai update_learning(...) để app.py không phải sửa.
- GitHub là kho lưu trữ bền vững; local chỉ là cache/fallback.
- Ghi file an toàn, có khóa luồng, retry, logging và cơ chế fail-safe.
- Tự tạo Outcome T+3/T+5/T+10 và Pattern Knowledge theo dữ liệu tích lũy.

Cấu hình GitHub
---------------
Ưu tiên đọc từ Streamlit secrets hoặc biến môi trường:

    GITHUB_TOKEN
    GITHUB_REPO_OWNER      (mặc định: SONVODAI)
    GITHUB_REPO_NAME       (mặc định: scanner-ga-chien-clean)
    GITHUB_BRANCH          (mặc định: main)
    EARNING_LEARNING_GITHUB_DIR
                           (mặc định: data/earning_learning)

Module vẫn chạy bình thường bằng local nếu GitHub chưa được cấu hình hoặc tạm lỗi.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import math
import os
import random
import re
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol, Sequence, Tuple
from urllib.parse import quote

import numpy as np
import pandas as pd

try:
    import requests
except Exception:  # pragma: no cover - chỉ xảy ra khi môi trường thiếu requests
    requests = None  # type: ignore[assignment]

try:
    import streamlit as st
except Exception:  # pragma: no cover - cho phép test module ngoài Streamlit
    st = None  # type: ignore[assignment]


MODULE_VERSION = "4.0.0"
BRAIN_GENERATION = "GEN3_EXPERIENCE"
FEATURE_VERSION = "DECISION_CONTEXT_V1"
DEFAULT_HORIZONS: Tuple[int, ...] = (3, 5, 10)

DEFAULT_DATA_DIR = Path("data") / "earning_learning"
DEFAULT_GITHUB_DIR = "data/earning_learning"
DEFAULT_GITHUB_OWNER = "SONVODAI"
DEFAULT_GITHUB_REPO = "scanner-ga-chien-clean"
DEFAULT_GITHUB_BRANCH = "main"

OBSERVATIONS_FILE = "observations.csv"
OUTCOMES_FILE = "outcomes.csv"
KNOWLEDGE_FILE = "pattern_knowledge.csv"
LIFECYCLE_FILE = "pattern_lifecycle.csv"
CONTINUATION_FILE = "continuation_knowledge.csv"
PATTERN_SNAPSHOT_FILE = "pattern_snapshot.csv"
PATTERN_HISTORY_FILE = "pattern_history.csv"
DECISION_ARCHIVE_FILE = "decision_archive.csv"
VERIFIED_DECISIONS_FILE = "verified_decisions.csv"
LEARNING_METADATA_FILE = "learning_status.json"
STATUS_FILE = "status.json"

_DATA_FILES = (
    OBSERVATIONS_FILE,
    OUTCOMES_FILE,
    KNOWLEDGE_FILE,
    LIFECYCLE_FILE,
    CONTINUATION_FILE,
    PATTERN_SNAPSHOT_FILE,
    PATTERN_HISTORY_FILE,
    DECISION_ARCHIVE_FILE,
    VERIFIED_DECISIONS_FILE,
    LEARNING_METADATA_FILE,
    STATUS_FILE,
)

_LOGGER = logging.getLogger(__name__)
_LOCK = threading.RLock()


COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "symbol": ("symbol", "ticker", "code", "mã", "ma", "Mã", "Ticker"),
    "trade_date": (
        "trade_date", "date", "datetime", "date_time", "time",
        "Ngày", "Ngày/Giờ",
    ),
    "price": (
        "price", "close", "last", "current_price",
        "daily_price_before_live", "Giá", "Close",
    ),
    "health_group": (
        "evolution_health_group", "health_group", "group_name",
        "health", "Trạng thái", "Nhóm",
    ),
    "health_score": (
        "evolution_health_score", "health_score", "total_score",
        "Điểm", "Score",
    ),
    "health_rank": ("evolution_health_rank", "health_rank", "rank"),
    "action": (
        "evolution_action", "action", "signal",
        "Mua/Bán", "Hành động",
    ),
    "reason": ("evolution_reason", "reason", "Lý do"),
    "rsi14": ("rsi14", "rsi", "RSI", "RSI14"),
    "rsi_slope": ("rsi_slope", "rsi14_slope", "RSI slope"),
    "rs5": ("rs5", "RS5", "rs_5"),
    "rs10": ("rs10", "RS10", "rs_10"),
    "rs_spread": ("rs_spread", "RS_SPREAD", "rs spread"),
    "ema9": ("ema9", "EMA9"),
    "ma20": ("ma20", "sma20", "MA20", "SMA20"),
    "ema9_ma20_slope": (
        "ema9_ma20_slope", "trend_slope", "slope", "Slope",
    ),
    "ema9_ma20_slope_change": (
        "ema9_ma20_slope_change", "slope_change",
    ),
    "obv_status": ("obv_status", "obv", "OBV"),
    "volume": ("volume", "vol", "Volume", "Khối lượng"),
    "vol_ma20": ("vol_ma20", "volume_ma20", "Vol MA20"),
    "dist_from_ema9_pct": (
        "dist_from_ema9_pct", "dist_ema9_pct",
    ),
    "near_bottom_20_pct": ("near_bottom_20_pct",),
    "near_bottom_60_pct": ("near_bottom_60_pct",),
    "dist_high20": ("dist_high20", "dist_high20_pct"),
    "green2": ("green_2_confirm", "green2", "early_green2"),
    "early": ("early", "early_signal", "early_dry_green2", "InEarlyLab"),
    "pull": ("pull", "pull_label", "pull_signal", "InPullback"),
    "group": ("group", "evolution_stage", "stage"),
    "sector": ("sector", "industry", "ngành", "Ngành"),
    "market_score": ("market_score", "market_real", "market_health"),
    "market_regime": ("market_regime", "regime", "market_state"),
    "market_live": ("market_live", "live_score"),
    "market_forecast": ("market_forecast", "forecast_score"),
    "breadth": ("breadth", "market_breadth", "breadth_pct"),
    "ema9_slope": ("ema9_slope",),
    "ma20_slope": ("ma20_slope",),
    "obv": ("obv", "obv_value"),
    "obv_ema9": ("obv_ema9",),
    "volume_ratio": ("volume_ratio", "vol_ratio", "volume_ratio20"),
    "dryup": ("dryup", "dry_up", "volume_dryup"),
    "near_bottom20": ("near_bottom20", "near_bottom_20"),
    "near_bottom60": ("near_bottom60", "near_bottom_60"),
    "leader_score": ("leader_score",),
    "storm_score": ("storm_score",),
    "evolution_score": ("evolution_score",),
    "total_score": ("total_score", "health_score"),
    "group_rank": ("group_rank",),
}

NUMERIC_FIELDS = (
    "price",
    "health_score",
    "health_rank",
    "rsi14",
    "rsi_slope",
    "rs5",
    "rs10",
    "ema9",
    "ma20",
    "ema9_ma20_slope",
    "ema9_ma20_slope_change",
    "volume",
    "vol_ma20",
    "dist_from_ema9_pct",
    "near_bottom_20_pct",
    "near_bottom_60_pct",
    "dist_high20",
    "market_score",
    "market_live",
    "market_forecast",
    "breadth",
    "ema9_slope",
    "ma20_slope",
    "obv",
    "obv_ema9",
    "volume_ratio",
    "near_bottom20",
    "near_bottom60",
    "leader_score",
    "storm_score",
    "evolution_score",
    "total_score",
    "group_rank",
)

BOOLEAN_FIELDS = ("green2", "early", "pull", "dryup")


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
    lifecycle_rows: int = 0
    continuation_rows: int = 0
    snapshot_rows: int = 0
    history_rows: int = 0
    decision_archive_rows: int = 0
    verified_decisions_rows: int = 0
    storage_mode: str = "LOCAL_ONLY"
    github_sync: str = "NOT_ATTEMPTED"
    skipped_reason: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitHubConfig:
    token: Optional[str]
    owner: str
    repo: str
    branch: str
    remote_dir: str

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.owner and self.repo)


@dataclass(frozen=True)
class StorageReadResult:
    text: Optional[str]
    source: str
    error: Optional[str] = None


@dataclass(frozen=True)
class StorageWriteResult:
    local_ok: bool
    github_ok: bool
    github_status: str
    error: Optional[str] = None


class TextStorage(Protocol):
    def read_text(self, filename: str) -> StorageReadResult:
        ...

    def write_text(
        self,
        filename: str,
        text: str,
        *,
        commit_message: str,
    ) -> StorageWriteResult:
        ...


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _secret_or_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value: Any = None

    if st is not None:
        try:
            value = st.secrets.get(name)
        except Exception:
            value = None

    if value in (None, ""):
        value = os.getenv(name, default)

    if value in (None, ""):
        return None

    return str(value).strip()


def _load_github_config(remote_dir: Optional[str] = None) -> GitHubConfig:
    return GitHubConfig(
        token=_secret_or_env("GITHUB_TOKEN"),
        owner=_secret_or_env("GITHUB_REPO_OWNER", DEFAULT_GITHUB_OWNER)
        or DEFAULT_GITHUB_OWNER,
        repo=_secret_or_env("GITHUB_REPO_NAME", DEFAULT_GITHUB_REPO)
        or DEFAULT_GITHUB_REPO,
        branch=_secret_or_env("GITHUB_BRANCH", DEFAULT_GITHUB_BRANCH)
        or DEFAULT_GITHUB_BRANCH,
        remote_dir=(
            remote_dir
            or _secret_or_env(
                "EARNING_LEARNING_GITHUB_DIR",
                DEFAULT_GITHUB_DIR,
            )
            or DEFAULT_GITHUB_DIR
        ).strip("/"),
    )


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
        "1",
        "true",
        "yes",
        "y",
        "ok",
        "x",
        "có",
        "co",
        "đúng",
        "dung",
        "green2",
        "early",
        "pull",
        "confirmed",
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


def _hash_payload(values: Iterable[Any]) -> str:
    raw = "|".join(_safe_text(value) for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _resolve_data_dir(
    data_dir: Optional[os.PathLike[str] | str],
) -> Path:
    path = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=path.suffix or ".tmp",
            prefix=f"{path.stem}_",
            dir=path.parent,
            delete=False,
            encoding="utf-8",
            newline="",
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _read_local_text(path: Path) -> Optional[str]:
    if not path.exists() or path.stat().st_size == 0:
        return None

    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8")


def _csv_to_text(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, encoding="utf-8-sig")


def _text_to_csv(text: Optional[str]) -> pd.DataFrame:
    if text is None or not text.strip():
        return pd.DataFrame()

    try:
        return pd.read_csv(io.StringIO(text))
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _json_to_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


class GitHubLocalStorage:
    """
    GitHub-first persistent storage with local cache/fallback.

    Read order:
        GitHub -> local cache

    Write order:
        local atomic write -> GitHub commit

    Local được ghi trước để app vẫn có dữ liệu ngay cả khi mạng GitHub tạm lỗi.
    """

    def __init__(
        self,
        local_dir: Path,
        github: GitHubConfig,
        *,
        timeout: Tuple[float, float] = (5.0, 15.0),
        max_retries: int = 3,
    ) -> None:
        self.local_dir = local_dir
        self.github = github
        self.timeout = timeout
        self.max_retries = max(1, int(max_retries))

    def _local_path(self, filename: str) -> Path:
        return self.local_dir / filename

    def _remote_path(self, filename: str) -> str:
        if self.github.remote_dir:
            return f"{self.github.remote_dir}/{filename}".strip("/")
        return filename.strip("/")

    def _api_url(self, filename: str) -> str:
        remote_path = quote(self._remote_path(filename), safe="/")
        return (
            f"https://api.github.com/repos/{self.github.owner}/"
            f"{self.github.repo}/contents/{remote_path}"
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.github.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mr-bot-earning-learning-v2",
        }

    def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        if requests is None:
            raise RuntimeError("requests package is not available")

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=self.timeout,
                    **kwargs,
                )

                if response.status_code not in {429, 500, 502, 503, 504}:
                    return response

                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    delay = min(float(retry_after), 5.0)
                else:
                    delay = min(
                        0.5 * (2**attempt) + random.uniform(0.0, 0.25),
                        4.0,
                    )
                time.sleep(delay)

            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    time.sleep(
                        min(
                            0.5 * (2**attempt)
                            + random.uniform(0.0, 0.25),
                            4.0,
                        )
                    )

        if last_error is not None:
            raise last_error

        raise RuntimeError("GitHub request failed after retries")

    def _github_read(self, filename: str) -> Optional[str]:
        if not self.github.enabled:
            return None

        response = self._request(
            "GET",
            self._api_url(filename),
            headers=self._headers(),
            params={"ref": self.github.branch},
        )

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            raise RuntimeError(
                f"GitHub read failed: HTTP {response.status_code} "
                f"{response.text[:300]}"
            )

        payload = response.json()
        encoded = payload.get("content", "")
        encoding = payload.get("encoding", "base64")

        if not encoded:
            return ""

        if encoding != "base64":
            raise RuntimeError(
                f"Unsupported GitHub content encoding: {encoding}"
            )

        return base64.b64decode(encoded).decode("utf-8-sig")

    def _github_sha(self, filename: str) -> Optional[str]:
        response = self._request(
            "GET",
            self._api_url(filename),
            headers=self._headers(),
            params={"ref": self.github.branch},
        )

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            raise RuntimeError(
                f"Cannot read GitHub SHA: HTTP {response.status_code}"
            )

        return response.json().get("sha")

    def _github_write_once(
        self,
        filename: str,
        text: str,
        commit_message: str,
    ) -> str:
        sha = self._github_sha(filename)

        payload: Dict[str, Any] = {
            "message": commit_message,
            "content": base64.b64encode(
                text.encode("utf-8")
            ).decode("ascii"),
            "branch": self.github.branch,
        }
        if sha:
            payload["sha"] = sha

        response = self._request(
            "PUT",
            self._api_url(filename),
            headers=self._headers(),
            json=payload,
        )

        if response.status_code not in {200, 201}:
            raise RuntimeError(
                f"GitHub write failed: HTTP {response.status_code} "
                f"{response.text[:300]}"
            )

        return "GITHUB_OK"

    def _github_write(
        self,
        filename: str,
        text: str,
        commit_message: str,
    ) -> str:
        if not self.github.enabled:
            return "GITHUB_DISABLED"

        # Nếu có xung đột SHA do hai lần ghi gần nhau, đọc SHA mới rồi thử lại.
        last_error: Optional[Exception] = None

        for conflict_attempt in range(2):
            try:
                return self._github_write_once(
                    filename,
                    text,
                    commit_message,
                )
            except Exception as exc:
                last_error = exc
                message = str(exc)
                if (
                    conflict_attempt == 0
                    and (
                        "HTTP 409" in message
                        or "HTTP 422" in message
                    )
                ):
                    time.sleep(0.4)
                    continue
                break

        if last_error is not None:
            raise last_error

        raise RuntimeError("Unknown GitHub write error")

    def read_text(self, filename: str) -> StorageReadResult:
        github_error: Optional[str] = None

        if self.github.enabled:
            try:
                text = self._github_read(filename)
                if text is not None:
                    try:
                        _atomic_write_text(
                            text,
                            self._local_path(filename),
                        )
                    except Exception:
                        _LOGGER.exception(
                            "Cannot refresh local cache: %s",
                            filename,
                        )
                    return StorageReadResult(text=text, source="GITHUB")
            except Exception as exc:
                github_error = f"{type(exc).__name__}: {exc}"
                _LOGGER.warning(
                    "GitHub read failed for %s; fallback local: %s",
                    filename,
                    github_error,
                )

        try:
            local_text = _read_local_text(self._local_path(filename))
            if local_text is not None:
                return StorageReadResult(
                    text=local_text,
                    source="LOCAL",
                    error=github_error,
                )
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
            return StorageReadResult(
                text=None,
                source="NONE",
                error=(
                    f"github={github_error}; local={local_error}"
                    if github_error
                    else local_error
                ),
            )

        return StorageReadResult(
            text=None,
            source="NONE",
            error=github_error,
        )

    def write_text(
        self,
        filename: str,
        text: str,
        *,
        commit_message: str,
    ) -> StorageWriteResult:
        local_ok = False
        github_ok = False
        github_status = "GITHUB_DISABLED"
        errors = []

        try:
            _atomic_write_text(text, self._local_path(filename))
            local_ok = True
        except Exception as exc:
            errors.append(f"local={type(exc).__name__}: {exc}")
            _LOGGER.exception("Local write failed: %s", filename)

        if self.github.enabled:
            try:
                github_status = self._github_write(
                    filename,
                    text,
                    commit_message,
                )
                github_ok = github_status == "GITHUB_OK"
            except Exception as exc:
                github_status = "GITHUB_ERROR"
                errors.append(f"github={type(exc).__name__}: {exc}")
                _LOGGER.warning(
                    "GitHub write failed for %s: %s",
                    filename,
                    exc,
                )

        return StorageWriteResult(
            local_ok=local_ok,
            github_ok=github_ok,
            github_status=github_status,
            error="; ".join(errors) or None,
        )


def _make_storage(
    data_dir: Optional[os.PathLike[str] | str] = None,
    remote_dir: Optional[str] = None,
) -> GitHubLocalStorage:
    directory = _resolve_data_dir(data_dir)
    config = _load_github_config(remote_dir)
    return GitHubLocalStorage(directory, config)


def _read_csv_from_storage(
    storage: TextStorage,
    filename: str,
) -> Tuple[pd.DataFrame, StorageReadResult]:
    result = storage.read_text(filename)

    try:
        return _text_to_csv(result.text), result
    except Exception as exc:
        _LOGGER.exception("Cannot parse CSV: %s", filename)
        return (
            pd.DataFrame(),
            StorageReadResult(
                text=None,
                source=result.source,
                error=f"{type(exc).__name__}: {exc}",
            ),
        )


def _write_csv_to_storage(
    storage: TextStorage,
    filename: str,
    df: pd.DataFrame,
    *,
    commit_message: str,
) -> StorageWriteResult:
    return storage.write_text(
        filename,
        _csv_to_text(df),
        commit_message=commit_message,
    )


def _write_json_to_storage(
    storage: TextStorage,
    filename: str,
    payload: Mapping[str, Any],
    *,
    commit_message: str,
) -> StorageWriteResult:
    return storage.write_text(
        filename,
        _json_to_text(payload),
        commit_message=commit_message,
    )


def _find_source_column(
    columns: Sequence[Any],
    aliases: Sequence[str],
) -> Optional[Any]:
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
        canonical[canonical_name] = (
            source[source_col]
            if source_col is not None
            else np.nan
        )

    context = dict(market_context or {})

    for field in ("market_score", "market_live", "market_forecast", "breadth", "market_regime"):
        if canonical[field].isna().all() and field in context:
            canonical[field] = context[field]

    canonical["symbol"] = canonical["symbol"].map(_normalise_symbol)
    canonical = canonical[canonical["symbol"] != ""].copy()

    context_date = context.get("trade_date") or context.get("date")
    parsed_date = pd.to_datetime(
        canonical["trade_date"],
        errors="coerce",
    )

    if context_date is not None:
        parsed_context_date = pd.to_datetime(
            context_date,
            errors="coerce",
        )
        parsed_date = parsed_date.fillna(parsed_context_date)

    parsed_date = parsed_date.fillna(pd.Timestamp(date.today()))
    canonical["trade_date"] = parsed_date.dt.strftime("%Y-%m-%d")

    for field in NUMERIC_FIELDS:
        canonical[field] = canonical[field].map(_safe_float)

    for field in BOOLEAN_FIELDS:
        canonical[field] = canonical[field].map(_safe_bool)

    for field in (
        "health_group",
        "action",
        "reason",
        "obv_status",
        "group",
        "sector",
        "market_regime",
    ):
        canonical[field] = canonical[field].map(_safe_text)

    canonical["rs_spread"] = (
        canonical["rs5"] - canonical["rs10"]
    )

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
        _hash_payload((trade_date_value, symbol))
        for trade_date_value, symbol in zip(
            canonical["trade_date"],
            canonical["symbol"],
        )
    ]

    canonical["decision_id"] = canonical["observation_id"]
    canonical["decision_status"] = "PENDING_OUTCOME"
    canonical["recorded_at"] = _utc_now_iso()
    canonical["module_version"] = MODULE_VERSION
    canonical["brain_generation"] = BRAIN_GENERATION
    canonical["feature_version"] = FEATURE_VERSION

    canonical = canonical.drop_duplicates(
        subset=["trade_date", "symbol"],
        keep="last",
    )

    ordered = [
        "observation_id",
        "decision_id",
        "decision_status",
        "trade_date",
        "recorded_at",
        "module_version",
        "brain_generation",
        "feature_version",
        "symbol",
        "price",
        "health_group",
        "health_score",
        "health_rank",
        "action",
        "reason",
        "rsi14",
        "rsi_slope",
        "rs5",
        "rs10",
        "rs_spread",
        "ema9",
        "ma20",
        "ema9_ma20_slope",
        "ema9_ma20_slope_change",
        "price_vs_ema9_pct",
        "price_vs_ma20_pct",
        "obv_status",
        "volume",
        "vol_ma20",
        "volume_ratio20",
        "dist_from_ema9_pct",
        "near_bottom_20_pct",
        "near_bottom_60_pct",
        "dist_high20",
        "green2",
        "early",
        "pull",
        "group",
        "sector",
        "ema9_slope",
        "ma20_slope",
        "obv",
        "obv_ema9",
        "volume_ratio",
        "dryup",
        "near_bottom20",
        "near_bottom60",
        "leader_score",
        "storm_score",
        "evolution_score",
        "total_score",
        "group_rank",
        "market_score",
        "market_live",
        "market_forecast",
        "breadth",
        "market_regime",
    ]

    return canonical[ordered].reset_index(drop=True)


def _normalise_observation_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()

    required = {
        "trade_date": "",
        "symbol": "",
        "observation_id": "",
        "decision_id": "",
        "decision_status": "PENDING_OUTCOME",
    }

    for column, default in required.items():
        if column not in out.columns:
            out[column] = default

    out["trade_date"] = out["trade_date"].astype(str)
    out["symbol"] = out["symbol"].map(_normalise_symbol)

    missing_id = out["observation_id"].astype(str).str.strip().isin(
        {"", "nan", "None"}
    )
    if missing_id.any():
        out.loc[missing_id, "observation_id"] = [
            _hash_payload((d, s))
            for d, s in zip(
                out.loc[missing_id, "trade_date"],
                out.loc[missing_id, "symbol"],
            )
        ]

    missing_decision_id = out["decision_id"].astype(str).str.strip().isin({"", "nan", "None"})
    out.loc[missing_decision_id, "decision_id"] = out.loc[missing_decision_id, "observation_id"]
    out["decision_status"] = out["decision_status"].replace({"": "PENDING_OUTCOME", "nan": "PENDING_OUTCOME"}).fillna("PENDING_OUTCOME")

    return out


def _upsert_observations(
    existing: pd.DataFrame,
    new_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, int, int]:
    existing = _normalise_observation_schema(existing)

    if existing.empty:
        combined = new_df.copy()
        added = len(new_df)
        updated = 0
    else:
        existing_keys = set(
            zip(
                existing["trade_date"].astype(str),
                existing["symbol"].astype(str),
            )
        )
        new_keys = list(
            zip(
                new_df["trade_date"].astype(str),
                new_df["symbol"].astype(str),
            )
        )

        added = sum(key not in existing_keys for key in new_keys)
        updated = len(new_df) - added

        combined = pd.concat(
            [existing, new_df],
            ignore_index=True,
            sort=False,
        )
        combined = combined.drop_duplicates(
            subset=["trade_date", "symbol"],
            keep="last",
        )

    combined["trade_date"] = combined["trade_date"].astype(str)
    combined = combined.sort_values(
        ["trade_date", "symbol"],
        kind="stable",
    ).reset_index(drop=True)

    return combined, int(added), int(updated)


def _validate_horizons(horizons: Sequence[int]) -> Tuple[int, ...]:
    cleaned = []

    for horizon in horizons:
        value = int(horizon)
        if value <= 0:
            raise ValueError("All horizons must be positive integers")
        if value not in cleaned:
            cleaned.append(value)

    if not cleaned:
        raise ValueError("At least one horizon is required")

    return tuple(sorted(cleaned))


def _build_outcomes(
    observations: pd.DataFrame,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    if observations.empty:
        return pd.DataFrame()

    valid_horizons = _validate_horizons(horizons)

    df = _normalise_observation_schema(observations)
    df["trade_date"] = pd.to_datetime(
        df["trade_date"],
        errors="coerce",
    )
    df["price"] = pd.to_numeric(df.get("price"), errors="coerce")

    df = df.dropna(
        subset=["trade_date", "symbol", "price"],
    )
    df = df[df["price"] > 0].copy()
    df = df.sort_values(
        ["symbol", "trade_date"],
        kind="stable",
    )
    rows = []

    for symbol, symbol_df in df.groupby("symbol", sort=False):
        symbol_df = symbol_df.reset_index(drop=True)

        for index, current in symbol_df.iterrows():
            base_price = _safe_float(current["price"])
            if not math.isfinite(base_price) or base_price <= 0:
                continue

            for horizon in valid_horizons:
                target_index = index + horizon
                if target_index >= len(symbol_df):
                    continue

                future = symbol_df.iloc[target_index]
                future_price = _safe_float(future["price"])
                if (
                    not math.isfinite(future_price)
                    or future_price <= 0
                ):
                    continue

                future_slice = symbol_df.iloc[
                    index + 1 : target_index + 1
                ]
                slice_prices = pd.to_numeric(
                    future_slice["price"],
                    errors="coerce",
                ).dropna()

                return_pct = (
                    future_price / base_price - 1.0
                ) * 100.0

                max_gain_pct = (
                    (slice_prices.max() / base_price - 1.0) * 100.0
                    if not slice_prices.empty
                    else np.nan
                )

                max_drawdown_pct = (
                    (slice_prices.min() / base_price - 1.0) * 100.0
                    if not slice_prices.empty
                    else np.nan
                )

                leader_threshold = {
                    3: 5.0,
                    5: 8.0,
                    10: 12.0,
                }.get(horizon, 10.0)

                rows.append(
                    {
                        "outcome_id": _hash_payload(
                            (
                                current["observation_id"],
                                horizon,
                            )
                        ),
                        "observation_id": current["observation_id"],
                        "symbol": symbol,
                        "entry_date": current[
                            "trade_date"
                        ].strftime("%Y-%m-%d"),
                        "entry_price": base_price,
                        "horizon": horizon,
                        "target_date": future[
                            "trade_date"
                        ].strftime("%Y-%m-%d"),
                        "target_price": future_price,
                        "return_pct": return_pct,
                        "max_gain_pct": max_gain_pct,
                        "max_drawdown_pct": max_drawdown_pct,
                        "is_win": bool(return_pct > 0.0),
                        "is_leader": bool(
                            max_gain_pct >= leader_threshold
                        ),
                        "evaluated_at": _utc_now_iso(),
                        "module_version": MODULE_VERSION,
                        "brain_generation": BRAIN_GENERATION,
                        "feature_version": FEATURE_VERSION,
                    }
                )

    if not rows:
        return pd.DataFrame()

    outcomes = pd.DataFrame(rows)
    outcomes = outcomes.drop_duplicates(
        subset=["outcome_id"],
        keep="last",
    )

    return outcomes.sort_values(
        ["entry_date", "symbol", "horizon"],
        kind="stable",
    ).reset_index(drop=True)


def _bucket_numeric(
    series: pd.Series,
    bins: Sequence[float],
    labels: Sequence[str],
) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")

    return pd.cut(
        numeric,
        bins=[-np.inf, *bins, np.inf],
        labels=labels,
        include_lowest=True,
        right=False,
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

    if any(
        token in text
        for token in (
            "positive",
            "dương",
            "duong",
            "tăng",
            "tang",
            "above",
            "strong",
            "🟢",
        )
    ):
        return "POSITIVE"

    if any(
        token in text
        for token in (
            "negative",
            "âm",
            "am",
            "giảm",
            "giam",
            "below",
            "weak",
            "🔴",
        )
    ):
        return "NEGATIVE"

    return "NEUTRAL"


def _ensure_pattern_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    defaults: Dict[str, Any] = {
        "health_group": "",
        "rsi14": np.nan,
        "rs10": np.nan,
        "rs_spread": np.nan,
        "ema9_ma20_slope": np.nan,
        "volume_ratio20": np.nan,
        "obv_status": "",
        "green2": False,
        "early": False,
        "pull": False,
        "dryup": False,
        "leader_score": np.nan,
        "market_forecast": np.nan,
        "breadth": np.nan,
        "market_score": np.nan,

        # ===== V4 =====
        # Giữ tương thích với dữ liệu cũ.
        "stock_pattern_key": "",
        "market_context_key": "",
    }

    for column, default in defaults.items():
        if column not in out.columns:
            out[column] = default

    return out

def _add_pattern_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = _ensure_pattern_columns(df)

    out["p_health"] = out["health_group"].map(
        _normalise_health_group
    )
    out["p_rsi"] = _bucket_numeric(
        out["rsi14"],
        (45, 50, 55, 60, 65, 70),
        (
            "<45",
            "45-50",
            "50-55",
            "55-60",
            "60-65",
            "65-70",
            ">=70",
        ),
    )
    out["p_rs10"] = _bucket_numeric(
        out["rs10"],
        (-2, 0, 2, 5, 10),
        ("<-2", "-2-0", "0-2", "2-5", "5-10", ">=10"),
    )
    out["p_rs_spread"] = _bucket_numeric(
        out["rs_spread"],
        (-2, 0, 2, 5),
        ("<-2", "-2-0", "0-2", "2-5", ">=5"),
    )
    out["p_slope"] = _bucket_numeric(
        out["ema9_ma20_slope"],
        (-0.2, 0, 0.2),
        ("STRONG_NEG", "NEG", "POS", "STRONG_POS"),
    )
    out["p_volume"] = _bucket_numeric(
        out["volume_ratio20"],
        (0.7, 1.0, 1.2, 1.5),
        ("<0.7", "0.7-1.0", "1.0-1.2", "1.2-1.5", ">=1.5"),
    )
    out["p_obv"] = out["obv_status"].map(_obv_bucket)
    out["p_green2"] = out["green2"].map(
        lambda value: "G2" if _safe_bool(value) else "NO_G2"
    )
    out["p_early"] = out["early"].map(
        lambda value: "EARLY"
        if _safe_bool(value)
        else "NO_EARLY"
    )
    out["p_pull"] = out["pull"].map(
        lambda value: "PULL" if _safe_bool(value) else "NO_PULL"
    )
    out["p_dryup"] = out["dryup"].map(
        lambda value: "DRYUP" if _safe_bool(value) else "NO_DRYUP"
    )
    out["p_leader"] = _bucket_numeric(
        out["leader_score"],
        (40, 60, 75, 85),
        ("<40", "40-60", "60-75", "75-85", ">=85"),
    )
    out["p_forecast"] = _bucket_numeric(
        out["market_forecast"],
        (4, 6, 8),
        ("<4", "4-6", "6-8", ">=8"),
    )
    out["p_breadth"] = _bucket_numeric(
        out["breadth"],
        (20, 40, 60, 80),
        ("<20", "20-40", "40-60", "60-80", ">=80"),
    )
    out["p_market"] = _bucket_numeric(
        out["market_score"],
        (4, 6, 8),
        ("<4", "4-6", "6-8", ">=8"),
    )

    stock_fields = [
        "p_health",
        "p_rsi",
        "p_rs10",
        "p_rs_spread",
        "p_slope",
        "p_obv",
        "p_volume",
        "p_green2",
        "p_early",
        "p_pull",
        "p_dryup",
        "p_leader",
    ]
    market_fields = [
        "p_forecast",
        "p_breadth",
        "p_market",
    ]

    # V4: tách DNA cổ phiếu khỏi bức ảnh thị trường.
    # pattern_key vẫn là khóa kết hợp để tương thích ngược với các bảng hiện tại.
    out["stock_pattern_key"] = out[stock_fields].astype(str).agg("|".join, axis=1)
    out["market_context_key"] = out[market_fields].astype(str).agg("|".join, axis=1)
    out["pattern_key"] = (
        "CTX[" + out["market_context_key"].astype(str) + "]::DNA["
        + out["stock_pattern_key"].astype(str)
        + "]"
    )

    # Khóa V4 tương thích ngược; hiện tại cùng giá trị với pattern_key.
    out["pattern_key_v2"] = out["pattern_key"]

    return out


def _coerce_bool_series(series: pd.Series) -> pd.Series:
    return series.map(_safe_bool).astype(int)


def _build_pattern_knowledge(
    observations: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> pd.DataFrame:
    if observations.empty or outcomes.empty:
        return pd.DataFrame()

    obs = _add_pattern_columns(observations)
    outcome_df = outcomes.copy()

    outcome_df["is_win"] = _coerce_bool_series(
        outcome_df["is_win"]
    )
    outcome_df["is_leader"] = _coerce_bool_series(
        outcome_df["is_leader"]
    )

    merged = outcome_df.merge(
        obs,
        on=["observation_id", "symbol"],
        how="inner",
        suffixes=("_outcome", ""),
    )

    if merged.empty:
        return pd.DataFrame()

    knowledge = (
        merged.groupby(
            [
                "market_context_key",
                "stock_pattern_key",
                "pattern_key",
                "horizon",
            ],
            dropna=False,
        )
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

    knowledge["win_rate_pct"] = (
        knowledge["wins"] / knowledge["samples"] * 100.0
    )
    knowledge["leader_rate_pct"] = (
        knowledge["leaders"] / knowledge["samples"] * 100.0
    )

    # Wilson lower bound 80%: hạn chế mẫu nhỏ đứng đầu bảng chỉ vì ăn may.
    z = 1.2815515655446004
    n = knowledge["samples"].astype(float)
    p = knowledge["wins"].astype(float) / n

    denominator = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * np.sqrt(
        (
            p * (1.0 - p)
            + z * z / (4.0 * n)
        )
        / n
    )

    knowledge["win_rate_lower_bound_pct"] = (
        (centre - margin) / denominator * 100.0
    )

    knowledge["knowledge_score"] = (
        0.45 * knowledge["win_rate_lower_bound_pct"]
        + 0.25 * knowledge["leader_rate_pct"]
        + 0.20
        * pd.to_numeric(
            knowledge["avg_return_pct"],
            errors="coerce",
        ).clip(-20, 30)
        + 0.10
        * pd.to_numeric(
            knowledge["avg_max_gain_pct"],
            errors="coerce",
        ).clip(-20, 40)
    )
    knowledge["pattern_version"] = "V4"
    knowledge["context_version"] = "MARKET_CONTEXT_V1"
    knowledge["updated_at"] = _utc_now_iso()
    knowledge["module_version"] = MODULE_VERSION
    knowledge["brain_generation"] = BRAIN_GENERATION
    knowledge["feature_version"] = FEATURE_VERSION

    return knowledge.sort_values(
        ["horizon", "knowledge_score", "samples"],
        ascending=[True, False, False],
        kind="stable",
    ).reset_index(drop=True)



def _build_pattern_lifecycle(
    observations: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> pd.DataFrame:
    """Ghép T3/T5/T10 của cùng Observation thành một vòng đời duy nhất."""
    if observations.empty or outcomes.empty:
        return pd.DataFrame()

    obs = _add_pattern_columns(observations)
    out = outcomes.copy()
    out["horizon"] = pd.to_numeric(out["horizon"], errors="coerce").astype("Int64")
    out = out[out["horizon"].isin(DEFAULT_HORIZONS)].copy()
    if out.empty:
        return pd.DataFrame()

    value_columns = [
        "target_date", "target_price", "return_pct",
        "max_gain_pct", "max_drawdown_pct", "is_win", "is_leader",
    ]
    frames = []
    for value_column in value_columns:
        pivot = out.pivot_table(
            index=["observation_id", "symbol", "entry_date", "entry_price"],
            columns="horizon",
            values=value_column,
            aggfunc="last",
        )
        pivot.columns = [f"t{int(h)}_{value_column}" for h in pivot.columns]
        frames.append(pivot)

    lifecycle = pd.concat(frames, axis=1).reset_index()
    lifecycle = lifecycle.merge(
        obs,
        on=["observation_id", "symbol"],
        how="left",
        suffixes=("", "_origin"),
    )

    for horizon in DEFAULT_HORIZONS:
        win_col = f"t{horizon}_is_win"
        return_col = f"t{horizon}_return_pct"
        if win_col in lifecycle.columns:
            lifecycle[win_col] = lifecycle[win_col].map(_safe_bool)
        if return_col not in lifecycle.columns:
            lifecycle[return_col] = np.nan

    t3 = pd.to_numeric(lifecycle.get("t3_return_pct"), errors="coerce")
    t5 = pd.to_numeric(lifecycle.get("t5_return_pct"), errors="coerce")
    t10 = pd.to_numeric(lifecycle.get("t10_return_pct"), errors="coerce")

    lifecycle["completed_horizons"] = pd.concat([t3, t5, t10], axis=1).notna().sum(axis=1)
    lifecycle["t3_to_t5_delta_pct"] = t5 - t3
    lifecycle["t5_to_t10_delta_pct"] = t10 - t5
    lifecycle["t3_to_t10_delta_pct"] = t10 - t3
    lifecycle["persistent_win_t5"] = (t3 > 0) & (t5 > 0)
    lifecycle["persistent_win_t10"] = (t3 > 0) & (t5 > 0) & (t10 > 0)
    lifecycle["flash_winner"] = (t3 > 0) & ((t5 <= 0) | (t10 <= 0))
    lifecycle["slow_burner"] = (t3 <= 0) & (t5 > 0) & (t10 > 0)
    lifecycle["gain_accelerating"] = (t3 > 0) & (t5 > t3) & (t10 > t5)

    lifecycle["lifecycle_class"] = np.select(
        [
            lifecycle["gain_accelerating"],
            lifecycle["persistent_win_t10"],
            lifecycle["flash_winner"],
            lifecycle["slow_burner"],
            (t3 <= 0) & (t5 <= 0) & (t10 <= 0),
        ],
        [
            "STRONG_RUNNER",
            "PERSISTENT_WINNER",
            "FLASH_WINNER",
            "SLOW_BURNER",
            "PERSISTENT_LOSER",
        ],
        default="MIXED",
    )
    lifecycle["updated_at"] = _utc_now_iso()
    lifecycle["module_version"] = MODULE_VERSION
    lifecycle["brain_generation"] = BRAIN_GENERATION
    lifecycle["feature_version"] = FEATURE_VERSION
    return lifecycle.sort_values(["entry_date", "symbol"], kind="stable").reset_index(drop=True)


def _wilson_lower_bound(
    wins: pd.Series,
    samples: pd.Series,
) -> pd.Series:
    """
    Wilson lower bound 80%.

    Dùng cận dưới thay cho win-rate thô để tránh mẫu rất ít
    nhưng thắng 100% bị xếp quá cao.
    """
    z = 1.2815515655446004

    n = pd.to_numeric(samples, errors="coerce").astype(float)
    w = pd.to_numeric(wins, errors="coerce").astype(float)

    valid = n > 0

    p = pd.Series(np.nan, index=n.index, dtype=float)
    p.loc[valid] = w.loc[valid] / n.loc[valid]

    denominator = pd.Series(np.nan, index=n.index, dtype=float)
    denominator.loc[valid] = (
        1.0 + (z * z) / n.loc[valid]
    )

    centre = pd.Series(np.nan, index=n.index, dtype=float)
    centre.loc[valid] = (
        p.loc[valid]
        + (z * z) / (2.0 * n.loc[valid])
    )

    margin = pd.Series(np.nan, index=n.index, dtype=float)
    margin.loc[valid] = z * np.sqrt(
        (
            p.loc[valid] * (1.0 - p.loc[valid])
            + (z * z) / (4.0 * n.loc[valid])
        )
        / n.loc[valid]
    )

    lower = pd.Series(np.nan, index=n.index, dtype=float)
    lower.loc[valid] = (
        (centre.loc[valid] - margin.loc[valid])
        / denominator.loc[valid]
        * 100.0
    )

    return lower


def _build_continuation_knowledge(
    lifecycle: pd.DataFrame,
) -> pd.DataFrame:
    """
    Học sức bền của mẫu từ T3 -> T5 -> T10.

    V4:
    - Giữ riêng DNA cổ phiếu.
    - Giữ riêng bối cảnh thị trường.
    - Không đánh đồng cùng một DNA xuất hiện trong các mùa thị trường khác nhau.
    - Học xác suất thắng tiếp sau khi đã thắng T3/T5.
    """
    if lifecycle is None or lifecycle.empty:
        return pd.DataFrame()

    df = lifecycle.copy()

    required_defaults: Dict[str, Any] = {
        "pattern_key": "",
        "pattern_key_v2": "",
        "stock_pattern_key": "",
        "market_context_key": "",
        "entry_date": "",
        "t3_return_pct": np.nan,
        "t5_return_pct": np.nan,
        "t10_return_pct": np.nan,
        "gain_accelerating": False,
        "persistent_win_t10": False,
        "flash_winner": False,
    }

    for column, default in required_defaults.items():
        if column not in df.columns:
            df[column] = default

    # Tương thích dữ liệu cũ: nếu chưa có pattern_key_v2,
    # dùng pattern_key hiện có làm fallback.
    missing_pattern_key_v2 = (
        df["pattern_key_v2"]
        .astype(str)
        .str.strip()
        .isin({"", "nan", "None"})
    )
    if missing_pattern_key_v2.any():
        df.loc[
            missing_pattern_key_v2,
            "pattern_key_v2",
        ] = df.loc[
            missing_pattern_key_v2,
            "pattern_key",
        ].astype(str)

    # Tương thích dữ liệu cũ:
    # nếu chưa có hai khóa V4 thì vẫn giữ pattern_key làm fallback.
    missing_stock_key = (
        df["stock_pattern_key"]
        .astype(str)
        .str.strip()
        .isin({"", "nan", "None"})
    )
    if missing_stock_key.any():
        df.loc[
            missing_stock_key,
            "stock_pattern_key",
        ] = df.loc[
            missing_stock_key,
            "pattern_key",
        ].astype(str)

    missing_market_key = (
        df["market_context_key"]
        .astype(str)
        .str.strip()
        .isin({"", "nan", "None"})
    )
    if missing_market_key.any():
        df.loc[
            missing_market_key,
            "market_context_key",
        ] = "LEGACY_CONTEXT"

    t3 = pd.to_numeric(
        df["t3_return_pct"],
        errors="coerce",
    )
    t5 = pd.to_numeric(
        df["t5_return_pct"],
        errors="coerce",
    )
    t10 = pd.to_numeric(
        df["t10_return_pct"],
        errors="coerce",
    )

    df["has_t3"] = t3.notna()
    df["has_t5"] = t5.notna()
    df["has_t10"] = t10.notna()

    df["t3_win_int"] = (
        df["has_t3"] & (t3 > 0)
    ).astype(int)

    df["t5_win_int"] = (
        df["has_t5"] & (t5 > 0)
    ).astype(int)

    df["t10_win_int"] = (
        df["has_t10"] & (t10 > 0)
    ).astype(int)

    rows = []
    group_fields = [
        "market_context_key",
        "stock_pattern_key",
        "pattern_key_v2",
    ]

    for keys, group in df.groupby(
        group_fields,
        dropna=False,
        sort=False,
    ):
        (
            market_context_key,
            stock_pattern_key,
            pattern_key_v2,
        ) = keys
        pattern_key = pattern_key_v2
        t3_available = group[
            group["has_t3"]
        ]

        t5_available = group[
            group["has_t5"]
        ]

        t10_available = group[
            group["has_t10"]
        ]

        # Chỉ những mẫu đã thắng T3 mới đủ điều kiện
        # để đo xác suất tiếp tục thắng T5/T10.
        t3_winners = group[
            group["has_t3"]
            & (group["t3_win_int"] == 1)
        ]

        # Chỉ những mẫu đã thắng T5 mới đủ điều kiện
        # để đo khả năng kéo dài tới T10.
        t5_winners = group[
            group["has_t5"]
            & (group["t5_win_int"] == 1)
        ]

        eligible_t3_to_t5 = t3_winners[
            t3_winners["has_t5"]
        ]

        eligible_t5_to_t10 = t5_winners[
            t5_winners["has_t10"]
        ]

        eligible_t3_to_t10 = t3_winners[
            t3_winners["has_t10"]
        ]

        row = {
            "market_context_key": market_context_key,
            "stock_pattern_key": stock_pattern_key,
            "pattern_key": pattern_key,

            "samples_t3": int(len(t3_available)),
            "wins_t3": int(
                t3_available["t3_win_int"].sum()
            ),

            "samples_t5": int(len(t5_available)),
            "wins_t5": int(
                t5_available["t5_win_int"].sum()
            ),

            "samples_t10": int(len(t10_available)),
            "wins_t10": int(
                t10_available["t10_win_int"].sum()
            ),

            "eligible_t3_to_t5": int(
                len(eligible_t3_to_t5)
            ),
            "continued_t3_to_t5": int(
                eligible_t3_to_t5[
                    "t5_win_int"
                ].sum()
            ),

            "eligible_t5_to_t10": int(
                len(eligible_t5_to_t10)
            ),
            "continued_t5_to_t10": int(
                eligible_t5_to_t10[
                    "t10_win_int"
                ].sum()
            ),

            "eligible_t3_to_t10": int(
                len(eligible_t3_to_t10)
            ),
            "continued_t3_to_t10": int(
                eligible_t3_to_t10[
                    "t10_win_int"
                ].sum()
            ),

            "avg_t3_return_pct": (
                float(
                    pd.to_numeric(
                        t3_available[
                            "t3_return_pct"
                        ],
                        errors="coerce",
                    ).mean()
                )
                if len(t3_available)
                else np.nan
            ),

            "avg_t5_return_pct": (
                float(
                    pd.to_numeric(
                        t5_available[
                            "t5_return_pct"
                        ],
                        errors="coerce",
                    ).mean()
                )
                if len(t5_available)
                else np.nan
            ),

            "avg_t10_return_pct": (
                float(
                    pd.to_numeric(
                        t10_available[
                            "t10_return_pct"
                        ],
                        errors="coerce",
                    ).mean()
                )
                if len(t10_available)
                else np.nan
            ),

            "strong_runners": int(
                group[
                    "gain_accelerating"
                ]
                .map(_safe_bool)
                .sum()
            ),

            "persistent_winners": int(
                group[
                    "persistent_win_t10"
                ]
                .map(_safe_bool)
                .sum()
            ),

            "flash_winners": int(
                group[
                    "flash_winner"
                ]
                .map(_safe_bool)
                .sum()
            ),

            "first_seen": (
                group["entry_date"].min()
            ),

            "last_seen": (
                group["entry_date"].max()
            ),
        }

        rows.append(row)

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    def pct(
        numerator_column: str,
        denominator_column: str,
    ) -> pd.Series:
        denominator = pd.to_numeric(
            result[denominator_column],
            errors="coerce",
        )

        numerator = pd.to_numeric(
            result[numerator_column],
            errors="coerce",
        )

        values = pd.Series(
            np.nan,
            index=result.index,
            dtype=float,
        )

        valid = denominator > 0

        values.loc[valid] = (
            numerator.loc[valid]
            / denominator.loc[valid]
            * 100.0
        )

        return values

    result["t3_win_rate_pct"] = pct(
        "wins_t3",
        "samples_t3",
    )

    result["t5_win_rate_pct"] = pct(
        "wins_t5",
        "samples_t5",
    )

    result["t10_win_rate_pct"] = pct(
        "wins_t10",
        "samples_t10",
    )

    result["t3_to_t5_rate_pct"] = pct(
        "continued_t3_to_t5",
        "eligible_t3_to_t5",
    )

    result["t5_to_t10_rate_pct"] = pct(
        "continued_t5_to_t10",
        "eligible_t5_to_t10",
    )

    result["t3_to_t10_rate_pct"] = pct(
        "continued_t3_to_t10",
        "eligible_t3_to_t10",
    )

    # Cận dưới Wilson rất quan trọng:
    # mẫu ít không được phép đứng đầu chỉ vì thắng 100%.
    result["t3_to_t10_lower_bound_pct"] = (
        _wilson_lower_bound(
            result["continued_t3_to_t10"],
            result["eligible_t3_to_t10"],
        )
    )

    # Chất lượng của một mẫu bền:
    # 1. Thắng từ T3 tới T10
    # 2. T5 tiếp tục thắng T10
    # 3. T3 tiếp tục thắng T5
    # 4. T10 có lợi nhuận thực
    # 5. Có đủ số mẫu để đáng tin
    result["continuation_score"] = (
        0.40
        * result[
            "t3_to_t10_lower_bound_pct"
        ].fillna(0.0)

        + 0.25
        * result[
            "t5_to_t10_rate_pct"
        ].fillna(0.0)

        + 0.20
        * result[
            "t3_to_t5_rate_pct"
        ].fillna(0.0)

        + 0.10
        * pd.to_numeric(
            result["avg_t10_return_pct"],
            errors="coerce",
        )
        .clip(-20, 30)
        .fillna(0.0)

        + 0.05
        * np.log1p(
            pd.to_numeric(
                result["samples_t10"],
                errors="coerce",
            ).fillna(0.0)
        )
        * 10.0
    )

    # Tỷ lệ mẫu thực sự chạy dai.
    sample_base = pd.to_numeric(
        result["samples_t10"],
        errors="coerce",
    )

    result["persistent_winner_rate_pct"] = np.where(
        sample_base > 0,
        pd.to_numeric(
            result["persistent_winners"],
            errors="coerce",
        )
        / sample_base
        * 100.0,
        np.nan,
    )

    result["strong_runner_rate_pct"] = np.where(
        sample_base > 0,
        pd.to_numeric(
            result["strong_runners"],
            errors="coerce",
        )
        / sample_base
        * 100.0,
        np.nan,
    )

    result["flash_winner_rate_pct"] = np.where(
        sample_base > 0,
        pd.to_numeric(
            result["flash_winners"],
            errors="coerce",
        )
        / sample_base
        * 100.0,
        np.nan,
    )
    result["pattern_version"] = "V4"
    result["context_version"] = "MARKET_CONTEXT_V1"
    result["updated_at"] = _utc_now_iso()
    result["module_version"] = MODULE_VERSION
    result["brain_generation"] = BRAIN_GENERATION
    result["feature_version"] = FEATURE_VERSION

    return result.sort_values(
        [
            "continuation_score",
            "samples_t10",
            "avg_t10_return_pct",
        ],
        ascending=[
            False,
            False,
            False,
        ],
        kind="stable",
    ).reset_index(drop=True)
def _stamp_versions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gắn thông tin version vào dataframe.

    Không ghi đè dữ liệu cũ nếu cột đã tồn tại,
    chỉ cập nhật theo version hiện tại.
    """
    if df is None:
        return pd.DataFrame()

    out = df.copy()

    out["module_version"] = MODULE_VERSION
    out["brain_generation"] = BRAIN_GENERATION
    out["feature_version"] = FEATURE_VERSION

    return out


def _build_pattern_snapshot(
    observations: pd.DataFrame,
    lifecycle: pd.DataFrame,
) -> pd.DataFrame:
    """
    Snapshot = 1 Observation + toàn bộ DNA + toàn bộ Outcome.

    Đây là bảng nền để:
        Pattern History
        Decision Archive
        Verified Decisions

    đều dùng chung một nguồn.
    """

    if observations is None or observations.empty:
        return pd.DataFrame()

    obs = _add_pattern_columns(observations)

    if lifecycle is None or lifecycle.empty:
        snapshot = obs.copy()

    else:
        life = lifecycle.copy()

        duplicated_columns = [
            c
            for c in life.columns
            if c in obs.columns
            and c not in {
                "observation_id",
                "symbol",
            }
        ]

        if duplicated_columns:
            life = life.drop(
                columns=duplicated_columns,
                errors="ignore",
            )

        snapshot = obs.merge(
            life,
            on=[
                "observation_id",
                "symbol",
            ],
            how="left",
            validate="one_to_one",
        )

    snapshot["snapshot_updated_at"] = _utc_now_iso()

    snapshot = _stamp_versions(snapshot)

    snapshot = snapshot.drop_duplicates(
        "observation_id",
        keep="last",
    )

    sort_columns = [
        c
        for c in (
            "trade_date",
            "symbol",
        )
        if c in snapshot.columns
    ]

    if sort_columns:
        snapshot = snapshot.sort_values(
            sort_columns,
            kind="stable",
        )

    snapshot.reset_index(
        drop=True,
        inplace=True,
    )

    return snapshot


def _stable_row_hash(
    df: pd.DataFrame,
) -> pd.Series:
    """
    Hash ổn định.

    Chỉ thay đổi khi dữ liệu thực sự thay đổi.

    Không phụ thuộc:
        updated_at
        snapshot_updated_at
        history_recorded_at
        ...
    """

    if df is None or df.empty:
        return pd.Series(dtype=str)

    ignore_columns = {
        "snapshot_updated_at",
        "history_recorded_at",
        "history_trade_date",
        "history_run_id",
        "recorded_at",
        "updated_at",
        "evaluated_at",
        "row_hash",
    }

    columns = sorted(
        c
        for c in df.columns
        if c not in ignore_columns
    )

    normalized = df.loc[:, columns].copy()

    for c in columns:
        normalized[c] = normalized[c].map(
            _safe_text
        )

    payload = normalized.astype(str).agg(
        "|".join,
        axis=1,
    )

    return payload.map(
        lambda x: hashlib.sha1(
            x.encode("utf-8")
        ).hexdigest()
    )
def _append_pattern_history(
    existing_history: pd.DataFrame,
    current_snapshot: pd.DataFrame,
    trade_date_value: Optional[str],
) -> Tuple[pd.DataFrame, int]:
    """
    Append-only nhưng chống phình dữ liệu: chỉ ghi mẫu mới hoặc mẫu có Outcome thay đổi.
    """
    if current_snapshot is None or current_snapshot.empty:
        return (existing_history.copy() if existing_history is not None else pd.DataFrame(), 0)

    current = current_snapshot.copy()
    current["row_hash"] = _stable_row_hash(current)

    old = existing_history.copy() if existing_history is not None else pd.DataFrame()
    latest_hash: Dict[str, str] = {}
    if not old.empty and "observation_id" in old.columns:
        if "history_recorded_at" in old.columns:
            old = old.sort_values("history_recorded_at", kind="stable")
        if "row_hash" not in old.columns:
            old["row_hash"] = _stable_row_hash(old)
        latest = old.drop_duplicates("observation_id", keep="last")
        latest_hash = dict(zip(latest["observation_id"].astype(str), latest["row_hash"].astype(str)))

    changed_mask = [
        latest_hash.get(str(obs_id)) != str(row_hash)
        for obs_id, row_hash in zip(current["observation_id"], current["row_hash"])
    ]
    changed = current.loc[changed_mask].copy()
    if changed.empty:
        return old.reset_index(drop=True), 0

    recorded_at = _utc_now_iso()
    changed["history_recorded_at"] = recorded_at
    changed["history_trade_date"] = trade_date_value or ""
    changed["history_run_id"] = _hash_payload(
        (recorded_at, trade_date_value, MODULE_VERSION, BRAIN_GENERATION)
    )
    changed = _stamp_versions(changed)

    history = pd.concat([old, changed], ignore_index=True, sort=False)
    history = history.drop_duplicates(
        ["history_run_id", "observation_id", "row_hash"],
        keep="last",
    )
    if "history_recorded_at" in history.columns:
        history = history.sort_values(
            ["history_recorded_at", "symbol"], kind="stable"
        )
    return history.reset_index(drop=True), int(len(changed))


def _build_decision_archive(
    snapshot: pd.DataFrame,
) -> pd.DataFrame:
    """Một dòng cho mỗi quyết định; giữ đầy đủ Context, DNA và Outcome hiện có."""
    if snapshot is None or snapshot.empty:
        return pd.DataFrame()

    archive = snapshot.copy()
    if "decision_id" not in archive.columns:
        archive["decision_id"] = archive.get("observation_id", "")
    archive["decision_id"] = archive["decision_id"].astype(str)

    completed = pd.to_numeric(
        archive.get("completed_horizons", pd.Series(0, index=archive.index)),
        errors="coerce",
    ).fillna(0).astype(int)
    archive["decision_status"] = np.where(
        completed > 0, "VERIFIED_PARTIAL", "PENDING_OUTCOME"
    )
    archive.loc[completed >= len(DEFAULT_HORIZONS), "decision_status"] = "VERIFIED_COMPLETE"
    archive["decision_updated_at"] = _utc_now_iso()
    archive = _stamp_versions(archive)
    return archive.drop_duplicates("decision_id", keep="last").reset_index(drop=True)


def _build_verified_decisions(
    decision_archive: pd.DataFrame,
) -> pd.DataFrame:
    """Chỉ trả các quyết định đã có ít nhất một Outcome T3/T5/T10."""
    if decision_archive is None or decision_archive.empty:
        return pd.DataFrame()

    verified = decision_archive.copy()
    completed = pd.to_numeric(
        verified.get("completed_horizons", pd.Series(0, index=verified.index)),
        errors="coerce",
    ).fillna(0).astype(int)
    verified = verified.loc[completed > 0].copy()
    if verified.empty:
        return verified

    verified["verified_level"] = np.select(
        [completed.loc[verified.index] >= 3, completed.loc[verified.index] >= 2],
        ["T10_COMPLETE", "T5_COMPLETE"],
        default="T3_COMPLETE",
    )
    verified["verified_at"] = _utc_now_iso()
    verified["is_fully_verified"] = completed.loc[verified.index] >= len(DEFAULT_HORIZONS)
    verified = _stamp_versions(verified)
    return verified.drop_duplicates("decision_id", keep="last").reset_index(drop=True)


def _build_learning_metadata(
    *,
    trade_date_value: Optional[str],
    observations: pd.DataFrame,
    outcomes: pd.DataFrame,
    knowledge: pd.DataFrame,
    lifecycle: pd.DataFrame,
    continuation: pd.DataFrame,
    snapshot: pd.DataFrame,
    history: pd.DataFrame,
    decision_archive: pd.DataFrame,
    verified_decisions: pd.DataFrame,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "last_learning_at": _utc_now_iso(),
        "last_trade_date": trade_date_value,
        "module_version": MODULE_VERSION,
        "brain_generation": BRAIN_GENERATION,
        "feature_version": FEATURE_VERSION,
        "observations_rows": int(len(observations)),
        "outcomes_rows": int(len(outcomes)),
        "knowledge_rows": int(len(knowledge)),
        "lifecycle_rows": int(len(lifecycle)),
        "continuation_rows": int(len(continuation)),
        "pattern_snapshot_rows": int(len(snapshot)),
        "pattern_history_rows": int(len(history)),
        "decision_archive_rows": int(len(decision_archive)),
        "verified_decisions_rows": int(len(verified_decisions)),
    }


def get_pattern_snapshot(
    data_dir: Optional[os.PathLike[str] | str] = None,
    *,
    remote_dir: Optional[str] = None,
) -> pd.DataFrame:
    storage = _make_storage(data_dir, remote_dir)
    snapshot, _ = _read_csv_from_storage(storage, PATTERN_SNAPSHOT_FILE)
    return snapshot


def get_pattern_history(
    data_dir: Optional[os.PathLike[str] | str] = None,
    *,
    remote_dir: Optional[str] = None,
) -> pd.DataFrame:
    storage = _make_storage(data_dir, remote_dir)
    history, _ = _read_csv_from_storage(storage, PATTERN_HISTORY_FILE)
    return history


def get_decision_archive(
    data_dir: Optional[os.PathLike[str] | str] = None,
    *,
    remote_dir: Optional[str] = None,
) -> pd.DataFrame:
    storage = _make_storage(data_dir, remote_dir)
    archive, _ = _read_csv_from_storage(storage, DECISION_ARCHIVE_FILE)
    return archive


def get_verified_decisions(
    data_dir: Optional[os.PathLike[str] | str] = None,
    *,
    remote_dir: Optional[str] = None,
) -> pd.DataFrame:
    storage = _make_storage(data_dir, remote_dir)
    verified, _ = _read_csv_from_storage(storage, VERIFIED_DECISIONS_FILE)
    return verified


def get_learning_metadata(
    data_dir: Optional[os.PathLike[str] | str] = None,
    *,
    remote_dir: Optional[str] = None,
) -> Dict[str, Any]:
    storage = _make_storage(data_dir, remote_dir)
    result = storage.read_text(LEARNING_METADATA_FILE)
    if result.text is None:
        return {
            "ok": True,
            "status": "NO_METADATA_YET",
            "module_version": MODULE_VERSION,
            "brain_generation": BRAIN_GENERATION,
            "feature_version": FEATURE_VERSION,
        }
    try:
        return json.loads(result.text)
    except Exception as exc:
        return {
            "ok": False,
            "status": "METADATA_READ_ERROR",
            "error": f"{type(exc).__name__}: {exc}",
        }


def get_pattern_lifecycle(
    data_dir: Optional[os.PathLike[str] | str] = None,
    *,
    remote_dir: Optional[str] = None,
) -> pd.DataFrame:
    storage = _make_storage(data_dir, remote_dir)
    lifecycle, _ = _read_csv_from_storage(storage, LIFECYCLE_FILE)
    return lifecycle


def get_continuation_knowledge(
    data_dir: Optional[os.PathLike[str] | str] = None,
    min_samples: int = 3,
    *,
    remote_dir: Optional[str] = None,
) -> pd.DataFrame:
    storage = _make_storage(data_dir, remote_dir)
    knowledge, _ = _read_csv_from_storage(storage, CONTINUATION_FILE)
    if knowledge.empty:
        return knowledge
    samples = pd.to_numeric(knowledge.get("samples_t10"), errors="coerce")
    return knowledge[samples >= max(1, int(min_samples))].copy().reset_index(drop=True)

def _storage_mode(
    storage: GitHubLocalStorage,
    write_results: Sequence[StorageWriteResult],
) -> str:
    if storage.github.enabled and any(
        result.github_ok for result in write_results
    ):
        return "GITHUB_PRIMARY"

    if any(result.local_ok for result in write_results):
        return "LOCAL_FALLBACK"

    return "NO_STORAGE"


def _github_sync_summary(
    storage: GitHubLocalStorage,
    write_results: Sequence[StorageWriteResult],
) -> str:
    if not storage.github.enabled:
        return "GITHUB_DISABLED"

    if write_results and all(
        result.github_ok for result in write_results
    ):
        return "GITHUB_OK"

    if any(result.github_ok for result in write_results):
        return "GITHUB_PARTIAL"

    return "GITHUB_ERROR"


def _save_status(
    storage: TextStorage,
    result: LearningResult,
) -> StorageWriteResult:
    payload = result.to_dict()
    payload["last_run_at"] = _utc_now_iso()
    payload["brain_generation"] = BRAIN_GENERATION
    payload["feature_version"] = FEATURE_VERSION

    return _write_json_to_storage(
        storage,
        STATUS_FILE,
        payload,
        commit_message=(
            f"Mr.BOT earning learning status "
            f"{result.trade_date or _utc_now_iso()}"
        ),
    )


def get_learning_status(
    data_dir: Optional[os.PathLike[str] | str] = None,
    *,
    remote_dir: Optional[str] = None,
) -> Dict[str, Any]:
    storage = _make_storage(data_dir, remote_dir)
    result = storage.read_text(STATUS_FILE)

    if result.text is None:
        return {
            "ok": True,
            "module_version": MODULE_VERSION,
            "status": "NO_RUN_YET",
            "storage_source": result.source,
            "storage_error": result.error,
        }

    try:
        payload = json.loads(result.text)
        payload.setdefault("storage_source", result.source)
        return payload
    except Exception as exc:
        return {
            "ok": False,
            "module_version": MODULE_VERSION,
            "status": "STATUS_READ_ERROR",
            "storage_source": result.source,
            "error": f"{type(exc).__name__}: {exc}",
        }


def get_pattern_knowledge(
    data_dir: Optional[os.PathLike[str] | str] = None,
    min_samples: int = 3,
    *,
    remote_dir: Optional[str] = None,
) -> pd.DataFrame:
    storage = _make_storage(data_dir, remote_dir)
    knowledge, _ = _read_csv_from_storage(
        storage,
        KNOWLEDGE_FILE,
    )

    if knowledge.empty:
        return knowledge

    samples = pd.to_numeric(
        knowledge.get("samples"),
        errors="coerce",
    )

    return knowledge[
        samples >= max(1, int(min_samples))
    ].copy().reset_index(drop=True)
def update_learning(
    earning_board_df: pd.DataFrame,
    *,
    market_context: Optional[Mapping[str, Any]] = None,
    data_dir: Optional[os.PathLike[str] | str] = None,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    strict: bool = False,
    remote_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lưu Earning Money Board hiện tại và cập nhật Outcome T+3/T+5/T+10.

    Tương thích ngược:
    -----------------
    Cách gọi cũ vẫn giữ nguyên:

        result = update_learning(
            earning_board_df,
            market_context=market_context,
        )

    Fail-safe:
    ----------
    Mặc định mọi lỗi đều được giữ trong kết quả trả về, không làm app.py chết.
    Chỉ dùng strict=True khi test local hoặc debug.
    """

    input_rows = (
        len(earning_board_df)
        if isinstance(earning_board_df, pd.DataFrame)
        else 0
    )
    storage = _make_storage(data_dir, remote_dir)

    try:
        with _LOCK:
            valid_horizons = _validate_horizons(horizons)
            canonical = _adapt_board(
                earning_board_df,
                market_context=market_context,
            )

            if canonical.empty:
                result = LearningResult(
                    ok=True,
                    module_version=MODULE_VERSION,
                    trade_date=None,
                    input_rows=input_rows,
                    valid_rows=0,
                    observations_added=0,
                    observations_updated=0,
                    outcomes_added=0,
                    knowledge_rows=0,
                    lifecycle_rows=0,
                    continuation_rows=0,
                    storage_mode=(
                        "GITHUB_PRIMARY"
                        if storage.github.enabled
                        else "LOCAL_ONLY"
                    ),
                    github_sync=(
                        "NOT_ATTEMPTED"
                        if storage.github.enabled
                        else "GITHUB_DISABLED"
                    ),
                    skipped_reason="EMPTY_OR_NO_VALID_SYMBOL",
                )
                _save_status(storage, result)
                return result.to_dict()

            trade_dates = sorted(
                canonical["trade_date"].astype(str).unique()
            )
            trade_date_value = (
                trade_dates[-1] if trade_dates else None
            )

            existing_observations, _ = _read_csv_from_storage(
                storage,
                OBSERVATIONS_FILE,
            )
            observations, added, updated = _upsert_observations(
                existing_observations,
                canonical,
            )

            old_outcomes, _ = _read_csv_from_storage(
                storage,
                OUTCOMES_FILE,
            )
            outcomes = _build_outcomes(
                observations,
                horizons=valid_horizons,
            )

            old_ids = set(
                old_outcomes.get(
                    "outcome_id",
                    pd.Series(dtype=str),
                ).astype(str)
            )
            new_ids = set(
                outcomes.get(
                    "outcome_id",
                    pd.Series(dtype=str),
                ).astype(str)
            )
            outcomes_added = len(new_ids - old_ids)

            knowledge = _build_pattern_knowledge(
                observations,
                outcomes,
            )
            lifecycle = _build_pattern_lifecycle(
                observations,
                outcomes,
            )
            continuation = _build_continuation_knowledge(lifecycle)

            # Data Foundation: kho phẳng hiện tại + lịch sử append-only có chống trùng.
            snapshot = _build_pattern_snapshot(observations, lifecycle)
            old_history, _ = _read_csv_from_storage(
                storage,
                PATTERN_HISTORY_FILE,
            )
            history, history_added = _append_pattern_history(
                old_history,
                snapshot,
                trade_date_value,
            )
            decision_archive = _build_decision_archive(snapshot)
            verified_decisions = _build_verified_decisions(decision_archive)
            metadata = _build_learning_metadata(
                trade_date_value=trade_date_value,
                observations=observations,
                outcomes=outcomes,
                knowledge=knowledge,
                lifecycle=lifecycle,
                continuation=continuation,
                snapshot=snapshot,
                history=history,
                decision_archive=decision_archive,
                verified_decisions=verified_decisions,
            )

            write_results = []

            write_results.append(
                _write_csv_to_storage(
                    storage,
                    OBSERVATIONS_FILE,
                    observations,
                    commit_message=(
                        "Mr.BOT update earning observations "
                        f"{trade_date_value}"
                    ),
                )
            )

            # Ghi file rỗng có header chỉ khi đã từng có dữ liệu.
            # Nếu chưa đủ T+n thì giữ file cũ hoặc chưa tạo để tránh mất schema.
            if not outcomes.empty or not old_outcomes.empty:
                write_results.append(
                    _write_csv_to_storage(
                        storage,
                        OUTCOMES_FILE,
                        outcomes,
                        commit_message=(
                            "Mr.BOT update earning outcomes "
                            f"{trade_date_value}"
                        ),
                    )
                )

            if not knowledge.empty:
                write_results.append(
                    _write_csv_to_storage(
                        storage,
                        KNOWLEDGE_FILE,
                        knowledge,
                        commit_message=(
                            "Mr.BOT update pattern knowledge "
                            f"{trade_date_value}"
                        ),
                    )
                )

            if not lifecycle.empty:
                write_results.append(
                    _write_csv_to_storage(
                        storage,
                        LIFECYCLE_FILE,
                        lifecycle,
                        commit_message=(
                            "Mr.BOT update pattern lifecycle "
                            f"{trade_date_value}"
                        ),
                    )
                )

            if not continuation.empty:
                write_results.append(
                    _write_csv_to_storage(
                        storage,
                        CONTINUATION_FILE,
                        continuation,
                        commit_message=(
                            "Mr.BOT update continuation knowledge "
                            f"{trade_date_value}"
                        ),
                    )
                )

            if not snapshot.empty:
                write_results.append(
                    _write_csv_to_storage(
                        storage,
                        PATTERN_SNAPSHOT_FILE,
                        snapshot,
                        commit_message=(
                            "Mr.BOT update pattern snapshot "
                            f"{trade_date_value}"
                        ),
                    )
                )

            if not history.empty:
                write_results.append(
                    _write_csv_to_storage(
                        storage,
                        PATTERN_HISTORY_FILE,
                        history,
                        commit_message=(
                            "Mr.BOT append pattern history "
                            f"{trade_date_value} +{history_added}"
                        ),
                    )
                )

            if not decision_archive.empty:
                write_results.append(
                    _write_csv_to_storage(
                        storage,
                        DECISION_ARCHIVE_FILE,
                        decision_archive,
                        commit_message=(
                            "Mr.BOT update decision archive "
                            f"{trade_date_value}"
                        ),
                    )
                )

            if not verified_decisions.empty:
                write_results.append(
                    _write_csv_to_storage(
                        storage,
                        VERIFIED_DECISIONS_FILE,
                        verified_decisions,
                        commit_message=(
                            "Mr.BOT update verified decisions "
                            f"{trade_date_value}"
                        ),
                    )
                )

            write_results.append(
                _write_json_to_storage(
                    storage,
                    LEARNING_METADATA_FILE,
                    metadata,
                    commit_message=(
                        "Mr.BOT update learning metadata "
                        f"{trade_date_value}"
                    ),
                )
            )

            failed_everywhere = any(
                not write.local_ok and not write.github_ok
                for write in write_results
            )
            if failed_everywhere:
                raise IOError(
                    "At least one learning file could not be saved "
                    "to local or GitHub"
                )

            storage_mode = _storage_mode(
                storage,
                write_results,
            )
            github_sync = _github_sync_summary(
                storage,
                write_results,
            )

            result = LearningResult(
                ok=True,
                module_version=MODULE_VERSION,
                trade_date=trade_date_value,
                input_rows=input_rows,
                valid_rows=len(canonical),
                observations_added=added,
                observations_updated=updated,
                outcomes_added=outcomes_added,
                knowledge_rows=len(knowledge),
                lifecycle_rows=len(lifecycle),
                continuation_rows=len(continuation),
                snapshot_rows=len(snapshot),
                history_rows=len(history),
                decision_archive_rows=len(decision_archive),
                verified_decisions_rows=len(verified_decisions),
                storage_mode=storage_mode,
                github_sync=github_sync,
            )

            status_result = _save_status(storage, result)

            # Status lỗi không được làm mất kết quả học đã ghi thành công.
            if (
                not status_result.local_ok
                and not status_result.github_ok
            ):
                _LOGGER.warning(
                    "Learning succeeded but status file could not be saved"
                )

            return result.to_dict()

    except Exception as exc:
        _LOGGER.exception("Earning Learning failed safely")

        result = LearningResult(
            ok=False,
            module_version=MODULE_VERSION,
            trade_date=None,
            input_rows=input_rows,
            valid_rows=0,
            observations_added=0,
            observations_updated=0,
            outcomes_added=0,
            knowledge_rows=0,
            storage_mode=(
                "GITHUB_PRIMARY"
                if storage.github.enabled
                else "LOCAL_ONLY"
            ),
            github_sync=(
                "GITHUB_ERROR"
                if storage.github.enabled
                else "GITHUB_DISABLED"
            ),
            error=f"{type(exc).__name__}: {exc}",
        )

        try:
            _save_status(storage, result)
        except Exception:
            _LOGGER.exception(
                "Cannot save Learning failure status"
            )

        if strict:
            raise

        return result.to_dict()


# ------------------------------------------------------------------
# Experience bridge (Decision Engine read path)
# Thresholds mirror decision_engine.MIN_PATTERN_SAMPLES / MIN_CONTINUATION_SAMPLES.
# Per-stock cap is intentionally lower than market-level MAX_V3_LEARNING (±18).
# ------------------------------------------------------------------
_EXPERIENCE_MIN_PATTERN_SAMPLES = 5
_EXPERIENCE_MIN_CONTINUATION_SAMPLES = 5
_EXPERIENCE_MAX_ADJUSTMENT = 8.0
_EXPERIENCE_PATTERN_COMPONENT_CAP = 5.0
_EXPERIENCE_CONTINUATION_COMPONENT_CAP = 3.0


def _neutral_experience_values() -> Dict[str, Any]:
    return {
        "stock_pattern_key": "",
        "market_context_key": "",
        "pattern_key": "",
        "ExperienceAdjustment": 0.0,
        "ExperienceSamples": 0,
        "LearnedWinRate": np.nan,
        "ContinuationScore": np.nan,
        "MatchedPattern": "",
        "MatchedMarketContext": "",
        "LearningStatus": "READY_FOR_CONNECTION",
    }


def _experience_int(value: Any, default: int = 0) -> int:
    parsed = _safe_float(value)
    if not math.isfinite(parsed):
        return default
    return int(parsed)
def _decision_rows_for_pattern_keys(
    decision_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
    breadth: float | None = None,
) -> pd.DataFrame:

    """
    Map decision rows onto the same canonical observation shape used by
    update_learning(), then derive keys via _add_pattern_columns().
    Preserves the original index for row-aligned merge back.
    """
    source = decision_df.copy(deep=True)
    canonical = pd.DataFrame(index=source.index)

    for canonical_name, aliases in COLUMN_ALIASES.items():
        source_col = _find_source_column(source.columns, aliases)
        canonical[canonical_name] = (
            source[source_col]
            if source_col is not None
            else np.nan
        )

    market_score = _safe_float(market_real)
    forecast = _safe_float(market_forecast)
    if canonical["market_score"].isna().all() and math.isfinite(market_score):
        canonical["market_score"] = market_score
    if canonical["market_forecast"].isna().all() and math.isfinite(forecast):
        canonical["market_forecast"] = forecast
    breadth_value = _safe_float(breadth)
    if canonical["breadth"].isna().all() and math.isfinite(breadth_value):
    canonical["breadth"] = breadth_value
    for field in NUMERIC_FIELDS:
        if field in canonical.columns:
            canonical[field] = canonical[field].map(_safe_float)

    for field in BOOLEAN_FIELDS:
        if field in canonical.columns:
            canonical[field] = canonical[field].map(_safe_bool)

    # Preserve rs_spread supplied by BUY ELITE when rs5 is not carried into
    # the compact decision frame.  Previously it was overwritten with NaN,
    # which changed stock_pattern_key and prevented historical matches.
    supplied_rs_spread = pd.to_numeric(
        canonical.get("rs_spread"), errors="coerce"
    )
    calculated_rs_spread = (
        pd.to_numeric(canonical.get("rs5"), errors="coerce")
        - pd.to_numeric(canonical.get("rs10"), errors="coerce")
    )
    canonical["rs_spread"] = calculated_rs_spread.where(
        calculated_rs_spread.notna(), supplied_rs_spread
    )

    vol_ma20 = pd.to_numeric(canonical.get("vol_ma20"), errors="coerce")
    volume = pd.to_numeric(canonical.get("volume"), errors="coerce")
    canonical["volume_ratio20"] = np.where(
        vol_ma20.abs() > 1e-12,
        volume / vol_ma20,
        pd.to_numeric(canonical.get("volume_ratio"), errors="coerce"),
    )

    keyed = _add_pattern_columns(canonical)
    return keyed[
        [
            "stock_pattern_key",
            "market_context_key",
            "pattern_key",
        ]
    ]


def _pattern_knowledge_lookup(
    pattern_df: pd.DataFrame,
) -> Dict[Tuple[str, str, int], pd.Series]:
    if pattern_df is None or pattern_df.empty:
        return {}

    required = {
        "market_context_key",
        "stock_pattern_key",
        "horizon",
    }
    if not required.issubset(pattern_df.columns):
        return {}

    lookup: Dict[Tuple[str, str, int], pd.Series] = {}
    df = pattern_df.copy()
    df["horizon"] = pd.to_numeric(df["horizon"], errors="coerce")

    for (market_key, stock_key, horizon), group in df.groupby(
        ["market_context_key", "stock_pattern_key", "horizon"],
        dropna=False,
        sort=False,
    ):
        if pd.isna(horizon):
            continue
        horizon_int = int(horizon)
        samples = pd.to_numeric(group.get("samples"), errors="coerce").fillna(0)
        best = group.loc[samples.idxmax()] if not group.empty else group.iloc[0]
        lookup[
            (
                str(market_key),
                str(stock_key),
                horizon_int,
            )
        ] = best

    return lookup


def _continuation_knowledge_lookup(
    continuation_df: pd.DataFrame,
) -> Dict[Tuple[str, str], pd.Series]:
    if continuation_df is None or continuation_df.empty:
        return {}

    required = {
        "market_context_key",
        "stock_pattern_key",
    }
    if not required.issubset(continuation_df.columns):
        return {}

    lookup: Dict[Tuple[str, str], pd.Series] = {}
    df = continuation_df.copy()

    for (market_key, stock_key), group in df.groupby(
        ["market_context_key", "stock_pattern_key"],
        dropna=False,
        sort=False,
    ):
        samples_t10 = pd.to_numeric(
            group.get("samples_t10"),
            errors="coerce",
        ).fillna(0)
        best = group.loc[samples_t10.idxmax()] if not group.empty else group.iloc[0]
        lookup[(str(market_key), str(stock_key))] = best

    return lookup


def _market_context_family(market_context_key: str) -> Tuple[str, str]:
    """Return (forecast_bucket, market_bucket), intentionally ignoring breadth.

    BUY ELITE currently receives market_real and market_forecast but not breadth.
    Exact context matching remains first priority.  This reduced key is only a
    conservative fallback when breadth is unavailable in the decision frame.
    """
    parts = str(market_context_key).split("|")
    if len(parts) >= 3:
        return parts[0], parts[2]
    return str(market_context_key), ""


def _lookup_pattern_row(
    lookup: Dict[Tuple[str, str, int], pd.Series],
    market_context_key: str,
    stock_pattern_key: str,
    *,
    preferred_horizon: int = 5,
    fallback_horizon: int = 10,
) -> Optional[pd.Series]:
    if not lookup:
        return None

    # 1) Exact pair: market context + stock DNA.
    for horizon in (preferred_horizon, fallback_horizon):
        row = lookup.get((market_context_key, stock_pattern_key, horizon))
        if row is not None:
            return row

    # 2) Breadth-safe fallback: same forecast bucket + same Market Real bucket
    # and exactly the same stock DNA.  Never crosses market regime or stock DNA.
    target_family = _market_context_family(market_context_key)
    for horizon in (preferred_horizon, fallback_horizon):
        candidates = []
        for (ctx_key, stock_key, h), row in lookup.items():
            if (
                stock_key == stock_pattern_key
                and h == horizon
                and _market_context_family(ctx_key) == target_family
            ):
                candidates.append(row)
        if candidates:
            return max(
                candidates,
                key=lambda r: _experience_int(r.get("samples")),
            )

    return None


def _lookup_continuation_row(
    lookup: Dict[Tuple[str, str], pd.Series],
    market_context_key: str,
    stock_pattern_key: str,
) -> Optional[pd.Series]:
    if not lookup:
        return None

    row = lookup.get((market_context_key, stock_pattern_key))
    if row is not None:
        return row

    target_family = _market_context_family(market_context_key)
    candidates = [
        candidate
        for (ctx_key, stock_key), candidate in lookup.items()
        if (
            stock_key == stock_pattern_key
            and _market_context_family(ctx_key) == target_family
        )
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda r: _experience_int(r.get("samples_t10")),
    )


def _compute_experience_adjustment(
    pattern_row: Optional[Mapping[str, Any]],
    continuation_row: Optional[Mapping[str, Any]],
) -> float:
    """
    Conservative bounded adjustment for one stock row.

    Thresholds (documented for Step 2 wiring):
    - Pattern: requires samples >= 5 (same as decision_engine.MIN_PATTERN_SAMPLES).
      Uses win_rate_lower_bound_pct when present; otherwise win_rate_pct * 0.85.
      Positive: lower bound >= 55 (+2) or >= 65 (+4).
      Negative: lower bound <= 45 (-2) or <= 35 (-4).
    - Continuation: requires samples_t10 >= 5
      (same as decision_engine.MIN_CONTINUATION_SAMPLES).
      Uses continuation_score with t3_to_t10_lower_bound_pct as tie-breaker.
      Positive: score >= 55 (+1.5) or >= 65 / lower bound >= 65 (+3).
      Negative: score <= 45 (-1.5) or <= 35 / lower bound < 30 (-3).
    - Total hard cap: +/- 8.0 per row (below market-level +/- 18).
    """
    pattern_adj = 0.0
    continuation_adj = 0.0

    if pattern_row is not None:
        pattern_samples_val = _safe_float(pattern_row.get("samples"))
        samples = (
            int(pattern_samples_val)
            if math.isfinite(pattern_samples_val)
            else 0
        )
        if samples >= _EXPERIENCE_MIN_PATTERN_SAMPLES:
            lower = _safe_float(pattern_row.get("win_rate_lower_bound_pct"))
            win_rate = _safe_float(pattern_row.get("win_rate_pct"))
            evidence = lower
            if not math.isfinite(evidence):
                evidence = (
                    win_rate * 0.85
                    if math.isfinite(win_rate)
                    else np.nan
                )
            if math.isfinite(evidence):
                if evidence >= 65:
                    pattern_adj = 4.0
                elif evidence >= 55:
                    pattern_adj = 2.0
                elif evidence <= 35:
                    pattern_adj = -4.0
                elif evidence <= 45:
                    pattern_adj = -2.0

            pattern_adj = float(
                np.clip(
                    pattern_adj,
                    -_EXPERIENCE_PATTERN_COMPONENT_CAP,
                    _EXPERIENCE_PATTERN_COMPONENT_CAP,
                )
            )

    if continuation_row is not None:
        samples_t10 = _experience_int(continuation_row.get("samples_t10"))
        if samples_t10 >= _EXPERIENCE_MIN_CONTINUATION_SAMPLES:
            score = _safe_float(continuation_row.get("continuation_score"))
            lower = _safe_float(
                continuation_row.get("t3_to_t10_lower_bound_pct")
            )
            if math.isfinite(score) or math.isfinite(lower):
                if (
                    (math.isfinite(score) and score >= 65)
                    or (math.isfinite(lower) and lower >= 65)
                ):
                    continuation_adj = 3.0
                elif (
                    (math.isfinite(score) and score >= 55)
                    or (math.isfinite(lower) and lower >= 50)
                ):
                    continuation_adj = 1.5
                elif (
                    (math.isfinite(score) and score <= 35)
                    or (math.isfinite(lower) and lower < 30)
                ):
                    continuation_adj = -3.0
                elif math.isfinite(score) and score <= 45:
                    continuation_adj = -1.5

            continuation_adj = float(
                np.clip(
                    continuation_adj,
                    -_EXPERIENCE_CONTINUATION_COMPONENT_CAP,
                    _EXPERIENCE_CONTINUATION_COMPONENT_CAP,
                )
            )

    total = pattern_adj + continuation_adj
    return float(
        np.clip(
            total,
            -_EXPERIENCE_MAX_ADJUSTMENT,
            _EXPERIENCE_MAX_ADJUSTMENT,
        )
    )


def _resolve_learning_status(
    pattern_row: Optional[Mapping[str, Any]],
    continuation_row: Optional[Mapping[str, Any]],
    experience_adjustment: float,
) -> str:
    has_pattern = pattern_row is not None
    has_continuation = continuation_row is not None

    if not has_pattern and not has_continuation:
        return "NO_PATTERN_MATCH"

    pattern_samples = _experience_int(
        pattern_row.get("samples") if pattern_row is not None else np.nan
    )
    continuation_samples = _experience_int(
        continuation_row.get("samples_t10")
        if continuation_row is not None
        else np.nan
    )

    pattern_ok = (
        has_pattern
        and pattern_samples >= _EXPERIENCE_MIN_PATTERN_SAMPLES
    )
    continuation_ok = (
        has_continuation
        and continuation_samples >= _EXPERIENCE_MIN_CONTINUATION_SAMPLES
    )

    if not pattern_ok and not continuation_ok:
        return "INSUFFICIENT_SAMPLES"

    if pattern_ok and continuation_ok:
        if experience_adjustment != 0.0:
            return "EXPERIENCE_ACTIVE"
        return "PATTERN_AND_CONTINUATION_LOADED"

    if pattern_ok:
        if experience_adjustment != 0.0:
            return "EXPERIENCE_ACTIVE"
        return "PATTERN_LOADED"

    if continuation_ok:
        if experience_adjustment != 0.0:
            return "EXPERIENCE_ACTIVE"
        return "CONTINUATION_LOADED"

    return "INSUFFICIENT_SAMPLES"


def _row_experience_from_keys(
    stock_pattern_key: str,
    market_context_key: str,
    pattern_key: str,
    pattern_lookup: Dict[Tuple[str, str, int], pd.Series],
    continuation_lookup: Dict[Tuple[str, str], pd.Series],
) -> Dict[str, Any]:
    result = _neutral_experience_values()
    result["stock_pattern_key"] = stock_pattern_key
    result["market_context_key"] = market_context_key
    result["pattern_key"] = pattern_key

    if not stock_pattern_key.strip() or not market_context_key.strip():
        result["LearningStatus"] = "KEY_GENERATION_FAILED"
        return result

    pattern_row = _lookup_pattern_row(
        pattern_lookup,
        market_context_key,
        stock_pattern_key,
        preferred_horizon=5,
        fallback_horizon=10,
    )
    continuation_row = _lookup_continuation_row(
        continuation_lookup,
        market_context_key,
        stock_pattern_key,
    )

    if pattern_row is not None:
        result["ExperienceSamples"] = _experience_int(
            pattern_row.get("samples")
        )
        win_rate = _safe_float(pattern_row.get("win_rate_pct"))
        result["LearnedWinRate"] = (
            float(win_rate) if math.isfinite(win_rate) else np.nan
        )
        matched_pattern = _safe_text(pattern_row.get("pattern_key"))
        result["MatchedPattern"] = (
            matched_pattern or pattern_key
        )

    if continuation_row is not None:
        continuation_score = _safe_float(
            continuation_row.get("continuation_score")
        )
        result["ContinuationScore"] = (
            float(continuation_score)
            if math.isfinite(continuation_score)
            else np.nan
        )

    matched_context = ""
    if pattern_row is not None:
        matched_context = _safe_text(pattern_row.get("market_context_key"))
    if not matched_context and continuation_row is not None:
        matched_context = _safe_text(continuation_row.get("market_context_key"))
    result["MatchedMarketContext"] = matched_context or market_context_key
    result["ExperienceAdjustment"] = _compute_experience_adjustment(
        pattern_row,
        continuation_row,
    )
    result["LearningStatus"] = _resolve_learning_status(
        pattern_row,
        continuation_row,
        float(result["ExperienceAdjustment"]),
    )
    return result
def apply_learning_experience(
    decision_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
    breadth: float | None = None,
) -> pd.DataFrame:

    """
    Cầu nối giữa Learning Engine và Decision Engine.

    Step 1:
    - Gắn bằng chứng học theo từng mã (stock_pattern_key + market_context_key).
    - Không ghi đè quyết định; ExperienceAdjustment chưa được nối vào EliteScore.
    - Fail-safe: mọi lỗi đọc/khớp đều trả về giá trị trung tính cho từng dòng.
    """
    if decision_df is None or decision_df.empty:
        return decision_df

    out = decision_df.copy()
    defaults = _neutral_experience_values()
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default

    try:
        pattern_df = get_pattern_knowledge(min_samples=1)
    except Exception:
        pattern_df = pd.DataFrame()

    try:
        continuation_df = get_continuation_knowledge(min_samples=1)
    except Exception:
        continuation_df = pd.DataFrame()

    try:
        key_frame = _decision_rows_for_pattern_keys(
            out,
            market_real=market_real,
            market_forecast=market_forecast,
            breadth=breadth,
            )
        
    except Exception:
        _LOGGER.exception(
            "apply_learning_experience key generation failed safely"
        )
        return out

    if pattern_df.empty and continuation_df.empty:
        for idx in out.index:
            try:
                keys = key_frame.loc[idx]
                out.at[idx, "stock_pattern_key"] = str(
                    keys.get("stock_pattern_key", "")
                )
                out.at[idx, "market_context_key"] = str(
                    keys.get("market_context_key", "")
                )
                out.at[idx, "pattern_key"] = str(keys.get("pattern_key", ""))
                out.at[idx, "LearningStatus"] = "NO_KNOWLEDGE_DATA"
            except Exception:
                pass
        return out

    pattern_lookup = _pattern_knowledge_lookup(pattern_df)
    continuation_lookup = _continuation_knowledge_lookup(continuation_df)

    experience_rows: List[Dict[str, Any]] = []
    for idx in out.index:
        try:
            keys = key_frame.loc[idx]
            experience_rows.append(
                _row_experience_from_keys(
                    stock_pattern_key=str(keys.get("stock_pattern_key", "")),
                    market_context_key=str(
                        keys.get("market_context_key", "")
                    ),
                    pattern_key=str(keys.get("pattern_key", "")),
                    pattern_lookup=pattern_lookup,
                    continuation_lookup=continuation_lookup,
                )
            )
        except Exception:
            _LOGGER.exception(
                "apply_learning_experience row lookup failed safely"
            )
            experience_rows.append(_neutral_experience_values())

    experience_df = pd.DataFrame(experience_rows, index=out.index)
    for col in defaults:
        out[col] = experience_df[col]

    return out


learn_from_earning_board = update_learning


__all__ = [
    "MODULE_VERSION",
    "DEFAULT_HORIZONS",
    "BRAIN_GENERATION",
    "FEATURE_VERSION",
    "update_learning",
    "learn_from_earning_board",
    "get_learning_status",
    "get_pattern_knowledge",
    "get_pattern_lifecycle",
    "get_continuation_knowledge",
    "get_pattern_snapshot",
    "get_pattern_history",
    "get_decision_archive",
    "get_verified_decisions",
    "get_learning_metadata",
    "apply_learning_experience",
]
