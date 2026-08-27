# Phase 3J.2 — Autonomous First-Experiment Objective, Candidate Generation & Selection

**Mode:** IMPLEMENTATION + DIAGNOSTIC (NOT EXECUTED)  
**Date:** 2026-08-22  
**Branch:** `cursor/phase-3j2-first-experiment-selection-aad2`  
**HEAD:** `1f87ea43c22ff40f82825b5884b72b55671c6ce3`  
**PR:** #59  
**Verdict:** `PASS` (overall)

**NO MARKET EXPERIMENT EXECUTED. NO NEW TOOLRESULT. NO DEPLOYMENT. NO PRODUCTION WIRING.**

---

## 0. Resume Status (Post-Interruption)

Work completed before interruption and preserved on this branch:

| Item | Status |
|------|--------|
| Selector executability gate (`executability_status != EXECUTABLE` rejected) | Done — `first_experiment_selector.py` |
| Birth-evidence feature alignment (context_modulation / surface_skew) | Done — `first_experiment_birth_evidence.py`, `_feature_field()` |
| BB-FirstExperiment-01 evaluation logic (overlap by cohort strategy, core-hash ordering invariance) | Done — `bb_first_experiment_01_fixtures.py` |
| Deterministic lexicographic tie-break via `scientific_action_core_hash` | Done — `first_experiment_selector.py` |
| Full diagnostic/regression re-run | Done — see §12 |

Uncommitted changes preserved (not part of 3J.2): unrelated `phase_3j1` artifact drift only.

---

## 1. Git / Branch

```
Branch: cursor/phase-3j2-first-experiment-selection-aad2
HEAD:   1f87ea43c22ff40f82825b5884b72b55671c6ce3
Commit: Phase 3J.2: autonomous first-experiment objective, candidates, and selection
```

**Files changed (16 in commit):**

| Path | Role |
|------|------|
| `modules/edge_research/opr_bridge/first_experiment_records.py` | Record types |
| `modules/edge_research/opr_bridge/first_experiment_objective.py` | Objective derivation |
| `modules/edge_research/opr_bridge/first_experiment_candidates.py` | Candidate generation |
| `modules/edge_research/opr_bridge/first_experiment_birth_evidence.py` | Birth overlap |
| `modules/edge_research/opr_bridge/first_experiment_core.py` | Identity dedup |
| `modules/edge_research/opr_bridge/first_experiment_selector.py` | Lexicographic selector |
| `modules/edge_research/opr_bridge/first_experiment_pipeline.py` | Orchestrator |
| `modules/edge_research/opr_bridge/bb_first_experiment_01_fixtures.py` | BB + CF fixtures |
| `tests/test_edge_research_opr_phase_3j2.py` | Tests |
| `diagnostics/phase_3j2_first_experiment_selection/*` | Runner + artifacts + report |

Phase 3J.0 production orchestrator, synthesis engine, dormancy, and trading paths are **unchanged**.

---

## 2. Capability Implemented

Smallest general first-experiment capability closing the 3J.1 autonomy break:

```
PropositionRecord
  → InitialExperimentObjectiveRecord(s)     [from commitments, not tools]
  → multiple FirstExperimentCandidateRecord [distinct cohort strategies]
  → deduplicate_by_scientific_identity()    [ScientificActionCore hash]
  → measure_birth_overlap()                 [evidence row structure]
  → classify + anti-rescue gates
  → select_first_experiment()               [frozen lexicographic, pre-result]
  → bind_experiment_spec()                  [tools last]
  → InitialExperimentPackage(NOT_EXECUTED)
  → STOP
```

Candidate classes supported: `DIRECT_INITIAL_TEST`, `FALSIFICATION_CAPABLE`, `CONFIRMATORY_ONLY`, `REDUNDANT_WITH_BIRTH_EVIDENCE`, `REPRESENTATION_ONLY`, `RESCUE_MUTATION`, `NEW_PROPOSITION_REQUIRED`, `NON_INFORMATIVE`, `NOT_EXECUTABLE`.

Valid silence: `NO_HIGH_INFORMATION_FIRST_EXPERIMENT`, `AMBIGUOUS_FIRST_EXPERIMENT`.

---

## 3. Frozen Selection Policy

1. Reject rescue / new-proposition / non-informative / representation-only / birth-redundant classes  
2. Reject non-executable executability status (validity gate, not selection driver)  
3. Reject confirmatory-only when falsification-capable alternatives exist  
4. Prefer falsification-capable over direct confirmatory  
5. Prefer higher evidence-derived sample independence  
6. Prefer lower birth-evidence overlap  
7. Prefer lower directness rank  
8. Executability tie-break only among scientific survivors  
9. Deterministic tie-break: `scientific_action_core_hash` (not candidate id or tool order)

---

## 4. BB-FirstExperiment-01

| Metric | Result |
|--------|--------|
| Version | `bb_first_experiment_01_v1_3j2` |
| Cases | **20 / 20 PASS** |
| Families | flux_tier_dispersion, delta_yield_gate, context_gate_modulation, modulation_axis, volatility_surface_skew |

Silence cases observed: BBFE-04, BBFE-06, BBFE-13, BBFE-15, BBFE-16 → `NO_HIGH_INFORMATION_FIRST_EXPERIMENT`.

Artifact: `artifacts/01_bb_first_experiment_01.json`

---

## 5. Counterfactuals CF-FE1–FE8

| ID | Result | Evidence |
|----|--------|----------|
| CF-FE1 | PASS | Objective rationale changes when motivating evidence removed |
| CF-FE2 | PASS | Overlap 1.0 (single-date panel) ≥ 0.33 (multi-date panel) |
| CF-FE3 | PASS | Valid silence when no executable candidates |
| CF-FE4 | PASS | Same core hash + disposition under tool reorder |
| CF-FE5 | PASS | Representation-only shares core hash with direct test |
| CF-FE6 | PASS | Redundant cohort → alternate or silence |
| CF-FE7 | PASS | No selection when all candidates non-executable |
| CF-FE8 | PASS | Rescue mutation generated and rejected |

Artifact: `artifacts/02_counterfactuals.json`

---

## 6. Abstract-Family Generalization

| Family | Case | Outcome |
|--------|------|---------|
| flux_tier_dispersion | BBFE-01–04, 08, 10–11, 14, 16 | Selection or valid silence |
| delta_yield_gate | BBFE-03, 07, 09, 11, 15, 19 | Tool-order invariant |
| context_gate_modulation | BBFE-05–06, 12, 17 | Context-gate feature alignment |
| modulation_axis | BBFE-09, 13, 18 | Order perturbation invariant |
| volatility_surface_skew | BBFE-20 | `skew_measure` / `carry_premium` — not rs_spread/t5_return |

Development firewall: no `rs_spread`, `t5_return`, or `prop-efb650d9bd5c451f` in abstract BB fixtures (verified by grep on implementation modules).

---

## 7. Real Proposition Diagnostic — `prop-efb650d9bd5c451f`

**Protocol:** Applied once after BB freeze. NOT EXECUTED. No ToolResult read.

### Selected first experiment

| Field | Value |
|-------|-------|
| Disposition | `SELECTED` |
| Execution status | `NOT_EXECUTED` |
| Cohort strategy | `episode_holdout_excluding_motivating` |
| Population | `trade_date not_in ['2026-08-02']` |
| Scientific classification | `FALSIFICATION_CAPABLE` |
| Birth overlap | 0.000 |
| Sample independence | HIGH |
| Tool (bound last) | `partition_group_compare`, `rs_spread` quintile, `t5_return` outcome |

### Causal explanation for selection

1. **Objective:** Null competing explanation flags episode artifact on motivating date 2026-08-02 → `episode_robustness` uncertainty ranks as first high-information test.  
2. **Candidates:** Three distinct strategies generated — full-panel direct, episode holdout, counterexample search.  
3. **Rejection:** Full-panel direct rejected — `confirmatory_only_when_falsification_available` (includes motivating episode; confirmatory vs. independent falsification).  
4. **Ranking:** Falsification-capable holdout wins lexicographic policy — zero birth overlap, HIGH sample independence, lower directness rank than directional-only confirmatory path.  
5. **Tool binding:** `partition_group_compare` is the bound instrument for the winning scientific test; it did not determine the scientific question.

### Legacy default comparison

| Path | Survives? |
|------|-----------|
| `executability_adapter` full-panel `partition_group_compare` | **Rejected** |
| `default_partition_group_compare_survives_selection` | **false** |
| `human_choice_material` | **false** |

Artifact: `artifacts/03_real_proposition_diagnostic.json`

---

## 8. Executability Audit

- Executability assessed **after** scientific classification via `bind_experiment_spec()`.
- Non-executable candidates are **rejected at eligibility** — never substituted silently (BBFE-13, CF-FE7).
- Abstract mode: missing tools → `NOT_EXECUTABLE` → valid silence.
- Real T2: all three generated candidates were executable; selection was on scientific merit, not tool availability alone.
- `partition_group_compare` receives **no privileged rank** — only binds the scientifically selected test.

---

## 9. Semantic Identity / Dedup Audit

- Identity = `ScientificActionCore` hash (uncertainty + commitment + cohort strategy + contrast relation).
- Alternative-tool candidates classified `REPRESENTATION_ONLY` — same core hash as direct test (CF-FE5).
- Dedup keeps best scientific class per core hash before selection.
- Tool name / representation excluded from identity hash.

---

## 10. Human-Choice Audit

| Check | T2 Result |
|-------|-----------|
| Winner determined by hardcoded single adapter path? | **No** — adapter default rejected |
| Winner determined because only executable path? | **No** — three executable candidates |
| `human_choice_material` | **false** |
| `human_choice_reason` | Scientific lexicographic dominance — tools bound last |

3J.1 finding (`human_choice_material: true`) is **resolved** for first-experiment selection capability.

---

## 11. Hidden-Firewall Audit

| Check | Result |
|-------|--------|
| rs_spread/t5_return in abstract BB fixtures | **Absent** |
| rs_spread/t5_return in first_experiment_*.py | **Absent** |
| Known T2 answer encoded in selector weights | **Absent** — lexicographic only |
| Zone C / future ToolResult used | **Absent** |
| Rules tuned after real diagnostic | **No** — real diagnostic run once post-BB freeze |
| Frozen 3I synthesis/dormancy hashes | **Unchanged** |

Artifact: `artifacts/04_frozen_hash_audit.json`

---

## 12. Regression Results (Post-Resume)

| Suite | Result |
|-------|--------|
| `tests/test_edge_research_opr_phase_3j2.py` | 7/7 PASS |
| `tests/test_edge_research_opr_phase_3j0.py` | 20/20 PASS |
| `tests/test_edge_research_opr_phase_3j1.py` | 5/5 PASS |
| `run_phase_3j2.py` diagnostic | OVERALL PASS |

---

## 13. Remaining Autonomy Break

| Gap | Status |
|-----|--------|
| First-experiment pipeline at proposition birth | **Closed** (this phase) |
| Wiring into `production_orchestrator` at `STOP_PROPOSITION_PERSISTED` | **Not in scope** — deliberate STOP boundary |
| Package execution / ToolResult ingestion | **Future phase** — package frozen NOT_EXECUTED |
| Legacy `executability_adapter` parallel path at proposition emission | Still exists; production OPR path does not auto-select via adapter |

---

## 14. Verdicts

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

## 15. Final Questions (A–H)

| Q | Answer |
|---|--------|
| **A** | **Yes** — objectives from proposition commitments only. |
| **B** | **Yes** — distinct cohort strategies, not tool variants. |
| **C** | **Yes** — overlap from evidence row structure. |
| **D** | **Yes** — redundant/confirmatory/rescue rejected scientifically. |
| **E** | **Yes** — invariant to order/naming; sensitive to evidence structure. |
| **F** | **Yes** — valid silence when no defensible executable test. |
| **G** | **No on T2** — no human/tool prior determined winner. |
| **H** | **Yes** — autonomous defensible package or silence at birth. |

---

## 16. STOP Confirmation

- NO market experiment executed  
- NO new ToolResult produced  
- NO deployment or trading changes  
- NO Phase 3J.0 production auto-execution wiring  
- Selected package: `execution_status=NOT_EXECUTED`  
- Phase 3J.3 not begun  

---

*End of Phase 3J.2. STOP.*
