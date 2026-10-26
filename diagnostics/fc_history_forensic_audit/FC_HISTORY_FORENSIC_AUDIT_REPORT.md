# FC History Forensic Audit (read-only)

**Audit date:** 2026-08-24  
**Scope:** Repository + persisted CSVs/artifacts only. No recovery implemented. No model training. No production Forecast / Market First / Edge Research changes.

**Verdict:** `FC_HISTORY_PARTIALLY_RECOVERABLE`

---

## Why the new Forecast pipeline found only 17 T0 sessions

1. `modules/forecast_research/t0_builder.py` reads **only** `data/earning_money_snapshots.csv` + optional `market_daily_t0.csv`.
2. EMS has **17** full-142 board dates (`2026-07-31` → `2026-08-24`).
3. EMS column `market_forecast` is **100% null** (2414/2414 rows). The builder **recomputes** FC via `_calc_fc(board)` from group composition — it does **not** load historically displayed FC from other stores.
4. Longer FC history in `buy_elite_learning_history.csv`, root `pattern_history.csv`, and EL stores was **never consulted**.

The number **17** is therefore the EMS board backfill count, **not** the age of FC in production.

---

## A / B / C (do not conflate)

| Quantity | Definition | Count (evidence-based) |
|---|---|---|
| **A. FC existed historically** | Code path `calc_market_forecast` / ForecastEngine present; UI/decision coupling | Code from **~2025-05** (`app.py`); operational market FC values evidenced in persisted files from **2026-06-25** |
| **B. FC was persisted historically** | Non-null `market_forecast` (or equivalent) in a durable file | **42 weekday sessions** union (`2026-06-25`→`2026-08-24`); **51** calendar dates if weekends in root PH included |
| **C. FC can become immutable PIT-safe full Forecast T0** | 142 board + honest completeness + no leakage | **COMPLETE: 8**; **PARTIAL 142 with persisted FC: 12**; **PARTIAL 142 board with reconstructed FC only: 17**; market-core (non-142) additional history feasible but not full T0 |

---

## Source inventory (evidence)

| File | FC field | Earliest→latest | Sessions w/ non-null FC | Universe | REAL/LIVE | PIT class |
|---|---|---|---:|---|---|---|
| `buy_elite_learning_history.csv` | `market_forecast` | 2026-06-25→08-24 | **41** | elite subset only | REAL yes; no LIVE col | `NOT_PROVABLY_PIT_SAFE` (signal ledger, not EOD board freeze) |
| `pattern_history.csv` (root) | `market_forecast` | 2026-07-02→08-24 | **43** calendar / **34** weekday | 7–133 (never 142) | REAL yes; **no** `market_live` | `NOT_PROVABLY_PIT_SAFE` + `LEAKAGE_RISK` if `t*_return` used; FC often multi-valued intraday |
| `data/earning_learning/pattern_history.csv` | `market_forecast` | FC non-null **08-07→08-24** (file dates from 07-23) | **12** | **142** | REAL/LIVE non-null from **08-13** only | `PIT_RECONSTRUCTABLE` with care (multi rows/day); earlier dates have **null** FC |
| `data/earning_learning/decision_archive.csv` / `observations.csv` / `pattern_snapshot.csv` | `market_forecast` | same EL window | **12** FC dates | 142 | REAL/LIVE from 08-13 | same as EL PH |
| `data/earning_money_snapshots.csv` | `market_forecast` | board 07-31→08-24 | **0** persisted FC rows | **142**/day ×17 | REAL/LIVE columns exist but null in practice for scores until MDT0 era overlay | Board DNA `PIT_SAFE`; FC `PIT_RECONSTRUCTABLE` from groups |
| `market_daily_t0.csv` | `market_forecast` (+ text/confidence) | 2026-08-13→08-24 | **8** | market scalar | REAL+LIVE yes | **`PIT_SAFE`** (canonical after ≥18:00 VN, first-write-wins) |
| `market_t0_snapshot.csv` | same | 08-13→08-24 | **8** | market scalar | yes | `PIT_SAFE` per session slot |
| `t0_observation_freeze.csv` | `market_forecast` | 08-13→08-24 | **8** | **142** | yes | `PIT_SAFE` immutable freeze |
| `market_aware_sweetspot_observer_ledger.csv` | `market_forecast_t0` | 08-14→… | subset of MDT0 era | context rows | yes | `PIT_SAFE`-ish observer |
| `data/forecast_research/forecast_t0_daily.csv` | derived | 07-31→08-24 | **17** | 142 | COMPLETE only when MDT0 present | derived layer (new); FC often **reconstructed**, not EMS-persisted |

No older FC parquet/JSON archives found under `brain/` (empty of data). Edge Research backups do not extend FC market history.

### Git / writer archaeology

- `calc_market_forecast` in `app.py`: present by **2025-05**.
- Root `pattern_history.csv` created **2026-07-01**; first rows **2026-07-02** already include `market_real`,`market_forecast` plus forward `t1/t3/t5` columns (empty at write).
- `forecast_engine.py` created **2026-07-31**.
- Canonical `market_daily_t0` writer from **2026-08-13**.

---

## Date coverage table

| Period | Trading sessions (weekday w/ any persisted FC) | FC source | FC available | REAL/LIVE | 142-stock context | PIT confidence |
| --- | ---: | --- | --- | --- | --- | --- |
| 2026-06-25 → 2026-07-01 | 4 | buy_elite only | yes (scalar on elite rows) | REAL only | no | low (`NOT_PROVABLY_PIT_SAFE`) |
| 2026-07-02 → 2026-07-22 | ~15 | buy_elite + root PH | yes (many FC≡0 stretch) | REAL; no LIVE | partial boards only | low–medium |
| 2026-07-23 → 2026-08-06 | ~11 | + EL 142 boards but **FC null** in EL; EMS from 07-31 FC null | root/buy_elite FC; EMS recon possible from 07-31 | REAL in root/buy_elite; LIVE rare | EL/EMS 142 boards **without** persisted FC | board DNA high; FC medium (recon) |
| 2026-08-07 → 2026-08-12 | 5 | EL PH persisted FC + EMS recon | yes | REAL/LIVE still mostly null in EL | 142 | medium (`PIT_RECONSTRUCTABLE`) |
| 2026-08-13 → 2026-08-24 | 8 | MDT0 + freeze + EL + EMS | yes | REAL+LIVE | 142 | **high (`PIT_SAFE`)** |

### Exact weekday union (42) — persisted FC somewhere

See `EVIDENCE.json` → `union_weekday_dates`.

Gap in span: **2026-06-26** (Friday) missing between 06-25 and 06-29.

Root PH also contains **weekend** calendar dates (07-04/05, 07-11/12, …) — not trading sessions; exclude from Forecast calendars.

---

## Deep audit: `pattern_history.csv` (root)

- Rows: 33343; cols: 80; date col: `date`
- Unique calendar dates: 43; weekday: 34
- Universe/day: **7–133** (median ~64); **0 days at 142**
- FC: always non-null; **scalar intent** but **14 weekdays have multiple FC values** (intraday appends)
- Long stretch **2026-07-13→07-31** (and others) with **FC mode = 0.0**
- Market context: `market_real`, `market_regime`, `market_phase`, `breadth_score`; **no `market_live`**
- Stock features present: rsi14, rs5/10, obv, slopes, near_bottom_*, groups — usable for **partial breadth** on the subset present that day
- Forward columns `t1/t3/t5/t10_return` exist → **LEAKAGE_RISK** if included in T0 features (currently often empty, but schema is contaminated)
- **Recoverable:** market-level FC + REAL history (with asof/mode policy)  
- **Not recoverable as full Forecast T0:** no complete 142 board

EL `pattern_history.csv`: 142 symbols × 27 dates, but `market_forecast` null until **08-07**; REAL/LIVE from **08-13**.

---

## Recovery potential (no implementation)

| Tier | Sessions | How far back | Notes |
|---|---:|---|---|
| Safe COMPLETE Forecast T0 (142 + REAL + LIVE + FC) | **8** | 2026-08-13 | MDT0/freeze |
| PARTIAL Forecast T0 (142 + persisted FC, weak/no LIVE) | **12** | 2026-08-07 | EL PH |
| PARTIAL Forecast T0 (142 board + **reconstructed** FC) | **17** | 2026-07-31 | EMS; formula-version risk |
| Market-core historical schema (FC + REAL, not full 142 T0) | **~41–42** weekdays | **2026-06-25** | buy_elite ∪ root PH; feasibility **yes**, not implemented |
| ~1 month usable FC | **yes** | ~Jun 25–Aug 24 ≈ **2 months** calendar | quality uneven |
| ~3 months / 6+ months | **no** in this repo | — | no pre-2026-06-25 persisted FC files found |

**Historical core feature schema (feasibility only):**  
Preserve daily `trade_date`, `fc_value` (with `fc_source`, `fc_asof_rule`), `market_real`, optional `breadth_score`/`regime`, `universe_n`, `completeness`, provenance hash — **without** joining `t*_return` and without claiming 142 parity. Do **not** invent LIVE/foreign/ADV.

---

## Final verdict

### `FC_HISTORY_PARTIALLY_RECOVERABLE`

**Rationale:** Substantially more FC is persisted than the derived-layer **17** (back to **2026-06-25**, ~42 weekdays), but full PIT-safe 142-stock Forecast T0 remains short (**8 COMPLETE**, **12** with persisted FC on full board). EMS never stored FC values. No 3–6 month archive exists in-repo. Recovery of a **market-core** series is feasible; full feature-parity Forecast T0 for older dates is not.

**STOP** — audit only; no recovery code in this change set.
