# Phase 3J.9 — Cumulative Research Decision #2

## Branch / commits / PR

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3j9-cumulative-research-decision-aad2` |
| Base | `cursor/phase-3j8-multi-evidence-interpretation-aad2` (3J.8 PASS) |
| Prior STOP | `STOP_SECOND_EVIDENCE_INTERPRETED` |
| New STOP | `STOP_SECOND_RESEARCH_DECISION_FROZEN` |
| PR | (opened after push) |

## Architecture reused / added

### Reused from 3J.5
- `decide_next_action` / `build_research_decision` (via `proposition_experiment_interpreter`)
- `CandidateActionEvaluation`, `SearchAccountingContext`
- `NULL_UNCERTAINTY_MAP`, `COHORT_NULL_MAP`, surviving-null policy
- Confirmation guard, STOP semantics, search accounting thresholds
- Gate + persistence + production bridge pattern

### New modules
| Module | Role |
|--------|------|
| `second_experiment_research_decider.py` | Cumulative Decision #2 engine |
| `second_experiment_research_decision_records.py` | `SecondExperimentResearchDecisionEnvelope` |
| `second_experiment_research_decision_gate.py` | Eligibility / idempotency gate |
| `second_experiment_research_decision_persistence.py` | Durable DecisionRecord #2 storage |
| `production_second_experiment_research_decision.py` | Production integration |
| `bb_cumulative_research_decision_01_fixtures.py` | CF-CD1–10 counterfactuals |

### Production wiring
- `production_orchestrator.py` v3j9 — `decide_second_experiment=True` after 3J.8
- `OprProductionSessionRecord.second_experiment_research_decision`

## Lifecycle transition

```
STOP_SECOND_EVIDENCE_INTERPRETED
  → reconstruct cumulative research state (interpretation #2 + decision #1 + cumulative ledger)
  → reconstruct cumulative null ledger + dependence/incremental summaries
  → reconstruct search/accounting (experiments_attempted=2, overlap/weak-incremental penalties)
  → enumerate admissible actions including STOP variants
  → evaluate information value / independence / redundancy / evidence burden
  → select exactly ONE action OR STOP
  → persist ResearchDecisionRecord #2 (decision_ordinal=2)
  → STOP_SECOND_RESEARCH_DECISION_FROZEN
```

No Experiment #3 design or execution.

## Cumulative-history reconstruction

Decision #2 consumes:
- Proposition + frozen contract
- First interpretation (Evidence #1) + first decision (Decision #1)
- Second interpretation (Evidence #2) + EpistemicUpdate #2
- `cumulative_assessment` (dependence, incremental contribution, cumulative null ledger)

Identity: `compute_cumulative_research_state_identity(proposition_hash, resulting_epistemic_state, second_interpretation_identity_hash, first_decision_hash)`.

## Null-ledger handling

- Surviving nulls derived from cumulative ledger (`STILL_PLAUSIBLE`, `WEAKENED`)
- Priority: `STILL_PLAUSIBLE` falsification targets rank above re-testing `WEAKENED` nulls
- Nulls already addressed by Exp #1/#2 rejected (`null_already_materially_addressed_by_cumulative_evidence`)
- Untested standard nulls (`population_concentration`, `context_instability`) enumerated at lower rank

## Evidence-burden accumulation

Search context for Decision #2:
- `experiments_attempted = 2`
- Complexity += second-experiment increment + overlap penalty (≥0.85) + weak-incremental penalty
- Burden escalates to `HIGH` when overlap ≥0.85 or incremental strength WEAK/INSUFFICIENT
- Burden does **not** reset after favorable results

## STOP policy

STOP candidates compete on equal footing:
- `STOP_LOW_INCREMENTAL` — weak incremental + high sample dependence, no STILL_PLAUSIBLE nulls
- `STOP_NO_MATERIAL_NULL` — no STILL_PLAUSIBLE nulls remain
- `STOP_BUDGET` — search budget exhausted
- `STOP_NO_INFORMATIVE_ACTION` — fallback when all continuation candidates rejected
- `STOP_REJECT` — cumulative negative/contradictory evidence

## Remaining-null prioritization

Ranked by scientific value, not fixed order:
1. `STILL_PLAUSIBLE` nulls (highest information gain)
2. Untested standard nulls (moderate gain)
3. `WEAKENED` null re-tests (low gain, usually rejected under burden)

## Replication vs falsification policy

- `SEEK_REPLICATION` requires `independent_replication_earned`: major nulls addressed, proposition viable, low expected overlap
- Blocked under high overlap, weak incremental support, contradictory/conflict history
- Continued falsification preferred when material `STILL_PLAUSIBLE` nulls exist
- Mechanical continuation from Decision #1 blocked (`mechanical_sequencing_decision1_falsification`)

## DecisionRecord #2

Persisted envelope includes: decision_ordinal=2, interpretation/update refs, first_decision refs, cumulative_research_state_identity, cumulative_null_ledger, candidate_evaluations, rejected actions, search_accounting, dependence/incremental summaries, confirmation_bias_guard_applied, mechanical_sequencing_blocked, third_experiment_generated=false.

## Counterfactuals (CF-CD1–10)

| ID | Result |
|----|--------|
| CF-CD1 | Different search burden → different decision |
| CF-CD2 | Different remaining nulls → different action |
| CF-CD3 | Dependent history → replication rejected |
| CF-CD4 | Major nulls addressed → replication admissible |
| CF-CD5 | STILL_PLAUSIBLE null → falsification wins |
| CF-CD6 | Weak incremental → STOP competes |
| CF-CD7 | Budget exhausted → STOP |
| CF-CD8 | Negative evidence → no confirmation seeking |
| CF-CD9 | Ordering invariant |
| CF-CD10 | No Experiment #3 leakage |

All PASS.

## Regression

All targeted suites PASS including 3J.9, 3J.8–3J.2, 3J.6A.

## Real diagnostic

Consumed persisted Phase 3J.8 cumulative state for `prop-efb650d9bd5c451f`:

| Field | Value |
|-------|-------|
| Epistemic state | SUPPORTED → SUPPORTED |
| Evidence #1 | episode_artifact → WEAKENED (MODERATE) |
| Evidence #2 raw | MODERATE |
| Evidence #2 incremental | WEAK |
| Row overlap | 0.977 |
| Independent replication | false |
| Null ledger | episode_artifact WEAKENED, directional_reversal WEAKENED |
| Evidence burden | HIGH (2 experiments, overlap penalty) |
| Decision #2 | **STOP** (`STOP_LOW_INCREMENTAL`) |
| Chosen action | HOLD_UNRESOLVED |
| Replication | rejected (4 reasons) |
| Mechanical sequencing | blocked |
| Confirmation guard | applied |
| Experiment #3 | not generated |

STOP is the scientifically valid outcome: both major nulls weakened but not eliminated, second experiment added only WEAK incremental evidence under HIGH sample dependence, and further search cost is not justified.

## Hidden-answer audit

PASS — no forbidden tokens in decision modules.

## Frozen artifact integrity

Prior phase hashes unchanged (engine, SAG, dormancy, integration).

## Known limitations

- Synthetic CF-CD context uses constructed second-interpretation envelopes when panel execution unavailable; real diagnostic uses full production chain.
- Untested tertiary nulls (`population_concentration`, `context_instability`) enumerated but typically rejected under HIGH burden without STILL_PLAUSIBLE priority.

## Next boundary

**STOP_SECOND_RESEARCH_DECISION_FROZEN** — Phase 3J.10 would design Experiment #3 (not in scope).
