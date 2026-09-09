# Candidate chronology / as-of audit

**Scope:** Slice 1 / 1B / 1C shadow Interpreter only (`cursor/intraday-pxv-v1-3384`, pin `120e2638d76061f6879d1f14141d486697f96277` plus this audit).  
**Not in scope:** P×V rules, 2-bar published state machine, thresholds, debounce internals, DGC handling, Camera writes, UI, Telegram, alerts, BUY/SELL, Slice 2/3, production.

**Question:** Can a candidate be interpreted by the Camera before that candidate actually existed in time?

## Verdict

**FAIL**

**Answer:** Yes. On every current shadow / replay / Camera-replay path, a session-dated BUY ELITE / MUA NHỎ row is interpreted from bar 8 (~09:50) through the cash close, even when the only stored existence timestamp is lunch or after the close (typical 15:11–23:51).

This is not an assumption about “the scan might have been true earlier.” It is what the code and the exclusive candidate file do.

The accepted 2-bar published state machine is **not** the defect. The defect is **which as-of bars are allowed to see a candidate**.

---

## 1. Candidate provenance (evidence)

### Exclusive source

| Item | Evidence |
|---|---|
| Source | `buy_elite_learning_history.csv` only (`CANDIDATE_SOURCE` in `modules/intraday_pxv_v1/candidates.py`) |
| Filter | `conclusion in {BUY ELITE, MUA NHỎ / ƯU TIÊN}` |
| Excluded | `WATCHLIST`, `WATCHLIST - MARKET YẾU`, `CHƯA ĐỦ ĐỒNG THUẬN`, `pattern_history.csv` |
| Identity | `(symbol, date)` — last file order wins (`drop_duplicates(..., keep="last")`) |
| Session ownership | CSV `date` → `CandidateEvent.session` |
| Creation / write clock | CSV `time` concatenated as `candidate_ts = f"{session} {time}"` |
| First-seen | **Not stored. Not recoverable.** No `created_at`, no `first_seen` |
| Update timestamp | CSV has no `updated_at`. `last_outcome_update` is T+1/T+3/T+5 fill, not candidate birth |
| Writer | `app.py` `append_today_buy_elite_signals` → `run_buy_elite_learning_cycle` |
| Writer clock | `now_time = vn_time_str("%H:%M:%S")` at the learning-cycle save |
| Writer key | `drop_duplicates(subset=["date", "symbol"], keep="last")` — later writes erase earlier ones |

Dynamic / Core Watchlist is **architecture prose only** (`HUMAN_CASE_REVIEW.md`, `POST_EXAMINER_DIAGNOSIS.md`). There is no watchlist constructor and no promotion state machine in `modules/intraday_pxv_v1/`. “Promotion” is a join: candidate `(symbol, session)` ∩ Camera overlay symbols for that session (`scripts/run_intraday_pxv_v1_slice1.py`).

### Recorded existence times (this checkout’s CSV)

Actionable last-wins rows: **405** across **20** session dates (`2026-06-29` … `2026-09-04`).

| Bucket of stored `time` | N | Share |
|---|---:|---:|
| Before 09:50 (first interpret bar) | 0 | 0% |
| Cash AM (09:15–11:30) | 0 | 0% |
| Lunch (11:30–13:00) | 25 | 6.2% — all `2026-08-28 12:45:55` |
| Cash PM (13:00–14:45) | 0 | 0% |
| After cash close (`>= 15:00`) | 380 | 93.8% |
| Evening or later (`>= 16:00`) | 360 | 88.9% |

There is **no** candidate in this file whose recorded existence is at or before 09:30.

`last_outcome_update` is later than `time` (example: GMD `2026-08-28` time `12:45:55`, outcome `2026-09-09 15:52:12`). That is T+n maintenance, not first-seen.

---

## 2. As-of integrity

### What is correct (bar clock, same session)

These paths slice Camera bars with `timestamp <= asof` and do **not** pull later **same-session** bars into an earlier as-of:

- `archive.asof_slice`
- `interpret.interpret_asof` (`bars[bars["timestamp"] <= pd.Timestamp(asof)]`)
- `features.compute_features` (re-slices `work["timestamp"] <= ts`)
- `gate.evaluate_gate` (same filter when `asof` is passed)
- Same-session expansion median uses only prior bars in that sliced frame

So a 14:45 **bar** does not leak into a 09:30 **feature** calculation. That is not the failure.

### What fails (candidate clock)

`interpret_candidate_session` never compares `asof` to `candidate.candidate_ts`.

```214:221:modules/intraday_pxv_v1/interpret.py
    for i in range(start, len(bars)):
        asof = bars.iloc[i]["timestamp"].to_pydatetime()
        row = interpret_asof(
            bars,
            asof=asof,
            candidate=candidate,
```

`start = max(RESEARCH_DEFAULT_EVAL_START_BAR - 1, 0)` with `RESEARCH_DEFAULT_EVAL_START_BAR = 8` → first as-of is the 8th 5m slot (~09:50 if the grid starts 09:15). `candidate_ts` is copied onto the ledger row and then ignored.

`candidate_ts` appears in exactly three code places: construction (`candidates.py`), copy onto `LedgerRow` (`interpret.py`), and the constant for the start bar. **Zero call sites filter on it.**

Empty-overlay fallback is worse: it interprets at `00:00` on the session date (`datetime.combine(candidate.session, datetime.min.time())`).

### Look-ahead contamination by path

| Path | Candidate-before-existence? | Other as-of leak? |
|---|---|---|
| Candidate selection | Session-date join only; no as-of gate | Last-wins destroys earlier writes |
| Candidate promotion | Join to Camera symbols for that session | None (no real promotion) |
| Watchlist construction | Does not exist in Slice 1 | N/A |
| Shadow runner `run_intraday_pxv_v1_slice1.py` | **Yes** — calls `interpret_candidate_session` | TOD baselines + qualified counts use **all** Camera sessions, including future dates |
| Camera replay `replay_intraday_pxv_v1_debounce.py` `_camera_replay` | **Yes** — same loop | Same TOD / qualified leak |
| Ledger debounce replay | Does not re-select candidates; replays stored rows | Inherits any pre-existence rows already in the Slice 1 ledger |
| Historical overlay `overlay_session` | Does not create candidates | **Yes** — later quarantine OHLCV replaces earlier bar values; session-level `overlay_applied` flags every as-of row |
| Examiner / human review | Read stored ledger | Will display morning published S/W that the candidate clock forbids |
| Unit test fixture | **Yes** — `_cand(..., candidate_ts=f"{day} 15:05:00")` then `interpret_asof` at 14:45 | Documents the hole |

### TOD / qualified-session look-ahead (related FAIL)

`build_tod_baselines(overlays, symbols)` walks **every** Camera session in the archive. `qualified[sym]` counts interval-quality sessions across that same full set. Both are passed into every candidate, including the earliest date.

Example: a `2026-06-29` ACB row is interpreted with TOD rvol/pace medians and `tod_qualified_sessions` that can include August/September sessions. That is future information in the feature/gate layer. It does not change P×V boolean rules, but it violates “only information available at that bar’s as-of time.”

---

## 3. Historical replay correctness

### Can a candidate visible at 14:30 incorrectly appear at 09:30 during replay?

**Yes — and the file does not even have 14:30 births.**

Eligibility is `(symbol, session_date)`, not `(symbol, asof >= candidate_ts)`. Replay therefore emits morning ledger rows for any candidate that is on that calendar date.

Official Slice 1C census (from `HUMAN_CASE_REVIEW.md`, operator VPS replay) already shows the leak in published output:

> First published S/W: **09:15–10:00 = 9**, 10:00–11:30 = 44, 13:00–14:00 = 74, 14:00–close = 25.

On this candidate file, **zero** actionable rows exist before 12:45:55. Those nine first-published prints in 09:15–10:00 cannot be legal under the stored existence clock.

Bar 8 is ~09:50, so “09:30” in the user’s question is the same class of failure (pre-existence AM as-of). The runner starts at ~09:50, not 09:15, unless the overlay is empty (then 00:00).

### Do end-of-day candidate files leak into intraday interpretation?

**Yes. That is the exclusive candidate source.**

`buy_elite_learning_history.csv` is a learning-cycle snapshot. `time` is the Streamlit/learning save clock, not a 5m decision clock. 19 of 20 dates have earliest `time` at or after 15:11 (post-close). Those EOD rows are then walked across the whole cash session.

Camera V1A itself is post-close collection (18:30 / 20:00 / 22:30, reconcile 07:30 next weekday — `docs/intraday_memory_deployment.md`, `scheduler.POST_CLOSE_HOUR = 16`). Historical “as-of 09:30” **bars** were typically not in the Camera store at 09:30. Bar-timestamp slicing is still the intended research clock for completed 5m OHLCV. Candidate EOD leak is a separate, harder error: the **thesis** was not on the watchlist yet.

---

## 4. Overlay provenance

### How `overlay=true` sessions are created

`modules/intraday_pxv_v1/archive.py` `overlay_session(camera_root, session)`:

1. Load canonical `bars.parquet` for that `session_date`.
2. Load **all** `quarantine/*.parquet` under that session; concat; last `(symbol, timestamp)` wins.
3. Left-merge quarantine OHLCV onto canonical keys. Matching keys get revised open/high/low/close/volume; `bar_source = revised_quarantine`.
4. Quarantine-only timestamps are **appended** (not invented into an existing identity).
5. `overlay_applied = True` on **every row** if any key was replaced **or** any extra timestamp was appended. Otherwise `False` on every row.

Quarantine is written by Camera reconcile (`modules/intraday_memory/storage.py`, `RECONCILE_POLICY = "quarantine_on_change"`). Canonical is not silently overwritten. Overlay is a **read-time** research view. It does not write Camera.

### Can overlay distort chronology?

**Yes, two ways. Neither is the primary candidate-existence FAIL; both are as-of leaks.**

**A. Value look-ahead (bar body)**  
A 09:30 bar first stored at collect (often 18:30+) can be revised at next-morning reconcile (07:30). Replay as-of 09:30 then uses the revised volume/OHLC. `collected_at` is on the bar schema but is **not** consulted by overlay or interpret.

**B. Session-level flag leak (gate label)**  
If only the 14:45 bar was revised, `overlay_applied=True` is copied onto the 09:15 row. `evaluate_gate` then sees overlay on the morning as-of slice (`work["overlay_applied"].any()`). That blocks TRUSTED and tags `STALE_FIRST_WRITE` on bars that were not themselves revised. Slice 1C already called this tautological for flicker; it is still a chronology distortion of the **gate**, not of P×V booleans.

**C. Extra timestamps**  
Appended quarantine-only bars are still filtered by `timestamp <= asof`, so a 14:45 extra bar does **not** appear in a 09:30 slice. Extra keys are not the 14:30→09:30 candidate bug.

### Overlay timeline example

```
2026-09-04 09:30  bar identity (symbol=HPG, timestamp=09:30+07)
2026-09-04 18:30  V1A collect writes canonical (collected_at ≈ 18:30)
2026-09-05 07:30  reconcile: OHLCV differs → quarantine/changed_*.parquet
replay as-of 2026-09-04 09:30
  → overlay replaces 09:30 OHLCV with 07:30-next-day revision
  → overlay_applied=true on all HPG rows that session
  → gate reason includes STALE_FIRST_WRITE even at 09:15
```

This can change QUALIFIED vs TRUSTED and TOD-tagged confidence. It does not create a candidate. It can change features if volume/OHLC changed.

---

## 5. Concrete examples

### Example A — EOD file, whole session illegal

- **ACB 2026-06-29** `conclusion=MUA NHỎ / ƯU TIÊN` `group=PULL VỪA`
- Stored existence: `candidate_ts = 2026-06-29 22:30:23`
- Session ownership: `2026-06-29`
- Runner: if Camera has ACB that day, `interpret_candidate_session` emits rows from ~09:50 through 14:45
- Every one of those as-of times is **12+ hours before** recorded existence
- Same pattern: VCB `2026-07-02 15:41:00`, HAH `2026-08-10 15:23:53`, and 377 other post-15:00 rows

```
09:30  candidate does not exist
09:50  Camera interprets ACB as a Candidate  ← illegal
14:30  Camera still interpreting              ← still before 22:30:23
14:45  cash close
22:30  first stored existence
```

### Example B — Lunch write, AM interpretation illegal (GMD)

- **GMD 2026-08-28** `MUA NHỎ / ƯU TIÊN` `PULL ĐẸP` `time=12:45:55`
- This is the session Slice 1C already treats as the noisy RAW example
- Legal as-of window under stored clock: `>= 12:45:55` (PM bars only)
- Actual window: from bar 8 (~09:50) through 14:45
- All AM published/raw rows for GMD that day are pre-existence
- 24 other names share `2026-08-28 12:45:55` (DBC, ACV, PVD, MWG, VCB, …)

```
09:30  GMD not a Candidate
09:50  interpret starts                     ← illegal
11:30  AM close, still illegal
12:45  first stored existence (lunch save)
13:00  first cash bar that could be legal
14:45  last bar
```

### Example C — Test fixture encodes the hole

`tests/test_intraday_pxv_v1.py` `_cand` sets `candidate_ts="{day} 15:05:00"` (after 14:45 close) and `test_alert_eligible_always_false` calls `interpret_asof` at the 14:45 bar. The suite never asserts `asof >= candidate_ts`.

---

## 6. Root cause(s)

1. **Primary:** Candidate eligibility is calendar-session, not as-of. `interpret_candidate_session` walks the Camera grid from bar 8 and only *records* `candidate_ts`.
2. **Provenance:** Exclusive source is an EOD/learning-cycle CSV whose `time` is save-clock, last-wins, with no first-seen. 93.8% of actionable rows are after 15:00.
3. **Related:** TOD baselines and qualified-session counts use the full Camera archive (future sessions).
4. **Related:** Latest-quarantine overlay applies post-session revisions to earlier as-of values and copies `overlay_applied` onto every row.

---

## 7. Affected paths / files / functions

| Role | Path | Function |
|---|---|---|
| Candidate load | `modules/intraday_pxv_v1/candidates.py` | `load_candidate_events`, `CandidateEvent` |
| Interpret loop | `modules/intraday_pxv_v1/interpret.py` | `interpret_candidate_session`, `interpret_asof` (copy-only) |
| Shadow | `scripts/run_intraday_pxv_v1_slice1.py` | `main` join + interpret |
| Replay | `scripts/replay_intraday_pxv_v1_debounce.py` | `_camera_replay` |
| Overlay | `modules/intraday_pxv_v1/archive.py` | `overlay_session`, `load_latest_quarantine` |
| TOD leak | `modules/intraday_pxv_v1/interpret.py` | `build_tod_baselines` |
| Qualified leak | both scripts above | `qualified[sym] += 1` over all sessions |
| Writer (not modified) | `app.py` | `append_today_buy_elite_signals` |
| Watchlist | — | **missing** (prose only) |

Unchanged and out of scope: `evidence.decide_evidence`, `features.compute_features`, `gate.evaluate_gate` internals, `debounce.PublishedDebouncer`, thresholds in `constants.py`, Camera collector/storage/reconcile, DGC structural gate, UI, Telegram, alerts.

---

## 8. Smallest remediation (not applied — audit only)

**One guard in the interpret loop. Do not touch P×V, debounce, or thresholds.**

In `interpret_candidate_session` only:

1. Parse `candidate.candidate_ts` as VN-local. If missing/unparseable → emit **no** rows (do not invent midnight).
2. `continue` when `asof < candidate_ts`.
3. Delete or gate the empty-bars `00:00` fallback the same way.
4. Optional but still small, same PR-class: in both runners, build TOD / `qualified` from sessions with `session_date < candidate.session` only.

Do **not**:

- Change `decide_evidence`, expansion/pace cuts, 2-bar publish rules, DGC, alerts, UI
- Invent first-seen from row order
- Treat `last_outcome_update` as birth
- “Fix” overlay by rewriting Camera

### Proof this does not change P×V logic

| Check | Why it holds |
|---|---|
| `decide_evidence` / `compute_features` / `evaluate_gate` / `PublishedDebouncer.step` | Not edited |
| Same legal bar in → same RAW / same published step | Guard only drops illegal as-of inputs |
| Thresholds | `constants.py` untouched |
| Camera / production hashes | `app.py`, `earning_learning.py`, `intraday_memory/{storage,collector,reconciliation,runner}.py` untouched |
| 2-bar machine | Still 2 consecutive RAW S/W to enter/reverse; it simply never sees pre-existence RAW bars |
| DGC | Structural UNUSABLE path unchanged |

Published **counts** in a re-replay will drop (morning 1C prints disappear). That is chronology correction, not a new Interpreter rule.

### Proof path (after a future fix; not run here)

```
# 1) Load events; assert 0 candidate_ts < 09:50
# 2) interpret_candidate_session(GMD, 2026-08-28) → min(asof) >= 12:45:55
# 3) interpret_candidate_session(ACB, 2026-06-29) → empty or min(asof) >= 22:30:23
# 4) Fixture: _cand(ts=15:05), asof=14:45 → no row / skip
# 5) Same post-existence bar: RAW and published equal to pre-fix
# 6) production_hash_before == production_hash_after
```

A live 5m Camera + a candidate file that records **first-seen** (not last learning save) is required before any live shadow. This CSV cannot supply first-seen.

---

## 9. Primary question

**Can a candidate be interpreted by the Camera before that candidate actually existed in time?**

**Yes. FAIL.**

Proof: exclusive source times are lunch or post-close; interpret walks from bar 8; `candidate_ts` is never used as a gate; official 1C census already contains 09:15–10:00 published S/W.

Stop. No Interpreter change in this audit.
