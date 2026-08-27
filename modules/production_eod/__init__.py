"""Production EOD package — headless canonical daily accumulation."""

from modules.production_eod.headless_eod import (
    HEADLESS_EOD_VERSION,
    PROBE_FAILED,
    PROBE_NOT_TRADING,
    PROBE_OK,
    RUN_CLASS_AUTONOMOUS,
    RUN_CLASS_RECOVERY,
    TradingDayProbeResult,
    resolve_trading_today,
    run_headless_eod,
    should_attempt_headless_eod,
)

__all__ = [
    "HEADLESS_EOD_VERSION",
    "PROBE_FAILED",
    "PROBE_NOT_TRADING",
    "PROBE_OK",
    "RUN_CLASS_AUTONOMOUS",
    "RUN_CLASS_RECOVERY",
    "TradingDayProbeResult",
    "resolve_trading_today",
    "run_headless_eod",
    "should_attempt_headless_eod",
]
