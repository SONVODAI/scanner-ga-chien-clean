# Phase 3J.13 — History-Aware Follow-On Experiment Generation

**Stop boundary:** `STOP_HISTORY_AWARE_FOLLOW_ON_GENERATION`  
**Branch:** `cursor/phase-3j13-history-aware-follow-on-experiment-generation-aad2`  
**Base:** `cursor/phase-3j12-n-experiment-research-generalization-aad2` (PR #70)  
**Status:** PASS

---

## Summary

Phase 3J.13 generalizes follow-on candidate generation from second-experiment-specific semantics to history-aware Experiment #N generation. For `experiment_ordinal >= 3`, the lifecycle now consumes frozen `ResearchDecision[N-1]` plus complete `ExperimentHistory[1..N-1]` when proposing candidates. Ordinal 2 remains frozen via the existing `second_experiment_*` path.

SILENCE remains valid: `NO_FAITHFUL_EXPERIMENT` is the generic disposition when no scientifically faithful, executable design exists. PASS does not require Experiment #3 execution.

---

## Second-Experiment Assumptions Removed (Ordinal >= 3)

| Removed assumption | Replacement |
|---|---|
| Overlap measured only vs Experiment #1 | `measure_max_prior_overlap` vs all prior fingerprints |
| Rejection keyed to `replicates_first_experiment_cohort` | `replicates_prior_experiment_cohort:ordinal_N` |
| Selector ranks by `first_experiment_overlap_fraction` only | Ranks by decision fidelity → falsification/replication → redundancy → max prior overlap |
| `NO_FAITHFUL_SECOND_EXPERIMENT` disposition | Generic `NO_FAITHFUL_EXPERIMENT` for ordinal >= 3 |
| Objective derived from empty adapter view | `candidate_evaluations` preserved in `NormalizedPriorDecision` |
| Generator always `second_experiment_generator_v1_3j6` | `follow_on_experiment_generator_v1_3j13` when history present |

---

## Architecture

### New modules

1. **`follow_on_experiment_history_context.py`** — Builds `FollowOnHistoryContext` from `ExperimentHistoryEntry` list: prior fingerprints, tested null/cohort pairs, content/core hashes, rejected cores, cumulative null ledger, search accounting.
2. **`follow_on_experiment_candidates.py`** — History-aware candidate generation reusing frozen `NULL_COHORT_STRATEGIES` grammar (no new benchmark families).
3. **`follow_on_experiment_selector.py`** — Lexicographic selector with generic dispositions.

### Wiring

- `second_experiment_pipeline.py` — When `experiment_ordinal >= 3` and `history` is provided, routes to follow-on generator/selector.
- `follow_on_experiment_core.py` — Passes full `history` into design pipeline.
- `follow_on_research_decision_adapter.py` — Preserves `candidate_evaluations` for objective derivation at ordinal >= 3.

### WHAT → HOW fidelity

- Frozen decision target null drives strategy enumeration; wrong-null audit candidates rejected.
- `SEEK_FALSIFICATION` rejects confirmation-only designs.
- `SEEK_REPLICATION` requires sample independence vs all prior experiments; fake replication and representation aliases rejected.
- Executability does not mutate the scientific question; non-executable faithful designs fail closed.

---

## Candidate Families (Existing Grammar)

Reuses `NULL_COHORT_STRATEGIES` only — population contrast, holdout/episode exclusion, full panel, regime partition. No mechanical combination enumeration; constrained by target null and search accounting.

---

## Full-History Novelty & Redundancy

Each candidate evaluated via rolling max-overlap vs all priors and `decompose_novelty` worst-case across history:

- ROW / population / contrast / outcome / null-target / scientific-question overlap
- Null cycling detection (A→B→A)
- Representation alias (content hash / core hash match)
- Search burden pressure at high complexity + high overlap

---

## Selector Behavior

Lexicographic priority:

1. Decision fidelity  
2. Falsification / replication capability (action-appropriate)  
3. Redundancy assessment  
4. Sample independence  
5. Max prior overlap (lower preferred)  
6. Birth overlap  
7. Executability  
8. Deterministic core-hash tie-break  

---

## Counterfactuals (CF-FG1–12)

All passed. See `diagnostics/phase_3j13_history_aware_follow_on_generation/artifacts/01_cf_fg_summary.json`.

| Case | Result |
|---|---|
| CF-FG1 | Ordinal 3 uses `follow_on_experiment_generator_v1_3j13` |
| CF-FG2 | Ordinal 4 generic path (no ord-3-only branch) |
| CF-FG3 | Exhausted strategies → `NO_FAITHFUL_EXPERIMENT` |
| CF-FG4 | Wrong-null audit rejected |
| CF-FG5 | High-row same-question → redundancy class B |
| CF-FG6 | New null + row reuse may remain admissible |
| CF-FG7 | Fake replication rejected under SEEK_REPLICATION |
| CF-FG8 | Replication path fail-closed when independence unavailable |
| CF-FG9 | Single horizon (no horizon shopping) |
| CF-FG10 | Null cycling detected |
| CF-FG11 | Search burden rejects low-information repeat |
| CF-FG12 | Ordering invariance preserved |

---

## Ordinal >= 3 Diagnostic (Seed 77 — not special-cased)

Generic production panel path (`seed=77`, budget=4):

- **Frozen Decision #2:** `SEEK_FALSIFICATION` targeting `episode_artifact` / `episode_robustness`
- **Ord 3 generator:** `follow_on_experiment_generator_v1_3j13`
- **Ord 3 disposition:** `NO_FAITHFUL_EXPERIMENT` (both episode strategies already exercised in history — scientifically justified SILENCE)
- **ToolResult #3:** Not produced (execution fail-closed on silence package — expected)
- **Termination:** `FAILED_CLOSED` / `experiment_3_execution_failed`

PASS: history-aware path active; SILENCE scientifically justified after removing ordinal-2-only overlap logic.

---

## Frozen Blind Longer-Budget Re-Exam (3J.11 suite, budget=4)

Same seeds, panels, policies as 3J.11. No post-hoc tuning.

| Metric | Value |
|---|---|
| Cases | 12 |
| Critical false positives | **0** |
| Avg outcome score | 0.65 |
| Avg process integrity | 0.917 |
| Scientific behavior pass | true |

No material false-positive regression vs 3J.12 baseline (critical FP remained 0).

---

## Regression

All passed:

- Phase 3J.13 tests  
- Phase 3J.12, 3J.11, 3J.10, 3J.9  
- CF-FG1–12  
- Hidden-answer audit (research modules clean)

---

## Hidden-Answer Audit

Research modules `follow_on_experiment_{candidates,history_context,selector}.py` and `second_experiment_pipeline.py` contain no blind benchmark IDs, ground truth, or seed-specific behavior.

---

## Frozen Artifact Integrity

- Ordinal 2 path unchanged (`second_experiment_generator_v1_3j6`, frozen dispositions).
- Historical session artifacts not mutated.
- Legacy `first_experiment_overlap_fraction` field at ordinal >= 3 semantically holds **max prior overlap** (documented in candidate `informative_observation`).

---

## Known Limitations

1. **Grammar coverage:** If all `NULL_COHORT_STRATEGIES` for a target null are exhausted in history, SILENCE is correct — no invented benchmark-specific families.
2. **Objective derivation:** Still uses `_selected_evaluation` lexicographic policy from frozen decision evaluations; does not re-run decider.
3. **Execution gate:** Still requires `SELECTED` disposition; silence packages correctly fail-closed at execution.

---

## Next Boundary

Phase beyond 3J.13 would address any **scientific capability gaps** where the frozen research grammar cannot operationalize a legitimate `ResearchDecision` class — to be reported explicitly rather than benchmark-tuned.

---

**HARD STOP:** `STOP_HISTORY_AWARE_FOLLOW_ON_GENERATION`
