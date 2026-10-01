# Phase 3I.9 — Autonomous Falsification Candidate Generation & Selection

**Mode:** Implementation + validation — **no falsification experiment executed**  
**Generator version:** `falsification_candidate_generator_v1_3i9`  
**Verdict:** **FALSIFICATION_SELECTION_PASS**

---

## 1. Branch / Commits / PR

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3i9-falsification-selection-aad2` |
| Base | 3I.8 falsification readiness audit |

---

## 2. Files Changed

### New modules

| File | Purpose |
|------|---------|
| `falsification_records.py` | FalsificationCandidateRecord, enums |
| `falsification_candidate_generator.py` | Proposition-scoped vulnerability-driven generator |
| `falsification_selector.py` | Lexicographic selector (no weighted score) |
| `falsification_runner.py` | Selection orchestration + 3I.7 lineage loader |

### Modified

| File | Change |
|------|--------|
| `interpretation_contract.py` | Provenance fix: hash excludes `frozen_at`; `interpretation_contract_from_dict()` |
| `lifecycle_runner.py` | Accept pre-built contract + `interpretation_contract_ref` |
| `research_grammar.py` | Add `trade_date` to allowed population filters (episode holdout) |

### Tests / diagnostics

| Path | Purpose |
|------|---------|
| `tests/test_edge_research_opr_phase_3i9.py` | 14 tests including BB-Falsify-01 + abstract fixtures |
| `diagnostics/phase_3i9_falsification_selection/` | Frozen one-shot package artifacts |

**Not modified:** OPR generator, prioritizer, 3I.7 interpretation semantics/thresholds.

---

## 3. Frozen 3I.7 Lineage Audit

Verified without regeneration:

| Check | Result |
|-------|--------|
| proposition_hash | `c3aab7de80fdb9e56b7be68d517ec0e4792b711ec9772638143df3cfe4e39c9b` |
| epistemic state | SUPPORTED |
| decision | SEEK_FALSIFICATION |
| lineage_hash | `86b004538c1ab25d86b1b803a5d5970d6839bef37de467eb59b71052e2521b0b` |

---

## 4. Interpretation-Contract Provenance Correction

| Field | Value |
|-------|-------|
| Pre-freeze artifact 03 hash | `3474a096...` (preserved, used in package) |
| Historical lineage runtime hash | `6cde6297...` (mismatch preserved in audit) |
| Forward fix | Hash body excludes `frozen_at`; load via `interpretation_contract_from_dict()` |
| Rule content regression | **Match** — new builds identical rules to artifact 03 |
| 3I.7 result | **Not reinterpreted** |

---

## 5. Generator Architecture

**Causal order:** proposition commitment → vulnerability → disconfirming evidence → experiment → executability

**Inputs (only):** frozen PropositionRecord, disconfirming_observation_spec, epistemic state, prior ExperimentSpec, panel metadata, cutoff constraints

**Forbidden inputs:** GAP codes, templates, Zone C, future ToolResult, profitability

---

## 6. Vulnerability Derivation

From proposition (not tool catalog):

1. **directional_reversal** — from `disconfirming_observation_spec`
2. **episode_instability** — from null explanation + motivating episode dates in provenance

Motivating dates extracted generically from `evidence_anchor.focal_date` and `empirical_artifacts[].date`.

---

## 7. Candidate-Generation Mechanism

Legitimate candidates derived from vulnerabilities:

- **independent_episode_holdout** — `partition_group_compare` on holdout dates excluding motivating episodes (population filter `trade_date in [...]`)

Audit-only sketches (BB-Falsify-01, not in real selection):

- confirmatory retest, population narrow, horizon mutation, different tool only, leaky cutoff

Real selection generates **1 candidate** (holdout); audit run generates 6 for benchmark validation.

---

## 8. FalsificationCandidateRecord

Implemented per 3I.8 design with deterministic `record_hash`. Selected record: `fc-independent_episode_holdout` / hash `30ef2424...`

---

## 9. Candidate Semantic Identity

| Candidate | Class |
|-----------|-------|
| independent_episode_holdout | INDEPENDENT_FALSIFICATION |
| audit_confirmatory_retest | NOT_ACTUALLY_FALSIFICATION |
| audit_same_question_different_tool | NOT_ACTUALLY_FALSIFICATION |
| audit_population_narrow | NOT_ACTUALLY_FALSIFICATION (anti-rescue) |
| audit_horizon_mutation | NOT_ACTUALLY_FALSIFICATION (anti-rescue) |

---

## 10. Counterfactual Falsifiability Gate

Holdout candidate: strong directional reversal → 3I.7 interpreter → DISCONFIRMING → WEAKENED/FALSIFIED. **Pass.**

Sensitivity/date_decomposition candidates: interpreter incompatible → **rejected**.

---

## 11. Anti-Rescue Gate

Population REFINE, horizon mutation, outcome/field changes → **REJECTED**. Proposition hash immutable.

---

## 12. Selector

`lexicographic_falsification_selector_v1_3i9` — validity → counterfactual → directness → independence → redundancy → rescue → tiebreak. No weighted score. No date preference.

Real outcome: **SELECTED** `fc-independent_episode_holdout`

---

## 13. BB-Falsify-01 Results

All 14 tests pass including:

- Confirmatory retest → REJECT
- Same question / different tool → REJECT
- Independent episode → SELECTED
- Population narrow / horizon mutation → REJECT
- Invalid/leaky → REJECT
- No viable when only confirmatory → NO_VALID_FALSIFICATION_CANDIDATE

---

## 14. Abstract-Feature Generalization

Abstract proposition (`vol_dispersion` / `t3_return`, focal `2026-03-15`) generates executable holdout candidate — **not** hardcoded to rs_spread/t5_return.

---

## 15. Human-Choice Audit

| Locus | Classification | Blocks PASS? |
|-------|----------------|--------------|
| Lexicographic criteria ordering | REPRESENTATIONAL (frozen) | No |
| trade_date grammar filter | EXECUTION CONSTRAINT | No |
| Falsification strategy selection | **AUTONOMOUS** | No |
| GAP/template scientific intent | Not used | — |

---

## 16. Hidden / Future-Result Blindness

| Check | Result |
|-------|--------|
| Zone C accessed | No |
| Future ToolResult read | No |
| Second experiment executed | **No** |
| Passed | **Yes** |

---

## 17. Real Candidate Set

Single legitimate candidate (hash `0eb83024...`):

- **fc-independent_episode_holdout** — 43 holdout dates excluding motivating `2026-08-02`
- Experiment content hash: `624e91d23ea6ec56...` ≠ prior `8555087e...`

---

## 18. Real Selection

**SELECTED:** `fc-independent_episode_holdout`  
Rationale: episode instability vulnerability; independent evidence cohort; counterfactual falsifiable; anti-rescue pass.

Selection emerged from generic principle (exclude motivating/supporting episodes), not hardcoded FC-02 or date preference.

---

## 19. Verdict

### **FALSIFICATION_SELECTION_PASS**

---

## 20. Frozen One-Shot Package

| Field | Value |
|-------|-------|
| package_hash | `bdd77912ccdde41d2245ed36a95071335af68b06b1e005f41c153f86314bba46` |
| execution_status | **NOT_EXECUTED** |
| interpretation_contract_hash | `3474a096aa6ee9c57ee1120f4a41398b08307038b23220016fa6bc9fddff77e2` |
| selected_experiment_content_hash | `624e91d23ea6ec56ee4f00d9346acc01475e999c6e891ece3e82b7a6c4396e6e` |

Full package: `diagnostics/phase_3i9_falsification_selection/artifacts/09_one_shot_package.json`

---

## 21. Remaining Limitation

Single interpreter-compatible tool path (partition_group_compare). Sensitivity/robustness tools require future FalsificationInterpretationContract variant. Package not yet executed or interpreted.

---

## 22. Proposed Next Phase

**Phase 3I.10 — One-Shot Falsification Execution:** Execute frozen package once, interpret via frozen 3I.7 contract, append second EpistemicUpdateRecord to lineage.

---

## Final Answers

### A. Did Mr.BOT autonomously derive multiple possible ways to challenge its proposition?

**Partially for real selection, yes for audit.** Real run: 1 viable candidate (holdout). BB audit run: 6 candidates with distinct classifications. Vulnerabilities and strategies derived from proposition, not templates.

### B. Did it distinguish genuine falsification from confirmatory retesting, representation changes, and rescue?

**Yes.** Confirmatory retest, tool-only change, population narrow, horizon mutation all rejected by gates.

### C. Did it autonomously choose a falsification experiment without knowing its result?

**Yes.** Selection from vulnerability-driven candidate set only; no ToolResult read; no Zone C.

### D. Is there a frozen experiment package executable once without further scientific human choice?

**Yes.** Package `bdd77912...` frozen with ExperimentSpec, interpretation requirements, cutoff policy, and `execution_status: NOT_EXECUTED`.

---

**STOP.** Falsification experiment not executed.
