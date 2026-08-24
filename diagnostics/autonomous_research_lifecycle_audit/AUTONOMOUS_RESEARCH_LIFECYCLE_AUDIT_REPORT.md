# Autonomous Research Lifecycle — Production Audit & Repair

**Date:** 2026-08-24  
**Branch:** `cursor/autonomous-research-lifecycle-heartbeat-aad2`  
**Stop:** `STOP_AUTONOMOUS_RESEARCH_LIFECYCLE_AUDIT_REPAIR`

## A. Root cause

**Autonomous research was NOT production-wired on `main`.**

Evidence:
- All `origin/cursor/phase-3j*` and `phase-3k*` branches are **unmerged** into `main` (24 remote branches).
- `main` has Edge Research discovery/challenger library + Streamlit UI only.
- Production triggers were **manual buttons only** (`Run discovery` / `Run challenger`).
- No daily-research systemd timer on `main`; Phase 3K.2 scheduling contract on feature branches still has `"activated": false`.
- `last_research_event: NONE` = default / never written by an autonomous path (diagnosis **B — lifecycle never ran**), not a deliberate `NO_RESEARCH` decision.
- Research coverage ends ~lifecycle `trade_date` max (~2026-08-18/19) while EOD freeze/observations advance to **2026-08-24** — panel keys off lifecycle, not a daily research runner.

## B. Existing architecture (correctly implemented on main)

- `EdgeResearchEngine` discovery + challenger (RESEARCH ONLY, `production_coupling=NONE`)
- `research_controller` / planner / grammar session tools (library; tests only — not production-scheduled)
- Streamlit panel display + manual action queue with busy guard
- Durable artifact publish helpers

Phase 3J/K OPR daily observation stack exists on **unmerged** PRs only (large tree; timer install-only / not enabled).

## C. Missing connection

`new EOD data → daily update` never called `observe → decide → persist` for research.  
Silence after new data was indistinguishable from “Brain never woke up.”

## D. Changes (minimal repair)

| File | Why |
|------|-----|
| `modules/edge_research/autonomous_heartbeat.py` | Cheap observe→decide→persist heartbeat; durable identity; deliberate NO_RESEARCH / WAIT / OPEN / REVIEW codes |
| `modules/edge_research/ui.py` | Invoke heartbeat on panel render (skip while manual run busy); compact observability |
| `modules/edge_research/engine.py` | Preserve heartbeat metadata when refreshing foundation status |
| `tests/test_edge_research_autonomous_heartbeat.py` | T1–T9 + coverage-lag / maturity cases |

Does **not** merge the full Phase 3J/K OPR mega-tree (would be a redesign-scale import). Heartbeat reuses Edge Research storage and stays RESEARCH ONLY so Phase 3K daily runner can later replace/extend this bridge when merged.

## E. Path after repair

```
new EOD / app SCAN panel load
  → observe data identity (freeze/market_t0/observations)
  → decide (NO_RESEARCH / REVIEW / WAIT / OPEN / CONTINUE / …)
  → persist heartbeat_state + decisions jsonl + engine_status.last_research_event
  → UI shows autonomous heartbeat + last research event
```

Expensive discovery/challenger is **not** auto-executed.

## F. Idempotency

Durable `data_identity` in `data/edge_research/autonomous_lifecycle/heartbeat_state.json`.  
Identical identity → `IDEMPOTENT_REPLAY` (no duplicate decision ledger rows; no budget burn).

## G. Tests

`python3 -m pytest tests/test_edge_research_autonomous_heartbeat.py -q` → **12 passed**  
Foundation/durable regression: **21 passed, 13 skipped**

## H. Expected after next EOD

On next Streamlit path that renders Edge Research: one heartbeat for the new cutoff; `Last research event` becomes `AUTONOMOUS HEARTBEAT: …` (not `NONE`). If coverage still lags EOD by ≥2d with unchanged regime → `RESEARCH_REVIEW_WARRANTED` (deliberate; not auto discovery).

## I. Manual buttons

Remain **optional diagnostic controls** for expensive discovery/challenger. Not required for the autonomous observe/decide heartbeat. Busy guard prevents heartbeat conflict during manual runs.

## J. Safety

- Research remains RESEARCH ONLY  
- Production coupling remains NONE  
- No Market First / Earning / Sweetspot / Camera / Position Guardian / BUY-SELL changes  
- Hidden examiner directory never read  
- No hidden edge taught to Mr.BOT  
