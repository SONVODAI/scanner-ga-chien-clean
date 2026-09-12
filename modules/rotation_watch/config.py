"""Human-editable Rotation watchlist. Not a Candidate / Edge / Learning store."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from modules.intraday_memory.normalize import normalize_price_to_integer_vnd
from modules.rotation_watch.constants import ENV_DIR, ENV_WATCHLIST, WATCHLIST_NAME

COLUMNS = (
    "symbol",
    "enabled",
    "lower_min",
    "lower_max",
    "upper_min",
    "upper_max",
    "entry_price",
    "entry_date",
    "note",
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def default_watch_dir() -> Path:
    raw = os.environ.get(ENV_DIR, "").strip()
    if raw:
        return Path(raw)
    return REPO_ROOT / "data" / "rotation_watch"


def default_watchlist_path() -> Path:
    raw = os.environ.get(ENV_WATCHLIST, "").strip()
    if raw:
        return Path(raw)
    return default_watch_dir() / WATCHLIST_NAME


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _optional_price_vnd(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    return normalize_price_to_integer_vnd(value)


def _required_price_vnd(value: Any, field: str) -> int:
    parsed = _optional_price_vnd(value)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def _optional_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    return date.fromisoformat(text[:10])


def quoted_price(vnd: int | None) -> float | None:
    if vnd is None:
        return None
    return vnd / 1000.0


@dataclass(frozen=True)
class WatchRow:
    symbol: str
    enabled: bool
    lower_min_vnd: int
    lower_max_vnd: int
    upper_min_vnd: int
    upper_max_vnd: int
    entry_price_vnd: int | None
    entry_date: date | None
    note: str
    source_path: str

    @property
    def has_position(self) -> bool:
        return self.entry_price_vnd is not None

    @property
    def zones_valid(self) -> bool:
        return (
            self.lower_min_vnd < self.lower_max_vnd
            and self.upper_min_vnd < self.upper_max_vnd
            and self.lower_min_vnd < self.upper_max_vnd
        )


def load_watchlist(path: Path | None = None, *, include_disabled: bool = False) -> list[WatchRow]:
    src = path or default_watchlist_path()
    if not src.exists():
        return []

    import pandas as pd

    df = pd.read_csv(src, dtype=str, keep_default_na=False)
    if df.empty:
        return []
    rows: list[WatchRow] = []
    for _, raw in df.iterrows():
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        enabled = _as_bool(raw.get("enabled", True))
        if not enabled and not include_disabled:
            continue
        try:
            row = WatchRow(
                symbol=symbol,
                enabled=enabled,
                lower_min_vnd=_required_price_vnd(raw.get("lower_min"), "lower_min"),
                lower_max_vnd=_required_price_vnd(raw.get("lower_max"), "lower_max"),
                upper_min_vnd=_required_price_vnd(raw.get("upper_min"), "upper_min"),
                upper_max_vnd=_required_price_vnd(raw.get("upper_max"), "upper_max"),
                entry_price_vnd=_optional_price_vnd(raw.get("entry_price")),
                entry_date=_optional_date(raw.get("entry_date")),
                note=str(raw.get("note") or "").strip(),
                source_path=str(src),
            )
        except (ValueError, TypeError):
            continue
        rows.append(row)
    return rows
