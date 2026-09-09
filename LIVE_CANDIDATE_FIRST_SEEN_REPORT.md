# LIVE Candidate first-seen + research Dynamic Watchlist

Isolated handoff contract only. No Camera, P×V, debounce, overlay, UI, Telegram, alerts, or BUY/SELL.

## Verdict

| Key | Value |
|---|---|
| **A. IMMUTABLE_FIRST_SEEN_READY** | **YES** |
| **B. DYNAMIC_WATCHLIST_RESEARCH_READY** | **YES** |
| **C. PRODUCTION_UNCHANGED** | **YES** |

C means Elite scores, ranking, `KẾT LUẬN`, Camera, P×V, debounce, and thresholds are unchanged. The history frame may gain two text columns (`candidate_first_seen_ts`, `candidate_updated_ts`) at the existing persist boundary. No production deploy. Tests wrote only to temp dirs.

---

## Contract

**Episode key:** `(session_date, symbol)`

| Event | Rule |
|---|---|
| First actionable observation | `candidate_first_seen_ts = observed_at` (immutable). `candidate_updated_ts = observed_at` |
| Later actionable, same session | **Keep** first_seen. Update `candidate_updated_ts` |
| Actionable → non-actionable, same session | **Keep** first_seen. Watchlist `status=HELD` (Candidate state, not P×V) |
| Non-actionable → actionable, same session, no first_seen yet | Stamp **now** (do not invent an earlier time) |
| Non-actionable → actionable, first_seen already set | Keep original first_seen |
| Same symbol, next session | **New** episode, **new** first_seen |
| Historical row without first_seen | Left empty. Never backfilled from session open, bar time, or EOD |

Last-wins still replaces conclusion/scores. It must not replace first_seen.

**eligible_from**

- first_seen ≤ 14:45 VN that session → `eligible_from = candidate_first_seen_ts`
- first_seen after 14:45 → `eligible_from = next weekday 09:15 VN` (no holiday calendar)
- Watchlist includes a row only if `eligible_from <= now < visible_until`
- During-session episode: visible until next session open
- After-close episode: visible for the next session only (until the following session open)
- One row per symbol on the snapshot (latest visible first_seen wins)

Source: `buy_elite_learning_history`. Isolated snapshot: `data/live_candidate/dynamic_watchlist.json` or `$MRBOT_LIVE_CANDIDATE_OUT`.

---

## Where it is stamped

`app.py` `append_today_buy_elite_signals` now calls:

1. `modules.live_candidate.persist.apply_immutable_first_seen`
2. `modules.live_candidate.watchlist.persist_research_watchlist`

Row building (`KẾT LUẬN`, WinProb, EliteScore, …) is unchanged. If the research module fails, the old concat + last-wins path still saves scores.

Historical CSV rows are **not** given a first_seen.

---

## Lifecycle examples (VN)

### 1. Intraday first-seen, rerun, restart

```
2026-08-14 10:05  HPG BUY ELITE
  first_seen = 2026-08-14T10:05:00+07:00
  updated    = 2026-08-14T10:05:00+07:00
  eligible_from = 10:05
  watchlist ACTIVE

2026-08-14 13:20  HPG BUY ELITE (Streamlit rerun)
  first_seen = 10:05          ← unchanged
  updated    = 13:20
  conclusion / winprob last-wins

2026-08-14 14:00  process restart, reload CSV, write again
  first_seen still 10:05
```

### 2. Actionable → WATCHLIST same session (still visible)

```
10:05  HPG BUY ELITE     first_seen=10:05  ACTIVE
11:00  HPG WATCHLIST     first_seen=10:05  HELD
Watchlist still lists HPG after 10:05. P×V NEUTRAL would not remove it.
```

### 3. WATCHLIST then BUY ELITE same session

```
10:00  HPG WATCHLIST     first_seen empty (not invented)
11:30  HPG BUY ELITE     first_seen=11:30 (stamped now, not 09:15)
```

### 4. After-close → next session open

```
Fri 2026-08-14 15:41  VCB MUA NHỎ / ƯU TIÊN
  first_seen = 15:41
  eligible_from = Mon 2026-08-17 09:15
  Friday 15:41 watchlist: VCB absent
  Monday 09:15 watchlist: VCB present
```

### 5. Next session = new episode

```
2026-08-14 10:05  HPG first_seen=10:05
2026-08-17 09:20  HPG BUY ELITE first_seen=09:20 (new episode)
```

### 6. Historical gap

```
2026-06-29 ACB 22:30 in CSV, no first_seen column
  → stays empty. Not on watchlist. Not backfilled.
```

---

## Tests

`tests/test_live_candidate_first_seen.py` — 12 passed, including A–G plus restart persist and isolated snapshot path.

P×V / chronology suites still 43 passed (untouched logic).

---

## Isolation

- No Camera / live poller / P×V / debounce / threshold / UI / Telegram / alert / BUY/SELL changes
- No production deploy
- Validation writes only under tmp / `$MRBOT_LIVE_CANDIDATE_OUT`

---

## Next smallest missing link

**What is the next smallest missing link between this Dynamic Watchlist and live 5m Camera observation?**

A **live 5m Camera read of watchlist symbols at bar close**, passing each row’s `candidate_first_seen_ts` / `eligible_from` into the already-gated `interpret_candidate_session` (`asof >= eligible_from`).

V1A Camera is still **post-close collect**, not a 5m poller. The missing link is that live bar feed + join, not another Candidate or P×V rule.

Stop. No Camera work in this PR.
