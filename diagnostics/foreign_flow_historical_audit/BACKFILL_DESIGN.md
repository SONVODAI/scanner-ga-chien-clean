# Foreign Flow Historical Backfill Design (NOT EXECUTED)

**Recommendation:** `BACKFILL_WORTHWHILE`  
**This document is design-only. Do not run backfill in this task.**

---

## Goal

Canonical **per-symbol HOSE** research store:

`foreign flow T0 (VALUE/VOLUME) + session OHLC`  
for blind stock-level Edge Research later.

**Not** a historical rewrite of production `p0_market_daily` EMS-142 aggregates (unless a separate, explicitly biased “current-universe projection” product is approved).

---

## Proposed schema (research store)

Path suggestion (future): `data/foreign_flow_research/hsx_symbol_daily.csv` (or partitioned by year).

| Column | Type | Notes |
|--------|------|-------|
| trade_date | date | from `reportDate` |
| symbol | str | HOSE code |
| exchange | str | `HOSE` |
| foreign_buy_value | float | VND; NULL if absent |
| foreign_sell_value | float | VND |
| foreign_net_value | float | derived; NULL if inputs NULL |
| foreign_buy_volume | float | shares |
| foreign_sell_volume | float | shares |
| foreign_net_volume | float | derived |
| biglot_buy_value | float | optional |
| biglot_sell_value | float | optional |
| open/high/low/close/average | float | from same HSX row |
| source | str | `HSX_FOREIGN_API` |
| retrieved_at | iso | fetch time |
| row_hash | str | stable hash of raw fields |
| schema_version | str | e.g. `ff_hsx_symbol_daily_v1` |

**Immutability:** first-write-wins on `(trade_date, symbol)`.  
**Missing:** never write 0 for absent foreign.

Optional side table: `membership_asof_ems.csv` only for dates EMS exists (17+ going forward).

---

## Safe backfill plan (future execution)

1. **Eligibility list:** EMS-142 ∩ HSX-nonempty (117 as of 2026-08-24) + optional expanded HOSE list — version the list with `asof_date`.
2. **Fetch:** `pageSize=5000` (or paginate) per symbol; throttle; retry on IncompleteRead; persist raw JSON optional.
3. **Parse** via existing `parse_hsx_foreign_payload` semantics (extend to keep OHLC).
4. **Validate:** weekday dates; non-negative values; buy/sell NULL policy; hash.
5. **Atomic durable write** (reuse `modules/durable_csv` patterns); bounded backups.
6. **Do not** mutate `p0_market_daily.csv`, Forecast T0, MDRR, or Market First.
7. **Coverage report:** per symbol first/last/n_dates; fraction of EMS-142; HNX gap list.
8. **No outcome materialization** in v1 store (keep labels separate later).

---

## What not to backfill yet

- EMS-142 daily **universe aggregate** history using today’s membership for past dates (survivorship).
- ADV/turnover features without an approved volume history source.
- Invented Market regime labels for 2009–2025.

---

## Estimated effort / risk

| Item | Note |
|------|------|
| Volume | ~117 symbols × ~4k rows ≈ ~0.5M rows — fine as CSV/parquet |
| API load | Throttle carefully; large payloads |
| Legal/ToS | Official public HSX API used by site; keep polite rate |
| Production risk | None if isolated research path |

---

## Exit criteria before Edge phase

1. Store frozen with provenance.  
2. Bias labels documented.  
3. Outcome layer designed separately.  
4. No hypothesis hard-coded.
