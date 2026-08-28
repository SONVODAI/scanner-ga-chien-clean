# Forecast Market History — Forensic Audit

**Audit ID:** `forecast_market_history_forensic_audit_v1`  
**Mode:** READ-ONLY (diagnostics artifacts only)  
**Verdict:** `MARKET_HISTORY_PARTIALLY_SUFFICIENT_KEEP_COLLECTING`

---

## Executive summary

There **is** more historical MARKET information than the 17 EMS / Forecast-T0 sessions — chiefly in root `pattern_history.csv` and `buy_elite_learning_history.csv` — but it is **not** three months of Forecast-compatible 142-stock T0.

| History class | Sessions | Span | ≥1m | ≥2m | ≥3m | ≥6m |
|---------------|----------|------|-----|-----|-----|-----|
| **A. Market Core** (FC/REAL ± regime) | **42** weekdays | 2026-06-25 → 2026-08-24 | YES | YES | **NO** | NO |
| **B. Rich Market** | **38** | ~Jul 2 → Aug 24 | YES | NO | NO | NO |
| **C. Full 142 Forecast-compatible** | **17** | 2026-07-31 → 2026-08-24 | NO | NO | NO | NO |
| **D. Outcome-matured (market T3)** | **14** (T5=12, T10=7) | from EMS calendar | NO | NO | NO | NO |

**Plain answer to the operator’s core question:**  
`pattern_history.csv` contains **~1.7 months / 43 sessions** of useful **Market Core** (FC+REAL on every date, after-close selectable on 40/43 days) — **not ≥3 months**, and **not** full-142 Forecast T0 (median ~64 symbols/day; only 2 days ≥130).

---

## 1. Global inventory

See `SOURCE_INVENTORY.csv` for machine-readable detail.

### Canonical vs duplicate

| Path | Role | Canonical? | First→Last | Unique dates | Rows | Notes |
|------|------|------------|------------|--------------|------|-------|
| `pattern_history.csv` | Root scan archive | **YES** (Market Core long series) | 2026-07-02→08-24 | 43 | 33,343 | FC+REAL all dates; multi-scan; outcome cols **empty** |
| `data/earning_learning/pattern_history.csv` | EL append history | YES (EL) | 2026-07-23→08-24 | 27 | 16,149 | Joined outcome targets → leakage if misused as T0 |
| `data/earning_money_snapshots.csv` | 142 board | **YES** | 2026-07-31→08-24 | 17 | 2,414 | Exact 142/day; market scalars **null** in workspace (FC reconstructed from groups) |
| `data/earning_learning/market_daily_t0.csv` | Canonical MDT0 | **YES** | 2026-08-13→08-24 | 8 | 8 | FC/REAL/LIVE/breadth/VNI OHLCV |
| `market_t0_snapshot.csv` | Near-duplicate MDT0 | NO (derived) | same | 8–9 | 9 | Do not double-count |
| `t0_observation_freeze.csv` | Stock T0 freeze | YES | 2026-08-13→08-24 | 8 | 1,136 | Sector present |
| `buy_elite_learning_history.csv` | Elite subset | YES (subset only) | 2026-06-25→08-24 | 41 | 749 | Earliest FC; **not** universe-representative |
| `observations.csv` / `outcomes.csv` | EL stock obs/labels | YES | 2026-07-23→… | 27 / 24 | 3,834 / 8,946 | Stock-level, not market Forecast outcomes |
| `pattern_lifecycle.csv` / `pattern_snapshot.csv` | Derived joins | NO | — | — | — | Do not count as independent history |
| `forecast_t0_daily.csv` | Immutable Forecast T0 | **YES** | 2026-07-31→08-24 | 17 | 17 | Schema-complete |
| `forecast_outcomes.csv` | Market T3/T5/T10 | **YES** | matured subset | 14/12/7 | 33 | Separate label layer |
| `historical_market_core.csv` | Recovered FC core | YES | 2026-06-25→08-24 | 42 | 42 | Mixed quality tiers |
| `mdrr_daily.csv` / `p0_market_daily.csv` | MDRR / P0 | YES | 17 each | 17 | — | Forward memory |

**No parquet Camera bars** present in this workspace; VPS may differ.

---

## 2. Deep audit — all `pattern_history`

### Root `pattern_history.csv`

| Metric | Value |
|--------|-------|
| Rows / cols | 33,343 / 80 |
| Date range | 2026-07-02 → 2026-08-24 (**43** dates, ~**1.7** months) |
| Symbols/day | min 7, median **64**, max 133; ≥130 on **2** days; ≥100 on **12** |
| FC present | **43/43** dates |
| REAL present | **43/43** |
| Multi-FC within date | **14** dates (intraday scans) |
| LIVE scalar | No `market_live` column; has `live_source` / `live_ts` / `is_live_adjusted` |
| breadth_score | Column exists, **100% null** |
| Regime / phase | Present as text fields |
| Group coverage | Typically 2–4 of 8 groups (not full EMS distribution) |
| Technicals | rsi14, slopes, OBV, volume — yes |
| T1/T3/T5/T10 return cols | Present in schema, **100% null** (safe to ignore as labels; strip if extracting T0) |
| Timestamps | `time` always present (541 unique); last scan ≥15:00 on **40/43** dates |
| AFTER_CLOSE selection | **Yes, reconstructable:** last scan with `time ≥ 15:00` yields unique FC mode on recent dates |
| Writer | `pattern_manager.write_pattern_history` — **full CSV rewrite** (retention risk) |
| PIT class | `LEAKAGE_RISK_SOURCE` (multi-FC + outcome schema) but T0 fields **extractable** if labels excluded and after-close rule applied → usable as `PIT_RECONSTRUCTABLE` Market Core |
| 142 DNA | **No** (except near-miss 131–133 on 2 days) |

### `data/earning_learning/pattern_history.csv`

| Metric | Value |
|--------|-------|
| Dates | 27 (2026-07-23 → 08-24) |
| Overlap with root | 22; EL-only: Aug 8,13,14,17,18; root-only: most of early July |
| Outcomes | Embedded `t3/t5/t10_target_*` — **LEAKAGE_RISK** if used as features |
| Sector | Yes |

### Explicit answers

1. **Does `pattern_history.csv` contain ≥3 months of useful MARKET history?**  
   **No.** ~1.7 months / 43 sessions of Market Core (FC+REAL). Useful: **yes, partially**. Three months: **no**.

2. **Does it contain ≥3 months of full 142-stock Forecast T0?**  
   **No.** Essentially never 142; only 2 days near-full.

These are **separate concepts** — Market Core ≠ Forecast T0.

---

## 3. True market-history timeline

Full matrix: `SESSION_COVERAGE_MATRIX.csv` (52 calendar dates / 42 weekdays).

Highlights:

- **Earliest:** 2026-06-25 (buy elite FC)  
- **FC weekdays:** 42 with only **1** gap (`2026-06-26`)  
- **LIVE / breadth:** essentially MDT0 window (8 sessions from 2026-08-13)  
- **Full 142 + foreign + VNI tech:** P0/EMS from 2026-07-31 (17 sessions)  
- **Market outcomes:** Forecast outcomes T3/T5/T10 = 14/12/7  

---

## 4. True history length (classes A–D)

### A. Market Core
FC / REAL / (sparse regime). **42** weekday sessions, ~**2.0** months. Gaps: 1 weekday. Quality: high continuity for scalars; poor for breadth/LIVE pre-MDT0.

### B. Rich Market
Core + groups/universe≥50 or VNI or breadth. **~38** sessions, ~**1.7** months.

### C. Full 142 Forecast-compatible
EMS + Forecast T0. **17** sessions, ~**0.8** months.

### D. Outcome-matured
Honest market T3/T5/T10 via `forecast_outcomes.csv`: **14 / 12 / 7**. Stock-level EL outcomes exist earlier but are **not** market Forecast labels.

**≥3 months of any class?** **No.**

---

## 5. Recoverability vs invention

| Class | Meaning | Where |
|-------|---------|-------|
| `PIT_SAFE` | Frozen at session with canonical MDT0 / Forecast T0 | MDT0 (8), Forecast T0 (17) |
| `PIT_RECONSTRUCTABLE` | Rebuildable without future labels | EMS group→FC (17); PH after-close FC rule |
| `MARKET_CORE_ONLY` | Scalars useful, not 142 DNA | Root PH early July; buy elite |
| `LEAKAGE_RISK_SOURCE` | Coexists with future schema / multi-FC | Root PH, EL PH (if outcomes kept) |
| `NOT_PROVABLY_PIT_SAFE` | Selection bias / ambiguity | Buy elite as market proxy; ambiguous multi-FC days without after-close rule |
| `UNRECOVERABLE` | Never observed | Pre-2026-06-25; breadth before MDT0; EMS market scalars (never stored); Camera bars in this workspace |

**Valid T0 extraction from PH:** Yes — use `date`, after-close `time`, `market_forecast`, `market_real`, `market_regime`, stock DNA columns; **exclude** all `t*_return` / `t*_win`. Do not invent missing breadth.

Hist-core tiers already recorded: `LEAKAGE_RISK_SOURCE` 21, `PIT_RECONSTRUCTABLE` 9, `PIT_SAFE_COMPLETE` 8, `NOT_PROVABLY_PIT_SAFE` 4.

---

## 6. Outcome recovery (possible, not implemented)

| Label | Possible now? | Basis | Sessions |
|-------|---------------|-------|----------|
| VNINDEX T3/T5/T10 return | **Partial** | MDT0 VNI close (8 days) + P0 volume/tech (17); need longer VNI close series for path MFE/MAE | Limited |
| Equal-weight universe T3/T5/T10 | **Yes** for EMS calendar | Already in `forecast_outcomes` | 14/12/7 |
| Breadth change T3/T5/T10 | **Limited** | Need MDT0 breadth ladder continuity | ~8 T0 side |
| MFE/MAE path | **Yes** where EMS boards exist for intervening sessions | Contract basis: EW path | Same as EMS overlap |

Stock EL `outcomes.csv` enables symbol-level T3/T5/T10 from 2026-07-23 — **different research object** than Market Forecast outcomes.

---

## 7. Forecast-Brain readiness

See `FORECAST_BRAIN_READINESS.md`.

| Stage | Status |
|-------|--------|
| 1 Descriptive | `LIMITED` |
| 2 Falsifiable candidates | `NOT_READY` (borderline LIMITED only for ultra-coarse FC→T3) |
| 3 OOS / episodes | `NOT_READY` |
| 4 Autonomous Brain | `NOT_READY` |

---

## 8. Data collection gap analysis

### P0 — must never lose

| Field | Source | When | Freq | PIT | Raw/derived | Automated now? |
|-------|--------|------|------|-----|-------------|----------------|
| EMS 142 board | EMS CSV | EOD | Daily session | Yes | Raw | Streamlit/EMS path |
| MDT0 FC/REAL/LIVE/breadth/VNI OHLCV | `market_daily_t0` | ≥18:00 VN | Daily | Yes | Raw+agg | Streamlit capture (Forecast **gated** on it) |
| Forecast T0 | forecast_t0_daily | After MDT0 | Daily | Yes | Derived freeze | **YES** timer stage |
| Outcomes T3/T5/T10 | forecast_outcomes | Maturity | Daily | Labels only | Derived | **YES** |
| MDRR | mdrr_daily | Daily | Daily | Yes | Derived | **YES** |
| P0 foreign/turnover/VNI tech | p0_market_daily | Daily | Daily | Yes | Raw+derived | **YES** |
| Root PH scans | pattern_history.csv | Intraday | Multi | Reconstructable | Raw scans | Scan/Streamlit — **not** Forecast timer |

### P1 — valuable

- Sector on EMS board  
- MDT0 VNINDEX technicals filled at freeze (cols exist, values empty; P0 already derives some)  
- After-close FC trajectory snapshot (intraday FC path) into append-only store  
- Camera late-session aggregates into Forecast-adjacent raw store  

### P2 — speculative

- Extra foreign providers beyond HSX/VCI cascade  
- Microstructure / order-book  

---

## 9. Retention audit

See `RETENTION_RISK_AUDIT.md`.

**Highest risk:** root `pattern_history.csv` **full rewrite** on each save.

---

## 10. Daily memory adequacy (accepted Forecast path)

If untouched 3–6 months with MDT0 present:

| | Fields |
|--|--------|
| **YES** | Forecast T0, outcomes maturity, MDRR, hist-core hook, P0 foreign/turnover/VNI tech |
| **PARTIAL** | LIVE/breadth/VNI OHLC (only when MDT0 writer runs); root PH Market Core (depends on scan writers) |
| **NO** | EMS sector column; dedicated intraday FC archive; Camera→Forecast coupling; pre-gap backfill |

**Remaining automation gaps:** ensure MDT0 capture never skips trading days; harden PH retention; optional EMS sector; verify Camera retention on VPS.

---

## 11. Future research dataset design

See `FORECAST_BRAIN_READINESS.md` architecture section. Strict layers: raw → Market T0 → outcomes → episodes → research → (future) production Forecast.

---

## 12. Critical questions — explicit answers

1. **Earliest genuine Market observation?** `2026-06-25` (buy elite FC/REAL).  
2. **Real trading sessions of Market history?** **42** weekdays with recoverable FC (52 calendar dates any source).  
3. **Sessions with FC?** **51** calendar / **42** weekdays.  
4. **REAL?** **51**.  
5. **LIVE?** **8** (MDT0).  
6. **Meaningful breadth/regime?** Breadth **8**; regime labels **12** (sparse).  
7. **Full 142 DNA?** **17**.  
8. **Honest market T3?** **14**.  
9. **T5?** **12**.  
10. **T10?** **7**.  
11. **≥3 months useful Market history in ANY form?** **No** (~2 months Market Core max).  
12. **Why prior recovery saw only 42 FC / 17 T0?** Forecast T0 demands EMS 142 → 17 sessions; FC recovery unions buy_elite + PH + EMS recon + MDT0 → 42 weekdays. PH’s extra value is **partial-universe Market Core**, excluded from Forecast T0 schema.  
13. **Valuable data not used as Forecast T0?** Root PH after-close FC/REAL series; EL sector; buy_elite early June FC; PH technical DNA on non-142 days; EL stock outcomes (different object).  
14. **Permanently unrecoverable?** Pre-2026-06-25; historical breadth before MDT0; EMS market scalars never stored; Camera bars absent here; invented values forbidden.  
15. **Must never lose from today?** EMS boards, MDT0, Forecast T0/outcomes/MDRR/P0, root PH until better archive exists.  
16. **Future session counts for stronger Stage 1/2/3?** Heuristic only: Stage1 ~60–90 breadth-complete weekdays; Stage2 ~40–60 matured full-142 T5; Stage3 needs many more regime episodes (often 6+ months continuous). Not statistical guarantees.

---

## Artifacts

| File | Purpose |
|------|---------|
| `SOURCE_INVENTORY.csv` | Per-source inventory |
| `SESSION_COVERAGE_MATRIX.csv` | Session×field coverage |
| `FIELD_COVERAGE_MATRIX.csv` | Field×source presence |
| `pattern_history_root_daily.csv` | Root PH per-day stats |
| `RETENTION_RISK_AUDIT.md` | Overwrite/purge risks |
| `FORECAST_BRAIN_READINESS.md` | Stages + dataset design |
| `EVIDENCE.json` | Machine-readable counts |

---

## Final verdict

# `MARKET_HISTORY_PARTIALLY_SUFFICIENT_KEEP_COLLECTING`

Enough Market Core (~2 months, 42 FC weekdays) for **limited** descriptive Stage-1 exploration; **not** enough full-142 / matured / multi-episode history for serious Forecast candidates, OOS, or a Forecast Brain. Continue automatic collection; do not invent history; do not train yet.
