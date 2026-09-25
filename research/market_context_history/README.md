# Market context history

Research retention only. Production scan, Market Real, Brain A, Live Candidate V2, and the Action Layer do not read this directory.

Runtime JSONL files are local artifacts and are not source.

## `previous_close.jsonl`

One row per `(session_date, symbol)`. The first write wins. A later attempt does not add a second row.

Canonical previous close is the close of the latest daily bar whose date is strictly before `session_date`. A same-day daily row is never stored in `previous_close`.

`previous_close` is integer VND via `round(d1_close, 0)`. The KBS thousands multiplier is not applied.

`last_d1_date` and `last_d1_close_before_injection` describe the last daily row before live injection. They are audit fields, not the canonical previous close.

`status`:

- `ok` — prior bar exists and is within 7 calendar days
- `stale` — prior bar exists but the gap is longer than 7 calendar days; the close is still stored
- `missing` — no dated bar before `session_date`; `previous_close` is null

## `market_context.jsonl`

Append-only log of Market Real, Market Live, Market Forecast, and regime already computed by a production run. The writer does not recompute them.

For the same `trade_date` and `source`, a new row is appended when any of `market_real`, `market_live`, `market_forecast`, or `scan_fingerprint` differs from the last retained row. Identical reruns are skipped. There is no minimum time gap.

`captured_at` is Asia/Ho_Chi_Minh.

`source` is `streamlit_scan` or `close_scan`.

`scan_fingerprint` is a SHA-256 of sorted `symbol|price|group` lines from the scan that produced the scores.

## No-look-ahead join

Camera bars are labeled at the start of the 5-minute bucket. A bar timestamp `T` completes at `T + 5 minutes`.

A future reader may attach a context row only when, after both clocks are converted to Asia/Ho_Chi_Minh:

`market_context.captured_at <= T + 5 minutes`

Previous close may be used only when `previous_close_date < session_date`.

Helpers: `modules/research_market_context/contract.py`.

This directory does not implement offensive-strength detection, Brain A below-6 nomination, or any buy rule.
