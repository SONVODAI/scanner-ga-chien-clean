"""Research-only LIVE Candidate first-seen + Dynamic Watchlist.

Not Camera. Not P×V. Not BUY/SELL. Not alerts.
"""

from modules.live_candidate.persist import apply_immutable_first_seen
from modules.live_candidate.watchlist import build_research_watchlist

__all__ = ["apply_immutable_first_seen", "build_research_watchlist"]
