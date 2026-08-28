# Phase 3K.4 — Mr.BOT Living Research UI

**Stop boundary:** `STOP_LIVING_RESEARCH_UI_READY`  
**Branch:** `cursor/phase-3k4-living-research-ui-aad2`  
**Continues from:** Phase 3K.3 (Forward Evidence & Calibration Ledger, PR #77)

## Mission

Build the first production-facing **read-only** Research Brain UI answering daily:

- What is Mr.BOT thinking today?
- What changed since yesterday?
- Why did belief change or remain unchanged?
- What is it uncertain about?
- What evidence is it waiting for?
- What did it say before outcomes were known?
- How much real forward evidence has accumulated?

The UI exposes the Brain honestly — including uncertainty, silence, mistakes, unchanged beliefs, weakened observations, rejected ideas, small samples, and missing evidence.

## Architecture

```
Persisted Records (3K.0–3K.3)
        ↓
production_living_research_ui_read_model.py  (authoritative read model)
        ↓
production_living_research_ui.py             (Streamlit presentation)
        ↓
app.py                                       (integrated after Edge Research panel)
```

**No duplicate research logic.** UI reads persisted products only. No production Brain execution on render.

### New Modules

| Module | Purpose |
|---|---|
| `production_living_research_ui_records.py` | Constants, forbidden terms, authority badges |
| `production_living_research_ui_read_model.py` | Read model builders (health, voice, daily change, observations, timeline, forward evidence, history) |
| `production_living_research_ui.py` | Streamlit panel + deterministic text snapshots for tests |
| `bb_living_research_ui_01_fixtures.py` | CF-UI-A through CF-UI-L fixtures |

## Source-of-Truth Mapping

| UI Section | Source |
|---|---|
| Today's Voice | `DailyVoiceContract` / `render_daily_voice()` from assessments |
| Daily Change | `DailyResearchSummary` + assessment epistemic/market deltas |
| Active Observations | `ResearchObservationBirthRecord` + latest `DailyResearchAssessment` |
| Observation Timeline | Birth + assessments + outcomes (temporal cutoff) |
| Forward Evidence | 3K.3 calibration ledger + `build_self_knowledge_read_model()` |
| Self-Knowledge | 3K.3 self-knowledge read model |
| Data Health | 3K.2 `ProductionDailyResearchRun` index |
| History View | Historical read model with `as_of_trade_date` cutoff |

## UI Hierarchy

1. **MR.BOT — HÔM NAY TÔI ĐANG NGHĨ GÌ?** (primary section)
2. Hôm nay vs hôm qua (daily change)
3. Observations đang sống (expandable with timeline)
4. Forward evidence panel
5. Mr.BOT biết gì về chính mình?
6. Research History (expander with date picker)

Authority badge: **RESEARCH ONLY** always visible. Run mode labels distinguish LIVE_FORWARD vs BACKFILL vs REPLAY.

## Daily Change Behavior

Shows TODAY vs PREVIOUS TRADING SESSION:

- Market regime delta
- Observation count delta (born / reassessed)
- Belief/lifecycle changes with why
- Unchanged belief despite market change (prominently explained)
- Honest "nothing meaningful changed" when applicable

Does not paraphrase the same conclusion to appear fresh.

## Observation Timeline

Chronological history per observation:

```
BIRTH → Assessment(s) → T3 → Assessment(s) → T5 → ... → T10
```

Each event shows state **at that time** — historical belief is never overwritten by current belief.

## Forward Evidence Panel

Conservative exposure of 3K.3 calibration:

- LIVE_FORWARD count, T3/T5/T10 availability, pending, maturity label
- Tiny-N warning when N < 3
- Explicit distinction: REAL FORWARD vs HISTORICAL/BACKFILL/TEST
- No win rate headline, no profitability badge, no edge claim

## Failure-State UX

Graceful handling for:

- No LIVE_FORWARD data yet
- Only historical replay
- WAITING_FOR_DATA / FAILED_CLOSED / PARTIAL_RECOVERABLE
- No active observations
- Narrator unavailable (falls back to assessment-derived voice)

Scientific records remain viewable even if narrative rendering fails.

## Performance

- **No research execution on render** — reads persisted JSON only
- Text snapshot renderer for tests/diagnostics without Streamlit overhead
- No heavy historical recomputation

## Existing Insight Panel Recommendation

**Recommendation: RETAIN AS LEGACY (Option B)**

| Panel | Authority | Question |
|---|---|---|
| Living Research UI (new) | 3K.0–3K.3 production records | What does Bot think *today* in production research? |
| BOT Learning Insight (legacy) | `data/earning_learning/` lifecycle | What has Bot learned overall from T3/T5/T10 patterns? |

Action taken: Added explicit legacy caption to `render_bot_learning_insight()` pointing users to the new panel. No deletion. No contradictory opinions without authority explanation.

## Preview (NON_FORWARD)

Diagnostics generate deterministic text snapshots (not screenshots):

1. Normal speaking day — voice narrative with daily change
2. NO_DISCOVERY/silence day — useful page with SILENCE lifecycle
3. Observation timeline — BIRTH-first chronological history
4. Forward evidence — tiny-N warning, BACKFILL labeled
5. All previews marked `counts_as_forward_evidence: false`

## CF-UI Fixtures

| ID | Scenario | Result |
|---|---|---|
| CF-UI-A | No LIVE_FORWARD yet | Honest empty state |
| CF-UI-B | Normal speaking day | Voice renders |
| CF-UI-C | Lifecycle states | Exposed |
| CF-UI-D | Weakening/challenged | Schema supported |
| CF-UI-E | Silence/no discovery | Useful page, not dead box |
| CF-UI-F | T3/T5/T10 panel | Schema visible |
| CF-UI-G | Pending horizons | Visible |
| CF-UI-H | WAITING_FOR_DATA | Recognized |
| CF-UI-I | FAILED_CLOSED | Schema supported |
| CF-UI-J | Historical view | No future leakage |
| CF-UI-K | Narrator unavailable | Assessment fallback |
| CF-UI-L | Tiny forward sample | Warning shown |
| CF-UI-TIMELINE | Observation timeline | BIRTH-first |
| CF-UI-AUTHORITY | No BUY/SELL terms | Pass |
| CF-UI-MODE | BACKFILL ≠ forward | Pass |
| CF-UI-ISOLATION | Trading isolated | Pass |

## Temporal / Authority Audit

Proven:

- Historical UI cannot see future evidence (`as_of_trade_date` cutoff)
- BACKFILL not labeled as LIVE_FORWARD
- Historical belief not overwritten in timeline
- UI cannot mutate scientific records (read-only)
- UI cannot trigger research policy or trading
- No BUY/SELL semantics in rendered output

## Regressions

Verified without weakening:

- Phase 3K.4 tests
- Phase 3K.3, 3K.2, 3K.1, 3K.0
- Phase 3J.14A, 3J.10
- Trading isolation audit
- Hidden-answer audit
- Frozen policy hash audit

## Known Limitations

1. **No LIVE_FORWARD production deployment** — UI shows historical/backfill until live runs begin
2. **Vietnamese voice quality** — bounded by structured DailyVoiceContract; not generative LLM
3. **No screenshot artifacts in CI** — text snapshots used instead
4. **No notifications/scheduling** — operational activation deferred
5. **Single-page integration** — no separate Streamlit multipage app

## Prerequisites for LIVE_FORWARD Deployment

1. Daily production runs with `run_mode=LIVE_FORWARD`
2. Persisted BirthRecords, assessments, outcomes, calibration ledger
3. Successful daily run health (not WAITING_FOR_DATA)
4. User understands BACKFILL preview data ≠ real forward evidence

## Definition of Pass

**PASS** means a user can open the application and truthfully understand what Mr.BOT thought on a selected trading day, what changed, why, what evidence was known then, what remains uncertain, and what forward evidence has accumulated — without the UI inventing science, leaking future information, or implying trading authority.

**PASS DOES NOT MEAN:** edge exists, profitability, BUY/SELL ready, LIVE_FORWARD deployed, or notifications active.

---

**STOP_LIVING_RESEARCH_UI_READY**
