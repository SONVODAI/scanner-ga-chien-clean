# Phase 3K.1 — Living Research Observation & Daily Assessment

**Stop boundary:** `STOP_LIVING_RESEARCH_OBSERVATION_READY`  
**Branch:** `cursor/phase-3k1-living-research-observation-aad2`  
**Base:** `cursor/phase-3k0-production-research-observation-foundation-aad2` (PR #74)  
**Status:** PASS

---

## Summary

Phase 3K.1 extends the Phase 3K.0 observation foundation so Mr.BOT produces **auditable daily living assessments** through time. Each trading day the system answers: what does Bot believe today, what changed since the prior session, why belief changed or did not change, and what Bot is waiting for.

Birth records remain **immutable**. Daily assessments are **append-only**. Forward T3/T5/T10 outcomes arrive only when legally eligible. No trading authority is granted.

**Verdict:** Three-layer temporal model operational. CF-LIVE1–14 pass. Historical 10-day replay demonstrates unchanged-belief days, market deltas, and forward horizon arrivals without forcing artificial state changes.

---

## Three-Layer Temporal Model

| Layer | Record | Mutability | Purpose |
|---|---|---|---|
| A | `ResearchObservationBirthRecord` | Immutable (3K.0) | What Bot believed at birth |
| B | `DailyResearchAssessment` | Append-only daily | What Bot believes TODAY given legal information |
| C | `ResearchObservationOutcomeRecord` | Append-only outcomes | What T3/T5/T10 actually did when eligible |

These layers are never merged into one mutable record.

---

## Architecture

### New modules (`modules/edge_research/opr_bridge/`)

| Module | Purpose |
|---|---|
| `production_living_observation_records.py` | DailyResearchAssessment, DailyVoiceContract, DailyResearchSummary, MarketDelta, EpistemicDelta, lifecycle enums |
| `production_living_observation_persistence.py` | Append-only persistence for assessments, outcomes, summaries, voices |
| `production_market_delta.py` | Market context delta (regime, breadth, transition, dispersion, cohort relative) |
| `production_forward_outcome_evaluator.py` | T3/T5/T10 outcome ingestion with temporal eligibility checks |
| `production_observation_lifecycle.py` | Lifecycle state derivation, stale-copy detection, artificial-change rejection |
| `production_daily_assessment.py` | Daily assessment orchestrator and summary builder |
| `production_daily_voice.py` | Vietnamese DailyVoiceContract renderer (structured-state-only) |
| `production_living_read_model.py` | TODAY / OBSERVATION DETAIL / HISTORY read model (no Streamlit) |
| `production_living_research_observation.py` | Daily living assessment runner + HISTORICAL_MULTI_DAY_REPLAY |
| `bb_living_research_observation_01_fixtures.py` | CF-LIVE1–14 counterfactuals |

### Extended module

| Module | Change |
|---|---|
| `production_observation_isolation.py` | Audit scope extended to all 3K.1 modules |

### Data stores (`data/edge_research/production_observations/`)

```
{observation_id}.json                    # immutable birth (3K.0)
daily_assessments/{assessment_id}.json   # append-only daily state
forward_outcomes/{outcome_record_id}.json
daily_summaries/{summary_id}.json
daily_voices/{assessment_id}.json
living_observation_index.json
daily_assessment_ledger.jsonl
forward_outcome_ledger.jsonl
daily_summary_ledger.jsonl
```

---

## DailyResearchAssessment Schema

Minimum fields implemented:

- `assessment_id`, `observation_id`, `assessment_trade_date`, `assessment_timestamp`
- `previous_assessment_id`, `birth_record_hash`
- `cutoff_provenance`, current/previous market context identity/hash
- `market_delta` (MarketDelta struct)
- `new_evidence_since_prior`, `forward_outcomes_newly_available`
- `current_epistemic_state`, `previous_epistemic_state`, `epistemic_delta`
- `null_ledger_current`, `null_ledger_delta`
- `contradictions`, `dependence_warnings`, `unresolved_uncertainties`, `current_limitations`
- `current_research_status`, `current_lifecycle_status`, `observation_lifecycle_state`
- `what_changed`, `what_did_not_change`, `why_belief_changed_or_not`
- `what_bot_is_waiting_for`, `next_eligible_evaluation_horizon/date`
- `observation_age_trading_days`, `change_flags`, `stale_copy_risk`
- `assessment_identity_hash` (deterministic, idempotent)
- `shadow_authority` (research_only=true, all trading flags false)

---

## Market Delta Semantics

`MarketDelta` captures meaningful change categories, not investment conclusions:

| Field | Values |
|---|---|
| `regime_changed` | bool — research_market_state changed |
| `breadth_direction` | STRENGTHENED / WEAKENED / UNCHANGED / UNKNOWN |
| `transition_direction` | ACCELERATED / DECELERATED / CHANGED / UNCHANGED |
| `dispersion_changed` | market_real vs market_forecast spread changed |
| `cohort_relative_changed` | implicated cohort mean return shifted |
| `compatibility_direction` | MORE_COMPATIBLE / LESS_COMPATIBLE / UNCHANGED / UNKNOWN |

Market delta is evidence/context only — never BUY/SELL authority.

---

## Belief Delta Semantics

Change kinds strictly distinguished:

| Flag | Meaning |
|---|---|
| `DATA_CHANGED` | Underlying data panel changed at cutoff |
| `MARKET_CHANGED` | Market context delta detected |
| `EVIDENCE_CHANGED` | New forward outcome or evidence arrived |
| `BELIEF_CHANGED` | Epistemic state changed (requires relevant evidence) |
| `UNCHANGED` | No material change |

Belief change is rejected without relevant evidence (`reject_artificial_belief_change`). Outcome evidence does not auto-upgrade/downgrade epistemic state (`automatic_belief_change: false`).

---

## Observation Lifecycle

Derived states (presentation layer, does not mutate BirthRecord):

`BORN` → `ACTIVE_PENDING` → `STRENGTHENED` / `UNCHANGED` / `CHALLENGED` / `WEAKENED` → `RESOLVED` / `REJECTED` / `EXPIRED` / `SILENCE`

Lifecycle is derived from structured evidence and forward outcome interpretation — not from return > 0 => good.

---

## T3/T5/T10 Forward Outcome Evaluator

- Evaluates horizons only when `assessment_trade_date >= eligible_evaluation_date`
- Early outcomes rejected (`CF-LIVE4`: T5 before eligible date)
- Uses panel `t3_return`, `t5_return`, `t10_return` fields
- Appends `ResearchObservationOutcomeRecord` — never modifies BirthRecord
- Outcome interpretation per frozen `ForwardEvaluationContract` — no automatic REJECTED/CONFIRMED
- Missing data handled explicitly (`MISSING_DATA` status)

---

## DailyResearchSummary

Aggregates per trading day:

- Market state, most meaningful market delta
- New observations born, active observations reassessed
- Strengthened / weakened-challenged / resolved-rejected counts
- Silence/no-discovery status
- Newly arrived forward evidence
- Most important unresolved question, what Bot is waiting for
- Provenance hash

Honest daily voice on NO_DISCOVERY / SILENCE days (`CF-LIVE12`).

---

## Vietnamese Narrative Contract (DailyVoiceContract)

Ten structured Vietnamese Q&A fields, all tracing to structured assessment state:

1. Hôm nay tôi thấy gì?
2. So với phiên trước, điều gì thay đổi?
3. Market thay đổi thế nào?
4. Evidence mới nào xuất hiện?
5. Quan điểm của tôi thay đổi hay không?
6. Nếu không thay đổi, tại sao?
7. Điều gì hiện chống lại hypothesis?
8. Tôi vẫn chưa biết điều gì?
9. Tôi đang chờ điều gì tiếp theo?
10. Observation cũ nào đáng xem lại hôm nay?

Canonical technical terms remain English. No BUY/SELL wording. Narrator cannot upgrade scientific state (`CF-LIVE11`).

---

## Stale-Copy Prevention

`stale_copy_risk` flag set when:
- Belief unchanged AND market context changed AND temporal explanation text identical to prior day

Each trading day must reassess against today's legally available context. When belief is unchanged, `why_belief_changed_or_not` explicitly explains why new market/data was insufficient.

Example from historical replay (2026-08-02):
> "Epistemic state remains UNRESOLVED. Market context changed (regime:EARLY_RECOVERY->STRESS; breadth:UNKNOWN; transition:CHANGED; cohort_relative:changed), but no relevant new evidence arrived to justify changing belief."

---

## No-Fake-Change Protection

- `reject_artificial_belief_change()` blocks epistemic changes without evidence (`CF-LIVE10`)
- Forward outcomes never set `automatic_belief_change: true`
- Daily assessment identity is deterministic — same cutoff + data + policy + prior state → same hash (`CF-LIVE1`)

---

## Historical Multi-Day Replay

`HISTORICAL_MULTI_DAY_REPLAY` over 10 trading days (2026-07-23 → 2026-08-02):

| Demonstration | Result |
|---|---|
| Unchanged-belief days | 2026-07-23, 2026-07-24, 2026-07-26 (and others) |
| Market delta days | regime/breadth/transition changes recorded |
| Forward horizon arrival | T3 outcomes on 2026-07-28, 2026-07-30 |
| Forced state change | None — no artificial change injected |
| Counts as forward evidence | **false** |

---

## UI Read Model (No Streamlit)

Three sections exposed via `production_living_read_model.py`:

| Section | Contents |
|---|---|
| TODAY | Daily voice, market/belief deltas, active observations, forward evidence, unresolved questions |
| OBSERVATION DETAIL | Birth snapshot, assessment timeline, T3/T5/T10, current state, null history |
| HISTORY | Prior daily summaries, silence days, calibration placeholders |

---

## Counterfactual Results (CF-LIVE1–14)

| ID | Description | Result |
|---|---|---|
| CF-LIVE1 | Same assessment rerun → idempotent | PASS |
| CF-LIVE2 | Market changes, evidence does not → belief unchanged OK | PASS |
| CF-LIVE3 | Relevant new evidence → assessment reflects it | PASS |
| CF-LIVE4 | T5 before eligible date → reject | PASS |
| CF-LIVE5 | T3 contradicts birth → contradiction recorded, no auto REJECTED | PASS |
| CF-LIVE6 | T3 supports birth → evidence recorded, no auto CONFIRMED | PASS |
| CF-LIVE7 | BirthRecord rewrite → reject | PASS |
| CF-LIVE8 | Prior assessment rewrite → reject | PASS |
| CF-LIVE9 | Stale-copy audit reflects stale_copy_risk flag | PASS |
| CF-LIVE10 | Artificial belief change without evidence → reject | PASS |
| CF-LIVE11 | Narrator upgrades scientific state → reject | PASS |
| CF-LIVE12 | NO_DISCOVERY day → DailyResearchSummary exists | PASS |
| CF-LIVE13 | Multiple active observations preserved | PASS |
| CF-LIVE14 | Trading write attempted → blocked | PASS |

---

## Trading Isolation

All 3K.1 modules audited. No forbidden imports or write paths to trading subsystems. Every assessment and summary carries:

```
research_only = true
trading_authority = false
buy_signal = false
sell_signal = false
edge_active = false
```

---

## Temporal Integrity

- All 3K.0 cutoff rules remain authoritative
- Today's assessment sees only information available by today's cutoff
- T5 cannot appear before eligible business-day offset
- Later outcomes cannot alter earlier DailyResearchAssessment
- Fail closed on provenance ambiguity

---

## Regressions

| Suite | Status |
|---|---|
| `test_edge_research_opr_phase_3k1.py` | PASS |
| `test_edge_research_opr_phase_3k0.py` | PASS |
| `test_edge_research_opr_phase_3j14a.py` | PASS |
| Phase 3J.14 CF-CG | PASS |
| Phase 3J.13 CF-FG | PASS |
| Phase 3J.12 CF-NX | PASS |
| Phase 3J.11 CF-BR | PASS |
| Phase 3J.10 CF-ARL1–12 | PASS |

Frozen 3I/3J scientific semantics unchanged. Policy hash integrity preserved.

---

## Known Limitations

1. **No continuous live observation** — infrastructure only; no cron/systemd
2. **No Streamlit UI** — read model contract only
3. **Epistemic auto-update conservative** — forward outcomes record evidence but rarely auto-change epistemic state without explicit contract rules; this preserves frozen 3I/3J semantics
4. **No scientifically justified expiry policy** — long-lived observations report waiting state rather than inventing expiry durations
5. **Summary idempotency** — daily summaries append on rerun (assessments are idempotent)
6. **Calibration placeholders** — HISTORY read model includes placeholders for future calibration data

---

## Exact Next Boundary

**Phase 3K.2** (not started):
- Streamlit "Bot speaks today" UI consuming read model
- Continuous daily observation scheduling
- Calibration feedback from forward outcomes
- Observation expiry policy when scientifically justified

**Hard stop:** `STOP_LIVING_RESEARCH_OBSERVATION_READY`

---

## Artifacts

```
diagnostics/phase_3k1_living_research_observation/
├── run_phase_3k1.py
├── PHASE_3K1_REPORT.md
└── artifacts/
    ├── 00_frozen_policy_hashes.json
    ├── 01_cf_live_summary.json
    ├── 02_historical_multi_day_replay.json
    ├── 03_read_model_contract.json
    ├── 04_trading_isolation_audit.json
    ├── 05_hidden_answer_audit.json
    ├── 06_regression_summary.json
    └── 07_audit_summary.json
```
