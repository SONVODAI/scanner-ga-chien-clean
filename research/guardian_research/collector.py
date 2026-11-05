"""Guardian Research Stage A collector.

Reuses the exact ``position_guardian.generate_signal(row)`` on existing scan
rows. Does not fetch market data, touch holdings/cost/P/L, or write production
Guardian state. Incomplete scan coverage becomes MISSING — never a fabricated
HOLD.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import ModuleType
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from research.guardian_research.contract import (
    CLASSIFICATION_FN,
    REQUIRED_TECH_FIELDS,
    SCHEMA_VERSION,
    STATUS_MISSING,
    STATUS_VALID,
)
from research.guardian_research.store import (
    GuardianT0Store,
    default_snapshot_path,
    snapshot_identity,
)

# Mirror production MISSING token without importing holdings UI helpers.
MISSING_LABEL = "—"


def _ensure_streamlit_stub() -> None:
    """Allow importing ``position_guardian`` outside Streamlit (research only)."""
    if "streamlit" in sys.modules:
        return
    st = ModuleType("streamlit")

    def _noop(*_a, **_k):  # noqa: ANN001
        return None

    st.markdown = _noop
    st.subheader = _noop
    st.caption = _noop
    st.button = lambda *_a, **_k: False
    st.success = _noop
    st.info = _noop
    st.warning = _noop
    st.error = _noop
    st.dataframe = _noop
    st.columns = lambda n: [ModuleType(f"col{i}") for i in range(n)]
    st.session_state = {}
    st.secrets = {}
    st.progress = lambda *_a, **_k: _noop
    sys.modules["streamlit"] = st


def load_guardian_classifier() -> ModuleType:
    """Import production ``position_guardian`` (exact generate_signal)."""
    _ensure_streamlit_stub()
    import position_guardian as pg  # noqa: WPS433 — intentional exact reuse

    return pg


def _text(value: object) -> str:
    return str(value or "").strip()


def _symbol(value: object) -> str:
    return _text(value).upper()


def _session_text(value: object) -> str:
    text = _text(value)
    return text[:10] if len(text) >= 10 else text


def _opt_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return float(number)


def _utc_now_iso(now: datetime | None = None) -> str:
    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def scan_fingerprint(scan_df: pd.DataFrame | None) -> str:
    """Deterministic hash of symbol + required tech fields (order-independent)."""
    lines: list[str] = []
    if scan_df is not None and isinstance(scan_df, pd.DataFrame) and not scan_df.empty:
        for rec in scan_df.to_dict("records"):
            symbol = _symbol(rec.get("symbol"))
            if not symbol:
                continue
            parts = [symbol]
            for col in REQUIRED_TECH_FIELDS:
                num = _opt_float(rec.get(col))
                parts.append("" if num is None else repr(num))
            lines.append("|".join(parts))
    payload = "\n".join(sorted(lines))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _index_scan_rows(scan_df: pd.DataFrame | None) -> dict[str, pd.Series]:
    by_symbol: dict[str, pd.Series] = {}
    if scan_df is None or not isinstance(scan_df, pd.DataFrame) or scan_df.empty:
        return by_symbol
    if "symbol" not in scan_df.columns:
        return by_symbol
    work = scan_df.copy()
    work["symbol"] = work["symbol"].astype(str).str.upper().str.strip()
    for _, row in work.iterrows():
        symbol = _symbol(row.get("symbol"))
        if symbol:
            by_symbol[symbol] = row
    return by_symbol


def _row_get(row: Mapping[str, Any] | pd.Series, column: str) -> object:
    if isinstance(row, pd.Series):
        return row[column] if column in row.index else None
    return row.get(column)


def row_tech_complete(row: Mapping[str, Any] | pd.Series | None) -> bool:
    """True only when every field ``generate_signal`` reads is present."""
    if row is None:
        return False
    for col in REQUIRED_TECH_FIELDS:
        if _opt_float(_row_get(row, col)) is None:
            return False
    return True


def classify_scan_row(row: pd.Series | Mapping[str, Any], *, pg: ModuleType | None = None) -> dict[str, Any]:
    """Call exact ``generate_signal``. Caller must ensure tech completeness."""
    classifier = pg or load_guardian_classifier()
    series = row if isinstance(row, pd.Series) else pd.Series(dict(row))
    signal, reason, score = classifier.generate_signal(series)
    return {
        "status": STATUS_VALID,
        "signal": signal,
        "reason": reason,
        "sell_score": int(score) if score is not None else None,
        "price": _opt_float(series.get("price")),
        "ema9": _opt_float(series.get("ema9")),
        "ma20": _opt_float(series.get("ma20")),
        "obv": _opt_float(series.get("obv")),
        "obv_ema9": _opt_float(series.get("obv_ema9")),
    }


def missing_snapshot_fields(symbol: str) -> dict[str, Any]:
    return {
        "status": STATUS_MISSING,
        "signal": MISSING_LABEL,
        "reason": MISSING_LABEL,
        "sell_score": None,
        "price": None,
        "ema9": None,
        "ma20": None,
        "obv": None,
        "obv_ema9": None,
    }


@dataclass
class CollectReport:
    symbols_considered: int = 0
    written: int = 0
    duplicates_skipped: int = 0
    valid: int = 0
    missing: int = 0
    notes: list[str] = field(default_factory=list)


def build_t0_record(
    *,
    session_date: str,
    symbol: str,
    classification: Mapping[str, Any],
    market_real: object = None,
    market_context_source: str | None = None,
    source_provenance: str,
    scan_fingerprint_value: str,
    captured_at: str | None = None,
) -> dict[str, Any]:
    session = _session_text(session_date)
    sym = _symbol(symbol)
    return {
        "schema": SCHEMA_VERSION,
        "record_type": "guardian_t0_snapshot",
        "snapshot_id": snapshot_identity(session, sym),
        "session_date": session,
        "symbol": sym,
        "status": classification.get("status"),
        "signal": classification.get("signal"),
        "reason": classification.get("reason"),
        "sell_score": classification.get("sell_score"),
        "price": classification.get("price"),
        "ema9": classification.get("ema9"),
        "ma20": classification.get("ma20"),
        "obv": classification.get("obv"),
        "obv_ema9": classification.get("obv_ema9"),
        "market_real": market_real if market_real is not None and market_real != "" else None,
        "market_context_source": _text(market_context_source) or None,
        "classification_fn": CLASSIFICATION_FN,
        "source_provenance": _text(source_provenance),
        "scan_fingerprint": scan_fingerprint_value,
        "captured_at": captured_at or _utc_now_iso(),
    }


def collect_guardian_t0(
    scan_df: pd.DataFrame | None,
    tracked_symbols: Sequence[str],
    *,
    session_date: str,
    store: GuardianT0Store | None = None,
    store_path: Path | None = None,
    market_real: object = None,
    market_context_source: str | None = None,
    source_provenance: str = "existing_scan_rows",
    captured_at: str | None = None,
    pg: ModuleType | None = None,
) -> CollectReport:
    """Classify all tracked symbols from an existing scan frame and persist T0 rows.

    Parameters
    ----------
    scan_df:
        Existing scanner rows (must already include Guardian tech columns).
    tracked_symbols:
        Explicit research universe. Holdings are never consulted.
    session_date:
        Exchange session date for the immutable T0 key.
    """
    report = CollectReport()
    session = _session_text(session_date)
    if not session:
        report.notes.append("session_date required")
        return report

    path = default_snapshot_path(store_path) if store is None else store.path
    active = store if store is not None else GuardianT0Store.open(path)
    classifier = pg or load_guardian_classifier()
    by_symbol = _index_scan_rows(scan_df)
    fingerprint = scan_fingerprint(scan_df)
    provenance = _text(source_provenance) or "existing_scan_rows"

    # One snapshot per tracked symbol for the session (order-preserving unique).
    universe: list[str] = []
    seen_symbols: set[str] = set()
    for raw_symbol in tracked_symbols:
        symbol = _symbol(raw_symbol)
        if not symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        universe.append(symbol)

    pending: list[dict[str, Any]] = []
    for symbol in universe:
        report.symbols_considered += 1
        if active.has(session, symbol):
            report.duplicates_skipped += 1
            continue

        scan_row = by_symbol.get(symbol)
        if scan_row is None or not row_tech_complete(scan_row):
            classification = missing_snapshot_fields(symbol)
            report.missing += 1
        else:
            classification = classify_scan_row(scan_row, pg=classifier)
            report.valid += 1

        pending.append(
            build_t0_record(
                session_date=session,
                symbol=symbol,
                classification=classification,
                market_real=market_real,
                market_context_source=market_context_source,
                source_provenance=provenance,
                scan_fingerprint_value=fingerprint,
                captured_at=captured_at,
            )
        )

    written_rows = active.append_new(pending)
    report.written = len(written_rows)
    return report
