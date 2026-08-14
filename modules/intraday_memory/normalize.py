"""
Price normalization: KBS returns OHLC in thousands of VND.

Canonical storage unit: integer VND.
Example: 22.20 → 22200

All open/high/low/close fields MUST use integer VND consistently.
"""

from __future__ import annotations

import math
from typing import Any

PRICE_SCALE_FACTOR = 1000
MIN_INTEGER_VND = 1


def normalize_price_to_integer_vnd(raw: Any) -> int:
    """
    Convert provider price to integer VND.

    KBS returns values like 22.20 meaning 22,200 VND.
    Legacy-style integer values (>1000) pass through unchanged.
    """
    if raw is None:
        raise ValueError("Price is None")

    if isinstance(raw, bool):
        raise ValueError("Price cannot be boolean")

    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Non-numeric price: {raw!r}") from exc

    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"Invalid numeric price: {value}")

    if value <= 0:
        raise ValueError(f"Price must be positive: {value}")

    # Already integer VND scale (e.g. Legacy-style 22200).
    if value >= 1000 and value == int(value):
        result = int(value)
    else:
        # KBS thousands scale: multiply by 1000 and round to nearest VND.
        result = int(round(value * PRICE_SCALE_FACTOR))

    if result < MIN_INTEGER_VND:
        raise ValueError(f"Normalized price too small: {result}")

    return result


def normalize_volume(raw: Any) -> int:
    """Convert volume to non-negative integer."""
    if raw is None:
        raise ValueError("Volume is None")

    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Non-numeric volume: {raw!r}") from exc

    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"Invalid numeric volume: {value}")

    if value < 0:
        raise ValueError(f"Volume cannot be negative: {value}")

    return int(round(value))
