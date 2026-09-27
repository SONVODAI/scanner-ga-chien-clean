"""EARLY RECOVERY WATCH V1. Isolated research panel. Not a buy engine."""

from modules.early_recovery_watch.contract import (
    DELTA_RS10_MIN,
    EARLY_RECOVERY_ALERT_ELIGIBLE,
    EARLY_RECOVERY_IS_BUY,
    MARKET_REAL_MAX_EXCLUSIVE,
    RS10_MAX,
)
from modules.early_recovery_watch.panel import render_early_recovery_watch

__all__ = [
    "DELTA_RS10_MIN",
    "EARLY_RECOVERY_ALERT_ELIGIBLE",
    "EARLY_RECOVERY_IS_BUY",
    "MARKET_REAL_MAX_EXCLUSIVE",
    "RS10_MAX",
    "render_early_recovery_watch",
]
