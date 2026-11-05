# Shared Research D1 Archive

Research-only historical daily OHLCV captured via the pinned legacy vnstock
DNSE/Entrade path (`stock_historical_data`), without live-bar injection.

## Files (local artifacts; not production)

- `d1_observations.jsonl` — append-only versioned bars (`adjustment_status=UNVERIFIED`)
- `d1_quality_events.jsonl` — missing symbols/sessions, duplicate dates, conflicts
- `vnindex_session_index_candidate.json` — candidate dates only (`verified: false`)
- `d1_run_reports.jsonl` — collection run summaries

## Hard rules

- Never silently overwrite a prior `(symbol, session_date)` payload
- Do **not** feed this archive into Research Ledger B1 `VerifiedSessionCalendar`
  / `PriceBook` or Guardian outcome calculations while unverified
- Production Position Guardian, scanners, V2 Action, and `app.py` do not read here
