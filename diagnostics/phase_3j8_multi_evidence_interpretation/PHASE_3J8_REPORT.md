# Phase 3J.8 — Multi-Evidence Interpretation & Epistemic Update #2

## Status: PASS

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3j8-multi-evidence-interpretation-aad2` |
| Commit | `cec299ae1` |
| PR | #66 |
| Base | `cursor/phase-3j7-second-experiment-execution-aad2` @ `5fa5e5bdd` |
| Hard STOP | `STOP_SECOND_EVIDENCE_INTERPRETED` |
| Prior STOP | `STOP_SECOND_EXPERIMENT_EXECUTED` |

## Scientific objective

Can Mr.BOT interpret ToolResult #2 in the context of full prior research history, distinguish new evidence from reused evidence, update epistemic state without double-counting correlated evidence, and stop before Research Decision #2?

**Answer: Yes.**

## Architecture

### Reused from 3J.4

- Frozen pre-result `InterpretationContract` via `freeze_interpretation_contract_pre_result` / `load_authoritative_contract`
- `interpret_experiment_evidence`, `build_epistemic_update`, intent-aware assessment enums
- Gate + idempotency + persistence pattern
- `FirstExperimentInterpretationEnvelope` as prior history input

### Added for 3J.8

| Module | Role |
|--------|------|
| `multi_evidence_accounting.py` | Dependence, incremental contribution, cumulative null ledger, incremental transition |
| `second_experiment_interpretation_records.py` | Envelope + EpistemicUpdate #2 contract |
| `second_experiment_interpretation_gate.py` | History-aware eligibility |
| `second_experiment_evidence_interpreter.py` | Cumulative interpreter (ordinal 2) |
| `second_experiment_interpretation_persistence.py` | Durable storage |
| `production_second_experiment_interpretation.py` | Production bridge |
| `bb_multi_evidence_interpretation_01_fixtures.py` | CF-MEI1–10 |

### 3I.12 integration

- `build_ledger_entry`, `classify_pair`, `compute_independence_profile` for structured dependence

## Lifecycle transition

```
STOP_SECOND_EXPERIMENT_EXECUTED
  → validate full research history
  → load PRE-RESULT frozen contract for Experiment #2
  → interpret ToolResult #2 in intent context
  → estimate incremental evidence contribution
  → account for dependence with Evidence #1
  → update cumulative null ledger
  → produce EpistemicUpdateRecord #2
→ STOP_SECOND_EVIDENCE_INTERPRETED
```

No Research Decision #2, no Experiment #3.

## Multi-evidence dependence accounting

Distinguishes:

| Dimension | Mechanism |
|-----------|-----------|
| Evidence novelty | 3J.6A novelty decomposition from execution envelope |
| Sample dependence | Row overlap + 3I.12 independence profile |
| Question novelty | NULL_TARGET_OVERLAP + SCIENTIFIC_QUESTION_OVERLAP |
| Incremental contribution | Raw strength capped by dependence; double-counting blocked |

High overlap + distinct null → informative for new question, **not** independent replication.

## Real diagnostic (`prop-efb650d9bd5c451f`)

| Field | Value |
|-------|-------|
| ToolResult #2 | `sefx-afb1b59c434c` |
| Target null | `directional_reversal` |
| ROW_OVERLAP | 0.977 |
| Raw strength | MODERATE |
| Incremental strength | WEAK (dependence-capped) |
| Independent replication | **false** |
| Prior state | SUPPORTED |
| Resulting state | SUPPORTED (no auto CONFIRMED) |
| directional_reversal | STILL_PLAUSIBLE → WEAKENED |
| episode_artifact | Preserved from Evidence #1 (WEAKENED) |
| Interpretation | `iefi2-fa66e56ee0a3` |
| Research Decision #2 | **None** |

## Counterfactuals (CF-MEI1–10)

All PASS — including no double-counting (MEI1), low-overlap stronger incremental (MEI2), new-null/high-overlap (MEI3), same-null redundancy (MEI4), conflict handling (MEI5/6), wrong-question (MEI7), contract mutation (MEI8), null preservation (MEI9), no research loop (MEI10).

## Regression

64 tests across 3J.8–3J.2: all PASS.

## Known limitations

- Synthetic BBFE panels may skip full interpreter CF-MEI8/10 (gate rejects execution)
- Per-experiment base classification still uses frozen proposition contract; cumulative layer applies dependence overlay
- Episode_artifact state carried forward from Exp #1 interpretation envelope (not re-tested by Exp #2)

## Next boundary

Phase 3J.9 would create Research Decision #2 — **explicitly out of scope**. Hard STOP at `STOP_SECOND_EVIDENCE_INTERPRETED`.
