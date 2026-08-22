# Phase 3J.12 — N-Experiment Research Generalization

## Branch / commits / PR

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3j12-n-experiment-research-generalization-aad2` |
| Base | `cursor/phase-3j11-blind-autonomous-research-exam-aad2` (3J.11 PASS) |
| Prior STOP | `STOP_BLIND_EXAMINATION_COMPLETE` |
| New STOP | `STOP_N_EXPERIMENT_GENERALIZATION` |
| PR | (opened after push) |

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

## Ordinal >= 3 diagnostic

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

3J.12 + 3J.11 + 3J.10 + 3J.9 PASS. Frozen ordinal-2 hashes preserved via default parameters.

## Known limitations

1. Follow-on **candidate generation** still uses 3J.6 second-experiment generator — ordinal >= 3 may produce `NO_FAITHFUL` silence when no admissible candidate exists (fail-closed, not bypass)
2. Full happy-path Exp #3 execute/interpret/decide requires proposition journey that continues with faithful candidates
3. Birth decision hash remains lineage anchor in envelope (compatibility field `first_decision_hash`)

## Explicit next boundary

**STOP_N_EXPERIMENT_GENERALIZATION** — no policy tuning from blind outcomes, no edge activation, no continuous live research.
