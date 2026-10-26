# Phase 3I.15 — Autonomous Next Scientific Action Readiness

**Mode:** AUDIT + DESIGN ONLY  
**Verdict:** `PARTIALLY_READY`  
**Date:** 2026-08-22  
**Branch:** `cursor/phase-3i15-next-action-readiness-aad2`  
**HEAD:** `5cf324189569` (3I.14 automatic lifecycle synthesis hook)  
**Prior accepted phase:** 3I.14 `AUTOMATIC_SYNTHESIS_HOOK_PASS`

No next-action generator was implemented. No new market experiment was executed.

Audit runner: `diagnostics/phase_3i15_next_action_readiness/run_audit.py`  
Artifacts: `diagnostics/phase_3i15_next_action_readiness/artifacts/`

---

## 1. Branch / HEAD / PR / git status

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3i15-next-action-readiness-aad2` |
| HEAD | `5cf324189569` |
| Base | 3I.14 automatic lifecycle synthesis hook |
| Mode | AUDIT + DESIGN ONLY |
| New experiment | **No** |
| Implementation | **No** |
| Engine hash (frozen) | `ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a` |

Summary artifact: `artifacts/23_audit_summary.json`

---

## 2. Mode confirmation

This phase audited whether Mr.BOT can autonomously transform a body-of-evidence `ResearchPriorityDecision` and its unresolved uncertainty structure into scientifically meaningful candidate next actions — without human/template choice and without knowing future results.

**Explicitly not done:**
- Next-action generator implementation
- Market experiment execution
- Proposition mutation
- Synthesis engine or priority rule changes
- Planner/Challenger/trading integration

---

## 3. Current capability inventory

**Central answer:** No existing component transforms arbitrary unresolved uncertainty from `ResearchPriorityDecision` into scientifically meaningful candidate next actions.

| Mechanism | Classification | Uncertainty→Action? |
|-----------|----------------|---------------------|
| `FalsificationCandidateGenerator` (3I.9) | PROPOSITION_SCOPED, TOOL_BOUND, TEMPLATE_BOUND | **No** — one holdout strategy; gates on immediate `ResearchDecisionRecord` |
| `FalsificationSelector` (3I.9) | EXECUTION_ONLY | **No** — selects among pre-generated candidates |
| `FalsificationExecutionRunner` (3I.10) | EXECUTION_ONLY | **No** |
| `generate_action_candidates` | GAP_BOUND, TEMPLATE_BOUND, TOOL_BOUND | **No** — requires Phase-2 GAP codes + completed experiment |
| `ResearchGrammar` proposers | GENERIC (needs question context) | **No** — reframing only; no cold-start from synthesis |
| `EvidenceSynthesisEngine` (3I.12) | PROPOSITION_SCOPED | **No** — emits priority enum, not actions |
| `LifecycleSynthesisHook` (3I.14) | DISCONNECTED from action gen | **No** — `ACTION_RECORDED_ONLY → STOP` |
| `PropositionSynthesizer` | DISCONNECTED | **No** — upstream observation→proposition |
| ResearchPlanner / Controller | EXECUTION_ONLY | **No** — selects GAP-bound pool |
| Discovery / Challenger | DISCONNECTED | **No** — separate Phase-2 model |
| `uncertainty_coverage.py` | GENERIC taxonomy | **No** — axis names only |

**Two stacks remain disconnected:**
- **Stack A:** GAP → `generate_action_candidates` → planner
- **Stack B:** synthesis → `ResearchPriorityDecision` → `ACTION_RECORDED_ONLY`

No bridge connects Stack B to action candidate generation.

Artifact: `artifacts/01_capability_inventory.json`

---

## 4. Source-of-authority audit

Preserved 3I.14 hierarchy:

| Role | Authority |
|------|-----------|
| Single-result interpretation | `EpistemicUpdateRecord` |
| Current proposition knowledge | `EvidenceSynthesisRecord` |
| Next research-budget recommendation | `ResearchPriorityDecision` |
| Immediate single-evidence (transitional) | `ResearchDecisionRecord` — **must not override** multi-evidence priority |

**Violations for next-action layer:**
1. `FalsificationCandidateGenerator` gates on `ResearchDecisionRecord.chosen_next_action`, not `ResearchPriorityDecision`.
2. `generate_action_candidates` uses GAP codes from `ResearchAssessment` — unrelated authority chain.

The next-action layer must consume `ResearchPriorityDecision` + `EvidenceSynthesisRecord` + immutable `PropositionRecord`.

Artifact: `artifacts/02_source_of_authority_audit.json`

---

## 5. Objective / action / ExperimentSpec separation

**Required causal order:**

```
uncertainty → ScientificObjective → ScientificAction → ExperimentSpec → tool
```

**Forbidden:** `available_tool → invent reason to use it`

| Layer | Definition | Must not include |
|-------|------------|------------------|
| **ScientificObjective** | What epistemic vulnerability to attack | tool_name, ExperimentSpec, GAP_code |
| **ScientificAction** | Concrete testable operation for that objective | tool as identity, template_id as semantics |
| **ExperimentSpec** | Executable representation of chosen action | Must be derived after scientific ranking |

Artifact: `artifacts/03_objective_action_separation.json`

---

## 6. ScientificObjectiveRecord design

Minimal immutable record derived from synthesis/priority:

| Field | Purpose |
|-------|---------|
| `objective_id`, hashes | Identity + lineage |
| `proposition_id/hash`, `synthesis_id/hash`, `priority_decision_id/hash` | Provenance |
| `target_uncertainty` | Single axis from `uncertainty_unresolved` |
| `scientific_vulnerability` | e.g. episode_instability, directional_reversal |
| `reason_this_uncertainty_matters` | From saturation + synthesis rationale |
| `current_evidence_coverage` | Axes touching this uncertainty |
| `desired_information_gain_type` | falsify / replicate / resolve_contradiction / expose_counterexample |
| `disconfirming_potential`, `contradiction_resolution_potential` | Pre-result capability flags |
| `independence_requirement` | Min profile vs prior ledger |
| `forbidden_rescue_mutations` | outcome, horizon, population_refine, feature |
| `provenance_refs`, `objective_hash` | Audit trail |

**Excluded at objective stage:** tool name, ExperimentSpec, GAP code, template ID.

Artifact: `artifacts/04_scientific_objective_record_design.json`

---

## 7. ScientificActionRecord design

**ScientificActionCandidateRecord** — generic candidate:

| Field | Purpose |
|-------|---------|
| `objective_ref` | Link to ScientificObjectiveRecord |
| `action_scientific_semantics` | Auditable description |
| `evidence_cohort_strategy` | full / holdout / regime_split / population_contrast / counterexample_search |
| `variable_population_outcome_commitments` | Proposition-aligned — no rescue |
| `relationship_to_prior_experiments` | REPLICATION / PARTIAL_REPLICATION / INDEPENDENT / REDUNDANT |
| `expected_new_uncertainty_coverage` | Axis if informative |
| `expected_independence_profile` | 7-dimension estimate |
| `possible_informative_outcomes`, `possible_non_informative_outcome` | Epistemic consequence pre-registration |
| `falsification_capability`, `contradiction_resolution_capability` | Capability flags |
| `rescue_risk`, `redundancy_classification` | Anti-rescue + dedup |
| `executability_status` | Tool/grammar compatibility |
| `experiment_spec_ref` | Optional — only after selection for packaging |
| `scientific_action_core_hash`, `record_hash` | Identity |

Tool identity must not define scientific novelty.

Artifact: `artifacts/05_scientific_action_record_design.json`

---

## 8. Generic uncertainty-to-action operator audit

| Operator | Classification | Template risk |
|----------|----------------|---------------|
| seek_independent_cohort | GENERIC | LOW |
| seek_counterexample | GENERIC | MEDIUM |
| test_concentration_dominance | GENERIC | MEDIUM |
| test_temporal_stability | GENERIC | **HIGH** — single holdout = TEMPLATE_TRANSLATION |
| test_population_robustness | GENERIC | MEDIUM |
| test_measurement_robustness | GENERIC | HIGH — outcome change → FORK territory |
| resolve_contradiction | GENERIC | LOW |
| test_alternative_explanation | GENERIC | MEDIUM |
| seek_replication | GENERIC | LOW |
| hold_no_high_information_action | GENERIC | NONE |
| independent_episode_holdout (3I.9) | SPECIALIZED | TEMPLATE_TRANSLATION for temporal axis |
| GAP_* → fixed tool (research_actions) | GAP_BOUND | TEMPLATE_TRANSLATION |

**Design rule:** Operator + proposition/ledger context must instantiate multiple distinct actions per broad uncertainty type.

Artifact: `artifacts/06_uncertainty_to_action_operators.json`

---

## 9. Template-creativity risk

**Test:** If uncertainty dimension X always maps to one fixed question or one fixed ExperimentSpec → `TEMPLATE_TRANSLATION`.

**Current system:** `TEMPLATE_TRANSLATION`
- 3I.9: episode/temporal uncertainty → exactly `independent_episode_holdout`
- `research_actions`: each GAP → fixed `action_code` + `question_template_id` + tool
- No branching on `saturation_assessment` or `independence_profiles` for action semantics

**Valid generator must:**
- Yield ≥2 distinct actions for same broad uncertainty when ledger context differs
- Change action semantics when unresolved set changes
- Change ranking when prior evidence independence changes

**T2 case:** Generic holdout is redundant (`episode_robustness` in `redundant_test_axes`) — another holdout would be representation-only exploration.

Artifact: `artifacts/07_template_creativity_risk.json`

---

## 10. Scientific action identity

**ScientificActionCore** (identity):
- objective target uncertainty
- evidence cohort **semantics** (not raw date lists)
- proposition commitment challenged
- causal/contrast relation
- expected epistemic consequence type

**Representation envelope** (non-identity):
- tool, parameterization, grouping implementation, syntax

**Rules:**
- Same core hash → same scientific action regardless of tool
- Reject if core hash matches executed action in ledger
- Lessons from 3H.10–3H.13: representation-only tool swap must not inflate novelty

**Action diversity example** — `temporal_regime_robustness`:
- Distinct: episode holdout, rolling stability, regime-separated contrast, counterexample-period search
- Not distinct: same cohort via different tool or SQL syntax

Artifact: `artifacts/08_scientific_action_identity.json`

---

## 11. Expected information contribution design

**Pre-result only** — no ToolResult access.

**Lexicographic dominance layers:**
1. INVALID / RESCUE_RISK → reject
2. REDUNDANT (core hash or `redundant_test_axes`) → reject
3. Non-executable → deprioritize vs executable (preserve record)
4. Priority alignment (SEEK_FALSIFICATION → falsification-capable first)
5. Attacks major unresolved non-redundant uncertainty
6. Higher expected independence vs ledger
7. Contradiction-resolution when `contradiction_structure` non-empty
8. Lower cohort correlation (`cohort_overlap_ratio`)

No tuned weighted scoring.

Artifact: `artifacts/09_expected_information_contribution.json`

---

## 12. Epistemic consequence matrix

Pre-registration of interpretability — not result prediction.

Every candidate must specify:
| Outcome | Required specification |
|---------|------------------------|
| Supporting | Which uncertainty axes move toward covered |
| Disconfirming | Epistemic state transition; priority shift |
| Conflicting | Contradiction structure update |
| Non-informative | What remains unknown |
| Invalid | Ideally no scientific state change |

Artifact: `artifacts/10_epistemic_consequence_matrix.json`

---

## 13. Anti-confirmation controls

| Threat | Current protection | Gap |
|--------|-------------------|-----|
| Confirmatory identical retest | 3I.9 content hash check | No multi-evidence generator applies this |
| Favorable cohort selection | Holdout excludes motivating dates | Not synthesis-aware |
| Repeating strongest period | — | No generator |
| Representation-only exploration | 3I.12 `redundant_test_axes` | Generator ignores redundant axes |

Artifact: `artifacts/11_anti_confirmation_controls.json`

---

## 14. Anti-rescue controls

**Forbidden:** narrower population, different horizon, changed outcome, changed proposition semantics to recover support.

**Current:** `_check_anti_rescue` in 3I.9; proposed `forbidden_rescue_mutations` on ScientificObjectiveRecord.

**Rule:** Rescue mutations valid only as future FORK — out of scope. Contradiction must not trigger rescue.

Artifact: `artifacts/12_anti_rescue_controls.json`

---

## 15. Anti-endless-testing controls

Generator must emit `NO_HIGH_INFORMATION_ACTION` when:
- Major executable axes saturated
- Remaining candidates all REDUNDANT
- Only representation changes remain
- No interpretable experiment can materially update knowledge

**Current:**
- Priority level: YES (3I.12 HOLD_PROVISIONALLY / HOLD_UNRESOLVED)
- Action candidate level: **NOT IMPLEMENTED**

Artifact: `artifacts/13_anti_endless_testing.json`

---

## 16. Priority-to-action semantics

| Priority | Allowed | Forbidden |
|----------|---------|-----------|
| **SEEK_FALSIFICATION** | Falsification-capable actions on major non-redundant axes | Confirmatory retest; redundant holdout; rescue |
| **SEEK_REPLICATION** | Independent replication with HIGH sample independence | Identical ExperimentSpec retest |
| **SEEK_CONTRADICTION_RESOLUTION** | Discriminating actions on contradiction_structure | Ignoring contradiction; rescue |
| **HOLD_PROVISIONALLY** | Silence; document low-info options without selecting | Experiment merely because generator can |
| **HOLD_UNRESOLVED** | Silence; catalog non-executable valid ideas | Forced experiment selection |
| **ABANDON** | NO_HIGH_INFORMATION_ACTION only | Rescue; new falsification |

Artifact: `artifacts/14_priority_to_action_semantics.json`

---

## 17. 3I.9 falsification reuse audit

| Category | Items |
|----------|-------|
| **Genuinely generic** | `derive_proposition_vulnerabilities`, anti-rescue, executability pattern, outcome text binding |
| **SEEK_FALSIFICATION-tied** | Gate on immediate decision; VulnerabilityKind framing; counterfactual_falsifiable semantics |
| **Partition-assumption** | Hard-coded `partition_group_compare`; quintile contrast only |
| **Reusable as specialized operator** | Episode holdout construction (when not redundant); directional_reversal vulnerability |
| **Must remain specialized** | Full generator as standalone next-action path |

**Recommendation:** `FalsificationOperator` under `ScientificActionGenerator` when priority=SEEK_FALSIFICATION and axis compatible.

Artifact: `artifacts/15_falsification_reuse_audit.json`

---

## 18. Tool/interpreter compatibility

| Classification | Meaning |
|----------------|---------|
| SCIENTIFICALLY_VALID_EXECUTABLE | Core valid; grammar + tool + sample pass |
| SCIENTIFICALLY_VALID_NOT_EXECUTABLE | Core valid; preserve for future capability |
| EXECUTABLE_BUT_LOW_INFORMATION | Runs but REDUNDANT or saturated |
| REPRESENTATION_ONLY | Same core as prior; different envelope |
| RESCUE_RISK | Anti-rescue fail |
| INVALID | Grammar/leakage violation |

**Rule:** Do not distort scientific action to fit tools silently.

OPR interpreter today: primarily `partition_group_compare`.

Artifact: `artifacts/16_tool_interpreter_compatibility.json`

---

## 19. BB-NextAction-01 design

Frozen abstract benchmark — **18 cases**, **2 proposition families** (`partition_contrast`, `context_modulation`).

Development firewall: no `rs_spread`, `t5_return`, `prop-efb650d9bd5c451f`.

Cases cover: temporal/population/measurement robustness, contradiction resolution, replication, saturation silence, falsified rescue temptation, HOLD_PROVISIONALLY silence, non-executable interpreter, same-action-two-tools, multi-distinct-actions, high-info vs redundant, correlated cohort disguise, leakage, template lure, proposition-mutation requirement, counterexample search, FORK temptation with immutable proposition.

Artifact: `artifacts/17_bb_next_action_01_design.json`

---

## 20. Creativity/adaptivity counterfactuals

| ID | Manipulation | Expected | Current |
|----|--------------|----------|---------|
| CF-01 | Change unresolved uncertainty; hold tools | Action set changes | **FAIL** |
| CF-02 | Change evidence independence | Ranking changes | **FAIL** |
| CF-03 | Remove contradiction | Resolution actions disappear | **FAIL** |
| CF-04 | Saturate one axis | Actions lose priority | **PARTIAL** (synthesis only) |
| CF-05 | Change tool availability only | Objective unchanged; executability may change | **FAIL** |
| CF-06 | Representation only change | Core hash unchanged | **NOT TESTED** |

All CF tests must pass in 3I.16.

Artifact: `artifacts/18_creativity_adaptivity_counterfactuals.json`

---

## 21. Human-choice audit

| Locus | Current | Classification |
|-------|---------|----------------|
| Uncertainty axis to pursue | Synthesis ranks; human chose holdout in 3I.9 | autonomy_blocker |
| Scientific objective | Implicit single strategy in 3I.9 | partially_automated |
| Candidate action generation | One holdout or GAP templates | **autonomy_blocker** |
| Cohort choice | Algorithmic holdout; not synthesis-aware | scientific_prior_in_code |
| Experiment design | Fixed quintile partition | tool_bound |
| Tool selection | partition_group_compare hard-coded | partial execution constraint |
| Selector outcome | Lexicographic 3I.9 | legitimate execution |
| Multi-evidence priority | Automated 3I.12 | autonomous |

**Highest-leverage autonomy blocker:** Candidate action generation from `ResearchPriorityDecision` + unresolved uncertainty structure.

Artifact: `artifacts/19_human_choice_audit.json`

---

## 22. Current real proposition diagnostic (T2 — LAST)

**Frozen state** (from `artifacts/05_hook_t2_replay.json`):
- State: **SUPPORTED**
- E2: **PARTIAL_REPLICATION** (~97.7% cohort overlap)
- Covered: directional_effect_full_universe, episode_robustness
- Redundant: episode_robustness
- Priority: **SEEK_FALSIFICATION** on non-redundant axes
- Unresolved: temporal_regime, population, horizon, effect_stability, concentration, measurement, counterexample, alternative_explanation, regime_context

### A. Scientific objectives derivable without human choice?

**Current system:** NONE autonomously.

**Design-derivable** (from frozen state, no execution):
1. Challenge `temporal_regime_robustness` — major unresolved, falsification-aligned
2. Challenge `population_robustness` — E2 LOW population independence
3. Test `concentration_dominance` — from null text + unresolved axis
4. Seek `counterexample_exposure` — from disconfirming_spec + unresolved axis

No component emits `ScientificObjectiveRecord` today.

### B. Multiple scientifically distinct candidate actions?

**Current:** NO — 3I.9 would emit only holdout (now **REDUNDANT**).

**Design-distinct:**
- Regime-separated quintile contrast (temporal_regime)
- Population subgroup contrast excluding prior overlap (population)
- Symbol concentration decomposition (concentration)
- Counterexample period search (counterexample)

**Not distinct:** Another episode holdout — redundant per `redundant_test_axes`.

### C. Executable with current tools?

| Candidate | Status |
|-----------|--------|
| Regime-separated contrast | SCIENTIFICALLY_VALID_EXECUTABLE (if regime column) |
| Population filter contrast | SCIENTIFICALLY_VALID_EXECUTABLE |
| Episode holdout | EXECUTABLE_BUT_LOW_INFORMATION |
| Symbol concentration | SCIENTIFICALLY_VALID_NOT_EXECUTABLE (no OPR interpreter) |

### D. Dominant by pre-result information contribution?

**Current:** Cannot compute — no candidate set.

**Design ranking:**
1. Regime-separated falsification (temporal_regime — major, non-redundant, falsification-capable)
2. Population independence contrast (population — 97.7% overlap on E2)
3. Counterexample search (counterexample_exposure)
4. **REJECT:** independent_episode_holdout (redundant_test_axes)

### E. Selected without knowing future result?

**Design:** YES — ranking uses only ledger, synthesis, proposition commitments.  
**Current:** N/A.

**Status:** NOT_EXECUTED — diagnostic only.

Artifact: `artifacts/20_t2_diagnostic.json`

---

## 23. Readiness verdict

### `PARTIALLY_READY`

**Rationale:** Body-of-evidence synthesis, uncertainty taxonomy, saturation assessment, and `ResearchPriorityDecision` exist and are lifecycle-integrated (3I.12–3I.14). No component transforms priority + unresolved uncertainty into ranked `ScientificAction` candidates. Exactly **one** general capability remains.

Artifact: `artifacts/21_readiness_verdict.json`

---

## 24. Exactly one missing capability

**`ScientificActionGenerator`**

```
ResearchPriorityDecision
  + EvidenceSynthesisRecord
  + PropositionRecord
  → ScientificObjectiveRecord(s)
  → ScientificActionCandidateRecord(s)  [via generic operators]
  → ScientificActionCore semantic dedup
  → pre-result lexicographic ranking
  → SELECT | HOLD | NO_HIGH_INFORMATION_ACTION
  → freeze NextActionPackage
  → STOP (no execution)
```

Must consume multi-evidence priority — not override with immediate `ResearchDecisionRecord`.

---

## 25. Minimal 3I.16 boundary (if PARTIALLY_READY → next implement phase)

| Must include | Must not |
|--------------|----------|
| BB-NextAction-01 fixtures + development firewall | Execute experiment |
| Generic operators + FalsificationOperator (3I.9 reuse) | Mutate proposition |
| `redundant_test_axes` enforcement before emission | Alter synthesis engine |
| T2 one-shot diagnostic (NOT_EXECUTED package) | Alter priority rules |
| Semantic dedup + lexicographic ranking | Wire planner/controller |

Artifact: `artifacts/22_minimal_3i16_boundary.json`

---

## 26. Proposed next phase only

**Phase 3I.16 — Minimal Scientific Action Generator**
1. Implement record types + core hash
2. Implement operator registry (generic + FalsificationOperator)
3. Run BB-NextAction-01 (18/18)
4. Run T2 diagnostic (NOT_EXECUTED package)
5. STOP — no execution

---

## Final answers

### A. Can Mr.BOT currently turn "what remains worth learning" into a concrete scientific action without a human choosing the experiment?

**No.** Synthesis and priority identify *what matters* (`uncertainty_unresolved`, `SEEK_FALSIFICATION`, `redundant_test_axes`) but no component derives `ScientificObjective` or `ScientificAction` from that state. The 3I.9 falsification path requires immediate `ResearchDecisionRecord`, emits at most one holdout strategy, and ignores multi-evidence redundancy.

### B. Can it distinguish a genuinely informative next action from a different representation of an old experiment?

**Partially.** The synthesis layer detects redundancy (`redundant_test_axes`, relationship map, independence profiles). There is no action-generation layer that applies `ScientificActionCore` dedup or rejects representation-only candidates before packaging.

### C. Can it generate silence/HOLD when no high-information next action exists?

**Partially.** `ResearchPriorityDecision` can emit `HOLD_PROVISIONALLY` / `HOLD_UNRESOLVED` (3I.12). No generator emits `NO_HIGH_INFORMATION_ACTION` at the action-candidate level when all executable options are redundant.

### D. What is the smallest missing capability before the research loop can autonomously choose its next scientific move?

**`ScientificActionGenerator`** — the single bridge from `ResearchPriorityDecision` + frozen synthesis state to ranked, deduplicated `ScientificActionCandidateRecord`s with pre-result information dominance, SELECT/HOLD/NO_HIGH_INFORMATION_ACTION disposition, and frozen package — stopping before execution.

---

**STOP.** No new market experiment. No implementation.
