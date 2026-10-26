# Phase 3K.5A — Production Prerequisite Closure

**Stop boundary:** `STOP_PRODUCTION_PREREQUISITES_CLOSED`  
**Branch:** `cursor/phase-3k5a-production-prerequisite-closure-aad2`  
**Continues from:** Phase 3K.5 (PR #79)

## Mission

Close concrete production prerequisites discovered in Phase 3K.5 before deployment or LIVE_FORWARD genesis. No scientific semantics changed.

**LIVE_FORWARD was NOT activated.** No genesis created. Scheduler NOT enabled.

---

## What Was Closed

### 1. Authoritative EOD Completeness

Wired `t0_observation_freeze.csv` as primary producer completion artifact:

- Requires freeze rows for target VN session with `frozen_at` timestamps
- Symbol/observation_id alignment with panel universe
- `market_t0_snapshot` `AFTER_CLOSE` secondary evidence
- Optional `eod_completion_manifest.json` for explicit producer contract
- Fail closed on partial freeze, wrong session, duplicate IDs, symbol mismatch

Module: `production_eod_completeness.py`

### 2. Vietnam Trading Calendar

Deterministic calendar contract in `config/vn_trading_calendar.json`:

- Weekends excluded
- 2026 exchange holidays configured
- Exceptional closure override support
- T3/T5/T10 via `offset_trading_sessions()` / `compute_horizon_eligible_date_vn()`
- Calendar identity versioned for auditability
- No runtime network dependency

Module: `production_vn_trading_calendar.py`

### 3. Timezone Canonicalization

- `trading_session_date` = Asia/Ho_Chi_Minh market date
- Operational timestamps remain UTC
- Genesis first eligible date validated as VN trading session
- CF-PR11 rejects UTC-calendar-derived genesis dates at boundary
- Entrypoint derives VN date when `--trade-date` omitted

Module: `production_timezone_policy.py`

### 4. Backup / Recovery

Filesystem snapshot backup for irreplaceable LIVE_FORWARD records:

- Protected paths: genesis, births, assessments, outcomes, runs, manifests, ledger, snapshots
- Integrity manifest with SHA256 checksums
- Restore verification via `verify_backup_integrity()`
- Retention contract (7 backups)
- **Scheduled backups NOT activated**

Module: `production_backup.py`

### 5. Scheduler Artifacts (Prepared Only)

- `deploy/systemd/mrbot-daily-research.service`
- `deploy/systemd/mrbot-daily-research.timer` (disabled)
- `deploy/systemd/install-daily-research.sh`
- `deploy/systemd/mrbot-daily-research.env.example`

### 6. Operational Health

Extended `build_operational_health_artifact()` with:

- Calendar eligibility, VN session date, EOD completeness
- Genesis status, scheduler artifact status, backup integrity
- LIVE_FORWARD authority state, UI freshness

### 7. DAY_0_SMOKE Revalidation

Hardened path: calendar → timezone → EOD → lock → persistence → health. Still `counts_as_forward_evidence: false`.

---

## GO / NO-GO Matrix

| Dimension | Verdict |
|-----------|---------|
| EOD authoritative completion | PASS |
| Vietnam trading calendar | PASS |
| Timezone semantics | PASS |
| Scheduler artifacts | PASS_WITH_OPERATOR_ACTION |
| Single-writer safety | PASS |
| Persistence | PASS |
| Backup | PASS_WITH_OPERATOR_ACTION |
| Restore verification | PASS_WITH_OPERATOR_ACTION |
| Operational health | PASS |
| DAY_0_SMOKE | PASS |
| Temporal integrity | PASS |
| Trading isolation | PASS |

**Recommendation:** `READY_FOR_DEPLOYMENT_DAY_0`

---

## Operator Actions Still Required (Production Host)

1. Install scheduler units: `deploy/systemd/install-daily-research.sh` — **do NOT enable timer yet**
2. Copy `mrbot-daily-research.env.example` → `/etc/mrbot/daily-research.env`
3. Run DAY_0_SMOKE against production panel on latest EOD-complete session
4. Create LIVE_FORWARD genesis (irreversible) — **not done in this phase**
5. Execute first manual backup: `create_live_forward_backup()` after genesis
6. Verify backup integrity before enabling scheduler
7. Enable `mrbot-daily-research.timer` only after DAY_0_SMOKE + genesis + backup verified

---

## Tests

- `tests/test_edge_research_opr_phase_3k5a.py` — **15 passed**
- CF-PR1–15 — all pass
- Phase 3K.5, 3K.4, 3K.3, 3K.2 regressions — pass

---

## Definition of Pass

PASS means software-side prerequisites are closed sufficiently for controlled production deployment and DAY_0_SMOKE.

PASS does NOT mean LIVE_FORWARD active, genesis created, scheduler enabled, or Day 1 executed.

---

**STOP_PRODUCTION_PREREQUISITES_CLOSED**
