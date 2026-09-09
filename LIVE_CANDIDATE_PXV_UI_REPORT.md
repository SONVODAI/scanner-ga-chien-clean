# LIVE CANDIDATE × P×V — read-only UI

Smallest observation surface on the existing Mr.BOT app.

A human opening the app can answer, without opening JSON/logs:

1. BOT đang theo dõi mã nào?
2. Candidate xuất hiện từ lúc nào?
3. Camera 5m vừa nhìn thấy điều gì?
4. P×V đang STRENGTHEN, NEUTRAL, WEAKEN hay UNUSABLE?
5. Vì sao?
6. Dữ liệu này có còn live/fresh không?

## Verdict

| Key | Value |
|---|---|
| **A. READ_ONLY_UI_READY** | **YES** |
| **B. NEUTRAL_CANDIDATE_VISIBLE** | **YES** |
| **C. LIVE_FRESHNESS_VISIBLE** | **YES** |
| **D. PROVIDER_NOT_CALLED_BY_UI** | **YES** |
| **E. PRODUCTION_UNCHANGED** | **YES** |
| **F. READY_FOR_ONE_REAL_LIVE_SESSION** | **YES** |

F means the exact command/config is ready. This slice does **not** start a live runner or deploy production. A real VN cash session + vnstock 4.x is still required to see live bars.

E means Elite scores / ranking / `KẾT LUẬN`, V1A Camera archive, P×V features / 2.0 / 0.70 / 1.5 / RAW / 2-bar debounce, Candidate semantics, and existing production expanders are unchanged. The only `app.py` change is an isolated try/except hook. Failure of the panel cannot break production.

---

## Placement

Existing app, first compact expander after the title:

**LIVE CANDIDATE × P×V**

Not a second app. Production panels (BUY ELITE, FINAL DECISION, STORM LEADERS, …) are untouched.

Read-only. Isolated from trading/research state.

---

## Sources (UI never writes, never recomputes)

| File | Role |
|---|---|
| research Dynamic Watchlist snapshot | which Candidates exist, first_seen, eligible_from |
| `live_evidence.jsonl` | latest legal completed bar, RAW, PUBLISHED, why |
| `live_shadow_status.json` | runner freshness / provider errors |

The UI does **not** import or call `KBSProvider`, `fetch_session`, `upsert_session`, `interpret_asof`, or `decide_evidence`.

---

## Visibility rules

- Every legally listed Candidate stays visible when RAW/PUBLISHED are NEUTRAL.
- This is a Candidate watch surface, not a signal-only list.
- `chronology_legal=false` is never shown as valid STRENGTHEN/WEAKEN evidence.
- Duplicate evidence rows collapse to one Candidate card (latest legal bar).
- Empty watchlist: **No active BOT Candidate.**
- Candidate with no legal completed bar: **Waiting for first eligible completed 5m bar.**
- `alert_eligible` is always displayed as false and never flipped.

---

## Fields per Candidate

Symbol · conclusion/reason · `candidate_first_seen_ts` · `eligible_from` · latest completed `bar_ts` · `observed_at` · RAW · PUBLISHED · data state/quality · `chronology_legal` · concise explanation.

Technical labels stay English: RAW / PUBLISHED / STRENGTHEN / NEUTRAL / WEAKEN / UNUSABLE.

Vietnamese frames wrap **existing** Interpreter `evidence_why` strings. No manufactured feature numbers.

History expander shows only meaningful transitions (NEUTRAL ↔ STRENGTHEN/WEAKEN, UNUSABLE / data failure), not every 5m print. No chart.

---

## Freshness

Runner `observed_at` older than **10 minutes** → banner:

`Live-shadow runner STALE / stopped. Evidence below is NOT current.`

Cards in that state are marked `freshness=STALE` (dashed / warning). Provider errors (`PROVIDER_ERROR`, `RATE_LIMITED`, `STALE_BAR`) surface as runner failures. Old evidence is never presented as live.

---

## Sorting (no new score)

1. PUBLISHED STRENGTHEN / WEAKEN
2. RAW STRENGTHEN / WEAKEN
3. NEUTRAL
4. unavailable / unusable / waiting

Tie-break: latest `observed_at`, then symbol.

---

## Tests

`tests/test_live_candidate_pxv_ui.py` — 15 passed (A–M + sort + history).

Related still green: live Camera shadow, first-seen (41 together with this file).

| | Case |
|---|---|
| A | NEUTRAL Candidate remains visible |
| B | STRENGTHEN visible |
| C | WEAKEN visible |
| D | UNUSABLE visible, not treated as a trade signal |
| E | `chronology_legal=false` never valid evidence |
| F | stale runner clearly marked |
| G | waiting for first completed bar |
| H | no Candidate empty state |
| I | duplicate evidence → one Candidate |
| J | UI source/import path does not call provider/Camera |
| K | watchlist / evidence / status files unchanged |
| L | `alert_eligible` remains false |
| M | production expander titles still present |

---

## One real-session shadow validation (do not auto-start)

**Do not run these in production deploy. Research/shadow only. No Telegram. No alerts.**

Prerequisites:

1. vnstock **4.x** in the environment (`pip install -r requirements-collector.txt` if needed)
2. `VNSTOCK_API_KEY` if the KBS guest path requires it
3. Isolated outputs (defaults are already research paths):
   - `MRBOT_LIVE_CANDIDATE_OUT=data/live_candidate` (optional)
   - `MRBOT_LIVE_CAMERA_SHADOW_OUT=data/intraday_pxv_live_shadow` (optional)
4. A Dynamic Watchlist snapshot with `now >= eligible_from` rows  
   (created when `app.py` saves BUY ELITE via `persist_research_watchlist`, or a hand-written research JSON)
5. VN cash session **09:15–14:45 Asia/Ho_Chi_Minh**
6. This branch checked out (read-only UI + shadow feed). No production Camera archive writes.

Commands (two terminals):

```bash
# Terminal 1 — live 5m shadow sweep, staggered 18 rpm, watchlist only (cap 50)
# Repeat each minute; do not use collect_session / upsert_session
cd /path/to/scanner-ga-chien-clean
export MRBOT_LIVE_CAMERA_SHADOW_OUT=data/intraday_pxv_live_shadow
python3 scripts/run_live_camera_shadow.py --live
# then, during the session:
watch -n 60 'python3 scripts/run_live_camera_shadow.py --live'
```

```bash
# Terminal 2 — existing app; panel reads the files above
cd /path/to/scanner-ga-chien-clean
streamlit run app.py
```

Dry-run (no KBS) to confirm the runner script:

```bash
python3 scripts/run_live_camera_shadow.py
```

HTML snapshot of the panel (no Streamlit, no Camera):

```bash
python3 scripts/preview_live_candidate_pxv_ui.py --fixture --now 2026-08-14T14:13:00
```

If Terminal 1 is not running, the UI must show **STALE / STOPPED** and must not look live.

---

## Safety

- Isolated branch / draft PR
- Read-only UI
- No production deploy
- No BUY/SELL, Telegram, popup alerts, or informational alert engine
- No threshold / debounce / score / Candidate / Camera archive changes

Stopped here. No alerts in this task.
