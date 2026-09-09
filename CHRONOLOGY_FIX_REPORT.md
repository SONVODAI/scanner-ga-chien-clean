# Chronology fix report — LIVE Candidate time contract

**Scope:** Isolated Slice 1 / 1C shadow gate only.  
**Not changed:** P×V features, `decide_evidence`, thresholds, 2-bar debounce rules, Camera collection, BUY/SELL, UI, Telegram, alerts, Slice 3.

## Final verdict

| Key | Value |
|---|---|
| **A. HISTORICAL_LOOKAHEAD_FIXED** | **YES** |
| **B. LIVE_CANDIDATE_FIRST_SEEN_READY** | **NO** |

A Candidate is never visible to Intraday P×V before it legally existed **on the research interpret / ledger-clean paths**. Production still has no immutable `candidate_first_seen_ts` and no Dynamic Watchlist handoff.

---

## 1. Historical / replay safety (implemented)

`interpret_candidate_session`:

- Resolves `LegalExistence` before any bar loop.
- Emits **no rows** if the timestamp is missing, date-only, or otherwise not legally usable.
- Emits **no rows** if existence is after cash close (14:45 VN) on the owned session.
- Otherwise emits only bars with `asof >= gate_ts`.
- Empty overlay no longer invents a 00:00 row.

`scripts/replay_intraday_pxv_v1_chronology.py` + `chronology_clean_ledger`:

- Drops illegal ledger rows, then **re-runs the existing** `PublishedDebouncer` on remaining RAW so published state is not inherited from pre-existence bars.
- Does not retune debounce or thresholds.

Tests: `tests/test_intraday_pxv_v1_chronology.py` (plus existing Slice 1 / 1C suites). 55 passed on this host.

---

## 2. LIVE Candidate time contract

| Field | Meaning | Mutable? |
|---|---|---|
| **A. `candidate_first_seen_ts`** | First moment BOT actually made that Candidate available | **Immutable** for the `(symbol, session)` episode |
| **B. `candidate_updated_ts`** | Later re-evaluation / last save | Yes |
| **C. `session` / date** | Which cash session owns the episode | Fixed at birth |

**Provenance classes**

| Class | When | May gate as-of? |
|---|---|---|
| `FIRST_SEEN_IMMUTABLE` | Dedicated first-seen column present and parseable | Yes — `gate_ts = first_seen` |
| `SAVE_CLOCK_LAST_WINS` | Only CSV `time` / `candidate_ts` exists | Yes, as **earliest proven** write — **not** claimed as first-seen |
| `MISSING_UNUSABLE` | Missing / date-only / invented midnight | **No interpretation** |

Do **not** treat an end-of-day save clock as proof the Candidate existed at 09:30.

### Session rule

- **Created after cash close (14:45 VN) on session D:** no same-day 5m interpretation. **LIVE:** eligible from **next trading session open**. Historical Slice 1 does **not** invent a D+1 candidate row (that would change the universe).
- **Created during session D:** Camera may interpret only bars with `asof >= candidate_first_seen_ts` (or earliest-proven save clock if that is all we have).
- **Created before session D** (carry from prior close): all D bars satisfy `asof >= first_seen` and are legal.

---

## 3. Current production capability

### Can the current BOT produce / promote a Candidate intraday?

**Produce a conclusion: yes, if Streamlit runs during the session.**  
**Promote a legally timestamped Candidate into a Dynamic Watchlist for Camera: no.**

| Step | Exists today? | Function |
|---|---|---|
| Compute `KẾT LUẬN` including BUY ELITE / MUA NHỎ | Yes | `app.py` `build_buy_elite_decision_engine` (page load) |
| Persist a row with a clock | Yes | `append_today_buy_elite_signals` → `run_buy_elite_learning_cycle` |
| Immutable first-seen | **No** | `time = vn_time_str(...)` then `drop_duplicates(["date","symbol"], keep="last")` |
| Dynamic / Core Watchlist object | **No** | Architecture prose only |
| Handoff to P×V | **No** | Slice 1 joins the CSV after the fact |

Evidence the engine *can* run before the close: 25 actionable rows at `2026-08-28 12:45:55` (lunch). Evidence it usually does not: **380 / 405** last-wins times are after 15:00.

**Exact stamp point if first-seen is added later (not implemented — no production deploy):**

`append_today_buy_elite_signals` in `app.py`. On first insert of an actionable `(date, symbol)`, set `candidate_first_seen_ts = now`. On later saves, keep that field, set `candidate_updated_ts = now`. Trading scores (`WinProb`, `KẾT LUẬN`, NAV) stay unchanged.

**How that enters a Dynamic Watchlist without changing trading logic:**  
Watchlist = today’s actionable conclusions that have a first-seen. P×V reads that list and already gates `asof >= first_seen`. No change to Elite weights, BUY/SELL, or alerts.

**Smallest architecture (defined, not built):**

1. Two columns on the existing history row: immutable `candidate_first_seen_ts`, mutable `candidate_updated_ts`.
2. Stamp in `append_today_buy_elite_signals` only.
3. Research-only watchlist snapshot: `{symbol, session, first_seen, reason}`.
4. P×V (already gated) consumes that snapshot.

Not a new engine. Not a 5m poller. Not Slice 3.

---

## 4. Overlay (unchanged)

Historical latest-quarantine overlay remains **retrospective / reconciled truth**.

Ledger field `overlay_truth_class`:

- `retrospective_reconciled` when `overlay_applied`
- `canonical_first_write` otherwise

This chronology-clean historical replay does **not** claim to reproduce exactly what Camera would have known live unless that overlay was also available as-of. Overlay was not redesigned.

---

## 5. Chronology-clean Slice 1C census

**No tuning.** Official 1C numbers are the **before** baseline.

This host has **no** official `shadow_ledger.jsonl` and **no** Camera archive. Run-level RAW/PUBLISHED counts therefore cannot be re-materialized here. Event-level eligibility from the exclusive candidate file **is** complete. Re-run on the VPS:

```
python scripts/replay_intraday_pxv_v1_chronology.py \
  --ledger /tmp/pxv-v1-slice1c-debounce/shadow_ledger.jsonl \
  --out /tmp/pxv-v1-chronology-clean
```

That path drops illegal rows and re-debounces RAW (debounce rules unchanged).

### Before (official 1C, operator VPS)

| | RAW | PUBLISHED |
|---|---:|---:|
| S/W runs | 967 | 152 |
| 1-bar | 814 | 108 |
| ≥2 | 153 | 44 |
| ≥3 | 27 | 11 |
| S↔W | 122 | 2 |

First published S/W: 09:15–10:00=**9**, 10:00–11:30=**44**, 13:00–14:00=**74**, 14:00–close=**25**.

Sessions: noisy=6, clean_persistent=9, never_leave_NEUTRAL=39, unusable=2.

### After — event eligibility (this checkout)

| | N |
|---|---:|
| Actionable last-wins events | 405 |
| Provenance `FIRST_SEEN_IMMUTABLE` | **0** |
| Provenance `SAVE_CLOCK_LAST_WINS` | 405 |
| Same-day 5m eligible (lunch `2026-08-28 12:45:55` only) | **25** |
| After-close → **zero** same-day 5m rows (next-open LIVE only) | **380** |

Removed as illegal look-ahead at **event** grain: **380 / 405 = 93.8%** of candidate-sessions lose all same-day interpretation. The remaining 25 keep **PM bars only** (`asof >= 12:45:55`).

### Structural implication for official timing (not a retune)

On this candidate file, **zero** events exist before 12:45:55.

- All **9 + 44 = 53** first-published prints in 09:15–11:30 are illegal look-ahead. After the gate they must be **0**.
- Afternoon first-published (74 + 25) can survive **only** if they belong to the 25 lunch names on 2026-08-28. All other dates are after-close and contribute **0** same-day rows.
- Do not treat the new (smaller) published stream as a reason to change debounce or thresholds.

### Selected human cases (contract, not invented bars)

| Case | Stored clock | After gate |
|---|---|---|
| **GMD 2026-08-28** (1C noisy example) | 12:45:55 lunch save-clock | AM rows illegal; PM bars legal; debounce starts at first PM RAW |
| **ACB 2026-06-29** | 22:30:23 | **No** same-day rows; next-session-open eligible |
| **VCB 2026-07-02** | 15:41:00 | **No** same-day rows; next-session-open eligible |

---

## 6. Proof P×V logic is unchanged

| Surface | Proof |
|---|---|
| `decide_evidence` / `compute_features` / `evaluate_gate` / `PublishedDebouncer.step` | Not edited |
| Thresholds in `constants.py` | No numeric cut changed |
| Same legal bar | `test_legal_bar_pxv_unchanged_vs_interpret_asof` — RAW, features, data_state match direct `interpret_asof` |
| Debounce identity | Existing 1C debounce tests still pass; fixtures now supply an explicit **first-seen at 09:15** so they test the machine, not look-ahead |
| Camera / production hashes | `app.py` and Camera modules untouched |
| `alert_eligible` | Still always false |

---

## 7. Exact next smallest step

Toward:

BOT Candidate → Dynamic/Core Watchlist → Live 5m Camera → RAW/PUBLISHED P×V → visible UI → optional informational alert → Human decides.

**Next smallest step (only):**

Stamp **immutable** `candidate_first_seen_ts` (and mutable `candidate_updated_ts`) in `append_today_buy_elite_signals` on first actionable `(date, symbol)`. Emit a research-only Dynamic Watchlist snapshot of those rows. Do not change Elite scores, Camera collection, UI, Telegram, or alerts.

Blocked after that: V1A Camera is still **post-close collect**, not a live 5m poller. Live Camera is a separate capability, not this PR.

---

Stop. No production deploy. No UI. No alerts. No threshold/debounce retune.
