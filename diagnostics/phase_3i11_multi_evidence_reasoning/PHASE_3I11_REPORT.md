# Phase 3I.11 — Multi-Evidence Epistemic Reasoning Readiness

**Mode:** AUDIT + DESIGN ONLY  
**Verdict:** `PARTIALLY_READY`  
**Date:** 2026-08-22  
**Branch:** `cursor/phase-3i11-multi-evidence-reasoning-aad2`  
**HEAD:** see `artifacts/17_audit_summary.json`  
**Prior accepted phase:** 3I.10 `AUTONOMOUS_FALSIFICATION_PASS`

No new experiment was executed. No multi-evidence synthesis engine was implemented. The frozen 3I.7–3I.10 proposition lineage was verified intact.

---

## 1. Git / mode confirmation

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3i11-multi-evidence-reasoning-aad2` |
| Base | 3I.10 falsification execution lineage |
| Mode | AUDIT + DESIGN ONLY |
| New experiment | **No** |
| New engine | **No** |

Artifacts: `diagnostics/phase_3i11_multi_evidence_reasoning/artifacts/`  
Audit runner: `diagnostics/phase_3i11_multi_evidence_reasoning/run_audit.py`

---

## 2. Lineage integrity (Section 2)

**Proposition:** `prop-efb650d9bd5c451f`  
**Proposition hash:** `c3aab7de80fdb9e56b7be68d517ec0e4792b711ec9772638143df3cfe4e39c9b` (recomputed match ✓)

**Frozen chain (unchanged, not regenerated):**

```
PropositionRecord
  → ExperimentSpec_1 (lifecycle_real_001)
  → ToolResult_1 → EpistemicUpdate_1 (epu-5a7bec6e47ec) SUPPORTING → SUPPORTED
  → ResearchDecision_1 (dec-c92fb28fdc13) SEEK_FALSIFICATION
  → FalsificationCandidate fc-independent_episode_holdout
  → OneShotPackage (bdd77912…)
  → ExperimentSpec_2 (624e91d2…)
  → ToolResult_2 → EpistemicUpdate_2 (epu-e75a6e8362a8) SUPPORTING → SUPPORTED
  → ResearchDecision_2 (dec-d71275b5fa30) SEEK_FALSIFICATION
```

**History summary:**  
`HYPOTHESIS → SUPPORTED → SEEK_FALSIFICATION → holdout SUPPORTING → SUPPORTED → SEEK_FALSIFICATION`

**Lineage audit:** `passed: true` (`artifacts/01_lineage_integrity.json`)

No proposition mutation. No regeneration of prior records.

---

## 3. 3I.10 `resolve_cohort` fix audit (Section 3)

**Change:** `resolve_cohort()` in `research_tools.py` now applies `research_scope.population_spec` via `apply_population_spec` / `parse_population_spec`. Previously the frozen holdout filter from 3I.9 was ignored at execution while 3I.9 executability checks did apply it.

| Question | Answer |
|----------|--------|
| **A.** Execution-correctness only? | **Yes.** Frozen ExperimentSpec already encoded holdout; fix honors pre-frozen spec. |
| **B.** New scientific choice after result knowable? | **No.** Patch landed before accepted 3I.10 artifacts; package frozen in 3I.9. |
| **C.** Holdout cohort preserved? | **Yes.** 43 holdout dates excluding `2026-08-02`; post-fix n=5964 vs erroneous pre-fix n=6106. |
| **D.** Changed selection or interpretation? | **No.** Selection frozen in 3I.9; interpretation contract unchanged. |
| **E.** ToolResult unavailable before fix? | **Partial.** Execution ran but cohort was wrong without filter — not absence of ToolResult. |

**Classification:** `EXECUTION_CORRECTNESS_ONLY`

**Contamination in accepted run:** **No.** An early development run without the filter duplicated the full-panel cohort (n=6106, metrics near-identical to Evidence 1). That run was **not** used for `AUTONOMOUS_FALSIFICATION_PASS` artifacts. Accepted ToolResult: n=5964, spread≈2.09.

**Metric evidence:**

| | Evidence 1 (full panel) | Evidence 2 (holdout, accepted) |
|--|-------------------------|--------------------------------|
| sample_size | 6106 | 5964 |
| spread | 2.35 | 2.09 |

---

## 4. Current lifecycle limitation (Section 25 precursor)

Mr.BOT today interprets **one ToolResult at a time** through a frozen `InterpretationContract`:

- `transition_mapping`: evidence class → resulting epistemic state (evidence-absolute; prior state ignored except via stored field)
- `decision_mapping`: evidence class → next action (always `SEEK_FALSIFICATION` on `SUPPORTING`)

```89:96:modules/edge_research/opr_bridge/interpretation_contract.py
    decision_mapping = {
        "SUPPORTING": "SEEK_FALSIFICATION",
        "DISCONFIRMING": "SEEK_REPLICATION",
        "DISCONFIRMING_STRONG": "ABANDON",
        "CONTRADICTORY": "SEEK_FALSIFICATION",
        "NON_INFORMATIVE": "HOLD_UNRESOLVED",
        "INVALID": "HOLD_UNRESOLVED",
    }
```

`ResearchDecisionRecord.evidence_considered` lists only the **current** evidence event. There is no synthesis over the full ledger, no saturation assessment, and no separation of epistemic uncertainty from research priority.

**Central question unanswered today:**  
*Given everything observed about this proposition, what is my epistemic position, what uncertainty remains, and is another experiment scientifically worth budget?*

---

## 5. Evidence ledger model (Section 4)

**Principle:** Raw append-only `EpistemicUpdateRecord` + linked `ExperimentSpec` / `ToolResult` remain authoritative. Ledger entries **index** them; they do not replace them.

**Record version:** `evidence_ledger_entry_v1_3i11`

**Required fields per event:**

| Category | Fields |
|----------|--------|
| Identity | `ledger_entry_id`, `proposition_id`, `epistemic_update_id`, `experiment_content_hash`, `tool_result_hash` |
| Scientific | `evidence_class`, `relationship_to_proposition`, `relationship_to_prior_evidence` |
| Scope | `population_spec`, `outcome_spec`, `observation_horizon`, `feature_semantics`, `cohort_episode_scope`, `data_cutoff` |
| Outcome | `sample_size`, `effect_direction`, `effect_magnitude`, `validity_status` |
| Structure | `independence_profile`, `contradiction_status`, `information_contribution` |
| Provenance | `provenance_hashes` |

**Explicit rejections:** No scalar confidence score. No collapsing ledger into a single posterior.

Design artifact: `artifacts/03_evidence_ledger_design.json`

---

## 6. Evidence relationship taxonomy (Section 5)

**Version:** `evidence_relationship_v1_3i11`

| Class | Definition |
|-------|------------|
| `EXACT_REPLICATION` | Identical `experiment_content_hash` |
| `REPRESENTATION_REPLICATION` | Same scientific question; instrument/representation change only |
| `PARTIAL_REPLICATION` | Overlapping cohort/measurement with subset change |
| `INDEPENDENT_REPLICATION` | New independent sample/episode; same proposition semantics |
| `INDEPENDENT_FALSIFICATION` | Disconfirm-oriented test; independent cohort design |
| `RELATED_EVIDENCE` | Same proposition; overlapping uncertainty dimension |
| `CONTRADICTORY_EVIDENCE` | Valid opposing directional implications |
| `NON_INFORMATIVE` | Valid but non-resolving |
| `INVALID` | Failed validity gate |

**Independence is NOT granted by:** tool change alone, date label alone, representation change alone.

**Reuse:** 3H `research_line_relationship`, 3I.9 `evidence_independence_class`, `compute_experiment_content_hash`.

Design artifact: `artifacts/04_evidence_relationship_taxonomy.json`

---

## 7. Evidence independence model (Section 6)

**Record:** `EvidenceIndependenceProfile` (`evidence_independence_profile_v1_3i11`)

| Dimension | Meaning |
|-----------|---------|
| `sample_independence` | Distinct row cohort vs prior experiment |
| `episode_independence` | Distinct trade_date sets / motivating episode exclusion |
| `population_independence` | Distinct `population_spec` semantics |
| `temporal_independence` | Non-overlapping time windows |
| `measurement_independence` | Distinct outcome/feature/metric formulation |
| `methodological_independence` | Distinct tool operationalizing a different test |
| `semantic_independence` | Distinct uncertainty dimension (3H cores) |

Dimensions are **not interchangeable**. Report per-dimension; avoid a single yes/no unless all relevant dimensions pass.

Design artifact: `artifacts/05_independence_profile_design.json`

---

## 8. Multi-evidence epistemic state (Section 9)

**Existing states are sufficient.** No new states such as `DOUBLY_SUPPORTED`.

| State | Role |
|-------|------|
| `PROPOSED` | Initial |
| `UNDER_TEST` | Active experiment |
| `SUPPORTED` | Compatible evidence; not proven |
| `WEAKENED` | Disconfirming but not falsified |
| `CONFLICTED` | Valid opposing independent evidence |
| `FALSIFIED` | Strong disconfirmation; preserved |
| `UNRESOLVED` | Insufficient / non-informative |
| `ABANDONED` | Research abandoned |
| `INSUFFICIENT_EVIDENCE` | Validity/sample failure |

**Note:** `HOLD_PROVISIONALLY` is a **ResearchPriorityDecision**, not an epistemic state. Provisional hold means research-usable for now — not proven true.

Design artifact: `artifacts/06_multi_evidence_state_design.json`

---

## 9. Evidence accumulation is not vote counting (Section 7)

**Explicitly rejected:**

- 2 SUPPORTING > 1 DISCONFIRMING
- Majority vote / experiment-count confidence
- Fixed N confirmations = accepted / N failures = rejected

Two highly correlated supporting experiments must **not** automatically outweigh one strong independent contradiction. Reasoning uses scientific information structure: independence, uncertainty coverage, contradiction resolution — not counts.

---

## 10. No Bayesian pseudo-precision (Section 8)

**Rejected:** Invented posterior probabilities (e.g. "83% confidence") without a defensible generative model.

**Preferred representation:**

- Categorical epistemic state
- Structured evidence ledger
- Evidence balance / contradiction structure
- Independence structure
- Unresolved uncertainty dimensions
- Information saturation assessment

---

## 11. Prior-state-conditioned reasoning (Section 10)

**Current limitation:** 3I.7 `transition_mapping` is evidence-absolute.

**Design:** `prior_state_conditioned_transition_table` — preregistered before synthesis implementation.

| Prior + New evidence | Required properties | Possible outcomes |
|----------------------|---------------------|-------------------|
| SUPPORTED + independent SUPPORTING | High episode/sample independence; dimension coverage | SUPPORTED unchanged; not auto-upgrade |
| SUPPORTED + independent DISCONFIRMING | Valid; independent cohort | WEAKENED, CONFLICTED, FALSIFIED (strong) |
| SUPPORTED + strong CONTRADICTORY | Valid opposing implications | CONFLICTED |
| WEAKENED + independent SUPPORTING | Conflict structure resolved? | SUPPORTED or CONFLICTED |
| CONFLICTED + additional contradiction | — | CONFLICTED persists; seek resolution |
| UNRESOLVED + informative | Valid resolving evidence | Per evidence class |
| FALSIFIED + later SUPPORTING | — | FALSIFIED preserved; anomaly flag; no resurrection |

Design artifact: `artifacts/07_prior_state_reasoning_design.json`

---

## 12. Scientific asymmetry (Section 11)

Support and falsification are **asymmetric**:

- Many compatible observations do not eliminate vulnerability to one strong independent contradiction.
- One contradiction may reflect noise, regime dependence, invalid measurement, population mismatch, or sampling instability — not necessarily proposition falsity.

**Generic distinction principles:**

| Signal type | Interpretation axis |
|-------------|---------------------|
| Challenge to proposition | Valid, independent, same semantic core |
| Challenge to universality | Valid but regime/population scoped |
| Invalid evidence | Validity gate failure |
| New proposition opportunity | Contradiction suggests narrower scope — **FORK deferred** |

Counterexample search keeps the original proposition **immutable**. Failure-condition discovery → interpret first; FORK only in a future phase.

---

## 13. Unresolved uncertainty representation (Section 12)

**Record version:** `unresolved_uncertainty_v1_3i11`

Example dimensions (not mandatory hard-coded priors):

- episode_robustness, temporal_robustness, population_robustness, horizon_robustness
- effect_stability, concentration/dominance, alternative_explanations
- measurement_robustness, regime_dependence, statistical_resolution

**Derivation:** From proposition canonical core + `disconfirming_observation_spec` + ledger coverage map.

**Representation:** Set of uncovered dimensions with executability hints — not a scalar.

Design artifact: `artifacts/08_unresolved_uncertainty_design.json`

---

## 14. Information contribution (Section 13)

**Mechanism:** `lexicographic_marginal_information_v1_3i11`

Ordered checks (dominance / set-coverage, not tuned weights):

1. Covers new uncertainty dimension?
2. Increases independence on untested dimension?
3. Resolves existing contradiction?
4. Non-redundant robustness gain?
5. Falsification opportunity unexhausted?
6. Evidence saturation not reached?

**Rejects:** experiment count, majority vote, N-confirmation rules.

Design artifact: `artifacts/09_information_contribution_design.json`

---

## 15. Evidence saturation (Section 16)

**Record:** `EvidenceSaturationAssessment` (`evidence_saturation_assessment_v1_3i11`)

**Forbidden:** after-2-supports-stop, after-3-tests-stop.

**Derived from:**

- Uncertainty dimension coverage completeness
- Diminishing independence between proposed experiments
- Presence/absence of unresolved contradictions
- Remaining executable high-value falsification opportunities
- Marginal information below threshold

**Outputs:** `NOT_SATURATED`, `PARTIALLY_SATURATED`, `SATURATED_FOR_CURRENT_UNCERTAINTY`

Silence / HOLD is allowed.

Design artifact: `artifacts/10_saturation_design.json`

---

## 16. Falsification sufficiency (Section 14)

**Problem:** 3I.7 always returns `SEEK_FALSIFICATION` after every `SUPPORTING` result.

**Valid next actions:**

- `SEEK_FALSIFICATION`
- `SEEK_REPLICATION`
- `SEEK_CONTRADICTION_RESOLUTION`
- `HOLD_PROVISIONALLY` — evidence sufficient for research-usable provisional status; marginal value lower than other frontier questions; **NOT proven true**
- `HOLD_UNRESOLVED`
- `ABANDON`

**Falsification no longer highest value when:**

- Episode robustness covered by independent holdout
- Remaining falsification axes redundant with ledger
- Saturation = `SATURATED_FOR_CURRENT_UNCERTAINTY`
- No executable counterexample axis with marginal information

Design artifact: `artifacts/11_falsification_sufficiency_design.json`

---

## 17. Research-budget opportunity cost (Section 15)

**Distinction:** epistemic uncertainty ≠ research priority.

A proposition can remain uncertain while no longer deserving the next unit of research budget.

**Existing infrastructure (future join, not integrated):**

- `research_frontier.py` — unexplored action queue
- Portfolio/branch intelligence — branch-scoped, not proposition-scoped
- Template information value — not OPR ledger

Future join key: `proposition_id`. Integration deferred.

Design artifact: `artifacts/12_research_priority_design.json`

---

## 18. Counterexample search (Section 17)

After repeated support, the highest-value action may become **search for conditions under which the proposition fails** — not another generic holdout.

This is distinct from hypothesis rescue (narrowing the proposition). Original proposition stays immutable; FORK deferred.

---

## 19. Conflict reasoning (Section 18)

Conflicting evidence is represented **without averaging**.

Example: Evidence A (strong independent SUPPORTING) + Evidence B (strong independent DISCONFIRMING) → enter **CONFLICTED**; propose resolution experiment.

No forced winner via counts or magnitude alone unless scientifically justified (e.g. INVALID on one branch).

---

## 20. Anti-confirmation-bias controls (Section 19)

| Control | Mechanism |
|---------|-----------|
| Repeated supportive replication | Independence profile + saturation; correlated supports do not stack |
| Cherry-picked cohorts | Population spec provenance; relationship taxonomy |
| Favorable population slices | Uncertainty dimension coverage audit |
| Ignoring contradictory evidence | CONFLICTED state mandatory; contradiction structure in synthesis |
| Downweighting disconfirmation | INVALID vs DISCONFIRMING separation; validity gates |
| Moving uncertainty after results | Preregistered uncertainty dimensions from proposition core |
| Saturation as truth | HOLD_PROVISIONALLY ≠ proven |
| Premature falsification stop | Falsification sufficiency requires axis exhaustion, not support count |

---

## 21. Anti-endless-skepticism controls (Section 20)

| Control | Mechanism |
|---------|-----------|
| Infinite SEEK_FALSIFICATION loops | Saturation assessment; marginal information collapse |
| Impossible universal proof | HOLD_PROVISIONALLY when dimensions covered |
| Budget after marginal collapse | ResearchPriorityDecision decoupled from epistemic state |
| Refusing provisional knowledge | Independent evidence on covered dimensions → HOLD allowed |
| Testing every representation | REPRESENTATION_REPLICATION flagged as low marginal information |

---

## 22. Proposed records (Section 21)

| Record | Purpose |
|--------|---------|
| `EvidenceLedgerEntry` | Index `EpistemicUpdateRecord` + experiment metadata; no duplicate metrics |
| `EvidenceSynthesisRecord` | Immutable snapshot: evidence considered, relationships, independence, contradictions, uncertainty coverage, saturation, resulting state, `synthesis_hash` |
| `ResearchPriorityDecision` | Separate from single-evidence `ResearchDecisionRecord`; epistemic state + saturation + marginal information + chosen priority action + frontier rationale |

Implementation deferred to 3I.12 except diagnostic fixtures if needed.

Design artifact: `artifacts/13_proposed_records_design.json`

---

## 23. Evidence-causality requirement (Section 22)

Any multi-evidence decision must cite **exact evidence properties** responsible.

**Counterfactual test design:**

1. Remove a decisive ledger entry → synthesis state/action should change where appropriate.
2. Reverse scientific implication of an entry (e.g. INVALID instead of DISCONFIRMING) → state/action should change.
3. Swap correlated support for independent support → saturation / priority should change.
4. Add representation-only replication → marginal information should not increase materially.

Tests to be implemented in 3I.12 on BB-Epistemic-01 fixtures.

---

## 24. BB-Epistemic-01 (Section 23)

**Benchmark ID:** `BB-Epistemic-01`  
**Mode:** design only (fixtures deferred to 3I.12)  
**Requirement:** abstract feature/outcome names (not `rs_spread` / `t5_return`)

| Case | Scenario | Expected hints |
|------|----------|----------------|
| BE-01 | one support only | SUPPORTED; SEEK_FALSIFICATION or replication |
| BE-02 | two correlated supports | SUPPORTED; NOT auto-strengthen |
| BE-03 | two independent supports | SUPPORTED; may HOLD_PROVISIONALLY |
| BE-04 | support + weak disconfirm | WEAKENED/CONFLICTED; SEEK_REPLICATION |
| BE-05 | support + strong independent disconfirm | WEAKENED/FALSIFIED; ABANDON or resolution |
| BE-06 | representation-only support | SUPPORTED unchanged info; reject redundancy |
| BE-07 | conflicting independent | CONFLICTED; SEEK_CONTRADICTION_RESOLUTION |
| BE-08 | invalid disconfirmation | prior unchanged; HOLD |
| BE-09 | non-informative repetition | UNRESOLVED/SUPPORTED; different axis or HOLD |
| BE-10 | supports + major dimension untouched | SUPPORTED; SEEK_FALSIFICATION on untouched axis |
| BE-11 | saturation, no contradiction | SUPPORTED; HOLD_PROVISIONALLY |
| BE-12 | unresolved contradiction | CONFLICTED; SEEK_CONTRADICTION_RESOLUTION |
| BE-13 | no executable high-info experiment | prior state; HOLD_PROVISIONALLY or HOLD_UNRESOLVED |
| BE-14 | falsified then support | FALSIFIED preserved; anomaly flag |
| BE-15 | narrow-after-contradiction temptation | FALSIFIED/CONFLICTED; reject rescue; FORK deferred |

Design artifact: `artifacts/14_bb_epistemic_01_design.json`

---

## 25. Diagnostic application — current proposition (Section 24)

**Evidence 1:** SUPPORTING, full-panel experiment, n=6106, spread≈2.35  
**Evidence 2:** SUPPORTING, independent-episode holdout (exclude 2026-08-02), n=5964, spread≈2.09

| Question | Diagnostic answer |
|----------|-------------------|
| How independent scientifically? | **PARTIAL_REPLICATION** with episode-independence attempt. ~97.7% row overlap. Episode: partial (one date excluded). Sample: low. Measurement: none (same partition/quintile/outcome). Semantic: low (same directional-spread dimension). |
| Uncertainty dimensions covered | Directional effect full market; directional effect holdout without focal date |
| Uncertainty dimensions untouched | Temporal regime, symbol concentration, horizon variation, population subsets, counterexample conditions, alternative explanations, measurement formulation change |
| SEEK_FALSIFICATION still justified? | **On untouched axes yes; generic holdout repeat NO** |
| Another generic holdout redundant? | **Yes** |
| Better falsification axis? | Counterexample search, symbol/date decomposition, regime slice — not another date-exclusion holdout |
| HOLD_PROVISIONALLY justified yet? | **No** — two correlated supports on same measurement; major dimensions open; not saturation |

*Diagnostic from frozen design principles — not tuned to desired answer.*

Design artifact: `artifacts/15_current_proposition_diagnostic.json`

---

## 26. Readiness verdict (Section 25)

### `PARTIALLY_READY`

**Reason:** Ledger fragments exist (two `EpistemicUpdateRecord`s, lineage integrity, experiment hashes, independence metadata from 3I.9). There is **no** `EvidenceSynthesisEngine` to reason over accumulated evidence, apply prior-state-conditioned transitions, assess saturation, or emit `ResearchPriorityDecision` without vote counting.

**Exactly one missing capability:** `EvidenceSynthesisEngine`

Synthesize append-only evidence ledger into: relationship taxonomy, independence profiles, contradiction structure, uncertainty coverage, saturation assessment, prior-state-conditioned epistemic state, and research priority — without N-confirmation rules or scalar confidence.

Design artifact: `artifacts/16_readiness_decision.json`

---

## 27. Minimal 3I.12 boundary (Section 26)

If proceeding from PARTIALLY_READY:

1. Implement **minimal `EvidenceSynthesisEngine`** on abstract **BB-Epistemic-01** fixtures only.
2. Freeze prior-state-conditioned transition table **before** real proposition application.
3. Apply **once diagnostically** to `prop-efb650d9bd5c451f` ledger (no new experiment).
4. Do **not** integrate planner, Challenger, trading, or FORK.
5. Do **not** change OPR generator, falsification generator, selector, or interpretation thresholds.

**Proposed next phase:** Phase 3I.12 — Minimal Evidence Synthesis Engine (abstract fixtures first)

---

## 28. Scope protection (Section 28)

Confirmed **not done:**

- No market experiment executed
- No proposition mutation
- No OPR/falsification generator or selector changes
- No scientific threshold changes
- No observation class additions
- No FORK, planner, Challenger, or trading integration
- No deployment / Streamlit / VPS restart

---

## 29. Final answers A–D

**A. Can Mr.BOT today reason scientifically over multiple pieces of evidence as a body of knowledge?**  
**No.** It reacts correctly to each `ToolResult` independently via frozen single-evidence `transition_mapping` / `decision_mapping`. It cannot synthesize the full ledger.

**B. Can it distinguish genuinely independent support from repeated versions of essentially the same evidence?**  
**Not autonomously.** Taxonomy and `EvidenceIndependenceProfile` are designed and partial metadata exists (3I.9 independence class, experiment content hashes), but no synthesis engine applies them to accumulated evidence.

**C. Can it know a proposition remains uncertain while deciding another experiment is not worth the next unit of research budget?**  
**No.** There is no saturation assessment, no epistemic-vs-priority separation, and no `ResearchPriorityDecision`. Every SUPPORTING → SEEK_FALSIFICATION regardless of ledger.

**D. Smallest missing capability before autonomous multi-evidence behavior?**  
**`EvidenceSynthesisEngine`** — minimal implementation on BB-Epistemic-01 abstract fixtures first, then one diagnostic application to the real proposition ledger.

---

**STOP.** No multi-evidence engine implementation. No additional experiment.
