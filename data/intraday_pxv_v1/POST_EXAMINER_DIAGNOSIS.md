# Slice 1B post-examiner diagnosis (design only)

Shadow / research only. No live alerts. No Slice 2/3. No T+n fitting. No production writes.

Architecture stays: BOT Candidate → Dynamic/Core Watchlist → Live 5m Camera → P×V Evidence → meaningful alert → Human decides.

## A. Root cause of flicker

The interpreter publishes a **1-bar boolean** with **no hysteresis and no confirmation**:

- `STRENGTHEN = (expanding AND confirming)` where confirming is already `up AND expansion>=2.0×`
- `WEAKEN = up+contraction OR (down+expansion vs long thesis)`
- expansion = current 5m volume / median of the **prior 6 bars** (current excluded)

That definition is **self-extinguishing**. A 2×+ spike fires STRENGTHEN; the next bar that spike **enters the lookback**, the ratio collapses, evidence returns to NEUTRAL. This is cause **C / C_WINDOW**, not a data bug.

Direct STRENGTHEN↔WEAKEN reversals are mostly **B (close vs open flip)** while expansion stays on. Tiny close−open differences still count as up/down (`close != open`). Material two-sided expansion is **G**; near-doji flips are B-noise, not genuine contradiction.

| Cause | Operative in Slice 1 evidence? | Why |
|---|---|---|
| A threshold-boundary | Secondary | Ratio hovering around 2.0× / 0.70× |
| B price-direction | Yes — main reversal path | close>open vs close<open |
| C volume expansion/contraction | Yes — main 1-bar path | spike then fade; window self-extinguish |
| D same-TOD / TOD_PRELIMINARY | **No (dead path)** | `CONFIRMING` already requires expansion, so pace-ahead cannot add STRENGTHEN |
| E overlay / stale-first-write | **Not 5m flicker** | `overlay_applied` is session-level if *any* bar was replaced |
| F data-state changes | Possible, expected rare | gate can change as bars accumulate |
| G contradictory P×V | Yes, subset of reversals | both bars expanding, material opposite direction |

Official 1B: **814/967 = 84.2%** one-bar runs; **122** direct opposite reversals; median persist **1 bar**. That shape matches C_WINDOW + B, not overlay and not TOD.

All stable ≥2 being QUALIFIED / overlay=true is **tautological** if every Camera session has some quarantine: the flag is copied onto every row of the session. It cannot explain bar-by-bar flicker.

Slice 1 `would_be_alert` already requires persist≥2 and one-per-direction, with `alert_eligible=false`. The examiner still judged TOO_NOISY because the **published evidence series** flickers, not because the alert counter is unfiltered.

### Empirical cause split

Shadow ledger is not on this host (`/tmp/pxv-v1-slice1-out/shadow_ledger.jsonl` lives on the isolated VPS clone). Re-run `scripts/diagnose_intraday_pxv_v1.py --ledger /tmp/pxv-v1-slice1-out/shadow_ledger.jsonl` there to fill A–G counts. The mechanism tests in `tests/test_intraday_pxv_v1_diagnose.py` already reproduce C_WINDOW and B on the real interpreter.

## B. Normalized apples-to-apples alert table

**Baseline event:** STRENGTHEN/WEAKEN run-start: the first bar of each consecutive same-label STRENGTHEN or WEAKEN streak in a symbol-session. This is the raw evidence-event universe the 1-bar state machine emits. Every suppression rule below is a filter on this same ordered list. R0 ledger would-be-alert (113) is NOT the baseline — it is already persist>=2 + one-per-direction + skip LOW_CONFIDENCE/UNUSABLE.

**Baseline count (official 1B):** 967

Every row uses that same 967. Retention % = retained / 967.

| Rule | baseline | retained | suppressed | retention % | source |
|---|---:|---:|---:|---:|---|
| `baseline_identity` | 967 | 967 | 0 | 100.0% | official_slice1b_examiner |
| `persist_ge_2` | 967 | 153 | 814 | 15.8% | official_slice1b_examiner |
| `persist_ge_3` | 967 | 27 | 940 | 2.8% | official_slice1b_examiner |
| `persist_ge_15m` | 967 | 11 | 956 | 1.1% | official_slice1b_examiner |
| `persist_ge_30m` | 967 | 7 | 960 | 0.7% | official_slice1b_examiner |
| `slice1_logged_would_be_alert` | 967 | 113 | 854 | 11.7% | official_slice1b_examiner |
| `persist_ge_2_plus_cooldown_30m_from_examiner_R7` | 967 | 142 | 825 | 14.7% | official_slice1b_examiner |

Known identities from official 1B (same baseline 967):

- persist ≥2 → **153** retained (15.8%) — suppresses the 814 one-bar runs
- persist ≥3 → **27** (2.8%)
- persist ≥15m → **11** (1.1%)
- Slice 1 logged would-be-alert → **113** (11.7%) = persist≥2 + one-per-direction + skip LOW/UNUSABLE
- examiner R7 cooldown 30m on persist≥2 → **142** (14.7% of 967). Cooldown only removed **11** of 153 persistent runs.

Why the old table was not comparable: **R0=113 is already compressed**. R1=153 counts every persist≥2 run, including 40 same-direction repeats after the first fire (153−113). R7=142 applies cooldown to the 153, not to the 113, and not to the 967. Some “compressed” counts exceeded R0 because they were not subsets of R0.

No rule below was chosen with T+n returns.

Ledger-dependent rows (first-per-symbol-session, one-per-direction on all 967, cooldown on all 967, persist+material) are produced by the diagnosis script against the existing VPS ledger. They are filters of the same 967, never a new event universe.

## C. Concrete noisy timelines

### C0. Mechanism (real interpreter, synthetic bars — not GMD prints)

These are what the current state machine **must** do. They are the explanation of the 814 one-bar runs and 122 reversals.

**C0a. Window self-extinguish (cause C_WINDOW)** — real interpreter, synthetic 5m bars

```
09:55  NEUTRAL     exp=NORMAL    1.00x  pxv=FLAT
10:00  NEUTRAL     exp=NORMAL    1.00x  pxv=FLAT
10:05  STRENGTHEN  exp=EXPANSION 4.00x  pxv=CONFIRMING     +1.00%   <- spike
10:10  NEUTRAL     exp=NORMAL    1.00x  pxv=FLAT           +1.20%   <- spike now in prior-6 median
```

One-bar STRENGTHEN. Persist>=2 suppresses it because the next bar is not expanding versus a window that now includes the spike. This is the structural reason 84.2% of runs last one bar — not overlay, not TOD.

**C0b. Direct opposite reversal (cause B, G if both moves are material)**

```
10:05  STRENGTHEN  exp=EXPANSION 4.00x  pxv=CONFIRMING     +1.00%
10:10  WEAKEN      exp=EXPANSION 3.80x  pxv=SELL_EXPANSION -1.24%   <- same expansion family, opposite close-vs-open
```

No NEUTRAL in between. Volume did not reverse; candle direction did. Near-doji close!=open flips are B-noise; material two-sided expansion is G.

**C0c. Weak-up after a spike (cause C)**

Up-bar expansion STRENGTHEN, next up-bar on contracted volume → WEAKEN (`price up on contracted volume`). Direction stayed up; volume state flipped.

**C0d. Boundary (cause A)**

Ratio 2.05× then 1.95× with the same up direction. Evidence chatters around the 2.0× cut. Hysteresis (enter 2.0 / exit 1.3) would hold; 2-bar confirmation would also hold unless both bars sit on opposite sides of the cut.

### GMD 2026-08-28 (observed — ledger required)

This host does not have `/tmp/pxv-v1-slice1-out/shadow_ledger.jsonl`. Do not invent GMD prints.

On the isolated VPS clone (do **not** checkout the PR on `/opt/mrbot-camera`):

```
python scripts/diagnose_intraday_pxv_v1.py \
  --ledger /tmp/pxv-v1-slice1-out/shadow_ledger.jsonl \
  --out /tmp/pxv-v1-slice1-diagnosis \
  --focus GMD:2026-08-28
```

Expected if GMD is the noisy example: many 1-bar STRENGTHEN tagged C_WINDOW, plus STRENGTHEN↔WEAKEN tagged B/G, overlay=true on every row (session flag), TOD_PRELIMINARY on every row (confidence label, not the boolean driver).

## D. Smallest recommended change (Interpreter / state machine) — do not implement yet

Do **not** retune 2.0× / 0.70× / 1.5× against T+n. Do **not** add live alerts.

| Mechanism | Addresses observed failure? | Or only hides alerts? |
|---|---|---|
| Persistence / debounce (2-bar confirm to *enter* S/W, 2-bar confirm to *reverse*) | **Yes.** 1-bar spikes never publish; 1-bar opposite does not reverse. Matches C_WINDOW + B. Persist≥2 as an *alert* filter already exists; the gap is that **published evidence** is still 1-bar. | Alert-only persist without changing published evidence just hid 814 runs from R0 while the examiner still saw flicker. |
| Hysteresis on expansion ratio (enter 2.0×, exit ~1.3×, pre-declared) | **Yes for A and residual C.** After 2-bar confirm, add only if boundary chatter remains. | If exit is too sticky, a dead spike stays STRENGTHEN — that would hide a real fade. |
| State-transition confirmation | Same as debounce if confirmation is on evidence, not on alerts. | — |
| Material-change re-alert | No. Dedup after quality exists. | Hides same-direction repeats (the 40 extra persist≥2 runs). Fine as layer 2. |
| 30m cooldown / dedup | **No.** R7: 153→142. Almost no effect on persistent events; if applied to all 967 it would fire on the first 1-bar spike then mute the morning. | Pure hiding. |

**Smallest change:** debounce the *published* evidence state.

1. Keep the current 1-bar boolean as `raw`.
2. Publish STRENGTHEN/WEAKEN only after **two consecutive raw** bars of that label.
3. Reverse S↔W only after **two consecutive** opposite raw bars; a single opposite or NEUTRAL returns published state to NEUTRAL (do not hold STRENGTHEN across a fade).
4. Leave RESEARCH_DEFAULT cuts unchanged. Leave TOD pace unused until TOD_EARLY *and* CONFIRMING is redefined (today pace is dead code).
5. Keep `alert_eligible=false`. Keep one-per-direction as a later alert policy, not as a substitute for confirmation.

Cooldown-only or material-change-only would make the alert counter look quieter without fixing the 84% one-bar evidence.

## E. Evidence required before live informational alerts

Still not Slice 2. Pre-declare these gates; do not fit them on T+n.

1. Re-run Slice 1B examiner on **published** (debounced) evidence, same archive, same candidates.
2. One-bar published S/W rate well below 84% (pre-declare e.g. <30% of published runs).
3. Direct opposite reversals drop vs 122/967; remaining reversals mostly tagged G (material two-sided expansion), not B-noise.
4. Cause split shows F+E are not the driver (overlay/session flag remains labeled QUALIFIED, never TRUSTED).
5. Normalized table from the **same** published-run baseline: persist≥2 is no longer the thing doing all the work (most published runs already last ≥2 by construction).
6. Human read of 5–10 symbol-sessions (including GMD 2026-08-28 and one clean persist example): message is informational, no trade verbs except BOT reason pass-through.
7. TOD still PRELIMINARY (16 sessions): any live message must say so. Do not wait for TOD_EARLY to allow *informational* alerts, but do not treat same-TOD ratios as trusted.
8. DGC remains UNUSABLE / no S/W (gate holds).
9. Production Camera, Discovery, Learning, BUY ELITE, Guardian unchanged.
10. Architecture unchanged. Human still decides. No BUY/SELL. No threshold search on T+n.

Until (1)–(6) hold, keep shadow-only.

## Operator replay (isolated VPS clone, not /opt/mrbot-camera)

```
cd /tmp/pxv-v1-slice1b   # or a fresh clone of this commit
python scripts/diagnose_intraday_pxv_v1.py \
  --ledger /tmp/pxv-v1-slice1-out/shadow_ledger.jsonl \
  --out /tmp/pxv-v1-slice1-diagnosis \
  --focus GMD:2026-08-28
```

Writes only `--out`. Does not touch Camera, production HEAD, or the ledger.
