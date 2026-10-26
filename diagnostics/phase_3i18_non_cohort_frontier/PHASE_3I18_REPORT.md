# Phase 3I.18 — Non-Cohort Scientific Frontier Reassessment

## Verdict: `SCIENTIFIC_FRONTIER_REASSESSMENT_PASS`

**Execution status:** `NOT_EXECUTED` — no experiment run, no ToolResult read, no deployment.

---

## 1. Branch / HEAD / PR

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3i18-non-cohort-frontier-aad2` |
| Base | `main` (includes accepted 3I.17b) |
| HEAD | post-commit on branch |
| PR | opened on push |

---

## 2. Mode confirmation

**AUDIT + DESIGN** with minimal general mechanism implementation.

- No market experiment
- No ToolResult from any proposed action
- No deployment, no Zone C, no proposition mutation
- Frozen historical packages preserved

---

## 3. Frozen lineage audit

| Artifact | Status |
|----------|--------|
| PropositionRecord | Unchanged |
| E1 / E2 | Unchanged |
| EpistemicUpdateRecords | Unchanged |
| EvidenceSynthesisRecord / engine | Unchanged hash `ee00da71…` |
| ResearchPriorityDecision rules | Unchanged |
| 3I.16 ScientificActionGenerator | Unchanged (legacy selection still `rolling_stability_contrast`) |
| 3I.17 audit | Unchanged |
| 3I.17b binder + diagnostic | Unchanged; `NO_DEFENSIBLE_COHORT` consumed as constraint |
| EvidenceSynthesisEngine | Unchanged |
| Historical packages | Unchanged; all `NOT_EXECUTED` |

**New (3I.18 only):** `ScientificFrontierReassessor`, frontier records, BB-Frontier-01, specialized audits.

---

## 4. Current unresolved frontier (from frozen T2 synthesis)

| Uncertainty | Scientific meaning | Evidence coverage | Why unresolved | Partially addressed? | 3I.17b impact | Epistemic impact | Executable now? |
|-------------|-------------------|-------------------|----------------|---------------------|---------------|------------------|-----------------|
| `temporal_regime_robustness` | Effect stability across temporal regimes | E1 full universe, E2 partial replication | Listed in synthesis unresolved; major vulnerability | Yes (E2 partial) | **COHORT_UNAVAILABLE** — blocks all temporal cohort routes | Material | No |
| `population_robustness` | Generalization across subgroups | E1 full universe | No independent subgroup evidence | Partially | **COHORT_UNAVAILABLE** | Material | No |
| `horizon_robustness` | Stability across observation horizons | E1/E2 at fixed horizon | No horizon sweep | Partially | **COHORT_UNAVAILABLE** | Material | No |
| `effect_stability` | Magnitude/direction stability | Supporting E1/E2 | No stability decomposition | Partially | **COHORT_UNAVAILABLE** | Material | No |
| `regime_context_robustness` | Context/regime modulation | E1/E2 | No independent regime slice | Partially | **COHORT_UNAVAILABLE** | Material | No |
| `concentration_dominance` | Symbol/date concentration driving effect | Not directly tested | No decomposition evidence | No | None — non-cohort route exists | Marginal (peripheral) | Yes (specifiable) |
| `measurement_robustness` | Measurement specification dependence | Fixed measurement in E1/E2 | No alt-measurement test | No | None | Marginal | Yes |
| `counterexample_exposure` | Observable falsifying conditions | Proposition null present | Not yet searched | No | Temporal cohort route blocked | Marginal | Blocked (cohort-dependent operator) |
| `alternative_explanation_exposure` | Competing explanation vs null | Null in proposition | Not discriminated | No | Temporal cohort route blocked | Marginal | Blocked |

Epistemic state remains **SUPPORTED** with 9 unresolved dimensions.

---

## 5. Researchability classification

| Uncertainty | Class | Rationale |
|-------------|-------|-----------|
| temporal/population/horizon/effect/regime_context | `COHORT_UNAVAILABLE` | 3I.17b binder: `NO_DEFENSIBLE_COHORT`; no defensible independent slice |
| concentration_dominance | `RESEARCHABLE_NOW` | Non-cohort decomposition specifiable pre-result |
| measurement_robustness | `RESEARCHABLE_NOW` | Legitimate alt-measurement without proposition fork |
| counterexample_exposure | `RESEARCHABLE_NOW` (axis) / blocked (action) | Axis researchable in principle; operator uses temporal cohort exclusion → unavailable after 3I.17b |
| alternative_explanation_exposure | Same as counterexample | Requires temporal holdout path blocked by cohort failure |

**Key separation:** unresolved ≠ must investigate. Major unresolved axes are **not currently actionable** without cohort independence.

---

## 6. Available scientific strategy audit (from 3I.16 operators)

| Strategy family | Class | Notes |
|-----------------|-------|-------|
| `population_subgroup_contrast` | cohort-dependent, redundant | Blocked: `NO_DEFENSIBLE_COHORT` |
| `regime_separated_contrast` | cohort-dependent, redundant | Blocked |
| `rolling_stability_contrast` | cohort-dependent, scientifically distinct | Blocked — was 3I.16 legacy winner |
| `episode_holdout_excluding_motivating` | cohort-dependent | Blocked (temporal + redundant axis) |
| `counterexample_period_search` | cohort-dependent (temporal exclusion) | Blocked on T2 |
| `concentration_decomposition` | **non-cohort** | Available but marginal-information gate |
| `measurement_robustness_check` | **non-cohort** | Available but marginal-information gate |
| `contradiction_discriminating_test` | non-cohort | Not generated for current T2 context |
| Low-information cohort fallbacks | representation-only / redundant | Rejected at frontier |

No rule equates `unresolved == must investigate`.

---

## 7. Cohort-failure propagation audit

- All `COHORT_DEPENDENT_STRATEGIES` pass through `_is_available()` with 3I.17b disposition check.
- `NO_DEFENSIBLE_COHORT` → action **UNAVAILABLE**; cannot be renamed into availability.
- `episode_holdout_excluding_motivating` blocked when temporal cohort unavailable (CF-F3).
- `counterexample_period_search` blocked when temporal cohort unavailable (semantic leakage test).
- CF-F3: **0 cohort-dependent actions remain available** under full cohort removal.

---

## 8. Frontier scientific identity audit

- Scientific identity = `scientific_action_core_hash` (ScientificActionCore).
- BBF-11/BBF-12: tool rename and strategy rename do not create duplicate scientific value.
- `_rank_frontier_key` uses structured marginal-information dimensions, not strategy name.
- Principle enforced: **new tool ≠ new scientific action**; **new strategy name ≠ new scientific action**.

---

## 9. Marginal information framework

Structured `MarginalInformationProfile` per candidate:

- unresolved dimension addressed
- ledger overlap estimate (from `max_cohort_overlap`)
- evidence independence (from candidate profile)
- counterexample potential
- vulnerability challenge (major vs peripheral)
- epistemic state change potential
- redundancy / executability / rescue risk

Lexicographic dominance (pre-result only): non-cohort → rescue → redundancy → vulnerability → independence → epistemic consequence → executability → axis tiebreak.

**Marginal-information gate:** when `priority.marginal_information=low` and no eligible action addresses `major_unresolved`, return `NO_HIGH_INFORMATION_ACTION` even if peripheral non-cohort actions are technically available.

---

## 10. Counterexample-search audit

| Check | T2 result |
|-------|-----------|
| Infrastructure generates counterexample candidates | Yes |
| Derives from proposition null | Yes (`null_competing_explanation` in proposition) |
| Uses future outcome | No |
| Panel subgroup mining | No |
| Valid pre-result specification | Yes (in abstract cases) |
| **T2 availability** | **Blocked** — operator path requires temporal cohort exclusion; 3I.17b `NO_DEFENSIBLE_COHORT` |

Capability exists; T2 route unavailable under cohort constraint. Not faked with templates.

---

## 11. Concentration/dominance audit

| Check | Result |
|-------|--------|
| Specifiable pre-result | Yes |
| Preserves proposition (no fork) | Yes — all candidates pass rescue |
| Scientifically valid | Yes |
| **Selected on T2?** | No — peripheral axis; marginal-information gate |

---

## 12. Measurement-robustness audit

| Check | Result |
|-------|--------|
| Tests same proposition (A) | Yes |
| Representation-only duplicate (B rejected) | 0 representation-only duplicates |
| Creates new proposition | No |
| Classification | `A_legitimate_robustness` |
| **Selected on T2?** | No — marginal-information gate |

---

## 13. Alternative-explanation audit

| Check | Result |
|-------|--------|
| Can formulate without human hypothesis | Yes — from proposition `null_competing_explanation` |
| Hardcoded alternative injected | No |
| T2 candidate | Generated but blocked (temporal cohort path) |

---

## 14. Priority reassessment

After removing invalid/redundant/unavailable actions and applying marginal-information gate:

**Authoritative frontier decision: `NO_HIGH_INFORMATION_ACTION`**

Not forced to `SELECTED_NON_COHORT_ACTION`. Silence is scientifically superior to peripheral activity.

---

## 15. Selection principle

Lexicographic pre-result ordering applied. On T2:
- Cohort-dependent major-vulnerability actions: unavailable
- Peripheral non-cohort actions: available individually but fail major-unresolved + low marginal-information gate
- No ambiguous tie among viable high-information actions

---

## 16. BB-Frontier-01 results

**20/20 passed** — see `artifacts/01_bb_frontier_01.json`

Covers all 20 pre-registered cases: cohort unavailable with non-cohort route, all redundant → HOLD, counterexample valid/blocked, concentration valid/blocked, measurement duplicate/legitimate, alternative requires null, ambiguity, dedup, rename, non-executable value, low-information, prior coverage, saturation HOLD, epistemic consequence, ordering perturbation, cross-family.

---

## 17. Counterfactual results

All passed — see `artifacts/02_counterfactuals.json`

| CF | Expected | Result |
|----|----------|--------|
| CF-F1 | Resolved uncertainty removes targeting actions | Pass |
| CF-F2 | Prior coverage reduces marginal information | Pass |
| CF-F3 | Cohort removal eliminates cohort actions (no rename leak) | Pass (0 available) |
| CF-F4 | Tool representation unchanged ranking | Pass (BBF-11) |
| CF-F5 | Order perturbation invariant | Pass |
| CF-F6 | Non-executable preserves scientific value | Pass |
| CF-F7 | All redundant → HOLD/NO_HIGH_INFORMATION | Pass |
| CF-F8 | Independent vulnerability changes frontier | Pass |

---

## 18. Real T2 complete frontier

| uncertainty | candidate scientific action | identity | redundancy | independence | epistemic consequence | executability | disposition |
|-------------|----------------------------|----------|------------|--------------|----------------------|---------------|-------------|
| temporal_regime_robustness | regime_separated_contrast | 34dae4d4… | REDUNDANT | LOW | MATERIAL | EXECUTABLE_BUT_LOW_INFORMATION | UNAVAILABLE |
| temporal_regime_robustness | rolling_stability_contrast | ca388af6… | NOVEL | MEDIUM | MATERIAL | SCIENTIFICALLY_VALID_EXECUTABLE | UNAVAILABLE |
| population_robustness | population_subgroup_contrast | efe9abd4… | REDUNDANT | LOW | MATERIAL | EXECUTABLE_BUT_LOW_INFORMATION | UNAVAILABLE |
| horizon_robustness | regime_separated_contrast | c73ae600… | REDUNDANT | LOW | MATERIAL | EXECUTABLE_BUT_LOW_INFORMATION | UNAVAILABLE |
| effect_stability | regime_separated_contrast | f1d224ff… | REDUNDANT | LOW | MATERIAL | EXECUTABLE_BUT_LOW_INFORMATION | UNAVAILABLE |
| concentration_dominance | concentration_decomposition | e2da9569… | NOVEL | MEDIUM | MATERIAL | SCIENTIFICALLY_VALID_EXECUTABLE | AVAILABLE (gated) |
| measurement_robustness | measurement_robustness_check | e6a28c04… | NOVEL | UNKNOWN | MATERIAL | SCIENTIFICALLY_VALID_EXECUTABLE | AVAILABLE (gated) |
| counterexample_exposure | counterexample_period_search | 6fa40d4f… | NOVEL | UNKNOWN | MATERIAL | SCIENTIFICALLY_VALID_EXECUTABLE | UNAVAILABLE |
| alternative_explanation_exposure | counterexample_period_search | d999bc7d… | NOVEL | UNKNOWN | MATERIAL | SCIENTIFICALLY_VALID_EXECUTABLE | UNAVAILABLE |
| regime_context_robustness | regime_separated_contrast | 5aa48f99… | REDUNDANT | LOW | MATERIAL | EXECUTABLE_BUT_LOW_INFORMATION | UNAVAILABLE |

Full JSON: `artifacts/03_t2_frontier_diagnostic.json`

---

## 19. Authoritative frontier decision

**`NO_HIGH_INFORMATION_ACTION`**

3I.16 legacy would select `rolling_stability_contrast` (cohort leak at 3I.16 layer). 3I.18 correctly overrides with evidence-derived silence.

---

## 20. Frozen package

**None manufactured.** Silence is authoritative.

Silence rationale: major unresolved vulnerabilities (population, temporal, horizon, effect, regime) require cohort independence unavailable after 3I.17b; `marginal_information=low`; peripheral non-cohort routes do not address major unresolved axes; `max_cohort_overlap=0.9767`.

**What would reopen frontier:**
- New evidence structure with lower overlap / independent cohort
- Resolution or saturation of major unresolved axes
- Non-cohort counterexample path not requiring temporal cohort exclusion (capability extension)

**Epistemic state:** remains **SUPPORTED** — silence is rational, not contradiction.

---

## 21. Learning-vs-answer leakage audit

| Check | Result |
|-------|--------|
| Human rule preferring concentration/counterexample/measurement | **None** |
| Hardcoded NORMAL/STRESS | **None** |
| Lexicographic rank only | Yes (`_rank_frontier_key`) |
| Strategy name preference | No |
| Audit passed | **Yes** |

Phase can **PASS** — no preferred scientific answer encoded.

---

## 22. Verdict

**`SCIENTIFIC_FRONTIER_REASSESSMENT_PASS`**

Mr.BOT correctly remains silent from frozen evidence without hardcoded scientific preference. Real-T2 `NO_HIGH_INFORMATION_ACTION` is the intended superior outcome.

---

## 23. Remaining capability gap

**None** for PASS verdict.

(Optional future enhancement, not blocking: result-blind counterexample operator that does not require temporal cohort exclusion — would reopen counterexample route under current T2 constraints.)

---

## 24. Minimal proposed next phase

**Phase 3I.19 — Provisional Hold Lifecycle Integration**

Wire `NO_HIGH_INFORMATION_ACTION` / `HOLD_PROVISIONALLY` into lifecycle state so research budget stops without forcing activity; document reopen triggers from evidence/capability change.

---

## 25. Explicit confirmation

**NO EXPERIMENT EXECUTED. NO TOOLRESULT ACCESSED. NO DEPLOYMENT.**

---

## Freeze hashes

| Artifact | Hash |
|----------|------|
| EvidenceSynthesisEngine (unchanged) | `ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a` |
| ScientificActionGenerator (unchanged) | `77e665c720b3f8c5050ff1113d076c38cd2c678db8df6773711e665e3fcc7eb9` |
| ScientificFrontierReassessor (3I.18) | `bd0c4a0231bced2518f3e2febbe8ffc376154cb40f9c1a98c5c30cc30bc0834b` |
| 3I.17b binder (unchanged) | `cfaf175de409fd2e893497bc8f68d4a6ddc081b3b17158e4dfd9c266ca788b51` |
| Historical 3I.16 rolling winner core | `ca388af652d39b0c1e07b21ae908a22d7051c83d51dd8bed803cc77a9cfe7757` |

---

## Final answers A–E

| Question | Answer |
|----------|--------|
| **A.** After cohort routes failed, did Mr.BOT autonomously reconsider the broader scientific frontier? | **Yes** — full uncertainty enumeration, strategy audit, marginal-information assessment |
| **B.** Did it distinguish “still unknown” from “worth spending research budget on now”? | **Yes** — `COHORT_UNAVAILABLE` vs `RESEARCHABLE_NOW` + marginal-information gate |
| **C.** Did it find a distinct high-information action, or rationally remain silent? | **Rationally silent** — `NO_HIGH_INFORMATION_ACTION` |
| **D.** Was that conclusion invariant to tool names, strategy names, and candidate order? | **Yes** — core-hash identity, BB ordering tests, CF-F4/F5 pass |
| **E.** Did any human-authored rule secretly choose the scientific answer? | **No** — leakage audit passed |

**STOP.**
