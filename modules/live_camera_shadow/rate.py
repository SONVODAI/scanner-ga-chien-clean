"""18 rpm live-sweep math. Not a ranking engine."""

from __future__ import annotations

GUEST_RPM = 18
BAR_SECONDS = 5 * 60
LIVE_UNIVERSE_CAP = 50


def min_interval_sec(rpm: int = GUEST_RPM) -> float:
    return 60.0 / max(1, rpm)


def sweep_seconds(n_symbols: int, rpm: int = GUEST_RPM) -> float:
    """Wall time if starts are spaced by the throttle floor (request < interval)."""
    return float(n_symbols) * min_interval_sec(rpm)


def sweep_seconds_with_payload(
    n_symbols: int,
    rpm: int = GUEST_RPM,
    payload_sec: float = 3.07,
) -> float:
    """Conservative: one request cannot start before max(interval, payload)."""
    return float(n_symbols) * max(min_interval_sec(rpm), payload_sec)


def universe_fits_5m(
    n_symbols: int,
    rpm: int = GUEST_RPM,
    payload_sec: float = 3.07,
    budget_sec: float = BAR_SECONDS,
) -> bool:
    return sweep_seconds_with_payload(n_symbols, rpm, payload_sec) <= budget_sec


def rate_report(rpm: int = GUEST_RPM) -> dict:
    sizes = (30, 40, 50, 142)
    return {
        "rpm": rpm,
        "min_interval_sec": min_interval_sec(rpm),
        "payload_sec_observed_v1a": 3.07,
        "sizes": {
            str(n): {
                "throttle_only_sec": round(sweep_seconds(n, rpm), 1),
                "conservative_sec": round(sweep_seconds_with_payload(n, rpm), 1),
                "fits_5m_bar": universe_fits_5m(n, rpm),
            }
            for n in sizes
        },
        "max_safe_under_18rpm_conservative": max(
            n for n in range(1, 143) if universe_fits_5m(n, rpm)
        ),
        "hard_cap_this_slice": LIVE_UNIVERSE_CAP,
        "full_142_live": False,
    }
