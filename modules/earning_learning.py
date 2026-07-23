"""
MR.BOT PRO - EARNING MONEY LEARNING ENGINE V2
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


MODULE_VERSION = "2.0.0"
DEFAULT_HORIZONS: Tuple[int, ...] = (3, 5, 10)

DEFAULT_DATA_DIR = Path("data") / "earning_learning"
DEFAULT_GITHUB_DIR = "data/earning_learning"
DEFAULT_GITHUB_OWNER = "SONVODAI"
DEFAULT_GITHUB_REPO = "scanner-ga-chien-clean"
DEFAULT_GITHUB_BRANCH = "main"

OBSERVATIONS_FILE = "observations.csv"
OUTCOMES_FILE = "outcomes.csv"
KNOWLEDGE_FILE = "pattern_knowledge.csv"
STATUS_FILE = "status.json"

_DATA_FILES = (
    OBSERVATIONS_FILE,
    OUTCOMES_FILE,
    KNOWLEDGE_FILE,
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
    "early": ("early", "early_signal", "early_dry_green2"),
    "pull": ("pull", "pull_label", "pull_signal"),
    "group": ("group", "evolution_stage", "stage"),
    "sector": ("sector", "industry", "ngành", "Ngành"),
    "market_score": ("market_score", "market_real", "market_health"),
    "market_regime": ("market_regime", "regime", "market_state"),
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

    for field in ("market_score", "market_regime"):
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

    canonical["recorded_at"] = _utc_now_iso()
    canonical["module_version"] = MODULE_VERSION

    canonical = canonical.drop_duplicates(
        subset=["trade_date", "symbol"],
        keep="last",
    )

    ordered = [
        "observation_id",
        "trade_date",
        "recorded_at",
        "module_version",
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
        "market_score",
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
        "market_score": np.nan,
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
    out["p_market"] = _bucket_numeric(
        out["market_score"],
        (4, 6, 8),
        ("<4", "4-6", "6-8", ">=8"),
    )

    fields = [
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
        "p_market",
    ]

    out["pattern_key"] = out[fields].astype(str).agg(
        "|".join,
        axis=1,
    )

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
            ["pattern_key", "horizon"],
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

    knowledge["updated_at"] = _utc_now_iso()
    knowledge["module_version"] = MODULE_VERSION

    return knowledge.sort_values(
        ["horizon", "knowledge_score", "samples"],
        ascending=[True, False, False],
        kind="stable",
    ).reset_index(drop=True)


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


learn_from_earning_board = update_learning


__all__ = [
    "MODULE_VERSION",
    "DEFAULT_HORIZONS",
    "update_learning",
    "learn_from_earning_board",
    "get_learning_status",
    "get_pattern_knowledge",
]
