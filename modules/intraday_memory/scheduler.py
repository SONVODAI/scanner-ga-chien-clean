"""
Scheduling helpers for unattended intraday memory deployment.

V1A deployment collects each completed trading session once (with idempotent
retries), not on a 5-minute whole-universe cadence. Guest-tier throttle math
does not permit ~142 symbols every 5 minutes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from modules.intraday_memory.timezone_policy import VN_TZ

# Live-validated guest-tier observation (5 symbols in 15.36s on VPS).
OBSERVED_SEC_PER_SYMBOL = 15.36 / 5.0
PRODUCTION_UNIVERSE_SIZE = 142
GUEST_RPM = 18

# Minimum throttle-only floor: 142 requests / 18 rpm ≈ 7.9 minutes.
THROTTLE_FLOOR_SEC = (PRODUCTION_UNIVERSE_SIZE / GUEST_RPM) * 60.0
ESTIMATED_FULL_UNIVERSE_SEC = PRODUCTION_UNIVERSE_SIZE * OBSERVED_SEC_PER_SYMBOL

# VN cash market regular close ~15:00; allow post-close collection after 16:00.
POST_CLOSE_HOUR = 16


def is_vn_weekend(day: date) -> bool:
    """True for Saturday/Sunday in VN calendar (no exchange holiday calendar in V1A)."""
    return day.weekday() >= 5


def previous_weekday(day: date) -> date:
    """Step back one calendar day, skipping weekends."""
    candidate = day - timedelta(days=1)
    while is_vn_weekend(candidate):
        candidate -= timedelta(days=1)
    return candidate


def resolve_collect_session_date(
    now: datetime | None = None,
) -> tuple[date | None, str | None]:
    """
    Resolve which session to collect for a scheduled run.

    Returns (session_date, skip_reason). skip_reason is set when the scheduler
    should not invoke the collector (weekend guard only — no holiday calendar).
    """
    local = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    today = local.date()

    if is_vn_weekend(today):
        return None, "weekend"

    if local.hour >= POST_CLOSE_HOUR:
        session = today
    else:
        session = previous_weekday(today)

    return session, None


def resolve_reconcile_session_date(
    now: datetime | None = None,
) -> tuple[date | None, str | None]:
    """
    Reconcile the most recently completed session.

    Morning runs target the prior weekday session (e.g. Tue 07:30 → Mon).
    """
    local = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    today = local.date()

    if is_vn_weekend(today):
        return None, "weekend"

    if local.hour >= POST_CLOSE_HOUR:
        session = today
    else:
        session = previous_weekday(today)

    return session, None


def estimate_full_universe_duration_sec(
    *,
    universe_size: int = PRODUCTION_UNIVERSE_SIZE,
    requests_per_minute: int = GUEST_RPM,
) -> float:
    """
    Conservative wall-clock estimate for one full-universe pass.

    Uses max(throttle floor, live observed per-symbol rate).
    """
    throttle_floor = (universe_size / max(1, requests_per_minute)) * 60.0
    observed = universe_size * OBSERVED_SEC_PER_SYMBOL
    return max(throttle_floor, observed)


def minimum_timer_spacing_minutes(
    *,
    universe_size: int = PRODUCTION_UNIVERSE_SIZE,
    requests_per_minute: int = GUEST_RPM,
    safety_factor: float = 1.25,
) -> int:
    """Recommended minimum minutes between full-universe scheduled runs."""
    seconds = estimate_full_universe_duration_sec(
        universe_size=universe_size,
        requests_per_minute=requests_per_minute,
    )
    return int((seconds * safety_factor) / 60.0) + 1
