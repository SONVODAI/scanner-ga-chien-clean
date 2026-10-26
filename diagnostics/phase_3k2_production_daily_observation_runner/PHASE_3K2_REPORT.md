# Phase 3K.2 — Production Daily Research Observation Runner

**Stop boundary:** `STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY`  
**Branch:** `cursor/phase-3k2-production-daily-observation-runner-aad2`  
**Base:** `cursor/phase-3k1-living-research-observation-aad2` (PR #75)  
**Status:** PASS

---

## Summary

Phase 3K.2 converts the proven 3K.0/3K.1 observation machinery into a **production-grade daily research runner** that can safely execute once per eligible trading session on real market data. This phase is infrastructure and orchestration only — no scientific policy changes, no deployment, no Streamlit UI, no trading authority.

**Verdict:** One complete research-only daily run per eligible session, with idempotency, crash recovery, forward/backfill mode separation, daily manifest, scheduling contract (not activated), and notification contract (not delivered).

---

## Architecture

### New modules (`modules/edge_research/opr_bridge/`)

| Module | Purpose |
|---|---|
| `production_daily_run_records.py` | ProductionDailyResearchRun, DailyManifest, ForwardClockEntry, run modes, dispositions |
| `production_trading_session_eligibility.py` | Panel-derived session eligibility + weekend guard |
| `production_data_readiness_gate.py` | EOD data readiness, temporal provenance verification |
| `production_forward_clock.py` | Trading-session-based T3/T5/T10 eligibility ledger |
| `production_daily_run_persistence.py` | Immutable run records, phase markers, crash recovery state |
| `production_daily_run_observability.py` | Structured operational logging |
| `production_daily_manifest.py` | Compact daily manifest for monitoring/UI |
| `production_scheduling_contract.py` | Future cron/systemd contract (NOT activated) |
| `production_notification_contract.py` | Neutral notification events (NOT delivered) |
| `production_daily_run_orchestrator.py` | Main daily run orchestrator + 15-session simulation |
| `production_daily_run_entrypoint.py` | CLI entrypoint for future scheduled runs |
| `bb_production_daily_run_01_fixtures.py` | CF-RUN1–18 counterfactuals |

---

## Daily Run Contract

`ProductionDailyResearchRun` records:

- `run_id`, `target_trade_date`, `run_mode`, timestamps
- Cutoff provenance, dataset identity/hash, market context
- Prior successful run link, policy hashes
- Observations born/reassessed, forward outcomes released
- Daily summary ID, disposition, failure/skip reason
- Phase history, shadow authority, immutable after finalization

Run modes:

| Mode | `counts_as_forward_evidence` |
|---|---|
| `LIVE_FORWARD` | true (prospective only) |
| `BACKFILL_NON_FORWARD` | false |
| `HISTORICAL_REPLAY_TEST` | false |

Mode conversion after persistence is forbidden (CF-RUN18).

---

## Trading-Day Eligibility

Uses **panel-derived trading sessions** as authoritative (consistent with 3K.0/3K.1). Weekend guard via `is_vn_weekend()` — no exchange holiday calendar invented.

| Condition | Disposition |
|---|---|
| Date in panel sessions | ELIGIBLE |
| Weekend, not in panel | SKIPPED_NON_TRADING_DAY |
| Weekday, not in panel | WAITING_FOR_DATA |

---

## Data Readiness Gate

Before scientific execution:

1. Panel non-empty through target date
2. Trading session eligible
3. Temporal provenance established (3K.0 cutoff rules)
4. No future row leakage
5. Market context available or explicitly classified

Fail closed on ambiguity (CF-RUN15).

---

## Orchestration Order

```
DATA READINESS
→ establish legal cutoff
→ run 3K.0 production research observation (new BirthRecords)
→ load all active prior observations (carry-forward)
→ evaluate newly eligible T3/T5/T10 outcomes
→ append OutcomeRecords
→ run 3K.1 DailyResearchAssessment for each eligible observation
→ create DailyResearchSummary
→ build DailyManifest + notification events
→ persist ProductionDailyResearchRun (immutable)
→ STOP DAILY RUN
```

---

## Forward Clock

Trading-session offsets (not calendar days) for T3/T5/T10 eligibility:

- Birth trade date + N trading sessions from panel
- Actual release date recorded when outcome evaluated
- Missing-data delay flagged explicitly

---

## Crash Recovery

Durable phase markers after each step:

`STARTED → DATA_READINESS → CUTOFF_ESTABLISHED → RESEARCH_COMPLETED → BIRTHS_PERSISTED → OUTCOMES_RELEASED → ASSESSMENTS_COMPLETED → SUMMARY_COMPLETED → RUN_FINALIZED`

Rerun with `resume_run_id` skips completed phases. Tested at BIRTHS_PERSISTED, OUTCOMES_RELEASED, SUMMARY_COMPLETED boundaries.

Idempotency: duplicate same-day invocation returns frozen run without re-execution (CF-RUN1).

---

## Silence Is a Valid Daily Product

Successful runs include NO_DISCOVERY, DESIGN_SILENCE, unchanged belief, waiting for horizon. Even with zero observations:

- Run record persisted
- Market context captured
- DailyResearchSummary created
- DailyManifest reports `bot_spoke_today` honestly

---

## Daily Manifest

Machine-readable per-day artifact:

- Run status, bot spoke today, discovery/assessment counts
- Newly released outcomes, belief changes, silence flag
- Market context hash, summary ID, errors/warnings
- Shadow authority status

Not trading advice.

---

## Scheduling Contract (NOT Activated)

Defined in `production_scheduling_contract.py`:

- Entrypoint: `python -m modules.edge_research.opr_bridge.production_daily_run_entrypoint`
- Post-EOD window: >= 18:00 Asia/Ho_Chi_Minh
- File lock, safe retry, exit codes
- `activated: false`, `cron_installed: false`, `systemd_timer_installed: false`

---

## Notification Contract (NOT Delivered)

Events exposed with `delivery_status: NOT_DELIVERED`:

- `DAILY_RESEARCH_READY`
- `FORWARD_OUTCOME_RELEASED`
- `MATERIAL_BELIEF_CHANGE`
- `RUN_FAILED` / `RUN_SKIPPED` / `WAITING_FOR_DATA`

No email, message, or BUY/SELL alerts.

---

## 15-Session Production Simulation

Sequential runs over real panel data (2026-07-23 → 2026-08-12), `HISTORICAL_REPLAY_TEST` mode:

- 15 eligible sessions executed
- Active observations carry forward
- T3/T5/T10 released on legal sessions
- Silence and unchanged-belief days persist
- Duplicate invocation idempotent
- Crash/resume at 3 lifecycle boundaries
- `counts_as_forward_evidence: false`

---

## CF-RUN1–18 Results

All pass. Key validations:

| ID | Validation |
|---|---|
| CF-RUN1 | Duplicate same-day idempotent |
| CF-RUN2 | Weekend → SKIP |
| CF-RUN3 | Missing EOD → WAITING_FOR_DATA |
| CF-RUN4 | Future rows excluded |
| CF-RUN5 | Crash after birth → resume |
| CF-RUN8 | No discovery → summary persisted |
| CF-RUN9 | Prior observation reassessed |
| CF-RUN10 | Early T5 rejected |
| CF-RUN11 | BACKFILL never forward evidence |
| CF-RUN12 | Completed run immutable |
| CF-RUN14 | Trading isolation |
| CF-RUN17 | Artificial belief change rejected |
| CF-RUN18 | Mode conversion rejected |

---

## Trading Isolation

All 3K.2 modules audited. Shadow authority preserved everywhere. No trading execution paths.

---

## Regressions

Phase 3K.2, 3K.1, 3K.0, 3J.14A–3J.10 CF suites pass. Frozen 3I/3J policy hashes unchanged.

---

## Known Limitations

1. **Not deployed** — no cron/systemd, no VPS Camera
2. **No Streamlit UI** — manifest + read model only
3. **No notification delivery** — events defined but not sent
4. **Weekend in synthetic panel** — anomaly test panel includes calendar weekends; real production panel excludes them
5. **Summary idempotency** — summaries may append on rerun (assessments and runs are idempotent)
6. **LIVE_FORWARD untested in production** — mode defined but deployment prerequisite

---

## Deployment Prerequisites (Phase 3K.3+)

1. Post-EOD data pipeline confirmed through target trade date
2. Cron/systemd timer installation from scheduling contract
3. File lock and monitoring on manifest output
4. Streamlit UI consuming read model + manifest
5. Optional notification delivery wiring

**Hard stop:** `STOP_PRODUCTION_DAILY_OBSERVATION_RUNNER_READY`

---

## Artifacts

```
diagnostics/phase_3k2_production_daily_observation_runner/
├── run_phase_3k2.py
├── PHASE_3K2_REPORT.md
└── artifacts/
    ├── 00_frozen_policy_hashes.json
    ├── 01_cf_run_summary.json
    ├── 02_production_simulation_15_sessions.json
    ├── 03_scheduling_contract.json
    ├── 04_trading_isolation_audit.json
    ├── 05_regression_summary.json
    └── 06_audit_summary.json
```
