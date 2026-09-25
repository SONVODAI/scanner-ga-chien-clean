"""Market-Aware Sweetspot Observer → Live Candidate V2 Brain B adapter.

SHADOW / OBSERVATION ONLY. Read-only ledger consumer.
Does not recompute Sweet. Does not write the ledger. Does not mint BUY_READY.
Candidate != BUY. Sweet-only has no Brain A timing reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import pandas as pd

from modules.candidate_router.contract import SRC_MARKET_AWARE_SWEETSPOT
from modules.live_candidate.calendar import as_vn, session_open_at
from modules.live_candidate.contract import has_legal_first_seen
from modules.live_candidate_v2_nomination.contract import (
    STATUS_NOMINATED,
    BrainANomination,
)
from modules.live_candidate_v2_nomination.freeze import chronology_status_for
from modules.live_candidate_v2_nomination.intent import INTENT_WATCH_SETUP
from modules.live_candidate_v2_nomination.predicate import as_number, market_permission
from modules.market_aware_sweetspot_observer import (
    LEDGER_COLUMNS,
    OBSERVER_LEDGER_FILE,
    STATUS_OBSERVE,
    filter_stock_candidate_rows,
    get_frozen_day,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SWEET_LEDGER = (
    REPO_ROOT / "data" / "earning_learning" / OBSERVER_LEDGER_FILE
)

BRAIN_B_NOMINATED = "NOMINATED"
BRAIN_B_VALID_EMPTY = "VALID_EMPTY"
BRAIN_B_UNAVAILABLE = "UNAVAILABLE"
BRAIN_B_NOT_TRADING_SESSION = "NOT_TRADING_SESSION"

REASON_NOT_TRADING = "T_NOT_VNINDEX_TRADING_SESSION"
REASON_NO_PREDECESSOR = "NO_PREDECESSOR_VNINDEX_SESSION"
REASON_MISSING_FREEZE = "PREDECESSOR_SWEET_FREEZE_MISSING"
REASON_LEDGER_FAILURE = "SWEET_LEDGER_READ_FAILURE"
REASON_FETCH_FAILURE = "VNINDEX_TRADING_DAY_FETCH_FAILURE"
REASON_ZERO = "PREDECESSOR_SWEET_ZERO_OR_INSUFFICIENT"
REASON_OBSERVE = "PREDECESSOR_SWEET_OBSERVE"

# Frozen T0 audit fields copied into provenance. Later-maturing outcomes stay out.
SWEET_PROVENANCE_FIELDS: tuple[str, ...] = (
    "observer_id",
    "matched_sweetspot",
    "sweetspot_horizon",
    "historical_sample_n",
    "historical_winrate",
    "historical_avg_return",
    "historical_median_return",
    "market_context_key",
    "context_match_level",
    "evidence_status",
    "price_t0",
    "rs5_t0",
    "rs10_t0",
    "rsi14_t0",
    "market_real_t0",
    "origin_group",
    "origin_setup",
    "origin_ema9",
    "origin_breakout_ref",
    "origin_pull_label",
    "origin_evolution_health_group",
    "origin_evolution_health_score",
)
SWEET_OUTCOME_FIELDS: tuple[str, ...] = (
    "t3_return_pct",
    "t5_return_pct",
    "t10_return_pct",
)

VnindexFetcher = Callable[[str, str], pd.DataFrame]


@dataclass(frozen=True)
class BrainBConsult:
    """Fail-visible Brain B consult. VALID_EMPTY is not UNAVAILABLE."""

    status: str
    session: str
    predecessor: str
    reason: str
    nominations: tuple[BrainANomination, ...] = ()
    provenance: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": SRC_MARKET_AWARE_SWEETSPOT,
            "status": self.status,
            "session": self.session,
            "predecessor": self.predecessor,
            "reason": self.reason,
            "n_nominations": len(self.nominations),
        }


def _unavailable(
    *,
    session: str = "",
    predecessor: str = "",
    reason: str,
) -> BrainBConsult:
    return BrainBConsult(
        status=BRAIN_B_UNAVAILABLE,
        session=session,
        predecessor=predecessor,
        reason=reason,
    )


def _jsonable(value: object) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value
    num = as_number(value)
    if num is not None:
        if float(num).is_integer():
            return int(num)
        return float(num)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    return text


def _parse_ts(raw: object) -> pd.Timestamp | None:
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Ho_Chi_Minh")
    else:
        ts = ts.tz_convert("Asia/Ho_Chi_Minh")
    return ts


def normalize_session_dates(dates: Iterable[object]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in dates or ():
        ts = pd.to_datetime(raw, errors="coerce")
        if pd.isna(ts):
            text = str(raw or "").strip()[:10]
            if len(text) == 10 and text[4] == "-" and text[7] == "-":
                ts = pd.to_datetime(text, errors="coerce")
        if pd.isna(ts):
            continue
        day = ts.date().isoformat()
        if day in seen:
            continue
        seen.add(day)
        out.append(day)
    out.sort()
    return tuple(out)


def cash_session_open(now: datetime) -> bool:
    """True while the production cash-session clock says T is already open.

    Reuses ``research_below_boundary_locked``: weekday 09:15 inclusive through
    15:10 exclusive, including lunch. That clock is the app's live-session
    signal. It does not read today's VNINDEX daily bar, and it is false on
    weekends and outside the window, so a bare Mon–Fri date is not a session.
    This repo has no exchange holiday calendar.
    """
    from modules.intraday_execution_boundary import research_below_boundary_locked

    return research_below_boundary_locked(now)


def predecessor_vnindex_session(session_t: str, trading_dates: Sequence[str]) -> str | None:
    """D = immediately preceding VNINDEX session strictly before T. Not calendar T-1."""
    want = str(session_t or "").strip()[:10]
    prior = [d for d in normalize_session_dates(trading_dates) if d < want]
    if not prior:
        return None
    return prior[-1]


def default_vnindex_fetcher(start_date: str, end_date: str) -> pd.DataFrame:
    """Existing VNINDEX last-N-days evidence (same source as is_vnindex_trading_today)."""
    from vnstock import stock_historical_data  # type: ignore[import-untyped]

    last: pd.DataFrame | None = None
    for kind in ("index", "stock"):
        try:
            df = stock_historical_data(
                symbol="VNINDEX",
                start_date=start_date,
                end_date=end_date,
                resolution="1D",
                type=kind,
                beautify=True,
            )
        except Exception:
            continue
        if df is None or df.empty:
            continue
        last = df
        date_col = next(
            (c for c in df.columns if "date" in str(c).lower() or "time" in str(c).lower()),
            None,
        )
        if date_col is None:
            continue
        work = df.copy()
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work = work.dropna(subset=[date_col]).sort_values(date_col)
        if work.empty:
            continue
        return work
    if last is None:
        return pd.DataFrame()
    return last


def fetch_vnindex_trading_dates(
    now: datetime,
    *,
    lookback_days: int = 10,
    fetcher: VnindexFetcher | None = None,
) -> tuple[str, ...]:
    vn = as_vn(now)
    end = vn.date().isoformat()
    start = (vn.date() - timedelta(days=max(1, int(lookback_days)))).isoformat()
    fn = fetcher or default_vnindex_fetcher
    df = fn(start, end)
    if df is None or getattr(df, "empty", True):
        raise RuntimeError("VNINDEX trading-day evidence empty")
    date_col = next(
        (c for c in df.columns if "date" in str(c).lower() or "time" in str(c).lower()),
        None,
    )
    if date_col is None:
        raise RuntimeError("VNINDEX trading-day evidence has no date column")
    return normalize_session_dates(df[date_col].tolist())


def read_sweet_ledger(path: Path | None = None) -> pd.DataFrame:
    src = Path(path) if path is not None else DEFAULT_SWEET_LEDGER
    df = pd.read_csv(src)
    if df is None or df.empty:
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))
    for col in LEDGER_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[list(LEDGER_COLUMNS)].copy()


def freeze_exists(ledger: pd.DataFrame, t0_date: str) -> bool:
    if ledger is None or ledger.empty or "t0_date" not in ledger.columns:
        return False
    want = str(t0_date or "").strip()[:10]
    return want in {str(v)[:10] for v in ledger["t0_date"].tolist()}


def sweet_provenance_extra(row: Mapping[str, Any], *, t0_date: str, created_at: str) -> dict[str, Any]:
    extra: dict[str, Any] = {
        "source": SRC_MARKET_AWARE_SWEETSPOT,
        "sweet_t0_date": str(t0_date),
        "sweet_created_at": str(created_at),
    }
    for key in SWEET_PROVENANCE_FIELDS:
        extra[key] = _jsonable(row.get(key))
    return extra


def _eligible_from_t_open(session_t: str) -> str:
    day = pd.Timestamp(str(session_t)[:10]).date()
    return session_open_at(day).isoformat()


def nomination_from_sweet_row(
    row: Mapping[str, Any],
    *,
    session_t: str,
    market_real: object,
    observed_at: datetime,
) -> tuple[BrainANomination, dict[str, Any]] | None:
    symbol = str(row.get("symbol") or "").strip().upper()
    if not symbol or str(row.get("observer_status") or "").strip() != STATUS_OBSERVE:
        return None
    created = str(row.get("created_at") or "").strip()
    if not has_legal_first_seen(created):
        return None
    first = _parse_ts(created)
    if first is None:
        return None
    elig = _eligible_from_t_open(session_t)
    elig_ts = _parse_ts(elig)
    if elig_ts is None or elig_ts < first:
        return None
    now = as_vn(observed_at)
    perm = market_permission(market_real)
    extra = sweet_provenance_extra(row, t0_date=str(row.get("t0_date") or "")[:10], created_at=created)
    matched = extra.get("matched_sweetspot") or ""
    why = "SWEET OBSERVE"
    if matched:
        why = f"SWEET OBSERVE {matched}"
    nom = BrainANomination(
        symbol=symbol,
        session=str(session_t)[:10],
        setup="",
        group="",
        candidate_first_seen_ts=created,
        candidate_updated_ts=now.isoformat(),
        eligible_from=elig,
        chronology_status=chronology_status_for(elig, now),
        price_at_first_seen=as_number(row.get("price_t0")),
        ema9_at_first_seen=None,
        breakout_ref_at_first_seen=None,
        nomination_reason=why,
        source_action="OBSERVE",
        source_reason=STATUS_OBSERVE,
        observation_intent=INTENT_WATCH_SETUP,
        observation_reference="",
        source=SRC_MARKET_AWARE_SWEETSPOT,
        elite_buy_grade="",
        market_real=as_number(market_real),
        market_permission=perm,
        in_early_lab=False,
        status=STATUS_NOMINATED,
        qualified_by=STATUS_OBSERVE,
        origin_setup=str(extra.get("origin_setup") or ""),
        origin_group=str(extra.get("origin_group") or ""),
        origin_ema9=as_number(extra.get("origin_ema9")),
        origin_breakout_ref=as_number(extra.get("origin_breakout_ref")),
        origin_pull_label=str(extra.get("origin_pull_label") or ""),
        origin_evolution_health_group=str(extra.get("origin_evolution_health_group") or ""),
        origin_evolution_health_score=as_number(extra.get("origin_evolution_health_score")),
    )
    extra["symbol"] = symbol
    extra["chronology_status"] = nom.chronology_status
    return nom, extra


def consult_brain_b(
    *,
    observed_at: datetime,
    market_real: object,
    trading_dates: Sequence[str] | None = None,
    ledger: pd.DataFrame | None = None,
    ledger_path: Path | None = None,
    vnindex_fetcher: VnindexFetcher | None = None,
    lookback_days: int = 10,
) -> BrainBConsult:
    """Predecessor-on-T: D is the VNINDEX session strictly before T. Never latest Sweet day.

    T is recognized when it is already in the VNINDEX daily history, or when
    the cash-session clock says today's session is open. The open clock does
    not require today's completed daily bar. D is always taken from that
    history, never from the open clock.
    """
    now = as_vn(observed_at)
    session_t = now.date().isoformat()
    try:
        dates = (
            normalize_session_dates(trading_dates)
            if trading_dates is not None
            else fetch_vnindex_trading_dates(
                now, lookback_days=lookback_days, fetcher=vnindex_fetcher
            )
        )
    except Exception as exc:  # noqa: BLE001 — fail-visible, never block Brain A
        return _unavailable(
            session=session_t,
            reason=f"{REASON_FETCH_FAILURE}: {type(exc).__name__}: {exc}",
        )

    history = tuple(dates)
    session_known = session_t in set(history) or (
        cash_session_open(now) and now.date().isoformat() == session_t
    )
    if not session_known:
        return BrainBConsult(
            status=BRAIN_B_NOT_TRADING_SESSION,
            session=session_t,
            predecessor="",
            reason=REASON_NOT_TRADING,
        )

    predecessor = predecessor_vnindex_session(session_t, history)
    if not predecessor:
        return _unavailable(
            session=session_t,
            reason=REASON_NO_PREDECESSOR,
        )

    try:
        frame = ledger if ledger is not None else read_sweet_ledger(ledger_path)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(
            session=session_t,
            predecessor=predecessor,
            reason=f"{REASON_LEDGER_FAILURE}: {type(exc).__name__}: {exc}",
        )

    if frame is None:
        return _unavailable(
            session=session_t,
            predecessor=predecessor,
            reason=REASON_LEDGER_FAILURE,
        )

    if not freeze_exists(frame, predecessor):
        return _unavailable(
            session=session_t,
            predecessor=predecessor,
            reason=REASON_MISSING_FREEZE,
        )

    day = get_frozen_day(frame, predecessor)
    observe_rows = filter_stock_candidate_rows(day)
    nominations: list[BrainANomination] = []
    extras: list[dict[str, Any]] = []
    for rec in observe_rows.to_dict("records"):
        built = nomination_from_sweet_row(
            rec,
            session_t=session_t,
            market_real=market_real,
            observed_at=now,
        )
        if built is None:
            continue
        nom, extra = built
        nominations.append(nom)
        extras.append(extra)
    nominations.sort(key=lambda n: (n.symbol, n.candidate_first_seen_ts))
    extras.sort(key=lambda e: str(e.get("symbol") or ""))
    if nominations:
        return BrainBConsult(
            status=BRAIN_B_NOMINATED,
            session=session_t,
            predecessor=predecessor,
            reason=REASON_OBSERVE,
            nominations=tuple(nominations),
            provenance=tuple(extras),
        )
    return BrainBConsult(
        status=BRAIN_B_VALID_EMPTY,
        session=session_t,
        predecessor=predecessor,
        reason=REASON_ZERO,
        nominations=(),
        provenance=(),
    )
