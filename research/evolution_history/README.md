# Evolution history

Research collection only. Production scan, Market Real, Brain A, Live Candidate V2, SweetSpot, and the Action Layer do not read this directory.

Runtime JSONL is a local artifact and is not source.

## `evolution_ledger.jsonl`

Append-only copy of raw fields already present on a completed production scan frame. The writer does not call a market-data provider, recompute indicators, or score a recovery.

One line is one symbol at one capture. Prior lines are never rewritten.

For the same `trade_date`, `source`, and `symbol`, a new line is appended only when the hash of the observed fields differs from the last retained line. Identical reruns are skipped. There is no minimum time gap, and collection is not reduced to one row per session slot.

`source` is `streamlit_scan` or `close_scan`. `close_scan` is a separate key, so its first line is kept even when the observed state matches the last `streamlit_scan` line.

`captured_at` is Asia/Ho_Chi_Minh. `session_slot` is the existing clock label (`PRE_MARKET`, `MORNING`, `MIDDAY`, `AFTERNOON`, `CLOSE`, `AFTER_CLOSE`) stored as provenance.

`scan_fingerprint` is the Research Data Foundation V1 batch id: SHA-256 of sorted `symbol|price|group`. It is not the per-symbol dedupe key. This writer does not read `research/market_context_history/*.jsonl`.

`state_hash` is the SHA-256 of the observed fields. It is the dedupe key, not a stock score.

`status` is `ok` when the line was written. A missing scan column is stored as null. A symbol absent from `scan_df` is not invented.

A truncated tail is left in place. The next append starts on a new line. Readers skip lines that are not JSON objects.

## No-look-ahead join

A future reader may attach a Market Context row when, after both clocks are Asia/Ho_Chi_Minh:

`context.captured_at <= evolution.captured_at`

for the same `trade_date` and `source`, preferring the matching `scan_fingerprint`.

Helper: `evolution_context_asof_eligible` in `modules/research_evolution_ledger/contract.py`.

This directory does not attach T3/T5/T10, compute path excursion, or classify a trajectory.
