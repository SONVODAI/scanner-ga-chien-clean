# Phase 3J.1 — Autonomous First-Experiment Selection Readiness

**Mode:** AUDIT + DESIGN ONLY  
**Date:** 2026-08-22  
**Branch:** `cursor/phase-3j1-first-experiment-readiness-aad2`  
**Verdict:** `NOT_READY` (overall)

**NO NEW MARKET EXPERIMENT. NO NEW TOOLRESULT. NO DEPLOYMENT.**

---

## 1. Branch / commits / PR

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3j1-first-experiment-readiness-aad2` |
| Base | Phase 3J.0 production OPR integration (`74ec7a9f0`) |
| Artifacts | `diagnostics/phase_3j1_first_experiment_readiness/artifacts/` |
| Audit runner | `run_phase_3j1.py` |

Frozen Phase 3I + 3J.0 scientific hashes preserved (`ee00da71…` synthesis engine unchanged).

---

## 2. Central Question

> Given a newly originated PropositionRecord, before any result is known, can Mr.BOT derive, compare, reject, and select the scientifically best first experiment?

**Answer: No.** Mr.BOT can bind **one** default experiment via `executability_adapter` (tool-last, single path). It cannot yet compare multiple scientifically distinct first experiments or reject birth-evidence duplication.

---

## 3. Current Path After STOP_PROPOSITION_PERSISTED

```
Production opportunity detected
  → PropositionRecord persisted
  → STOP_PROPOSITION_PERSISTED (3J.0)
  → [nothing selects first experiment]
```

Parallel path at proposition emission (pre-3J.0 stop):

```
synthesize_contrast_to_proposition
  → adapt_executability(record, panel)   # single partition_group_compare
  → experiment_spec_draft embedded in record
  → STOP (not executed in production)
```

---

## 4. Mechanism Inventory & Classification

| Component | Classification | At birth? |
|-----------|----------------|-----------|
| `executability_adapter` | **TOOL_BINDING_ONLY** | Yes — single candidate |
| `proposition_synthesizer` (falsifiable/disconfirm specs) | **SCIENTIFIC_OBJECTIVE_DERIVED (partial)** | Yes |
| `derive_proposition_vulnerabilities` | **SCIENTIFIC_OBJECTIVE_DERIVED (partial)** | Callable, unwired |
| `scientific_action_generator` | **NOT_APPLICABLE_AT_PROPOSITION_BIRTH** | Requires synthesis |
| `falsification_candidate_generator` | **NOT_APPLICABLE_AT_PROPOSITION_BIRTH** | Requires EPU + decision |
| `research_actions` / `research_planner` | **LEGACY_PRIOR** | Blocked under OPR |
| `lifecycle_runner` | **EXECUTION_UTILITY** | No selection |
| `cohort_overlap_estimator` | **EXECUTION_UTILITY (reusable)** | Not wired at birth |

Full inventory: `artifacts/01_mechanism_inventory.json`

**Critical finding:** The causal order today is effectively:

```
PropositionRecord → partition_group_compare (predetermined) → ExperimentSpec
```

Not:

```
PropositionRecord → vulnerability → objective → candidates → selection → ExperimentSpec
```

---

## 5. InitialExperimentObjectiveRecord (Design)

Minimum record design: `artifacts/02_initial_experiment_objective_design.json`

Must answer: *What uncertainty should the first experiment reduce?*

Derivation sources at birth (legitimate):
- `falsifiable_expectation`
- `disconfirming_observation_spec`
- `null_competing_explanation`
- `canonical_proposition_core`
- `observation_provenance.structural_context`

**Capability gap:** No module derives `InitialExperimentObjectiveRecord` at proposition birth.

**Partial readiness:** Objective *content* exists scattered in PropositionRecord fields but is not unified or ranked for first-experiment purposes.

---

## 6. Candidate Generation Readiness

| Question | Status |
|----------|--------|
| Multiple scientifically distinct first experiments? | **No** — one `adapt_executability` path |
| Tools last? | **Violated** — tool hardcoded first |
| Falsification candidates at birth? | **No** — generator requires post-EPU inputs |

Existing post-synthesis operators (`episode_holdout_excluding_motivating`, etc.) are **not invokable** at `STOP_PROPOSITION_PERSISTED`.

---

## 7. Scientific Identity

Post-synthesis dedup exists in `scientific_action_core` for 3I.16 actions. **No first-experiment identity** layer exists. Two tools testing the same commitment would not be deduplicated at birth.

Design requirement documented in selection policy (`artifacts/03_selection_policy_design.json`).

---

## 8. Candidate Classifications (Real Proposition Diagnostic)

Applied to frozen `prop-efb650d9bd5c451f` — **NOT EXECUTED**

| Candidate | Classification |
|-----------|----------------|
| `executability_adapter` default | **REDUNDANT_WITH_BIRTH_EVIDENCE** + **CONFIRMATORY_ONLY** |
| Falsification sketches (episode holdout) | **FALSIFICATION_CAPABLE** — not invokable at birth |

Artifact: `artifacts/04_real_proposition_diagnostic.json`

```json
"execution_status": "NOT_EXECUTED"
"human_choice_material": true
```

**Birth-evidence overlap:** Same `rs_spread` quintile / `t5_return` contrast on panel including focal date `2026-08-02` — duplicates motivating quintile evidence. Independence: **LOW**.

---

## 9. Pre-Result Selection Policy (Design)

Lexicographic policy designed (no weights):

1. Reject NON_EXECUTABLE, RESCUE_MUTATION, NEW_PROPOSITION_REQUIRED  
2. Reject REDUNDANT_WITH_BIRTH_EVIDENCE  
3. Reject CONFIRMATORY_ONLY when FALSIFICATION_CAPABLE exists  
4. Reject REPRESENTATION_ONLY  
5. Prefer birth-evidence independence  
6. Prefer directness to central commitment  
7. Prefer falsification-capable branches  
8. Executability tie-break only  

Valid outcomes: `AMBIGUOUS_FIRST_EXPERIMENT`, `NO_HIGH_INFORMATION_FIRST_EXPERIMENT`

**No selector module exists.**

---

## 10. Birth-Evidence Independence

**NOT_READY**

- Motivating observation computed quintile spread on focal date  
- Default first experiment recomputes quintile spread on full panel including same date/feature/outcome  
- `cohort_overlap_estimator` could quantify this but is not wired at birth  
- Would fail independence gate in designed policy

---

## 11. Falsification-First at Birth

Partial: `disconfirming_observation_spec` defines disconfirm path. Default experiment is confirmatory (same contrast direction). Episode-holdout falsification would be scientifically stronger first test but is **not generated** at birth.

Outcome branches (A more credible / B less credible / C unresolved) are implicit in interpretation contract but not used for **pre-result selection**.

---

## 12. Anti-Rescue

Anti-rescue exists in falsification generator and scientific action operators — **post-synthesis only**. No first-experiment rescue rejection at birth.

---

## 13. BB-FirstExperiment-01 (Pre-Registered Design)

**20 cases**, 4+ abstract families (`flux_tier_dispersion`, `delta_yield_gate`, `context_gate_modulation`, `volatility_surface_skew`).

Design: `modules/edge_research/opr_bridge/bb_first_experiment_01_design.py`  
Artifact: `artifacts/06_bb_first_experiment_01_design.json`

**Implementation status:** NOT IMPLEMENTED (3J.1 design only)  
**Expected pass rate vs current mechanisms:** 0/20

---

## 14. Counterfactuals (CF-FE1–FE8)

| ID | Passed | Reason |
|----|--------|--------|
| CF-FE1 Remove motivating evidence | No | No objective derivation |
| CF-FE2 Increase overlap | No | Overlap estimator not wired at birth |
| CF-FE3 Resolve uncertainty | No | No birth objective lifecycle |
| CF-FE4 Tool reorder | No | Single candidate only |
| CF-FE5 Representation identity | No | No first-experiment dedup |
| CF-FE6 Redundant cohort | No | No selector |
| CF-FE7 Non-executable best | No | No selector policy |
| CF-FE8 Rescue mutation | Partial | Anti-rescue post-synthesis only |

Artifact: `artifacts/05_counterfactuals.json`

---

## 15. Production Relationship (3J.0 → future)

```
production evidence
  → autonomous proposition birth
  → STOP_PROPOSITION_PERSISTED          ← 3J.0 stops here
  → [MISSING: first-experiment selector]  ← 3J.1 gap
  → InitialExperimentPackage
  → STOP (no execution in integration phase)
```

Not wired in 3J.1.

---

## 16. Legacy Authority Firewall

- Legacy `bootstrap_research_graph` still seeds human question + template experiment if OPR flag off  
- Under OPR authority: legacy planner **blocked**  
- **No OPR first-experiment selector** — gap is missing capability, not legacy override  
- Closest failure mode: `executability_adapter` acts as implicit template translation (partition_group_compare predetermined)

---

## 17. Verdicts

| Verdict | Result |
|---------|--------|
| FIRST_EXPERIMENT_OBJECTIVE_READINESS | **PARTIALLY_READY** |
| FIRST_EXPERIMENT_CANDIDATE_GENERATION_READINESS | **NOT_READY** |
| FIRST_EXPERIMENT_SELECTION_READINESS | **NOT_READY** |
| BIRTH_EVIDENCE_INDEPENDENCE_READINESS | **NOT_READY** |
| **Overall** | **`NOT_READY`** |

---

## 18. Final Questions (A–H)

| Q | Answer |
|---|--------|
| **A** | **Partially.** Scattered objective content in proposition fields; no unified first-experiment objective derivation. |
| **B** | **No.** Only one tool-bound candidate at birth. |
| **C** | **No.** Cannot reject default experiment as birth-evidence recomputation (diagnostic shows REDUNDANT_WITH_BIRTH_EVIDENCE). |
| **D** | **No.** No comparative pre-result selection. |
| **E** | **No** at birth. Anti-rescue/confirmatory rejection exists only post-synthesis. |
| **F** | **No.** Cannot emit NO_HIGH_INFORMATION_FIRST_EXPERIMENT at birth. |
| **G** | **Yes.** `executability_adapter` hardcodes `partition_group_compare`; human-encoded tool binding materially determines the only path. |
| **H** | **Immediately after proposition birth:** no module derives ranked objectives, generates multiple candidates, measures birth overlap, or selects. Earliest break = **first-experiment candidate generation + selection layer missing**. |

---

## 19. Highest-Leverage Missing Capability (for future phase)

**FirstExperimentSelector** — general module at `STOP_PROPOSITION_PERSISTED`:

```
PropositionRecord
  → derive InitialExperimentObjectiveRecord(s) from commitments
  → generate multiple candidate tests (incl. episode-independent falsification)
  → measure birth-evidence independence (reuse cohort_overlap_estimator)
  → lexicographic pre-result selection
  → InitialExperimentPackage (NOT_EXECUTED until proven safe)
```

Must not special-case `rs_spread`/`t5_return`. Must reject birth-evidence duplication before any ToolResult.

---

## 20. Explicit Confirmation

- NO new market experiment executed  
- NO new ToolResult produced  
- NO deployment  
- NO scientific rule / threshold changes  
- NO wiring of selector into production (design only)

---

*End of Phase 3J.1. STOP.*
