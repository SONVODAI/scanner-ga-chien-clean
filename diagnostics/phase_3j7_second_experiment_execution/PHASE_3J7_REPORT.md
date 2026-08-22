# Phase 3J.7 — Second-Experiment Execution

## Status: PASS

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3j7-second-experiment-execution-aad2` |
| Commit | `2f28b5e2d` |
| PR | #65 |
| Base | `cursor/phase-3j6a-scientific-novelty-audit-aad2` @ `838788901` |
| Hard STOP | `STOP_SECOND_EXPERIMENT_EXECUTED` |
| Prior STOP | `STOP_SECOND_EXPERIMENT_DESIGNED` |

## Scientific objective

Can production faithfully execute the frozen autonomous `SecondExperimentPackage` from 3J.6, preserving scientific identity, target null, novelty audit, provenance, and exact execution semantics, and persist an auditable ToolResult #2 — without interpreting the result?

**Answer: Yes.** The executor is an instrument; it does not interpret Experiment #2.

## Architecture

### Reused from 3J.3 (first-experiment execution)

- Execution eligibility pattern (`ExecutionEligibility`, fail-closed)
- Exact binding (`bind_frozen_experiment_spec`, `verify_binding_identity`)
- Tool resolver (`resolve_execution_spec`)
- Controlled executor (`execute_frozen_experiment`)
- ToolResult envelope structure (adapted for ordinal 2)
- Provenance hashing (`compute_panel_provenance_hash`, `compute_execution_identity_hash`)
- Idempotency index lookup
- Interpretation firewall (`FORBIDDEN_ENVELOPE_INTERPRETATION_KEYS`)

### Added for 3J.7

| Module | Role |
|--------|------|
| `second_experiment_execution_adapter.py` | Thin adapter: `SecondExperimentPackage` → `InitialExperimentPackage` for 3J.3 binding reuse |
| `second_experiment_execution_records.py` | ToolResult #2 envelope, `STOP_SECOND_EXPERIMENT_EXECUTED` |
| `second_experiment_execution_gate.py` | Novelty-aware eligibility; blocks scientific redundancy (3J.6A Case B) |
| `second_experiment_executor.py` | Controlled execution; no interpretation |
| `second_experiment_execution_persistence.py` | Durable `second_experiment_executions/` + index |
| `production_second_experiment_execution.py` | Production integration |
| `bb_second_experiment_execution_01_fixtures.py` | CF-SE1–10 |

### Production integration

- `production_orchestrator.py`: `execute_second_experiment=True` extends lifecycle after 3J.6
- `production_persistence.py`: `second_experiment_execution` field on session record

## Lifecycle transition

```
STOP_SECOND_EXPERIMENT_DESIGNED
  → second-experiment eligibility gate
  → novelty decomposition enforcement (3J.6A)
  → exact scientific binding (3J.3 reuse via adapter)
  → controlled execution (exactly ONE Experiment #2)
  → ToolResult #2 persistence
→ STOP_SECOND_EXPERIMENT_EXECUTED
```

No EpistemicUpdate #2, no Research Decision #2, no Experiment #3 design.

## Eligibility gate

Before execution verifies:

- Package exists, ordinal = 2, disposition = SELECTED, status = NOT_EXECUTED (or valid idempotent replay)
- Proposition and ResearchDecisionRecord identity/hash match
- Target null matches frozen decision intent (`directional_reversal`)
- Candidate executable; spec matches package; no binding mutation
- Novelty decomposition present; **not** `SCIENTIFIC_REDUNDANCY`
- Tool in registry; no fallback substitution
- Population/outcome representable on panel
- Fail closed on stale provenance or conflicting ToolResult #2 identity

## Novelty enforcement (3J.6A)

Execution consumes/reconstructs novelty decomposition via `decompose_novelty()`.

| Case | Row overlap | Scientific question | Gate |
|------|-------------|---------------------|------|
| A — high reuse, new question | High | Distinct | **Admit** (CF-SE3) |
| B — high reuse, same question | High | Same | **Block** (CF-SE4) |
| C — low overlap, wrong null | Low | Wrong null | **Block** (CF-SE5) |

Row-overlap threshold alone is **not** the gate; `coarse_redundancy_interpretation == SCIENTIFIC_REDUNDANCY` blocks.

## Exact binding

Preserves chain:

`SEEK_FALSIFICATION` → `directional_reversal` → `directional_effect_full_universe` → `full_panel_contrast`

Adapter translates representation only; binding layer audits `executed_question_equals_selected_question`.

## Outcome-semantics integrity

Preserves frozen semantics:

- Outcome: `t5_return > 0`
- Tool: `partition_group_compare` on `rs_spread` quintiles
- Distinction maintained between tool success-rate output, `raw_quintile_metrics.quintile_mean_spread`, and the directional-reversal scientific question
- No silent semantic substitution

## ToolResult #2 contract

Envelope includes: proposition/package/decision identity, experiment ordinal = 2, scientific-action hash, target null/uncertainty, novelty decomposition reference, binding audit, tool result + hash, raw quintile metrics, panel provenance, sample size, warnings/errors, `interpretation_generated=False`, `research_decision_generated=False`.

## History preservation

Experiment #2 is a new ordinal event. Experiment #1 records are not overwritten. Lineage reconstructable:

Exp #1 → Evidence #1 → EpistemicUpdate #1 → ResearchDecision #1 → Experiment #2 → ToolResult #2

## Idempotency

Identical frozen package + provenance → `IDEMPOTENT_REPLAY` returns existing envelope (CF-SE7, production persistence index).

## Counterfactuals (CF-SE1–10)

| ID | Scenario | Expected | Result |
|----|----------|----------|--------|
| CF-SE1 | Package mutation after freeze | Reject | PASS |
| CF-SE2 | Decision/target-null mismatch | Reject | PASS |
| CF-SE3 | Case A: high overlap, new question | Admit at gate | PASS |
| CF-SE4 | Case B: high overlap, same question | Block redundancy | PASS |
| CF-SE5 | Case C: wrong null | Block | PASS |
| CF-SE6 | Tool convenience substitution | Reject | PASS |
| CF-SE7 | Duplicate execution | Idempotent reuse | PASS |
| CF-SE8 | Stale provenance | Fail closed | PASS |
| CF-SE9 | Tool semantic contamination | No epistemic judgment in envelope | PASS |
| CF-SE10 | Interpretation leakage | No Evidence/Decision #2 | PASS |

## Regression

| Suite | Result |
|-------|--------|
| Phase 3J.7 tests | PASS (7) |
| CF-SE suite | PASS |
| 3J.6A novelty tests | PASS |
| 3J.6 regression | PASS |
| 3J.5–3J.2 regression | PASS (50) |

## Real diagnostic (`prop-efb650d9bd5c451f`)

| Field | Value |
|-------|-------|
| Proposition | `prop-efb650d9bd5c451f` |
| ResearchDecisionRecord | `dec-4c5eef9ff644` |
| SecondExperimentPackage | `sefp-ef0593efdb17` |
| Target null | `directional_reversal` |
| Target uncertainty | `directional_effect_full_universe` |
| Design | `full_panel_contrast` |
| Tool | `partition_group_compare` |
| Population | `all` |
| Outcome | `t5_return > 0` |
| ROW_OVERLAP | 0.977 |
| NULL_TARGET_OVERLAP | 0.0 |
| SCIENTIFIC_QUESTION_OVERLAP | 0.0 |
| Novelty | `HIGH_SAMPLE_REUSE_NEW_QUESTION` |
| Execution status | SUCCESS |
| ToolResult #2 | `sefx-afb1b59c434c` |
| Sample size | 6106 |
| Quintile mean spread | 2.352 (measurement only) |
| Substitution | None |
| Interpretation | None |
| STOP | `STOP_SECOND_EXPERIMENT_EXECUTED` |

## Hidden-answer audit

No encoded expected outcomes, directional answers, July 27 references, or proposition-specific pass thresholds in execution modules.

## Frozen artifact integrity

Prior phase artifacts and hashes unchanged. Execution reads persisted 3J.3/3J.4/3J.5/3J.6 state; does not mutate frozen Experiment #1 semantics.

## Known limitations

- Synthetic BBFE panels may fail tool grammar at execution; gate/idempotency counterfactuals use real panel where full execution is required
- `t5_return > 0` binding to quintile mean-spread remains partial but consistent with frozen 3J.6/3J.6A semantics (not redesigned)
- Package hash gate accepts non-empty hash (adapter preserves 3J.6 hash; does not re-validate full body recompute)

## Next boundary

Phase 3J.8 would interpret ToolResult #2 — **explicitly out of scope**. Hard STOP at `STOP_SECOND_EXPERIMENT_EXECUTED`.
