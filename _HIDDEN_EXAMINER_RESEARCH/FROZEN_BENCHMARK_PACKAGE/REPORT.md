# HIDDEN EXAMINER REPORT
## Decline → Recovery State Transitions
### Isolated from Mr.BOT Research Brain

- **Run ID:** `examiner-recovery-transition-20260824T094938Z`
- **Timestamp (UTC):** 2026-08-24T09:49:38Z
- **Dataset cutoff:** 2026-08-21 (last trading session in panel)
- **Universe:** 142 production WATCHLIST symbols from `app.py`
- **Classification standard:** conservative. One V-bottom month cannot support a robust edge.

**THIS DOCUMENT IS EXAMINER-ONLY.** It must not be ingested by Research Brain, prompts, grammar, feature registries, tests, UI, or production memory.

---

## Isolation verification

| Check | Result |
|---|---|
| Output root | `_HIDDEN_EXAMINER_RESEARCH/` |
| Brain storage path `data/edge_research/` | not created, not written |
| `modules.edge_research.storage` imported | **No** |
| Production / Brain / tests / prompts modified | **Zero** |
| Hidden path collides with Brain inputs | **No** |
| Reads | existing repo CSVs only (same information legally available to Mr.BOT) |

Brain persistence is hard-wired to `data/edge_research/` (or `EDGE_RESEARCH_DATA_DIR`). Adapters read `data/earning_learning/`, `pattern_history.csv`, `buy_elite_learning_history.csv`, and `research_exports/`. This sandbox is outside all of those paths.

Details: `outputs/isolation_verification.json`.

---

## Data used and cutoff

### Sources (SHA-256 in isolation file)

| File | Role |
|---|---|
| `app.py` WATCHLIST | 142-symbol universe |
| `data/earning_learning/pattern_lifecycle.csv` | Canonical daily T0 panel 2026-07-23 → 2026-08-18 with indicators + vendor T3/T5/T10 |
| `data/earning_learning/pattern_history.csv` | Extra sessions 2026-08-19/20/21; last snapshot per symbol-date |
| `pattern_history.csv` (repo root) | Daily `market_real` path through the July crash (full-universe panel does not start until 07-23) |
| `data/earning_learning/outcomes.csv` | Outcome store (not used as features) |
| `data/earning_learning/market_daily_t0.csv` | Market T0 (only 2026-08-13 onward; too late for the bottom) |

No raw multi-year EOD OHLC archive exists in the repository. Prior-decline information is carried in T0 fields that were themselves computed from longer price history (`dist_high20`, `near_bottom_20_pct`, `near_bottom_60_pct`, RSI, RS, EMA/MA). That is legitimate and look-ahead-free at the snapshot date.

### Canonical panel

- 142 symbols × **22 weekday trading sessions** with complete indicators: 2026-07-23, 24, 27–31, 08-03–07, 10–14, 17–21.
- Weekend/incomplete dates (07-26, 08-01, 08-02, 08-08) dropped from **signals and forward-return paths**.
- Forward returns T+3/5/10/15/20 and MFE/MAE computed from subsequent **closes on the trading-session path only**.
- Same-date cross-sectional excess: `ret_t{h} − median(universe ret_t{h} on that date)`.
- Discovery/holdout split frozen *before* ranking: first 11 sessions (through 2026-08-06) vs remainder (from 2026-08-07).

Descriptive (look-ahead) panel-min count: **62/142 symbols** printed their sample minimum on 2026-07-27 (user observation was ~65; the difference is weekend-date filtering and using trading-session prices only). This diagnostic was **not** used as a signal.

---

## A. Population

A “meaningful decline” was **not** defined as “stocks that later bounced.” Every definition is a T0 state.

Primary search population (pre-declared, not reverse-engineered from FRT/GIL/etc.):

> **P_dd20_8_nb20_5:** `dist_high20 <= -8` AND `near_bottom_20_pct <= 5`  
> N = 895 observations, 131 stocks, 22 dates.  
> T5 median +2.70%, win rate 75%. T10 median +4.26%, win rate 80%.  
> July 27–31 cluster share: 46%.

This is “already down ≥8% from the 20-day high and within 5% of the 20-day low.” It includes strong recoveries, weak recoveries, false bottoms, continued declines, and sideways cases.

### All population definitions tested

| ID | Definition | N | T5 med | T10 med | July share |
|---|---|---:|---:|---:|---:|
| P_dd20_8 | dist_high20 ≤ −8 | 1598 | +1.79 | +2.63 | 0.36 |
| P_dd20_12 | dist_high20 ≤ −12 | 978 | +2.58 | +3.72 | 0.44 |
| P_dd20_15 | dist_high20 ≤ −15 | 647 | +2.90 | +4.31 | 0.48 |
| P_nb20_2 | near 20d low ≤ 2% | 704 | +2.48 | +4.64 | 0.39 |
| P_nb20_5 | near 20d low ≤ 5% | 1401 | +1.84 | +3.36 | 0.35 |
| P_nb60_3 | near 60d low ≤ 3% | 757 | +2.76 | +4.69 | 0.41 |
| P_rs10_m5 | RS10 ≤ −5 | 791 | +3.16 | +4.74 | 0.58 |
| P_rs10_m10 | RS10 ≤ −10 | 394 | +4.04 | +6.21 | 0.62 |
| P_rsi_30 | RSI14 ≤ 30 | 402 | +4.03 | +6.25 | 0.53 |
| P_rsi_35 | RSI14 ≤ 35 | 638 | +3.34 | +5.35 | 0.52 |
| P_below_ma20_8 | price vs MA20 ≤ −8% | 408 | +4.60 | +6.34 | 0.60 |
| **P_dd20_8_nb20_5** | **primary combo** | **895** | **+2.70** | **+4.26** | **0.46** |
| P_rsi40_dd20_10 | RSI≤40 and dd20≤−10 | 820 | +2.86 | +4.60 | 0.52 |

**Baseline A** for the rest of the study is the primary combo (all eligible declined names).

Universe-wide (any state) Baseline-all-rows: T5 median **+0.86%**, T10 median **+1.78%**. Declined names beat the unconditional universe in this sample. That is **not** yet an edge: the sample is a crash-and-rebound month.

Monotonicity inside the primary pop (tertiles, T5 median):

- **Deeper remaining drawdown → higher T5** (`dist_high20` T1 − T3 spread −3.89 pp; more negative drawdown is T1).
- **Lower RSI, lower RS10, more negative EMA9–MA20 slope, further below EMA9 → higher T5.**
- **Higher RS-spread (RS5−RS10) → higher T5** (only strong *upward* monotonic stock feature).
- **Higher share of the universe sitting on 20d lows that day → higher T5** (`xs_pct_nb20_le2` spread +2.82 pp).

Volume tertiles were **not** monotonic. RSI slope was weakly inverted (more negative RSI slope did slightly better).

---

## B. Search process

The question was treated as open. The search asked what **state changes**, if any, distinguish recoveries from continued declines *relative to other declined names*, not “did prices go up after July 27.”

### Questions tested (ledger: 13 populations + 13 tertile features + 45 named states + 4 alternate-pop sensitivities ≈ **250 evaluations**)

1. Is decline *depth* enough (levels, not transitions)?
2. Do slope transitions (neg→flat, neg→pos, acceleration) add anything inside a decline?
3. Do RSI trajectory / RSI cross-40 add anything?
4. Does short-term RS turning up while 10-day RS is still weak add anything?
5. Does price reclaiming EMA9 or MA20 confirm a better recovery?
6. Does OBV red→green or volume dry-up→expansion confirm?
7. Is sitting *on* the 20d low different from *leaving* it?
8. Does **market-wide** synchronization (many names at 20d lows the same day) dominate stock-level structure?
9. Do ordered sequences (low then reclaim, low then RSI rising, dry-up then expand) beat single states?
10. Are Mr.BOT labeled flags (green2 / early / pull) even active in deep decline?
11. What looks like an anti-edge (still making lows, volume expansion on new lows, slope still steeply negative)?
12. Early (day-0 at the low) vs later/stricter confirmation (1–3 sessions later + EMA9 reclaim).

Hypotheses were logged as tested/rejected/promising **before** any production mapping. No rule was fitted to reproduce FRT +41% / GIL +33% examples.

---

## C. Strongest discovered candidates

None meet the bar for **ROBUST EDGE** or **RESEARCH EDGE**. Holdout (from 2026-08-07) absolute T5 is negative for every promising in-sample structure. Independent pre-July history does not exist in the full-universe panel.

### Candidate 1 — Market-wide 20d-low synchronization  
**ID T21** · family: market · complexity: 1  
**Verdict: INTERESTING OBSERVATION** (structurally closer to **REGIME-CONDITIONAL**, but the incremental vs same-date universe is tiny)

**Exact state (T0-safe):**  
Inside the primary decline population, the session is a *sync-bottom day*: ≥35% of the 142-name universe has `near_bottom_20_pct <= 2`.

**Why discovered:** tertile of `xs_pct_nb20_le2` was the strongest *upward* monotonic market feature; T21 is the binary version.

| | |
|---|---|
| N | 454 obs / 127 stocks / **4 dates** / **1 episode** |
| Dates | 2026-07-23, 07-24, 07-27, 07-28 |
| T3 / T5 / T10 / T15 / T20 median | +1.57 / **+3.90** / **+6.00** / +3.84 / +3.37 |
| T5 mean / win / p10 | +4.17 / 76.0% / −1.78 |
| T5 MFE / MAE median | +4.43 / −0.35 |
| Baseline A (all declined, any date) T5 | +2.70 |
| Baseline B (all stocks on the 4 signal dates) T5 | +3.17 ; incremental **+0.74 pp** |
| Baseline C (declined, *not* those dates) T5/T10 incremental | **+2.26 / +4.11 pp** |
| Baseline D (declined *on those same dates*) | **identical to T21 by construction** (the rule is a date filter) |
| Excess vs same-date universe T5 | **+0.28 pp** |
| July 27–31 share | 51% (all four dates sit in E1) |
| Holdout | **N = 0** (no sync-bottom day after 07-28) |
| Failure rate T5 / T10 | 24.0% / 13.9% |
| Complexity | 1 threshold on a cross-sectional count |

**Interpretation:** this mostly selects **the market-bottom dates**, not a stock-specific recovery mechanic. Baseline D is tautological. Once you compare to all names on those same dates (Baseline B / excess), the extra return collapses to ~0.3–0.7 pp. The right reading is: *being in a meaningful decline on a synchronized-low day participated in the V-bottom*. That is regime identification, not a tradable stock-picker.

**Anti-edge / invalidation:** a 20d low in **mid-August** without synchronization (E3: NTL, HUT, etc.) produced the worst T5s in the failure file. Isolated new lows ≠ crash lows.

---

### Candidate 2 — Sync-bottom day AND RSI rising  
**ID T22** · complexity: 3  
**Verdict: INTERESTING OBSERVATION** (downgraded from a regime-conditional *stock* overlay after Baseline D)

**Exact state:** T21 AND `rsi14 > rsi14_lag1 + 0.5`.

| | |
|---|---|
| N | 131 / 96 stocks / **3 dates** / **1 episode** |
| Dates | 2026-07-24, 07-27, 07-28 |
| T3 / T5 / T10 / T15 / T20 median | +2.08 / **+5.08** / **+6.27** / +3.79 / +3.82 |
| T5 mean / win / p10 | +5.28 / 83.2% / −1.39 |
| T5 MFE / MAE median | +5.66 / **+0.60** (median path never went negative after entry *in this episode*) |
| Incremental vs C (other dates) T5/T10 | **+2.48 / +2.33 pp** — this is mostly **date selection** |
| Incremental vs B (all names, same dates) T5 | +0.87 pp |
| Incremental vs D (declined names, **same dates**) T5/T10 | **+0.05 / −0.76 pp** |
| Excess vs same-date universe T5 | +0.70 pp |
| Holdout | **N = 0** |
| T5 failure rate | 16.8% |
| T10 p10 | **+0.93%** |

The fair stock-selection test is Baseline D: other names that were also in a meaningful decline **on the same three dates**. T22 does not beat them. The large vs-C gap is “these dates vs other dates,” which T21 already captures. T22 is not a distinct recovery-transition edge.

**Failures:** PDR, SZC, CII, HHS on 2026-07-24 (still going down into 07-27). The overlay does not prevent buying one session too early inside the crash. T10 often repaired those T5 failures — again, because the V-bottom continued.

---

### Candidate 3 — RS10 still weak, RS5 turning up  
**ID T10** · family: transition · complexity: 3  
**Verdict: INTERESTING OBSERVATION**

**Exact state:** `rs10 <= -3` AND `rs5 > rs5_lag1 + 1`.

| | |
|---|---|
| N | 289 / 118 stocks / 17 dates / 4 episode labels |
| T3 / T5 / T10 / T15 / T20 median | +2.37 / **+4.31** / **+5.95** / +4.05 / +4.23 |
| T5 mean / win / p10 | +4.64 / 80.1% / −1.44 |
| T5 MFE / MAE median | +4.71 / +0.18 |
| Incremental vs C T5/T10 | **+1.88 / +2.10 pp** |
| Incremental vs D (same dates, same decline) T5 | **+1.19 pp** (the only named transition with a non-trivial same-date same-state residual — still E1-dominated) |
| Excess vs same-date universe T5 | +0.40 pp |
| July share | **72%** |
| Discovery T5 | +4.41 (n=268) |
| Holdout T5 | **−3.31 (n=21), excess −1.00** — **fails temporal split** |
| E1 / E2 / E3 T5 | +4.72 / +0.52 / **−3.65** |
| T5 failure rate | 18.7% |

This is the most “transition-shaped” stock rule that survived in-sample screening. It did **not** survive the holdout or E3 (failed-bottom) window. The in-sample lift is almost entirely E1.

Related simpler state **T08 `rs_spread > 0`** (RS5 > RS10): N=752, all 22 dates, incC T5 +1.46 pp, excess T5 only +0.19. Holdout absolute T5 −1.00 but **holdout excess +0.80** — a weak hint of relative-strength selection when the market is no longer a V-bottom. Not enough N/stability to call an edge.

---

### Candidate 4 — At the 20-day low (level, not a transition)  
**ID T18 / T39** · complexity: 1  
**Verdict: INTERESTING OBSERVATION**

**Exact state:** `near_bottom_20_pct <= 1` inside the primary decline pop.

T3/T5/T10/T15/T20 median +1.47 / +3.42 / +6.04 / +4.48 / +3.83. T5 MFE/MAE +3.61 / −0.38. incC T5 +1.15 / T10 **+3.21**. incD T5 +0.72. Excess T5 +0.31. Holdout T5 −1.53.

This is the “buy the low” level. In a V-bottom it looks excellent at T10; in E3 it does not. It is **not** a recovered-structure transition.

---

### What the attractive confirmation transitions actually did

These were the hypotheses a human technician would usually write down first. They **failed fair testing inside the decline population.**

| ID | State | N | incC T5 | incC T10 | Verdict |
|---|---|---:|---:|---:|---|
| T01 | EMA9–MA20 slope crosses up | 1 | n/a | n/a | almost never fires while still in the decline pop |
| T11 / T45 | price reclaims EMA9 | 30 | **−1.36** | **−3.66** | NO EDGE |
| T40 | 1–3d after 20d low AND >EMA9 | 25 | **−1.34** | **−3.43** | NO EDGE |
| T34 | 20d-low then reclaim EMA9 | 18 | −0.33 | **−3.31** | NO EDGE |
| T03 | slope accelerating from negative | 200 | **−1.84** | **−4.62** | NO EDGE |
| T24 / T25 | 2 / 3 consecutive up closes | 68 / 17 | −1.23 / −1.32 | −1.57 / −2.98 | NO EDGE |
| T26 | drawdown “healing” | 206 | −1.11 | −1.73 | NO EDGE |

T11 also: T15 median 0.0, T20 −1.35, T5 MFE/MAE +2.54 / −0.68, incD T5 −0.11. Waiting did not improve MAE vs sitting on the low.

**Mechanism:** by the time a declined name reclaims EMA9 or prints consecutive up days, a large piece of the bounce is already in the entry price. Remaining forward T10 is then *worse* than names still sitting on the low. In this sample, **later confirmation was later, not safer, for magnitude.**

### Required outcome grid (strongest + confirmation contrast)

Baseline A = all primary-pop declined names. B = all stocks on the candidate’s signal dates. C = primary pop without the state. D = primary pop on the candidate’s signal dates (fair same-state, same-date control). Returns in median %.

| ID | N / stocks / dates / eps | T3 | T5 | T10 | T15 | T20 | T5 wr | T5 p10 | MFE5 | MAE5 | vs A | vs B | vs C | vs D |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T21 | 454 / 127 / 4 / 1 | +1.57 | +3.90 | +6.00 | +3.84 | +3.37 | 76% | −1.78 | +4.43 | −0.35 | +1.20 | +0.74 | +2.26 | 0.00 |
| T22 | 131 / 96 / 3 / 1 | +2.08 | +5.08 | +6.27 | +3.79 | +3.82 | 83% | −1.39 | +5.66 | +0.60 | +2.38 | +0.87 | +2.48 | **+0.05** |
| T10 | 289 / 118 / 17 / 4 | +2.37 | +4.31 | +5.95 | +4.05 | +4.23 | 80% | −1.44 | +4.71 | +0.18 | +1.60 | +3.20 | +1.88 | +1.19 |
| T08 | 752 / 129 / 22 / 4 | +1.63 | +2.90 | +4.42 | +3.45 | +3.45 | 76% | −1.67 | +3.58 | −0.30 | +0.20 | +2.03 | +1.46 | +0.20 |
| T18/39 | 391 / 115 / 22 / 4 | +1.47 | +3.42 | +6.04 | +4.48 | +3.83 | 75% | −1.77 | +3.61 | −0.38 | +0.72 | +2.56 | +1.15 | +0.72 |
| T11 | 30 / 25 / 8 / 3 | +0.78 | +1.67 | +1.22 | 0.00 | −1.35 | 83% | −0.32 | +2.54 | −0.68 | −1.04 | +0.32 | **−1.36** | −0.11 |
| T40 | 25 / 19 / 9 / 3 | +1.41 | +1.67 | +1.38 | +0.45 | −0.90 | 88% | +0.06 | +3.05 | −0.58 | −1.04 | +1.07 | **−1.34** | +0.09 |

T20 N is thin (only the earliest signal dates have a 20-session window). Do not over-read T20.

---

## D. Rejected candidates (especially the attractive ones)

1. **Slope cross / flatten / accelerate as recovery confirmation** — either N≈0 inside a still-declined state, or negative incremental vs names that had not confirmed.
2. **EMA9/MA20 reclaim** — negative incremental T5 and T10 vs Baseline C; MA20 reclaim N=2.
3. **OBV red→green, volume dry-up, dry-up-then-expand** — T15 dry-up −0.65 pp T5; T16 expansion −0.36; sequences underpowered (T37 n=30, T38 n=22) and not better than sitting on the low.
4. **Mr.BOT green2 / early / pull flags** — **N = 0** in the primary decline population. Those labels do not fire when names are still ≥8% off the 20d high and within 5% of the 20d low. They cannot explain this phenomenon.
5. **Health-score improvement** — T20 incC T5 −0.83. Health rising is coincident with price already lifting.
6. **“Anti-edge” T30/T31/T32 (still steeply below EMA9, new low with RSI falling, volume expansion on a new low)** — these *outperformed* Baseline C in E1. They are **not** anti-edges in a V-bottom; they *are* the invalidation set in a failed-bottom regime (E3). Treating them as a general “don’t catch knives” rule would have missed the July episode; treating them as a general “always buy knives” rule would have bought NTL/HUT in August. **The anti-edge is: new lows without market-wide synchronization.**

---

## E. Earlier vs later confirmation

Frozen comparison on the primary population:

| | Early (T39): at 20d low today | Later (T40): 1–3 sessions after a 20d low AND price > EMA9 |
|---|---|---|
| N | 391 / 115 stocks / 22 dates | 25 / 19 stocks / 9 dates |
| Entry extension (`near_bottom_20` median) | **0.0%** (on the low) | **+3.98%** off the low |
| T3 median | +1.47% | +1.41% |
| T5 median | **+3.42%** | **+1.67%** |
| T10 median | **+6.04%** | **+1.38%** |
| T5 win rate | 74.6% | **88.0%** |
| T5 false-positive (ret≤0) | 22.8% | **12.0%** |
| MAE T5 median | −0.38% | −0.58% |
| MFE T5 median | +3.61% | +3.05% |
| Incremental vs C T5 | +1.15 | **−1.34** |
| Excess vs universe T5 | +0.31 | +1.13 |

**Trade-off the data actually shows (this sample):**

- **Later confirmation** reduced T5 false positives (12% vs 23%) and had higher same-date *excess* (you are no longer buying the whole crashed tape).
- **Later confirmation** paid a large **magnitude** cost: T10 median +1.4% vs +6.0%, and it lost to other declined names that had not “confirmed.”
- MAE was **not** improved by waiting (slightly worse).
- Entry was ~4% worse versus the low.

The data do **not** say “always buy day-0.” They say: in a *synchronized V-bottom*, early/at-low dominates magnitude; later EMA9 reclaim is a late ticket with a cleaner hit-rate and less leftover bounce. In a *failed-bottom* tape, the early ticket is the one that fails (NTL cluster). Without a regime detector, neither timing rule is a general edge.

---

## F. Market dependence

Root `pattern_history.csv` `market_real` path (median across whatever names were snapshotted that day):

| Date | market_real |
|---|---|
| 2026-07-13 → 07-22 | 1.8 → **0.6** (slide) |
| **2026-07-27** | **0.5** (low) |
| 2026-07-30 | 4.3 |
| 2026-08-10 | 8.2 |
| 2026-08-12 | 9.0 |

The July 23–28 window is one market episode. T21’s entire N lives there. T22’s entire N lives there. T10 is 72% July-cluster; E1 T5 +4.72 vs E3 T5 −3.65.

**Label: `SINGLE-EPISODE / REGIME-CONDITIONAL`.**

Same-date excess returns for the “best” stock rules are 0.2–0.7 pp at T5. Most of the raw +4% to +6% T10 after declined states is **beta to the rebound**, not a hidden stock transition.

The user-cited rebound examples (FRT, GIL, DGW, …) are real *outcomes* of that episode. They are not a distinct microstructure that we could isolate from “the market found a low with ~half the universe on 20d lows.”

---

## G. Robustness

| Test | Result |
|---|---|
| Pre-declared discovery/holdout (split 2026-08-06 / 08-07) | **Absolute T5 of T08/T10/T18/T21-style states goes negative in holdout.** T21/T22 have no holdout dates at all. |
| Episode split E1 vs E3 | Sign **flips** for at-low / RS-turn states. |
| Alternate decline definitions | Direction of T10/T21/T08 generally persists *inside E1*; not a single-threshold artifact. |
| Multiple-testing | ~250 evaluations. Best in-sample incC T5 is +2.5 pp on 3 dates. This would not survive a serious FDR claim. |
| True OOS / earlier independent crash | **Not available.** Full 142-name indicator panel starts 2026-07-23, two sessions before the low. |
| Independent episodes | One primary (July V-bottom), one contrary (mid-August isolated lows). That is the entire temporal evidence. |

**Available history is insufficient for true out-of-sample validation of a recovery-transition edge.**

---

## H. Verdict

| Candidate | Verdict |
|---|---|
| T21 sync-bottom day | **INTERESTING OBSERVATION** (date/regime identification; Baseline D tautological; excess ≈ 0.3 pp) |
| T22 sync-bottom + RSI rising | **INTERESTING OBSERVATION** (vs C looks large; **vs D ≈ 0** — not a stock overlay) |
| T10 RS10 weak + RS5 rising | **INTERESTING OBSERVATION** (best same-date same-state residual; fails holdout / E3) |
| T08 RS-spread positive | **INTERESTING OBSERVATION** (weak holdout excess only) |
| T18/T39 at 20d low | **INTERESTING OBSERVATION** (V-bottom magnitude, not a transition) |
| T11/T40/T01/T34 EMA/slope confirmation | **NO EDGE** (late; negative incremental) |
| T30/T31 “still falling” as anti-edge | **NO EDGE as a general anti-rule**; they *helped* in E1 and *hurt* in E3 |
| Anything claiming a general recovery-structure edge | **NO EDGE** |
| Robust edge | **Not found** |

### Examiner answer (what a capable general researcher should find)

1. Construct the population **prospectively** from T0 drawdown / near-low states, including failures.
2. Notice that **almost all full-universe history is one July-2026 V-bottom**.
3. Discover that **oversold depth is monotonic** for subsequent T5/T10 in that episode.
4. Discover that **market-wide synchronization of 20-day lows** is the dominant state, and that stock-level MA-reclaim / slope-cross “confirmation” is **late and incrementally negative** inside still-declined names.
5. Measure **same-date excess and Baseline D** (same decline, same dates). Apparent vs-C edges that vanish vs D are date filters, not stock transitions.
6. Find the **invalidation**: new lows **without** synchronization (mid-August) fail.
7. Conclude **no robust or research edge**: one V-bottom episode, same-date same-decline controls erase most of the apparent stock transition, and confirmation rules are late.

If Mr.BOT later “discovers” an EMA9 golden-cross buy rule fitted to FRT/GIL, that is a **capability miss** (survivorship + confirmation bias). If it reports “one episode, sync-bottom, confirmation is late, excess is small,” that is a **capability hit**.

---

## Search accounting (multiple-testing)

| Bucket | Count |
|---|---|
| Population definitions | 13 |
| Tertile features | 13 |
| Named transition / sequence / anti / timing / labeled states | 45 |
| Alternate-population sensitivities (45 × 4) | 180 |
| Approximate search cardinality | **~250** |
| Candidates promoted to REGIME-CONDITIONAL | **0** after Baseline D (T21 is a date filter; T22 vs D ≈ 0) |
| Candidates promoted to RESEARCH/ROBUST EDGE | **0** |

---

## Files

- Isolation: `README_ISOLATION.md`, `outputs/isolation_verification.json`
- Panel: `outputs/canonical_panel.csv`, `outputs/panel_meta.json`
- Ledger: `outputs/research_ledger.json`
- Screens: `outputs/transition_screen.csv`, `outputs/tertile_screen_primary_pop.json`
- Failures: `outputs/failure_analyses.json`
- Timing: `outputs/early_vs_late.json`
- Frozen exam: `FROZEN_BENCHMARK_PACKAGE/`
