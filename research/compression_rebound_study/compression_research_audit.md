# Compression Rebound Examiner Dataset — Audit

Extracted at: `2026-09-08T15:19:21Z` (UTC).
Status: **examiner dataset only**. Not an edge, not a production rule, not a discovery input.

## 0. Scientific constraints honored

- Production code, timers, services, Edge Research, genesis, Edge Memory, and BOT behavior were not modified.
- No historical artifact was regenerated or rewritten.
- No missing history was synthesized.
- No future field enters a T0 feature column.
- T3/T5/T10 are joined from already-stored production outcomes; they are labels, not features.
- Market DATE is the primary independent unit in preview C. Stock-days on the same date are not treated as independent market observations.
- No threshold (40%, 50%, RSI<40, etc.) was optimized.
- This hypothesis was not encoded as an ACTIVE edge and was not fed into autonomous discovery.

## 1. Inspection: what can be supplied exactly

| requested | status | notes |
|---|---|---|
| trade_date × ticker | **exact** | 142-symbol production universe from `observations.csv`; snapshot fill only where no observation/freeze row exists |
| production health state | **exact** | Evolution Health labels: ĐANG HỒI / TRUNG TÍNH / YẾU / YẾU DẦN / RẤT YẾU |
| previous 1–5 trading-day states | **examiner lag** | Backward shift of stored `health_group` on weekday rows |
| action group | **exact** | THEO DÕI / TÍCH LŨY / MUA EARLY / PULL VỪA / PULL ĐẸP / MUA BREAK / CP MẠNH / GÀ TĂNG TỐC |
| close | **exact stored `price`** | Used as close; no separate close column exists |
| open / high / low | **unavailable** | Not stored in any historical earning-learning / snapshot / group-evolution artifact |
| volume, vol_ma20, volume_ratio20 | **exact when stored** | Missing on weekend observation rows and before OBV backfill |
| RSI14, RS5, RS10 | **exact stored** | Not recomputed |
| EMA9, MA20 | **exact stored** | Missing on weekend observation rows |
| WMA45 | **unavailable** | Stock-level WMA45 is not stored. VNINDEX WMA45 column exists in market T0 schema but is 100% empty |
| OBV | **exact when stored** | Missing 2026-07-23..07-30 and weekend rows in observations |
| T3/T5/T10 return + maturity | **exact stored** | From `outcomes.csv` via `observation_id`. Snapshot-fill rows have no outcomes |
| VNINDEX close / return | **exact from 2026-08-13** | Canonical `market_daily_t0.csv`. 2026-08-28 is midday session only |
| Market Real / regime | **exact from 2026-08-13** | Earlier dates have `market_regime` text on weekday observations only; no Market Real |
| market transition | **unavailable** | Edge Research computes transition live; no historical store in earning-learning artifacts |
| breadth by health state | **not stored** | Preview A computes it from same-date stored states |
| breadth by action group | **exact from 2026-08-13** | `ga_tang_toc` … `theo_doi` in `market_daily_t0.csv` |
| foreign buy/sell/net | **unavailable** | No historical foreign-flow artifact |
| 2026-06-25 .. 2026-07-22 | **unavailable for this hypothesis** | `group_evolution_history.csv` has action groups + price/volume, not Evolution Health / RSI / RS |

## 2. What is unavailable

- Stock OHLC except stored `price` (treated as close).
- Stock WMA45.
- Foreign flow history.
- Historical market `transition` series.
- Evolution Health history before **2026-07-23**.
- Canonical daily Market T0 for **2026-08-28** (MIDDAY session snapshot only).
- Trading sessions **2026-08-31, 2026-09-01, 2026-09-02** in all inspected health/price panel artifacts (likely VN holiday window around 2 Sep). Not synthesized.
- True trading-session T+n that is independent of observation-row presence. Stored outcomes use **observation-row index**, including four weekend observation dates.

## 3. Expected / actual output size

- CSV rows: **4970** (one stock × date).
- Unique tickers: **142**.
- Unique dates: **35** (2026-07-23 … 2026-09-08).
- Weekday / trading-day rows: **4402**.
- Weekend observation rows retained (because production outcomes use them): **568**.
- Source mix: {'observations': 2698, 't0_freeze': 1992, 'snapshot_fill': 280}.
- File: `/workspace/research/compression_rebound_study/compression_stock_research.csv`.

## 4. Source artifacts used (read-only)

| artifact | role | coverage used |
|---|---|---|
| `data/earning_learning/observations.csv` | backbone stock×date; health/indicators/outcomes identity | 4690 rows, 2026-07-23..2026-09-08, 34 dates, 142 tickers |
| `data/earning_learning/t0_observation_freeze.csv` | **preferred T0 values** on overlap (first-write-wins PIT) | 1992 rows, 2026-08-13..2026-09-08 |
| `data/earning_learning/outcomes.csv` | stored T3/T5/T10 | 11514 rows; horizons 3/5/10 |
| `data/earning_money_snapshots.csv` | fill **only** missing stock×date (2026-08-26 full day; 2026-09-03 missing 138 names) | 3550 rows |
| `data/earning_learning/market_daily_t0.csv` | canonical VNINDEX + Market Real/regime + action-group breadth | 14 dates from 2026-08-13 |
| `data/earning_learning/market_t0_snapshot.csv` | 2026-08-28 MIDDAY VNINDEX/context only | 1 extra date |
| `group_evolution_history.csv` | inspected only; **not used as health panel** | 10914 rows from 2026-05-26; early window is action-group taxonomy |
| `app.py` / `modules/evolution_health.py` / `modules/earning_learning.py` | definition lookup only | no writes |

### Field → source map

| field | source | stored or derived |
|---|---|---|
| `health_group`, `health_score`, `action_group` | freeze if present else observations else snapshot | stored |
| `close` | stored `price` / snapshot `price` | stored, renamed |
| `rsi14`, `rs5`, `rs10`, `ema9`, `ma20`, `obv`, `volume`, `vol_ma20` | same priority | stored |
| `volume_ratio20`, `price_vs_ema9_pct`, `price_vs_ma20_pct` | stored; snapshot ratio may be volume/vol_ma20 if the stored ratio is empty | stored / identity fill |
| `state_lag1..5` | examiner backward shift of stored `health_group` on weekday rows | derived, PIT-safe |
| `t3/t5/t10_return` + status + target_date | `outcomes.csv` via `observation_id` | stored |
| `vnindex_*` | `market_daily_t0.csv` (canonical) or 2026-08-28 MIDDAY snapshot | stored |
| `market_real/regime/live/forecast` | canonical market daily when present, else freeze/obs row | stored |
| `ga_tang_toc` … `theo_doi` | `market_daily_t0.csv` action-group counts | stored |
| `open,high,low,wma45,foreign_*,market_transition` | none | **omitted from CSV** |
| `source_artifact`, `t0_priority`, `is_weekend`, `universe_n` | extractor metadata | derived |

## 5. Date coverage and incomplete universe

Panel dates: `2026-07-23, 2026-07-24, 2026-07-26, 2026-07-27, 2026-07-28, 2026-07-29, 2026-07-30, 2026-07-31, 2026-08-01, 2026-08-02, 2026-08-03, 2026-08-04, 2026-08-05, 2026-08-06, 2026-08-07, 2026-08-08, 2026-08-10, 2026-08-11, 2026-08-12, 2026-08-13, 2026-08-14, 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-20, 2026-08-21, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-08-28, 2026-09-03, 2026-09-04, 2026-09-07, 2026-09-08`.

After snapshot fill, every panel date has **142** tickers. Original observation/freeze coverage:

| date | original observation n | panel n after fill |
|---|---:|---:|
| 2026-08-26 | 0 | 142 |
| 2026-09-03 | 4 | 142 |

Only dates that were incomplete in `observations.csv` / freeze are listed above.

Weekend observation dates retained (health/price mostly copies of prior session, except 2026-08-08 which is **not** a copy):

- 2026-07-26 Sunday
- 2026-08-01 Saturday
- 2026-08-02 Sunday
- 2026-08-08 Saturday

Missing weekday sessions with **no** health panel in observations/freeze (not synthesized):

- 2026-08-26: full 142-row snapshot exists → included as `snapshot_fill`, no stored T3/T5/T10
- 2026-08-31, 2026-09-01, 2026-09-02: absent from observations, freeze, snapshots, and group-evolution

`group_evolution_history.csv` from 2026-06-25 through 2026-07-22: 2970 rows, 20 dates, 152 symbols (includes 10 non-current-universe names). Action groups only. Not included in the CSV.

## 6. Missingness in the extracted CSV

| field | missing % | nonempty | stored? |
|---|---:|---:|---|
| `health_group` | 0.0% | 4970 | from source artifacts / examiner lag |
| `close` | 0.0% | 4970 | from source artifacts / examiner lag |
| `volume` | 11.4% | 4402 | from source artifacts / examiner lag |
| `rsi14` | 0.0% | 4970 | from source artifacts / examiner lag |
| `rs5` | 0.0% | 4970 | from source artifacts / examiner lag |
| `rs10` | 0.0% | 4970 | from source artifacts / examiner lag |
| `ema9` | 11.4% | 4402 | from source artifacts / examiner lag |
| `ma20` | 11.4% | 4402 | from source artifacts / examiner lag |
| `obv` | 28.6% | 3550 | from source artifacts / examiner lag |
| `t3_return` | 14.2% | 4264 | from source artifacts / examiner lag |
| `t5_return` | 19.9% | 3980 | from source artifacts / examiner lag |
| `t10_return` | 34.2% | 3270 | from source artifacts / examiner lag |
| `vnindex_close` | 57.1% | 2130 | from source artifacts / examiner lag |
| `market_real` | 57.1% | 2130 | from source artifacts / examiner lag |
| `market_regime` | 14.3% | 4260 | from source artifacts / examiner lag |
| `state_lag1` | 2.9% | 4828 | from source artifacts / examiner lag |
| `state_lag5` | 17.1% | 4118 | from source artifacts / examiner lag |
| `open` | 100.0% | 0 | omitted from CSV; unavailable in historical artifacts |
| `high` | 100.0% | 0 | omitted from CSV; unavailable in historical artifacts |
| `low` | 100.0% | 0 | omitted from CSV; unavailable in historical artifacts |
| `wma45` | 100.0% | 0 | omitted from CSV; unavailable in historical artifacts |
| `market_transition` | 100.0% | 0 | omitted from CSV; unavailable in historical artifacts |
| `foreign_net` | 100.0% | 0 | omitted from CSV; unavailable in historical artifacts |

## 7. Stored vs recomputed

- **Not recomputed:** RSI14, RS5, RS10, EMA9, MA20, OBV, volume, health_group, Market Real, VNINDEX, T3/T5/T10.
- **Renamed only:** stored `price` → `close`.
- **Examiner derived (backward only):** `state_lag1..5`; preview B streak / RS-RSI deltas / close drawdowns.
- **Identity fill:** snapshot `volume_ratio20` empty → `volume/vol_ma20` when both stored. Not a new indicator definition.
- **No silent alternate definitions.**

## 8. Production definitions (as discoverable in code)

### 8.1 Evolution Health group / YẾU DẦN

Source: `modules/evolution_health.py` (`add_evolution_health`).

Composite score (0–100), rounded to 1 decimal:

- RS 24% + EMA 20% + OBV 18% + RSI 15% + volume 8% + position 9% + pattern 6%
- RS uses stored RS5/RS10; RSI uses stored RSI14 + `rsi_slope`; EMA uses `ema9_ma20_slope` and its 3-session change

Base buckets:

- ≥68 → 🌱 ĐANG HỒI
- 54–68 → 🟡 TRUNG TÍNH
- 40–54 → 🔴 YẾU
- 27–40 → ⚠️ YẾU DẦN
- <27 → ⛔ RẤT YẾU

Override: if `weakening` and score ∈ [27, 54) → ⚠️ YẾU DẦN.
`weakening` = at least 3 of: `ema9_ma20_slope<0`, `ema9_ma20_slope_change<0`, `rsi_slope<0`, `rs5<rs10`, `rs5<0`.

Therefore YẾU DẦN is **not** a pure “was strong, now compressed” label. It mixes low score and a 3-of-5 weakening vote. Distinguishing spring compression from structural weakness is **not** already encoded.

### 8.2 RS5 / RS10

Source: `app.py` indicator block:

```
rs5  = (close / close.shift(5)  - 1) * 100
rs10 = (close / close.shift(10) - 1) * 100
```

These are own-price percentage changes over 5/10 bars on the production OHLCV series, **not** vs VNINDEX. Stored values were copied; not recomputed here.

### 8.3 RSI14

Source: `app.py` `calc_rsi(close, period=14)`:

- Wilder-style EWM: `alpha = 1/14`, `adjust=False`
- `gain = clip(diff, lower=0)`, `loss = -clip(diff, upper=0)`
- `RSI = 100 - 100/(1 + avg_gain/avg_loss)`
- `fillna(50)` when undefined

Stored `rsi14` values were copied; not recomputed.

### 8.4 Forward T3 / T5 / T10

Source: `modules/earning_learning.py` `_build_outcomes`.

- Horizons `{3,5,10}`
- Per symbol, observations sorted by `trade_date`
- Target = observation row at `index + horizon` (**observation-row**, not a separately curated trading calendar)
- `return_pct = (target_price / entry_price - 1) * 100` using stored `price`
- `is_win` iff `return_pct > 0`
- A horizon is written only when that future observation row exists

Edge Research (`modules/edge_research/outcomes.py`) defines T+n as **trading-session** close-to-close. That path is **not** what is stored in `outcomes.csv`. This examiner file uses the stored earning-learning outcomes only.

Implication: four weekend observation dates sit in the observation index, so some stored T3/T5/T10 spans are “3 observation rows later” rather than “3 HOSE sessions later”. 2026-09-03 having only 4 observation rows also stretches later horizons for other names (T3 from 2026-08-25 often lands on 2026-09-04).

Maturity in this file: `MATURE` if that horizon exists in `outcomes.csv`; `WAITING` if the row has an `observation_id` but no stored horizon yet; `UNAVAILABLE` for snapshot-fill rows with no observation id.

Latest stored outcome entry_date: **2026-09-03**.

## 9. PIT / look-ahead / survivorship concerns

1. **Freeze vs later observations.** On 2026-08-13+, `t0_observation_freeze.csv` is first-write-wins by `observation_id`. Later `observations.csv` values can differ (health disagreed on 75 overlapping rows; 2026-08-28 is the worst drift). This extract **uses freeze values** on overlap. Example: 2026-08-28 observations were `recorded_at=2026-09-03T16:04:10Z` while freeze was `2026-08-28T05:43:21Z`. Using observations as T0 on that date would leak later information.
2. **Freeze clock is not always EOD.** Several freeze timestamps are morning/midday UTC+7, not EOD+3h. 2026-08-28 freeze is midday. Treat those T0 prints as “first captured that date”, not guaranteed official close.
3. **Weekend observation rows.** 2026-07-26 / 08-01 / 08-02 copy the prior session almost exactly. 2026-08-08 does not. Production outcomes still count them as rows. They are flagged `is_weekend=true`. Preview A/B/C use weekday rows only.
4. **2026-09-03 incomplete capture.** Only 4 observation/freeze names. Snapshot fill restores 142 health prints for breadth, but those 138 names have **no** stored T3/T5/T10.
5. **Survivorship.** Current `app.py` WATCHLIST is 142 names. `observations.csv` already matches that 142-set on every full date. `group_evolution_history.csv` earlier used 152–164 names (extra: AAA, BCM, DTD, ELC, FMC, LHG, PAC, PAN, VCS, YEG). Pre-2026-07-23 action-group history is a **different universe** and was not merged.
6. **Look-ahead into outcomes.** Outcome columns are future labels. Do not use them as T0 features.
7. **Same-date dependence.** All 142 names on one date share one market episode. Preview C therefore reports date-level medians, then the median across dates.
8. **No official trading calendar artifact.** Weekday ∩ stored panel is the working trading-day list. Holiday gaps are left as gaps.

## 10. Statistical preview A — state mix by date

Computed from weekday panel rows only. Percentages use that date’s available universe (`n`). Δ is versus the previous weekday panel date. No threshold is applied.

| date | wd | n | ĐANG HỒI % | Δ | TRUNG TÍNH % | Δ | YẾU % | Δ | YẾU DẦN % | Δ | RẤT YẾU % | Δ |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-07-23 | Thu | 142 | 2.8 | n/a | 2.8 | n/a | 1.4 | n/a | 38.7 | n/a | 54.2 | n/a |
| 2026-07-24 | Fri | 142 | 2.1 | -0.7 | 8.5 | 5.6 | 3.5 | 2.1 | 28.9 | -9.9 | 57.0 | 2.8 |
| 2026-07-27 | Mon | 142 | 2.1 | 0.0 | 5.6 | -2.8 | 2.8 | -0.7 | 38.0 | 9.2 | 51.4 | -5.6 |
| 2026-07-28 | Tue | 142 | 2.1 | 0.0 | 7.0 | 1.4 | 7.0 | 4.2 | 44.4 | 6.3 | 39.4 | -12.0 |
| 2026-07-29 | Wed | 142 | 10.6 | 8.5 | 28.2 | 21.1 | 14.1 | 7.0 | 38.7 | -5.6 | 8.5 | -31.0 |
| 2026-07-30 | Thu | 142 | 12.7 | 2.1 | 38.7 | 10.6 | 17.6 | 3.5 | 28.9 | -9.9 | 2.1 | -6.3 |
| 2026-07-31 | Fri | 142 | 17.6 | 4.9 | 24.6 | -14.1 | 21.8 | 4.2 | 34.5 | 5.6 | 1.4 | -0.7 |
| 2026-08-03 | Mon | 142 | 45.1 | 27.5 | 35.9 | 11.3 | 11.3 | -10.6 | 7.0 | -27.5 | 0.7 | -0.7 |
| 2026-08-04 | Tue | 142 | 50.0 | 4.9 | 26.1 | -9.9 | 13.4 | 2.1 | 9.9 | 2.8 | 0.7 | 0.0 |
| 2026-08-05 | Wed | 142 | 40.8 | -9.2 | 21.1 | -4.9 | 25.4 | 12.0 | 12.0 | 2.1 | 0.7 | 0.0 |
| 2026-08-06 | Thu | 142 | 29.6 | -11.3 | 29.6 | 8.5 | 10.6 | -14.8 | 28.2 | 16.2 | 2.1 | 1.4 |
| 2026-08-07 | Fri | 142 | 50.0 | 20.4 | 31.0 | 1.4 | 9.2 | -1.4 | 9.2 | -19.0 | 0.7 | -1.4 |
| 2026-08-10 | Mon | 142 | 52.1 | 2.1 | 29.6 | -1.4 | 8.5 | -0.7 | 9.2 | 0.0 | 0.7 | 0.0 |
| 2026-08-11 | Tue | 142 | 58.5 | 6.3 | 22.5 | -7.0 | 7.0 | -1.4 | 12.0 | 2.8 | 0.0 | -0.7 |
| 2026-08-12 | Wed | 142 | 56.3 | -2.1 | 21.8 | -0.7 | 14.1 | 7.0 | 7.7 | -4.2 | 0.0 | 0.0 |
| 2026-08-13 | Thu | 142 | 41.5 | -14.8 | 14.1 | -7.7 | 20.4 | 6.3 | 23.9 | 16.2 | 0.0 | 0.0 |
| 2026-08-14 | Fri | 142 | 25.4 | -16.2 | 13.4 | -0.7 | 14.8 | -5.6 | 45.1 | 21.1 | 1.4 | 1.4 |
| 2026-08-17 | Mon | 142 | 28.9 | 3.5 | 14.1 | 0.7 | 4.2 | -10.6 | 52.1 | 7.0 | 0.7 | -0.7 |
| 2026-08-18 | Tue | 142 | 25.4 | -3.5 | 20.4 | 6.3 | 4.2 | 0.0 | 49.3 | -2.8 | 0.7 | 0.0 |
| 2026-08-19 | Wed | 142 | 17.6 | -7.7 | 16.9 | -3.5 | 3.5 | -0.7 | 59.2 | 9.9 | 2.8 | 2.1 |
| 2026-08-20 | Thu | 142 | 16.9 | -0.7 | 23.2 | 6.3 | 4.2 | 0.7 | 52.1 | -7.0 | 3.5 | 0.7 |
| 2026-08-21 | Fri | 142 | 51.4 | 34.5 | 29.6 | 6.3 | 11.3 | 7.0 | 6.3 | -45.8 | 1.4 | -2.1 |
| 2026-08-24 | Mon | 142 | 58.5 | 7.0 | 22.5 | -7.0 | 12.0 | 0.7 | 7.0 | 0.7 | 0.0 | -1.4 |
| 2026-08-25 | Tue | 142 | 38.7 | -19.7 | 25.4 | 2.8 | 21.8 | 9.9 | 14.1 | 7.0 | 0.0 | 0.0 |
| 2026-08-26 | Wed | 142 | 48.6 | 9.9 | 23.2 | -2.1 | 12.7 | -9.2 | 15.5 | 1.4 | 0.0 | 0.0 |
| 2026-08-27 | Thu | 142 | 34.5 | -14.1 | 23.9 | 0.7 | 19.0 | 6.3 | 22.5 | 7.0 | 0.0 | 0.0 |
| 2026-08-28 | Fri | 142 | 26.1 | -8.5 | 40.1 | 16.2 | 7.0 | -12.0 | 26.1 | 3.5 | 0.7 | 0.7 |
| 2026-09-03 | Thu | 142 | 28.9 | 2.8 | 22.5 | -17.6 | 5.6 | -1.4 | 40.8 | 14.8 | 2.1 | 1.4 |
| 2026-09-04 | Fri | 142 | 21.1 | -7.7 | 24.6 | 2.1 | 5.6 | 0.0 | 47.9 | 7.0 | 0.7 | -1.4 |
| 2026-09-07 | Mon | 142 | 14.1 | -7.0 | 16.9 | -7.7 | 3.5 | -2.1 | 62.7 | 14.8 | 2.8 | 2.1 |
| 2026-09-08 | Tue | 142 | 19.0 | 4.9 | 16.9 | 0.0 | 4.2 | 0.7 | 57.7 | -4.9 | 2.1 | -0.7 |

Largest weekday expansions in % YẾU DẦN (descriptive, not a detector):

- 2026-08-14: YẾU DẦN 45.1% (Δ 21.1 pp), n=142
- 2026-08-06: YẾU DẦN 28.2% (Δ 16.2 pp), n=142
- 2026-08-13: YẾU DẦN 23.9% (Δ 16.2 pp), n=142
- 2026-09-07: YẾU DẦN 62.7% (Δ 14.8 pp), n=142
- 2026-09-03: YẾU DẦN 40.8% (Δ 14.8 pp), n=142

## 11. Statistical preview B — YẾU DẦN rows (weekday only)

Weekday YẾU DẦN stock-days: **1320**. These are **not** independent market observations.

### Streak length (consecutive weekday YẾU DẦN including T0)

| streak | n |
|---:|---:|
| 1 | 552 |
| 2 | 310 |
| 3 | 186 |
| 4 | 117 |
| 5 | 63 |
| 6 | 35 |
| 7 | 16 |
| 8 | 11 |
| 9 | 7 |
| 10 | 7 |
| 11 | 6 |
| 12 | 4 |
| 13 | 4 |
| 14 | 2 |

### Previous weekday state

| previous state | n |
|---|---:|
| ⚠️ YẾU DẦN | 768 |
| 🟡 TRUNG TÍNH | 185 |
| 🔴 YẾU | 138 |
| ⛔ RẤT YẾU | 108 |
| 🌱 ĐANG HỒI | 66 |
| (none/first) | 55 |

### Stored-indicator changes vs 1/3/5 weekday rows earlier

| series | vs 1d | vs 3d | vs 5d |
|---|---|---|---|
| RS5 | n=1265 median=-0.46 p25=-1.89 p75=0.96 | n=1170 median=-1.78 p25=-4.33 p75=0.90 | n=1052 median=-3.22 p25=-5.92 p75=-0.35 |
| RS10 | n=1265 median=-0.25 p25=-1.67 p75=0.97 | n=1170 median=-1.09 p25=-4.24 p75=1.39 | n=1052 median=-1.82 p25=-6.49 p75=1.38 |
| RSI14 | n=1265 median=-1.00 p25=-2.98 p75=0.70 | n=1170 median=-3.18 p25=-6.73 p75=0.31 | n=1052 median=-5.31 p25=-9.28 p75=-0.96 |

### Close drawdown from prior 5/10 weekday highs (examiner, from stored close)

- vs prior 5-day high: n=1265 median=-2.82 p25=-4.19 p75=-1.62
- vs prior 10-day high: n=1265 median=-3.68 p25=-5.18 p75=-2.17

### Volume vs stored 20-day average, distance to stored EMA9/MA20

- `volume_ratio20`: n=1320 median=0.79 p25=0.57 p75=1.10
- `price_vs_ema9_pct`: n=1320 median=-1.44 p25=-2.24 p75=-0.80
- `price_vs_ma20_pct`: n=1320 median=-2.12 p25=-4.44 p75=-0.71
- distance to WMA45: **unavailable**

Previous-state mix shows many YẾU DẦN prints follow YẾU / YẾU DẦN / RẤT YẾU, not only former ĐANG HỒI. That is relevant to the “good spring vs falling knife” question and is left un-tuned.

## 12. Statistical preview C — mature T3/T5/T10, date as unit

Only weekday rows with already-stored mature outcomes. Each date contributes one median per state. Stock-days on the same date are collapsed first.

### T3 (MATURE)

| date | n_mature | n YẾU DẦN | med T3 ĐANG HỒI | med TRUNG TÍNH | med YẾU | med YẾU DẦN | med RẤT YẾU |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-07-23 | 142 | 55 | -0.33 | -1.79 | -2.50 | -1.88 | -2.36 |
| 2026-07-24 | 142 | 41 | -1.63 | -1.07 | -3.30 | -1.40 | -1.61 |
| 2026-07-27 | 142 | 54 | -1.38 | 2.40 | 2.26 | 3.26 | 4.07 |
| 2026-07-28 | 142 | 63 | 1.00 | 1.13 | 1.72 | 2.31 | 2.52 |
| 2026-07-29 | 142 | 55 | -0.33 | 0.30 | 0.14 | 0.00 | 0.71 |
| 2026-07-30 | 142 | 41 | 0.21 | -0.37 | -0.48 | -0.43 | 1.22 |
| 2026-07-31 | 142 | 49 | 1.36 | 2.19 | 1.84 | 2.33 | 6.60 |
| 2026-08-03 | 142 | 10 | 0.00 | -0.42 | -0.16 | -0.60 | -4.90 |
| 2026-08-04 | 142 | 14 | -0.30 | -0.41 | 0.84 | 0.38 | -5.63 |
| 2026-08-05 | 142 | 17 | -0.45 | 0.33 | 0.30 | 0.37 | -4.29 |
| 2026-08-06 | 142 | 40 | 1.48 | 1.52 | 1.18 | 2.22 | 1.82 |
| 2026-08-07 | 142 | 13 | 0.00 | 0.61 | 0.83 | 0.91 | 2.24 |
| 2026-08-10 | 142 | 13 | -0.98 | -1.74 | -1.50 | -0.70 | 0.00 |
| 2026-08-11 | 142 | 17 | -2.19 | -1.48 | -3.11 | -1.27 | n/a |
| 2026-08-12 | 142 | 11 | -2.17 | -2.43 | -2.60 | -2.10 | n/a |
| 2026-08-13 | 142 | 34 | -1.16 | -1.02 | -1.11 | -1.51 | n/a |
| 2026-08-14 | 142 | 64 | -0.33 | -1.69 | -1.49 | -0.66 | -0.86 |
| 2026-08-17 | 142 | 74 | -1.26 | -0.12 | -1.64 | -0.82 | -1.53 |
| 2026-08-18 | 142 | 70 | 0.28 | 2.28 | 2.49 | 1.88 | 2.35 |
| 2026-08-19 | 142 | 84 | 1.58 | 2.27 | 5.42 | 3.39 | 4.67 |
| 2026-08-20 | 142 | 74 | 0.51 | 1.74 | 0.55 | 2.85 | 4.65 |
| 2026-08-21 | 142 | 9 | 0.35 | -0.30 | 0.10 | 0.35 | 1.35 |
| 2026-08-24 | 142 | 10 | -1.24 | -0.44 | -1.22 | -0.86 | n/a |
| 2026-08-25 | 142 | 20 | -0.84 | -0.51 | -0.32 | -1.24 | n/a |
| 2026-08-27 | 142 | 32 | -2.57 | -2.93 | -2.17 | -0.82 | n/a |
| 2026-08-28 | 142 | 37 | -0.88 | -1.08 | -0.91 | -0.81 | 2.46 |
| 2026-09-03 | 4 | 1 | n/a | 0.46 | -2.68 | -1.23 | n/a |

Cross-date median of **date-level medians** (not pooled stock-days): ĐANG HỒI -0.33; TRUNG TÍNH -0.37; YẾU -0.32; YẾU DẦN -0.60; RẤT YẾU 1.29. N_dates=27.

On 26 T3 dates with n_mature≥130 (or all dates if none qualify), median(date-median YẾU DẦN − date-median RẤT YẾU) = -0.59; median(date-median YẾU DẦN − date-median YẾU) = 0.43. This is descriptive only. No threshold was tuned.

### T5 (MATURE)

| date | n_mature | n YẾU DẦN | med T5 ĐANG HỒI | med TRUNG TÍNH | med YẾU | med YẾU DẦN | med RẤT YẾU |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-07-23 | 142 | 55 | 1.06 | -0.99 | 0.49 | 0.27 | 0.00 |
| 2026-07-24 | 142 | 41 | 0.77 | 0.51 | -0.72 | 0.65 | 1.26 |
| 2026-07-27 | 142 | 54 | -1.38 | 1.98 | 2.02 | 2.90 | 3.45 |
| 2026-07-28 | 142 | 63 | 1.00 | 1.13 | 1.72 | 2.31 | 2.52 |
| 2026-07-29 | 142 | 55 | 0.66 | 1.97 | 2.47 | 2.98 | 3.49 |
| 2026-07-30 | 142 | 41 | 1.75 | 2.03 | 3.26 | 3.01 | 1.84 |
| 2026-07-31 | 142 | 49 | 0.80 | 2.42 | 1.45 | 1.79 | 10.30 |
| 2026-08-03 | 142 | 10 | -0.34 | -0.20 | 0.17 | 0.00 | -6.29 |
| 2026-08-04 | 142 | 14 | 0.50 | 1.27 | 0.89 | 1.40 | -4.93 |
| 2026-08-05 | 142 | 17 | 1.26 | 1.89 | 1.93 | 1.90 | -2.14 |
| 2026-08-06 | 142 | 40 | 1.04 | 1.41 | 1.04 | 2.32 | 5.45 |
| 2026-08-07 | 142 | 13 | -1.30 | -0.49 | -1.03 | -0.12 | 0.75 |
| 2026-08-10 | 142 | 13 | -2.07 | -1.60 | -3.08 | -2.51 | -2.96 |
| 2026-08-11 | 142 | 17 | -2.07 | -2.64 | -3.37 | -2.80 | n/a |
| 2026-08-12 | 142 | 11 | -2.47 | -2.74 | -3.26 | -3.12 | n/a |
| 2026-08-13 | 142 | 34 | -1.76 | -1.16 | -1.78 | -2.64 | n/a |
| 2026-08-14 | 142 | 64 | 1.35 | 1.07 | 1.28 | 2.45 | 0.38 |
| 2026-08-17 | 142 | 74 | 1.77 | 2.17 | 2.06 | 2.74 | -0.76 |
| 2026-08-18 | 142 | 70 | 0.00 | 1.94 | 2.51 | 2.32 | 1.47 |
| 2026-08-19 | 142 | 84 | 0.72 | 2.13 | 5.72 | 3.46 | 2.42 |
| 2026-08-20 | 142 | 74 | 0.79 | 1.50 | 1.08 | 1.86 | 1.55 |
| 2026-08-21 | 142 | 9 | -0.37 | -1.45 | -0.96 | -1.03 | -2.17 |
| 2026-08-24 | 142 | 10 | -2.66 | -1.09 | -2.59 | -2.50 | n/a |
| 2026-08-25 | 142 | 20 | -2.16 | -2.12 | -1.38 | -2.35 | n/a |
| 2026-08-27 | 4 | 2 | -5.38 | n/a | n/a | 1.82 | n/a |

Cross-date median of **date-level medians** (not pooled stock-days): ĐANG HỒI 0.50; TRUNG TÍNH 1.10; YẾU 0.96; YẾU DẦN 1.79; RẤT YẾU 1.26. N_dates=25.

On 24 T5 dates with n_mature≥130 (or all dates if none qualify), median(date-median YẾU DẦN − date-median RẤT YẾU) = 0.45; median(date-median YẾU DẦN − date-median YẾU) = 0.42. This is descriptive only. No threshold was tuned.

### T10 (MATURE)

| date | n_mature | n YẾU DẦN | med T10 ĐANG HỒI | med TRUNG TÍNH | med YẾU | med YẾU DẦN | med RẤT YẾU |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-07-23 | 142 | 55 | -0.05 | -0.39 | 1.68 | 1.87 | 2.84 |
| 2026-07-24 | 142 | 41 | 1.09 | 0.83 | 1.44 | 2.31 | 4.57 |
| 2026-07-27 | 142 | 54 | 1.38 | 1.48 | 1.27 | 4.16 | 6.25 |
| 2026-07-28 | 142 | 63 | 2.82 | 0.86 | 3.90 | 5.97 | 6.86 |
| 2026-07-29 | 142 | 55 | 1.31 | 1.01 | 2.31 | 2.41 | 4.49 |
| 2026-07-30 | 142 | 41 | 3.50 | 2.92 | 4.87 | 4.20 | 0.91 |
| 2026-07-31 | 142 | 49 | 2.27 | 3.69 | 3.41 | 4.52 | 7.24 |
| 2026-08-03 | 142 | 10 | -0.29 | 0.00 | 0.57 | -1.00 | -8.39 |
| 2026-08-04 | 142 | 14 | -1.47 | -1.56 | -2.06 | -0.07 | -7.75 |
| 2026-08-05 | 142 | 17 | -0.94 | -0.42 | -0.94 | -0.54 | -5.71 |
| 2026-08-06 | 142 | 40 | -1.77 | -1.55 | -2.68 | -0.76 | 0.00 |
| 2026-08-07 | 142 | 13 | -2.65 | -2.20 | -2.35 | -3.75 | -3.73 |
| 2026-08-10 | 142 | 13 | -0.24 | 0.66 | 0.00 | 0.00 | -3.70 |
| 2026-08-11 | 142 | 17 | -0.57 | 0.07 | -2.00 | -0.89 | n/a |
| 2026-08-12 | 142 | 11 | 0.39 | -0.81 | -0.15 | -2.21 | n/a |
| 2026-08-13 | 142 | 34 | -0.65 | 0.09 | 0.63 | 1.81 | n/a |
| 2026-08-14 | 142 | 64 | -0.01 | 0.00 | -0.36 | 1.26 | 12.37 |
| 2026-08-17 | 142 | 74 | 0.00 | -0.13 | -3.19 | 0.00 | -4.58 |
| 2026-08-18 | 142 | 70 | -0.68 | -0.41 | 1.72 | 0.21 | -1.47 |
| 2026-08-19 | 4 | 3 | n/a | -4.58 | n/a | 0.14 | n/a |

Cross-date median of **date-level medians** (not pooled stock-days): ĐANG HỒI -0.05; TRUNG TÍNH 0.00; YẾU 0.57; YẾU DẦN 0.17; RẤT YẾU 0.46. N_dates=20.

On 19 T10 dates with n_mature≥130 (or all dates if none qualify), median(date-median YẾU DẦN − date-median RẤT YẾU) = -0.39; median(date-median YẾU DẦN − date-median YẾU) = 0.87. This is descriptive only. No threshold was tuned.

### Waiting / unavailable

- T3: {'MATURE': 4264, 'WAITING': 426, 'UNAVAILABLE': 280}
- T5: {'MATURE': 3980, 'WAITING': 710, 'UNAVAILABLE': 280}
- T10: {'MATURE': 3270, 'WAITING': 1420, 'UNAVAILABLE': 280}

Do not read any median gap as a tradable edge. Sample of market dates is small. Weekend-row outcome semantics and 2026-09-03 incompleteness remain unresolved data issues.

## 13. How not to use this file

- Do not add it to Edge Memory / ACTIVE edges / autonomous discovery.
- Do not optimize cutoffs on % YẾU DẦN, RSI, RS, or streak.
- Do not treat 142 names on one date as 142 independent trials.
- Do not drop `t0_priority` / `is_weekend` / `universe_n` when studying breadth episodes.

## 14. Clean trading-session T3/T5/T10 (examiner overlay)

Appended at: `2026-09-08T15:28:23Z` (UTC).
Status: **examiner overlay only**. Production `t3/t5/t10_*` columns are unchanged.
No threshold was tuned. No hypothesis test. No trading rule. No production write.

### 14.1 File

- `/workspace/research/compression_rebound_study/compression_stock_research_clean_outcomes.csv`
- Rows: **4970** (same identity as `compression_stock_research.csv`)
- Added columns: `clean_T3_date`, `clean_T3_return`, `clean_T3_status`, and the T5/T10 analogues

### 14.2 Definition

- T0 = the row’s `trade_date` **only if** that date is an eligible HOSE/HNX session
- T+n = the **nth eligible trading session after T0**
- Raw return = `close(T+n) / close(T0) - 1`
- `clean_T*_return` is stored as **percentage points** (`× 100`) so it sits beside production `t*_return`
- If T0 is not an eligible session (weekend observation row): all clean horizons = `UNAVAILABLE`
- If T+n session exists in the confirmed calendar but that ticker’s close is missing: `UNAVAILABLE` (no jump to another date)
- If T+n falls after the last confirmed stored session (**2026-09-08**): `WAITING` (date may be a weekday projection; return is empty)

### 14.3 Trading calendar source / derivation

There is **no official HOSE calendar artifact** in the repo. The examiner calendar is derived, not inferred from observation rows alone.

A date is an **eligible session** only if all of the following hold:

1. It is Monday–Friday.
2. It is **not** in the 2026 National Day non-trading window `2026-08-31`, `2026-09-01`, `2026-09-02`.
3. It has **independent session evidence** from at least one stored price/market artifact:
   - `group_evolution_history.csv` with a non-null `price`
   - `data/earning_money_snapshots.csv`
   - `data/earning_learning/market_daily_t0.csv`
   - `data/earning_learning/market_t0_snapshot.csv` with a VNINDEX close
   - weekday `observations.csv` rows that also store `volume` (weekend observation rows are ignored even if they exist)

Observation-row presence **alone** is not enough. That is why `2026-07-26`, `2026-08-01`, `2026-08-02`, and `2026-08-08` are excluded.

**National Day:** 2 Sep 2026 is Vietnam’s Quốc khánh. Across `observations`, freeze, snapshots, group-evolution, and market T0, those three weekdays have **zero** stored session prints. They are treated as the exchange holiday window. They are not synthesized as sessions.

**2026-08-26** is kept. It is a Wednesday. `observations` / group-evolution missed it, but `earning_money_snapshots.csv` has 142 names whose prices/volumes differ from 2026-08-25 and 2026-08-27 (120/142 prices changed vs 25 Aug). That is treated as a real session, not a holiday.

Confirmed eligible sessions used for MATURE closes:

`2026-07-23, 2026-07-24, 2026-07-27, 2026-07-28, 2026-07-29, 2026-07-30, 2026-07-31, 2026-08-03, 2026-08-04, 2026-08-05, 2026-08-06, 2026-08-07, 2026-08-10, 2026-08-11, 2026-08-12, 2026-08-13, 2026-08-14, 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-20, 2026-08-21, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-08-28, 2026-09-03, 2026-09-04, 2026-09-07, 2026-09-08`

Evidence table for the study window:

| date | wd | weekend | ND window | gev px | snap | mkt daily | VNINDEX sess | wd obs+vol | eligible |
|---|---|---|---|---|---|---|---|---|---|
| 2026-07-23 | Thu |  |  | Y |  |  |  | Y | YES |
| 2026-07-24 | Fri |  |  | Y |  |  |  | Y | YES |
| 2026-07-25 | Sat | Y |  |  |  |  |  |  |  |
| 2026-07-26 | Sun | Y |  |  |  |  |  |  |  |
| 2026-07-27 | Mon |  |  | Y |  |  |  | Y | YES |
| 2026-07-28 | Tue |  |  | Y |  |  |  | Y | YES |
| 2026-07-29 | Wed |  |  | Y |  |  |  | Y | YES |
| 2026-07-30 | Thu |  |  | Y |  |  |  | Y | YES |
| 2026-07-31 | Fri |  |  | Y | Y |  |  | Y | YES |
| 2026-08-01 | Sat | Y |  |  |  |  |  |  |  |
| 2026-08-02 | Sun | Y |  |  |  |  |  |  |  |
| 2026-08-03 | Mon |  |  | Y | Y |  |  | Y | YES |
| 2026-08-04 | Tue |  |  | Y | Y |  |  | Y | YES |
| 2026-08-05 | Wed |  |  | Y | Y |  |  | Y | YES |
| 2026-08-06 | Thu |  |  | Y | Y |  |  | Y | YES |
| 2026-08-07 | Fri |  |  | Y | Y |  |  | Y | YES |
| 2026-08-08 | Sat | Y |  |  |  |  |  |  |  |
| 2026-08-09 | Sun | Y |  |  |  |  |  |  |  |
| 2026-08-10 | Mon |  |  | Y | Y |  |  | Y | YES |
| 2026-08-11 | Tue |  |  | Y | Y |  |  | Y | YES |
| 2026-08-12 | Wed |  |  | Y | Y |  |  | Y | YES |
| 2026-08-13 | Thu |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-14 | Fri |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-15 | Sat | Y |  |  |  |  |  |  |  |
| 2026-08-16 | Sun | Y |  |  |  |  |  |  |  |
| 2026-08-17 | Mon |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-18 | Tue |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-19 | Wed |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-20 | Thu |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-21 | Fri |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-22 | Sat | Y |  |  |  |  |  |  |  |
| 2026-08-23 | Sun | Y |  |  |  |  |  |  |  |
| 2026-08-24 | Mon |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-25 | Tue |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-26 | Wed |  |  |  | Y |  |  |  | YES |
| 2026-08-27 | Thu |  |  | Y | Y | Y | Y | Y | YES |
| 2026-08-28 | Fri |  |  | Y | Y |  | Y | Y | YES |
| 2026-08-29 | Sat | Y |  |  |  |  |  |  |  |
| 2026-08-30 | Sun | Y |  |  |  |  |  |  |  |
| 2026-08-31 | Mon |  | Y |  |  |  |  |  |  |
| 2026-09-01 | Tue |  | Y |  |  |  |  |  |  |
| 2026-09-02 | Wed |  | Y |  |  |  |  |  |  |
| 2026-09-03 | Thu |  |  | Y | Y | Y | Y | Y | YES |
| 2026-09-04 | Fri |  |  | Y | Y | Y | Y | Y | YES |
| 2026-09-05 | Sat | Y |  |  |  |  |  |  |  |
| 2026-09-06 | Sun | Y |  |  |  |  |  |  |  |
| 2026-09-07 | Mon |  |  | Y | Y | Y | Y | Y | YES |
| 2026-09-08 | Tue |  |  | Y | Y | Y | Y | Y | YES |

Closes used for clean returns are the stored `close` values already on the examiner panel for that ticker × eligible session (freeze > observations > snapshot fill). No close was recomputed or interpolated.

### 14.4 Production vs clean comparison

Comparable row = production status `MATURE` **and** clean status `MATURE`. Date comparison uses production `t*_target_date` vs `clean_T*_date`. Return difference is absolute percentage-point gap.

| horizon | prod MATURE | clean MATURE | prod WAITING | clean WAITING | prod UNAVAIL | clean UNAVAIL | comparable | target date differs | date-diff % | mean\|Δret\| | median\|Δret\| |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T3 | 4264 | 3976 | 426 | 426 | 280 | 568 | 3696 | 1838 | 49.7 | 0.9531 | 0.0000 |
| T5 | 3980 | 3692 | 710 | 710 | 280 | 568 | 3412 | 2414 | 70.8 | 1.3161 | 0.6711 |
| T10 | 3270 | 2982 | 1420 | 1420 | 280 | 568 | 2702 | 2418 | 89.5 | 1.6841 | 1.0401 |

Maturity-date differences (clean vs production):

- T3: clean has -288 MATURE rows vs production (3976 vs 4264). Clean WAITING=426 (production 426); clean UNAVAILABLE=568 (production 280).
- T5: clean has -288 MATURE rows vs production (3692 vs 3980). Clean WAITING=710 (production 710); clean UNAVAILABLE=568 (production 280).
- T10: clean has -288 MATURE rows vs production (2982 vs 3270). Clean WAITING=1420 (production 1420); clean UNAVAILABLE=568 (production 280).

T0 dates with the most production-vs-clean **target date** mismatches among comparable rows:

- T3: 2026-07-23: 142 rows, 2026-07-24: 142 rows, 2026-07-29: 142 rows, 2026-07-30: 142 rows, 2026-07-31: 142 rows, 2026-08-05: 142 rows, 2026-08-06: 142 rows, 2026-08-07: 142 rows
- T5: 2026-07-23: 142 rows, 2026-07-24: 142 rows, 2026-07-27: 142 rows, 2026-07-28: 142 rows, 2026-07-29: 142 rows, 2026-07-30: 142 rows, 2026-07-31: 142 rows, 2026-08-03: 142 rows
- T10: 2026-07-23: 142 rows, 2026-07-24: 142 rows, 2026-07-27: 142 rows, 2026-07-28: 142 rows, 2026-07-29: 142 rows, 2026-07-30: 142 rows, 2026-07-31: 142 rows, 2026-08-03: 142 rows

### 14.5 Dates most affected by weekend / holiday observation rows

Weekend T0 rows (`is_weekend=true`) are **not** eligible sessions. Clean T3/T5/T10 on those rows are `UNAVAILABLE`. Production still treats them as observation-index T0.

- Weekend T0 rows in the panel: **568** (4 dates × 142 names).
- Weekend T0 dates: `2026-07-26`, `2026-08-01`, `2026-08-02`, `2026-08-08`.
- National Day window skipped by the clean calendar: `2026-08-31`, `2026-09-01`, `2026-09-02`.
- Capture hole that **is** a session: `2026-08-26` (in clean calendar via snapshots; absent from production observation index).
- Capture hole that stretches production T+n: `2026-09-03` has only 4 observation rows, so production often jumps from `2026-08-28` to `2026-09-04` for the other 138 names. Clean T+1 after `2026-08-28` is `2026-09-03` for every name that has a stored close that day.

Worked examples (not a rule):

- ACB 2026-08-08: prod T3 MATURE date=2026-08-12 ret=1.562; clean T3 UNAVAILABLE date=nan ret=n/a  ← Saturday observation T0
- ACB 2026-08-25: prod T3 MATURE date=2026-09-04 ret=0.000; clean T3 MATURE date=2026-08-28 ret=1.126  ← production skips 2026-08-26
- ACB 2026-08-28: prod T3 MATURE date=2026-09-08 ret=0.450; clean T3 MATURE date=2026-09-07 ret=-0.891  ← National Day + 09-03 observation hole
- ACB 2026-08-26: prod T3 UNAVAILABLE date=nan ret=n/a; clean T3 MATURE date=2026-09-03 ret=-0.225  ← snapshot-only session; production has no observation_id

Use this overlay only to see how much the observation-row T+n clock differs from a session clock. Do not encode the difference as an edge.
