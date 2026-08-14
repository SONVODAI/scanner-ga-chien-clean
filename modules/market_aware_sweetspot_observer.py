"""
Market-Aware Sweetspot Observer V1 — read-only forward research layer.

Computes qualified historical Sweetspots using ONLY lifecycle rows with
``trade_date < T0``, matches today's full Earning Money universe, and freezes
results append-only. Does not influence production scoring or decisions.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from modules.sweetspot_analyzer import (
    MIN_RANK_N,
    bucket_values,
    combined_statistics,
    evidence_label,
    rank_top_sweetspots,
    RS5_RS10_BIN_EDGES,
    RSI14_BIN_EDGES,
)

logger = logging.getLogger(__name__)

OBSERVER_LEDGER_FILE = "market_aware_sweetspot_observer_ledger.csv"
OBSERVER_VERSION = "1.0.0"

CONTEXT_MATCH_EXACT = "EXACT"
CONTEXT_MATCH_FAMILY = "FAMILY"
CONTEXT_MATCH_INSUFFICIENT = "INSUFFICIENT"

STATUS_OBSERVE = "OBSERVE"
STATUS_NO_QUALIFIED = "NO_QUALIFIED_SWEETSPOT"
STATUS_INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT_EVIDENCE"
STATUS_ZERO_CANDIDATES = "QUALIFIED_SWEETSPOT_BUT_0_CANDIDATES"

HORIZON_ORDER: Tuple[str, ...] = ("T5", "T10", "T3")

LEDGER_COLUMNS: Tuple[str, ...] = (
    "observer_id",
    "t0_date",
    "symbol",
    "observer_status",
    "market_real_t0",
    "market_forecast_t0",
    "breadth_t0",
    "market_regime_t0",
    "market_context_key",
    "context_match_level",
    "earning_universe_n",
    "price_t0",
    "rs5_t0",
    "rs10_t0",
    "rsi14_t0",
    "matched_sweetspot",
    "sweetspot_horizon",
    "historical_sample_n",
    "historical_winrate",
    "historical_avg_return",
    "historical_median_return",
    "evidence_status",
    "t3_return_pct",
    "t5_return_pct",
    "t10_return_pct",
    "created_at",
)

BOARD_RENAME_INVERSE: Dict[str, str] = {
    "Health": "health",
    "Mã": "symbol",
    "Giá": "price",
    "RS5": "rs5",
    "RS10": "rs10",
    "RSI14": "rsi14",
    "Action": "action",
    "Why": "reason",
}


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def observer_id(t0_date: str, symbol: str = "") -> str:
    key = f"{t0_date}|{symbol.strip().upper() or '__STATUS__'}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _safe_float(value: Any) -> float:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return np.nan
        result = float(value)
        return result if np.isfinite(result) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _safe_int(value: Any, default: int = 0) -> int:
    num = _safe_float(value)
    if pd.isna(num):
        return default
    return int(num)


def _display_text(value: Any, default: str = "—") -> str:
    if value is None:
        return default
    if isinstance(value, float) and np.isnan(value):
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _normalize_universe(board_df: pd.DataFrame) -> pd.DataFrame:
    if board_df is None or board_df.empty:
        return pd.DataFrame()

    out = board_df.copy()
    if "Mã" in out.columns:
        out = out.rename(columns=BOARD_RENAME_INVERSE)

    required = {"symbol", "price", "rs5", "rs10", "rsi14"}
    missing = required.difference(out.columns)
    if missing:
        raise ValueError(f"Earning universe missing columns: {sorted(missing)}")

    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()
    for col in ("price", "rs5", "rs10", "rsi14"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.reset_index(drop=True)


def build_t0_market_context_key(
    *,
    market_real: float,
    market_forecast: float,
    breadth: float | None,
) -> str:
    """Build ``market_context_key`` using existing earning-learning bucketing."""
    from modules.earning_learning import _add_pattern_columns

    row = pd.DataFrame(
        [
            {
                "market_score": _safe_float(market_real),
                "market_forecast": _safe_float(market_forecast),
                "breadth": _safe_float(breadth),
            }
        ]
    )
    enriched = _add_pattern_columns(row)
    return str(enriched["market_context_key"].iloc[0])


def _market_context_family(market_context_key: str) -> Tuple[str, str]:
    from modules.earning_learning import _market_context_family

    return _market_context_family(market_context_key)


def filter_lifecycle_as_of(
    lifecycle: pd.DataFrame,
    t0_date: str,
) -> pd.DataFrame:
    """Strict AS-OF filter: only ``trade_date < T0`` (never equal)."""
    if lifecycle is None or lifecycle.empty:
        return pd.DataFrame()

    date_col = "trade_date" if "trade_date" in lifecycle.columns else "entry_date"
    if date_col not in lifecycle.columns:
        return pd.DataFrame()

    out = lifecycle.copy()
    dates = pd.to_datetime(out[date_col], errors="coerce")
    cutoff = pd.Timestamp(str(t0_date))
    mask = dates.notna() & (dates < cutoff)
    return out.loc[mask].copy()


def _filter_by_context_match(
    lifecycle: pd.DataFrame,
    market_context_key: str,
    match_level: str,
) -> pd.DataFrame:
    if lifecycle.empty or "market_context_key" not in lifecycle.columns:
        return pd.DataFrame()

    keys = lifecycle["market_context_key"].astype(str)
    if match_level == CONTEXT_MATCH_EXACT:
        return lifecycle[keys == str(market_context_key)].copy()

    if match_level == CONTEXT_MATCH_FAMILY:
        target = _market_context_family(market_context_key)
        family_mask = keys.map(
            lambda k: _market_context_family(k) == target
        )
        return lifecycle[family_mask].copy()

    return pd.DataFrame()


def _sweetspot_label(row: Mapping[str, Any]) -> str:
    return (
        f"RS5={row.get('RS5 Range', '')} | "
        f"RS10={row.get('RS10 Range', '')} | "
        f"RSI14={row.get('RSI14 Range', '')}"
    )


def _pick_best_qualified_sweetspot(
    lifecycle: pd.DataFrame,
) -> Tuple[Optional[pd.Series], str]:
    """Return best ranked sweetspot row and horizon key (T3/T5/T10)."""
    if lifecycle.empty:
        return None, ""

    combined = combined_statistics(lifecycle, window="all")
    best_row: Optional[pd.Series] = None
    best_horizon = ""
    best_sort: Tuple[Any, ...] = ()

    for horizon in HORIZON_ORDER:
        frame = combined.get(horizon, pd.DataFrame())
        ranked = rank_top_sweetspots(frame, top_n=1)
        if ranked.empty:
            continue
        candidate = ranked.iloc[0]
        sort_key = (
            _safe_float(candidate.get("Winrate")),
            _safe_float(candidate.get("Avg Return")),
            _safe_float(candidate.get("Median Return")),
            _safe_int(candidate.get("N", 0)),
        )
        if best_row is None or sort_key > best_sort:
            best_row = candidate
            best_horizon = horizon
            best_sort = sort_key

    if best_row is None:
        return None, ""
    return best_row, best_horizon


def _stock_bucket_labels(
    rs5: float,
    rs10: float,
    rsi14: float,
) -> Tuple[str, str, str]:
    rs5_b = bucket_values(pd.Series([rs5]), RS5_RS10_BIN_EDGES).iloc[0]
    rs10_b = bucket_values(pd.Series([rs10]), RS5_RS10_BIN_EDGES).iloc[0]
    rsi_b = bucket_values(pd.Series([rsi14]), RSI14_BIN_EDGES).iloc[0]
    return str(rs5_b), str(rs10_b), str(rsi_b)


def _stock_matches_sweetspot(
    rs5: float,
    rs10: float,
    rsi14: float,
    sweetspot: Mapping[str, Any],
) -> bool:
    if any(pd.isna(v) for v in (rs5, rs10, rsi14)):
        return False
    rs5_b, rs10_b, rsi_b = _stock_bucket_labels(rs5, rs10, rsi14)
    return (
        rs5_b == str(sweetspot.get("RS5 Range", ""))
        and rs10_b == str(sweetspot.get("RS10 Range", ""))
        and rsi_b == str(sweetspot.get("RSI14 Range", ""))
    )


def _base_row(
    *,
    t0_date: str,
    symbol: str,
    observer_status: str,
    market_real: float,
    market_forecast: float,
    breadth: float | None,
    market_regime: str,
    market_context_key: str,
    context_match_level: str,
    earning_universe_n: int = 0,
    sweetspot: Optional[Mapping[str, Any]] = None,
    sweetspot_horizon: str = "",
) -> Dict[str, Any]:
    row: Dict[str, Any] = {col: np.nan for col in LEDGER_COLUMNS}
    row.update(
        {
            "observer_id": observer_id(t0_date, symbol),
            "t0_date": str(t0_date),
            "symbol": str(symbol).strip().upper(),
            "observer_status": observer_status,
            "market_real_t0": _safe_float(market_real),
            "market_forecast_t0": _safe_float(market_forecast),
            "breadth_t0": _safe_float(breadth),
            "market_regime_t0": str(market_regime or ""),
            "market_context_key": str(market_context_key or ""),
            "context_match_level": str(context_match_level or ""),
            "earning_universe_n": int(earning_universe_n),
            "created_at": _utc_now_iso(),
        }
    )
    if sweetspot is not None:
        n = _safe_int(sweetspot.get("N", 0))
        row.update(
            {
                "matched_sweetspot": _sweetspot_label(sweetspot),
                "sweetspot_horizon": sweetspot_horizon,
                "historical_sample_n": n,
                "historical_winrate": _safe_float(sweetspot.get("Winrate")),
                "historical_avg_return": _safe_float(sweetspot.get("Avg Return")),
                "historical_median_return": _safe_float(
                    sweetspot.get("Median Return")
                ),
                "evidence_status": evidence_label(n),
            }
        )
    return row


def compute_observer_snapshot(
    *,
    t0_date: str,
    earning_board_df: pd.DataFrame,
    lifecycle_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
    breadth: float | None,
    market_regime: str = "",
) -> Dict[str, Any]:
    """
    Pure AS-OF computation — does not read or write the ledger.

    Returns dict with status, context_match_level, sweetspot, candidates, rows.
    """
    universe = _normalize_universe(earning_board_df)
    market_context_key = build_t0_market_context_key(
        market_real=market_real,
        market_forecast=market_forecast,
        breadth=breadth,
    )
    historical = filter_lifecycle_as_of(lifecycle_df, t0_date)

    result: Dict[str, Any] = {
        "t0_date": str(t0_date),
        "market_context_key": market_context_key,
        "universe_size": int(len(universe)),
        "historical_rows": int(len(historical)),
        "context_match_level": CONTEXT_MATCH_INSUFFICIENT,
        "observer_status": STATUS_INSUFFICIENT_CONTEXT,
        "sweetspot": None,
        "sweetspot_horizon": "",
        "candidates": pd.DataFrame(),
        "rows": [],
    }

    if historical.empty:
        status_row = _base_row(
            t0_date=t0_date,
            symbol="",
            observer_status=STATUS_INSUFFICIENT_CONTEXT,
            market_real=market_real,
            market_forecast=market_forecast,
            breadth=breadth,
            market_regime=market_regime,
            market_context_key=market_context_key,
            context_match_level=CONTEXT_MATCH_INSUFFICIENT,
            earning_universe_n=universe_n,
        )
        result["rows"] = [status_row]
        return result

    sweetspot: Optional[pd.Series] = None
    sweetspot_horizon = ""
    match_level = CONTEXT_MATCH_INSUFFICIENT
    universe_n = int(len(universe))

    for level in (CONTEXT_MATCH_EXACT, CONTEXT_MATCH_FAMILY):
        matched = _filter_by_context_match(historical, market_context_key, level)
        if matched.empty:
            continue
        candidate, horizon = _pick_best_qualified_sweetspot(matched)
        if candidate is not None:
            sweetspot = candidate
            sweetspot_horizon = horizon
            match_level = level
            break

    if sweetspot is None:
        family_hist = _filter_by_context_match(
            historical,
            market_context_key,
            CONTEXT_MATCH_FAMILY,
        )
        exact_hist = _filter_by_context_match(
            historical,
            market_context_key,
            CONTEXT_MATCH_EXACT,
        )
        max_context_rows = max(len(exact_hist), len(family_hist))
        if max_context_rows < MIN_RANK_N:
            observer_status = STATUS_INSUFFICIENT_CONTEXT
            match_level = CONTEXT_MATCH_INSUFFICIENT
        else:
            observer_status = STATUS_NO_QUALIFIED
            match_level = (
                CONTEXT_MATCH_EXACT
                if len(exact_hist) >= MIN_RANK_N
                else CONTEXT_MATCH_FAMILY
            )

        status_row = _base_row(
            t0_date=t0_date,
            symbol="",
            observer_status=observer_status,
            market_real=market_real,
            market_forecast=market_forecast,
            breadth=breadth,
            market_regime=market_regime,
            market_context_key=market_context_key,
            context_match_level=match_level,
            earning_universe_n=universe_n,
        )
        result.update(
            {
                "context_match_level": match_level,
                "observer_status": observer_status,
                "rows": [status_row],
            }
        )
        return result

    candidates = universe[
        universe.apply(
            lambda r: _stock_matches_sweetspot(
                r["rs5"],
                r["rs10"],
                r["rsi14"],
                sweetspot,
            ),
            axis=1,
        )
    ].copy()

    rows: List[Dict[str, Any]] = []
    if candidates.empty:
        status_row = _base_row(
            t0_date=t0_date,
            symbol="",
            observer_status=STATUS_ZERO_CANDIDATES,
            market_real=market_real,
            market_forecast=market_forecast,
            breadth=breadth,
            market_regime=market_regime,
            market_context_key=market_context_key,
            context_match_level=match_level,
            earning_universe_n=universe_n,
            sweetspot=sweetspot,
            sweetspot_horizon=sweetspot_horizon,
        )
        rows.append(status_row)
    else:
        for _, stock in candidates.iterrows():
            row = _base_row(
                t0_date=t0_date,
                symbol=str(stock["symbol"]),
                observer_status=STATUS_OBSERVE,
                market_real=market_real,
                market_forecast=market_forecast,
                breadth=breadth,
                market_regime=market_regime,
                market_context_key=market_context_key,
                context_match_level=match_level,
                earning_universe_n=universe_n,
                sweetspot=sweetspot,
                sweetspot_horizon=sweetspot_horizon,
            )
            row["price_t0"] = _safe_float(stock["price"])
            row["rs5_t0"] = _safe_float(stock["rs5"])
            row["rs10_t0"] = _safe_float(stock["rs10"])
            row["rsi14_t0"] = _safe_float(stock["rsi14"])
            rows.append(row)

    result.update(
        {
            "context_match_level": match_level,
            "observer_status": (
                STATUS_OBSERVE if not candidates.empty else STATUS_ZERO_CANDIDATES
            ),
            "sweetspot": sweetspot.to_dict() if sweetspot is not None else None,
            "sweetspot_horizon": sweetspot_horizon,
            "candidates": candidates,
            "rows": rows,
        }
    )
    return result


def _empty_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=list(LEDGER_COLUMNS))


def load_observer_ledger(
    data_dir: Optional[str] = None,
    *,
    remote_dir: Optional[str] = None,
) -> pd.DataFrame:
    from modules.earning_learning import _make_storage, _read_csv_from_storage

    storage = _make_storage(data_dir, remote_dir)
    ledger, _ = _read_csv_from_storage(storage, OBSERVER_LEDGER_FILE)
    if ledger is None or ledger.empty:
        return _empty_ledger()
    for col in LEDGER_COLUMNS:
        if col not in ledger.columns:
            ledger[col] = np.nan
    return ledger[list(LEDGER_COLUMNS)].copy()


def _is_day_frozen(ledger: pd.DataFrame, t0_date: str) -> bool:
    if ledger is None or ledger.empty or "t0_date" not in ledger.columns:
        return False
    return str(t0_date) in set(ledger["t0_date"].astype(str))


def append_observer_ledger(
    existing: pd.DataFrame,
    new_rows: pd.DataFrame,
    *,
    t0_date: str,
) -> Tuple[pd.DataFrame, int]:
    """
    Append-only first-write-wins for an entire ``t0_date``.

    If any row already exists for ``t0_date``, nothing is appended.
    """
    if _is_day_frozen(existing, t0_date):
        return (
            existing.copy() if existing is not None else _empty_ledger(),
            0,
        )

    if new_rows is None or new_rows.empty:
        return (
            existing.copy() if existing is not None else _empty_ledger(),
            0,
        )

    prepared = new_rows.copy()
    for col in LEDGER_COLUMNS:
        if col not in prepared.columns:
            prepared[col] = np.nan
    prepared = prepared[list(LEDGER_COLUMNS)]

    old = existing.copy() if existing is not None else _empty_ledger()
    combined = pd.concat([old, prepared], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(subset=["observer_id"], keep="first")
    return combined.reset_index(drop=True), int(len(prepared))


def freeze_daily_observer_if_eligible(
    *,
    t0_date: str,
    earning_board_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
    breadth: float | None,
    market_regime: str = "",
    lifecycle_df: Optional[pd.DataFrame] = None,
    data_dir: Optional[str] = None,
    remote_dir: Optional[str] = None,
    now: Optional[datetime] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Canonical daily freeze aligned with Market T0 (>= 18:00 Asia/Ho_Chi_Minh).

    When ``force=True`` (tests only), skips the canonical time gate.
    """
    from modules.earning_learning import (
        _make_storage,
        _read_csv_from_storage,
        _write_csv_to_storage,
        get_pattern_lifecycle,
    )
    from modules.market_t0_capture import is_canonical_eligible, validate_canonical_trade_date

    if not force and not is_canonical_eligible(now):
        return {
            "ok": True,
            "added": 0,
            "skipped_reason": "BEFORE_EOD_PLUS_3H",
        }

    if not force:
        ok_date, date_reason = validate_canonical_trade_date(t0_date, now=now)
        if not ok_date:
            return {
                "ok": True,
                "added": 0,
                "skipped_reason": date_reason,
            }

    if lifecycle_df is None:
        lifecycle_df = get_pattern_lifecycle(data_dir, remote_dir=remote_dir)

    snapshot = compute_observer_snapshot(
        t0_date=t0_date,
        earning_board_df=earning_board_df,
        lifecycle_df=lifecycle_df,
        market_real=market_real,
        market_forecast=market_forecast,
        breadth=breadth,
        market_regime=market_regime,
    )

    storage = _make_storage(data_dir, remote_dir)
    existing, _ = _read_csv_from_storage(storage, OBSERVER_LEDGER_FILE)
    new_df = pd.DataFrame(snapshot["rows"], columns=list(LEDGER_COLUMNS))
    merged, added = append_observer_ledger(existing, new_df, t0_date=t0_date)

    if added > 0:
        _write_csv_to_storage(
            storage,
            OBSERVER_LEDGER_FILE,
            merged,
            commit_message=(
                f"Mr.BOT append market-aware sweetspot observer {t0_date} +{added}"
            ),
        )

    return {
        "ok": True,
        "added": added,
        "t0_date": t0_date,
        "observer_status": snapshot.get("observer_status"),
        "context_match_level": snapshot.get("context_match_level"),
        "candidate_count": int(len(snapshot.get("candidates", []))),
        "skipped_reason": None if added > 0 else "ALREADY_FROZEN",
    }


def _lifecycle_lookup(lifecycle: pd.DataFrame) -> Dict[Tuple[str, str], pd.Series]:
    lookup: Dict[Tuple[str, str], pd.Series] = {}
    if lifecycle is None or lifecycle.empty:
        return lookup

    date_col = "trade_date" if "trade_date" in lifecycle.columns else "entry_date"
    for _, row in lifecycle.iterrows():
        d = str(row.get(date_col, "")).strip()
        sym = str(row.get("symbol", "")).strip().upper()
        if d and sym:
            lookup[(d, sym)] = row
    return lookup


def mature_observer_outcomes(
    *,
    lifecycle_df: Optional[pd.DataFrame] = None,
    data_dir: Optional[str] = None,
    remote_dir: Optional[str] = None,
    immature_session_dates: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """
    Attach matured T3/T5/T10 to frozen observer rows from lifecycle.

    Reuses the same lifecycle return columns as ``mature_forward_outcomes``:
    each horizon is the N-th future **observation session** for that symbol
    (project earning-learning convention), keyed by ``(t0_date, symbol)``.

    Only outcome columns on the observer ledger are updated; T0 fields stay frozen.
    """
    from modules.earning_learning import (
        _make_storage,
        _read_csv_from_storage,
        _write_csv_to_storage,
        get_pattern_lifecycle,
    )

    storage = _make_storage(data_dir, remote_dir)
    ledger, _ = _read_csv_from_storage(storage, OBSERVER_LEDGER_FILE)
    if ledger.empty:
        return ledger

    if lifecycle_df is None:
        lifecycle_df = get_pattern_lifecycle(data_dir, remote_dir=remote_dir)

    life_by_key = _lifecycle_lookup(lifecycle_df)
    blocked = {
        str(d).strip()
        for d in (immature_session_dates or [])
        if str(d).strip()
    }

    updated = ledger.copy()
    changed = False

    for idx, row in updated.iterrows():
        t0_date = str(row.get("t0_date", "")).strip()
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol or t0_date in blocked:
            continue

        life = life_by_key.get((t0_date, symbol))
        if life is None:
            continue

        for col, life_col in (
            ("t3_return_pct", "t3_return_pct"),
            ("t5_return_pct", "t5_return_pct"),
            ("t10_return_pct", "t10_return_pct"),
        ):
            current = _safe_float(row.get(col))
            new_val = _safe_float(life.get(life_col))
            if pd.isna(current) and pd.notna(new_val):
                updated.at[idx, col] = new_val
                changed = True

    if changed:
        _write_csv_to_storage(
            storage,
            OBSERVER_LEDGER_FILE,
            updated,
            commit_message="Mr.BOT mature market-aware sweetspot observer outcomes",
        )

    return updated


def get_frozen_day(ledger: pd.DataFrame, t0_date: str) -> pd.DataFrame:
    if ledger is None or ledger.empty:
        return _empty_ledger()
    return ledger[ledger["t0_date"].astype(str) == str(t0_date)].copy()


def render_market_aware_sweetspot_observer_panel(
    *,
    t0_date: str,
    data_dir: Optional[str] = None,
    remote_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Read-only UI — renders frozen ledger rows only (no recompute).
    """
    import streamlit as st

    st.markdown("### 🍯 MARKET-AWARE SWEETSPOT OBSERVER")
    st.caption(
        "Forward research observer. Reads frozen T0 ledger only — "
        "does not influence BUY/SELL, Elite, or NAV."
    )

    try:
        ledger = load_observer_ledger(data_dir, remote_dir=remote_dir)
    except Exception as exc:
        st.info("Observer ledger unavailable.")
        st.caption(f"{type(exc).__name__}: {exc}")
        return {"ok": False, "error": str(exc)}

    day = get_frozen_day(ledger, t0_date)
    if day.empty:
        st.info(
            "No frozen Observer result for this session yet. "
            "Canonical daily freeze runs at or after 18:00 Asia/Ho_Chi_Minh."
        )
        return {"ok": True, "status": "NOT_FROZEN", "t0_date": t0_date}

    header = day.iloc[0]
    candidates = day[day["symbol"].astype(str).str.strip() != ""].copy()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        mr = _safe_float(header.get("market_real_t0"))
        st.metric("Market Real", f"{mr:.1f}" if pd.notna(mr) else "—")
    with c2:
        st.metric("Context Match", str(header.get("context_match_level", "—")))
    with c3:
        st.metric("Sweetspot Horizon", _display_text(header.get("sweetspot_horizon")))
    with c4:
        st.metric("Earning Universe", str(_safe_int(header.get("earning_universe_n"))))

    st.caption(
        f"Market Context: `{header.get('market_context_key', '—')}` | "
        f"Regime: {header.get('market_regime_t0', '—')}"
    )

    n = _safe_int(header.get("historical_sample_n"))
    wr = _safe_float(header.get("historical_winrate"))
    avg = _safe_float(header.get("historical_avg_return"))
    med = _safe_float(header.get("historical_median_return"))
    evidence = str(header.get("evidence_status", "—"))
    st.caption(
        f"Evidence: N={n} | WR={wr:.2f}% | Avg={avg:.2f}% | Median={med:.2f}% | {evidence}"
        if n > 0 and pd.notna(wr)
        else f"Observer status: {header.get('observer_status', '—')}"
    )

    status = str(header.get("observer_status", ""))
    if status in (
        STATUS_NO_QUALIFIED,
        STATUS_INSUFFICIENT_CONTEXT,
        STATUS_ZERO_CANDIDATES,
    ):
        st.warning(status.replace("_", " "))

    st.metric("Qualified Candidates", len(candidates))

    if not candidates.empty:
        display = candidates[
            [
                "symbol",
                "price_t0",
                "rs5_t0",
                "rs10_t0",
                "rsi14_t0",
                "matched_sweetspot",
                "sweetspot_horizon",
                "historical_sample_n",
                "historical_winrate",
                "evidence_status",
                "observer_status",
            ]
        ].copy()
        display = display.rename(
            columns={
                "symbol": "Mã",
                "price_t0": "Giá T0",
                "rs5_t0": "RS5",
                "rs10_t0": "RS10",
                "rsi14_t0": "RSI14",
                "matched_sweetspot": "Sweetspot",
                "sweetspot_horizon": "Horizon",
                "historical_sample_n": "N",
                "historical_winrate": "Historical WR",
                "evidence_status": "Evidence",
                "observer_status": "Status",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)

    return {
        "ok": True,
        "t0_date": t0_date,
        "frozen_rows": int(len(day)),
        "candidate_count": int(len(candidates)),
        "observer_status": status,
    }


__all__ = [
    "OBSERVER_LEDGER_FILE",
    "CONTEXT_MATCH_EXACT",
    "CONTEXT_MATCH_FAMILY",
    "CONTEXT_MATCH_INSUFFICIENT",
    "STATUS_OBSERVE",
    "STATUS_NO_QUALIFIED",
    "STATUS_INSUFFICIENT_CONTEXT",
    "STATUS_ZERO_CANDIDATES",
    "append_observer_ledger",
    "build_t0_market_context_key",
    "compute_observer_snapshot",
    "filter_lifecycle_as_of",
    "freeze_daily_observer_if_eligible",
    "get_frozen_day",
    "load_observer_ledger",
    "mature_observer_outcomes",
    "observer_id",
    "render_market_aware_sweetspot_observer_panel",
]
