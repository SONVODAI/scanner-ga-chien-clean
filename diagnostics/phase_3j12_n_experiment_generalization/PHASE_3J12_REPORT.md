# Phase 3J.12 — N-Experiment Research Generalization

## Branch / commits / PR

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3j12-n-experiment-research-generalization-aad2` |
| Base | `cursor/phase-3j11-blind-autonomous-research-exam-aad2` (3J.11 PASS) |
| Prior STOP | `STOP_BLIND_EXAMINATION_COMPLETE` |
| New STOP | `STOP_N_EXPERIMENT_GENERALIZATION` |
| Commit | `8d8b63c22` |
| PR | [#70](https://github.com/SONVODAI/scanner-ga-chien-clean/pull/70) |

## Ordinal-2 architectural breaks removed

| Break | Resolution |
|-------|------------|
| `ARCHITECTURAL_MAX_FOLLOW_ON_ORDINAL = 2` | Removed; ordinal >= 3 routes to generic follow-on core |
| `research_state_identity` vs `cumulative_research_state_identity` | `follow_on_research_decision_adapter.normalize_prior_decision()` |
| Pairwise-only interpretation (Exp #1 vs #2) | `follow_on_experiment_interpreter` uses `build_rolling_cumulative_assessment` |
| Hardcoded `experiment_ordinal == 2` gates | Parameterized `expected_ordinal` (default 2 preserves frozen behavior) |
| Decision identity chained to `first_decision_hash` only | `compute_follow_on_decision_identity_hash(prior_decision_hash, decision_ordinal)` |

## Generic history architecture

- `experiment_history[]` remains authoritative for ordinal >= 3
- Legacy `first_*` / `second_*` flat fields synced for ordinals 1–2 (unchanged)
- Controller: ordinal 2 → frozen `production_second_experiment_*`; ordinal >= 3 → `follow_on_experiment_core`

## New modules

| Module | Role |
|--------|------|
| `follow_on_research_decision_adapter.py` | Normalize prior decisions across ordinals |
| `follow_on_experiment_records.py` | N-parameterized identity hashes and stop boundaries |
| `follow_on_experiment_design_gate.py` | Design eligibility for ordinal >= 3 |
| `follow_on_experiment_core.py` | Generic design/execute/interpret/decide |
| `follow_on_experiment_interpreter.py` | Rolling cumulative interpretation |
| `bb_n_experiment_generalization_01_fixtures.py` | CF-NX1–12 |

## Exact ordinal-2 assumptions audited (3J.6–3J.9)

### 3J.6 Design
| Assumption | Location | Generic resolution |
|------------|----------|-------------------|
| Prior decision is `FirstExperimentResearchDecisionEnvelope` | `production_second_experiment_design.py` | Ordinal 2: unchanged. Ordinal >= 3: `normalize_prior_decision()` + `as_first_decision_envelope_view()` |
| Design hash uses `research_state_identity` only | `second_experiment_design_gate.py` | Adapter maps `cumulative_research_state_identity` → canonical `research_state_identity` |
| Overlap vs birth experiment only | `second_experiment_candidates.py` | Unchanged at ord 2; ord >= 3 reuses generator (limitation documented) |
| `experiment_ordinal=2` in package | `second_experiment_pipeline._build_package` | Parameterized `experiment_ordinal` (default 2) |
| First-decision hash verification gate | `validate_second_experiment_design_eligibility` | Ordinal >= 3: `validate_follow_on_design_eligibility` (no first-hash re-verify) |

### 3J.7 Execution
| Assumption | Location | Generic resolution |
|------------|----------|-------------------|
| Gate requires `package.experiment_ordinal == 2` | `second_experiment_execution_gate.py` | `expected_ordinal` param (default 2) |
| Novelty vs birth execution only | `second_experiment_executor.py` | Unchanged (birth anchor preserved) |
| Envelope `experiment_ordinal=2` | `build_second_execution_envelope` | Parameterized (default 2) |

### 3J.8 Interpretation
| Assumption | Location | Generic resolution |
|------------|----------|-------------------|
| Pairwise `build_cumulative_assessment` (E1 vs E2) | `second_experiment_evidence_interpreter.py` | Ordinal 2: frozen. Ordinal >= 3: `build_rolling_cumulative_assessment` |
| Gate requires `execution.experiment_ordinal == 2` | `second_experiment_interpretation_gate.py` | `expected_ordinal` param (default 2) |
| Identity keyed to `first_interpretation_id` | `compute_second_interpretation_identity_hash` | Ordinal >= 3: `compute_follow_on_interpretation_identity_hash` includes ordinal |
| Prior epistemic from birth only | Interpreter | Ordinal >= 3: immediate prior (N-1) for transition |

### 3J.9 Decision
| Assumption | Location | Generic resolution |
|------------|----------|-------------------|
| `decision_ordinal=2` hardcoded in identity hash | `compute_second_decision_identity_hash` | Ordinal >= 3: `compute_follow_on_decision_identity_hash(prior_decision_hash, N)` |
| `cumulative_research_state_identity` chains to `first_decision_hash` | `compute_cumulative_research_state_identity` | Ordinal >= 3: `compute_follow_on_research_state_identity(prior_decision_hash, N)` |
| Gate requires `interpretation.experiment_ordinal == 2` | `second_experiment_research_decision_gate.py` | Ordinal 2 path unchanged; ord >= 3 uses follow-on decide with rebuilt envelope |
| Decider anchors to birth decision envelope | `decide_second_experiment_research_action` | Birth anchor preserved; search burden seeded from prior decision accounting |

### Safest abstraction chosen

**Dual-path controller** (not monolithic rewrite):
- `ordinal == 2` → frozen `production_second_experiment_*` (zero semantic change)
- `ordinal >= 3` → `follow_on_experiment_core` composing same scientific primitives with N-parameterized gates/records

No bypass of architectural conflicts: when 3J.6 generator produces `NO_FAITHFUL_SECOND_EXPERIMENT` at ordinal 3, execution fail-closes rather than substituting.

## Persistence / idempotency

- Ordinals 1–2: existing flat fields + indexes unchanged
- Ordinal >= 3: `experiment_history[]` canonical; shared second-experiment persistence indexes keyed by identity hashes including ordinal

## Anti-loop / search burden

- Search complexity/cardinality seeded from prior decision `search_accounting` in follow-on decide path
- Rolling cumulative assessment prevents false independence when E3 overlaps E1 heavily
- No ordinal-number confidence inflation (CF-NX12)

## Hidden-answer audit

PASS — no BLIND class labels, benchmark seeds, or expected outcomes in research modules.

## Frozen artifact integrity

3J.2–3J.9 + 3J.10 + 3J.11 regression PASS at current HEAD (`8d8b63c22`).

## Ordinal >= 3 diagnostic (refreshed)

Seed 101 synthetic panel, `max_experiment_iterations=4`:
- Reaches Experiment #3 **design** with `experiment_ordinal=3`
- No `architectural_break` errors
- Fail-closed on `NO_FAITHFUL_SECOND_EXPERIMENT` silence package (execution correctly rejected)

## Blind longer-budget comparison (diagnostic only)

Sample of 4 frozen 3J.11 cases re-run with `max_experiment_iterations=4`:
- **Critical false positives: 0** (no degradation in false-positive restraint)
- Policies unchanged — comparison only

## CF-NX counterfactuals

All CF-NX1–12 PASS.

## Regression

| Suite | Result |
|-------|--------|
| Phase 3J.12 tests + CF-NX | PASS |
| Phase 3J.11 | PASS |
| Phase 3J.10 | PASS |
| Phase 3J.9 | PASS |
| Phase 3J.2–3J.8 | 64/64 PASS |

Frozen ordinal-2 hashes preserved via default parameters.

## Known limitations

1. Follow-on **candidate generation** still uses 3J.6 second-experiment generator — ordinal >= 3 may produce `NO_FAITHFUL` silence when no admissible candidate exists (fail-closed, not bypass)
2. Full happy-path Exp #3 execute/interpret/decide requires proposition journey that continues with faithful candidates
3. Birth decision hash remains lineage anchor in envelope (compatibility field `first_decision_hash`)

## Explicit next boundary

**STOP_N_EXPERIMENT_GENERALIZATION** — no policy tuning from blind outcomes, no edge activation, no continuous live research.
