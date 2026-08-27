"""Production EOD package — headless canonical daily accumulation."""

from modules.production_eod.headless_eod import (
    HEADLESS_EOD_VERSION,
    run_headless_eod,
    should_attempt_headless_eod,
)

__all__ = [
    "HEADLESS_EOD_VERSION",
    "run_headless_eod",
    "should_attempt_headless_eod",
]
