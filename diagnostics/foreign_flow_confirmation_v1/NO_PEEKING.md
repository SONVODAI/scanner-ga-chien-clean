# No-Peeking / Anti-HARKing Controls

## Design-time proof (this task)

1. Criteria, thresholds, windows, and candidate scope were written from **V1 holdout/discovery/validation artifacts only**.
2. Canonical store check at design time: **0** rows with `trade_date > 2026-08-24`.
3. No aggregate `ret_t10` / incremental performance was computed on any post-freeze sample while designing PASS/FAIL.
4. Historical effect sizes cited in criteria are **pre-freeze V1 holdout** numbers already published in Blind Research V1.

## Runtime controls

1. `protocol_hash` embedded in every event; changing criteria files after start requires a **new protocol_id** (not silent edit).
2. T0 events are **append-only**; outcomes live in a separate layer.
3. Default operator summary exposes **counts only** (triggers, matured, symbols, dates, DQ) until `final_judgment_allowed=true`.
4. Code path `compute_pass_fail` refuses to run unless matured unique dates ≥ preferred window **or** patience exhausted (inconclusive path).
5. Forbidden: rewriting thresholds, swapping z20→z60, adding interactions, changing T10, or combining candidates after seeing results.

## What interim status may show

- candidate
- state
- triggers
- matured T10
- unique symbols / dates
- data-quality status
- whether final judgment is allowed yet

Not for protocol mutation: any interim performance printout.
