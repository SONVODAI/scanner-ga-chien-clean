# Market context history

Research retention only. Production scan, Market Real, Brain A, Live Candidate V2, and the Action Layer do not read this directory.

Runtime JSONL files are local artifacts and are not source.

## `previous_close.jsonl`

Canonical previous close is the close of the latest daily bar whose date is strictly before `session_date`. A same-day daily row is never stored in `previous_close`.

The current row for a `(session_date, symbol)` is the **last line** with that key. Earlier lines stay in the file.

- An `ok` line is immutable. A later scan does not append another line for that key.
- A `stale` line may be followed by a correction when a later download has a strictly newer `previous_close_date` that is still before `session_date`. The new line sets `supersedes` to the corrected line's `captured_at`. The stale line is not deleted.

`previous_close` is integer VND via `round(d1_close, 0)`. The KBS thousands multiplier is not applied.

`last_d1_date` and `last_d1_close_before_injection` describe the last daily row before live injection. They are audit fields, not the canonical previous close.

`status` is a research quality label, not a validity bit and not a trading rule:

- `ok` — a prior bar exists and the calendar gap is 7 days or less
- `stale` — a prior bar exists and the calendar gap is longer than 7 days. The close is still stored and is still usable. This is only a data-quality warning. A long exchange holiday can make the true prior session older than 7 calendar days, so `stale` does **not** mean invalid, discarded, or unusable
- `missing` — no dated bar before `session_date`. Nothing is written, and no close is invented

There is no exchange-holiday calendar in this archive. `modules/live_candidate/calendar.py` only skips weekends, so it is not used to decide `stale`.

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
