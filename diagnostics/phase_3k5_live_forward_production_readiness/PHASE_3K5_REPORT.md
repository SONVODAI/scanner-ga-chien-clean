# Phase 3K.5 — LIVE_FORWARD Production Readiness Audit

**Stop boundary:** `STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED`  
**Branch:** `cursor/phase-3k5-live-forward-production-readiness-aad2`  
**Continues from:** Phase 3K.4 (Living Research UI, PR #78)

## Mission

Final end-to-end production-readiness audit for the complete 3K.0 → 3K.4 Living Research system **before** LIVE_FORWARD activation.

**LIVE_FORWARD was NOT activated in this phase.**

## Central Question

> If we activate LIVE_FORWARD after this phase, can the next eligible trading session safely become Day 1 of Mr.BOT's prospective research history without future leakage, record rewriting, silent data staleness, duplicate execution, or accidental trading authority?

**Answer:** Architecture and operational contracts are sufficient **with documented manual prerequisites**. Automated EOD completeness and scheduling activation remain operator responsibilities.

---

## End-to-End Architecture Audit

Eight authoritative boundaries documented in `production_readiness_audit.py`:

```
REAL EOD DATA → session eligibility → data readiness → cutoff
  → Research Brain → BirthRecord → assessments → outcomes
  → calibration ledger → UI read model
```

Each boundary specifies: input, output, persistence, identity hash, temporal guarantee, idempotency, failure semantics, recovery.

## Production Data Sources

| Source | Path | Producer | Cadence |
|--------|------|----------|---------|
| Stock panel | `data/earning_learning/pattern_lifecycle.csv` | earning_learning pipeline | daily post-EOD |
| Market context | `data/earning_learning/market_t0_snapshot.csv` | market_t0_capture | daily >= 18:00 VN |
| Forward labels | `data/earning_learning/outcomes.csv` | earning_learning | daily |
| Fallback market | `pattern_history.csv`, `buy_elite_learning_history.csv` | historical | fallback |

Panel builder: `modules.edge_research.adapters.build_research_panel()`

**Gap:** `t0_observation_freeze.csv` not wired to readiness gate.

## Runtime Architecture

| Component | Location |
|-----------|----------|
| Streamlit UI | `app.py` (read-only for research) |
| Daily runner | `production_daily_run_entrypoint.py` (outside Streamlit) |
| Persistence | `data/edge_research/production_observations/` |
| Timezone | `Asia/Ho_Chi_Minh` (scheduling contract) |

**Manual verification required:** production host, venv, cron/systemd, permissions.

## Timezone Audit

- Authoritative session dates: VN local calendar via `derive_vn_trade_date()`
- Birth cutoff records: UTC timestamps (documented split-brain)
- UTC/VN boundary: explicitly detected; production must use VN date for `target_trade_date`
- UI "today": `latest_successful_research_date` from run index, not server clock

## EOD Completeness Gate

Current gate proves:
- Panel non-empty, session eligible, source_max >= target
- Temporal provenance valid, rows exist for target date

**Does NOT prove:**
- 18:00 VN post-EOD freeze
- Universe coverage threshold
- Producer completion marker

**Verdict:** `PASS_WITH_PREREQUISITE` — manual EOD verification required before Day 1.

## LIVE_FORWARD Genesis Contract

Implemented in `production_live_forward_genesis.py`:
- Irreversible `live_forward_genesis.json`
- Records: activation identity, first eligible date, commit, policy hashes, dataset identities, timezone, authority flags
- Guards: no backward move, no second genesis, no BACKFILL→LIVE_FORWARD promotion, LIVE_FORWARD requires genesis

**No real genesis record created in 3K.5.**

## DAY_0_SMOKE Mode

`DAY_0_SMOKE` run mode:
- Isolated namespace: `production_observations/day0_smoke_namespace/`
- Exercises readiness, cutoff, pipeline, lock, UI
- Never counts as forward evidence, never promotable

## First LIVE_FORWARD Day Protocol

Documented in `LIVE_FORWARD_DEPLOYMENT_RUNBOOK.md`:
- PRE-RUN: commit, policy hashes, data completeness, genesis, RESEARCH ONLY
- RUN: acquire lock, single daily run, persist, release lock
- POST-RUN: verify BirthRecord, summary, manifest, calibration, UI, trading isolation

## Scheduling Proposal

| Parameter | Value |
|-----------|-------|
| Window | >= 18:30 Asia/Ho_Chi_Minh (post-EOD) |
| Entrypoint | `python -m modules.edge_research.opr_bridge.production_daily_run_entrypoint` |
| Lock | `--use-lock` → `daily_run.lock` |
| Retry | 3 attempts, backoff [60, 300, 900]s |
| Exit codes | 0/1/2/3/4/10 |
| **Activated** | **false** |

## Concurrency / Lock

Implemented `production_run_lock.py`:
- Exclusive non-blocking `fcntl` lock
- Stale lock recovery (dead PID / timeout)
- CF-READY4/5 verified
- Entrypoint exit code 10 on LOCK_HELD

## Persistence Durability

- Atomic writes via temp + `os.replace`
- Append-only ledgers (JSONL)
- Immutable records after freeze
- Phase markers for crash recovery

**Irreplaceable once LIVE_FORWARD begins:** genesis, BirthRecords, assessments, outcomes, forward evidence ledger, calibration snapshots.

## Backup Plan

Minimum backup scope (manual, not activated):
- `live_forward_genesis.json`
- All observation birth records
- `daily_assessments/`, `forward_outcomes/`, `daily_summaries/`
- `daily_runs/`, `daily_manifests/`
- `forward_evidence_ledger/`, `calibration_snapshots/`

**Never reconstruct forward evidence from hindsight if lost.**

## UI Production Readiness

3K.4 UI verified against production persistence contracts:
- Read-only, no Brain execution on render
- Explicit trade date selection
- WAITING_FOR_DATA / FAILED_CLOSED visible
- Historical temporal cutoff
- Legacy Insight labeled separately

## Observability

`build_operational_health_artifact()` answers:
- Runner status, data readiness, births, assessments, outcomes
- Calibration updates, UI alignment, staleness, lock state
- Genesis existence, fail-closed events

## Notification Readiness (No Delivery)

Events defined, never delivered:
- `DAILY_RESEARCH_READY`, `MATERIAL_BELIEF_CHANGE`, `FORWARD_OUTCOME_RELEASED`
- `RUN_FAILED`, `RUN_SKIPPED`, `WAITING_FOR_DATA`

## Security / Authority Isolation

```
research_only = true
trading_authority = false
buy_signal = false
sell_signal = false
edge_active = false
```

Trading isolation audit: PASS (all 3K modules audited).

## CF-READY1–20

All 20 counterfactuals pass. See `artifacts/02_cf_ready_summary.json`.

## Pre-Deployment Dry Run

`PRE_DEPLOYMENT_DRY_RUN` mode in isolated namespace:
- Full pipeline exercised
- Label: NON_FORWARD / NEVER PROMOTABLE
- Calibration correctly rejects non-forward

## Readiness Matrix

| Dimension | Verdict |
|-----------|---------|
| Scientific integrity | PASS |
| Temporal integrity | PASS_WITH_PREREQUISITE |
| Production data readiness | PASS |
| EOD completeness | PASS_WITH_PREREQUISITE |
| Timezone correctness | PASS_WITH_PREREQUISITE |
| Idempotency | PASS |
| Crash recovery | PASS |
| Persistence durability | PASS_WITH_PREREQUISITE |
| Backup readiness | PASS_WITH_PREREQUISITE |
| UI truthfulness | PASS |
| Operational observability | PASS |
| Security/trading isolation | PASS |
| Scheduling readiness | PASS_WITH_PREREQUISITE |
| Day-0 smoke readiness | PASS |
| LIVE_FORWARD Day-1 readiness | PASS_WITH_PREREQUISITE |

**No FAIL items** when production data panel is available.

## Deployment Recommendation

```
READY_FOR_DAY_0_SMOKE_AND_GENESIS_CREATION —
complete manual prerequisites in runbook before LIVE_FORWARD Day 1
```

## Known Limitations / Blockers

1. EOD completeness gate is row-presence only — operator must verify 18:00 VN freeze manually
2. No VN exchange holiday calendar
3. Scheduling not activated (by design)
4. No notification delivery adapter
5. Backup not automated
6. UTC/VN timestamp split on birth records (documented, not blocking)

## Prerequisites for LIVE_FORWARD Day 1

1. Execute Phase 3K.5 audit with `phase_pass: true`
2. Run DAY_0_SMOKE successfully
3. Create genesis record (irreversible)
4. Verify EOD data complete for target session
5. Enable scheduler with `--use-lock`
6. Execute first LIVE_FORWARD run
7. Verify records + UI + backup

---

## Definition of Pass

**PASS** means architecture and operational contracts are sufficient to deploy and begin prospective LIVE_FORWARD observation without changing scientific semantics or risking hindsight contamination.

**PASS does NOT mean** LIVE_FORWARD has been activated.

---

**STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED**
