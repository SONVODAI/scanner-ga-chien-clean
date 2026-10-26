# Automation Design — Foreign Flow Confirmation V1

## Goal

Smallest safe unattended path for **confirmation recording only**. No trading behavior.

```
daily HSX symbol foreign-flow T0
  → evaluate frozen candidate eligibility (DQ fail-closed)
  → append confirmation event (if trigger + eligible)
  → wait 10 trading sessions
  → append outcome layer
  → update confirmation status (counts / state machine)
```

## Integration preference

Reuse existing P0/HSX foreign collection **fields** and the accepted historical path:

- Official source: `https://api.hsx.vn/mk/api/v1/market/securities/foreign/{SYM}`
- Module: `modules/foreign_flow_history/` (client/parse/schema) — **read patterns only**; do not mutate P0 semantics or Forecast.
- Confirmation ledgers live only under `data/foreign_flow_confirmation/`.

## Required forward fields

| Field | Needed for | Already in freeze store? | In P0 daily universe aggregate? |
|-------|------------|---------------------------|----------------------------------|
| `trade_date`, `symbol` | key | yes (≤2026-08-24) | partial / different grain |
| `foreign_net_value` | all candidates | yes | universe sum, not symbol×day history |
| `foreign_buy_value`, `foreign_sell_value` | provenance/DQ | yes | universe-level |
| `close_price`, `high_price`, `low_price` | outcome + CA gate | yes | not this store |
| trailing 60 sessions net | `abn_abs_z20` | yes historically | **NO** in P0 |
| trailing 252 sessions net | `net_hi_pct90` | yes historically | **NO** in P0 |
| streak history | anti-edge | computable from net series | **NO** in P0 |

### Forward-memory gap — CLOSED in code (pending deploy)

1. **Daily symbol×day HSX foreign append** → `modules/foreign_flow_confirmation/daily.py` + `exact_date.py` → `data/foreign_flow_confirmation/forward_panel/by_symbol/`.
2. **Lookback continuity** → `continuity.join_history_and_forward` (freeze READ-ONLY + forward).
3. **Session calendar** → `offset_trading_sessions` for T10 maturity.

Deploy via existing Forecast Memory daily stage hook (`ff_confirmation_forward`). No new timer.

## Isolated runtime layout

```
data/foreign_flow_confirmation/
  events/           # append-only T0 JSONL
  outcomes/         # append-only maturity JSONL
  baselines/        # periodic baseline snapshots
  status/           # per-candidate status JSON
  forward_panel/    # post-freeze symbol×day rows (not mixed into freeze raw)
  manifests/        # run manifests / hashes
```

## Daily job (design only in this phase)

1. Fetch HSX foreign for EMS HOSE cohort (same 117 overlap policy as freeze, or document cohort drift).
2. Write/append forward panel row(s) for T0.
3. Build feature intermediates with history+forward (exact V1 formulas).
4. For each frozen candidate: if trigger & DQ pass → append event **before** any outcome known.
5. For events with maturity date ≤ today: append outcome if missing.
6. Recompute status counts only (triggers, matured, symbols, dates, DQ fails).
7. **Do not** recompute PASS metrics into operator summary until preferred window (or explicit audit mode).

## Explicit non-goals

- No timers beyond existing daily research infrastructure hooks.
- No BUY/SELL alerts.
- No Streamlit / Camera / Market First / Forecast score edits.
- No automatic deployment in this protocol-freeze task.

## Module

`modules/foreign_flow_confirmation/` — ledger append, status machine, operator summary (counts-only by default).
