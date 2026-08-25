# Outcome Semantics

## PIT timing

- Each canonical row is one HOSE `trade_date × symbol` session from the official HSX foreign endpoint.
- Fields (`foreign_*`, OHLC) are treated as **known at/after that session's close** for research purposes.
- Exact intra-day release timestamp of HSX foreign prints is **not** separately verified; conservative rule: **no same-session forward return using T0 close as both feature path and exit**.

## Earliest legitimate outcome

- **T0 close** = state / marking price only.
- **T1** = next trading session's close / T0 close − 1.
- **T3 / T5 / T10** = 3rd / 5th / 10th subsequent **trading session** close / T0 close − 1.
- Horizons are **session counts**, not calendar days.

## Integrity filters

- Drop research rows where `close_price <= 0`.
- Drop rows with extreme prior-close→T0 jump (`ratio > 1.8` or `< 0.55`) as likely CA/bad prints.
- Forward return requires destination close `> 0`.
- Corporate-action adjustment status of provider OHLC is **unknown**; long-horizon levels may still contain split artifacts even after jump filters — documented as a caveat.

## MFE / MAE

- MFE/MAE over next 10 sessions vs T0 close using path high/low when available.
- Not used as primary discovery metric; descriptive only.
