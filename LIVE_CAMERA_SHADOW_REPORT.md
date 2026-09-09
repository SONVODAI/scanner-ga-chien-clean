# LIVE 5m Camera shadow feed

Smallest research-only bridge:

**Dynamic Watchlist → live completed 5m Camera observation → chronology-gated P×V Interpreter → isolated shadow evidence.**

No UI. No alerts. No Telegram. No BUY/SELL. No threshold or debounce retune. No canonical Camera archive writes.

## Verdict

| Key | Value |
|---|---|
| **A. LIVE_5M_PROVIDER_READY** | **YES** |
| **B. DYNAMIC_WATCHLIST_TO_CAMERA_READY** | **YES** |
| **C. CAMERA_TO_PXV_SHADOW_READY** | **YES** |
| **D. PRODUCTION_UNCHANGED** | **YES** |

D means Elite scores / ranking / `KẾT LUẬN`, V1A Camera archive collect/reconcile, P×V features, 2.0 / 0.70 / 1.5 cuts, RAW evidence, published 2-bar debounce, semantic gate, and Candidate logic are unchanged. This slice adds an isolated research package and writes only under `data/intraday_pxv_live_shadow/` (or `$MRBOT_LIVE_CAMERA_SHADOW_OUT`). No production deploy.

---

## 1. Universe

Read **only** legally eligible Dynamic Watchlist symbols:

`now >= eligible_from`

- Hard cap this slice: **50**
- No extra ranking. Stable order: `eligible_from`, then `symbol`
- Cap applies to eligible symbols only; `NOT_YET_ELIGIBLE` rows are never fetched
- Production 142-name universe is **not** polled
- Room left for a later Core + Dynamic Candidate split (this slice does not invent that split)

---

## 2. Provider audit (reuse, do not replace V1A)

Existing `modules.intraday_memory.provider.KBSProvider.fetch_session` is safe to reuse as a **read path**:

- `Quote.history(..., interval="5m")` with `start=session-1`, `end=session+1`, then filter to the session
- Throttle floor **18 rpm** (`_min_interval = 60/rpm`)
- Returns raw `{time, open, high, low, close, volume}` records
- **Does not write parquet**

Archive writes exist only in `IntradayCollector` / `upsert_session`. This feed never imports or calls them.

Live shadow isolation:

- Injected provider in tests (`MockProvider`)
- Default live construction is lazy `KBSProvider` via `scripts/run_live_camera_shadow.py --live`
- Script without `--live` is a dry-run (prints rate math, no KBS call)
- `archive_root` if provided is left untouched (no mkdir, no parquet)

V1A post-close collect/reconcile is **unchanged**. This is not a second Camera system.

Bar contract (existing convention): `bar_ts` is the exchange **slot open** on the 09:15–14:45 VN 5m grid. A bar is completed iff `now >= bar_ts + 5 minutes`. Unfinished bars are ignored. `observed_at` is recorded separately. Same `(symbol, bar_ts)` is deduplicated. Completed bars are never written into an earlier Candidate state.

---

## 3. Chronology invariant

Interpreter receives a live bar only when:

`asof >= candidate_first_seen_ts` (existing `asof_allowed` / `resolve_legal_existence`)

**and**

`asof >= eligible_from` (watchlist floor)

A Candidate that appears at 13:37 does **not** receive 13:35 evidence. At 13:42 the 13:40 bar is still unfinished. The first legal completed bar is 13:40, observable at 13:45+.

`CandidateEvent.session` is **today’s** trading date (the session of the bars). After-close Friday first-seen with Monday `eligible_from=09:15` therefore interprets Monday bars, not Friday’s closed session.

Live interpretation uses existing `interpret_asof` + `PublishedDebouncer` per new legal completed bar. It does **not** call `interpret_candidate_session`, because that research loop still starts at frozen `RESEARCH_DEFAULT_EVAL_START_BAR = 8` (~09:50) and would skip a legal 09:15 completed bar. That start offset is **not** changed.

---

## 4. Rate-limit / scheduling (18 rpm)

Guest throttle: **18 rpm → 3.333 s between request starts**.

V1A observed payload ≈ 3.07 s/symbol, so the throttle floor dominates. Symbols are staggered; they are not requested at the same second.

| Universe | Throttle-only sweep | Conservative (`max(interval, 3.07s)`) | Fits one 5m bar (300s)? |
|---|---:|---:|---|
| 30 | 100.0 s | 100.0 s | YES |
| 40 | 133.3 s | 133.3 s | YES |
| 50 | 166.7 s | 166.7 s | YES |
| 142 | 473.3 s | 473.3 s | **NO** |

**Maximum safe live universe under 18 rpm** (request ≤ 3.33 s): **90 symbols** (`90 × 3.333s = 300s`).

This slice still hard-caps at **50** (expected last-symbol latency ≈ **167 s**). If p95 payload were 5 s, 50 still fits (`50 × 5s = 250s`); 142 does not.

No full-142 live polling.

---

## 5. P×V integration (frozen interpreter)

Per new legal completed bar:

1. `interpret_asof(overlay, asof=bar_ts, candidate=..., tod_store=None, tod_qualified_sessions=0)`
2. `PublishedDebouncer.step(raw)` (persisted per symbol under the shadow dir)

Unchanged and unused as tunables:

- feature definitions
- 2.0 / 0.70 / 1.5 thresholds
- RAW `decide_evidence`
- published 2-bar debounce rules
- semantic gate
- Candidate first-seen / episode logic

Output both `raw_evidence` and `published_evidence`.

`alert_eligible = false` always. `would_be_alert = false` on this path. No BUY/SELL fallback.

---

## 6. Shadow output

Isolated path: `data/intraday_pxv_live_shadow/` or `$MRBOT_LIVE_CAMERA_SHADOW_OUT`

| File | Role |
|---|---|
| `live_bars.jsonl` | completed legal bars actually observed |
| `live_evidence.jsonl` | RAW + PUBLISHED + chronology flag |
| `live_shadow_status.json` | per-symbol status + rate block |
| `emitted_keys.json` | `(symbol, bar_ts)` dedup |
| `debounce_state.json` | isolated PublishedDebouncer state |

Each evidence row reconstructs:

| Question | Field |
|---|---|
| Candidate became available when? | `candidate_first_seen_ts` + `eligible_from` |
| Which completed 5m bar? | `bar_ts` / `asof` / `asof_hm` |
| When did Camera observe it? | `observed_at` |
| RAW? | `raw_evidence` |
| PUBLISHED? | `published_evidence` |
| Chronology-legal? | `chronology_legal` |

---

## 7. Failure behavior

Provider / Camera failure **never** invents OHLCV or evidence.

| Status | Meaning |
|---|---|
| `NO_DATA` | provider returned no rows |
| `STALE_BAR` | latest completed bar older than 15m + 5m |
| `RATE_LIMITED` | provider exception looks like 429 / rate limit |
| `PROVIDER_ERROR` | other provider exception |
| `NOT_YET_ELIGIBLE` | `now < eligible_from` — **no fetch** |
| `UNUSABLE` | missing contract fields or all rows rejected |
| `WAITING_COMPLETED_BAR` | legal next slot exists but is unfinished |
| `SKIPPED_CAP` | eligible but beyond the 50 cap — **no fetch** |

No BUY/SELL fallback.

---

## 8. Tests (A–J)

`tests/test_live_camera_shadow.py` — 14 passed (A–J + cap-50 + NO_DATA + rate 30/40/50 + bar-complete boundary).

Also still green: `tests/test_live_candidate_first_seen.py`, `tests/test_intraday_pxv_v1_chronology.py` (41 together).

| | Case | Result |
|---|---|---|
| A | Candidate before session → first legal completed bar only | 09:15 at 09:21 |
| B | Candidate at 13:37 | no 13:35; 13:42 emits nothing; 13:46 emits 13:40 |
| C | Repeated provider response | no duplicate evidence |
| D | Unfinished 5m | 13:40 ignored at 13:42 |
| E | Provider failure | no evidence, `PROVIDER_ERROR` |
| F | Not yet eligible | no fetch, `NOT_YET_ELIGIBLE` |
| G | Same legal bar | RAW/PUBLISHED = `interpret_asof` + `PublishedDebouncer` |
| H | `alert_eligible` | always false |
| I | Canonical Camera archive | no parquet writes |
| J | Poll universe | only Dynamic Watchlist symbols |

---

## 9. Safety

- Isolated branch / draft PR
- Research / shadow only
- No production deploy
- No BUY/SELL, Telegram, UI, or informational alerts
- No threshold / debounce / T+n fitting
- Production Camera archive not modified
- Script default is dry-run (no KBS)

---

## Remaining blocker before Candidate + live P×V is visible on the app UI

This slice stops at isolated JSONL / status files. It does **not** render anything.

Exact remaining blocker:

1. A **read-only UI surface** that displays Dynamic Watchlist rows beside `live_evidence.jsonl` (Candidate first-seen, completed bar, observed_at, RAW, PUBLISHED, chronology-legal).
2. A **real live session** (`scripts/run_live_camera_shadow.py --live` + vnstock 4.x + eligible watchlist). V1A archive collect remains post-close and must stay that way.
3. Still **no alerts** (informational or otherwise) until a later explicit slice. `alert_eligible` must remain false until that slice exists.

Do not wire this feed into Telegram, production Camera, or BUY/SELL.

---

## Deliverables

- `modules/live_camera_shadow/` — universe, bars, rate, feed
- `scripts/run_live_camera_shadow.py` — dry-run by default
- `tests/test_live_camera_shadow.py`
- `LIVE_CAMERA_SHADOW_REPORT.md`
- `live_camera_shadow_report.json`
