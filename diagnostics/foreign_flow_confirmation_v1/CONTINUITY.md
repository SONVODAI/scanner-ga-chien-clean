# Continuity: Freeze History + Forward Panel

## Rule

| Domain | Store | Writable by confirmation? |
|--------|-------|---------------------------|
| `trade_date <= 2026-08-24` | `data/foreign_flow_history/canonical/by_symbol/*.csv` | **READ ONLY** |
| `trade_date > 2026-08-24` | `data/foreign_flow_confirmation/forward_panel/by_symbol/*.csv` | **YES** (append / first-write-wins) |

## Join for features (`join_history_and_forward`)

```
series(symbol, asof) =
  history[symbol][trade_date <= 2026-08-24]
  ∪ forward_panel[symbol][2026-08-24 < trade_date <= asof]
```

Sorted by `trade_date` ascending. Domains are disjoint; freeze files are never rewritten.

## Lookbacks

| Candidate | Need |
|-----------|------|
| `abn_abs_z20` | 60 sessions with finite `foreign_net_value` ending at T0 |
| `net_hi_pct90` | 252 sessions with finite `foreign_net_value` ending at T0 |
| `streak_neg_le_m5` | finite T0 net + consecutive sign path (NULL ≠ 0) |

Early post-freeze T0s obtain lookback from freeze history automatically.
