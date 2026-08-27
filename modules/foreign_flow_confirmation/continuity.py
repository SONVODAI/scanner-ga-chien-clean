"""Lookback continuity: frozen history (≤2026-08-24) + forward panel (>2026-08-24).

Forward calculations READ freeze canonical CSVs but never rewrite them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from modules.foreign_flow_confirmation.forward_panel import LAST_IN_SAMPLE, read_forward_symbol
from modules.foreign_flow_history.schema import CANONICAL_COLUMNS
from modules.foreign_flow_history.store import read_symbol_canonical

DEFAULT_HISTORY_ROOT = Path("data/foreign_flow_history")


def join_history_and_forward(
    symbol: str,
    *,
    asof_trade_date: str,
    history_root: Path | str = DEFAULT_HISTORY_ROOT,
    confirmation_root: Optional[Path | str] = None,
) -> pd.DataFrame:
    """
    Build PIT series for one symbol as-of ``asof_trade_date``.

    Continuity rule:
    - Rows with trade_date <= LAST_IN_SAMPLE come from freeze history only.
    - Rows with trade_date > LAST_IN_SAMPLE come from confirmation forward_panel only.
    - Result filtered to trade_date <= asof_trade_date, sorted ascending.
    - Duplicate keys: history wins on pre-freeze; forward wins on post-freeze
      (domains are disjoint by construction).
    """
    asof = str(asof_trade_date)[:10]
    hist = read_symbol_canonical(symbol, history_root)
    fwd = read_forward_symbol(symbol, confirmation_root)

    frames = []
    if hist is not None and not hist.empty:
        h = hist.copy()
        h["trade_date"] = h["trade_date"].astype(str).str[:10]
        h = h[h["trade_date"] <= LAST_IN_SAMPLE]
        frames.append(h)
    if fwd is not None and not fwd.empty:
        f = fwd.copy()
        f["trade_date"] = f["trade_date"].astype(str).str[:10]
        f = f[f["trade_date"] > LAST_IN_SAMPLE]
        frames.append(f)

    if not frames:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    out = pd.concat(frames, ignore_index=True)
    out = out[out["trade_date"] <= asof]
    out = out.sort_values("trade_date").drop_duplicates(subset=["trade_date"], keep="last")
    for col in CANONICAL_COLUMNS:
        if col not in out.columns:
            out[col] = None
    return out[CANONICAL_COLUMNS].reset_index(drop=True)


def lookback_complete(series: pd.DataFrame, *, need: int) -> bool:
    """Require ``need`` sessions with non-null foreign_net_value ending at asof."""
    if series is None or series.empty:
        return False
    nets = series["foreign_net_value"]
    # trailing window including last row
    tail = nets.iloc[-need:] if len(nets) >= need else nets
    if len(tail) < need:
        return False
    return bool(tail.notna().all())
