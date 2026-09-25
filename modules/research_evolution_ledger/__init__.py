"""Evolution Observer V1. Retention only. Not a production input."""

from modules.research_evolution_ledger.contract import evolution_context_asof_eligible
from modules.research_evolution_ledger.ledger import try_append_evolution_ledger

__all__ = [
    "evolution_context_asof_eligible",
    "try_append_evolution_ledger",
]
