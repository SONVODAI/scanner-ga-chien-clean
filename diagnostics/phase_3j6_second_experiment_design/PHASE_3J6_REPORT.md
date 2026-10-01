# Phase 3J.6 — Second-Experiment Design From Frozen Research Decision

## Status: PASS

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3j6-second-experiment-design-aad2` |
| Base | `cursor/phase-3j5-research-decision-aad2` @ `b1c487bb9` |
| Hard STOP | `STOP_SECOND_EXPERIMENT_DESIGNED` |
| Prior STOP | `STOP_RESEARCH_DECISION_FROZEN` |

## Scientific objective

Given an authoritative frozen `ResearchDecisionRecord`, Mr.BOT autonomously designs a concrete second experiment that operationalizes the selected scientific action, targets the intended unresolved null, adds genuinely new information relative to birth evidence and Experiment #1, preserves falsification capability where required, and freezes `SecondExperimentPackage(NOT_EXECUTED)` without execution.

## Architecture

### Reused from 3J.2 / 3J.5

- Objective derivation pattern (`second_experiment_objective.py`)
- Candidate generation via `FirstExperimentContext`, `bind_experiment_spec`, birth overlap (`first_experiment_birth_evidence.py`)
- Lexicographic selection (`second_experiment_selector.py`)
- Scientific-action hashing and experiment content hash
- Gate + idempotent persistence pattern from 3J.3–3J.5

### Added for 3J.6

| Module | Role |
|--------|------|
| `second_experiment_records.py` | `SecondExperimentPackage`, candidate/objective records |
| `second_experiment_objective.py` | Derive objective from frozen decision (no `decide_next_action`) |
| `second_experiment_candidates.py` | Null-targeted generation, wrong-null rejection, history overlap |
| `first_experiment_execution_overlap.py` | Experiment #1 cohort fingerprint + overlap |
| `second_experiment_selector.py` | Lexicographic selection (falsification → first-exp independence) |
| `second_experiment_design_gate.py` | Eligibility, stale-package fail-closed |
| `second_experiment_pipeline.py` | Orchestrator |
| `second_experiment_design_persistence.py` | Durable package storage + index |
| `production_second_experiment_design.py` | Production integration |
| `bb_second_experiment_design_01_fixtures.py` | CF-SD1–10 |

### Production integration

- `production_orchestrator.py`: `design_second_experiment=True` extends lifecycle after 3J.5
- `production_persistence.py`: `second_experiment_package` field on session record

## Lifecycle transition

```
STOP_RESEARCH_DECISION_FROZEN
  → load authoritative ResearchDecisionRecord
  → reconstruct scientific target / surviving null
  → derive second-experiment objective
  → generate candidate experiment designs
  → evaluate scientific fidelity
  → evaluate independence / redundancy (birth + Experiment #1)
  → evaluate executability WITHOUT execution
  → select ONE design OR SILENCE
  → freeze SecondExperimentPackage(NOT_EXECUTED)
→ STOP_SECOND_EXPERIMENT_DESIGNED
```

## WHAT → HOW separation

- Consumes frozen 3J.5 decision; does **not** rerun `decide_next_action()`
- Wrong-null cohort strategies (e.g. holdout when decision targets `directional_reversal`) are inadmissible
- `include_wrong_null_audit` path explicitly rejects decision substitution (CF-SD1)

## History-aware design

Experiment #2 design accounts for:

- Birth evidence fingerprint
- Experiment #1 specification and execution cohort
- Null addressed by Experiment #1 (`episode_artifact`)
- Surviving null from decision (`directional_reversal`)
- Epistemic update and research-state identity

## Real diagnostic (`prop-efb650d9bd5c451f`)

| Field | Value |
|-------|-------|
| Research decision ID | `dec-4c5eef9ff644` |
| Selected action | `SEEK_FALSIFICATION` |
| Target null | `directional_reversal` |
| Target uncertainty | `directional_effect_full_universe` |
| Derived objective | Full cross-section directional quintile test |
| Selected cohort | `full_panel_contrast` |
| Population | `all` (full panel) |
| Outcome | `t5_return` compare `> 0` |
| Tool | `partition_group_compare` |
| Falsification capability | `FALSIFICATION_CAPABLE` |
| Birth overlap | 0.023 (HIGH independence) |
| Exp #1 overlap | 0.977 (LOW sample independence; holdout ⊂ full panel) |
| Redundancy | `HIGH_FIRST_EXPERIMENT_OVERLAP` (explicit, not hidden) |
| Package status | `NOT_EXECUTED` |
| Decision substitution | false |
| Execution | false |
| STOP | `STOP_SECOND_EXPERIMENT_DESIGNED` |

SILENCE is valid when no faithful executable design exists; this proposition yields a faithful `full_panel_contrast` falsification design.

## Counterfactual suite (CF-SD1–10)

| ID | Result |
|----|--------|
| CF-SD1 | PASS — wrong-null substitution rejected |
| CF-SD2 | PASS — replication disguise detected |
| CF-SD3 | PASS — first-experiment overlap penalized separately from birth |
| CF-SD4 | PASS — science wins over convenience |
| CF-SD5 | PASS — non-executable → silence |
| CF-SD6 | PASS — confirmation-only rejected under SEEK_FALSIFICATION |
| CF-SD7 | PASS — different history → different design |
| CF-SD8 | PASS — ordering invariant |
| CF-SD9 | PASS — stale package identity rejected |
| CF-SD10 | PASS — NOT_EXECUTED, no ToolResult |

## Regression

All passed:

- `test_edge_research_opr_phase_3j6.py` (11)
- `test_edge_research_opr_phase_3j5.py` (10)
- `test_edge_research_opr_phase_3j4.py` (10)
- `test_edge_research_opr_phase_3j3.py` (9)
- `test_edge_research_opr_phase_3j2.py` (7)
- Frozen scientific hashes unchanged

## Hidden-answer audit

No prohibited tokens in `second_experiment*.py` / `production_second_experiment*.py`.

## Known limitations

- Only one faithful cohort strategy per null key in `NULL_COHORT_STRATEGIES`; diversity is limited to scientifically compatible variants
- High row overlap between holdout (Exp #1) and full panel (Exp #2) is expected; independence profiles surface this explicitly rather than requiring zero overlap
- `second_experiment_generated` flag on 3J.5 decision envelope is not mutated; package is persisted separately

## Next boundary (NOT entered)

- Experiment #2 execution (3J.7+)
- ToolResult #2
- Evidence interpretation #2
- Research Decision #2

**HARD STOP: `STOP_SECOND_EXPERIMENT_DESIGNED`**
