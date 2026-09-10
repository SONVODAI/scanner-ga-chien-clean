"""Read-only LIVE CANDIDATE × P×V observation panel.

Displays Dynamic Watchlist + live shadow evidence. Never calls Camera,
never recomputes P×V, never writes watchlist/evidence, never alerts.
"""

from modules.live_candidate_pxv_ui.view import build_panel

__all__ = ["build_panel"]
