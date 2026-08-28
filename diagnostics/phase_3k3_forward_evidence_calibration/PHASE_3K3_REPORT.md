# Phase 3K.3 — Forward Evidence & Calibration Ledger

**Stop boundary:** `STOP_FORWARD_EVIDENCE_CALIBRATION_READY`  
**Branch:** `cursor/phase-3k3-forward-evidence-calibration-ledger-aad2`  
**Continues from:** Phase 3K.2 (production daily observation runner, PR #76)

## Mission

Build the authoritative research-only Forward Evidence & Calibration Ledger that accumulates prospective outcomes from immutable `LIVE_FORWARD` observations. This phase answers: *What did Mr.BOT say before the future was known, what subsequently happened, and how well calibrated has the Research Brain actually been?*

This is **measurement infrastructure**, not scientific policy tuning.

## Ledger Architecture

Append-only ledger under `data/edge_research/production_observations/`:

| Store | Path | Purpose |
|---|---|---|
| Forward evidence entries | `forward_evidence_ledger/{id}.json` | One entry per eligible horizon outcome |
| Calibration snapshots | `calibration_snapshots/{id}.json` | Immutable point-in-time calibration views |
| Index | `calibration_ledger_index.json` | Entry/snapshot lookup |

Every ledger entry traces:

```
BirthRecord → DailyResearchAssessment history → ForwardOutcomeRecord
  → ProductionDailyResearchRun → source/cutoff/policy identities
```

**Modules:**

- `production_calibration_records.py` — record types, maturity thresholds, identity hashes
- `production_forward_evidence_eligibility.py` — LIVE_FORWARD-only eligibility gate
- `production_pre_outcome_snapshot.py` — freeze belief before T3/T5/T10 observable
- `production_calibration_cohorts.py` — pre-declared cohort identity + anti-cherry-picking
- `production_calibration_ledger_persistence.py` — append-only persistence
- `production_calibration_engine.py` — descriptive calibration views (no policy feedback)
- `production_calibration_updater.py` — incremental idempotent daily update
- `production_calibration_self_knowledge.py` — research-only read model
- `production_calibration_simulation.py` — NON_FORWARD mechanics verification

## Eligibility (Fail Closed)

An observation counts as forward evidence only if **all** checks pass:

1. `run_mode == LIVE_FORWARD`
2. `counts_as_forward_evidence == true` from birth
3. BirthRecord existed before outcome eligibility
4. Temporal provenance valid
5. Required source identities available
6. Outcome legally released by trading-session clock
7. Not invalidated by data-integrity failure

**Permanently excluded:** `BACKFILL_NON_FORWARD`, `HISTORICAL_REPLAY_TEST`

## Temporal Ordering & Pre-Outcome State Freezing

For every eligible horizon, the ledger preserves exactly what Bot believed **immediately before** that outcome became observable:

- Epistemic state
- Evidence strength
- Observation lifecycle state
- Active nulls / unresolved uncertainties
- Market context hash
- DailyVoice/assessment references
- Age in trading sessions

Implementation: latest `DailyResearchAssessment` strictly before `min(eligible_evaluation_date, release_trade_date)`. Birth record fallback if no prior assessment. Post-outcome assessments cannot substitute (CF-CAL4).

## Outcome Accounting

Tracked independently at **T3**, **T5**, **T10**:

- Raw `cohort_mean_return` preserved
- Sign derived descriptively (POSITIVE/NEGATIVE/ZERO)
- Horizon, release date, evaluation status retained
- Missing/suspended outcomes never imputed as zero (CF-CAL11)

## Calibration Dimensions (Descriptive Only)

- Outcome distribution by epistemic state
- Outcome distribution by evidence-strength bucket
- T3/T5/T10 by lifecycle state
- Regime/context-conditioned results via cohort identity
- Always shows: N, eligible N, pending N, missing N, dependence flags

**No automatic edge inference.** Guards block:

- Binary correct/incorrect for NO_DISCOVERY (CF-CAL9)
- UNRESOLVED + positive labeled "correct" (CF-CAL10)
- Policy mutation from calibration (CF-CAL13)
- Trading authority from favorable results (CF-CAL14)

## Claim Maturity Semantics

Conservative operational thresholds (descriptive only):

| Label | Eligible N |
|---|---|
| `NO_FORWARD_EVIDENCE` | 0 |
| `IMMATURE` | 1–2 |
| `EARLY_SAMPLE` | 3–5 |
| `ACCUMULATING` | 6–14 |
| `REVIEWABLE` | 15+ |

These labels describe **sample maturity only**. They do NOT mean EDGE_ACTIVE, PROFITABLE, BUYABLE, or VALIDATED TRADING SIGNAL.

## Cohort Identity & Anti-Cherry-Picking

Pre-declared dimensions (not selected by realized returns):

- Birth regime, market transition
- Hypothesis family
- Epistemic state, evidence strength bucket
- Horizon, observation age bucket
- Outcome availability

Anti-cherry-picking audit blocks:

- Tiny-N cohort summaries (min N=3, CF-CAL6)
- Return-selected cohort definitions (CF-CAL7)

## Snapshot Immutability

Calibration snapshots are frozen at creation. Later T10 outcomes cannot rewrite earlier snapshots (CF-CAL8, CF-CAL18). Snapshots only include entries with `release_trade_date <= as_of_trade_date`.

## Daily Calibration Update (3K.2 Integration)

`production_daily_run_orchestrator.py` calls `update_calibration_ledger()` after assessments when `run_mode == LIVE_FORWARD`. Returns `calibration_result` in run output.

Properties:

- **Idempotent:** same source records → same ledger state
- **Crash-safe:** duplicate entries rejected via identity hash
- **Non-destructive:** completed historical entries never altered

## Bot Self-Knowledge Read Model

`build_self_knowledge_read_model()` generates research-only statements:

- "I currently have N LIVE_FORWARD observations."
- "Only M have reached T5; this is too little evidence."
- "Forward evidence maturity: NO_FORWARD_EVIDENCE — measurement infrastructure ready but no LIVE_FORWARD outcomes yet."

No self-congratulation. No profitability claims. No BUY/SELL.

## Historical Simulation

`run_calibration_mechanics_simulation()` runs sequential BACKFILL daily runs to verify:

- Ledger entry creation mechanics
- T3/T5/T10 staggered arrival paths
- Pre-outcome state freezing
- Snapshot immutability
- Pending → eligible transitions
- No future leakage
- No BACKFILL counted as forward
- Idempotent rebuild

All simulated evidence remains **NON_FORWARD**.

## CF-CAL1–18 Counterfactuals

| ID | Scenario | Result |
|---|---|---|
| CF-CAL1 | BACKFILL as forward evidence | Reject |
| CF-CAL2 | Outcome predates BirthRecord | Reject |
| CF-CAL3 | T5 not legally observable | Pending, not counted |
| CF-CAL4 | Post-outcome assessment substituted | Reject |
| CF-CAL5 | Duplicate outcome | Idempotent |
| CF-CAL6 | Tiny-N cohort as edge | Blocked |
| CF-CAL7 | Return-selected cohort | Reject |
| CF-CAL8 | Old snapshot rewritten by T10 | Reject |
| CF-CAL9 | NO_DISCOVERY scored as loss | Reject |
| CF-CAL10 | UNRESOLVED + positive = correct | Reject |
| CF-CAL11 | Missing treated as zero | Reject |
| CF-CAL12 | Crash during update | Safe resume |
| CF-CAL13 | Policy mutation from calibration | Blocked |
| CF-CAL14 | Trading authority from results | Blocked |
| CF-CAL15 | Replay mixed with LIVE_FORWARD | Reject |
| CF-CAL16 | Reordered records → same identity | Pass |
| CF-CAL17 | Dependence ignored | Flagged |
| CF-CAL18 | Future outcome in earlier snapshot | Reject |

## Regressions

Verified without weakening prior tests:

- Phase 3K.3 focused tests (11 tests)
- CF-CAL1–18
- Sequential calibration simulation
- Phase 3K.2, 3K.1, 3K.0
- Phase 3J.14A through 3J.10 frozen scientific suites
- Temporal integrity audit
- Trading isolation audit
- Hidden-answer audit
- Frozen policy hash audit

## Known Limitations

1. **No LIVE_FORWARD production data yet** — ledger is empty until real forward observations begin
2. **Maturity thresholds are operational/descriptive** — not scientific policy; may be revised with explicit audit
3. **No Streamlit UI** — read model exists for future narrator integration
4. **No deployment/scheduling activation** — daily runner contract from 3K.2 remains inactive
5. **Cohort aggregation is descriptive** — no statistical significance testing or edge claims

## Inputs Required Once LIVE_FORWARD Begins

1. Daily production runs with `run_mode=LIVE_FORWARD` and `counts_as_forward_evidence=true`
2. Immutable BirthRecords with valid temporal provenance
3. DailyResearchAssessment history preceding each outcome release
4. Legally released T3/T5/T10 outcomes via trading-session clock
5. Source/cutoff/policy identity hashes from frozen Research Brain

## Definition of Pass

**PASS** means the system can truthfully preserve and summarize what Mr.BOT claimed before future outcomes were known and compare those claims with subsequent legally observed evidence — without hindsight contamination, cherry-picking, policy tuning, or trading authority.

**PASS DOES NOT MEAN:** edge proven, profitability, good calibration, BUY/SELL ready, or deployment active.

---

**STOP_FORWARD_EVIDENCE_CALIBRATION_READY**
