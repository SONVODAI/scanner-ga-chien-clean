# Phase 3J.2 — Autonomous First-Experiment Objective, Candidate Generation & Selection

**Mode:** IMPLEMENTATION + DIAGNOSTIC (NOT EXECUTED)  
**Date:** 2026-08-22  
**Branch:** `cursor/phase-3j2-first-experiment-selection-aad2`  
**Verdict:** `PASS` (overall)

**NO MARKET EXPERIMENT EXECUTED. NO NEW TOOLRESULT. NO DEPLOYMENT. NO PRODUCTION WIRING.**

---

## 1. Mission

Close the Phase 3J.1 autonomy break: after `PropositionRecord` birth, derive what to learn first, generate multiple scientifically distinct candidates, measure birth-evidence independence, apply frozen lexicographic selection, bind tools last, freeze `InitialExperimentPackage` with `execution_status=NOT_EXECUTED`, and STOP.

---

## 2. Causal Pipeline (Implemented)

```
PropositionRecord
  → derive_initial_experiment_objectives()
  → generate_first_experiment_candidates()
  → deduplicate_by_scientific_identity()
  → measure_birth_overlap() / derive_independence_from_overlap()
  → classify + anti-rescue gates
  → select_first_experiment() [lexicographic, pre-result]
  → bind_experiment_spec() [tools last]
  → InitialExperimentPackage(execution_status=NOT_EXECUTED)
  → STOP
```

| Module | Role |
|--------|------|
| `first_experiment_objective.py` | `InitialExperimentObjectiveRecord` from proposition commitments |
| `first_experiment_candidates.py` | Scientific candidate generation (not tool-first) |
| `first_experiment_birth_evidence.py` | Birth-evidence fingerprint + overlap (generalized 3I.17b) |
| `first_experiment_core.py` | Scientific identity / dedup (generalized 3I.16) |
| `first_experiment_selector.py` | Frozen lexicographic pre-result policy |
| `first_experiment_pipeline.py` | Orchestrator + package freeze |
| `bb_first_experiment_01_fixtures.py` | Frozen BB-FirstExperiment-01 + CF-FE1–FE8 |

Phase 3J.0 production orchestrator is **unchanged** — no automatic execution wired.

---

## 3. Frozen Selection Policy

Lexicographic order (no tuned weights):

1. Reject `RESCUE_MUTATION`, `NEW_PROPOSITION_REQUIRED`, `NON_INFORMATIVE`, `REPRESENTATION_ONLY`, `REDUNDANT_WITH_BIRTH_EVIDENCE`
2. Reject `NOT_EXECUTABLE` executability status
3. Reject confirmatory-only paths when falsification-capable candidates exist
4. Prefer `FALSIFICATION_CAPABLE` over `DIRECT_INITIAL_TEST`
5. Prefer higher evidence-derived sample independence
6. Prefer lower birth-evidence overlap
7. Prefer lower directness rank (more central commitment)
8. Executability tie-break only among survivors
9. Deterministic tie-break via `scientific_action_core_hash` (not candidate id or tool order)

Valid silence: `NO_HIGH_INFORMATION_FIRST_EXPERIMENT`, `AMBIGUOUS_FIRST_EXPERIMENT`

---

## 4. BB-FirstExperiment-01

| Metric | Result |
|--------|--------|
| Cases | 20 / 20 PASS |
| Abstract families | flux_tier_dispersion, delta_yield_gate, context_gate_modulation, modulation_axis, volatility_surface_skew |
| Firewall | No rs_spread / t5_return / prop-efb650d9bd5c451f in abstract fixtures |

Artifact: `artifacts/01_bb_first_experiment_01.json`

---

## 5. Counterfactuals CF-FE1–FE8

| ID | Result |
|----|--------|
| CF-FE1 Remove motivating evidence → rationale changes | PASS |
| CF-FE2 Increase birth overlap → overlap fraction rises | PASS |
| CF-FE3 Resolve uncertainty → valid silence | PASS |
| CF-FE4 Tool reorder → same scientific winner | PASS |
| CF-FE5 Representation-only → same scientific core hash | PASS |
| CF-FE6 Redundant cohort → alternate or silence | PASS |
| CF-FE7 Best candidate non-executable → no inferior substitution | PASS |
| CF-FE8 Rescue mutation → generated and rejected | PASS |

Artifact: `artifacts/02_counterfactuals.json`

---

## 6. Real Diagnostic — `prop-efb650d9bd5c451f` (NOT EXECUTED)

Applied **once** after benchmark freeze. No outcome inspection. No execution.

### Objectives derived

| Target uncertainty | Vulnerability | Source |
|-------------------|---------------|--------|
| `directional_effect_full_universe` | directional_reversal | falsifiable_expectation + disconfirming_observation_spec |
| `episode_robustness` | episode_instability | null_competing_explanation + motivating date 2026-08-02 |

### Candidates considered

| Cohort strategy | Classification | Birth overlap | Executability |
|-----------------|----------------|---------------|---------------|
| `full_panel_contrast` | DIRECT_INITIAL_TEST | 0.023 | EXECUTABLE |
| `episode_holdout_excluding_motivating` | FALSIFICATION_CAPABLE | 0.000 | EXECUTABLE |
| `counterexample_period_search` | FALSIFICATION_CAPABLE | 0.000 | EXECUTABLE |

### Rejections

- Full-panel direct path: **rejected** — `confirmatory_only_when_falsification_available`

### Selection

| Field | Value |
|-------|-------|
| Disposition | `SELECTED` |
| Winner | Episode holdout falsification (`trade_date not_in ['2026-08-02']`) |
| Tool (bound last) | `partition_group_compare` on `rs_spread` quintile contrast |
| `human_choice_material` | **false** |
| `default_partition_group_compare_survives_selection` | **false** |

The historical full-panel `partition_group_compare` default does **not** win. An independent falsification experiment dominates per frozen pre-result rules.

Artifact: `artifacts/03_real_proposition_diagnostic.json`

---

## 7. Frozen Scientific Integrity

Prior Phase 3I / 3J.0 hashes unchanged. Artifact: `artifacts/04_frozen_hash_audit.json`

---

## 8. Verdicts

| Verdict | Result |
|---------|--------|
| FIRST_EXPERIMENT_OBJECTIVE | PASS |
| FIRST_EXPERIMENT_CANDIDATE_GENERATION | PASS |
| FIRST_EXPERIMENT_SELECTION | PASS |
| BIRTH_EVIDENCE_INDEPENDENCE | PASS |
| BB_FIRST_EXPERIMENT_01 | PASS (20/20) |
| COUNTERFACTUALS_CF_FE | PASS (8/8) |
| REAL_T2_DIAGNOSTIC | PASS (NOT_EXECUTED) |
| FROZEN_SCIENTIFIC_INTEGRITY | PASS |
| **OVERALL** | **PASS** |

---

## 9. Final Questions (A–H)

| Q | Answer |
|---|--------|
| **A** | **Yes.** Objectives derived from falsifiable_expectation, disconfirming_observation_spec, null_competing_explanation, canonical core, and provenance — no tool names in derivation. |
| **B** | **Yes.** Multiple distinct cohort strategies generated (full panel, episode holdout, counterexample search); representation-only duplicates classified and rejected. |
| **C** | **Yes.** Independence from `cohort_overlap_estimator` on row keys; episode_independence LOW when motivating dates overlap; not assigned from strategy labels alone. |
| **D** | **Yes.** Confirmatory full-panel rejected when falsification exists; rescue/outcome-mutation/non-informative paths rejected in benchmark. |
| **E** | **Yes.** Winner invariant to panel row order and tool registry order; sensitive to motivating evidence removal and overlap structure (CF-FE1–FE2). |
| **F** | **Yes.** `NO_HIGH_INFORMATION_FIRST_EXPERIMENT` emitted when no executable high-information candidate survives (BBFE-13, BBFE-15). |
| **G** | **No on T2.** `human_choice_material=false`; default adapter path rejected scientifically, not because of tool unavailability alone. |
| **H** | **Yes.** After proposition birth, Mr.BOT autonomously selects episode-holdout falsification or valid silence — without human intervention and without executing. |

---

## 10. Explicit STOP Confirmation

- NO market experiment executed  
- NO new ToolResult produced  
- NO deployment or trading changes  
- NO modification to frozen synthesis/dormancy semantics  
- NO wiring into Phase 3J.0 production auto-execution  
- Selected package remains `execution_status=NOT_EXECUTED`

---

*End of Phase 3J.2. STOP.*
