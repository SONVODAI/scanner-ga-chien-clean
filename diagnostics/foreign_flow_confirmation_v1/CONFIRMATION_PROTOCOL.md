# Foreign Flow Confirmation Protocol V1

## Status

Prospective, pre-registered confirmation protocol.  
**Discovery is closed.** No grammar expansion, threshold search, or candidate replacement.

## Freeze boundary

| Item | Value |
|------|-------|
| Last in-sample trade date | `2026-08-24` |
| First eligible confirmation T0 | **strictly after** `2026-08-24` |
| Blind research freeze dataset | `ff_hsx_symbol_daily_v1_20260825T045650Z` |

No post-freeze observation may influence thresholds, features, outcomes, PASS/FAIL criteria, or candidate scope.

## Question

> Do the pre-registered Foreign Flow magnitude candidates continue to show the same incremental T10 effect in genuinely unseen future data?

## Frozen candidates

See `CANDIDATE_FREEZE.json`.

1. **Primary:** `abn_abs_z20` @ T10 — `|net_z_60| > 2.0`
2. **Secondary:** `net_hi_pct90` @ T10 — `net_pct_252 >= 0.90`
3. **Optional anti-edge:** `streak_neg_le_m5` @ T10 — `net_streak <= -5`

Judged **independently**. Secondary success cannot rescue primary failure. Combination not pre-registered.

## PIT / feature timing

- Features use data available by **T0 close only** (including T0 foreign_net_value and T0 OHLC as state).
- No future bars; no revised future information; no T10 label at event-append time.
- **Earliest valid prediction timestamp:** T0 session close (conservative; intra-day HSX foreign release not separately verified — same as V1).
- **Outcome maturity date:** close of the **10th subsequent trading session** after T0.
- Lookbacks: 60 sessions (`abn_abs_z20`), 252 sessions (`net_hi_pct90`), variable streak (`streak_neg_le_m5`), all `min_periods` full — incomplete lookback ⇒ not eligible (NULL ≠ 0).

## Outcome (locked)

- Primary: `ret_t10 = close_{T+10} / close_T0 - 1` (trading sessions).
- Metrics: mean, median, win rate, incremental mean vs baseline, sample breadth, symbol/date concentration; secondary MAE/MFE/forward drawdown.
- Do not change primary outcome after confirmation starts.

## Baseline (locked)

Family from V1:

1. **Unconditional eligible** observations in the same confirmation era (post-freeze matured rows passing DQ + price filters).
2. **Same-era contemporaneous baseline** = (1), computed only on dates that exist in the confirmation window.
3. **Parent-condition baseline** for price-control tests only (`px_ret_20` terciles / OLS residual) — not a license to add new parents.

Primary evidence = **incremental**, not absolute return.

## PASS / FAIL

See `PASS_FAIL_CRITERIA.json` (A–H). Frozen before any post-freeze T10 aggregate inspection.

## Windows

See `EXPECTED_TRIGGER_FREQUENCY.md`.

- Minimum ≈ 90 matured trigger dates (monitoring).
- Preferred ≈ 200 matured trigger dates (final).
- Max patience = 504 sessions from first post-freeze T0.

## States (exact)

`WAITING_FOR_EVENTS` → `WAITING_FOR_MATURITY` → `CONFIRMATION_IN_PROGRESS` → `CONFIRMED` | `FAILED_CONFIRMATION` | `INCONCLUSIVE`

## No peeking

After freeze: do not change thresholds, features, candidates, horizon, baseline, PASS criteria, or evaluation window based on interim performance. Interim operator view may show only trigger/matured/coverage/DQ counts unless explicitly marked non-binding.

## Safety

No Market First / Forecast score / P0 semantics / Edge Research / Camera changes. No BUY/SELL. No alerts. Confirmation recording only in isolated namespace.
