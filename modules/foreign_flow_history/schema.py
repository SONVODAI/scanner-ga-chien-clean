"""Schema for canonical HSX symbol-daily foreign-flow history."""

from __future__ import annotations

SCHEMA_VERSION = "ff_hsx_symbol_daily_v1"
SOURCE_NAME = "HSX_FOREIGN_API"
SOURCE_SCOPE = "HOSE_SYMBOL_LEVEL"
SOURCE_UNITS = "VND"
EXCHANGE = "HOSE"

# Natural key: (trade_date, symbol)
CANONICAL_COLUMNS = [
    "trade_date",
    "symbol",
    "exchange",
    "foreign_buy_value",
    "foreign_sell_value",
    "foreign_net_value",
    "foreign_buy_volume",
    "foreign_sell_volume",
    "foreign_net_volume",
    "biglot_buy_value",
    "biglot_sell_value",
    "biglot_buy_volume",
    "biglot_sell_volume",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "average_price",
    "source",
    "source_scope",
    "source_units",
    "fetched_at",
    "schema_version",
    "row_hash",
]

DEFAULT_DATA_ROOT = "data/foreign_flow_history"
