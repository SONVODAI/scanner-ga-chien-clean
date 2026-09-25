"""Research data foundation. Retention only. Not a production input."""

from modules.research_market_context.contract import (
    market_context_asof_eligible,
    previous_close_date_eligible,
)
from modules.research_market_context.market_context import try_append_market_context
from modules.research_market_context.previous_close import try_archive_previous_close

__all__ = [
    "market_context_asof_eligible",
    "previous_close_date_eligible",
    "try_append_market_context",
    "try_archive_previous_close",
]
