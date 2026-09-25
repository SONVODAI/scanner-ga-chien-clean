"""Research-only SHADOW BUY measurement. Not an order path."""

from modules.research_shadow_buy.ledger import try_record_shadow_buy

__all__ = ["try_record_shadow_buy"]
