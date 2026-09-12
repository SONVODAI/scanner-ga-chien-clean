"""Volume Semantic / Quality Gate — runs BEFORE any feature interpretation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

import pandas as pd

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.constants import (
    DATA_LOW,
    DATA_QUALIFIED,
    DATA_TRUSTED,
    DATA_UNUSABLE,
    RESEARCH_DEFAULT_CUMULATIVE_LAST_FRAC,
    RESEARCH_DEFAULT_DOJI_FRAC,
    RESEARCH_DEFAULT_FIFTEEN_MIN_SEC,
    RESEARCH_DEFAULT_STRUCTURAL_BARS,
    RESEARCH_DEFAULT_THIN_FRAC,
    SESSION_AM_END,
    SESSION_AM_START,
    SESSION_PM_END,
    SESSION_PM_START,
    TOD_EARLY,
    TOD_EARLY_MIN_SESSIONS,
    TOD_MATURE,
    TOD_MATURE_MIN_SESSIONS,
    TOD_PRELIMINARY,
)

GATE_UNAVAILABLE = "UNAVAILABLE"
GATE_STRUCTURAL = "STRUCTURAL"
GATE_THIN = "THIN"
GATE_CUMULATIVE = "CUMULATIVE"
GATE_INTERVAL = "INTERVAL"
GATE_STALE = "STALE_FIRST_WRITE"
GATE_TOD_IMMATURE = "TOD_IMMATURE"
GATE_BAD_QUALITY = "BAD_QUALITY_FLAG"


@dataclass
class GateResult:
    data_state: str
    gate_reason: str
    volume_kind: str
    tod_maturity: str
    overlay_applied: bool
    n_bars: int
    expected_bars: int
    doji_frac: float
    median_gap_sec: float | None
    last_over_sum: float | None
    max_over_sum: float | None
    notes: list[str] = field(default_factory=list)

    @property
    def usable_volume(self) -> bool:
        return self.data_state != DATA_UNUSABLE

    @property
    def allow_increments(self) -> bool:
        return self.usable_volume and self.volume_kind == GATE_INTERVAL

    @property
    def allow_cumulative_pace(self) -> bool:
        return self.usable_volume and self.volume_kind in {GATE_INTERVAL, GATE_CUMULATIVE}


def _hm(ts) -> tuple[int, int]:
    return int(ts.hour), int(ts.minute)


def expected_slots_through(asof: datetime) -> int:
    """Count 5m clock slots from 09:15 through asof, skipping lunch."""
    local = asof.astimezone(VN_TZ) if getattr(asof, "tzinfo", None) else asof.replace(tzinfo=VN_TZ)
    cursor = datetime.combine(local.date(), time(*SESSION_AM_START), tzinfo=VN_TZ)
    end = local
    am_end = datetime.combine(local.date(), time(*SESSION_AM_END), tzinfo=VN_TZ)
    pm_start = datetime.combine(local.date(), time(*SESSION_PM_START), tzinfo=VN_TZ)
    pm_end = datetime.combine(local.date(), time(*SESSION_PM_END), tzinfo=VN_TZ)
    n = 0
    while cursor <= end and cursor <= pm_end:
        hm = (cursor.hour, cursor.minute)
        in_am = (SESSION_AM_START <= hm <= SESSION_AM_END)
        in_pm = (SESSION_PM_START <= hm <= SESSION_PM_END)
        if in_am or in_pm:
            n += 1
        cursor += timedelta(minutes=5)
        if cursor > am_end and cursor < pm_start:
            cursor = pm_start
    return n


def tod_maturity_label(n_qualified_sessions: int) -> str:
    if n_qualified_sessions >= TOD_MATURE_MIN_SESSIONS:
        return TOD_MATURE
    if n_qualified_sessions >= TOD_EARLY_MIN_SESSIONS:
        return TOD_EARLY
    return TOD_PRELIMINARY


def evaluate_gate(
    bars: pd.DataFrame,
    *,
    asof: datetime | None = None,
    tod_qualified_sessions: int = 0,
) -> GateResult:
    maturity = tod_maturity_label(tod_qualified_sessions)
    notes: list[str] = []

    if bars is None or bars.empty:
        return GateResult(
            data_state=DATA_UNUSABLE,
            gate_reason=GATE_UNAVAILABLE,
            volume_kind=GATE_UNAVAILABLE,
            tod_maturity=maturity,
            overlay_applied=False,
            n_bars=0,
            expected_bars=0,
            doji_frac=0.0,
            median_gap_sec=None,
            last_over_sum=None,
            max_over_sum=None,
            notes=["no bars"],
        )

    work = bars.sort_values("timestamp").reset_index(drop=True)
    if asof is not None:
        ts = pd.Timestamp(asof)
        if ts.tzinfo is None:
            ts = ts.tz_localize(VN_TZ)
        work = work[work["timestamp"] <= ts].reset_index(drop=True)
        if work.empty:
            return evaluate_gate(pd.DataFrame(), asof=asof, tod_qualified_sessions=tod_qualified_sessions)

    n = len(work)
    overlay = bool(work["overlay_applied"].any()) if "overlay_applied" in work.columns else False
    last_ts = work["timestamp"].iloc[-1].to_pydatetime()
    expected = expected_slots_through(last_ts)

    close = pd.to_numeric(work["close"], errors="coerce")
    open_ = pd.to_numeric(work["open"], errors="coerce")
    high = pd.to_numeric(work["high"], errors="coerce") if "high" in work.columns else close
    low = pd.to_numeric(work["low"], errors="coerce") if "low" in work.columns else close
    vol = pd.to_numeric(work["volume"], errors="coerce").fillna(0.0)
    doji = ((close == open_) & (high == low)).mean() if n else 0.0
    close_eq_open = float((close == open_).mean()) if n else 0.0

    gaps = work["timestamp"].diff().dt.total_seconds().dropna()
    median_gap = float(gaps.median()) if len(gaps) else None

    vsum = float(vol.sum())
    vlast = float(vol.iloc[-1]) if n else 0.0
    vmax = float(vol.max()) if n else 0.0
    last_frac = (vlast / vsum) if vsum > 0 else None
    max_frac = (vmax / vsum) if vsum > 0 else None

    qflags = work["quality_flag"].astype(str) if "quality_flag" in work.columns else None
    bad_q = bool(qflags is not None and (qflags != "ok").any())
    if qflags is not None and (qflags == "ok").all():
        notes.append("quality_flag=ok_not_sufficient")

    # --- hard UNUSABLE ---
    structural = False
    lo, hi = RESEARCH_DEFAULT_STRUCTURAL_BARS
    fifteen = median_gap is not None and median_gap >= RESEARCH_DEFAULT_FIFTEEN_MIN_SEC
    if lo <= n <= hi and fifteen:
        structural = True
        notes.append("rigid_15m_grid")
    if close_eq_open >= RESEARCH_DEFAULT_DOJI_FRAC and doji >= 0.80:
        structural = True
        notes.append("degenerate_ohlc")

    thin = expected > 0 and (n / expected) < RESEARCH_DEFAULT_THIN_FRAC

    if structural:
        return GateResult(
            DATA_UNUSABLE, GATE_STRUCTURAL, GATE_STRUCTURAL, maturity,
            overlay, n, expected, float(doji), median_gap, last_frac, max_frac, notes,
        )
    if n == 0:
        return GateResult(
            DATA_UNUSABLE, GATE_UNAVAILABLE, GATE_UNAVAILABLE, maturity,
            overlay, 0, expected, 0.0, None, None, None, notes,
        )
    if thin:
        return GateResult(
            DATA_UNUSABLE, GATE_THIN, GATE_THIN, maturity,
            overlay, n, expected, float(doji), median_gap, last_frac, max_frac, notes,
        )

    cumulative = (
        last_frac is not None
        and max_frac is not None
        and (
            last_frac >= RESEARCH_DEFAULT_CUMULATIVE_LAST_FRAC
            or max_frac >= RESEARCH_DEFAULT_CUMULATIVE_LAST_FRAC
        )
    )
    kind = GATE_CUMULATIVE if cumulative else GATE_INTERVAL
    if cumulative:
        notes.append("volume_looks_cumulative")

    reasons = [kind]
    if overlay:
        reasons.append(GATE_STALE)
        notes.append("latest_quarantine_overlay")
    if maturity == TOD_PRELIMINARY:
        reasons.append(GATE_TOD_IMMATURE)
    if bad_q:
        reasons.append(GATE_BAD_QUALITY)

    # TRUSTED requires interval + no overlay + mature TOD + all quality ok.
    if (
        kind == GATE_INTERVAL
        and not overlay
        and not bad_q
        and maturity in {TOD_EARLY, TOD_MATURE}
        and maturity == TOD_MATURE
    ):
        state = DATA_TRUSTED
    elif kind == GATE_INTERVAL and not thin:
        state = DATA_QUALIFIED
        if maturity == TOD_PRELIMINARY or overlay or bad_q:
            # same-session families may be QUALIFIED; TOD stays tagged separately
            if bad_q:
                state = DATA_LOW
                notes.append("non_ok_quality_flag")
    elif kind == GATE_CUMULATIVE:
        state = DATA_QUALIFIED
        notes.append("increments_omitted")
    else:
        state = DATA_LOW

    if maturity == TOD_PRELIMINARY:
        notes.append(TOD_PRELIMINARY)

    return GateResult(
        data_state=state,
        gate_reason="+".join(reasons),
        volume_kind=kind,
        tod_maturity=maturity,
        overlay_applied=overlay,
        n_bars=n,
        expected_bars=expected,
        doji_frac=float(doji),
        median_gap_sec=median_gap,
        last_over_sum=last_frac,
        max_over_sum=max_frac,
        notes=notes,
    )
