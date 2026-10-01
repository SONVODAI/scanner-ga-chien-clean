# Phase 3J.5 — Research Decision After First Evidence

## Status: PASS

**Branch:** `cursor/phase-3j5-research-decision-aad2`  
**Hard STOP:** `STOP_RESEARCH_DECISION_FROZEN` — no second experiment generation or execution

---

## Scientific objective

> Given the proposition, scientific intent of the first experiment, frozen InterpretationContract, executed ToolResult, and authoritative EpistemicUpdateRecord, can Mr.BOT autonomously decide what the scientifically justified NEXT RESEARCH ACTION should be — including deciding to STOP — without executing that action?

**Evidence:** Real diagnostic on persisted 3J.4 state for `prop-efb650d9bd5c451f` selected `SEEK_FALSIFICATION` targeting surviving null `directional_reversal`; confirmatory replication rejected by confirmation-bias guard; no second experiment generated.

---

## Production lifecycle

```
STOP_FIRST_EVIDENCE_INTERPRETED
  → reconstruct authoritative research state from interpretation envelope
  → enumerate scientifically admissible next actions
  → evaluate surviving nulls / redundancy / search burden
  → select exactly ONE action OR STOP
  → persist ResearchDecisionRecord (+ audit envelope)
  → STOP_RESEARCH_DECISION_FROZEN
```

Orchestrator flags (additive, backward compatible):
- `decide_first_experiment=True` (requires `interpret_first_experiment=True`)

---

## Architecture

### Reused (3I.7 / OPR)
| Component | Role |
|-----------|------|
| `decide_next_action()` | Baseline evidence-causal action from frozen `decision_mapping` |
| `build_research_decision()` | Persistable `ResearchDecisionRecord` |
| `NextResearchAction` vocabulary | SEEK_FALSIFICATION, SEEK_REPLICATION, HOLD_UNRESOLVED, ABANDON |
| `InterpretationContract.decision_mapping` | Pre-result frozen mapping |

### Added (3J.5)
| Module | Role |
|--------|------|
| `first_experiment_research_decision_records.py` | Decision envelope, STOP boundary, audit fields |
| `first_experiment_research_decider.py` | Surviving-null priority, confirmation guard, STOP semantics |
| `first_experiment_research_decision_gate.py` | Eligibility + idempotency |
| `first_experiment_research_decision_persistence.py` | Durable decision storage |
| `production_first_experiment_research_decision.py` | Production integration |
| `bb_first_experiment_research_decision_01_fixtures.py` | CF-RD1–10 |

**Extended (additive):**
- `production_orchestrator.py` v3j5 — `decide_first_experiment` flag
- `production_persistence.py` — `first_experiment_research_decision`

**Explicitly NOT invoked:** `on_epistemic_update_completed`, experiment pipeline, falsification package generation.

---

## Decision policy

1. **Authoritative inputs only** — consumes 3J.4 interpretation envelope; does not re-interpret evidence
2. **Baseline** — `decide_next_action()` from frozen contract
3. **Candidate enumeration** — TEST_NEXT_NULL per surviving null, CONTINUE_FALSIFICATION, SEEK_REPLICATION, STOP variants
4. **Surviving-null priority** — falsification of alive nulls ranks above confirmatory replication
5. **Confirmation addiction guard** — SUPPORTING + same uncertainty → reject SEEK_REPLICATION (CF-RD1)
6. **Redundancy penalty** — actions reproducing first-experiment cohort rejected (CF-RD6)
7. **Search budget** — exhausted budget → STOP (CF-RD3, CF-RD9)
8. **STOP is first-class** — STOP_BUDGET, STOP_NO_INFORMATIVE_ACTION, STOP_REJECT

Action families map to existing `NextResearchAction` codes; no parallel vocabulary.

---

## Real diagnostic (`prop-efb650d9bd5c451f`)

| Field | Value |
|-------|-------|
| Epistemic state | SUPPORTED |
| First experiment null addressed | episode_artifact |
| Surviving nulls | directional_reversal |
| Interpretation | HIGH / SUPPORTS / MODERATE |
| Selected action | **SEEK_FALSIFICATION** (TEST_NEXT_NULL) |
| Target uncertainty | directional_effect_full_universe |
| Target null | directional_reversal |
| Expected information | HIGH |
| SEEK_REPLICATION | **Rejected** (confirmation guard + redundancy) |
| Confirmation bias guard | Applied |
| Second experiment generated | **No** |
| STOP | `STOP_RESEARCH_DECISION_FROZEN` |

Artifact: `artifacts/02_real_proposition_diagnostic.json`

---

## Counterfactuals (CF-RD1–10): 10/10 PASS

Including confirmation temptation rejection, surviving-null sensitivity, budget STOP, weak evidence continuation, negative evidence non-confirmation, redundancy rejection, ordering invariance, science-over-convenience, no-informative STOP, execution leakage guard.

---

## Regression

| Suite | Result |
|-------|--------|
| 3J.5 | 10/10 |
| CF-RD1–10 | 10/10 |
| 3J.4 | 10/10 |
| 3J.3 | 9/9 |
| 3J.2 | 7/7 |
| 3J.0 | 20/20 |
| 3I.7 | 11/11 |
| Frozen 3I hashes | Unchanged |

---

## Hidden-answer audit

No encoding of focal dates, known observations, or proposition-specific decision logic in 3J.5 modules.

Artifact: `artifacts/03_hidden_answer_grep.json` — **clean**

---

## Known limitations

1. Search accounting uses first-experiment stub (complexity=3.0, cardinality=1); full planner ledger not yet wired to OPR production sessions.
2. `ResearchDecisionRecord` uses existing 3I.7 schema; extended audit fields live in decision envelope wrapper.
3. Synthesis hook (`on_epistemic_update_completed`) deferred — immediate decision is transitional per 3I.13 authority model.

---

## Explicit remaining boundary (Phase 3J.6+)

- Second experiment package generation
- Experiment execution loop
- `on_epistemic_update_completed` / multi-evidence synthesis in production path
- Frontier / dormancy / edge activation / BUY-SELL

---

## Commits / PR

See branch `cursor/phase-3j5-research-decision-aad2` for commits and PR link.
