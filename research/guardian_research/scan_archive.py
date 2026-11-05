"""Read one persisted scan session. This module does not scan or write."""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

INPUTS = ("price", "ema9", "ma20", "obv", "obv_ema9")
SNAPSHOT_FILE = Path("data") / "earning_money_snapshots.csv"
OBSERVATION_FILE = Path("data") / "earning_learning" / "observations.csv"
FREEZE_FILE = Path("data") / "earning_learning" / "t0_observation_freeze.csv"


class ArchiveRejected(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def load_persisted_scan(project_root: Path, session: str, tracked: tuple[str, ...]) -> dict:
    """Return one same-session frame, or reject it. Nothing is filled in."""
    try:
        day = date.fromisoformat(session)
    except ValueError as exc:
        raise ArchiveRejected("SESSION_DATE_INVALID") from exc
    snapshot = _read_table(
        Path(project_root) / SNAPSHOT_FILE,
        ("snapshot_date", "symbol", "saved_at", "market_real", "is_live_adjusted", *INPUTS),
        "SCAN_ARCHIVE_ABSENT",
    )
    selected = _session_rows(snapshot, "snapshot_date", day.isoformat())
    if selected.empty:
        raise ArchiveRejected("SCAN_SESSION_ABSENT")
    saved_at = _one_saved_at(selected["saved_at"], day)
    symbols = _symbols(selected["symbol"])
    if len(set(symbols)) != len(symbols):
        raise ArchiveRejected("DUPLICATE_SYMBOLS")
    if set(symbols) != set(tracked):
        missing = [symbol for symbol in tracked if symbol not in set(symbols)]
        if missing:
            raise ArchiveRejected("MISSING_SYMBOLS")
        raise ArchiveRejected("EXTRA_SYMBOLS")
    if not _inputs_complete(selected):
        raise ArchiveRejected("INCOMPLETE_INPUT")
    live = _live_flags(selected["is_live_adjusted"])
    if live is None:
        raise ArchiveRejected("INCOMPLETE_INPUT")
    market_real, market_source = _market_real(project_root, day.isoformat(), selected, tracked)
    frame = pd.DataFrame(
        {
            "symbol": symbols,
            "date": day.isoformat(),
            "price": pd.to_numeric(selected["price"], errors="coerce").to_numpy(),
            "ema9": pd.to_numeric(selected["ema9"], errors="coerce").to_numpy(),
            "ma20": pd.to_numeric(selected["ma20"], errors="coerce").to_numpy(),
            "obv": pd.to_numeric(selected["obv"], errors="coerce").to_numpy(),
            "obv_ema9": pd.to_numeric(selected["obv_ema9"], errors="coerce").to_numpy(),
            "is_live_adjusted": live,
        }
    )
    return {
        "scan_df": frame,
        "market_real": market_real,
        "coverage": {"requested": list(tracked), "errors": []},
        "provenance": {
            "source": SNAPSHOT_FILE.as_posix(),
            "session": day.isoformat(),
            "rows": int(len(frame)),
            "saved_at": saved_at,
            "market_real_source": market_source,
        },
    }


def _market_real(project_root: Path, session: str, snapshot: pd.DataFrame, tracked: tuple[str, ...]):
    stored = _single_market(snapshot["market_real"])
    if stored == "conflict":
        raise ArchiveRejected("MARKET_CONTEXT_CONFLICT")
    observations = _confirmed_market(project_root / OBSERVATION_FILE, session, snapshot, tracked)
    freeze = _confirmed_market(project_root / FREEZE_FILE, session, snapshot, tracked)
    if observations == "inputs" or freeze == "inputs":
        raise ArchiveRejected("INPUT_SOURCE_CONFLICT")
    if observations == "conflict" or freeze == "conflict":
        raise ArchiveRejected("MARKET_CONTEXT_CONFLICT")
    if stored is not None:
        if not _market_agrees(stored, observations) or not _market_agrees(stored, freeze):
            raise ArchiveRejected("MARKET_CONTEXT_CONFLICT")
        return stored, SNAPSHOT_FILE.as_posix()
    if not isinstance(observations, float) or not isinstance(freeze, float):
        raise ArchiveRejected("MARKET_CONTEXT_ABSENT")
    if not math.isclose(observations, freeze, abs_tol=1e-6):
        raise ArchiveRejected("MARKET_CONTEXT_CONFLICT")
    return observations, OBSERVATION_FILE.as_posix()


def _confirmed_market(path: Path, session: str, snapshot: pd.DataFrame, tracked: tuple[str, ...]):
    if not path.is_file():
        return None
    table = _read_table(path, ("trade_date", "symbol", "market_real", *INPUTS), "MARKET_CONTEXT_ABSENT")
    selected = _session_rows(table, "trade_date", session)
    if selected.empty:
        return None
    symbols = _symbols(selected["symbol"])
    if len(set(symbols)) != len(symbols) or set(symbols) != set(tracked):
        return "conflict"
    if not _inputs_complete(selected):
        return "conflict"
    if not _same_inputs(snapshot, selected):
        return "inputs"
    market = _single_market(selected["market_real"])
    if market == "conflict" or market is None:
        return "conflict"
    return market


def _market_agrees(stored: float, other) -> bool:
    if other is None:
        return True
    if not isinstance(other, float):
        return False
    return math.isclose(stored, other, abs_tol=1e-6)


def _read_table(path: Path, columns: tuple[str, ...], missing_reason: str) -> pd.DataFrame:
    if not path.is_file():
        raise ArchiveRejected(missing_reason)
    try:
        frame = pd.read_csv(path, usecols=list(columns))
    except (OSError, ValueError) as exc:
        raise ArchiveRejected(missing_reason) from exc
    return frame


def _session_rows(frame: pd.DataFrame, column: str, session: str) -> pd.DataFrame:
    dates = pd.to_datetime(frame[column], errors="coerce")
    selected = frame.loc[dates.dt.strftime("%Y-%m-%d").eq(session)].copy()
    if selected.empty:
        return selected
    check = pd.to_datetime(selected[column], errors="coerce").dt.strftime("%Y-%m-%d")
    if check.isna().any() or not check.eq(session).all():
        raise ArchiveRejected("MIXED_SESSION")
    return selected


def _symbols(values) -> list[str]:
    return [str(value).strip().upper() for value in values]


def _inputs_complete(frame: pd.DataFrame) -> bool:
    for name in INPUTS:
        numbers = pd.to_numeric(frame[name], errors="coerce")
        if not numbers.map(math.isfinite).all():
            return False
    return True


def _same_inputs(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    first = _indexed_inputs(left)
    second = _indexed_inputs(right)
    if not first.index.equals(second.index):
        return False
    for name in INPUTS:
        delta = (first[name] - second[name]).abs()
        if delta.isna().any() or bool((delta > 1e-6).any()):
            return False
    return True


def _indexed_inputs(frame: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"symbol": _symbols(frame["symbol"])})
    for name in INPUTS:
        out[name] = pd.to_numeric(frame[name], errors="coerce").to_numpy()
    return out.sort_values("symbol").set_index("symbol")


def _single_market(values):
    numbers = pd.to_numeric(values, errors="coerce")
    present = int(numbers.notna().sum())
    if present == 0:
        return None
    if present != len(numbers):
        return "conflict"
    unique = [float(value) for value in numbers.dropna().unique()]
    if len(unique) != 1 or not math.isfinite(unique[0]):
        return "conflict"
    return unique[0]


def _one_saved_at(values, session: date) -> str:
    text = [str(value).strip() for value in values]
    if any(not item or item.lower() == "nan" for item in text):
        raise ArchiveRejected("MIXED_SESSION")
    if len(set(text)) != 1:
        raise ArchiveRejected("MIXED_SESSION")
    parsed = pd.to_datetime(text[0], errors="coerce")
    if pd.isna(parsed):
        raise ArchiveRejected("MIXED_SESSION")
    stamp = parsed.tz_convert("Asia/Ho_Chi_Minh") if parsed.tzinfo is not None else parsed
    saved_day = stamp.date()
    if saved_day not in (session, session + timedelta(days=1)):
        raise ArchiveRejected("STALE_ARCHIVE")
    return text[0]


def _live_flags(values):
    flags = []
    for value in values:
        if isinstance(value, bool):
            flags.append(value)
            continue
        text = str(value).strip().lower()
        if text == "true":
            flags.append(True)
        elif text == "false":
            flags.append(False)
        else:
            return None
    return flags
